"""The interactive Sensors outline as an HTML fragment (cuore/services/sensors_interactive.py).

* ``GET /v/{vin}/sensors/outline``                the outline partial; nothing selected
* ``GET /v/{vin}/sensors/outline?sensor=<id>``    the same with that sensor and its cross-check partners
                                                  highlighted and its card open (works without JavaScript);
                                                  an id that is not a sensor of this car -> 404

Reads saved data and the in-process live snapshot only; nothing here contacts the adapter. Importing this
module also registers the Jinja global ``sensors_interactive_outline(vin, sensor, token, base)`` so sensors.html
can ``{% include "_sensors_interactive.html" %}`` with no extra context (the partial calls it when ``sio`` is
not already defined).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import sensors_interactive
from .routes import templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _token(request: Request) -> str:
    return request.query_params.get("token") or ""


@router.get("/v/{vin}/sensors/outline", response_class=HTMLResponse)
def sensors_outline(request: Request, vin: str, sensor: str = "") -> HTMLResponse:
    sio = sensors_interactive.outline(vin, sensor or None, token=_token(request))
    if sio is None:
        return HTMLResponse("Unknown sensor for this vehicle", status_code=404)
    return templates.TemplateResponse(request, "_sensors_interactive.html", {"vin": vin, "sio": sio})


# --- Jinja global for sensors.html ---------------------------------------------------------------------

def sensors_interactive_outline(vin: str, sensor: Optional[str] = None, token: str = "",
                                base: str = "") -> Optional[dict[str, Any]]:
    """The outline context. An unknown ``sensor`` is ignored here (the page still renders); the route 404s.
    Never raises: the outline must not break the Sensors page."""
    try:
        out = sensors_interactive.outline(vin, sensor or None, token=token, base=base)
        return out if out is not None else sensors_interactive.outline(vin, None, token=token, base=base)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"outline unavailable: {exc.__class__.__name__}", "sensors": [], "selected": None}


templates.env.globals["sensors_interactive_outline"] = sensors_interactive_outline
