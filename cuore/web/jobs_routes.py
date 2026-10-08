"""Web-form face of the Job (case) workflow.

Same posture as ``cuore.web.dossier_routes``: a second router on the same
app reusing ``cuore.web.routes``'s own page/dossier helpers, so rendering
stays identical to every other ``/v/{vin}`` page. Every form here degrades
with no JavaScript -- a stepper of plain GET/POST/redirect forms, same
convention as ``/v/{vin}/dealer`` and ``/v/{vin}/notes``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..services import jobs_bridge
from ..services.errors import BridgeError
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _job_page(request: Request, vin: str, job_id: str = "", **extra: Any) -> HTMLResponse:
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    view = jobs_bridge.build_job_view(vin, job_id or None)
    response = web_routes._page(request, "job.html", vin=vin, bar=bar, view=view,
                                tab="job", **extra)
    web_routes._set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/job", response_class=HTMLResponse)
def job_page(request: Request, vin: str) -> HTMLResponse:
    """The current (or most recent) job for this vehicle, with the stepper."""
    return _job_page(request, vin)


@router.get("/v/{vin}/job/{job_id}", response_class=HTMLResponse)
def job_page_one(request: Request, vin: str, job_id: str) -> HTMLResponse:
    """One specific job by id -- e.g. a closed case from this car's history."""
    return _job_page(request, vin, job_id=job_id)


@router.post("/v/{vin}/job/open", response_class=HTMLResponse)
async def job_open(request: Request, vin: str,
                   technician: str = Form(default=""),
                   complaint: str = Form(default="")) -> RedirectResponse:
    """Step 1: open a new case for this vehicle, in the driver's own words."""
    jobs_bridge.open_job(vin, technician=technician, complaint=complaint)
    return RedirectResponse(url=f"/v/{vin}/job", status_code=303)


@router.post("/v/{vin}/job/{job_id}/hypotheses", response_class=HTMLResponse)
async def hypothesis_add(request: Request, vin: str, job_id: str,
                         text: str = Form(...), system: str = Form(default=""),
                         next_test: str = Form(default="")) -> RedirectResponse:
    """Step 4: add a hypothesis to the ledger by hand."""
    jobs_bridge.add_hypothesis(job_id, text, system=system, next_test=next_test)
    return RedirectResponse(url=f"/v/{vin}/job#hypotheses", status_code=303)


@router.post("/v/{vin}/job/{job_id}/hypotheses/suggested", response_class=HTMLResponse)
async def hypothesis_add_suggested(request: Request, vin: str, job_id: str,
                                   text: str = Form(...), system: str = Form(default=""),
                                   next_test: str = Form(default=""),
                                   evidence_for: str = Form(default="[]"),
                                   evidence_against: str = Form(default="[]")
                                   ) -> RedirectResponse:
    """Step 4: promote one of the auto-suggested hypotheses, with its real
    evidence attached in the same step -- the refs travel as a hidden JSON
    field rather than being retyped, so nothing here can invent evidence
    that was not already shown on the page."""
    suggestion = {
        "text": text, "system": system, "next_test": next_test,
        "evidence_for": json.loads(evidence_for) if evidence_for.strip() else [],
        "evidence_against": json.loads(evidence_against) if evidence_against.strip() else [],
    }
    jobs_bridge.add_suggested_hypothesis(job_id, suggestion)
    return RedirectResponse(url=f"/v/{vin}/job#hypotheses", status_code=303)


@router.post("/v/{vin}/job/{job_id}/hypotheses/{hyp_id}/status", response_class=HTMLResponse)
async def hypothesis_set_status(request: Request, vin: str, job_id: str, hyp_id: str,
                                status: str = Form(...)) -> RedirectResponse:
    """Step 4: the 44px status buttons -- open / supported / refuted / confirmed."""
    jobs_bridge.set_hypothesis(job_id, hyp_id, status=status)
    return RedirectResponse(url=f"/v/{vin}/job#hypotheses", status_code=303)


@router.post("/v/{vin}/job/{job_id}/hypotheses/{hyp_id}/next_test", response_class=HTMLResponse)
async def hypothesis_set_next_test(request: Request, vin: str, job_id: str, hyp_id: str,
                                   next_test: str = Form(default="")) -> RedirectResponse:
    jobs_bridge.set_hypothesis(job_id, hyp_id, next_test=next_test)
    return RedirectResponse(url=f"/v/{vin}/job#hypotheses", status_code=303)


@router.post("/v/{vin}/job/{job_id}/actions", response_class=HTMLResponse)
async def action_add(request: Request, vin: str, job_id: str,
                     kind: str = Form(...), text: str = Form(...)) -> RedirectResponse:
    """Step 5: record one repair action -- test, inspection, repair, part,
    clear, or a free-text note."""
    jobs_bridge.add_action(job_id, kind, text)
    return RedirectResponse(url=f"/v/{vin}/job#actions", status_code=303)


@router.post("/v/{vin}/job/{job_id}/close", response_class=HTMLResponse)
async def job_close(request: Request, vin: str, job_id: str,
                    outcome: str = Form(...),
                    codes_returned: str = Form(default=""),
                    verdict: str = Form(default="")) -> HTMLResponse:
    """Step 7: close the case. Outcome is required -- a job can never be
    closed with no stated result."""
    codes = [c.strip() for c in codes_returned.split(",") if c.strip()]
    error = None
    try:
        jobs_bridge.close_job(job_id, outcome, codes_returned=codes or None,
                              verdict=verdict or None)
    except BridgeError as exc:
        error = str(exc)
    return _job_page(request, vin, job_id=job_id, close_error=error)


__all__ = ["router"]
