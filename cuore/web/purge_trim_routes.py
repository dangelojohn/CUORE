"""``GET /v/{vin}/purge-trim``: the on-screen script for the passive purge-trim EVAP test.

The page only *shows* the script and live values and drives the API
(``/api/live/purge-trim/start|status|stop|analysis``); the test itself is the
read-only recording in :mod:`cuore.live.purge_trim`. Rendering the page never
opens the adapter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..live import channels as channels_mod
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/purge-trim", response_class=HTMLResponse)
def purge_trim_page(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    spec = channels_mod.recording_presets()["purge_trim"]
    reg = channels_mod.registry()
    spec["channel_rows"] = [{"id": c, "present": c in reg,
                             "name": reg[c].name if c in reg else c,
                             "unit": reg[c].unit if c in reg else ""} for c in spec["channels"]]
    response = _page(request, "purge_trim.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="gauges", spec=spec)
    _set_active_vehicle(response, vin)
    return response
