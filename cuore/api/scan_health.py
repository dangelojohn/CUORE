"""HTTP surface for the scan health report.

Thin wrapper over :mod:`cuore.services.scan_health_bridge`, same posture as
every other API module here -- see ``cuore/api/tests.py``. The only mutation
is ``POST .../health/save``, which writes the report to disk (never over a
hand-written file of the same name; see the bridge's ``save``).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from ..services import scan_health_bridge
from .deps import require_token

router = APIRouter(tags=["scan_health"], dependencies=[Depends(require_token)])


@router.get("/scans/{vin}/{scan_id}/health", summary="The scan health report, as JSON")
def scan_health_json(vin: str, scan_id: str) -> dict[str, Any]:
    sid = None if scan_id == "latest" else scan_id
    return scan_health_bridge.build_cached(vin, sid)


@router.get("/scans/{vin}/{scan_id}/health.md", summary="The scan health report, as markdown",
           response_class=PlainTextResponse)
def scan_health_markdown(vin: str, scan_id: str) -> str:
    sid = None if scan_id == "latest" else scan_id
    return scan_health_bridge.markdown(vin, sid)


@router.post("/scans/{vin}/{scan_id}/health/save",
            summary="Write the report to disk (never over a hand-written file)")
def scan_health_save(vin: str, scan_id: str) -> dict[str, Any]:
    sid = None if scan_id == "latest" else scan_id
    return scan_health_bridge.save(vin, sid)


__all__ = ["router"]
