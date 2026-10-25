"""Voltage-drop test plan, split-the-path, shared points and repair proof for
one code's electrical path.

Nothing here talks to the car. The append-only store is
``<state dir>/path_tests.jsonl`` (one JSON object per line):

* ``kind="test"``   -- vin, code, side, from_id, to_id, measured_v, limit_v,
  limit_source, pass, state, at, by, note
* ``kind="repair"`` -- vin, code, element, what, by, date, at

Every number shown comes from either an element's own sourced data or the
labelled general rule (:data:`GENERAL_LABEL`). Pure functions take their
inputs as arguments so they can be tested without the app.
"""

from __future__ import annotations

import json
import math
import re
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

GENERAL_LABEL = "general practice, not a Stelvio spec"
POWER_LIMIT_V = 0.5
GROUND_LIMIT_V = 0.2
GROUND_PER_CONNECTION_V = 0.1

#: Element kinds that carry current (a hose or tank is on a path but is not
#: something a meter can be put across).
ELECTRICAL_KINDS = {"fuse", "relay", "battery", "connector", "module", "ground", "harness_section",
                    "splice", "switch", "sensor", "valve", "pump", "component", "motor",
                    "actuator", "controller"}
_LIMIT_KEYS = ("max_voltage_drop_v", "max_drop_v", "voltage_drop_limit_v", "voltage_drop_limit")
_TERMINAL_KEYS = ("terminal", "pin", "pins", "terminals")
STATES = ("", "ignition_off", "ignition_on", "engine_running", "component_commanded")
STATE_LABELS = {"": "not stated", "ignition_off": "ignition off", "ignition_on": "ignition on",
                "engine_running": "engine running", "component_commanded": "component commanded on"}

_LOCK = threading.Lock()
_CODE_RE = re.compile(r"^[A-Za-z0-9]{3,8}(-[0-9A-Za-z]{2})?$")
_VIN_RE = re.compile(r"^[A-Za-z0-9]{11,17}$")


def store_path() -> Path:
    from ..live.config import state_dir
    return Path(state_dir()) / "path_tests.jsonl"


