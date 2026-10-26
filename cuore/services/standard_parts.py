"""Standard parts: the part the owner always fits on this car (owner-attested).

Data lives only in the state dir (``parts_catalog/standard_parts.json`` plus
``parts_catalog/sources/standard/``), never in the repo. Read-only. Missing or
corrupt files give an empty result, never an exception.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..live.config import state_dir

#: Strict file name for a standard-part photo.
_IMG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}\.(jpg|jpeg|png|webp)$")
#: Specs worth showing large; the rest sit in a fold.
KEY_SPECS = ("Height", "Thread Size", "Inner Diameter [mm]", "Diameter")


def _base() -> Path:
    return state_dir() / "parts_catalog"


def img_dir() -> Path:
    return _base() / "sources" / "standard" / "img"


def image_path(name: str) -> Path | None:
    """The photo file for ``name``, or None (bad name, traversal, missing)."""
    if not isinstance(name, str) or not _IMG_RE.match(name):
        return None
    try:
        base = img_dir().resolve()
        p = (base / name).resolve()
        p.relative_to(base)
    except (OSError, ValueError):
        return None
    return p if p.is_file() else None


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _detail(rel: str) -> dict[str, Any]:
    if not isinstance(rel, str) or not rel:
        return {}
    try:
        root = (_base() / "sources" / "standard").resolve()
        p = (_base() / rel).resolve()
        p.relative_to(root)
    except (OSError, ValueError):
        return {}
    d = _read_json(p)
    return d if isinstance(d, dict) else {}


def _image_names(entry: dict[str, Any]) -> list[str]:
    out = []
    for rel in entry.get("images") or []:
        name = str(rel).replace("\\", "/").rsplit("/", 1)[-1]
        if image_path(name):
            out.append(name)
    return out


def sole_vin() -> str:
    """The VIN when the file holds exactly one vehicle (the catalogue is for one car), else ''."""
    data = _read_json(_base() / "standard_parts.json")
    veh = data.get("vehicles") if isinstance(data, dict) else None
    return next(iter(veh)) if isinstance(veh, dict) and len(veh) == 1 else ""


def for_vin(vin: str) -> list[dict[str, Any]]:
    """Standard parts for ``vin``, details merged; ``[]`` when none/unreadable."""
    data = _read_json(_base() / "standard_parts.json")
    veh = (data or {}).get("vehicles") if isinstance(data, dict) else None
    mine = veh.get((vin or "").strip().upper()) if isinstance(veh, dict) else None
    if not isinstance(mine, dict):
        return []
    out = []
    for key, e in mine.items():
        if not isinstance(e, dict):
            continue
        d = _detail(e.get("detail_file", ""))
        specs = d.get("specs") if isinstance(d.get("specs"), dict) else {}
        oe = [o for o in (d.get("oe_numbers") or []) if isinstance(o, dict) and o.get("number")]
        rr = e.get("retailer_ref") if isinstance(e.get("retailer_ref"), dict) else {}
        out.append({
            "key": key, "role": e.get("role") or key, "brand": e.get("brand") or d.get("brand") or "",
            "part_number": e.get("part_number") or d.get("article_number") or "",
            "ean": e.get("ean") or d.get("ean") or "", "type": e.get("type") or "",
            "thread": e.get("thread") or "", "basis": e.get("basis") or "", "status": e.get("status") or "",
            "title": d.get("title") or "", "images": _image_names(e),
            "key_specs": [(k, specs[k]) for k in KEY_SPECS if specs.get(k)],
            "other_specs": [(k, v) for k, v in specs.items() if k not in KEY_SPECS],
            "oe_alfa": [str(x) for x in (e.get("oe_alfa") or [])],
            "oe_numbers": oe, "advantages": d.get("advantages") or "",
            "retailer": {"shop": rr.get("shop", ""), "price": rr.get("price", ""),
                         "fetched": rr.get("fetched", ""), "url": rr.get("url", "")} if rr.get("price") else None,
        })
    return out


def oil_filter(vin: str) -> dict[str, Any] | None:
    for p in for_vin(vin):
        if p["key"] == "oil_filter":
            return p
    return None


def oil_filter_conflict(vin: str) -> dict[str, Any] | None:
    """The standard oil filter when it is spin-on (so the cartridge/housing-cap
    notes in service_specs do not apply), else None."""
    p = oil_filter(vin)
    return p if p and p["type"].strip().lower() == "spin-on" else None
