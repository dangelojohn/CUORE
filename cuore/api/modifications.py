"""``/api/mods*``: the Modifications layer -- CUORE diagnoses, it never
performs coding/configuration writes itself (NO-GO decided 2026-10-14; see
``docs/handbook/01-decisions-and-rules.md`` and
``docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md``). A modification is
done in MES/wiTECH via a handoff card and RECORDED here with who/when/
from->to/backup/verification.

HTTP face of :mod:`cuore.services.modifications_bridge`; see that module's
docstring for the catalogue/ledger split and the owner_events read-side
merge. The catalogue (``/api/mods/catalog*``) is read-only, same convention
as every other sourced knowledge table in this repo (``/api/parts*``,
``/api/tools-kb*``, the Tests catalogue) -- it is generated from a research
pass, not something a bench page edits; the ledger (``/api/mods/{vin}*``)
is the writable part.

Not registered on the app here -- ``app.py`` is owned by another agent.
The one line needed there, beside the other ``api`` router includes::

    ``app.include_router(modifications_api.router, prefix="/api")``

(importing this module as ``from .api import modifications as modifications_api``.)
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import modifications_bridge as bridge
from .deps import require_token

router = APIRouter(tags=["modifications"], dependencies=[Depends(require_token)])


class ModRecordRequest(BaseModel):
    """Loosely typed on purpose, same convention as ``api/owner_events.py``'s
    ``OwnerEventRequest``: a bad ``by_role``/``tool``/``done_at`` comes back
    as a 400 naming the problem (via :func:`cuore.live.modifications.add`'s
    own ``ValueError``), not FastAPI's generic 422."""

    mod_id: str = Field(default="", description="A mes.modifications catalogue id, "
                                                "or leave blank and use free_text.")
    free_text: str = Field(default="", description="A modification not in the "
                                                    "catalogue -- required if mod_id is blank.")
    done_at: Optional[str] = Field(default=None, description="ISO date/timestamp; default now.")
    by_role: str = Field(default="mechanic", description="mechanic | dealer | owner")
    by_name: str = Field(default="")
    tool: str = Field(default="MES", description="MES | wiTECH | dealer | other")
    from_value: str = Field(default="")
    to_value: str = Field(default="")
    backup: str = Field(default="none", description="File/media id, or \"none\".")
    verification_how: str = Field(default="")
    verification_when: str = Field(default="")
    verification_result: str = Field(default="")
    proxi_realigned: Optional[bool] = Field(default=None)
    notes: str = Field(default="")
    media_ids: list[str] = Field(default_factory=list)


class ModEditRequest(BaseModel):
    """``PATCH`` body -- every key optional, send only what changed. Keys
    mirror :class:`ModRecordRequest` minus ``media_ids`` (not editable
    through this endpoint)."""

    mod_id: Optional[str] = Field(default=None)
    free_text: Optional[str] = Field(default=None)
    done_at: Optional[str] = Field(default=None)
    tool: Optional[str] = Field(default=None)
    from_value: Optional[str] = Field(default=None)
    to_value: Optional[str] = Field(default=None)
    backup: Optional[str] = Field(default=None)
    verification_how: Optional[str] = Field(default=None)
    verification_when: Optional[str] = Field(default=None)
    verification_result: Optional[str] = Field(default=None)
    proxi_realigned: Optional[bool] = Field(default=None)
    notes: Optional[str] = Field(default=None)
    by_role: str = Field(default="mechanic", description="Who made this edit.")
    by_name: str = Field(default="")


# --- catalogue (read-only) --------------------------------------------------


@router.get("/mods/catalog", summary="Every known modification (paddle shift first)")
def list_catalog(q: str = "", module: str = "") -> dict[str, Any]:
    if q:
        rows = bridge.search_mods(q)
    elif module:
        rows = bridge.mods_for_module(module)
    else:
        rows = bridge.all_mods()
    return {"modifications": rows, "count": len(rows)}


@router.get("/mods/catalog/{mod_id}", summary="One catalogue modification by id")
def get_catalog_mod(mod_id: str) -> dict[str, Any]:
    return bridge.mod(mod_id)


@router.get("/mods/catalog/{mod_id}/handoff", summary="The 'Do it in MES' handoff card, if one exists")
def get_handoff(mod_id: str) -> dict[str, Any]:
    bridge.mod(mod_id)  # 404s on an unknown id before answering about its handoff
    card = bridge.handoff_for(mod_id)
    return {"mod_id": mod_id, "handoff": card}


# --- per-VIN ledger ----------------------------------------------------------


@router.get("/mods/{vin}", summary="This car's modification status and ledger")
def get_status(vin: str) -> dict[str, Any]:
    return bridge.status(vin)


@router.get("/mods/{vin}/non-stock", summary="Chips for other surfaces: this car's non-stock configuration")
def get_non_stock(vin: str) -> dict[str, Any]:
    chips = bridge.non_stock(vin)
    return {"vin": vin, "chips": chips, "count": len(chips)}


@router.post("/mods/{vin}/record", summary="Record one modification done to this car")
def post_record(vin: str, body: ModRecordRequest) -> dict[str, Any]:
    return bridge.record(vin, **body.model_dump())


@router.patch("/mods/{vin}/{entry_id}", summary="Edit one ledger entry")
def patch_entry(vin: str, entry_id: str, body: ModEditRequest) -> dict[str, Any]:
    changes = {k: v for k, v in body.model_dump(exclude={"by_role", "by_name"}).items()
              if v is not None}
    return bridge.edit(entry_id, by_role=body.by_role, by_name=body.by_name, **changes)


@router.delete("/mods/{vin}/{entry_id}", summary="Soft-delete one ledger entry")
def delete_entry(vin: str, entry_id: str) -> dict[str, Any]:
    return bridge.delete(entry_id)


@router.post("/mods/{vin}/{entry_id}/restore", summary="Undo a soft-delete")
def restore_entry(vin: str, entry_id: str) -> dict[str, Any]:
    return bridge.restore(entry_id)


__all__ = ["router"]
