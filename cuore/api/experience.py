"""HTTP face of ``cuore.services.experience_bridge``: what other owners,
forums and video creators have published about a code, family or job --
plus (added 2026-10-14) what a driver or mechanic on THIS shop floor typed
in themselves, with full read/write round-trip on their own rows.

Same posture as the rest of ``cuore.api``: payload shape comes from the
bridge unchanged.

Not registered on the app here -- ``app.py`` is owned by another agent, but
already includes this router (``app.include_router(experience_api.router,
prefix="/api")`` next to the other ``/api``-prefixed includes), so the new
``/experience/{vin}/inputs`` routes below need no further wiring.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..services import experience_bridge
from .deps import require_token

# Import-time side effect: registers the `experience_links` Jinja global on
# every page's template environment (see that module's docstring). Done here
# rather than in cuore/web/* directly so none of those route modules (owned
# by other agents) need to change.
from ..web import experience_globals  # noqa: F401

router = APIRouter(tags=["experience"], dependencies=[Depends(require_token)])


class ExperienceInputRequest(BaseModel):
    """Body for adding one driver/mechanic-found link."""

    scope: dict[str, str] = Field(default_factory=dict,
                                  description="Any of code/family/system/job.")
    url: str
    title: str = ""
    kind: str = Field(..., description="video|forum|article|manual|audio|photo|note")
    role: str = Field(..., description="driver|mechanic|owner|cuore")
    name: str = ""
    note: str = ""
    rating: str = Field(default="unsure", description="helped|unsure|wrong")
    verify: bool = True
    confirm_duplicate: bool = False


class ExperienceInputEditRequest(BaseModel):
    by_role: str
    by_name: str = ""
    note: Optional[str] = None
    rating: Optional[str] = None
    title: Optional[str] = None
    kind: Optional[str] = None
    scope: Optional[dict[str, str]] = None


class ExperienceFlagRequest(BaseModel):
    by_role: str
    by_name: str = ""
    note: str = ""
    flag_kind: str = Field(default="wrong", description="wrong|outdated")


class ExperienceWorkedRequest(BaseModel):
    by_role: str
    by_name: str = ""
    job_ref: str = ""


@router.get("/experience", summary="Others' experience: videos, threads, teardowns")
def experience(code: Optional[str] = None, family: Optional[str] = None,
               job: Optional[str] = None, vin: Optional[str] = None) -> dict[str, Any]:
    """Merged, tiered-then-scored links (curated plus driver/mechanic-added)
    for whichever of ``code``, ``family`` or ``job`` are passed. See
    :func:`cuore.services.experience_bridge.links_for`."""
    return experience_bridge.links_for(code=code, family=family, job=job, vin=vin)


@router.get("/experience/{vin}/inputs", summary="Driver/mechanic-added links for this vehicle")
def list_inputs(vin: str, role: Optional[str] = None,
                scope_field: Optional[str] = Query(default=None, description="code|family|system|job"),
                scope_value: Optional[str] = None,
                include_deleted: bool = False) -> dict[str, Any]:
    return experience_bridge.list_inputs(vin, role=role, scope_field=scope_field,
                                         scope_value=scope_value, include_deleted=include_deleted)


@router.post("/experience/{vin}/inputs", summary="Add one driver/mechanic-found link")
def add_input(vin: str, body: ExperienceInputRequest) -> dict[str, Any]:
    """Returns the new row, or ``{"duplicate": true, "existing": {...}}``
    without writing anything when the same URL is already on file for this
    vehicle and ``confirm_duplicate`` wasn't set."""
    return experience_bridge.add_input(
        vin=vin, scope=body.scope, url=body.url, title=body.title, kind=body.kind,
        role=body.role, name=body.name, note=body.note, rating=body.rating,
        verify=body.verify, confirm_duplicate=body.confirm_duplicate)


@router.patch("/experience/{vin}/inputs/{id}", summary="Edit a driver/mechanic-added link")
def edit_input(vin: str, id: str, body: ExperienceInputEditRequest) -> dict[str, Any]:
    """``vin`` is accepted for a stable REST shape but not otherwise used --
    a row is addressed by its own id, same posture as feedback-row edits."""
    return experience_bridge.edit_input(
        id, by_role=body.by_role, by_name=body.by_name, note=body.note,
        rating=body.rating, title=body.title, kind=body.kind, scope=body.scope)


@router.post("/experience/{vin}/inputs/{id}/verify",
             summary="Run the deferred link check and record its result")
def verify_input(vin: str, id: str) -> dict[str, Any]:
    """``vin`` is accepted for a stable REST shape but not otherwise used.
    The add form saves with ``verify: false`` so the save never blocks on
    an outbound check (2026-10-14, N3); this is the background call the
    page makes right after, to swap the row's "Verifying..." badge for the
    real result."""
    return experience_bridge.verify_input(id)


@router.delete("/experience/{vin}/inputs/{id}", summary="Soft-delete a driver/mechanic-added link")
def delete_input(vin: str, id: str) -> dict[str, Any]:
    return experience_bridge.delete_input(id)


@router.post("/experience/{vin}/inputs/{id}/restore", summary="Undo a soft-delete")
def restore_input(vin: str, id: str) -> dict[str, Any]:
    return experience_bridge.restore_input(id)


@router.post("/experience/links/{link_id}/flag", summary="Flag a link (curated or added) as wrong/outdated")
def flag_link(link_id: str, body: ExperienceFlagRequest) -> dict[str, Any]:
    return experience_bridge.flag_curated(link_id, by_role=body.by_role, by_name=body.by_name,
                                          note=body.note, flag_kind=body.flag_kind)


@router.post("/experience/links/{link_id}/worked", summary='"Worked on this car?" tick')
def mark_worked(link_id: str, body: ExperienceWorkedRequest) -> dict[str, Any]:
    return experience_bridge.mark_worked(link_id, by_role=body.by_role, by_name=body.by_name,
                                         job_ref=body.job_ref)


@router.get("/experience/{vin}/inputs/export", summary="Export user-added links for curation review")
def export_for_curation(vin: str, role: str = "mechanic", rating: str = "helped") -> dict[str, Any]:
    """JSON export of user-added links in the curated table's own shape, for
    a human to review and hand-promote -- never an auto-promotion."""
    return experience_bridge.export_for_curation(vin, role=role, rating=rating)


__all__ = ["router"]
