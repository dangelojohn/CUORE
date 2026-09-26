"""Service records: oil changes, general service, and brakes/wheels/tyres.

This is where a technician's own work gets recorded -- distinct from
``mes.dealer`` (what wiTECH said) and ``mes.notes`` (free-text context on
something else). Three kinds share one append-only JSONL store, same state
directory as ``mes.dealer`` and ``mes.notes`` (``CUORE_STATE_DIR``, else
``%PROGRAMDATA%\\cuore``, else ``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``)
-- kept independent of ``cuore`` so ``mes`` never imports it, for the same
reason those two modules are independent of it. The state-dir helper is
duplicated here rather than imported, matching the existing convention in
this package: each store stays a single small file with no cross-module
coupling, so one being mid-edit elsewhere never breaks another.

* ``oil_change``          -- what oil went in, what came out, every torque
                             actually applied, whether the reminder was
                             reset, and what to watch for next time.
* ``service``             -- everything else: brakes, tyres, filters,
                             fluids, parts, labour notes, keyed by a job
                             ``category`` (see ``mes.service_specs``
                             .CATEGORIES).
* ``brakes_wheels_tires``  -- a dedicated corner-by-corner brake/wheel/tyre
                             record (pads, rotors, tyres, TPMS, rotation/
                             balance/alignment, EPB service mode).
* ``drivetrain``           -- transmission / transfer case / differentials /
                             driveline / mounts service, keyed by ``section``
                             (see :mod:`mes.drivetrain_specs`.SECTIONS) and a
                             ``job`` from that section's ``jobs``: fluid
                             used, quantities drained/added, fluid condition,
                             fluid temperature at level check (flagged for
                             transmission if outside the 30-50 C fill
                             window), adaptation-relearn done, parts
                             replaced, and the job's torque checklist.
* ``maintenance``          -- general engine/vehicle routine maintenance
                             (air/cabin/fuel filters, spark plugs, coils,
                             coolant, brake fluid, drive belt, 12V battery,
                             wipers, PCV, throttle body, boost hoses, washer
                             fluid, A/C, EPS, hinge/latch lubrication), keyed
                             by one or more item keys from
                             :mod:`mes.maintenance_specs`.ITEMS. A single
                             record can cover several items in one visit
                             (e.g. air filter + cabin filter + wipers), each
                             with its own action/parts/measurements; the
                             torque checklist is the union of the covered
                             items' ``torque_keys``.

History is a ledger, never rewritten. A record is written once with
``op: "record"``; a correction is a second line with ``op: "amend"`` that
names the original record's ``id`` and carries only the fields being
changed, plus why. :func:`load` folds amendments onto their target (later
amendments override earlier ones, field by field) for display -- the
original line is never edited or deleted, so the full trail stays
auditable.

Every kind that names fasteners carries a ``torque_checklist``: the specs
from :mod:`mes.service_specs` for that job's category (or categories),
joined against whatever the technician actually applied. Each row is
flagged ``missing``, ``invalid``, ``deviating`` (outside the specced value
by more than :data:`TORQUE_TOLERANCE`), or ``unknown_spec`` (the spec
itself is UNKNOWN, so the applied value cannot be checked against
anything) -- the flag exists so that is never silent.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from . import drivetrain_specs, maintenance_specs, service_specs

KINDS = ("oil_change", "service", "brakes_wheels_tires", "drivetrain", "maintenance")
CORNERS = ("FL", "FR", "RL", "RR")

#: what a technician actually did to one maintenance item on a visit.
MAINTENANCE_ACTIONS = ("replaced", "inspected_ok", "inspected_needs_attention",
                       "topped_up", "flushed", "tested")

#: actions after which an item's ``post_service`` steps (a reset, a bleed, a
#: relearn) actually need doing -- a plain inspection has nothing to reset.
MAINTENANCE_POST_SERVICE_ACTIONS = ("replaced", "topped_up", "flushed")

#: "due soon" window for :func:`maintenance_due` -- within this many km or
#: this many days of the computed next-due point, an item that isn't yet
#: overdue is still called out rather than silently marked "ok".
MAINTENANCE_DUE_SOON_KM = 1500
MAINTENANCE_DUE_SOON_DAYS = 30

#: the five self-contained drivetrain areas a ``drivetrain`` record can name
#: (mirrors :data:`mes.drivetrain_specs.SECTIONS`'s keys).
DRIVETRAIN_SECTIONS = ("transmission", "transfer_case", "differentials",
                       "driveline", "mounts")

#: ZF 8HP fill/level-check temperature window, degrees C (FCA/ZF service
#: info, see ``docs/reference/ZF8HP_SERVICE_DATA.md``) -- a transmission
#: fluid-temperature reading outside this band at the level check is flagged.
TRANSMISSION_FILL_TEMP_MIN_C = 30
TRANSMISSION_FILL_TEMP_MAX_C = 50

#: +/- band around a numeric torque spec that still counts as "applied
#: correctly". A generous shop-floor tolerance for wrench/gauge variance,
#: not a precision-engineering figure -- the flag exists to catch a wrong
#: fastener or a typo, not to referee calibration disputes. A spec that
#: itself carries an explicit ``value_range`` (a source-given range, not a
#: guess) uses that range directly instead of this percentage.
TORQUE_TOLERANCE = 0.10

#: legal minimum / advisory tyre tread depth, in mm (2/32in and 4/32in).
TREAD_LEGAL_MM = 1.5875
TREAD_ADVISORY_MM = 3.175

#: tyre pressure deviation, in kPa, past which a flag is raised (~2 psi).
PRESSURE_TOLERANCE_KPA = 14

#: tread-depth spread across one tyre (inside vs outside) past which
#: uneven wear -- often an alignment symptom -- is flagged.
TREAD_UNEVEN_SPREAD_MM = 1.5

_KM_PER_MILE = 1.60934


# --- state dir (mirrors mes.dealer.state_dir exactly) ------------------------


def state_dir() -> Path:
    """Mirror ``mes.dealer.state_dir()``: same candidates, first writable wins."""
    override = os.environ.get("CUORE_STATE_DIR")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    if os.environ.get("PROGRAMDATA"):
        candidates.append(Path(os.environ["PROGRAMDATA"], "cuore"))
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"], "cuore"))
    candidates.append(Path.home() / ".cuore")
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write-test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return d
        except OSError:
            continue
    return Path.cwd()


def store_path() -> Path:
    return state_dir() / "service_records.jsonl"


# --- small coercion helpers ---------------------------------------------------


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _req_num(data: dict[str, Any], key: str, label: str) -> float:
    v = _num(data.get(key))
    if v is None:
        raise ValueError(f"{label} needs a numeric {key}")
    return v


def _req_str(data: dict[str, Any], key: str, label: str) -> str:
    v = str(data.get(key, "")).strip()
    if not v:
        raise ValueError(f"{label} needs {key}")
    return v


def _as_list_str(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.splitlines() if s.strip()]
    if isinstance(v, (list, tuple)):
        return [str(s).strip() for s in v if str(s).strip()]
    return [str(v).strip()]


def _as_parts(v: Any) -> list[dict[str, Any]]:
    if not isinstance(v, list):
        return []
    out = []
    for p in v:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        out.append({"name": name, "part_no": str(p.get("part_no", "")).strip(),
                    "qty": _num(p.get("qty")) or 1})
    return out


# --- torque checklist ---------------------------------------------------------


def _spec_range(spec: dict[str, Any]) -> Optional[tuple[float, float]]:
    if spec.get("value_range"):
        lo, hi = spec["value_range"]
        return (float(lo), float(hi))
    val = spec.get("value")
    if val is None or not isinstance(val, (int, float)):
        return None
    return (val * (1 - TORQUE_TOLERANCE), val * (1 + TORQUE_TOLERANCE))


def build_torque_checklist(categories: Any) -> list[dict[str, Any]]:
    """The spec rows a job needs, before anything has been applied.

    ``categories`` is a single category string or an iterable of them (a
    brakes/wheels/tyres job spans several categories at once).
    """
    return service_specs.checklist_for(categories)


def _join_checklist_rows(specs: list[dict[str, Any]],
                         applied: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Join a list of torque spec rows against what the technician entered.

    Shared by :func:`apply_torque_checklist` (categories, from
    :mod:`mes.service_specs`) and :func:`apply_drivetrain_torque_checklist`
    (a job's steps, from :mod:`mes.drivetrain_specs`) -- both row shapes
    carry the same ``key``/``component``/``value``/``value_range``/``unit``/
    ``confidence`` fields, so one join implementation covers both.

    ``applied`` maps a torque row's ``key`` to the raw value entered on the
    form (string or number). Returns ``{"rows": [...], "flags": [...]}``;
    every row keeps its spec fields plus ``applied`` and ``flag`` (``None``
    when nothing is wrong).
    """
    applied = applied or {}
    rows: list[dict[str, Any]] = []
    flags: list[str] = []
    for spec in specs:
        key = spec["key"]
        raw = applied.get(key)
        row = dict(spec)
        row["applied"] = None
        row["flag"] = None
        if raw is None or str(raw).strip() == "":
            row["flag"] = "missing"
            flags.append(f"{spec['component']}: no torque value recorded")
        else:
            val = _num(raw)
            if val is None:
                row["flag"] = "invalid"
                flags.append(f"{spec['component']}: '{raw}' is not a number")
            else:
                row["applied"] = val
                if spec.get("confidence") == service_specs.UNKNOWN or spec.get("value") is None:
                    row["flag"] = "unknown_spec"
                    flags.append(
                        f"{spec['component']}: torque applied ({val} "
                        f"{spec.get('unit') or ''}) against an UNKNOWN spec "
                        "-- verify with the service manual (TechAuthority)")
                else:
                    rng = _spec_range(spec)
                    if rng and not (rng[0] <= val <= rng[1]):
                        row["flag"] = "deviating"
                        flags.append(
                            f"{spec['component']}: applied {val} "
                            f"{spec['unit']} is outside spec {spec['value']} "
                            f"{spec['unit']} ({rng[0]:.1f}-{rng[1]:.1f})")
        rows.append(row)
    return {"rows": rows, "flags": flags}


