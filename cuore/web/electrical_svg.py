"""Server-side inline SVG for the electrical layout diagram
(``/v/{vin}/electrical``).

Same posture as :mod:`cuore.web.timeline_svg` (its docstring explains why):
no JS, no CDN, no charting library. Colour comes from the CSS custom
properties in ``cuore.css`` so the diagram reads correctly in both themes
without this module knowing which is active.

Visual grammar:

* A top-down Stelvio line-art drawing (body, tyres, mirrors, nose,
  glazing, sunroof) behind translucent zone boxes (engine bay / dash / cabin driver+passenger
  / trunk stacked, with the four wheel wells attached at the sides, and an
  "underbody" strip drawn with a dashed border below the outline -- it is
  conceptually underneath the car, not a visible compartment, so it is drawn
  separately rather than pretending to be geographically accurate).
* Each electrical element is a small node placed inside its zone's box.
  Node **fill colour** is the latest inspection condition for that element on
  this vehicle: green ok, amber loose/chafed/corroded/water, red not_found,
  grey never inspected -- the only colour channel this diagram uses, so it
  stays readable to anyone who already knows the rest of this app's chip
  colours.
* When a code's path is supplied, every node on that path gets a ring
  (``class="path-hop"``) and a sequence number, a thick connecting line
  (``class="path-hop"``) is drawn through them in order, and every other
  node is dimmed (``opacity`` on its wrapping ``<g>``) -- so the path reads
  at a glance against a busy diagram instead of needing the legend to find it.

Every text node is escaped. An empty element set still renders a small,
well-formed "no data" SVG rather than an empty or broken one.
"""

from __future__ import annotations

from typing import Any, Optional
from xml.sax.saxutils import escape as _esc

try:  # pragma: no cover -- defensive, same posture as electrical_bridge's
      # own guarded imports: a services-layer hiccup must dim the glyph,
      # never break the diagram.
    from ..services.layout_bridge import SYSTEM_COLORS, SYSTEM_LABELS
except Exception:  # noqa: BLE001
    SYSTEM_COLORS, SYSTEM_LABELS = {}, {}

_SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'
_DEFAULT_SYSTEM_COLOR = "var(--ink-3)"

#: Alternate zone names seen in the wild (``mes.electrical`` names wheel
#: wells "front_left_wheel_well" etc. and has an "unknown" zone;
#: ``electrical_svg`` draws "wheel_fl"-style boxes) folded onto this
#: module's own zone ids before the "known zone?" check below.
_ZONE_ALIASES: dict[str, str] = {
    "front_left_wheel_well": "wheel_fl",
    "front_right_wheel_well": "wheel_fr",
    "rear_left_wheel_well": "wheel_rl",
    "rear_right_wheel_well": "wheel_rr",
}

#: Known zones, in drawing/card order. ``dashed`` marks a zone that is not a
#: real visible compartment (underbody) so it gets a dashed border instead of
#: a solid one.
ZONES: list[dict[str, Any]] = [
    {"id": "engine_bay", "label": "Engine bay", "x": 50, "y": 74, "w": 220, "h": 100},
    {"id": "dash", "label": "Dash", "x": 50, "y": 174, "w": 220, "h": 42},
    {"id": "cabin_driver", "label": "Cabin (driver)", "x": 50, "y": 216, "w": 108, "h": 150},
    {"id": "cabin_passenger", "label": "Cabin (passenger)", "x": 162, "y": 216, "w": 108, "h": 150},
    {"id": "trunk", "label": "Trunk", "x": 50, "y": 366, "w": 220, "h": 80},
    {"id": "underbody", "label": "Underbody (whole underside)", "x": 50, "y": 458, "w": 220,
     "h": 50, "dashed": True},
    {"id": "wheel_fl", "label": "Wheel well (FL)", "short": "FL", "x": -44, "y": 94, "w": 86, "h": 66},
    {"id": "wheel_fr", "label": "Wheel well (FR)", "short": "FR", "x": 278, "y": 94, "w": 86, "h": 66},
    {"id": "wheel_rl", "label": "Wheel well (RL)", "short": "RL", "x": -44, "y": 366, "w": 86, "h": 66},
    {"id": "wheel_rr", "label": "Wheel well (RR)", "short": "RR", "x": 278, "y": 366, "w": 86, "h": 66},
]
_ZONE_BY_ID = {z["id"]: z for z in ZONES}
_OTHER_ZONE = {"id": "other", "label": "Other / unplaced", "x": 50, "y": 514, "w": 220, "h": 40}

