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
#: centres y=269, sill y~300, roof y~54); a drawing convention, not a measurement.
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


_AXLE_F, _AXLE_R, _WHEEL_Y, _TYRE_R, _RIM_R = 199, 650, 269, 59, 44

#: Credit for the photo the side view is traced from. The photo is CC0 (no credit
#: is required); it is given anyway. The trace itself is released the same way.
SIDE_VIEW_CREDIT = {
    "text": 'Side view traced from "Alfa Romeo Stelvio 154026" by Trop86, Wikimedia Commons, CC0',
    "photo": "https://commons.wikimedia.org/wiki/File:Alfa_Romeo_Stelvio_154026.jpg",
    "licence": "https://creativecommons.org/publicdomain/zero/1.0/",
}

# --- side outline, drawn to a true side-on photograph -----------------------------
# Reference: SIDE_VIEW_CREDIT (2446x1809, grey Stelvio parked side-on, about 8 degrees
# off axis with the rear nearer the camera). The photo was levelled on the two tyres
# and mapped into this frame (axles pinned at x=199 / 650, wheel centres y=269, tyre
# radius 59; docs/research/stelvio-side-trace-2026-10-27/). The 2026-10-27 automatic
# contour trace was replaced on 2026-10-29 by a hand-drawn outline over that
# rectified photo (named points, corner-aware Catmull-Rom; generator kept with the
# research tools): the trace had stretched the nose, bloated the tail and floated the
# rear glass. Arch radii measured on the photo: cladding 78.5 / 77, opening ~70.
#: Arch opening radius / cladding outer radius (drawing units).
_ARCH_R, _CLAD_R = 70.0, 78.0

_SIDE_BODY = (
    "M69.0,185.0 C64.2,187.5 63.0,193.2 61.0,198.0 C59.0,202.8 57.8,208.3 57.0,214.0 C56.2,219.7 "
    "56.0,226.0 56.0,232.0 C56.0,238.0 55.8,244.3 57.0,250.0 C58.2,255.7 60.5,261.7 63.0,266.0 "
    "C65.5,270.3 68.2,273.0 72.0,276.0 C75.8,279.0 80.3,282.0 86.0,284.0 C91.7,286.0 106.0,288.0 "
    "106.0,288.0 C106.0,288.0 118.9,260.8 123.0,251.5 C127.1,242.1 127.1,238.0 130.4,231.9 "
    "C133.7,225.8 137.9,220.0 142.7,215.0 C147.5,210.0 153.1,205.5 159.1,202.0 C165.0,198.5 "
    "171.6,195.6 178.3,193.8 C184.9,192.0 192.1,191.0 199.0,191.0 C205.9,191.0 213.1,192.0 "
    "219.7,193.8 C226.4,195.6 233.0,198.5 238.9,202.0 C244.9,205.5 250.5,210.0 255.3,215.0 "
    "C260.1,220.0 264.3,225.8 267.6,231.9 C270.9,238.0 272.4,241.1 275.0,251.5 C277.6,261.8 "
    "283.0,294.0 283.0,294.0 C283.0,294.0 305.5,295.7 330.0,296.0 C354.5,296.3 398.3,296.0 "
    "430.0,296.0 C461.7,296.0 497.3,296.3 520.0,296.0 C542.7,295.7 566.0,294.0 566.0,294.0 "
    "C566.0,294.0 571.4,261.9 574.0,251.5 C576.6,241.0 578.3,237.5 581.7,231.3 C585.2,225.1 "
    "589.6,219.1 594.7,214.0 C599.7,209.0 605.6,204.5 611.8,201.0 C618.0,197.5 625.0,194.8 "
    "631.9,193.1 C638.9,191.5 646.3,190.8 653.4,191.1 C660.5,191.4 667.9,192.7 674.6,195.0 "
    "C681.4,197.2 688.1,200.6 694.0,204.6 C699.8,208.6 705.4,213.6 709.9,219.1 C714.5,224.5 "
    "718.4,230.9 721.3,237.4 C724.2,243.9 723.3,249.4 727.2,258.1 C731.2,266.9 745.0,290.0 "
    "745.0,290.0 C745.0,290.0 764.5,289.8 772.0,288.0 C779.5,286.2 785.2,283.3 790.0,279.0 "
    "C794.8,274.7 798.3,268.5 801.0,262.0 C803.7,255.5 804.8,248.3 806.0,240.0 C807.2,231.7 "
    "807.8,221.7 808.0,212.0 C808.2,202.3 807.7,191.0 807.0,182.0 C806.3,173.0 805.0,164.7 "
    "804.0,158.0 C803.0,151.3 802.2,147.0 801.0,142.0 C799.8,137.0 798.3,132.2 797.0,128.0 "
    "C795.7,123.8 795.2,120.7 793.0,117.0 C790.8,113.3 788.8,110.2 784.0,106.0 C779.2,101.8 "
    "771.7,96.7 764.0,92.0 C756.3,87.3 747.3,82.2 738.0,78.0 C728.7,73.8 718.7,69.8 708.0,67.0 "
    "C697.3,64.2 686.3,62.3 674.0,61.0 C661.7,59.7 647.7,59.3 634.0,59.0 C620.3,58.7 606.0,58.7 "
    "592.0,59.0 C578.0,59.3 563.7,60.0 550.0,61.0 C536.3,62.0 523.0,63.3 510.0,65.0 C497.0,66.7 "
    "483.3,69.0 472.0,71.0 C460.7,73.0 451.0,74.2 442.0,77.0 C433.0,79.8 426.3,83.5 418.0,88.0 "
    "C409.7,92.5 400.7,98.5 392.0,104.0 C383.3,109.5 373.8,115.5 366.0,121.0 C358.2,126.5 352.3,133.2 "
    "345.0,137.0 C337.7,140.8 331.8,141.7 322.0,144.0 C312.2,146.3 299.0,148.7 286.0,151.0 "
    "C273.0,153.3 258.3,155.7 244.0,158.0 C229.7,160.3 214.7,162.7 200.0,165.0 C185.3,167.3 "
    "170.0,169.7 156.0,172.0 C142.0,174.3 127.0,177.2 116.0,179.0 C105.0,180.8 97.8,182.0 90.0,183.0 "
    "C82.2,184.0 73.8,182.5 69.0,185.0 Z"
)

