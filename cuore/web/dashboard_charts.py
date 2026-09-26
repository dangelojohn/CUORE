"""Server-side inline SVG for the per-vehicle dashboard.

No JS, no CDN, no charting library -- these have to render on a Raspberry Pi
with no network, in an ``<img>``-free ``<svg>`` inline in the page. Colour
comes from the CSS custom properties already defined in ``cuore.css`` (the
``--sev-*`` status ramp, ``--ok``, ``--ink*``) so a chart looks right in both
the app's light and dark themes without knowing which one is active --
``currentColor`` and the ``var(...)`` references are resolved by the browser,
not by this module.

Every text node is escaped. Every generator degrades to a small, well-formed
"no data" SVG rather than an empty or malformed one, because an empty vehicle
is a real page this app has to render, not an error case.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Optional
from xml.sax.saxutils import escape as _esc

_SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'

#: status (per-event) -> (shape, colour var, label). Shape and colour both
#: carry identity, per the spec: a reader relying on either alone still gets
#: the right answer.
_STATUS_STYLE: dict[str, tuple[str, str, str]] = {
    "stored":    ("circle",   "var(--sev-chronic)",  "stored"),
    "cleared":   ("square",   "var(--sev-cleared)",  "cleared"),
    "returned":  ("triangle", "var(--sev-returned)", "returned"),
    "uncleared": ("diamond",  "var(--ink-3)",         "would not clear"),
    "absent":    ("ring",     "var(--ok)",            "absent"),
}
_DEFAULT_STYLE = ("ring", "var(--ink-3)", "unknown")


def _parse_dt(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    s = str(ts).strip().replace(" ", "T")[:19]
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _no_data_svg(title: str, message: str = "No data for this vehicle yet.") -> str:
    w, h = 600, 90
    return (
        f'<svg {_SVG_NS} viewBox="0 0 {w} {h}" width="100%" '
        f'role="img" aria-label="{_esc(title)}: {_esc(message)}">'
        f'<title>{_esc(title)}</title>'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="none"/>'
        f'<text x="{w/2}" y="{h/2}" text-anchor="middle" dominant-baseline="middle" '
        f'fill="var(--ink-3)" font-size="13" font-family="var(--sans), sans-serif">'
        f'{_esc(message)}</text></svg>'
    )


def _marker(x: float, y: float, shape: str, color: str, r: float = 5.0) -> str:
    if shape == "circle":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}"/>'
    if shape == "square":
        s = r * 1.6
        return (f'<rect x="{x - s/2:.1f}" y="{y - s/2:.1f}" width="{s:.1f}" '
                f'height="{s:.1f}" fill="{color}"/>')
    if shape == "triangle":
        s = r * 1.3
        pts = f"{x:.1f},{y-s:.1f} {x-s:.1f},{y+s*0.8:.1f} {x+s:.1f},{y+s*0.8:.1f}"
        return f'<polygon points="{pts}" fill="{color}"/>'
    if shape == "diamond":
        s = r * 1.2
        pts = f"{x:.1f},{y-s:.1f} {x+s:.1f},{y:.1f} {x:.1f},{y+s:.1f} {x-s:.1f},{y:.1f}"
        return f'<polygon points="{pts}" fill="{color}"/>'
    # ring: hollow, for absent / unknown
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 0.8:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="1.6"/>')


def _legend(items: Iterable[tuple[str, str, str]], x0: float, y0: float,
            width: float) -> tuple[str, float]:
    """A row of shape+colour+label swatches, wrapped to fit ``width``."""
    parts = []
    x, y = x0, y0
    row_h = 16
    for shape, color, label in items:
        text = _esc(label)
        needed = 20 + 7 * len(label) + 18
        if x + needed > x0 + width and x > x0:
            x = x0
            y += row_h
        parts.append(_marker(x + 6, y, shape, color, r=4.2))
        parts.append(f'<text x="{x + 16:.1f}" y="{y + 4:.1f}" font-size="11" '
                     f'fill="var(--ink-2)" font-family="var(--sans), sans-serif">{text}</text>')
        x += needed
    return "".join(parts), y + row_h


def code_timeline_svg(code_timeline: list[dict[str, Any]],
                      ledger: Optional[list[dict[str, Any]]] = None) -> str:
    """One row per code; markers by event status; dashed lines for repairs/tests."""
    ledger = ledger or []
    rows = [r for r in code_timeline if r.get("events")]
    if not rows:
        return _no_data_svg("Code timeline")

    all_dt = [d for r in rows for e in r["events"] if (d := _parse_dt(e.get("at")))]
    ledger_dt = [(d, row) for row in ledger if (d := _parse_dt(row.get("at")))]
    all_dt += [d for d, _ in ledger_dt]
    if not all_dt:
        return _no_data_svg("Code timeline")
    lo, hi = min(all_dt), max(all_dt)
    if hi == lo:
        hi = lo + timedelta(days=1)
    span = (hi - lo).total_seconds() or 1.0

    margin_l, margin_r = 150, 24
    row_h = 24
    top_pad = 48  # legend
    axis_h = 28
    width = 920
    height = top_pad + len(rows) * row_h + axis_h + 10
    plot_w = width - margin_l - margin_r

    def xf(dt: datetime) -> float:
        return margin_l + (dt - lo).total_seconds() / span * plot_w

    used_status = {e.get("status") for r in rows for e in r["events"]}
    legend_items = [(_STATUS_STYLE.get(s, _DEFAULT_STYLE)[0],
                     _STATUS_STYLE.get(s, _DEFAULT_STYLE)[1],
                     _STATUS_STYLE.get(s, _DEFAULT_STYLE)[2])
                    for s in sorted(used_status, key=lambda s: list(_STATUS_STYLE).index(s)
                                    if s in _STATUS_STYLE else 99)]
    if ledger_dt:
        legend_items.append(("line", "var(--ink-3)", "repair / test"))

    parts: list[str] = [
        f'<svg {_SVG_NS} viewBox="0 0 {width} {height}" width="100%" '
        f'role="img" aria-label="Code timeline, {len(rows)} codes">',
        f'<title>Code timeline: {len(rows)} codes, {lo.date()} to {hi.date()}</title>',
    ]

    # legend (shapes handled by _marker; the synthetic "line" entry drawn by hand)
    lx, ly = margin_l, 14
    for shape, color, label in legend_items:
        text = _esc(label)
        needed = 20 + 7 * len(label) + 18
        if lx + needed > width - margin_r and lx > margin_l:
            lx = margin_l
            ly += 16
        if shape == "line":
            parts.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{lx+12:.1f}" y2="{ly:.1f}" '
                         f'stroke="{color}" stroke-width="1.5" stroke-dasharray="3,2"/>')
        else:
            parts.append(_marker(lx + 6, ly, shape, color, r=4.2))
        parts.append(f'<text x="{lx + 16:.1f}" y="{ly + 4:.1f}" font-size="11" '
                     f'fill="var(--ink-2)" font-family="var(--sans), sans-serif">{text}</text>')
        lx += needed

    plot_top = top_pad
    plot_bottom = top_pad + len(rows) * row_h

    # ledger vertical lines (drawn under the row lines/markers)
    for dt, row in ledger_dt:
        x = xf(dt)
        kind = _esc(str(row.get("kind") or "")[:10])
        what = _esc(str(row.get("what") or ""))
        parts.append(f'<line x1="{x:.1f}" y1="{plot_top:.1f}" x2="{x:.1f}" y2="{plot_bottom:.1f}" '
                     f'stroke="var(--ink-3)" stroke-width="1.2" stroke-dasharray="3,2" opacity="0.7">'
                     f'<title>{kind}: {what} ({_esc(str(row.get("at")))})</title></line>')

    # rows
    for i, row in enumerate(rows):
        y = plot_top + i * row_h + row_h / 2
        code = _esc(str(row.get("code") or ""))
        cls = _esc(str(row.get("class") or ""))
        parts.append(f'<text x="{margin_l - 10:.1f}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="12" font-family="var(--mono), monospace" fill="var(--ink)">'
                     f'{code}</text>')
        parts.append(f'<line x1="{margin_l:.1f}" y1="{y:.1f}" x2="{width - margin_r:.1f}" y2="{y:.1f}" '
                     f'stroke="var(--rule)" stroke-width="1"/>')
        for e in row["events"]:
            dt = _parse_dt(e.get("at"))
            if dt is None:
                continue
            status = e.get("status") or ""
            shape, color, label = _STATUS_STYLE.get(status, _DEFAULT_STYLE)
            km = e.get("odometer_km")
            km_txt = f", {km:,.0f} km" if isinstance(km, (int, float)) else ""
            src = _esc(str(e.get("source") or ""))
            parts.append(f'<g>{_marker(xf(dt), y, shape, color)}'
                         f'<title>{code} {_esc(label)} on {_esc(str(e.get("at")))}{_esc(km_txt)} '
                         f'({src})</title></g>')

    # date axis: start / mid / end labels
    axis_y = plot_bottom + 18
    parts.append(f'<line x1="{margin_l:.1f}" y1="{plot_bottom:.1f}" '
                 f'x2="{width - margin_r:.1f}" y2="{plot_bottom:.1f}" stroke="var(--rule)"/>')
    for frac, anchor in ((0.0, "start"), (0.5, "middle"), (1.0, "end")):
        dt = lo + (hi - lo) * frac
        x = xf(dt)
        parts.append(f'<text x="{x:.1f}" y="{axis_y:.1f}" text-anchor="{anchor}" font-size="10" '
                     f'fill="var(--ink-3)" font-family="var(--sans), sans-serif">'
                     f'{_esc(dt.date().isoformat())}</text>')

    parts.append("</svg>")
    return "".join(parts)


def odometer_svg(odometer_series: list[dict[str, Any]]) -> str:
    """Odometer (km) over time, as a simple line-with-dots chart."""
    points = [(_parse_dt(r.get("at")), r.get("odometer_km")) for r in odometer_series]
    points = [(d, km) for d, km in points if d is not None and isinstance(km, (int, float))]
    if not points:
        return _no_data_svg("Odometer over time")
    points.sort(key=lambda p: p[0])

    width, height = 920, 220
    margin_l, margin_r, margin_t, margin_b = 70, 20, 20, 32
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    lo_d, hi_d = points[0][0], points[-1][0]
    if hi_d == lo_d:
        hi_d = lo_d + timedelta(days=1)
    span = (hi_d - lo_d).total_seconds() or 1.0
    kms = [km for _, km in points]
    lo_k, hi_k = min(kms), max(kms)
    if hi_k == lo_k:
        hi_k = lo_k + 1

    def xf(dt: datetime) -> float:
        return margin_l + (dt - lo_d).total_seconds() / span * plot_w

    def yf(km: float) -> float:
        return margin_t + plot_h - (km - lo_k) / (hi_k - lo_k) * plot_h

    coords = [(xf(d), yf(km)) for d, km in points]
    path_d = " ".join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}' for i, (x, y) in enumerate(coords))

    parts = [
        f'<svg {_SVG_NS} viewBox="0 0 {width} {height}" width="100%" '
        f'role="img" aria-label="Odometer over time, {len(points)} readings">',
        f'<title>Odometer over time: {lo_k:,.0f} to {hi_k:,.0f} km, '
        f'{lo_d.date()} to {hi_d.date()}</title>',
    ]
    # gridlines + km axis labels (min/max)
    for frac in (0.0, 0.5, 1.0):
        y = margin_t + plot_h * (1 - frac)
        km = lo_k + (hi_k - lo_k) * frac
        parts.append(f'<line x1="{margin_l:.1f}" y1="{y:.1f}" x2="{width - margin_r:.1f}" y2="{y:.1f}" '
                     f'stroke="var(--rule-soft)" stroke-width="1"/>')
        parts.append(f'<text x="{margin_l - 8:.1f}" y="{y + 3:.1f}" text-anchor="end" font-size="10" '
                     f'fill="var(--ink-3)" font-family="var(--sans), sans-serif">{km:,.0f}</text>')

    parts.append(f'<path d="{path_d}" fill="none" stroke="var(--sev-cleared)" stroke-width="2" '
                 f'stroke-linecap="round" stroke-linejoin="round"/>')
    for (x, y), (d, km) in zip(coords, points):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="var(--sev-cleared)">'
                     f'<title>{_esc(d.date().isoformat())}: {km:,.0f} km</title></circle>')

    axis_y = height - 10
    for frac, anchor in ((0.0, "start"), (0.5, "middle"), (1.0, "end")):
        dt = lo_d + (hi_d - lo_d) * frac
        x = margin_l + plot_w * frac
        parts.append(f'<text x="{x:.1f}" y="{axis_y:.1f}" text-anchor="{anchor}" font-size="10" '
                     f'fill="var(--ink-3)" font-family="var(--sans), sans-serif">'
                     f'{_esc(dt.date().isoformat())}</text>')
    parts.append("</svg>")
    return "".join(parts)


def module_bar_svg(modules: list[dict[str, Any]]) -> str:
    """Horizontal bar per module: DTC count, active-now modules called out."""
    rows = [m for m in modules if m.get("dtc_count")]
    if not rows:
        return _no_data_svg("DTCs by module")
    rows = sorted(rows, key=lambda m: -m["dtc_count"])[:16]
    max_count = max(r["dtc_count"] for r in rows) or 1

    width = 920
    row_h = 24
    margin_l, margin_r, margin_t = 170, 60, 10
    height = margin_t + len(rows) * row_h + 10
    plot_w = width - margin_l - margin_r

    parts = [
        f'<svg {_SVG_NS} viewBox="0 0 {width} {height}" width="100%" '
        f'role="img" aria-label="DTC count by module, {len(rows)} modules">',
        f'<title>DTCs by module: {len(rows)} modules</title>',
    ]
    for i, m in enumerate(rows):
        y = margin_t + i * row_h
        bar_h = row_h - 8
        w = max(2.0, m["dtc_count"] / max_count * plot_w)
        name = _esc(str(m.get("abbrev") or m.get("module") or ""))
        active = bool(m.get("active_now"))
        color = "var(--sev-returned)" if active else "var(--ink-2)"
        parts.append(f'<text x="{margin_l - 10:.1f}" y="{y + bar_h/2 + 4:.1f}" text-anchor="end" '
                     f'font-size="11" font-family="var(--mono), monospace" fill="var(--ink)">'
                     f'{name}</text>')
        title = f'{name}: {m["dtc_count"]} code(s)' + (" -- active now" if active else "")
        parts.append(f'<rect x="{margin_l:.1f}" y="{y:.1f}" width="{w:.1f}" height="{bar_h:.1f}" '
                     f'rx="2" fill="{color}"><title>{_esc(title)}</title></rect>')
        parts.append(f'<text x="{margin_l + w + 6:.1f}" y="{y + bar_h/2 + 4:.1f}" font-size="11" '
                     f'fill="var(--ink-2)" font-family="var(--sans), sans-serif">'
                     f'{m["dtc_count"]}{" (active)" if active else ""}</text>')
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["code_timeline_svg", "odometer_svg", "module_bar_svg"]
