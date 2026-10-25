"""Server-side SVG: a left-side PROFILE of the Stelvio with one coloured dot
per sensor, placed at its zone's anchor (``/v/{vin}/sensors``).

Same house style as :mod:`cuore.web.electrical_svg` (CSS classes / CSS
variables only, ``_smooth_closed`` for rounded outlines, thin ink-3 line art
under the data) but a side view, front of the car to the LEFT, because a
mechanic points at a sensor from the side of the car. No JavaScript.

Placement is by *zone only*. A zone's anchor is a drawing convention, not a
measured position: the dot says "somewhere in this area". Sensors sharing a
zone fan out around the anchor (hex grid, nearest free cell first) so dots
never overlap. Right-side sensors sit at the same longitudinal spot with a
small ``R`` tag, left-side ones ``L``; the right-side wheel-well anchors are
drawn on the lower half of the wheel to stay apart from the left-side ones.
A sensor whose zone is not in :data:`ZONES` is *unplaced* -- the page lists
those in a tray instead of guessing.
"""
from __future__ import annotations

import math
from html import escape
from typing import Any, Iterable, Optional

_VB_W, _VB_H = 860, 360
_R = 9           # dot radius
_PITCH = 22      # centre-to-centre distance in a cluster
_GROUND = 328

#: id, label, anchor (ax, ay), label position (lx, ly), text-anchor.
ZONES: list[dict[str, Any]] = [
    {"id": "front_bumper", "label": "Front bumper", "ax": 64, "ay": 236, "lx": 60, "ly": 346, "ta": "start"},
    {"id": "engine_bay", "label": "Engine bay", "ax": 168, "ay": 226, "lx": 150, "ly": 150, "ta": "middle"},
    {"id": "front_left_wheel_well", "label": "Front wheel wells", "ax": 210, "ay": 248, "lx": 210, "ly": 346, "ta": "middle"},
    {"id": "front_right_wheel_well", "label": "", "ax": 210, "ay": 304, "lx": 210, "ly": 346, "ta": "middle"},
    {"id": "windscreen", "label": "Windscreen", "ax": 356, "ay": 130, "lx": 330, "ly": 72, "ta": "middle"},
    {"id": "cabin_dash", "label": "Dash", "ax": 322, "ay": 190, "lx": 300, "ly": 238, "ta": "middle"},
    {"id": "cabin_driver", "label": "Cabin (driver)", "ax": 420, "ay": 190, "lx": 400, "ly": 238, "ta": "middle"},
    {"id": "cabin_passenger", "label": "Cabin (passenger)", "ax": 490, "ay": 190, "lx": 510, "ly": 238, "ta": "middle"},
    {"id": "roof", "label": "Roof", "ax": 520, "ay": 62, "lx": 520, "ly": 36, "ta": "middle"},
    {"id": "under_car_exhaust", "label": "Underbody / exhaust", "ax": 430, "ay": 302, "lx": 430, "ly": 346, "ta": "middle"},
    {"id": "fuel_tank", "label": "Fuel tank", "ax": 560, "ay": 252, "lx": 560, "ly": 288, "ta": "middle"},
    {"id": "rear_left_wheel_well", "label": "Rear wheel wells", "ax": 640, "ay": 248, "lx": 640, "ly": 346, "ta": "middle"},
    {"id": "rear_right_wheel_well", "label": "", "ax": 640, "ay": 304, "lx": 640, "ly": 346, "ta": "middle"},
    {"id": "trunk", "label": "Tailgate / trunk", "ax": 736, "ay": 186, "lx": 760, "ly": 112, "ta": "middle"},
    {"id": "fuse_box_engine_bay", "label": "Fuse box (engine bay)", "ax": 112, "ay": 222, "lx": 100, "ly": 120, "ta": "middle"},
    {"id": "fuse_box_interior", "label": "Fuse box (dash / footwell)", "ax": 350, "ay": 226, "lx": 350, "ly": 296, "ta": "middle"},
    {"id": "fuse_box_rear", "label": "Fuse box (rear)", "ax": 722, "ay": 228, "lx": 760, "ly": 290, "ta": "middle"},
    {"id": "rear_bumper", "label": "Rear bumper", "ax": 788, "ay": 246, "lx": 800, "ly": 346, "ta": "end"},
]
ZONE_BY_ID = {z["id"]: z for z in ZONES}
#: Zone id -> drawing anchor (placement only, not a measured position).
ZONE_ANCHORS: dict[str, tuple[float, float]] = {z["id"]: (z["ax"], z["ay"]) for z in ZONES}

