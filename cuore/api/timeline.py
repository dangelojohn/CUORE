"""The mechanic-vs-driver timeline: codes on one axis, what was actually felt
on the other.

HTTP face of ``cuore.services.timeline_bridge``, same posture as
``cuore/api/vehicles.py``: payload shapes come from the bridge unchanged.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import timeline_bridge
from .deps import require_token

router = APIRouter(tags=["timeline"], dependencies=[Depends(require_token)])


class SymptomRequest(BaseModel):
    """A driver/mechanic symptom report, submitted for recording.

    See ``mes.symptoms.SYMPTOM_TAGS``/``CONDITIONS`` for the full vocabulary.
    ``drives_normally`` cannot be combined with a drivability tag
    (rough_idle, hesitation, loss_of_power, hard_start).
    """

    at: str = Field(..., description="ISO timestamp of when the symptom happened.")
    odometer_km: Optional[float] = None
    reporter: str = "driver"
    tags: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    text: str = ""


@router.get("/vehicles/{vin}/timeline", summary="Codes vs. what the driver noticed")
def timeline(vin: str) -> dict[str, Any]:
    """Every code family, clear, note, service record and symptom report for
    this VIN, laid out on one timeline, plus the per-family correlation
    between a code's occurrences and whether a symptom was ever reported
    near them. For EVAP the honest finding is usually that none was."""
    return timeline_bridge.build_timeline(vin)


@router.get("/vehicles/{vin}/symptoms", summary="Symptom reports for this vehicle")
def list_symptoms(vin: str, include_hidden: bool = False) -> dict[str, Any]:
    return timeline_bridge.symptoms(vin, include_hidden=include_hidden)


@router.post("/vehicles/{vin}/symptoms", summary="Record a symptom report")
def add_symptom(vin: str, body: SymptomRequest) -> dict[str, Any]:
    return timeline_bridge.add_symptom(
        vin, body.at, odometer_km=body.odometer_km, reporter=body.reporter,
        tags=body.tags, conditions=body.conditions, text=body.text)


@router.post("/vehicles/{vin}/symptoms/{id}/hide", summary="Hide a symptom report (soft delete)")
def hide_symptom(vin: str, id: str) -> dict[str, Any]:
    """``vin`` is not used to authorize this -- a symptom report is addressed
    by its own id -- but is kept in the path so the route sits beside the
    rest of this vehicle's symptom endpoints."""
    return timeline_bridge.hide_symptom(id)


@router.get("/vehicles/{vin}/code/{code}/feel", summary="What would the driver feel?")
def code_feel(vin: str, code: str) -> dict[str, Any]:
    """The sourced knowledge-table entry for this code (or ``null`` if
    nothing is tabulated for it) next to this car's own pattern: how many
    sessions it has appeared in, and whether a symptom report has ever
    landed near one of them."""
    return timeline_bridge.code_feel(vin, code)


__all__ = ["router"]
