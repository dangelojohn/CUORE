"""Knowledge library: manufacturer documents (layer 1) and the facts extracted from them (layer 2).

Pure and offline.  Nothing here touches the network, git or any folder outside
``state_dir()``.  Folders are created only by :func:`register`.  An absent or
empty library is an empty index, never an error.

Layout (see docs/design/KNOWLEDGE_LIBRARY.md)
    <state>/library/<source>/<YYYY-MM-DD>/<file>  + <file>.source.json   originals + SOURCES record
    <state>/knowledge/<platform>/<kind>.json                              extracted facts (list)
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

from ..live.config import state_dir

SIDECAR = ".source.json"

#: fact kind -> CUORE pages that show it (label, path pattern; {vin} = per-vehicle page)
KIND_PAGES: dict[str, list[tuple[str, str]]] = {
    "procedures": [("Adjustments", "/v/{vin}/adjustments")],
    "test_steps": [("Codes", "/v/{vin}/codes")],
    "specs": [("Facts", "/facts")],
    "pinouts": [("Electrical", "/v/{vin}/electrical"), ("Harnesses", "/v/{vin}/harnesses")],
    "fuse_maps": [("Fuses", "/v/{vin}/fuses")],
    "locations": [("Sensors", "/v/{vin}/sensors"), ("Systems", "/v/{vin}/systems")],
    "part_fitment": [("Parts", "/catalog")],
    "torque": [("Parts", "/catalog")],
    "fluids": [("Parts", "/catalog")],
    "proxi_map": [("Configuration", "/v/{vin}/configuration")],
    "bulletins": [("TSB", "/tsb"), ("Job", "/v/{vin}/job"), ("Arrive-ready", "/v/{vin}/arrive-ready"),
                  ("Warranty pack", "/v/{vin}/warranty")],
    # corporate data (UDS specs, ODX/CDD, DBC)
    "module_dids": [("Modules", "/modules")],
    "routines": [("Tests", "/v/{vin}/tests")],
    "dtc_defs": [("Codes", "/v/{vin}/codes")],
    "dbc": [("Live", "/v/{vin}/liveboard")],
}
KINDS = tuple(KIND_PAGES)


def library_root() -> Path:
    return state_dir() / "library"


def knowledge_root() -> Path:
    return state_dir() / "knowledge"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", s.strip().lower()).strip("-") or "unknown"


def register(path: str | Path, source: str, title: str, doc_no: str = "", url: str = "",
             licence: str = "", retrieved: Optional[str] = None) -> dict[str, Any]:
    """Write/update the SOURCES record next to *path*.  Copies nothing.

    *path* must already sit in ``<state>/library/<source>/<date>/``; a file elsewhere
    is refused so no record is ever written outside the library.
    """
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    root = library_root().resolve()
    try:
        rel = p.relative_to(root)
    except ValueError:
        raise ValueError(f"{p} is not inside {root}; place the download there first") from None
    sha = _sha256(p)
    side = p.with_name(p.name + SIDECAR)
    old: dict[str, Any] = {}
    if side.is_file():
        try:
            old = json.loads(side.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
    rec = {
        "doc_id": sha[:12],
        "file": p.name,
        "title": title or old.get("title", p.name),
        "doc_no": doc_no or old.get("doc_no", ""),
        "source": _slug(source),
        "url": url or old.get("url", ""),
        "licence": licence or old.get("licence", ""),
        "retrieved": retrieved or old.get("retrieved")
        or (rel.parts[1] if len(rel.parts) > 2 else date.today().isoformat()),
        "sha256": sha,
        "bytes": p.stat().st_size,
    }
    side.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return rec


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _all_facts() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    kr = knowledge_root()
    if not kr.is_dir():
        return out
    for pdir in sorted(d for d in kr.iterdir() if d.is_dir()):
        for f in sorted(pdir.glob("*.json")):
            data = _load_json(f)
            items = data.get("facts") if isinstance(data, dict) else data
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, dict):
                    out.append({**it, "_platform": pdir.name, "_kind": f.stem})
    return out


def facts(platform: str, kind: str) -> list[dict[str, Any]]:
    """Layer-2 facts for one platform and kind (empty if none)."""
    return [{k: v for k, v in f.items() if not k.startswith("_")}
            for f in _all_facts() if f["_platform"] == platform and f["_kind"] == kind]


def _cites(fact: dict[str, Any], doc: dict[str, Any]) -> bool:
    ref = str(fact.get("source_doc_id", "")).strip().lower()
    return bool(ref) and ref in {str(doc.get("doc_id", "")).lower(), str(doc.get("doc_no", "")).lower()}


def _docs() -> list[dict[str, Any]]:
    root = library_root()
    docs: list[dict[str, Any]] = []
    if not root.is_dir():
        return docs
    for side in sorted(root.glob("*/*/*" + SIDECAR)):
        rec = _load_json(side)
        if isinstance(rec, dict):
            rec["path"] = str(side.with_name(side.name[: -len(SIDECAR)]))
            docs.append(rec)
    return docs


def cited_on(doc_id: str, *, _doc_list: Optional[list] = None,
             _fact_list: Optional[list] = None) -> list[tuple[str, str]]:
    """CUORE pages (label, path pattern) that show facts from this document (id or doc number)."""
    docs = _doc_list if _doc_list is not None else _docs()
    allf = _fact_list if _fact_list is not None else _all_facts()
    doc = next((d for d in docs if str(doc_id).lower() in
                (str(d.get("doc_id", "")).lower(), str(d.get("doc_no", "")).lower())), None)
    if doc is None:
        return []
    seen: dict[str, tuple[str, str]] = {}
    for f in allf:
        if _cites(f, doc):
            for pg in KIND_PAGES.get(f["_kind"], []):
                seen.setdefault(pg[1], pg)
    return list(seen.values())


def index() -> list[dict[str, Any]]:
    """Every document with metadata, ``n_facts``, ``kinds`` and ``pages`` (label, pattern)."""
    allf = _all_facts()
    docs = _docs()
    for d in docs:
        mine = [f for f in allf if _cites(f, d)]
        d["n_facts"] = len(mine)
        d["kinds"] = sorted({f["_kind"] for f in mine})
        d["pages"] = cited_on(d.get("doc_id", ""), _doc_list=docs, _fact_list=allf)
    docs.sort(key=lambda d: (d.get("retrieved", ""), d.get("title", "")), reverse=True)
    return docs


def _haystack(d: dict[str, Any], mine: list[dict[str, Any]]) -> str:
    parts = [d.get("title", ""), d.get("doc_no", ""), d.get("source", ""), d.get("file", "")]
    for f in mine:
        for k, v in f.items():
            if k.startswith("_") or k in ("confidence", "extracted_by"):
                continue
            parts.append(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return " ".join(str(p) for p in parts).lower()


def search(q: str) -> list[dict[str, Any]]:
    """Documents whose title, doc number, or cited facts (DTCs, parts...) contain every word of *q*."""
    words = [w for w in (q or "").lower().split() if w]
    docs = index()
    if not words:
        return docs
    allf = _all_facts()
    out = []
    for d in docs:
        hay = _haystack(d, [f for f in allf if _cites(f, d)])
        if all(w in hay for w in words):
            out.append(d)
    return out


def summary() -> dict[str, Any]:
    docs = index()
    return {
        "documents": len(docs),
        "sources": len({d.get("source") for d in docs}),
        "facts_in_use": sum(d["n_facts"] for d in docs if d["pages"]),
        "last_added": max((d.get("retrieved", "") for d in docs), default=""),
    }


def source_line(fact: dict[str, Any], doc: Optional[dict[str, Any]] = None) -> str:
    """'Source: <site>, <title> <doc no> §<section>, retrieved <date>' for templates.

    *doc* (an index entry) supplies site/title/doc number when the fact only carries ids.
    """
    doc = doc or {}
    if not doc and fact.get("source_doc_id"):
        doc = next((d for d in _docs() if _cites(fact, d)), {})
    site = doc.get("source") or fact.get("source") or "unknown source"
    title = doc.get("title") or fact.get("title") or ""
    no = doc.get("doc_no") or fact.get("doc_no") or fact.get("source_doc_id") or ""
    sec = fact.get("section") or fact.get("page") or ""
    head = " ".join(x for x in (title, no) if x)
    s = f"Source: {site}, {head}".rstrip(", ")
    if sec != "":
        s += f" §{sec}"
    s += f", retrieved {fact.get('retrieved') or doc.get('retrieved') or 'date unknown'}"
    return s
