"""The only module in CUORE that imports :mod:`mes.systems`.

Mirrors the pattern ``known_good_bridge.py``/``parts_bridge.py`` already
use: every route reaches the vehicle-systems graph and its DTC-correlation
view only through this file.

Nothing here invents data -- each function is a thin pass-through to
``mes.systems``, which is where every source citation and confidence level
actually lives (see that module's docstring).
"""

from __future__ import annotations

from typing import Any

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path

from mes import systems as systems_mod  # noqa: E402


def systems() -> dict[str, dict[str, Any]]:
    """Every vehicle system in the graph, in reading order."""
    return systems_mod.systems()


def systems_for_code(code: str, description: str = "") -> list[dict[str, Any]]:
    """Every system a DTC implicates (primary + upstream), each sourced."""
    return systems_mod.systems_for_code(code, description)


def correlate(vin: str) -> dict[str, Any]:
    """One vehicle's DTC corpus projected onto the systems graph: per-system
    counts/status, pairwise co-occurrence, and dependency chains. See
    ``mes.systems.correlate`` for the full contract."""
    return systems_mod.correlate(vin)


__all__ = ["systems", "systems_for_code", "correlate"]
