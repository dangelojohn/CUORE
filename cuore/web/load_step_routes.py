"""``GET /v/{vin}/load-step``: the on-screen script for the load-step voltage test.

The page only *shows* the timed script and drives the API
(``/api/live/load-step/start|status|stop|analysis``); the test itself is the
read-only recording in :mod:`cuore.live.load_step`. Rendering the page never
opens the adapter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..live import channels as channels_mod
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/load-step", response_class=HTMLResponse)
def load_step_page(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    spec = channels_mod.recording_presets()["load_step_voltage"]
    reg = channels_mod.registry()
    spec["channel_rows"] = [{"id": c, "present": c in reg,
                             "name": reg[c].name if c in reg else c,
                             "unit": reg[c].unit if c in reg else ""} for c in spec["channels"]]
    response = _page(request, "load_step.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="electrical", spec=spec)
    _set_active_vehicle(response, vin)
    return response
