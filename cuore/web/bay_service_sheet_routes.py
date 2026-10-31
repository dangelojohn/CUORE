"""GET /v/{vin}/bay-service-sheet (the printable windshield card) and /v/{vin}/bay-card (the read-only phone page
its QR opens). Both rebuild from the stores on every request and send ``Cache-Control: no-store``.
Neither sends anything to the car; /bay-card has no form, button or action."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token, settings_of
from ..services import bay_service_sheet as svc
from ..services import dossier_bridge, landing_bridge, mes_bridge
from .routes import _dossier, _set_active_vehicle, _status_strip, _vehicle_bar, templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])
NO_STORE = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"}


def _common(vin: str) -> tuple[dict[str, Any], dict[str, Any], dict]:
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    try:
        verdict = dossier_bridge.build_view(vin, dossier, _status_strip())["verdict"]
    except Exception:  # noqa: BLE001
        verdict = None
    return bar, dossier, verdict or {}


def _marque_name(vin: str) -> str:
    try:
        b = landing_bridge.brand(mes_bridge.marque_for_vin(vin))
        return (b or {}).get("name") or ""
    except Exception:  # noqa: BLE001
        return ""


@router.get("/v/{vin}/bay-service-sheet", response_class=HTMLResponse)
def bay_service_sheet(request: Request, vin: str, print: str = "") -> HTMLResponse:  # noqa: A002
    bar, _d, verdict = _common(vin)
    s = svc.build(vin, bar=bar, verdict=verdict, marque_name=_marque_name(vin))
    link = svc.card_url(s["vin"], settings_of(request))
    b = landing_bridge.brand(mes_bridge.marque_for_vin(vin)) or {}
    s["mark_url"], s["mark_kind"] = b.get("mark_url"), b.get("mark_kind") or "image"
    s["art"] = landing_bridge._art(s["vin"], s["name"])  # same lookup as the car list; None = no drawing, none printed
    s["url"], s["problem"] = link["url"], link["problem"]
    s["qr"] = svc.qr_svg(link["url"]) if link["url"] else ""
    response = templates.TemplateResponse(request, "bay_service_sheet.html",
                                          {"s": s, "auto_print": print == "1", "vin": vin}, headers=NO_STORE)
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/bay-card", response_class=HTMLResponse)
def bay_card(request: Request, vin: str) -> HTMLResponse:
    from ..services import bay_sheet, next_action
    bar, _d, verdict = _common(vin)
    s = svc.build(vin, bar=bar, verdict=verdict, marque_name=_marque_name(vin))
    codes, more, _cards = bay_sheet._codes(s["vin"], svc._job(s["vin"]))
    try:
        na = next_action.gather(s["vin"])
    except Exception:  # noqa: BLE001
        na = {}
    s.update(codes=codes, more_codes=more, next=svc._s(na.get("title")), next_why=svc._s(na.get("why")),
             state=svc._s(verdict.get("label")), summary=svc._s(verdict.get("summary")),
             not_read=[f"{m.get('ecu', '')}: {m.get('banner', '')}".strip(": ") for m in (verdict.get("not_read") or [])])
    return templates.TemplateResponse(request, "bay_card.html", {"s": s, "vin": vin}, headers=NO_STORE)
