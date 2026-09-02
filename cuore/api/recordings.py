"""CSV recordings from MES's graph subsystem.

These are the only MES output carrying real per-sample timestamps, which makes
them the only place a measured rate, a dropout, or a threshold excursion can be
computed honestly. The same endpoints will serve CUORE's own drive recordings
at P3 -- the recorder writes the identical schema on purpose, so one analyzer
covers both and nothing here has to learn a second format.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..services import mes_bridge
from .deps import require_token

router = APIRouter(tags=["recordings"], dependencies=[Depends(require_token)])


@router.get("/recordings", summary="Every recording, newest first")
def recordings() -> dict[str, Any]:
    return mes_bridge.list_recordings()


@router.get("/recording/{name}", summary="Columns, timing and events")
def recording(name: str, preview_rows: int = Query(default=10, ge=0, le=200)
              ) -> dict[str, Any]:
    """Parse one recording.

    Reports the *measured* sample rate and any dropouts -- gaps over three
    times the median interval, which is an adapter or ECU-link stall and is
    structurally invisible in a .txt session log.
    """
    return mes_bridge.read_recording(name, preview_rows=preview_rows)


@router.get("/recording/{name}/series", summary="One channel as a timed series")
def series(name: str, parameter: str = Query(
        ..., description="Column name (exact or unique substring) or index.")
        ) -> dict[str, Any]:
    return mes_bridge.recording_series(name, parameter)


@router.get("/recording/{name}/events", summary="Markers, dropouts, excursions")
def events(name: str, condition: str = Query(
        default="",
        description="e.g. 'Engine speed > 3000'. Returns one event per "
                    "excursion, not one per sample.")) -> dict[str, Any]:
    return mes_bridge.recording_events(name, condition=condition)


@router.get("/recording/{name}/snapshot", summary="Post-hoc freeze frame")
def snapshot(name: str, at: float = Query(
        ..., description="Seconds from the start of the recording.")
        ) -> dict[str, Any]:
    """Every recorded value at the sample nearest a given time.

    After ``events`` finds when a DTC tag fired or a threshold tripped, this
    shows what everything else read at that moment.
    """
    return mes_bridge.recording_snapshot(name, at)
