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
                "parts": dedupe_parts(dg.get("parts") or []),
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
        low = h.get("confidence_level") == "low"
        words = " -> ".join(a["label"].lower() for a in route) or "not shown"
        out.append({**h, "n": n, "route": route, "low": low, "route_words": words,
                    "summary": ("Area not resolved: the drawing and its title disagree. No route drawn." if low
                                else words + ("" if h["placement_basis"] == "drawn" else " (from the title)")),
                    "chip": ("unresolved" if low else "placed by drawing" if h["placement_basis"] == "drawn"
                             else "placed by title only"),
                    "diagrams": dias, "related": related, "has_related": any(related.values())})
    by_area = []
    for a in d.get("areas", []):
        hs = [h for h in out if any(r["id"] == a["id"] for r in h["route"]) and not h["low"]]
        if hs:
            by_area.append({"area": a, "harnesses": hs})
    by_item: list[dict[str, Any]] = []
    for kind in ("fuse_boxes", "sensors", "elements"):
        seen: dict[str, dict[str, Any]] = {}
        for h in out:
            for r in h["related"][kind]:
                seen.setdefault(r["id"], {**r, "kind": kind, "harnesses": []})["harnesses"].append(h)
        by_item += list(seen.values())
    return {"vin": vin, "source": d.get("source", ""), "caption": d.get("caption", ""),
            "elem_labels": labels["elements"],
            "areas": d.get("areas", []), "harnesses": out, "by_area": by_area, "by_item": by_item,
            "catalogue_ok": bool(cid and diagrams)}


def dedupe_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (callout, name, description); part numbers merged. ``side`` is "left" / "right" only when the
    catalogue's own name or description says so; otherwise "" (not stated)."""
    import re
    rows: dict[tuple, dict[str, Any]] = {}
    for p in parts:
        name, desc = (p.get("name") or "").strip(), (p.get("description") or "").strip()
        if desc.lower() == name.lower():
            desc = ""
        key = (p.get("ref"), name.lower(), desc.lower())
        r = rows.setdefault(key, {"ref": p.get("ref"), "name": name, "description": desc, "pns": []})
        pn = p.get("pn") or ""
        if pn and pn not in r["pns"]:
            r["pns"].append(pn)
    out = list(rows.values())
    for r in out:
        t = f'{r["name"]} {r["description"]}'.lower()
        left, right = bool(re.search(r"\bleft\b", t)), bool(re.search(r"\bright\b", t))
        r["side"] = "left" if left and not right else "right" if right and not left else ""
        r["pn"] = ", ".join(r["pns"])
    return out


# --- the directing call ------------------------------------------------------

import re as _re

# words in a symptom / code description that name a harness's own area. Matching is on the printed words only.
_WORDS = {
    "front-door-left": lambda t: bool(_re.search(r"\b(door|window)\b", t) and "front" in t
                                      and _re.search(r"\b(left|driver)\b", t) and "rear" not in t),
    "headlamp-to-dash": lambda t: bool(_re.search(r"head ?(lamp|light)", t)),
    "seat-left": lambda t: bool(_re.search(r"\bseat\b", t) and _re.search(r"\b(left|driver)\b", t)),
    "console": lambda t: "console" in t,
    "ac-module": lambda t: bool(_re.search(r"a/c|air.?condition|climate control|hvac", t)),
    "instrument-panel": lambda t: "instrument panel" in t,
}


def _short(text: str, n: int = 60) -> str:
    s = _re.split(r"[.;(\n]", text or "", 1)[0].strip()
    return (s[:n].rsplit(" ", 1)[0] if len(s) > n else s)


