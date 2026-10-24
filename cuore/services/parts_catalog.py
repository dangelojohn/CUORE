"""Read-only access to the full parts catalogue (every diagram and part number
for the car), built by ``scripts/parts/build_parts_catalog.py`` into
``<state dir>/parts_catalog/<id>/``.

The curated job parts in :mod:`cuore.services.parts_bridge` (``/v/{vin}/parts``)
stay the place for what-it-does, aftermarket and buy links; this module is the
complete catalogue -- schematic, callout, part number, name, notes -- and links
each catalogue part back to the curated card, the torque library, CUORE's own
records and the TSB catalogue when they mention it.

Built around the mechanic's question "what is the torque on this fastener,
and is this the part?": every torque value (CUORE torque library or research
notes) becomes one *spec* row with Nm and ft-lb, angle, single-use flag,
confidence and source; specs are matched to the catalogue rows they name
(``match_specs``, by words, labelled as a name match) and are searchable.

Every value says where it came from: catalogue rows are the dealer
catalogue's; torque rows carry the torque library's own confidence and
source; ``mechanic*.json`` notes (written by research agents) carry theirs.
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
#: Words a mechanic adds to a search that never appear in part text.
_SEARCH_STOP = {"torque", "torques", "spec", "specs", "specification", "nm", "ft", "lb", "lbs", "ftlb",
                "ft-lb", "value", "tighten", "tightening", "for", "the", "of", "on", "what", "is", "a"}
_FASTENER = re.compile(r"\b(bolts?|nuts?|screws?|studs?|plugs?|fasteners?)\b")
#: Words too common to identify which fastener a spec means.
_MATCH_STOP = {"bolt", "bolts", "nut", "nuts", "screw", "screws", "stud", "studs", "plug", "plugs", "front",
               "rear", "left", "right", "brake", "assembly", "and", "or", "to", "the", "of", "with", "x", "kit",
               "mounting", "mount", "retaining", "fastener", "fasteners", "fitting", "lh", "rh", "upper",
               "lower", "inner", "outer", "zf", "8hp", "transmission"}

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
        mtime = max([p.stat().st_mtime] + [f.stat().st_mtime for f in (root() / cid).glob("mechanic*.json")])
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


def _section_view(cat: dict[str, Any], slug: str) -> Optional[dict[str, Any]]:
    s = cat["_sections"].get(slug)
    if not s:
        return None
    ds = [cat["diagrams"][d] for d in s["diagrams"] if d in cat["diagrams"]]
    return {**s, "diagram_objs": ds, "part_count": sum(len(d["parts"]) for d in ds),
            "spec_count": len([x for x in section_specs(cat, slug) if x["known"]])}


def groups_view(cat: dict[str, Any]) -> list[dict[str, Any]]:
    """Group tiles: title, counts and one cover image each (no per-diagram cards)."""
    out = []
    for g in cat.get("groups", []):
        secs = [s for s in (_section_view(cat, slug) for slug in g.get("sections", [])) if s]
        if not secs:
            continue
        cover = next((d["image"] for s in secs for d in s["diagram_objs"] if d["image"].get("file")), {})
        out.append({**g, "section_objs": secs, "cover": cover,
                    "diagram_count": sum(len(s["diagram_objs"]) for s in secs),
                    "part_count": sum(s["part_count"] for s in secs)})
    return out


def group(cat: dict[str, Any], gid: str) -> Optional[dict[str, Any]]:
    return next((g for g in groups_view(cat) if g["id"] == gid), None)


# --- specs: torque values in one shape ---------------------------------------

def _num(x: Any) -> str:
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


def _library_rows(spec: dict[str, list[str]]) -> list[dict[str, Any]]:
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
    return rows


def _from_library(t: dict[str, Any]) -> dict[str, Any]:
    nm, lbft = t.get("value_nm"), t.get("value_lbft")
    if nm is not None:
        value = f"{_num(nm)} Nm"
        alt = f"{_num(lbft)} ft-lb" if lbft is not None else ""
    else:
        value, alt = (t.get("display") or ""), ""
    known = (t.get("confidence") != "UNKNOWN") and nm is not None or bool(t.get("value_range"))
    if t.get("value_range") and nm is None:
        value = t.get("display") or str(t["value_range"])
    return {"key": "lib:" + t["key"], "item": t.get("component", ""), "value": value, "alt": alt,
            "angle": t.get("angle") or "", "single_use": bool(t.get("single_use")),
            "confidence": t.get("confidence", ""), "source": t.get("source") or "", "notes": t.get("notes") or "",
            "origin": "CUORE torque library", "known": bool(known)}


_NM = re.compile(r"(\d+(?:\.\d+)?)\s*N\s*[·.]?\s*m\b", re.I)
_LBFT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:ft[-\s]?lbs?|lb[-\s]?ft)\b", re.I)


def _from_research(t: dict[str, Any], i: int, slug: str) -> dict[str, Any]:
    raw = str(t.get("value", ""))
    nm, lb = _NM.search(raw), _LBFT.search(raw)
    alt = ""
    if nm and not lb:
        alt = f"{float(nm.group(1)) * 0.7376:.0f} ft-lb"
    angle = ""
    m = re.search(r"\+\s*\d+\s*°|\d+\s*(?:°|deg(?:rees)?)", raw)
    if m:
        angle = m.group(0)
    return {"key": f"res:{slug}:{i}", "item": t.get("item", ""), "value": raw, "alt": alt, "angle": angle,
            "single_use": bool(re.search(r"single[- ]use|replace", raw, re.I)),
            "confidence": t.get("confidence", ""), "source": t.get("source", ""), "notes": "",
            "origin": "research note", "known": bool(nm or lb or re.search(r"\d", raw))}


def section_specs(cat: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    """Every torque value for a section: library rows, then research rows; known first."""
    sec = cat["_sections"].get(slug) or {}
    out, seen = [], set()
    for t in _library_rows(sec.get("torque") or {}):
        s = _from_library(t)
        if s["key"] not in seen:
            seen.add(s["key"]); out.append(s)
    m = cat["_mechanic"]
    group_id = sec.get("group", "")
    for scope, key in (("sections", slug), ("groups", group_id)):
        for i, t in enumerate((m[scope].get(key) or {}).get("torque") or []):
            s = _from_research(t, i, key)
            if s["key"] not in seen:
                seen.add(s["key"]); out.append(s)
    return sorted(out, key=lambda s: (not s["known"],))


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 2 and w not in _MATCH_STOP}


def match_specs(part: dict[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Specs whose fastener description names this part (a name match, not a lookup).

    A fastener spec only matches a fastener part; at least one distinctive
    word (caliper, knuckle, drain, ...) must be shared, two when the spec
    names more than two distinctive words.
    """
    text = f"{part.get('name', '')} {part.get('description', '')}"
    pw = _words(text)
    is_fastener = bool(_FASTENER.search(text.lower()))
    out = []
    for s in specs:
        if not s["known"]:
            continue
        sw = _words(s["item"])
        if not sw:
            continue
        if bool(_FASTENER.search(s["item"].lower())) and not is_fastener:
            continue
        shared = pw & sw
        if len(shared) >= (2 if len(sw) > 2 else 1):
            out.append(s)
    return out


