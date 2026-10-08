"""``GET /v/{vin}/liveboard`` -- the passenger-seat live gauge board.

One surface, read from a moving car at a glance: every channel CUORE knows
about for this vehicle, grouped by system, as a big digital readout coloured
by how far out of band it is -- no hero, no tabs, nothing that needs a
second look to find.

Reaches the same vehicle-page plumbing ``cuore/web/live_dashboard_routes.py``
does (``_page``, ``_dossier``, ``_vehicle_bar`` from ``cuore.web.routes``),
read-only, and adds no new template environment -- ``static_url``/``icon``/
``t`` are already registered on that shared one. This module renders the
page shell only; everything about the board's *behaviour* is client-side, in
``cuore/web/static/liveboard.js``, talking to two surfaces this module never
touches:

* the existing live poll/stream/snapshot engine at ``/api/live/*``
  (``cuore/api/live.py``, ``cuore/api/live_ui.py``);
* the liveboard data contract at ``/api/liveboard/*`` -- ``GET
  /api/liveboard/{vin}`` (groups/channels/bands) and ``POST
  /api/liveboard/evaluate`` (recommendations) -- built in parallel by
  another agent against the same contract this module and its script were
  written against. ``liveboard.js`` carries its own client-side fixture and
  falls back to it if that endpoint isn't there yet (or errors), so this
  page works in Demo mode whether or not the data API has landed.

Deliberately does *not* include ``_vbar.html`` (see ``liveboard.html``'s
``vehiclebar`` block): that partial's hero and tab row are exactly the
chrome this single-purpose cockpit view skips in favour of its own compact
40px status line, built client-side so it can also show session state and
a live "updated Ns ago". The link into this page from the rest of the app
(nav, vehicle page, wherever) is added later, by another agent -- this
module and its template don't add one themselves, and nothing outside this
file list is touched to get here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

#: Server-rendered page: same posture as ``cuore.web.routes.router`` and
#: ``cuore.web.live_dashboard_routes.router``.
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/liveboard", response_class=HTMLResponse)
def liveboard_page(request: Request, vin: str) -> HTMLResponse:
    """The passenger-seat live gauge board: status line, big buttons, groups
    of digital channel readouts, a Problems strip up top."""
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    response = _page(request, "liveboard.html", vin=vin, bar=bar)
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