#: Alternate zone names (electrical_svg's own ids and a few synonyms).
ALIASES = {
    "wheel_fl": "front_left_wheel_well", "wheel_fr": "front_right_wheel_well",
    "wheel_rl": "rear_left_wheel_well", "wheel_rr": "rear_right_wheel_well",
    "dash": "cabin_dash", "underbody": "under_car_exhaust",
}

_STATUS_WORD = {"green": "OK", "orange": "fault / out of range", "red": "dead / not responding",
                "grey": "not read yet"}


def resolve_zone(zone: Optional[str]) -> Optional[str]:
    """Zone string -> a drawn zone id, or None (unplaced)."""
    z = (zone or "").strip().lower()
    z = ALIASES.get(z, z)
    return z if z in ZONE_BY_ID else None


def _smooth_closed(pts: list[tuple[float, float]]) -> str:
    n = len(pts)
    mid = [((pts[i][0] + pts[(i + 1) % n][0]) / 2, (pts[i][1] + pts[(i + 1) % n][1]) / 2)
           for i in range(n)]
    d = [f"M{mid[-1][0]:.1f},{mid[-1][1]:.1f}"]
    for i in range(n):
        d.append(f"Q{pts[i][0]:.1f},{pts[i][1]:.1f} {mid[i][0]:.1f},{mid[i][1]:.1f}")
    return " ".join(d) + " Z"


def _wheel(cx: float) -> str:
    cy = 290
    p = [f'<circle cx="{cx}" cy="{cy}" r="39" fill="var(--surface-2)" stroke="var(--ink-2)" stroke-width="1.6"/>',
         f'<circle cx="{cx}" cy="{cy}" r="27" fill="none" stroke="var(--ink-3)" stroke-width="1"/>',
         f'<circle cx="{cx}" cy="{cy}" r="7" fill="none" stroke="var(--ink-3)" stroke-width="1"/>']
    for k in range(5):  # 5 spokes
        a = math.radians(-90 + k * 72)
        p.append(f'<line x1="{cx + 8 * math.cos(a):.1f}" y1="{cy + 8 * math.sin(a):.1f}" '
                 f'x2="{cx + 26 * math.cos(a):.1f}" y2="{cy + 26 * math.sin(a):.1f}" '
                 f'stroke="var(--ink-3)" stroke-width="2.2" stroke-linecap="round"/>')
    return "".join(p)


