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
_SIDE = {"engine": (140, 192, "up"), "interior": (384, 222, "down"), "rear": (775, 238, "down"), "luggage": (690, 140, "up")}
_TOP = {"engine": (140, 200), "interior": (384, 200), "rear": (775, 200), "luggage": (690, 200)}
_SHIFT = 64
_HIT, _DOT = 30, 14
NOTE = "Slots shown in number order - real positions in the box are not sourced yet; add a box-cover photo"


_COLOURS = {"grey": "grey", "gray": "grey", "violet": "violet", "purple": "violet", "tan": "tan", "brown": "brown",
            "red": "red", "blue": "blue", "yellow": "yellow", "clear/white": "clear", "clear": "clear", "white": "clear",
            "green": "green", "blue-grey": "bluegrey", "orange": "orange", "black": "black"}


def colour_class(name: Any) -> str:
    """CSS class (``fz-*``) for a colour name; unknown names get ``fz-other`` (a neutral swatch)."""
    return "fz-" + _COLOURS.get(str(name or "").strip().lower(), "other") if name else "fz-none"


def area_of(b: dict[str, Any]) -> Optional[str]:
    return b.get("area") or AREA_BY_ID.get(b.get("id")) or AREA_BY_ZONE.get(b.get("zone"))


def _marker(b: dict[str, Any], x: float, y: float, d: str, view: str) -> str:
    st = b["status"] if b["status"] in MARK else "grey"
    side = b.get("side")
    far = view == "side" and side == "right"
    tag = "R, far side" if far else ("R" if side == "right" else "L" if side == "left" else "")
    lines = [(b["short"], "fm-name")]
    if tag:
        lines.append((tag, "fm-sub"))
    if b.get("location_confidence") != "SOURCED":
        lines.append(("position not sourced", "fm-sub"))
    n = len(lines)
    y0 = y - _DOT - 8 - (n - 1) * 13 if d == "up" else y + _DOT + 14
    txt = "".join(f'<text class="{c}" x="{x:.0f}" y="{y0 + k * 13:.0f}" text-anchor="middle">{escape(t)}</text>'
                  for k, (t, c) in enumerate(lines))
    tip = (f'{b["short"]} - {b["count"]} listed, {b["status_word"]}'
           + (" - on the car's right side, the far side in this view" if far else "")
           + ("" if b.get("location_confidence") == "SOURCED" else " - position not sourced (worked out, not checked)"))
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
            d = "up" if y < 200 else "down"
        out.append((b, x, y, d))
    return out


def _ground_strip(grounds: list[dict[str, Any]], w: float, y: float) -> str:
    """Ground symbols in a labelled strip under the car: no ground point has a sourced position, so none is
    drawn on the body."""
    if not grounds:
        return ""
    n = len(grounds)
    p = [f'<text class="fm-sub" x="14" y="{y + 12:.0f}">Ground points (position not sourced, so not placed on the car)</text>']
    for k, g in enumerate(grounds):
        x = w * (k + 1) / (n + 1)
        cy = y + 40
        tip = f'{g["name"]} - position not sourced'
        p.append(f'<a class="fm-ground" href="#ground-{escape(g["id"], quote=True)}"><title>{escape(tip)}</title>'
                 f'<circle class="fm-hit" cx="{x:.0f}" cy="{cy:.0f}" r="24"/>'
                 f'<path class="fm-gsym" d="M{x:.0f} {cy - 14:.0f}v14M{x - 12:.0f} {cy:.0f}h24M{x - 8:.0f} {cy + 6:.0f}h16M{x - 4:.0f} {cy + 12:.0f}h8"/>'
                 f'<text class="fm-name" x="{x:.0f}" y="{cy + 30:.0f}" text-anchor="middle">{escape(g["short"])}</text></a>')
    return "".join(p)


def _view_svg(boxes: list[dict[str, Any]], view: str, aria: str, grounds: Optional[list[dict[str, Any]]] = None) -> str:
    w, h = (_s._VB_W, _s._VB_H) if view == "side" else (_s._TOP_W, _s._TOP_H)
    art = _s._car_line_art() if view == "side" else _s._car_top_art()
    cls = "sens-profile fm-svg" + ("" if view == "side" else " sens-top")
    marks = "".join(_marker(b, x, y, d, view) for b, x, y, d in _place(boxes, view))
    marks += _ground_strip(grounds or [], w, h)
    h += 100 if grounds else 0
    return (f'<svg class="{cls}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" '
            f'role="img" aria-label="{escape(aria, quote=True)}">{art}{marks}</svg>')


