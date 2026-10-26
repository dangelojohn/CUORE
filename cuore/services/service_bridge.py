"""The only module in CUORE that imports :mod:`mes.service` / :mod:`mes.service_specs`.

Mirrors ``cuore.services.mes_bridge`` for this feature: ``mes_bridge.py`` was
being edited concurrently by another agent while this was built, so this
stays a separate file rather than adding to it, but follows the same rule
-- every route reaches the ledger and the spec library through here, never
directly, so the HTML pages and the JSON API cannot drift apart.

Nothing here re-implements validation, torque checking, or next-due
arithmetic. All of that lives in ``mes.service`` and ``mes.service_specs``
and is unit-tested there; this file only calls it and translates "bad
input"/"not found" into the exceptions the HTTP layer turns into status
codes.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from .errors import BadRequest, NotFound

from mes import service as service_mod  # noqa: E402
from mes import service_specs  # noqa: E402
from mes import maintenance_specs  # noqa: E402


# --- oil change --------------------------------------------------------------


def record_oil_change(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return service_mod.record_oil_change(vin, data)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def oil_change_checklist(vin: str) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return service_mod.oil_change_checklist(vin)


def next_oil_change(vin: str) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return service_mod.next_oil_change(vin)


# --- general service -----------------------------------------------------


def record_service(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return service_mod.record_service(vin, data)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


# --- brakes / wheels / tyres -----------------------------------------------


def record_brakes_wheels_tires(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return service_mod.record_brakes_wheels_tires(vin, data)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def brakes_wheels_tires_checklist(vin: str) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return service_mod.brakes_wheels_tires_checklist(vin)


def latest_tpms_observation(vin: str) -> dict[str, Any]:
    """The newest RFHUB TPMS DID observation for this VIN, read-only.

    Reads ``mes.live_obs`` -- never writes, never triggers a live read.
    Returns ``{"available": False}`` when nothing has been recorded, or
    when the live_obs module cannot be reached for any reason (a broken
    live-link store must never break this page).
    """
    dids = set(service_specs.TPMS_DIDS["dids"].values())
    try:
        from mes import live_obs
        obs = live_obs.load(vin=vin, kind="did", from_car_only=True)
    except Exception:
        return {"available": False}
    by_corner: dict[str, Any] = {}
    corner_by_did = {v: k for k, v in service_specs.TPMS_DIDS["dids"].items()}
    for entry in reversed(obs):
        data = entry.get("data") or {}
        if str(data.get("ecu", "")).upper() != service_specs.TPMS_DIDS["module"]:
            continue
        did = data.get("did")
        try:
            did_int = int(did, 16) if isinstance(did, str) else int(did)
        except (TypeError, ValueError):
            continue
        corner = corner_by_did.get(did_int)
        if not corner or corner in by_corner:
            continue
        by_corner[corner] = {"at": entry.get("at"), "value": data.get("value"),
                             "bytes": data.get("bytes"), "did": did}
        if len(by_corner) == len(dids):
            break
    return {"available": bool(by_corner), "corners": by_corner}


# --- drivetrain (transmission / transfer case / differentials / driveline /
#     mounts) --------------------------------------------------------------


def drivetrain_sections() -> list[str]:
    return list(service_mod.DRIVETRAIN_SECTIONS)


def record_drivetrain(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return service_mod.record_drivetrain(vin, data)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def drivetrain_section_checklist(vin: str, section: str) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return service_mod.drivetrain_section_checklist(vin, section)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


def drivetrain_job_torque_checklist(section: str, job: str) -> list[dict[str, Any]]:
    return service_mod.build_drivetrain_torque_checklist(section, job)


# --- maintenance (air/cabin/fuel filters, spark plugs, coils, coolant, brake
#     fluid, belt, 12V battery, wipers, PCV, throttle body, boost hoses,
#     washer fluid, A/C, EPS, hinge/latch lubrication) ------------------------


def maintenance_item_keys() -> list[str]:
    return list(maintenance_specs.ITEMS.keys())


def record_maintenance(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return service_mod.record_maintenance(vin, data)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def maintenance_checklist(vin: str, current_odometer_km: Optional[float] = None) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return service_mod.maintenance_checklist(vin, current_odometer_km)


def maintenance_due(vin: str, current_odometer_km: Optional[float] = None) -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return service_mod.maintenance_due(vin, current_odometer_km)


def maintenance_label(item_key: str) -> str:
    return (maintenance_specs.ITEMS.get(item_key) or {}).get("label", item_key)


#: The ledger requires a technician; a one-tap record is labelled so it is
#: never mistaken for a hand-written visit.
DONE_TODAY_TECHNICIAN = "owner (Done today tap)"
DONE_TODAY_ACTIONS = ("replaced", "inspected_ok")

_STATUS_ORDER = ("overdue", "due_soon", "ok", "unknown")
_STATUS_GROUP_LABEL = {
    "overdue": "Overdue",
    "due_soon": "Due soon",
    "ok": "OK",
    "unknown": "Never logged or interval unknown",
}


def age_label(days: Optional[int]) -> str:
    if days is None:
        return ""
    if days <= 0:
        return "today"
    if days < 60:
        return f"{days} d ago"
    if days < 730:
        return f"{days // 30} mo ago"
    return f"{days // 365} y ago"


def maintenance_groups(checklist: dict[str, Any], today: Any = None) -> list[dict[str, Any]]:
    """The maintenance items re-ordered for reading: overdue, due soon, OK,
    then every never-logged / interval-unknown item folded into one counted
    group. Inside a group the most recently done comes first (overdue and
    due-soon: soonest due first). Nothing is invented -- an unknown stays
    UNKNOWN and an item never logged shows no age."""
    from datetime import date as _date
    today = today or _date.today()
    due_by_key = {d["item_key"]: d for d in checklist["due"]["items"]}
    labels = checklist.get("category_labels") or {}
    rows: list[dict[str, Any]] = []
    for category, items in checklist["items_by_category"].items():
        for it in items:
            due = due_by_key.get(it["key"]) or {}
            status = due.get("status") or "interval_unknown"
            group = status if status in ("overdue", "due_soon", "ok") else "unknown"
            parsed = service_mod._parse_date(due.get("last_date"))
            days = (today - parsed).days if parsed else None
            rows.append({
                "it": it, "due": due, "status": status, "group": group,
                "category_label": labels.get(category, str(category).replace("_", " ").title()),
                "age": age_label(days), "days": days,
            })
    out = []
    for g in _STATUS_ORDER:
        members = [r for r in rows if r["group"] == g]
        if not members:
            continue
        if g in ("overdue", "due_soon"):
            members.sort(key=lambda r: (r["due"].get("next_due_date") or "9999", r["it"]["label"]))
        else:
            members.sort(key=lambda r: (r["days"] is None, r["days"] or 0, r["it"]["label"]))
        out.append({"key": g, "label": _STATUS_GROUP_LABEL[g], "rows": members,
                    "count": len(members), "open": g in ("overdue", "due_soon")})
    return out


def record_done_today(vin: str, item_key: str, odometer_km: Any,
                      action: str = "replaced") -> dict[str, Any]:
    """One-tap "Done today": records one maintenance item through the same
    ledger call the full visit form uses, dated today. The caller supplies
    only the odometer."""
    from datetime import date as _date
    if item_key not in maintenance_specs.ITEMS:
        raise NotFound(f"unknown maintenance item {item_key!r}")
    if action not in DONE_TODAY_ACTIONS:
        raise BadRequest("action must be one of: " + ", ".join(DONE_TODAY_ACTIONS))
    return record_maintenance(vin, {
        "date": _date.today().isoformat(),
        "odometer_km": odometer_km,
        "technician": DONE_TODAY_TECHNICIAN,
        "items": [{"item_key": item_key, "action": action}],
    })


def undo_done_today(vin: str, record_id: str) -> dict[str, Any]:
    """Undo a one-tap record through the ledger's own ``amend`` (history is
    never rewritten: the original line stays, an amendment empties its items
    and marks it voided, so it no longer counts as 'last done')."""
    rec = next((r for r in service_mod.load(vin, "maintenance") if r.get("id") == record_id), None)
    if rec is None:
        raise NotFound("no such maintenance record for this vehicle")
    if (rec.get("data") or {}).get("technician") != DONE_TODAY_TECHNICIAN:
        raise BadRequest("only a one-tap Done today record can be undone here")
    return amend_record(vin, record_id, {"items": [], "flags": [], "voided": True},
                        note="Undo of Done today tap")


def build_maintenance_torque_checklist(item_keys: Any) -> list[dict[str, Any]]:
    return service_mod.build_maintenance_torque_checklist(item_keys)


def latest_gearbox_oil_temp_observation(vin: str) -> dict[str, Any]:
    """The newest TCM DID 04FE (gearbox oil temperature) observation for
    this VIN, read-only. Reads ``mes.live_obs`` -- never writes, never
    triggers a live read. Returns ``{"available": False}`` when nothing has
    been recorded, or when the live_obs module cannot be reached for any
    reason (a broken live-link store must never break this page).
    """
    try:
        from mes import live_obs
        obs = live_obs.load(vin=vin, kind="did", from_car_only=True)
    except Exception:
        return {"available": False}
    for entry in reversed(obs):
        data = entry.get("data") or {}
        if str(data.get("ecu", "")).upper() != "TCM":
            continue
        did = data.get("did")
        try:
            did_int = int(did, 16) if isinstance(did, str) else int(did)
        except (TypeError, ValueError):
            continue
        if did_int != 0x04FE:
            continue
        return {"available": True, "at": entry.get("at"), "value": data.get("value"),
                "bytes": data.get("bytes"), "did": did}
    return {"available": False}


# --- service hub -------------------------------------------------------------


def _flags_of(entry: Optional[dict[str, Any]]) -> list[str]:
    if not entry:
        return []
    d = entry.get("data", {}) or {}
    out = list(d.get("flags") or [])
    out.extend((d.get("torque_checklist") or {}).get("flags") or [])
    fw = d.get("fill_window_flag")
    if fw:
        out.append(fw)
    return out


def _mes_service_events(vin: str) -> list[dict[str, Any]]:
    """Service-type adjustments MES logged on this car (oil-change reset,
    turbo replacement, ...), newest first, one per operation per day.
    These come from MES logs, not from a cuore service record."""
    try:
        from mes import workup
        attempted = workup.build(vin).get("already_attempted") or []
    except Exception:  # MES logs unavailable must never break the hub
        return []
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for a in attempted:
        if a.get("kind") != "adjustment" or not a.get("operation"):
            continue
        date = str(a.get("timestamp") or "")[:10]
        key = (a["operation"], date)
        if key in seen:
            continue
        seen.add(key)
        out.append({"operation": a["operation"], "date": date,
                    "outcome": a.get("outcome"), "source": "logged in MES"})
    out.sort(key=lambda e: e["date"], reverse=True)
    return out


def service_hub(vin: str) -> dict[str, Any]:
    """Everything the service hub page/JSON needs: last service + open flags
    for every section, assembled from records already validated and
    torque-checked by :mod:`mes.service` -- no new checking happens here.
    """
    if not vin.strip():
        raise BadRequest("a VIN is required")

    last_oil = service_mod.last_oil_change(vin)
    last_svc = service_mod.last_of_kind(vin, "service")
    last_brakes = service_mod.last_of_kind(vin, "brakes_wheels_tires")

    drivetrain: dict[str, Any] = {}
    for section in service_mod.DRIVETRAIN_SECTIONS:
        last = service_mod.last_drivetrain(vin, section)
        drivetrain[section] = {"last": last, "flags": _flags_of(last)}

    last_maintenance = service_mod.last_of_kind(vin, "maintenance")
    maint_due = service_mod.maintenance_due(vin)
    due_items = maint_due.get("items", [])

    return {
        "vin": vin,
        "oil_service": {
            "last_oil_change": last_oil,
            "last_service": last_svc,
            "flags": _flags_of(last_oil) + _flags_of(last_svc),
            "next_oil_due": service_mod.next_oil_change(vin),
            "mes_events": _mes_service_events(vin),
        },
        "brakes_tires": {"last": last_brakes, "flags": _flags_of(last_brakes)},
        "drivetrain": drivetrain,
        "maintenance": {
            "last": last_maintenance,
            "flags": _flags_of(last_maintenance),
            "due": maint_due,
            "overdue_count": sum(1 for i in due_items if i["status"] == "overdue"),
            "due_soon_count": sum(1 for i in due_items if i["status"] == "due_soon"),
        },
    }


# --- records list / amendments ---------------------------------------------


def load_records(vin: str, kind: str = "") -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    if kind and kind not in service_mod.KINDS:
        raise BadRequest(f"kind must be one of: {', '.join(service_mod.KINDS)}")
    return {"vin": vin, "kind": kind or None,
            "records": service_mod.load(vin, kind or None)}


def amend_record(vin: str, record_id: str, data: dict[str, Any],
                 note: str = "") -> dict[str, Any]:
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return service_mod.amend(vin, record_id, data, note=note)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


# --- torque library ----------------------------------------------------------


def search_torques(q: str = "", category: str = "") -> dict[str, Any]:
    if category and category not in service_specs.CATEGORIES:
        raise BadRequest(f"category must be one of: "
                         + ", ".join(service_specs.CATEGORIES))
    rows = service_specs.search_torques(q=q, category=category)
    return {"q": q, "category": category or None, "count": len(rows),
            "categories": list(service_specs.CATEGORIES),
            "category_labels": service_specs.CATEGORY_LABELS,
            "torques": rows}


def torque_categories() -> dict[str, Any]:
    return {"categories": list(service_specs.CATEGORIES),
            "labels": service_specs.CATEGORY_LABELS}


def build_torque_checklist(categories: Any) -> list[dict[str, Any]]:
    return service_mod.build_torque_checklist(categories)


__all__ = [
    "record_oil_change", "oil_change_checklist", "next_oil_change",
    "record_service", "record_brakes_wheels_tires",
    "brakes_wheels_tires_checklist", "latest_tpms_observation",
    "drivetrain_sections", "record_drivetrain", "drivetrain_section_checklist",
    "drivetrain_job_torque_checklist", "latest_gearbox_oil_temp_observation",
    "maintenance_item_keys", "record_maintenance", "maintenance_groups",
    "record_done_today", "undo_done_today", "maintenance_label", "maintenance_checklist",
    "maintenance_due", "build_maintenance_torque_checklist",
    "service_hub",
    "load_records", "amend_record", "search_torques", "torque_categories",
    "build_torque_checklist",
]
