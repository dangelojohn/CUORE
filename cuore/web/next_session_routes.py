"""``/v/{vin}/next-session`` -- the plan for the next time the car is connected."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..services import next_session, shop_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/next-session", response_class=HTMLResponse)
def next_session_page(request: Request, vin: str) -> HTMLResponse:
    bar = _vehicle_bar(vin, _dossier(vin))
    bar["name"] = shop_bridge.resolve_vehicle_name(vin) or bar["name"]
    response = _page(request, "next_session.html", vin=vin, bar=bar, tab="scans",
                     ns=next_session.view(vin))
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/next-session/{step_id}")
def next_session_mark(vin: str, step_id: str, action: str = Form("done"),
                      return_to: str = Form("")) -> RedirectResponse:
    next_session.mark(vin, step_id, action != "undo")
    allowed = (f"/v/{vin}", f"/v/{vin}/next-session")
    dest = return_to if return_to in allowed else f"/v/{vin}/next-session"
    return RedirectResponse(dest, status_code=303)


__all__ = ["router"]
