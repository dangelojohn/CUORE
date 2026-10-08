"""JSON face of the shop day board and release gate -- see
``cuore.services.shop_bridge``.

Not registered on the app here -- ``app.py`` is owned by another agent while
this was built. The two lines needed there (next to the other ``/api``
router imports, as ``from .api import shop as shop_api``):

    ``app.include_router(shop_api.router, prefix="/api")``
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import shop_bridge
from .deps import require_token

router = APIRouter(tags=["shop"], dependencies=[Depends(require_token)])


class Intake(BaseModel):
    vin: str
    complaint: str = Field(default="")
    technician: str = Field(default="")
    bay: str = Field(default="")
    promised_at: Optional[str] = None


class StatusSet(BaseModel):
    status: str


class StepMark(BaseModel):
    step: int


class ReleaseBody(BaseModel):
    """``verified`` is deliberately absent -- it is derived from the
    dossier verdict, never taken from the request."""
    report_printed: bool = False
    labels_printed: bool = False
    parts_logged: bool = False
    tools_reviewed: bool = False
    notes: str = Field(default="")
    reason: Optional[str] = None


@router.get("/shop/board", summary="The day board: cars currently in, plus today's throughput")
def board() -> dict[str, Any]:
    return shop_bridge.build_board()


@router.post("/shop/intake", summary="Take a car in: register the visit and open a linked Job")
def intake(body: Intake) -> dict[str, Any]:
    return shop_bridge.intake(body.vin, body.complaint, technician=body.technician,
                              bay=body.bay, promised_at=body.promised_at)


@router.get("/shop/visits/{visit_id}", summary="One visit by id")
def get_visit(visit_id: str) -> dict[str, Any]:
    return shop_bridge.get_visit(visit_id)


@router.post("/shop/visits/{visit_id}/status", summary="Move a visit to a new status")
def set_status(visit_id: str, body: StatusSet) -> dict[str, Any]:
    return shop_bridge.set_status(visit_id, body.status)


@router.post("/shop/visits/{visit_id}/steps/start", summary="Start timing a job step (1-7)")
def start_step(visit_id: str, body: StepMark) -> dict[str, Any]:
    return shop_bridge.start_step(visit_id, body.step)


@router.post("/shop/visits/{visit_id}/steps/end", summary="End timing a job step (1-7)")
def end_step(visit_id: str, body: StepMark) -> dict[str, Any]:
    return shop_bridge.end_step(visit_id, body.step)


@router.get("/shop/visits/{visit_id}/release", summary="The release gate view for one visit")
def release_view(visit_id: str) -> dict[str, Any]:
    return shop_bridge.build_release_view(visit_id)


@router.post("/shop/visits/{visit_id}/release",
            summary="Release the car -- advises and records, never blocks")
def release(visit_id: str, body: ReleaseBody) -> dict[str, Any]:
    checks = {"report_printed": body.report_printed, "labels_printed": body.labels_printed,
             "parts_logged": body.parts_logged, "tools_reviewed": body.tools_reviewed,
             "notes": body.notes}
    return shop_bridge.release(visit_id, checks, reason=body.reason)


__all__ = ["router"]
