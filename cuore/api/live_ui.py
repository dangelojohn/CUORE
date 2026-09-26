"""HTTP surface for the live-data dashboard UI: layouts, replay, custom
channels, snapshots and triggers.

Every route is a thin wrapper over :mod:`cuore.live.layouts`,
:mod:`cuore.live.replay` and :mod:`cuore.live.ui_store` -- none of it talks to
the adapter, and none of it is evidence about the car (see each module's own
docstring). ``router`` is mounted by the app factory under the ``/api``
prefix, alongside every other live route in :mod:`cuore.api.live`.

Trigger evaluation is NOT done here: rules are stored and validated only.
``GET/PUT /live/triggers`` exist so a rule set can be edited and persisted;
the dashboard's own JavaScript evaluates them against the SSE stream it is
already consuming.
"""

from __future__ import annotations

import json as _json
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from ..live import layouts as layouts_mod
from ..live import replay as replay_mod
from ..live import ui_store
from .deps import require_token

router = APIRouter(tags=["live-ui"], dependencies=[Depends(require_token)])


# ===========================================================================
# 1. layouts
# ===========================================================================

@router.get("/live/layouts", summary="Every layout (built-in and user), name and page count")
def live_layouts_list() -> dict[str, Any]:
    return {"layouts": layouts_mod.list_layouts()}


@router.post("/live/layouts/import", summary="Import a layout; assigns a free id if taken")
def live_layouts_import(layout: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return layouts_mod.import_layout(layout)


@router.get("/live/layouts/{layout_id}", summary="One layout, full definition")
def live_layouts_get(layout_id: str) -> dict[str, Any]:
    return layouts_mod.get_layout(layout_id)


@router.put("/live/layouts/{layout_id}", summary="Save a user layout (400 if the id is built-in)")
def live_layouts_put(layout_id: str, layout: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return layouts_mod.put_layout(layout_id, layout)


@router.delete("/live/layouts/{layout_id}", summary="Delete a user layout (400 if built-in)")
def live_layouts_delete(layout_id: str) -> dict[str, Any]:
    return layouts_mod.delete_layout(layout_id)


@router.get("/live/layouts/{layout_id}/export", summary="Download one layout as JSON")
def live_layouts_export(layout_id: str) -> Any:
    layout = layouts_mod.export_layout(layout_id)
    body = _json.dumps(layout, indent=2)
    return PlainTextResponse(
        body, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{layout_id}.json"'})


# ===========================================================================
# 2. replay
# ===========================================================================

@router.get("/live/recordings", summary="Every replayable recording: cuore's own plus MES CSVs")
def live_recordings_list() -> dict[str, Any]:
    return {"recordings": replay_mod.list_recordings()}


@router.get("/live/replay/{recording_id}/channels",
           summary="One recording's columns as {slug: {name, unit}}")
def live_replay_channels(recording_id: str) -> dict[str, Any]:
    return {"channels": replay_mod.replay_channels(recording_id)}


@router.get("/live/replay/{recording_id}/stream",
           summary="Replay a recording as SSE, same shape as /live/stream, plus replay:true")
def live_replay_stream(recording_id: str, speed: float = Query(default=1.0),
                       start: float = Query(default=0.0)):
    # Validation/loading happens here, synchronously, so a bad id or a bad
    # speed/start comes back as an ordinary 400/404 -- not a broken stream.
    messages = replay_mod.open_replay_stream(recording_id, speed=speed, start=start)

    def gen():
        for msg in messages:
            yield f"data: {_json.dumps(msg)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ===========================================================================
# 3. custom channels (Torque-style)
# ===========================================================================

@router.get("/live/custom-channels", summary="User-defined DID/computed channels")
def live_custom_channels_get() -> dict[str, Any]:
    return ui_store.load_custom_channels_raw()


@router.put("/live/custom-channels", summary="Replace the whole custom-channel set")
def live_custom_channels_put(channels: list[dict[str, Any]] = Body(..., embed=True)
                             ) -> dict[str, Any]:
    return ui_store.save_custom_channels(channels)


# ===========================================================================
# 4. snapshots
# ===========================================================================

@router.post("/live/snapshots", summary="Save a freeze-frame of the current widget values")
def live_snapshots_post(layout: str = Body(..., embed=True),
                        page: str = Body(..., embed=True),
                        source: str = Body(..., embed=True,
                                          description="live | replay | demo"),
                        values: dict[str, Any] = Body(..., embed=True),
                        note: str = Body(default="", embed=True)) -> dict[str, Any]:
    return ui_store.save_snapshot(layout, page, source, values, note=note)


@router.get("/live/snapshots", summary="Recent snapshots, newest first")
def live_snapshots_list(limit: int = Query(default=50, ge=1, le=1000)) -> dict[str, Any]:
    return {"snapshots": ui_store.list_snapshots(limit)}


@router.get("/live/snapshots/{snapshot_id}", summary="One saved snapshot")
def live_snapshots_get(snapshot_id: str) -> dict[str, Any]:
    return ui_store.get_snapshot(snapshot_id)


@router.get("/live/snapshots/{snapshot_id}/csv", summary="One snapshot as a one-row MES-format CSV")
def live_snapshots_csv(snapshot_id: str) -> Any:
    entry = ui_store.get_snapshot(snapshot_id)
    body = ui_store.snapshot_csv(entry)
    return PlainTextResponse(
        body, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{snapshot_id}.csv"'})


# ===========================================================================
# 5. triggers
# ===========================================================================

@router.get("/live/triggers", summary="Stored trigger rules (evaluated in the browser, not here)")
def live_triggers_get() -> dict[str, Any]:
    return ui_store.load_triggers()


@router.put("/live/triggers", summary="Replace the whole trigger rule set")
def live_triggers_put(rules: list[dict[str, Any]] = Body(..., embed=True)) -> dict[str, Any]:
    return ui_store.save_triggers(rules)


__all__ = ["router"]
