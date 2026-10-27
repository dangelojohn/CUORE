"""Session login for the web UI (see api/deps.py).

GET /login?token=...  verify, set the signed session cookie, redirect to next.
GET /login            the typing form.  POST /login the same, from the form.
GET /logout           clear the cookie.

With no token configured there is nothing to log in to: /login just redirects.
Not behind require_token (it *is* the way in).
"""
from __future__ import annotations

import logging
import math
import threading
import time
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import __version__
from ..api.deps import (COOKIE, SESSION_MAX_AGE, make_session, resolve_token,
                        safe_next, settings_of, token_ok)
from .routes import templates

router = APIRouter(include_in_schema=False)
log = logging.getLogger("cuore.login")

MAX_FAILS = 5                 # failed attempts allowed ...
WINDOW = 10 * 60.0            # ... per this many seconds, per client
CLOCK = time.monotonic        # tests replace this
_FAILS: dict[str, list[float]] = {}
_FLOCK = threading.Lock()


def _client(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    first = xff.split(",")[0].strip()
    return first or (request.client.host if request.client else "unknown")


def _retry_after(client: str) -> int:
    """Seconds until this client may try again (0 = not locked out)."""
    with _FLOCK:
        now = CLOCK()
        hits = [t for t in _FAILS.get(client, []) if now - t < WINDOW]
        if hits:
            _FAILS[client] = hits
        else:
            _FAILS.pop(client, None)
        if len(hits) < MAX_FAILS:
            return 0
        return max(1, math.ceil(WINDOW - (now - hits[0])))


def _record_fail(client: str) -> None:
    with _FLOCK:
        _FAILS.setdefault(client, []).append(CLOCK())
    log.warning("failed login from %s", client)      # never the token value


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
    client = _client(request)
    wait = _retry_after(client)
    if wait:
        mins = math.ceil(wait / 60)
        resp = _form(request, nxt, f"Too many wrong tries. Try again in {mins} minute"
                     f"{'' if mins == 1 else 's'}.", 429)
        resp.headers["Retry-After"] = str(wait)
        return resp
    if not token_ok(offered, expected):
        _record_fail(client)
        return _form(request, nxt, "That token is not correct.", 403)
    with _FLOCK:
        _FAILS.pop(client, None)
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
