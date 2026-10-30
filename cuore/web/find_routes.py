"""GET /find?q=&vin= : site-wide search for a mechanic who is lost. Read only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import find
from .routes import _active_vehicle, _page, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/find", response_class=HTMLResponse)
def find_page(request: Request, q: str = "", vin: str = "") -> HTMLResponse:
    vin = _active_vehicle(request, vin).upper() if (vin or q) else ""
    user = getattr(request.state, "user", None)
    res = find.search(q, vin, getattr(user, "role", None) if user else None)
    return _page(request, "find.html", vin=vin or None, tab="", res=res, q=res["q"])
