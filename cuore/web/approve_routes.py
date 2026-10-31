"""The human-only consent page: GET/POST /approve/{request_id}, plus the machine-side
/api/consent/request and /api/consent/redeem used by the MCP server.

A person approves ONE exact car-affecting action here (see cuore/live/consent_gate.py).
The POST accepts only a browser session:

* an ``X-Cuore-Token`` header or ``?token=`` is the machine path and is refused outright;
* the request must be same-origin (Origin, else Referer, must match Host);
* it needs the per-render CSRF nonce AND the cookie set when that page was rendered;
* in accounts mode a signed-in user with a permitted role, whose name is recorded; the
  shared machine token (header or cookie) is not a person;
* the phrase typed must equal the one shown on the page.

There is no approve route under /api. The machine token can create a request and redeem an
approved one; it cannot approve. Honest limit: a local process that can drive a logged-in
browser, or fetch the page and the cookie itself, is not stopped by any of this
(docs/design/CONSENT_GATE.md).
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, Form, Request
from fastapi.responses import HTMLResponse

from ..api.deps import identify, require_token
from ..live import audit, consent_gate
from ..live.errors import Refused
from ..services import accounts
from .routes import _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

_COOKIE = "cuore_consent"


def _store() -> consent_gate.ConsentStore:
    """This process is the consent authority (idempotent)."""
    return consent_gate.activate_authority()


def _cookie_path(request_id: str) -> str:
    return f"/approve/{request_id}"


def _machine_path(request: Request) -> bool:
    """True when the request carries the machine credential in either form."""
    return ("x-cuore-token" in request.headers) or ("token" in request.query_params)


def _same_origin(request: Request) -> bool:
    host = (request.headers.get("host") or "").strip().lower()
    src = request.headers.get("origin")
    if src is None:
        src = request.headers.get("referer")
    if not host or not src or src.strip().lower() == "null":
        return False
    u = urlparse(src)
    if u.scheme not in ("http", "https") or u.netloc.lower() != host:
        return False
    fetch_site = request.headers.get("sec-fetch-site")
    return fetch_site in (None, "", "same-origin")


def _approver(request: Request) -> tuple[Optional[str], str]:
    """``(name, "")`` for a person who may approve, else ``(None, why)``."""
    if not accounts.mode_active():
        return "browser session (no accounts configured)", ""
    # header_token="" so the machine header can never count as identity here
    kind, user = identify(request, header_token="")
    if kind == "user" and user and user.get("role") in consent_gate.APPROVER_ROLES:
        return str(user["username"]), ""
    if kind == "user":
        return None, "your role cannot approve car-affecting actions"
    if kind == "machine":
        return None, "a machine token session is not a person; sign in with your own account"
    return None, "sign in with your own account to approve"


def _render(request: Request, request_id: str, *, status: int = 200, msg: str = "",
            msg_kind: str = "ok", with_form: bool = True) -> HTMLResponse:
    store = _store()
    view = store.page_view(request_id)
    nonce = ""
    cookie = ""
    notice = ""
    can_approve = False
    if view is not None and view["state"] == "pending" and with_form:
        who, why = _approver(request)
        if _machine_path(request):
            # the page, its phrase and its form are for a person's browser session only
            notice = ("This request carries the machine token (header or ?token=), which cannot "
                      "approve. Log in at /login in a browser and open this page without a token.")
        elif who is None:
            notice = why
        else:
            pair = store.issue_secrets(request_id)
            if pair:
                nonce, cookie = pair
                can_approve = True
    if view is not None and not can_approve:
        view = {**view, "phrase": ""}      # the phrase is shown only to a page that can approve
    response = _page(request, "approve.html", v=view, can_approve=can_approve, nonce=nonce,
                     notice=notice, msg=msg, msg_kind=msg_kind, request_id=request_id)
    response.status_code = status
    if can_approve:
        response.set_cookie(_COOKIE, cookie, max_age=int(consent_gate.REQUEST_TTL_S) + 60,
                            path=_cookie_path(request_id), httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/approve/{request_id}", response_class=HTMLResponse)
def approve_page(request: Request, request_id: str) -> HTMLResponse:
    return _render(request, request_id, status=200 if _store().status(request_id) else 404)


@router.post("/approve/{request_id}", response_class=HTMLResponse)
def approve_submit(request: Request, request_id: str, phrase: str = Form(""),
                   nonce: str = Form("")) -> HTMLResponse:
    store = _store()

    def reject(reason: str, status: int = 403) -> HTMLResponse:
        view = store.page_view(request_id)
        audit.record("consent_approve_rejected", request_id=request_id, reason=reason,
                     action_hash=view["action_hash"] if view else None)
        return _render(request, request_id, status=status, msg=reason, msg_kind="err")

    if _machine_path(request):
        return reject("approval is refused on the machine path (token header or ?token=); "
                      "a person must use the browser page")
    if not _same_origin(request):
        return reject("approval must be submitted from this page (same origin)")
    who, why = _approver(request)
    if who is None:
        return reject(why)
    try:
        store.approve(request_id, phrase, nonce, request.cookies.get(_COOKIE, ""), who)
    except Refused as e:
        return _render(request, request_id, status=400, msg=str(e), msg_kind="err")
    return _render(request, request_id, msg="Approved. Tell the assistant to repeat the same call "
                   "with this request id. The approval works once and expires with the request.",
                   with_form=False)


# --- machine side: create a request, redeem an approved one. No approve route exists here. -------

@router.post("/api/consent/request")
def consent_request(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    action = consent_gate.Action.from_dict(body.get("action"))
    return _store().create(action, requested_by="api")


@router.post("/api/consent/redeem")
def consent_redeem(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    action = consent_gate.Action.from_dict(body.get("action"))
    rid = body.get("request_id")
    if not isinstance(rid, str) or not rid or len(rid) > 80:
        raise consent_gate.ConsentRefused("malformed request id")
    grant = _store().redeem(rid, action)
    return {"granted": True, "request_id": grant.request_id, "action_hash": grant.action_hash,
            "approver": grant.approver, "tool": grant.tool}
