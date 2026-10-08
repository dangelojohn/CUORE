"""``GET /v/{vin}/systems/{key}`` -- phase 1 of the Systems dive-in: one
page per vehicle system (all 25 keys ``systems_bridge.systems()`` knows),
reached from each cell of the existing ``/v/{vin}/systems`` map.

Same posture as :mod:`cuore.web.systems_routes` (built the same pass):
a separate router, reusing ``_dossier``/``_page``/``_set_active_vehicle``/
``_vehicle_bar`` from :mod:`cuore.web.routes` by import rather than
duplicating that plumbing. The whole view model lives in
:mod:`cuore.services.system_detail_bridge` (``build_system_view(vin,
key)``) -- this module only turns that dict into a response and 404s an
unknown key.

Importing :mod:`cuore.web.systems_routes` here (not just its router) is
the side effect that matters: that module registers the ``systems_for_code``
and ``system_label`` Jinja globals on both template environments this
feature touches (see its own docstring) -- the same
Jinja-global-via-import-side-effect pattern :mod:`cuore.web.liveboard_routes`
and :mod:`cuore.web.parts_routes` already use, done here just by importing
the module that already does it rather than re-registering anything.

Not registered on the app here if ``app.py`` has not picked it up yet --
every test below includes this router itself first, the same guard
``cuore/tests/check_systems_page.py`` uses.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import system_detail_bridge
from . import systems_routes  # noqa: F401 -- side effect: registers Jinja globals
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/systems/{key}", response_class=HTMLResponse)
def system_detail_page(request: Request, vin: str, key: str) -> HTMLResponse:
    """One system's dive-in: status strip, relationship ring, components
    placed, how it fails here, hypotheses, what this car has taught,
    others' experience, and what else to look at next.

    404s (as a normal error page, via the existing ``BridgeError``/
    ``HTTPException`` machinery ``app.py`` already wires up) for any key
    not in ``systems_bridge.systems()`` -- never a blank or guessed page
    for a mistyped or retired system key.
    """
    view = system_detail_bridge.build_system_view(vin, key)
    if view is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"unknown system key: {key!r}")
    dossier = _dossier(vin)
    response = _page(request, "system.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="systems", view=view)
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
