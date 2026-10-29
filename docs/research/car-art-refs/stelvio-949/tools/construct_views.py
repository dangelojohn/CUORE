"""Construct the TOP and REAR views orthographically from the traced side/front views + official dimensions.
Outputs: constructed_views.json {top:{strokes, silhouette}, rear:{strokes, silhouette}} and preview2.html.
Run from the scratchpad with the project venv (PIL only)."""
import json, math, os
SCR = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(SCR, "view_measurements.json"), encoding="utf-8"))
K = 0.16  # units per mm

def f(v): return f"{v:.1f}"
def poly(pts, closed=True):
    d = "M" + " L".join(f"{f(x)},{f(y)}" for x, y in pts)
    return d + (" Z" if closed else "")
def catmull(pts, closed=False, tension=6.0):
    n = len(pts); d = [f"M{f(pts[0][0])},{f(pts[0][1])}"]
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        p1 = pts[i]; p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed else pts[min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / tension, p1[1] + (p2[1] - p0[1]) / tension)
        c2 = (p2[0] - (p3[0] - p1[0]) / tension, p2[1] - (p3[1] - p1[1]) / tension)
        d.append(f"C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(p2[0])},{f(p2[1])}")
    return " ".join(d) + (" Z" if closed else "")

# ------------------------------------------------------------------ TOP VIEW (860x400, centre y=200, nose left)
CY = 200
def top_sym_closed(half):
    """half: points (x, d) with d >= 0 offsets from the centre line, ordered nose->tail; returns closed outline."""
    up = [(x, CY - d) for x, d in half]
    down = [(x, CY + d) for x, d in reversed(half)]
    return up + down

W_BODY = 1903 * K / 2            # 152.2
W_MIRROR = 2082 * K / 2          # 166.6 (blueprint mirrors; official 2163 incl. mirrors would be 173)
TRACK_F, TRACK_R = 1613 * K / 2, 1653 * K / 2
TYRE_W, TYRE_R = 296 * K, 59

body_half = [(61, 0), (62, 40), (66, 78), (74, 108), (88, 128), (108, 141), (134, 149), (165, 152.2), (300, 152.2),
             (600, 152.2), (735, 151.5), (768, 149), (790, 142), (803, 130), (809, 110), (811.5, 80), (811.5, 40), (811.5, 0)]
top_outline = catmull(top_sym_closed(body_half), closed=True)

strokes = []
strokes.append(top_outline)
# bonnet: leading edge, side seams to the A-pillar base (x=276), cowl line
bonnet_half = [(74, 0), (76, 60), (84, 100), (100, 124), (143, 132), (276, 124)]
strokes.append(catmull([(x, CY - d) for x, d in bonnet_half]))
strokes.append(catmull([(x, CY + d) for x, d in bonnet_half]))
strokes.append(poly([(276, CY - 124), (276, CY + 124)], closed=False))          # cowl / windscreen base
# windscreen: base x=276 (+-118), top x=470 (+-86); roof outline +-93 from 470 to 632; rear glass to 720 (+-100)
strokes.append(poly([(276, CY - 118), (470, CY - 86), (470, CY + 86), (276, CY + 118)]))
strokes.append(poly([(470, CY - 93), (632, CY - 93), (632, CY + 93), (470, CY + 93)]))
strokes.append(poly([(632, CY - 93), (720, CY - 100), (720, CY + 100), (632, CY + 93)]))
strokes.append(poly([(720, CY - 100), (720, CY + 100)], closed=False))        # spoiler trailing edge
# roof rails and antenna fin
for s in (-1, 1):
    strokes.append(poly([(478, CY + s * 82), (704, CY + s * 82)], closed=False))
strokes.append(poly([(648, CY), (656, CY - 4), (690, CY - 2), (690, CY + 2), (656, CY + 4)]))
# beltline (door tops) and door shut lines
for s in (-1, 1):
    strokes.append(catmull([(290, CY + s * 128), (330, CY + s * 136), (480, CY + s * 140), (650, CY + s * 140), (705, CY + s * 136)]))
    for x in (300, 485, 645):
        strokes.append(poly([(x, CY + s * 93), (x, CY + s * 152)], closed=False))
