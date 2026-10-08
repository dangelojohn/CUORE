"""``GET /v/{vin}/electrical``: the car-layout electrical diagram, and
``_electrical_path.html``'s data for one code's path (included from
``code.html`` and ``report.html``).

Same posture as :mod:`cuore.web.timeline_routes` (built the same way,
concurrently with other agents): a separate router, reusing
``_dossier``/``_vehicle_bar``/``_page``/``_set_active_vehicle`` from
:mod:`cuore.web.routes` by import rather than duplicating that plumbing, and
registering its template-facing helpers as Jinja globals on the *shared*
``cuore.web.routes`` template environment -- the same one ``code.html`` and
``report.html`` already render through (``report_routes.py`` calls
``web_routes._page``), so nothing there needs a route change to pick this up.

The data contract lives in ``cuore.services.layout_bridge`` (itself merging
``cuore.services.electrical_bridge`` -- electrical only -- with
``mes.layout_systems`` -- every system, built in parallel by another agent
and not necessarily present yet):

    elements(system=None) -> {id: {kind, label, system, location: {zone,
                   description, source, confidence}, feeds,
                   part_of_systems, tsb_refs, inspection_hint, notes}}
    code_path(code) -> {code, path: [{id, role, kind, label, location,
                   source, confidence}], systems_interaction: [{system,
                   how, confidence, source}], inspect_steps: [{element,
                   what, how, source}]}
    systems() -> [(key, label), ...] -- the filter chip row, "all" first
    inspections(vin) / latest(vin, element) -> {at, by, condition, note,
                   media_ids}
    add_inspection(vin, element, by, condition, note)

``inspections``/``latest``/``add_inspection`` stay on ``electrical_bridge``
directly (inspections are vehicle+element records, not a layout concern).
Every call into either bridge is wrapped and falls back to the fixtures
below (built to the exact shape the contract specifies, tagged with a
``system`` the same way ``layout_bridge.canonical_system`` would, and to an
in-memory inspection store for the write path) so this page, and the two
included partials, are developable and testable before ``mes.layout_systems``
lands. Once it exists, nothing here needs to change -- the lazy import just
starts succeeding.

Not registered on the app here -- ``app.py`` is owned by another agent. The
two lines needed there:

    ``from .web import electrical_routes``
    ``app.include_router(electrical_routes.router)``

(next to the other ``web`` router imports/includes.)
"""

from __future__ import annotations

import itertools
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..services.errors import BridgeError
from ..api.deps import require_token
from . import electrical_svg
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

CONDITIONS = ["ok", "loose", "chafed", "corroded", "water", "not_found"]
CONDITION_LABELS = {"ok": "OK", "loose": "Loose", "chafed": "Chafed",
                    "corroded": "Corroded", "water": "Water intrusion",
                    "not_found": "Not found"}


# --- fixture: the exact shape cuore.services.electrical_bridge will return,
# used until that module lands (or for any vehicle/code it does not cover).
# ---------------------------------------------------------------------------

