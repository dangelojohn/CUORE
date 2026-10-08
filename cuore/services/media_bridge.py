"""The bridge between :mod:`cuore.web.media_routes`'s lazy import and
:mod:`cuore.live.media`, the mechanic evidence media library.

``cuore.web.media_routes`` tries ``from ..services import media_bridge``
first and falls back to its own in-memory fixture store on import failure or
on any exception out of ``list_media``/``save_media``/``recent_tags`` (see
that module's docstring). This module is what makes that import succeed: a
thin, deliberately boring wrap of ``cuore.live.media`` in exactly the shapes
``media_routes`` already calls -- ``list_media`` returns ``{"items": [...]}``
(not a bare list), and ``save_media`` takes the same ``files=`` list of
``{"filename", "content_type", "content"}`` dicts ``media_routes.save_media``
builds from each ``UploadFile`` it read.

``cuore.api.media`` (the JSON surface) talks to ``cuore.live.media``
directly rather than through here -- that predates this module and there is
no drift to fix: both ultimately read and write the same index, so the
gallery page and the JSON API cannot disagree.

The remaining wraps (``get``/``path``/``thumb_path``/``update``/``hide``/
``export_zip``) mirror ``cuore.live.media`` call-for-call, for any other
caller that reaches the media library through the services layer instead of
importing ``cuore.live.media`` itself -- same posture as every other
``*_bridge.py`` in this package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..live import media as media_store
from .errors import BadRequest, NotFound


def list_media(vin: str, *, q: str = "", kind: str = "", tag: str = "",
               target_kind: str = "", target_id: str = "", since: str = "",
               until: str = "", symptom_tag: str = "") -> dict[str, Any]:
    """``{"items": [...]}`` -- the shape ``media_routes.list_media`` expects
    back, newest ``captured_at`` first, hidden excluded."""
    rows = media_store.search(vin, q=q, kind=kind, tag=tag, target_kind=target_kind,
                              target_id=target_id, since=since, until=until,
                              symptom_tag=symptom_tag)
    return {"items": rows}


def save_media(vin: str, *, files: list[dict[str, Any]], caption: str = "",
               tags: Optional[list[str]] = None, target_kind: str = "vehicle",
               target_id: str = "", odometer_km: Optional[float] = None,
               author: str = "", symptom_tags: Optional[list[str]] = None,
               feels_like: str = "") -> list[dict[str, Any]]:
    """Store each of ``files`` via :func:`cuore.live.media.add`. Returns the
    new index rows, one per file, in the same order.

    ``files`` is exactly what ``media_routes.save_media`` already read off
    each ``UploadFile`` -- ``{"filename", "content_type", "content"}`` dicts,
    bytes included -- so nothing here re-reads anything.
    """
    rows: list[dict[str, Any]] = []
    for f in files:
        mime = f.get("content_type") or "application/octet-stream"
        try:
            row = media_store.add(
                vin, f.get("content") or b"", f.get("filename") or "upload", mime,
                caption=caption, tags=list(tags or []), target_kind=target_kind or "vehicle",
                target_id=target_id, odometer_km=odometer_km, author=author,
                symptom_tags=list(symptom_tags or []), feels_like=feels_like,
            )
        except media_store.BadMedia as exc:
            raise BadRequest(str(exc)) from exc
        rows.append(row)
    return rows


def recent_tags(vin: str, limit: int = 12) -> list[str]:
    """Up to ``limit`` distinct tags, most-recently-used first."""
    seen: list[str] = []
    for row in media_store.search(vin):  # already newest captured_at first
        for t in row.get("tags") or []:
            if t not in seen:
                seen.append(t)
    return seen[:limit]


def get(id_: str) -> dict[str, Any]:
    try:
        return media_store.get(id_)
    except media_store.UnknownMedia as exc:
        raise NotFound(f"no media with id {id_!r}") from exc


def path(id_: str) -> Path:
    try:
        return media_store.path(id_)
    except media_store.UnknownMedia as exc:
        raise NotFound(f"no media with id {id_!r}") from exc


def thumb_path(id_: str) -> Optional[Path]:
    try:
        return media_store.thumb_path(id_)
    except media_store.UnknownMedia as exc:
        raise NotFound(f"no media with id {id_!r}") from exc


def update(id_: str, *, caption: Optional[str] = None, tags: Optional[list[str]] = None,
           target_kind: Optional[str] = None, target_id: Optional[str] = None,
           symptom_tags: Optional[list[str]] = None,
           feels_like: Optional[str] = None) -> dict[str, Any]:
    try:
        return media_store.update(id_, caption=caption, tags=tags,
                                  target_kind=target_kind, target_id=target_id,
                                  symptom_tags=symptom_tags, feels_like=feels_like)
    except media_store.UnknownMedia as exc:
        raise NotFound(f"no media with id {id_!r}") from exc
    except media_store.BadMedia as exc:
        raise BadRequest(str(exc)) from exc


def hide(id_: str) -> dict[str, Any]:
    try:
        return media_store.hide(id_)
    except media_store.UnknownMedia as exc:
        raise NotFound(f"no media with id {id_!r}") from exc


def export_zip(vin: str) -> Path:
    return media_store.export_zip(vin)


__all__ = ["list_media", "save_media", "recent_tags", "get", "path", "thumb_path",
          "update", "hide", "export_zip"]
