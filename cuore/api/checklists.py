"""Shop-visible checklist state over HTTP: GET/POST one step at a time.

A step id is only meaningful in the context of the vehicle whose open-work
cards named it (``dossier_bridge.checklist_step_ids``), so a POST for a step
id this VIN's dossier does not expose is rejected -- a 400, not a silent
no-op and not a 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..live import checklists as checklist_store
from ..services import cache, dossier_bridge, mes_bridge
from ..services.errors import BadRequest
from .deps import require_token

router = APIRouter(tags=["vehicles"], dependencies=[Depends(require_token)])

#: The bench's evidence-gate outcomes (BENCH_UX_SPEC_2026-10-08.md B5) -- a
#: bare done/undone flag cannot tell "passed" from "ticked and ignored".
_OUTCOMES = {"ok", "fault_found", "skipped"}


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


__all__ = ["router"]
