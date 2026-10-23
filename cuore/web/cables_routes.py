"""``GET /cables``: the adapter-cable catalogue page (read-only).

External reference, not a CUORE reading. Marks which cables CUORE can drive
live (blue A5, grey A6) and which it cannot (everything else).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import adapter_cables_bridge
from .routes import _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/cables", response_class=HTMLResponse)
def cables_page(request: Request, brand: str = "") -> HTMLResponse:
    return _page(request, "cables.html", live_strip=None, data=adapter_cables_bridge.payload(brand),
                 brand=brand)
