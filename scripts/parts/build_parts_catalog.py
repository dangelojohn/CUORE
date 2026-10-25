"""Build CUORE's parts catalogue from a saved catalogue export.

Input: the JSON the owner's browser saved from the dealer parts site
(``stelvio-2018-2.0l-catalogue.json``: ``{source, fetched_at, cats, errors,
pages: {slug: {slug, title, heads, thumbs, rows}}}``).
Output, under CUORE's state dir (never the repo -- diagram art and photos are
the catalogue publisher's): ``parts_catalog/<id>/catalog.json`` plus the
diagram images and any real part photos in ``img/``.

Grouping, exclusions and torque links come from
``cuore/data/parts_catalog_groups.json``. Images are fetched politely (one at a
time, short pause) and skipped when already on disk, so a re-run only fetches
what is new.

The site only puts the first diagram's rows in a section page; the others load
per diagram from ``/ajax/oem-assembly-panel/<slug>/<index>``. Those rows come in
a second saved file (``stelvio-2018-2.0l-diagram-rows.json``: ``{rows:
{"<slug>|<index>": [row, ...]}}``), merged in when present.

Run:  .venv/Scripts/python.exe scripts/parts/build_parts_catalog.py [export.json] [--rows rows.json] [--no-images]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cuore.live.config import state_dir  # noqa: E402

CATALOG_ID = "stelvio-2018-2.0l"
DEFAULT_EXPORT = Path.home() / "Downloads" / "stelvio-2018-2.0l-catalogue.json"
DEFAULT_ROWS = Path.home() / "Downloads" / "stelvio-2018-2.0l-diagram-rows.json"
# Other shops' Stelvio lists, saved the same way. Kept apart from the dealer
# catalogue as "listings": only what the dealer catalogue lacks, with fitment
# judged from the shop's own wording.
DEFAULT_SUPPLEMENTS = [Path.home() / "Downloads" / n for n in
                       ("stelvio-canada-aftermarket.json", "stelvio-centerline-products.json")]
_MERCH = re.compile(r"\b(sign|art print|poster|keychain|key ?ring|mug|t-?shirt|shirt|hat|baseball cap|jacket|hoodie|"
                    r"scale model|diecast|book|calendar|gift ?card|umbrella|lanyard|pin badge|display|pillow|socks?|wrapping paper|water bottle|glass|ornament|sweatshirt|blanket|towel|tumbler|coaster|apparel)\b", re.I)
_OTHER = re.compile(r"\b(qv|quadrifoglio|2\.9l?|4c|giulietta|mito|spider|gtv|brera|147|156|159|164)\b", re.I)
_OURS = re.compile(r"\b(stelvio|2\.0l?)\b", re.I)
GROUPS = ROOT / "cuore" / "data" / "parts_catalog_groups.json"
UA = "CUORE parts catalogue builder (personal workshop use)"
PLACEHOLDER = re.compile(r"/assets/images/")


def _abs(url: str) -> str:
    return "https:" + url if url.startswith("//") else url


def _img_name(url: str) -> str:
    ext = Path(url.split("?")[0]).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        ext = ".img"
    return hashlib.sha1(url.encode()).hexdigest()[:20] + ext


def _section_title(page: dict) -> str:
    t = (page.get("title") or "").strip()
    return re.sub(r"\s+for\s+\d{4}\s+.*$", "", t) or page["slug"].split("--")[-1].replace("-", " ").title()


def _diagram_title(head: str, i: int) -> str:
    m = re.match(r"^Diagram\s+\d+:\s*(.*)$", head or "")
    return (m.group(1) if m else head) or f"Diagram {i + 1}"


def _fitment(notes: str, cfg: dict) -> str:
    """'own' / 'other-engine' / '' from the row's Engines: note."""
    m = re.search(r"Engines?:\s*([^.]*(?:\.\d[^.]*)*)", notes or "", re.I)
    if not m:
        return ""
    engines = m.group(1).upper()
    if any(k.upper() in engines for k in cfg["own_engine_markers"]):
        return "own"
    if any(k.upper() in engines for k in cfg["other_engine_markers"]):
        return "other-engine"
    return ""