_BODY_OUTLINE = {"x": 50, "y": 74, "w": 220, "h": 372}
_H_SEPARATORS = [174, 216, 366]
_V_SEPARATOR = {"x": 160, "y0": 216, "y1": 366}

#: Right half of a top-down Stelvio body outline (front at the top), traced
#: clockwise from the nose centre to the tail centre in the same frame as
#: ZONES: front arches over the FL/FR wheel wells, wider rear haunches over
#: RL/RR. Mirrored about x=160 for the left half. A recognisable drawing to
#: orient by, not a dimensioned body plan.
_BODY_HALF = [
    (160, 64), (205, 66), (240, 74), (258, 88), (266, 100), (274, 112), (277, 128),
    (274, 150), (268, 164), (268, 250), (269, 350), (274, 362), (278, 384), (275, 410),
    (268, 428), (262, 442), (240, 454), (200, 460), (160, 461),
]


def _mirror(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(320 - x, y) for x, y in pts]


def _smooth_closed(pts: list[tuple[float, float]]) -> str:
    """Closed path through the midpoints of ``pts``, each point used as a
    quadratic control -- rounds every corner without hand-placed curves."""
    n = len(pts)
    mid = [((pts[i][0] + pts[(i + 1) % n][0]) / 2, (pts[i][1] + pts[(i + 1) % n][1]) / 2)
           for i in range(n)]
    d = [f"M{mid[-1][0]:.1f},{mid[-1][1]:.1f}"]
    for i in range(n):
        d.append(f"Q{pts[i][0]:.1f},{pts[i][1]:.1f} {mid[i][0]:.1f},{mid[i][1]:.1f}")
    return " ".join(d) + " Z"


def _car_line_art() -> str:
    """Top-down Stelvio line art drawn under the zones: body, tyres, mirrors,
    headlights, the scudetto and side intakes of the trilobo nose, hood
    creases, windscreen, roof with sunroof, rear screen and tail lamps."""
    outline = _BODY_HALF + _mirror(_BODY_HALF[1:-1])[::-1]
    line = 'fill="none" stroke="var(--ink-3)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"'
    thin = 'fill="none" stroke="var(--ink-3)" stroke-width="0.9" stroke-linecap="round" opacity="0.7"'
    p = ['<g class="car-art" aria-hidden="true">']
    for x in (32, 270):  # tyres, under the arches
        for y in (104, 376):
            p.append(f'<rect x="{x}" y="{y}" width="18" height="52" rx="6" fill="var(--ink-3)" opacity="0.22"/>')
    p.append(f'<path d="{_smooth_closed(outline)}" fill="var(--surface)" stroke="var(--ink-2)" '
             f'stroke-width="1.6" stroke-linejoin="round"/>')
    for s in (1, -1):  # mirrors, either side of the A-pillars
        x0 = 160 + s * 108
        p.append(f'<path d="M{x0},180 L{x0 + s * 13},176 L{x0 + s * 14},186 L{x0},190" {line}/>')
    p.append(f'<path d="M150,64 L170,64 L160,84 Z" {line}/>')  # scudetto
    for s in (1, -1):
        p.append(f'<path d="M{160 + s * 16},68 L{160 + s * 40},70 L{160 + s * 36},78 L{160 + s * 18},76" {thin}/>')
        p.append(f'<path d="M{160 + s * 62},74 L{160 + s * 92},84 L{160 + s * 98},96 L{160 + s * 70},84" {line}/>')
        p.append(f'<path d="M{160 + s * 34},86 Q{160 + s * 40},130 {160 + s * 36},170" {thin}/>')  # hood creases
        p.append(f'<path d="M{160 + s * 74},446 L{160 + s * 98},432" {line}/>')  # tail lamps
    p.append(f'<path d="M78,178 Q160,170 242,178 L232,214 Q160,208 88,214 Z" {line}/>')  # windscreen
    p.append(f'<rect x="88" y="216" width="144" height="152" rx="16" {thin}/>')  # roof
    p.append(f'<rect x="108" y="230" width="104" height="72" rx="8" {thin} stroke-dasharray="4,3"/>')  # sunroof
    p.append(f'<path d="M90,370 Q160,376 230,370 L220,404 Q160,410 100,404 Z" {line}/>')  # rear screen
    p.append('<text x="160" y="58" text-anchor="middle" font-size="8" fill="var(--ink-3)" '
             'font-family="var(--sans), sans-serif" letter-spacing="1">FRONT</text>')
    p.append("</g>")
    return "".join(p)

