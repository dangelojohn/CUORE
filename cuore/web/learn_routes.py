"""``GET /v/{vin}/learn`` -- the signal-learning workbench.

Pick a bus (CAN-IHS or CAN-CH, whichever bypass cable is fitted), press
Start, perform one named physical action for a few seconds (press the
brake pedal, turn the wheel, open the driver door, switch the HVAC fan),
Stop. The page shows ranked ``(CAN id, byte offset)`` candidates -- the
bytes that changed the most while the action was held -- and lets the
mechanic name the best one and save it.

Reaches the same vehicle-page plumbing ``cuore/web/liveboard_routes.py``
does (``_page``, ``_dossier``, ``_vehicle_bar`` from ``cuore.web.routes``).
This module renders the page shell only; the Start/Stop/rank/accept flow
is client-side, in ``cuore/web/static/liveboard.js``, talking to
``/api/buscapture/{bus}/learn/*`` (``cuore/api/buscapture.py``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..live.buses import BUSES
from ..services import shop_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

#: Server-rendered page: same posture as ``cuore.web.liveboard_routes.router``.
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: Buses worth learning signals on from this page -- CAN-C is already fully
#: covered by the DID catalogue and the guided DTC sweep; a bypass cable is
#: what makes CAN-IHS/CAN-CH worth listening to at all.
LEARNABLE_BUSES = [BUSES["can_ihs"], BUSES["can_ch"]]

#: Suggested physical actions per bus -- named here, shown as buttons on the
#: page; the mechanic can still type a custom action in the free-text field.
SUGGESTED_ACTIONS: dict[str, list[str]] = {
    "can_ihs": ["switch the HVAC fan", "open the driver door", "flash the turn signal"],
    "can_ch": ["press the brake pedal", "turn the wheel"],
}


@router.get("/v/{vin}/learn", response_class=HTMLResponse)
def learn_page(request: Request, vin: str) -> HTMLResponse:
    """The signal-learning workbench: bus picker, action buttons, Start/Stop,
    ranked candidates, name-and-save."""
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    bar["name"] = shop_bridge.resolve_vehicle_name(vin) or bar["name"]
    buses = [{"key": b.key, "name": b.name, "suggested_actions": SUGGESTED_ACTIONS.get(b.key, [])}
            for b in LEARNABLE_BUSES]
    response = _page(request, "learn.html", vin=vin, bar=bar, buses=buses)
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
