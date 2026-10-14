"""``/v/{vin}/scan`` -- the guided full-scan wizard.

The garage's bypass cables have to be swapped by hand mid-scan (blue A5 for
CAN-IHS, grey A6 for CAN-CH); this page is what makes that feel like one
continuous scan instead of three separate ones the mechanic has to restart.
Every actual read, every bit of state, and the whole pause/resume machinery
live in :mod:`cuore.live.fullscan` (``run_guided``/``continue_guided``/
``skip_guided``/``abandon_guided``) -- this module only renders that state
and relays the four actions as plain form posts.

Same posture as ``cuore/web/tests_routes.py``/``cuore/web/scan_health_routes.py``:
a second router over ``cuore.web.routes``'s own ``_page``/``_dossier``/
``_vehicle_bar`` helpers, so this page looks and behaves like every other
``/v/{vin}`` page (same vehicle bar, same tab strip, same error handling --
a ``BridgeError`` raised from ``fullscan.py`` is rendered by ``cuore.app``'s
own exception handler exactly as it is everywhere else).

Works without JS: every POST here is a plain ``<form>`` that redirects
(303) straight back to the GET page, which always renders whatever phase
the persisted guided-scan state says it's in. ``cuore/web/static/fullscan.js``
only adds a "Working..." busy state on the button that is about to block for
a real adapter read, and a 1.5s poll of the state endpoint while a pause
card is showing (so this screen notices if the MCP tools or a second tab
moved the same session on, and reloads to match) -- neither changes what
gets POSTed or rendered.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..live import fullscan
from ..services import shop_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

#: Server-rendered page: same posture as cuore.web.routes.router and
#: cuore.web.tests_routes.router.
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _bar(vin: str) -> dict:
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    bar["name"] = shop_bridge.resolve_vehicle_name(vin) or bar["name"]
    return bar


def _phase(state: dict) -> str:
    """Which of the wizard's screens to render: ``idle`` (nothing open, or
    the last session was abandoned -- either way, offer Start), ``pause_blue``
    / ``pause_grey`` / ``remove_cable`` (paused, waiting on that step), or
    ``summary`` (the session finished)."""
    status = state.get("status")
    if status == "done":
        return "summary"
    if status != "paused":
        return "idle"
    nxt = state.get("next") or {}
    cable = nxt.get("cable")
    if cable == "blue_a5":
        return "pause_blue"
    if cable == "grey_a6":
        return "pause_grey"
    return "remove_cable"  # the closing step: next.cable == "none"


def _state_for(vin: str) -> dict:
    """The open guided scan, but only if it belongs to this VIN -- a session
    started for a different car on the bench must never bleed onto this
    page, same as every other ``/v/{vin}`` surface stays scoped to its own
    vehicle."""
    state = fullscan.guided_state()
    if state.get("vin") and state["vin"] != vin:
        return {"scan_id": None, "status": None, "note": "no guided scan is open"}
    return state


@router.get("/v/{vin}/scan", response_class=HTMLResponse)
def scan_page(request: Request, vin: str) -> HTMLResponse:
    state = _state_for(vin)
    response = _page(request, "fullscan.html", vin=vin, bar=_bar(vin), tab="scan",
                     state=state, phase=_phase(state))
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/scan/start", response_class=HTMLResponse)
def scan_start(request: Request, vin: str) -> HTMLResponse:
    fullscan.run_guided(vin)
    return RedirectResponse(url=f"/v/{vin}/scan", status_code=303)


@router.post("/v/{vin}/scan/continue", response_class=HTMLResponse)
def scan_continue(request: Request, vin: str, scan_id: str = Form(...),
                  cable_fitted: str = Form(...)) -> HTMLResponse:
    fullscan.continue_guided(scan_id, cable_fitted)
    return RedirectResponse(url=f"/v/{vin}/scan", status_code=303)


@router.post("/v/{vin}/scan/skip", response_class=HTMLResponse)
def scan_skip(request: Request, vin: str, scan_id: str = Form(...)) -> HTMLResponse:
    fullscan.skip_guided(scan_id)
    return RedirectResponse(url=f"/v/{vin}/scan", status_code=303)


@router.post("/v/{vin}/scan/abandon", response_class=HTMLResponse)
def scan_abandon(request: Request, vin: str, scan_id: str = Form(...)) -> HTMLResponse:
    fullscan.abandon_guided(scan_id)
    return RedirectResponse(url=f"/v/{vin}/scan", status_code=303)


__all__ = ["router"]