def _car_line_art() -> str:
    """Left-side Stelvio profile, nose to the left: long bonnet, raked
    windscreen, sloping roofline into a short tail, pronounced arches."""
    line = 'fill="none" stroke="var(--ink-3)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"'
    thin = 'fill="none" stroke="var(--ink-3)" stroke-width="0.9" stroke-linecap="round" opacity="0.7"'
    body = ("M72,270 Q58,268 58,250 Q56,222 66,208 Q80,196 130,190 Q220,172 300,158 L392,104 "
            "Q410,90 440,88 L600,88 Q650,90 700,122 Q760,150 780,176 Q796,196 798,226 L798,255 "
            "Q796,270 780,272 L689,272 A52,52 0 0 0 591,272 L259,272 A52,52 0 0 0 161,272 Z")
    p = ['<g class="car-art" aria-hidden="true">',
         f'<line x1="20" y1="{_GROUND}" x2="840" y2="{_GROUND}" stroke="var(--rule)" stroke-width="1"/>',
         f'<path d="{body}" fill="var(--surface)" stroke="var(--ink-2)" stroke-width="1.8" stroke-linejoin="round"/>',
         _wheel(210), _wheel(640)]
    for cx in (210, 640):  # arch lips
        p.append(f'<path d="M{cx - 49},272 A52,52 0 0 1 {cx + 49},272" {thin} transform="translate(0,-3)"/>')
    # glasshouse, B-pillar, belt line, door cuts, sills
    p.append('<path d="M318,154 L398,112 Q412,103 430,102 L592,102 Q630,104 660,126 L678,154 Z" '
             'fill="var(--surface-2)" stroke="var(--ink-3)" stroke-width="1.1" stroke-linejoin="round"/>')
    p.append(f'<path d="M512,102 L512,154" {line}/>')
    p.append(f'<path d="M300,158 L778,176" {thin}/>')
    p.append(f'<path d="M512,154 L512,262 M672,160 L676,262 M322,158 L330,262" {thin}/>')
    p.append(f'<path d="M330,262 L688,262" {thin}/>')
    p.append(f'<path d="M455,172 L485,172 M600,174 L630,174" {line}/>')  # door handles
    p.append(f'<path d="M318,150 L298,150 Q289,152 291,161 L316,163 Z" {line}/>')  # mirror
    p.append(f'<path d="M440,86 L600,86" {thin}/>')  # roof rail
    p.append(f'<path d="M66,212 L124,198 L130,206 L72,226 Z" {line}/>')  # headlamp
    p.append(f'<path d="M58,232 L68,230 L69,248 L58,246 Z" {line}/>')  # scudetto
    p.append(f'<path d="M74,254 L136,258" {line}/><path d="M60,262 L90,266" {thin}/>')  # intake, bumper
    p.append(f'<path d="M772,178 Q790,192 792,214 L778,212 L760,186 Z" {line}/>')  # tail lamp
    p.append(f'<path d="M797,248 L728,252" {thin}/>')  # rear bumper line
    p.append('<text x="20" y="150" font-size="9" fill="var(--ink-3)" letter-spacing="1" '
             'font-family="var(--sans), sans-serif">FRONT</text>')
    p.append("</g>")
    return "".join(p)


def _cells(n: int) -> list[tuple[float, float]]:
    """Hex-grid offsets around (0,0), nearest first, at least ``n`` of them."""
    cells = []
    for q in range(-6, 7):
        for r in range(-6, 7):
            x = _PITCH * (q + r / 2)
            y = _PITCH * (r * math.sqrt(3) / 2)
            cells.append((round(x, 1), round(y, 1)))
    cells.sort(key=lambda c: (c[0] ** 2 + c[1] ** 2, c[1], c[0]))
    return cells


def layout(sensors: list[dict[str, Any]]) -> tuple[dict[str, tuple[float, float]], list[str]]:
    """``({sensor_id: (x, y)}, [unplaced sensor ids])``. Deterministic."""
    placed: dict[str, tuple[float, float]] = {}
    unplaced: list[str] = []
    by_zone: dict[str, list[str]] = {}
    for s in sensors:
        z = resolve_zone(s.get("zone"))
        if z is None:
            unplaced.append(s["id"])
        else:
            by_zone.setdefault(z, []).append(s["id"])
    taken: list[tuple[float, float]] = []
    cells = _cells(0)
    for z in ZONES:  # drawing order: stable
        for sid in by_zone.get(z["id"], []):
            for dx, dy in cells:
                x, y = z["ax"] + dx, z["ay"] + dy
                if not (14 <= x <= _VB_W - 14 and 14 <= y <= _VB_H - 14):
                    continue
                if all((x - tx) ** 2 + (y - ty) ** 2 >= (2 * _R + 2) ** 2 for tx, ty in taken):
                    taken.append((x, y))
                    placed[sid] = (x, y)
                    break
            else:  # pathological crowding: stack on the anchor
                placed[sid] = (z["ax"], z["ay"])
    return placed, unplaced


def _reason(s: dict[str, Any]) -> str:
    r = [x for x in (s.get("reasons") or []) if x]
    return r[0] if r else ""


