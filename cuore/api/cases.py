"""``/vehicles/{vin}/cases/*``: case memory, fed by
:mod:`cuore.services.cases_bridge` -- see ``mes.cases`` for how a Case is
built and how ``match``/``prefill`` are worded (never "proven").

Not registered on the app here -- ``app.py`` is out of scope for this
change. The one line needed there (next to the other ``api`` router
includes):

    ``app.include_router(cases_api.router, prefix="/api")``

(importing this module as ``from .api import cases as cases_api``.)
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from ..services import cases_bridge
from .deps import require_token

router = APIRouter(tags=["cases"], dependencies=[Depends(require_token)])


def _codes_list(codes: Optional[str]) -> list[str]:
    if not codes:
        return []
    return [c.strip() for c in codes.split(",") if c.strip()]


@router.get("/vehicles/{vin}/cases/match", summary="Prior cases for this model, ranked by overlap")
def match(vin: str, codes: str = Query("", description="Comma-separated DTCs")) -> dict[str, Any]:
    return cases_bridge.match(vin, _codes_list(codes))


@router.get("/vehicles/{vin}/cases/prefill", summary="Suggested starting point from the best prior case")
def prefill(vin: str, codes: str = Query("", description="Comma-separated DTCs")) -> dict[str, Any]:
    return cases_bridge.prefill(vin, _codes_list(codes))


__all__ = ["router"]
