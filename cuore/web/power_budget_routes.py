"""Power and ground budget: ``/v/{vin}/power-budget`` and friends.

Measured voltage drops along a feed or ground, kept by
:mod:`cuore.services.power_budget`. Reads and records saved data only; never
contacts the car.

Not registered on the app here (``app.py`` is owned elsewhere). The two lines
needed there, next to the other ``web`` router imports/includes:

    ``from .web import power_budget_routes``
    ``app.include_router(power_budget_routes.router)``

Importing this module also registers the Jinja global
``power_budget_panel(vin, element, ...)`` on the shared template environment,
so any page can embed the panel:

    ``{% with pb = power_budget_panel(vin, "g003a") %}{% include "_power_budget_panel.html" %}{% endwith %}``
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..api.deps import require_token
from ..services import electrical_bridge, power_budget
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar, form_sync
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _check_vin(vin: str) -> str:
    vin = (vin or "").strip()
    if not vin or len(vin) > 40 or not vin.replace("-", "").isalnum():
        raise HTTPException(status_code=404, detail="unknown vehicle")
    return vin


def _check_element(element: str) -> str:
    element = (element or "").strip()
    if not electrical_bridge.get_element(element):
        raise HTTPException(status_code=404, detail="unknown electrical element")
    return element


def panel_context(vin: str, element: str, redirect_to: str = "", error: str = "",
                  saved: bool = False, open_form: bool = False) -> dict[str, Any]:
    """The context ``_power_budget_panel.html`` needs, as ``pb``."""
    return power_budget.panel(vin, element, redirect_to=redirect_to, error=error,
                              saved=saved, open_form=open_form)


# Template-facing helper on the shared environment (same trick as
# electrical_routes): pages embed the partial without a route change.
_shared_templates.env.globals["power_budget_panel"] = panel_context


def _safe_redirect(vin: str, url: str) -> bool:
    base = f"/v/{vin}/power-budget"
    return (url == base or url.startswith(base + "/") or url.startswith(base + "?")) \
        and not any(c in url for c in (chr(92), chr(13), chr(10)))


@router.get("/v/{vin}/power-budget", response_class=HTMLResponse)
def power_budget_page(request: Request, vin: str, saved: str = "", error: str = "") -> HTMLResponse:
    vin = _check_vin(vin)
    dossier = _dossier(vin)
    ov = power_budget.overview(vin)
    ids = ([power_budget.FIRST_ELEMENT] if ov["first_unmeasured"] else []) + ov["measured"]
    panels = [panel_context(vin, eid, redirect_to=f"/v/{vin}/power-budget",
                            error=error if i == 0 else "", saved=bool(saved) and i == 0)
              for i, eid in enumerate(ids)]
    response = _page(request, "power_budget.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="electrical", panels=panels, ov=ov, element=None,
                     basis=power_budget.limits(), error=error, saved=bool(saved))
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/power-budget/{element}", response_class=HTMLResponse)
def power_budget_element(request: Request, vin: str, element: str, saved: str = "",
                         error: str = "") -> HTMLResponse:
    vin = _check_vin(vin)
    element = _check_element(element)
    dossier = _dossier(vin)
    pb = panel_context(vin, element, error=error, saved=bool(saved), open_form=True)
    response = _page(request, "power_budget.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="electrical", panels=[pb], ov=power_budget.overview(vin), element=element,
                     basis=power_budget.limits(), error=error, saved=bool(saved))
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/power-budget/measure", response_class=HTMLResponse)
def power_budget_measure(request: Request, vin: str) -> RedirectResponse:
    """Record one measurement. Plain form POST, no JavaScript. The form is
    read in the threadpool (``form_sync``) so the file write never runs on
    the event loop."""
    vin = _check_vin(vin)
    form = form_sync(request)

    def val(name: str) -> str:
        return str(form.get(name, "") or "").strip()

    element = val("element")
    redirect_base = val("redirect_to") or f"/v/{vin}/power-budget/{quote(element)}"
    if not _safe_redirect(vin, redirect_base):
        redirect_base = f"/v/{vin}/power-budget"
    error = None
    try:
        power_budget.record(
            vin, element, volts=val("volts"), condition=val("condition"),
            from_point=val("from_point"), to_point=val("to_point"), preset=val("preset"),
            side=val("side"), by=val("by"), meter=val("meter"), tag=val("tag"),
            note=val("note"), battery_v=val("battery_v"),
            media_ids=[m for m in val("media_id").replace(",", " ").split()])
    except ValueError as exc:
        error = str(exc)
    sep = "&" if "?" in redirect_base else "?"
    url = f"{redirect_base}{sep}{'saved=1' if error is None else 'error=' + quote(error)}"
    return RedirectResponse(url=url, status_code=303)


@router.get("/api/vehicles/{vin}/power-budget")
def power_budget_api(vin: str, element: str = "") -> JSONResponse:
    vin = _check_vin(vin)
    if element:
        element = _check_element(element)
    return JSONResponse(power_budget.api_payload(vin, element))
