"""``/v/{vin}/five-minute`` -- result page of the five-minute mechanic test (a yardstick).

All measuring lives in :mod:`cuore.live.five_minute`; this module only renders the last run
and the last 10, and relays the run as a form post / JSON call. No menu tile.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..live import five_minute
from .brand_gate import refuse_vin
from .fullscan_routes import _bar
from .routes import _page, _set_active_vehicle

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/five-minute", response_class=HTMLResponse)
def five_minute_page(request: Request, vin: str) -> HTMLResponse:
    hist = five_minute.history(10)
    last = None
    if hist:
        import json
        from ..live.config import state_dir
        try:
            last = json.loads((state_dir() / "five_minute" / hist[0]["file"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            last = None
    response = _page(request, "five_minute.html", vin=vin, bar=_bar(vin), tab="five-minute",
                     last=last, history=hist, min_volts=five_minute.MIN_VOLTS)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/five-minute/run", response_class=HTMLResponse)
def five_minute_run(vin: str) -> RedirectResponse:
    five_minute.run(vin)
    return RedirectResponse(f"/v/{vin}/five-minute", status_code=303)


@router.post("/api/live/five-minute")
def five_minute_api(vin: str = Query(default=""), bus: str = Query(default=""),
                    confirm: bool = Query(default=False)) -> dict[str, Any]:
    refuse_vin(vin)
    return five_minute.run(vin, bus=bus, confirm=confirm)
