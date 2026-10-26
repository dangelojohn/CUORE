"""MES parameter inventory page: per module, what MultiEcuScan says it reports.

Read-only. GET /v/{vin}/mes-parameters (checklist + lists), GET .../mes-parameters.csv.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from ..api.deps import require_token
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _svc():
    from ..services import mes_parameters
    return mes_parameters


@router.get("/v/{vin}/mes-parameters", response_class=HTMLResponse)
def mes_parameters_page(request: Request, vin: str, module: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    error = None
    try:
        inv = _svc().inventory(vin)
    except Exception as exc:  # noqa: BLE001 -- the page must render without the MES logs
        inv = {"modules": [], "other": [], "captured": 0, "total": 0, "parameter_count": 0}
        error = f"MES logs could not be read: {exc}"
    rows: list[dict[str, Any]] = inv["modules"]
    order = {"can_c": 0, "can_ch": 1, "can_ihs": 2}
    todo = sorted((m for m in rows if not m["captured"]),
                  key=lambda m: (m["present"] != "confirmed", order.get(m["bus"], 9), m["code"]))
    done = [m for m in rows if m["captured"]] + list(inv["other"])
    response = _page(request, "mes_parameters.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="sensors",
                     inv=inv, todo=todo, done=done, open_module=module.strip().upper(), error=error)
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/mes-parameters.csv")
def mes_parameters_csv(vin: str) -> Response:
    return Response(_svc().to_csv(vin).encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="mes-parameters-{vin}.csv"'})
