"""GET /v/{vin}/bay-sheet[?job=<id>]: the one-page sheet that travels with the car. Read only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import bay_sheet, dossier_bridge
from .routes import _dossier, _page, _set_active_vehicle, _status_strip, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/bay-sheet", response_class=HTMLResponse)
def bay_sheet_page(request: Request, vin: str, job: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    try:
        verdict = dossier_bridge.build_view(vin, dossier, _status_strip())["verdict"]
    except Exception:  # noqa: BLE001
        verdict = None
    url = str(request.base_url).rstrip("/") + f"/v/{vin}/bay-sheet" + (f"?job={job}" if job else "")
    response = _page(request, "bay_sheet.html", vin=vin, bar=bar, tab="job",
                     s=bay_sheet.build(vin, job, bar=bar, verdict=verdict, url=url))
    _set_active_vehicle(response, vin)
    return response
