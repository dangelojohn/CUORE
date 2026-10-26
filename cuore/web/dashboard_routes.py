"""``GET /v/{vin}/dashboard`` and ``GET /api/vehicles/{vin}/dashboard``.

Both reach the assembly through :mod:`cuore.services.dashboard_bridge` (see
that module's docstring for why it exists separately from ``mes_bridge`` for
now). Page rendering reuses the vehicle-page plumbing already in
:mod:`cuore.web.routes` -- ``templates`` (via ``_page``), ``_dossier``,
``_vehicle_bar`` and ``_set_active_vehicle`` -- read-only: ``routes.py`` was
being edited concurrently by another agent when this was built, so this
module adds no page-rendering machinery of its own and takes exactly what it
needs from there by import.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import cache, codes_call, dashboard_bridge, mes_bridge, oil_level_bridge
from . import dashboard_charts
from .routes import _dossier, _page, _relative_ago, _set_active_vehicle, _vehicle_bar

#: Server-rendered page: same posture as ``cuore.web.routes.router``.
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: JSON: same posture as ``cuore.api.vehicles.router``, mounted under ``/api``.
api_router = APIRouter(tags=["dashboard"], dependencies=[Depends(require_token)])


def _dashboard(vin: str) -> dict[str, Any]:
    """The cached dashboard for a VIN, memoised the same way the dossier is."""
    return cache.get_or_build(
        ("dashboard", vin, mes_bridge.newest_mtime(vin)),
        lambda: dashboard_bridge.dashboard(vin),
    )


def _recent(timeline: list[dict[str, Any]], ledger: list[dict[str, Any]], days: int = 90):
    """Only the events and ledger rows in the last ``days`` before the newest event."""
    from datetime import datetime, timedelta

    def when(v):
        try:
            return datetime.fromisoformat(str(v).replace(" ", "T")[:19])
        except (TypeError, ValueError):
            return None

    stamps = [w for r in timeline for e in r.get("events", []) if (w := when(e.get("at")))]
    if not stamps:
        return timeline, ledger
    cutoff = max(stamps) - timedelta(days=days)
    rows = []
    for r in timeline:
        ev = [e for e in r.get("events", []) if (w := when(e.get("at"))) and w >= cutoff]
        if ev:
            rows.append({**r, "events": ev})
    led = [x for x in ledger if (w := when(x.get("at"))) and w >= cutoff]
    return rows, led


TOP_CODES = 8


def _top_code_groups(vin: str, dossier: dict[str, Any], timeline: list[dict[str, Any]]):
    """The worst ``TOP_CODES`` codes in /codes' own order (``codes_call.group_rows``:
    returned, chronic, recurring, cleared, seen-once; the open job's codes first),
    newest first inside each state; plus the total so the page can link to /codes."""
    job_codes = codes_call.job_state(vin, dossier)[0]
    rows = []
    for r in sorted(timeline, key=lambda r: str(r.get("last_seen") or ""), reverse=True):
        rows.append({**r, "dtc": r.get("code", ""), "severity": r.get("class"),
                     "in_job": codes_call.base(r.get("code", "")) in job_codes,
                     "ago": _relative_ago(r.get("last_seen")),
                     "first_ago": _relative_ago(r.get("first_seen"))})
    left = TOP_CODES
    groups = []
    for g in codes_call.group_rows(rows):
        keep = g["rows"][:left]
        left -= len(keep)
        if keep:
            groups.append({**g, "rows": keep, "shown": len(keep)})
    return groups, len(rows)


@router.get("/v/{vin}/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, vin: str) -> HTMLResponse:
    """Verdict-first: the headline numbers, then the three charts, then the tables."""
    data = _dashboard(vin)
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    charts = {
        "code_timeline": dashboard_charts.code_timeline_svg(
            data["code_timeline"], data["repairs_and_tests"]),
        "code_timeline_recent": dashboard_charts.code_timeline_svg(
            *_recent(data["code_timeline"], data["repairs_and_tests"], days=90)),
        "odometer": dashboard_charts.odometer_svg(data["odometer_series"]),
        "modules": dashboard_charts.module_bar_svg(data["modules"]),
    }
    oil = oil_level_bridge.card(vin)
    code_groups, codes_total = _top_code_groups(vin, dossier, data["code_timeline"])
    response = _page(request, "dashboard.html", vin=vin, d=data, bar=bar,
                     code_groups=code_groups, codes_total=codes_total,
                     charts=charts, tab="dashboard", oil=oil,
                     oil_error=request.query_params.get("oil_error", ""))
    _set_active_vehicle(response, vin)
    return response


@api_router.get("/vehicles/{vin}/dashboard", summary="Per-vehicle dashboard")
def dashboard_json(vin: str) -> dict[str, Any]:
    """The same assembly the page renders, as JSON."""
    return _dashboard(vin)


__all__ = ["router", "api_router"]