def _fixture_elements() -> dict[str, dict[str, Any]]:
    def loc(zone: str, description: str, source: str = "wiring diagram",
           confidence: str = "medium") -> dict[str, Any]:
        return {"zone": zone, "description": description, "source": source,
                "confidence": confidence}

    return {
        "battery": {"kind": "component", "label": "Battery",
                    "location": loc("engine_bay", "passenger-side engine bay",
                                    "owner's manual", "high"),
                    "feeds": ["fuse_f23"], "part_of_systems": ["charging"],
                    "tsb_refs": [], "inspection_hint": "check terminal tightness and corrosion",
                    "notes": None},
        "fuse_f23": {"kind": "fuse", "label": "Fuse F23 (15A)",
                     "location": loc("engine_bay", "engine-bay fuse box, position F23",
                                     "wiring diagram", "high"),
                     "feeds": ["conn_c1_pcm"], "part_of_systems": ["EVAP"],
                     "tsb_refs": ["18-030-17"],
                     "inspection_hint": "check for corrosion at the fuse box lid gasket",
                     "notes": "shared circuit with the canister vent valve"},
        "conn_c1_pcm": {"kind": "connector", "label": "PCM connector C1",
                        "location": loc("engine_bay", "driver side of the PCM, under the intake",
                                        "wiring diagram", "high"),
                        "feeds": ["purge_valve"], "part_of_systems": ["EVAP", "engine_management"],
                        "tsb_refs": [], "inspection_hint": "look for bent pins and a seated locking tab",
                        "notes": None},
        "purge_valve": {"kind": "component", "label": "Evaporative purge valve",
                        "location": loc("engine_bay", "top of the intake manifold, driver side",
                                        "service manual S2125000002", "high"),
                        "feeds": ["ground_g101"], "part_of_systems": ["EVAP"],
                        "tsb_refs": ["18-030-17"],
                        "inspection_hint": "actuate KOEO and listen/feel for a click",
                        "notes": "frequently actuated with the engine running by mistake, "
                                 "which always fails"},
        "ground_g101": {"kind": "ground", "label": "Ground G101",
                        "location": loc("engine_bay", "engine block, behind the alternator",
                                        "wiring diagram", "medium"),
                        "feeds": [], "part_of_systems": ["EVAP", "engine_management", "charging"],
                        "tsb_refs": [],
                        "inspection_hint": "check for a loose bolt or surface corrosion under the ring terminal",
                        "notes": None},
        "canister_vent_valve": {"kind": "component", "label": "EVAP canister vent valve",
                                "location": loc("underbody", "near the fuel tank, forward of the rear axle",
                                                "service manual", "medium"),
                                "feeds": ["ground_g301"], "part_of_systems": ["EVAP"],
                                "tsb_refs": ["18-030-17"],
                                "inspection_hint": "check the vent line for mud/debris blocking it",
                                "notes": None},
        "fuel_tank_pressure_sensor": {"kind": "sensor", "label": "Fuel tank pressure sensor",
                                      "location": loc("underbody", "top of the fuel tank",
                                                      "service manual", "medium"),
                                      "feeds": [], "part_of_systems": ["EVAP"], "tsb_refs": [],
                                      "inspection_hint": "inspect connector for water intrusion after a car wash",
                                      "notes": None},
        "ground_g301": {"kind": "ground", "label": "Ground G301",
                        "location": loc("underbody", "frame rail near the fuel tank strap",
                                        "wiring diagram", "low"),
                        "feeds": [], "part_of_systems": ["EVAP", "body"], "tsb_refs": [],
                        "inspection_hint": "check for rust under the ring terminal", "notes": None},
        "obd_connector": {"kind": "connector", "label": "OBD-II connector",
                          "location": loc("dash", "under the steering column", "service manual", "high"),
                          "feeds": ["bcm"], "part_of_systems": ["network"], "tsb_refs": [],
                          "inspection_hint": "check pin 4/5 ground pins for looseness", "notes": None},
        "cluster": {"kind": "module", "label": "Instrument cluster",
                   "location": loc("dash", "behind the dash, driver side", "service manual", "high"),
                   "feeds": [], "part_of_systems": ["network", "body"], "tsb_refs": [],
                   "inspection_hint": "check the two main harness connectors behind the cluster",
                   "notes": None},
        "bcm": {"kind": "module", "label": "Body Control Module",
               "location": loc("cabin_driver", "under the driver-side dash, above the kick panel",
                               "wiring diagram", "high"),
               "feeds": ["trunk_module"], "part_of_systems": ["body", "network"], "tsb_refs": [],
               "inspection_hint": "check the connector lock and nearby ground strap", "notes": None},
        "trunk_module": {"kind": "module", "label": "Rear/trunk control module",
                         "location": loc("trunk", "driver side of the trunk, behind the liner",
                                         "wiring diagram", "medium"),
                         "feeds": ["ground_g301"], "part_of_systems": ["body", "network"], "tsb_refs": [],
                         "inspection_hint": "check the harness grommet where it passes through the body",
                         "notes": None},
        "wheel_speed_fl": {"kind": "sensor", "label": "Wheel speed sensor FL",
                           "location": loc("wheel_fl", "front-left hub carrier", "service manual", "high"),
                           "feeds": [], "part_of_systems": ["chassis"], "tsb_refs": [],
                           "inspection_hint": "check the connector and harness for chafing against the strut",
                           "notes": None},
        "wheel_speed_fr": {"kind": "sensor", "label": "Wheel speed sensor FR",
                           "location": loc("wheel_fr", "front-right hub carrier", "service manual", "high"),
                           "feeds": [], "part_of_systems": ["chassis"], "tsb_refs": [],
                           "inspection_hint": "check the connector and harness for chafing against the strut",
                           "notes": None},
        "wheel_speed_rl": {"kind": "sensor", "label": "Wheel speed sensor RL",
                           "location": loc("wheel_rl", "rear-left hub carrier", "service manual", "high"),
                           "feeds": [], "part_of_systems": ["chassis"], "tsb_refs": [],
                           "inspection_hint": "check the connector and harness for chafing near the trailing arm",
                           "notes": None},
        "wheel_speed_rr": {"kind": "sensor", "label": "Wheel speed sensor RR",
                           "location": loc("wheel_rr", "rear-right hub carrier", "service manual", "high"),
                           "feeds": [], "part_of_systems": ["chassis"], "tsb_refs": [],
                           "inspection_hint": "check the connector and harness for chafing near the trailing arm",
                           "notes": None},
        # --- fuel / air-boost: covers the ?system=fuel, ?system=air_boost
        # chips and the P0171 (lean fuel trim) path below before real
        # mes.layout_systems data lands.
        "map_sensor": {"kind": "sensor", "label": "MAP sensor",
                       "location": loc("engine_bay", "top of the intake manifold",
                                       "service manual", "medium"),
                       "feeds": [], "part_of_systems": ["air_intake_boost"], "tsb_refs": [],
                       "inspection_hint": "check the vacuum port and connector for cracking/oil fouling",
                       "notes": None},
        "intake_boost_hose": {"kind": "component", "label": "Intake/boost hose",
                              "location": loc("engine_bay", "turbo-to-intercooler charge pipe",
                                              "service manual", "low"),
                              "feeds": [], "part_of_systems": ["air_intake_boost"], "tsb_refs": [],
                              "inspection_hint": "check clamps and hose wall for a boost leak",
                              "notes": None},
        "fuel_pump": {"kind": "component", "label": "Fuel pump",
                      "location": loc("underbody", "inside the fuel tank",
                                      "service manual", "medium"),
                      "feeds": ["fuel_injector"], "part_of_systems": ["fuel"], "tsb_refs": [],
                      "inspection_hint": "check delivery pressure against spec",
                      "notes": None},
        "fuel_injector": {"kind": "component", "label": "Fuel injector",
                          "location": loc("engine_bay", "fuel rail, cylinder bank",
                                          "service manual", "medium"),
                          "feeds": [], "part_of_systems": ["fuel"], "tsb_refs": [],
                          "inspection_hint": "check injector connector and look for a lean-running misfire pattern",
                          "notes": None},
    }


