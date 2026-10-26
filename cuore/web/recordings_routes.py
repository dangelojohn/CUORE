"""``/v/{vin}/recordings`` -- record live channels over a drive, graph, compare, export.

Pages only; all state and sampling live in :mod:`cuore.services.recordings`,
which reads the already-running live session's cache and never talks to the
car. Graphs are server-side SVG (no JS needed, no hover): one small chart per
channel with min/max/avg, all on one shared time axis; ``?vs=<id>`` overlays a
second recording (dashed) on the same axes.
"""
from __future__ import annotations

import csv
import io
from html import escape
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from markupsafe import Markup

from ..api.deps import require_token
from ..services import recordings as rec_svc
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

W, H = 720, 120
PAD_L, PAD_R, PAD_T, PAD_B = 62, 10, 8, 8
MAX_POINTS = 600


def fmt_dur(s: Optional[float]) -> str:
    s = int(round(s or 0))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def series(rec: dict[str, Any], channel: str) -> list[tuple[float, Optional[float]]]:
    return [(float(r["t"]), _num((r.get("v") or {}).get(channel))) for r in rec.get("rows", [])]


def stats(pts: list[tuple[float, Optional[float]]]) -> Optional[dict[str, float]]:
    vals = [v for _, v in pts if v is not None]
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals), "avg": sum(vals) / len(vals), "n": len(vals)}


def _g(v: float) -> str:
    return f"{v:.4g}" if abs(v) < 1000 else f"{v:.0f}"


def _thin(pts: list[tuple[float, Optional[float]]]) -> list[tuple[float, Optional[float]]]:
    if len(pts) <= MAX_POINTS:
        return pts
    step = len(pts) / MAX_POINTS
    return [pts[int(i * step)] for i in range(MAX_POINTS)]


def _ticks(tmax: float) -> list[float]:
    if tmax <= 0:
        return [0.0]
    raw = tmax / 6
    for nice in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600):
        if nice >= raw:
            break
    out, t = [], 0.0
    while t <= tmax + 1e-9:
        out.append(t)
        t += nice
    return out


def _x(t: float, tmax: float) -> float:
    return PAD_L + (t / tmax if tmax > 0 else 0) * (W - PAD_L - PAD_R)


def chart_svg(channel: str, unit: str, tmax: float,
              a: list[tuple[float, Optional[float]]], b: Optional[list[tuple[float, Optional[float]]]]) -> str:
    allv = [v for s in (a, b or []) for _, v in s if v is not None]
    if allv:
        lo, hi = min(allv), max(allv)
        if hi == lo:
            lo, hi = lo - 1, hi + 1
        padv = (hi - lo) * 0.06
        lo, hi = lo - padv, hi + padv
    else:
        lo, hi = 0.0, 1.0

    def y(v: float) -> float:
        return PAD_T + (1 - (v - lo) / (hi - lo)) * (H - PAD_T - PAD_B)

    parts = [f'<svg class="rg" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="{escape(channel)} ({escape(unit)}) over time" preserveAspectRatio="none">']
    for t in _ticks(tmax):
        xx = _x(t, tmax)
        parts.append(f'<line class="rg-grid" x1="{xx:.1f}" y1="{PAD_T}" x2="{xx:.1f}" y2="{H - PAD_B}"/>')
    parts.append(f'<text class="rg-lab" x="{PAD_L - 6}" y="{PAD_T + 14}" text-anchor="end">{escape(_g(hi))}</text>')
    parts.append(f'<text class="rg-lab" x="{PAD_L - 6}" y="{H - PAD_B - 2}" text-anchor="end">{escape(_g(lo))}</text>')
    for cls, s in (("rg-a", a), ("rg-b", b)):
        if not s:
            continue
        run: list[str] = []
        d: list[str] = []
        for t, v in _thin(s):
            if v is None:
                if run:
                    d.append("M" + " L".join(run))
                run = []
            else:
                run.append(f"{_x(t, tmax):.1f},{y(v):.1f}")
        if run:
            d.append("M" + " L".join(run))
        if d:
            parts.append(f'<path class="rg-line {cls}" d="{" ".join(d)}" fill="none"/>')
    parts.append("</svg>")
    return "".join(parts)


