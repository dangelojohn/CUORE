"""HTTP surface for the Tests catalogue -- a read-only knowledge base of
mechanic tests (:mod:`mes.mechanic_tests`) plus a per-VIN results view.

Thin wrapper over :mod:`cuore.services.tests_bridge`, same posture as every
other API module here. No route writes to the car -- the only mutation is
``POST /tests/{vin}/{test_id}/result``, which stores a technician's
recorded result (and, when it names a hypothesis, auto-attaches evidence
through the existing job-evidence path) exactly the way
``cuore.api.checklists``'s ``/result`` route already does for a job-page
test row.

2026-10-14 addition: the MES handoff routes below (``/tests/mes-handoff/*``
and ``/tests/{vin}/mes-import``), a thin wrapper over
:mod:`cuore.services.mes_handoff_bridge`. Still no write to the car --
``mes-import`` only reads a file MES already wrote and records it in this
service's own small ledger.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import mes_handoff_bridge, tests_bridge
from .deps import require_token

router = APIRouter(tags=["tests"], dependencies=[Depends(require_token)])


class MesImportBody(BaseModel):
    name: str = Field(..., description="bare MES log filename on a configured "
                                       "MES_LOG_DIR root, e.g. SCAN_2610080920.txt")


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


@router.get("/tests/mes-handoff/candidates", summary="Every catalogued MES "
                                                     "function, trimmed for "
                                                     "client-side matching "
                                                     "against a test/step "
                                                     "name")
def mes_handoff_candidates() -> dict[str, Any]:
    return {"functions": mes_handoff_bridge.candidates()}


@router.get("/tests/mes-handoff/by-test/{test_id}", summary="Handoff card "
                                                            "for a mechanic-"
                                                            "test catalogue "
                                                            "id, or "
                                                            "handoff: null")
def mes_handoff_by_test(test_id: str) -> dict[str, Any]:
    return {"test_id": test_id, "handoff": mes_handoff_bridge.find_for_test(test_id)}


@router.get("/tests/mes-handoff/by-text", summary="Handoff card matching a "
                                                   "free-text job-step "
                                                   "label, or handoff: null")
def mes_handoff_by_text(text: str) -> dict[str, Any]:
    return {"text": text, "handoff": mes_handoff_bridge.find_for_text(text)}


@router.post("/tests/{vin}/mes-import", summary="Import an MES SCAN/FES log "
                                                "already on a configured MES "
                                                "root: records it as a Scans-"
                                                "timeline entry (source MES) "
                                                "with the same health "
                                                "verdict a live scan gets")
def mes_import(vin: str, body: MesImportBody) -> dict[str, Any]:
    scan = mes_handoff_bridge.import_mes_log(vin, body.name)
    return {"vin": vin, "scan": scan, "health_line": mes_handoff_bridge.health_line(scan)}


@router.get("/tests/{vin}/mes-scans", summary="MES-imported scans on file "
                                               "for this vehicle (source "
                                               "MES), newest first")
def mes_scans(vin: str) -> dict[str, Any]:
    scans = mes_handoff_bridge.list_mes_scans(vin)
    return {"vin": vin, "scans": scans,
           "lines": [mes_handoff_bridge.health_line(s) for s in scans]}


__all__ = ["router"]
