"""Service pages: oil change, general service, brakes/wheels/tyres, torque
library.

A separate router from ``cuore.web.routes`` (which was being edited
concurrently by another agent while this was built) but the same posture:
every page calls the same :mod:`cuore.services.service_bridge` functions the
JSON endpoints below do, so the two surfaces cannot disagree.

Page set:

===========================  ==================================================
``/v/{vin}/oil-change``      the oil-change page: specs, torque checklist, form
``/v/{vin}/service``         general service record list + entry form
``/v/{vin}/brakes-tires``    brakes/wheels/tyres corner-by-corner page
``/v/{vin}/torque``          the searchable torque library
``/v/{vin}/maintenance``     routine maintenance: due table, item specs, form
===========================  ==================================================

Not registered on the app here -- ``app.py`` is owned by another agent while
this was built. The one line needed there:

    ``app.include_router(service_routes.router)``
    ``app.include_router(service_routes.api_router, prefix="/api")``

(importing this module next to the other web-route imports as
``from .web import service_routes``.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..services import cache, mes_bridge, service_bridge
from ..services.errors import BridgeError
from ..api.deps import require_token, settings_of

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(include_in_schema=False,
                   dependencies=[Depends(require_token)])

api_router = APIRouter(tags=["service"], dependencies=[Depends(require_token)])

_VIN_COOKIE = "cuore_vin"


# --- helpers (small, deliberate duplicates of cuore.web.routes's private
#     helpers -- that module was being edited concurrently, so this stays
#     self-contained rather than importing private names from it) -----------


def _dossier(vin: str) -> dict[str, Any]:
    """The cached workup for a VIN -- or an empty dossier when the corpus has
    no logs for it yet.

    Service records (oil change, general service, brakes/wheels/tyres) are
    valid to start on a car MES has never scanned -- a service history has
    to be startable before the first log exists, not just after. Only the
    vehicle-bar/odometer *display* degrades here; the ledger itself never
    depends on this.
    """
    try:
        return cache.get_or_build(
            ("workup", vin, mes_bridge.newest_mtime(vin)),
            lambda: mes_bridge.workup(vin=vin),
        )
    except BridgeError:
        return {"identity": {}}


def _vehicle_bar(vin: str, dossier: dict[str, Any]) -> dict[str, Any]:
    ident = dossier.get("identity", {})
    first, last = ident.get("odometer_first_km"), ident.get("odometer_last_km")
    span = None
    if isinstance(first, (int, float)) and isinstance(last, (int, float)):
        span = int(last) - int(first)
    return {
        "vin": vin,
        "name": ident.get("vehicle") or "(unnamed vehicle)",
        "logs": ident.get("log_count"),
        "first_log": ident.get("first_log"),
        "last_log": ident.get("last_log"),
        "odo_first": first,
        "odo_last": last,
        "odo_span": span,
        "ecus": ident.get("ecu_seen") or [],
    }


def _page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    settings = settings_of(request)
    ctx.setdefault("version", __version__)
    ctx.setdefault("profile", settings.profile.value)
    ctx.setdefault("live_strip", None)
    return templates.TemplateResponse(request, name, ctx)


def _set_active_vehicle(response: Response, vin: str) -> None:
    response.set_cookie(_VIN_COOKIE, vin, max_age=60 * 60 * 24 * 30, samesite="lax")


def _current_odometer(dossier: dict[str, Any]) -> Any:
    return (dossier.get("identity") or {}).get("odometer_last_km")


# --- oil change ----------------------------------------------------------


@router.get("/v/{vin}/oil-change", response_class=HTMLResponse)
def oil_change_form(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    checklist = service_bridge.oil_change_checklist(vin)
    response = _page(request, "oil_change.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="oil-change", checklist=checklist,
                     current_odometer=_current_odometer(dossier), error=None, saved=False)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/oil-change", response_class=HTMLResponse)
async def oil_change_submit(request: Request, vin: str) -> HTMLResponse:
    form = await request.form()

    def field(name: str) -> str:
        return str(form.get(name, "")).strip()

    torque_keys = [t["key"] for t in service_bridge.oil_change_checklist(vin)["torque_checklist"]]
    torques_applied = {k: field(f"torque_{k}") for k in torque_keys if field(f"torque_{k}")}

    data = {
        "date": field("date"),
        "odometer_km": field("odometer_km"),
        "oil": {"brand": field("oil_brand"), "product": field("oil_product"),
                "viscosity": field("oil_viscosity"), "spec": field("oil_spec")},
        "quantity_added_l": field("quantity_added_l"),
        "drained": {"color": field("drained_color"), "smell": field("drained_smell"),
                    "metal": form.get("drained_metal") == "on",
                    "fuel_dilution_suspected": form.get("fuel_dilution_suspected") == "on",
                    "coolant_suspected": form.get("coolant_suspected") == "on",
                    "condition_notes": field("drained_condition_notes")},
        "filter": {"brand": field("filter_brand"), "part_no": field("filter_part_no")},
        "drain_plug_washer_replaced": form.get("drain_plug_washer_replaced") == "on",
        "torques_applied": torques_applied,
        "reset": {"done": form.get("reset_done") == "on", "method": field("reset_method")},
        "sample_taken": form.get("sample_taken") == "on",
        "leaks_found": field("leaks_found"),
        "discoveries": field("discoveries"),
        "considerations_next": field("considerations_next"),
        "technician": field("technician"),
    }

    error = None
    saved = False
    try:
        service_bridge.record_oil_change(vin, data)
        saved = True
    except BridgeError as exc:
        error = str(exc)

    dossier = _dossier(vin)
    checklist = service_bridge.oil_change_checklist(vin)
    response = _page(request, "oil_change.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="oil-change", checklist=checklist,
                     current_odometer=_current_odometer(dossier), error=error, saved=saved)
    _set_active_vehicle(response, vin)
    return response


# --- general service -------------------------------------------------------


@router.get("/v/{vin}/service", response_class=HTMLResponse)
def service_form(request: Request, vin: str, category: str = "") -> HTMLResponse:
    """``category`` (query string) picks which job the torque checklist
    below the form is generated for -- the category <select> resubmits as a
    plain GET on change, so this works with no JavaScript beyond that one
    auto-submit."""
    dossier = _dossier(vin)
    from mes import service_specs
    records = service_bridge.load_records(vin)["records"]
    category = category.strip().lower()
    checklist_rows = service_bridge.build_torque_checklist(category) if category in service_specs.CATEGORIES else []
    response = _page(request, "service.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="service", records=records,
                     categories=service_specs.CATEGORIES,
                     category_labels=service_specs.CATEGORY_LABELS,
                     current_odometer=_current_odometer(dossier), error=None, saved=False,
                     selected_category=category, checklist_rows=checklist_rows)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/service", response_class=HTMLResponse)
async def service_submit(request: Request, vin: str) -> HTMLResponse:
    form = await request.form()

    def field(name: str) -> str:
        return str(form.get(name, "")).strip()

    category = field("category")
    torque_keys = [t["key"] for t in service_bridge.build_torque_checklist(category)] if category else []
    torques_applied = {k: field(f"torque_{k}") for k in torque_keys if field(f"torque_{k}")}

    parts = []
    names = form.getlist("part_name") if hasattr(form, "getlist") else []
    part_nos = form.getlist("part_no") if hasattr(form, "getlist") else []
    qtys = form.getlist("part_qty") if hasattr(form, "getlist") else []
    for i, name in enumerate(names):
        name = name.strip()
        if not name:
            continue
        parts.append({"name": name,
                      "part_no": part_nos[i].strip() if i < len(part_nos) else "",
                      "qty": qtys[i].strip() if i < len(qtys) else 1})

    data = {
        "date": field("date"),
        "odometer_km": field("odometer_km"),
        "category": category,
        "work_done": field("work_done"),
        "parts": parts,
        "fluids": field("fluids"),
        "torques_applied": torques_applied,
        "discoveries": field("discoveries"),
        "considerations_next": field("considerations_next"),
        "technician": field("technician"),
    }

    error = None
    saved = False
    try:
        service_bridge.record_service(vin, data)
        saved = True
    except BridgeError as exc:
        error = str(exc)

    from mes import service_specs
    dossier = _dossier(vin)
    records = service_bridge.load_records(vin)["records"]
    checklist_rows = service_bridge.build_torque_checklist(category) if category else []
    response = _page(request, "service.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="service", records=records,
                     categories=service_specs.CATEGORIES,
                     category_labels=service_specs.CATEGORY_LABELS,
                     current_odometer=_current_odometer(dossier), error=error, saved=saved,
                     selected_category=category, checklist_rows=checklist_rows)
    _set_active_vehicle(response, vin)
    return response


# --- brakes / wheels / tyres -------------------------------------------------


@router.get("/v/{vin}/brakes-tires", response_class=HTMLResponse)
def brakes_tires_form(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    checklist = service_bridge.brakes_wheels_tires_checklist(vin)
    tpms = service_bridge.latest_tpms_observation(vin)
    from mes import service as service_mod
    response = _page(request, "brakes_tires.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="brakes-tires", checklist=checklist, tpms=tpms,
                     corners=service_mod.CORNERS,
                     current_odometer=_current_odometer(dossier), error=None, saved=False)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/brakes-tires", response_class=HTMLResponse)
async def brakes_tires_submit(request: Request, vin: str) -> HTMLResponse:
    form = await request.form()
    from mes import service as service_mod

    def field(name: str) -> str:
        return str(form.get(name, "")).strip()

    def corner_field(corner: str, name: str) -> str:
        return field(f"{corner}_{name}")

    corners: dict[str, Any] = {}
    for c in service_mod.CORNERS:
        corners[c] = {
            "pad_thickness_mm": {"inner": corner_field(c, "pad_inner"),
                                 "outer": corner_field(c, "pad_outer")},
            "rotor_thickness_mm": corner_field(c, "rotor_thickness"),
            "rotor_runout_mm": corner_field(c, "rotor_runout"),
            "rotor_condition": corner_field(c, "rotor_condition"),
            "caliper_condition": corner_field(c, "caliper_condition"),
            "slider_condition": corner_field(c, "slider_condition"),
            "boot_condition": corner_field(c, "boot_condition"),
            "hose_condition": corner_field(c, "hose_condition"),
            "tyre": {"brand": corner_field(c, "tyre_brand"),
                    "model": corner_field(c, "tyre_model"),
                    "size": corner_field(c, "tyre_size"),
                    "load_speed_index": corner_field(c, "tyre_lsi"),
                    "dot_date_code": corner_field(c, "tyre_dot")},
            "tread_depth_mm": {"inside": corner_field(c, "tread_inside"),
                               "middle": corner_field(c, "tread_middle"),
                               "outside": corner_field(c, "tread_outside")},
            "pressure_found_kpa": corner_field(c, "pressure_found"),
            "pressure_set_kpa": corner_field(c, "pressure_set"),
            "damage_notes": corner_field(c, "damage_notes"),
            "wheel_condition": corner_field(c, "wheel_condition"),
            "tpms": {"sensor_id": corner_field(c, "tpms_id"),
                    "pressure_kpa": corner_field(c, "tpms_pressure"),
                    "temperature_c": corner_field(c, "tpms_temp")},
            "lug_torque_applied": corner_field(c, "lug_torque"),
        }

    torque_keys = [t["key"] for t in
                   service_bridge.build_torque_checklist(["brakes_front", "brakes_rear", "wheels"])]
    torques_applied = {k: field(f"torque_{k}") for k in torque_keys if field(f"torque_{k}")}

    data = {
        "date": field("date"),
        "odometer_km": field("odometer_km"),
        "technician": field("technician"),
        "corners": corners,
        "fluid": {"type": field("fluid_type"),
                 "moisture_test_result": field("fluid_moisture_result"),
                 "boiling_point_c": field("fluid_boiling_point"),
                 "replaced": form.get("fluid_replaced") == "on"},
        "rotation": {"done": form.get("rotation_done") == "on",
                    "pattern": field("rotation_pattern")},
        "balance_done": form.get("balance_done") == "on",
        "alignment": {"done": form.get("alignment_done") == "on",
                     "needed": form.get("alignment_needed") == "on"},
        "epb_service_mode": {"used": form.get("epb_used") == "on",
                             "tool": field("epb_tool")},
        "torques_applied": torques_applied,
        "discoveries": field("discoveries"),
        "considerations_next": field("considerations_next"),
    }

    error = None
    saved = False
    try:
        service_bridge.record_brakes_wheels_tires(vin, data)
        saved = True
    except BridgeError as exc:
        error = str(exc)

    dossier = _dossier(vin)
    checklist = service_bridge.brakes_wheels_tires_checklist(vin)
    tpms = service_bridge.latest_tpms_observation(vin)
    response = _page(request, "brakes_tires.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="brakes-tires", checklist=checklist, tpms=tpms,
                     corners=service_mod.CORNERS,
                     current_odometer=_current_odometer(dossier), error=error, saved=saved)
    _set_active_vehicle(response, vin)
    return response


# --- torque library page ---------------------------------------------------


@router.get("/v/{vin}/torque", response_class=HTMLResponse)
def torque_page(request: Request, vin: str, q: str = "", category: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    result = service_bridge.search_torques(q=q, category=category)
    response = _page(request, "torque.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="torque", result=result, q=q, category=category)
    _set_active_vehicle(response, vin)
    return response


# --- routine maintenance ------------------------------------------------------


def _selected_item_keys(raw: list[str], valid_keys: list[str]) -> list[str]:
    """``raw`` is the repeated ``items``/``selected_items`` values from a
    checkbox group (query string on GET, form field on POST) -- keeps
    order, drops blanks and anything not a real item key (never lets a
    stale/forged key reach the torque-checklist lookup)."""
    seen: set[str] = set()
    out: list[str] = []
    for k in raw or []:
        k = (k or "").strip()
        if k in valid_keys and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _maintenance_page(request: Request, vin: str, *, selected: list[str],
                      error: Optional[str], saved: bool) -> HTMLResponse:
    from mes import service as service_mod
    dossier = _dossier(vin)
    current_odo = _current_odometer(dossier)
    checklist = service_bridge.maintenance_checklist(vin, current_odo)
    torque_rows = service_bridge.build_maintenance_torque_checklist(selected) if selected else []
    all_items = [it for group in checklist["items_by_category"].values() for it in group]
    response = _page(request, "maintenance.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="service-hub", checklist=checklist,
                     item_keys=service_bridge.maintenance_item_keys(), all_items=all_items,
                     selected_items=selected, torque_rows=torque_rows,
                     actions=service_mod.MAINTENANCE_ACTIONS,
                     current_odometer=current_odo, error=error, saved=saved)
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/maintenance", response_class=HTMLResponse)
def maintenance_form(request: Request, vin: str,
                     items: list[str] = Query(default=[])) -> HTMLResponse:
    """``items`` (repeated query param, one per checked checkbox) picks which
    items get a detailed action/parts/measurements block plus a torque
    checklist in the record form below -- a plain GET resubmit, same
    mechanism as the general service page's category picker and the
    drivetrain job picker, generalised to a multi-select."""
    valid_keys = service_bridge.maintenance_item_keys()
    selected = _selected_item_keys(items, valid_keys)
    return _maintenance_page(request, vin, selected=selected, error=None, saved=False)


@router.post("/v/{vin}/maintenance", response_class=HTMLResponse)
async def maintenance_submit(request: Request, vin: str) -> HTMLResponse:
    form = await request.form()

    def field(name: str) -> str:
        return str(form.get(name, "")).strip()

    valid_keys = service_bridge.maintenance_item_keys()
    selected = _selected_item_keys(
        form.getlist("selected_items") if hasattr(form, "getlist") else [], valid_keys)

    items_payload = []
    for key in valid_keys:
        if form.get(f"record_item_{key}") != "on":
            continue
        measurements: dict[str, Any] = {}
        for i in (1, 2, 3):
            label = field(f"measure_label_{key}_{i}")
            value = field(f"measure_value_{key}_{i}")
            if label and value:
                measurements[label] = value
        items_payload.append({
            "item_key": key,
            "action": field(f"action_{key}"),
            "part_brand": field(f"part_brand_{key}"),
            "part_number": field(f"part_number_{key}"),
            "fluid_brand": field(f"fluid_brand_{key}"),
            "fluid_amount": field(f"fluid_amount_{key}"),
            "condition_notes": field(f"condition_notes_{key}"),
            "measurements": measurements,
        })

    torque_keys = ([t["key"] for t in service_bridge.build_maintenance_torque_checklist(selected)]
                  if selected else [])
    torques_applied = {k: field(f"torque_{k}") for k in torque_keys if field(f"torque_{k}")}

    data = {
        "date": field("date"),
        "odometer_km": field("odometer_km"),
        "technician": field("technician"),
        "items": items_payload,
        "torques_applied": torques_applied,
        "discoveries": field("discoveries"),
        "next_time_notes": field("next_time_notes"),
        "post_service_done": field("post_service_done"),
    }

    error = None
    saved = False
    try:
        service_bridge.record_maintenance(vin, data)
        saved = True
    except BridgeError as exc:
        error = str(exc)

    return _maintenance_page(request, vin, selected=selected, error=error, saved=saved)


# --- JSON API ----------------------------------------------------------------


@api_router.get("/vehicles/{vin}/service-records")
def api_list_service_records(vin: str, kind: str = "") -> dict[str, Any]:
    return service_bridge.load_records(vin, kind)


@api_router.post("/vehicles/{vin}/service-records")
async def api_record_service(vin: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    kind = str(body.get("kind", "")).strip()
    data = body.get("data") or {}
    if kind == "oil_change":
        return service_bridge.record_oil_change(vin, data)
    if kind == "service":
        return service_bridge.record_service(vin, data)
    if kind == "brakes_wheels_tires":
        return service_bridge.record_brakes_wheels_tires(vin, data)
    raise BridgeError("kind must be one of: oil_change, service, brakes_wheels_tires")


@api_router.get("/vehicles/{vin}/oil-change/next")
def api_next_oil_change(vin: str) -> dict[str, Any]:
    return service_bridge.next_oil_change(vin)


@api_router.get("/vehicles/{vin}/brakes-tires/checklist")
def api_brakes_tires_checklist(vin: str) -> dict[str, Any]:
    return service_bridge.brakes_wheels_tires_checklist(vin)


@api_router.get("/vehicles/{vin}/maintenance")
def api_maintenance_get(vin: str, current_odometer_km: Optional[float] = None) -> dict[str, Any]:
    return service_bridge.maintenance_checklist(vin, current_odometer_km)


@api_router.post("/vehicles/{vin}/maintenance")
async def api_maintenance_post(vin: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    return service_bridge.record_maintenance(vin, body)


@api_router.get("/vehicles/{vin}/maintenance/due")
def api_maintenance_due(vin: str, current_odometer_km: Optional[float] = None) -> dict[str, Any]:
    return service_bridge.maintenance_due(vin, current_odometer_km)


@api_router.get("/vehicles/{vin}/torque")
def api_torque_search(vin: str, q: str = "", category: str = "") -> dict[str, Any]:
    # vin is accepted (and ignored beyond validation) for a consistent
    # per-vehicle URL shape, matching the other /api/vehicles/{vin}/* routes
    # -- the torque library itself is not vehicle-specific data.
    return service_bridge.search_torques(q=q, category=category)


__all__ = ["router", "api_router", "templates", "TEMPLATE_DIR"]
