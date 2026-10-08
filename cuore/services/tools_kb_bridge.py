"""HTTP/template face of :mod:`mes.tools_kb` and :mod:`mes.tool_usage`.

Same posture as ``cuore.services.feedback_bridge``: a thin bridge that
translates ``mes``'s own ``ValueError``s into :class:`BadRequest`, used by
both ``cuore/api/tools_kb.py`` (JSON) and the Jinja globals registered in
``cuore/web/tools_kb_globals.py`` (for ``job.html``/``maintenance.html``).

Nothing here invents a tool, a size, or a verdict -- ``recommend`` and
``learn`` are direct pass-through reads; the only shaping done here is
merging a step's recommendation with what was actually learned about it
(:func:`recommend_with_learning`), so the Job page's "Tools for this step"
panel can show both in one call.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from .errors import BadRequest

from mes import tool_usage as tool_usage_mod  # noqa: E402
from mes import tools_kb  # noqa: E402


def recommend(step: str) -> list[dict[str, Any]]:
    """Tool rows for one job/step key -- see ``mes.tools_kb.recommend`` --
    each annotated with ``have`` ("owned"/"not_owned"/"unknown", from the
    garage's own simple inventory list) and, for a *required* tool that
    isn't owned, a ``decision`` card (see ``mes.tools_kb.decision_for``) --
    one worked example exists (the EVAP smoke machine), everything else
    returns ``None`` and the UI shows no card."""
    step = (step or "").strip()
    rows = tools_kb.recommend(step)
    for row in rows:
        key = row["tool_info"]["key"]
        have = tool_usage_mod.have_status(key)
        row["have"] = have
        row["decision"] = (tools_kb.decision_for(step, key)
                           if row["required"] and have != "owned" else None)
    return rows


def learn(step: str, *, vin: Optional[str] = None) -> dict[str, Any]:
    """Aggregated learning for one job/step key -- see ``mes.tool_usage.learn``."""
    return tool_usage_mod.learn(step, vin=vin)


def recommend_with_learning(step: str, *, vin: Optional[str] = None) -> dict[str, Any]:
    """What the Job/Maintenance pages actually need for one step: the
    recommended tools, plus what was learned about this step last time
    (top tools used, flagged wrong, buy suggestions, missing tools) --
    scoped to this VIN first, falling back to every vehicle."""
    step = (step or "").strip()
    return {
        "step": step,
        "tools": recommend(step),
        "learned": learn(step, vin=vin),
    }


def add_usage(vin: str, step: str, *, job_id: str = "", by: str = "",
             tools_used: Optional[list[dict[str, Any]]] = None,
             missing_tools: Optional[list[str]] = None,
             would_buy: Optional[list[dict[str, Any]]] = None,
             time_min: Optional[float] = None) -> dict[str, Any]:
    """Record one tool-usage review. Raises BadRequest on invalid input."""
    try:
        return tool_usage_mod.add(vin, step, job_id=job_id, by=by, tools_used=tools_used,
                                  missing_tools=missing_tools, would_buy=would_buy,
                                  time_min=time_min)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def usage_for(vin: str, *, step: Optional[str] = None) -> list[dict[str, Any]]:
    """Every tool-usage review recorded for this VIN, optionally filtered
    by step -- oldest first."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    return tool_usage_mod.load(vin=vin, step=step)


def has_review(vin: str, job_id: str) -> bool:
    """Whether any tool-usage review has been recorded against this job --
    the gate ``cuore.web.jobs_routes`` checks before letting a job close."""
    if not job_id:
        return False
    return any(r.get("job_id") == job_id for r in tool_usage_mod.load(vin=vin))


def inventory_set(tool: str, status: str, *, note: str = "") -> dict[str, Any]:
    """Record whether the shop has this tool -- "owned"/"not_owned".
    Raises BadRequest on invalid input."""
    try:
        return tool_usage_mod.inventory_set(tool, status, note=note)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def inventory_list() -> dict[str, dict[str, Any]]:
    """The garage's current owned/not-owned list, keyed by tool."""
    return tool_usage_mod.inventory_list()


__all__ = ["recommend", "learn", "recommend_with_learning", "add_usage",
          "usage_for", "has_review", "inventory_set", "inventory_list"]
