"""Tech-entered element locations: append-only ``element_locations.jsonl`` in
the CUORE state dir, keyed by model so another car of the same model
inherits them. Later lines win; a ``retract`` line undoes one entry. Nothing
is ever pre-filled or guessed -- every entry names its source."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..live import config as _config

FILE = "element_locations.jsonl"
CONFIDENCES = ("observed", "documented")
MAX_DESC, MAX_ACCESS, MAX_SOURCE, MAX_BY = 300, 200, 200, 60

# Higher beats lower; a tech entry only replaces data it strictly outranks.
_RANK = {"": 0, "unknown": 0, "none": 0, "low": 1, "medium": 2, "documented": 2,
         "high": 3, "observed": 3, "inferred": 1, "single-source": 3, "confirmed": 4}
_UNSOURCED = re.compile(r"not sourced|unknown|^\s*$|^none$", re.I)


def model_key(vin: str) -> str:
    v = (vin or "").upper()
    if v.startswith("ZASFAKPN") and len(v) >= 10 and v[9] == "J":
        return "stelvio-2018-2.0"
    return f"vin:{v}"


def _path():
    return _config.state_dir() / FILE


def _read() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for line in _path().read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict):
                out.append(o)
    except OSError:
        pass
    return out


def _append(rec: dict[str, Any]) -> None:
    with _path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate(zone_ids: set[str], element_ids: set[str], element: str, zone: str,
             description: str, access: str, source: str, confidence: str,
             by: str) -> Optional[str]:
    if element not in element_ids:
        return "unknown element"
    if zone not in zone_ids:
        return "unknown zone"
    if not description.strip():
        return "describe where exactly it is"
    if len(description) > MAX_DESC:
        return f"description too long (max {MAX_DESC})"
    if len(access) > MAX_ACCESS:
        return f"access note too long (max {MAX_ACCESS})"
    if not source.strip():
        return "a source is required (diagram, manual page, or 'observed on car by ...')"
    if len(source) > MAX_SOURCE:
        return f"source too long (max {MAX_SOURCE})"
    if confidence not in CONFIDENCES:
        return "confidence must be observed or documented"
    if len(by) > MAX_BY:
        return "name too long"
    return None


def set_location(vin: str, element: str, zone: str, description: str, source: str,
                 confidence: str, access: str = "", by: str = "") -> dict[str, Any]:
    rec = {"op": "set", "id": uuid.uuid4().hex[:10], "at": _now(),
           "vin": (vin or "").upper(), "model_key": model_key(vin), "element_id": element,
           "zone": zone, "description": description.strip(), "access": access.strip(),
           "source": source.strip(), "confidence": confidence, "by": by.strip() or "mechanic"}
    _append(rec)
    return rec


def retract(vin: str, entry_id: str) -> bool:
    mk = model_key(vin)
    if not any(r.get("op") == "set" and r.get("id") == entry_id and r.get("model_key") == mk
               for r in _read()):
        return False
    _append({"op": "retract", "id": uuid.uuid4().hex[:10], "target": entry_id, "at": _now(),
             "vin": (vin or "").upper(), "model_key": mk})
    return True


def latest_for_model(vin: str) -> dict[str, dict[str, Any]]:
    """{element_id: newest live (un-retracted) set entry} for this car's model."""
    mk = model_key(vin)
    rows = [r for r in _read() if r.get("model_key") == mk]
    dead = {r.get("target") for r in rows if r.get("op") == "retract"}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("op") == "set" and r.get("id") not in dead and r.get("element_id"):
            out[r["element_id"]] = r
    return out


def _is_unknown(loc: dict[str, Any], resolve_zone) -> bool:
    if resolve_zone(loc.get("zone")) == "other":
        return True
    if _UNSOURCED.search(str(loc.get("source") or "")) or not str(loc.get("description") or "").strip():
        return True
    return _RANK.get(str(loc.get("confidence") or "").lower(), 0) == 0


def _as_location(r: dict[str, Any], vin: str) -> dict[str, Any]:
    return {"zone": r["zone"], "description": r.get("description", ""), "access": r.get("access", ""),
            "source": r.get("source", ""), "confidence": r.get("confidence", ""),
            "tech_entry": True, "entry_id": r.get("id"), "entered_by": r.get("by"),
            "entered_at": r.get("at"),
            "from_other_car": (r.get("vin") or "").upper() != (vin or "").upper()}


def overlay_location(entry: Optional[dict[str, Any]], vin: str, current: Optional[dict[str, Any]],
                     resolve_zone) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    """(location to use, proposed correction or None)."""
    current = dict(current or {})
    if not entry:
        return current, None
    mine = _as_location(entry, vin)
    if _is_unknown(current, resolve_zone):
        return mine, None
    cur_rank = _RANK.get(str(current.get("confidence") or "").lower(), 0)
    if _RANK.get(mine["confidence"], 0) > cur_rank:
        return mine, None
    return current, mine


def apply_to_elements(vin: str, elements: dict[str, dict[str, Any]], resolve_zone) -> dict[str, dict[str, Any]]:
    entries = latest_for_model(vin)
    for eid, e in elements.items():
        ent = entries.get(eid)
        if ent:
            loc, prop = overlay_location(ent, vin, e.get("location"), resolve_zone)
            e["location"] = loc
            if prop:
                e["location_proposed"] = prop
    return elements


def apply_to_hops(vin: str, hops: list[dict[str, Any]], resolve_zone) -> None:
    entries = latest_for_model(vin)
    for h in hops:
        ent = entries.get(h.get("id") or "")
        if not ent:
            continue
        loc, prop = overlay_location(ent, vin, h.get("location"), resolve_zone)
        h["location"] = loc
        if prop:
            h["location_proposed"] = prop
        else:
            h["source"], h["confidence"] = loc.get("source"), loc.get("confidence")
