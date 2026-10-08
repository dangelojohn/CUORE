"""Merges :mod:`cuore.services.electrical_bridge` (electrical-only) with
``mes.layout_systems`` (all-systems: fuel, EVAP, air/boost, cooling, oil,
exhaust, driveline, brakes, steering, suspension, body, ADAS, HVAC) into one
``elements()``/``code_path()``/``systems()`` surface for
:mod:`cuore.web.electrical_routes`.

``mes.layout_systems`` is being built in parallel by another agent, to this
contract:

    elements(system=None) -> {id: {kind, label, location {zone, description,
                   source, confidence}, feeds, part_of_systems, tsb_refs,
                   inspection_hint, notes}}   # same element schema as
                   mes.electrical
    code_physical_path(code) -> {code, path: [{id, role, kind, label,
                   location, source, confidence}], systems_interaction,
                   inspect_steps}
    all_paths()

Imported lazily and guarded exactly the way ``electrical_bridge`` guards
``mes.electrical``: missing, broken, or not-yet-landed must degrade this
module to electrical-only, never raise. Every call here falls back that
way -- the page keeps working before, during and after that module lands.

Every element this module returns gets one extra field: ``system``, a
single canonical key (:data:`CANONICAL_SYSTEMS`) used for the page's filter
chips and node colour. Neither ``mes.electrical``'s informal
``part_of_systems`` tags nor ``mes.systems``'s keys line up exactly with
that chip row, so :data:`_SYSTEM_ALIASES` reconciles them.

``mes.electrical.code_electrical_path`` (reached through
``electrical_bridge.path_for_code``) shapes its path hops as
``{"element", "role", "details", "source", "confidence"}`` -- not the
``{"id", "role", "kind", "label", "location", "source", "confidence"}``
contract above. :func:`_normalize_hop` reconciles that too, so
``code_path()`` always returns the one contract shape regardless of which
source answered.
"""

from __future__ import annotations

from typing import Any, Optional

from . import electrical_bridge

#: (key, label), in the chip-row order the page shows. "all" is not a real
#: element system -- it is the page's "no filter" choice.
CANONICAL_SYSTEMS: list[tuple[str, str]] = [
    ("all", "All"),
    ("electrical", "Electrical"),
    ("fuel", "Fuel"),
    ("evap", "EVAP"),
    ("air_boost", "Air & boost"),
    ("cooling", "Cooling"),
    ("oil", "Oil"),
    ("exhaust", "Exhaust"),
    ("driveline", "Driveline"),
    ("brakes", "Brakes"),
    ("steering", "Steering"),
    ("suspension", "Suspension"),
    ("body", "Body"),
    ("adas", "ADAS"),
    ("hvac", "HVAC"),
]
SYSTEM_LABELS: dict[str, str] = dict(CANONICAL_SYSTEMS)
SYSTEM_KEYS: set[str] = set(SYSTEM_LABELS) - {"all"}

#: reuse var(--fam-*) from cuore.css where the family already matches;
#: otherwise a neutral per-system hue (same literal in both themes -- these
#: are small node/chip accents, not body text, so no dark-mode remap needed).
SYSTEM_COLORS: dict[str, str] = {
    "electrical": "var(--fam-network)",
    "fuel": "var(--fam-engine)",
    "evap": "var(--fam-evap)",
    "air_boost": "var(--fam-engine)",
    "cooling": "var(--fam-engine)",
    "oil": "var(--fam-engine)",
    "exhaust": "var(--fam-engine)",
    "driveline": "var(--fam-chassis)",
    "brakes": "var(--fam-chassis)",
    "steering": "var(--fam-chassis)",
    "suspension": "var(--fam-chassis)",
    "body": "var(--fam-body)",
    "adas": "#8a6fd8",
    "hvac": "#3f9c8f",
}

#: informal electrical_bridge/mes.electrical tags, mes.systems keys, and
#: whatever mes.layout_systems turns out to tag elements with, all land on
#: one of CANONICAL_SYSTEMS. Checked case-insensitively.
_SYSTEM_ALIASES: dict[str, str] = {
    "electrical": "electrical", "electrical_supply": "electrical",
    "charging": "electrical", "cranking": "electrical",
    "network": "electrical", "lighting": "electrical",
    "engine_management": "electrical",
    "evap": "evap",
    "fuel": "fuel",
    "air_intake_boost": "air_boost", "air_boost": "air_boost",
    "boost": "air_boost", "intake": "air_boost",
    "cooling": "cooling",
    "lubrication": "oil", "oil": "oil",
    "exhaust_emissions": "exhaust", "exhaust": "exhaust",
    "transmission_driveline": "driveline", "driveline": "driveline",
    "transmission": "driveline",
    "brakes_abs": "brakes", "brakes": "brakes", "abs": "brakes",
    "chassis": "brakes",
    "steering": "steering",
    "suspension": "suspension",
    "body_comfort": "body", "body": "body",
    "adas_sensors": "adas", "adas": "adas",
    "hvac": "hvac",
}


