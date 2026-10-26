"""Fuse page drawings (server-side SVG, no JS, CSS variables only).

* :func:`box_map` - the car picture with a Side / Top toggle (two radio inputs +
  CSS). ONE large marker per fuse BOX, labelled next to it, linking to the box
  section. Fuses never appear on the car. Reuses the car line art that the
  Sensors page draws (``sensor_profile_svg``), which is left unchanged.
* :func:`slot_svg` - a box outline with one slot per listed fuse/relay. TRUE slot
  positions are not sourced for any box, so slots go in position-number order
  unless a row carries explicit ``layout: {row, col}`` data.
"""
from __future__ import annotations

import re
from html import escape
from typing import Any, Optional

from . import sensor_profile_svg as _s

MARK = {"green": "✓", "orange": "!", "red": "✕", "grey": "?"}
AREA_BY_ID = {"engine_pdc": "engine", "interior_box": "interior", "rear_pdc": "rear", "luggage_box": "luggage"}
AREA_BY_ZONE = {"fuse_box_engine_bay": "engine", "fuse_box_interior": "interior", "fuse_box_rear": "rear"}
# area -> (x, y, label direction) on the side view (left side of the car shown); top view (y before side shift)
_SIDE = {"engine": (140, 192, "up"), "interior": (384, 222, "down"), "rear": (775, 215, "up"), "luggage": (690, 140, "up")}
_TOP = {"engine": (140, 200), "interior": (384, 200), "rear": (775, 200), "luggage": (690, 200)}
_SHIFT = 64
_HIT, _DOT = 30, 14
NOTE = "Slots shown in number order - real positions in the box are not sourced yet"
WORD = {"green": "OK", "orange": "Suspect", "red": "Blown"}
_LINE = 19   # line height of a marker label, in drawing units


_COLOURS = {"grey": "grey", "gray": "grey", "violet": "violet", "purple": "violet", "tan": "tan", "brown": "brown",
            "red": "red", "blue": "blue", "yellow": "yellow", "clear/white": "clear", "clear": "clear", "white": "clear",
            "green": "green", "blue-grey": "bluegrey", "orange": "orange", "black": "black"}


def colour_class(name: Any) -> str:
    """CSS class (``fz-*``) for a colour name; unknown names get ``fz-other`` (a neutral swatch)."""
    return "fz-" + _COLOURS.get(str(name or "").strip().lower(), "other") if name else "fz-none"


def area_of(b: dict[str, Any]) -> Optional[str]:
    return b.get("area") or AREA_BY_ID.get(b.get("id")) or AREA_BY_ZONE.get(b.get("zone"))


def _label_geom(b: dict[str, Any], x: float, y: float, d: str, view: str) -> tuple[list[tuple[str, str]], str, float, float]:
    """(lines, text-anchor, text x, first baseline y) of a box marker's label."""
    side = b.get("side")
    far = view == "side" and side == "right"
    tag = "R, far side" if far else ("R" if side == "right" else "L" if side == "left" else "")
    lines = [(b["short"], "fm-name")]
    if tag:
        lines.append((tag, "fm-sub"))
    n = len(lines)
    y0 = y - _DOT - 8 - (n - 1) * _LINE if d == "up" else y + _DOT + 18
    half = max(len(t) for t, _ in lines) * 5.2   # rough half-width of the widest line
    anchor, tx = "middle", x
    if x + half > 800:
        anchor, tx = "end", x + _DOT
    elif x - half < 24:
        anchor, tx = "start", x - _DOT
    return lines, anchor, tx, y0


def _text_rect(text: str, anchor: str, tx: float, y0: float, pad: float = 2.0) -> tuple[float, float, float, float]:
    """Bounding box (x0, y0, x1, y1) of one label line, in drawing units (about 9.5 units a character at 17 px bold)."""
    w = len(text) * 9.5
    x0 = tx - w / 2 if anchor == "middle" else tx - w if anchor == "end" else tx
    return (x0 - pad, y0 - 15 - pad, x0 + w + pad, y0 + 5 + pad)


def _marker(b: dict[str, Any], x: float, y: float, d: str, view: str) -> str:
    st = b["status"] if b["status"] in MARK else "grey"
    side = b.get("side")
    far = view == "side" and side == "right"
    lines, anchor, tx, y0 = _label_geom(b, x, y, d, view)
    txt = "".join(f'<text class="{c}" x="{tx:.0f}" y="{y0 + k * _LINE:.0f}" text-anchor="{anchor}">{escape(t)}</text>'
                  for k, (t, c) in enumerate(lines))
    tip = (f'{b["short"]} - {b["count"]} listed, {b["status_word"]}'
           + (" - on the car's right side, the far side in this view" if far else ""))
    cls = f'fm-box fuse-{st}' + (" fm-far" if far else "")
    return (f'<a class="{cls}" href="#fuse-box-{escape(b["id"], quote=True)}"><title>{escape(tip)}</title>'
            f'<circle class="fm-hit" cx="{x:.0f}" cy="{y:.0f}" r="{_HIT}"/>'
            f'<circle class="fm-dot" cx="{x:.0f}" cy="{y:.0f}" r="{_DOT}"/>'
            f'<text class="fm-mark" x="{x:.0f}" y="{y + 5:.0f}" text-anchor="middle">{MARK[st]}</text>{txt}</a>')


