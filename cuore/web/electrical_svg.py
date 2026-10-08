"""Server-side inline SVG for the electrical layout diagram
(``/v/{vin}/electrical``).

Same posture as :mod:`cuore.web.timeline_svg` (its docstring explains why):
no JS, no CDN, no charting library. Colour comes from the CSS custom
properties in ``cuore.css`` so the diagram reads correctly in both themes
without this module knowing which is active.

Visual grammar:

* A simple top-down car outline (engine bay / dash / cabin driver+passenger
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
    {"id": "wheel_fl", "label": "Wheel well (FL)", "x": 6, "y": 94, "w": 38, "h": 66},
    {"id": "wheel_fr", "label": "Wheel well (FR)", "x": 276, "y": 94, "w": 38, "h": 66},
    {"id": "wheel_rl", "label": "Wheel well (RL)", "x": 6, "y": 366, "w": 38, "h": 66},
    {"id": "wheel_rr", "label": "Wheel well (RR)", "x": 276, "y": 366, "w": 38, "h": 66},
]
_ZONE_BY_ID = {z["id"]: z for z in ZONES}
_OTHER_ZONE = {"id": "other", "label": "Other / unplaced", "x": 50, "y": 514, "w": 220, "h": 40}

_BODY_OUTLINE = {"x": 50, "y": 74, "w": 220, "h": 372}
_H_SEPARATORS = [174, 216, 366]
_V_SEPARATOR = {"x": 160, "y0": 216, "y1": 366}

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


def _layout_zone_nodes(ids: list[str], box: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Simple grid flow of node centres inside one zone box, top-left down,
    wrapping to fit the box's own width. Good enough for the handful of
    elements any one zone carries -- this is a labelled-node diagram, not a
    precision schematic."""
    pad = 12.0
    avail_w = max(box["w"] - 2 * pad, 1.0)
    step = 52.0
    cols = max(1, int(avail_w // step))
    out: dict[str, tuple[float, float]] = {}
    for i, eid in enumerate(ids):
        col, row = i % cols, i // cols
        x = box["x"] + pad + col * step + step / 2
        y = box["y"] + 26 + row * 28
        out[eid] = (x, y)
    return out


def _cond_style(condition: Optional[str]) -> tuple[str, str]:
    return _COND_STYLE.get((condition or "").lower(), _DEFAULT_COND_STYLE)


def _zone_rect(z: dict[str, Any]) -> str:
    dash = ' stroke-dasharray="5,4"' if z.get("dashed") else ""
    return (f'<rect x="{z["x"]}" y="{z["y"]}" width="{z["w"]}" height="{z["h"]}" rx="10" '
            f'fill="var(--surface-2)" stroke="var(--rule)" stroke-width="1.2"{dash}/>'
            f'<text x="{z["x"] + 6}" y="{z["y"] + 13}" font-size="9.5" fill="var(--ink-3)" '
            f'font-family="var(--sans), sans-serif">{_esc(z["label"])}</text>')


def render(elements: dict[str, dict[str, Any]], *, conditions: Optional[dict[str, Optional[str]]] = None,
          path_ids: Optional[list[str]] = None, width: int = 320) -> str:
    """The car-layout diagram. ``elements`` is ``layout_bridge.elements()``'s
    shape: ``{id: {kind, label, system, location: {zone, ...}, ...}}`` --
    an element's own ``system`` key (when present) draws a small coloured
    glyph dot on its node (see ``SYSTEM_COLORS``/``_ZONE_ALIASES`` above).
    ``conditions`` is ``{id: condition_or_None}`` (``None``/missing = never
    inspected). ``path_ids`` highlights one code's path, in order, when
    given."""
    conditions = conditions or {}
    path_ids = [p for p in (path_ids or []) if p in elements]
    if not elements:
        return _no_data_svg()

    by_zone: dict[str, list[str]] = {}
    for eid, e in elements.items():
        zone = resolve_zone((e.get("location") or {}).get("zone"))
        by_zone.setdefault(zone, []).append(eid)

    other_present = bool(by_zone.get("other"))
    zones = list(ZONES) + ([_OTHER_ZONE] if other_present else [])
    height = (_OTHER_ZONE["y"] + _OTHER_ZONE["h"] if other_present
              else 458 + 50) + 10

    centres: dict[str, tuple[float, float]] = {}
    for z in zones:
        centres.update(_layout_zone_nodes(by_zone.get(z["id"], []), z))

    parts: list[str] = [
        f'<svg {_SVG_NS} viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
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
        parts.append(f'<circle cx="{lx + 6}" cy="{ly}" r="5.5" fill="{color}"/>')
        parts.append(f'<text x="{lx + 16}" y="{ly + 3.5}" font-size="10" fill="var(--ink-2)" '
                     f'font-family="var(--sans), sans-serif">{_esc(label)}</text>')
        lx += 18 + 6.0 * len(label) + 14
        if lx > width - 20:
            lx, ly = 6, ly + 16
    ly += 16
    parts.append(f'<line x1="6" y1="{ly}" x2="26" y2="{ly}" stroke="var(--accent)" stroke-width="3.5" '
                 f'class="path-hop"/>')
    parts.append(f'<text x="30" y="{ly + 3.5}" font-size="10" fill="var(--ink-2)" '
                 f'font-family="var(--sans), sans-serif">on this code\'s path (others dimmed)</text>')

    # --- car outline ---------------------------------------------------
    bo = _BODY_OUTLINE
    parts.append(f'<rect x="{bo["x"]}" y="{bo["y"]}" width="{bo["w"]}" height="{bo["h"]}" rx="20" '
                 f'fill="none" stroke="var(--ink-3)" stroke-width="1.6"/>')
    for y in _H_SEPARATORS:
        parts.append(f'<line x1="{bo["x"]}" y1="{y}" x2="{bo["x"] + bo["w"]}" y2="{y}" '
                     f'stroke="var(--rule)" stroke-width="1"/>')
    vs = _V_SEPARATOR
    parts.append(f'<line x1="{vs["x"]}" y1="{vs["y0"]}" x2="{vs["x"]}" y2="{vs["y1"]}" '
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
        dim = ' opacity="0.35"' if (path_set and not on_path) else ""
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
        if on_path:
            seq = path_ids.index(eid) + 1
            inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{NODE_R + 3:.1f}" fill="none" '
                         f'stroke="var(--accent)" stroke-width="2" class="path-hop"/>')
            inner.append(f'<text x="{x:.1f}" y="{y - NODE_R - 6:.1f}" text-anchor="middle" '
                         f'font-size="9" font-weight="700" fill="var(--accent)" '
                         f'font-family="var(--mono), monospace">{seq}</text>')
        inner.append(f'<text x="{x:.1f}" y="{y + NODE_R + 10:.1f}" text-anchor="middle" '
                     f'font-size="7.5" fill="var(--ink-2)" font-family="var(--sans), sans-serif">'
                     f'{_esc(label[:9])}</text>')
        title = f"{label} -- {cond_word}" + (f" ({sys_label})" if system_key else "")
        link = (f'<a href="#el-{_esc(eid)}"><title>{_esc(title)}</title>{"".join(inner)}</a>')
        parts.append(f'<g{dim}>{link}</g>')

    parts.append("</svg>")
    return "".join(parts)


__all__ = ["render", "ZONES", "NODE_R", "resolve_zone"]
