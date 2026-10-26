"""Wiring harness maps: the nine harness diagrams of the owner's Mopar parts
catalogue, placed by coarse area on a top view of the car.

The repo file ``cuore/data/harnesses_stelvio_2018.json`` holds only diagram
ids, titles and area/route descriptions. Part names, part numbers and images
are read from the catalogue in ProgramData at call time (the way
``fuse_health.catalogue_parts`` does) and are empty when it is not built.
Reading never contacts the car.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parents[1] / "data"
DATA_FILE = _DATA / "harnesses_stelvio_2018.json"


def _read(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def data() -> dict[str, Any]:
    return _read(DATA_FILE) or {"areas": [], "harnesses": []}


def _catalogue() -> tuple[str, dict[str, Any]]:
    try:
        from . import parts_catalog
        cid = parts_catalog.default_id() or ""
        return cid, (parts_catalog.load(cid) or {}).get("diagrams") or {}
    except Exception:  # noqa: BLE001 -- no catalogue: show the data file alone
        return "", {}


def _labels() -> dict[str, dict[str, str]]:
    fuses = {b["id"]: b.get("label", b["id"]) for b in _read(_DATA / "fuses_stelvio_2018.json").get("boxes", [])}
    sens = {s["id"]: s.get("label") or s["id"] for s in _read(_DATA / "sensors_stelvio_2018.json").get("sensors", [])}
    elems: dict[str, str] = {}
    try:
        from . import electrical_bridge
        elems = {e["id"]: e.get("label") or e["id"] for e in electrical_bridge.list_elements() if e.get("id")}
    except Exception:  # noqa: BLE001
        pass
    return {"fuse_boxes": fuses, "sensors": sens, "elements": elems}


def view(vin: str) -> dict[str, Any]:
    d = data()
    cid, diagrams = _catalogue()
    labels = _labels()
    areas = {a["id"]: a for a in d.get("areas", [])}
    out: list[dict[str, Any]] = []
    for n, h in enumerate(d.get("harnesses", []), 1):
        route = [areas[a] for a in h.get("areas", []) if a in areas]
        dias = []
        for did in h.get("diagram_ids", []):
            dg = diagrams.get(did) or {}
            img = (dg.get("image") or {}).get("file")
            dias.append({
                "id": did, "href": f"/catalog/d/{did}", "in_catalogue": bool(dg),
                "image": f"/catalog/img/{cid}/{img}" if img and cid else "",
                "parts": [{"ref": p.get("ref"), "name": p.get("name", ""), "description": p.get("description", ""),
                           "pn": p.get("pn", "")} for p in dg.get("parts") or []],
            })
        rel = h.get("related") or {}
        related = {
            "fuse_boxes": [{"id": i, "label": labels["fuse_boxes"][i], "href": f"/v/{vin}/fuses#fuse-box-{i}"}
                           for i in rel.get("fuse_boxes", []) if i in labels["fuse_boxes"]],
            "sensors": [{"id": i, "label": labels["sensors"][i], "href": f"/v/{vin}/sensors#sensor-{i}"}
                        for i in rel.get("sensors", []) if i in labels["sensors"]],
            "elements": [{"id": i, "label": labels["elements"][i], "href": f"/v/{vin}/electrical"}
                         for i in rel.get("elements", []) if i in labels["elements"]],
        }
        out.append({**h, "n": n, "route": route,
                    "route_words": " -> ".join(a["label"].lower() for a in route) or "not shown",
                    "diagrams": dias, "related": related, "has_related": any(related.values())})
    by_area = []
    for a in d.get("areas", []):
        hs = [h for h in out if any(r["id"] == a["id"] for r in h["route"])]
        if hs:
            by_area.append({"area": a, "harnesses": hs})
    by_item: list[dict[str, Any]] = []
    for kind in ("fuse_boxes", "sensors", "elements"):
        seen: dict[str, dict[str, Any]] = {}
        for h in out:
            for r in h["related"][kind]:
                seen.setdefault(r["id"], {**r, "kind": kind, "harnesses": []})["harnesses"].append(h)
        by_item += list(seen.values())
    placed = sum(1 for h in out if h["placement_basis"] == "drawn")
    call = (f"{len(out)} harness diagrams from the Mopar parts catalogue: {placed} placed by what the drawing shows, "
            f"{len(out) - placed} by title only. Pin-level wiring is not here.")
    return {"vin": vin, "source": d.get("source", ""), "caption": d.get("caption", ""), "call": call,
            "areas": d.get("areas", []), "harnesses": out, "by_area": by_area, "by_item": by_item,
            "catalogue_ok": bool(cid and diagrams)}


# --- top-view map ----------------------------------------------------------

COLOURS = ("var(--fam-mil)", "var(--fam-evap)", "var(--fam-network)", "var(--fam-body)", "var(--fam-chassis)",
           "var(--fam-engine)", "var(--ok)", "var(--sev-chronic)", "var(--sev-cleared)")


def colour(n: int) -> str:
    return COLOURS[(n - 1) % len(COLOURS)]


def map_svg(harnesses: list[dict[str, Any]]) -> str:
    """Top view (nose left), one coloured route line + arrow + number label per harness.

    Single-area harnesses get a short stub arrow pointing toward the rear; the
    stub is a marker, not a route."""
    from html import escape
    try:
        from ..web import sensor_profile_svg as psvg  # read-only reuse of the car art
        art, w, h = psvg._car_top_art(), psvg._TOP_W, psvg._TOP_H
    except Exception:  # noqa: BLE001 -- plain outline fallback
        w, h = 860, 400
        art = ('<rect x="58" y="47" width="748" height="306" rx="60" fill="var(--surface)" '
               'stroke="var(--ink-2)" stroke-width="1.8"/>')
    p = [f'<svg class="hn-map" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" '
         f'aria-label="Top view of the car with {len(harnesses)} harnesses placed by area">', art]
    used = {a["id"]: a for hn in harnesses for a in hn["route"]}
    for a in used.values():
        low = a["y"] >= 230
        p.append(f'<line class="hn-lead" x1="{a["x"]}" y1="{a["y"]}" x2="{a["x"]}" y2="{376 if low else 28}" '
                 f'stroke="var(--rule)" stroke-width="1" stroke-dasharray="2 4"/>'
                 f'<text class="hn-area" x="{a["x"]}" y="{392 if low else 20}" text-anchor="middle">{escape(a["label"])}</text>')
    for hn in harnesses:
        c, n, pts = colour(hn["n"]), hn["n"], [(a["x"], a["y"]) for a in hn["route"]]
        if not pts:
            continue
        # spread overlapping lines vertically a little so each stays visible
        off = ((n - 1) % 5 - 2) * 9
        pts = [(x, y + off) for x, y in pts]
        dash = ' stroke-dasharray="7 5"' if hn["placement_basis"] != "drawn" else ""
        if len(pts) == 1:
            x, y = pts[0]
            pts = [(x - 22, y), (x + 22, y)]
        d = "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in pts)
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        ln = max(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5, 1)
        ux, uy = (x1 - x0) / ln, (y1 - y0) / ln
        head = (f"M{x1:.0f},{y1:.0f} L{x1 - 12 * ux + 6 * uy:.0f},{y1 - 12 * uy - 6 * ux:.0f} "
                f"L{x1 - 12 * ux - 6 * uy:.0f},{y1 - 12 * uy + 6 * ux:.0f} Z")
        mx, my = pts[0]
        p.append(f'<g class="hn-route" data-harness="{escape(hn["id"])}"><a href="#harness-{escape(hn["id"])}">'
                 f'<title>{n}. {escape(hn["title"])}: {escape(hn["route_words"])}</title>'
                 f'<path class="hn-line" d="{d}" fill="none" stroke="{c}" stroke-width="5" stroke-linecap="round" '
                 f'stroke-linejoin="round"{dash}/>'
                 f'<path class="hn-arrow" d="{head}" fill="{c}" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>'
                 f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="11" fill="var(--surface)" stroke="{c}" stroke-width="3"/>'
                 f'<text class="hn-num" x="{mx:.0f}" y="{my + 4:.0f}" text-anchor="middle">{n}</text>'
                 f'</a></g>')
    p.append("</svg>")
    return "".join(p)
