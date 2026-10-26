"""Drift and trend tracking across visits: ``GET /v/{vin}/trends`` and
``GET /api/vehicles/{vin}/trends``.

Mount with one line in ``cuore/app.py``::

    from .web import trends_routes
    app.include_router(trends_routes.router)

(One router carries both paths; the JSON path is spelled out in full, so no ``/api`` prefix is
needed at include time.)

To embed the compact panel on another page (job, dashboard), that page's route passes
``trends=trends_routes.trends_panel_context(vin)`` and its template does
``{% include "_trends_panel.html" %}`` (the partial also reads ``vin``).

Nothing here touches the car. The maths is in :mod:`cuore.services.trends`; this module only
turns its numbers into server-side SVG sparklines (no JS, no CDN; colours are the ``--sev-*``,
``--ink*`` tokens of cuore.css, so light and dark both work) and renders the page.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional
from xml.sax.saxutils import escape as _esc

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import trends
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

W, H, PAD = 360.0, 96.0, 8.0


def _fmt(v: float, dec: int) -> str:
    return f"{v:.{dec}f}"


def sparkline(series: dict[str, Any], unit: str, dec: int) -> Optional[dict[str, Any]]:
    """{"svg", "y_top", "y_bottom", "x_left", "x_right", "caption"} for one stream, or None with no points.

    Marks carry meaning by shape and line style, not colour alone: circles = daily medians, a ring
    on the latest, a diamond where a CUSUM shift began, a dotted line = least-squares trend, a
    long-dash line = the limit. Axis words are HTML (outside the SVG) so they stay a readable size.
    """
    pts = series.get("points") or []
    if not pts:
        return None
    ds = [date.fromisoformat(p["date"]) for p in pts]
    ys = [p["value"] for p in pts]
    d0 = ds[0]
    xs = [float((d - d0).days) for d in ds]
    lim = series.get("limit") or {}
    lo, hi = lim.get("lo"), lim.get("hi")
    ymin, ymax = min(ys), max(ys)
    span = (ymax - ymin) or max(abs(ymax) * 0.05, 1e-6)
    off_scale = []
    for name, v in (("lower", lo), ("upper", hi)):
        if v is None:
            continue
        if ymin - 1.5 * span <= v <= ymax + 1.5 * span:
            ymin, ymax = min(ymin, v), max(ymax, v)
        else:
            off_scale.append((name, v))
    pad = ((ymax - ymin) or 1.0) * 0.08
    ymin, ymax = ymin - pad, ymax + pad
    xspan = (xs[-1] - xs[0]) or 1.0

    def X(x: float) -> float:
        return PAD + (x - xs[0]) / xspan * (W - 2 * PAD) if len(xs) > 1 else W / 2

    def Y(y: float) -> float:
        return PAD + (ymax - y) / (ymax - ymin) * (H - 2 * PAD)

    parts: list[str] = []
    for v, nm in ((lo, "lower limit"), (hi, "upper limit")):
        if v is not None and ymin <= v <= ymax:
            parts.append(f'<line class="tr-limit" x1="{PAD}" x2="{W - PAD}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"><title>{nm} '
                         f'{_fmt(v, dec)} {_esc(unit)}</title></line>')
    b = series.get("slope_per_day")
    if b is not None and len(ys) >= 2:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        y_at = lambda x: my + b * (x - mx)          # noqa: E731
        parts.append(f'<line class="tr-fit" x1="{X(xs[0]):.1f}" y1="{Y(y_at(xs[0])):.1f}" '
                     f'x2="{X(xs[-1]):.1f}" y2="{Y(y_at(xs[-1])):.1f}"><title>least-squares trend</title></line>')
    if len(pts) > 1:
        poly = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in zip(xs, ys))
        parts.append(f'<polyline class="tr-line" points="{poly}"/>')
    cs = series.get("cusum")
    shift_i = cs["since_index"] if cs else None
    for i, (x, y, p) in enumerate(zip(xs, ys, pts)):
        cx, cy = X(x), Y(y)
        tip = f'<title>{p["date"]}: {_fmt(y, dec)} {_esc(unit)} ({p["readings"]} reading{"s" if p["readings"] != 1 else ""})</title>'
        if shift_i is not None and i == shift_i:
            parts.append(f'<polygon class="tr-shift" points="{cx:.1f},{cy - 7:.1f} {cx + 7:.1f},{cy:.1f} '
                         f'{cx:.1f},{cy + 7:.1f} {cx - 7:.1f},{cy:.1f}">{tip}</polygon>')
        else:
            parts.append(f'<circle class="tr-dot" cx="{cx:.1f}" cy="{cy:.1f}" r="4">{tip}</circle>')
    cx, cy = X(xs[-1]), Y(ys[-1])
    parts.append(f'<circle class="tr-last" cx="{cx:.1f}" cy="{cy:.1f}" r="8"/>')
    label = (f'{series.get("stream", "")}: {len(pts)} daily point{"s" if len(pts) != 1 else ""} from {pts[0]["date"]} '
             f'to {pts[-1]["date"]}, latest {_fmt(ys[-1], dec)} {unit}')
    svg = (f'<svg class="tr-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
           f'aria-label="{_esc(label, {chr(34): "&quot;"})}"><title>{_esc(label)}</title>'
           f'<rect class="tr-bg" x="0" y="0" width="{W:.0f}" height="{H:.0f}"/>' + "".join(parts) + "</svg>")
    key = ["circle = daily median", "ring = latest"]
    if b is not None and len(ys) >= 2:
        key.append("dotted line = least-squares trend")
    if any(v is not None and ymin <= v <= ymax for v in (lo, hi)):
        key.append("long dashes = limit")
    if shift_i is not None:
        key.append("diamond = where the shift began")
    note = "; ".join(f"the {n} limit {_fmt(v, dec)} {unit} is off this scale" for n, v in off_scale)
    return {"svg": svg, "y_top": f"{_fmt(ymax, dec)} {unit}", "y_bottom": f"{_fmt(ymin, dec)} {unit}",
            "x_left": pts[0]["date"], "x_right": pts[-1]["date"],
            "caption": f"Up is {unit}; across is the day of the reading. " + ", ".join(key) + "." +
                       (f" ({note})" if note else "")}


def trends_panel_context(vin: str) -> dict[str, Any]:
    """The context object the ``_trends_panel.html`` partial needs, passed as ``trends``.

    ``trends.panel(vin)`` (cached on file state) plus, on each stream, a ``plot`` with its inline
    SVG. A copy is returned so the cached object is never mutated.
    """
    base = trends.panel(vin)
    metrics = []
    for m in base["metrics"]:
        dec = m["decimals"]
        series = []
        for s in m["series"]:
            s2 = dict(s)
            s2["plot"] = sparkline(s, m["unit"], dec) if s["n"] else None
            for k in ("first", "last", "slope_per_day", "change"):
                s2[k + "_txt"] = _fmt(s[k], dec if k != "slope_per_day" else dec + 2) if s.get(k) is not None else ""
            series.append(s2)
        metrics.append({**m, "series": series,
                        "series_with_data": [s for s in series if s["n"]],
                        "series_empty": [s for s in series if not s["n"]]})
    shown = [m for m in metrics if m["status"] != "no_data"]
    return {**base, "metrics": metrics, "metrics_shown": shown,
            "metrics_idle": [m for m in metrics if m["status"] == "no_data"]}


@router.get("/v/{vin}/trends", response_class=HTMLResponse)
def trends_page(request: Request, vin: str) -> HTMLResponse:
    """Drift across visits: one line first, then each trend with its sparkline and its working."""
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    response = _page(request, "trends.html", vin=vin, bar=bar, trends=trends_panel_context(vin), tab="trends")
    _set_active_vehicle(response, vin)
    return response


@router.get("/api/vehicles/{vin}/trends", tags=["trends"], summary="Drift and trend tracking across visits",
            include_in_schema=True)
def trends_json(vin: str) -> dict[str, Any]:
    """The same numbers the page shows (no SVG), including excluded readings with their reasons."""
    return trends.panel(vin)


__all__ = ["router", "trends_panel_context", "sparkline"]
