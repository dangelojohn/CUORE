"""wiTECH recording page. Listen-only: no route here transmits or writes anything.

GET  /v/{vin}/witech-recording            page
POST .../declare-splitter | start | stop | draft   (declare, passive record, stop+save, decode to draft)
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..live import buscapture, witech_recording as wr
from ..live.errors import BadCommand, Refused
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _back(vin: str, msg: str, kind: str = "ok") -> RedirectResponse:
    return RedirectResponse(f"/v/{vin}/witech-recording?msg={quote(msg)}&kind={kind}", status_code=303)


@router.get("/v/{vin}/witech-recording", response_class=HTMLResponse)
def witech_page(request: Request, vin: str, msg: str = "", kind: str = "ok") -> HTMLResponse:
    dossier = _dossier(vin)
    try:
        sess = wr.status()
        sess = sess if sess.get("purpose") == "witech" else None
    except BadCommand:
        sess = None
    recs = []
    for r in wr.list_recordings():
        full = wr.load_recording(r["id"])
        recs.append({**r, "rows": wr.transcript(full), "drafts": wr.list_drafts(r["id"])})
    response = _page(request, "witech_recording.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="adjustments", cable=buscapture.cable_header()["cable"], session=sess,
                     recordings=recs, checklist=wr.CHECKLIST, flash_msg=msg, flash_kind=kind)
    _set_active_vehicle(response, vin)
    return response


def _do(vin: str, fn, ok: str) -> RedirectResponse:
    try:
        fn()
    except (Refused, BadCommand) as e:
        return _back(vin, str(e), "err")
    return _back(vin, ok)


@router.post("/v/{vin}/witech-recording/declare-splitter")
def declare(vin: str) -> RedirectResponse:
    return _do(vin, wr.declare_splitter, "Splitter declared. CAN-C is listen-only.")


@router.post("/v/{vin}/witech-recording/start")
def start(vin: str, function: str = Form("")) -> RedirectResponse:
    return _do(vin, lambda: wr.start(function), "Listening (passive). Run the function in wiTECH now.")


@router.post("/v/{vin}/witech-recording/stop")
def stop(vin: str) -> RedirectResponse:
    def _go():
        wr.stop()
        wr.save(vin)
    return _do(vin, _go, "Stopped and saved.")


@router.post("/v/{vin}/witech-recording/draft")
def draft(vin: str, recording: str = Form("")) -> RedirectResponse:
    return _do(vin, lambda: wr.make_draft(recording), "Draft procedure(s) saved (not executable).")
