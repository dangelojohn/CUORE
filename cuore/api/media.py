"""Mechanic evidence media library: upload, browse, and recover photos,
scans, and borescope clips.

Thin HTTP face over ``cuore.live.media`` -- the same split as every other
router here: this module turns requests into calls against the service
layer and turns its results (or its ``BadMedia``/``UnknownMedia``) into HTTP.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from ..live import media as media_store
from .deps import require_token

router = APIRouter(tags=["media"], dependencies=[Depends(require_token)])

#: HTTP-layer cap for this endpoint -- deliberately tighter than
#: ``media_store.MAX_SIZE`` (500 MB, still enforced as a defensive
#: fallback). iPhone photos/HEIC/Live Photos are the case this is sized
#: for; a fast, clear 413 beats reading a huge body only to 400 later.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


_SAFE_VIN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _check_vin(vin: str) -> str:
    """``media_store.vin_dir`` joins the VIN onto a path as-is, so ``..`` or
    ``..%5Cx`` (a backslash is a separator on Windows) would write outside the
    media root. Refuse anything that is not a plain id."""
    if not _SAFE_VIN.match(vin or ""):
        raise HTTPException(status_code=400, detail=f"invalid vehicle id {vin!r}")
    return vin


def _row_or_404(id_: str) -> dict[str, Any]:
    try:
        return media_store.get(id_)
    except media_store.UnknownMedia:
        raise HTTPException(status_code=404, detail=f"no media with id {id_!r}")


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    """Add HTTP-layer fields (``url``, ``thumb_url``) on top of the storage
    row -- ``cuore.live.media`` knows nothing about where it's mounted, so
    those are built here, not there."""
    row = dict(row)
    id_ = row.get("id", "")
    row["url"] = f"/api/media/{id_}/file"
    row["thumb_url"] = f"/api/media/{id_}/thumb" if media_store.thumb_path(id_) else None
    return row


@router.post("/vehicles/{vin}/media", summary="Upload one or more media files")
async def upload(
    vin: str,
    file: list[UploadFile] = File(...),
    caption: str = Form(default=""),
    tags: str = Form(default="", description="Comma-separated."),
    target_kind: str = Form(default="vehicle"),
    target_id: str = Form(default=""),
    odometer_km: float | None = Form(default=None),
    author: str = Form(default=""),
    symptom_tags: str = Form(default="", description="Comma-separated."),
    feels_like: str = Form(default=""),
    note: str = Form(default="", description="Alias for caption, used when caption is blank."),
    event_id: str = Form(default="", description="Shorthand for target_kind=timeline, target_id=event_id."),
    keep_location: bool = Form(default=False, description="Keep decoded GPS lat/lon on the record. Default off (owner privacy) -- has_gps is reported either way."),
) -> dict[str, Any]:
    _check_vin(vin)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    symptom_tag_list = [t.strip() for t in symptom_tags.split(",") if t.strip()]
    effective_caption = caption or note
    effective_target_kind, effective_target_id = target_kind, target_id
    if event_id and target_kind == "vehicle" and not target_id:
        effective_target_kind, effective_target_id = "timeline", event_id
    rows = []
    for up in file:
        if up.size is not None and up.size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(f"{up.filename or 'file'} is {up.size} bytes, over the "
                        f"{MAX_UPLOAD_BYTES} byte (25 MB) upload limit"),
            )
        body = await up.read()
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(f"{up.filename or 'file'} is {len(body)} bytes, over the "
                        f"{MAX_UPLOAD_BYTES} byte (25 MB) upload limit"),
            )
        mime = up.content_type or "application/octet-stream"
        try:
            # add() hashes, writes and thumbnails: blocking, so off the loop.
            row = await run_in_threadpool(
                media_store.add, vin, body, up.filename or "upload", mime,
                caption=effective_caption, tags=tag_list, target_kind=effective_target_kind,
                target_id=effective_target_id, odometer_km=odometer_km, author=author,
                symptom_tags=symptom_tag_list, feels_like=feels_like,
                keep_location=keep_location,
            )
        except media_store.BadMedia as e:
            raise HTTPException(status_code=400, detail=str(e))
        rows.append(_enrich(row))
    return {"count": len(rows), "media": rows}


@router.get("/vehicles/{vin}/media", summary="Search this vehicle's media")
def list_media(
    vin: str,
    q: str = Query(default=""),
    kind: str = Query(default=""),
    tag: str = Query(default=""),
    target_kind: str = Query(default=""),
    target_id: str = Query(default=""),
    since: str = Query(default=""),
    until: str = Query(default=""),
    symptom_tag: str = Query(default=""),
) -> dict[str, Any]:
    _check_vin(vin)
    rows = media_store.search(vin, q=q, kind=kind, tag=tag, target_kind=target_kind,
                              target_id=target_id, since=since, until=until,
                              symptom_tag=symptom_tag)
    return {"count": len(rows), "media": [_enrich(r) for r in rows]}


@router.get("/vehicles/{vin}/media/export.zip", summary="Export every file plus the index, for recovery")
def export(vin: str) -> FileResponse:
    zpath = media_store.export_zip(_check_vin(vin))
    return FileResponse(zpath, media_type="application/zip",
                        filename=f"{vin}-media.zip",
                        content_disposition_type="attachment")


@router.get("/media/{id}/file", summary="The original media file")
def file_(id: str) -> FileResponse:
    row = _row_or_404(id)
    return FileResponse(media_store.path(id), media_type=row["mime"],
                        content_disposition_type="inline")


@router.get("/media/{id}/thumb", summary="320px thumbnail (or first frame, for video)")
def thumb(id: str) -> FileResponse:
    _row_or_404(id)
    tpath = media_store.thumb_path(id)
    if tpath is None:
        raise HTTPException(status_code=404, detail=f"no thumbnail for {id!r}")
    return FileResponse(tpath, media_type="image/jpeg",
                        content_disposition_type="inline")


@router.post("/media/{id}", summary="Edit caption, tags, target, symptom tags, or feels_like")
def update(id: str, caption: str | None = None, tags: str | None = None,
          target_kind: str | None = None, target_id: str | None = None,
          symptom_tags: str | None = None, feels_like: str | None = None) -> dict[str, Any]:
    _row_or_404(id)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags is not None else None
    symptom_tag_list = ([t.strip() for t in symptom_tags.split(",") if t.strip()]
                        if symptom_tags is not None else None)
    try:
        return media_store.update(id, caption=caption, tags=tag_list,
                                  target_kind=target_kind, target_id=target_id,
                                  symptom_tags=symptom_tag_list, feels_like=feels_like)
    except media_store.BadMedia as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/media/{id}/hide", summary="Hide a media item (soft delete)")
def hide(id: str) -> dict[str, Any]:
    _row_or_404(id)
    return media_store.hide(id)