def mechanic_notes(cat: dict[str, Any], d: dict[str, Any]) -> list[dict[str, Any]]:
    m = cat["_mechanic"]
    return [x for x in (m["diagrams"].get(d["id"]), m["sections"].get(d["slug"]), m["groups"].get(d["group"])) if x]


# --- search -----------------------------------------------------------------

def _query_words(q: str) -> list[str]:
    return [w for w in re.split(r"\s+", (q or "").lower()) if w and w not in _SEARCH_STOP]


def search(cat: dict[str, Any], q: str, limit: int = 300) -> list[dict[str, Any]]:
    """Part-number match first (exact, then partial), else every word in the text."""
    q = (q or "").strip()
    if not q:
        return []
    n = norm_pn(q)
    hits: list[tuple[str, int]] = []
    if len(n) >= 4 and any(c.isdigit() for c in n) and " " not in q.strip():
        exact = cat["_by_pn"].get(n, [])
        partial = [x for pn, xs in cat["_by_pn"].items() if n in pn and pn != n for x in xs]
        hits = exact + partial
    words = _query_words(q)
    if not hits and words:
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
    return sorted(out, key=lambda h: h.get("fitment") == "other-engine")


def search_specs(cat: dict[str, Any], q: str, limit: int = 30) -> list[dict[str, Any]]:
    """Torque values whose fastener, section or diagram titles hold every query word."""
    words = _query_words(q)
    if not words:
        return []
    direct, loose = [], []
    for s in cat.get("sections", []):
        first = next((d for d in s["diagrams"] if d in cat["diagrams"]), None)
        for spec in section_specs(cat, s["slug"]):
            if not spec["known"]:
                continue
            row = {**spec, "section": s["title"], "diagram_id": first}
            if all(w in spec["item"].lower() for w in words):
                direct.append(row)  # the fastener itself is named
            elif all(w in f"{spec['item']} {s['title']}".lower() for w in words):
                loose.append(row)   # named only together with its section
    out = direct or loose
    seen, uniq = set(), []
    for x in out:
        if x["key"] not in seen:
            seen.add(x["key"]); uniq.append(x)
    return uniq[:limit]


