"""Whole-vehicle coverage: every bus, every module, one tracked session.

The STN1170 has one CAN peripheral, so reading the whole car is sequential:
CAN-C with no cable, CAN-CH through the grey A6, CAN-IHS through the blue A5
(GIORGIO_MODULE_MAP.md, Table B "Hard constraint"). Each cable change is a
re-plug on a live bus, and the platform notes record that re-plugs and serial
UDS sweeps both *manufacture* bystander codes (-87 / -2F). A tool that just
concatenates three scans hands those to the technician as faults.

So the session is shaped around that:

1. ``c_first``  CAN-C, no cable. The baseline, read before anything is
   re-plugged. Every other pass is refused until it is done.
2. ``ch``       CAN-CH, grey A6. Brakes, airbags, steering: every request
   needs explicit confirmation, which the transport already enforces.
3. ``ihs``      CAN-IHS, blue A5. Never scanned on this car; full sweep.
4. ``c_final``  CAN-C again, cable removed. Diffed against ``c_first``:
   an active code that appears between the two was set during this session
   and is reported as a likely bystander, not a fault.

Nothing here clears a code or writes to a module. State is a JSON file in
the cuore state directory so a phone can drive the passes one request at a
time while the technician swaps cables.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from . import audit
from . import store
from .addressing import MODULES, ECUAddress, on_bus
from .buses import BUSES, PIN_1_9_WARNING
from .config import state_dir
from .errors import BadCommand, Refused

_LOCK = threading.Lock()
#: Held for the whole of a pass. A double-click must not sweep a bus twice
#: (on CAN-CH that is the brakes and airbag bus) or lose one result.
_RUN_LOCK = threading.Lock()

#: UDS status bits that mean "this is a fault now": testFailed, pendingDTC,
#: confirmedDTC. ``testFailedSinceLastClear`` alone is history.
ACTIVE_MASK = 0x01 | 0x04 | 0x08
HISTORY_BIT = 0x20
NOT_RUN_SINCE_CLEAR_BIT = 0x10


@dataclass(frozen=True)
class Pass:
    key: str
    bus: str
    cable: str
    title: str
    discover: bool
    checklist: tuple[str, ...]


_FEPS = ("The vLinker FS can put 18 V on OBD pin 13, which is CAN-CH(-) on this car. "
         "Never issue a FEPS or programming-voltage command during this pass.")

PASSES: tuple[Pass, ...] = (
    Pass("c_first", "can_c", "none", "Main bus, no cable (baseline)", True, (
        "Plain adapter, no coloured cable. HS/MS switch on HS.",
        "Ignition ON. Engine running is better for network codes: several "
        "lost-communication codes set only with the key on and the engine off.",
        "MultiEcuScan disconnected from the adapter.",
        "Do not clear any codes until the final pass is done.",
    )),
    Pass("ch", "can_ch", "grey_a6", "Chassis bus, grey A6 cable", True, (
        "Continuity-check the grey cable first: " + PIN_1_9_WARNING,
        "Fit the grey A6 between the adapter and the car, then declare it.",
        "This bus carries brakes, airbags and steering. Every request needs "
        "confirmation; the reads are read-only.",
        _FEPS,
    )),
    Pass("ihs", "can_ihs", "blue_a5", "Body bus, blue A5 cable", True, (
        "Continuity-check the blue cable first: " + PIN_1_9_WARNING,
        "Fit the blue A5, then declare it. The bus runs at 125 kbps; the route "
        "has never been tested on this car, so a silent result is information.",
        "Full address sweep: nothing on this bus has a known address yet.",
    )),
    Pass("c_final", "can_c", "none", "Main bus re-read, cable removed", False, (
        "Remove the coloured cable and declare 'none'.",
        "This re-read is compared with the baseline to catch codes the cable "
        "changes or the sweep itself set.",
    )),
)
PASS_BY_KEY = {p.key: p for p in PASSES}


# --- persistence ---------------------------------------------------------------

def path() -> Path:
    return state_dir() / "coverage.json"


def _load() -> Optional[dict[str, Any]]:
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(sess: dict[str, Any]) -> None:
    path().write_text(json.dumps(sess, indent=2, default=str), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- pure helpers -----------------------------------------------------------------

def classify_records(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Split a UDS 19 02 block into active faults and history.

    The ECM alone tracks 278 codes and reports every one; "codes in the
    reply" is not "faults on the car". Only the status byte says which.
    """
    active, history, not_run = [], [], 0
    for rec in records:
        st = int(rec.get("status") or 0)
        if st & ACTIVE_MASK:
            active.append(rec["code"])
        elif st & HISTORY_BIT:
            history.append(rec["code"])
        if st & NOT_RUN_SINCE_CLEAR_BIT:
            not_run += 1
    return {"active": sorted(active), "history": sorted(history),
            "tracked": len(records), "not_run_since_clear": not_run}


