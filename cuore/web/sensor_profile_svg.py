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

# --- side outline, traced from a true side-on photograph -----------------------
# Source: SIDE_VIEW_CREDIT (2446x1809, grey Stelvio parked side-on, level camera).
# Method (docs/research/stelvio-side-trace-2026-10-27/): the car was cut from the
# hedge/road by hue + saturation thresholds and flood fill, the outer contour
# traced, smoothed, Douglas-Peucker simplified (0.9 unit) and written as
# corner-aware Catmull-Rom Beziers. The photo was levelled on the two tyres
# (axle line rotated flat, scale along the car set by the tyre radius so the
# near-end perspective is removed), then mapped into this drawing's frame:
# axles pinned at x=199 / 650, wheel centres y=269, tyre radius 59, nose x=57,
# tail x=801, so every zone anchor keeps its place. Because the axles and both
# ends are pinned, the photo's overhangs are rescaled to this frame's 142 / 151
# (nose x1.47, tail x0.89): the nose is the least certain part of the shape.
#: Arch opening / arch-lining outer radius, from the photo (1.24 and 1.38 tyre radii).
_ARCH_R, _CLAD_R = 73.2, 81.0

_SIDE_BODY = (
    "M516.5,55.2 C536.2,54.6 552.0,57.2 560.2,57.4 C568.4,57.6 558.9,56.3 565.6,56.1 "
    "C572.3,56.0 588.0,56.0 600.2,56.6 C612.4,57.2 631.3,59.3 638.9,59.7 "
    "C646.6,60.1 643.3,60.2 646.2,59.1 C649.0,58.0 653.2,54.0 656.1,53.1 "
    "C659.1,52.1 662.1,53.0 663.9,53.3 C665.6,53.6 665.7,53.4 666.5,54.7 "
    "C667.3,56.0 667.9,59.6 668.7,61.0 C669.4,62.4 666.9,62.3 671.2,63.1 "
    "C675.5,63.8 685.2,64.3 694.7,65.8 C704.3,67.3 728.4,72.2 728.4,72.2 "
    "C728.4,72.2 728.4,80.0 728.7,82.0 C729.0,84.0 728.6,83.5 730.2,84.3 "
    "C731.8,85.1 734.2,85.1 738.2,86.8 C742.2,88.6 748.9,91.5 754.0,94.9 "
    "C759.2,98.3 765.7,104.6 769.3,107.3 C772.9,109.9 773.1,110.0 775.7,110.7 "
    "C778.2,111.4 784.5,111.4 784.5,111.4 C784.5,111.4 784.7,115.9 786.4,117.9 "
    "C788.1,119.9 794.6,123.4 794.6,123.4 C794.6,123.4 795.1,149.0 795.9,156.9 "
    "C796.6,164.9 798.7,167.2 799.3,171.4 C799.9,175.6 799.8,179.4 799.4,182.0 "
    "C799.0,184.6 797.3,185.1 796.8,187.0 C796.3,188.8 797.1,191.2 796.5,193.0 "
    "C795.9,194.9 793.1,198.2 793.1,198.2 C793.1,198.2 798.0,208.0 798.9,214.3 "
    "C799.9,220.5 799.9,228.6 798.6,235.5 C797.4,242.3 793.3,251.5 791.5,255.3 "
    "C789.6,259.1 789.2,256.3 787.6,258.3 C785.9,260.3 784.4,264.8 781.6,267.3 "
    "C778.9,269.8 777.9,270.6 771.0,273.4 C764.1,276.1 749.9,281.7 740.2,283.8 "
    "C730.5,285.8 712.8,285.8 712.8,285.8 C712.8,285.8 714.8,274.4 714.9,268.3 "
    "C715.0,262.3 714.6,255.5 713.5,249.5 C712.3,243.6 710.4,237.7 708.1,232.7 "
    "C705.9,227.7 703.3,223.6 700.2,219.6 C697.1,215.6 693.5,211.8 689.5,208.5 "
    "C685.4,205.3 680.8,202.4 676.1,200.3 C671.4,198.2 666.5,196.8 661.4,196.0 "
    "C656.4,195.2 650.9,195.1 645.7,195.5 C640.5,196.0 635.9,196.7 630.2,198.5 "
    "C624.6,200.4 617.7,203.1 611.9,206.5 C606.0,209.9 599.7,215.0 595.3,219.0 "
    "C591.0,223.0 588.6,226.1 585.7,230.5 C582.7,234.9 579.7,240.4 577.6,245.3 "
    "C575.5,250.2 574.1,254.6 573.2,259.9 C572.3,265.2 571.7,271.7 572.0,277.1 "
    "C572.2,282.6 574.4,289.9 574.7,292.7 C575.0,295.5 573.8,294.2 573.8,294.2 L269.1,297.6 "
    "C269.1,297.6 267.3,299.8 268.3,296.2 C269.2,292.5 273.6,281.5 274.9,275.6 "
    "C276.1,269.7 276.1,266.0 275.7,260.8 C275.3,255.5 274.5,249.8 272.6,244.2 "
    "C270.7,238.6 268.2,232.7 264.5,227.3 C260.9,222.0 255.1,216.0 250.8,212.2 "
    "C246.5,208.3 243.9,206.6 238.8,204.0 C233.8,201.5 226.5,198.6 220.5,197.1 "
    "C214.5,195.6 209.1,195.0 202.7,194.8 C196.3,194.7 188.8,195.4 182.1,196.3 "
    "C175.3,197.3 168.1,198.8 162.1,200.5 C156.1,202.1 151.4,203.6 145.8,206.0 "
    "C140.2,208.3 134.9,210.5 128.7,214.5 C122.5,218.6 114.0,225.0 108.7,230.1 "
    "C103.4,235.2 100.1,240.0 97.1,245.2 C94.1,250.5 91.8,257.7 90.5,261.7 "
    "C89.1,265.7 89.4,265.7 89.2,269.4 C89.1,273.0 89.6,283.5 89.6,283.5 "
    "C89.6,283.5 82.8,283.8 79.5,283.5 C76.2,283.2 71.8,282.4 69.8,281.8 "
    "C67.7,281.2 67.0,279.9 67.0,279.9 C67.0,279.9 66.4,277.3 66.8,275.4 "
    "C67.2,273.4 69.9,271.3 69.4,268.1 C68.9,265.0 65.7,259.8 63.9,256.6 "
    "C62.1,253.5 60.4,251.3 58.5,249.2 C56.6,247.1 53.7,247.3 52.5,244.0 "
    "C51.3,240.8 51.1,229.6 51.1,229.6 C51.1,229.6 56.3,226.6 57.5,224.2 "
    "C58.7,221.9 57.2,218.6 58.1,215.5 C59.0,212.5 61.9,208.7 62.8,205.7 "
    "C63.8,202.7 62.8,200.0 63.6,197.5 C64.3,195.0 64.4,193.9 67.3,190.8 "
    "C70.3,187.7 76.5,182.2 81.4,178.9 C86.3,175.5 91.9,172.8 96.7,170.6 "
    "C101.5,168.4 100.9,168.0 110.1,165.6 C119.3,163.3 141.2,158.5 151.7,156.4 "
    "C162.2,154.3 167.8,154.2 173.2,153.1 C178.6,152.0 175.0,151.3 184.3,149.7 "
    "C193.5,148.1 218.6,145.2 228.9,143.4 C239.2,141.6 241.2,139.6 246.1,138.8 "
    "C251.0,137.9 253.7,138.8 258.1,138.2 C262.4,137.6 268.5,135.8 272.1,135.3 "
    "C275.7,134.8 279.7,135.2 279.7,135.2 C279.7,135.2 281.1,137.6 281.8,138.2 "
    "C282.5,138.9 281.5,139.8 284.0,138.9 C286.5,138.0 290.7,134.2 296.9,132.7 "
    "C303.1,131.3 316.8,130.7 321.1,130.1 C325.4,129.5 322.2,130.3 322.5,128.9 "
    "C322.8,127.6 322.2,124.6 323.0,122.1 C323.8,119.6 324.6,115.9 327.3,114.1 "
    "C329.9,112.3 332.8,114.8 339.0,111.3 C345.2,107.9 356.1,98.9 364.5,93.6 "
    "C372.9,88.3 381.7,83.7 389.4,79.8 C397.1,75.9 405.0,72.3 410.6,70.1 "
    "C416.3,68.0 420.4,67.7 423.2,66.7 C426.0,65.7 424.3,65.0 427.4,64.1 "
    "C430.5,63.2 427.0,62.8 441.8,61.3 C456.7,59.9 496.7,55.9 516.5,55.2 Z"
)

