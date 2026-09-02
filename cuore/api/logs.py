"""Raw log access: the index, one file verbatim, and regex search.

**Security note, because this endpoint is where it matters.** ``/api/log/{name}``
takes a caller-supplied filename. It resolves through
:func:`mes.paths.resolve_log`, which requires a bare filename matching a MES log
pattern and verifies the fully resolved real path lies inside a configured root.

That is not a theoretical precaution. An earlier version of the MCP server built
the path as ``Path(LOG_DIR) / name``, which on Windows contains nothing: a
``..`` walks out, and an *absolute* name replaces the base entirely. Every file
the server process could read was reachable through a tool call. The fix is
regression-tested in ``mes-log-mcp/tests/check_server.py``, and this route
inherits it by calling the same resolver.

Serving it over HTTP widens the audience from one local process to every device
that can reach the port, so the resolver must never be bypassed for convenience.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from ..services import mes_bridge
from .deps import require_token

router = APIRouter(tags=["logs"], dependencies=[Depends(require_token)])


@router.get("/logs", summary="The log index, newest first")
def logs(kind: str = Query(default="", description="'fes', 'scan', or empty."),
         vehicle: str = "", vin: str = "", since: str = "", until: str = "",
         limit: int = Query(default=30, ge=1, le=500),
         include_simulation: bool = False) -> dict[str, Any]:
    return mes_bridge.list_logs(kind=kind, vehicle=vehicle, vin=vin,
                                since=since, until=until, limit=limit,
                                include_simulation=include_simulation)


@router.get("/log/{name}", summary="One log, verbatim")
def log(name: str = Path(..., description="Bare filename. Paths are rejected."),
        max_bytes: int = Query(default=200_000, ge=1, le=5_000_000)
        ) -> dict[str, Any]:
    """Read a MES log as text, decoded and with stray control bytes stripped.

    Flags simulation content explicitly, and reports SCAN provenance as
    unverifiable rather than clean -- that format carries no simulation marker
    at all, so silence about it would be a claim the file cannot support.
    """
    return mes_bridge.read_log(name, max_bytes=max_bytes)


@router.get("/search", summary="Regex search across logs")
def search(pattern: str = Query(..., min_length=1,
                                description="Python regex, case-insensitive."),
           kind: str = "", vehicle: str = "", vin: str = "",
           context_lines: int = Query(default=2, ge=0, le=20),
           max_matches: int = Query(default=40, ge=1, le=500),
           include_simulation: bool = False) -> dict[str, Any]:
    return mes_bridge.search_logs(pattern, kind=kind, vehicle=vehicle, vin=vin,
                                  context_lines=context_lines,
                                  max_matches=max_matches,
                                  include_simulation=include_simulation)