# mirrors
for s in (-1, 1):
    strokes.append(poly([(326, CY + s * 140), (322, CY + s * 150), (330, CY + s * W_MIRROR), (356, CY + s * W_MIRROR), (360, CY + s * 150), (356, CY + s * 140)]))
# lamps
for s in (-1, 1):
    strokes.append(poly([(74, CY + s * 100), (84, CY + s * 118), (104, CY + s * 134), (143, CY + s * 150), (143, CY + s * 142), (108, CY + s * 128), (88, CY + s * 112), (76, CY + s * 96)]))
    strokes.append(poly([(748, CY + s * 150), (790, CY + s * 141), (806, CY + s * 122), (809, CY + s * 108), (803, CY + s * 114), (792, CY + s * 132), (748, CY + s * 143)]))
# wheels (plan): rounded rectangles at the tracks; the part under the body stays visible as a thin outline
def rrect(cx, cy, w, h, r=6):
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    return (f"M{f(x0 + r)},{f(y0)} L{f(x1 - r)},{f(y0)} Q{f(x1)},{f(y0)} {f(x1)},{f(y0 + r)} L{f(x1)},{f(y1 - r)} "
            f"Q{f(x1)},{f(y1)} {f(x1 - r)},{f(y1)} L{f(x0 + r)},{f(y1)} Q{f(x0)},{f(y1)} {f(x0)},{f(y1 - r)} "
            f"L{f(x0)},{f(y0 + r)} Q{f(x0)},{f(y0)} {f(x0 + r)},{f(y0)} Z")
wheel_strokes = []
for cx, tr in ((199, TRACK_F), (650, TRACK_R)):
    for s in (-1, 1):
        wheel_strokes.append(rrect(cx, CY + s * tr, 2 * TYRE_R, TYRE_W))
top = {"strokes": " ".join(strokes), "wheels": " ".join(wheel_strokes), "silhouette": top_outline,
       "method": "constructed orthographically: x positions from the side-view trace (nose 61, headlamps 73-143, A-pillar base 276, windscreen top 470, B-pillar 485, rear glass start 632, spoiler edge 720, tail 811), widths from the front-view trace (body 1903 mm, mirrors 2082 mm, roof 917 mm at rail level, windscreen 1073/1475 mm) and the official tracks 1613/1653 mm"}

# ------------------------------------------------------------------ REAR VIEW (400x360, centre x=200, ground 328)
S = M["front"]["scale_units_per_px"]; CX = M["front"]["centre_px"]; TB = M["front"]["tyre_bottom_y"]
def ux(px): return 200 + (px - CX) * S
def uy(py): return 328 - (TB - py) * S
prof = M["front"]["silhouette_profile"]
# envelope: average the two sides for symmetry, then mirror
env = []
for r in prof:
    half = (ux(r["right"]) - ux(r["left"])) / 2
    env.append((uy(r["y"]), half))
env.sort()
right = [(200 + h, y) for y, h in env]
left = [(200 - h, y) for y, h in reversed(env)]
# close over the roof: top of profile is the roof (first entry y smallest)
rear_outline = catmull(right + left, closed=True, tension=8.0)
rs = [rear_outline]
# spoiler line and rear glass (heights from the side-view tail profile: spoiler edge y=77, glass bottom y=126)
rs.append(poly([(200 - 96, 77), (200 + 96, 77)], closed=False))
rs.append(catmull([(200 - 88, 80), (200 + 88, 80), (200 + 118, 126), (200 - 118, 126)], closed=True, tension=10))
rs.append(catmull([(200 - 60, 108), (200 - 20, 114), (200 + 30, 114)], closed=False))     # wiper
# tail lamps (y 130-172), pointed toward the centre, outer edge on the body
for s in (-1, 1):
    rs.append(catmull([(200 + s * 50, 141), (200 + s * 100, 132), (200 + s * 146, 133), (200 + s * 150, 150), (200 + s * 148, 164),
                       (200 + s * 104, 166), (200 + s * 72, 154)], closed=True, tension=7))
