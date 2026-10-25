"""Network view, wiggle-test marks and pin data for the code page.

Reads saved data only and appends to CUORE's own jsonl stores; nothing here
opens the adapter (see :mod:`cuore.services.path_diag`).

Registered in app.py: ``app.include_router(path_diag_routes.router)``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..services import path_diag
from . import electrical_routes
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _hops(vin: str, code: str) -> list[dict[str, Any]]:
    try:
        return electrical_routes.electrical_path_for(vin, code).get("path") or []
    except Exception:  # noqa: BLE001
        return []


def path_more_for(vin: str, code: str) -> dict[str, Any]:
    """Jinja global used by ``_electrical_path_more.html``."""
    return path_diag.more_for(vin, code, _hops(vin, code))


_shared_templates.env.globals["path_more_for"] = path_more_for


def _back(form: Any, vin: str, code: str) -> str:
    base = str(form.get("redirect_to", "") or "")
    if not base or not electrical_routes._safe_redirect(base):
        base = f"/v/{vin}/code/{quote(code)}" if code else f"/v/{vin}/network"
    return base


def _done(base: str, error: str | None, ok_key: str, anchor: str) -> RedirectResponse:
    sep = "&" if "?" in base else "?"
    base = base.split("#")[0]
    q = f"{ok_key}=1" if error is None else "error=" + quote(error)
    return RedirectResponse(url=f"{base}{sep}{q}#{anchor}", status_code=303)


@router.get("/v/{vin}/network", response_class=HTMLResponse)
def network_page(request: Request, vin: str, code: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    net = path_diag.build_network(vin, code)
    response = _page(request, "network.html", vin=vin, bar=_vehicle_bar(vin, dossier), code=code.upper(),
                     net=net, net_svg=path_diag.network_svg(net), checklist=path_diag.CAN_CHECKLIST)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/wiggle", response_class=HTMLResponse)
async def wiggle_submit(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()
    code = str(form.get("code", "")).strip().upper()
    base = _back(form, vin, code)
    hops = {str(h.get("id")) for h in _hops(vin, code) if h.get("id")}
    err = path_diag.add_wiggle(
        vin, code, str(form.get("action", "")).strip(), str(form.get("hop", "")),
        str(form.get("note", "")), valid_hops=hops, by=str(form.get("by", "")).strip())
    return _done(base, err, "wiggle", "wiggle-test")


@router.post("/v/{vin}/pins", response_class=HTMLResponse)
async def pins_submit(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()
    code = str(form.get("code", "")).strip().upper()
    base = _back(form, vin, code)
    err = path_diag.add_pin(
        vin, str(form.get("element", "")).strip(),
        {k: form.get(k, "") for k in path_diag.PIN_FIELDS},
        str(form.get("source", "")), str(form.get("by", "")),
        valid_elements=set(electrical_routes._elements()),
        amends=str(form.get("amends", "")).strip())
    return _done(base, err, "pin", "pin-data")
