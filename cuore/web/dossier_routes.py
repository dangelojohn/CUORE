"""Web-form face of the checklist store, and the "Verify repair" page.

Kept as a second router rather than added to ``cuore.web.routes`` so the
template agent's work on that module's templates and this file's own routes
do not collide while both are being built at once. It reuses ``routes``'s
own page/dossier helpers (``_page``, ``_dossier``, ``_vehicle_bar``,
``_status_strip``, ``_set_active_vehicle``) so rendering stays identical --
this is a second router on the same app, not a second implementation of the
dossier.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..live import checklists as checklist_store
from ..live import ops as live_ops
from ..live.errors import LiveError
from ..api.deps import require_token
from ..services import dossier_bridge
from ..services.errors import BadRequest
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

_TRUE = ("1", "true", "on", "yes")


@router.post("/v/{vin}/checklist", response_class=HTMLResponse)
async def checklist_submit(request: Request, vin: str,
                           step_id: str = Form(...),
                           done: str = Form(default=""),
                           by: str = Form(default="")) -> RedirectResponse:
    """Tick (or untick) one checklist step from the dossier page's own form.
    No JavaScript required -- same posture as ``/v/{vin}/dealer`` and
    ``/v/{vin}/notes``. Validated the same way the JSON API validates it: a
    step id this car's open-work cards do not expose is a 400."""
    dossier = web_routes._dossier(vin)
    valid = dossier_bridge.checklist_step_ids(vin, dossier)
    if step_id not in valid:
        raise BadRequest(f"unknown checklist step id {step_id!r} for this vehicle")
    checklist_store.set_step(vin, step_id, done.strip().lower() in _TRUE, by=by)
    return RedirectResponse(url=f"/v/{vin}#open-work", status_code=303)


@router.get("/v/{vin}/verify", response_class=HTMLResponse)
def verify_form(request: Request, vin: str) -> HTMLResponse:
    """Read live readiness, if the adapter is reachable, and show the
    recomputed verdict. A read, never a write: ``ops.obd_readiness`` is
    Mode 01 PID 01/41 plus the drive-cycle counters, nothing more -- and it
    records its own observation, which is what lets the verdict change."""
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    live_status = web_routes._status_strip()

    result = None
    if dossier_bridge.live_available(live_status):
        try:
            result = dossier_bridge.readiness_result(live_ops.obd_readiness())
        except LiveError:
            result = None

    view = dossier_bridge.build_view(vin, dossier, live_status)
    response = web_routes._page(request, "verify.html", vin=vin, result=result,
                                verdict=view["verdict"], bar=bar, tab="dossier")
    web_routes._set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