def _fixture_code_path(code: str) -> dict[str, Any]:
    els = _fixture_elements()

    def hop(eid: str, role: str) -> dict[str, Any]:
        e = els[eid]
        return {"id": eid, "role": role, "kind": e["kind"], "label": e["label"],
               "location": e["location"], "source": e["location"]["source"],
               "confidence": e["location"]["confidence"]}

    code = (code or "").upper()
    if code in ("P0440", "P0455", "P0456"):
        return {
            "code": code,
            "path": [hop("fuse_f23", "fuse"), hop("conn_c1_pcm", "connector"),
                     hop("purge_valve", "component"), hop("ground_g101", "ground")],
            "systems_interaction": [
                {"system": "EVAP", "how": "the purge valve meters vapour flow to the intake; "
                 "stuck open or closed, it sets P0440/P0455/P0456", "confidence": "high",
                 "source": "service manual S2125000002"},
                {"system": "engine_management", "how": "the PCM commands the valve and reads the "
                 "fuel tank pressure sensor to run the EVAP monitor", "confidence": "medium",
                 "source": "wiring diagram"},
            ],
            "inspect_steps": [
                {"element": "fuse_f23", "what": "fuse condition",
                 "how": "pull and visually inspect the element; check for corrosion at the socket",
                 "source": "wiring diagram"},
                {"element": "conn_c1_pcm", "what": "connector pins",
                 "how": "unplug and check for bent/pushed-back pins and a seated lock",
                 "source": "wiring diagram"},
                {"element": "purge_valve", "what": "valve operation",
                 "how": "actuate KOEO (never with the engine running) and confirm it clicks",
                 "source": "service manual S2125000002"},
                {"element": "ground_g101", "what": "ground integrity",
                 "how": "check bolt torque and clean the ring terminal contact surface",
                 "source": "wiring diagram"},
            ],
        }
    if code in ("P0171", "P0172"):
        return {
            "code": code,
            "path": [hop("map_sensor", "sensor"), hop("intake_boost_hose", "line"),
                     hop("fuel_pump", "component"), hop("fuel_injector", "component")],
            "systems_interaction": [
                {"system": "air_intake_boost", "how": "an unmetered intake/boost leak admits extra "
                 "air the MAP sensor cannot account for, reading as a lean trim", "confidence": "medium",
                 "source": "fixture"},
                {"system": "fuel", "how": "a weak fuel pump or a dirty injector under-delivers fuel "
                 "for the air the ECM has measured, reading the same way", "confidence": "medium",
                 "source": "fixture"},
            ],
            "inspect_steps": [
                {"element": "map_sensor", "what": "connector and vacuum port",
                 "how": "check for cracking/oil fouling and a seated connector",
                 "source": "fixture"},
                {"element": "intake_boost_hose", "what": "boost leak",
                 "how": "smoke test or soapy water under light boost",
                 "source": "fixture"},
                {"element": "fuel_pump", "what": "delivery pressure",
                 "how": "check fuel pressure against spec at idle and under load",
                 "source": "fixture"},
                {"element": "fuel_injector", "what": "injector condition",
                 "how": "balance test / listen for an uneven click pattern",
                 "source": "fixture"},
            ],
        }
    if code in ("U0100", "U0101"):
        return {
            "code": code,
            "path": [hop("obd_connector", "connector"), hop("bcm", "module"),
                     hop("trunk_module", "module"), hop("ground_g301", "ground")],
            "systems_interaction": [
                {"system": "network", "how": "a lost-communication code against the ECM is read "
                 "through the gateway/BCM path, not a direct wire", "confidence": "medium",
                 "source": "wiring diagram"},
                {"system": "body", "how": "the trunk module shares the same body ground as the "
                 "network backbone", "confidence": "low", "source": "wiring diagram"},
            ],
            "inspect_steps": [
                {"element": "obd_connector", "what": "connector pins",
                 "how": "check pin 4/5 ground pins for looseness", "source": "service manual"},
                {"element": "bcm", "what": "connector lock",
                 "how": "reseat and check the connector lock and nearby ground strap",
                 "source": "wiring diagram"},
                {"element": "trunk_module", "what": "harness grommet",
                 "how": "check the harness grommet where it passes through the body for chafing",
                 "source": "wiring diagram"},
                {"element": "ground_g301", "what": "ground integrity",
                 "how": "check for rust under the ring terminal", "source": "wiring diagram"},
            ],
        }
    return {"code": code, "path": [], "systems_interaction": [], "inspect_steps": []}


