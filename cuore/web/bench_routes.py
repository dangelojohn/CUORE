"""The bench: ``GET /v/{vin}``, the screen a mechanic sees the instant a car
lands on the lift.

Kept as its own router, same posture as ``cuore/web/dossier_routes.py``
(see that file's own docstring): the old dossier owned ``/v/{vin}`` until
this landed, and still owns everything else under ``/v/{vin}/*`` --
``cuore/web/routes.py``'s own ``/v/{vin}`` handler was moved to
``/v/{vin}/dossier`` to make room for this one, rather than this file
reaching into that module's handler.

This page writes nothing new of its own -- its only form is the same
``POST /v/{vin}/checklist`` the dossier's open-work cards already post to
(``cuore/web/dossier_routes.py``), reused as-is so ticking a step from the
bench and ticking it from the full dossier land in the exact same store.
"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from fastapi import APIRouter

from ..api.deps import require_token
from ..services import bench_bridge
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}", response_class=HTMLResponse)
def bench_page(request: Request, vin: str) -> HTMLResponse:
    """What to do right now: the verdict's next action, the top three open
    steps (each with its parts and tools already resolved), and jump-off
    points to the codes, the job and the full dossier."""
    bench = bench_bridge.build_bench(vin)
    response = web_routes._page(request, "bench.html", vin=vin, bench=bench,
                                tab="bench")
    web_routes._set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
