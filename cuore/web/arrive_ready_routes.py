"""GET /v/{vin}/arrive-ready: what to prepare before the car arrives. Read only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import arrive_ready
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/arrive-ready", response_class=HTMLResponse)
def arrive_ready_page(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    response = _page(request, "arrive_ready.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="job",
                     a=arrive_ready.build(vin))
    _set_active_vehicle(response, vin)
    return response
