"""HTTP face of ``cuore.services.tools_kb_bridge``: which tools a job/step
needs, and what mechanics actually used/learned last time.

Not registered on the app here -- ``app.py`` is owned by another agent. The
one line needed there (next to the other ``/api``-prefixed includes):

    ``app.include_router(tools_kb_api.router, prefix="/api")``

(importing this module as ``from .api import tools_kb as tools_kb_api``,
alongside the sibling ``api`` imports.)
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services import tools_kb_bridge
from .deps import require_token

# Import-time side effect: registers the `tools_recommend`/`tools_learn`
# Jinja globals on every page's template environment (see that module's
# docstring). Done here rather than in cuore/web/* directly so none of
# those route modules (owned by other agents) need to change.
from ..web import tools_kb_globals  # noqa: F401

router = APIRouter(tags=["tools-kb"], dependencies=[Depends(require_token)])


class ToolUsed(BaseModel):
    tool: str
    was_right: str = Field(default="unsure")
    note: str = Field(default="")


class WouldBuy(BaseModel):
    name: str
    why: str = Field(default="")


class ToolUsageAdd(BaseModel):
    job_id: str = Field(default="")
    step: str
    by: str = Field(default="")
    tools_used: list[ToolUsed] = Field(default_factory=list)
    missing_tools: list[str] = Field(default_factory=list)
    would_buy: list[WouldBuy] = Field(default_factory=list)
    time_min: Optional[float] = None


class InventorySet(BaseModel):
    tool: str
    status: str
    note: str = Field(default="")


@router.get("/tools-kb/recommend/{step}", summary="Recommended tools for a job/step")
def recommend(step: str, vin: Optional[str] = None) -> dict[str, Any]:
    """Recommended tools for ``step``, merged with what was learned about
    it last time (scoped to ``vin`` first, else every vehicle)."""
    return tools_kb_bridge.recommend_with_learning(step, vin=vin)


@router.get("/tools-kb/learn/{step}", summary="Aggregated tool-usage learning for a job/step")
def learn(step: str, vin: Optional[str] = None) -> dict[str, Any]:
    return tools_kb_bridge.learn(step, vin=vin)


@router.get("/vehicles/{vin}/tool-usage", summary="Tool-usage reviews recorded for this vehicle")
def usage_for(vin: str, step: Optional[str] = None) -> dict[str, Any]:
    return {"vin": vin, "reviews": tools_kb_bridge.usage_for(vin, step=step)}


@router.post("/vehicles/{vin}/tool-usage", summary="Record a tool-usage review")
def add_usage(vin: str, body: ToolUsageAdd) -> dict[str, Any]:
    return tools_kb_bridge.add_usage(
        vin, body.step, job_id=body.job_id, by=body.by,
        tools_used=[t.model_dump() for t in body.tools_used],
        missing_tools=body.missing_tools,
        would_buy=[b.model_dump() for b in body.would_buy],
        time_min=body.time_min)


@router.get("/tools-kb/inventory", summary="The garage's owned/not-owned tool list")
def inventory_list() -> dict[str, Any]:
    return {"inventory": tools_kb_bridge.inventory_list()}


@router.post("/tools-kb/inventory", summary="Record whether the shop has a tool")
def inventory_set(body: InventorySet) -> dict[str, Any]:
    return tools_kb_bridge.inventory_set(body.tool, body.status, note=body.note)


__all__ = ["router"]
