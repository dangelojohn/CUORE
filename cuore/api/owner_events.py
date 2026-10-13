"""``/api/owner/{vin}/...`` -- "Tell CUORE": owner/driver/mechanic reports
that the car cannot discover on its own.

Every row this API writes or returns is ATTESTED -- who said it, when, at
confidence ``"reported"``. **No route here writes to the car**: nothing in
this module reaches ``cuore.live.actuate``/``clear``/``learn`` or any other
module that talks to the vehicle.

HTTP face of :mod:`cuore.services.owner_events_bridge`, which does the real
work; see that module's docstring for the taxonomy, correlation and
messages contract. Like ``api/feedback.py``, routes here raise
``cuore.services.errors.BadRequest`` straight through and let ``cuore.app``'s
own ``BridgeError`` exception handler turn it into a 400 -- no local
try/except needed.

Registration note: ``cuore/app.py`` is owned by another agent. The one line
needed there, beside the other ``/api`` routers::

    app.include_router(owner_events.router, prefix="/api")
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import owner_events_bridge as bridge
from .deps import require_token

router = APIRouter(tags=["owner-events"], dependencies=[Depends(require_token)])


class OwnerEventRequest(BaseModel):
    """Loosely typed on purpose, same convention ``api/attested.py`` and
    ``api/feedback.py`` use: a bad category/kind must come back as a 400
    naming the problem, not FastAPI's generic 422, so validation happens in
    :func:`cuore.live.owner_events.add` and its ``ValueError`` (turned into a
    ``BadRequest`` by the bridge) becomes the 400 here."""

    category: str = Field(...)
    kind: str = Field(...)
    at: Optional[str] = Field(default=None, description="ISO date or timestamp; default now.")
    by_role: str = Field(default="owner", description="owner | driver | mechanic")
    by_name: str = Field(default="")
    fields: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(default="")
    media_ids: list[str] = Field(default_factory=list)
    odometer_km: Optional[float] = Field(default=None)
    fields_meta: dict[str, str] = Field(
        default_factory=dict,
        description="Optional {field_key: \"photo\"|\"typed\"} provenance tag per "
                    "field -- e.g. a native app that read a value off a photo marks "
                    "that key \"photo\" the same way the HTML form's own "
                    "source_<key>=photo hidden input does. Any key that isn't one of "
                    "this kind's real fields, or any value that isn't \"photo\"/"
                    "\"typed\", is silently dropped by cuore.live.owner_events.add.")


class ReplyRequest(BaseModel):
    text: str = Field(...)
    by: str = Field(default="owner")


@router.get("/owner/{vin}/taxonomy", summary="Category/kind table for the Tell CUORE form")
def get_taxonomy(vin: str) -> dict[str, Any]:
    return bridge.taxonomy()


@router.get("/owner/{vin}/events", summary="This VIN's owner-reported events")
def get_events(vin: str, include_deleted: bool = False) -> dict[str, Any]:
    return bridge.list_events(vin, include_deleted=include_deleted)


@router.post("/owner/{vin}/events", summary="Record one owner-reported event")
def post_event(vin: str, body: OwnerEventRequest) -> dict[str, Any]:
    return bridge.add(vin, body.category, body.kind, at=body.at, by_role=body.by_role,
                      by_name=body.by_name, fields=body.fields, note=body.note,
                      media_ids=body.media_ids, odometer_km=body.odometer_km,
                      fields_meta=body.fields_meta)


@router.delete("/owner/{vin}/events/{id}", summary="Soft-delete one owner event")
def delete_event(vin: str, id: str) -> dict[str, Any]:
    return bridge.delete(id)


@router.get("/owner/{vin}/messages", summary="Questions for the owner, CUORE's and the mechanic's")
def get_messages(vin: str) -> dict[str, Any]:
    return bridge.messages(vin)


@router.post("/owner/{vin}/messages/{id}/reply",
            summary="Owner's (or mechanic's) reply to one message")
def reply_message(vin: str, id: str, body: ReplyRequest) -> dict[str, Any]:
    return bridge.reply_message(id, body.text, by=body.by)


@router.get("/owner/{vin}/correlations",
           summary="Owner events near each code's first/returned occurrence")
def get_correlations(vin: str) -> dict[str, Any]:
    return bridge.correlate(vin)
