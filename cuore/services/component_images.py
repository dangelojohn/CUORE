"""Real component photos for CUORE items, from the owner's locally saved parts
catalogue (``<state dir>/parts_catalog/<id>/``).

Part numbers and photo files live only in the state dir and are read at runtime.
``cuore/data/component_image_keys.json`` maps CUORE item ids (sensor ids, fuse
types, ...) to *search terms* only. A photo shows the catalogue part, not this
car's own part. No catalogue -> every function returns ``[]``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from . import parts_catalog as pc

KEYS_FILE = Path(__file__).resolve().parents[1] / "data" / "component_image_keys.json"
_idx: dict[str, Any] = {"sig": None, "rows": []}


def _rows() -> list[dict[str, Any]]:
    cid = pc.default_id()
    if not cid:
        return []
    cat = pc.load(cid)
    if not cat:
        return []
    sig = (str(pc.root()), cid, id(cat))
    if _idx["sig"] == sig:
        return _idx["rows"]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for did, d in (cat.get("diagrams") or {}).items():
        for p in d.get("parts") or []:
            pn = pc.norm_pn(p.get("pn", ""))
            photos = [ph.get("file") for ph in (p.get("photos") or []) if ph.get("file")]
            if not pn or not photos or pn in seen:
                continue
            seen.add(pn)
            rows.append({"pn": p.get("pn", ""), "name": p.get("name", ""), "description": p.get("description", ""),
                         "own": p.get("fitment") == "own", "diagram_id": did,
                         "photo_url": f"/catalog/img/{cid}/{photos[0]}",
                         "part_url": f"/catalog/p/{p.get('pn', '')}",
                         "_text": f"{p.get('name', '')} {p.get('description', '')}".lower()})
    _idx.update(sig=sig, rows=rows)
    return rows


def _out(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in ("pn", "name", "description", "photo_url", "part_url", "diagram_id")}


def images_for_pn(pn: str) -> list[dict[str, Any]]:
    n = pc.norm_pn(pn)
    return [_out(r) for r in _rows() if pc.norm_pn(r["pn"]) == n][:1]


def images_for(terms: list[str], *, fitment_own: bool = True, limit: int = 3) -> list[dict[str, Any]]:
    ts = [t.lower().strip() for t in (terms or []) if t and t.strip()]
    if not ts:
        return []
    hits = [r for r in _rows() if all(t in r["_text"] for t in ts) and (r["own"] or not fitment_own)]
    hits.sort(key=lambda r: not r["own"])  # stable: fitting parts first
    return [_out(r) for r in hits[:max(0, limit)]]


def keys() -> dict[str, list[str]]:
    try:
        data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, list)}


def images_for_key(key: str, *, limit: int = 3) -> list[dict[str, Any]]:
    terms = keys().get(key)
    return images_for(terms, limit=limit) if terms else []
