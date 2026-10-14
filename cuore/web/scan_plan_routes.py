"""``GET /v/{vin}/scan-plan`` -- the owner's ten scans, status per row.

Same posture as ``cuore.web.scanlog_routes``: a thin page shell over
``cuore.services.scan_plan_bridge.build_plan``, reusing
``_dossier``/``_page``/``_set_active_vehicle``/``_vehicle_bar`` from
``cuore.web.routes`` rather than duplicating that plumbing. Read-only --
nothing here writes to the car; the Connect-to-car button on the next due
row links to the existing ``/v/{vin}/scan`` guided-scan wizard
(``cuore.web.fullscan_routes``), the same link ``_vbar.html``'s own
Connect-to-car button already uses.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import scan_plan_bridge, shop_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _bar_for(vin: str) -> dict:
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    bar["name"] = shop_bridge.resolve_vehicle_name(vin) or bar["name"]
    return bar


@router.get("/v/{vin}/scan-plan", response_class=HTMLResponse)
def scan_plan_page(request: Request, vin: str) -> HTMLResponse:
    plan = scan_plan_bridge.build_plan(vin)
    response = _page(request, "scan_plan.html", vin=vin, bar=_bar_for(vin),
                     tab="scans", plan=plan)
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
