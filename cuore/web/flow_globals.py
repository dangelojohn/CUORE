"""Registers the ``flow_state_for`` Jinja global on every template
environment that renders ``_flow_bar.html`` / ``_vtabs.html`` (any page
that already has ``cuore.web.experience_globals`` wired in shares the same
``Jinja2Templates`` instances, so this follows that module's own pattern
rather than inventing a new one).

``flow_state_for(vin)`` calls ``cuore.services.flow_bridge.flow_state(vin)``,
which a separate effort is building (see ``project_mes_toolchain``-style
notes): a dict shaped like::

    {
      "steps": [{"n": 1, "key": "...", "title": "...", "href": "...",
                  "status": "done" | "current" | "todo" | "blocked",
                  "why": "...", "est_min": 10}, ...],
      "current": 6,
      "next": {"n": 7, "title": "...", "href": "...", "button_label": "..."},
      "visit": {...}, "job": {...}, "blockers": [...],
    }

``flow_bridge`` does not exist yet as this module is written, so the import
is deliberately lazy (inside the call, not at module load) and every
failure mode -- module missing, ``flow_state`` raising, a VIN the service
has no opinion on -- degrades to ``None`` rather than a 500. The templates
that read this global already treat ``None`` as "show the minimal
'take this car in' bar", so nothing here needs to know about that UI.

Importing this module is the side effect that does the registration --
nothing here is called directly. Wiring it in (so the global actually
exists at render time) is the same one-line move ``cuore.api.experience``
uses for ``experience_globals`` -- ``from ..web import flow_globals  # noqa:
F401`` from whatever module ends up owning the flow feature's HTTP surface,
or directly from ``app.py``; left for the integration pass, not done here.
"""

from __future__ import annotations

import importlib
from typing import Any


def _flow_state(vin: str, **kw: Any) -> dict[str, Any] | None:
    try:
        from ..services import flow_bridge  # lazy: module may not exist yet
    except Exception:  # noqa: BLE001 -- missing/broken service must never 500 a page
        return None
    try:
        return flow_bridge.flow_state(vin, **kw)
    except Exception:  # noqa: BLE001 -- same: a template global must never raise
        return None


def _register(templates: Any) -> None:
    templates.env.globals["flow_state_for"] = _flow_state


for _module_name in ("routes", "service_routes", "drivetrain_routes", "timeline_routes"):
    try:
        _mod = importlib.import_module(f".{_module_name}", __package__)
        _tmpl = getattr(_mod, "templates", None) or getattr(_mod, "_shared_templates", None)
        if _tmpl is not None:
            _register(_tmpl)
    except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
        pass


__all__: list[str] = []
