"""``GET /v/{vin}/scans/{scan_id}/health`` and ``GET /v/{vin}/health`` -- the
scan health report, shop-floor page.

Same posture as ``cuore/web/tests_routes.py``: a second router reusing
``cuore.web.routes``'s own ``_page``/``_dossier``/``_vehicle_bar`` helpers, so
rendering stays identical to every other ``/v/{vin}`` page. Everything the
page shows comes from :mod:`cuore.services.scan_health_bridge`, the same
bridge ``GET /api/scans/{vin}/{id}/health`` calls -- the two surfaces cannot
disagree.

A missing scan is two different things on purpose: asking for a *named* scan
that does not exist is a 404 (handled by ``cuore.app``'s ``BridgeError``
handler, same as everywhere else); asking for "the latest scan" on a vehicle
with no from-car read at all is a normal page state (no scan has happened
yet), rendered 200 with that said plainly, never a 500.

Note for whoever wires up the Scans detail page (``cuore/web/scanlog.html``/
``scan.html``): a "Health report" link to ``/v/{vin}/health`` (or
``/v/{vin}/scans/{id}/health`` for a specific past scan) belongs on that
page, next to the scan's other actions -- this module only owns the report
page itself, not the Scans area's own navigation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import scan_health_bridge, shop_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _bar(vin: str) -> dict:
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    bar["name"] = shop_bridge.resolve_vehicle_name(vin) or bar["name"]
    return bar


@router.get("/v/{vin}/health", response_class=HTMLResponse)
def latest_health_page(request: Request, vin: str) -> HTMLResponse:
    """The latest scan's health report, or a plain "no scan on file" state --
    never a 500 just because this vehicle has not been scanned yet."""
    bar = _bar(vin)
    if not scan_health_bridge.has_any_scan(vin):
        response = _page(request, "scan_health.html", vin=vin, bar=bar, tab="health",
                         report=None, scan_id=None)
        _set_active_vehicle(response, vin)
        return response
    report = scan_health_bridge.build_cached(vin, None)
    response = _page(request, "scan_health.html", vin=vin, bar=bar, tab="health",
                     report=report, scan_id=report["scan_id"])
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/scans/{scan_id}/health", response_class=HTMLResponse)
def scan_health_page(request: Request, vin: str, scan_id: str) -> HTMLResponse:
    """One specific scan's health report. An unknown ``scan_id`` raises
    ``NotFound`` out of the bridge, which ``cuore.app``'s exception handler
    renders as a 404 page -- not handled here."""
    bar = _bar(vin)
    report = scan_health_bridge.build_cached(vin, scan_id)
    response = _page(request, "scan_health.html", vin=vin, bar=bar, tab="health",
                     report=report, scan_id=report["scan_id"])
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
