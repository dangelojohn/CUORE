"""Read-only check of the assumed OBD Mode $06 record layout against a raw reply.

:mod:`mode06` decodes ``46`` + repeating 9-byte records
OBDMID(1) TID(1) UASID(1) value(2) min(2) max(2), big-endian words. That layout
is the standard's, but it has never been checked against a live reply from this
car. :func:`mode06_layout_check` takes the raw reply exactly as the transport
returned it (``out["raw"]`` of :func:`mode06.read_mode06`, or a plain list of
raw reply texts), re-parses it, and says whether the assumed layout holds.
The verdict and the raw reply are saved once under
``<state>/mode06_layout_check/<timestamp>.json`` so the layout is proven (or
disproven) on evidence and kept.

Nothing here touches the adapter. The ranges tested are the ones this module
assumes the standard allows; they are listed in :data:`RULES` so a reader can
see exactly what "ok" meant.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir
from .framing import payloads_for, reassemble
from .mode06 import decode_supported_mid_bitmap

#: MIDs that are supported-ID bitmaps, never test records.
BITMAP_MIDS: tuple[str, ...] = ("00", "20", "40", "60", "80", "A0", "C0", "E0")

RULES: dict[str, str] = {
    "length": "reply = 46 + a whole number of 9-byte records",
    "obdmid": "01..FF and not one of the supported-ID bitmap ids (00,20,40,60,80,A0,C0,E0)",
    "tid": "01..FF (00 assumed reserved)",
    "uasid": "01..FE (00 and FF assumed reserved)",
    "range": "min <= value <= max for the majority (> 50%) of records "
             "(two's complement when UASID bit 7 is set)",
    "bitmap": "each record MID is in the ECU's supported-MID bitmap (when 06 00/20/.. frames are present)",
    "alternatives": "no alternative layout fits the same bytes better than the assumed one",
}

ASSUMED_LAYOUT = {"name": "assumed", "stride": 9, "start": "data[1]",
                  "fields": "OBDMID TID UASID value(2) min(2) max(2)", "byte_order": "big-endian"}


def _w(hi: str, lo: str, little: bool = False) -> int:
    a, b = int(hi, 16), int(lo, 16)
    return (b << 8) | a if little else (a << 8) | b


def _signed(v: int, uasid: int) -> int:
    return v - 0x10000 if (uasid & 0x80 and v & 0x8000) else v


def _recs_9(body: list[str], little: bool) -> tuple[list[dict[str, Any]], int]:
    """9-byte records with an own MID; returns (records, leftover bytes)."""
    out = []
    for i in range(0, len(body) - 8, 9):
        r = body[i:i + 9]
        out.append({"mid": r[0], "tid": r[1], "uasid": r[2], "value": _w(r[3], r[4], little),
                    "min": _w(r[5], r[6], little), "max": _w(r[7], r[8], little)})
    return out, len(body) % 9


def _recs_8(body: list[str]) -> tuple[list[dict[str, Any]], int]:
    """MID once, then 8-byte TID UASID value min max records."""
    if not body:
        return [], 0
    mid, rest = body[0], body[1:]
    out = []
    for i in range(0, len(rest) - 7, 8):
        r = rest[i:i + 8]
        out.append({"mid": mid, "tid": r[0], "uasid": r[1], "value": _w(r[2], r[3]),
                    "min": _w(r[4], r[5]), "max": _w(r[6], r[7])})
    return out, len(rest) % 8


def _field_problems(r: dict[str, Any]) -> list[str]:
    p = []
    mid, tid, uas = int(r["mid"], 16), int(r["tid"], 16), int(r["uasid"], 16)
    if mid == 0 or r["mid"] in BITMAP_MIDS:
        p.append(f"OBDMID {r['mid']} is not a test id")
    if tid == 0:
        p.append("TID 00")
    if uas in (0x00, 0xFF):
        p.append(f"UASID {r['uasid']}")
    return p


def _in_range(r: dict[str, Any]) -> bool:
    u = int(r["uasid"], 16)
    return _signed(r["min"], u) <= _signed(r["value"], u) <= _signed(r["max"], u)


def _score(records: list[dict[str, Any]], leftover: int) -> dict[str, Any]:
    n = len(records)
    valid = sum(1 for r in records if not _field_problems(r))
    inr = sum(1 for r in records if _in_range(r))
    both = sum(1 for r in records if not _field_problems(r) and _in_range(r))
    return {"records": n, "leftover_bytes": leftover, "fields_valid": valid, "in_range": inr,
            "fit": round(both / n, 3) if n and not leftover else 0.0}


def _parse_reply(text: str, headers_on: bool) -> dict[str, list[str]]:
    """Per-ECU ``46`` payloads from one raw reply text."""
    for ho in (headers_on, not headers_on):
        got = payloads_for(reassemble(text, headers_on=ho), "46")
        if got:
            return got
    return {}


def _collect(raw: Any, headers_on: bool) -> list[tuple[str, str, list[str]]]:
    """(source key, ecu header, 46-payload) for every positive reply in ``raw``."""
    items: list[tuple[str, Any]]
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        items = [(f"frame{i}", t) for i, t in enumerate(raw)]
    else:
        items = [("frame0", raw)]
    out: list[tuple[str, str, list[str]]] = []
    for key, val in items:
        if isinstance(val, dict) and "retry" in val:      # CAN-ERROR retry shape
            val = val["retry"]
        if isinstance(val, str):
            for hdr, data in _parse_reply(val, headers_on).items():
                out.append((str(key), hdr, [b.upper() for b in data]))
        elif isinstance(val, dict):                         # pre-parsed {hdr: [bytes]}
            for hdr, data in val.items():
                if data and str(data[0]).upper() == "46":
                    out.append((str(key), str(hdr), [str(b).upper() for b in data]))
    return out


def mode06_layout_check(raw_reply_frames: Any, *, headers_on: bool = True) -> dict[str, Any]:
    """Validate the assumed Mode $06 layout against a raw reply.

    Returns ``{ok, records, anomalies, assumed_layout, alternative_layouts_tried}``
    plus ``bitmap_check`` (what the supported-MID frames said, or why none).
    ``ok`` is False when there is nothing to check.
    """
    replies = _collect(raw_reply_frames, headers_on)
    anomalies: list[str] = []
    bitmap: dict[str, set[str]] = {}
    test_replies: list[tuple[str, str, list[str]]] = []
    for key, hdr, data in replies:
        if len(data) >= 2 and data[1] in BITMAP_MIDS:
            if len(data) == 6:
                sup, _more = decode_supported_mid_bitmap(data[1], data[2:6])
                bitmap.setdefault(hdr, set()).update(sup)
            else:
                anomalies.append(f"{key} [{hdr}]: supported-MID reply {data[1]} is "
                                 f"{len(data) - 2} data bytes, expected 4")
        else:
            test_replies.append((key, hdr, data))
    if not test_replies:
        return {"ok": False, "records": [], "anomalies": anomalies + ["no positive Mode 06 test reply in the input"],
                "assumed_layout": ASSUMED_LAYOUT, "alternative_layouts_tried": [],
                "bitmap_check": "not run: no test replies"}

    assumed: list[dict[str, Any]] = []
    # alternatives: name -> accumulated (records, leftover)
    alts: dict[str, list[Any]] = {"little_endian_words": [[], 0], "no_mid_per_record_8byte": [[], 0],
                                  "shifted_one_byte": [[], 0]}
    leftover_total = 0
    for key, hdr, data in test_replies:
        body = data[1:]
        recs, left = _recs_9(body, False)
        for r in recs:
            r["source"], r["ecu"] = key, hdr
        assumed.extend(recs)
        if left:
            leftover_total += 1
            anomalies.append(f"{key} [{hdr}]: {len(body)} bytes after 46 is not a whole number of "
                             f"9-byte records ({left} left over)")
        for name, (r2, l2) in (("little_endian_words", _recs_9(body, True)),
                               ("no_mid_per_record_8byte", _recs_8(body)),
                               ("shifted_one_byte", _recs_9(body[1:], False))):
            alts[name][0].extend(r2)
            alts[name][1] += 1 if l2 else 0
        if recs and recs[0]["mid"] != key and key in {f"{i:02X}" for i in range(256)}:
            anomalies.append(f"{key} [{hdr}]: first record MID {recs[0]['mid']} does not echo the "
                             f"requested MID")
    field_bad = 0
    for r in assumed:
        probs = _field_problems(r)
        if probs:
            field_bad += 1
            if field_bad <= 10:
                anomalies.append(f"{r['source']} [{r['ecu']}] MID {r['mid']} TID {r['tid']}: "
                                 + "; ".join(probs))
    if field_bad > 10:
        anomalies.append(f"... {field_bad - 10} more records with out-of-range id fields")
    n = len(assumed)
    in_rng = sum(1 for r in assumed if _in_range(r))
    if n and in_rng * 2 <= n:
        anomalies.append(f"only {in_rng} of {n} records have min <= value <= max (need a majority)")
    if not n:
        anomalies.append("no complete 9-byte record in any reply")

    bitmap_check: Any
    if bitmap:
        bitmap_check = {"supported": {h: sorted(s) for h, s in bitmap.items()}}
        union = set().union(*bitmap.values())
        seen = {r["mid"] for r in assumed}
        stray = sorted(seen - union)
        if stray:
            anomalies.append(f"record MIDs not in any supported-MID bitmap: {', '.join(stray)}")
        bitmap_check["records_not_in_bitmap"] = stray
        asked = {k for k, _h, _d in test_replies}
        bitmap_check["supported_but_no_reply_seen"] = sorted(
            m for m in union if m not in asked and m not in seen)[:40]
    else:
        bitmap_check = "not run: no Mode 06 PID 00/20/.. support frames in the input"

    base = _score(assumed, leftover_total)
    tried = []
    for name, (recs, left_n) in alts.items():
        sc = _score(recs, left_n)
        sc["layout"] = name
        tried.append(sc)
        if sc["fit"] > base["fit"]:
            anomalies.append(f"alternative layout {name} fits better ({sc['fit']} vs {base['fit']})")
    ok = not anomalies and n > 0
    return {"ok": ok, "records": assumed, "anomalies": anomalies,
            "assumed_layout": {**ASSUMED_LAYOUT, "score": base, "rules": RULES},
            "alternative_layouts_tried": tried, "bitmap_check": bitmap_check}


def save_layout_check(raw: Any, verdict: dict[str, Any], *, directory: Optional[Path] = None
                      ) -> Path:
    """Write ``{raw, verdict}`` to ``<state>/mode06_layout_check/<timestamp>.json``."""
    d = directory or (state_dir() / "mode06_layout_check")
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    p = d / f"{now:%Y%m%dT%H%M%S}.json"
    n = 1
    while p.exists():
        p = d / f"{now:%Y%m%dT%H%M%S}_{n}.json"
        n += 1
    p.write_text(json.dumps({"at": now.isoformat(timespec="seconds"), "raw": raw,
                             "verdict": verdict}, indent=2, default=str), encoding="utf-8")
    return p


def check_and_save(raw: Any, *, headers_on: bool = True) -> dict[str, Any]:
    """Run the check on a live reply and keep it. Never raises: a failure here
    must not spoil the read it rides on."""
    try:
        verdict = mode06_layout_check(raw, headers_on=headers_on)
        path = save_layout_check(raw, verdict)
        return {"ok": verdict["ok"], "anomalies": verdict["anomalies"][:10],
                "record_count": len(verdict["records"]), "saved_to": str(path)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"layout check failed: {type(e).__name__}: {e}"}


__all__ = ["RULES", "mode06_layout_check", "save_layout_check", "check_and_save"]