def _place(boxes: list[dict[str, Any]], view: str) -> list[tuple[dict[str, Any], float, float, str]]:
    used: dict[str, int] = {}
    out = []
    for b in boxes:
        a = area_of(b)
        if a not in _SIDE:
            continue
        k = used[a] = used.get(a, -1) + 1
        if view == "side":
            x, y, d = _SIDE[a]
            x += 80 * k
        else:
            x, y = _TOP[a]
            y += {"right": -_SHIFT, "left": _SHIFT}.get(b.get("side") or "", 0)
            x += 80 * k
            d = "down" if y <= 200 else "up"   # centre-line boxes label below, clear of right-side labels
        out.append((b, x, y, d))
    return out


def _ground_strip(grounds: list[dict[str, Any]], w: float, y: float) -> str:
    """Ground symbols in a labelled strip under the car: no ground point has a sourced position, so none is
    drawn on the body."""
    if not grounds:
        return ""
    n = len(grounds)
    p = [f'<text class="fm-sub" x="14" y="{y + 16:.0f}">Ground points (not placed on the car)</text>']
    for k, g in enumerate(grounds):
        x = w * (k + 1) / (n + 1)
        cy = y + 40
        tip = g["name"]
        p.append(f'<a class="fm-ground" href="#ground-{escape(g["id"], quote=True)}"><title>{escape(tip)}</title>'
                 f'<circle class="fm-hit" cx="{x:.0f}" cy="{cy:.0f}" r="24"/>'
                 f'<path class="fm-gsym" d="M{x:.0f} {cy - 14:.0f}v14M{x - 12:.0f} {cy:.0f}h24M{x - 8:.0f} {cy + 6:.0f}h16M{x - 4:.0f} {cy + 12:.0f}h8"/>'
                 f'<text class="fm-name" x="{x:.0f}" y="{cy + 30:.0f}" text-anchor="middle">{escape(g["short"])}</text></a>')
    return "".join(p)


# Component clusters sit at their OWN area's spot, using the car art's wheel / axle coordinates (front axle x=199, rear axle
# x=650; side view wheel centre y=269, top view left wheels y=329). area -> view -> (x, y, x offsets for 2nd, 3rd... marker)
_CPOS = {
    "engine": {"side": (235, 150, (0, 46, 92, 138)), "top": (235, 200, (0, 46, 92, 138))},
    # over the rear-left wheel arch: side = on the arch above the rear wheel; top = inside the left-rear dashed wheel box
    "rear": {"side": (650, 240, (0, -44, 44, -88)), "top": (650, 337, (0, -40, 40, -80))},
    # clear of the sill line and of the interior zone edge
    "underbody": {"side": (440, 314, (0, 46, 92, -46)), "top": (500, 200, (0, 46, 92, -46))},
}
_CLABEL = {"underbody": "Underbody"}
_NUDGE = [(0, 0), (0, -46), (0, 46), (46, 0), (-46, 0), (46, -46), (-46, -46), (46, 46), (-46, 46),
          (0, -92), (0, 92), (92, 0), (-92, 0)]   # fixed order: tried until the cluster is clear
_CR = 22   # cluster hit radius
_CLEAR = 8   # minimum gap, in drawing units, between a component marker and any box marker or box label


def _cluster_rect(x: float, y: float, label: str = "") -> tuple[float, float, float, float]:
    """Box around a cluster marker: hit circle, the count badge at its top right and, when set, the area label below."""
    return (x - _CR, y - _CR - 8, x + _CR + 10, y + _CR + (24 if label else 0))


def _hit(a: tuple[float, float, float, float], b: tuple[float, float, float, float], clear: float = 0.0) -> bool:
    """True when the boxes overlap or sit closer than ``clear`` units."""
    return a[0] - clear < b[2] and b[0] - clear < a[2] and a[1] - clear < b[3] and b[1] - clear < a[3]