#: Detail paths in the same frame (drawing units).
_SIDE_DETAIL = {
    "glass": (
        "M350.0,140.0 C350.0,140.0 360.7,128.0 368.0,122.0 C375.3,116.0 385.0,109.7 394.0,104.0 "
        "C403.0,98.3 412.7,92.3 422.0,88.0 C431.3,83.7 436.7,80.7 450.0,78.0 C463.3,75.3 483.3,73.2 "
        "502.0,72.0 C520.7,70.8 543.3,70.5 562.0,71.0 C580.7,71.5 599.3,72.8 614.0,75.0 C628.7,77.2 "
        "640.7,80.8 650.0,84.0 C659.3,87.2 664.3,90.0 670.0,94.0 C675.7,98.0 681.0,103.3 684.0,108.0 "
        "C687.0,112.7 688.0,122.0 688.0,122.0 C688.0,122.0 682.3,131.0 676.0,134.0 C669.7,137.0 "
        "662.7,138.7 650.0,140.0 C637.3,141.3 621.7,141.7 600.0,142.0 C578.3,142.3 548.3,142.0 "
        "520.0,142.0 C491.7,142.0 453.3,142.2 430.0,142.0 C406.7,141.8 393.3,141.3 380.0,141.0 "
        "C366.7,140.7 350.0,140.0 350.0,140.0 Z"
),
    "bpillar": "M472.0,75.0 L488.0,75.0 L477.0,141.0 L462.0,141.0 L472.0,75.0 Z",
    "quarter": "M636.0,76.0 C636.0,76.0 633.3,97.3 632.0,108.0 C630.7,118.7 628.0,140.0 628.0,140.0",
    "rearglass": (
        "M712.0,84.0 C712.0,84.0 756.5,94.3 770.0,100.0 C783.5,105.7 788.2,112.7 793.0,118.0 C797.8,123.3 "
        "799.0,132.0 799.0,132.0 C799.0,132.0 779.8,129.0 770.0,126.0 C760.2,123.0 749.0,118.3 "
        "740.0,114.0 C731.0,109.7 720.7,105.0 716.0,100.0 C711.3,95.0 712.0,84.0 712.0,84.0 Z"
),
    "mirror": (
        "M330.0,140.0 C329.2,137.0 329.7,131.5 331.0,128.0 C332.3,124.5 334.8,121.0 338.0,119.0 "
        "C341.2,117.0 346.0,116.2 350.0,116.0 C354.0,115.8 359.0,116.3 362.0,118.0 C365.0,119.7 "
        "367.2,121.8 368.0,126.0 C368.8,130.2 367.0,143.0 367.0,143.0 C367.0,143.0 355.2,145.5 "
        "350.0,146.0 C344.8,146.5 339.3,147.0 336.0,146.0 C332.7,145.0 330.8,143.0 330.0,140.0 Z"
),
    "flap": "M668.0,144.0 L702.0,144.0 L704.0,176.0 L668.0,176.0 L668.0,144.0 Z",
    "lamp": (
        "M714.0,146.0 C714.0,146.0 734.8,142.2 745.0,142.0 C755.2,141.8 765.8,143.3 775.0,145.0 "
        "C784.2,146.7 800.0,152.0 800.0,152.0 L801.0,166.0 C801.0,166.0 784.3,165.0 775.0,164.0 "
        "C765.7,163.0 755.2,161.3 745.0,160.0 C734.8,158.7 714.0,156.0 714.0,156.0 L714.0,146.0 Z"
),
    "head": (
        "M66.0,189.0 C66.0,189.0 76.7,186.2 84.0,185.0 C91.3,183.8 101.0,182.5 110.0,182.0 C119.0,181.5 "
        "138.0,182.0 138.0,182.0 C138.0,182.0 141.0,189.3 136.0,192.0 C131.0,194.7 116.7,195.8 "
        "108.0,198.0 C99.3,200.2 91.0,203.2 84.0,205.0 C77.0,206.8 66.0,209.0 66.0,209.0 L66.0,189.0 Z"
),
    "h1": (
        "M420.0,166.0 C420.0,166.0 426.7,161.8 432.0,161.0 C437.3,160.2 447.0,160.2 452.0,161.0 "
        "C457.0,161.8 462.0,166.0 462.0,166.0"
),
    "h2": (
        "M586.0,158.0 C586.0,158.0 592.7,153.8 598.0,153.0 C603.3,152.2 613.0,152.2 618.0,153.0 "
        "C623.0,153.8 628.0,158.0 628.0,158.0"
),
    "door1": (
        "M312.0,150.0 C312.0,150.0 302.7,165.7 300.0,176.0 C297.3,186.3 296.0,199.7 296.0,212.0 "
        "C296.0,224.3 298.3,237.3 300.0,250.0 C301.7,262.7 306.0,288.0 306.0,288.0"
),
    "door2": (
        "M470.0,143.0 C470.0,143.0 467.0,158.0 466.0,170.0 C465.0,182.0 464.2,200.8 464.0,215.0 "
        "C463.8,229.2 464.5,242.5 465.0,255.0 C465.5,267.5 467.0,290.0 467.0,290.0"
),
    "door3": (
        "M636.0,142.0 C636.0,142.0 631.3,160.3 628.0,170.0 C624.7,179.7 619.7,191.3 616.0,200.0 "
        "C612.3,208.7 606.0,222.0 606.0,222.0"
),
    "sill": "M283.0,284.0 L566.0,284.0 L566.0,295.0 L283.0,295.0 L283.0,284.0 Z",
    "exhaust": "M768.0,270.0 L786.0,262.0 L788.0,270.0 L776.0,280.0 L768.0,270.0 Z",
    "shoulder": (
        "M100.0,184.0 C100.0,184.0 166.7,171.3 200.0,166.0 C233.3,160.7 276.7,155.3 300.0,152.0 "
        "C323.3,148.7 340.0,146.0 340.0,146.0"
),
    "clad_f": "M123.0,251.5 A78,78 0 1 1 275.0,251.5 L267.2,253.3 A70,70 0 1 0 130.8,253.3 Z",
    "clad_r": "M574.0,251.5 A78,78 0 1 1 727.2,258.1 L719.3,259.3 A70,70 0 1 0 581.8,253.3 Z",
}


