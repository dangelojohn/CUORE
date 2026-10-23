"""Oil level card: ``POST /v/{vin}/oil-level`` (the card's own form) and
``GET|POST /api/vehicles/{vin}/oil-level``. Readings are owner events
(fluids / oil_level) -- see :mod:`cuore.services.oil_level_bridge`. Nothing
here touches the car."""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..api.deps import require_token
from ..services import oil_level_bridge as bridge
from ..services.errors import BridgeError

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])
api_router = APIRouter(tags=["oil-level"], dependencies=[Depends(require_token)])


class OilLevelRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="ISO date; default today.")
    odometer_km: Optional[float] = None
    method: str = Field(default="dipstick", description="dipstick | measured_fill | drain_volume")
    dipstick_position_pct: Optional[float] = Field(
        default=None, description="0 = MIN mark, 100 = MAX mark; may be <0 or >100.")
    litres: Optional[float] = Field(default=None, description="Measured fill / drain volume.")
    note: str = ""


@router.post("/v/{vin}/oil-level")
async def oil_level_form(request: Request, vin: str) -> RedirectResponse:
    f = await request.form()

    def g(k: str) -> str:
        return str(f.get(k) or "").strip()

    try:
        odo = float(g("odometer_km")) if g("odometer_km") else None
        bridge.add(vin, date_=g("date") or None, odometer_km=odo,
                   method=g("method") or "dipstick",
                   dipstick_position_pct=g("dipstick_position_pct"), litres=g("litres"),
                   note=g("note"))
    except (BridgeError, ValueError) as exc:
        return RedirectResponse(f"/v/{vin}/dashboard?oil_error={quote(str(exc))}#oil-level",
                                status_code=303)
    return RedirectResponse(f"/v/{vin}/dashboard#oil-level", status_code=303)


@api_router.get("/vehicles/{vin}/oil-level", summary="Oil level card data and readings")
def oil_level_get(vin: str) -> dict[str, Any]:
    return bridge.card(vin)


@api_router.post("/vehicles/{vin}/oil-level", summary="Record one oil-level reading")
def oil_level_post(vin: str, body: OilLevelRequest) -> dict[str, Any]:
    return bridge.add(vin, date_=body.date, odometer_km=body.odometer_km, method=body.method,
                      dipstick_position_pct=body.dipstick_position_pct, litres=body.litres,
                      note=body.note)


__all__ = ["router", "api_router"]
