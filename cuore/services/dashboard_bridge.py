"""The one module that imports :mod:`mes.dashboard`.

Mirrors :mod:`cuore.services.mes_bridge`'s role for this one feature: the
dashboard route and API endpoint reach ``mes`` only through here, never
directly. It is a separate module rather than an addition to ``mes_bridge``
only because ``mes_bridge.py`` was being edited concurrently by another agent
when this was built (2026-09-26) -- the owner may fold ``dashboard()`` into
``mes_bridge`` later, at which point this module can go away.
"""

from __future__ import annotations

from typing import Any

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from .errors import NotFound

from mes import dashboard as dashboard_mod  # noqa: E402


def dashboard(vin: str) -> dict[str, Any]:
    """The per-vehicle dashboard. Raises :class:`NotFound` when no logs match."""
    result = dashboard_mod.build(vin=vin)
    if "error" in result:
        raise NotFound(result["error"])
    return result


__all__ = ["dashboard"]
