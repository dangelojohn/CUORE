"""Adjustments page: GET /v/{vin}/adjustments and GET /v/{vin}/adjustments/{name}. Read-only; no write route exists."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import adjustments
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _render(request: Request, vin: str, name: str) -> HTMLResponse:
    dossier = _dossier(vin)
    response = _page(request, "adjustments.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="adjustments",
                     b=adjustments.board(name))
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/adjustments", response_class=HTMLResponse)
def adjustments_page(request: Request, vin: str) -> HTMLResponse:
    return _render(request, vin, "")


@router.get("/v/{vin}/adjustments/{name}", response_class=HTMLResponse)
def adjustments_card(request: Request, vin: str, name: str) -> HTMLResponse:
    return _render(request, vin, name)
