"""Registers the ``tools_recommend`` and ``tools_learn`` Jinja globals on
every template environment a page that wants the "Tools for this step"
panel renders through.

Same trick :mod:`cuore.web.experience_globals` uses for
``experience_links``: importing this module is the side effect that does
the registration -- nothing here is called directly.
``cuore.api.tools_kb`` imports it at module load time, so including that
router (see its docstring for the one line ``app.py`` needs) is what wires
this in, without editing any of the route modules themselves.

Registered on both distinct ``Jinja2Templates`` instances this feature's
pages span: ``cuore.web.routes``'s (for ``job.html``) and
``cuore.web.service_routes``'s (for ``maintenance.html``) -- the same
two-environments wrinkle ``experience_globals``/``parts_routes`` already
document and work around.
"""

from __future__ import annotations

from typing import Any, Optional

from ..services import tools_kb_bridge


def _recommend(step: str = "", vin: Optional[str] = None) -> dict[str, Any]:
    try:
        return tools_kb_bridge.recommend_with_learning(step, vin=vin)
    except Exception:  # noqa: BLE001 -- a template global must never 500 a page
        return {"step": step, "tools": [], "learned": {"step": step, "review_count": 0,
                "scope": "all", "top_tools": [], "flagged_wrong": [],
                "buy_suggestions": [], "missing_tools": []}}


def _learn(step: str = "", vin: Optional[str] = None) -> dict[str, Any]:
    try:
        return tools_kb_bridge.learn(step, vin=vin)
    except Exception:  # noqa: BLE001
        return {"step": step, "review_count": 0, "scope": "all", "top_tools": [],
                "flagged_wrong": [], "buy_suggestions": [], "missing_tools": []}


def _register(templates: Any) -> None:
    templates.env.globals["tools_recommend"] = _recommend
    templates.env.globals["tools_learn"] = _learn


for _module_name in ("routes", "service_routes"):
    try:
        import importlib
        _mod = importlib.import_module(f".{_module_name}", __package__)
        _tmpl = getattr(_mod, "templates", None) or getattr(_mod, "_shared_templates", None)
        if _tmpl is not None:
            _register(_tmpl)
    except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
        pass


__all__: list[str] = []
