"""Fault board routes: a JSON read and the two plain-form POSTs (Fixed / Undo).

Include with ``app.include_router(fault_board_routes.router)`` (the JSON route already carries its ``/api`` path;
no prefix). Handlers are plain ``def`` so FastAPI runs them in the threadpool -- the board build never touches
the event loop. The forms need no JavaScript and redirect back to a safe same-site ``return_to``.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from ..api.deps import require_token
from ..services import fault_board
from ..services.errors import BridgeError

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def form_sync(request: Request):
    """Read the form body from a plain ``def`` handler (same as ``cuore.web.routes.form_sync``)."""
    from anyio import from_thread
    return from_thread.run(request.form)


def _safe_return(url: str, default: str) -> str:
    """Same-site relative paths only: starts with one '/', no scheme/host, no backslash or control characters."""
    u = (url or "").strip()
    if (not u.startswith("/") or u.startswith("//") or any(c in u for c in ("\\", "\r", "\n"))
            or urlsplit(u).netloc or urlsplit(u).scheme):
        return default
    return u


def _back(vin: str, return_to: str, msg: str, kind: str) -> RedirectResponse:
    base = _safe_return(return_to, f"/v/{vin}/job")
    frag = ""
    if "#" in base:
        base, frag = base.split("#", 1)
        frag = "#" + frag
    sep = "&" if "?" in base else "?"
    return RedirectResponse(url=f"{base}{sep}msg={quote(msg)}&mk={kind}{frag or '#fault-board'}", status_code=303)


@router.get("/api/vehicles/{vin}/fault-board")
def fault_board_json(vin: str, sort: str = Query(default="importance"), group: str = Query(default="none"),
                     job: str = Query(default="")) -> dict[str, Any]:
    cards = fault_board.sort_by(fault_board.board(vin, job or None), sort)
    groups = fault_board.group_by(cards, group)
    pub = {c["key"]: p for c, p in zip(cards, fault_board.public(cards))}
    return {"vin": vin, "sort": sort if sort in fault_board.SORTS else "importance",
            "group": group if group in fault_board.GROUPS else "none",
            "order": "Ordered by priority, then most recent", "total": len(cards),
            "groups": [{"id": g["id"], "label": g["label"], "summary": g["summary"], "count": g["count"],
                        "active": g["active"], "open": g["open"], "cards": [pub[c["key"]] for c in g["cards"]]}
                       for g in groups]}


def _act(request: Request, vin: str, undo: bool) -> RedirectResponse:
    form = form_sync(request)
    key = str(form.get("fault_key", "")).strip()
    job_id: Optional[str] = str(form.get("job_id", "")).strip() or None
    by = str(form.get("by", "")).strip() or None
    back = str(form.get("return_to", ""))
    try:
        if undo:
            fault_board.undo_fixed(vin, key, job_id, by)
            return _back(vin, back, "Fixed mark undone", "ok")
        res = fault_board.mark_fixed(vin, key, job_id, by)
        msg = ("Marked fixed -- now verifying. " + res.get("rule", "")) if res["status"] == "verifying" else "Marked resolved"
        return _back(vin, back, msg.strip(), "ok")
    except BridgeError as exc:
        return _back(vin, back, str(exc), "err")


@router.post("/v/{vin}/fault-board/fixed")
def fault_board_fixed(request: Request, vin: str) -> RedirectResponse:
    return _act(request, vin, undo=False)


@router.post("/v/{vin}/fault-board/undo")
def fault_board_undo(request: Request, vin: str) -> RedirectResponse:
    return _act(request, vin, undo=True)


__all__ = ["router"]
