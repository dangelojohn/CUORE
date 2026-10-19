"""``GET /slvt?vin=...`` -- the SLVT replica: the bulletin 18-048-23 checklist,
a Run button and the last graded result. ``POST /slvt/run`` does the three
read-only reads (``cuore.services.slvt_bridge.run``) and redirects back, so a
refresh never re-reads the car.

Same posture as ``cuore/web/tsb_routes.py``: reuses ``cuore.web.routes``'s
``_page``/``_dossier``/``_vehicle_bar`` so the page shares the app's shell.
Nothing here can send a write: the replica waits for the ECM's own EVAP
monitor and reads its outcome.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..api.deps import require_token
from ..services import slvt_bridge, tsb_bridge
from ..services.errors import BadRequest
from .routes import _active_vehicle, _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _safe_bar(vin: str) -> dict[str, Any] | None:
    """The vehicle bar, or None -- the page must render for a VIN the log
    corpus does not know (it only loses the vehicle tabs)."""
    try:
        return _vehicle_bar(vin, _dossier(vin))
    except Exception:  # noqa: BLE001
        return None


def _vin_for(request: Request, vin: str) -> str:
    vin = _active_vehicle(request, vin).upper()
    if not vin:
        vin = (tsb_bridge.catalogue()["vehicle"].get("vin") or "").upper()
    if not vin:
        raise BadRequest("a VIN is required (/slvt?vin=...)")
    return vin


@router.get("/slvt", response_class=HTMLResponse)
def slvt_page(request: Request, vin: str = "", ran: str = "") -> HTMLResponse:
    vin = _vin_for(request, vin)
    view = slvt_bridge.build_view(vin)
    response = _page(request, "slvt.html", vin=vin, bar=_safe_bar(vin), tab="tsb",
                     view=view, ran=ran)
    _set_active_vehicle(response, vin)
    return response


@router.post("/slvt/run")
async def slvt_run(request: Request) -> Response:
    form = await request.form()
    vin = _vin_for(request, str(form.get("vin") or ""))
    result = slvt_bridge.run(vin, [str(v) for v in form.getlist("pre")])
    return RedirectResponse(
        f"/slvt?vin={quote(vin)}&ran={'1' if result['ran'] else '0'}#result", status_code=303)
