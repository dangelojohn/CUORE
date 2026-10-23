"""``GET /api/cables``: the coloured adapter-cable catalogue, read-only.

External reference, not a CUORE reading -- see
:mod:`cuore.services.adapter_cables_bridge`. Only ``blue_a5`` and ``grey_a6``
carry a non-null ``live_route``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services import adapter_cables_bridge
from .deps import require_token

router = APIRouter(tags=["cables"], dependencies=[Depends(require_token)])


@router.get("/cables", summary="Adapter-cable catalogue (external reference, read-only)")
def cables(brand: str = "") -> dict[str, Any]:
    return adapter_cables_bridge.payload(brand)


__all__ = ["router"]
