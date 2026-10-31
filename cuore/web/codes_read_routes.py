"""``POST /v/{vin}/codes/read`` -- the Codes page's "Read now" buttons.

One press reads one confirmed CAN-C module through the existing guarded read (``cuore.services.codes_read``), then
returns to the Codes page with the result line. Read only: no clear, no reset, no write service is reachable from here.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ..api.deps import require_token
from ..services import codes_read, codes_scan_all

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.post("/v/{vin}/codes/read")
def codes_read_now(request: Request, vin: str, module: str = Form("")) -> RedirectResponse:
    out = codes_read.read_now(vin, module)
    tok = request.query_params.get("token")
    url = (f"/v/{quote(vin)}/codes?msg={quote(out['line'])}&mk={'ok' if out['ok'] else 'warn'}"
           + (f"&token={quote(tok)}" if tok else "") + "#read-now")
    return RedirectResponse(url, status_code=303)


@router.post("/v/{vin}/codes/read-all")
def codes_read_all(request: Request, vin: str) -> RedirectResponse:
    """Start "Read all modules" in the background (read only); the Codes page shows progress and results."""
    out = codes_scan_all.start(vin)
    tok = request.query_params.get("token")
    msg = "Reading all modules" if out["started"] else out["reason"]
    url = (f"/v/{quote(vin)}/codes?msg={quote(msg)}&mk={'ok' if out['started'] else 'warn'}"
           + (f"&token={quote(tok)}" if tok else "") + "#read-now")
    return RedirectResponse(url, status_code=303)


__all__ = ["router"]
