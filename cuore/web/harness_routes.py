"""``GET /v/{vin}/harnesses``: the nine Mopar harness diagrams placed by area on
a top view, with route in words, ends, related fuses/sensors/modules and the
parts diagram. Data: :mod:`cuore.services.harnesses`. Read-only; never contacts the car."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/harnesses", response_class=HTMLResponse)
def harnesses_page(request: Request, vin: str) -> HTMLResponse:
    from ..services import harnesses as svc  # lazy
    dossier = _dossier(vin)
    v = svc.view(vin)
    response = _page(request, "harnesses.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="harnesses",
                     v=v, svg=svc.map_svg(v["harnesses"]), colour=svc.colour)
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