def box_map(boxes: list[dict[str, Any]], grounds: Optional[list[dict[str, Any]]] = None) -> str:
    """Side/Top toggle + one marker per box. ``boxes``: id, short, side, zone/area, status, status_word,
    count, location_confidence."""
    side = _view_svg(boxes, "side", "Side view of the car (left side shown) with one marker per fuse box", grounds)
    top = _view_svg(boxes, "top", "Top view of the car with one marker per fuse box", grounds)
    return ('<div class="fm-wrap">'
            '<input class="fm-radio" type="radio" name="fm-view" id="fm-v-side" checked>'
            '<input class="fm-radio" type="radio" name="fm-view" id="fm-v-top">'
            '<div class="fm-tabs" role="group" aria-label="Car view">'
            '<label for="fm-v-side">Side</label><label for="fm-v-top">Top</label></div>'
            "<figure class=\"fm-fig fm-side\"><figcaption>Side view: the car's left (driver's) side. "
            f'Boxes on the right side are drawn hollow, on the far side.</figcaption><div class="fm-scroll">{side}</div></figure>'
            '<figure class="fm-fig fm-topv"><figcaption>Top view: looking down, front to the left; right side at the top.'
            f'</figcaption><div class="fm-scroll">{top}</div></figure></div>')


def _pos_key(r: dict[str, Any]) -> tuple[int, int, str]:
    m = re.search(r"\d+", str(r.get("position") or ""))
    return (0, int(m.group()), str(r.get("position") or "")) if m else (1, 0, str(r.get("label") or ""))


def slot_svg(rows: list[dict[str, Any]], title: str, cols: int = 6) -> tuple[str, bool]:
    """(svg, every slot placed from layout data). ('', False) for no rows."""
    if not rows:
        return "", False
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
    cw, ch, gap, pad, top = 84, 64, 8, 14, 34
    W, H = cols * (cw + gap) - gap + 2 * pad, nrows * (ch + gap) - gap + top + pad
    p = [f'<svg class="fm-slots" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="{escape("Slot layout of " + title + ": " + str(len(rows)) + " listed, in number order", quote=True)}">',
         f'<rect class="fm-outline" x="2" y="2" width="{W - 4}" height="{H - 4}" rx="10"/>',
         f'<text class="fm-slot-title" x="{pad}" y="22">{escape(title)}</text>']
    for (r_, c_), it in sorted(cells.items()):
        x, y = pad + c_ * (cw + gap), top + r_ * (ch + gap)
        st = it.get("status") if it.get("status") in MARK else "grey"
        rating = f'{it["rating_a"]:g} A' if it.get("rating_a") else "A ?"
        pos = it.get("position") or "?"
        rx = 22 if it.get("kind") == "relay" else 6
        sp = it.get("spec") or {}
        typ = str(sp.get("type") or ("relay" if it.get("kind") == "relay" else ""))[:10]
        col = sp.get("colour") or ""
        tip = f'{pos} {it.get("label", "")} - {rating} - {typ or "type not sourced"} - {col or "colour not sourced"} - {it.get("status_word", "")}'
        p.append(f'<a class="fm-slot fuse-{st}" href="#fuse-{escape(str(it["anchor"]), quote=True)}"><title>{escape(tip)}</title>'
                 f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="{rx}"/>'
                 f'<text class="fm-pos" x="{x + cw / 2}" y="{y + 26}" text-anchor="middle">{escape(str(pos))}</text>'
                 f'<text class="fm-amp" x="{x + cw / 2}" y="{y + 43}" text-anchor="middle">{escape(rating)}</text>'
                 f'<text class="fm-kind" x="{x + cw / 2}" y="{y + 57}" text-anchor="middle">{escape(typ)}</text>'
                 + (f'<rect class="fm-sw {colour_class(col)}" x="{x + 6}" y="{y + 8}" width="14" height="9" rx="2"/>' if col else "")
                 + f'<text class="fm-smark" x="{x + cw - 8}" y="{y + 15}" text-anchor="end">{MARK[st]}</text></a>')
    p.append("</svg>")
    return "".join(p), explicit and not rest
