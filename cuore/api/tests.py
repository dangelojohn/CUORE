"""HTTP surface for the Tests catalogue -- a read-only knowledge base of
mechanic tests (:mod:`mes.mechanic_tests`) plus a per-VIN results view.

Thin wrapper over :mod:`cuore.services.tests_bridge`, same posture as every
other API module here. No route writes to the car -- the only mutation is
``POST /tests/{vin}/{test_id}/result``, which stores a technician's
recorded result (and, when it names a hypothesis, auto-attaches evidence
through the existing job-evidence path) exactly the way
``cuore.api.checklists``'s ``/result`` route already does for a job-page
test row.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import tests_bridge
from .deps import require_token

router = APIRouter(tags=["tests"], dependencies=[Depends(require_token)])


class TestResultBody(BaseModel):
    result: Optional[str] = Field(
        default=None, description="pass | fail | inconclusive | not_possible, "
                                  "or null to clear")
    value: Optional[float] = Field(default=None, description="measured value, when "
                                                             "the test has a spec")
    unit: str = Field(default="")
    reason: str = Field(default="")
    hypothesis_id: Optional[str] = Field(
        default=None, description="which of the job's open hypotheses this result "
                                  "bears on, if any")
    supports: str = Field(default="for", description="for | against -- which side "
                                                     "of hypothesis_id this result's "
                                                     "evidence counts toward; "
                                                     "ignored unless result is "
                                                     "pass/fail")
    by: str = Field(default="")


@router.get("/tests/catalog", summary="The full mechanic-test catalogue, no "
                                      "per-VIN state")
def tests_catalog() -> dict[str, Any]:
    from mes import mechanic_tests
    return {"tests": mechanic_tests.all_tests(), "categories": sorted(mechanic_tests.CATEGORIES)}


@router.get("/tests/{vin}", summary="The Tests view for this vehicle: catalogue, "
                                    "latest results, relevance ranking, counts")
def tests_view(vin: str) -> dict[str, Any]:
    return tests_bridge.build_tests_view(vin)


@router.post("/tests/{vin}/{test_id}/result", summary="Record a test result; "
                                                      "auto-attaches evidence on "
                                                      "pass/fail when a hypothesis "
                                                      "is named")
def post_test_result(vin: str, test_id: str, body: TestResultBody) -> dict[str, Any]:
    return tests_bridge.record_result(
        vin, test_id, body.result, reason=body.reason, value=body.value,
        unit=body.unit, hypothesis_id=body.hypothesis_id, supports=body.supports,
        by=body.by)


__all__ = ["router"]