def _box_rects(boxes: list[dict[str, Any]], view: str) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Every box marker (hit circle) and every label line of the box markers, as named boxes."""
    out = []
    for b, x, y, d in _place(boxes, view):
        out.append((f'marker:{b["id"]}', (x - _HIT, y - _HIT, x + _HIT, y + _HIT)))
        _, anchor, tx, y0 = _label_geom(b, x, y, d, view)
        for k, (t, _c) in enumerate(_label_geom(b, x, y, d, view)[0]):
            out.append((f'label:{b["id"]}:{k}', _text_rect(t, anchor, tx, y0 + k * _LINE)))
    return out


def comp_positions(clusters: list[dict[str, Any]], boxes: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    """Where each component cluster is drawn: [{cluster, x, y, label, rect}]. Starts at the area's own anchor, then is nudged in
    a fixed order until its box overlaps no box marker, no box label and no earlier cluster."""
    fixed = [r for _, r in _box_rects(boxes, view)]
    w, h = (_s._VB_W, _s._VB_H) if view == "side" else (_s._TOP_W, _s._TOP_H)
    used: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for c in clusters:
        a = c["view_area"]
        if a not in _CPOS:
            continue
        k = used[a] = used.get(a, -1) + 1
        x0, y0, offs = _CPOS[a][view]
        x0 += offs[k % len(offs)]
        if a == "rear" and view == "top":
            y0 = 63 if c.get("side") == "right" else 337
        elif a != "rear" and view == "top":
            y0 = 200 + {"left": _SHIFT, "right": -_SHIFT}.get(c.get("side") or "", 0)
        label = _CLABEL.get(a, "") if k == 0 else ""
        placed = (x0, y0, _cluster_rect(x0, y0, label))
        for dx, dy in _NUDGE:
            x, y = x0 + dx, y0 + dy
            r = _cluster_rect(x, y, label)
            if r[0] < 4 or r[2] > w - 4 or r[1] < 4 or r[3] > h:
                continue
            if any(_hit(r, f, _CLEAR) for f in fixed) or any(_hit(r, o["rect"]) for o in out):
                continue
            placed = (x, y, r)
            break
        out.append({"cluster": c, "x": placed[0], "y": placed[1], "label": label, "rect": placed[2]})
    return out


def _comp_marks(clusters: list[dict[str, Any]], view: str, boxes: Optional[list[dict[str, Any]]] = None) -> str:
    """One icon per (area, category) cluster with a count; tap -> the Components section filtered to that area."""
    out = []
    for p in comp_positions(clusters, boxes or [], view):
        c, x, y = p["cluster"], p["x"], p["y"]
        tip = f'{c["label"]}: {c["count"]} in {c["area_text"]} - show the list'
        lab = (f'<text class="fm-sub fm-clabel" x="{x}" y="{y + _CR + 16}" text-anchor="middle">{escape(p["label"])}</text>'
               if p["label"] else "")
        out.append(f'<a class="fm-comp" href="{escape(c["href"], quote=True)}"><title>{escape(tip)}</title>'
                   f'<circle class="fm-hit" cx="{x}" cy="{y}" r="{_CR}"/>'
                   f'<circle class="fm-cdot" cx="{x}" cy="{y}" r="17"/>'
                   f'<use href="#ci-{escape(c["cat"])}" x="{x - 11}" y="{y - 11}" width="22" height="22" class="fm-cicon"/>'
                   f'<text class="fm-cnum" x="{x + 17}" y="{y - 12}" text-anchor="middle">{c["count"]}</text>{lab}</a>')
    return "".join(out)


def _view_svg(boxes: list[dict[str, Any]], view: str, aria: str, grounds: Optional[list[dict[str, Any]]] = None,
              comps: Optional[list[dict[str, Any]]] = None) -> str:
    w, h = (_s._VB_W, _s._VB_H) if view == "side" else (_s._TOP_W, _s._TOP_H)
    art = _s._car_line_art() if view == "side" else _s._car_top_art()
    cls = "sens-profile fm-svg" + ("" if view == "side" else " sens-top")
    marks = "".join(_marker(b, x, y, d, view) for b, x, y, d in _place(boxes, view))
    marks += _comp_marks(comps or [], view, boxes)
    marks += _ground_strip(grounds or [], w, h)
    h += 100 if grounds else 0
    return (f'<svg class="{cls}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" '
            f'role="img" aria-label="{escape(aria, quote=True)}">{art}{marks}</svg>')


def box_map(boxes: list[dict[str, Any]], grounds: Optional[list[dict[str, Any]]] = None,
            default_view: str = "side", comps: Optional[list[dict[str, Any]]] = None) -> str:
    """Side/Top toggle + one marker per box. ``boxes``: id, short, side, zone/area, status, status_word,
    count, location_confidence. ``default_view`` ("side" / "top") is which radio is checked, set server-side."""
    top_on = default_view == "top"
    side = _view_svg(boxes, "side", "Side view of the car (left side shown) with one marker per fuse box", grounds, comps)
    top = _view_svg(boxes, "top", "Top view of the car with one marker per fuse box", grounds, comps)
    return ('<div class="fm-wrap">'
            f'<input class="fm-radio" type="radio" name="fm-view" id="fm-v-side"{"" if top_on else " checked"}>'
            f'<input class="fm-radio" type="radio" name="fm-view" id="fm-v-top"{" checked" if top_on else ""}>'
            '<div class="fm-tabs" role="group" aria-label="Car view">'
            '<label for="fm-v-side">Side</label><label for="fm-v-top">Top</label></div>'
            "<figure class=\"fm-fig fm-side\"><figcaption>Side view: the car's left (driver's) side. "
            f'Boxes on the right side are drawn hollow, on the far side.</figcaption><div class="fm-scroll">{side}</div></figure>'
            '<figure class="fm-fig fm-topv"><figcaption>Top view: looking down, front to the left; right side at the top.'
            f'</figcaption><div class="fm-scroll">{top}</div></figure></div>')


def _pos_key(r: dict[str, Any]) -> tuple[int, int, str]:
    m = re.search(r"\d+", str(r.get("position") or ""))
    return (0, int(m.group()), str(r.get("position") or "")) if m else (1, 0, str(r.get("label") or ""))


def slot_svg(rows: list[dict[str, Any]], title: str, cols: int = 4, job_ids: Optional[set] = None) -> tuple[str, bool]:
    """(svg, every slot placed from layout data). ('', False) for no rows. Slots are large (about 180 x 112 on screen)
    so a gloved thumb can hit them; ``job_ids`` are the rows for this job and are drawn filled with a heavy outline."""
    if not rows:
        return "", False
    job_ids = job_ids or set()
    cells: dict[tuple[int, int], dict[str, Any]] = {}
    rest = []
    for r in sorted(rows, key=_pos_key):
        lay = r.get("layout") or {}
        try:
            rc = (int(lay["row"]), int(lay["col"]))
        except (KeyError, TypeError, ValueError):
            rc = None
        if rc and rc[0] >= 0 and 0 <= rc[1] < 24 and rc not in cells:
            cells[rc] = r
        else:
            rest.append(r)
    explicit = bool(cells)
    if explicit:
        cols = max(cols, max(c for _, c in cells) + 1)
    k = 0
    for r in rest:
        while (k // cols, k % cols) in cells:
            k += 1
        cells[(k // cols, k % cols)] = r
        k += 1
    nrows = max(rc[0] for rc in cells) + 1
    cw, ch, gap, pad, top = 180, 112, 10, 14, 44
    W, H = cols * (cw + gap) - gap + 2 * pad, nrows * (ch + gap) - gap + top + pad
    p = [f'<svg class="fm-slots" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="{escape("Slot layout of " + title + ": " + str(len(rows)) + " listed, in number order", quote=True)}">',
         f'<rect class="fm-outline" x="2" y="2" width="{W - 4}" height="{H - 4}" rx="10"/>',
         f'<text class="fm-slot-title" x="{pad}" y="30">{escape(title)}</text>']
    for (r_, c_), it in sorted(cells.items()):
        x, y = pad + c_ * (cw + gap), top + r_ * (ch + gap)
        st = it.get("status") if it.get("status") in MARK else "grey"
        rating = f'{it["rating_a"]:g} A' if it.get("rating_a") else ""
        pos = it.get("position") or "-"
        rx = 36 if it.get("kind") == "relay" else 8
        sp = it.get("spec") or {}
        typ = str(sp.get("type") or ("relay" if it.get("kind") == "relay" else ""))[:12]
        col = sp.get("colour") or ""
        known = [str(v) for v in (rating, typ, col) if v]
        tip = f'{pos} {it.get("label", "")}' + (" - " + " - ".join(known) if known else "") + f' - {it.get("status_word", "")}'
        job = it["id"] in job_ids
        p.append(f'<a class="fm-slot fuse-{st}{" fm-job" if job else ""}" href="#fuse-{escape(str(it["anchor"]), quote=True)}">'
                 f'<title>{escape(tip)}</title>'
                 f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="{rx}"/>'
                 f'<text class="fm-pos" x="{x + cw / 2}" y="{y + 40}" text-anchor="middle">{escape(str(pos))}</text>'
                 + (f'<text class="fm-amp" x="{x + cw / 2}" y="{y + 68}" text-anchor="middle">{escape(rating)}</text>' if rating else "")
                 + (f'<text class="fm-kind" x="{x + cw / 2}" y="{y + 94}" text-anchor="middle">{escape(typ)}</text>' if typ else "")
                 + (f'<rect class="fm-sw {colour_class(col)}" x="{x + 12}" y="{y + 12}" width="26" height="16" rx="3"/>' if col else "")
                 + (f'<text class="fm-smark" x="{x + cw - 10}" y="{y + 26}" text-anchor="end">{MARK[st]} {WORD[st]}</text>'
                    if st in WORD else "")
                 + ("</a>"))
    p.append("</svg>")
    return "".join(p), explicit and not rest
