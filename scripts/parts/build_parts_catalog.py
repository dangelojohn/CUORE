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

Run:  .venv/Scripts/python.exe scripts/parts/build_parts_catalog.py [export.json] [--no-images]
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


def build(export: Path, fetch_images: bool) -> Path:
    cfg = json.loads(GROUPS.read_text(encoding="utf-8"))
    raw = json.loads(export.read_text(encoding="utf-8"))
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
    }
    (out_dir / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    n_parts = sum(len(d["parts"]) for d in diagrams.values())
    n_pn = len({p["pn"] for d in diagrams.values() for p in d["parts"]})
    print(f"catalog: {len(sections)} sections, {len(diagrams)} diagrams, {n_parts} rows, {n_pn} part numbers -> {out_dir}")
    return out_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("export", nargs="?", default=str(DEFAULT_EXPORT))
    ap.add_argument("--no-images", action="store_true")
    a = ap.parse_args()
    build(Path(a.export), not a.no_images)
