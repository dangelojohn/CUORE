"""``GET /api/wiring``: the failure-type wiring map for one vehicle.

HTTP face of :mod:`cuore.services.wiring_bridge` (payload shape unchanged).
Read-only; touches only the MES log corpus and CUORE's observation store,
never the adapter.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..services import wiring_bridge
from ..services.errors import BadRequest
from .deps import require_token

router = APIRouter(tags=["wiring"], dependencies=[Depends(require_token)])


def _default_vin() -> str:
    try:
        from ..services import mes_bridge
        for v in mes_bridge.vehicles(real_only=True):
            if v.get("vin"):
                return v["vin"]
    except Exception:  # noqa: BLE001
        pass
    return ""


@router.get("/wiring", summary="DTCs grouped by failure type per module, with a ground-suspect score")
def wiring(vin: str = Query(default="", description="VIN; default = the most recent real vehicle"),
           table: bool = Query(default=False, description="Only the flat one-row-per-module table")
           ) -> Any:
    """Per module: which circuits have wiring-type (-11..-17), communication
    (-8x), performance (-9x) or signal/range failures, how many separate reads
    and on which dates; plus a ground-suspect score (an INFERENCE, labelled as
    one). Built from every real MES log of the VIN and the CUORE store."""
    use = (vin or _default_vin()).strip().upper()
    if not use:
        raise BadRequest("no VIN given and no real vehicle found in the log corpus")
    if table:
        return {"vin": use, "rows": wiring_bridge.flat_table(use)}
    return wiring_bridge.wiring_map(use)