def profile_svg(items: list[dict[str, Any]], *, href_prefix: str = "sensor-",
                legend: Optional[list[tuple[str, str]]] = None,
                aria_label: str = "Sensor locations on the Stelvio",
                dim: Iterable[str] = ()) -> str:
    """Generic profile renderer. Each item: ``id, label, status``
    (green|orange|red|grey), ``zone, side, location_confidence, number``
    and optional ``title`` (tooltip; default "label -- status") .
    Dots link to ``#<href_prefix><id>``. ``legend`` is an optional list of
    ``(status, text)`` drawn inside the SVG; ``dim`` ids are faded. Items
    with an unknown zone are not drawn (see :func:`layout`). Safe for []."""
    dim = set(dim)
    pos, _ = layout(items)
    by_id = {s["id"]: s for s in items}
    used = {resolve_zone(s.get("zone")) for s in items}
    label = aria_label.replace("{n}", str(len(pos)))
    p = [f'<svg class="sens-profile" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_VB_W} {_VB_H}" '
         f'width="100%" role="img" aria-label="{escape(label, quote=True)}">',
         _car_line_art(), '<g class="sens-zones" aria-hidden="true">']
    # only the areas this page actually uses get a label: an unused label
    # (the sensor areas on the fuse page, say) is clutter under the dots
    for z in ZONES:
        if not z["label"] or z["id"] not in used:
            continue
        cls = "sens-zl on"
        p.append(f'<text class="{cls}" x="{z["lx"]}" y="{z["ly"]}" text-anchor="{z["ta"]}">{escape(z["label"])}</text>')
    p.append("</g>")
    if legend:
        x = 20
        p.append('<g class="sens-svg-legend" aria-hidden="true">')
        for st, text in legend:
            st = st if st in _STATUS_WORD else "grey"
            p.append(f'<g class="sens-dot sens-{st}"><circle class="sens-fill" cx="{x}" cy="20" r="6"/></g>'
                     f'<text class="sens-zl on" x="{x + 10}" y="24">{escape(text)}</text>')
            x += 28 + 6 * len(text)
        p.append("</g>")
    for sid, (x, y) in pos.items():
        s = by_id[sid]
        st = s.get("status") if s.get("status") in _STATUS_WORD else "grey"
        n = s.get("number", "")
        tip = s.get("title") or f'{s.get("label", sid)} — {_STATUS_WORD[st]}'
        cls = f"sens-dot sens-{st}" + (" sens-dim" if sid in dim else "")
        tag = {"left": "L", "right": "R"}.get(s.get("side") or "", "")
        g = [f'<a class="{cls}" href="#{escape(href_prefix, quote=True)}{escape(sid, quote=True)}"><title>{escape(tip)}</title>']
        if s.get("location_confidence") == "INFERRED":
            g.append(f'<circle class="sens-ring" cx="{x:.1f}" cy="{y:.1f}" r="{_R + 4}"/>')
        g.append(f'<circle class="sens-fill" cx="{x:.1f}" cy="{y:.1f}" r="{_R}"/>')
        g.append(f'<text class="sens-num" x="{x:.1f}" y="{y + 3.5:.1f}" text-anchor="middle">{n}</text>')
        if tag:
            g.append(f'<text class="sens-side" x="{x + _R + 1:.1f}" y="{y - _R + 1:.1f}">{tag}</text>')
        g.append("</a>")
        p.append("".join(g))
    p.append("</svg>")
    return "".join(p)


def render(sensors: list[dict[str, Any]], numbers: Optional[dict[str, int]] = None,
           dim: Iterable[str] = ()) -> str:
    """Sensor page wrapper: builds items (number, tooltip with first reason)
    and calls :func:`profile_svg`. ``numbers`` maps sensor id -> list number."""
    numbers = numbers or {}
    items = []
    for s in sensors:
        st = s.get("status") if s.get("status") in _STATUS_WORD else "grey"
        reason = _reason(s)
        title = f'{s.get("label", s["id"])} — {_STATUS_WORD[st]}' + (f" — {reason}" if reason else "")
        items.append({**s, "status": st, "number": numbers.get(s["id"], ""), "title": title})
    return profile_svg(items, href_prefix="sensor-", dim=dim,
                       aria_label="Side view of the car with {n} sensors placed by zone")


__all__ = ["render", "profile_svg", "layout", "resolve_zone", "ZONES", "ZONE_ANCHORS"]