def direct(vin: str, harnesses: list[dict[str, Any]], items: list[dict[str, Any]],
           elem_labels: dict[str, str], symptoms: list[dict[str, Any]], codes: list[str], code_text: dict[str, str],
           path_for_code) -> dict[str, Any]:
    """Which harness, if any, the open job points to. Two sources only: (a) a harness's own linked fuse box /
    electrical element sits on CUORE's electrical path for an open code; (b) a symptom or code description names
    the harness's area in words. Returns ``call`` (text), ``hits`` ({harness id: [reasons]}), ``order`` (ids),
    ``connected`` (harnesses that link to anything), ``instead`` ({text, href} or None)."""
    hits: dict[str, list[str]] = {}
    paths: dict[str, list[dict[str, Any]]] = {}
    for c in codes:
        try:
            paths[c] = path_for_code(c).get("path") or []
        except Exception:  # noqa: BLE001
            paths[c] = []
    for c, path in paths.items():
        elems = {p["element"] for p in path}
        boxes: dict[str, list[str]] = {}
        for it in items:
            if it.get("box") and (it["id"] in elems or set(it.get("feeds_elements") or []) & elems):
                boxes.setdefault(it["box"], []).append(it.get("position") or it.get("label") or it["id"])
        for h in harnesses:
            for e in h["related"]["elements"]:
                if e["id"] in elems:
                    hits.setdefault(h["id"], []).append(f"{c}: the electrical path includes {e['label']}, which this harness lists")
            for b in h["related"]["fuse_boxes"]:
                if b["id"] in boxes:
                    hits.setdefault(h["id"], []).append(
                        f"{c}: the electrical path runs through {', '.join(sorted(set(boxes[b['id']])))} in the {b['label']}, "
                        "which this harness lists")
    texts = [(f'the symptom "{_short(s.get("text", ""))}"', (s.get("text") or "").lower()) for s in symptoms]
    texts += [(f'{c} "{code_text.get(c, "")}"', (code_text.get(c) or "").lower()) for c in codes]
    for h in harnesses:
        rule = _WORDS.get(h["id"])
        for label, t in texts:
            if rule and t and rule(t):
                hits.setdefault(h["id"], []).append(f"{label} names this area")
    for v in hits.values():
        v[:] = list(dict.fromkeys(v))
    order = [h["id"] for h in harnesses if h["id"] in hits]
    by_id = {h["id"]: h for h in harnesses}
    connected = [h for h in harnesses if h["has_related"]]
    what = [f"{h['title']}: " + ", ".join(r["label"] for k in ("fuse_boxes", "sensors", "elements") for r in h["related"][k])
            for h in connected]
    n = len(harnesses)
    stat = (f"{len(connected)} of the {n} harness diagrams link to anything CUORE knows"
            + (f" ({'; '.join(what)})" if what else "") + ".")
    if order:
        first = by_id[order[0]]
        call = (f"Look at harness {first['n']}, {first['title']}, first: {hits[order[0]][0]}."
                + (f" {len(order) - 1} more below." if len(order) > 1 else "")
                + (" Its area is unresolved, so this points to the drawing only." if first["low"] else ""))
    else:
        call = ("No open job points to a harness - harness maps are areas, not wiring paths."
                if (codes or symptoms) else
                "No open job, so nothing points to a harness - harness maps are areas, not wiring paths.")
    instead = None
    words = set(_re.findall(r"[a-z]{4,}", (symptoms[0].get("text") or "").lower())) if symptoms else set()
    pick = next((c for c in codes if paths.get(c)
                 and words & set(_re.findall(r"[a-z]{4,}", (code_text.get(c) or "").lower()))), None)
    pick = pick or next((c for c in codes if paths.get(c)), None)
    if pick:
        comp = next((p["element"] for p in paths[pick] if p.get("role") == "component"), paths[pick][0]["element"])
        instead = {"text": f"Instead, follow CUORE's electrical path for {pick} ({elem_labels.get(comp, comp)})",
                   "href": f"/v/{vin}/electrical#el-{comp}"}
    return {"call": call, "stat": stat, "hits": hits, "order": order, "connected": connected, "instead": instead,
            "checked": f"{len(codes)} open code{'s' if len(codes) != 1 else ''} and {len(symptoms)} open "
                       f"symptom{'s' if len(symptoms) != 1 else ''}"}


# --- top-view map ----------------------------------------------------------

LABEL_PX, LABEL_H, LABEL_GAP = 8.0, 22, 10   # approx. glyph width at 13 px, box height, min gap between boxes
MAP_W, MAP_H = 860, 400


