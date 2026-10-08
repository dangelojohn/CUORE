"""JSON face of the Job (case) workflow -- see ``cuore.services.jobs_bridge``.

Read-only ``GET /vehicles/{vin}/job`` mirrors what the HTML job page renders;
the POST endpoints are thin pass-through to the bridge, which is thin
pass-through to ``mes.jobs``. Nothing here writes to the car or the MES
corpus -- a job lives entirely in its own JSONL store.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import jobs_bridge
from .deps import require_token

router = APIRouter(tags=["jobs"], dependencies=[Depends(require_token)])


class JobOpen(BaseModel):
    technician: str = Field(default="")
    complaint: str = Field(default="")


class JobClose(BaseModel):
    outcome: str
    readiness_at: Optional[str] = None
    codes_returned: Optional[list[str]] = None
    verdict: Optional[str] = None


class HypothesisAdd(BaseModel):
    text: str
    system: str = Field(default="")
    next_test: str = Field(default="")


class HypothesisSet(BaseModel):
    status: Optional[str] = None
    next_test: Optional[str] = None


class ActionAdd(BaseModel):
    kind: str
    text: str
    ref: Optional[dict[str, Any]] = None


class RefAttach(BaseModel):
    ref: dict[str, Any]
    hyp_id: Optional[str] = None
    supports: bool = True
    link: Optional[str] = None


@router.get("/vehicles/{vin}/job", summary="The current (or most recent) job for this vehicle")
def view(vin: str) -> dict[str, Any]:
    return jobs_bridge.build_job_view(vin)


@router.get("/vehicles/{vin}/job/{job_id}", summary="One job by id")
def view_one(vin: str, job_id: str) -> dict[str, Any]:
    return jobs_bridge.build_job_view(vin, job_id)


@router.post("/vehicles/{vin}/job", summary="Open a new job (case) for this vehicle")
def open_job(vin: str, body: JobOpen) -> dict[str, Any]:
    return jobs_bridge.open_job(vin, technician=body.technician, complaint=body.complaint)


@router.post("/jobs/{job_id}/close", summary="Close a job -- outcome required")
def close_job(job_id: str, body: JobClose) -> dict[str, Any]:
    return jobs_bridge.close_job(job_id, body.outcome, readiness_at=body.readiness_at,
                                 codes_returned=body.codes_returned, verdict=body.verdict)


@router.post("/jobs/{job_id}/hypotheses", summary="Add a hypothesis to a job's ledger")
def add_hypothesis(job_id: str, body: HypothesisAdd) -> dict[str, Any]:
    return jobs_bridge.add_hypothesis(job_id, body.text, system=body.system,
                                      next_test=body.next_test)


@router.post("/jobs/{job_id}/hypotheses/{hyp_id}", summary="Change a hypothesis's status/next test")
def set_hypothesis(job_id: str, hyp_id: str, body: HypothesisSet) -> dict[str, Any]:
    return jobs_bridge.set_hypothesis(job_id, hyp_id, status=body.status,
                                      next_test=body.next_test)


@router.post("/jobs/{job_id}/actions", summary="Record one action against a job")
def add_action(job_id: str, body: ActionAdd) -> dict[str, Any]:
    return jobs_bridge.add_action(job_id, body.kind, body.text, ref=body.ref)


@router.post("/jobs/{job_id}/attach", summary="Attach a real record as hypothesis evidence or a job link")
def attach(job_id: str, body: RefAttach) -> dict[str, Any]:
    return jobs_bridge.attach(job_id, body.ref, hyp_id=body.hyp_id,
                              supports=body.supports, link=body.link)


__all__ = ["router"]
