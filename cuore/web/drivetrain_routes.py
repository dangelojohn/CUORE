"""Drivetrain pages (transmission / transfer case / differentials /
driveline / mounts) and the service hub.

Same posture as ``cuore.web.service_routes``: every page and JSON endpoint
here calls :mod:`cuore.services.service_bridge`, never ``mes`` directly, so
the HTML and JSON surfaces cannot drift apart. Page-rendering plumbing
(``_dossier``, ``_vehicle_bar``, ``_page``, ``_set_active_vehicle``,
``_current_odometer``, the shared ``templates`` instance) is reused from
``cuore.web.service_routes`` by import rather than re-duplicated a third
time -- that module already duplicated it once (deliberately, from
``cuore.web.routes``) with a documented reason; a third independent copy
would just be more places for the three to disagree.

Page set:

===================================  ========================================
``/v/{vin}/service-hub``             one card per service area, verdict-first
``/v/{vin}/drivetrain/{section}``    one page per drivetrain section
===================================  ========================================

Not registered on the app here -- see ``cuore/app.py`` for the two lines
that wire this router (and ``service_routes``'s) in.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..services import service_bridge
from ..services.errors import BridgeError
from ..api.deps import require_token
from .service_routes import (
    _current_odometer,
    _dossier,
    _page,
    _set_active_vehicle,
    _vehicle_bar,
    templates,  # noqa: F401 -- re-exported for anything that imports it from here
)

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])
api_router = APIRouter(tags=["service"], dependencies=[Depends(require_token)])

#: display labels -- presentation only, kept out of the mes data modules.
SECTION_LABELS: dict[str, str] = {
    "transmission": "Transmission (ZF 8HP)",
    "transfer_case": "Transfer case (Q4)",
    "differentials": "Differentials",
    "driveline": "Driveline",
    "mounts": "Mounts",
}

SECTION_ORDER = ("transmission", "transfer_case", "differentials", "driveline", "mounts")


# --- drivetrain section page --------------------------------------------------


def _pick_job(jobs: dict[str, Any], requested: str) -> str:
    requested = (requested or "").strip()
    if requested in jobs:
        return requested
    return next(iter(jobs), "")


@router.get("/v/{vin}/drivetrain/{section}", response_class=HTMLResponse)
def drivetrain_section_form(request: Request, vin: str, section: str,
                            job: str = "") -> HTMLResponse:
    """``job`` (query string) picks which job's torque checklist loads below
    the specs -- a plain GET resubmit, same mechanism as the general service
    page's category picker, so this needs no JavaScript beyond the
    auto-submitting ``<select>``."""
    dossier = _dossier(vin)
    checklist = service_bridge.drivetrain_section_checklist(vin, section)
    jobs = checklist.get("jobs", {})
    job = _pick_job(jobs, job)
    torque_rows = service_bridge.drivetrain_job_torque_checklist(section, job) if job else []
    steps = jobs.get(job, [])
    live_temp = (service_bridge.latest_gearbox_oil_temp_observation(vin)
                if section == "transmission" else None)
    response = _page(request, "drivetrain_section.html", vin=vin,
                     bar=_vehicle_bar(vin, dossier), tab="service-hub",
                     section=section, section_label=SECTION_LABELS.get(section, section),
                     checklist=checklist, jobs=jobs, job=job, steps=steps,
                     torque_rows=torque_rows, live_temp=live_temp,
                     current_odometer=_current_odometer(dossier), error=None, saved=False)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/drivetrain/{section}", response_class=HTMLResponse)
async def drivetrain_section_submit(request: Request, vin: str, section: str) -> HTMLResponse:
    form = await request.form()

    def field(name: str) -> str:
        return str(form.get(name, "")).strip()

    job = field("job")
    checklist = service_bridge.drivetrain_section_checklist(vin, section)
    jobs = checklist.get("jobs", {})
    torque_keys = ([t["key"] for t in service_bridge.drivetrain_job_torque_checklist(section, job)]
                  if job in jobs else [])
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
        "section": section,
        "job": job,
        "date": field("date"),
        "odometer_km": field("odometer_km"),
        "technician": field("technician"),
        "fluid": {"brand": field("fluid_brand"), "spec": field("fluid_spec"),
                 "part_no": field("fluid_part_no")},
        "quantity_drained_l": field("quantity_drained_l"),
        "quantity_added_l": field("quantity_added_l"),
        "fluid_condition": {"color": field("fluid_color"), "smell": field("fluid_smell"),
                           "debris_metal_on_magnet": form.get("fluid_debris_metal") == "on"},
        "fluid_temp_c": field("fluid_temp_c"),
        "adaptation_relearn": {"done": form.get("adaptation_done") == "on",
                               "tool": field("adaptation_tool")},
        "parts_replaced": parts,
        "torques_applied": torques_applied,
        "leaks_found": field("leaks_found"),
        "discoveries": field("discoveries"),
        "considerations_next": field("considerations_next"),
    }

    error = None
    saved = False
    try:
        service_bridge.record_drivetrain(vin, data)
        saved = True
    except BridgeError as exc:
        error = str(exc)

    dossier = _dossier(vin)
    checklist = service_bridge.drivetrain_section_checklist(vin, section)
    jobs = checklist.get("jobs", {})
    job = _pick_job(jobs, job)
    torque_rows = service_bridge.drivetrain_job_torque_checklist(section, job) if job else []
    steps = jobs.get(job, [])
    live_temp = (service_bridge.latest_gearbox_oil_temp_observation(vin)
                if section == "transmission" else None)
    response = _page(request, "drivetrain_section.html", vin=vin,
                     bar=_vehicle_bar(vin, dossier), tab="service-hub",
                     section=section, section_label=SECTION_LABELS.get(section, section),
                     checklist=checklist, jobs=jobs, job=job, steps=steps,
                     torque_rows=torque_rows, live_temp=live_temp,
                     current_odometer=_current_odometer(dossier), error=error, saved=saved)
    _set_active_vehicle(response, vin)
    return response


# --- service hub ---------------------------------------------------------------


def _hub_cards(vin: str, hub: dict[str, Any]) -> list[dict[str, Any]]:
    """The eleven hub cards, in the required order, each with its links, last
    service, and open flags -- pure presentation over ``hub`` (from
    :func:`service_bridge.service_hub`), no new business logic.
    """
    def last_summary(entry: Any) -> dict[str, Any] | None:
        if not entry:
            return None
        d = entry.get("data", {}) or {}
        return {"date": d.get("date"), "odometer_km": d.get("odometer_km")}

    oil = hub["oil_service"]
    oil_last = oil["last_oil_change"] or oil["last_service"]
    nd = oil.get("next_oil_due") or {}

    maint = hub["maintenance"]
    due_items = (maint.get("due") or {}).get("items") or []
    top_due = sorted(
        (i for i in due_items if i["status"] in ("overdue", "due_soon")),
        key=lambda i: (i["status"] != "overdue"))[:4]
    maint_counts = []
    if maint.get("overdue_count"):
        maint_counts.append(f"{maint['overdue_count']} overdue")
    if maint.get("due_soon_count"):
        maint_counts.append(f"{maint['due_soon_count']} due soon")

    cards = [
        {"key": "oil_service", "title": "Engine oil & service",
         "links": [("/v/" + vin + "/oil-change", "Oil change"),
                   ("/v/" + vin + "/service", "General service")],
         "last": last_summary(oil_last), "flags": oil["flags"],
         "mes_events": oil.get("mes_events") or [],
         "next_due": (f"{nd['next_due_odometer_km']:,.0f} km" if nd.get("known")
                     and nd.get("next_due_odometer_km") else
                     (nd.get("next_due_date") if nd.get("known") else None))},
        {"key": "maintenance", "title": "Routine maintenance",
         "links": [("/v/" + vin + "/maintenance", "Routine maintenance")],
         "last": last_summary(maint["last"]), "flags": maint["flags"],
         "next_due": (", ".join(maint_counts) if maint_counts else None),
         "top_due": [f"{i['label']} ({i['status'].replace('_', ' ')})" for i in top_due]},
        {"key": "brakes_tires", "title": "Brakes, wheels & tyres",
         "links": [("/v/" + vin + "/brakes-tires", "Brakes / wheels / tyres")],
         "last": last_summary(hub["brakes_tires"]["last"]),
         "flags": hub["brakes_tires"]["flags"], "next_due": None},
    ]
    for section in SECTION_ORDER:
        sec = hub["drivetrain"][section]
        cards.append({
            "key": section, "title": SECTION_LABELS[section],
            "links": [(f"/v/{vin}/drivetrain/{section}", SECTION_LABELS[section])],
            "last": last_summary(sec["last"]), "flags": sec["flags"], "next_due": None,
        })
    cards.append({"key": "evap", "title": "EVAP & emissions",
                  "links": [("/v/" + vin + "/tree", "Fault tree"),
                            ("/v/" + vin + "/dashboard", "Dashboard")],
                  "last": None, "flags": [], "next_due": None,
                  "note": "Diagnosis, not a service-record ledger."})
    cards.append({"key": "torque", "title": "Torque library",
                  "links": [("/v/" + vin + "/torque", "Torque library")],
                  "last": None, "flags": [], "next_due": None})
    return cards


@router.get("/v/{vin}/service-hub", response_class=HTMLResponse)
def service_hub_page(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    hub = service_bridge.service_hub(vin)
    cards = _hub_cards(vin, hub)
    response = _page(request, "service_hub.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="service-hub", cards=cards)
    _set_active_vehicle(response, vin)
    return response


# --- JSON API ------------------------------------------------------------------


@api_router.get("/vehicles/{vin}/service-hub")
def api_service_hub(vin: str) -> dict[str, Any]:
    return service_bridge.service_hub(vin)


@api_router.get("/vehicles/{vin}/drivetrain/{section}")
def api_drivetrain_get(vin: str, section: str) -> dict[str, Any]:
    return service_bridge.drivetrain_section_checklist(vin, section)


@api_router.post("/vehicles/{vin}/drivetrain/{section}")
async def api_drivetrain_post(vin: str, section: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    body = dict(body or {})
    body["section"] = section
    return service_bridge.record_drivetrain(vin, body)


__all__ = ["router", "api_router", "SECTION_LABELS", "SECTION_ORDER"]
