"""The tappable Systems map fragment (cuore/services/systems_interactive.py).

* ``GET /v/{vin}/systems/map?system=KEY``  the map partial as an HTML fragment; no ``system`` = nothing selected;
                                           a key that is not a system in the graph = 404

Reads saved data only; nothing here contacts the adapter. Importing this module also registers the Jinja global
``systems_interactive_map(vin, system)`` so the Systems page can ``{% include "_systems_interactive.html" %}`` with no
extra context (the partial calls it when ``sx`` is not already defined). An unknown ``?system=`` on the page itself
falls back to nothing selected rather than breaking the page.

Router order: ``/v/{vin}/systems/{key}`` (system_routes) would swallow ``/systems/map`` as an unknown system key, so
include this router BEFORE ``system_routes.router``.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import systems_interactive
from .routes import templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _token(request: Request) -> str:
    return request.query_params.get("token") or ""


@router.get("/v/{vin}/systems/map", response_class=HTMLResponse)
def systems_map_route(request: Request, vin: str, system: str = "") -> HTMLResponse:
    sx = systems_interactive.map(vin, system or None, token=_token(request))
    if sx is None:
        return HTMLResponse("Unknown system", status_code=404)
    return templates.TemplateResponse(request, "_systems_interactive.html", {"vin": vin, "sx": sx})


# --- Jinja global for the Systems page ---------------------------------------------------------------

def systems_interactive_map(vin: str, system: Optional[str] = None, token: str = "") -> Optional[dict[str, Any]]:
    sx = systems_interactive.map(vin, system or None, token=token)
    if sx is None and system:
        sx = systems_interactive.map(vin, None, token=token)
    return sx


templates.env.globals["systems_interactive_map"] = systems_interactive_map