# badge, tailgate lower edge, licence plate recess and plate
rs.append(f"M{f(193)},{f(150)} a7,7 0 1 0 14,0 a7,7 0 1 0 -14,0")
rs.append(catmull([(200 - 146, 232), (200 - 60, 236), (200 + 60, 236), (200 + 146, 232)], closed=False))
rs.append(catmull([(200 - 72, 190), (200 - 40, 184), (200 + 40, 184), (200 + 72, 190), (200 + 70, 232), (200 - 70, 232)], closed=True, tension=10))
rs.append(poly([(200 - 36, 194), (200 + 36, 194), (200 + 36, 226), (200 - 36, 226)]))
# bumper: diffuser band and exhaust tips, reflectors
rs.append(catmull([(200 - 150, 258), (200 - 100, 262), (200, 264), (200 + 100, 262), (200 + 150, 258)], closed=False))
rs.append(catmull([(200 - 120, 284), (200 - 60, 288), (200 + 60, 288), (200 + 120, 284)], closed=False))
for s in (-1, 1):
    cx = 200 + s * 86
    rs.append(f"M{f(cx - 11)},{f(272)} a11,11 0 1 0 22,0 a11,11 0 1 0 -22,0")
    rs.append(f"M{f(cx - 7)},{f(272)} a7,7 0 1 0 14,0 a7,7 0 1 0 -14,0")
    rs.append(poly([(200 + s * 120, 262), (200 + s * 142, 262), (200 + s * 142, 268), (200 + s * 120, 268)]))
rear = {"strokes": " ".join(rs), "silhouette": rear_outline,
        "method": "constructed orthographically: silhouette = the front-view trace's envelope mirrored (the outer envelope is the same from both ends); feature heights from the side-view trace (spoiler edge y=77, glass bottom 126, lamps 130-172, bumper top 232, diffuser 258-288); widths from the CC BY-SA rear reference photo (docs/research/car-art-refs/stelvio-949/)"}

json.dump({"top": top, "rear": rear}, open(os.path.join(SCR, "constructed_views.json"), "w"), indent=0)
CSS = ":root{--ink:#1b1f23;--ink-2:#3a4248;--ink-3:#7d888f;--surface:#fff;--surface-2:#f1f3f4;--rule:#c9cfd3}body{margin:0;padding:8px;background:#fff;font-family:system-ui}svg{display:block;border:1px solid #ddd;margin-bottom:12px}"
ink = 'fill="none" stroke="#1b1f23" stroke-width="1.1" stroke-linejoin="round" stroke-linecap="round"'
html = f"""<!doctype html><html><head><meta charset="utf-8"><title>constructed</title><style>{CSS}</style></head><body>
<b>Top 860x400</b><svg viewBox="0 0 860 400" width="1240"><path d="{top['silhouette']}" fill="#eef3fa"/><path d="{top['wheels']}" fill="#dde3ea" stroke="#7d888f" stroke-width="0.9"/><path d="{top['strokes']}" {ink}/>
<line x1="199" y1="20" x2="199" y2="380" stroke="#0a0" stroke-width="0.5"/><line x1="650" y1="20" x2="650" y2="380" stroke="#0a0" stroke-width="0.5"/><line x1="20" y1="200" x2="840" y2="200" stroke="#0a0" stroke-width="0.5" stroke-dasharray="4 4"/></svg>
<b>Rear 400x360</b><svg viewBox="0 0 400 360" width="560"><path d="{rear['silhouette']}" fill="#eef3fa"/><path d="{rear['strokes']}" {ink}/><line x1="16" y1="328" x2="384" y2="328" stroke="#c9cfd3"/><line x1="200" y1="40" x2="200" y2="340" stroke="#0a0" stroke-width="0.5" stroke-dasharray="4 4"/></svg>
</body></html>"""
open(os.path.join(SCR, "preview2.html"), "w", encoding="utf-8").write(html)
print("ok top strokes", len(top["strokes"]), "rear strokes", len(rear["strokes"]), "env pts", len(env))