def bystander_diff(first: dict[str, list[str]], final: dict[str, list[str]]
                   ) -> list[dict[str, Any]]:
    """Per-module active-code changes between the two CAN-C passes."""
    out = []
    for code in sorted(set(first) | set(final)):
        a, b = set(first.get(code, [])), set(final.get(code, []))
        if a == b:
            continue
        out.append({
            "module": code,
            "appeared": sorted(b - a),
            "gone": sorted(a - b),
            "reading": (
                "Codes that appeared between the baseline and the re-read were set "
                "during this session, by a cable re-plug or the sweep itself. Treat "
                "them as bystanders; do not chase them."
                if b - a else
                "Codes active at baseline but not on re-read: intermittent, or "
                "their monitor re-ran and passed. Not proof of repair."),
        })
    return out


# --- session lifecycle ----------------------------------------------------------

def start(vin: str, engine_running: Optional[bool] = None) -> dict[str, Any]:
    if not vin or len(vin) != 17:
        raise BadCommand("start needs the 17-character VIN of the car being covered")
    sess = {
        "id": _now(), "vin": vin.upper(), "started": _now(),
        "engine_running": engine_running,
        "passes": {p.key: {"status": "pending"} for p in PASSES},
        "finished": False,
    }
    with _LOCK:
        _save(sess)
    audit.record("coverage_start", vin=sess["vin"])
    return status()


def current() -> Optional[dict[str, Any]]:
    with _LOCK:
        return _load()


def _require() -> dict[str, Any]:
    sess = current()
    if not sess:
        raise Refused("no coverage session; start one with the car's VIN")
    return sess


def next_pass(sess: dict[str, Any]) -> Optional[Pass]:
    for p in PASSES:
        if sess["passes"][p.key]["status"] == "pending":
            return p
    return None


def _gate(sess: dict[str, Any], p: Pass, cable: str) -> None:
    base = sess["passes"]["c_first"]["status"]
    if p.key != "c_first" and base != "done":
        raise Refused("read the CAN-C baseline first: every later pass involves a re-plug, "
                      "and codes set by re-plugging can only be told apart from real ones "
                      "against a baseline taken before it")
    if p.key == "c_final":
        others = [k for k in ("ch", "ihs") if sess["passes"][k]["status"] == "pending"]
        if others:
            raise Refused(f"run or skip {', '.join(others)} before the final re-read")
    if cable != p.cable:
        raise Refused(f"pass {p.key!r} needs cable {p.cable!r} but {cable!r} is declared; "
                      f"fit it and declare it first")


def _unaddressed(bus_key: str, vin: str) -> list[ECUAddress]:
    known = store.confirmed_targets(vin)
    return [m for m in on_bus(bus_key) if not m.usable and m.code not in known]


def run_pass(key: str, *, ops: Any, confirm: bool = False, seconds: float = 3.0,
             discover: Optional[bool] = None,
             per_target_timeout: float = 0.25) -> dict[str, Any]:
    """Run one pass: passive verify, address discovery, then a DTC read.

    ``ops`` is :mod:`cuore.live.ops`, passed in rather than imported so this
    module stays free of the transport and is testable with a fake.
    """
    p = PASS_BY_KEY.get(key)
    if p is None:
        raise BadCommand(f"unknown pass {key!r}; one of {list(PASS_BY_KEY)}")
    if not _RUN_LOCK.acquire(blocking=False):
        raise Refused("a coverage pass is already running; wait for it to finish")
    try:
        return _run_pass_locked(p, ops=ops, confirm=confirm, seconds=seconds,
                                discover=discover, per_target_timeout=per_target_timeout)
    finally:
        _RUN_LOCK.release()


