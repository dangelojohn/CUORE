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
                 budget_left: Callable[[], bool] = lambda: True) -> tuple[str, str]:
    """CAN-C only: verify, adapter identity, Mode 09, DTCs + freeze frame,
    readiness, Mode 06, and a Mode 01 PID snapshot. Returns ``(car_vin,
    stream_desc)`` for every later recording in the same run/segment to
    share. Shared by :func:`run` and ``run_guided``'s segment 1."""
    verify = _step("verify_bus can_c", ops.verify_bus, "can_c")
    probe = _step("probe", ops.probe, allow_while_mes_connected=True)
    stream_desc = _stream_desc()
    store.record_observation("adapter_identity", {"probe": probe, "verify_can_c": verify},
                             vin=vin, bus="can_c", cable=cable, stream=stream_desc)

    vin_result = _step("obd_vin", ops.obd_vin) or {}
    car_vin = vin_result.get("vin") or vin

    def _mode09_rest() -> dict[str, Any]:
        # Calibration IDs, CVNs, ECU names and in-use performance counters
        # (EVAP completion rate) through the Mode 09 reader in cuore.live.mode09.
        from . import mode09 as _m09
        with ops._obd_session("fullscan_mode09") as sess:
            return _m09.read_mode09(sess, ["04", "06", "08", "0A"])
    m09 = _step("mode09 04/06/08/0A", _mode09_rest) or {}
    gaps = [g for g in _MODE09_GAPS if not (m09.get(g) or m09.get("pids", {}).get(g))]
    store.record_observation(
        "mode09", {**vin_result, "mode09": m09, "gaps": gaps,
                   "gap_reason": "PID not answered by the ECM" if gaps else None},
        vin=car_vin, bus="can_c", cable=cable, stream=stream_desc)

    dtc_results: dict[str, dict[str, Any]] = {}
    for kind in ("stored", "pending", "permanent"):
        r = _step(f"obd_dtcs {kind}", ops.obd_dtcs, kind)
        if r is None:
            continue
        dtc_results[kind] = r
        store.record_observation("obd_dtcs", {"dtc_kind": kind, **r}, vin=car_vin, bus="can_c",
                                 cable=cable, stream=stream_desc)

    supported = _step("obd_supported_pids", ops.obd_supported_pids)
    stored = dtc_results.get("stored") or {}
    by_ecu_codes: dict[str, list[str]] = {h: c for h, c in (stored.get("by_ecu") or {}).items()
                                          if c}
    if by_ecu_codes and supported:
        by_ecu_pids = supported.get("by_ecu") or {}
        all_pids = sorted({p for h in by_ecu_codes for p in (by_ecu_pids.get(h) or {}).get(
            "pids", [])})
        frames: dict[str, dict[str, Any]] = {h: {} for h in by_ecu_codes}
        for pid in all_pids:
            ff = _step(f"freeze_frame {pid}", ops.obd_freeze_frame, pid)
            if not ff:
                continue
            for h, reading in (ff.get("by_ecu") or {}).items():
                if h in frames and isinstance(reading, dict) and "value" in reading:
                    frames[h][pid] = {"name": ff.get("name"), "value": reading.get("value"),
                                      "unit": reading.get("unit")}
        for h, codes in by_ecu_codes.items():
            for code in codes:
                store.record_observation("freeze_frame",
                                         {"code": code, "ecu": h, "frame": frames.get(h, {})},
                                         vin=car_vin, bus="can_c", cable=cable,
                                         stream=stream_desc)

    readiness = _step("obd_readiness", ops.obd_readiness)
    if readiness is not None:
        store.record_observation("readiness", readiness, vin=car_vin, bus="can_c", cable=cable,
                                 stream=stream_desc)

    mode06 = _step("obd_mode06", ops.obd_mode06)
    if mode06 is not None:
        store.record_observation("mode06", mode06, vin=car_vin, bus="can_c", cable=cable,
                                 stream=stream_desc)

    if supported:
        by_ecu_pids = supported.get("by_ecu") or {}
        snapshot: dict[str, dict[str, Any]] = {h: {} for h in by_ecu_pids}
        all_snapshot_pids = sorted({p for info in by_ecu_pids.values() for p in info.get(
            "pids", [])})
        for pid in all_snapshot_pids:
            if not budget_left():
                break
            r = _step(f"read_pid {pid}", ops.obd_pid, pid)
            if not r:
                continue
            for h, reading in (r.get("by_ecu") or {}).items():
                if h in snapshot and isinstance(reading, dict):
                    snapshot[h][pid] = {"name": r.get("name"), "value": reading.get("value"),
                                        "unit": reading.get("unit")}
        store.record_observation("pids_snapshot", {"by_ecu": snapshot}, vin=car_vin, bus="can_c",
                                 cable=cable, stream=stream_desc)

    return car_vin, stream_desc


