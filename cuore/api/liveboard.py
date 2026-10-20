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

from fastapi import APIRouter, Body, Depends, Form

from ..services import liveboard_bridge
from .deps import require_token

router = APIRouter(tags=["liveboard"], dependencies=[Depends(require_token)])


@router.get("/live/chassis/passive",
           summary="CAN-CH passive panel: a 2 s receive-only listen decoded through the "
                   "Giorgio DBC (grey A6 cable only)")
def liveboard_chassis_passive() -> dict[str, Any]:
    return liveboard_bridge.chassis_passive()


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


# --- Freeze frame panel: capture (Start/Stop), status, Save, Discard -------
#
# Read-only until Save: capture/status/stop only ever read the car (through
# cuore.live.ops, which refuses on its own if a poller or MES holds the
# adapter); Save is the one write, into the CUORE log via
# cuore.live.store.record_observation. Save also accepts a plain HTML form
# post (application/x-www-form-urlencoded, Form() below) so it works with
# no JS -- Start/Stop still need JS, since they drive the live "Capturing..."
# state.

@router.post("/liveboard/{vin}/freeze/capture",
            summary="Start a freeze-frame capture: stored codes, then every "
                    "supported PID's freeze frame + a Mode 01 snapshot, plus "
                    "readiness -- read-only, held unsaved for 30 minutes")
def liveboard_freeze_capture(vin: str) -> dict[str, Any]:
    return liveboard_bridge.freeze_capture_start(vin)


@router.get("/liveboard/{vin}/freeze/status",
           summary="Poll a freeze-frame capture's progress")
def liveboard_freeze_status(vin: str, capture_id: str) -> dict[str, Any]:
    return liveboard_bridge.freeze_capture_status(vin, capture_id)


@router.post("/liveboard/{vin}/freeze/stop",
            summary="Stop a running freeze-frame capture; data already read is "
                    "kept and the capture ends partial")
def liveboard_freeze_stop(vin: str, capture_id: str = Body(..., embed=True)) -> dict[str, Any]:
    return liveboard_bridge.freeze_capture_stop(vin, capture_id)


@router.post("/liveboard/{vin}/freeze/save",
            summary="Save a finished freeze-frame capture into the CUORE log as "
                    "from-car observations; returns the scan id it lands under")
def liveboard_freeze_save(vin: str, capture_id: str = Form(...),
                          note: str = Form("")) -> dict[str, Any]:
    return liveboard_bridge.freeze_capture_save(vin, capture_id, note)


@router.post("/liveboard/{vin}/freeze/discard",
            summary="Discard an unsaved freeze-frame capture")
def liveboard_freeze_discard(vin: str, capture_id: str = Body(..., embed=True)) -> dict[str, Any]:
    return liveboard_bridge.freeze_capture_discard(vin, capture_id)


__all__ = ["router"]
