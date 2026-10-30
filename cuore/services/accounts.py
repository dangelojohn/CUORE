"""User accounts and roles (rollout phase 2).

Stored in ``<state_dir>/accounts.json``. Accounts MODE is off unless the file
holds an enabled admin AND ``accounts_enabled`` is true, so an existing
shared-token install is never locked out by this module merely existing.

Passwords: scrypt with a per-user random salt, constant-time compare. Hashes
and passwords are never returned by any function here and never logged.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime
from typing import Any

ROLES = ("admin", "shop_lead", "technician")
SHOP_KINDS = ("dealer", "independent")
MIN_PASSWORD = 8
MAX_FAILS = 5
COOLDOWN = 5 * 60.0
CLOCK = time.monotonic          # tests replace this
_USERNAME = re.compile(r"^[a-z0-9_-]{2,32}$")
_SCRYPT = dict(n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
_LOCK = threading.RLock()
_FAILS: dict[str, list[float]] = {}


class AccountError(ValueError):
    """Bad input for an account operation (message is safe to show)."""


def _path():
    from ..live.config import state_dir
    return state_dir() / "accounts.json"


def _load() -> dict[str, Any]:
    p = _path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("accounts_enabled", False)
    if not isinstance(data.get("users"), list):
        data["users"] = []
    return data


def _save(data: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _hash(password: str, salt: bytes) -> str:
    return base64.b64encode(hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)).decode()


def _make_hash(password: str) -> dict[str, str]:
    salt = secrets.token_bytes(16)
    return {"salt": base64.b64encode(salt).decode(), "hash": _hash(password, salt)}


def _check_password_rules(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise AccountError(f"password must be at least {MIN_PASSWORD} characters")


def _public(u: dict[str, Any]) -> dict[str, Any]:
    return {k: u.get(k) for k in ("username", "display_name", "role", "shop_id",
                                  "shop_kind", "created_at", "disabled")}


def _find(data: dict[str, Any], username: str) -> dict[str, Any] | None:
    username = (username or "").strip().lower()
    for u in data["users"]:
        if u.get("username") == username:
            return u
    return None


# --- mode -------------------------------------------------------------------

def mode_active() -> bool:
    """True only when the switch is on AND an enabled admin exists."""
    try:
        d = _load()
    except Exception:  # noqa: BLE001 -- never lock anyone out on a read problem
        return False
    return bool(d.get("accounts_enabled")) and any(
        u.get("role") == "admin" and not u.get("disabled") for u in d["users"])


def set_mode(enabled: bool) -> None:
    with _LOCK:
        d = _load()
        if enabled and not any(u.get("role") == "admin" and not u.get("disabled") for u in d["users"]):
            raise AccountError("create an enabled admin account before enabling accounts mode")
        d["accounts_enabled"] = bool(enabled)
        _save(d)


# --- operations ---------------------------------------------------------------

def create(username: str, password: str, role: str = "technician", display_name: str = "",
           shop_id: str = "main", shop_kind: str = "independent") -> dict[str, Any]:
    username = (username or "").strip().lower()
    if not _USERNAME.match(username):
        raise AccountError("username must be 2-32 characters: a-z, 0-9, _ or -")
    if role not in ROLES:
        raise AccountError(f"role must be one of {', '.join(ROLES)}")
    if shop_kind not in SHOP_KINDS:
        raise AccountError("shop_kind must be dealer or independent")
    _check_password_rules(password)
    shop_id = (shop_id or "main").strip()[:40] or "main"
    with _LOCK:
        d = _load()
        if _find(d, username):
            raise AccountError("that username already exists")
        u = {"username": username, "display_name": (display_name or username).strip()[:60],
             "role": role, "shop_id": shop_id, "shop_kind": shop_kind,
             "password": _make_hash(password),
             "created_at": datetime.now().isoformat(timespec="seconds"), "disabled": False}
        d["users"].append(u)
        _save(d)
    return _public(u)


def verify(username: str, password: str) -> dict[str, Any] | None:
    """Login check. Returns the public account or None. Locks a name out after
    MAX_FAILS failures for COOLDOWN seconds (applies to unknown names too, so
    the response does not reveal which usernames exist)."""
    key = (username or "").strip().lower()
    with _LOCK:
        now = CLOCK()
        hits = [t for t in _FAILS.get(key, []) if now - t < COOLDOWN]
        _FAILS[key] = hits
        if len(hits) >= MAX_FAILS:
            return None
        u = _find(_load(), key)
    ok = False
    if u and not u.get("disabled") and isinstance(u.get("password"), dict):
        salt = base64.b64decode(u["password"]["salt"])
        ok = hmac.compare_digest(_hash(password or "", salt), u["password"]["hash"])
    else:
        _hash(password or "", b"\0" * 16)       # equalise timing for unknown/disabled
    with _LOCK:
        if ok:
            _FAILS.pop(key, None)
        else:
            _FAILS.setdefault(key, []).append(CLOCK())
    return _public(u) if ok and u else None


def locked_out(username: str) -> int:
    """Seconds of lockout remaining for this name (0 = not locked)."""
    key = (username or "").strip().lower()
    with _LOCK:
        now = CLOCK()
        hits = [t for t in _FAILS.get(key, []) if now - t < COOLDOWN]
        if len(hits) < MAX_FAILS:
            return 0
        return max(1, int(COOLDOWN - (now - hits[0])) + 1)


def get(username: str) -> dict[str, Any] | None:
    u = _find(_load(), username)
    return _public(u) if u else None


def set_password(username: str, password: str) -> None:
    _check_password_rules(password)
    with _LOCK:
        d = _load()
        u = _find(d, username)
        if not u:
            raise AccountError("no such user")
        u["password"] = _make_hash(password)
        _save(d)
        _FAILS.pop(u["username"], None)


def _enabled_admins(d: dict[str, Any]) -> int:
    return sum(1 for u in d["users"] if u.get("role") == "admin" and not u.get("disabled"))


def disable(username: str, disabled: bool = True) -> None:
    with _LOCK:
        d = _load()
        u = _find(d, username)
        if not u:
            raise AccountError("no such user")
        if disabled and u.get("role") == "admin" and not u.get("disabled") and _enabled_admins(d) <= 1 \
                and d.get("accounts_enabled"):
            raise AccountError("cannot disable the last enabled admin while accounts mode is on")
        u["disabled"] = bool(disabled)
        _save(d)


def list_users(shop_id: str | None = None) -> list[dict[str, Any]]:
    """Public fields only (no hashes). ``shop_id`` filters to one shop."""
    out = [_public(u) for u in _load()["users"]]
    if shop_id is not None:
        out = [u for u in out if u["shop_id"] == shop_id]
    return sorted(out, key=lambda u: (u["shop_id"], u["username"]))
