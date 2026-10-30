"""Shared route dependencies.

Auth here is a single shared token, and that is the right amount for T1 and T2:
one shop, one LAN, devices the owner controls. It exists because the moment
``host`` is widened past loopback every device on the network can read a corpus
containing customer VINs -- so there has to be *something*, and something
simple that gets used beats something proper that gets disabled.

When the token is unset, auth is off. That is safe paired with the loopback
default and is checked at startup, which warns if the two disagree.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import quote, urlencode

from fastapi import Header, HTTPException, Query, Request

from ..config import Settings

COOKIE = "cuore_session"
SESSION_MAX_AGE = 30 * 24 * 3600
# Probed by cuore-keepalive.ps1 -- must answer without credentials.
OPEN_PATHS = frozenset({"/api/health"})
_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
_secret_cache: dict[str, bytes] = {}


class LoginRedirect(Exception):
    """Raised for an unauthenticated browser GET; app.py turns it into a 302."""

    def __init__(self, location: str) -> None:
        self.location = location


def settings_of(request: Request) -> Settings:
    """The live settings object, stashed on app state at startup."""
    return request.app.state.settings


def web_token_path():
    from ..live.config import state_dir
    return state_dir() / "web_token.txt"


def resolve_token(configured: str) -> str:
    """Token source: CUORE_TOKEN (settings) first, else state-dir web_token.txt."""
    if configured.strip():
        return configured.strip()
    try:
        p = web_token_path()
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


def _secret() -> bytes:
    from ..live.config import state_dir
    path = state_dir() / "web_secret.txt"
    key = str(path)
    if key not in _secret_cache:
        if not path.exists():
            path.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
        _secret_cache[key] = path.read_text(encoding="utf-8").strip().encode()
    return _secret_cache[key]


def _sign(sid: str, expected: str) -> str:
    # The token is mixed into the key so rotating it ends every session.
    key = _secret() + b"|" + expected.encode()
    return hmac.new(key, sid.encode(), hashlib.sha256).hexdigest()


def make_session(expected: str) -> str:
    """A signed cookie value. The random id below is the one-controller key:
    see :func:`session_id` (used by the procedure prototype routes)."""
    sid = f"{secrets.token_urlsafe(16)}.{int(time.time())}"
    return f"{sid}.{_sign(sid, expected)}"


def _valid_session(value: str | None, expected: str) -> bool:
    if not value:
        return False
    sid, _, sig = value.rpartition(".")
    if not sid or not hmac.compare_digest(sig, _sign(sid, expected)):
        return False
    try:
        issued = int(sid.rsplit(".", 1)[1])
    except (IndexError, ValueError):
        return False
    return 0 <= time.time() - issued <= SESSION_MAX_AGE


def session_id(request: Request) -> str | None:
    """The id inside a valid login cookie (one-controller key), else None."""
    value = request.cookies.get(COOKIE)
    if value and value.startswith("u~") and _user_from_cookie(value):
        return value.rpartition(".")[0]
    expected = resolve_token(settings_of(request).token)
    if not expected or not _valid_session(value, expected):
        return None
    return (value or "").rpartition(".")[0]


def token_ok(offered: str, expected: str) -> bool:
    return bool(offered) and hmac.compare_digest(offered.strip(), expected)


def safe_next(nxt: str | None) -> str:
    """Same-site path only: one leading slash, no scheme, no backslash."""
    if (not nxt or not nxt.startswith("/") or nxt.startswith("//")
            or any(c in nxt for c in "\\\r\n")):
        return "/"
    return nxt


_ACCT_KEY = "cuore-accounts-session"


def make_user_session(username: str, role: str) -> str:
    """Signed cookie for an accounts-mode login: carries username + role."""
    sid = f"u~{username}~{role}~{secrets.token_urlsafe(8)}.{int(time.time())}"
    return f"{sid}.{_sign(sid, _ACCT_KEY)}"


def _user_from_cookie(value: str | None) -> dict | None:
    """The live account behind a valid user cookie (re-read, so a disabled
    account or changed role takes effect at once), else None."""
    if not value or not value.startswith("u~") or not _valid_session(value, _ACCT_KEY):
        return None
    parts = value.split("~")
    if len(parts) < 4:
        return None
    from ..services import accounts
    u = accounts.get(parts[1])
    if not u or u["disabled"]:
        return None
    return u


def identify(request: Request, header_token: str | None = None) -> tuple[str, dict | None]:
    """Who is asking: ("off", None) accounts mode off; ("machine", None) shared
    token (header or token cookie); ("user", account); ("anon", None)."""
    from ..services import accounts
    if not accounts.mode_active():
        return "off", None
    expected = resolve_token(settings_of(request).token)
    if expected:
        hdr = header_token if header_token is not None else request.headers.get("x-cuore-token", "")
        if token_ok(hdr or "", expected) or _valid_session(request.cookies.get(COOKIE), expected):
            return "machine", None
    u = _user_from_cookie(request.cookies.get(COOKIE))
    return ("user", u) if u else ("anon", None)


def actor(request: Request, fallback: str) -> str:
    """The name to record as author: the logged-in username in accounts mode,
    else the caller-supplied/legacy value."""
    u = getattr(request.state, "user", None)
    return u["username"] if u else fallback


def require_role(*roles: str):
    """Dependency: in accounts mode only these roles (admin always) or the
    shared token may proceed. A no-op when accounts mode is off."""
    allowed = set(roles) | {"admin"}

    async def _dep(request: Request) -> None:
        kind, u = identify(request)
        if kind in ("off", "machine"):
            return
        if kind == "user" and u["role"] in allowed:
            request.state.user = u
            return
        if kind == "anon" and request.method in _SAFE and not request.url.path.startswith("/api/"):
            raise LoginRedirect("/login?next=" + quote(request.url.path, safe=""))
        raise HTTPException(status_code=403, detail="your role cannot do this")

    return _dep


async def require_token(
    request: Request,
    x_cuore_token: str | None = Header(default=None),
    token: str | None = Query(default=None,
                              description="Alternative to the header, for "
                                          "links opened on a tablet."),
) -> None:
    """Reject the request unless it is authorised.

    A no-op when no token is configured. Reads (GET/HEAD) accept the
    X-Cuore-Token header, ?token=, or a valid session cookie. State-changing
    methods accept only a session cookie or the header (never ?token=, so a
    pasted link cannot carry write rights). Compared with
    :func:`hmac.compare_digest`.
    """
    if request.url.path not in OPEN_PATHS:
        kind, user = identify(request, x_cuore_token)
        if kind == "user":
            request.state.user = user
            return
        if kind == "machine":
            return
        if kind == "anon":
            expected = resolve_token(settings_of(request).token)
            if (request.method in _SAFE and expected
                    and token_ok(token or "", expected)):
                return
            path = request.url.path
            if request.method in _SAFE and (not path.startswith("/api/") or path == "/api/docs"):
                q = urlencode([(k, v) for k, v in request.query_params.multi_items()
                               if k != "token"])
                raise LoginRedirect("/login?next=" + quote(path + (f"?{q}" if q else ""), safe=""))
            raise HTTPException(status_code=401 if request.method in _SAFE else 403,
                                detail="login required")
    expected = resolve_token(settings_of(request).token)
    if not expected or request.url.path in OPEN_PATHS:
        return
    has_session = _valid_session(request.cookies.get(COOKIE), expected)
    header_ok = token_ok(x_cuore_token or "", expected)
    if request.method in _SAFE:
        if has_session or header_ok or token_ok(token or "", expected):
            return
        path = request.url.path
        if not path.startswith("/api/") or path == "/api/docs":
            q = urlencode([(k, v) for k, v in request.query_params.multi_items()
                           if k != "token"])
            nxt = path + (f"?{q}" if q else "")
            raise LoginRedirect("/login?next=" + quote(nxt, safe=""))
        raise HTTPException(
            status_code=401, detail="missing or incorrect token",
            headers={"WWW-Authenticate": "Token"})
    if has_session or header_ok:
        return
    raise HTTPException(
        status_code=403,
        detail="this action needs a logged-in session (open /login); a "
               "?token= link is read-only")