def merge_diagram_rows(raw: dict, rows_file: Path) -> int:
    """Add per-diagram rows to ``raw["pages"]``; a diagram that already has rows is left alone."""
    extra = json.loads(rows_file.read_text(encoding="utf-8")).get("rows") or {}
    added = 0
    for key, rows in extra.items():
        slug, _, idx = key.rpartition("|")
        page = raw["pages"].get(slug)
        if page is None or not rows:
            continue
        if any(r.get("d") == int(idx) for r in page["rows"]):
            continue
        page["rows"].extend(dict(r, d=int(idx)) for r in rows)
        added += len(rows)
    return added


def _first(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def load_listings(paths: list[Path], core_pns: set[str]) -> list[dict]:
    """Other shops' items the dealer catalogue lacks, each with a fitment
    verdict and the reason for it. Merchandise is dropped."""
    out, seen = [], set()
    for path in paths:
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        src = raw.get("source", "")
        aftermarket = raw.get("brand_type") == "aftermarket"
        for it in raw.get("items") or []:
            name = _first(it, "name", "title")
            if not name or _MERCH.search(name):
                continue
            pn = _first(it, "part_number", "part", "pn", "partNumber", "part_num", "mpn").upper().replace(" ", "")
            sku = _first(it, "sku", "parent_sku")
            if pn and pn.replace("-", "") in core_pns:
                continue
            fits = _first(it, "fits", "fits_text", "fitment_text")
            if aftermarket:
                fit, why = "own", fits or "listed by the shop for this exact vehicle (2018 Stelvio base 2.0L)"
            elif _OTHER.search(name) and not re.search(r"\b2\.0", name):
                fit, why = "other-engine", "name points to another engine or model"
            elif _OURS.search(name):
                fit, why = "by-name", "name mentions Stelvio or 2.0; not confirmed by part number"
            else:
                fit, why = "unverified", "no fitment given; listed under the shop's Stelvio filter"
            key = (src, pn or sku or name)
            if key in seen:
                continue
            seen.add(key)
            price = _first(it, "price", "sale_price", "sale_cad")
            out.append({
                "source": src, "source_name": raw.get("source_name") or re.sub(r"^https?://(www\.)?", "", src).split("/")[0],
                "kind": "aftermarket" if aftermarket else "retailer",
                "brand": _first(it, "brand", "manufacturer"), "pn": pn, "sku": sku, "name": name,
                "notes": _first(it, "position", "notes"),
                "price": price, "currency": "CAD" if aftermarket else "",
                "msrp": _first(it, "msrp", "msrp_cad"), "url": _first(it, "url", "product_url"),
                "category": _first(it, "category_slug", "category"),
                "fitment": fit, "fitment_why": why,
            })
    return out


def build(export: Path, fetch_images: bool, rows_file: Path | None = None,
          supplements: list[Path] | None = None) -> Path:
    cfg = json.loads(GROUPS.read_text(encoding="utf-8"))
    raw = json.loads(export.read_text(encoding="utf-8"))
    if rows_file and rows_file.exists():
        print(f"diagram rows: {merge_diagram_rows(raw, rows_file)} added from {rows_file.name}")
    out_dir = state_dir() / "parts_catalog" / CATALOG_ID
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    def group_of(slug: str) -> tuple[str, str]:
        prefix = slug.split("--")[0]
        for ex in cfg["excluded"]:
            if prefix == ex["prefix"]:
                return "excluded", ex["reason"]
        for g in cfg["groups"]:
            if prefix in g["prefixes"]:
                return g["id"], ""
        return "other", ""

    def torque_for(slug: str) -> dict:
        svc, drv = [], []
        for t in cfg["torque"]:
            if any(m in slug for m in t["match"]):
                svc += [c for c in t.get("service", []) if c not in svc]
                drv += [c for c in t.get("drivetrain", []) if c not in drv]
        return {"service": svc, "drivetrain": drv}

    wanted: dict[str, str] = {}  # url -> local name
    sections, diagrams = [], {}
    for slug in raw.get("cats") or sorted(raw["pages"]):
        page = raw["pages"].get(slug)
        if not page:
            continue
        gid, reason = group_of(slug)
        thumbs = [_abs(u) for u in page.get("thumbs") or page.get("mains") or []]
        heads = page.get("heads") or []
        n = max(len(thumbs), len(heads), 1 + max([r.get("d", 0) for r in page.get("rows", [])] or [0]))
        ids = []
        for i in range(n):
            did = f"{slug}--{i + 1}"
            url = thumbs[i] if i < len(thumbs) else ""
            if url:
                wanted[url] = _img_name(url)
            parts = []
            for r in page.get("rows", []):
                if r.get("d", 0) != i:
                    continue
                info = r.get("info") or {}
                notes = info.get("Notes", "")
                photo = _abs(r.get("img") or "")
                photos = [] if (not photo or PLACEHOLDER.search(photo)) else [photo]
                for p in photos:
                    wanted[p] = _img_name(p)
                parts.append({
                    "ref": str(r.get("ref") or ""),
                    "pn": (r.get("pn") or "").strip().upper(),
                    "name": r.get("name") or "",
                    "description": info.get("Description", ""),
                    "notes": notes,
                    "info": {k: v for k, v in info.items() if k not in ("Notes", "Description")},
                    "fitment": _fitment(notes, cfg),
                    "url": (raw.get("source", "").split("/v-")[0] + r["href"]) if r.get("href") else "",
                    "photos": [{"file": wanted[p], "url": p} for p in photos],
                })
            diagrams[did] = {
                "id": did, "slug": slug, "index": i + 1, "group": gid,
                "section": _section_title(page),
                "title": _diagram_title(heads[i] if i < len(heads) else "", i),
                "image": {"file": wanted.get(url, ""), "url": url},
                "source_url": raw.get("source", "") + "/" + slug,
                "parts": parts,
            }
            ids.append(did)
        sections.append({"slug": slug, "title": _section_title(page), "group": gid,
                         "excluded_reason": reason, "diagrams": ids, "torque": torque_for(slug)})

    groups = [{"id": g["id"], "title": g["title"], "sections": [s["slug"] for s in sections if s["group"] == g["id"]]}
              for g in cfg["groups"]]
    groups.append({"id": "excluded", "title": "Not for this car (Quadrifoglio)",
                   "sections": [s["slug"] for s in sections if s["group"] == "excluded"]})

    if fetch_images:
        got = skipped = failed = 0
        for url, name in wanted.items():
            dest = img_dir / name
            if dest.exists() and dest.stat().st_size > 0:
                skipped += 1
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    dest.write_bytes(resp.read())
                got += 1
            except Exception as e:  # noqa: BLE001 -- one bad image never stops the build
                failed += 1
                print(f"image failed: {url} ({e})")
            time.sleep(0.4)
        print(f"images: {got} fetched, {skipped} already here, {failed} failed")

    for d in diagrams.values():  # only point at files that exist
        f = d["image"]["file"]
        if f and not (img_dir / f).exists():
            d["image"]["file"] = ""

    catalog = {
        "id": CATALOG_ID,
        "title": "2018 Alfa Romeo Stelvio 2.0L parts catalogue",
        "vehicle": "2018 Alfa Romeo Stelvio, 2.0L L4 turbo (280 hp), ZF 8HP50, Q4 AWD, North America",
        "source": raw.get("source", ""),
        "source_name": "Mopar Online Parts (dealer catalogue, read in the owner's browser)",
        "fetched_at": raw.get("fetched_at", ""),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "missing_sections": raw.get("errors", []),
        "groups": groups, "sections": sections, "diagrams": diagrams,
        "listings": load_listings(supplements or [], {p["pn"].replace("-", "") for d in diagrams.values() for p in d["parts"]}),
    }
    (out_dir / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    n_parts = sum(len(d["parts"]) for d in diagrams.values())
    n_pn = len({p["pn"] for d in diagrams.values() for p in d["parts"]})
    print(f"catalog: {len(sections)} sections, {len(diagrams)} diagrams, {n_parts} rows, {n_pn} part numbers -> {out_dir}")
    empty = [i for i, d in diagrams.items() if not d["parts"]]
    if catalog["listings"]:
        by = {}
        for x in catalog["listings"]:
            by[(x["source_name"], x["fitment"])] = by.get((x["source_name"], x["fitment"]), 0) + 1
        print("listings: " + "; ".join(f"{k[0]} {k[1]} {v}" for k, v in sorted(by.items())))
    print(f"diagrams with no parts: {len(empty)}" + (f" (first: {', '.join(empty[:5])})" if empty else ""))
    return out_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("export", nargs="?", default=str(DEFAULT_EXPORT))
    ap.add_argument("--rows", default=str(DEFAULT_ROWS))
    ap.add_argument("--supplement", action="append", help="another shop's saved list (repeatable)")
    ap.add_argument("--no-images", action="store_true")
    a = ap.parse_args()
    build(Path(a.export), not a.no_images, Path(a.rows),
          [Path(x) for x in a.supplement] if a.supplement else DEFAULT_SUPPLEMENTS)
