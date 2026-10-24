"""``GET /v/{vin}/facts`` -- the Vehicle facts quick-view -- and ``GET /facts``
(the header link: redirects to the active vehicle's page). Read-only; nothing
here touches the car. Data: :mod:`cuore.services.vehicle_facts_bridge`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..services import vehicle_facts_bridge as bridge
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/facts")
def facts_redirect(request: Request) -> RedirectResponse:
    vin = web_routes._active_vehicle(request) or bridge.first_vin_with_facts()
    return RedirectResponse(f"/v/{vin}/facts" if vin else "/vehicles", status_code=303)


@router.get("/v/{vin}/facts", response_class=HTMLResponse)
def facts_page(request: Request, vin: str) -> HTMLResponse:
    response = web_routes._page(request, "facts.html", vin=vin, facts=bridge.load(vin),
                                tab="facts", live_strip=None)
    web_routes._set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
