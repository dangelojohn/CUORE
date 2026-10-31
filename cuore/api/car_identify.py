"""JSON face of Add Service -- see ``cuore.services.car_identify``.

Two lines for ``cuore/app.py`` (import next to the other ``.api`` imports, router
next to ``shop_api``):

    from .api import car_identify as car_identify_api  # noqa: E402
    app.include_router(car_identify_api.router, prefix="/api")
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..services import car_identify
from .deps import require_token

router = APIRouter(tags=["car-identify"], dependencies=[Depends(require_token)])


class IdentifyBody(BaseModel):
    vin: str = Field(default="", description="typed VIN, optional; the car's own VIN wins")
    read_car: bool = Field(default=True, description="false = decode the typed VIN only, no car contact")
    stream: bool = Field(default=False, description="true = newline-delimited JSON, one event per line")
    bus: str = ""
    confirm: bool = False


class ServiceBody(BaseModel):
    fields: dict[str, Any]
    reason: str = ""
    odometer: Optional[Any] = None
    unit: str = "km"
    technician: str = ""


@router.post("/car/identify", summary="Identify a car: read it (read-only) or decode a typed VIN")
def identify(body: IdentifyBody):
    if not body.read_car:
        dec = car_identify.decode_vin(body.vin)
        return {"events": [], "card": {"vin": dec["vin"], "fields": {
            "vin": car_identify.make_field(dec["vin"], car_identify.SRC_TYPED), **dec["fields"]},
            "validation": dec["validation"], "modules": [], "silent_modules": [], "read_only": True,
            "online_lookup": car_identify.online_lookup(dec["vin"])}}
    events = car_identify.identify_from_car(body.vin, bus=body.bus, confirm=body.confirm)
    if body.stream:
        return StreamingResponse((json.dumps(e) + "\n" for e in events),
                                 media_type="application/x-ndjson")
    return car_identify.identify_result(events)


@router.post("/car/create-service", summary="Open a service job for the identified car")
def create_service(body: ServiceBody) -> dict[str, Any]:
    return car_identify.create_service(body.fields, body.reason, body.odometer,
                                       unit=body.unit, technician=body.technician)