_FIXTURE_INSPECTIONS: dict[str, dict[str, list[dict[str, Any]]]] = {}
_id_seq = itertools.count(1)


def _layout_bridge():
    """``cuore.services.layout_bridge``, or ``None`` if it has not landed
    (it ships with this page, so absence here means a packaging problem,
    not the normal "other agent hasn't landed yet" case -- still guarded,
    same posture as every other bridge lookup in this file)."""
    try:
        from ..services import layout_bridge
        return layout_bridge
    except ImportError:
        return None


def _inspections_bridge():
    """``cuore.services.electrical_bridge`` -- inspections stay on it
    directly; they are a vehicle+element record, not a layout concern."""
    try:
        from ..services import electrical_bridge
        return electrical_bridge
    except ImportError:
        return None


def _tag_system(elements: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Tags fixture elements with a canonical ``system`` key the same way
    ``layout_bridge.elements()`` would, so ``?system=`` filtering and the
    SVG's system glyph work identically whether layout_bridge answered or
    this fixture did."""
    layout = _layout_bridge()
    if layout is None:
        return elements
    for eid, e in elements.items():
        e.setdefault("system", layout.canonical_system(e))
    return elements


def _elements(system: str = "") -> dict[str, dict[str, Any]]:
    layout = _layout_bridge()
    if layout is not None:
        try:
            result = layout.elements(system or None)
            if result:
                return result
        except Exception:  # noqa: BLE001 -- a bridge misfire must fall back, not 500
            pass
    fixture = _tag_system(_fixture_elements())
    if system and system != "all":
        fixture = {eid: e for eid, e in fixture.items() if e.get("system") == system}
    return fixture


def _code_path(code: str) -> dict[str, Any]:
    layout = _layout_bridge()
    if layout is not None:
        try:
            result = layout.code_path(code)
            if result and result.get("path"):
                return result
        except Exception:  # noqa: BLE001
            pass
    return _fixture_code_path(code)


def _inspections(vin: str) -> dict[str, list[dict[str, Any]]]:
    bridge = _inspections_bridge()
    if bridge is not None:
        try:
            out: dict[str, list[dict[str, Any]]] = {}
            for rec in bridge.list_inspections(vin):
                out.setdefault(rec.get("element", ""), []).append(rec)
            return out
        except Exception:  # noqa: BLE001
            pass
    return _FIXTURE_INSPECTIONS.get(vin, {})


def _latest(vin: str, element: str) -> Optional[dict[str, Any]]:
    bridge = _inspections_bridge()
    if bridge is not None:
        try:
            rows = bridge.list_inspections(vin, element)
            if rows:
                return rows[-1]
        except Exception:  # noqa: BLE001
            pass
    rows = _FIXTURE_INSPECTIONS.get(vin, {}).get(element, [])
    return rows[-1] if rows else None


def _add_inspection(vin: str, element: str, by: str, condition: str,
                    note: str) -> Optional[str]:
    """Record one inspection. Returns an error string, or ``None`` on
    success -- same shape as ``timeline_routes._save_symptom``."""
    bridge = _inspections_bridge()
    if bridge is not None:
        fn = getattr(bridge, "add_inspection", None)
        if fn is not None:
            try:
                # electrical_bridge.add_inspection's real signature is
                # (vin, element, condition, by=, note=) -- condition
                # third, not by/condition swapped as a positional call
                # would silently do.
                fn(vin, element, condition, by=by, note=note)
                return None
            except BridgeError as exc:
                return str(exc)
            except Exception:  # noqa: BLE001 -- fall back to the fixture, never 500
                pass
    at = datetime.now().isoformat(timespec="seconds")
    record = {"at": at, "by": by, "condition": condition, "note": note,
             "media_ids": [], "id": f"insp{next(_id_seq)}"}
    _FIXTURE_INSPECTIONS.setdefault(vin, {}).setdefault(element, []).append(record)
    return None


# --- Jinja globals for _electrical_path.html (code.html / report.html) ----

def electrical_path_for(vin: str, code: str) -> dict[str, Any]:
    """``_electrical_path.html``'s data: one code's path, each hop enriched
    with its latest inspection condition, plus the systems-interaction list
    and a ready-made "open in layout" href. Always returns a dict -- the
    template checks ``found`` rather than needing a guard at every call
    site."""
    cp = _code_path(code)
    path = cp.get("path") or []
    for hop_item in path:
        rec = _latest(vin, hop_item.get("id", ""))
        hop_item["condition"] = rec.get("condition") if rec else None
    return {
        "code": cp.get("code") or (code or "").upper(),
        "path": path,
        "systems_interaction": cp.get("systems_interaction") or [],
        "inspect_steps": cp.get("inspect_steps") or [],
        "found": bool(path),
        "layout_href": f"/v/{vin}/electrical?code={quote((code or '').upper())}",
    }


_shared_templates.env.globals["electrical_path_for"] = electrical_path_for


# --- the page --------------------------------------------------------------


def _element_cards(vin: str, elements: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    zone_order = [z["id"] for z in electrical_svg.ZONES] + ["other"]
    zone_label = {z["id"]: z["label"] for z in electrical_svg.ZONES}
    zone_label["other"] = "Other / unplaced"
    layout = _layout_bridge()
    sys_labels = layout.SYSTEM_LABELS if layout is not None else {}

    cards = []
    for eid, e in elements.items():
        zone = electrical_svg.resolve_zone((e.get("location") or {}).get("zone"))
        rec = _latest(vin, eid)
        cards.append({
            "id": eid, "kind": e.get("kind"), "label": e.get("label") or eid,
            "location": e.get("location") or {}, "zone": zone,
            "zone_label": zone_label.get(zone, zone),
            "system": e.get("system"),
            "system_label": sys_labels.get(e.get("system"), e.get("system")),
            "feeds": e.get("feeds") or [], "part_of_systems": e.get("part_of_systems") or [],
            "tsb_refs": e.get("tsb_refs") or [], "inspection_hint": e.get("inspection_hint"),
            "notes": e.get("notes"), "latest": rec,
        })
    cards.sort(key=lambda c: (zone_order.index(c["zone"]) if c["zone"] in zone_order else 999,
                              c["label"]))
    return cards


@router.get("/v/{vin}/electrical", response_class=HTMLResponse)
def electrical_page(request: Request, vin: str, code: str = "", system: str = "",
                    saved: str = "", error: str = "") -> HTMLResponse:
    """The car-layout electrical diagram: every known element across every
    system, placed in its zone and coloured by its latest inspection
    condition, with ``?system=`` scoping which systems' elements show, and
    ``?code=`` thick-lining that code's full (possibly cross-system) path
    regardless of the system filter -- a path is what it is; the filter
    only scopes browsing."""
    dossier = _dossier(vin)
    layout = _layout_bridge()
    all_systems = layout.CANONICAL_SYSTEMS if layout is not None else [("all", "All")]
    system_colors = layout.SYSTEM_COLORS if layout is not None else {}
    system_keys = {k for k, _ in all_systems}
    system_k = (system or "").strip().lower()
    if system_k not in system_keys:
        system_k = "all"

    code_u = code.strip().upper()
    path_data = electrical_path_for(vin, code_u) if code_u else None
    path_ids = [h["id"] for h in path_data["path"]] if path_data else []

    # A code's path can span systems (P0171: air intake + fuel) -- the
    # diagram always shows every element when one is active, so the full
    # path is visible no matter which chip is selected; the chip still
    # scopes the element cards underneath it.
    diagram_elements = _elements() if code_u else _elements(system_k)
    cards = _element_cards(vin, _elements(system_k))
    conditions = {eid: ((_latest(vin, eid) or {}).get("condition")) for eid in diagram_elements}

    svg = electrical_svg.render(diagram_elements, conditions=conditions, path_ids=path_ids, width=320)

    systems_filter = [{"key": k, "label": lbl, "active": k == system_k,
                       "color": system_colors.get(k)} for k, lbl in all_systems]

    qs = []
    if code_u:
        qs.append(f"code={quote(code_u)}")
    if system_k != "all":
        qs.append(f"system={quote(system_k)}")
    redirect_to = f"/v/{vin}/electrical" + (f"?{'&'.join(qs)}" if qs else "")

    response = _page(request, "electrical.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="electrical", svg=svg, cards=cards, code=code_u, path_data=path_data,
                     system=system_k, systems_filter=systems_filter,
                     conditions=CONDITIONS, condition_labels=CONDITION_LABELS,
                     saved=bool(saved), inspect_error=error, redirect_to=redirect_to)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/electrical/inspect", response_class=HTMLResponse)
async def electrical_inspect_submit(request: Request, vin: str) -> RedirectResponse:
    """Record one inspection. Plain POST, no JavaScript required -- same
    degrade-first shape as ``/v/{vin}/symptoms`` and ``/v/{vin}/notes``."""
    form = await request.form()
    redirect_base = str(form.get("redirect_to", "") or f"/v/{vin}/electrical")
    if not redirect_base.startswith("/") or redirect_base.startswith("//"):
        redirect_base = f"/v/{vin}/electrical"

    element = str(form.get("element", "")).strip()
    by = str(form.get("by", "")).strip() or "mechanic"
    condition = str(form.get("condition", "")).strip()
    note = str(form.get("note", "")).strip()

    error = None
    if not element:
        error = "no element given"
    elif condition not in CONDITIONS:
        error = f"condition must be one of {', '.join(CONDITIONS)}, got {condition!r}"

    if error is None:
        error = _add_inspection(vin, element, by, condition, note)

    sep = "&" if "?" in redirect_base else "?"
    url = f"{redirect_base}{sep}{'saved=1' if error is None else 'error=' + quote(error)}"
    return RedirectResponse(url=url, status_code=303)


__all__ = ["router", "electrical_path_for", "CONDITIONS", "CONDITION_LABELS"]
