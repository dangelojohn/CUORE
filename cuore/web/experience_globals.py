"""Registers the ``experience_links`` Jinja global on every template
environment a page that wants the "Others' experience" card renders
through.

Same trick ``cuore.web.timeline_routes`` uses for ``code_feel``
(``_shared_templates.env.globals["code_feel"] = _code_feel_data``), just
applied to more than one environment, since this feature's pages are spread
across four route modules (``routes``, ``service_routes`` -- reused by
``drivetrain_routes`` -- and ``timeline_routes``, which reuses ``routes``'s
own ``templates``). Across those four modules there are exactly two distinct
``Jinja2Templates`` instances; both are registered here, defensively
including the two reusing modules in case that identity ever changes.

Importing this module is the side effect that does the registration --
nothing here is called directly. ``cuore.api.experience`` imports it at
module load time, so including that router (see its docstring for the one
line ``app.py`` needs) is what wires this in, without editing any of the
four route modules' own code. Every import is independently guarded: a
route module that fails to import (shouldn't happen, but this must never be
why a page 500s) just leaves that environment without the global, and the
templates themselves guard with ``is defined`` for the same reason -- this
can land, and be tested, before ``app.py`` includes the router.
"""

from __future__ import annotations

from typing import Any

from ..services import experience_bridge


def _links(**kw: Any) -> dict[str, Any]:
    try:
        return experience_bridge.links_for(**kw)
    except Exception:  # noqa: BLE001 -- a template global must never 500 a page
        return {"links": [], "count": 0}


def _register(templates: Any) -> None:
    templates.env.globals["experience_links"] = _links


for _module_name in ("routes", "service_routes", "drivetrain_routes", "timeline_routes"):
    try:
        import importlib
        _mod = importlib.import_module(f".{_module_name}", __package__)
        _tmpl = getattr(_mod, "templates", None) or getattr(_mod, "_shared_templates", None)
        if _tmpl is not None:
            _register(_tmpl)
    except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
        pass


__all__: list[str] = []
