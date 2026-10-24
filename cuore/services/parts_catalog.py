"""Read-only access to the full parts catalogue (every diagram and part number
for the car), built by ``scripts/parts/build_parts_catalog.py`` into
``<state dir>/parts_catalog/<id>/``.

The curated job parts in :mod:`cuore.services.parts_bridge` (``/v/{vin}/parts``)
stay the place for what-it-does, aftermarket and buy links; this module is the
complete catalogue -- schematic, callout, part number, name, notes -- and links
each catalogue part back to the curated card, the torque library, CUORE's own
records and the TSB catalogue when they mention it.

Every value says where it came from: catalogue rows are the dealer
catalogue's; torque rows carry the torque library's own confidence and
source; ``mechanic.json`` notes (written by research agents) carry theirs.
Nothing here touches the car or the adapter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live.config import state_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
TSB_CATALOGUE = REPO_ROOT / "cuore" / "data" / "tsb_catalogue.json"
_ID_RE = re.compile(r"^[a-z0-9.-]{1,80}$")
_IMG_RE = re.compile(r"^[a-f0-9]{20}\.(png|jpg|jpeg|webp|gif|img)$")
#: CUORE's own record files searched for a part number (state dir).
_RECORD_FILES = ("jobs.jsonl", "notes.jsonl", "symptoms.jsonl", "observations.jsonl", "shop_visits.jsonl")

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def root() -> Path:
    return state_dir() / "parts_catalog"


def norm_pn(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def catalog_ids() -> list[str]:
    r = root()
    if not r.is_dir():
        return []
    return sorted(d.name for d in r.iterdir() if (d / "catalog.json").is_file())


def default_id() -> Optional[str]:
    ids = catalog_ids()
    return ids[0] if ids else None


def load(cid: Optional[str] = None) -> Optional[dict[str, Any]]:
    """The catalogue plus derived indexes; ``None`` when not built yet."""
    cid = cid or default_id()
    if not cid or not _ID_RE.match(cid):
        return None
    p = root() / cid / "catalog.json"
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    hit = _cache.get(cid)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        cat = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    by_pn: dict[str, list[tuple[str, int]]] = {}
    for did, d in cat.get("diagrams", {}).items():
        for i, part in enumerate(d.get("parts", [])):
            by_pn.setdefault(norm_pn(part.get("pn", "")), []).append((did, i))
    cat["_by_pn"] = by_pn
    cat["_sections"] = {s["slug"]: s for s in cat.get("sections", [])}
    cat["_groups"] = {g["id"]: g for g in cat.get("groups", [])}
    cat["_mechanic"] = _load_mechanic(root() / cid)
    _cache[cid] = (mtime, cat)
    return cat


def _load_mechanic(d: Path) -> dict[str, Any]:
    """Merged ``mechanic*.json`` files: {diagrams:{}, sections:{}, groups:{}}."""
    out: dict[str, dict[str, Any]] = {"diagrams": {}, "sections": {}, "groups": {}}
    for f in sorted(d.glob("mechanic*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for k in out:
            for key, val in (data.get(k) or {}).items():
                if isinstance(val, dict):
                    out[k][key] = val
    return out


def image_path(cid: str, name: str) -> Optional[Path]:
    if not _ID_RE.match(cid or "") or not _IMG_RE.match(name or ""):
        return None
    p = root() / cid / "img" / name
    return p if p.is_file() else None


def stats(cat: dict[str, Any]) -> dict[str, int]:
    ds = cat.get("diagrams", {})
    return {"sections": len(cat.get("sections", [])), "diagrams": len(ds),
            "rows": sum(len(d["parts"]) for d in ds.values()), "part_numbers": len(cat["_by_pn"])}


def groups_view(cat: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for g in cat.get("groups", []):
        secs = []
        for slug in g.get("sections", []):
            s = cat["_sections"].get(slug)
            if not s:
                continue
            ds = [cat["diagrams"][d] for d in s["diagrams"] if d in cat["diagrams"]]
            secs.append({**s, "diagram_objs": ds, "part_count": sum(len(d["parts"]) for d in ds)})
        if secs:
            out.append({**g, "section_objs": secs})
    return out


def search(cat: dict[str, Any], q: str, limit: int = 300) -> list[dict[str, Any]]:
    """Part-number match first (exact, then partial), else every word in the text."""
    q = (q or "").strip()
    if not q:
        return []
    n = norm_pn(q)
    hits: list[tuple[str, int]] = []
    if len(n) >= 4 and any(c.isdigit() for c in n):
        exact = cat["_by_pn"].get(n, [])
        partial = [x for pn, xs in cat["_by_pn"].items() if n in pn and pn != n for x in xs]
        hits = exact + partial
    if not hits:
        words = [w for w in re.split(r"\s+", q.lower()) if w]
        for did, d in cat["diagrams"].items():
            ctx = f"{d['title']} {d['section']}".lower()
            for i, p in enumerate(d["parts"]):
                text = f"{p['name']} {p['description']} {p['notes']} {p['pn']} {ctx}".lower()
                if all(w in text for w in words):
                    hits.append((did, i))
    out, seen = [], set()
    for did, i in hits:
        d = cat["diagrams"][did]
        p = d["parts"][i]
        key = (p["pn"], did)
        if key in seen:
            continue
        seen.add(key)
        out.append({**p, "diagram_id": did, "diagram_title": d["title"], "section": d["section"],
                    "group": d["group"], "image": d["image"]})
        if len(out) >= limit:
            break
    return out


# --- what the mechanic needs to know ----------------------------------------

def _torque_rows(spec: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        from mes import service_specs
        rows += [t for t in service_specs.TORQUES if set(t.get("categories", [])) & set(spec.get("service", []))]
    except Exception:  # noqa: BLE001 -- the torque library is optional here
        pass
    try:
        from mes import drivetrain_specs
        rows += [t for t in drivetrain_specs.TORQUES if t.get("section") in spec.get("drivetrain", [])]
    except Exception:  # noqa: BLE001
        pass
    seen, out = set(), []
    for t in rows:
        if t["key"] not in seen:
            seen.add(t["key"])
            out.append(t)
    return out


def mechanic_for_diagram(cat: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    sec = cat["_sections"].get(d["slug"], {})
    m = cat["_mechanic"]
    notes = [x for x in (m["diagrams"].get(d["id"]), m["sections"].get(d["slug"]), m["groups"].get(d["group"])) if x]
    return {"torque": _torque_rows(sec.get("torque") or {}), "notes": notes}


def diagram(cat: dict[str, Any], did: str) -> Optional[dict[str, Any]]:
    d = cat.get("diagrams", {}).get(did)
    if not d:
        return None
    sec = cat["_sections"].get(d["slug"], {})
    ids = sec.get("diagrams", [])
    i = ids.index(did) if did in ids else -1
    return {**d, "section_obj": sec, "group_obj": cat["_groups"].get(d["group"], {}),
            "prev": ids[i - 1] if i > 0 else None, "next": ids[i + 1] if 0 <= i < len(ids) - 1 else None,
            "siblings": [cat["diagrams"][x] for x in ids if x in cat["diagrams"]],
            "mechanic": mechanic_for_diagram(cat, d)}


def _record_refs(pn: str) -> list[dict[str, Any]]:
    out = []
    pat = re.compile(re.escape(pn), re.I)
    for name in _RECORD_FILES:
        f = state_dir() / name
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            m = pat.search(line)
            if not m:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                rec = {}
            text = rec.get("text") or rec.get("complaint") or line
            j = text.upper().find(pn.upper())
            excerpt = text[max(0, j - 140): j + 160] if j >= 0 else text[:300]
            out.append({"kind": name.replace(".jsonl", ""), "id": rec.get("id") or rec.get("job_id") or "",
                        "job_id": rec.get("job_id") or "", "at": rec.get("at") or "", "excerpt": excerpt})
    return out[-12:]


def _tsb_refs(pn: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(TSB_CATALOGUE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for item in data.get("items", []):
        if pn.upper() in json.dumps(item).upper():
            out.append({"id": item.get("id") or item.get("number") or "", "title": item.get("title") or item.get("summary") or ""})
    return out


def _curated(pn: str) -> list[dict[str, Any]]:
    n = norm_pn(pn)
    try:
        from . import parts_bridge
        rows = parts_bridge.all_parts()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in rows:
        nums = [norm_pn(o.get("number") or "") for o in r.get("oem") or []]
        if any(x and len(x) >= 7 and (x == n or x.lstrip("0") == n.lstrip("0")
                                      or n.lstrip("0").startswith(x.lstrip("0"))) for x in nums):
            out.append(r)
    return out


def part(cat: dict[str, Any], pn: str) -> Optional[dict[str, Any]]:
    n = norm_pn(pn)
    locs = cat["_by_pn"].get(n)
    if not locs:
        return None
    appearances, photos, seen_img, torque, notes = [], [], set(), {}, []
    for did, i in locs:
        d = cat["diagrams"][did]
        p = d["parts"][i]
        callout = [x for x in d["parts"] if x["ref"] == p["ref"] and x["pn"] != p["pn"]] if p["ref"] else []
        appearances.append({"diagram": d, "row": p, "callout_mates": callout})
        for ph in p.get("photos", []):
            if ph["file"] and ph["file"] not in seen_img:
                seen_img.add(ph["file"]); photos.append({**ph, "kind": "part photo"})
        if d["image"].get("file") and d["image"]["file"] not in seen_img:
            seen_img.add(d["image"]["file"])
            photos.append({**d["image"], "kind": f"diagram: {d['title']} (callout {p['ref'] or '-'})", "diagram_id": did})
        mech = mechanic_for_diagram(cat, d)
        for t in mech["torque"]:
            torque.setdefault(t["key"], t)
        for x in mech["notes"]:
            if x not in notes:
                notes.append(x)
    first = appearances[0]["row"]
    pn_shown = first["pn"]
    return {"pn": pn_shown, "name": first["name"],
            "names": sorted({a["row"]["name"] for a in appearances}),
            "descriptions": sorted({a["row"]["description"] for a in appearances if a["row"]["description"]}),
            "notes": sorted({a["row"]["notes"] for a in appearances if a["row"]["notes"]}),
            "fitment": sorted({a["row"]["fitment"] for a in appearances if a["row"]["fitment"]}),
            "source_urls": sorted({a["row"]["url"] for a in appearances if a["row"]["url"]}),
            "appearances": appearances, "photos": photos,
            "torque": list(torque.values()), "mechanic_notes": notes,
            "records": _record_refs(pn_shown), "tsbs": _tsb_refs(pn_shown), "curated": _curated(pn_shown)}
