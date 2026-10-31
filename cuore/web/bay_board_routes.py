"""GET /bay: the shop-wide Bay board. Read-only; reads CUORE's own stores, never the car or the adapter."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import bay_board
from .routes import _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/bay", response_class=HTMLResponse)
def bay_board_page(request: Request) -> HTMLResponse:
    resp = _page(request, "bay_board.html", board=bay_board.build(), live_strip=None)
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp
