import re
p=r'C:\Users\User\mcp-servers\cuore\web\sensor_profile_svg.py'
s=open(p,encoding='utf-8').read()
a=s.index('_AXLE_F, _AXLE_R, _WHEEL_Y')
b=s.index('def _cells(')
consts=open('emit_consts.py',encoding='utf-8').read()
new='''_AXLE_F, _AXLE_R, _WHEEL_Y, _TYRE_R, _RIM_R = 199, 650, 269, 59, 44

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

'''+consts+'''

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
         f'<path d="{d["clad_f"]}" {clad}/>', f'<path d="{d["clad_r"]}" {clad}/>',
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


'''
s=s[:a]+new+s[b:]
# header comment of module mentions the old drawing numbers? update the ZONES comment line
open(p,'w',encoding='utf-8').write(s)
