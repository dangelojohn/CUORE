"""``GET /v/{vin}/crosschecks`` (page) and ``GET /api/vehicles/{vin}/crosschecks`` (JSON).

Sensor cross-checks: pairs of readings that must agree with each other (see
:mod:`cuore.services.sensor_crosscheck` and ``cuore/data/sensor_crosschecks.json``). Reads saved
readings, the running live session's in-memory cache, or one drive recording (``?recording=<id>``).
Never contacts the car.

Not registered here -- ``app.py`` is shared. The two lines needed there:

    from .web import crosscheck_routes
    app.include_router(crosscheck_routes.router)
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..api.deps import require_token
from ..services import sensor_crosscheck
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _hours(raw: str) -> Optional[float]:
    try:
        v = float(str(raw).strip())
    except ValueError:
        return None
    return v if 0 <= v <= 24 * 365 else None


def _recordings(vin: str) -> list[dict[str, Any]]:
    try:
        from ..services import recordings
        return [{"id": r.get("id"), "label": r.get("label") or "", "start": r.get("start") or "",
                 "n_rows": r.get("n_rows", 0)} for r in recordings.list_recordings(vin)[:8] if r.get("id")]
    except Exception:  # noqa: BLE001 -- the list is a convenience
        return []


@router.get("/v/{vin}/crosschecks", response_class=HTMLResponse)
def crosschecks_page(request: Request, vin: str, recording: str = "", soaked_h: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    cc = sensor_crosscheck.panel(vin, recording.strip() or None, _hours(soaked_h))
    response = _page(request, "crosschecks.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="sensors",
                     cc=cc, recordings=_recordings(vin), soaked_in=soaked_h.strip())
    _set_active_vehicle(response, vin)
    return response


@router.get("/api/vehicles/{vin}/crosschecks")
def crosschecks_json(vin: str, recording: str = "", soaked_h: str = "") -> JSONResponse:
    cc = sensor_crosscheck.panel(vin, recording.strip() or None, _hours(soaked_h))
    return JSONResponse(cc, status_code=404 if cc.get("error", "").startswith("LookupError") else 200)