def apply_torque_checklist(categories: Any,
                           applied: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Join a job's spec checklist (by ``service_specs`` category/ies)
    against what the technician entered. See :func:`_join_checklist_rows`."""
    return _join_checklist_rows(build_torque_checklist(categories), applied)


# --- torque checklist: drivetrain (mes.drivetrain_specs) -----------------


def build_drivetrain_torque_checklist(section: str, job: str) -> list[dict[str, Any]]:
    """The torque spec rows a drivetrain job needs, in step order,
    de-duplicated -- one row per distinct ``torque_ref`` named by the job's
    steps in :data:`mes.drivetrain_specs.SECTIONS`.
    """
    section = (section or "").strip()
    job = (job or "").strip()
    jobs = (drivetrain_specs.SECTIONS.get(section) or {}).get("jobs") or {}
    steps = jobs.get(job) or []
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for step in steps:
        ref = step.get("torque_ref")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        spec = drivetrain_specs.torque_by_key(ref)
        if spec:
            rows.append(spec)
    return rows


def apply_drivetrain_torque_checklist(section: str, job: str,
                                      applied: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Join a drivetrain job's torque checklist against what the technician
    entered. See :func:`_join_checklist_rows`."""
    return _join_checklist_rows(build_drivetrain_torque_checklist(section, job), applied)


# --- torque checklist: maintenance (mes.maintenance_specs) -------------------


def build_maintenance_torque_checklist(item_keys: Any) -> list[dict[str, Any]]:
    """The torque spec rows for one or more maintenance items, de-duplicated
    -- one row per distinct ``torque_ref`` named by
    :data:`mes.maintenance_specs.ITEMS`'s ``torque_keys``.

    ``item_keys`` is a single item-key string or an iterable of them.
    Reads ``maintenance_specs.ITEMS`` directly (not the ``item()`` helper,
    which raises on an unknown key) so an unrecognised key is simply
    skipped here -- callers that need to *reject* an unknown key do that in
    :func:`_clean_maintenance_item` before this ever runs.
    """
    if isinstance(item_keys, str):
        item_keys = [item_keys]
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for key in item_keys or []:
        spec = maintenance_specs.ITEMS.get(key)
        if not spec:
            continue
        for ref in spec.get("torque_keys") or []:
            if ref in seen:
                continue
            seen.add(ref)
            row = service_specs.torque_by_key(ref)
            if row:
                rows.append(row)
    return rows


def apply_maintenance_torque_checklist(item_keys: Any,
                                       applied: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Join the torque checklist for a set of maintenance items against what
    the technician entered. See :func:`_join_checklist_rows`."""
    return _join_checklist_rows(build_maintenance_torque_checklist(item_keys), applied)


# --- validation: oil_change ---------------------------------------------------


def _validate_oil_change(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    date_s = _req_str(data, "date", "oil_change")
    odometer_km = _req_num(data, "odometer_km", "oil_change")

    oil = data.get("oil") or {}
    if not isinstance(oil, dict):
        raise ValueError("oil_change.oil must be an object")
    brand = _req_str(oil, "brand", "oil_change.oil")
    viscosity = _req_str(oil, "viscosity", "oil_change.oil")
    product = str(oil.get("product", "")).strip()
    spec_used = str(oil.get("spec", "")).strip()

    quantity_added_l = _req_num(data, "quantity_added_l", "oil_change")

    drained = data.get("drained") or {}
    if not isinstance(drained, dict):
        raise ValueError("oil_change.drained must be an object")
    drained_clean = {
        "color": str(drained.get("color", drained.get("colour", ""))).strip(),
        "smell": str(drained.get("smell", "")).strip(),
        "metal": bool(drained.get("metal", False)),
        "fuel_dilution_suspected": bool(drained.get("fuel_dilution_suspected", False)),
        "coolant_suspected": bool(drained.get("coolant_suspected", False)),
        "condition_notes": str(drained.get("condition_notes", "")).strip(),
    }

    filt = data.get("filter") or {}
    if not isinstance(filt, dict):
        raise ValueError("oil_change.filter must be an object")
    filter_part_no = _req_str(filt, "part_no", "oil_change.filter")
    filter_brand = str(filt.get("brand", "")).strip()

    reset = data.get("reset") or {}
    reset_clean = {"done": bool(reset.get("done", False)),
                    "method": str(reset.get("method", "")).strip()}

    technician = _req_str(data, "technician", "oil_change")

    checklist = apply_torque_checklist("oil_change", data.get("torques_applied"))

    return {
        "date": date_s,
        "odometer_km": odometer_km,
        "oil": {"brand": brand, "product": product, "viscosity": viscosity,
                "spec": spec_used},
        "quantity_added_l": quantity_added_l,
        "drained": drained_clean,
        "filter": {"brand": filter_brand, "part_no": filter_part_no},
        "drain_plug_washer_replaced": bool(data.get("drain_plug_washer_replaced", False)),
        "torque_checklist": checklist,
        "reset": reset_clean,
        "sample_taken": bool(data.get("sample_taken", False)),
        "leaks_found": str(data.get("leaks_found", "")).strip(),
        "discoveries": _as_list_str(data.get("discoveries")),
        "considerations_next": _as_list_str(data.get("considerations_next")),
        "next_due_override": {
            "odometer_km": _num((data.get("next_due_override") or {}).get("odometer_km")),
            "date": str((data.get("next_due_override") or {}).get("date", "")).strip(),
        },
        "technician": technician,
        "attachments": _as_list_str(data.get("attachments")),
    }


# --- validation: service ------------------------------------------------------


def _validate_service(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    date_s = _req_str(data, "date", "service")
    odometer_km = _req_num(data, "odometer_km", "service")
    category = _req_str(data, "category", "service").strip().lower()
    if category not in service_specs.CATEGORIES:
        raise ValueError("service.category must be one of: "
                         + ", ".join(service_specs.CATEGORIES))
    work_done = _req_str(data, "work_done", "service")
    technician = _req_str(data, "technician", "service")

    checklist = apply_torque_checklist(category, data.get("torques_applied"))

    return {
        "date": date_s,
        "odometer_km": odometer_km,
        "category": category,
        "work_done": work_done,
        "parts": _as_parts(data.get("parts")),
        "fluids": _as_list_str(data.get("fluids")),
        "torque_checklist": checklist,
        "discoveries": _as_list_str(data.get("discoveries")),
        "considerations_next": _as_list_str(data.get("considerations_next")),
        "technician": technician,
    }


# --- validation: brakes_wheels_tires -----------------------------------------


def _clean_corner(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    pad = raw.get("pad_thickness_mm") or {}
    tyre = raw.get("tyre") or {}
    tread = raw.get("tread_depth_mm") or {}
    tpms = raw.get("tpms") or {}
    tread_out = {"inside": _num(tread.get("inside")),
                 "middle": _num(tread.get("middle")),
                 "outside": _num(tread.get("outside"))}
    return {
        "pad_thickness_mm": {"inner": _num(pad.get("inner")),
                             "outer": _num(pad.get("outer"))},
        "rotor_thickness_mm": _num(raw.get("rotor_thickness_mm")),
        "rotor_runout_mm": _num(raw.get("rotor_runout_mm")),
        "rotor_condition": str(raw.get("rotor_condition", "")).strip(),
        "caliper_condition": str(raw.get("caliper_condition", "")).strip(),
        "slider_condition": str(raw.get("slider_condition", "")).strip(),
        "boot_condition": str(raw.get("boot_condition", "")).strip(),
        "hose_condition": str(raw.get("hose_condition", "")).strip(),
        "tyre": {
            "brand": str(tyre.get("brand", "")).strip(),
            "model": str(tyre.get("model", "")).strip(),
            "size": str(tyre.get("size", "")).strip(),
            "load_speed_index": str(tyre.get("load_speed_index", "")).strip(),
            "dot_date_code": str(tyre.get("dot_date_code", "")).strip(),
        },
        "tread_depth_mm": tread_out,
        "tread_depth_32nds": {
            k: (round(v / 0.79375, 1) if v is not None else None)
            for k, v in tread_out.items()
        },
        "pressure_found_kpa": _num(raw.get("pressure_found_kpa")),
        "pressure_set_kpa": _num(raw.get("pressure_set_kpa")),
        "damage_notes": str(raw.get("damage_notes", "")).strip(),
        "wheel_condition": str(raw.get("wheel_condition", "")).strip(),
        "tpms": {"sensor_id": str(tpms.get("sensor_id", "")).strip(),
                "pressure_kpa": _num(tpms.get("pressure_kpa")),
                "temperature_c": _num(tpms.get("temperature_c"))},
        "lug_torque_applied": _num(raw.get("lug_torque_applied")),
        "parts_replaced": _as_parts(raw.get("parts_replaced")),
    }


def corner_flags(corner: str, clean: dict[str, Any]) -> list[str]:
    """Verdict flags for one corner: below-minimum, tread, pressure, wear.

    Reads :mod:`mes.service_specs`.BRAKE_SPEC; a spec that is itself
    UNKNOWN never suppresses a flag silently -- the flag names the value
    found and says the spec could not be checked.
    """
    out: list[str] = []
    side = "front" if corner in ("FL", "FR") else "rear"
    brake = service_specs.BRAKE_SPEC

    pad_min = (brake.get("pad_min_mm", {}).get(side) or {}).get("value")
    for which in ("inner", "outer"):
        val = clean["pad_thickness_mm"].get(which)
        if val is None:
            continue
        if pad_min is not None and val < pad_min:
            out.append(f"{corner} {which} pad {val:.1f} mm: below {pad_min:.1f} mm minimum")
        elif pad_min is None:
            out.append(f"{corner} {which} pad {val:.1f} mm recorded -- no sourced "
                       "minimum to check it against (UNKNOWN spec)")

    rotor_min = (brake.get("rotor_min_mm", {}).get(side) or {}).get("value")
    rotor_val = clean.get("rotor_thickness_mm")
    if rotor_val is not None:
        if rotor_min is not None and rotor_val < rotor_min:
            out.append(f"{corner} rotor {rotor_val:.1f} mm: below {rotor_min:.1f} mm minimum")
        elif rotor_min is None:
            out.append(f"{corner} rotor {rotor_val:.1f} mm recorded -- no sourced "
                       "minimum to check it against (UNKNOWN spec); read the "
                       "cast-in MIN TH marking on the rotor itself")

    tread = clean["tread_depth_mm"]
    tread_vals = [v for v in tread.values() if v is not None]
    if tread_vals:
        worst = min(tread_vals)
        if worst < TREAD_LEGAL_MM:
            out.append(f"{corner} tread {worst:.1f} mm: below legal minimum "
                      f"({TREAD_LEGAL_MM:.2f} mm / 2/32in)")
        elif worst < TREAD_ADVISORY_MM:
            out.append(f"{corner} tread {worst:.1f} mm: below advisory depth "
                      f"({TREAD_ADVISORY_MM:.2f} mm / 4/32in)")
        if tread["inside"] is not None and tread["outside"] is not None:
            spread = abs(tread["inside"] - tread["outside"])
            if spread >= TREAD_UNEVEN_SPREAD_MM:
                out.append(f"{corner} uneven wear: inside/outside tread differs by "
                          f"{spread:.1f} mm -- check alignment")

    pressure_spec = brake.get("tire_pressure_kpa", {}).get(side) or {}
    target = pressure_spec.get("value")
    set_val = clean.get("pressure_set_kpa")
    if target is not None and set_val is not None:
        if abs(set_val - target) > PRESSURE_TOLERANCE_KPA:
            out.append(f"{corner} pressure set {set_val:.0f} kPa deviates from "
                      f"placard target {target:.0f} kPa by more than "
                      f"{PRESSURE_TOLERANCE_KPA} kPa")

    return out


def _validate_brakes_wheels_tires(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    date_s = _req_str(data, "date", "brakes_wheels_tires")
    odometer_km = _req_num(data, "odometer_km", "brakes_wheels_tires")
    technician = _req_str(data, "technician", "brakes_wheels_tires")

    raw_corners = data.get("corners") or {}
    if not isinstance(raw_corners, dict):
        raise ValueError("brakes_wheels_tires.corners must be an object")
    corners_clean = {c: _clean_corner(raw_corners.get(c)) for c in CORNERS}

    fluid = data.get("fluid") or {}
    fluid_clean = {
        "type": str(fluid.get("type", "")).strip(),
        "moisture_test_result": str(fluid.get("moisture_test_result", "")).strip(),
        "boiling_point_c": _num(fluid.get("boiling_point_c")),
        "replaced": bool(fluid.get("replaced", False)),
    }

    rotation = data.get("rotation") or {}
    rotation_clean = {"done": bool(rotation.get("done", False)),
                      "pattern": str(rotation.get("pattern", "")).strip()}

    alignment = data.get("alignment") or {}
    alignment_clean = {
        "done": bool(alignment.get("done", False)),
        "needed": bool(alignment.get("needed", False)),
        "before": alignment.get("before") if isinstance(alignment.get("before"), dict) else {},
        "after": alignment.get("after") if isinstance(alignment.get("after"), dict) else {},
    }

    epb = data.get("epb_service_mode") or {}
    epb_clean = {"used": bool(epb.get("used", False)),
                "tool": str(epb.get("tool", "")).strip()}

    checklist = apply_torque_checklist(
        ["brakes_front", "brakes_rear", "wheels"], data.get("torques_applied"))

    flags: list[str] = []
    for corner in CORNERS:
        flags.extend(corner_flags(corner, corners_clean[corner]))
    if any(corners_clean[c]["lug_torque_applied"] == 0 for c in CORNERS):
        flags.append("a lug torque of 0 was recorded -- treat as not applied")

    return {
        "date": date_s,
        "odometer_km": odometer_km,
        "corners": corners_clean,
        "fluid": fluid_clean,
        "rotation": rotation_clean,
        "balance_done": bool(data.get("balance_done", False)),
        "alignment": alignment_clean,
        "epb_service_mode": epb_clean,
        "torque_checklist": checklist,
        "flags": flags,
        "discoveries": _as_list_str(data.get("discoveries")),
        "considerations_next": _as_list_str(data.get("considerations_next")),
        "technician": technician,
    }


# --- validation: drivetrain ----------------------------------------------


def _validate_drivetrain(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    section = _req_str(data, "section", "drivetrain").strip().lower()
    if section not in DRIVETRAIN_SECTIONS:
        raise ValueError("drivetrain.section must be one of: "
                         + ", ".join(DRIVETRAIN_SECTIONS))
    section_jobs = (drivetrain_specs.SECTIONS.get(section) or {}).get("jobs") or {}
    job = _req_str(data, "job", "drivetrain").strip()
    if job not in section_jobs:
        raise ValueError(f"drivetrain.job must be one of: "
                         + ", ".join(section_jobs) + f" for section {section!r}")
    date_s = _req_str(data, "date", "drivetrain")
    odometer_km = _req_num(data, "odometer_km", "drivetrain")
    technician = _req_str(data, "technician", "drivetrain")

    fluid = data.get("fluid") or {}
    if not isinstance(fluid, dict):
        raise ValueError("drivetrain.fluid must be an object")
    fluid_clean = {"brand": str(fluid.get("brand", "")).strip(),
                   "spec": str(fluid.get("spec", "")).strip(),
                   "part_no": str(fluid.get("part_no", "")).strip()}

    condition = data.get("fluid_condition") or {}
    if not isinstance(condition, dict):
        raise ValueError("drivetrain.fluid_condition must be an object")
    condition_clean = {
        "color": str(condition.get("color", condition.get("colour", ""))).strip(),
        "smell": str(condition.get("smell", "")).strip(),
        "debris_metal_on_magnet": bool(condition.get(
            "debris_metal_on_magnet", condition.get("metal", False))),
    }

    fluid_temp_c = _num(data.get("fluid_temp_c"))
    fill_window_flag = None
    if section == "transmission" and fluid_temp_c is not None:
        if not (TRANSMISSION_FILL_TEMP_MIN_C <= fluid_temp_c <= TRANSMISSION_FILL_TEMP_MAX_C):
            fill_window_flag = (
                f"fluid temperature {fluid_temp_c:.1f} C at the level check is "
                f"outside the {TRANSMISSION_FILL_TEMP_MIN_C}-"
                f"{TRANSMISSION_FILL_TEMP_MAX_C} C fill window")

    adaptation = data.get("adaptation_relearn") or {}
    if not isinstance(adaptation, dict):
        raise ValueError("drivetrain.adaptation_relearn must be an object")
    adaptation_clean = {"done": bool(adaptation.get("done", False)),
                        "tool": str(adaptation.get("tool", "")).strip()}

    checklist = apply_drivetrain_torque_checklist(section, job, data.get("torques_applied"))
    flags = list(checklist["flags"])
    if fill_window_flag:
        flags.append(fill_window_flag)

    return {
        "section": section,
        "job": job,
        "date": date_s,
        "odometer_km": odometer_km,
        "fluid": fluid_clean,
        "quantity_drained_l": _num(data.get("quantity_drained_l")),
        "quantity_added_l": _num(data.get("quantity_added_l")),
        "fluid_condition": condition_clean,
        "fluid_temp_c": fluid_temp_c,
        "fill_window_flag": fill_window_flag,
        "adaptation_relearn": adaptation_clean,
        "parts_replaced": _as_parts(data.get("parts_replaced")),
        "torque_checklist": checklist,
        "flags": flags,
        "leaks_found": str(data.get("leaks_found", "")).strip(),
        "discoveries": _as_list_str(data.get("discoveries")),
        "considerations_next": _as_list_str(data.get("considerations_next")),
        "technician": technician,
    }


# --- validation: maintenance --------------------------------------------------


def _clean_maintenance_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("maintenance item entries must be objects")
    item_key = _req_str(raw, "item_key", "maintenance item")
    if item_key not in maintenance_specs.ITEMS:
        raise ValueError(f"unknown maintenance item_key {item_key!r}; use one of: "
                         + ", ".join(maintenance_specs.ITEMS.keys()))
    action = _req_str(raw, "action", "maintenance item").strip().lower()
    if action not in MAINTENANCE_ACTIONS:
        raise ValueError("maintenance item action must be one of: "
                         + ", ".join(MAINTENANCE_ACTIONS))
    measurements = raw.get("measurements")
    if measurements is not None and not isinstance(measurements, dict):
        raise ValueError("maintenance item measurements must be an object")
    return {
        "item_key": item_key,
        "action": action,
        "part_brand": str(raw.get("part_brand", "")).strip(),
        "part_number": str(raw.get("part_number", "")).strip(),
        "fluid_brand": str(raw.get("fluid_brand", "")).strip(),
        "fluid_amount": str(raw.get("fluid_amount", "")).strip(),
        "condition_notes": str(raw.get("condition_notes", "")).strip(),
        "measurements": {str(k): v for k, v in (measurements or {}).items()},
    }


def _validate_maintenance(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    date_s = _req_str(data, "date", "maintenance")
    odometer_km = _req_num(data, "odometer_km", "maintenance")
    technician = _req_str(data, "technician", "maintenance")

    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("maintenance needs at least one entry in 'items'")
    items_clean = [_clean_maintenance_item(it) for it in raw_items]
    item_keys = [it["item_key"] for it in items_clean]

    checklist = apply_maintenance_torque_checklist(item_keys, data.get("torques_applied"))

    post_service_done = _as_list_str(data.get("post_service_done"))
    done_set = {s.strip().lower() for s in post_service_done}

    flags: list[str] = list(checklist["flags"])
    for it in items_clean:
        spec = maintenance_specs.ITEMS.get(it["item_key"]) or {}
        label = spec.get("label", it["item_key"])
        if it["action"] == "inspected_needs_attention":
            note = f": {it['condition_notes']}" if it["condition_notes"] else ""
            flags.append(f"{label}: needs attention{note}")
        if it["action"] in MAINTENANCE_POST_SERVICE_ACTIONS:
            for step in spec.get("post_service") or []:
                if step.strip().lower() not in done_set:
                    flags.append(f"{label}: post-service step not done: {step}")

    return {
        "date": date_s,
        "odometer_km": odometer_km,
        "technician": technician,
        "items": items_clean,
        "torque_checklist": checklist,
        "discoveries": _as_list_str(data.get("discoveries")),
        "next_time_notes": _as_list_str(data.get("next_time_notes")),
        "post_service_done": post_service_done,
        "flags": flags,
    }


_VALIDATORS = {
    "oil_change": _validate_oil_change,
    "service": _validate_service,
    "brakes_wheels_tires": _validate_brakes_wheels_tires,
    "drivetrain": _validate_drivetrain,
    "maintenance": _validate_maintenance,
}


# --- ledger --------------------------------------------------------------


def _append(entry: dict[str, Any]) -> dict[str, Any]:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _record(vin: str, kind: str, data: dict[str, Any]) -> dict[str, Any]:
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    if kind not in KINDS:
        raise ValueError(f"unknown service record kind {kind!r}; use one of: "
                         + ", ".join(KINDS))
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    clean = _VALIDATORS[kind](data)
    entry = {
        "op": "record",
        "id": uuid.uuid4().hex,
        "at": datetime.now().isoformat(timespec="seconds"),
        "vin": vin,
        "kind": kind,
        "data": clean,
    }
    return _append(entry)


def record_oil_change(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    """Record one oil-change service. Raises ``ValueError`` on bad input."""
    return _record(vin, "oil_change", data)


def record_service(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    """Record one general service entry. Raises ``ValueError`` on bad input."""
    return _record(vin, "service", data)


def record_brakes_wheels_tires(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    """Record one brakes/wheels/tyres service. Raises ``ValueError`` on bad input."""
    return _record(vin, "brakes_wheels_tires", data)


def record_drivetrain(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    """Record one drivetrain (transmission/transfer case/differentials/
    driveline/mounts) service. Raises ``ValueError`` on bad input."""
    return _record(vin, "drivetrain", data)


def record_maintenance(vin: str, data: dict[str, Any]) -> dict[str, Any]:
    """Record one routine-maintenance visit, covering one or more items from
    :mod:`mes.maintenance_specs`.ITEMS. Raises ``ValueError`` on bad input."""
    return _record(vin, "maintenance", data)


def amend(vin: str, record_id: str, data: dict[str, Any], note: str = "") -> dict[str, Any]:
    """Append an amendment to an existing record. Never rewrites history.

    ``data`` carries only the fields being corrected; :func:`load` merges
    these onto the original record (later amendments win, field by field)
    and keeps the full amendment trail under ``amendments`` on the returned
    view. The original ``record`` line is untouched.
    """
    vin = (vin or "").strip()
    record_id = (record_id or "").strip()
    if not vin:
        raise ValueError("vin is required")
    if not record_id:
        raise ValueError("record_id is required")
    if not isinstance(data, dict) or not data:
        raise ValueError("amend needs at least one field to change, as an object")
    entry = {
        "op": "amend",
        "id": record_id,
        "at": datetime.now().isoformat(timespec="seconds"),
        "vin": vin,
        "data": data,
        "note": (note or "").strip(),
    }
    return _append(entry)


def _read_lines() -> list[dict[str, Any]]:
    p = store_path()
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def load(vin: str = "", kind: Optional[str] = None) -> list[dict[str, Any]]:
    """Service records oldest-first, amendments folded in, filtered by VIN/kind.

    Each returned entry is the ``record`` line with any amendments merged
    onto its ``data`` (later amendments override earlier ones field by
    field) and an ``amendments`` list of ``{at, note, data}`` kept for
    audit -- history is never dropped, only superseded for display.
    """
    vin = (vin or "").strip()
    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    amendments: dict[str, list[dict[str, Any]]] = {}
    for obj in _read_lines():
        if vin and obj.get("vin") != vin:
            continue
        op = obj.get("op", "record")
        rid = obj.get("id")
        if not rid:
            continue
        if op == "record":
            if kind and obj.get("kind") != kind:
                continue
            records[rid] = obj
            order.append(rid)
        elif op == "amend":
            amendments.setdefault(rid, []).append(
                {"at": obj.get("at"), "note": obj.get("note", ""),
                 "data": obj.get("data", {})})
    out = []
    for rid in order:
        base = records[rid]
        merged = dict(base.get("data") or {})
        amends = amendments.get(rid, [])
        for a in amends:
            merged.update(a.get("data") or {})
        view = dict(base)
        view["data"] = merged
        if amends:
            view["amendments"] = amends
        out.append(view)
    return out


def last_oil_change(vin: str) -> Optional[dict[str, Any]]:
    entries = load(vin, "oil_change")
    return entries[-1] if entries else None


def last_of_kind(vin: str, kind: str) -> Optional[dict[str, Any]]:
    entries = load(vin, kind)
    return entries[-1] if entries else None


def drivetrain_history(vin: str, section: str) -> list[dict[str, Any]]:
    """Every ``drivetrain`` record for one section, oldest-first."""
    return [e for e in load(vin, "drivetrain") if e.get("data", {}).get("section") == section]


def last_drivetrain(vin: str, section: str) -> Optional[dict[str, Any]]:
    entries = drivetrain_history(vin, section)
    return entries[-1] if entries else None


def last_maintenance_item(vin: str, item_key: str) -> Optional[dict[str, Any]]:
    """The newest ``maintenance`` record that covered ``item_key``, with that
    item's own entry pulled out alongside the visit's date/odometer/
    technician. ``None`` if this item has never been recorded for this VIN.
    A record can cover several items at once, so this scans every record's
    ``items`` list rather than filtering on a top-level field.
    """
    for entry in reversed(load(vin, "maintenance")):
        d = entry.get("data", {}) or {}
        for it in d.get("items", []):
            if it.get("item_key") == item_key:
                return {
                    "record_id": entry.get("id"),
                    "at": entry.get("at"),
                    "date": d.get("date"),
                    "odometer_km": d.get("odometer_km"),
                    "technician": d.get("technician"),
                    "item": it,
                }
    return None


# --- next oil change ----------------------------------------------------------


def _add_months(date_s: str, months: int) -> Optional[str]:
    try:
        y, m, d = (int(p) for p in date_s.split("-")[:3])
    except (ValueError, AttributeError):
        return None
    m0 = m - 1 + months
    y += m0 // 12
    m = m0 % 12 + 1
    for day in (d, 28, 27, 26):
        try:
            return f"{y:04d}-{m:02d}-{day:02d}"
        except ValueError:
            continue
    return f"{y:04d}-{m:02d}-01"


def _mes_oil_change_events(vin: str) -> list[dict[str, Any]]:
    """MES 'Oil change' adjustment events from the workup, read-only.

    Corroboration only -- these are actuator/adjustment routines the logs
    recorded being run, not a substitute for this store's own ledger.
    """
    if not vin.strip():
        return []
    try:
        from . import workup as workup_mod
        dossier = workup_mod.build(vin=vin)
    except Exception:
        return []
    if "error" in dossier:
        return []
    out = []
    for row in dossier.get("already_attempted", []):
        if row.get("kind") != "adjustment":
            continue
        if "oil" in str(row.get("operation", "")).lower():
            out.append(row)
    return out


def next_oil_change(vin: str) -> dict[str, Any]:
    """When the next oil change is due, from the ledger plus the spec
    interval, corroborated (never overridden) by MES 'Oil change'
    adjustment events.
    """
    interval = service_specs.SERVICE_INTERVAL
    interval_km = interval.get("km")
    interval_months = interval.get("months")
    mes_events = _mes_oil_change_events(vin)

    last = last_oil_change(vin)
    if last:
        d = last["data"]
        override = d.get("next_due_override") or {}
        base_odo = d["odometer_km"]
        base_date = d["date"]
        next_km = override.get("odometer_km") or (
            base_odo + interval_km if interval_km is not None else None)
        next_date = override.get("date") or (
            _add_months(base_date, interval_months) if interval_months else None)
        return {
            "known": True,
            "based_on": "service_records",
            "last_oil_change_at": base_date,
            "last_oil_change_odometer_km": base_odo,
            "next_due_odometer_km": next_km,
            "next_due_date": next_date,
            "interval": interval,
            "considerations_carried_forward": d.get("considerations_next", []),
            "mes_corroboration": mes_events,
        }

    if mes_events:
        newest = mes_events[0]
        return {
            "known": False,
            "based_on": "mes_adjustment_only",
            "reason": ("no oil change recorded in the service ledger yet; "
                      "MES shows an 'Oil change' adjustment routine that "
                      "was run, but no odometer/date baseline for a "
                      "reliable next-due calculation"),
            "mes_corroboration": mes_events,
            "newest_mes_event": newest,
            "interval": interval,
        }

    return {
        "known": False,
        "based_on": "none",
        "reason": "no oil change on record and none found in the MES logs",
        "interval": interval,
        "mes_corroboration": [],
    }


# --- maintenance due -----------------------------------------------------------


def _parse_date(date_s: Optional[str]):
    """``"YYYY-MM-DD"`` -> :class:`datetime.date`, or ``None`` if unparseable."""
    from datetime import date as _date
    try:
        y, m, d = (int(p) for p in (date_s or "").split("-")[:3])
        return _date(y, m, d)
    except (ValueError, TypeError, AttributeError):
        return None


def maintenance_due(vin: str, current_odometer_km: Optional[float] = None) -> dict[str, Any]:
    """Per-item due status for every :mod:`mes.maintenance_specs` item:
    last date/odometer recorded (if any), next due by km and by date from
    the item's interval (``None`` when that half of the interval is
    UNKNOWN), and a ``status``:

    * ``interval_unknown`` -- neither an interval-km nor an interval-months
      figure is sourced for this item; nothing to compare against.
    * ``never_recorded``   -- the interval is known but this item has never
      been recorded for this VIN.
    * ``overdue``          -- past the next-due km and/or date.
    * ``due_soon``         -- within :data:`MAINTENANCE_DUE_SOON_KM` km or
      :data:`MAINTENANCE_DUE_SOON_DAYS` days of next-due, not yet overdue.
    * ``ok``                -- neither of the above.

    Never raises for a VIN with no maintenance history -- every item simply
    comes back ``never_recorded`` or ``interval_unknown``.
    """
    today = datetime.now().date()
    items_out: list[dict[str, Any]] = []
    for key, spec in maintenance_specs.ITEMS.items():
        last = last_maintenance_item(vin, key)
        interval_km = spec.get("interval_km")
        if interval_km is None and spec.get("interval_miles") is not None:
            interval_km = round(spec["interval_miles"] * _KM_PER_MILE)
        interval_months = spec.get("interval_months")

        last_date = last["date"] if last else None
        last_odo = last["odometer_km"] if last else None
        next_due_km = (last_odo + interval_km
                      if last_odo is not None and interval_km is not None else None)
        next_due_date = (_add_months(last_date, interval_months)
                        if last_date and interval_months else None)

        if interval_km is None and interval_months is None:
            status = "interval_unknown"
        elif last is None:
            status = "never_recorded"
        else:
            overdue = due_soon = False
            if next_due_km is not None and current_odometer_km is not None:
                remaining_km = next_due_km - current_odometer_km
                if remaining_km <= 0:
                    overdue = True
                elif remaining_km <= MAINTENANCE_DUE_SOON_KM:
                    due_soon = True
            parsed_due = _parse_date(next_due_date)
            if parsed_due is not None:
                remaining_days = (parsed_due - today).days
                if remaining_days <= 0:
                    overdue = True
                elif remaining_days <= MAINTENANCE_DUE_SOON_DAYS:
                    due_soon = True
            status = "overdue" if overdue else ("due_soon" if due_soon else "ok")

        items_out.append({
            "item_key": key,
            "label": spec.get("label", key),
            "category": spec.get("category"),
            "last_date": last_date,
            "last_odometer_km": last_odo,
            "next_due_odometer_km": next_due_km,
            "next_due_date": next_due_date,
            "interval_confidence": spec.get("interval_confidence"),
            "interval_source": spec.get("interval_source"),
            "interval_note": spec.get("interval_note"),
            "status": status,
        })
    return {"vin": vin, "current_odometer_km": current_odometer_km, "items": items_out}


# --- checklists for the pages -------------------------------------------------


def oil_change_checklist(vin: str) -> dict[str, Any]:
    """Everything the oil-change page needs in one call: specs with
    sources, the last change's carried-forward considerations, open EVAP/
    engine codes worth noting, and the torque checklist for the job.
    """
    specs = service_specs.oil_change_specs()
    last = last_oil_change(vin)
    considerations = list((last or {}).get("data", {}).get("considerations_next", []))

    open_codes: list[Any] = []
    try:
        from . import workup as workup_mod
        dossier = workup_mod.build(vin=vin)
        if "error" not in dossier:
            current = dossier.get("current_picture", {}) or {}
            for key in ("latest_session", "last_session_with_findings"):
                session = current.get(key)
                if session:
                    open_codes.extend(session.get("dtcs", []))
            for r in dossier.get("history", {}).get("chronic", []):
                open_codes.append({"dtc": r.get("dtc"), "note": "chronic"})
    except Exception:
        pass

    return {
        "vin": vin,
        "specs": specs,
        "last_oil_change": last,
        "carried_forward_considerations": considerations,
        "open_codes_worth_noting": open_codes,
        "next_due": next_oil_change(vin),
        "torque_checklist": build_torque_checklist("oil_change"),
    }


def brakes_wheels_tires_checklist(vin: str) -> dict[str, Any]:
    """Everything the brakes/wheels/tyres page needs: specs, last record's
    carried-forward considerations, and the torque checklist for the job.
    """
    specs = service_specs.brake_wheel_tire_specs()
    last = last_of_kind(vin, "brakes_wheels_tires")
    considerations = list((last or {}).get("data", {}).get("considerations_next", []))
    return {
        "vin": vin,
        "specs": specs,
        "last_service": last,
        "carried_forward_considerations": considerations,
        "torque_checklist": build_torque_checklist(
            ["brakes_front", "brakes_rear", "wheels"]),
    }


def drivetrain_section_checklist(vin: str, section: str) -> dict[str, Any]:
    """Everything a drivetrain section page needs: this section's specs/
    torques/jobs (from :mod:`mes.drivetrain_specs`), the section's service
    history, the last record's carried-forward considerations. Raises
    ``ValueError`` for an unknown section.
    """
    section = (section or "").strip().lower()
    if section not in DRIVETRAIN_SECTIONS:
        raise ValueError("section must be one of: " + ", ".join(DRIVETRAIN_SECTIONS))
    sec_data = drivetrain_specs.SECTIONS[section]
    history = drivetrain_history(vin, section)
    last = history[-1] if history else None
    considerations = list((last or {}).get("data", {}).get("considerations_next", []))
    return {
        "vin": vin,
        "section": section,
        "specs": sec_data,
        "jobs": sec_data.get("jobs", {}),
        "history": history,
        "last_service": last,
        "carried_forward_considerations": considerations,
    }


def maintenance_checklist(vin: str, current_odometer_km: Optional[float] = None) -> dict[str, Any]:
    """Everything the routine-maintenance page needs: every item grouped by
    category (from :mod:`mes.maintenance_specs`), the last maintenance
    record, its carried-forward "next time" notes, and per-item due status.
    """
    last = last_of_kind(vin, "maintenance")
    considerations = list((last or {}).get("data", {}).get("next_time_notes", []))
    return {
        "vin": vin,
        "items_by_category": maintenance_specs.items_by_category(),
        "category_labels": {c: c.replace("_", " ").title() for c in maintenance_specs.CATEGORIES},
        "last_maintenance": last,
        "carried_forward_next_time_notes": considerations,
        "due": maintenance_due(vin, current_odometer_km),
    }


__all__ = [
    "KINDS", "CORNERS", "DRIVETRAIN_SECTIONS", "TRANSMISSION_FILL_TEMP_MIN_C",
    "TRANSMISSION_FILL_TEMP_MAX_C", "TORQUE_TOLERANCE", "TREAD_LEGAL_MM",
    "TREAD_ADVISORY_MM", "PRESSURE_TOLERANCE_KPA", "MAINTENANCE_ACTIONS",
    "MAINTENANCE_POST_SERVICE_ACTIONS", "MAINTENANCE_DUE_SOON_KM",
    "MAINTENANCE_DUE_SOON_DAYS", "state_dir", "store_path",
    "build_torque_checklist", "apply_torque_checklist",
    "build_drivetrain_torque_checklist", "apply_drivetrain_torque_checklist",
    "build_maintenance_torque_checklist", "apply_maintenance_torque_checklist",
    "corner_flags", "record_oil_change", "record_service",
    "record_brakes_wheels_tires", "record_drivetrain", "record_maintenance",
    "amend", "load", "last_oil_change", "last_of_kind", "drivetrain_history",
    "last_drivetrain", "last_maintenance_item", "next_oil_change",
    "maintenance_due", "oil_change_checklist", "brakes_wheels_tires_checklist",
    "drivetrain_section_checklist", "maintenance_checklist",
]
