"""Server-side inline SVG for the /v/{vin}/systems dependency graph.

Same posture as :mod:`cuore.web.timeline_svg` (its docstring explains why):
no JS, no CDN, no charting library. Colour comes from the CSS custom
properties already in ``cuore.css`` -- the same red/amber/green/grey
severity ramp the rest of the app uses for a code's status chip -- so the
graph reads correctly in both themes without this module knowing which is
active.

Visual grammar (restated in the page's own legend, so nothing here is
colour-only):

* Node fill/stroke = that system's status, from ``correlate()``'s
  ``by_system`` rows: red active, amber cleared-but-unverified, green
  verified clean, grey stale/no data.
* Node badge = that system's open code count (a small filled circle with
  a number), omitted when zero.
* Edge *line style* carries ``depends_on`` confidence, never colour:
  solid for CONFIRMED/CORROBORATED, dashed for SINGLE-SOURCE, dotted for
  UNKNOWN. An arrowhead marks the direction (A depends on B).
* Every node and every edge carries its own ``<title>`` (hover/long-press
  text), so nothing here is readable only by colour, dash pattern or
  position.
* Nodes are plain ``<a href="#node-{key}">`` wraps -- "tapping" one is just
  an in-page anchor jump to its detail block below, no JS required. Edges
  are likewise wrapped in ``<a href="#edge-{a}-{b}">`` -- "tapping" a line
  jumps to that edge's own detail block.

Layout is a small fixed grid keyed by the systems this app already knows
about (see ``_GRID``), not force-directed -- stable across reloads and
cheap to reason about. Any system key this module has never seen (a
``systems_bridge`` taxonomy change) is placed in an overflow row below the
known grid rather than breaking the page.
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape as _esc

_SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'

NODE_W, NODE_H = 118, 46
_COL_W, _ROW_H = 160, 80
_MARGIN = 24

#: Hand-placed (col, row) for the systems most commonly implicated (the
#: ones with ``depends_on`` edges and/or real DTC history on this app's
#: test vehicle). Mes.systems' full taxonomy runs to 16 systems -- anything
#: not named here lands in a wrapped overflow grid -- see ``_positions``.
_GRID: dict[str, tuple[int, int]] = {
    "electrical_supply": (0, 0),
    "network":           (1, 0),
    "fuel":              (2, 0),
    "evap":              (3, 0),
    "ignition":          (0, 1),
    "brakes_abs":        (1, 1),
    "body_comfort":      (2, 1),
    "adas_sensors":      (3, 1),
}
#: Overflow rows (any system key outside ``_GRID``) wrap at this many
#: columns instead of running one unbroken row.
_OVERFLOW_COLS = 4

#: Status vocabulary exactly as ``mes.systems.correlate()`` emits it.
STATUS_COLOR: dict[str, str] = {
    "active":            "var(--sev-returned)",
    "cleared_unverified": "var(--sev-chronic)",
    "clean":             "var(--ok)",
    "stale":             "var(--ink-3)",
}
_STATUS_BG: dict[str, str] = {
    "active":            "var(--sev-returned-bg)",
    "cleared_unverified": "var(--sev-chronic-bg)",
    "clean":             "var(--ok-bg)",
    "stale":             "var(--surface-2)",
}
STATUS_TEXT: dict[str, str] = {
    "active": "active", "cleared_unverified": "cleared, unverified",
    "clean": "verified clean", "stale": "stale / no data",
}
#: depends_on confidence -> (dash pattern, legend label). CONFIRMED and
#: CORROBORATED both read as a plain solid line -- the distinction between
#: them is explained in each edge's own <title> and the card text, not the
#: line itself (there are only three line *styles* to go around).
_DASH: dict[str, str] = {"SINGLE-SOURCE": "8,5", "UNKNOWN": "2,4"}
CONFIDENCE_TEXT: dict[str, str] = {
    "CONFIRMED": "confirmed", "CORROBORATED": "corroborated",
    "SINGLE-SOURCE": "single source", "UNKNOWN": "unverified / unknown",
}


def _no_data_svg(message: str = "No systems data yet.") -> str:
    w, h = 400, 70
    return (
        f'<svg {_SVG_NS} viewBox="0 0 {w} {h}" width="100%" role="img" '
        f'aria-label="System dependency graph: {_esc(message)}">'
        f'<title>System dependency graph</title>'
        f'<text x="{w/2}" y="{h/2}" text-anchor="middle" dominant-baseline="middle" '
        f'fill="var(--ink-3)" font-size="13" font-family="var(--sans), sans-serif">'
        f'{_esc(message)}</text></svg>'
    )


def _positions(keys: list[str]) -> dict[str, tuple[float, float]]:
    pos: dict[str, tuple[float, float]] = {}
    max_row = max((r for _, r in _GRID.values()), default=-1)
    overflow_i = 0
    for key in keys:
        if key in _GRID:
            col, row = _GRID[key]
        else:
            col = overflow_i % _OVERFLOW_COLS
            row = max_row + 1 + overflow_i // _OVERFLOW_COLS
            overflow_i += 1
        pos[key] = (_MARGIN + col * _COL_W + NODE_W / 2, _MARGIN + row * _ROW_H + NODE_H / 2)
    return pos


def render(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """``nodes``: ``[{key, label, status, code_count}]``.
    ``edges``: ``[{a, b, confidence, why}]`` meaning *a depends_on b*."""
    if not nodes:
        return _no_data_svg()
    keys = [n["key"] for n in nodes if n.get("key")]
    pos = _positions(keys)
    if not pos:
        return _no_data_svg()
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    width = int(max(xs) + NODE_W / 2 + _MARGIN)
    height = int(max(ys) + NODE_H / 2 + _MARGIN)
    by_key = {n["key"]: n for n in nodes}

    parts: list[str] = [
        f'<svg {_SVG_NS} viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="System dependency graph, {len(nodes)} systems">',
        '<title>System dependency graph</title>',
        '<defs><marker id="sys-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" '
        'orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--ink-3)"/></marker></defs>',
    ]

    for e in edges:
        a, b = e.get("a"), e.get("b")
        if a not in pos or b not in pos:
            continue
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        conf = (e.get("confidence") or "UNKNOWN").upper()
        dash = _DASH.get(conf)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        a_label = by_key.get(a, {}).get("label", a)
        b_label = by_key.get(b, {}).get("label", b)
        title = f"{a_label} depends on {b_label} ({CONFIDENCE_TEXT.get(conf, conf.lower())})"
        if e.get("why"):
            title += f": {e['why']}"
        # Trim the line endpoints back off the node rectangles a little so
        # the arrowhead does not sit buried under the next node's fill.
        dx, dy = x2 - x1, y2 - y1
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        trim = NODE_W / 2 + 4
        x1t, y1t = x1 + dx / dist * trim, y1 + dy / dist * trim
        x2t, y2t = x2 - dx / dist * trim, y2 - dy / dist * trim
        parts.append(
            f'<a href="#edge-{_esc(a)}-{_esc(b)}">'
            f'<g><line x1="{x1t:.1f}" y1="{y1t:.1f}" x2="{x2t:.1f}" y2="{y2t:.1f}" '
            f'stroke="var(--ink-3)" stroke-width="1.6"{dash_attr} marker-end="url(#sys-arrow)"/>'
            f'<title>{_esc(title)}</title></g></a>')

    for n in nodes:
        key = n.get("key")
        if key not in pos:
            continue
        x, y = pos[key]
        status = n.get("status") or "stale"
        fill = _STATUS_BG.get(status, "var(--surface-2)")
        stroke = STATUS_COLOR.get(status, "var(--ink-3)")
        count = n.get("code_count") or 0
        label = n.get("label") or key
        title = f"{label} -- {STATUS_TEXT.get(status, status)}, {count} code(s)"
        inner = (
            f'<rect x="{x - NODE_W/2:.1f}" y="{y - NODE_H/2:.1f}" width="{NODE_W}" height="{NODE_H}" '
            f'rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11.5" '
            f'fill="var(--ink)" font-family="var(--sans), sans-serif">{_esc(label)}</text>')
        if count:
            bx, by = x + NODE_W / 2 - 10, y - NODE_H / 2 + 10
            inner += (f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="9" fill="{stroke}"/>'
                      f'<text x="{bx:.1f}" y="{by + 3.2:.1f}" text-anchor="middle" '
                      f'font-size="10" fill="var(--surface)" font-family="var(--mono), monospace">{count}</text>')
        parts.append(f'<a href="#node-{_esc(key)}"><g>{inner}<title>{_esc(title)}</title></g></a>')

    parts.append("</svg>")
    return "".join(parts)


__all__ = ["render", "STATUS_COLOR", "STATUS_TEXT", "CONFIDENCE_TEXT"]
