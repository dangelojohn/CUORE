"""Warranty evidence pack: GET /v/{vin}/warranty-pack (page), .json (structured download with a
SHA-256 manifest), .html (standalone printable). Read only; reads existing records, writes nothing."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from ..api.deps import actor, require_token
from ..services import warranty_pack
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar, templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _pack(request: Request, vin: str, job: str, customer: str) -> dict:
    p = warranty_pack.build(warranty_pack.gather(vin, job), include_customer=customer == "1")
    p["assembled_by"] = actor(request, "")
    return p


@router.get("/v/{vin}/warranty-pack", response_class=HTMLResponse)
def warranty_page(request: Request, vin: str, job: str = "", customer: str = "") -> HTMLResponse:
    response = _page(request, "warranty_pack.html", vin=vin, bar=_vehicle_bar(vin, _dossier(vin)),
                     tab="warranty", p=_pack(request, vin, job, customer), job=job,
                     customer=customer == "1")
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/warranty-pack.json")
def warranty_json(request: Request, vin: str, job: str = "", customer: str = "") -> Response:
    p = _pack(request, vin, job, customer)
    return Response(json.dumps(p, indent=2, ensure_ascii=False, default=str), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="warranty-pack-{vin}.json"'})


@router.get("/v/{vin}/warranty-pack.html", response_class=HTMLResponse)
def warranty_print(request: Request, vin: str, job: str = "", customer: str = "") -> HTMLResponse:
    html = templates.get_template("warranty_pack_print.html").render(
        p=_pack(request, vin, job, customer), vin=vin)
    return HTMLResponse(html, headers={"Content-Disposition": f'attachment; filename="warranty-pack-{vin}.html"'})
