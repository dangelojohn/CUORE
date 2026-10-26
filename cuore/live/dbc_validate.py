"""Read-only check of the DBC scales against ONE real capture (never transmits).

``validate(capture, snapshot)`` takes a saved raw capture (a path written by
:mod:`cuore.live.rawframes`, or the dict :func:`rawframes.read_capture` returns)
plus a same-moment live DID snapshot ``{"rpm": ..., "speed_kmh": ...}`` (ecm_1000
rpm, ecm_1002 speed), decodes the Giorgio-DBC signals and returns, per signal,
``PLAUSIBLE`` / ``SUSPECT`` / ``NO DATA`` with the reason and numbers.

PLAUSIBLE means "agrees with the DID reference within tolerance in this one
capture" -- it is a reason to test further and, only after several states
(parked, steering lock, rolling), to promote a scale in did_catalog. It is never
diagnostic proof on its own. Signals with no reference in the snapshot stay
NO DATA (a bare range check can only make a signal SUSPECT, never PLAUSIBLE).
MAYBE_VOLTAGE is always reported as an unidentified signal, never as volts.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Optional, Union

from . import dbc as dbc_mod
from . import rawframes

PLAUSIBLE, SUSPECT, NO_DATA = "PLAUSIBLE", "SUSPECT", "NO DATA"

# (frame id, signal) -> kind of check
_CHECKS = [
    (0x0FC, "ENGINE_RPM", "rpm"),
    (0x101, "VEHICLE_SPEED", "speed_ms"),
    (0x11C, "VEHICLE_SPEED", "speed_ms"),
    (0x0EE, "WHEEL_SPEED_FL", "speed_ms"),
    (0x0EE, "WHEEL_SPEED_FR", "speed_ms"),
    (0x0EE, "WHEEL_SPEED_RL", "speed_ms"),
    (0x0EE, "WHEEL_SPEED_RR", "speed_ms"),
    (0x0DE, "STEERING_ANGLE", "steer"),
    (0x0F1, "MAYBE_VOLTAGE", "unidentified"),
]


def _series(frames: list[dict[str, Any]], fid: int, name: str,
            db: dbc_mod.Dbc) -> list[float]:
    out: list[float] = []
    for f in frames:
        try:
            if int(str(f.get("id", "")), 16) != fid:
                continue
            data = bytes.fromhex(str(f.get("data", "")))
        except ValueError:
            continue
        dec = db.decode(fid, data, extended=False)
        if dec and name in dec["signals"]:
            out.append(float(dec["signals"][name][0]))
    return out


def _overlaps(db: dbc_mod.Dbc, fid: int, name: str) -> Optional[str]:
    msg = db.get(fid, False)
    sig = msg.signals.get(name) if msg else None
    if sig is None:
        return None
    mine = set(sig.bit_positions())
    for o in msg.signals.values():
        if o.name != name and mine & set(o.bit_positions()):
            return o.name
    return None


def _verdict(sig: str, fid: int, kind: str, vals: list[float],
             snap: dict[str, Any], note: str) -> dict[str, Any]:
    r: dict[str, Any] = {"id": f"{fid:03X}", "signal": sig, "frames": len(vals),
                         "confidence": dbc_mod.UNVERIFIED_LABEL}
    if not vals:
        return {**r, "verdict": NO_DATA, "reason": "id not present in the capture"}
    med = statistics.median(vals)
    r.update({"decoded_median": round(med, 3), "decoded_min": min(vals), "decoded_max": max(vals)})
    if kind == "unidentified":
        return {**r, "verdict": SUSPECT, "label": dbc_mod.NOT_BATTERY_VOLTAGE_NOTE,
                "reason": "upstream marks this signal as a guess; it is not compared to "
                          "or presented as battery voltage"}
    if kind == "rpm":
        ref = snap.get("rpm")
        if med > 9000 or min(vals) < 0:
            return {**r, "verdict": SUSPECT, "reason": f"decoded {med} rpm is outside 0-9000"}
        if ref is None:
            return {**r, "verdict": NO_DATA, "reason": "no rpm in the DID snapshot to compare"}
        tol = max(50.0, 0.05 * float(ref))
        ok = abs(med - float(ref)) <= tol
        return {**r, "reference": ref, "tolerance": tol, "verdict": PLAUSIBLE if ok else SUSPECT,
                "reason": (f"median {med} rpm vs DID {ref} rpm (tolerance +-{tol:.0f})")}
    if kind == "speed_ms":
        kmh = med * 3.6
        r["decoded_kmh"] = round(kmh, 2)
        ref = snap.get("speed_kmh")
        if kmh < 0 or kmh > 350:
            return {**r, "verdict": SUSPECT, "reason": f"{kmh:.1f} km/h is out of range"}
        if ref is None:
            return {**r, "verdict": NO_DATA, "reason": "no speed in the DID snapshot to compare"}
        tol = max(2.0, 0.05 * float(ref))
        ok = abs(kmh - float(ref)) <= tol
        return {**r, "reference": ref, "tolerance": tol, "verdict": PLAUSIBLE if ok else SUSPECT,
                "reason": f"{kmh:.1f} km/h (assuming m/s) vs DID {ref} km/h (tolerance +-{tol:.1f})"}
    if kind == "steer":
        centred = any(w in note.lower() for w in ("centred", "centered", "straight"))
        if abs(med) > 900:
            return {**r, "verdict": SUSPECT, "reason": f"{med} deg is beyond steering range"}
        if not centred:
            return {**r, "verdict": NO_DATA,
                    "reason": "state_note does not say the wheel was centred; no reference"}
        ok = abs(med) <= 10
        return {**r, "reference": 0, "tolerance": 10,
                "verdict": PLAUSIBLE if ok else SUSPECT,
                "reason": f"wheel centred: median {med} deg (expect within +-10)"}
    return {**r, "verdict": NO_DATA, "reason": "no check defined"}


def validate(capture: Union[str, Path, dict[str, Any]], snapshot: dict[str, Any],
             db: Optional[dbc_mod.Dbc] = None) -> dict[str, Any]:
    cap = capture if isinstance(capture, dict) else rawframes.read_capture(capture)
    frames = cap.get("frames") or []
    header = cap.get("header") or {}
    db = db or dbc_mod.default()
    note = str(header.get("state_note") or "")
    results = []
    for fid, sig, kind in _CHECKS:
        v = _verdict(sig, fid, kind, _series(frames, fid, sig, db), snapshot, note)
        other = _overlaps(db, fid, sig)
        if other and v["verdict"] == PLAUSIBLE:
            v["verdict"] = SUSPECT
            v["reason"] += f"; but the DBC bit range overlaps {other} in the same message"
        elif other:
            v["structure"] = f"DBC bit range overlaps {other}"
        results.append(v)
    counts = {v: sum(1 for r in results if r["verdict"] == v) for v in (PLAUSIBLE, SUSPECT, NO_DATA)}
    return {"signals": results, "counts": counts, "header": header,
            "frames": len(frames), "torn_lines": cap.get("torn_lines", 0),
            "confidence": dbc_mod.UNVERIFIED_LABEL,
            "note": "PLAUSIBLE = agrees with the DID reference in this one capture; "
                    "not proof. Promote a scale only after parked / steering / rolling states agree."}


__all__ = ["validate", "PLAUSIBLE", "SUSPECT", "NO_DATA"]
