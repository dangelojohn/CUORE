"""One read-only "full scan": every subsystem the adapter can reach, captured
as from-car observations through :func:`cuore.live.store.record_observation`
so the Scans area, the dossier and the health report all see it without a
mechanic having to drive fifteen separate manual calls.

Everything the car is actually asked goes through the existing
:mod:`cuore.live.ops` functions -- this module adds no new adapter traffic of
its own, only the sequencing, the per-module DID table, and the coverage
rollup. Where ``ops.py`` has no reader at all (Mode 09 calibration IDs,
CVNs, ECU names, in-use performance tracking -- only VIN, PID 02, is wired
up today) that gap is recorded honestly in the ``mode09`` observation rather
than invented.

Because the test suite (and some HTTP/MCP callers) monkeypatch individual
``ops`` functions with canned replies, this module never relies on an
``ops`` call's own internal recording (``ops._observe``) -- a monkeypatched
function skips that silently. Instead every kind named in the spec is
recorded explicitly, here, from whatever the (possibly fake) ``ops`` call
returned. On a real adapter this duplicates a few of ``ops``'s own
recordings (harmless -- the store is an append-only log); in a test it is
the only recording that happens, which is exactly what makes the kinds
checkable.

Resilience: each step is wrapped so one failure (a raised ``LiveError``, or
anything else) is captured in ``steps``/the coverage rows and the scan
continues; an optional ``budget_s`` stops starting new steps once the clock
runs out. The whole-scan guards (MultiEcuScan connected, the live-data
poller holding the adapter) are checked once, up front, via the existing
guards -- a full scan must refuse outright for those, not record a
"coverage gap" and carry on.

--------------------------------------------------------------------------
Guided scan (the coloured-cable workflow)
--------------------------------------------------------------------------

The garage's bypass cables (blue A5 -> CAN-IHS, grey A6 -> CAN-CH) have to be
swapped by hand mid-scan, which used to mean stopping the tool, losing the
sense that anything was "running", and re-starting three separate reads.
``run_guided``/``continue_guided``/``skip_guided``/``abandon_guided`` turn
that into one resumable session, built on exactly the same two building
blocks :func:`run` uses (:func:`_obd_readout`, :func:`_sweep_bus_modules`):

1. ``run_guided(vin)`` declares cable "none" and runs the full CAN-C segment
   (verify, Mode 09, DTCs, every freeze-frame PID, readiness, Mode 06, PID
   snapshot, then the UDS sweep of CAN-C's own modules) -- then pauses,
   returning ``next`` with the colour, bus and module list the mechanic
   needs to fit next.
2. ``continue_guided(scan_id, cable_fitted)`` declares the cable the
   mechanic just fitted (the same ``ops.set_cable`` path every other caller
   uses -- a declaration only, writes stay blocked as always), verifies that
   bus with a passive listen (right for IHS/CH -- both broadcast, unlike the
   gateway-isolated CAN-C), sweeps its modules, and pauses again for the
   next cable -- or, on the final "remove the cable" step, redeclares
   "none" and re-verifies CAN-C, and closes the session.
3. ``skip_guided(scan_id)`` records the segment currently paused on as
   "not reachable: skipped, needs <cable>" -- honest, never invented --
   and moves on.
4. ``abandon_guided(scan_id)`` closes an open session without pretending it
   finished.

Every segment is recorded under the ONE ``scan_id`` picked when
``run_guided`` started, and the ``scan_coverage`` observation (same kind
:func:`run` writes) is rewritten at the end of every segment so it always
describes the whole session so far -- the Scans area and the health report
never see a partial scan as if it were the final word, and never see more
than one scan for what was, start to finish, one session with the owner
swapping cables by hand.

State lives at ``state_dir()/fullscan_guided.json``, nowhere else, so a page
reload or an MCP reconnect resumes exactly where the mechanic left off; the
pause itself holds nothing (no adapter session is open between calls -- see
each function's own docstring).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from . import coverage as coverage_mod
from . import did_catalog
from . import interlock
from . import ops
from . import store
from .addressing import on_bus
from .buses import BUSES, buses_for_cable
from .config import state_dir
from .errors import BadCommand, LinkUnavailable, LiveError, Refused
from ..services.errors import NotFound

#: Cable a bus needs before it is reachable at all (``buses.py`` Table B).
_CABLE_FOR_BUS = {"can_ihs": "blue_a5", "can_ch": "grey_a6"}
_CABLE_LABEL = {"blue_a5": "blue A5 cable", "grey_a6": "grey A6 cable", "none": "no cable"}

#: Per-module channel this scan is willing to read a DID for. The keyword is
#: matched against the catalogued DID *name* -- never a guessed DID, only
#: one already in ``addressing.DIDS``/``did_catalog.EXTRA_DIDS`` (the same
#: registry ``channels.py`` draws on) or a previously learned/accepted DID.
_KNOWN_DID_KEYWORDS = {"ECM": "oil temperature", "TCM": "oil temperature", "BCM": "battery"}

#: Mode 09 PIDs this scan would like to read but ``ops.py`` has no reader
#: for yet -- recorded as an honest gap, never fabricated.
_MODE09_GAPS = ("calibration IDs (PID 04)", "CVNs (PID 06)",
               "ECU names (PID 0A)", "in-use performance tracking / IUPR (PID 08)")


def _last_file() -> Path:
    return state_dir() / "fullscan_last.json"


def _stream_desc() -> str:
    """Best-effort "serial COM3@115200"-shaped tag for the observations this
    module writes itself (see module docstring -- it never opens a session,
    so it cannot read ``sess.stream.describe`` the way ``ops._observe``
    does). Falls back to "" (not from-car) when the port/baud are unknown,
    e.g. every monkeypatched test."""
    try:
        st = ops.status()
        port, baud = st.get("port"), st.get("baud")
        if port and baud:
            return f"serial {port}@{baud}"
    except Exception:  # noqa: BLE001 -- never let the tag break the scan
        pass
    return ""


def _known_did(module: str, vin: str) -> Optional[tuple[int, str, str]]:
    """``(did, name, source)`` for this module's one known channel, or None."""
    kw = _KNOWN_DID_KEYWORDS.get(module)
    if kw:
        for spec in did_catalog.all_dids(module):
            if kw in spec.name.lower():
                return spec.did, spec.name, "catalog"
    if vin:
        try:
            learned = (ops.learned_dids(vin).get("learned") or {}).get(vin) or []
        except Exception:  # noqa: BLE001
            learned = []
        for entry in learned:
            if entry.get("module") == module and entry.get("status") == "accepted":
                try:
                    return int(entry["did"], 16), entry.get("name", ""), "learned"
                except (KeyError, TypeError, ValueError):
                    continue
    return None


