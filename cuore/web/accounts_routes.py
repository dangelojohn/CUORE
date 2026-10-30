"""Accounts page: GET /accounts (admin, shop_lead), add / disable / reset password.

Active only in accounts mode; with mode off the page says so and offers nothing.
shop_lead sees and manages technicians of their own shop only; admin sees all
and is the only role that resets passwords. Passwords/hashes never reach a page.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import identify, require_role, require_token
from ..services import accounts
from .routes import _page

router = APIRouter(include_in_schema=False,
                   dependencies=[Depends(require_token), Depends(require_role("shop_lead"))])


def _me(request: Request) -> dict | None:
    kind, u = identify(request)
    return u        # None for the shared-token machine path (treated as admin)


def _back(text: str, kind: str) -> RedirectResponse:
    return RedirectResponse(f"/accounts?msg={quote(text[:200])}&mk={kind}", status_code=303)


def _may_manage(me: dict | None, target: dict | None) -> bool:
    if not target:
        return False
    if me is None or me["role"] == "admin":
        return True
    return target["shop_id"] == me["shop_id"] and target["role"] == "technician"


@router.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request, msg: str = "", mk: str = "") -> HTMLResponse:
    me = _me(request)
    shop = None if me is None or me["role"] == "admin" else me["shop_id"]
    return _page(request, "accounts.html", users=accounts.list_users(shop) if accounts.mode_active() else [],
                 mode_on=accounts.mode_active(), me=me, is_admin=me is None or me["role"] == "admin",
                 flash_msg=msg[:200], flash_kind="err" if mk == "err" else "ok")


@router.post("/accounts/add")
def accounts_add(request: Request, username: str = Form(""), password: str = Form(""),
                 display_name: str = Form(""), role: str = Form("technician"),
                 shop_id: str = Form(""), shop_kind: str = Form("independent")) -> RedirectResponse:
    me = _me(request)
    if me is not None and me["role"] != "admin":     # shop_lead: own shop, technicians only
        role, shop_id, shop_kind = "technician", me["shop_id"], me["shop_kind"]
    try:
        u = accounts.create(username, password, role, display_name, shop_id or "main", shop_kind)
    except accounts.AccountError as exc:
        return _back(f"Not added: {exc}", "err")
    return _back(f"Added {u['username']} ({u['role']}).", "ok")


@router.post("/accounts/disable")
def accounts_disable(request: Request, username: str = Form(""), enable: str = Form("")) -> RedirectResponse:
    me = _me(request)
    if not _may_manage(me, accounts.get(username)):
        raise HTTPException(status_code=403, detail="not your shop or not a technician")
    if me is not None and me["username"] == username.strip().lower():
        return _back("You cannot disable your own account.", "err")
    try:
        accounts.disable(username, disabled=not enable)
    except accounts.AccountError as exc:
        return _back(f"Not changed: {exc}", "err")
    return _back(f"{'Enabled' if enable else 'Disabled'} {username}.", "ok")


@router.post("/accounts/password")
def accounts_password(request: Request, username: str = Form(""), password: str = Form("")) -> RedirectResponse:
    me = _me(request)
    if me is not None and me["role"] != "admin":
        raise HTTPException(status_code=403, detail="only an admin resets passwords")
    try:
        accounts.set_password(username, password)
    except accounts.AccountError as exc:
        return _back(f"Not changed: {exc}", "err")
    return _back(f"Password reset for {username}.", "ok")
