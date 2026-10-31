"""Parity board page: GET /v/{vin}/parity (filters ?state= ?group=), GET /v/{vin}/parity.csv. Read-only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from ..api.deps import require_token
from ..services import code_compare, parity
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/parity", response_class=HTMLResponse)
def parity_page(request: Request, vin: str, state: str = "", group: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    b = parity.board(state.strip() or None, group.strip() or None)
    try:
        cmp = code_compare.compare(vin)
    except Exception as exc:  # noqa: BLE001 -- the board must render without the comparison
        cmp = {"error": f"{type(exc).__name__}: {exc}"}
    response = _page(request, "parity.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="parity", b=b, cmp=cmp)
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/parity.csv")
def parity_csv(vin: str) -> Response:
    return Response(parity.to_csv().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="parity-{vin}.csv"'})
