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


__all__ = ["list_elements", "get_element", "path_for_code",
           "list_inspections", "add_inspection"]