def label_layout(areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Area label boxes. Labels for areas above the car (y < 230) and below it are each packed into rows so no two
    boxes in a row overlap (an overlapping label goes to the next row). Returns dicts with box ``x0 x1 y0 y1``,
    text anchor ``tx ty``, leader end ``ly``, ``side`` and ``row``."""
    out: list[dict[str, Any]] = []
    for side in ("top", "bottom"):
        group = sorted((a for a in areas if (a["y"] < 230) == (side == "top")), key=lambda a: a["x"])
        rows: list[list[dict[str, Any]]] = []
        for a in group:
            w = LABEL_PX * len(a["label"]) + 12
            x0 = max(2, min(a["x"] - w / 2, MAP_W - w - 2))
            box = {"id": a["id"], "label": a["label"], "x": a["x"], "y": a["y"], "side": side, "x0": x0, "x1": x0 + w}
            for ri, row in enumerate(rows):
                if all(box["x0"] >= o["x1"] + LABEL_GAP or box["x1"] <= o["x0"] - LABEL_GAP for o in row):
                    row.append(box)
                    box["row"] = ri
                    break
            else:
                rows.append([box])
                box["row"] = len(rows) - 1
            out.append(box)
    for b in out:
        if b["side"] == "top":
            b["y0"] = 4 - b["row"] * (LABEL_H + 4)
            b["ly"] = b["y0"] + LABEL_H
        else:
            b["y0"] = MAP_H - 22 + 4 + b["row"] * (LABEL_H + 4)
            b["ly"] = b["y0"]
        b["y1"] = b["y0"] + LABEL_H
        b["ty"] = b["y0"] + 16
        b["tx"] = (b["x0"] + b["x1"]) / 2
    return out


COLOURS = ("var(--fam-mil)", "var(--fam-evap)", "var(--fam-network)", "var(--fam-body)", "var(--fam-chassis)",
           "var(--fam-engine)", "var(--ok)", "var(--sev-chronic)", "var(--sev-cleared)")


def colour(n: int) -> str:
    return COLOURS[(n - 1) % len(COLOURS)]


def map_svg(harnesses: list[dict[str, Any]]) -> str:
    """Top view (nose left). One coloured route line + arrow + number disc per harness whose area is resolved;
    low-confidence harnesses are not drawn (they are listed). Area labels are packed so none overlap.
    Single-area harnesses get a short stub arrow: a marker, not a route."""
    from html import escape
    try:
        from ..web import sensor_profile_svg as psvg  # read-only reuse of the car art
        art = psvg._car_top_art()
    except Exception:  # noqa: BLE001 -- plain outline fallback
        art = ('<rect x="58" y="47" width="748" height="306" rx="60" fill="var(--surface)" '
               'stroke="var(--ink-2)" stroke-width="2.2"/>')
    drawn = [hn for hn in harnesses if not hn.get("low") and hn["route"]]
    used = {a["id"]: a for hn in drawn for a in hn["route"]}
    boxes = label_layout(list(used.values()))
    top = max([0] + [-b["y0"] for b in boxes if b["side"] == "top"])
    bot = max([0] + [b["y1"] - MAP_H for b in boxes if b["side"] == "bottom"])
    p = [f'<svg class="hn-map" xmlns="http://www.w3.org/2000/svg" viewBox="0 {-top - 4} {MAP_W} {MAP_H + top + bot + 8}" '
         f'width="100%" role="img" aria-label="Top view of the car with {len(drawn)} harness areas marked. '
         f'Areas, not wiring paths.">', art]
    for b in boxes:
        p.append(f'<line class="hn-lead" x1="{b["x"]}" y1="{b["y"]}" x2="{b["x"]}" y2="{b["ly"]}" '
                 f'stroke="var(--ink-3)" stroke-width="1" stroke-dasharray="2 4"/>'
                 f'<rect class="hn-lbox" data-area="{escape(b["id"])}" x="{b["x0"]:.0f}" y="{b["y0"]}" '
                 f'width="{b["x1"] - b["x0"]:.0f}" height="{LABEL_H}" rx="4" fill="var(--surface)" stroke="var(--rule)"/>'
                 f'<text class="hn-area" x="{b["tx"]:.0f}" y="{b["ty"]}" text-anchor="middle">{escape(b["label"])}</text>')
    for hn in drawn:
        c, n, pts = colour(hn["n"]), hn["n"], [(a["x"], a["y"]) for a in hn["route"]]
        off = ((n - 1) % 5 - 2) * 9      # spread overlapping lines vertically a little so each stays visible
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
                 f'<title>{n}. {escape(hn["title"])}: {escape(hn["route_words"])} (area, not an exact path)</title>'
                 f'<path d="{d}" fill="none" stroke="var(--surface)" stroke-width="9" stroke-linecap="round" '
                 f'stroke-linejoin="round"/>'
                 f'<path class="hn-line" d="{d}" fill="none" stroke="{c}" stroke-width="5" stroke-linecap="round" '
                 f'stroke-linejoin="round"{dash}/>'
                 f'<path class="hn-arrow" d="{head}" fill="{c}" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>'
                 f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="15" fill="var(--surface)" stroke="{c}" stroke-width="4"/>'
                 f'<text class="hn-num" x="{mx:.0f}" y="{my + 5:.0f}" text-anchor="middle">{n}</text>'
                 f'</a></g>')
    p.append("</svg>")
    return "".join(p)
