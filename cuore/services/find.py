"""Site-wide search for /find. Pure: no network, no adapter, no writes.

``search(q, vin)`` returns the BEST match (a page, code, bulletin, part...) plus grouped results.
Rank: exact page/word match > code > bulletin number > part number > words in titles.
Sources: nav_items (labels, words, answers), DTC pattern, tsb_catalogue.json, the parts catalogue,
the library index and docs/handbook/*.md headings.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..web import nav_items

_DTC = re.compile(r"^[pbcu][0-9a-f]{4}(-[0-9a-f]{2})?$", re.I)
_DATA = Path(__file__).resolve().parent.parent / "data"
START_KEYS = ("bench", "job", "codes", "adjustments", "catalog", "library")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _stem(w: str) -> str:
    for suf in ("ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def _words(s: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", norm(s))]


def _phrases(csv: str) -> list[str]:
    return [norm(p) for p in (csv or "").split(",") if p.strip()]


def _res(kind: str, title: str, href: str, says: str, score: int) -> dict[str, Any]:
    return {"kind": kind, "title": title, "href": href, "says": says, "score": score}


def _pages(q: str, vin: str, role: str | None) -> list[dict[str, Any]]:
    nq, qw = norm(q), _words(q)
    menu = nav_items.nav_menu(vin or None, "", role, "")
    out = []
    for g in menu["groups"]:
        for it in g["items"]:
            label = norm(it["label"])
            lw = _words(it["label"])
            phrases = _phrases(it.get("words", ""))
            pw = {w for p in phrases for w in _words(p)}
            score = 0
            if nq == label:
                score = 100
            elif nq in phrases:
                score = 95
            elif nq and any(nq in p or (len(p) > 3 and p in nq) for p in phrases):
                score = 85
            elif nq and nq in label:
                score = 80
            elif qw and all(w in lw or w in pw for w in qw):
                score = 70
            elif qw and any(w in lw for w in qw):
                score = 40
            elif qw and any(w in pw for w in qw if len(w) > 3):
                score = 35
            if score:
                out.append(_res("Pages", it["label"], it["href"], it.get("answers") or g["title"], score))
    return out


def _value_groups(q: str, vin: str) -> list[dict[str, Any]]:
    """"battery" -> the Battery and charging group on the Live board (needs a car, so no VIN = no result)."""
    if not vin:
        return []
    from . import value_groups
    return [_res("Value groups", m["group"]["label"], value_groups.href(vin, m["group"]["id"]),
                 "Every related reading together: " + m["group"].get("blurb", ""), m["score"])
            for m in value_groups.match(q)]


def _codes(q: str, vin: str) -> list[dict[str, Any]]:
    out = []
    for tok in re.split(r"[\s,;]+", q.strip()):
        if not _DTC.match(tok):
            continue
        code = tok.upper()
        base = code.split("-")[0]
        says = "Fault code"
        try:
            from . import mes_bridge
            d = mes_bridge.describe_dtc(code)
            says = str(d.get("description") or d.get("text") or says)
            if d.get("source_tag") and says != "Fault code":
                says += f" (source: {d['source_tag']})"
        except Exception:  # noqa: BLE001 - description is a bonus, never required
            pass
        href = (f"/v/{vin}/codes?q={base}#row-{base}" if vin else f"/library?q={base}")
        title = f"Code {code}" + ("" if vin else " (no car picked: shown in the library)")
        out.append(_res("Fault codes", title, href, says, 90))
    return out


def _tsb_items() -> list[dict[str, Any]]:
    try:
        return json.loads((_DATA / "tsb_catalogue.json").read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return []


def _bulletins(q: str, vin: str) -> list[dict[str, Any]]:
    nq, qw = norm(q), [w for w in _words(q) if len(w) > 2]
    qn = re.sub(r"[^a-z0-9]", "", nq)
    out = []
    base = f"/tsb?vin={vin}" if vin else "/tsb"
    for it in _tsb_items():
        num = norm(it.get("number", ""))
        numn = re.sub(r"[^a-z0-9]", "", num)
        title = it.get("title", "")
        score = 0
        if qn and len(qn) >= 4 and qn[:1].isdigit() and (qn == numn or qn in numn):
            score = 80
        elif qw:
            hay = norm(" ".join([title, it.get("summary", ""), " ".join(it.get("symptoms", []) or []),
                                 " ".join(it.get("dtcs", []) or [])]))
            hw = set(_words(hay))
            if all(w in hw for w in qw):
                score = 30 + (10 if all(w in _words(title) for w in qw) else 0)
        if score:
            out.append(_res("Bulletins", f"{it.get('number', '')}: {title}"[:140], base + "#tsb-row-" + _slug(it["id"]),
                            (it.get("condition") or it.get("summary") or "")[:160], score))
    return sorted(out, key=lambda r: -r["score"])[:8]


def _slug(text: str) -> str:
    try:
        from . import tsb_bridge
        return tsb_bridge.row_anchor(text).removeprefix("tsb-row-")
    except Exception:  # noqa: BLE001
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _parts(q: str) -> list[dict[str, Any]]:
    if len(q.strip()) < 2:
        return []
    try:
        from . import parts_catalog as pc
        cat = pc.load()
        if not cat:
            return []
        t = pc.typeahead(cat, q, n=8)
    except Exception:  # noqa: BLE001
        return []
    pn_like = bool(re.search(r"\d", q)) and " " not in q.strip()
    out = []
    for p in t.get("parts", []):
        out.append(_res("Parts", f"{p['name']} ({p['pn']})", f"/catalog/p/{quote(p['pn'])}",
                        f"On diagram: {p['diagram_title']}", 60 if pn_like else 25))
    return out


def _library(q: str) -> list[dict[str, Any]]:
    if len(q.strip()) < 2:
        return []
    try:
        from . import library
        docs = library.search(q.strip())
    except Exception:  # noqa: BLE001
        return []
    out = []
    for d in docs[:6]:
        t = d.get("title") or d.get("file") or "Document"
        out.append(_res("Library", t[:140], "/library?q=" + quote(t[:80]),
                        " ".join(x for x in (d.get("doc_no"), d.get("source")) if x) or "Manufacturer document", 20))
    return out


def _handbook(q: str) -> list[dict[str, Any]]:
    qw = [w for w in _words(q) if len(w) > 2]
    if not qw:
        return []
    from . import handbook
    out = []
    for slug, f in handbook.slugs().items():
        try:
            hs = handbook.headings(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for h in hs:
            if all(w in _words(h["text"]) for w in qw):
                out.append(_res("How-to", h["text"][:140], f"/handbook/{slug}#{h['id']}", f"Handbook: {f.name}", 22))
    return out[:6]


ORDER = ["Value groups", "Pages", "Fault codes", "Bulletins", "Parts", "How-to", "Library"]


def start_pages(vin: str, role: str | None = None) -> list[dict[str, Any]]:
    menu = nav_items.nav_menu(vin or None, "", role, "")
    by = {it["key"]: it for g in menu["groups"] for it in g["items"]}
    return [_res("Pages", by[k]["label"], by[k]["href"], by[k].get("answers", ""), 0) for k in START_KEYS if k in by]


def search(q: str, vin: str = "", role: str | None = None) -> dict[str, Any]:
    q = (q or "").strip()[:200]
    vin = (vin or "").strip().upper()
    if not q:
        return {"q": q, "best": None, "groups": [], "start": start_pages(vin, role)}
    allr = _pages(q, vin, role) + _value_groups(q, vin) + _codes(q, vin) + _bulletins(q, vin) + _parts(q) + _handbook(q) + _library(q)
    allr.sort(key=lambda r: -r["score"])
    best = next((r for r in allr if r["href"]), None)
    groups = []
    for k in ORDER:
        rows = [r for r in allr if r["kind"] == k and r is not best]
        if rows:
            groups.append({"title": k, "rows": rows[:8]})
    return {"q": q, "best": best, "groups": groups,
            "start": [] if allr else start_pages(vin, role)}
