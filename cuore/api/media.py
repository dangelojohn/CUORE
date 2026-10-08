"""Mechanic evidence media library: upload, browse, and recover photos,
scans, and borescope clips.

Thin HTTP face over ``cuore.live.media`` -- the same split as every other
router here: this module turns requests into calls against the service
layer and turns its results (or its ``BadMedia``/``UnknownMedia``) into HTTP.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ..live import media as media_store
from .deps import require_token

router = APIRouter(tags=["media"], dependencies=[Depends(require_token)])


def _row_or_404(id_: str) -> dict[str, Any]:
    try:
        return media_store.get(id_)
    except media_store.UnknownMedia:
        raise HTTPException(status_code=404, detail=f"no media with id {id_!r}")


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
) -> dict[str, Any]:
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    rows = []
    for up in file:
        body = await up.read()
        mime = up.content_type or "application/octet-stream"
        try:
            row = media_store.add(
                vin, body, up.filename or "upload", mime,
                caption=caption, tags=tag_list, target_kind=target_kind,
                target_id=target_id, odometer_km=odometer_km, author=author,
            )
        except media_store.BadMedia as e:
            raise HTTPException(status_code=400, detail=str(e))
        rows.append(row)
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
) -> dict[str, Any]:
    rows = media_store.search(vin, q=q, kind=kind, tag=tag, target_kind=target_kind,
                              target_id=target_id, since=since, until=until)
    return {"count": len(rows), "media": rows}


@router.get("/vehicles/{vin}/media/export.zip", summary="Export every file plus the index, for recovery")
def export(vin: str) -> FileResponse:
    zpath = media_store.export_zip(vin)
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


@router.post("/media/{id}", summary="Edit caption, tags, or target")
def update(id: str, caption: str | None = None, tags: str | None = None,
          target_kind: str | None = None, target_id: str | None = None) -> dict[str, Any]:
    _row_or_404(id)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags is not None else None
    try:
        return media_store.update(id, caption=caption, tags=tag_list,
                                  target_kind=target_kind, target_id=target_id)
    except media_store.BadMedia as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/media/{id}/hide", summary="Hide a media item (soft delete)")
def hide(id: str) -> dict[str, Any]:
    _row_or_404(id)
    return media_store.hide(id)
