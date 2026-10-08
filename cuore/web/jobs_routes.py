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
from ..services import cases_bridge, dossier_bridge, jobs_bridge, tools_kb_bridge
from ..services.errors import BridgeError
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.post("/tools-kb/inventory-form", response_class=HTMLResponse)
async def tools_inventory_form(status: str = Form(...), tool: str = Form(...),
                               return_to: str = Form(default="/")) -> RedirectResponse:
    """The "I have this / I don't" button pair on the tools panel -- a
    garage-wide owned/not-owned list (``cuore.services.tools_kb_bridge``),
    not tied to any one vehicle, so it lives here rather than under
    ``/v/{vin}/...`` even though the tools panel itself renders on
    vehicle-scoped pages (job.html, maintenance.html)."""
    tools_kb_bridge.inventory_set(tool, status)
    return RedirectResponse(url=return_to or "/", status_code=303)


def _job_page(request: Request, vin: str, job_id: str = "", tools_step: str = "",
             **extra: Any) -> HTMLResponse:
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    job_view = jobs_bridge.build_job_view(vin, job_id or None, tools_step=tools_step or None)
    live_status = web_routes._status_strip()
    try:
        dossier_view = dossier_bridge.build_view(vin, dossier, live_status)
    except Exception:  # noqa: BLE001 -- the job page must still render
        dossier_view = {"verdict": None, "open_work": [], "codes": [],
                        "code_counts": {}, "attempted": []}
    active_codes = [c["code"] for c in dossier_view.get("codes", [])
                    if c.get("status") == "ACTIVE"]
    try:
        case_prefill = cases_bridge.prefill(vin, active_codes)
    except Exception:  # noqa: BLE001 -- case memory must never 500 the job page
        case_prefill = None
    # `view` carries the full dossier view -- the shape _verdict_card.html,
    # _codes_table.html and _open_work.html already expect everywhere else
    # they're included; `job_view` carries the Job-specific data only
    # job.html itself reads.
    response = web_routes._page(request, "job.html", vin=vin, bar=bar, view=dossier_view,
                                job_view=job_view, case_prefill=case_prefill,
                                active_codes=active_codes, tab="job", **extra)
    web_routes._set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/job", response_class=HTMLResponse)
def job_page(request: Request, vin: str, tools_step: str = "", step: str = "") -> HTMLResponse:
    """The current (or most recent) job for this vehicle, one step per
    screen -- ``step`` is the only query param this page reads to pick
    which of the 12 steps is the full screen (default: the flow's own
    current step, resolved inside job.html itself)."""
    return _job_page(request, vin, tools_step=tools_step, step=step)


@router.get("/v/{vin}/job/{job_id}", response_class=HTMLResponse)
def job_page_one(request: Request, vin: str, job_id: str, tools_step: str = "",
                 step: str = "") -> HTMLResponse:
    """One specific job by id -- e.g. a closed case from this car's history."""
    return _job_page(request, vin, job_id=job_id, tools_step=tools_step, step=step)


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


@router.post("/v/{vin}/job/{job_id}/tools-review", response_class=HTMLResponse)
async def tools_review_add(request: Request, vin: str, job_id: str) -> RedirectResponse:
    """Step 7: the mandatory "tools used" review -- what was actually used
    at release, right/wrong/unsure with a reason, anything missing, and
    what he'd buy next time. Field names are dynamic (one triplet per
    recommended tool, keyed by tool key) because the recommended-tool list
    itself is dynamic, so this reads the raw form rather than a fixed
    Pydantic/Form model -- same reasoning job_page's tools panel is built
    for a variable-length list.
    """
    form = await request.form()

    def _get(key: str) -> str:
        v = form.get(key)
        return str(v).strip() if v is not None else ""

    step = _get("step") or "diagnostics"
    tools_used: list[dict[str, Any]] = []
    for key in form.keys():
        if key.startswith("used__") and _get(key):
            tool_key = key[len("used__"):]
            tools_used.append({
                "tool": tool_key,
                "was_right": _get(f"right__{tool_key}") or "unsure",
                "note": _get(f"note__{tool_key}"),
            })
    for i in range(1, 4):
        name = _get(f"extra{i}_name")
        if name:
            tools_used.append({
                "tool": name,
                "was_right": _get(f"extra{i}_right") or "unsure",
                "note": _get(f"extra{i}_note"),
            })

    missing_tools = [m.strip() for m in _get("missing_tools").split(",") if m.strip()]

    would_buy: list[dict[str, Any]] = []
    for i in range(1, 4):
        name = _get(f"buy{i}_name")
        if name:
            would_buy.append({"name": name, "why": _get(f"buy{i}_why")})

    time_min_raw = _get("time_min")
    time_min = float(time_min_raw) if time_min_raw else None

    jobs_bridge.add_tool_usage(vin, step, job_id, by=_get("by"), tools_used=tools_used,
                               missing_tools=missing_tools, would_buy=would_buy,
                               time_min=time_min)
    return RedirectResponse(url=f"/v/{vin}/job/{job_id}#outcome", status_code=303)


@router.post("/v/{vin}/job/{job_id}/close", response_class=HTMLResponse)
async def job_close(request: Request, vin: str, job_id: str,
                    outcome: str = Form(...),
                    codes_returned: str = Form(default=""),
                    verdict: str = Form(default=""),
                    tools_review_skip_reason: str = Form(default="")) -> HTMLResponse:
    """Step 7: close the case. Outcome is required -- a job can never be
    closed with no stated result. Also gated on the tools-used review
    (see ``jobs_bridge.close_job``) -- ``tools_review_skip_reason`` lets a
    mechanic close without filling the review, but only by stating why."""
    codes = [c.strip() for c in codes_returned.split(",") if c.strip()]
    error = None
    try:
        jobs_bridge.close_job(job_id, outcome, codes_returned=codes or None,
                              verdict=verdict or None,
                              tools_review_skip_reason=tools_review_skip_reason)
    except BridgeError as exc:
        error = str(exc)
    # Rendered directly (no redirect) -- the close form lives on step 12's
    # screen, so that's the screen the re-render must show, regardless of
    # the flow's own current-step opinion, or a refusal would render onto
    # whatever step happens to be current and never be seen.
    return _job_page(request, vin, job_id=job_id, close_error=error, step="12")


__all__ = ["router"]