#: ISO 14229-1's standard "identification" DID block -- generic across any
#: UDS ECU, never model-specific, and never assumed supported until the
#: module actually answers one. Paired with this project's own catalogued
#: TCM DIDs (``did_catalog.all_dids("TCM")``) as the candidate list for
#: :func:`_tcm_did_candidates`: the whole point of :func:`_tcm_did_discovery`
#: is that it tries ONLY documented candidates, never a blind scan of
#: DID-space (contrast ``readall.discover_dids``'s contiguous-range sweep,
#: a different tool for a different, broader job).
_ISO14229_F1XX_IDS: tuple[tuple[int, str], ...] = (
    (0xF180, "bootSoftwareIdentification"),
    (0xF181, "applicationSoftwareIdentification"),
    (0xF182, "applicationDataIdentification"),
    (0xF183, "bootSoftwareFingerprint"),
    (0xF184, "applicationSoftwareFingerprint"),
    (0xF185, "applicationDataFingerprint"),
    (0xF186, "activeDiagnosticSessionDataIdentifier"),
    (0xF187, "vehicleManufacturerSparePartNumber"),
    (0xF188, "vehicleManufacturerECUSoftwareNumber"),
    (0xF189, "vehicleManufacturerECUSoftwareVersionNumber"),
    (0xF18A, "systemSupplierIdentifier"),
    (0xF18B, "ECUManufacturingDate"),
    (0xF18C, "ECUSerialNumber"),
    (0xF190, "VIN"),
    (0xF191, "vehicleManufacturerECUHardwareNumber"),
    (0xF192, "systemSupplierECUHardwareNumber"),
    (0xF193, "systemSupplierECUHardwareVersionNumber"),
    (0xF194, "systemSupplierECUSoftwareNumber"),
    (0xF195, "systemSupplierECUSoftwareVersionNumber"),
    (0xF197, "systemNameOrEngineType"),
)

#: Per-DID timeout and the hard cap on candidates tried, per the TCM DID
#: discovery requirement this satisfies.
_TCM_DID_DISCOVERY_TIMEOUT_S = 0.3
_TCM_DID_DISCOVERY_MAX = 40


def _tcm_did_candidates() -> list[tuple[int, str]]:
    """Up to :data:`_TCM_DID_DISCOVERY_MAX` ``(did, name)`` candidates for
    :func:`_tcm_did_discovery`: every TCM DID this project already has
    documented (``did_catalog.all_dids("TCM")``, which folds in
    ``addressing.DIDS`` -- TCM's own catalogued rows live there, not in
    ``did_catalog.EXTRA_DIDS``, per that module's own docstring), plus the
    ISO 14229-1 standard identification block above. De-duplicated by DID;
    ``did_catalog``'s own rows win a collision.
    """
    seen: set[int] = set()
    out: list[tuple[int, str]] = []
    for spec in did_catalog.all_dids("TCM", include_diesel=False):
        if spec.did not in seen:
            seen.add(spec.did)
            out.append((spec.did, spec.name))
    for did, name in _ISO14229_F1XX_IDS:
        if did not in seen:
            seen.add(did)
            out.append((did, name))
    return out[:_TCM_DID_DISCOVERY_MAX]


def _tcm_did_discovery_sweep(car_vin: str) -> dict[str, Any]:
    """Read-only UDS ``0x22`` sweep of :func:`_tcm_did_candidates` against
    the TCM, through :func:`ops.module_did_sweep` -- same "this module
    never opens a session itself, it only calls ``ops``" posture as every
    other step in :func:`_obd_readout` (see this module's own docstring),
    which is also exactly what lets this step be checked against a
    monkeypatched ``ops.module_did_sweep`` in the test suite rather than
    a real adapter. Every DID that answers with a positive payload is
    recorded as a *learned* entry
    (:func:`cuore.live.learned.record_did_answer`) -- raw bytes only, kind
    ``"did"``, module ``"TCM"``, scale ``"unknown"``: this sweep finds out
    WHICH DIDs this TCM answers, never what the bytes mean (that still
    needs watching a live MES recording against the raw bytes, same as
    any other learned, unscaled entry). Returns ``{"tried", "answered"}``.
    """
    from . import learned
    candidates = _tcm_did_candidates()
    dids = [f"{did:04X}" for did, _name in candidates]
    result = ops.module_did_sweep("TCM", dids, vin=car_vin,
                                  per_did_timeout=_TCM_DID_DISCOVERY_TIMEOUT_S) or {}
    hits = result.get("hits") or []
    for hit in hits:
        did_hex = hit.get("did", "")
        if did_hex:
            learned.record_did_answer(car_vin, "TCM", did_hex, hit.get("bytes") or [],
                                      source="fullscan_tcm_discovery")
    return {"tried": result.get("tried", len(dids)), "answered": len(hits)}


