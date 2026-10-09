"""``POST /api/attested/{vin}`` -- file one attested mechanic input against
an UNKNOWN marker on a system page (phase 3 of the Systems dive-in; see
``cuore/live/attested.py`` for what this is and, just as important, what
it is **not**: never a car measurement, never an evidence-gate input,
never a replacement for the knowledge-table value it sits beside).

Registration note: ``cuore/app.py`` is owned by another agent and is not
edited by this module beyond the one line it asks for::

    app.include_router(attested.router, prefix="/api")
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..live import attested as attested_store
from .deps import require_token

router = APIRouter(tags=["attested"], dependencies=[Depends(require_token)])


class AttestedRequest(BaseModel):
    """Loosely typed on purpose: a bad ``kind`` or a missing field must
    come back as a 400 with a message naming the problem, not FastAPI's
    generic 422 -- so every field is a plain ``str`` here and the real
    validation happens in :func:`cuore.live.attested.add`, whose
    ``ValueError`` the handler below turns into a 400 itself."""

    system: str = Field(default="")
    fact_key: str = Field(default="")
    value: str = Field(default="")
    unit: str = Field(default="")
    source: str = Field(default="")
    by: str = Field(default="mechanic")
    kind: str = Field(default="measured")


@router.post("/attested/{vin}", summary="File one attested mechanic input")
def add_attested(vin: str, body: AttestedRequest) -> dict[str, Any]:
    try:
        return attested_store.add(
            vin, body.system, body.fact_key, body.value, unit=body.unit,
            source=body.source, by=body.by, kind=body.kind)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/attested/{vin}/{system}", summary="Attested inputs on file for one system")
def list_attested(vin: str, system: str) -> dict[str, Any]:
    return {"facts": attested_store.latest_by_fact(vin, system)}


__all__ = ["router"]
