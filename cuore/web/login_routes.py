"""Session login for the web UI (see api/deps.py).

GET /login?token=...  verify, set the signed session cookie, redirect to next.
GET /login            the typing form.  POST /login the same, from the form.
GET /logout           clear the cookie.

With no token configured there is nothing to log in to: /login just redirects.
Not behind require_token (it *is* the way in).
"""
from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import __version__
from ..api.deps import (COOKIE, SESSION_MAX_AGE, make_session, resolve_token,
                        safe_next, settings_of, token_ok)
from .routes import templates

router = APIRouter(include_in_schema=False)


def _form(request: Request, nxt: str, error: str, status: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "login.html",
        {"next": nxt, "error": error, "version": __version__,
         "profile": settings_of(request).profile.value},
        status_code=status)


def _attempt(request: Request, offered: str, nxt: str):
    expected = resolve_token(settings_of(request).token)
    if not expected:
        return RedirectResponse(nxt, status_code=302)
    if not token_ok(offered, expected):
        return _form(request, nxt, "That token is not correct.", 403)
    resp = RedirectResponse(nxt, status_code=302)
    resp.set_cookie(COOKIE, make_session(expected), max_age=SESSION_MAX_AGE,
                    httponly=True, samesite="lax", path="/")
    return resp


@router.get("/login")
async def login_get(request: Request, token: str | None = None,
                    next: str | None = None):
    nxt = safe_next(next)
    if token is None:
        if not resolve_token(settings_of(request).token):
            return RedirectResponse(nxt, status_code=302)
        return _form(request, nxt, "", 200)
    return _attempt(request, token, nxt)


@router.post("/login")
async def login_post(request: Request):
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    return _attempt(request, (form.get("token") or [""])[0],
                    safe_next((form.get("next") or [""])[0]))


@router.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE, path="/")
    return resp
