"""``GET /api/systems/{vin}/state`` -- read-only live state for the Systems
map overlay (Phase 2, ``docs/research/SYSTEMS_DIVE_IN_PLAN_2026-10-08.md``):
per-system colour state + open-code badge, hot co-occurrence/dependency
edges, and the session timeline for the time slider. Fed entirely by
:mod:`cuore.services.systems_map_bridge` -- see that module for sourcing.

``GET /api/systems/{vin}/live`` is Phase 4's live overlay: per-system worst
live colour grade, an honest scanner status, and any brand-new DTC the live
poller has just seen -- also entirely :mod:`cuore.services.systems_map_bridge`
(:func:`~cuore.services.systems_map_bridge.live_state`). No route here ever
writes to the car.

Registered on ``cuore.app`` next to the other ``api`` router includes:
``app.include_router(systems_map_api.router, prefix="/api")``
(``from .api import systems_map as systems_map_api``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services import systems_map_bridge
from .deps import require_token

router = APIRouter(tags=["systems"], dependencies=[Depends(require_token)])


@router.get("/systems/{vin}/state",
            summary="Live per-system map state, hot edges and session timeline")
def systems_state(vin: str) -> dict[str, Any]:
    return systems_map_bridge.build_state(vin)


@router.get("/systems/{vin}/live",
            summary="Live overlay: per-system worst live grade, scanner status, new DTCs")
def systems_live(vin: str) -> dict[str, Any]:
    return systems_map_bridge.live_state(vin)


__all__ = ["router"]
