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
#: Anchors follow the drawing below (front axle x=199, rear axle x=650, wheel
#: centres y=269, sill y=292, roof y~59); a drawing convention, not a measurement.
ZONES: list[dict[str, Any]] = [
    {"id": "front_bumper", "label": "Front bumper", "ax": 66, "ay": 262, "lx": 40, "ly": 346, "ta": "start"},
    {"id": "engine_bay", "label": "Engine bay", "ax": 236, "ay": 178, "lx": 236, "ly": 110, "ta": "middle"},
    {"id": "front_left_wheel_well", "label": "Front wheel wells", "ax": 199, "ay": 236, "lx": 199, "ly": 346, "ta": "middle"},
    {"id": "front_right_wheel_well", "label": "", "ax": 199, "ay": 298, "lx": 199, "ly": 346, "ta": "middle"},
    {"id": "windscreen", "label": "Windscreen", "ax": 398, "ay": 112, "lx": 372, "ly": 70, "ta": "middle"},
    {"id": "cabin_dash", "label": "Dash", "ax": 372, "ay": 176, "lx": 352, "ly": 230, "ta": "middle"},
    {"id": "cabin_driver", "label": "Cabin (driver)", "ax": 446, "ay": 180, "lx": 432, "ly": 230, "ta": "middle"},
    {"id": "cabin_passenger", "label": "Cabin (passenger)", "ax": 540, "ay": 178, "lx": 540, "ly": 230, "ta": "middle"},
    {"id": "roof", "label": "Roof", "ax": 570, "ay": 60, "lx": 570, "ly": 44, "ta": "middle"},
    {"id": "under_car_exhaust", "label": "Underbody / exhaust", "ax": 424, "ay": 310, "lx": 424, "ly": 346, "ta": "middle"},
    {"id": "fuel_tank", "label": "Fuel tank", "ax": 566, "ay": 266, "lx": 566, "ly": 314, "ta": "middle"},
    {"id": "rear_left_wheel_well", "label": "Rear wheel wells", "ax": 650, "ay": 236, "lx": 650, "ly": 346, "ta": "middle"},
    {"id": "rear_right_wheel_well", "label": "", "ax": 650, "ay": 298, "lx": 650, "ly": 346, "ta": "middle"},
    {"id": "trunk", "label": "Tailgate / trunk", "ax": 728, "ay": 138, "lx": 772, "ly": 76, "ta": "middle"},
    {"id": "fuse_box_engine_bay", "label": "Fuse box (engine bay)", "ax": 140, "ay": 192, "lx": 120, "ly": 160, "ta": "middle"},
    {"id": "fuse_box_interior", "label": "Fuse box (dash / footwell)", "ax": 384, "ay": 222, "lx": 384, "ly": 316, "ta": "middle"},
    {"id": "fuse_box_rear", "label": "Fuse box (rear)", "ax": 752, "ay": 196, "lx": 822, "ly": 252, "ta": "end"},
    {"id": "rear_bumper", "label": "Rear bumper", "ax": 800, "ay": 254, "lx": 830, "ly": 346, "ta": "end"},
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


_AXLE_F, _AXLE_R, _WHEEL_Y, _TYRE_R, _RIM_R = 199, 650, 269, 59, 37
_ARCH_R, _CLAD_R, _SILL_Y = 70, 79, 288

#: Credit for the photo the side view is traced from (CC BY-SA 4.0 requires it;
#: the traced outline below is a derivative and is shared under the same licence).
SIDE_VIEW_CREDIT = {
    "text": 'Side view traced from "2018 Alfa Romeo Stelvio 2.1" by Vauxford, Wikimedia Commons, CC BY-SA 4.0',
    "photo": "https://commons.wikimedia.org/wiki/File:2018_Alfa_Romeo_Stelvio_2.1.jpg",
    "licence": "https://creativecommons.org/licenses/by-sa/4.0/",
}


def _wheel(cx: float) -> str:
    """Tyre and the five-hole 'telephone dial' rim the reference car wears."""
    cy = _WHEEL_Y
    p = [f'<circle cx="{cx}" cy="{cy}" r="{_TYRE_R}" fill="var(--ink-3)" fill-opacity="0.22" '
         f'stroke="var(--ink-2)" stroke-width="1.6"/>',
         f'<circle cx="{cx}" cy="{cy}" r="{_RIM_R}" fill="var(--surface-2)" stroke="var(--ink-3)" stroke-width="1.2"/>',
         f'<circle cx="{cx}" cy="{cy}" r="7" fill="var(--surface)" stroke="var(--ink-3)" stroke-width="1"/>']
    for k in range(5):
        a = math.radians(-90 + k * 72)
        p.append(f'<circle cx="{cx + 21 * math.cos(a):.1f}" cy="{cy + 21 * math.sin(a):.1f}" r="10" '
                 f'fill="var(--ink-3)" fill-opacity="0.35" stroke="var(--ink-3)" stroke-width="1"/>')
    return "".join(p)


def _arch(cx: float, r: float) -> tuple[float, float]:
    dx = math.sqrt(r * r - (_SILL_Y - _WHEEL_Y) ** 2)
    return cx - dx, cx + dx


def _car_line_art() -> str:
    """Left-side Stelvio (949) profile, nose to the LEFT.

    Traced from a photograph (see :data:`SIDE_VIEW_CREDIT`): the photo was
    perspective-corrected on the four tyre top/bottom points so the side
    plane between the wheels is true to scale, and the roofline, window
    outline (with its pointed rear tip), B-pillar, quarter-glass frame,
    mirror, door shut lines, handles, shoulder and lower crease, sill strip,
    fuel flap and tail lamp were read off it. The photo is a front
    three-quarter view, so the overhangs are set to the car's published
    length (4687 mm, 2818 mm wheelbase) rather than read from it; the
    front/rear split of the 1869 mm of overhang is not in any source found,
    so it is a drawing choice.
    0.16 drawing units per mm; axles at x=199 / 650, wheel centres y=269,
    ground y=328."""
    ink = 'stroke="var(--ink-3)" stroke-linecap="round" stroke-linejoin="round"'
    line = f'fill="none" {ink} stroke-width="1.2"'
    thin = f'fill="none" {ink} stroke-width="0.9" opacity="0.8"'
    clad = 'fill="var(--ink-3)" fill-opacity="0.28" stroke="var(--ink-3)" stroke-width="0.9" stroke-linejoin="round"'
    glass = 'fill="var(--surface-2)" stroke="var(--ink-3)" stroke-width="1.2" stroke-linejoin="round"'
    fa0, fa1 = _arch(_AXLE_F, _ARCH_R)
    ra0, ra1 = _arch(_AXLE_R, _ARCH_R)
    body = (f"M{fa0:.1f},{_SILL_Y} "
            "L118,292 C92,294 74,296 66,294 "            # front lower lip
            "C60,290 57,280 57,266 "                      # bumper face
            "C56,244 57,220 60,204 "                      # nose
            "C63,188 70,178 82,172 "                      # bonnet leading edge
            "C160,159 260,148 326,141 "                   # bonnet / fender line to the screen base
            "C350,112 372,86 396,64 "                     # raked A-pillar
            "C430,56 490,54 540,56 "                      # roof
            "C590,59 630,70 660,92 "                      # roof falls to the spoiler
            "L672,97 L668,103 "                           # roof spoiler lip
            "C700,114 735,128 756,138 "                   # fast tailgate glass
            "C772,142 786,146 794,156 "                   # over the tail lamp
            "C799,170 800,188 800,206 "                   # tailgate edge
            "L801,244 "                                    # rear bumper face
            "C801,258 797,268 790,274 "                   # bumper round-under
            "C780,282 770,288 760,290 "                   # diffuser
            f"L{ra1:.1f},{_SILL_Y} "
            f"A{_ARCH_R},{_ARCH_R} 0 1 0 {ra0:.1f},{_SILL_Y} "   # rear arch
            f"L{fa1:.1f},{_SILL_Y} "                              # sill
            f"A{_ARCH_R},{_ARCH_R} 0 1 0 {fa0:.1f},{_SILL_Y} Z")  # front arch
    p = ['<g class="car-art" aria-hidden="true">',
         f'<line x1="16" y1="{_GROUND}" x2="844" y2="{_GROUND}" stroke="var(--rule)" stroke-width="1"/>',
         f'<path d="{body}" fill="var(--surface)" stroke="var(--ink-2)" stroke-width="1.8" stroke-linejoin="round"/>']
    # black arch cladding (a band outside each opening) and lower sill cladding
    for cx in (_AXLE_F, _AXLE_R):
        a0, a1 = _arch(cx, _ARCH_R)
        c0, c1 = _arch(cx, _CLAD_R)
        p.append(f'<path d="M{a1:.1f},{_SILL_Y} A{_ARCH_R},{_ARCH_R} 0 1 0 {a0:.1f},{_SILL_Y} L{c0:.1f},{_SILL_Y} '
                 f'A{_CLAD_R},{_CLAD_R} 0 1 1 {c1:.1f},{_SILL_Y} Z" {clad}/>')
    p.append(f'<path d="M{_arch(_AXLE_F, _CLAD_R)[1]:.1f},{_SILL_Y} L{_arch(_AXLE_R, _CLAD_R)[0]:.1f},{_SILL_Y} '
             f'L{_arch(_AXLE_R, _CLAD_R)[0] - 2:.1f},281 L{_arch(_AXLE_F, _CLAD_R)[1] + 2:.1f},281 Z" {clad}/>')
    p += [_wheel(_AXLE_F), _wheel(_AXLE_R)]
    # glasshouse: front door glass, rear door glass, fixed quarter glass, rising to a pointed rear tip
    p.append('<path d="M340,136 C356,112 374,88 396,72 C440,66 500,66 540,70 C574,73 600,82 616,96 '
             'C622,102 626,108 627,113 C540,120 420,130 340,136 Z" ' + glass + '/>')
    p.append('<path d="M337,139 C430,131 540,121 630,113" fill="none" stroke="var(--ink-2)" stroke-width="1.2"/>')
    p.append('<path d="M466,68 L470,128 L486,127 L484,68 Z" fill="var(--ink-3)" fill-opacity="0.6"/>')  # B-pillar
    p.append('<path d="M580,74 L583,120 L589,119 L587,76 Z" fill="var(--ink-3)" fill-opacity="0.6"/>')  # quarter frame
    # door mirror on the door, ahead of the glass
    p.append('<path d="M334,140 C330,126 342,113 362,112 C380,111 391,119 389,129 C387,139 372,145 352,146 '
             'L346,151 L338,150 Z" fill="var(--surface)" stroke="var(--ink-3)" stroke-width="1.2" stroke-linejoin="round"/>')
    # door shut lines: front door leading edge, front/rear split, rear door around the arch
    p.append(f'<path d="M327,143 C320,154 316,166 315,182 L314,281" {thin}/>')
    p.append(f'<path d="M478,130 L482,281" {thin}/>')
    p.append(f'<path d="M627,114 C640,124 646,136 645,152 C644,168 638,182 630,192" {thin}/>')
    # handles, shoulder crease through them, lower door crease, chrome sill strip
    p.append(f'<path d="M436,159 C446,156 466,156 478,158 M590,150 C600,147 618,147 630,149" {line}/>')
    p.append(f'<path d="M156,178 C280,164 420,152 520,146 C620,140 700,138 760,142" {thin}/>')
    p.append(f'<path d="M292,248 C380,243 500,239 600,236" {thin}/>')
    p.append(f'<path d="M296,278 L592,276" fill="none" stroke="var(--ink-2)" stroke-width="1.4" stroke-linecap="round"/>')
    # rear quarter: fuel flap, tail lamp, reflector; nose: headlamp, side intake, shield edge
    p.append(f'<path d="M672,146 C672,142 676,141 680,141 L722,141 C727,141 729,144 729,148 L729,166 '
             f'C729,170 726,172 722,172 L679,172 C675,172 672,170 672,166 Z" {line}/>')
    p.append(f'<path d="M742,142 C762,141 784,145 795,154 L797,170 C780,166 760,163 742,161 Z" {line}/>')
    p.append(f'<path d="M778,238 L800,238" {line}/>')
    p.append(f'<path d="M64,192 C96,182 130,175 158,172 L152,184 C124,188 96,194 66,206 Z" {line}/>')
    p.append(f'<path d="M64,240 L94,244 L98,282 L68,286 Z" {line}/>')
    p.append(f'<path d="M57,204 L62,203 L64,246 L58,250 Z" {line}/>')
    p.append('<text x="18" y="150" font-size="9" fill="var(--ink-3)" letter-spacing="1" '
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


_TRAY_ROW = 26
_TRAY_X0, _TRAY_PER_ROW = 24, 34


def _tray(unplaced: list[dict[str, Any]], y0: float, width: float, href_prefix: str, dim: set[str]) -> tuple[str, float]:
    """Every item with no sourced location, as a row of dots UNDER the drawing,
    so each icon appears on the picture even before its location is known.
    Returns (svg, extra height)."""
    if not unplaced:
        return "", 0.0
    per = max(1, int((width - 2 * _TRAY_X0) // (2 * _R + 6)))
    rows = (len(unplaced) + per - 1) // per
    p = [f'<line x1="16" y1="{y0 + 4}" x2="{width - 16}" y2="{y0 + 4}" stroke="var(--rule)" stroke-dasharray="3 4"/>',
         f'<text class="sens-zl on" x="16" y="{y0 + 20}">Location not sourced yet ({len(unplaced)}) '
         f'- shown here so every item is on the picture; not placed on the car</text>']
    for i, s in enumerate(unplaced):
        r, c = divmod(i, per)
        x = _TRAY_X0 + _R + c * (2 * _R + 6)
        y = y0 + 38 + r * _TRAY_ROW
        p.append(_dot(s, x, y, href_prefix, dim, show_side=False))
    return "".join(p), 36 + rows * _TRAY_ROW + 4


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
    tray, extra = _tray([s for s in items if resolve_zone(s.get("zone")) is None], _VB_H, _VB_W, href_prefix, dim)
    p = [f'<svg class="sens-profile" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_VB_W} {_VB_H + extra:.0f}" '
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
        p.append(_dot(by_id[sid], x, y, href_prefix, dim, show_side=True))
    p.append(tray)
    p.append("</svg>")
    return "".join(p)


# --- top view ---------------------------------------------------------------------
#
# Same x scale as the side view (front axle x=199, rear axle x=650, nose x=55,
# tail x=805), and every area sits at the same front-to-back x in both views.
# Looking down, nose to the LEFT: the car's LEFT side (the one the side view
# shows; the driver's side on this car) is at the BOTTOM, its RIGHT side at
# the TOP. Width 1903 mm at 0.16 units/mm: body y 48..352, centre line y=200,
# wheel track ~1610 mm so wheel centres at y=71 (right) and y=329 (left).

_TOP_W, _TOP_H = 860, 400
_CY = 200
_SIDE_SHIFT = 64     # how far a "left"/"right" item moves off the centre line

#: zone id -> top-view anchor and label. ``sided``: a left/right item moves
#: toward that side; wheel wells already are one side.
TOP_ZONES: dict[str, dict[str, Any]] = {
    "front_bumper": {"ax": 66, "ay": 200, "label": "Front bumper", "lx": 40, "ly": 386, "ta": "start", "sided": True},
    "engine_bay": {"ax": 236, "ay": 200, "label": "Engine bay", "lx": 236, "ly": 120, "ta": "middle", "sided": True},
    "front_left_wheel_well": {"ax": 199, "ay": 329, "label": "Front left wheel", "lx": 199, "ly": 386, "ta": "middle", "sided": False},
    "front_right_wheel_well": {"ax": 199, "ay": 71, "label": "Front right wheel", "lx": 199, "ly": 22, "ta": "middle", "sided": False},
    "windscreen": {"ax": 398, "ay": 160, "label": "Windscreen", "lx": 398, "ly": 118, "ta": "middle", "sided": True},
    "cabin_dash": {"ax": 372, "ay": 236, "label": "Dash", "lx": 372, "ly": 278, "ta": "middle", "sided": True},
    "cabin_driver": {"ax": 446, "ay": 268, "label": "Driver seat (left)", "lx": 446, "ly": 386, "ta": "middle", "sided": False},
    "cabin_passenger": {"ax": 540, "ay": 132, "label": "Passenger seat (right)", "lx": 540, "ly": 22, "ta": "middle", "sided": False},
    "roof": {"ax": 570, "ay": 156, "label": "Roof", "lx": 570, "ly": 118, "ta": "middle", "sided": True},
    "under_car_exhaust": {"ax": 424, "ay": 196, "label": "Under the car / exhaust", "lx": 424, "ly": 226, "ta": "middle", "sided": True},
    "fuel_tank": {"ax": 566, "ay": 244, "label": "Fuel tank (under)", "lx": 566, "ly": 286, "ta": "middle", "sided": True},
    "rear_left_wheel_well": {"ax": 650, "ay": 329, "label": "Rear left wheel", "lx": 650, "ly": 386, "ta": "middle", "sided": False},
    "rear_right_wheel_well": {"ax": 650, "ay": 71, "label": "Rear right wheel", "lx": 650, "ly": 22, "ta": "middle", "sided": False},
    "trunk": {"ax": 728, "ay": 200, "label": "Tailgate / trunk", "lx": 728, "ly": 146, "ta": "middle", "sided": True},
    "fuse_box_engine_bay": {"ax": 140, "ay": 200, "label": "Fuse box (engine bay)", "lx": 140, "ly": 146, "ta": "middle", "sided": True},
    # the interior box is named "passenger-side ... footwell" in its source: right side, by the dash
    "fuse_box_interior": {"ax": 384, "ay": 116, "label": "Fuse box (passenger footwell)", "lx": 384, "ly": 22, "ta": "middle", "sided": False},
    "fuse_box_rear": {"ax": 752, "ay": 200, "label": "Fuse box (rear)", "lx": 752, "ly": 22, "ta": "middle", "sided": True},
    "rear_bumper": {"ax": 800, "ay": 200, "label": "Rear bumper", "lx": 830, "ly": 386, "ta": "end", "sided": True},
}


def _top_anchor(item: dict[str, Any]) -> Optional[tuple[str, float, float]]:
    z = resolve_zone(item.get("zone"))
    t = TOP_ZONES.get(z or "")
    if t is None:
        return None
    side = (item.get("side") or "").lower()
    ay = t["ay"]
    if t["sided"] and side in ("left", "right"):
        ay += _SIDE_SHIFT if side == "left" else -_SIDE_SHIFT
    return f"{z}|{side if t['sided'] else ''}", t["ax"], ay


def top_layout(items: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """{item id: (x, y)} on the top view, clustered like :func:`layout`."""
    groups: dict[str, tuple[float, float, list[str]]] = {}
    for s in items:
        a = _top_anchor(s)
        if a is None:
            continue
        key, ax, ay = a
        groups.setdefault(key, (ax, ay, []))[2].append(s["id"])
    placed: dict[str, tuple[float, float]] = {}
    taken: list[tuple[float, float]] = []
    cells = _cells(0)
    for key in sorted(groups, key=lambda k: (groups[k][0], groups[k][1])):
        ax, ay, ids = groups[key]
        for sid in ids:
            for dx, dy in cells:
                x, y = ax + dx, ay + dy
                if not (14 <= x <= _TOP_W - 14 and 34 <= y <= _TOP_H - 30):
                    continue
                if all((x - tx) ** 2 + (y - ty) ** 2 >= (2 * _R + 2) ** 2 for tx, ty in taken):
                    taken.append((x, y))
                    placed[sid] = (x, y)
                    break
            else:
                placed[sid] = (ax, ay)
    return placed


def _car_top_art() -> str:
    """Plan view, nose LEFT, drawn to the same proportions as the side view
    (a proportional drawing, not a traced blueprint)."""
    ink = 'stroke="var(--ink-3)" stroke-linecap="round" stroke-linejoin="round"'
    line = f'fill="none" {ink} stroke-width="1.2"'
    thin = f'fill="none" {ink} stroke-width="0.9" opacity="0.75"'
    glass = 'fill="var(--surface-2)" stroke="var(--ink-3)" stroke-width="1.1" stroke-linejoin="round"'
    upper = [(58, 118), (64, 74), (100, 54), (199, 47), (300, 52), (420, 56), (560, 54),
             (650, 47), (744, 54), (792, 70), (806, 112)]
    pts = upper + [(x, 2 * _CY - y) for x, y in reversed(upper)]
    body = _smooth_closed(pts)
    p = ['<g class="car-art" aria-hidden="true">']
    # tyres first, dashed where the body hides them
    for cx in (_AXLE_F, _AXLE_R):
        for cy in (71, 329):
            p.append(f'<rect x="{cx - 59}" y="{cy - 19}" width="118" height="38" rx="9" '
                     f'fill="var(--ink-3)" fill-opacity="0.18" stroke="var(--ink-2)" stroke-width="1.2"/>')
    p.append(f'<path d="{body}" fill="var(--surface)" fill-opacity="0.9" stroke="var(--ink-2)" stroke-width="1.8" stroke-linejoin="round"/>')
    for cx in (_AXLE_F, _AXLE_R):
        for cy in (71, 329):
            p.append(f'<rect x="{cx - 59}" y="{cy - 19}" width="118" height="38" rx="9" fill="none" '
                     f'stroke="var(--ink-3)" stroke-width="0.9" stroke-dasharray="4 3"/>')
    # bonnet shut lines and its two raised ridges
    p.append(f'<path d="M86,88 C180,78 280,76 336,82 M86,312 C180,322 280,324 336,318" {thin}/>')
    p.append(f'<path d="M104,170 C200,166 290,170 334,178 M104,230 C200,234 290,230 334,222" {thin}/>')
    # windscreen, roof panel, rear screen
    p.append(f'<path d="M336,82 L456,96 L456,304 L336,318 Z" {glass}/>')
    p.append(f'<path d="M456,96 L742,104 L742,296 L456,304 Z" {thin}/>')
    p.append(f'<path d="M742,104 L794,120 L794,280 L742,296 Z" {glass}/>')
    # door mirrors at the A-pillar base, both sides
    p.append(f'<path d="M326,54 L334,30 Q340,26 352,28 L356,34 L350,56 Z" {line}/>')
    p.append(f'<path d="M326,346 L334,370 Q340,374 352,372 L356,366 L350,344 Z" {line}/>')
    # door shut lines across the top of the sills
    for y0, y1 in ((52, 60), (348, 340)):
        p.append(f'<path d="M296,{y0} L296,{y1} M511,{y0 + (2 if y0 < 200 else -2)} L511,{y1} '
                 f'M650,{y0 + (4 if y0 < 200 else -4)} L650,{y1}" {thin}/>')
    # head and tail lamps at the corners, shield on the nose
    p.append(f'<path d="M62,96 C70,72 90,60 116,56 L118,64 C96,70 80,84 72,104 Z" {line}/>')
    p.append(f'<path d="M62,304 C70,328 90,340 116,344 L118,336 C96,330 80,316 72,296 Z" {line}/>')
    p.append(f'<path d="M778,64 C792,72 802,86 806,104 L798,104 C794,90 786,78 774,70 Z" {line}/>')
    p.append(f'<path d="M778,336 C792,328 802,314 806,296 L798,296 C794,310 786,322 774,330 Z" {line}/>')
    p.append(f'<path d="M57,184 L64,186 L64,214 L57,216 Z" {line}/>')
    p.append(f'<path d="M70,200 L790,200" fill="none" stroke="var(--rule)" stroke-width="0.8" stroke-dasharray="2 6"/>')
    t = 'font-size="9" fill="var(--ink-3)" letter-spacing="1" font-family="var(--sans), sans-serif"'
    p.append(f'<text x="18" y="172" {t}>FRONT</text>')
    p.append(f'<text x="848" y="40" text-anchor="end" {t}>RIGHT SIDE</text>')
    p.append(f'<text x="848" y="368" text-anchor="end" {t}>LEFT SIDE (driver)</text>')
    p.append("</g>")
    return "".join(p)


def _dot(s: dict[str, Any], x: float, y: float, href_prefix: str, dim: set[str], show_side: bool) -> str:
    sid = s["id"]
    st = s.get("status") if s.get("status") in _STATUS_WORD else "grey"
    n = s.get("number", "")
    tip = s.get("title") or f'{s.get("label", sid)} — {_STATUS_WORD[st]}'
    cls = f"sens-dot sens-{st}" + (" sens-dim" if sid in dim else "")
    g = [f'<a class="{cls}" href="#{escape(href_prefix, quote=True)}{escape(sid, quote=True)}"><title>{escape(tip)}</title>']
    if s.get("location_confidence") == "INFERRED":
        g.append(f'<circle class="sens-ring" cx="{x:.1f}" cy="{y:.1f}" r="{_R + 4}"/>')
    elif s.get("location_confidence") == "GENERAL":
        g.append(f'<circle class="sens-ring sens-ring-general" cx="{x:.1f}" cy="{y:.1f}" r="{_R + 4}"/>')
    g.append(f'<circle class="sens-fill" cx="{x:.1f}" cy="{y:.1f}" r="{_R}"/>')
    g.append(f'<text class="sens-num" x="{x:.1f}" y="{y + 3.5:.1f}" text-anchor="middle">{n}</text>')
    tag = {"left": "L", "right": "R"}.get(s.get("side") or "", "") if show_side else ""
    if tag:
        g.append(f'<text class="sens-side" x="{x + _R + 1:.1f}" y="{y - _R + 1:.1f}">{tag}</text>')
    g.append("</a>")
    return "".join(g)


def top_svg(items: list[dict[str, Any]], *, href_prefix: str = "sensor-",
            aria_label: str = "Top view of the car, {n} items placed by area",
            dim: Iterable[str] = ()) -> str:
    """Top view with the same items/dots as :func:`profile_svg`. Safe for []."""
    dim = set(dim)
    pos = top_layout(items)
    by_id = {s["id"]: s for s in items}
    used = {resolve_zone(s.get("zone")) for s in items if s["id"] in pos}
    label = aria_label.replace("{n}", str(len(pos)))
    tray, extra = _tray([s for s in items if s["id"] not in pos], _TOP_H, _TOP_W, href_prefix, dim)
    p = [f'<svg class="sens-profile sens-top" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_TOP_W} {_TOP_H + extra:.0f}" '
         f'width="100%" role="img" aria-label="{escape(label, quote=True)}">',
         _car_top_art(), '<g class="sens-zones" aria-hidden="true">']
    for zid, z in TOP_ZONES.items():
        if zid in used:
            p.append(f'<text class="sens-zl on" x="{z["lx"]}" y="{z["ly"]}" text-anchor="{z["ta"]}">'
                     f'{escape(z["label"])}</text>')
    p.append("</g>")
    for sid, (x, y) in pos.items():
        p.append(_dot(by_id[sid], x, y, href_prefix, dim, show_side=False))
    p.append(tray)
    p.append("</svg>")
    return "".join(p)


def both_views(items: list[dict[str, Any]], *, href_prefix: str = "sensor-",
               aria_label: str = "Side view of the car with {n} items placed by area",
               legend: Optional[list[tuple[str, str]]] = None, dim: Iterable[str] = ()) -> str:
    """Side view then top view, each with a caption. Same dots, same numbers."""
    dim = list(dim)
    side = profile_svg(items, href_prefix=href_prefix, legend=legend, aria_label=aria_label, dim=dim)
    top = top_svg(items, href_prefix=href_prefix, dim=dim)
    c = SIDE_VIEW_CREDIT
    credit = (f'<p class="sens-credit">{escape(c["text"])} '
              f'(<a href="{c["photo"]}" rel="noopener">photo</a>, '
              f'<a href="{c["licence"]}" rel="noopener">licence</a>)</p>')
    return ('<figure class="sens-view"><figcaption>Side view: the car\'s left (driver\'s) side, front to the left'
            f'</figcaption>{side}{credit}</figure>'
            '<figure class="sens-view"><figcaption>Top view: looking down, front to the left; '
            f'left (driver\'s) side at the bottom, right side at the top</figcaption>{top}</figure>')


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
    return both_views(items, href_prefix="sensor-", dim=dim,
                      aria_label="Side view of the car with {n} sensors placed by zone")


# --- the mechanic's map: ONE view with a Side / Top toggle, clusters as count markers -------------
#
# Used by the sensors page only (the fuse page keeps both_views / box_map). One marker per area:
# a numbered dot for a lone sensor, a count marker for several (it opens the list filtered to that area).
# Labels are placed greedily where they touch neither a marker nor another label.

_MARK_R = 17          # numbered dot radius, drawing units
_CLUSTER_R = 24       # count marker radius
_HIT_R = 27           # invisible tap target: >= 44 px on screen once the drawing is >= 0.84 scale
_LABEL_FS = 19        # label font size in drawing units (16 px on screen at 0.84)
_STATUS_ORDER = ("red", "orange", "grey", "green")
_WORD = {"red": "not responding", "orange": "fault / out of range", "grey": "not read yet", "green": "OK"}


#: top-view anchors moved for THIS map only, so two tap targets never overlap (the fuse page keeps TOP_ZONES as is)
_MAP_NUDGE_TOP = {"windscreen": (398, 128), "under_car_exhaust": (430, 206)}


def _worst(statuses: Iterable[str]) -> str:
    s = set(statuses)
    return next((k for k in _STATUS_ORDER if k in s), "grey")


def _st(i: dict[str, Any]) -> str:
    return i.get("status") if i.get("status") in _STATUS_WORD else "grey"


def _is_right(it: dict[str, Any], zid: str) -> bool:
    return (it.get("side") or "").lower() == "right" or zid.endswith("_right_wheel_well")


def right_hidden(items: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """[(area label, how many)] for the right-side items the SIDE view leaves out (the Top view shows them)."""
    out: dict[str, int] = {}
    for it in items:
        zid = resolve_zone(it.get("zone"))
        if zid and _is_right(it, zid):
            left = ZONE_BY_ID.get(zid.replace("_right_", "_left_"), ZONE_BY_ID[zid])
            name = left["label"] or zid.replace("_", " ")
            out[name] = out.get(name, 0) + 1
    return list(out.items())


def _map_groups(items: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for it in items:
        zid = resolve_zone(it.get("zone"))
        if zid is None:
            continue
        if view != "top" and _is_right(it, zid):
            continue   # the side view is the car's left side: right-side items live on the Top view
        if view == "top":
            a = _top_anchor(it)
            if a is None:
                continue
            key, x, y = a
            x, y = _MAP_NUDGE_TOP.get(zid, (x, y))
        else:
            key, x, y = zid, ZONE_BY_ID[zid]["ax"], ZONE_BY_ID[zid]["ay"]
        g = groups.setdefault(key, {"key": key, "zone": zid, "x": x, "y": y, "items": []})
        g["items"].append(it)
    return list(groups.values())


def _label_text(g: dict[str, Any], view: str) -> str:
    top = TOP_ZONES.get(g["zone"]) or {}
    base = top.get("label") or ZONE_BY_ID[g["zone"]]["label"] or g["zone"].replace("_", " ")
    side = g["key"].partition("|")[2]
    return f"{base} ({side})" if view == "top" and side in ("left", "right") and top.get("sided") else base


def _rects_hit(a: tuple, b: tuple) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _box_dist(box: tuple, x: float, y: float) -> float:
    return math.hypot(max(box[0] - x, 0, x - box[2]), max(box[1] - y, 0, y - box[3]))


def _place_labels(groups: list[dict[str, Any]], view: str, w: float, h: float, fixed: list[tuple]) -> dict[str, tuple]:
    """{group key: (x, y, text-anchor, text)} for every label that fits without touching a marker or a label."""
    own_box = {g["key"]: (g["x"] - _HIT_R, g["y"] - _HIT_R, g["x"] + _HIT_R, g["y"] + _HIT_R) for g in groups}
    avoid = list(own_box.values()) + list(fixed)
    out: dict[str, tuple] = {}
    for g in sorted(groups, key=lambda g: (-len(g["items"]), g["x"], g["y"])):
        text = _label_text(g, view)
        tw = 0.56 * _LABEL_FS * len(text) + 6
        r = _CLUSTER_R + 5 if len(g["items"]) > 1 else _MARK_R
        x, y = g["x"], g["y"]
        for dx, dy, ta in ((0, r + _LABEL_FS + 2, "middle"), (0, -(r + 8), "middle"),
                           (r + 8, 6, "start"), (-(r + 8), 6, "end"),
                           (r + 4, r + _LABEL_FS, "start"), (-(r + 4), r + _LABEL_FS, "end"),
                           (r + 4, -(r + 2), "start"), (-(r + 4), -(r + 2), "end"),
                           (0, r + 2 * _LABEL_FS + 6, "middle"), (0, -(r + _LABEL_FS + 12), "middle"),
                           (r + 8, r + 2 * _LABEL_FS, "start"), (-(r + 8), r + 2 * _LABEL_FS, "end"),
                           (r + 8, -(r + _LABEL_FS), "start"), (-(r + 8), -(r + _LABEL_FS), "end")):
            lx, ly = x + dx, y + dy
            x0 = lx - tw / 2 if ta == "middle" else lx if ta == "start" else lx - tw
            box = (x0, ly - _LABEL_FS, x0 + tw, ly + 6)
            if box[0] < 2 or box[2] > w - 2 or box[1] < 2 or box[3] > h - 2:
                continue
            if any(_rects_hit(box, a) for a in avoid if a is not own_box[g["key"]]):
                continue
            mine = _box_dist(box, x, y)
            if any(_box_dist(box, o["x"], o["y"]) <= mine for o in groups if o is not g):
                continue   # a label must be nearer its own marker than any other
            g["box"] = box
            out[g["key"]] = (lx, ly, ta, text)
            avoid.append(box)
            break
    return out


def _marker(g: dict[str, Any], href_prefix: str, cluster_href: Any, dim: set) -> str:
    its = g["items"]
    st = _worst(_st(i) for i in its)
    x, y = g["x"], g["y"]
    faded = " sens-dim" if all(i["id"] in dim for i in its) else ""
    if len(its) == 1:
        i = its[0]
        href = f"#{href_prefix}{i['id']}"
        tip = i.get("title") or f"{i.get('label', i['id'])} — {_STATUS_WORD[st]}"
        body = (f'<circle class="sm-fill" cx="{x:.1f}" cy="{y:.1f}" r="{_MARK_R}"/>'
                f'<text class="sm-num" x="{x:.1f}" y="{y + 6:.1f}" text-anchor="middle">{escape(str(i.get("number", "")))}</text>')
        cls = "sm-single"
    else:
        href = cluster_href(g["zone"]) if cluster_href else f"#{href_prefix}{its[0]['id']}"
        counts = {k: sum(1 for i in its if _st(i) == k) for k in _STATUS_ORDER}
        detail = ", ".join(f"{n} {_WORD[k]}" for k, n in counts.items() if n)
        tip = f"{_label_text(g, 'side')}: {len(its)} sensors ({detail}). Opens the list for this area."
        body = (f'<circle class="sm-ring" cx="{x:.1f}" cy="{y:.1f}" r="{_CLUSTER_R + 5}"/>'
                f'<circle class="sm-fill" cx="{x:.1f}" cy="{y:.1f}" r="{_CLUSTER_R}"/>'
                f'<text class="sm-num sm-count" x="{x:.1f}" y="{y + 7:.1f}" text-anchor="middle">{len(its)}</text>')
        cls = "sm-cluster"
    return (f'<a class="sm-mark {cls} sens-{st}{faded}" href="{escape(href, quote=True)}"><title>{escape(tip)}</title>'
            f'<circle class="sm-hit" cx="{x:.1f}" cy="{y:.1f}" r="{_HIT_R}"/>{body}</a>')


def map_view_svg(items: list[dict[str, Any]], view: str, *, href_prefix: str = "sensor-", cluster_href: Any = None,
                 dim: Iterable[str] = ()) -> tuple[str, list[dict[str, Any]]]:
    """(svg, groups) for ``view`` in {"side", "top"}. Items without a drawn zone are not in the svg."""
    dim = set(dim)
    w, h = (_VB_W, _VB_H) if view == "side" else (_TOP_W, _TOP_H)
    groups = _map_groups(items, view)
    fixed = [(14, 138, 70, 156)] if view == "side" else [(14, 160, 70, 178), (740, 26, 850, 44), (660, 356, 850, 374)]
    labels = _place_labels(groups, view, w, h, fixed)
    art = _car_line_art() if view == "side" else _car_top_art()
    name = "Side view (the car's left side)" if view == "side" else "Top view"
    p = [f'<svg class="sens-profile sens-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" '
         f'aria-label="{escape(name)} with {len(groups)} areas marked">', art, '<g aria-hidden="true">']
    for g in groups:
        if g["key"] in labels:
            lx, ly, ta, text = labels[g["key"]]
            p.append(f'<text class="sm-label" x="{lx:.1f}" y="{ly:.1f}" text-anchor="{ta}">{escape(text)}</text>')
    p.append("</g>")
    for g in groups:
        g["label"] = labels[g["key"]][3] if g["key"] in labels else ""
        g["name"] = _label_text(g, view)
    p += [_marker(g, href_prefix, cluster_href, dim) for g in groups]
    p.append("</svg>")
    return "".join(p), groups


def sensor_map(items: list[dict[str, Any]], *, href_prefix: str = "sensor-", cluster_href: Any = None,
               default_view: str = "side", dim: Iterable[str] = ()) -> str:
    """ONE car picture with a Side / Top toggle (no script: two radios, like the fuse page). Safe for []."""
    dim = list(dim)
    side, sg = map_view_svg(items, "side", href_prefix=href_prefix, cluster_href=cluster_href, dim=dim)
    top, tg = map_view_svg(items, "top", href_prefix=href_prefix, cluster_href=cluster_href, dim=dim)
    top_on = default_view == "top"
    c = SIDE_VIEW_CREDIT

    def unl(gs: list[dict[str, Any]]) -> str:
        miss = [g for g in gs if not g["label"]]
        if not miss:
            return ""
        return ('<p class="sv-legend">Not labelled on the drawing: '
                + "; ".join(escape(f"{g['name']} ({', '.join('#' + str(i.get('number', '')) for i in g['items'])})") for g in miss)
                + "</p>")

    hidden = right_hidden(items)
    note = ('<p class="sv-legend sv-right">+ right side: see Top. '
            + "; ".join(f"{escape(n)} ({k})" for n, k in hidden) + "</p>") if hidden else ""
    return ('<div class="sv-wrap">'
            f'<input class="sv-radio" type="radio" name="sv-view" id="sv-side"{"" if top_on else " checked"}>'
            f'<input class="sv-radio" type="radio" name="sv-view" id="sv-top"{" checked" if top_on else ""}>'
            '<div class="sv-tabs" role="group" aria-label="Car view"><label for="sv-side">Side</label>'
            '<label for="sv-top">Top</label></div>'
            "<figure class=\"sv-fig sv-sidev\"><figcaption>Side view: the car's left (driver's) side, front to the left. "
            f'Each marker is an area, not an exact spot.</figcaption><div class="sv-scroll">{side}</div>{note}{unl(sg)}'
            f'<p class="sens-credit">{escape(c["text"])} (<a href="{c["photo"]}" rel="noopener">photo</a>, '
            f'<a href="{c["licence"]}" rel="noopener">licence</a>)</p></figure>'
            "<figure class=\"sv-fig sv-topv\"><figcaption>Top view: looking down, front to the left; left (driver's) "
            f'side at the bottom, right side at the top.</figcaption><div class="sv-scroll">{top}</div>{unl(tg)}</figure></div>')




__all__ = ["SIDE_VIEW_CREDIT", "render", "profile_svg", "top_svg", "both_views", "layout", "top_layout", "resolve_zone",
           "ZONES", "ZONE_ANCHORS", "TOP_ZONES", "sensor_map", "map_view_svg"]
