"""``GET /tsb?vin=...`` -- the TSB layer: every bulletin, recall, CSN,
campaign and extended coverage known for the car, as a per-VIN checklist.
``POST /tsb/status`` records one row's status/note (form post -> redirect
back to the row; JSON body -> JSON answer).

Same posture as ``cuore/web/tests_routes.py``: reuses ``cuore.web.routes``'s
``_page``/``_dossier``/``_vehicle_bar`` so the page shares the app's shell.
Data comes from ``cuore.services.tsb_bridge``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from ..api.deps import require_token
from ..services import tsb_bridge
from ..services.errors import BadRequest
from .routes import _active_vehicle, _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

KIND_LABELS = {"tsb": "TSB", "recall": "Recall", "csn": "CSN", "campaign": "Campaign",
               "extended_warranty": "Extended coverage", "emissions": "Emissions"}
APPLIES_LABELS = {"yes": "yes", "no": "no", "vin_check": "VIN check needed"}


def _safe_dossier(vin: str) -> dict[str, Any] | None:
    """The workup, or None -- the checklist must render even for a VIN the
    log corpus does not know (it only loses the dossier cross-links)."""
    try:
        return _dossier(vin)
    except Exception:  # noqa: BLE001
        return None


def _group(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["systems"] or ["Other"])[0], []).append(r)
    return [{"system": k, "rows": v} for k, v in sorted(groups.items())]


@router.get("/tsb", response_class=HTMLResponse)
def tsb_page(request: Request, vin: str = "", kind: str = "", system: str = "") -> HTMLResponse:
    vin = _active_vehicle(request, vin).upper()
    if not vin:
        vin = (tsb_bridge.catalogue()["vehicle"].get("vin") or "").upper()
    if not vin:
        raise BadRequest("a VIN is required (/tsb?vin=...)")
    dossier = _safe_dossier(vin)
    view = tsb_bridge.checklist(vin, dossier)
    rows = [r for r in view["items"]
            if (not kind or r["kind"] == kind) and (not system or system in r["systems"])]
    bar = None
    if dossier:
        try:
            bar = _vehicle_bar(vin, dossier)
        except Exception:  # noqa: BLE001
            bar = None
    response = _page(request, "tsb.html", vin=vin, bar=bar, tab="tsb", view=view,
                     groups=_group(rows), shown=len(rows), kind=kind, system=system,
                     kind_labels=KIND_LABELS, applies_labels=APPLIES_LABELS,
                     status_labels=tsb_bridge.STATUS_LABELS,
                     statuses=tsb_bridge.STATUSES)
    _set_active_vehicle(response, vin)
    return response


@router.post("/tsb/status")
async def tsb_status(request: Request) -> Response:
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        if not isinstance(body, dict):
            raise BadRequest("JSON object expected")
        as_json = True
    else:
        body = dict(await request.form())
        as_json = False
    vin = str(body.get("vin") or "")
    item_id = str(body.get("item_id") or "")
    note = body.get("note")
    entry = tsb_bridge.set_status(vin, item_id, str(body.get("status") or ""),
                                  None if note is None else str(note))
    if as_json:
        return JSONResponse(entry)
    back = f"/tsb?vin={quote(entry['vin'])}"
    for key in ("kind", "system"):
        if body.get(key):
            back += f"&{key}={quote(str(body[key]))}"
    return RedirectResponse(f"{back}#{tsb_bridge.row_anchor(item_id)}", status_code=303)
