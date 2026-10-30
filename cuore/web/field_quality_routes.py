"""Field-quality early warning: GET /field-quality, GET /field-quality.json, POST /field-quality/sharing.
Export only; nothing is sent anywhere."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..api.deps import require_token
from ..services import field_quality
from .routes import _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/field-quality", response_class=HTMLResponse)
def field_quality_page(request: Request) -> HTMLResponse:
    return _page(request, "field_quality.html", v=field_quality.view())


@router.get("/field-quality.json")
def field_quality_feed() -> JSONResponse:
    return JSONResponse(field_quality.export(),
                        headers={"Content-Disposition": 'attachment; filename="field-quality.json"'})


@router.post("/field-quality/sharing")
def field_quality_sharing(sharing: str = Form("off")) -> RedirectResponse:
    field_quality.set_sharing(sharing == "on")
    return RedirectResponse("/field-quality", status_code=303)
