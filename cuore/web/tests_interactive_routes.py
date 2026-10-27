"""Two Tests-page fragments: the live band + one-tap record, and the test map (cuore/services/tests_interactive.py).

* ``GET /v/{vin}/tests/{id}/live``  the live-band partial as an HTML fragment; unknown test id = 404
* ``GET /v/{vin}/tests/{id}/map``   the test-map partial; unknown test id = 404

Both read saved data and the in-process live snapshot only; nothing here contacts the adapter. Recording goes to
the existing ``POST /v/{vin}/tests/{id}/result`` form route. Importing this module registers the Jinja globals
``tests_live_band(vin, test_id)`` and ``tests_map(vin, test_id)`` so tests.html can include the partials with
``test`` in scope (``test.id``) and no other context.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import tests_interactive
from .routes import templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _token(request: Request) -> str:
    return request.query_params.get("token") or ""


@router.get("/v/{vin}/tests/{test_id}/live", response_class=HTMLResponse)
def tests_live_route(request: Request, vin: str, test_id: str) -> HTMLResponse:
    live = tests_interactive.live_band(vin, test_id, token=_token(request))
    if live is None:
        return HTMLResponse("Unknown test", status_code=404)
    return templates.TemplateResponse(request, "_tests_live.html", {"vin": vin, "test": {"id": test_id}, "tlive": live})


@router.get("/v/{vin}/tests/{test_id}/map", response_class=HTMLResponse)
def tests_map_route(request: Request, vin: str, test_id: str) -> HTMLResponse:
    tmap = tests_interactive.test_map(vin, test_id, token=_token(request))
    if tmap is None:
        return HTMLResponse("Unknown test", status_code=404)
    return templates.TemplateResponse(request, "_tests_map.html", {"vin": vin, "test": {"id": test_id}, "tmap": tmap})


def tests_live_band(vin: str, test_id: str, token: str = "") -> Optional[dict[str, Any]]:
    return tests_interactive.live_band(vin, test_id, token=token)


def tests_map(vin: str, test_id: str, token: str = "") -> Optional[dict[str, Any]]:
    return tests_interactive.test_map(vin, test_id, token=token)


templates.env.globals["tests_live_band"] = tests_live_band
templates.env.globals["tests_map"] = tests_map
