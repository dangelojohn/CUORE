"""HTTP client for the cuore bench service. Stdlib only.

Why this exists: the obd2 MCP server and cuore used to drive the adapter
separately, each with its own cable declaration and its own "bus verified"
flag. On 2026-09-25 that meant verifying the same bus twice, a cable declared
in the web UI that the MCP server never heard about, and MCP tools running
stale code until Claude Code restarted them. Now cuore owns the adapter and
the MCP read tools are requests to it.

If nothing answers at ``CUORE_URL`` and the URL is local, the client starts
cuore itself (``CUORE_AUTOSTART=0`` turns that off). When cuore still cannot
be reached the caller falls back to in-process, so there is exactly one owner
either way.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]


class CuoreUnavailable(Exception):
    """Nothing answered at the configured URL, even after an autostart."""


class CuoreTimeout(Exception):
    """cuore accepted the request but did not finish in time. The operation
    may still be running there, so the caller must not retry it elsewhere."""


def base_url() -> str:
    return os.environ.get("CUORE_URL", "http://127.0.0.1:5000").rstrip("/")


def _is_local(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return host in ("127.0.0.1", "localhost", "::1")


def _qs(query: Optional[dict[str, Any]]) -> str:
    if not query:
        return ""
    clean: dict[str, str] = {}
    for k, v in query.items():
        if v is None or v == "":
            continue
        clean[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    return ("?" + urllib.parse.urlencode(clean)) if clean else ""


def _request(method: str, path: str, query: Optional[dict[str, Any]],
             body: Optional[dict[str, Any]], timeout: float) -> Any:
    url = base_url() + "/api" + path + _qs(query)
    data = None if body is None else json.dumps(
        {k: v for k, v in body.items() if v is not None}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    token = os.environ.get("CUORE_TOKEN", "").strip()
    if token:
        req.add_header("X-Cuore-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        # cuore answers LiveError as {"error": kind, "detail": msg, "status": n}.
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            payload = {}
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, list):  # FastAPI validation errors
            detail = "; ".join(str(d.get("msg", d)) for d in detail)
        return {"error": detail or str(e), "kind": (payload.get("error")
                if isinstance(payload, dict) else None) or f"HTTP {e.code}",
                "status": e.code}


def ping(timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(base_url() + "/api/capabilities", timeout=timeout).close()
        return True
    except urllib.error.HTTPError:
        return True  # something answered; auth or routing is the caller's problem
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _spawn() -> None:
    port = str(urllib.parse.urlparse(base_url()).port or 5000)
    py = REPO / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    log_dir = Path(os.environ.get("PROGRAMDATA", str(REPO))) / "cuore"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / "cuore-autostart.log", "ab")
    except OSError:
        log = subprocess.DEVNULL  # type: ignore[assignment]
    subprocess.Popen([str(py), "-m", "cuore", "--profile", "bench", "--port", port],
                     cwd=str(REPO), stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)


def ensure_server(wait: float = 20.0) -> dict[str, Any]:
    """Make sure cuore answers; start it when local and allowed."""
    if ping():
        return {"running": True, "started": False}
    if os.environ.get("CUORE_AUTOSTART", "1") == "0" or not _is_local(base_url()):
        raise CuoreUnavailable(f"cuore is not answering at {base_url()} and autostart is off")
    _spawn()
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(0.5)
        if ping(1.0):
            return {"running": True, "started": True}
    raise CuoreUnavailable(f"started cuore but nothing answered at {base_url()} within "
                           f"{wait:.0f} s; see cuore-autostart.log in the cuore state directory")


def call(method: str, path: str, *, query: Optional[dict[str, Any]] = None,
         body: Optional[dict[str, Any]] = None, timeout: float = 120.0) -> Any:
    """One request to cuore's API. Starts cuore once if it is not running."""
    try:
        return _request(method, path, query, body, timeout)
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        if isinstance(e, TimeoutError) or "timed out" in str(e):
            raise CuoreTimeout(f"cuore did not finish {path} within {timeout:.0f} s; it may "
                               f"still be running there, so it was not retried") from e
        ensure_server()
        return _request(method, path, query, body, timeout)


__all__ = ["CuoreUnavailable", "CuoreTimeout", "base_url", "ping", "ensure_server", "call"]
