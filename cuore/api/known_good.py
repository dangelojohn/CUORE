"""GET /api/live/known-good: known-good reference bands for live channels.

A new router file, kept separate from ``cuore/api/live.py`` per instruction
(that file is owned by another agent's concurrent work). Read-only, and the
only HTTP surface for :mod:`cuore.services.known_good_bridge`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services import known_good_bridge
from .deps import require_token

router = APIRouter(tags=["known-good"], dependencies=[Depends(require_token)])


@router.get("/live/known-good",
           summary="Known-good bands for live-dashboard channels, "
                   "optionally with this VIN's own observed ranges")
def known_good(vin: str = "") -> dict[str, Any]:
    """Every live channel's reference band (min/max/warn/alarm, confidence,
    source, notes) this project has researched, keyed by channel id from
    :mod:`cuore.live.channels`. Pass ``vin`` to also get that vehicle's own
    MES-logged percentiles per channel (``observed`` in the response) --
    never a spec, always distinct from ``channels``.
    """
    return known_good_bridge.known_good_payload(vin=vin)


__all__ = ["router"]
