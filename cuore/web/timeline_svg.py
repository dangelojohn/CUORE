"""Server-side inline SVG for the codes-vs-symptoms swimlane timeline.

Same posture as :mod:`cuore.web.dashboard_charts` (its docstring explains
why): no JS, no CDN, no charting library. Colour comes from the CSS custom
properties in ``cuore.css`` -- the ``--sev-*``/``--ok``/``--ink*`` ramp plus
the ``--fam-*`` per-family palette appended there for this page -- so the
chart reads correctly in both themes without this module knowing which is
active.

Visual grammar (shown in full in the legend, so nothing here is colour-only):

* Each code-family lane (mil/evap/network/body/chassis/engine_other) is drawn
  in that family's own colour. *State* is carried by line **style**, not
  colour, on top of that: solid = present/active, dashed = cleared but the
  gap since has not been verified clean, dotted = stale (never re-seen,
  no clear on record), thick = returned -- the sighting right after a
  dashed gap. This is derived per-lane by grouping that lane's flat event
  list by ``label`` (the only code-identity signal the contract gives a
  lane) and walking it in time order; see ``_bar_segments``.
* Markers: circle = a session's read of that code (filled = present, hollow
  = read clean); triangle = a clear, drawn with the vertical dash-dot line
  that already crosses every lane; diamond = a repair/part/actuator test
  (filled green = completed, hollow amber = failed, by keyword match on the
  event's own text -- the contract carries no separate completed/failed
  field); square = a mechanic note; a filled star = a drivability symptom,
  an amber star = a smell/refuel/warning-light symptom, a hollow green
  circle = "drives normally". Severity is still the colour-outline fallback
  (red active/amber warn/green ok/grey stale) for anything that does not
  fit one of the shapes above.
* The ``conditions`` lane is its own mini line graph rather than markers:
  fuel % as a polyline on the left scale with the 15-85% EVAP window shaded
  and out-of-window points highlighted amber, engine temperature as a
  dashed polyline on a right-hand scale. Both are read out of each event's
  free-text ``label``/``detail`` by regex -- the contract gives conditions
  no structured numeric fields.
* A thin secondary axis runs along the top: interpolated odometer when
  ``axis="time"``, interpolated dates when ``axis="odometer"`` (both linear
  across ``tl["range"]``). Light dotted month gridlines and a solid "today"
  line are drawn on the time axis only -- projecting "today" onto an
  odometer axis would be extrapolation past the data, not a reading of it.

Every text node is escaped. An empty or malformed timeline still renders a
small, well-formed "no data" SVG rather than an empty or broken one.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional
from xml.sax.saxutils import escape as _esc

_SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'

# --- shared row geometry -----------------------------------------------
# ``lane_layout()`` hands the page the same numbers so the sticky HTML label
# column (outside the horizontally-scrolling SVG) lines up with each row.
ROW_H = 26
CONDITIONS_ROW_H = 64
SEC_AXIS_Y = 12
TOP_PAD = 96       # secondary axis + the (now large) legend, wrapped to ~3 rows
AXIS_H = 28
MARGIN_L = 50      # room for the conditions lane's left (fuel %) scale
MARGIN_R = 46      # room for the conditions lane's right (temp) scale
DAY_PX = 22        # minimum px per day on the time axis before it scrolls

_FAMILY_COLOR: dict[str, str] = {
    "mil":          "var(--fam-mil)",
    "evap":         "var(--fam-evap)",
    "network":      "var(--fam-network)",
    "body":         "var(--fam-body)",
    "chassis":      "var(--fam-chassis)",
    "engine_other": "var(--fam-engine)",
}

#: fallback severity -> (shape, colour, legend label), used for any point
#: event that is not one of the special-cased shapes below.
_SEVERITY_STYLE: dict[str, tuple[str, str, str]] = {
    "active":     ("circle",  "var(--sev-returned)", "active"),
    "cleared":    ("square",  "var(--ink-3)",         "cleared"),
    "info":       ("circle",  "var(--ink-3)",         "note"),
    "symptom":    ("star",    "var(--sev-returned)",  "symptom reported"),
    "no_symptom": ("ring",    "var(--ok)",             "drives normally"),
    "work":       ("diamond", "var(--sev-cleared)",    "work done"),
    "warn":       ("diamond", "var(--sev-chronic)",    "condition (warn)"),
}
_DEFAULT_STYLE = ("ring", "var(--ink-3)", "unknown")

_FUEL_RE = re.compile(r"fuel[^0-9]{0,12}(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)
_TEMP_RE = re.compile(r"(-?\d{1,3}(?:\.\d+)?)\s*(?:deg(?:ree)?s?)?\s*°?\s*c\b", re.IGNORECASE)

_DRIVABILITY_WORDS = ("hard_start", "hard start", "rough_idle", "rough idle",
                      "hesitation", "loss_of_power", "loss of power", "noise",
                      "vibration")
_WARNING_WORDS = ("fuel_smell", "fuel smell", "hard_to_refuel", "hard to refuel",
                  "warning_message", "warning message", "mil_on", "mil on")

# --- small helpers ---------------------------------------------------------


def _parse_dt(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    s = str(ts).strip().replace(" ", "T")[:19]
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _to_float(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) else None


def _now() -> datetime:
    return datetime.now()


def _no_data_svg(message: str = "No timeline data for this vehicle yet.") -> str:
    w, h = 600, 90
    return (
        f'<svg {_SVG_NS} viewBox="0 0 {w} {h}" width="100%" '
        f'role="img" aria-label="Timeline: {_esc(message)}">'
        f'<title>Timeline</title>'
        f'<text x="{w/2}" y="{h/2}" text-anchor="middle" dominant-baseline="middle" '
        f'fill="var(--ink-3)" font-size="13" font-family="var(--sans), sans-serif">'
        f'{_esc(message)}</text></svg>'
    )


def _marker(x: float, y: float, shape: str, color: str, r: float = 5.2,
           filled: bool = True) -> str:
    if shape == "circle":
        if filled:
            return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}"/>'
        return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="none" '
                f'stroke="{color}" stroke-width="1.8"/>')
    if shape == "square":
        s = r * 1.6
        return (f'<rect x="{x - s/2:.1f}" y="{y - s/2:.1f}" width="{s:.1f}" '
                f'height="{s:.1f}" fill="{color}"/>')
    if shape == "diamond":
        s = r * 1.25
        pts = f"{x:.1f},{y-s:.1f} {x+s:.1f},{y:.1f} {x:.1f},{y+s:.1f} {x-s:.1f},{y:.1f}"
        if filled:
            return f'<polygon points="{pts}" fill="{color}"/>'
        return f'<polygon points="{pts}" fill="none" stroke="{color}" stroke-width="1.8"/>'
    if shape == "triangle":
        s = r * 1.3
        pts = f"{x:.1f},{y-s:.1f} {x-s:.1f},{y+s*0.8:.1f} {x+s:.1f},{y+s*0.8:.1f}"
        return f'<polygon points="{pts}" fill="{color}"/>'
    if shape == "star":
        return _star(x, y, r * 1.15, color)
    # ring: hollow -- "drives normally" / unknown fallback
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 0.85:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="1.8"/>')


def _star(cx: float, cy: float, r: float, color: str) -> str:
    """A filled 5-point star -- the drivability/warning symptom mark."""
    import math
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append(f"{cx + rad * math.cos(ang):.1f},{cy + rad * math.sin(ang):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{color}"/>'


def _wrap(inner: str, href: Optional[str], title: str) -> str:
    body = f"{inner}<title>{_esc(title)}</title>"
    if href:
        return f'<a href="{_esc(href)}">{body}</a>'
    return f"<g>{body}</g>"


def _symptom_shape(ev: dict[str, Any]) -> tuple[str, str, str]:
    """Which mark a 'symptoms' lane event gets: hollow green circle for
    "drives normally", filled red star for a drivability complaint, amber
    star for a smell/refuel/warning-light report. The contract's event dict
    carries no separate tag field, so this reads the same free text a human
    filed the symptom with."""
    if ev.get("severity") == "no_symptom":
        return "ring", "var(--ok)", "drives normally"
    text = f"{ev.get('label') or ''} {ev.get('detail') or ''}".lower()
    if any(w in text for w in _WARNING_WORDS):
        return "star", "var(--sev-chronic)", "symptom (smell/refuel/warning)"
    return "star", "var(--sev-returned)", "symptom (drivability)"


def _work_shape(ev: dict[str, Any]) -> tuple[str, str, str, bool]:
    """Diamond for a repair/part/actuator test: filled green = completed,
    hollow amber = failed -- by keyword match, same reason as above."""
    text = f"{ev.get('label') or ''} {ev.get('detail') or ''}".lower()
    if "fail" in text or "not complete" in text or "incomplete" in text:
        return "diamond", "var(--sev-chronic)", "repair/test (failed)", False
    return "diamond", "var(--ok)", "repair/test (completed)", True


# --- derived bar-state segments (solid/dashed/dotted/thick) ----------------

_STALE_AFTER = timedelta(days=45)


def _bar_segments(events: list[dict[str, Any]], now_dt: datetime
                  ) -> list[tuple[datetime, datetime, str, dict[str, Any]]]:
    """One lane's flat event list -> drawable ``(start, end, style, event)``
    segments. Grouped by ``label`` (the code) because that is the only
    code-identity signal a lane's events carry; an event with no label is
    its own singleton group so it still renders on its own."""
    groups: dict[Any, list[dict[str, Any]]] = {}
    for e in events:
        groups.setdefault(e.get("label") or id(e), []).append(e)

    segments: list[tuple[datetime, datetime, str, dict[str, Any]]] = []
    for evs in groups.values():
        evs = sorted(evs, key=lambda e: _parse_dt(e.get("t")) or now_dt)
        prev_was_clear = False
        for i, e in enumerate(evs):
            t0 = _parse_dt(e.get("t"))
            if t0 is None:
                continue
            t_end = _parse_dt(e.get("t_end"))
            severity = e.get("severity")
            if severity == "cleared":
                gap_start = t_end or t0
                if t_end:
                    segments.append((t0, t_end, "solid", e))
                nxt = evs[i + 1] if i + 1 < len(evs) else None
                gap_end = (_parse_dt(nxt.get("t")) if nxt else None) or now_dt
                if gap_end > gap_start:
                    segments.append((gap_start, gap_end, "dashed", e))
                prev_was_clear = True
            elif severity == "active":
                end = t_end or now_dt
                style = "thick" if prev_was_clear else "solid"
                if not t_end and (now_dt - t0) > _STALE_AFTER:
                    mid = min(t0 + timedelta(days=7), now_dt)
                    segments.append((t0, mid, style, e))
                    if now_dt > mid:
                        segments.append((mid, now_dt, "dotted", e))
                else:
                    segments.append((t0, end, style, e))
                prev_was_clear = False
            else:
                # Not a presence/clear event (e.g. a plain "info" read) --
                # left to the point-marker fallback in the caller.
                prev_was_clear = False
    return segments


_STYLE_DASH = {"solid": None, "thick": None, "dashed": "10,6", "dotted": "1.8,5"}
_STYLE_LABEL = {"solid": "active", "thick": "returned after clear",
               "dashed": "cleared (unverified)", "dotted": "stale (not seen since)"}


# --- conditions mini line-graph lane ---------------------------------------


def _conditions_series(events: list[dict[str, Any]]) -> tuple[list[tuple[datetime, float]],
                                                                list[tuple[datetime, float]]]:
    fuel: list[tuple[datetime, float]] = []
    temp: list[tuple[datetime, float]] = []
    for e in events:
        t = _parse_dt(e.get("t"))
        if t is None:
            continue
        text = f"{e.get('label') or ''} {e.get('detail') or ''}"
        if (m := _FUEL_RE.search(text)):
            try:
                fuel.append((t, float(m.group(1))))
            except ValueError:
                pass
        if (m := _TEMP_RE.search(text)):
            try:
                temp.append((t, float(m.group(1))))
            except ValueError:
                pass
    fuel.sort(key=lambda p: p[0])
    temp.sort(key=lambda p: p[0])
    return fuel, temp


def _render_conditions_row(events: list[dict[str, Any]], y_top: float, row_h: float,
                          xf, esc=_esc) -> str:
    """The conditions lane: fuel% polyline + 15-85% band on the left scale,
    engine-temp dashed polyline on a right-hand scale. Falls back to plain
    markers (via the caller) when neither series has any points."""
    fuel, temp = _conditions_series(events)
    parts: list[str] = []
    plot_top, plot_bot = y_top + 3, y_top + row_h - 3

    def fy(pct: float) -> float:
        pct = max(0.0, min(100.0, pct))
        return plot_bot - pct / 100.0 * (plot_bot - plot_top)

    if fuel:
        band_top, band_bot = fy(85), fy(15)
        parts.append(f'<rect x="{xf.margin_l:.1f}" y="{band_top:.1f}" '
                     f'width="{xf.plot_w:.1f}" height="{band_bot - band_top:.1f}" '
                     f'fill="var(--ok-bg)" opacity="0.55"><title>EVAP monitor window: '
                     f'fuel 15-85%</title></rect>')
        pts = [(xf(t), fy(v)) for t, v in fuel]
        pts = [(x, y) for x, y in pts if x is not None]
        if pts:
            d = " ".join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}' for i, (x, y) in enumerate(pts))
            parts.append(f'<path d="{d}" fill="none" stroke="var(--fam-evap)" stroke-width="1.6"/>')
        for t, v in fuel:
            x = xf(t)
            if x is None:
                continue
            out_of_band = v < 15 or v > 85
            color = "var(--sev-chronic)" if out_of_band else "var(--fam-evap)"
            parts.append(f'<circle cx="{x:.1f}" cy="{fy(v):.1f}" r="{3.2 if out_of_band else 2.4:.1f}" '
                         f'fill="{color}"><title>Fuel {v:g}%'
                         f'{" -- outside the 15-85% EVAP window" if out_of_band else ""}</title></circle>')
        parts.append(f'<text x="{xf.margin_l - 6:.1f}" y="{plot_top + 8:.1f}" text-anchor="end" '
                     f'font-size="9.5" fill="var(--fam-evap)" font-family="var(--sans), sans-serif">Fuel %</text>')

    if temp:
        tvals = [v for _, v in temp]
        tlo, thi = min(tvals + [0.0]), max(tvals + [90.0])
        if thi == tlo:
            thi = tlo + 1.0

        def ty(v: float) -> float:
            return plot_bot - (v - tlo) / (thi - tlo) * (plot_bot - plot_top)

        pts = [(xf(t), ty(v)) for t, v in temp]
        pts = [(x, y) for x, y in pts if x is not None]
        if pts:
            d = " ".join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}' for i, (x, y) in enumerate(pts))
            parts.append(f'<path d="{d}" fill="none" stroke="var(--fam-chassis)" '
                         f'stroke-width="1.4" stroke-dasharray="5,3"/>')
            for t, v in temp:
                x = xf(t)
                if x is None:
                    continue
                parts.append(f'<circle cx="{x:.1f}" cy="{ty(v):.1f}" r="2.2" fill="var(--fam-chassis)">'
                             f'<title>Engine temp {v:g} C</title></circle>')
        parts.append(f'<text x="{xf.margin_l + xf.plot_w + 6:.1f}" y="{plot_top + 8:.1f}" '
                     f'font-size="9.5" fill="var(--fam-chassis)" '
                     f'font-family="var(--sans), sans-serif">Temp C</text>')

    return "".join(parts)


# --- lane partitioning -------------------------------------------------


def _plot_lanes(tl: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (tl.get("lanes") or []) if (r.get("kind") or "bars") != "lines"
            and r.get("id") != "clears"]


def _line_lanes(tl: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (tl.get("lanes") or []) if (r.get("kind") or "") == "lines"
            or r.get("id") == "clears"]


def _row_height(lane: dict[str, Any]) -> int:
    return CONDITIONS_ROW_H if lane.get("id") == "conditions" else ROW_H


def lane_layout(tl: dict[str, Any]) -> list[dict[str, Any]]:
    """Row geometry for the sticky HTML label column: one entry per plotted
    lane, in the same top-offset/height units ``render()`` draws at."""
    rows = _plot_lanes(tl)
    out, top = [], TOP_PAD
    for r in rows:
        h = _row_height(r)
        out.append({"id": r.get("id"), "label": r.get("label") or r.get("id") or "",
                     "top": top, "height": h})
        top += h
    return out


def _event_value(ev: dict[str, Any], axis: str) -> Any:
    return ev.get("odo") if axis == "odometer" else ev.get("t")


# --- the public entry point -------------------------------------------


class _Scale:
    """A callable time/odometer -> x mapper that also carries the plot's
    own margin/width, so ``_render_conditions_row`` can draw its band and
    axis labels without a separate parameter list."""

    def __init__(self, xf, margin_l: float, plot_w: float):
        self._xf = xf
        self.margin_l = margin_l
        self.plot_w = plot_w

    def __call__(self, raw: Any) -> Optional[float]:
        return self._xf(raw)


def render(tl: dict[str, Any], axis: str = "time", width: int = 920) -> str:
    """The swimlane plot (no row labels -- see module docstring)."""
    axis = axis if axis in ("time", "odometer") else "time"
    rows = _plot_lanes(tl)
    line_rows = _line_lanes(tl)
    if not rows:
        return _no_data_svg()
    now_dt = _now()
    rng = tl.get("range") or {}

    # --- establish the axis range, and a start<->end interpolator for the
    # secondary (top) axis, which is always the *other* unit. -------------
    t_lo = _parse_dt(rng.get("start"))
    t_hi = _parse_dt(rng.get("end"))
    o_lo = _to_float(rng.get("odo_start"))
    o_hi = _to_float(rng.get("odo_end"))
    all_t = [d for d in (t_lo, t_hi) if d is not None]
    all_o = [v for v in (o_lo, o_hi) if v is not None]
    for r in rows + line_rows:
        for e in r.get("events") or []:
            for raw in (e.get("t"), e.get("t_end")):
                if (d := _parse_dt(raw)) is not None:
                    all_t.append(d)
            if (v := _to_float(e.get("odo"))) is not None:
                all_o.append(v)

    if axis == "time":
        if not all_t:
            return _no_data_svg()
        lo, hi = min(all_t), max(all_t)
        if hi == lo:
            hi = lo + timedelta(days=1)
        span = (hi - lo).total_seconds() or 1.0
        span_days = max(1.0, span / 86400.0)
        min_plot_w = span_days * DAY_PX

        def xf(raw: Any) -> Optional[float]:
            d = raw if isinstance(raw, datetime) else _parse_dt(raw)
            if d is None:
                return None
            return margin_l + (d - lo).total_seconds() / span * plot_w

        axis_vals, axis_text = [lo, lo + (hi - lo) / 2, hi], None
    else:
        if not all_o:
            return _no_data_svg("No odometer-tagged events for this vehicle yet.")
        lo, hi = min(all_o), max(all_o)
        if hi == lo:
            hi = lo + 1.0
        span = (hi - lo) or 1.0
        min_plot_w = 0.0

        def xf(raw: Any) -> Optional[float]:
            v = raw if isinstance(raw, (int, float)) else _to_float(raw)
            if v is None:
                return None
            return margin_l + (v - lo) / span * plot_w

        axis_vals, axis_text = [lo, lo + (hi - lo) / 2, hi], None

    margin_l, margin_r = MARGIN_L, MARGIN_R
    width = max(int(width), int(min_plot_w + margin_l + margin_r), 400)
    plot_w = width - margin_l - margin_r
    layout = lane_layout(tl)
    plot_top = TOP_PAD
    plot_bottom = layout[-1]["top"] + layout[-1]["height"] if layout else TOP_PAD
    height = plot_bottom + AXIS_H + 10
    scale = _Scale(xf, margin_l, plot_w)

    def _interp_odo_for_time(x_val: Any) -> Optional[float]:
        """Project a time-axis value onto the odometer secondary axis,
        linearly across the vehicle's overall range. None when the range
        does not carry both ends of both units (the odometer-axis case
        does the inverse projection inline, where it is used)."""
        if t_lo is None or t_hi is None or o_lo is None or o_hi is None or t_hi == t_lo:
            return None
        d = x_val if isinstance(x_val, datetime) else _parse_dt(x_val)
        if d is None:
            return None
        frac = (d - t_lo).total_seconds() / (t_hi - t_lo).total_seconds()
        return o_lo + frac * (o_hi - o_lo)

    parts: list[str] = [
        f'<svg {_SVG_NS} viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="Codes vs. what the driver notices, {len(rows)} lanes">',
        f'<title>Codes vs. what the driver notices</title>',
    ]

    # --- secondary axis along the top --------------------------------
    if axis == "time" and o_lo is not None and o_hi is not None and t_lo and t_hi and t_hi != t_lo:
        for val, anchor in zip((lo, lo + (hi - lo) / 2, hi), ("start", "middle", "end")):
            x = xf(val)
            km = _interp_odo_for_time(val)
            if x is None or km is None:
                continue
            parts.append(f'<text x="{x:.1f}" y="{SEC_AXIS_Y:.1f}" text-anchor="{anchor}" '
                         f'font-size="10" fill="var(--ink-3)" font-family="var(--mono), monospace">'
                         f'{km:,.0f} km</text>')
    elif axis == "odometer" and t_lo and t_hi and o_lo is not None and o_hi is not None and o_hi != o_lo:
        for val, anchor in zip((lo, lo + (hi - lo) / 2, hi), ("start", "middle", "end")):
            x = xf(val)
            if x is None:
                continue
            frac = (val - o_lo) / (o_hi - o_lo)
            d = t_lo + (t_hi - t_lo) * frac
            parts.append(f'<text x="{x:.1f}" y="{SEC_AXIS_Y:.1f}" text-anchor="{anchor}" '
                         f'font-size="10" fill="var(--ink-3)" font-family="var(--sans), sans-serif">'
                         f'{_esc(d.date().isoformat())}</text>')

    # --- month gridlines + today (time axis only) -----------------------
    if axis == "time":
        cur = lo.replace(day=1)
        if cur < lo:
            pass
        months_drawn = 0
        while cur <= hi and months_drawn < 60:
            if cur >= lo:
                x = xf(cur)
                if x is not None:
                    parts.append(f'<line x1="{x:.1f}" y1="{plot_top:.1f}" x2="{x:.1f}" '
                                 f'y2="{plot_bottom:.1f}" stroke="var(--rule-soft)" '
                                 f'stroke-width="1" stroke-dasharray="1,3"/>')
            months_drawn += 1
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        if lo <= now_dt <= hi:
            x = xf(now_dt)
            if x is not None:
                parts.append(f'<line x1="{x:.1f}" y1="{plot_top - 10:.1f}" x2="{x:.1f}" '
                             f'y2="{plot_bottom:.1f}" stroke="var(--ink)" stroke-width="1.3"/>')
                parts.append(f'<text x="{x + 3:.1f}" y="{plot_top - 2:.1f}" font-size="9.5" '
                             f'fill="var(--ink)" font-family="var(--sans), sans-serif">today</text>')

    # --- legend (every symbol, wraps across rows) ------------------------
    legend_entries: list[tuple[str, str, str, bool]] = [
        ("line-solid", "var(--ink-2)", "active", True),
        ("line-dashed", "var(--ink-2)", "cleared (unverified)", True),
        ("line-dotted", "var(--ink-2)", "stale (not seen since)", True),
        ("line-thick", "var(--ink-2)", "returned after clear", True),
        ("circle", "var(--sev-returned)", "code read (present)", True),
        ("circle", "var(--ink-3)", "code read (clean)", False),
        ("line-dashdot", "var(--ink-3)", "clear", True),
        ("diamond", "var(--ok)", "repair/test completed", True),
        ("diamond", "var(--sev-chronic)", "repair/test failed", False),
        ("square", "var(--ink-3)", "mechanic note", True),
        ("star", "var(--sev-returned)", "symptom: drivability", True),
        ("star", "var(--sev-chronic)", "symptom: smell/refuel/warning", True),
        ("ring", "var(--ok)", "drives normally", True),
    ]
    fam_used = {r.get("id") for r in rows if r.get("id") in _FAMILY_COLOR}
    for fid in fam_used:
        legend_entries.append(("square", _FAMILY_COLOR[fid], next(
            (r.get("label") for r in rows if r.get("id") == fid), fid), True))

    # Wrapped to a fixed, screen-sized width regardless of the chart's own
    # (potentially multi-thousand-pixel, for a multi-year "all" range) total
    # width -- otherwise the legend would stretch across the whole scrollable
    # canvas and never wrap within anything a person could actually see.
    legend_wrap_r = margin_l + min(width - margin_l - margin_r, 900)
    lx, ly = margin_l, 30
    for shape, color, label, filled in legend_entries:
        text = _esc(label)
        needed = 24 + 6.1 * len(label) + 14
        if lx + needed > legend_wrap_r and lx > margin_l:
            lx, ly = margin_l, ly + 15
        if shape.startswith("line-"):
            dash = {"line-solid": None, "line-dashed": "6,3", "line-dotted": "1.6,3",
                   "line-thick": None, "line-dashdot": "6,2,2,2"}[shape]
            sw = 3.4 if shape == "line-thick" else 2.0
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            parts.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{lx+16:.1f}" y2="{ly:.1f}" '
                         f'stroke="{color}" stroke-width="{sw}"{dash_attr}/>')
        else:
            parts.append(_marker(lx + 7, ly, shape, color, r=4.6, filled=filled))
        parts.append(f'<text x="{lx + 20:.1f}" y="{ly + 3.5:.1f}" font-size="10.5" '
                     f'fill="var(--ink-2)" font-family="var(--sans), sans-serif">{text}</text>')
        lx += needed

    # --- cross-cutting "clear" lines, drawn under everything else --------
    for lr in line_rows:
        for e in lr.get("events") or []:
            x = xf(_event_value(e, axis))
            if x is None:
                continue
            label = _esc(str(e.get("label") or lr.get("label") or "clear"))
            detail = _esc(str(e.get("detail") or ""))
            title = f"{label}: {detail}" if detail else label
            inner = (f'<line x1="{x:.1f}" y1="{plot_top:.1f}" x2="{x:.1f}" y2="{plot_bottom:.1f}" '
                     f'stroke="var(--ink-3)" stroke-width="1.4" stroke-dasharray="6,2,2,2" opacity="0.85"/>'
                     f'{_marker(x, plot_top - 6, "triangle", "var(--ink-3)", r=4.0)}'
                     f'<text x="{x+6:.1f}" y="{plot_top - 3:.1f}" font-size="9" fill="var(--ink-3)" '
                     f'font-family="var(--sans), sans-serif">cleared</text>')
            parts.append(_wrap(inner, e.get("href"), title))

    # --- rows -----------------------------------------------------------
    for row_meta, row in zip(layout, rows):
        y_top, row_h = row_meta["top"], row_meta["height"]
        y = y_top + row_h / 2
        lane_id = row.get("id") or ""
        kind = row.get("kind") or "bars"
        events = row.get("events") or []
        parts.append(f'<line x1="{margin_l:.1f}" y1="{y_top + row_h - 1:.1f}" '
                     f'x2="{width - margin_r:.1f}" y2="{y_top + row_h - 1:.1f}" '
                     f'stroke="var(--rule-soft)" stroke-width="1"/>')

        if lane_id == "conditions":
            parts.append(_render_conditions_row(events, y_top, row_h, scale))
            continue

        if kind == "bars":
            fam_color = _FAMILY_COLOR.get(lane_id, "var(--ink-2)")
            bar_h = row_h - 10
            drawn_points: set[int] = set()
            for (t0, t1, style, e) in _bar_segments(events, now_dt):
                x0 = xf(t0 if axis == "time" else e.get("odo"))
                x1 = xf(t1 if axis == "time" else e.get("odo"))
                if x0 is None or x1 is None:
                    continue
                dash = _STYLE_DASH.get(style)
                # Dashed/dotted read as *gaps* (a code clear not yet verified, or
                # a sighting with nothing since) so they get a visibly thinner
                # track than a real presence bar -- a full-height bar with a tiny
                # dash pattern just reads as a solid block with slits in it.
                if style in ("dashed", "dotted"):
                    sw = max(3.0, bar_h * 0.4)
                elif style == "thick":
                    sw = bar_h * 1.6
                else:
                    sw = bar_h
                if x1 - x0 < 1.5:
                    # zero-width segment -- a bare marker instead of a bar
                    filled = e.get("severity") == "active"
                    inner = _marker((x0 + x1) / 2, y, "circle", fam_color, r=5.0, filled=filled)
                else:
                    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
                    inner = (f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" '
                             f'stroke="{fam_color}" stroke-width="{sw:.1f}" '
                             f'stroke-linecap="butt"{dash_attr}/>')
                    label_text = str(e.get("label") or "")
                    if label_text and (x1 - x0) > 7 * len(label_text) + 6:
                        parts.append(f'<text x="{(x0+x1)/2:.1f}" y="{y - bar_h/2 - 3:.1f}" '
                                     f'text-anchor="middle" font-size="9.5" fill="var(--ink-2)" '
                                     f'font-family="var(--mono), monospace">{_esc(label_text)}</text>')
                    count = e.get("count")
                    if isinstance(count, (int, float)) and count:
                        parts.append(f'<text x="{x1 + 4:.1f}" y="{y + 3:.1f}" font-size="9.5" '
                                     f'fill="var(--ink-3)" font-family="var(--mono), monospace">'
                                     f'x{count:g}</text>')
                label_txt = str(e.get("label") or lane_id)
                title = f"{label_txt} -- {_STYLE_LABEL.get(style, style)}"
                if e.get("detail"):
                    title += f" ({e['detail']})"
                parts.append(_wrap(inner, e.get("href"), title))
        else:  # "points" lanes: symptoms / notes / work / anything else
            for e in events:
                x = xf(_event_value(e, axis))
                if x is None:
                    continue
                if lane_id == "symptoms":
                    shape, color, style_label = _symptom_shape(e)
                    filled = True
                elif lane_id == "work":
                    shape, color, style_label, filled = _work_shape(e)
                else:
                    shape, color, style_label = _SEVERITY_STYLE.get(
                        e.get("severity") or "", _DEFAULT_STYLE)
                    filled = True
                label = str(e.get("label") or "")
                detail = str(e.get("detail") or "")
                title = f"{label or style_label}: {detail}" if detail else (label or style_label)
                parts.append(_wrap(_marker(x, y, shape, color, filled=filled), e.get("href"), title))

    # --- bottom (primary) axis ------------------------------------------
    axis_y = plot_bottom + 18
    parts.append(f'<line x1="{margin_l:.1f}" y1="{plot_bottom:.1f}" '
                 f'x2="{width - margin_r:.1f}" y2="{plot_bottom:.1f}" stroke="var(--rule)"/>')
    if axis == "time":
        labels = [d.date().isoformat() for d in axis_vals]
    else:
        labels = [f"{v:,.0f} km" for v in axis_vals]
    for val, text, anchor in zip(axis_vals, labels, ("start", "middle", "end")):
        x = xf(val)
        if x is None:
            continue
        parts.append(f'<text x="{x:.1f}" y="{axis_y:.1f}" text-anchor="{anchor}" font-size="10" '
                     f'fill="var(--ink-3)" font-family="var(--sans), sans-serif">{_esc(text)}</text>')

    parts.append("</svg>")
    return "".join(parts)


def sparkline(occurrences: list[float], symptoms: list[float],
             width: int = 110, height: int = 26) -> str:
    """Small bar+dot chart for one correlation-table row: occurrence counts
    per period as grey bars, symptom-report counts over the same periods
    overlaid as red dots. Either list may be empty."""
    n = max(len(occurrences), len(symptoms), 1)
    occ = (list(occurrences) + [0] * n)[:n]
    sym = (list(symptoms) + [0] * n)[:n]
    max_occ = max(occ) or 1
    max_sym = max(sym) or 1
    bw = width / n
    base = height - 4
    parts = [f'<svg {_SVG_NS} viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="occurrences and symptom reports over time">'
            f'<title>Occurrences (bars) vs. symptom reports (dots) over time</title>']
    for i in range(n):
        bh = (occ[i] / max_occ) * (height - 10)
        x = i * bw + 1
        parts.append(f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{max(1.0, bw - 2):.1f}" '
                     f'height="{bh:.1f}" fill="var(--ink-3)" rx="1">'
                     f'<title>{occ[i]:g} occurrence(s)</title></rect>')
        if sym[i]:
            cy = base - (sym[i] / max_sym) * (height - 10)
            parts.append(f'<circle cx="{x + bw/2:.1f}" cy="{cy:.1f}" r="2.6" fill="var(--sev-returned)">'
                         f'<title>{sym[i]:g} symptom report(s)</title></circle>')
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["render", "lane_layout", "sparkline", "ROW_H", "CONDITIONS_ROW_H", "TOP_PAD"]
