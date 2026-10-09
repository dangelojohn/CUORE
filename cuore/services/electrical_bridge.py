"""The only module in CUORE that imports :mod:`mes.electrical` /
:mod:`mes.electrical_inspections`.

Same posture as :mod:`cuore.services.parts_bridge`: the import is lazy and
guarded so a missing/broken ``mes`` package degrades the page instead of
500ing it. Unlike ``parts_bridge``, there is no synthetic fixture here --
``mes.electrical`` was built in this same pass, so the real data is used
directly; the guards exist for resilience (a corpus-root misconfiguration,
a future refactor), not because the module is expected to be absent.

Contract reached here:

* ``mes.electrical.ELEMENTS`` / ``element(id)`` / ``elements_for_system(key)``
  (this module's own :func:`elements_for_system` wraps that one with the
  ``mes.systems.ELEMENT_TAGS_FOR`` alias table, so a caller can pass either
  a systems-graph key or a raw electrical tag)
* ``mes.electrical.code_electrical_path(code)``
* ``mes.electrical_inspections.add(...)`` / ``load(vin, element)``

Every public function here degrades to an empty result rather than
raising, except :func:`get_element`, which returns ``None`` for an unknown
id so the API layer can turn that into a 404 -- same convention as
``parts_bridge.part``.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401 -- side effect: puts `mes` on sys.path


def _electrical_mod():
    try:
        from mes import electrical
        return electrical
    except Exception:  # noqa: BLE001 -- must never be why a page 500s
        return None


def _inspections_mod():
    try:
        from mes import electrical_inspections
        return electrical_inspections
    except Exception:  # noqa: BLE001
        return None


def _systems_mod():
    try:
        from mes import systems
        return systems
    except Exception:  # noqa: BLE001
        return None


def list_elements() -> list[dict[str, Any]]:
    mod = _electrical_mod()
    if mod is None:
        return []
    return [mod.element(eid) for eid in sorted(mod.ELEMENTS)]


def get_element(elem_id: str) -> Optional[dict[str, Any]]:
    mod = _electrical_mod()
    if mod is None:
        return None
    return mod.element((elem_id or "").strip())


def path_for_code(code: str) -> dict[str, Any]:
    mod = _electrical_mod()
    if mod is None:
        return {"code": (code or "").strip().upper(), "family": None,
                "path": [], "systems_interaction": [], "inspect_steps": [],
                "note": "mes.electrical not available"}
    return mod.code_electrical_path(code)


def elements_for_system(system_key: str) -> list[dict[str, Any]]:
    """Every electrical-layout element tagged under ``system_key``'s own
    electrical-layout tag(s), via ``mes.systems.ELEMENT_TAGS_FOR`` -- the
    single canonical systems-key <-> electrical-tag map (moved there from
    this app's previous ad-hoc per-caller tag matching; see that module's
    own docstring for why the two vocabularies aren't a 1:1 match).

    Accepts either a systems-graph key (``"brakes_abs"``) or any free text
    ``mes.systems.normalize_system`` already resolves (an electrical tag
    like ``"chassis"``, a label, an alias) -- both land on the same
    element set. Degrades to an empty list rather than raising: no
    ``mes.electrical``/``mes.systems``, an unrecognised key, or a key with
    no tagged elements at all are all the same "nothing to show" case.
    """
    mod = _electrical_mod()
    if mod is None:
        return []
    key = (system_key or "").strip()
    if not key:
        return []
    systems_mod = _systems_mod()
    tags: set[str] = {key}
    if systems_mod is not None:
        try:
            norm = systems_mod.normalize_system(key)
        except Exception:  # noqa: BLE001
            norm = None
        if norm:
            tags.add(norm)
            tags.update(systems_mod.ELEMENT_TAGS_FOR.get(norm, []))
    seen: dict[str, dict[str, Any]] = {}
    for tag in tags:
        for el in mod.elements_for_system(tag):
            if el and el.get("id") not in seen:
                seen[el["id"]] = el
    return list(seen.values())


def list_inspections(vin: str, element: str = "") -> list[dict[str, Any]]:
    mod = _inspections_mod()
    if mod is None:
        return []
    return mod.load(vin=(vin or "").strip(), element=(element or "").strip())


def add_inspection(vin: str, element: str, condition: str,
                    by: str = "technician", note: str = "",
                    media_ids: Optional[list[str]] = None) -> dict[str, Any]:
    mod = _inspections_mod()
    if mod is None:
        raise RuntimeError("mes.electrical_inspections not available")
    return mod.add(vin, element, condition, by=by, note=note,
                    media_ids=media_ids or [])


__all__ = ["list_elements", "get_element", "path_for_code", "elements_for_system",
           "list_inspections", "add_inspection"]
