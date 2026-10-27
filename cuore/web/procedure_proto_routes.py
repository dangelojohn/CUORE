"""PROTOTYPE interactive-procedure screens: /v/{vin}/procedures/prototype[/{proc}].

Runs ONLY against the simulated car in :mod:`cuore.services.procedure_sim`. Nothing here imports or calls the
live adapter layer; nothing is sent to the Stelvio. Stop is a plain form POST; live numbers come from a server
event stream (native EventSource) and the server stops the run when the stream drops.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

import secrets

from ..api.deps import require_token, session_id
from ..services import procedure_sim as sim
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


CTL_COOKIE = "cuore_ctl"


def _cid(request: Request) -> tuple[str, bool]:
    """This screen's controller id: the login session id, else a per-browser random cookie. (id, is_new)."""
    sid = session_id(request)
    if sid:
        return "s:" + sid, False
    c = request.cookies.get(CTL_COOKIE)
    return ("c:" + c, False) if c else ("c:" + secrets.token_urlsafe(12), True)


def _stamp(resp, cid: str, new: bool):
    if new:
        resp.set_cookie(CTL_COOKIE, cid[2:], max_age=30 * 24 * 3600, httponly=True, samesite="lax", path="/")
    return resp


def _base(vin: str) -> str:
    return f"/v/{vin}/procedures/prototype"


def _back(vin: str, proc: str, msg: str = "", run: str = "") -> RedirectResponse:
    q = [f"{k}={quote(v)}" for k, v in (("run", run), ("msg", msg)) if v]
    return RedirectResponse(f"{_base(vin)}/{proc}" + ("?" + "&".join(q) if q else ""), status_code=303)


def _known(proc: str) -> bool:
    return proc in sim.PROCS


@router.get("/v/{vin}/procedures/prototype", response_class=HTMLResponse)
def proto_list(request: Request, vin: str) -> HTMLResponse:
    sim.reap()
    procs = [{"key": k, "title": p["title"], "blurb": p["blurb"], "module": p["module"], "bus": p["bus"],
              "ready": sim.readiness(k)["ready"]} for k, p in sim.PROCS.items()]
    response = _page(request, "procedure_proto_list.html", vin=vin, bar=_vehicle_bar(vin, _dossier(vin)), tab="procedures",
                     base=_base(vin), procs=procs, banner=sim.BANNER)
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/procedures/prototype/{proc}", response_class=HTMLResponse)
def proto_page(request: Request, vin: str, proc: str, run: str = "", msg: str = "") -> HTMLResponse:
    if not _known(proc):
        return HTMLResponse("Unknown prototype procedure", status_code=404)
    sim.reap()
    p = sim.PROCS[proc]
    r = sim.RUNS.get(run) if run else sim.active_run()
    if r is not None and r.proc != proc:
        r = None
    cid, new = _cid(request)
    view = "setup"
    snap = None
    if r is not None:
        snap = r.snapshot()
        view = "running" if r.state == "running" else "after"
    rd = sim.readiness(proc)
    token = sim.mint_token(proc) if view == "setup" else None
    job = sim.open_job(vin, proc)
    word = (r.result or {}).get("word") if r and r.result else ""
    evidence = {"WORKED": "FOR", "DIDN'T": "AGAINST"}.get(word, "neither for nor against")
    ctx = dict(vin=vin, bar=_vehicle_bar(vin, _dossier(vin)), tab="procedures", base=_base(vin), proc=proc, p=p, banner=sim.BANNER,
               view=view, run=r, snap=snap, rd=rd, token=token, job=job, msg=msg, faults=sim.FAULTS,
               active_faults=sorted(sim.CAR.faults), evidence=evidence, max_run=int(sim.MAX_RUN),
               ctl=(r is not None and r.owner == cid))
    response = _page(request, "procedure_proto.html", **ctx)
    _set_active_vehicle(response, vin)
    return _stamp(response, cid, new)


@router.post("/v/{vin}/procedures/prototype/{proc}/recheck")
def proto_recheck(vin: str, proc: str, ask: list[str] = Form(default=[])) -> RedirectResponse:
    if not _known(proc):
        return RedirectResponse(_base(vin), status_code=303)
    for a in ask:
        sim.answer(a, True)
    return _back(vin, proc)


@router.post("/v/{vin}/procedures/prototype/{proc}/sim")
def proto_sim(vin: str, proc: str, fault: str = Form(default=""), clear: str = Form(default="")) -> RedirectResponse:
    if clear:
        sim.CAR.reset()
    elif fault in sim.FAULTS:
        sim.CAR.toggle(fault)
    sim.reap()
    return _back(vin, proc) if _known(proc) else RedirectResponse(_base(vin), status_code=303)


@router.post("/v/{vin}/procedures/prototype/{proc}/start")
def proto_start(request: Request, vin: str, proc: str, token: str = Form(default="")) -> RedirectResponse:
    if not _known(proc):
        return RedirectResponse(_base(vin), status_code=303)
    cid, new = _cid(request)
    run, why = sim.start(proc, token, owner=cid)
    if run is None:
        return _stamp(_back(vin, proc, msg=why), cid, new)
    return _stamp(_back(vin, proc, run=run.id), cid, new)


@router.post("/v/{vin}/procedures/prototype/{proc}/stop")
def proto_stop(vin: str, proc: str, run: str = Form(default="")) -> RedirectResponse:
    sim.stop(run, "stop")
    return _back(vin, proc, run=run) if _known(proc) else RedirectResponse(_base(vin), status_code=303)


@router.get("/v/{vin}/procedures/prototype/{proc}/stream")
def proto_stream(request: Request, vin: str, proc: str, run: str = "") -> StreamingResponse:
    r = sim.RUNS.get(run)
    viewer = r is not None and r.owner != _cid(request)[0]
    return StreamingResponse(sim.stream_events(run, viewer=viewer), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
