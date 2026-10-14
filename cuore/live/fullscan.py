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
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import coverage as coverage_mod
from . import did_catalog
from . import interlock
from . import ops
from . import store
from .addressing import on_bus
from .buses import BUSES, buses_for_cable
from .config import state_dir
from .errors import LinkUnavailable, LiveError

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
    stream_desc = ""

    def _budget_left() -> bool:
        return deadline is None or time.monotonic() <= deadline

    def _step(name: str, fn, *a, **kw):
        if not _budget_left():
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

    # --- 1. verify can_c, adapter identity, voltage -------------------------
    verify = _step("verify_bus can_c", ops.verify_bus, "can_c")
    probe = _step("probe", ops.probe, allow_while_mes_connected=True)
    stream_desc = _stream_desc()
    store.record_observation("adapter_identity", {"probe": probe, "verify_can_c": verify},
                             vin=vin, bus="can_c", cable=cable, stream=stream_desc)

    # --- 2. Mode 09 -----------------------------------------------------------
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

    # --- 3. Mode 03/07/0A DTCs, then freeze frame for every supported PID ----
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

    # --- 4. readiness, Mode 06, Mode 01 snapshot of every supported PID ------
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
            if not _budget_left():
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

        scan_result = _step(f"scan_modules {bus_key}", ops.scan_modules, bus_key, vin=car_vin,
                            mask=0xFF, confirm=confirm, detail=True)
        if scan_result is None:
            why = steps[-1].get("error", "scan_modules failed") if steps else "scan_modules failed"
            for ecu in on_bus(bus_key):
                coverage_rows.append({"bus": bus_key, "module": ecu.code,
                                      "category": "not_reachable", "why": why,
                                      "active": 0, "history": 0, "not_run": 0})
            continue

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
            coverage_rows.append({"bus": bus_key, "module": code, "category": category,
                                  "why": why, "active": len(cls["active"]),
                                  "history": len(cls["history"]),
                                  "not_run": cls["not_run_since_clear"]})

            store.record_observation(
                "module_dtcs",
                {"ecu": code, "bus": bus_key,
                 "dtcs": [{"code": r["code"], "status": r["status"], "flags": r["flags"]}
                         for r in records]},
                vin=car_vin, bus=bus_key, cable=cable, stream=stream_desc)

            if category not in ("answered", "silent") or not _budget_left():
                continue

            ident = _step(f"module_identity {code}", ops.module_identity, code, vin=car_vin,
                         confirm=confirm)
            if ident is not None:
                store.record_observation("module_identity", ident, vin=car_vin, bus=bus_key,
                                         cable=cable, stream=stream_desc)

            known = _known_did(code, car_vin)
            if known is None:
                coverage_rows[-1]["did"] = "UNKNOWN: no known DID in the registry for this module"
            else:
                did_int, did_name, did_source = known
                did_result = _step(f"module_did {code} {did_int:04X}", ops.module_did, code,
                                   f"{did_int:04X}", vin=car_vin, confirm=confirm)
                if did_result is not None:
                    store.record_observation("did", did_result, vin=car_vin, bus=bus_key,
                                             cable=cable, stream=stream_desc)
                    coverage_rows[-1]["did"] = {"did": f"{did_int:04X}", "name": did_name,
                                                "source": did_source}

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
    """The most recent full scan's result, or a note that none has run yet."""
    p = _last_file()
    if not p.exists():
        return {"scan_id": None, "note": "no full scan has been run yet"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"scan_id": None, "note": "could not read the last full scan result"}


__all__ = ["run", "last"]
