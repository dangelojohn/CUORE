"""Static reference data shipped with cuore (JSON files beside this module).

:func:`load_tsb_catalogue` reads ``tsb_catalogue.json`` -- the per-car list
of technical service bulletins, recalls, CSNs, campaigns and extended
coverage. The schema is documented inside the file itself (``_schema``).
The loader is deliberately tolerant: merge steps append rows compiled from
NHTSA / Transport Canada, so unknown fields pass through untouched and every
optional field gets a default. Only ``id`` is required; rows without one are
dropped, and a duplicate id keeps the first row.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

KINDS = ("tsb", "recall", "csn", "campaign", "extended_warranty", "emissions")
APPLIES = ("yes", "no", "vin_check")

_DEFAULTS: dict[str, Any] = {
    "kind": "tsb", "number": None, "nhtsa_id": None, "title": "", "date": None,
    "summary": "", "condition": None, "remedy": None, "systems": [], "dtcs": [],
    "links": [], "applies": "vin_check", "source": None, "verified": False,
}


def _read_text(name: str) -> str:
    try:  # package-safe (zip/wheel installs)
        return resources.files(__name__).joinpath(name).read_text(encoding="utf-8")
    except (AttributeError, FileNotFoundError, ModuleNotFoundError, OSError):
        return (Path(__file__).resolve().parent / name).read_text(encoding="utf-8")


def _norm_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not str(raw.get("id") or "").strip():
        return None
    item = dict(raw)
    for k, v in _DEFAULTS.items():
        if item.get(k) is None:
            item[k] = list(v) if isinstance(v, list) else v
    item["id"] = str(item["id"]).strip()
    item["number"] = item["number"] or item["id"]
    item["kind"] = str(item["kind"]).strip().lower()
    if item["applies"] not in APPLIES:
        item["applies"] = "vin_check"
    for k in ("systems", "dtcs"):
        v = item[k]
        item[k] = [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]
    links = item["links"]
    if isinstance(links, dict):
        links = [links]
    item["links"] = [lk for lk in (links if isinstance(links, list) else [])
                     if isinstance(lk, dict) and lk.get("url")]
    return item


def load_tsb_catalogue(text: str | None = None) -> dict[str, Any]:
    """``{"vehicle", "updated", "items": [...]}`` with every item normalised.
    ``text`` overrides the shipped file (tests, merge previews)."""
    data = json.loads(text if text is not None else _read_text("tsb_catalogue.json"))
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for raw in data.get("items") or []:
        item = _norm_item(raw)
        if item is None or item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append(item)
    return {"vehicle": data.get("vehicle") or {}, "updated": data.get("updated"),
            "items": items}


__all__ = ["KINDS", "APPLIES", "load_tsb_catalogue"]