#: condition -> (css colour var, legend word). Anything not in this table
#: (including ``None`` -- never inspected) uses the default below.
_COND_STYLE: dict[str, tuple[str, str]] = {
    "ok": ("var(--ok)", "ok"),
    "loose": ("var(--sev-chronic)", "loose"),
    "chafed": ("var(--sev-chronic)", "chafed"),
    "corroded": ("var(--sev-chronic)", "corroded"),
    "water": ("var(--sev-chronic)", "water intrusion"),
    "not_found": ("var(--sev-returned)", "not found"),
}
_DEFAULT_COND_STYLE = ("var(--ink-3)", "never inspected")

NODE_R = 8.0


def resolve_zone(zone: Optional[str]) -> str:
    """One zone string -> this module's own zone id, or ``"other"``.
    Shared with :mod:`cuore.web.electrical_routes` (its element-card zone
    grouping) so a card lands in the same zone bucket the diagram drew it
    in, even for an alternate zone name like ``mes.electrical``'s
    ``"front_left_wheel_well"``."""
    z = (zone or "").strip()
    z = _ZONE_ALIASES.get(z, z)
    return z if z in _ZONE_BY_ID else "other"


def _no_data_svg(message: str = "No electrical elements known for this vehicle yet.") -> str:
    w, h = 320, 90
    return (
        f'<svg {_SVG_NS} viewBox="0 0 {w} {h}" width="100%" '
        f'role="img" aria-label="Electrical layout: {_esc(message)}">'
        f'<title>Electrical layout</title>'
        f'<text x="{w/2}" y="{h/2}" text-anchor="middle" dominant-baseline="middle" '
        f'fill="var(--ink-3)" font-size="13" font-family="var(--sans), sans-serif">'
        f'{_esc(message)}</text></svg>'
    )


_ROW = 32.0       # vertical pitch between node rows inside a zone
_OX = 50          # the drawing frame is shifted right by this inside the viewBox
_MAX_LABEL = 12   # label characters drawn under a node (full text in the tooltip)


