"""Service layer for the label-printing feature (oil-change / service /
torque-tag / reminder labels on Avery weatherproof sheets).

Separate from :mod:`cuore.services.service_bridge` and
:mod:`cuore.services.mes_bridge` on purpose -- both of those were being
edited concurrently by another agent while this was built, and this feature
only needs read-only access to the ledger (``mes.service``), the spec
libraries (``mes.service_specs``, ``mes.drivetrain_specs``) and the vehicle
workup (``mes.workup``), never a write. It imports ``mes`` directly (via
``cuore.bootstrap``), the same pattern ``service_bridge.py`` uses, rather
than going through either of the other bridges.

Nothing here touches :mod:`cuore.labels.render` or ``.templates`` beyond
translating a record/VIN into the plain dict those modules expect --
geometry and drawing stay in ``cuore.labels``, which has no ``mes``/``cuore``
imports at all and is testable standalone.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401 -- side effect: puts `mes` on sys.path
from .errors import BadRequest, NotFound
from ..labels import render as label_render
from ..labels import templates as label_templates

from mes import service as service_mod  # noqa: E402
from mes import service_specs  # noqa: E402
from mes import drivetrain_specs  # noqa: E402


# --- templates -------------------------------------------------------------


def list_templates() -> dict[str, Any]:
    rows = []
    for t in label_templates.list_templates():
        rows.append({
            "id": t.id, "name": t.name, "material": t.material,
            "printer": t.printer, "cols": t.cols, "rows": t.rows,
            "count": t.count, "label_w_in": t.label_w_in,
            "label_h_in": t.label_h_in, "label_w_mm": t.label_w_mm,
            "label_h_mm": t.label_h_mm, "page_w_mm": t.page_w_mm,
            "page_h_mm": t.page_h_mm,
            "confidence": t.confidence,
            "geometry_confirmed": t.geometry_confirmed,
            "sources": list(t.sources), "notes": t.notes,
        })
    return {"templates": rows, "kinds": list(label_render.KINDS)}


def get_template(template_id: str, custom: Optional[dict[str, Any]] = None):
    if template_id == "custom":
        if not custom:
            raise BadRequest("custom template requires dimensions")
        try:
            return label_templates.build_custom(**custom)
        except (TypeError, ValueError) as exc:
            raise BadRequest(f"bad custom template: {exc}") from exc
    try:
        return label_templates.get(template_id)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


# --- vehicle context ---------------------------------------------------------


def _vehicle_name(vin: str) -> str:
    try:
        from mes import workup as workup_mod
        dossier = workup_mod.build(vin=vin)
        if "error" not in dossier:
            return (dossier.get("identity") or {}).get("vehicle") or vin
    except Exception:
        pass
    return vin


# --- records -----------------------------------------------------------------


def list_records(vin: str, kind: str = "") -> list[dict[str, Any]]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    if kind and kind not in service_mod.KINDS:
        raise BadRequest(f"kind must be one of: {', '.join(service_mod.KINDS)}")
    return service_mod.load(vin, kind or None)


def torque_lookup(key: str) -> Optional[dict[str, Any]]:
    """A torque row by key, checked against both spec libraries -- the
    whole-car ledger (:mod:`mes.service_specs`) and the drivetrain deep-dive
    (:mod:`mes.drivetrain_specs`) use the same row shape."""
    key = (key or "").strip()
    if not key:
        return None
    return service_specs.torque_by_key(key) or drivetrain_specs.torque_by_key(key)


def search_torques(q: str = "") -> list[dict[str, Any]]:
    rows = list(service_specs.search_torques(q=q))
    seen = {r["key"] for r in rows}
    for r in drivetrain_specs.TORQUES:
        if r["key"] in seen:
            continue
        haystack = " ".join([r.get("component", ""), r.get("notes", "") or "",
                             r.get("section", "")]).lower()
        if not q or q.lower() in haystack:
            rows.append(dict(r))
    return rows


# --- record -> label field dicts ---------------------------------------------


def _fmt_num(v: Any, digits: int = 0) -> str:
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:,.{digits}f}"


def oil_change_label_data(vin: str, record: Optional[dict[str, Any]],
                          shop_name: str, overrides: dict[str, Any]) -> dict[str, Any]:
    d = dict((record or {}).get("data") or {})
    oil = d.get("oil") or {}
    filt = d.get("filter") or {}
    next_due = service_mod.next_oil_change(vin) if vin.strip() else {"known": False}

    odo_km = overrides.get("odometer_km") or d.get("odometer_km")
    next_km = overrides.get("next_due_km") or next_due.get("next_due_odometer_km")
    data = {
        "shop_name": overrides.get("shop_name") or shop_name or "CUORE",
        "date": overrides.get("date") or d.get("date") or "",
        "odometer_km": _fmt_num(odo_km),
        "odometer_mi": _fmt_num(label_render.km_to_mi(odo_km)),
        "oil_viscosity": overrides.get("oil_viscosity") or oil.get("viscosity") or "",
        "oil_spec": overrides.get("oil_spec") or oil.get("spec") or "",
        "quantity_l": overrides.get("quantity_l") or d.get("quantity_added_l") or "",
        "filter_part_no": overrides.get("filter_part_no") or filt.get("part_no") or "",
        "technician": overrides.get("technician") or d.get("technician") or "",
        "vin_short": label_render.short_vin(vin),
        "next_due_km": _fmt_num(next_km),
        "next_due_mi": _fmt_num(label_render.km_to_mi(next_km)),
        "next_due_date": overrides.get("next_due_date") or next_due.get("next_due_date") or "",
    }
    return data


def service_label_data(vin: str, record: Optional[dict[str, Any]],
                       overrides: dict[str, Any]) -> dict[str, Any]:
    d = dict((record or {}).get("data") or {})
    odo_km = overrides.get("odometer_km") or d.get("odometer_km")
    category = overrides.get("section") or d.get("category") or ""
    label = service_specs.CATEGORY_LABELS.get(category, category) if category else ""
    return {
        "section": overrides.get("section") or label or "Service",
        "date": overrides.get("date") or d.get("date") or "",
        "work_done": overrides.get("work_done") or d.get("work_done") or "",
        "odometer_km": _fmt_num(odo_km),
        "odometer_mi": _fmt_num(label_render.km_to_mi(odo_km)),
        "next_due": overrides.get("next_due") or "",
        "key_spec": overrides.get("key_spec") or "",
        "key_torque": overrides.get("key_torque") or "",
        "technician": overrides.get("technician") or d.get("technician") or "",
    }


def torque_tag_label_data(overrides: dict[str, Any]) -> dict[str, Any]:
    row = torque_lookup(overrides.get("torque_key", "")) or {}
    nm = overrides.get("torque_nm") or row.get("value_nm")
    lbft = overrides.get("torque_lbft") or row.get("value_lbft")
    return {
        "component": overrides.get("component") or row.get("component") or "",
        "torque_nm": _fmt_num(nm, 1) if nm else "",
        "torque_lbft": _fmt_num(lbft, 1) if lbft else "",
        "angle": overrides.get("angle") or row.get("angle") or "",
        "single_use": bool(overrides.get("single_use") if "single_use" in overrides
                          else row.get("single_use", False)),
        "date": overrides.get("date") or "",
        "technician": overrides.get("technician") or "",
    }


def reminder_label_data(vin: str, overrides: dict[str, Any]) -> dict[str, Any]:
    next_due = service_mod.next_oil_change(vin) if vin.strip() else {"known": False}
    next_km = overrides.get("next_due_km") or next_due.get("next_due_odometer_km")
    return {
        "vehicle": overrides.get("vehicle") or _vehicle_name(vin),
        "job": overrides.get("job") or "Oil change",
        "next_due_km": _fmt_num(next_km),
        "next_due_mi": _fmt_num(label_render.km_to_mi(next_km)),
        "next_due_date": overrides.get("next_due_date") or next_due.get("next_due_date") or "",
    }


_LABEL_DATA_BUILDERS = {
    "oil_change": lambda vin, record, overrides: oil_change_label_data(
        vin, record, overrides.get("shop_name", ""), overrides),
    "service": lambda vin, record, overrides: service_label_data(vin, record, overrides),
    "torque_tag": lambda vin, record, overrides: torque_tag_label_data(overrides),
    "reminder": lambda vin, record, overrides: reminder_label_data(vin, overrides),
}


def build_label_data(vin: str, kind: str, record: Optional[dict[str, Any]],
                     overrides: dict[str, Any]) -> dict[str, Any]:
    if kind not in _LABEL_DATA_BUILDERS:
        raise BadRequest(f"kind must be one of: {', '.join(label_render.KINDS)}")
    return _LABEL_DATA_BUILDERS[kind](vin, record, overrides)


def find_record(vin: str, kind: str, record_id: str) -> Optional[dict[str, Any]]:
    if not record_id:
        return None
    for r in list_records(vin, kind):
        if r.get("id") == record_id:
            return r
    raise NotFound(f"no {kind} record {record_id!r} for {vin}")


# --- rendering ---------------------------------------------------------------


def render_pdf(*, vin: str, kind: str, template_id: str, record_id: str = "",
               overrides: Optional[dict[str, Any]] = None,
               custom: Optional[dict[str, Any]] = None,
               copies: int = 1, start_index: int = 0,
               offset_x_mm: float = 0.0, offset_y_mm: float = 0.0,
               qr_url: Optional[str] = None) -> bytes:
    overrides = dict(overrides or {})
    template = get_template(template_id, custom)
    record = find_record(vin, kind, record_id) if record_id else None
    data = build_label_data(vin, kind, record, overrides)
    try:
        return label_render.generate_labels_pdf(
            template, kind, data, copies=copies, start_index=start_index,
            offset_x_mm=offset_x_mm, offset_y_mm=offset_y_mm, qr_url=qr_url)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def render_test_grid(template_id: str, custom: Optional[dict[str, Any]] = None,
                     offset_x_mm: float = 0.0, offset_y_mm: float = 0.0) -> bytes:
    template = get_template(template_id, custom)
    return label_render.generate_test_grid_pdf(
        template, offset_x_mm=offset_x_mm, offset_y_mm=offset_y_mm)


__all__ = [
    "list_templates", "get_template", "list_records", "torque_lookup",
    "search_torques", "build_label_data", "find_record", "render_pdf",
    "render_test_grid",
]
