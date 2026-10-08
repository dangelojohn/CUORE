"""``/api/electrical*``: electrical elements, per-DTC electrical paths, and
vehicle inspection records, fed by :mod:`cuore.services.electrical_bridge`
(the only module that imports :mod:`mes.electrical`/
:mod:`mes.electrical_inspections` -- see that module's docstring).

Not registered on the app here -- ``app.py`` is excluded from this pass.
The lines needed there (next to the other ``api`` router includes):

    ``from .api import electrical as electrical_api``
    ``app.include_router(electrical_api.router, prefix="/api")``
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import electrical_bridge
from ..services.errors import NotFound
from .deps import require_token

router = APIRouter(tags=["electrical"], dependencies=[Depends(require_token)])


class InspectionRequest(BaseModel):
    """One technician-entered electrical inspection finding, for recording.

    ``element`` is an id from ``mes.electrical.ELEMENTS`` (e.g. "xy201",
    "g003a", "f82", "esim_connector"); any string is accepted so a
    not-yet-catalogued element can still be logged. ``condition`` is one
    of ``mes.electrical_inspections.CONDITIONS``.
    """

    element: str = Field(..., description="e.g. xy201, g003a, f82, esim_connector")
    condition: str = Field(..., description="ok | corroded | chafed | loose | "
                                            "water | repaired | replaced | not_found")
    by: str = "technician"
    note: str = ""
    media_ids: list[str] = Field(default_factory=list)


@router.get("/electrical/elements", summary="Every electrical element known")
def list_elements() -> dict[str, Any]:
    rows = electrical_bridge.list_elements()
    return {"elements": rows, "count": len(rows)}


@router.get("/electrical/elements/{element_id}", summary="One electrical element by id")
def get_element(element_id: str) -> dict[str, Any]:
    row = electrical_bridge.get_element(element_id)
    if row is None:
        raise NotFound(f"no electrical element known by id {element_id!r}")
    return row


@router.get("/electrical/path/{code}", summary="Electrical path for a DTC")
def path_for_code(code: str) -> dict[str, Any]:
    return electrical_bridge.path_for_code(code)


@router.get("/vehicles/{vin}/electrical/inspections",
            summary="Electrical inspection history for this vehicle")
def list_inspections(vin: str, element: str = "") -> dict[str, Any]:
    rows = electrical_bridge.list_inspections(vin, element=element)
    return {"vin": vin, "element": element or None, "count": len(rows),
            "inspections": rows}


@router.post("/vehicles/{vin}/electrical/inspections",
             summary="Record an electrical inspection finding")
def add_inspection(vin: str, body: InspectionRequest) -> dict[str, Any]:
    return electrical_bridge.add_inspection(
        vin, body.element, body.condition, by=body.by, note=body.note,
        media_ids=body.media_ids)


__all__ = ["router"]
