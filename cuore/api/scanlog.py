"""``GET /api/scans/{vin}`` -- the scan log, as JSON.

The HTTP face of ``cuore.live.scanlog``/``cuore.services.scanlog_bridge``.
Read-only: nothing here writes to the car, and the MES-format export writes
only under ``CUORE_STATE_DIR/scans/<vin>/``, never into MultiEcuScan's own
LOG folder.
"""

from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..live.config import state_dir
from ..services import scanlog_bridge
from .deps import require_token

router = APIRouter(prefix="/scans", tags=["scans"], dependencies=[Depends(require_token)])

#: Store files under CUORE_STATE_DIR that /scans/search covers, besides the
#: recordings/ CSV headers handled separately below. Self-contained here
#: (not a cross-import of mes-log-mcp's own mes.cuore_log, a different
#: process/venv) -- same five sources, same read-only posture: this endpoint
#: never writes to any of them.
_SEARCH_FILES = ("observations.jsonl", "owner_events.jsonl", "attested.jsonl", "jobs.jsonl")


def _bound(value: str, *, end: bool) -> str:
    v = (value or "").strip()
    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        return v + ("T23:59:59" if end else "T00:00:00")
    return v


def _in_bounds(stamp: str, since: str, until: str) -> bool:
    if not stamp:
        return not since and not until
    if since and stamp < _bound(since, end=False):
        return False
    if until and stamp > _bound(until, end=True):
        return False
    return True


def _line_at(line: str) -> Optional[str]:
    try:
        obj = _json.loads(line)
    except ValueError:
        return None
    return str(obj.get("at")) if isinstance(obj, dict) and obj.get("at") else None


def _search_cuore_logs(pattern: str, *, since: str = "", until: str = "",
                       kinds: Optional[list[str]] = None, context_lines: int = 2,
                       max_matches: int = 40) -> dict[str, Any]:
    """Regex search (case-insensitive), newest first, across every CUORE
    log -- same shape and sources as ``mes.cuore_log.search`` on the MCP
    side (that module's own docstring explains why this is reimplemented
    here rather than imported: the two run as separate processes)."""
    rx = re.compile(pattern, re.IGNORECASE)
    all_sources = tuple(f.removesuffix(".jsonl") for f in _SEARCH_FILES) + ("recordings",)
    want = {k.strip().lower() for k in (kinds or []) if k.strip()} or set(all_sources)
    d = state_dir()
    hits: list[dict[str, Any]] = []

    for name in _SEARCH_FILES:
        if name.removesuffix(".jsonl") not in want:
            continue
        path = d / name
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if not rx.search(line):
                continue
            at = _line_at(line)
            if not _in_bounds(at or "", since, until):
                continue
            lo, hi = max(0, i - context_lines), min(len(lines), i + context_lines + 1)
            hits.append({
                "source": name.removesuffix(".jsonl"), "file": name, "line": i + 1, "at": at,
                "match": line.strip()[:500],
                "context": [f"{j + 1}: {lines[j][:500]}" for j in range(lo, hi)],
            })

    if "recordings" in want:
        rdir = d / "recordings"
        if rdir.is_dir():
            try:
                csvs = sorted(rdir.glob("*.csv"))
            except OSError:
                csvs = []
            for p in csvs:
                try:
                    head = p.read_text(encoding="utf-8", errors="replace").splitlines()[:2]
                except OSError:
                    continue
                for i, line in enumerate(head):
                    if rx.search(line):
                        hits.append({
                            "source": "recordings", "file": p.name, "line": i + 1, "at": None,
                            "match": line.strip()[:500],
                            "context": [f"{j + 1}: {head[j][:500]}" for j in range(len(head))],
                        })

    hits.sort(key=lambda h: h.get("at") or "", reverse=True)
    truncated = len(hits) > max_matches
    return {"count": min(len(hits), max_matches), "truncated": truncated,
           "matches": hits[:max_matches]}


@router.get("/search", summary="Regex search across every CUORE log, newest first")
def search(pattern: str = Query(...), since: str = Query(""), until: str = Query(""),
          kinds: str = Query("", description="comma-separated: observations,owner_events,"
                                             "attested,jobs,recordings; empty = all"),
          context_lines: int = Query(2), max_matches: int = Query(40)) -> dict[str, Any]:
    kind_list = [k.strip() for k in kinds.split(",") if k.strip()]
    return _search_cuore_logs(pattern, since=since, until=until, kinds=kind_list,
                              context_lines=context_lines, max_matches=max_matches)


@router.get("/{vin}", summary="Scan summaries for one vehicle, newest first")
def list_scans(vin: str) -> dict[str, Any]:
    return scanlog_bridge.list_scans(vin)


@router.get("/{vin}/diff", summary="Diff two scans")
def diff(vin: str, a: str = Query(...), b: str = Query(...)) -> dict[str, Any]:
    return scanlog_bridge.diff(vin, a, b)


@router.get("/{vin}/{scan_id}", summary="One scan in full")
def scan(vin: str, scan_id: str) -> dict[str, Any]:
    return scanlog_bridge.scan(vin, scan_id)


@router.get("/{vin}/{scan_id}/export", summary="Export one scan as JSON or an MES-style log")
def export(vin: str, scan_id: str, fmt: str = Query("json")) -> Response:
    result = scanlog_bridge.export(vin, scan_id, fmt)
    if fmt == "json":
        import json
        body = json.dumps(result["content"], default=str)
    else:
        body = result["content"]
    return Response(content=body, media_type=result["media_type"],
                    headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'})


__all__ = ["router"]
