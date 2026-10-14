"""``GET /api/scans/{vin}`` -- the scan log, as JSON.

The HTTP face of ``cuore.live.scanlog``/``cuore.services.scanlog_bridge``.
Read-only: nothing here writes to the car, and the MES-format export writes
only under ``CUORE_STATE_DIR/scans/<vin>/``, never into MultiEcuScan's own
LOG folder.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..services import scanlog_bridge
from .deps import require_token

router = APIRouter(prefix="/scans", tags=["scans"], dependencies=[Depends(require_token)])


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
