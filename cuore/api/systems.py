"""``/systems*``: the vehicle-systems graph and DTC-system correlation,
fed by :mod:`cuore.services.systems_bridge` -- see ``mes.systems`` for the
sourced data and the correlation contract.

Not registered on the app here -- ``app.py`` is owned by another agent. The
one line needed there (next to the other ``api`` router includes):

    ``app.include_router(systems_api.router, prefix="/api")``

(importing this module as ``from .api import systems as systems_api``.)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services import systems_bridge
from ..services.errors import NotFound
from .deps import require_token

router = APIRouter(tags=["systems"], dependencies=[Depends(require_token)])


@router.get("/systems", summary="Every vehicle system in the graph")
def list_systems() -> dict[str, Any]:
    rows = systems_bridge.systems()
    return {"systems": list(rows.values()), "count": len(rows)}


@router.get("/systems/for-code/{code}", summary="Which system(s) a DTC implicates")
def systems_for_code(code: str, description: str = "") -> dict[str, Any]:
    rows = systems_bridge.systems_for_code(code, description)
    return {"code": code.strip().upper(), "systems": rows, "count": len(rows)}


@router.get("/vehicles/{vin}/systems", summary="DTC-system correlation for one vehicle")
def vehicle_systems(vin: str) -> dict[str, Any]:
    result = systems_bridge.correlate(vin)
    if isinstance(result, dict) and result.get("error"):
        raise NotFound(result["error"])
    return result


__all__ = ["router"]