def read_all(vin: str = "", code: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        with open(store_path(), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if vin and str(rec.get("vin", "")).upper() != vin.upper():
                    continue
                if code and str(rec.get("code", "")).upper() != code.upper():
                    continue
                out.append(rec)
    except OSError:
        pass
    return out


def append(rec: dict[str, Any]) -> None:
    line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
    with _LOCK:
        p = store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


# --- the plan ---------------------------------------------------------------

def _first_val(e: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if e.get(k) not in (None, "", [], {}):
            return e[k]
    return None


def _terminal(hop: dict[str, Any], el: dict[str, Any]) -> str:
    t = _first_val(el, _TERMINAL_KEYS) or _first_val(hop, _TERMINAL_KEYS)
    if isinstance(t, (list, tuple)):
        t = ", ".join(str(x) for x in t)
    if t:
        return f"terminal/pin {t} of {hop.get('label')}"
    return f"the {hop.get('label')} end (terminal not given in CUORE data; use the wiring diagram)"


def _sourced_limit(a: dict[str, Any], b: dict[str, Any]) -> Optional[tuple[float, str]]:
    for e in (b, a):
        v = _first_val(e, _LIMIT_KEYS)
        try:
            f = float(v) if v is not None else None
        except (TypeError, ValueError):
            f = None
        if f is not None and f > 0:
            src = (e.get("location") or {}).get("source") or e.get("source") or "element data"
            return f, f"sourced: {src} ({e.get('label')})"
    return None


def electrical_hops(path: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [h for h in path if str(h.get("kind") or "").lower() in ELECTRICAL_KINDS and h.get("id")]


def is_ground(h: dict[str, Any]) -> bool:
    return str(h.get("kind") or "").lower() == "ground" or str(h.get("role") or "").lower() == "ground"


def seg_id(side: str, a: str, b: str) -> str:
    return f"{side}:{a}>{b}"


def build_segments(path: list[dict[str, Any]], elements: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Voltage-drop segments: consecutive non-ground electrical hops (power
    side) and the last such hop before each ground -> that ground (ground
    side)."""
    hops = electrical_hops(path)
    segs: list[dict[str, Any]] = []
    prev: Optional[dict[str, Any]] = None
    for h in hops:
        if is_ground(h):
            if prev is not None:
                segs.append(_segment("ground", prev, h, elements))
            continue
        if prev is not None:
            segs.append(_segment("power", prev, h, elements))
        prev = h
    return segs


def _segment(side: str, a: dict[str, Any], b: dict[str, Any],
             elements: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ea, eb = elements.get(a["id"]) or {}, elements.get(b["id"]) or {}
    sourced = _sourced_limit(ea, eb)
    if sourced:
        limit, source = sourced
    elif side == "ground":
        limit, source = GROUND_LIMIT_V, f"{GENERAL_LABEL}: max 0.2 V across the ground side ({GROUND_PER_CONNECTION_V} V per ground connection)"
    else:
        limit, source = POWER_LIMIT_V, f"{GENERAL_LABEL}: max 0.5 V across the power side of a circuit"
    ta, tb = _terminal(a, ea), _terminal(b, eb)
    if side == "ground":
        how = (f"Circuit loaded (component operating). DC volts. Red lead on {ta}; black lead on {tb} "
               f"(or the ground's bare metal/bolt). Read the drop across the ground side.")
    else:
        how = (f"Circuit loaded (component operating, not key-off). DC volts. Red lead on {ta}; "
               f"black lead on {tb}. Read the drop across this stretch of the power side.")
    return {"id": seg_id(side, a["id"], b["id"]), "side": side, "from_id": a["id"], "to_id": b["id"],
            "from_label": a.get("label"), "to_label": b.get("label"), "limit_v": limit,
            "limit_source": source, "general": not sourced, "instruction": how}


# --- results ---------------------------------------------------------------

def latest_results(records: list[dict[str, Any]], vin: str, code: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("kind") != "test" or str(r.get("vin", "")).upper() != vin.upper() \
                or str(r.get("code", "")).upper() != code.upper():
            continue
        out[seg_id(str(r.get("side")), str(r.get("from_id")), str(r.get("to_id")))] = r
    return out


def history_for(records: list[dict[str, Any]], vin: str, code: str, sid: str) -> list[dict[str, Any]]:
    return [r for r in records if r.get("kind") == "test" and str(r.get("vin", "")).upper() == vin.upper()
            and str(r.get("code", "")).upper() == code.upper()
            and seg_id(str(r.get("side")), str(r.get("from_id")), str(r.get("to_id"))) == sid]


def cleared_hops(hops: list[dict[str, Any]], segments: list[dict[str, Any]],
                 results: dict[str, dict[str, Any]]) -> dict[str, str]:
    """``{hop id: reason}`` for hops that need no more testing: latest
    inspection ok, or touched by a segment whose latest reading passed."""
    out: dict[str, str] = {}
    for h in hops:
        if h.get("condition") == "ok":
            out[h["id"]] = "inspected ok"
    for s in segments:
        r = results.get(s["id"])
        if r and r.get("pass"):
            for hid in (s["from_id"], s["to_id"]):
                out.setdefault(hid, f"voltage drop passed ({s['from_label']} to {s['to_label']})")
    return out


def split_suggestion(hops: list[dict[str, Any]], segments: list[dict[str, Any]],
                     results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cleared = cleared_hops(hops, segments, results)
    remaining = [h for h in hops if h["id"] not in cleared]
    n = len(remaining)
    if n == 0:
        return {"remaining": 0, "hop_id": None, "message": "Every hop on the path is cleared by an ok inspection or a passing reading.",
                "cleared": cleared}
    pick = remaining[n // 2] if n > 1 else remaining[0]
    if n == 1:
        msg = f"Test here first: {pick['label']} (the only hop left untested)."
    else:
        msg = f"Test here first: {pick['label']} (splits the remaining {n} hops in half)."
    return {"remaining": n, "hop_id": pick["id"], "message": msg, "cleared": cleared,
            "remaining_ids": [h["id"] for h in remaining]}


# --- shared points -----------------------------------------------------------

def shared_points(code: str, hops: list[dict[str, Any]],
                  others: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """``others``: ``{code: {"ids": set/list of element ids, "active": bool}}``
    for every other code on the car. Returns ``{hop id: {codes: [...],
    common: bool}}``; ``common`` means at least one sharing code is active."""
    out: dict[str, dict[str, Any]] = {}
    for h in hops:
        rows = [{"code": c, "active": bool(v.get("active"))}
                for c, v in sorted(others.items())
                if c.upper() != code.upper() and h["id"] in set(v.get("ids") or [])]
        if rows:
            out[h["id"]] = {"codes": rows, "common": any(r["active"] for r in rows)}
    return out


# --- repair + proof ------------------------------------------------------------

def latest_repairs(records: list[dict[str, Any]], vin: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("kind") == "repair" and str(r.get("vin", "")).upper() == vin.upper():
            out[str(r.get("element"))] = r
    return out


def repair_state(hop_id: str, repair: Optional[dict[str, Any]], segments: list[dict[str, Any]],
                 records: list[dict[str, Any]], vin: str, code: str,
                 code_last_seen: str = "", newest_scan: str = "") -> dict[str, Any]:
    """``state`` is ``none`` / ``repaired`` / ``proven`` / ``code_returned``.
    Proven needs a passing voltage-drop reading taken after the repair on a
    segment touching the hop, and no sighting of the code after the repair
    date. ``scan_confirms`` says whether a later scan also lacks the code."""
    if not repair:
        return {"state": "none"}
    at = str(repair.get("at") or "")
    rdate = str(repair.get("date") or at[:10])[:10]
    touching = {s["id"] for s in segments if hop_id in (s["from_id"], s["to_id"])}
    passed = None
    for r in records:
        if r.get("kind") != "test" or str(r.get("vin", "")).upper() != vin.upper() \
                or str(r.get("code", "")).upper() != code.upper():
            continue
        if seg_id(str(r.get("side")), str(r.get("from_id")), str(r.get("to_id"))) not in touching:
            continue
        if str(r.get("at") or "") > at and r.get("pass"):
            passed = r
    seen_after = bool(code_last_seen) and code_last_seen[:10] > rdate
    if seen_after:
        return {"state": "code_returned", "repair": repair, "test": passed,
                "note": f"code last seen {code_last_seen[:16]}, after the repair date {rdate}"}
    if not passed:
        return {"state": "repaired", "repair": repair,
                "note": "repaired; no passing post-repair voltage-drop reading on a segment touching this hop yet"}
    scan_ok = bool(newest_scan) and newest_scan[:10] > rdate
    return {"state": "proven", "repair": repair, "test": passed, "scan_confirms": scan_ok,
            "note": ("post-repair voltage drop passed" +
                     ("; a later scan on file does not show the code" if scan_ok
                      else "; no later scan on file yet to confirm the code is gone"))}


# --- validation ----------------------------------------------------------------

def valid_vin(vin: str) -> bool:
    return bool(_VIN_RE.match(vin or ""))


def valid_code(code: str) -> bool:
    return bool(_CODE_RE.match(code or ""))


def validate_test(form: dict[str, Any], vin: str, code: str,
                  segments: list[dict[str, Any]]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    sid = str(form.get("segment", "")).strip()
    seg = next((s for s in segments if s["id"] == sid), None)
    if seg is None:
        return None, "unknown segment for this code's path"
    raw = str(form.get("measured_v", "")).strip().replace(",", ".")
    try:
        v = float(raw)
    except ValueError:
        return None, "measured volts must be a number"
    if not math.isfinite(v) or not (-50 <= v <= 50):
        return None, "measured volts must be between -50 and 50"
    state = str(form.get("state", "")).strip()
    if state not in STATES:
        return None, "unknown load/ignition state"
    by = str(form.get("by", "")).strip()[:40] or "mechanic"
    note = str(form.get("note", "")).strip()[:200]
    rec = {"kind": "test", "vin": vin.upper(), "code": code.upper(), "side": seg["side"],
           "from_id": seg["from_id"], "to_id": seg["to_id"], "measured_v": round(v, 3),
           "limit_v": seg["limit_v"], "limit_source": seg["limit_source"],
           "pass": abs(v) <= seg["limit_v"], "state": state, "note": note,
           "at": datetime.now().isoformat(timespec="seconds"), "by": by}
    return rec, None


def validate_repair(form: dict[str, Any], vin: str, code: str,
                    hop_ids: set[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    el = str(form.get("element", "")).strip()
    if el not in hop_ids:
        return None, "unknown element for this code's path"
    what = str(form.get("what", "")).strip()
    if not what:
        return None, "say what was done"
    if len(what) > 300:
        return None, "description too long (300 characters max)"
    d = str(form.get("date", "")).strip() or date.today().isoformat()
    try:
        date.fromisoformat(d)
    except ValueError:
        return None, "date must be YYYY-MM-DD"
    by = str(form.get("by", "")).strip()[:40] or "mechanic"
    rec = {"kind": "repair", "vin": vin.upper(), "code": code.upper(), "element": el, "what": what,
           "by": by, "date": d, "at": datetime.now().isoformat(timespec="seconds")}
    return rec, None
