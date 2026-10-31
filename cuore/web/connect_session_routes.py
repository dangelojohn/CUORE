"""``/v/{vin}/connect-session``: the guided one-screen connection session (Alfa cars; the brand gate
keeps Maserati and Ferrari out). All reading lives in :mod:`cuore.live.connect_session`; this module
renders the session and relays the person's button presses. Reads only."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..live import connect_session as cs
from .fullscan_routes import _bar
from .routes import _page, _set_active_vehicle

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _back(vin: str, msg: str = "") -> RedirectResponse:
    return RedirectResponse(f"/v/{vin}/connect-session" + (f"?msg={quote(msg)}" if msg else ""), status_code=303)


@router.get("/v/{vin}/connect-session", response_class=HTMLResponse)
def connect_session_page(request: Request, vin: str, msg: str = "") -> HTMLResponse:
    st = cs.current(vin)
    nxt = cs.next_step(st)
    steps = []
    for s in cs.STEPS:
        ss = st["steps"][s["id"]]
        last = ss["runs"][-1] if ss["runs"] else None
        keys = set(last["items"]) if last else set()
        steps.append({**s, "status": ss["status"], "blocked": cs.blocked_reason(st, s["id"], confirm=True),
                      "items": [i for k, i in st["items"].items() if k in keys],
                      "last": last, "is_next": s["id"] == nxt})
    response = _page(request, "connect_session.html", vin=vin, bar=_bar(vin), tab="connect-session",
                     st=st, steps=steps, msg=msg, min_volts=cs.MIN_VOLTS, summary=cs.summary(st))
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/connect-session/run")
def connect_session_run(vin: str, step: str = Form(...), confirm: str = Form(default="")) -> RedirectResponse:
    if step not in cs.STEP_BY_ID:
        return _back(vin, "unknown step")
    r = cs.run_step(vin, step, confirm=bool(confirm))
    return _back(vin, ("Not run: " + r["reason"]) if r["refused"] else "")


@router.post("/v/{vin}/connect-session/cable")
def connect_session_cable(vin: str, cable: str = Form(...)) -> RedirectResponse:
    try:
        cs.confirm_cable(vin, cable)
    except ValueError as e:
        return _back(vin, str(e))
    return _back(vin)


@router.post("/v/{vin}/connect-session/skip")
def connect_session_skip(vin: str, step: str = Form(...)) -> RedirectResponse:
    if step in cs.STEP_BY_ID:
        cs.skip(vin, step)
    return _back(vin)


@router.post("/v/{vin}/connect-session/resume")
def connect_session_resume(vin: str) -> RedirectResponse:
    cs.resume(vin)
    return _back(vin)


@router.post("/v/{vin}/connect-session/new")
def connect_session_new(vin: str) -> RedirectResponse:
    cs.start_new(vin)
    return _back(vin)


@router.post("/v/{vin}/connect-session/finish")
def connect_session_finish(vin: str) -> RedirectResponse:
    cs.finish(vin)
    return RedirectResponse(f"/v/{vin}/connect-session/summary", status_code=303)


@router.get("/v/{vin}/connect-session/summary", response_class=HTMLResponse)
def connect_session_summary(request: Request, vin: str) -> HTMLResponse:
    st = cs.latest(vin) or cs.current(vin)
    response = _page(request, "connect_summary.html", vin=vin, bar=_bar(vin), tab="connect-session",
                     sm=cs.summary(st))
    _set_active_vehicle(response, vin)
    return response
