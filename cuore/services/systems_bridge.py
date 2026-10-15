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


def related_systems(system_key: str, depth: int = 1) -> list[dict[str, Any]]:
    """Systems within ``depth`` ``depends_on`` hops of ``system_key``, both
    directions. Each row: ``system``, ``direction`` ("upstream" = the key
    depends on it, "downstream" = it depends on the key), ``depth``,
    ``path`` (keys from ``system_key`` to the row's system) and ``why``
    (the ``depends_on`` edge's own sourced reason, for the last hop).
    Read straight off ``mes.systems.SYSTEMS``; nothing inferred."""
    graph = systems_mod.systems()
    if system_key not in graph or depth < 1:
        return []
    out: list[dict[str, Any]] = []
    seen = {system_key}
    frontier = [(system_key, [system_key])]
    for level in range(1, depth + 1):
        nxt: list[tuple[str, list[str]]] = []
        for cur, path in frontier:
            edges: list[tuple[str, str, str]] = []
            for dep in graph[cur].get("depends_on") or []:
                edges.append((dep["system"], "upstream", dep.get("why") or ""))
            for other, rec in graph.items():
                for dep in rec.get("depends_on") or []:
                    if dep.get("system") == cur:
                        edges.append((other, "downstream", dep.get("why") or ""))
            for other, direction, why in edges:
                if other in seen or other not in graph:
                    continue
                seen.add(other)
                row_path = path + [other]
                out.append({"system": other, "direction": direction, "depth": level,
                            "path": row_path, "why": why})
                nxt.append((other, row_path))
        frontier = nxt
    return out


__all__ = ["systems", "systems_for_code", "correlate", "related_systems"]