def _sweep_bus_modules(bus_key: str, car_vin: str, cable: str, stream_desc: str, confirm: bool,
                       _step: Callable[..., Any], steps: list[dict[str, Any]],
                       budget_left: Callable[[], bool] = lambda: True) -> list[dict[str, Any]]:
    """UDS sweep of every confirmed module on ``bus_key``: DTCs with status
    flags, identity, and the one known DID per module. Returns that bus's
    coverage rows. Assumes the caller has already established the current
    cable reaches this bus -- never checks reachability itself. Shared by
    :func:`run`'s per-bus loop and every guided-scan cable segment."""
    coverage_rows: list[dict[str, Any]] = []
    scan_result = _step(f"scan_modules {bus_key}", ops.scan_modules, bus_key, vin=car_vin,
                        mask=0xFF, confirm=confirm, detail=True)
    if scan_result is None:
        why = steps[-1].get("error", "scan_modules failed") if steps else "scan_modules failed"
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

        if category not in ("answered", "silent") or not budget_left():
            continue

        ident = _step(f"module_identity {code}", ops.module_identity, code, vin=car_vin,
                     confirm=confirm)
        if ident is not None:
            store.record_observation("module_identity", ident, vin=car_vin, bus=bus_key,
                                     cable=cable, stream=stream_desc)

        known = _known_did(code, car_vin)
        if known is None:
            row["did"] = "UNKNOWN: no known DID in the registry for this module"
        else:
            did_int, did_name, did_source = known
            did_result = _step(f"module_did {code} {did_int:04X}", ops.module_did, code,
                               f"{did_int:04X}", vin=car_vin, confirm=confirm)
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

    # --- 1-4. verify, adapter identity, Mode 09, DTCs/freeze frame, readiness,
    #          Mode 06, PID snapshot -- all on CAN-C. ------------------------
    car_vin, stream_desc = _obd_readout(vin, cable, _step, _budget_left)

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
                                                _step, steps, budget_left=_budget_left))

    # --- 6. coverage summary ---------------------------------------------------
    totals = {"active": sum(r["active"] for r in coverage_rows),
             "history": sum(r["history"] for r in coverage_rows),
             "not_run": sum(r["not_run"] for r in coverage_rows)}
    duration_s = round(time.monotonic() - t0, 1)
    result = {
        "scan_id": scan_id, "vin": car_vin, "cable": cable,
        "buses_attempted": sorted(attempt), "duration_s": duration_s,
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

    car_vin, stream_desc = _obd_readout(vin, cable, _step)
    coverage_rows = _sweep_bus_modules("can_c", car_vin, cable, stream_desc, False, _step, steps)

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
        "steps": steps, "coverage": coverage_rows,
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
        raise BadCommand(f"guided scan {scan_id!r} is waiting for cable {seg['cable']!r} "
                         f"(got {cable_fitted!r})")

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

    verify = _step(f"verify_bus {seg['bus']}", ops.verify_bus, seg["bus"])
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
                                      _step, steps)
        state["coverage"].extend(new_rows)
        state["segments"][idx]["status"] = "done"
        state["pending_index"] = idx + 1

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
    state["pending_index"] = idx + 1

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