def axis_svg(tmax: float) -> str:
    parts = [f'<svg class="rg rg-axis" viewBox="0 0 {W} 30" role="img" aria-label="Time axis, minutes:seconds" '
             f'preserveAspectRatio="none">']
    for t in _ticks(tmax):
        xx = _x(t, tmax)
        parts.append(f'<line class="rg-tick" x1="{xx:.1f}" y1="0" x2="{xx:.1f}" y2="5"/>')
        parts.append(f'<text class="rg-lab" x="{xx:.1f}" y="24" text-anchor="middle">{escape(fmt_dur(t))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _span(rec: Optional[dict[str, Any]]) -> float:
    if not rec:
        return 0.0
    rows = rec.get("rows") or []
    return max(float(rec.get("duration_s") or 0), float(rows[-1]["t"]) if rows else 0.0)


def build_charts(a: dict[str, Any], b: Optional[dict[str, Any]]) -> dict[str, Any]:
    tmax = max(_span(a), _span(b), 0.001)
    ach = list(a.get("channels") or [])
    bch = list((b or {}).get("channels") or [])
    chans = ach + [c for c in bch if c not in ach]
    charts = []
    for c in chans:
        sa = series(a, c) if c in ach else []
        sb = series(b, c) if (b and c in bch) else None
        unit = (a.get("units") or {}).get(c) or ((b or {}).get("units") or {}).get(c) or ""
        note = ""
        if b and c not in bch:
            note = "only in this recording"
        elif b and c not in ach:
            note = "only in the compared recording"
        charts.append({"channel": c, "unit": unit, "svg": Markup(chart_svg(c, unit, tmax, sa, sb)),
                       "a": stats(sa) if sa else None, "b": stats(sb) if sb else None, "note": note})
    return {"charts": charts, "axis": Markup(axis_svg(tmax)), "tmax": tmax}


def _cell(v: Any) -> Any:
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v  # no spreadsheet formula injection from a channel name/value
    return "" if v is None else v


def csv_text(rec: dict[str, Any]) -> str:
    chans = list(rec.get("channels") or [])
    units = rec.get("units") or {}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["time_iso", "seconds"] + [_cell(f"{c} ({units[c]})" if units.get(c) else c) for c in chans])
    for r in rec.get("rows", []):
        v = r.get("v") or {}
        w.writerow([r.get("at", ""), r.get("t", "")] + [_cell(v.get(c)) for c in chans])
    return buf.getvalue()


def _tok(request: Request) -> str:
    t = request.query_params.get("token")
    return f"?token={quote(t)}" if t else ""


def _row(r: dict[str, Any]) -> dict[str, Any]:
    return {**r, "dur": fmt_dur(r.get("duration_s")), "date": (r.get("start") or "")[:19].replace("T", " ")}


@router.get("/v/{vin}/recordings", response_class=HTMLResponse)
def recordings_page(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    state = rec_svc.live_state()
    rows = [_row(r) for r in rec_svc.list_recordings(vin)]
    response = _page(request, "recordings.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="recordings",
                     state=state, rows=rows, msg=request.query_params.get("msg", ""), tok=_tok(request),
                     rate=rec_svc.DEFAULT_RATE_HZ, fmt_dur=fmt_dur)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/recordings/start")
def recordings_start(request: Request, vin: str, label: str = Form(""), channels: list[str] = Form(default=[])):
    try:
        out = rec_svc.start(vin, channels=channels, label=label.strip()[:80])
        msg = f"Recording {out['id']} started: {len(out['channels'])} channels"
    except rec_svc.RecordingError as e:
        msg = str(e)
    return RedirectResponse(f"/v/{quote(vin)}/recordings?msg={quote(msg)}" + _tok(request).replace("?", "&"),
                            status_code=303)


@router.post("/v/{vin}/recordings/stop")
def recordings_stop(request: Request, vin: str):
    out = rec_svc.stop()
    msg = f"Stopped {out['id']}: {out['rows']} samples" if out.get("stopped") else out["detail"]
    return RedirectResponse(f"/v/{quote(vin)}/recordings?msg={quote(msg)}" + _tok(request).replace("?", "&"),
                            status_code=303)


def _load_or_none(vin: str, rec_id: str) -> Optional[dict[str, Any]]:
    try:
        return rec_svc.load(vin, rec_id)
    except rec_svc.RecordingError:
        return None


@router.get("/v/{vin}/recordings/{rec_id}.csv")
def recording_csv(vin: str, rec_id: str) -> Response:
    rec = _load_or_none(vin, rec_id)
    if rec is None:
        return Response("recording not found", status_code=404, media_type="text/plain")
    return Response(csv_text(rec), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{rec["id"]}.csv"'})


@router.get("/v/{vin}/recordings/{rec_id}", response_class=HTMLResponse)
def recording_page(request: Request, vin: str, rec_id: str, vs: str = "") -> HTMLResponse:
    rec = _load_or_none(vin, rec_id)
    if rec is None:
        return HTMLResponse("recording not found", status_code=404)
    other = _load_or_none(vin, vs) if vs else None
    dossier = _dossier(vin)
    others = [_row(r) for r in rec_svc.list_recordings(vin) if r.get("id") != rec["id"]]
    response = _page(request, "recording.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="recordings",
                     rec=_row({**rec, "rows": []}), other=_row({**other, "rows": []}) if other else None,
                     others=others, tok=_tok(request), fmt_dur=fmt_dur, **build_charts(rec, other))
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