# --- pages ------------------------------------------------------------------

def diagram(cat: dict[str, Any], did: str) -> Optional[dict[str, Any]]:
    d = cat.get("diagrams", {}).get(did)
    if not d:
        return None
    sec = cat["_sections"].get(d["slug"], {})
    ids = sec.get("diagrams", [])
    i = ids.index(did) if did in ids else -1
    specs = section_specs(cat, d["slug"])
    rows = [{**p, "specs": match_specs(p, specs)} for p in d["parts"]]
    refs: dict[str, list[str]] = {}
    for r in rows:
        for s in r["specs"]:
            if r["ref"] and r["ref"] not in refs.setdefault(s["key"], []):
                refs[s["key"]].append(r["ref"])
    specs = [{**s, "refs": refs.get(s["key"], [])} for s in specs]
    return {**d, "rows": rows, "section_obj": sec, "group_obj": cat["_groups"].get(d["group"], {}),
            "prev": ids[i - 1] if i > 0 else None, "next": ids[i + 1] if 0 <= i < len(ids) - 1 else None,
            "siblings": [cat["diagrams"][x] for x in ids if x in cat["diagrams"]],
            "specs": [s for s in specs if s["known"]], "specs_unknown": [s for s in specs if not s["known"]],
            "other_engine": sum(1 for p in d["parts"] if p.get("fitment") == "other-engine"),
            "notes": mechanic_notes(cat, d)}


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
            if not pat.search(line):
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
    appearances, photos, seen_img = [], [], set()
    matched: dict[str, dict[str, Any]] = {}
    assembly: dict[str, dict[str, Any]] = {}
    notes: list[dict[str, Any]] = []
    for did, i in locs:
        d = cat["diagrams"][did]
        p = d["parts"][i]
        callout = [x for x in d["parts"] if x["ref"] == p["ref"] and x["pn"] != p["pn"]] if p["ref"] else []
        appearances.append({"diagram": d, "row": p, "callout_mates": callout})
        for ph in p.get("photos", []):
            if ph["file"] and ph["file"] not in seen_img:
                seen_img.add(ph["file"]); photos.append({**ph, "kind": "part photo"})
        specs = section_specs(cat, d["slug"])
        for s in match_specs(p, specs):
            matched.setdefault(s["key"], s)
        for s in specs:
            if s["known"]:
                assembly.setdefault(s["key"], s)
        for x in mechanic_notes(cat, d):
            if x not in notes:
                notes.append(x)
    first = appearances[0]
    return {"pn": first["row"]["pn"], "name": first["row"]["name"],
            "names": sorted({a["row"]["name"] for a in appearances}),
            "descriptions": sorted({a["row"]["description"] for a in appearances if a["row"]["description"]}),
            "notes": sorted({a["row"]["notes"] for a in appearances if a["row"]["notes"]}),
            "fitment": sorted({a["row"]["fitment"] for a in appearances if a["row"]["fitment"]}),
            "source_urls": sorted({a["row"]["url"] for a in appearances if a["row"]["url"]}),
            "primary": first, "appearances": appearances, "photos": photos,
            "specs_matched": list(matched.values()),
            "specs_assembly": [s for k, s in assembly.items() if k not in matched],
            "mechanic_notes": notes,
            "records": _record_refs(first["row"]["pn"]), "tsbs": _tsb_refs(first["row"]["pn"]),
            "curated": _curated(first["row"]["pn"])}