def _run_pass_locked(p: Pass, *, ops: Any, confirm: bool, seconds: float,
                     discover: Optional[bool], per_target_timeout: float) -> dict[str, Any]:
    sess = _require()
    if sess["passes"][p.key]["status"] != "pending":
        raise Refused(f"pass {p.key!r} is already {sess['passes'][p.key]['status']}; "
                      f"discard the session to run it again")
    _gate(sess, p, ops.cable_state()["cable"])
    vin = sess["vin"]
    rec: dict[str, Any] = {"status": "running", "at": _now(), "bus": p.bus, "cable": p.cable}

    ver = ops.verify_bus(p.bus, seconds=seconds)
    rec["verify"] = {k: ver.get(k) for k in ("verified", "frames", "rate_hz", "ids",
                                              "stn_protocol", "error", "note")}
    if not ver.get("verified"):
        rec["status"] = "silent"
        rec["reading"] = ("No traffic on this bus. Check the cable is fitted and declared, "
                          "the adapter's HS/MS switch, seating, and the ignition. Silence is "
                          "not 'no faults'.")
        return _store_pass(sess, p, rec)

    do_discover = p.discover if discover is None else discover
    missing = _unaddressed(p.bus, vin)
    if do_discover and missing:
        present_known = [m for m in missing if m.present == "confirmed"]
        stop = len(present_known) if len(present_known) == len(missing) else None
        disc = ops.discover(p.bus, vin=vin, confirm=confirm, stop_after=stop,
                            per_target_timeout=per_target_timeout)
        rec["discover"] = {"tried": disc.get("tried"), "seconds": disc.get("seconds"),
                           "hits": disc.get("hits")}

    scan = ops.scan_modules(p.bus, vin=vin, confirm=confirm)
    mods: dict[str, Any] = {}
    for m in scan.get("modules", []):
        code = m.get("ecu")
        if m.get("skipped"):
            mods[code] = {"read": False, "reason": m["skipped"]}
            continue
        entry: dict[str, Any] = {"read": bool(m.get("codes") is not None and not m.get("error")),
                                 "error": m.get("error"), "nrc": m.get("nrc"),
                                 "warning": m.get("warning")}
        entry.update(classify_records(m.get("dtcs") or []))
        if m.get("codes") is None:
            entry["read"] = False
        mods[code] = entry
    rec["modules"] = mods
    rec["status"] = "done"
    return _store_pass(sess, p, rec)


def skip_pass(key: str, reason: str) -> dict[str, Any]:
    p = PASS_BY_KEY.get(key)
    if p is None:
        raise BadCommand(f"unknown pass {key!r}")
    if key == "c_first":
        raise Refused("the baseline cannot be skipped; everything else is judged against it")
    sess = _require()
    return _store_pass(sess, p, {"status": "skipped", "at": _now(),
                                 "reason": reason or "skipped"})


