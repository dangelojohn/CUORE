"""Mechanic feedback on a fact cuore showed -- corrections, questions,
confirmations, input, and disagreement, each pinned to one page/section/item
and later answerable.

This is the HTTP face of :mod:`mes.feedback` via
``cuore.services.feedback_bridge``, mirroring the MCP tools
``feedback_list``/``feedback_add``/``feedback_answer``/``feedback_status`` in
``mes-log-mcp/server.py`` call-for-call so an answer here and an answer there
are the same answer.

Registration note: ``cuore/app.py`` is owned by another agent and is not
edited by this module. Wiring this router in needs one line added there,
beside the other ``/api`` routers::

    app.include_router(feedback.router, prefix="/api")
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..services import feedback_bridge
from .deps import require_token

router = APIRouter(tags=["feedback"], dependencies=[Depends(require_token)])


class FeedbackTarget(BaseModel):
    """What fact this feedback is about. ``page`` and ``label`` are required;
    ``section``/``item`` narrow the target further and default to empty."""

    page: str = Field(..., description="The cuore page/route the fact appeared on.")
    section: str = ""
    item: str = ""
    label: str = Field(..., description="The fact text itself, as shown. "
                                        "Max 200 characters.")


class FeedbackRequest(BaseModel):
    kind: str = Field(..., description="correction | question | confirm | "
                                       "input | disagree")
    target: FeedbackTarget
    text: str = ""
    author: str = "technician"
    media_ids: list[str] = Field(default_factory=list)


class FeedbackAnswerRequest(BaseModel):
    text: str = Field(..., description="The answer text.")
    by: str = "claude"


class FeedbackStatusRequest(BaseModel):
    status: str = Field(..., description="open | answered | applied | dismissed")
    note: str = ""


@router.get("/vehicles/{vin}/feedback", summary="Mechanic feedback for this vehicle")
def list_feedback(vin: str, status: str = "") -> dict[str, Any]:
    return feedback_bridge.load(vin, status=status)


@router.post("/vehicles/{vin}/feedback", summary="Record mechanic feedback")
def add_feedback(vin: str, body: FeedbackRequest) -> dict[str, Any]:
    return feedback_bridge.add(vin, body.kind, body.target.model_dump(),
                               text=body.text, author=body.author,
                               media_ids=body.media_ids)


@router.get("/vehicles/{vin}/feedback/counts", summary="Per-target feedback tallies")
def feedback_counts(vin: str, targets: str = Query(
        default="", description="Comma-separated page|section|item keys.")) -> dict[str, Any]:
    target_list = [t.strip() for t in targets.split(",") if t.strip()]
    return feedback_bridge.counts(vin, target_list)


@router.post("/feedback/{id}/answer", summary="Answer one feedback row")
def answer_feedback(id: str, body: FeedbackAnswerRequest) -> dict[str, Any]:
    """Not addressed under a VIN -- a feedback row is addressed by its own id,
    same posture as note edits/hides."""
    return feedback_bridge.answer(id, body.text, by=body.by)


@router.post("/feedback/{id}/status", summary="Set one feedback row's status")
def set_feedback_status(id: str, body: FeedbackStatusRequest) -> dict[str, Any]:
    return feedback_bridge.set_status(id, body.status, note=body.note)
