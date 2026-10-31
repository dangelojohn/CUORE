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


#: Key channels for the answer-first block: (channel id, short label, decimals).
_NOW_CHANNELS = (("engine_rpm", "RPM", 0), ("engine_coolant_temp", "Coolant", 0),
                 ("battery_voltage", "Battery", 1), ("control_module_voltage", "Battery", 1),
                 ("fuel_level", "Fuel", 1), ("vehicle_speed", "Speed", 0),
                 ("ecm_19bd", "IBS charge", 0))


def _fmt_at(at) -> str:
    from datetime import datetime
    try:
        d = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        return f"{d.day} {d.strftime('%b %H:%M')}"
    except (ValueError, TypeError):
        return str(at or "")


def _now_view(vin: str) -> dict:
    """What the car is doing right now: the open session's latest readings, else the last captured
    ones (saved snapshot or from-car PID observation) with time and source. Nothing is invented."""
    from ..live import channels as ch_mod
    from ..services import bench_interactive as bi
    snap = bi._live_snapshot()
    live = snap.get("channels") or {}
    connected = bool(snap.get("active"))
    reg = ch_mod.registry()
    items, seen, newest, origins = [], set(), "", []
    for cid, label, dec in _NOW_CHANNELS:
        if label in seen:
            continue
        c = reg.get(cid)
        unit = (getattr(c, "unit", "") or "") if c else ""
        val = at = origin = None
        n = bi._num((live.get(cid) or {}).get("value")) if connected else None
        if n is not None:
            val = n
        else:
            sv = bi._saved_value(vin, cid, getattr(c, "pid", "") or "") if getattr(c, "pid", "") or cid == "battery_voltage" else None
            if sv:
                val, at, origin = sv["value"], sv["at"], sv["origin"]
        if val is None:
            continue
        seen.add(label)
        if c is not None and c.kind == "did":
            label += " (scale confirmed)" if c.confidence == "confirmed" else " (unconfirmed)"
        unit = {"C": "°C"}.get(unit, unit)
        items.append({"label": label, "text": f"{val:.{dec}f} {unit}".strip()})
        if at:
            newest = max(newest, str(at))
            if origin and origin not in origins:
                origins.append(origin)
    if connected:
        state, action = "connected", "Connected: readings below update live. Press Record to keep this run."
    else:
        state = "idle"
        action = "Pick Live car, then press Connect to watch this car now."
    try:
        from ..live import decode_flow
        decode = decode_flow.status()["headline"]
    except Exception:  # noqa: BLE001 -- a status line must never break the page
        decode = ""
    return {"decode": decode, "connected": connected, "items": items, "action": action, "state": state,
            "at": _fmt_at(newest) if newest and not connected else "", "source": "; ".join(origins)}


@router.get("/v/{vin}/gauges", response_class=HTMLResponse)
def gauges_page(request: Request, vin: str) -> HTMLResponse:
    """The customizable live-data dashboard: toolbar, page tabs, widget grid."""
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    try:
        now = _now_view(vin)
    except Exception:  # noqa: BLE001 -- the answer block must never break the page
        now = {"connected": False, "items": [], "action": "Pick Live car, then press Connect.", "state": "idle", "at": "", "source": ""}
    response = _page(request, "live_dashboard.html", vin=vin, bar=bar, tab="gauges", now=now)
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
