"""Web-form face of the one-car-at-a-time shop flow: start a car, release it.

The mechanic works one Stelvio from start to finish, then starts the next --
no board, no queue, no throughput numbers on a page (those stay in the
store, if written at all). Same posture as ``cuore.web.jobs_routes``: a
second router reusing ``cuore.web.routes``'s own page/dossier helpers, so
rendering stays identical to every other page. Every form here degrades
with no JavaScript -- plain GET/POST/redirect forms, same convention as
``/v/{vin}/job``.

Not registered on the app here -- ``app.py`` is owned by another agent while
this was built. The two lines needed there (next to the other ``web``
router imports, as ``from .web import shop_routes``):

    ``app.include_router(shop_routes.router)``

Page set:

===========================  ==================================================
``/start``                   "Start this Stelvio": VIN + complaint -- intake +
                              open Job -> job page
``/v/{vin}/release``         verified/not with evidence, records the decision
                              and reason, ending in "Tools away" -> ``/start``
===========================  ==================================================
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..services import shop_bridge
from ..services.errors import BridgeError
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/start", response_class=HTMLResponse)
def start_page(request: Request, intake_error: str = "") -> HTMLResponse:
    """"Start this Stelvio": the one-car intake form. VIN prefills from the
    corpus; submitting opens the visit and its linked Job in one step, then
    drops straight into the job page -- the diagnostic work, not a board."""
    return web_routes._page(request, "intake.html",
                            vehicle_choices=shop_bridge.vehicle_choices(),
                            intake_error=intake_error or None)


@router.post("/start", response_class=HTMLResponse)
async def start_submit(request: Request, vin: str = Form(...),
                       complaint: str = Form(default=""),
                       technician: str = Form(default="")) -> HTMLResponse:
    """Intake + open Job in one step, then straight to that car's job page --
    the next thing a mechanic starting a car actually does."""
    try:
        visit = shop_bridge.intake(vin, complaint, technician=technician)
    except BridgeError as exc:
        return start_page(request, intake_error=str(exc))
    return RedirectResponse(url=f"/v/{visit['vin']}/job", status_code=303)


def _release_page(request: Request, vin: str, **extra: Any) -> HTMLResponse:
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    view = shop_bridge.build_release_view_for_vin(vin)
    response = web_routes._page(request, "release.html", vin=vin, bar=bar,
                                view=view, tab="release", **extra)
    web_routes._set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/release", response_class=HTMLResponse)
def release_page(request: Request, vin: str) -> HTMLResponse:
    """The release gate: checklist, dossier verdict, big Release button,
    ending in "Tools away, start the next Stelvio" once released."""
    return _release_page(request, vin)


@router.post("/v/{vin}/release", response_class=HTMLResponse)
async def release_submit(request: Request, vin: str, visit_id: str = Form(...),
                         report_printed: str = Form(default=""),
                         labels_printed: str = Form(default=""),
                         parts_logged: str = Form(default=""),
                         tools_reviewed: str = Form(default=""),
                         notes: str = Form(default=""),
                         reason: str = Form(default="")) -> HTMLResponse:
    """The one-tap Release button. Advises and records -- never blocks on an
    unmet checklist item. ``verified`` is never read from the form: it is
    looked up fresh from the dossier verdict inside the bridge."""
    checks = {
        "report_printed": bool(report_printed), "labels_printed": bool(labels_printed),
        "parts_logged": bool(parts_logged), "tools_reviewed": bool(tools_reviewed),
        "notes": notes,
    }
    error = None
    try:
        shop_bridge.release(visit_id, checks, reason=reason or None)
    except BridgeError as exc:
        error = str(exc)
    return _release_page(request, vin, release_error=error)


@router.post("/v/{vin}/release/tools_away", response_class=HTMLResponse)
async def tools_away_submit(request: Request, vin: str) -> RedirectResponse:
    """The release page's final button: record whatever tools-away state
    the mechanic gave (per-tool put-away/location/not-available, plus a
    restock line) and move on to the next car. Advises and records --
    never blocks, so even a malformed or empty submission still proceeds
    to ``/start``."""
    form = await request.form()
    job_id = (str(form.get("job_id") or "")).strip() or None
    restock = str(form.get("restock") or "").strip()
    put_away: list[dict[str, str]] = []
    not_available: list[dict[str, str]] = []
    i = 0
    while f"tool_{i}" in form:
        tool = str(form.get(f"tool_{i}") or "").strip()
        if tool:
            if form.get(f"put_away_{i}"):
                put_away.append({"tool": tool,
                                "location": str(form.get(f"location_{i}") or "").strip()})
            status = str(form.get(f"not_available_{i}") or "").strip()
            if status:
                not_available.append({"tool": tool, "status": status})
        i += 1
    try:
        shop_bridge.confirm_tools_away(vin, job_id, put_away, restock, not_available)
    except Exception:  # noqa: BLE001 -- advise, never block the next car
        pass
    return RedirectResponse(url="/start", status_code=303)


__all__ = ["router"]