def _make_step_runner(steps: list[dict[str, Any]], budget_left: Callable[[], bool]):
    """One ``_step(name, fn, *a, **kw)`` closure, shared by :func:`run` and
    the guided-scan functions: calls ``fn``, appends ``{"step", "ok"[,
    "error"]}`` to ``steps``, and never lets one failed step raise out of
    the scan."""

    def _step(name: str, fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
        if not budget_left():
            steps.append({"step": name, "ok": False, "error": "time budget exceeded"})
            return None
        try:
            out = fn(*a, **kw)
            steps.append({"step": name, "ok": True})
            return out
        except LiveError as e:
            steps.append({"step": name, "ok": False, "error": f"{type(e).__name__}: {e}"})
            return None
        except Exception as e:  # noqa: BLE001 -- one bad step must never kill the scan
            steps.append({"step": name, "ok": False, "error": f"{type(e).__name__}: {e}"})
            return None

    return _step


def _obd_readout(vin: str, cable: str, _step: Callable[..., Any],
                 budget_left: Callable[[], bool] = lambda: True,
                 session_counter: Optional[list[int]] = None) -> tuple[str, str]:
    """CAN-C only: verify, adapter identity, Mode 09, DTCs + freeze frame,
    readiness, Mode 06, and a Mode 01 PID snapshot. Returns ``(car_vin,
    stream_desc)`` for every later recording in the same run/segment to
    share. Shared by :func:`run` and ``run_guided``'s segment 1.

    ``session_counter`` (a one-element ``[int]`` box so it accumulates
    across both this function and :func:`_sweep_bus_modules`) is bumped once
    for every call made here that opens exactly one held adapter session --
    see ``run()``'s own docstring note on ``sessions_opened``. Freeze frame
    and the PID snapshot are each ONE such call (:func:`ops.obd_freeze_frames`
    / :func:`ops.obd_pids_snapshot`), not one per PID as before.
    """
    counter = session_counter if session_counter is not None else [0]
    verify = _step("verify_bus can_c", ops.verify_bus, "can_c")
    counter[0] += 1
    probe = _step("probe", ops.probe, allow_while_mes_connected=True)
    counter[0] += 1
    stream_desc = _stream_desc()
    store.record_observation("adapter_identity", {"probe": probe, "verify_can_c": verify},
                             vin=vin, bus="can_c", cable=cable, stream=stream_desc)

    vin_result = _step("obd_vin", ops.obd_vin) or {}
    counter[0] += 1
    car_vin = vin_result.get("vin") or vin

    def _mode09_rest() -> dict[str, Any]:
        # Calibration IDs, CVNs, ECU names and in-use performance counters
        # (EVAP completion rate) through the Mode 09 reader in cuore.live.mode09.
        from . import mode09 as _m09
        with ops._obd_session("fullscan_mode09") as sess:
            return _m09.read_mode09(sess, ["04", "06", "08", "0A"])
    m09 = _step("mode09 04/06/08/0A", _mode09_rest) or {}
    counter[0] += 1
    gaps = [g for g in _MODE09_GAPS if not (m09.get(g) or m09.get("pids", {}).get(g))]
    store.record_observation(
        "mode09", {**vin_result, "mode09": m09, "gaps": gaps,
                   "gap_reason": "PID not answered by the ECM" if gaps else None},
        vin=car_vin, bus="can_c", cable=cable, stream=stream_desc)

    dtc_results: dict[str, dict[str, Any]] = {}
    for kind in ("stored", "pending", "permanent"):
        r = _step(f"obd_dtcs {kind}", ops.obd_dtcs, kind)
        counter[0] += 1
        if r is None:
            continue
        dtc_results[kind] = r
        store.record_observation("obd_dtcs", {"dtc_kind": kind, **r}, vin=car_vin, bus="can_c",
                                 cable=cable, stream=stream_desc)

    supported = _step("obd_supported_pids", ops.obd_supported_pids)
    counter[0] += 1
    stored = dtc_results.get("stored") or {}
    by_ecu_codes: dict[str, list[str]] = {h: c for h, c in (stored.get("by_ecu") or {}).items()
                                          if c}
    if by_ecu_codes and supported:
        by_ecu_pids = supported.get("by_ecu") or {}
        all_pids = sorted({p for h in by_ecu_codes for p in (by_ecu_pids.get(h) or {}).get(
            "pids", [])})
        frames: dict[str, dict[str, Any]] = {h: {} for h in by_ecu_codes}
        if all_pids:
            # ONE held session for every freeze-frame PID this scan wants,
            # across every code -- was one ops.obd_freeze_frame() open PER
            # PID (see this function's own docstring).
            ff = _step("freeze_frame_set (held session, "
                      f"{len(all_pids)} PIDs)", ops.obd_freeze_frames, all_pids) or {}
            counter[0] += 1
            for h, reading_map in (ff.get("by_ecu") or {}).items():
                if h in frames:
                    # Same gate the old per-PID loop used: only a reading that
                    # actually carries "value" (pid "02", the stored DTC
                    # itself, is decoded as a DTC, not a value -- see
                    # ops.obd_freeze_frames).
                    frames[h] = {pid: {"name": r.get("name"), "value": r.get("value"),
                                       "unit": r.get("unit")}
                                for pid, r in reading_map.items() if r.get("value") is not None}
        for h, codes in by_ecu_codes.items():
            for code in codes:
                store.record_observation("freeze_frame",
                                         {"code": code, "ecu": h, "frame": frames.get(h, {})},
                                         vin=car_vin, bus="can_c", cable=cable,
                                         stream=stream_desc)

    readiness = _step("obd_readiness", ops.obd_readiness)
    counter[0] += 1
    if readiness is not None:
        store.record_observation("readiness", readiness, vin=car_vin, bus="can_c", cable=cable,
                                 stream=stream_desc)

    mode06 = _step("obd_mode06", ops.obd_mode06)
    counter[0] += 1
    if mode06 is not None:
        store.record_observation("mode06", mode06, vin=car_vin, bus="can_c", cable=cable,
                                 stream=stream_desc)

    if supported:
        by_ecu_pids = supported.get("by_ecu") or {}
        snapshot: dict[str, dict[str, Any]] = {h: {} for h in by_ecu_pids}
        all_snapshot_pids = sorted({p for info in by_ecu_pids.values() for p in info.get(
            "pids", [])})
        if all_snapshot_pids and budget_left():
            # ONE held session, Session.query_pids() batching <=6 PIDs per
            # request with a per-PID fallback -- was one ops.obd_pid() open
            # PER PID (see this function's own docstring).
            snap = _step("pids_snapshot (held session, query_pids, "
                        f"{len(all_snapshot_pids)} PIDs)", ops.obd_pids_snapshot,
                        all_snapshot_pids) or {}
            counter[0] += 1
            for h, readings in (snap.get("by_ecu") or {}).items():
                if h in snapshot:
                    snapshot[h] = readings
        store.record_observation("pids_snapshot", {"by_ecu": snapshot}, vin=car_vin, bus="can_c",
                                 cable=cable, stream=stream_desc)

    # Read-only TCM DID discovery: a documented-candidates-only 0x22 sweep
    # (see _tcm_did_candidates), for the next guided scan to learn which of
    # them this TCM actually answers -- never a meaning, just which DIDs
    # are live. Skipped, like every other step here, once the time budget
    # is spent; its own failure (e.g. the TCM has no confirmed address) is
    # one coverage-neutral step, never a failed scan.
    if budget_left():
        did_disc = _step("tcm_did_discovery", _tcm_did_discovery_sweep, car_vin)
        counter[0] += 1
        if did_disc is not None:
            store.record_observation("did_discovery", {"module": "TCM", **did_disc},
                                     vin=car_vin, bus="can_c", cable=cable, stream=stream_desc)

    return car_vin, stream_desc


def _sweep_bus_modules(bus_key: str, car_vin: str, cable: str, stream_desc: str, confirm: bool,
                       _step: Callable[..., Any], steps: list[dict[str, Any]],
                       budget_left: Callable[[], bool] = lambda: True,
                       session_counter: Optional[list[int]] = None) -> list[dict[str, Any]]:
    """UDS sweep of every confirmed module on ``bus_key``: DTCs with status
    flags, identity, and the one known DID per module. Returns that bus's
    coverage rows. Assumes the caller has already established the current
    cable reaches this bus -- never checks reachability itself. Shared by
    :func:`run`'s per-bus loop and every guided-scan cable segment.

    ONE held adapter session for the whole bus, via
    :func:`ops.sweep_bus_full` -- was :func:`ops.scan_modules` (one open)
    then :func:`ops.module_identity` (one open per module) then
    :func:`ops.module_did` (one open per module with a known DID); see
    docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md for the timed
    before/after. ``session_counter`` is bumped once here, same convention
    as :func:`_obd_readout`.
    """
    counter = session_counter if session_counter is not None else [0]
    coverage_rows: list[dict[str, Any]] = []

    def _known_did_int(code: str) -> Optional[int]:
        known = _known_did(code, car_vin)
        return known[0] if known else None

    scan_result = _step(f"sweep_bus_full {bus_key}", ops.sweep_bus_full, bus_key, vin=car_vin,
                        mask=0xFF, confirm=confirm, known_did=_known_did_int)
    counter[0] += 1
    if scan_result is None:
        why = steps[-1].get("error", "sweep_bus_full failed") if steps else "sweep_bus_full failed"
        for ecu in on_bus(bus_key):
            coverage_rows.append({"bus": bus_key, "module": ecu.code,
                                  "category": "not_reachable", "why": why,
                                  "active": 0, "history": 0, "not_run": 0})
        return coverage_rows

    for mod in scan_result.get("modules", []):
        code = mod.get("ecu")
        if "skipped" in mod:
            coverage_rows.append({"bus": bus_key, "module": code,
                                  "category": "not_reachable",
                                  "why": "no known address: run discovery",
                                  "active": 0, "history": 0, "not_run": 0})
            continue

        records = mod.get("dtcs") or []
        cls = coverage_mod.classify_records(records)
        if mod.get("error"):
            category, why = "not_reachable", f"ADAPTER/BUS ERROR: {mod['error']}"
        elif mod.get("nrc"):
            category, why = "not_reachable", f"NRC {mod['nrc']}"
        elif mod.get("warning") == "no answer from the module":
            category, why = "silent", mod["warning"]
        else:
            category, why = "answered", None
        row = {"bus": bus_key, "module": code, "category": category, "why": why,
              "active": len(cls["active"]), "history": len(cls["history"]),
              "not_run": cls["not_run_since_clear"]}
        coverage_rows.append(row)

        store.record_observation(
            "module_dtcs",
            {"ecu": code, "bus": bus_key,
             "dtcs": [{"code": r["code"], "status": r["status"], "flags": r["flags"]}
                     for r in records]},
            vin=car_vin, bus=bus_key, cable=cable, stream=stream_desc)

        if category not in ("answered", "silent"):
            continue

        ident = mod.get("identity")
        if ident is not None:
            store.record_observation("module_identity", ident, vin=car_vin, bus=bus_key,
                                     cable=cable, stream=stream_desc)

        known = _known_did(code, car_vin)
        if known is None:
            row["did"] = "UNKNOWN: no known DID in the registry for this module"
        else:
            did_int, did_name, did_source = known
            did_result = mod.get("did")
            if did_result is not None:
                store.record_observation("did", did_result, vin=car_vin, bus=bus_key,
                                         cable=cable, stream=stream_desc)
                row["did"] = {"did": f"{did_int:04X}", "name": did_name, "source": did_source}

    return coverage_rows


def run(vin: str = "", buses: Optional[list[str]] = None, budget_s: Optional[float] = None,
       confirm: bool = False) -> dict[str, Any]:
    """Run the full scan and return (and persist, and record) its result.

    ``buses`` names extra buses to attempt beyond ``can_c`` (default: try
    both ``can_ihs`` and ``can_ch`` -- whichever the currently declared
    cable actually reaches; the other is reported in coverage as not
    reachable, not silently dropped). ``confirm`` is forwarded to every UDS
    call on ``can_ch``, which refuses transmission without it by design
    (brakes/airbags/steering); a refusal there is one isolated coverage row,
    not a failed scan.

    ``result["sessions_opened"]`` counts how many held adapter sessions this
    run actually opened (one per :func:`_obd_readout` call that used to be
    one-per-PID, now one for the whole PID snapshot and one for the whole
    freeze-frame set; one per bus in the sweep below, now one for DTCs +
    identity + DID together instead of one open per module per read) --
    the measurable half of the 2026-10-14 connectivity-review wiring, next
    to ``duration_s``, which was already here.
    """
    t0 = time.monotonic()
    deadline = (t0 + budget_s) if budget_s else None

    # Whole-scan guards -- reuse the existing ones exactly, checked up front
    # so a blocked scan refuses outright instead of limping through steps
    # that would all fail the same way.
    ops._poller_active_guard()
    ms = interlock.mes_status()
    if ms.get("state") == "connected":
        raise LinkUnavailable(
            f"MultiEcuScan is connected to the vehicle (label {ms.get('label')!r}); "
            f"disconnect it before a full scan.")

    scan_id = f"SCAN_{datetime.now().strftime('%y%m%d%H%M')}"
    cable = ops.cable_state().get("cable", "none")
    reachable = {b.key for b in buses_for_cable(cable)}
    wanted_extra = set(buses) if buses else {"can_ihs", "can_ch"}
    attempt = {"can_c"} | (wanted_extra & reachable)

    steps: list[dict[str, Any]] = []

    def _budget_left() -> bool:
        return deadline is None or time.monotonic() <= deadline

    _step = _make_step_runner(steps, _budget_left)
    session_counter = [0]

    # --- 1-4. verify, adapter identity, Mode 09, DTCs/freeze frame, readiness,
    #          Mode 06, PID snapshot -- all on CAN-C. ------------------------
    car_vin, stream_desc = _obd_readout(vin, cable, _step, _budget_left, session_counter)

    # --- 5. UDS sweep: every bus the declared cable reaches ------------------
    coverage_rows: list[dict[str, Any]] = []

    for bus_key in BUSES:
        if bus_key not in attempt:
            needed = _CABLE_FOR_BUS.get(bus_key, "none")
            why = f"needs {_CABLE_LABEL.get(needed, needed)}"
            for ecu in on_bus(bus_key):
                coverage_rows.append({"bus": bus_key, "module": ecu.code,
                                      "category": "not_reachable", "why": why,
                                      "active": 0, "history": 0, "not_run": 0})
            continue

        if not _budget_left():
            for ecu in on_bus(bus_key):
                coverage_rows.append({"bus": bus_key, "module": ecu.code,
                                      "category": "not_reachable", "why": "time budget exceeded",
                                      "active": 0, "history": 0, "not_run": 0})
            continue

        coverage_rows.extend(_sweep_bus_modules(bus_key, car_vin, cable, stream_desc, confirm,
                                                _step, steps, budget_left=_budget_left,
                                                session_counter=session_counter))

    # --- 6. coverage summary ---------------------------------------------------
    totals = {"active": sum(r["active"] for r in coverage_rows),
             "history": sum(r["history"] for r in coverage_rows),
             "not_run": sum(r["not_run"] for r in coverage_rows)}
    duration_s = round(time.monotonic() - t0, 1)
    result = {
        "scan_id": scan_id, "vin": car_vin, "cable": cable,
        "buses_attempted": sorted(attempt), "duration_s": duration_s,
        "sessions_opened": session_counter[0],
        "steps": steps, "coverage": coverage_rows, "counts": totals,
    }
    store.record_observation("scan_coverage", result, vin=car_vin, bus="", cable=cable,
                             stream=stream_desc)

    try:
        _last_file().write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass
    return result


def last() -> dict[str, Any]:
    """The most recent full scan's result, or a note that none has run yet.

    This also reflects a guided scan's progress (see below) -- the guided
    functions rewrite this same file at the end of every segment, so "the
    last full-vehicle scan" means the same thing regardless of which path
    produced it.
    """
    p = _last_file()
    if not p.exists():
        return {"scan_id": None, "note": "no full scan has been run yet"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"scan_id": None, "note": "could not read the last full scan result"}


# ===========================================================================
# Guided scan: one scan session paused at each coloured-cable swap.
# ===========================================================================

_GUIDED_FILE_NAME = "fullscan_guided.json"

#: The four segments in swap order. Index 0 is the one ``run_guided`` itself
#: performs (cable "none", CAN-C in full); the table still lists it so the
#: persisted state and the API/UI can describe the whole session as one
#: ordered list ("segment 2 of 4"). Index 3 is the closing step: no sweep (
#: CAN-C's modules were already fully read at index 0), just redeclaring
#: "none" and re-verifying the bus is still alive with the cable off.
_GUIDED_SEGMENTS: tuple[dict[str, Any], ...] = (
    {"cable": "none", "bus": "can_c"},
    {"cable": "blue_a5", "bus": "can_ihs"},
    {"cable": "grey_a6", "bus": "can_ch"},
    {"cable": "none", "bus": "can_c", "final": True},
)

_GUIDED_CABLE_NAME = {"blue_a5": "BLUE A5", "grey_a6": "GREY A6"}
_GUIDED_BUS_LABEL = {"can_ihs": "CAN-IHS", "can_ch": "CAN-CH", "can_c": "CAN-C"}


def _guided_file() -> Path:
    return state_dir() / _GUIDED_FILE_NAME


def _load_guided() -> Optional[dict[str, Any]]:
    p = _guided_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_guided(state: dict[str, Any]) -> None:
    try:
        _guided_file().write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass


def _elapsed_s(state: dict[str, Any]) -> float:
    """Wall-clock elapsed since the session started -- not
    ``time.monotonic()``, which cannot survive the process restarting
    between a pause and the mechanic pressing Continue."""
    try:
        return round((datetime.now() - datetime.fromisoformat(state["started"])
                     ).total_seconds(), 1)
    except (KeyError, ValueError, TypeError):
        return 0.0


_OPEN_SEGMENT_STATUSES = ("pending", "failed")


def _open_segment_indices(state: dict[str, Any]) -> list[int]:
    """Indices of the cable segments (never the closing step) that still
    need a sweep: not yet attempted, or attempted and silent."""
    return [i for i, seg in enumerate(_GUIDED_SEGMENTS)
            if not seg.get("final") and i < len(state["segments"])
            and state["segments"][i].get("status") in _OPEN_SEGMENT_STATUSES]


def _open_segment_for(state: dict[str, Any], cable: str) -> Optional[int]:
    """The open cable segment that ``cable`` belongs to, or ``None``."""
    for i in _open_segment_indices(state):
        if _GUIDED_SEGMENTS[i]["cable"] == cable:
            return i
    return None


def _next_pending_index(state: dict[str, Any]) -> int:
    """Where the session pauses next: the lowest cable segment still open,
    else the closing "remove the cable" step. Segments may be completed
    out of order (see ``continue_guided``), so this is not "idx + 1"."""
    open_idx = _open_segment_indices(state)
    if open_idx:
        return open_idx[0]
    return len(_GUIDED_SEGMENTS) - 1


def _guided_next(state: dict[str, Any]) -> Optional[dict[str, Any]]:
    """What the mechanic needs to do next, or ``None`` once the session is
    done or abandoned."""
    idx = state.get("pending_index")
    if state.get("status") != "paused" or idx is None:
        return None
    seg = _GUIDED_SEGMENTS[idx]
    cable, bus_key = seg["cable"], seg["bus"]
    if seg.get("final"):
        return {"cable": "none", "bus": "can_c", "modules": [],
                "instruction": "Remove the cable, then press Continue"}
    modules = [{"code": m.code, "name": m.name} for m in on_bus(bus_key)]
    if state["segments"][idx].get("status") == "failed":
        return {"cable": cable, "bus": bus_key, "modules": modules,
               "instruction": f"{_GUIDED_BUS_LABEL[bus_key]} was silent -- check the "
                              f"{_GUIDED_CABLE_NAME[cable]} cable is seated, the adapter switch "
                              f"is on HS and the ignition is on, then press Continue to retry, "
                              f"or Skip"}
    return {"cable": cable, "bus": bus_key, "modules": modules,
           "instruction": f"Fit the {_GUIDED_CABLE_NAME[cable]} cable "
                          f"({_GUIDED_BUS_LABEL[bus_key]}), then press Continue"}


def _guided_view(state: dict[str, Any]) -> dict[str, Any]:
    """The public shape returned by every guided-scan function and served by
    the API/MCP/wizard. ``segment_done`` lists the bus keys fully read so
    far (the spec's own minimal pause shape); ``segments`` is the richer
    per-segment table the wizard page renders as a progress list."""
    totals = {"active": sum(r["active"] for r in state["coverage"]),
             "history": sum(r["history"] for r in state["coverage"]),
             "not_run": sum(r["not_run"] for r in state["coverage"])}
    segment_done = [seg["bus"] for seg in state["segments"] if seg["status"] == "done"]
    return {**state, "segment_done": segment_done, "next": _guided_next(state),
           "counts": totals}


def _require_guided(scan_id: str) -> dict[str, Any]:
    state = _load_guided()
    if state is None:
        raise NotFound("no guided scan is open; start one first")
    if state["scan_id"] != scan_id:
        raise BadCommand(f"scan_id {scan_id!r} does not match the open guided scan "
                         f"{state['scan_id']!r}")
    if state.get("status") != "paused":
        raise BadCommand(f"guided scan {scan_id!r} is {state.get('status')}, not paused")
    return state


def _record_guided_coverage(state: dict[str, Any]) -> None:
    """Rewrite the ``scan_coverage`` observation (same kind :func:`run`
    writes, and the same last-scan file) so it always describes the whole
    guided session so far -- called at the end of every segment, skip and
    abandon, never left stale for the Scans area or the health report to
    read a half-finished picture as the final one."""
    totals = {"active": sum(r["active"] for r in state["coverage"]),
             "history": sum(r["history"] for r in state["coverage"]),
             "not_run": sum(r["not_run"] for r in state["coverage"])}
    buses_done = sorted({seg["bus"] for seg in state["segments"] if seg["status"] == "done"})
    result = {
        "scan_id": state["scan_id"], "vin": state["vin"], "cable": state["cable"],
        "buses_attempted": buses_done, "duration_s": _elapsed_s(state),
        "sessions_opened": state.get("session_opens", 0),
        "steps": state["steps"], "coverage": state["coverage"], "counts": totals,
        "guided": True, "guided_status": state["status"],
    }
    store.record_observation("scan_coverage", result, vin=state["vin"], bus="",
                             cable=state["cable"], stream=state["stream"])
    try:
        _last_file().write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass


def run_guided(vin: str = "") -> dict[str, Any]:
    """Start a guided scan: segment 1 (cable "none", CAN-C in full) runs
    immediately, then the session pauses for the blue A5 cable. Refuses
    outright (same whole-scan guards as :func:`run`, nothing recorded) if a
    guided session is already open -- :func:`continue_guided`,
    :func:`skip_guided` or :func:`abandon_guided` it first.
    """
    existing = _load_guided()
    if existing is not None and existing.get("status") == "paused":
        raise Refused(
            f"a guided scan ({existing['scan_id']}) is already open; continue it, skip its "
            f"current step, or abandon it before starting a new one.")

    ops._poller_active_guard()
    ms = interlock.mes_status()
    if ms.get("state") == "connected":
        raise LinkUnavailable(
            f"MultiEcuScan is connected to the vehicle (label {ms.get('label')!r}); "
            f"disconnect it before a guided scan.")

    scan_id = f"SCAN_{datetime.now().strftime('%y%m%d%H%M')}"
    started = datetime.now().isoformat(timespec="seconds")

    cable = ops.set_cable("none").get("cable", "none")
    steps: list[dict[str, Any]] = []
    _step = _make_step_runner(steps, lambda: True)
    session_counter = [0]

    car_vin, stream_desc = _obd_readout(vin, cable, _step, session_counter=session_counter)
    coverage_rows = _sweep_bus_modules("can_c", car_vin, cable, stream_desc, False, _step, steps,
                                       session_counter=session_counter)

    # The other two buses are not reachable until their cable is fitted --
    # a pending gap, not a failure, so it is recorded the same honest way
    # run()'s own "needs <cable>" rows are.
    for seg in _GUIDED_SEGMENTS[1:3]:  # blue_a5/can_ihs, grey_a6/can_ch
        for ecu in on_bus(seg["bus"]):
            coverage_rows.append({"bus": seg["bus"], "module": ecu.code,
                                  "category": "not_reachable",
                                  "why": f"needs {_CABLE_LABEL[seg['cable']]}",
                                  "active": 0, "history": 0, "not_run": 0})

    state = {
        "scan_id": scan_id, "vin": car_vin, "started": started, "stream": stream_desc,
        "cable": cable, "status": "paused", "pending_index": 1,
        "segments": [
            {"n": 1, "cable": "none", "bus": "can_c", "status": "done", "why": None},
            {"n": 2, "cable": "blue_a5", "bus": "can_ihs", "status": "pending", "why": None},
            {"n": 3, "cable": "grey_a6", "bus": "can_ch", "status": "pending", "why": None},
            {"n": 4, "cable": "none", "bus": "can_c", "status": "pending", "why": None},
        ],
        "steps": steps, "coverage": coverage_rows, "session_opens": session_counter[0],
    }
    _save_guided(state)
    _record_guided_coverage(state)
    return _guided_view(state)


def guided_state() -> dict[str, Any]:
    """The open (or most recently closed) guided scan, or a plain "none
    open" note -- never a 404 just because nothing has started yet."""
    state = _load_guided()
    if state is None:
        return {"scan_id": None, "status": None, "note": "no guided scan is open"}
    return _guided_view(state)


def continue_guided(scan_id: str, cable_fitted: str) -> dict[str, Any]:
    """Declare the cable the mechanic just fitted (or, on the final step,
    that it has been removed), verify its bus, sweep its modules, and pause
    again for the next step -- or close the session on the final step.

    ``cable_fitted`` must match what the open session is actually waiting
    for (``state["next"]["cable"]``); a mismatch is a caller error
    (``BadCommand``), not silently accepted, since declaring the wrong
    cable would scan the wrong bus under the wrong label.
    """
    state = _require_guided(scan_id)
    idx = state["pending_index"]
    seg = _GUIDED_SEGMENTS[idx]
    if cable_fitted != seg["cable"]:
        # Out of order is fine as long as the fitted cable's own segment is
        # still open (pending or failed): a mechanic who could not get the
        # body bus to answer and has already swapped to the grey cable is
        # not sent back to refit the blue one. The pause comes back to the
        # lowest unfinished segment afterwards, so nothing is lost.
        alt = _open_segment_for(state, cable_fitted)
        if alt is None:
            open_cables = sorted({_GUIDED_SEGMENTS[i]["cable"]
                                  for i in _open_segment_indices(state)})
            raise BadCommand(f"guided scan {scan_id!r} is waiting for cable {seg['cable']!r} "
                             f"(got {cable_fitted!r}); cables still open: {open_cables}")
        idx, seg = alt, _GUIDED_SEGMENTS[alt]

    if not seg.get("final"):
        ms = interlock.mes_status()
        if ms.get("state") == "connected":
            raise LinkUnavailable(
                f"MultiEcuScan is connected to the vehicle (label {ms.get('label')!r}); "
                f"disconnect it before continuing the guided scan.")

    cable = ops.set_cable(cable_fitted).get("cable", cable_fitted)
    state["cable"] = cable
    steps: list[dict[str, Any]] = state["steps"]
    _step = _make_step_runner(steps, lambda: True)

    session_counter = [state.get("session_opens", 0)]
    verify = _step(f"verify_bus {seg['bus']}", ops.verify_bus, seg["bus"])
    session_counter[0] += 1
    store.record_observation("adapter_identity", {f"verify_{seg['bus']}": verify},
                             vin=state["vin"], bus=seg["bus"], cable=cable, stream=state["stream"])

    if seg.get("final"):
        # CAN-C's own modules were already fully read in segment 1; this
        # step only proves the bus is still alive with the cable off.
        state["segments"][idx]["status"] = "done"
        state["status"] = "done"
        state["pending_index"] = None
    else:
        # Drop this bus's "not reachable: needs <cable>" placeholder rows
        # from the pause, then sweep it for real.
        state["coverage"] = [r for r in state["coverage"] if r["bus"] != seg["bus"]]
        new_rows = _sweep_bus_modules(seg["bus"], state["vin"], cable, state["stream"], False,
                                      _step, steps, session_counter=session_counter)
        state["coverage"].extend(new_rows)
        sweep_name = f"sweep_bus_full {seg['bus']}"
        failed = next((s for s in reversed(steps) if s["step"] == sweep_name), {})
        if failed.get("ok") is False:
            # Nothing answered (bus silent / sweep refused): not a swept bus.
            # Stay on this segment so the same cable step is offered again.
            state["segments"][idx]["status"] = "failed"
            state["segments"][idx]["why"] = failed.get("error", "sweep failed")
        else:
            state["segments"][idx]["status"] = "done"
            state["segments"][idx]["why"] = None
            state["pending_index"] = _next_pending_index(state)
    state["session_opens"] = session_counter[0]

    _save_guided(state)
    _record_guided_coverage(state)
    return _guided_view(state)


def skip_guided(scan_id: str) -> dict[str, Any]:
    """Skip the segment currently paused on -- the mechanic has no cable on
    hand, or chooses not to fit it. Recorded honestly as "not reachable:
    skipped, needs <cable>" for every module on that bus, never silently
    dropped from coverage. Only the two cable segments can be skipped;
    there is nothing to skip on the closing "remove the cable" step.
    """
    state = _require_guided(scan_id)
    idx = state["pending_index"]
    seg = _GUIDED_SEGMENTS[idx]
    if seg.get("final"):
        raise BadCommand('the final step only redeclares "none" and re-verifies CAN-C; '
                         "there is nothing to skip")

    why = f"skipped, needs {_CABLE_LABEL[seg['cable']]}"
    state["coverage"] = [r for r in state["coverage"] if r["bus"] != seg["bus"]]
    for ecu in on_bus(seg["bus"]):
        state["coverage"].append({"bus": seg["bus"], "module": ecu.code,
                                  "category": "not_reachable",
                                  "why": f"not reachable: {why}",
                                  "active": 0, "history": 0, "not_run": 0})
    state["segments"][idx]["status"] = "skipped"
    state["segments"][idx]["why"] = why
    state["pending_index"] = _next_pending_index(state)

    _save_guided(state)
    _record_guided_coverage(state)
    return _guided_view(state)


def abandon_guided(scan_id: str) -> dict[str, Any]:
    """Close an open guided scan honestly: marks it abandoned rather than
    deleting it, so the Scans area still shows exactly what was and was not
    captured before the mechanic stopped. Idempotent -- abandoning a
    session that already finished or was already abandoned just returns its
    current view."""
    state = _load_guided()
    if state is None:
        raise NotFound("no guided scan is open; nothing to abandon")
    if state["scan_id"] != scan_id:
        raise BadCommand(f"scan_id {scan_id!r} does not match the open guided scan "
                         f"{state['scan_id']!r}")
    if state.get("status") == "paused":
        state["status"] = "abandoned"
        state["pending_index"] = None
        _save_guided(state)
        _record_guided_coverage(state)
    return _guided_view(state)


__all__ = ["run", "last", "run_guided", "guided_state", "continue_guided", "skip_guided",
           "abandon_guided"]