def canonical_system(element: dict[str, Any]) -> str:
    """The one canonical system key an element belongs to, for callers (the
    routes module's own fixture included) that need to tag an element this
    module did not itself build."""
    for tag in element.get("part_of_systems") or []:
        key = _SYSTEM_ALIASES.get((tag or "").strip().lower())
        if key:
            return key
    return "electrical"


def _layout_mod():
    try:
        from mes import layout_systems
        return layout_systems
    except Exception:  # noqa: BLE001 -- lands concurrently; must never 500
        return None


def _layout_elements(system: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """``mes.layout_systems.elements(system)``, normalized to an
    ``{id: element}`` dict regardless of whether it answers with that shape
    or a list of elements each carrying its own ``id`` (the contract names
    the former; this tolerates the latter too)."""
    mod = _layout_mod()
    if mod is None:
        return {}
    try:
        raw = mod.elements(system) if system else mod.elements()
    except Exception:  # noqa: BLE001
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {e["id"]: e for e in raw if isinstance(e, dict) and e.get("id")}
    return {}


def elements(system: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Every known element -- electrical plus whatever ``mes.layout_systems``
    adds, deduped by id (an id present in both wins from layout_systems, the
    richer/newer source) -- each tagged with a canonical ``system`` key.
    ``system=None``/``"all"`` returns everything."""
    merged: dict[str, dict[str, Any]] = {e["id"]: dict(e) for e in electrical_bridge.list_elements()}
    merged.update({eid: dict(e) for eid, e in _layout_elements().items()})
    for eid, e in merged.items():
        e.setdefault("id", eid)
        if not e.get("system"):
            e["system"] = canonical_system(e)
    if system and system != "all":
        merged = {eid: e for eid, e in merged.items() if e.get("system") == system}
    return merged


def _normalize_hop(hop: dict[str, Any]) -> dict[str, Any]:
    """Reconciles ``mes.electrical.code_electrical_path``'s own hop shape
    (``{"element", "role", "details", "source", "confidence"}``) with the
    ``{"id", "role", "kind", "label", "location", "source", "confidence"}``
    contract ``mes.layout_systems`` and the page both use. Already-contract
    hops (they carry ``id``) pass through untouched."""
    if "id" in hop:
        return hop
    el = hop.get("details") or {}
    loc = el.get("location") or {}
    return {
        "id": hop.get("element"), "role": hop.get("role"),
        "kind": el.get("kind"), "label": el.get("label") or hop.get("element"),
        "location": loc,
        "source": hop.get("source") or loc.get("source"),
        "confidence": hop.get("confidence") or loc.get("confidence"),
    }


def code_path(code: str) -> dict[str, Any]:
    """The physical path for one code: ``mes.layout_systems``'s cross-system
    path when it has one, else the electrical-only path from
    ``electrical_bridge`` (itself falling back to its own fixture), every
    hop normalized to the one contract shape."""
    mod = _layout_mod()
    if mod is not None:
        try:
            result = mod.code_physical_path(code)
            if result and result.get("path"):
                result = dict(result)
                result["path"] = [_normalize_hop(h) for h in result["path"]]
                result.setdefault("systems_interaction", [])
                result.setdefault("inspect_steps", [])
                return result
        except Exception:  # noqa: BLE001
            pass
    fallback = electrical_bridge.path_for_code(code)
    fallback = dict(fallback)
    fallback["path"] = [_normalize_hop(h) for h in (fallback.get("path") or [])]
    fallback.setdefault("systems_interaction", fallback.get("systems_interaction") or [])
    fallback.setdefault("inspect_steps", fallback.get("inspect_steps") or [])
    return fallback


def systems() -> list[tuple[str, str]]:
    """``CANONICAL_SYSTEMS``, or ``mes.layout_systems.all_systems()``/the
    systems named in ``mes.systems`` when that module names something this
    list does not already cover -- kept simple: the page's chip row is
    fixed, so this just returns the fixed list."""
    return CANONICAL_SYSTEMS


__all__ = ["elements", "code_path", "systems", "canonical_system",
           "CANONICAL_SYSTEMS", "SYSTEM_LABELS", "SYSTEM_COLORS", "SYSTEM_KEYS"]
