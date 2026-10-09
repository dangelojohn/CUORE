"""JSON face of the Job (case) workflow -- see ``cuore.services.jobs_bridge``.

Read-only ``GET /vehicles/{vin}/job`` mirrors what the HTML job page renders;
the POST endpoints are thin pass-through to the bridge, which is thin
pass-through to ``mes.jobs``. Nothing here writes to the car or the MES
corpus -- a job lives entirely in its own JSONL store.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..services import jobs_bridge
from ..services.jobs_bridge import RuleViolation
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
    codes: Optional[list[str]] = None
    likelihood: Optional[str] = Field(default=None, description="low | med | high")
    by: Optional[str] = None


class HypothesisStatusSet(BaseModel):
    status: str = Field(..., description="open | supported | refuted | confirmed")
    by: Optional[str] = None


class HypothesisEdit(BaseModel):
    text: Optional[str] = None
    system: Optional[str] = None
    codes: Optional[list[str]] = None
    likelihood: Optional[str] = Field(default=None, description="low | med | high")
    next_test: Optional[str] = None
    by: Optional[str] = None


class HypothesisEvidence(BaseModel):
    action: str = Field(..., description="add | remove | resolve")
    side: str = Field(default="for", description="for | against")
    ref: Optional[dict[str, Any]] = Field(
        default=None, description="required for action=add: {kind, id, label, result?}")
    ref_id: Optional[Any] = Field(
        default=None, description="required for action=remove/resolve")
    ref_kind: Optional[str] = None
    resolved: bool = True
    by: Optional[str] = None


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
                                      next_test=body.next_test, codes=body.codes,
                                      likelihood=body.likelihood, by=body.by)


@router.get("/jobs/{job_id}/hypotheses/similar",
           summary="The most similar existing hypothesis to a proposed one (merge prompt)")
def similar_hypothesis(job_id: str, text: str, system: str = "") -> dict[str, Any]:
    return {"similar": jobs_bridge.check_similar(job_id, text, system=system)}


@router.post("/jobs/{job_id}/hypotheses/{hyp_id}/status",
            summary="Change a hypothesis's status -- 409 on a rule violation")
def set_hypothesis_status(job_id: str, hyp_id: str, body: HypothesisStatusSet) -> Any:
    """``open -> supported -> confirmed``, plus ``refuted`` from any state.
    Jumping ``open -> confirmed``, or confirming without a passed/failed
    test linked (or with unresolved evidence against), is refused as HTTP
    409 with the body ``{"detail": reason, "next_test": ...}`` at the top
    level (a plain ``JSONResponse``, not ``HTTPException``'s own envelope,
    so ``next_test`` sits beside ``detail`` rather than nested under it) --
    see JOB_UX_FIXES_2026-10-08.md #1."""
    try:
        return jobs_bridge.set_hypothesis(job_id, hyp_id, status=body.status, by=body.by)
    except RuleViolation as exc:
        return JSONResponse(status_code=409,
                            content={"detail": exc.reason, "next_test": exc.next_test})


@router.post("/jobs/{job_id}/hypotheses/{hyp_id}", summary="Edit a hypothesis's own fields")
def edit_hypothesis(job_id: str, hyp_id: str, body: HypothesisEdit) -> dict[str, Any]:
    return jobs_bridge.edit_hypothesis(job_id, hyp_id, text=body.text, system=body.system,
                                       codes=body.codes, likelihood=body.likelihood,
                                       next_test=body.next_test, by=body.by)


@router.delete("/jobs/{job_id}/hypotheses/{hyp_id}", summary="Soft-delete a hypothesis")
def delete_hypothesis(job_id: str, hyp_id: str, by: Optional[str] = None) -> dict[str, Any]:
    return jobs_bridge.delete_hypothesis(job_id, hyp_id, by=by)


@router.post("/jobs/{job_id}/hypotheses/{hyp_id}/undelete", summary="Undo a soft-delete")
def undelete_hypothesis(job_id: str, hyp_id: str, by: Optional[str] = None) -> dict[str, Any]:
    return jobs_bridge.undelete_hypothesis(job_id, hyp_id, by=by)


@router.post("/jobs/{job_id}/hypotheses/{hyp_id}/evidence",
            summary="Add, remove, or resolve one evidence ref on a hypothesis")
def hypothesis_evidence(job_id: str, hyp_id: str, body: HypothesisEvidence) -> dict[str, Any]:
    action = body.action.strip().lower()
    if action == "add":
        if not body.ref:
            raise HTTPException(status_code=400, detail="ref is required for action=add")
        return jobs_bridge.add_evidence(job_id, hyp_id, body.side, body.ref, by=body.by)
    if action == "remove":
        if body.ref_id is None:
            raise HTTPException(status_code=400, detail="ref_id is required for action=remove")
        return jobs_bridge.remove_evidence(job_id, hyp_id, body.side, body.ref_id,
                                           ref_kind=body.ref_kind, by=body.by)
    if action == "resolve":
        if body.ref_id is None:
            raise HTTPException(status_code=400, detail="ref_id is required for action=resolve")
        return jobs_bridge.resolve_evidence(job_id, hyp_id, body.ref_id, ref_kind=body.ref_kind,
                                            resolved=body.resolved, by=body.by)
    raise HTTPException(status_code=400, detail="action must be one of add | remove | resolve")


@router.get("/jobs/steps", summary="The flow's step registry (n/key/title) for cross-references")
def steps() -> dict[str, Any]:
    return {"steps": jobs_bridge.step_registry()}


@router.post("/jobs/{job_id}/actions", summary="Record one action against a job")
def add_action(job_id: str, body: ActionAdd) -> dict[str, Any]:
    return jobs_bridge.add_action(job_id, body.kind, body.text, ref=body.ref)


@router.post("/jobs/{job_id}/attach", summary="Attach a real record as hypothesis evidence or a job link")
def attach(job_id: str, body: RefAttach) -> dict[str, Any]:
    return jobs_bridge.attach(job_id, body.ref, hyp_id=body.hyp_id,
                              supports=body.supports, link=body.link)


@router.post("/jobs/migrate-systems",
            summary="Backfill system_text on old-shape hypothesis records (idempotent)")
def migrate_systems(job_id: Optional[str] = None) -> dict[str, Any]:
    """One-off admin sweep (loopback-only app, no extra guard beyond the
    existing token dependency) -- see ``mes.jobs.migrate_systems`` for what
    it does and why it's safe to re-run. Imports ``mes.jobs`` directly
    rather than through ``cuore.services.jobs_bridge`` (that module is
    mid-edit elsewhere right now, and this sweep doesn't need its
    page-view machinery), same posture as ``cuore.api.tests``' own direct
    ``from mes import mechanic_tests``."""
    from mes import jobs as jobs_mod
    return jobs_mod.migrate_systems(job_id=job_id)


__all__ = ["router"]
