"""Crawl ingest: lets a crawl script on an allow-listed public site save pages.

CUORE has no auth and a public page (e.g. autodoc.co.uk) will POST to
http://127.0.0.1:5000, so this router is deliberately narrow:

* a request is accepted only with BOTH a valid one-time token
  (``X-Cuore-Ingest``, constant-time compare against
  ``CUORE_STATE_DIR/ingest_token.txt``) AND an ``Origin`` in the allowlist
  (``CUORE_STATE_DIR/ingest_origins.json``). Both are created by
  ``scripts/ingest_token.py``. Anything else is 403.
* bodies are JSON, at most 2 MB, validated for JSON syntax only (never
  interpreted) and written atomically to
  ``parts_catalog/sources/ingest/<source>/<key>.json``.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import tempfile
from pathlib import Path

import anyio
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..live.config import state_dir

router = APIRouter(tags=["ingest"])

MAX_BYTES = 2 * 1024 * 1024
PART_RE = re.compile(r"^[A-Za-z0-9._|-]{1,120}$")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def _valid_part(s: str) -> bool:
    if not PART_RE.match(s) or s.startswith(".") or s.endswith("."):
        return False
    return s.split(".")[0].upper() not in _RESERVED


def _fname(key: str) -> str:
    # "|" is illegal in Windows file names; "~" is outside the key alphabet,
    # so the mapping is reversible and collision-free.
    return key.replace("|", "~") + ".json"


def _cors(origin: str) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Cuore-Ingest",
        "Access-Control-Allow-Private-Network": "true",
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
    }


def _allowed_origins() -> list[str]:
    try:
        data = json.loads((state_dir() / "ingest_origins.json").read_text(encoding="utf-8"))
        return [o for o in data if isinstance(o, str)]
    except (OSError, ValueError, TypeError):
        return []


def _token_ok(given: str | None) -> bool:
    try:
        real = (state_dir() / "ingest_token.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not real or not given:
        return False
    return hmac.compare_digest(real.encode(), given.encode())


def _reply(status: int, body: dict, origin: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=body,
                        headers=_cors(origin) if origin else None)


def _gate(request: Request):
    """Return (origin, None) when allowed, else (None, 403 response)."""
    origin = request.headers.get("origin")
    if not origin or origin not in _allowed_origins():
        return None, _reply(403, {"error": "forbidden"})
    if not _token_ok(request.headers.get("x-cuore-ingest")):
        return None, _reply(403, {"error": "forbidden"}, origin)
    return origin, None


def _dir(source: str) -> Path:
    return state_dir() / "parts_catalog" / "sources" / "ingest" / source


@router.options("/ingest/{source}/{key}")
def ingest_preflight(source: str, key: str, request: Request) -> Response:
    origin = request.headers.get("origin")
    if not origin or origin not in _allowed_origins():
        return Response(status_code=403)
    return Response(status_code=204, headers=_cors(origin))


@router.get("/ingest/{source}/keys")
def ingest_keys(source: str, request: Request):
    origin, denied = _gate(request)
    if denied:
        return denied
    if not _valid_part(source):
        return _reply(400, {"error": "bad source"}, origin)
    d = _dir(source)
    keys = sorted(p.stem.replace("~", "|") for p in d.glob("*.json")) if d.is_dir() else []
    return _reply(200, {"source": source, "count": len(keys), "keys": keys}, origin)


@router.post("/ingest/{source}/{key}")
def ingest_save(source: str, key: str, request: Request):
    origin, denied = _gate(request)
    if denied:
        return denied
    if not _valid_part(source) or not _valid_part(key):
        return _reply(400, {"error": "bad source or key"}, origin)
    try:
        declared = int(request.headers.get("content-length", "-1"))
    except ValueError:
        declared = -1
    if declared > MAX_BYTES:
        return _reply(413, {"error": "body too large"}, origin)
    body = anyio.from_thread.run(request.body)
    if len(body) > MAX_BYTES:
        return _reply(413, {"error": "body too large"}, origin)
    try:
        json.loads(body)
    except ValueError:
        return _reply(400, {"error": "body is not valid JSON"}, origin)
    d = _dir(source)
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ing-", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        os.replace(tmp, d / _fname(key))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return _reply(200, {"saved": True, "source": source, "key": key, "bytes": len(body)}, origin)
