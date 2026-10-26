"""Real component photos for CUORE items, from the owner's locally saved parts
catalogue (``<state dir>/parts_catalog/<id>/``).

Part numbers and photo files live only in the state dir and are read at runtime.
``cuore/data/component_image_keys.json`` maps CUORE item ids (sensor ids, fuse
types, ...) to *search terms* only. A photo shows the catalogue part, not this
car's own part. No catalogue -> every function returns ``[]``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from . import parts_catalog as pc

KEYS_FILE = Path(__file__).resolve().parents[1] / "data" / "component_image_keys.json"
_idx: dict[str, Any] = {"sig": None, "rows": [], "shared": {}}
# a photo file used by this many distinct part numbers is a brand / logo / "no image" placeholder, not a part photo
PLACEHOLDER_MIN_PARTS = 5
_HINT = re.compile(r"logo|placeholder|no[-_ ]?image|coming[-_ ]?soon|genuine[-_ ]?parts|badge", re.I)


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
    shared: dict[str, set] = {}
    for d in (cat.get("diagrams") or {}).values():
        for p in d.get("parts") or []:
            for ph in p.get("photos") or []:
                if ph.get("file"):
                    shared.setdefault(ph["file"], set()).add(pc.norm_pn(p.get("pn", "")))
    for did, d in (cat.get("diagrams") or {}).items():
        for p in d.get("parts") or []:
            pn = pc.norm_pn(p.get("pn", ""))
            photos = [ph.get("file") for ph in (p.get("photos") or []) if ph.get("file")]
            if not pn or not photos or pn in seen:
                continue
            seen.add(pn)
            rows.append({"pn": p.get("pn", ""), "name": p.get("name", ""), "description": p.get("description", ""),
                         "own": p.get("fitment") == "own", "diagram_id": did,
                         "photo_url": f"/catalog/img/{cid}/{photos[0]}", "_files": photos, "_cid": cid,
                         "part_url": f"/catalog/p/{p.get('pn', '')}",
                         "_text": f"{p.get('name', '')} {p.get('description', '')}".lower()})
    _idx.update(sig=sig, rows=rows, shared={f: len(v) for f, v in shared.items()})
    return rows


def is_placeholder(photo: Any, name: str = "", description: str = "") -> bool:
    """True when a catalogue photo is a brand / logo placeholder rather than a real part photo: the same file is used by
    >= PLACEHOLDER_MIN_PARTS distinct part numbers, or the file name / url / part name hints logo / placeholder.
    ``photo``: a photo URL or file name, or one of this module's result dicts."""
    if isinstance(photo, dict):
        url, name, description = str(photo.get("photo_url") or photo.get("url") or photo.get("file") or ""),             photo.get("name", name), photo.get("description", description)
    else:
        url = str(photo or "")
    _rows()
    f = url.rsplit("/", 1)[-1]
    if _idx["shared"].get(f, 0) >= PLACEHOLDER_MIN_PARTS:
        return True
    return bool(_HINT.search(f"{url} {name or ''} {description or ''}"))


def _pick(r: dict[str, Any], exclude: bool) -> Optional[dict[str, Any]]:
    """Result dict for a row; with ``exclude`` the first non-placeholder photo, or None when the part has only placeholders."""
    out = {k: r[k] for k in ("pn", "name", "description", "photo_url", "part_url", "diagram_id")}
    if not exclude:
        return out
    for f in r["_files"]:
        url = f"/catalog/img/{r['_cid']}/{f}"
        if not is_placeholder(url, r["name"], r["description"]):
            out["photo_url"] = url
            return out
    return None


def _out(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in ("pn", "name", "description", "photo_url", "part_url", "diagram_id")}


def images_for_pn(pn: str, *, exclude_placeholders: bool = True) -> list[dict[str, Any]]:
    n = pc.norm_pn(pn)
    out = [_pick(r, exclude_placeholders) for r in _rows() if pc.norm_pn(r["pn"]) == n]
    return [o for o in out if o][:1]


def images_for(terms: list[str], *, fitment_own: bool = True, limit: int = 3,
               exclude_placeholders: bool = True) -> list[dict[str, Any]]:
    ts = [t.lower().strip() for t in (terms or []) if t and t.strip()]
    if not ts:
        return []
    hits = [r for r in _rows() if all(t in r["_text"] for t in ts) and (r["own"] or not fitment_own)]
    hits.sort(key=lambda r: not r["own"])  # stable: fitting parts first
    out = [_pick(r, exclude_placeholders) for r in hits]
    return [o for o in out if o][:max(0, limit)]


def keys() -> dict[str, list[str]]:
    try:
        data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, list)}


def images_for_key(key: str, *, limit: int = 3, exclude_placeholders: bool = True) -> list[dict[str, Any]]:
    terms = keys().get(key)
    return images_for(terms, limit=limit, exclude_placeholders=exclude_placeholders) if terms else []