def _grid(w: float) -> tuple[float, int]:
    """(column step, columns) for a zone of width ``w``."""
    avail = max(w - 12.0, 1.0)
    step = 66.0 if avail >= 130 else 48.0
    return step, max(1, int(avail // step))


def _needed_h(n: int, box: dict[str, Any]) -> float:
    """Height a zone needs to hold ``n`` nodes plus their labels."""
    if n <= 0:
        return float(box["h"])
    _, cols = _grid(box["w"])
    rows = -(-n // cols)
    return max(float(box["h"]), 28.0 + (rows - 1) * _ROW + 30.0)


def _layout_zone_nodes(ids: list[str], box: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Grid flow of node centres inside one zone box, centred horizontally,
    wrapping to the box's width. The zone is grown (see ``_arrange``) so
    every node and its label sit inside it."""
    step, cols = _grid(box["w"])
    out: dict[str, tuple[float, float]] = {}
    for i, eid in enumerate(ids):
        col, row = i % cols, i // cols
        in_row = min(cols, len(ids) - row * cols)
        x0 = box["x"] + (box["w"] - in_row * step) / 2
        out[eid] = (x0 + col * step + step / 2, box["y"] + 28 + row * _ROW)
    return out


def _arrange(by_zone: dict[str, list[str]], other_present: bool):
    """Zones with heights grown to fit their nodes. Returns
    ``(zones, h_separators, v_separator, body_scale, total_height)``.
    Body zones stack top-down (later ones shift down when an earlier one
    grows); wheel wells hang off the engine bay / trunk tops."""
    n = lambda zid: len(by_zone.get(zid, []))  # noqa: E731
    base = {z["id"]: dict(z) for z in ZONES}
    y = float(base["engine_bay"]["y"])
    out: dict[str, dict[str, Any]] = {}
    for zid in ("engine_bay", "dash"):
        z = base[zid]; z["y"] = y; z["h"] = _needed_h(n(zid), z); y += z["h"]; out[zid] = z
    cab_h = max(_needed_h(n("cabin_driver"), base["cabin_driver"]),
                _needed_h(n("cabin_passenger"), base["cabin_passenger"]))
    for zid in ("cabin_driver", "cabin_passenger"):
        z = base[zid]; z["y"] = y; z["h"] = cab_h; out[zid] = z
    cab_top = y
    y += cab_h
    z = base["trunk"]; z["y"] = y; z["h"] = _needed_h(n("trunk"), z); out["trunk"] = z
    trunk_top, body_end = y, y + z["h"]
    seps = [out["dash"]["y"], cab_top, trunk_top]
    orig_h = 446.0 - 74.0
    scale = (body_end - 74.0) / orig_h
    bottom = body_end
    ny = body_end + 12
    z = base["underbody"]; z["y"] = ny; z["h"] = _needed_h(n("underbody"), z); out["underbody"] = z
    ny += z["h"]
    if other_present:
        z = dict(_OTHER_ZONE); z["y"] = ny + 6; z["h"] = _needed_h(n("other"), z); out["other"] = z
        ny = z["y"] + z["h"]
    for zid, anchor in (("wheel_fl", out["engine_bay"]["y"] + 20), ("wheel_fr", out["engine_bay"]["y"] + 20),
                        ("wheel_rl", trunk_top), ("wheel_rr", trunk_top)):
        z = base[zid]; z["y"] = anchor; z["h"] = _needed_h(n(zid), z); out[zid] = z
        ny = max(ny, z["y"] + z["h"])
    order = [z["id"] for z in ZONES] + (["other"] if other_present else [])
    return [out[i] for i in order], seps, (cab_top, cab_top + cab_h), scale, ny + 10


def _cond_style(condition: Optional[str]) -> tuple[str, str]:
    return _COND_STYLE.get((condition or "").lower(), _DEFAULT_COND_STYLE)


def _zone_rect(z: dict[str, Any]) -> str:
    dash = ' stroke-dasharray="5,4"' if z.get("dashed") else ""
    # Translucent so the car line art underneath stays readable.
    return (f'<rect x="{z["x"]}" y="{z["y"]}" width="{z["w"]}" height="{z["h"]}" rx="10" '
            f'fill="var(--surface-2)" fill-opacity="0.35" stroke="var(--rule)" stroke-width="1.2"{dash}/>'
            f'<text x="{z["x"] + 6}" y="{z["y"] + 13}" font-size="9.5" fill="var(--ink-3)" '
            f'font-family="var(--sans), sans-serif">{_esc(z.get("short") or z["label"])}</text>')


#: Module-reachability ring: state -> (css colour, dash array, legend word).
_MODULE_RING: dict[str, tuple[str, str, str]] = {
    "answered": ("var(--ok)", "", "answered"),
    "silent": ("var(--sev-returned)", "", "silent"),
    "unchecked": ("var(--ink-3)", "2,2", "not checked"),
}


def _glyph_safety(x: float, y: float) -> str:
    """Small warning triangle with a bang, at the node's upper left."""
    cx, cy = x - NODE_R * 0.95, y - NODE_R * 0.95
    return (f'<g class="glyph-safety"><polygon points="{cx:.1f},{cy - 4.6:.1f} {cx + 4.6:.1f},{cy + 3.4:.1f} '
            f'{cx - 4.6:.1f},{cy + 3.4:.1f}" fill="var(--sev-chronic)" stroke="var(--ink)" '
            f'stroke-width="0.8" stroke-linejoin="round"/>'
            f'<text x="{cx:.1f}" y="{cy + 2.6:.1f}" text-anchor="middle" font-size="5.5" '
            f'font-weight="700" fill="var(--ink)" font-family="var(--sans), sans-serif">!</text></g>')


def _glyph_repaired(x: float, y: float) -> str:
    """Small wrench (handle + ring head) at the node's lower right."""
    cx, cy = x + NODE_R * 0.95, y + NODE_R * 0.7
    return (f'<g class="glyph-repaired" transform="translate({cx:.1f},{cy:.1f}) rotate(-45)">'
            f'<rect x="-4.2" y="-0.9" width="8.4" height="1.8" rx="0.8" fill="var(--ink)"/>'
            f'<circle cx="-4.2" cy="0" r="2.1" fill="var(--surface)" stroke="var(--ink)" '
            f'stroke-width="1"/></g>')


def _glyph_camera(x: float, y: float) -> str:
    """Small camera (body + lens) at the node's lower left."""
    cx, cy = x - NODE_R * 0.95, y + NODE_R * 0.7
    return (f'<g class="glyph-photo"><rect x="{cx - 4:.1f}" y="{cy - 2.6:.1f}" width="8" height="5.4" '
            f'rx="1" fill="var(--surface)" stroke="var(--ink)" stroke-width="0.9"/>'
            f'<circle cx="{cx:.1f}" cy="{cy + 0.1:.1f}" r="1.5" fill="var(--ink)"/></g>')


def render(elements: dict[str, dict[str, Any]], *, conditions: Optional[dict[str, Optional[str]]] = None,
          path_ids: Optional[list[str]] = None, width: int = 420,
          safety: Optional[set[str]] = None, modules: Optional[dict[str, dict[str, Any]]] = None,
          repaired: Optional[set[str]] = None, photos: Optional[set[str]] = None,
          step: Optional[dict[str, Any]] = None, matches: Optional[set[str]] = None,
          search: Optional[dict[str, str]] = None) -> str:
    """The car-layout diagram. ``elements`` is ``layout_bridge.elements()``'s
    shape: ``{id: {kind, label, system, location: {zone, ...}, ...}}`` --
    an element's own ``system`` key (when present) draws a small coloured
    glyph dot on its node (see ``SYSTEM_COLORS``/``_ZONE_ALIASES`` above).
    ``conditions`` is ``{id: condition_or_None}`` (``None``/missing = never
    inspected). ``path_ids`` highlights one code's path, in order, when
    given.

    Optional layers, all by element id: ``safety`` (warning triangle),
    ``modules`` (``{id: {state, title}}`` reachability ring on module nodes),
    ``repaired`` (wrench), ``photos`` (camera). ``step`` is the guided
    walk-through state ``{"current": id, "done": {id: "pass"|"fail"}}`` --
    the current node is drawn strong, finished ones carry a tick/cross, and
    everything else is dimmed. ``matches`` are ids to pulse (the find box);
    ``search`` is ``{id: lowercase text}`` for the client-side filter."""
    conditions = conditions or {}
    safety, repaired, photos = safety or set(), repaired or set(), photos or set()
    modules, matches, search = modules or {}, matches or set(), search or {}
    step_current = (step or {}).get("current")
    step_done = (step or {}).get("done") or {}
    path_ids = [p for p in (path_ids or []) if p in elements]
    if not elements:
        return _no_data_svg()

    by_zone: dict[str, list[str]] = {}
    for eid, e in elements.items():
        zone = resolve_zone((e.get("location") or {}).get("zone"))
        by_zone.setdefault(zone, []).append(eid)

    other_present = bool(by_zone.get("other"))
    zones, h_seps, v_sep, body_scale, height = _arrange(by_zone, other_present)
    height = int(height + 0.999)

    centres: dict[str, tuple[float, float]] = {}
    for z in zones:
        centres.update(_layout_zone_nodes(by_zone.get(z["id"], []), z))

    parts: list[str] = [
        f'<svg {_SVG_NS} viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Electrical layout, {len(elements)} elements across '
        f'{len(zones)} zones">',
        '<title>Electrical layout</title>',
    ]

    # --- legend (top) -------------------------------------------------
    legend_entries = [
        ("var(--ok)", "ok"),
        ("var(--sev-chronic)", "loose / chafed / corroded / water"),
        ("var(--sev-returned)", "not found"),
        ("var(--ink-3)", "never inspected"),
    ]
    lx, ly = 6, 12
    for color, label in legend_entries:
        entry_w = 18 + 5.6 * len(label)
        if lx > 6 and lx + entry_w > width - 6:
            lx, ly = 6, ly + 16
        parts.append(f'<circle cx="{lx + 6}" cy="{ly}" r="5.5" fill="{color}"/>')
        parts.append(f'<text x="{lx + 16}" y="{ly + 3.5}" font-size="10" fill="var(--ink-2)" '
                     f'font-family="var(--sans), sans-serif">{_esc(label)}</text>')
        lx += entry_w + 12
    ly += 16
    parts.append(f'<line x1="6" y1="{ly}" x2="26" y2="{ly}" stroke="var(--accent)" stroke-width="3.5" '
                 f'class="path-hop"/>')
    parts.append(f'<text x="30" y="{ly + 3.5}" font-size="10" fill="var(--ink-2)" '
                 f'font-family="var(--sans), sans-serif">on this code\'s path (others dimmed)</text>')

    # --- car line art + zone separators ---------------------------------
    bo = _BODY_OUTLINE
    parts.append(f'<g transform="translate({_OX},0)">')
    parts.append(f'<g transform="translate(0,74) scale(1,{body_scale:.4f}) translate(0,-74)">'
                 + _car_line_art() + '</g>')
    for y in h_seps:
        parts.append(f'<line x1="{bo["x"]}" y1="{y}" x2="{bo["x"] + bo["w"]}" y2="{y}" '
                     f'stroke="var(--rule)" stroke-width="1"/>')
    vs = _V_SEPARATOR
    parts.append(f'<line x1="{vs["x"]}" y1="{v_sep[0]}" x2="{vs["x"]}" y2="{v_sep[1]}" '
                 f'stroke="var(--rule)" stroke-width="1"/>')

    # --- zone boxes + labels --------------------------------------------
    for z in zones:
        parts.append(_zone_rect(z))

    # --- path connector line (under the nodes) --------------------------
    if len(path_ids) >= 2:
        pts = " ".join(f"{centres[p][0]:.1f},{centres[p][1]:.1f}" for p in path_ids if p in centres)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="var(--accent)" '
                     f'stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" '
                     f'class="path-hop"/>')

    # --- nodes -----------------------------------------------------------
    path_set = set(path_ids)
    for eid, (x, y) in centres.items():
        e = elements.get(eid, {})
        label = str(e.get("label") or eid)
        condition = conditions.get(eid)
        color, cond_word = _cond_style(condition)
        on_path = eid in path_set
        if step:
            dimmed = eid != step_current and eid not in step_done
        else:
            dimmed = bool(path_set) and not on_path
        dim = ' opacity="0.35"' if dimmed else ""
        system_key = e.get("system")
        sys_color = SYSTEM_COLORS.get(system_key, _DEFAULT_SYSTEM_COLOR)
        sys_label = SYSTEM_LABELS.get(system_key, system_key)
        inner = [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{NODE_R:.1f}" fill="{color}" '
                 f'stroke="var(--surface)" stroke-width="1.5"/>']
        if system_key:
            # Small per-system glyph dot, offset to the node's upper-right --
            # a second colour channel from the condition fill, so a node's
            # system reads at a glance without disturbing the condition
            # legend. Not drawn for an element with no resolved system.
            gx, gy = x + NODE_R * 0.72, y - NODE_R * 0.72
            inner.append(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="3" fill="{sys_color}" '
                         f'stroke="var(--surface)" stroke-width="0.8"/>')
        mod = modules.get(eid)
        if mod:
            ring_color, dash, _ = _MODULE_RING.get(mod.get("state"), _MODULE_RING["unchecked"])
            da = f' stroke-dasharray="{dash}"' if dash else ""
            inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{NODE_R + 5.5:.1f}" fill="none" '
                         f'stroke="{ring_color}" stroke-width="1.8"{da} class="mod-ring mod-{_esc(str(mod.get("state")))}"/>')
        if eid in safety:
            inner.append(_glyph_safety(x, y))
        if eid in repaired:
            inner.append(_glyph_repaired(x, y))
        if eid in photos:
            inner.append(_glyph_camera(x, y))
        if eid in step_done:
            ok = step_done[eid] == "pass"
            inner.append(f'<text x="{x:.1f}" y="{y + 3.2:.1f}" text-anchor="middle" font-size="10" '
                         f'font-weight="700" fill="var(--surface)" class="step-mark" '
                         f'font-family="var(--sans), sans-serif">{"&#10003;" if ok else "&#10007;"}</text>')
        if eid == step_current:
            inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{NODE_R + 5:.1f}" fill="none" '
                         f'stroke="var(--accent)" stroke-width="3.5" class="path-hop step-current"/>')
        if on_path:
            seq = path_ids.index(eid) + 1
            inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{NODE_R + 3:.1f}" fill="none" '
                         f'stroke="var(--accent)" stroke-width="2" class="path-hop"/>')
            inner.append(f'<text x="{x:.1f}" y="{y - NODE_R - 6:.1f}" text-anchor="middle" '
                         f'font-size="9" font-weight="700" fill="var(--accent)" '
                         f'font-family="var(--mono), monospace">{seq}</text>')
        inner.append(f'<text x="{x:.1f}" y="{y + NODE_R + 10:.1f}" text-anchor="middle" '
                     f'font-size="8.6" fill="var(--ink-2)" font-family="var(--sans), sans-serif">'
                     f'{_esc(label[:_MAX_LABEL])}</text>')
        title = f"{label} -- {cond_word}" + (f" ({sys_label})" if system_key else "")
        if mod:
            title += f" | {mod.get('title')}"
        if eid in safety:
            title += " | safety warning"
        if eid in repaired:
            title += " | repaired before"
        if eid in photos:
            title += " | has photos"
        link = (f'<a href="#el-{_esc(eid)}"><title>{_esc(title)}</title>{"".join(inner)}</a>')
        cls = "el-node" + (" el-match" if eid in matches else "")
        stext = _esc(search.get(eid, ""), {'"': "&quot;"})
        parts.append(f'<g class="{cls}" data-eid="{_esc(eid, {chr(34): "&quot;"})}" '
                     f'data-search="{stext}"{dim}>{link}</g>')

    parts.append("</g></svg>")
    return "".join(parts)


__all__ = ["render", "ZONES", "NODE_R", "resolve_zone"]
