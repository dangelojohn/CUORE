"""The module-tree pages: ``/v/{vin}/modules`` and ``/v/{vin}/modules/{code}``.

MultiEcuScan shows a vehicle as a tree of modules, each with Info, Errors,
Parameters, Actuators and Adjustments tabs. These two pages are CUORE's
read of the same tree, backed entirely by ``cuore.services.modules_bridge``
(see that module for where every field comes from).

Kept as a second router rather than added to ``cuore.web.routes``, same
posture as ``dossier_routes.py``: it reuses that module's own page/dossier
helpers (``_page``, ``_dossier``, ``_vehicle_bar``, ``_set_active_vehicle``)
so rendering never forks from the rest of the ``/v/`` surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import modules_bridge
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/modules", response_class=HTMLResponse)
def vmodules(request: Request, vin: str) -> HTMLResponse:
    """The module tree: one row per module, status chips, counts."""
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    rows = modules_bridge.list_modules(vin)
    response = web_routes._page(request, "vmodules.html", vin=vin, bar=bar,
                                rows=rows, tab="modules")
    web_routes._set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/modules/{code}", response_class=HTMLResponse)
def vmodule_detail(request: Request, vin: str, code: str) -> HTMLResponse:
    """One module's tabs: errors, parameters, actuators, adjustments, info."""
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    detail = modules_bridge.module_detail(vin, code)
    response = web_routes._page(request, "vmodule.html", vin=vin, bar=bar,
                                m=detail, tab="modules")
    web_routes._set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
