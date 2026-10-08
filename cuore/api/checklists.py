"""Shop-visible checklist state over HTTP: GET/POST one step at a time.

A step id is only meaningful in the context of the vehicle whose open-work
cards named it (``dossier_bridge.checklist_step_ids``), so a POST for a step
id this VIN's dossier does not expose is rejected -- a 400, not a silent
no-op and not a 500.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..live import checklists as checklist_store
from ..services import cache, dossier_bridge, jobs_bridge, mes_bridge
from ..services.errors import BadRequest
from .deps import require_token

router = APIRouter(tags=["vehicles"], dependencies=[Depends(require_token)])

#: The bench's evidence-gate outcomes (BENCH_UX_SPEC_2026-10-08.md B5) -- a
#: bare done/undone flag cannot tell "passed" from "ticked and ignored".
_OUTCOMES = {"ok", "fault_found", "skipped"}

#: Step 6's "result sheet" outcomes (JOB_UX_FIXES_2026-10-08.md #3) --
#: distinct from the bench's own ok/fault_found/skipped above. Only
#: pass/fail count toward hypothesis test evidence.
_RESULTS = {"pass", "fail", "inconclusive", "not_possible"}


class ChecklistResult(BaseModel):
    result: Optional[str] = Field(
        default=None, description="pass | fail | inconclusive | not_possible, "
                                  "or null to clear")
    reason: str = Field(default="", description="required detail for fail/inconclusive/"
                                               "not_possible, e.g. why it failed")
    value: Optional[float] = Field(default=None, description="measured value, when the "
                                                             "test has a spec")
    unit: str = Field(default="")
    hypothesis_id: Optional[str] = Field(
        default=None, description="which hypothesis this result bears on, if any")
    supports: str = Field(default="for", description="for | against -- which side of "
                                                     "hypothesis_id this result's evidence "
                                                     "counts toward; ignored unless "
                                                     "result is pass/fail")
    media_ids: list[str] = Field(default_factory=list)
    by: str = Field(default="")


class ChecklistUpdate(BaseModel):
    step_id: str = Field(..., description="e.g. evap-1, network-2 -- see "
                                          "GET /api/vehicles/{vin}/view -> "
                                          "open_work[].steps[].id")
    done: bool
    by: str = Field(default="", description="technician name/initials, optional")
    outcome: str = Field(default="", description="one of ok/fault_found/skipped, "
                                                 "only meaningful when done=true")
    note: str = Field(default="", description="one-line finding (outcome=fault_found) "
                                               "or reason (outcome=skipped)")


def _dossier(vin: str) -> dict[str, Any]:
    return cache.get_or_build(
        ("workup", vin, mes_bridge.newest_mtime(vin)),
        lambda: mes_bridge.workup(vin=vin))


def _step_text(vin: str, step_id: str) -> str:
    """This step's own text from the vehicle's open-work cards, for the
    evidence ref's label -- falls back to the bare id if the dossier can't
    be read or no card names this step (never blocks the result save)."""
    try:
        view = dossier_bridge.build_view(vin, _dossier(vin), None)
    except Exception:  # noqa: BLE001
        return step_id
    for card in view.get("open_work", []):
        for s in card.get("steps", []):
            if s.get("id") == step_id:
                return s.get("text") or step_id
    return step_id


@router.get("/vehicles/{vin}/checklist", summary="Checklist state for this vehicle")
def get_checklist(vin: str) -> dict[str, Any]:
    return {"vin": vin, "checklist": checklist_store.get(vin)}


@router.post("/vehicles/{vin}/checklist", summary="Tick (or untick) one checklist "
                                                   "step, with an outcome")
def set_checklist_step(vin: str, body: ChecklistUpdate) -> dict[str, Any]:
    valid = dossier_bridge.checklist_step_ids(vin, _dossier(vin))
    if body.step_id not in valid:
        raise BadRequest(f"unknown checklist step id {body.step_id!r} for this vehicle")
    outcome = body.outcome.strip() or None
    if body.done and outcome and outcome not in _OUTCOMES:
        raise BadRequest(f"outcome must be one of {sorted(_OUTCOMES)}, got {outcome!r}")
    entry = checklist_store.set_step(vin, body.step_id, body.done, by=body.by,
                                     outcome=outcome, note=body.note)
    if body.done and outcome == "fault_found" and body.note.strip():
        try:
            mes_bridge.add_note(vin, body.note.strip(), target_kind="tree_step",
                                target_id=body.step_id, author=body.by or "technician",
                                tags=["bench", "finding"])
        except Exception:  # noqa: BLE001 -- the checklist write must still succeed
            pass
    return {"vin": vin, "step_id": body.step_id, **entry}


@router.post("/vehicles/{vin}/checklist/{step_id}/result",
            summary="Record a test result on one checklist row (step 6 result sheet)")
def set_checklist_result(vin: str, step_id: str, body: ChecklistResult) -> dict[str, Any]:
    """The step 6 "result sheet" (JOB_UX_FIXES_2026-10-08.md #3): Pass / Fail
    / Inconclusive / Not possible, with an optional measured value+unit and
    which hypothesis it bears on. When ``hypothesis_id`` is given and the
    result is pass/fail, this also attaches a ``kind="test"`` evidence ref
    to that hypothesis (for/against per ``supports``) -- only pass/fail
    count as hypothesis test evidence."""
    valid = dossier_bridge.checklist_step_ids(vin, _dossier(vin))
    if step_id not in valid:
        raise BadRequest(f"unknown checklist step id {step_id!r} for this vehicle")
    if body.result is not None and body.result not in _RESULTS:
        raise BadRequest(f"result must be one of {sorted(_RESULTS)}, got {body.result!r}")
    if body.supports not in ("for", "against"):
        raise BadRequest("supports must be 'for' or 'against'")
    entry = checklist_store.set_result(vin, step_id, body.result, reason=body.reason,
                                       value=body.value, unit=body.unit,
                                       hypothesis_id=body.hypothesis_id,
                                       media_ids=body.media_ids, by=body.by)
    if body.hypothesis_id and body.result in ("pass", "fail"):
        label = f"{_step_text(vin, step_id)}: {body.result}"
        if body.value is not None:
            label += f" {body.value:g}{body.unit}"
        try:
            jobs_bridge.add_test_evidence(vin, body.hypothesis_id, step_id, label,
                                          body.result, supports=body.supports, by=body.by)
        except Exception:  # noqa: BLE001 -- the result must still save
            pass
    return {"vin": vin, "step_id": step_id, **entry}


__all__ = ["router"]
