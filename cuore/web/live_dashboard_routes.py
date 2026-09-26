"""``GET /v/{vin}/gauges`` and ``GET /v/{vin}/gauges/hud`` -- the customizable
live-data dashboard.

Reaches the vehicle-page plumbing already in :mod:`cuore.web.routes` --
``_page``, ``_dossier``, ``_vehicle_bar`` and ``_set_active_vehicle`` -- the
same way :mod:`cuore.web.dashboard_routes` does, read-only: this module adds
no page-rendering machinery of its own, and it is not registered in
``cuore/app.py`` by this change -- see the module docstring note below.

Everything about the dashboard's *behaviour* lives client-side, in
``cuore/web/static/live/dashboard.js``, talking straight to two other
surfaces this module never touches:

* the existing live poll/stream engine already mounted at ``/api/live/*``
  (``cuore/api/live.py`` -- channels, session start/stop, stream, snapshot,
  record, alarms);
* the dashboard's own layout/replay/custom-channel/snapshot/trigger routes,
  also under ``/api/live/*`` (``cuore/api/live_ui.py``, built in parallel by
  another agent against the same contract this module was written against).

This router only renders the page shell those scripts mount into. The HUD
route deliberately does *not* extend ``base.html`` -- HUD mode is a black,
chrome-free full screen, and the shared page chrome (top nav, vehicle bar,
footer, keyboard-help panel) has no ``{% block %}`` seam to opt out of, so
building it as a small standalone document here is the least invasive way to
get a bare canvas without touching a template outside this feature.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

#: Server-rendered pages: same posture as ``cuore.web.routes.router`` and
#: ``cuore.web.dashboard_routes.router``. NOT yet included by ``cuore/app.py``
#: -- see this module's docstring and the build report for the one
#: ``app.include_router(...)`` line that still needs adding there.
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/gauges", response_class=HTMLResponse)
def gauges_page(request: Request, vin: str) -> HTMLResponse:
    """The customizable live-data dashboard: toolbar, page tabs, widget grid."""
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    response = _page(request, "live_dashboard.html", vin=vin, bar=bar, tab="gauges")
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/gauges/hud", response_class=HTMLResponse)
def gauges_hud_page(request: Request, vin: str) -> HTMLResponse:
    """Full-screen HUD mode: black background, up to four large mirrored gauges.

    A standalone document (see the module docstring for why) rather than a
    second Jinja template -- the whole thing is short enough that a template
    file would only add a second place to keep in sync with the script's
    ``initHud`` contract (``?layout=&page=&source=&recording=&speed=&mirror=``).
    """
    return HTMLResponse(_HUD_HTML.format(vin=vin))


_HUD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>Gauges HUD -- {vin}</title>
<link rel="stylesheet" href="/static/live/widgets.css">
<link rel="stylesheet" href="/static/live/dashboard.css">
</head>
<body class="dd-hud-body">
<div id="dd-hud-grid" class="dd-hud-grid"></div>
<div class="dd-hud-bar">
  <button id="dd-hud-mirror" type="button">Mirror</button>
  <a href="/v/{vin}/gauges">Exit HUD</a>
</div>
<script src="/static/live/widgets.js"></script>
<script src="/static/live/dashboard.js"></script>
<script>
  document.addEventListener("DOMContentLoaded", function () {{
    if (window.CuoreDashboard) window.CuoreDashboard.initHud({{vin: "{vin}"}});
  }});
</script>
</body>
</html>
"""


__all__ = ["router"]
