"""GET /api/vehicles/{vin}/flow -- the 12-step mechanic flow, as JSON.

The HTTP face of ``flow_bridge.flow_state``. Read-only: nothing here writes
to the car or the corpus.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services import flow_bridge
from .deps import require_token

router = APIRouter(tags=["vehicles"], dependencies=[Depends(require_token)])


@router.get("/vehicles/{vin}/flow", summary="The 12-step mechanic flow for this VIN")
def flow(vin: str) -> dict[str, Any]:
    return flow_bridge.flow_state(vin)


__all__ = ["router"]
