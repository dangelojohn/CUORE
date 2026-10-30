"""GET /handbook and /handbook/{slug}: the mechanic handbook as pages. Read only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import handbook
from .routes import _active_vehicle, _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/handbook", response_class=HTMLResponse)
def handbook_index(request: Request, vin: str = "") -> HTMLResponse:
    vin = _active_vehicle(request, vin).upper() if vin else ""
    return _page(request, "handbook.html", vin=vin or None, tab="", guides=handbook.guides())


@router.get("/handbook/{slug}", response_class=HTMLResponse)
def handbook_page(request: Request, slug: str, vin: str = "") -> HTMLResponse:
    g = handbook.guide(slug)
    if g is None:
        raise HTTPException(status_code=404, detail="No such guide")
    vin = _active_vehicle(request, vin).upper() if vin else ""
    return _page(request, "handbook_page.html", vin=vin or None, tab="", g=g)
