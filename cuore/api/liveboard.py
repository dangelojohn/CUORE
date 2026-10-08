"""HTTP surface for the liveboard: a read-only, at-a-glance board of live
channels grouped by system, each graded against ``mes.known_good`` -- built
for a passenger (never the driver) to watch safely while someone else
drives.

Thin wrapper over :mod:`cuore.services.liveboard_bridge`, same posture as
every other live route in :mod:`cuore.api.live`. The page itself saves
snapshots through the existing ``POST /api/live/snapshots`` (source
``"live"``, layout ``"liveboard"``) -- this module does not duplicate that.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from ..services import liveboard_bridge
from .deps import require_token

router = APIRouter(tags=["liveboard"], dependencies=[Depends(require_token)])


@router.get("/liveboard/{vin}",
           summary="Live channels grouped by system, rated and graded against known-good")
def liveboard_board(vin: str) -> dict[str, Any]:
    return liveboard_bridge.board(vin)


@router.post("/liveboard/evaluate",
            summary="Grade a set of live values; recommendations, excessive first")
def liveboard_evaluate(values: dict[str, float] = Body(..., embed=True)) -> dict[str, Any]:
    return {"recommendations": liveboard_bridge.snapshot_recommendations(values)}


@router.post("/liveboard/{vin}/snapshot-to-job",
            summary="Score a saved liveboard snapshot against the current job's hypotheses")
def liveboard_snapshot_to_job(vin: str, snapshot_id: str = Body(..., embed=True),
                              values: dict[str, float] = Body(..., embed=True)
                              ) -> dict[str, Any]:
    return liveboard_bridge.attach_snapshot_to_job(vin, snapshot_id, values)


__all__ = ["router"]
