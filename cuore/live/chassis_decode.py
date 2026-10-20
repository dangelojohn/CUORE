"""Decode a passive CAN-CH capture through the Giorgio DBC.

Input is the frame list :func:`cuore.live.capture.listen` returns (each frame
``{"t", "id": hex string, "data": hex string}``). Output is the latest decoded
signals per message plus its rate. Pure: never opens a session, never
transmits.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from . import dbc as dbc_mod

#: Messages seen on this car's CAN-CH (STP 33 listen, 2026-10-14).
INTEREST = {
    0x0DE: "EPS_1", 0x0EE: "ABS_1", 0x0FA: "ABS_3", 0x0FC: "ENGINE_1",
    0x106: "EPS_2", 0x10E: "ABS_7", 0x116: "ABS_5", 0x122: "EPS_3",
    0x11C: "vehicle speed",
}


def decode_capture(frames: Iterable[dict[str, Any]], seconds: Optional[float] = None,
                   dbc: Optional[dbc_mod.Dbc] = None) -> dict[str, Any]:
    """Latest decoded signals per message, with counts and rates.

    ``rate_hz`` is count / ``seconds`` when given, else (count - 1) / the
    message's own time span (0 for a single frame). Ids the DBC lacks are
    tallied under ``unknown_ids``; unparseable frames under ``bad_frames``.
    """
    db = dbc or dbc_mod.default()
    msgs: dict[str, dict[str, Any]] = {}
    unknown: dict[str, int] = {}
    total = bad = 0
    for f in frames:
        total += 1
        id_text = str(f.get("id", "")).strip().upper()
        try:
            fid = int(id_text, 16)
            data = bytes.fromhex(str(f.get("data", "")))
        except ValueError:
            bad += 1
            continue
        t = float(f.get("t") or 0.0)
        dec = db.decode(fid, data, extended=len(id_text) > 3)
        if dec is None:
            unknown[id_text] = unknown.get(id_text, 0) + 1
            continue
        entry = msgs.setdefault(id_text, {
            "id": id_text, "message": dec["message"], "count": 0, "first_t": t,
            "interest": INTEREST.get(fid) if len(id_text) <= 3 else None})
        entry["count"] += 1
        entry["last_t"] = t
        entry["data"] = data.hex().upper()
        entry["signals"] = {k: {"value": v[0], "unit": v[1]}
                            for k, v in dec["signals"].items()}
    for e in msgs.values():
        if seconds:
            e["rate_hz"] = round(e["count"] / float(seconds), 1)
        else:
            span = e["last_t"] - e["first_t"]
            e["rate_hz"] = round((e["count"] - 1) / span, 1) if span > 0 else 0.0
        e.pop("first_t", None)
    return {"frames": total, "messages": dict(sorted(msgs.items())),
            "unknown_ids": dict(sorted(unknown.items(), key=lambda kv: -kv[1])),
            "bad_frames": bad}


__all__ = ["decode_capture", "INTEREST"]