def _wheel(cx: float) -> str:
    """Tyre and the black five-twin-spoke rim the reference photo shows."""
    cy = _WHEEL_Y
    p = [f'<circle cx="{cx}" cy="{cy}" r="{_TYRE_R}" fill="var(--ink-3)" fill-opacity="0.22" '
         f'stroke="var(--ink-2)" stroke-width="1.6"/>',
         f'<circle cx="{cx}" cy="{cy}" r="{_RIM_R}" fill="var(--surface-2)" stroke="var(--ink-3)" stroke-width="1.2"/>']
    for k in range(5):
        for off in (-9, 9):
            a = math.radians(-90 + k * 72 + off)
            p.append(f'<line x1="{cx + 9 * math.cos(a):.1f}" y1="{cy + 9 * math.sin(a):.1f}" '
                     f'x2="{cx + 41 * math.cos(a):.1f}" y2="{cy + 41 * math.sin(a):.1f}" '
                     f'stroke="var(--ink-3)" stroke-width="2.6" stroke-linecap="round"/>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="6.5" fill="var(--surface)" stroke="var(--ink-3)" stroke-width="1"/>')
    return "".join(p)


def _car_line_art() -> str:
    """Left-side Stelvio (949) profile, nose to the LEFT, traced from a side-on
    photograph (see the block comment above and :data:`SIDE_VIEW_CREDIT`).
    Outline, wheel arches, glasshouse (front and rear door glass, B-pillar,
    quarter glass, rear glass edge), mirror, door shut lines, handles, fuel
    flap, tail lamp, headlamp, sill and exhaust are all read off that photo.
    Axles at x=199 / 650, wheel centres y=269, ground y=328."""
    ink = 'stroke="var(--ink-3)" stroke-linecap="round" stroke-linejoin="round"'
    line = f'fill="none" {ink} stroke-width="1.2"'
    thin = f'fill="none" {ink} stroke-width="0.9" opacity="0.8"'
    clad = 'fill="var(--ink-3)" fill-opacity="0.28" stroke="var(--ink-3)" stroke-width="0.9" stroke-linejoin="round"'
    glass = 'fill="var(--surface-2)" stroke="var(--ink-2)" stroke-width="1.3" stroke-linejoin="round"'
    d = _SIDE_DETAIL
    p = ['<g class="car-art" aria-hidden="true">',
         f'<line x1="16" y1="{_GROUND}" x2="844" y2="{_GROUND}" stroke="var(--rule)" stroke-width="1"/>',
         f'<path d="{_SIDE_BODY}" fill="var(--surface)" stroke="var(--ink-2)" stroke-width="1.8" stroke-linejoin="round"/>',
         f'<clipPath id="car-body-clip"><path d="{_SIDE_BODY}"/></clipPath>',
         f'<path d="{d["clad_f"]}" clip-path="url(#car-body-clip)" {clad}/>',
         f'<path d="{d["clad_r"]}" clip-path="url(#car-body-clip)" {clad}/>',
         f'<path d="{d["sill"]}" {clad}/>',
         _wheel(_AXLE_F), _wheel(_AXLE_R),
         f'<path d="{d["glass"]}" {glass}/>',
         f'<path d="{d["bpillar"]}" fill="var(--ink-3)" fill-opacity="0.6"/>',
         f'<path d="{d["quarter"]}" {line}/>',
         f'<path d="{d["rearglass"]}" {glass}/>',
         f'<path d="{d["mirror"]}" fill="var(--surface)" stroke="var(--ink-3)" stroke-width="1.2" stroke-linejoin="round"/>',
         f'<path d="{d["door1"]}" {thin}/>', f'<path d="{d["door2"]}" {thin}/>', f'<path d="{d["door3"]}" {thin}/>',
         f'<path d="{d["shoulder"]}" {thin}/>',
         f'<path d="{d["h1"]}" {line}/>', f'<path d="{d["h2"]}" {line}/>',
         f'<path d="{d["flap"]}" {line}/>', f'<path d="{d["lamp"]}" {line}/>',
         f'<path d="{d["head"]}" {line}/>', f'<path d="{d["exhaust"]}" {line}/>',
         '<text x="18" y="150" font-size="9" fill="var(--ink-3)" letter-spacing="1" '
         'font-family="var(--sans), sans-serif">FRONT</text>',
         "</g>"]
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
