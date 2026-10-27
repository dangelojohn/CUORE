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


# --- placement in the parts catalogue --------------------------------------

#: Mopar number family of the engine oil filter (04892339AB per FCA TSB 01-001-26).
OIL_FILTER_PN_FAMILY = "4892339"
OIL_FILTER_COMPARE_PN = "04892339AB"
OIL_FILTER_QUESTION = ("Spin-on vs cartridge is not settled by any official source; "
                       f"compare with {OIL_FILTER_COMPARE_PN}.")
_NOT_IN_EXPORT = "standard on this car (not in the Mopar catalogue export)"


def _npn(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def label(s: dict[str, Any]) -> str:
    """Short chip label, e.g. ``HENGST H98W`` (brand's first word + number)."""
    brand = (s.get("brand") or "").split()
    return " ".join(x for x in ((brand[0] if brand else ""), s.get("part_number") or "") if x)


def question(s: dict[str, Any]) -> str:
    return OIL_FILTER_QUESTION if s.get("key") == "oil_filter" else ""


def _oil_filter_row(d: dict[str, Any], p: dict[str, Any]) -> bool:
    if p.get("fitment") == "other-engine":
        return False
    if _npn(p.get("pn", "")).lstrip("0").startswith(OIL_FILTER_PN_FAMILY):
        return True
    slug = d.get("slug", "")
    if "transmission" in slug or slug.startswith("8hp"):
        return False
    if not any(k in slug for k in ("oiling", "service-kit", "lubric")):
        return False
    name = re.sub(r"[^a-z]", "", (p.get("name") or "").lower())
    return name in ("filterengineoil", "engineoilfilter", "oilfilter", "filteroil")


def _oil_filter_diagram(cat: dict[str, Any]) -> str:
    """Where a standard oil filter with no catalogue row sits: the oil-filter
    diagram, else the engine-oiling section's oil-cooler/first diagram."""
    ds = cat.get("diagrams", {})
    for did, d in ds.items():
        if "oil filter" in (d.get("title") or "").lower() and "transmission" not in did:
            return did
    oiling = [did for did, d in ds.items() if "engine-oiling" in d.get("slug", "") and "transmission" not in d.get("slug", "")]
    for did in oiling:
        if "oil cooler" in (ds[did].get("title") or "").lower():
            return did
    return oiling[0] if oiling else ""


def attach(cat: dict[str, Any] | None, standard: list[dict[str, Any]]) -> dict[str, Any]:
    """Where each standard part lives in the catalogue.

    ``by_pn``  {normalised catalogue pn: standard part}  (matched rows)
    ``own``    {diagram id: [standard part]}  (no matching row: its own row there)
    Never drops a part: with no oiling section at all it still lands in ``own[""]``.
    """
    out: dict[str, Any] = {"by_pn": {}, "own": {}, "where": {}}
    if not cat:
        return out
    for s in standard:
        if s.get("key") != "oil_filter":
            continue
        found = [(did, p) for did, d in cat.get("diagrams", {}).items() for p in d.get("parts", []) if _oil_filter_row(d, p)]
        if found:
            for did, p in found:
                out["by_pn"][_npn(p["pn"])] = s
            out["where"][s["key"]] = {"pn": found[0][1]["pn"], "diagram": found[0][0], "mode": "attached"}
        else:
            did = _oil_filter_diagram(cat)
            out["own"].setdefault(did, []).append(s)
            out["where"][s["key"]] = {"pn": "", "diagram": did, "mode": "own-row"}
    return out


def own_row(s: dict[str, Any]) -> dict[str, Any]:
    """A listing row for a standard part that has no catalogue row."""
    return {"ref": "–", "pn": s.get("part_number") or "", "name": s.get("role") or s.get("key"),
            "description": f"{s.get('brand', '')} {s.get('part_number', '')}".strip(),
            "notes": "", "fitment": "own", "info": {}, "specs": [], "standard": s, "own_row": True,
            "flag": _NOT_IN_EXPORT, "anchor": f"standard-{s.get('key')}"}


_STOP = {"on", "the", "a", "this", "car", "standard"}


def search(cat: dict[str, Any] | None, standard: list[dict[str, Any]], q: str, att: dict[str, Any]) -> list[dict[str, Any]]:
    """Search hits for standard parts (H98W, Hengst, oil filter ...), shaped like catalogue hits."""
    words = [w for w in re.split(r"\s+", (q or "").lower()) if w and w not in _STOP]
    if not cat or not words:
        return []
    out = []
    for s in standard:
        text = " ".join([s.get("brand", ""), s.get("part_number", ""), s.get("role", ""), s.get("title", ""),
                         s.get("type", ""), s.get("ean", ""), " ".join(s.get("oe_alfa", [])),
                         " ".join(o.get("number", "") for o in s.get("oe_numbers", []))]).lower()
        if s.get("key") == "oil_filter":
            text += " oil filter engine oil filter"
        compact = _npn(text)
        if not all(w in text or _npn(w) in compact for w in words):
            continue
        where = att["where"].get(s["key"])
        if not where or not where["diagram"] and where["mode"] == "own-row":
            continue
        d = cat["diagrams"].get(where["diagram"], {})
        if where["mode"] == "attached":
            href = f"/catalog/p/{where['pn']}"
            pn = where["pn"]
        else:
            href = f"/catalog/d/{where['diagram']}#standard-{s['key']}"
            pn = s.get("part_number", "")
        out.append({"ref": "", "pn": pn, "name": s.get("role") or s["key"], "description": "", "notes": "",
                    "fitment": "own", "diagram_id": where["diagram"], "diagram_title": d.get("title", ""),
                    "section": d.get("section", ""), "standard": s, "href": href,
                    "flag": "" if where["mode"] == "attached" else _NOT_IN_EXPORT})
    return out
