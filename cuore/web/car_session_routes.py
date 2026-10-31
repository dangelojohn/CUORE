"""Printable car-session checklist: GET /v/{vin}/car-session. Read-only; never marks a parity row done."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import car_session
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/car-session", response_class=HTMLResponse)
def car_session_page(request: Request, vin: str) -> HTMLResponse:
    response = _page(request, "car_session.html", vin=vin, bar=_vehicle_bar(vin, _dossier(vin)),
                     tab="car-session", cs=car_session.build(vin))
    _set_active_vehicle(response, vin)
    return response