#: Detail paths traced from the same photo, same frame (drawing units).
_SIDE_DETAIL = {
    "glass": (
        "M345.7,144.8 C345.7,144.8 348.7,133.0 350.8,127.6 C352.9,122.3 355.2,117.3 358.4,112.9 "
        "C361.7,108.5 366.1,104.8 370.1,101.0 C374.2,97.2 378.6,92.9 382.8,90.1 "
        "C387.1,87.3 391.3,85.8 395.5,84.1 C399.7,82.4 401.4,81.5 408.1,80.0 "
        "C414.8,78.5 423.7,76.4 435.8,75.2 C447.9,73.9 470.4,72.8 480.8,72.5 "
        "C491.2,72.1 492.5,72.6 498.1,73.1 C503.8,73.6 506.7,75.1 514.5,75.7 "
        "C522.3,76.2 537.5,76.3 545.0,76.5 C552.6,76.7 552.4,76.2 559.7,76.7 "
        "C567.1,77.2 580.1,77.9 589.0,79.4 C598.0,80.9 606.0,83.9 613.3,85.9 "
        "C620.6,87.9 626.3,89.3 632.7,91.5 C639.0,93.6 647.7,96.5 651.6,98.8 "
        "C655.6,101.2 656.5,105.5 656.5,105.5 C656.5,105.5 655.6,109.9 653.7,112.5 "
        "C651.7,115.0 648.2,118.3 644.7,121.0 C641.2,123.6 638.7,126.2 632.7,128.2 "
        "C626.6,130.2 620.6,131.6 608.5,133.0 C596.3,134.4 576.1,135.5 559.7,136.8 "
        "C543.4,138.0 524.5,139.6 510.5,140.6 C496.5,141.6 490.8,142.0 475.8,142.6 "
        "C460.8,143.2 437.5,143.8 420.7,144.4 C404.0,144.9 386.2,145.4 375.2,145.8 "
        "C364.2,146.1 359.8,146.6 354.9,146.4 C349.9,146.3 345.7,144.8 345.7,144.8 Z"
    ),
    "bpillar": "M497.2,73.6 L509.5,74.3 L480.8,142.5 L468.3,142.9 L497.2,73.6 Z",
    "quarter": "M618.2,86.7 C618.2,86.7 614.3,102.7 612.3,110.3 C610.4,118.0 606.5,132.6 606.5,132.6",
    "rearglass": (
        "M690.3,96.9 C690.3,96.9 697.0,96.9 704.4,94.3 C711.8,91.6 734.6,80.9 734.6,80.9 "
        "L782.4,110.9 L766.5,128.3 C766.5,128.3 745.3,129.0 736.6,127.5 "
        "C727.9,126.0 722.2,124.3 714.5,119.2 C706.8,114.1 690.3,96.9 690.3,96.9 Z"
    ),
    "mirror": (
        "M314.4,144.8 C314.4,144.8 314.0,138.7 316.5,135.0 C319.0,131.2 324.6,125.4 329.3,122.4 "
        "C334.0,119.4 339.8,117.5 344.7,117.1 C349.5,116.8 354.9,118.0 358.4,120.2 "
        "C361.9,122.3 364.5,125.6 365.6,130.1 C366.7,134.7 365.1,147.6 365.1,147.6 "
        "C365.1,147.6 351.3,151.0 344.7,151.6 C338.0,152.2 330.2,152.4 325.2,151.3 "
        "C320.2,150.2 314.4,144.8 314.4,144.8 Z"
    ),
    "flap": (
        "M667.9,148.9 C673.6,147.8 690.7,147.7 696.3,148.8 C702.0,149.8 700.8,151.6 701.6,155.3 "
        "C702.4,159.1 702.4,167.5 701.2,171.2 C700.0,174.8 699.9,176.2 694.3,177.4 "
        "C688.8,178.5 673.3,179.0 667.9,178.1 C662.6,177.2 663.2,175.7 662.2,172.0 "
        "C661.3,168.2 661.3,159.4 662.2,155.5 C663.2,151.7 662.3,150.1 667.9,148.9 Z"
    ),
    "lamp": (
        "M714.5,152.6 C714.5,152.6 728.3,149.9 736.6,149.5 C744.9,149.0 757.2,149.1 764.5,149.7 "
        "C771.8,150.4 780.4,153.6 780.4,153.6 L780.4,168.7 C780.4,168.7 765.2,167.1 756.6,165.2 "
        "C747.9,163.3 735.6,159.5 728.6,157.4 C721.6,155.3 714.5,152.6 714.5,152.6 Z"
    ),
    "head": (
        "M63.0,200.1 C63.0,200.1 66.3,190.7 70.5,187.6 C74.7,184.6 82.0,183.1 88.5,182.1 "
        "C94.9,181.0 109.4,181.5 109.4,181.5 L110.9,190.5 C110.9,190.5 94.9,198.3 88.5,202.4 "
        "C82.0,206.5 72.0,215.1 72.0,215.1 L63.0,200.1 Z"
    ),
    "h1": (
        "M416.7,171.8 C416.7,171.8 422.2,167.7 428.3,166.6 C434.4,165.5 447.7,164.8 453.3,165.2 "
        "C458.9,165.6 461.8,169.2 461.8,169.2"
    ),
    "h2": (
        "M583.2,162.9 C583.2,162.9 588.1,158.8 593.9,157.5 C599.7,156.2 612.3,154.9 618.2,155.3 "
        "C624.0,155.6 628.8,159.5 628.8,159.5"
    ),
    "door1": (
        "M308.8,149.9 C308.8,149.9 300.0,163.8 297.4,173.3 C294.8,182.8 293.1,193.1 293.3,206.8 "
        "C293.5,220.5 296.7,243.3 298.5,255.6 C300.2,268.0 303.6,280.8 303.6,280.8"
    ),
    "door2": (
        "M478.3,143.5 C478.3,143.5 466.4,170.4 463.3,185.2 C460.3,200.1 460.2,217.8 459.8,232.9 "
        "C459.4,247.9 460.8,275.6 460.8,275.6"
    ),
    "door3": (
        "M653.7,122.1 C653.7,122.1 649.3,141.3 646.2,150.7 C643.0,160.1 637.8,171.6 634.6,178.6 "
        "C631.4,185.6 626.9,192.7 626.9,192.7"
    ),
    "sill": "M267.4,283.4 L578.3,281.9 L578.3,294.4 L267.4,297.7 L267.4,283.4 Z",
    "exhaust": (
        "M771.7,248.2 L777.3,246.1 C777.3,246.1 781.5,248.6 782.0,251.1 "
        "C782.5,253.6 780.4,260.9 780.4,260.9 L774.1,262.2 L771.7,248.2 Z"
    ),
    "shoulder": "M95.9,179.8 C95.9,179.8 182.4,163.9 215.3,158.4 C248.2,153.0 293.3,146.9 293.3,146.9",
    "clad_f": "M123.9,299.3 A81.0,81.0 0 1 1 274.1,299.3 L266.9,296.4 A73.2,73.2 0 1 0 131.1,296.4 Z",
    "clad_r": "M574.9,299.3 A81.0,81.0 0 1 1 725.1,299.3 L717.9,296.4 A73.2,73.2 0 1 0 582.1,296.4 Z",
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
