"""``GET /v/{vin}/learn-mes`` -- the MES-learn review workbench.

Fit a second adapter on a Y-splitter on CAN-C, name its port, press Start,
let MultiEcuScan run its own live view and record a CSV, Stop, point this
page at that CSV. Every named column MES graphed is fit against every
module/DID this listener overheard; the candidates that cleared the
confidence bar are listed with their fit numbers (R², scale, offset, sample
count) for Accept/Reject.

Reaches the same vehicle-page plumbing ``cuore/web/liveboard_routes.py`` and
``cuore/web/learn_routes.py`` do (``_page``, ``_dossier``, ``_vehicle_bar``
from ``cuore.web.routes``). This module renders the page shell only; the
Start/Stop/candidates/accept/reject flow is client-side, talking to
``/api/mes-learn/*`` (``cuore/api/mes_learn.py``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..live import mes_learn
from ..services import shop_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

#: Server-rendered page: same posture as ``cuore.web.learn_routes.router``.
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/learn-mes", response_class=HTMLResponse)
def learn_mes_page(request: Request, vin: str) -> HTMLResponse:
    """The MES-learn review workbench: Start/Stop on a second adapter, the
    CSV to align against, ranked fit candidates, Accept/Reject."""
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    bar["name"] = shop_bridge.resolve_vehicle_name(vin) or bar["name"]
    response = _page(request, "mes_learn.html", vin=vin, bar=bar,
                     review=mes_learn.latest_review(vin))
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
