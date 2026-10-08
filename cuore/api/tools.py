"""HTTP surface for the mechanic-facing Tools catalogue.

Read-only data for a page another agent renders at ``/tools``. Nothing here
writes to the car; the catalogue itself lists the MCP-only write operations
as inert cards (see ``cuore/services/tools_bridge.py``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from ..services import tools_bridge
from .deps import require_token

router = APIRouter(tags=["tools"], dependencies=[Depends(require_token)])


def _catalogue(request: Request, vin: str) -> dict[str, Any]:
    state = tools_bridge.current_state(vin)
    return tools_bridge.catalogue(request.app.openapi(), state)


@router.get("/tools/catalogue", summary="The full mechanic-facing tools catalogue")
def catalogue(request: Request, vin: str = Query(default="")) -> dict[str, Any]:
    return _catalogue(request, vin)


@router.get("/tools/suggest", summary="Next sensible tools given the current state")
def suggest(request: Request, vin: str = Query(default="")) -> dict[str, Any]:
    cat = _catalogue(request, vin)
    return {"suggested": tools_bridge.suggest(cat["state"], cat)}


@router.get("/tools/workflows", summary="Semi-automatic read-only workflows")
def workflows(request: Request, vin: str = Query(default="")) -> dict[str, Any]:
    return {"workflows": _catalogue(request, vin)["workflows"]}


@router.post("/tools/shape", summary="Shape one tool's raw payload for display")
def shape(tool_id: str = Body(..., embed=True), payload: Any = Body(..., embed=True)
         ) -> dict[str, Any]:
    return tools_bridge.shape_result(tool_id, payload)


__all__ = ["router"]