def _store_pass(sess: dict[str, Any], p: Pass, rec: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        fresh = _load() or sess
        fresh["passes"][p.key] = rec
        fresh["finished"] = next_pass(fresh) is None
        _save(fresh)
    audit.record("coverage_pass", key=p.key, status=rec["status"])
    return status()


# --- reporting ---------------------------------------------------------------

def _pass_modules(sess: dict[str, Any], key: str) -> dict[str, Any]:
    rec = sess["passes"].get(key) or {}
    return rec.get("modules") or {}


def report(sess: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    sess = sess or _require()
    vin = sess["vin"]
    confirmed = store.confirmed_targets(vin)
    rows = []
    for m in MODULES:
        bus_passes = [p for p in PASSES if p.bus == m.bus_key]
        # Prefer the baseline for CAN-C; the final re-read feeds the diff.
        chosen = next((p for p in bus_passes if p.key != "c_final"), bus_passes[0])
        prec = sess["passes"].get(chosen.key) or {}
        pst = prec.get("status", "pending")
        got = (prec.get("modules") or {}).get(m.code)
        addr = confirmed.get(m.code, m.target if m.usable else None)
        row: dict[str, Any] = {
            "code": m.code, "name": m.name, "bus": m.bus_key, "pass": chosen.key,
            "present": m.present,
            "address": None if addr is None else f"{addr:02X}",
            "address_source": ("this car" if m.code in confirmed
                               else ("registry" if m.usable else None)),
        }
        if pst in ("pending", "running"):
            row["status"] = "not_reached"
        elif pst == "skipped":
            row["status"] = "skipped"
        elif pst == "silent":
            row["status"] = "bus_silent"
        elif got and got.get("read"):
            row["status"] = "read"
            row.update({k: got.get(k) for k in ("active", "history", "tracked",
                                                 "not_run_since_clear")})
        elif got:
            row["status"] = "no_answer" if not got.get("reason") else "no_address"
            row["detail"] = got.get("error") or got.get("nrc") or got.get("warning") \
                or got.get("reason")
        else:
            row["status"] = "no_address"
        if row["status"] == "no_address" and m.present != "confirmed":
            row["status"] = "not_found"
            row["detail"] = "not found by the address sweep: likely not fitted, or asleep"
        rows.append(row)

    fitted = [r for r in rows if r["present"] == "confirmed"]
    read = [r for r in fitted if r["status"] == "read"]
    extra = [r for r in rows if r["present"] != "confirmed" and r["status"] == "read"]
    first = {c: v.get("active", []) for c, v in _pass_modules(sess, "c_first").items()
             if v.get("read")}
    final_rec = sess["passes"].get("c_final") or {}
    diff = (bystander_diff(first, {c: v.get("active", []) for c, v in
                                   _pass_modules(sess, "c_final").items() if v.get("read")})
            if final_rec.get("status") == "done" else None)
    faults = [{"module": r["code"], "bus": r["bus"], "active": r["active"]}
              for r in rows if r.get("active")]
    return {
        "vin": vin, "session": sess["id"], "finished": sess.get("finished", False),
        "coverage": {"fitted_modules": len(fitted), "read": len(read),
                     "percent": round(100 * len(read) / len(fitted)) if fitted else 0,
                     "found_beyond_table_a": [r["code"] for r in extra]},
        "faults": faults,
        "bystanders": diff,
        "bystander_note": (None if diff is not None else
                           "run the final CAN-C re-read to separate real faults from codes "
                           "set by the cable changes"),
        "modules": rows,
    }


def status() -> dict[str, Any]:
    sess = current()
    if not sess:
        return {"active": False, "passes": [dict(key=p.key, bus=p.bus, cable=p.cable,
                                                 title=p.title, checklist=list(p.checklist))
                                            for p in PASSES]}
    nxt = next_pass(sess)
    return {
        "active": True, "vin": sess["vin"], "session": sess["id"],
        "engine_running": sess.get("engine_running"),
        "finished": sess.get("finished", False),
        "next": None if nxt is None else nxt.key,
        "passes": [dict(key=p.key, bus=p.bus, bus_name=BUSES[p.bus].name, cable=p.cable,
                        title=p.title, checklist=list(p.checklist),
                        **{k: v for k, v in sess["passes"][p.key].items()
                           if k in ("status", "at", "reason", "reading")})
                   for p in PASSES],
        "report": report(sess),
    }


def reset() -> dict[str, Any]:
    with _LOCK:
        try:
            path().unlink()
        except OSError:
            pass
    audit.record("coverage_reset")
    return status()


__all__ = ["PASSES", "PASS_BY_KEY", "ACTIVE_MASK", "classify_records", "bystander_diff",
           "start", "current", "run_pass", "skip_pass", "report", "status", "reset", "path"]
