"""One decision: "this marque has no vehicle data for this page".

A brand with ``has_data: false`` in ``data/brands.json`` (Maserati, Ferrari today) holds no
vehicle data in CUORE, so any page that would draw from the Alfa/Stelvio reference data must
not render for that brand's cars: a Stelvio fuse map on a Grecale is misinformation. Instead
the page's normal heading and frame render with one calm empty panel (``_brand_empty.html``).

What stays open is data, not code: ``data/brand_pages.json`` lists the first path segments
under ``/v/{vin}/`` that open normally (the record-keeping and "no scan on file" pages). Every
other per-car page is gated by default, so a newly added Alfa-only page is safe without
anyone remembering to list it. Give a brand data = set ``has_data`` true; nothing else changes.

Wired in ``app.create_app`` as an app dependency (``brand_gate``) plus an exception handler.
Auth runs first (``require_token``), so the skeleton is never shown to a logged-out visitor.
Nothing here touches the adapter.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fastapi import Header, Query, Request

from ..api.deps import require_token
from ..services import landing_bridge, mes_bridge
from . import nav_items

_PAGES = Path(__file__).resolve().parents[1] / "data" / "brand_pages.json"
_CAR_PATH = re.compile(r"^/v/([^/]+)(?:/([^/]*))?")
#: global routes that take the car as ?vin= (the Menu's "TSB for this car")
_VIN_QUERY_SLUG = {"/tsb": "tsb"}


class BrandEmpty(Exception):
    """Raised by the gate; the app turns it into the brand's empty skeleton page."""

    def __init__(self, vin: str, slug: str, marque: str):
        super().__init__(f"{marque} has no data for {slug}")
        self.vin, self.slug, self.marque = vin, slug, marque


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    try:
        return json.loads(_PAGES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def has_data(marque: str) -> bool:
    """False only for a known brand marked ``has_data: false``; unknown brands keep today's behaviour."""
    b = landing_bridge.brand(marque or "")
    return True if b is None else bool(b.get("has_data", True))


def brand_name(marque: str) -> str:
    return (landing_bridge.brand(marque or "") or {}).get("name") or ""


def _slug_title(slug: str) -> str:
    for it in nav_items.ITEMS:
        href = it["href"]
        if "{vin}" in href and href.split("{vin}", 1)[1].strip("/").split("/")[0].split("?")[0] == slug:
            return it["label"]
    if slug == "tsb":
        return "TSB"
    return slug.replace("-", " ").replace("_", " ").strip().capitalize() or "This"


def page_note(slug: str) -> str:
    """Extra truthful line for a page (for example why it cannot connect), from the data file."""
    return str((_config().get("notes") or {}).get(slug, ""))


def empty_line(title: str) -> str:
    low = title if title.isupper() else title[:1].lower() + title[1:]
    return f"No {low} data for this model yet."


def _target(request: Request) -> Optional[tuple[str, str]]:
    path = request.url.path
    m = _CAR_PATH.match(path)
    if m and m.group(1):
        return m.group(1), (m.group(2) or "")
    slug = _VIN_QUERY_SLUG.get(path)
    vin = (request.query_params.get("vin") or "").strip()
    return (vin, slug) if slug and vin else None


async def brand_gate(request: Request, x_cuore_token: str | None = Header(default=None),
                     token: str | None = Query(default=None)) -> None:
    t = _target(request)
    if not t:
        return
    vin, slug = t
    try:
        marque = mes_bridge.marque_for_vin(vin)
    except Exception:  # noqa: BLE001 -- a broken decode must never sink a page
        return
    if has_data(marque) or slug in set(_config().get("open") or []):
        return
    await require_token(request, x_cuore_token, token)   # logged-out visitors get the login redirect
    raise BrandEmpty(vin, slug, marque)


def render(request: Request, exc: BrandEmpty):
    """The skeleton: the page's heading in the brand's theme and one empty panel."""
    from ..services import car_identify, shop_bridge
    from . import routes as web_routes
    title = _slug_title(exc.slug)
    try:
        name = car_identify.card_name(exc.vin) or shop_bridge.resolve_vehicle_name(exc.vin) or ""
    except Exception:  # noqa: BLE001
        name = ""
    resp = web_routes._page(request, "_brand_empty.html", vin=exc.vin, tab=exc.slug, live_strip=None,
                            bar={"name": name, "vin": exc.vin}, page_title=title,
                            empty_line=empty_line(title), page_note=page_note(exc.slug),
                            brand_label=brand_name(exc.marque))
    resp.status_code = 200 if request.method in ("GET", "HEAD") else 409
    return resp


__all__ = ["BrandEmpty", "brand_gate", "has_data", "render", "brand_name", "page_note"]
