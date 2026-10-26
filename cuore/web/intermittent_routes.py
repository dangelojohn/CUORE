"""Intermittent-fault correlator routes.

* ``GET /v/{vin}/intermittent``            overview: every code / symptom with events
* ``GET /v/{vin}/intermittent/{code}``     one code (``U0100``) or symptom tag (``noise``)
* ``GET /api/vehicles/{vin}/intermittent/{code}``   the same result as JSON

The logic lives in :mod:`cuore.services.intermittent`. Nothing here touches
the car. Importing this module also registers the Jinja global
``intermittent_panel(vin, code)`` so ``_intermittent_panel.html`` can be
included from the code page or the job page with only ``vin`` and ``code``
in scope.

Not registered on the app here (``cuore/app.py`` is owned elsewhere). Add::

    from .web import intermittent_routes
    app.include_router(intermittent_routes.router)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import intermittent
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: Lets a template write ``{% set im = intermittent_panel(vin, code) %}``.
_shared_templates.env.globals["intermittent_panel"] = intermittent.panel


@router.get("/v/{vin}/intermittent", response_class=HTMLResponse)
def intermittent_overview(request: Request, vin: str) -> HTMLResponse:
    data = intermittent.overview(vin)
    response = _page(request, "intermittent.html", vin=vin, mode="overview", ov=data, im=None,
                     bar=_vehicle_bar(vin, _dossier(vin)), tab="intermittent")
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/intermittent/{code}", response_class=HTMLResponse)
def intermittent_code(request: Request, vin: str, code: str) -> HTMLResponse:
    result = intermittent.analyze(vin, code)
    response = _page(request, "intermittent.html", vin=vin, mode="one", ov=None, im=result,
                     code=result["subject"]["key"], bar=_vehicle_bar(vin, _dossier(vin)),
                     tab="intermittent")
    _set_active_vehicle(response, vin)
    return response


@router.get("/api/vehicles/{vin}/intermittent/{code}", include_in_schema=True,
            summary="Conditions shared by a code's set events (or a symptom's occurrences)")
def intermittent_json(vin: str, code: str) -> dict[str, Any]:
    result = intermittent.analyze(vin, code)
    # Each line already names its events by id; do not repeat their bodies.
    for key in ("lines", "never"):
        result[key] = [{k: v for k, v in r.items() if k != "events"} for r in result[key]]
    return result


__all__ = ["router"]
