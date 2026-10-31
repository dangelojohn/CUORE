"""Add Service: the page ("/add") and the two small read-only lookups it needs.

The page is one screen of JavaScript (``static/add_service.js``) that talks to the
JSON routes in ``cuore.api.car_identify`` (``/api/car/identify``,
``/api/car/create-service``). This module only adds:

``/add``          the page (with the Choose pick lists from ``data/car_choices.json`` inlined)
``/add/art``      the traced side-view drawing for a model, or 404 (never a stand-in)
``/add/story``    what CUORE's own records hold for a VIN: first visit, or the last
                  visit and the open jobs. Read-only; nothing is inferred.

Nothing here contacts the car or the network. ``/start`` is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from ..api.deps import require_token
from ..services import car_identify, landing_bridge, shop_bridge
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: The wording on the five job-reason tiles; the text is what gets stored as the reason.
REASONS = (("warning lamp", "Warning lamp"), ("noise", "Noise"), ("shudder", "Shudder"),
           ("no start", "No start"), ("service", "Service"))


CHOICES_PATH = Path(__file__).resolve().parents[1] / "data" / "car_choices.json"
_choices_cache: dict[str, Any] = {}


def choices() -> dict[str, Any]:
    """The pick lists for the Choose screen (``cuore/data/car_choices.json``). A pick
    list, not evidence; the page inlines it, so nothing is fetched."""
    if not _choices_cache:
        _choices_cache.update(json.loads(CHOICES_PATH.read_text(encoding="utf-8")))
    return _choices_cache


@router.get("/add", response_class=HTMLResponse)
def add_page(request: Request, brand: str = "") -> HTMLResponse:
    """``?brand=<key>`` (from the Add Service card on /cars) themes the whole flow in
    that marque and preselects it on Choose. An unknown or missing brand is today's page."""
    chosen = landing_bridge.brand((brand or "").strip().lower())
    return web_routes._page(request, "add_service.html", reasons=REASONS, brands=landing_bridge.brands(),
                           choices=choices(), live_strip=None, page_brand=chosen,
                           marque=chosen["key"] if chosen else "alfa")


@router.get("/add/art")
def add_art(model: str = "") -> dict[str, str]:
    slug = "".join(ch for ch in (model or "").lower() if ch.isalnum())
    art = landing_bridge._side_art(slug)  # same lookup the car cards use
    if not art:
        raise HTTPException(status_code=404, detail="no drawing for this model yet")
    return art


@router.get("/car-art/{vin}.svg")
def car_art_svg(vin: str) -> Response:
    """The car's side drawing as one image, for the Menu. 404 when it has none."""
    art = landing_bridge._art(vin, shop_bridge.resolve_vehicle_name(vin))
    if not art:
        raise HTTPException(status_code=404, detail="no drawing for this car yet")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 40 860 300">'
           f'<path fill="#000" fill-rule="evenodd" d="{art["ink"]}"/></svg>')
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "max-age=3600"})


@router.get("/add/story")
def add_story(vin: str = "") -> dict[str, Any]:
    """Only facts already in CUORE's records: the stored card, visits and jobs for
    this VIN. ``first_visit`` is true only when none of them exist."""
    from mes import jobs as jobs_mod
    from mes import shop as shop_mod
    v = car_identify.validate_vin(vin)["vin"]
    if not v:
        raise HTTPException(status_code=400, detail="a VIN is required")
    visits = shop_mod.load(v)
    open_jobs = jobs_mod.open_jobs(v)
    on_file = bool(visits or jobs_mod.load(v) or car_identify.get_card(v))
    last = visits[-1] if visits else None
    return {
        "vin": v, "on_file": on_file, "first_visit": not on_file,
        "visits": len(visits),
        "last_visit": ({"at": last.get("in_at"), "reason": last.get("complaint") or "",
                        "status": last.get("status")} if last else None),
        "open_jobs": [{"id": j.get("id"), "reason": j.get("complaint") or ""} for j in open_jobs],
    }


__all__ = ["router"]
