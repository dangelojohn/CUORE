""""Tell CUORE": what the owner, driver or mechanic reports that the car
cannot tell CUORE on its own -- a fill-up, a fluid top-up, a pothole hit, a
window left open in the rain, a part fitted by another shop.

**This is an ATTESTED record, never a car measurement.** Every row says who
said it, when, at confidence ``"reported"`` -- a human claim, kept separate
from, and never promoted into, :mod:`mes.verdict`'s evidence gate. Same
posture as :mod:`cuore.live.attested` and ``mes.symptoms``: a thing a person
typed is evidence that a conversation happened, not evidence the car has a
fault. See the footer this feature's pages render for the same sentence in
the UI.

One exception, by design, not oversight: a "noise/smell/vibration noticed"
report (category ``incidents``) is not stored here at all -- it is handed to
``mes.symptoms`` (via :mod:`cuore.services.timeline_bridge`), the store the
mechanic-vs-driver timeline already reads, so the same report shows up in
both places instead of forking into a second, drifting copy. See
:mod:`cuore.services.owner_events_bridge` for where that hand-off happens.

Append-only JSONL under ``cuore.live.config.state_dir()`` (``CUORE_STATE_DIR``,
same precedence as every other cuore live store), one file,
``owner_events.jsonl``, three record shapes distinguished by ``op``:

* ``event`` -- {op, id, vin, at, recorded_at, by: {role, name}, category,
  kind, fields, fields_meta, note, media_ids, odometer_km, confidence="reported"}
* ``delete``-- {op, id, at} -- marks an event hidden (soft delete)
* ``restore`` -- {op, id, at} -- undoes a ``delete`` (the Mobile page's own
  "Undo" on the post-delete confirmation screen); folded against ``delete``
  in append order, so a delete/restore/delete... history is read correctly
  regardless of how many times it happened
* ``event_edit`` (added 2026-10-13) -- {op, id, at (the EDIT's own
  timestamp, never the event's own occurrence time unless ``changes.at``
  says so), by: {role, name}, changes: {fields: {key: {from, to}},
  note: {from, to}, odometer_km: {from, to}, at: {from, to}}} -- never
  rewrites the original ``event`` row; :func:`load` folds every
  ``event_edit`` for an id onto its ``event`` row, in append order, and
  keeps the folded result's ``audit`` list (one entry per edit: who, when,
  what changed) for the UI's disclosure. A changed field's ``fields_meta``
  becomes ``"typed"`` -- it is a hand edit now, even if the field started
  life as a photo read -- **unless the edit resubmits the exact same value
  it already had** ("keeps the photo value"), in which case the field's
  existing provenance tag (photo or typed, or none) is left alone.

``fields_meta`` (added 2026-10-13, additive -- older rows simply have none)
is ``{field_key: "photo"|"typed"}``, one entry per field whose provenance
is worth remembering -- "photo" for a value read off a picture by the
Mobile "Snap & fill" screen (``cuore.web.owner_routes``) rather than typed
by the person, "typed" for an explicit hand-entry note; see that module's
own docstring, and ``cuore.api.owner_events``, for the two callers (the
HTML form's ``source_<key>=photo`` hidden inputs, and the JSON API's own
``fields_meta`` body key) that both feed this same parameter. Only a key
that is (a) one of this kind's real taxonomy fields and (b) one of these
two words survives into the stored row -- anything else is dropped
silently, same posture as an unknown field key ever since this store
existed. It is informational only: a photo-read field is stored at the
same ``confidence: "reported"`` as every other owner-typed value (a human
still tapped Save) -- this just remembers *how* the value got into the
box, for the "check before saving" amber chip and for anyone auditing the
report later.

This module owns the taxonomy -- the single source of truth the add/list
form, the API's validation, and the timeline lane all read from -- plus
plain append/soft-delete/load. Everything that reaches outside ``cuore.live``
(systems lookups, correlation against DTC history, the feedback/inbox
"messages" bridge) lives in ``cuore.services.owner_events_bridge`` instead,
same split ``cuore.live.media`` / nothing-yet-equivalent keeps.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir

_LOCK = threading.Lock()

MAX_NOTE = 4000
MAX_FIELD_TEXT = 500

#: Who can file a report. ``name`` is optional free text (e.g. "Dad", "Mario
#: at Midtown Tire") kept alongside the role.
BY_ROLES = ("owner", "driver", "mechanic")


def _kind(label: str, fields: dict[str, dict[str, Any]], why_it_matters: str,
         systems: tuple[str, ...], **relevance: bool) -> dict[str, Any]:
    """One taxonomy entry. ``relevance`` is any of the ``*_relevant`` flags
    (e.g. ``evap_relevant=True``) -- stored as a dict so a caller can test
    ``kind["relevance"].get("evap_relevant")`` without a KeyError."""
    return {
        "label": label,
        "fields": fields,
        "why_it_matters": why_it_matters,
        "systems": list(systems),
        "relevance": dict(relevance),
    }


def _f(type_: str, label: str, *, unit: str = "", choices: Optional[tuple[str, ...]] = None,
      required: bool = False, remember: bool = False) -> dict[str, Any]:
    """One form field descriptor: ``type`` is one of text|number|choice|bool|
    date|datetime. ``choices`` renders as big tap chips on the mobile form."""
    out: dict[str, Any] = {"type": type_, "label": label, "required": required}
    if remember:
        # Free text the garage types again and again (oil brand, filter make,
        # fuel station): the form offers the values last used, this car first,
        # then the rest of the garage (see recent_values). Typing stays open.
        out["remember"] = True
    if unit:
        out["unit"] = unit
    if choices:
        out["choices"] = list(choices)
    return out


#: category_key -> {label, kinds: {kind_key: _kind(...)}}
#: The single source the mobile "Add" tiles, the API's category/kind
#: validation, and the timeline owner-events lane all read. Add a kind here
#: and it is immediately offered on the phone, validated by the API, and
#: shown on the history page -- nowhere else needs to know about it.
TAXONOMY: dict[str, dict[str, Any]] = {

    "fluids": {
        "label": "Fluids",
        "kinds": {
            "engine_oil_change": _kind(
                "Engine oil change",
                {"brand": _f("text", "Oil brand", remember=True),
                 "viscosity": _f("text", "Viscosity (e.g. 5W-30)", remember=True),
                 "qty": _f("number", "Quantity", unit="L"),
                 "filter_changed": _f("bool", "Filter changed"),
                 "filter_brand": _f("text", "Filter brand (e.g. Mann, UFI, Mopar)", remember=True),
                 "filter_part_no": _f("text", "Filter part number", remember=True)},
                "Oil interval and viscosity both matter for wear-related codes and for whether "
                "an oil-life reset is overdue.",
                ("lubrication",)),
            "engine_oil_topup": _kind(
                "Engine oil top-up",
                {"qty": _f("number", "Quantity added", unit="L")},
                "A top-up between changes can mean a slow leak or consumption worth tracking.",
                ("lubrication",)),
            "coolant_change": _kind(
                "Coolant change",
                {"type": _f("text", "Coolant type"), "qty": _f("number", "Quantity", unit="L")},
                "Wrong coolant type or a recent change can mask or explain a cooling-system code.",
                ("cooling",)),
            "coolant_topup": _kind(
                "Coolant top-up",
                {"qty": _f("number", "Quantity added", unit="L")},
                "A coolant top-up between services often means a small leak building toward a "
                "bigger one.",
                ("cooling",)),
            "brake_fluid": _kind(
                "Brake fluid change/top-up",
                {"action": _f("choice", "Action", choices=("changed", "topped up")),
                 "qty": _f("number", "Quantity", unit="L")},
                "Low brake fluid without a matching pad-wear note can point to a leak, not just "
                "wear.",
                ("brakes_abs",)),
            "driveline_fluid": _kind(
                "Transmission / transfer-case / differential oil",
                {"which": _f("choice", "Which unit",
                             choices=("transmission", "transfer case", "differential")),
                 "action": _f("choice", "Action", choices=("changed", "topped up")),
                 "qty": _f("number", "Quantity", unit="L")},
                "Driveline fluid history explains shift-quality complaints and some network/"
                "module codes tied to a driveline control unit.",
                ("transmission_driveline",)),
            "washer_fluid": _kind(
                "Washer fluid top-up",
                {"qty": _f("number", "Quantity added", unit="L")},
                "Rarely diagnostic on its own; kept for a complete service picture.",
                ("body_comfort",)),
            "adblue_na": _kind(
                "AdBlue -- not applicable",
                {},
                "Recorded once so the fluids list doesn't keep asking; this car has no AdBlue "
                "system.",
                ("exhaust_emissions",)),
            "fluid_level_checked": _kind(
                "Fluid level checked",
                {"fluid": _f("choice", "Which fluid",
                             choices=("engine oil", "coolant", "brake fluid",
                                     "transmission/transfer-case/differential", "washer fluid")),
                 "result": _f("choice", "Result", choices=("was low", "ok"))},
                "A level that was low points a mechanic straight at that system before anything "
                "else.",
                ("lubrication", "cooling", "brakes_abs", "transmission_driveline")),
        },
    },

    "fuel": {
        "label": "Fuel",
        "kinds": {
            "fill_up": _kind(
                "Fill-up",
                {"station": _f("text", "Station/brand", remember=True),
                 "octane": _f("choice", "Octane/RON",
                             choices=("87", "89", "91", "93", "94", "RON 95", "RON 98")),
                 "litres": _f("number", "Litres", unit="L", required=True),
                 "price": _f("number", "Price", unit="$"),
                 "ethanol": _f("choice", "Ethanol", choices=("none", "E10", "E15", "E85")),
                 "additive_used": _f("bool", "Fuel additive used"),
                 "cap_clicked": _f("bool", "Cap clicked shut"),
                 "overfilled": _f("bool", "Pump stopped early / overfilled"),
                 "filled_engine_running": _f("bool", "Filled with engine running")},
                "A cap that wasn't clicked, an overfill, or filling with the engine running are "
                "the three most common owner actions that set an EVAP leak code with no actual "
                "leak in the system.",
                ("fuel", "evap"),
                evap_relevant=True),
            "fuel_cap_issue": _kind(
                "Fuel cap issue noticed later",
                {"detail": _f("text", "What happened (left loose, missing, cracked...)")},
                "A loose, missing or cracked cap is the single most common cause of a P0455/"
                "P0457-family EVAP code.",
                ("fuel", "evap"),
                evap_relevant=True),
            "ran_low_or_out": _kind(
                "Ran very low on fuel / ran out",
                {"detail": _f("text", "What happened")},
                "Running near-empty repeatedly can disturb the fuel-level sender and some EVAP "
                "monitors that require a mid-range fuel level to run.",
                ("fuel", "evap"),
                evap_relevant=True),
        },
    },

    "battery_electrical": {
        "label": "Battery / electrical",
        "kinds": {
            "battery_replaced": _kind(
                "Battery replaced",
                {"brand": _f("text", "Brand", remember=True), "ah": _f("number", "Capacity", unit="Ah"),
                 "date_code": _f("text", "Date code")},
                "A battery replacement resets adaptive charging strategy and can trigger stored "
                "voltage/network codes for a day or two afterward.",
                ("electrical_supply", "starting_charging"),
                electrical_relevant=True),
            "battery_charged": _kind(
                "Battery charged / trickle charged",
                {"charger_type": _f("text", "Charger type"),
                 "hours": _f("number", "Hours", unit="h")},
                "A recent deep charge explains a temporarily high resting voltage reading.",
                ("electrical_supply",),
                electrical_relevant=True),
            "jump_started": _kind(
                "Jump started",
                {"direction": _f("choice", "Direction", choices=("gave a jump", "received a jump"))},
                "A jump start is a voltage spike event that can set, and then clear on its own, "
                "a module communication code.",
                ("electrical_supply", "network", "starting_charging"),
                electrical_relevant=True),
            "battery_disconnected": _kind(
                "Battery disconnected",
                {"how_long": _f("text", "How long")},
                "Disconnecting the battery clears adaptive memory and some module learned "
                "values -- explains a code that reappears needing a relearn, not a repeat fault.",
                ("electrical_supply", "network", "security_immobiliser"),
                electrical_relevant=True),
            "aftermarket_electrical": _kind(
                "Aftermarket electrical fitted",
                {"item": _f("choice", "Item",
                            choices=("dashcam", "lights", "audio", "trailer wiring", "tracker",
                                    "phone charger", "other")),
                 "by_whom": _f("text", "Fitted by")},
                "The single most common cause of an intermittent parasitic drain or a noise-"
                "related network code the car's own wiring never had.",
                ("electrical_supply", "network", "lighting", "infotainment_cluster"),
                electrical_relevant=True),
            "fuse_replaced": _kind(
                "Fuse replaced",
                {"circuit": _f("text", "Circuit/fuse")},
                "Which circuit blew, and how often, narrows a short far faster than a code alone.",
                ("electrical_supply",),
                electrical_relevant=True),
            "module_coded": _kind(
                "Module coded / flashed",
                {"module": _f("text", "Module"), "by_whom": _f("text", "By whom")},
                "A recent flash/coding event explains a one-time communication code at the "
                "moment it was done.",
                ("network", "security_immobiliser"),
                electrical_relevant=True),
            "key_fob_battery": _kind(
                "Key fob battery changed",
                {},
                "Rules out a weak fob as the cause of an intermittent no-start or lock complaint.",
                ("security_immobiliser",)),
            "car_sat_unused": _kind(
                "Car sat unused",
                {"days": _f("number", "Days", unit="d")},
                "Extended standing is the most common cause of a weak-battery no-start and of a "
                "monitor that \"hasn't run yet\" after a clear.",
                ("electrical_supply", "evap"),
                evap_relevant=True, electrical_relevant=True),
        },
    },

    "tyres_wheels_brakes": {
        "label": "Tyres / wheels / brakes",
        "kinds": {
            "tyres_replaced": _kind(
                "Tyres replaced",
                {"which": _f("choice", "Which", choices=("all four", "front pair", "rear pair",
                                                          "one")),
                 "brand": _f("text", "Brand/model", remember=True)},
                "A tyre-size or brand change can throw off ABS/TPMS wheel-speed comparisons.",
                ("wheels_tpms", "brakes_abs")),
            "tyres_rotated": _kind(
                "Tyres rotated",
                {},
                "Explains an even wear pattern and resets which corner a TPMS sensor reports from.",
                ("wheels_tpms",)),
            "tyre_plugged": _kind(
                "Tyre plugged/repaired",
                {"position": _f("choice", "Position", choices=("FL", "FR", "RL", "RR"))},
                "A repair can disturb a TPMS sensor seal -- worth knowing before chasing a slow "
                "leak as a sensor fault.",
                ("wheels_tpms",)),
            "pressure_set": _kind(
                "Pressure set",
                {"fl": _f("number", "FL", unit="kPa"), "fr": _f("number", "FR", unit="kPa"),
                 "rl": _f("number", "RL", unit="kPa"), "rr": _f("number", "RR", unit="kPa")},
                "Per-corner pressures right before a TPMS or ABS wheel-speed complaint are "
                "exactly the evidence a mechanic needs and the car cannot log.",
                ("wheels_tpms", "brakes_abs")),
            "wheel_removed": _kind(
                "Wheel removed/refitted",
                {"torque_used": _f("bool", "Torque wrench used")},
                "A wheel refitted without a torque wrench is a common cause of a brake-judder or "
                "wheel-speed complaint that looks like a sensor fault.",
                ("wheels_tpms", "brakes_abs", "steering")),
            "alignment": _kind(
                "Alignment performed",
                {"shop": _f("text", "Shop")},
                "Recent alignment work explains a steering-angle sensor relearn requirement.",
                ("steering", "suspension", "adas_sensors")),
            "brake_work": _kind(
                "Brake pads/discs replaced",
                {"which": _f("choice", "Which axle", choices=("front", "rear", "all"))},
                "New pads need a bed-in period that can feel like a brake complaint for a short "
                "while.",
                ("brakes_abs",)),
            "wheel_bearing": _kind(
                "Wheel bearing replaced",
                {"position": _f("choice", "Position", choices=("FL", "FR", "RL", "RR"))},
                "Explains a wheel-speed/ABS code and a noise that changes with speed.",
                ("brakes_abs", "wheels_tpms", "suspension")),
        },
    },

    "parts_repairs_elsewhere": {
        "label": "Parts / repairs elsewhere",
        "kinds": {
            "part_fitted_elsewhere": _kind(
                "Part fitted by another shop or owner",
                {"part": _f("text", "Part", required=True),
                 "source": _f("choice", "Source", choices=("OEM", "aftermarket", "used")),
                 "who": _f("text", "Fitted by")},
                "Any work this record doesn't already know about is a gap that can make a "
                "correctly-fixed car look like it still has the original fault.",
                ()),
            "dealer_software_update": _kind(
                "Software update at dealer",
                {"module": _f("text", "Module/system"), "dealer": _f("text", "Dealer")},
                "A software update can change monitor behaviour and freeze-frame content for "
                "codes set afterward.",
                ("network",)),
            "recall_performed": _kind(
                "Recall performed",
                {"recall_no": _f("text", "Recall number")},
                "Rules a known factory campaign in or out before treating a symptom as novel.",
                ()),
            "warranty_visit": _kind(
                "Warranty visit",
                {"reason": _f("text", "Reason")},
                "A prior warranty visit for the same complaint changes how a repeat failure "
                "should be read.",
                ()),
        },
    },

    "environment_exposure": {
        "label": "Environment / exposure",
        "kinds": {
            "left_open_in_rain": _kind(
                "Window/sunroof left open in rain",
                {},
                "Water intrusion near a control module is a leading cause of an intermittent "
                "electrical fault with no obvious source.",
                ("electrical_supply", "body_comfort", "network")),
            "deep_water_flood": _kind(
                "Deep water / flood exposure",
                {"depth": _f("text", "How deep")},
                "Water ingress at intake or connector height can cause hydro-lock risk and "
                "corrosion-driven faults for months afterward.",
                ("air_intake_boost", "electrical_supply")),
            "car_wash": _kind(
                "Car wash",
                {"type": _f("choice", "Type", choices=("touchless", "brush", "hand", "engine bay"))},
                "A pressure wash near the engine bay or wheel wells is a common, short-lived "
                "cause of a sensor or ABS code that clears once things dry out.",
                ("electrical_supply", "wheels_tpms")),
            "parked_under_trees": _kind(
                "Parked under trees / sap exposure",
                {},
                "Sap/debris around the cowl and drains can block a drain and lead to water "
                "intrusion later -- useful context for an electrical fault months on.",
                ("body_comfort",)),
            "rodents_seen": _kind(
                "Rodents seen/evidence",
                {"detail": _f("text", "What was seen")},
                "Rodent damage to wiring is a classic cause of an intermittent, hard-to-pin "
                "electrical fault that no scan tool will name directly.",
                ("electrical_supply", "network")),
            "extreme_temp": _kind(
                "Extreme cold/heat exposure",
                {"which": _f("choice", "Which", choices=("extreme cold", "extreme heat")),
                 "temp_c": _f("number", "Approx. temperature", unit="C")},
                "Temperature extremes change battery capacity and some monitors' ability to run "
                "at all that day.",
                ("electrical_supply", "evap"),
                evap_relevant=True),
            "salt_roads": _kind(
                "Driven on salted roads",
                {},
                "Salt exposure history explains an underbody corrosion finding and connector "
                "corrosion on an otherwise unexplained circuit fault.",
                ("electrical_supply", "brakes_abs", "wheels_tpms")),
            "long_storage": _kind(
                "Long storage",
                {"days": _f("number", "Days", unit="d")},
                "Same as a dead-battery/monitor-not-run gap, but for a planned layup rather than "
                "neglect -- useful context either way.",
                ("electrical_supply", "evap"),
                evap_relevant=True),
            "off_road_gravel": _kind(
                "Off-road / gravel driving",
                {},
                "Explains an underbody scrape or a debris-strike finding that otherwise looks "
                "unexplained.",
                ("suspension", "exhaust_emissions")),
            "towing": _kind(
                "Towing / towed / roof rack or trailer load",
                {"which": _f("choice", "Which",
                             choices=("towed a trailer", "was towed", "roof rack/cargo load"))},
                "Sustained load changes suspension and transmission stress and is worth knowing "
                "before treating a strain-related fault as spontaneous.",
                ("suspension", "transmission_driveline", "brakes_abs")),
        },
    },

    "incidents": {
        "label": "Incidents",
        "kinds": {
            "pothole_kerb_strike": _kind(
                "Pothole/kerb strike",
                {"detail": _f("text", "What happened")},
                "The single most common real-world cause of a wheel-speed, alignment or "
                "suspension-noise complaint with no prior code.",
                ("suspension", "wheels_tpms", "steering")),
            "minor_collision": _kind(
                "Minor collision",
                {"detail": _f("text", "What happened")},
                "Even a minor impact can trigger a restraints/ADAS calibration requirement that "
                "a code alone won't name.",
                ("restraints", "adas_sensors", "body_comfort")),
            "underbody_scrape": _kind(
                "Underbody scrape",
                {"detail": _f("text", "What happened")},
                "A scrape is a prime candidate for a holed exhaust, a cracked EVAP line, or a "
                "damaged sensor wire -- all things that otherwise look mysterious.",
                ("exhaust_emissions", "evap", "suspension"),
                evap_relevant=True),
            "debris_strike": _kind(
                "Debris strike",
                {"detail": _f("text", "What happened")},
                "Explains a sudden, isolated noise or vibration complaint with no fault history "
                "before it.",
                ("suspension", "wheels_tpms")),
            "theft_attempt": _kind(
                "Theft attempt",
                {"detail": _f("text", "What happened")},
                "A forced-entry or steering-lock attempt explains a security/immobiliser code "
                "that otherwise has no obvious cause.",
                ("security_immobiliser",)),
            "warning_light_seen": _kind(
                "Warning light seen",
                {"which": _f("text", "Which light"), "how_long": _f("text", "How long it stayed on"),
                 "dash_message": _f("text", "Dash message text, if any")},
                "The light's colour, duration and any accompanying message are evidence the "
                "car's own log may not capture as clearly as the person who saw it.",
                ()),
            "noise_smell_vibration": _kind(
                "Noise / smell / vibration noticed",
                {"description": _f("text", "What was noticed", required=True),
                 "when": _f("text", "When it happens (cold start, braking, highway...)")},
                "Stored in the symptom timeline (not duplicated here) so the mechanic sees one "
                "record, not two.",
                (),
                delegate_to_symptoms=True),
            "engine_stalled": _kind(
                "Engine stalled",
                {"conditions": _f("text", "Conditions (idle, turning, highway...)")},
                "A stall is one of the few owner reports worth treating almost like a code: it "
                "narrows fuel/ignition/network causes quickly.",
                ("fuel", "ignition", "engine_management", "network")),
            "hard_start": _kind(
                "Hard start",
                {"conditions": _f("text", "Conditions (cold, hot, after sitting...)")},
                "The conditions under which starting is hard (cold vs. hot vs. after sitting) "
                "point at different systems entirely.",
                ("starting_charging", "fuel", "ignition")),
            "limp_mode": _kind(
                "Limp mode",
                {"detail": _f("text", "What the car did")},
                "Limp mode is the car's own protective response -- knowing exactly when it "
                "entered narrows the search dramatically.",
                ("engine_management", "transmission_driveline")),
        },
    },

    "driving_pattern": {
        "label": "Driving pattern",
        "kinds": {
            "typical_trip_length": _kind(
                "Typical trip length",
                {"minutes": _f("number", "Typical trip length", unit="min")},
                "Short-trip-only driving is one of the most common root causes of chronic EVAP "
                "and oil-dilution codes that otherwise look like a hardware fault.",
                ("evap", "lubrication"),
                evap_relevant=True),
            "short_trips_only": _kind(
                "Short trips only",
                {},
                "Confirms the single biggest EVAP/oil-life risk factor directly, without relying "
                "on a trip-length estimate.",
                ("evap", "lubrication"),
                evap_relevant=True),
            "highway_share": _kind(
                "Highway share of driving",
                {"percent": _f("number", "Approx. % highway", unit="%")},
                "Low highway share means monitors that need sustained speed/load may rarely get "
                "the chance to run.",
                ("evap", "exhaust_emissions"),
                evap_relevant=True),
            "idling": _kind(
                "Idling pattern",
                {"detail": _f("text", "Typical idling (e.g. long warm-ups, deliveries)")},
                "Heavy idling changes oil-life and emissions-monitor-run assumptions.",
                ("lubrication", "exhaust_emissions")),
            "cold_starts_per_day": _kind(
                "Cold starts per day",
                {"count": _f("number", "Cold starts/day")},
                "More cold starts per day means more opportunities for a cold-start-only fault "
                "to show, and less time for some monitors to complete.",
                ("evap", "lubrication"),
                evap_relevant=True),
        },
    },

    "cleaning_maintenance": {
        "label": "Cleaning / maintenance by owner",
        "kinds": {
            "engine_bay_washed": _kind(
                "Engine bay washed",
                {"water_near_connectors": _f("bool", "Water got near connectors")},
                "Among the most common, most overlooked causes of a short-lived electrical fault "
                "with no other explanation.",
                ("electrical_supply", "network")),
            "air_filter_cleaned": _kind(
                "Air filter cleaned/replaced by owner",
                {},
                "A dirty or wrongly-reinstalled filter can trip a MAF/boost-pressure related code.",
                ("air_intake_boost",)),
            "detailing_with_electronics": _kind(
                "Detailing involving electronics",
                {"detail": _f("text", "What was done (dash, seats with heaters/switches...)")},
                "Cleaning fluid near switches and connectors is a common, short-lived cause of a "
                "body-control code.",
                ("body_comfort", "electrical_supply")),
            "battery_terminal_cleaned": _kind(
                "Battery terminal cleaned",
                {},
                "A cleaned terminal can resolve a voltage-drop symptom on its own -- worth "
                "knowing before chasing anything else.",
                ("electrical_supply", "starting_charging")),
        },
    },
}


#: code family (a ``mes.systems`` key -- see ``mes.systems.systems_for_code``)
#: -> the CUORE-generated questions worth asking the owner when a code in
#: that family is active. Moved here from ``cuore.services.owner_events_
#: bridge`` (2026-10-14) to sit with :data:`TAXONOMY`, the other static
#: config this feature's pages/API read whole.
#:
#: Each question is ``{"id", "text", "chips"}``:
#:
#: * ``id`` is part of the dedup key ``owner_events_bridge.messages`` uses
#:   (together with the active code) so the same question is never refiled
#:   for the same code twice.
#: * ``text`` is the owner-facing question, plain language, no jargon.
#: * ``chips`` is zero or more one-tap answers, each
#:   ``{"label", "category", "kind", "fields"}``: tapping it sends ``label``
#:   back as the reply text (the same free-text reply path every message
#:   already has) and, when ``category``/``kind`` are not ``None``, that
#:   reply text is recognised by ``owner_events_bridge.reply_message`` and
#:   turned into exactly the owner event ``add(vin, category, kind,
#:   fields=fields, ...)`` would create by hand -- no second, parallel
#:   "chip answer" store. A chip with ``category=None`` (e.g. "none of
#:   these") records the reply only, same as typing it.
PROMPT_RULES: dict[str, list[dict[str, Any]]] = {
    "evap": [
        {"id": "evap_fillup_recent",
         "text": "Did you fill up in the last 2 days? Did the cap click? Did the "
                 "pump stop early or did you top off?",
         "chips": [
             {"label": "Filled up, cap clicked, pump stopped normally",
              "category": "fuel", "kind": "fill_up",
              "fields": {"cap_clicked": True, "overfilled": False}},
             {"label": "Filled up, but the cap did NOT click",
              "category": "fuel", "kind": "fill_up", "fields": {"cap_clicked": False}},
             {"label": "Filled up, pump stopped early / topped off",
              "category": "fuel", "kind": "fill_up", "fields": {"overfilled": True}},
             {"label": "Haven't filled up in the last 2 days",
              "category": None, "kind": None, "fields": {}},
         ]},
        {"id": "evap_short_trips",
         "text": "Is this car mostly short trips lately (under ~15 minutes)?",
         "chips": [
             {"label": "Yes, mostly short trips",
              "category": "driving_pattern", "kind": "short_trips_only", "fields": {}},
             {"label": "No, a regular mix of trips",
              "category": None, "kind": None, "fields": {}},
         ]},
    ],
    "electrical_supply": [
        {"id": "elec_recent_work",
         "text": "Any battery work, jump start, or aftermarket electrical fitted "
                 "recently (dashcam, lights, audio, tracker)?",
         "chips": []},
    ],
    "network": [
        {"id": "network_recent_elec",
         "text": "Any aftermarket electrical fitted recently (dashcam, lights, "
                 "charger)? Battery changed or jump-started? Car washed with the "
                 "engine bay open?",
         "chips": [
             {"label": "Aftermarket electrical fitted",
              "category": "battery_electrical", "kind": "aftermarket_electrical",
              "fields": {}},
             {"label": "Battery changed/replaced",
              "category": "battery_electrical", "kind": "battery_replaced", "fields": {}},
             {"label": "Jump-started",
              "category": "battery_electrical", "kind": "jump_started", "fields": {}},
             {"label": "Car washed, engine bay open",
              "category": "environment_exposure", "kind": "car_wash",
              "fields": {"type": "engine bay"}},
             {"label": "None of these",
              "category": None, "kind": None, "fields": {}},
         ]},
    ],
    "starting_charging": [
        {"id": "start_conditions",
         "text": "When it's hard to start, is that cold, hot, or after the car "
                 "has been sitting a while?",
         "chips": []},
    ],
    "security_immobiliser": [
        {"id": "security_recent",
         "text": "Any key fob battery change, module work, or anything unusual "
                 "around the doors/locks recently?",
         "chips": []},
    ],
}


def state_path() -> Path:
    return state_dir() / "owner_events.jsonl"


def _append(entry: dict[str, Any]) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _raw_records() -> list[dict[str, Any]]:
    p = state_path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def kind_def(category: str, kind: str) -> dict[str, Any]:
    """Raises ``ValueError`` if ``category``/``kind`` is not in :data:`TAXONOMY`."""
    cat = TAXONOMY.get(category)
    if cat is None:
        raise ValueError(f"unknown category {category!r}; use one of: "
                         + ", ".join(TAXONOMY))
    kd = cat["kinds"].get(kind)
    if kd is None:
        raise ValueError(f"unknown kind {kind!r} for category {category!r}; use one of: "
                         + ", ".join(cat["kinds"]))
    return kd


def _parse_iso_or_date(at: Optional[str]) -> str:
    """``at`` may be a full timestamp or a bare date; default is now."""
    s = (at or "").strip()
    if not s:
        return datetime.now().isoformat(timespec="seconds")
    try:
        datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"at must be an ISO date or timestamp, got {at!r}") from exc
    return s


def add(vin: str, category: str, kind: str, *, at: Optional[str] = None,
        by_role: str = "owner", by_name: str = "", fields: Optional[dict[str, Any]] = None,
        note: str = "", media_ids: Optional[list[str]] = None,
        odometer_km: Optional[float] = None,
        fields_meta: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Validate against :data:`TAXONOMY`, stamp and append one owner-event
    row. Raises ``ValueError`` on anything the API layer should turn into a
    400: unknown category/kind, bad role, bad timestamp, note too long.

    ``fields`` is not type-checked field-by-field beyond stringifying and
    length-capping each value -- the taxonomy's per-kind field list is a
    form/display contract, not a second validation gate; the one thing this
    function enforces strictly is that the category/kind itself exists.
    """
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    category = (category or "").strip()
    kind = (kind or "").strip()
    kd = kind_def(category, kind)  # raises on unknown category/kind

    by_role = (by_role or "owner").strip().lower()
    if by_role not in BY_ROLES:
        raise ValueError("by_role must be one of: " + ", ".join(BY_ROLES))

    at_v = _parse_iso_or_date(at)
    note = (note or "").strip()
    if len(note) > MAX_NOTE:
        raise ValueError(f"note must be {MAX_NOTE} characters or fewer")

    clean_fields: dict[str, Any] = {}
    for k, v in (fields or {}).items():
        if v is None:
            continue
        if isinstance(v, bool):
            clean_fields[str(k)] = v
        elif isinstance(v, (int, float)):
            clean_fields[str(k)] = v
        else:
            sv = str(v).strip()
            if sv:
                clean_fields[str(k)] = sv[:MAX_FIELD_TEXT]

    odo = None
    if odometer_km is not None and str(odometer_km).strip() != "":
        try:
            odo = float(odometer_km)
        except (TypeError, ValueError) as exc:
            raise ValueError("odometer_km must be numeric") from exc

    # A meta tag is only kept for a field that (a) actually survived cleaning
    # above -- a source note for a field that was blank/dropped would be a
    # dangling claim about a value never stored -- and (b) is a real field
    # of THIS kind (``kd["fields"]``, the same taxonomy gate ``fields``
    # itself is deliberately NOT held to; ``fields_meta`` is, since it is
    # provenance metadata, not a value, and a stray key here is always a
    # caller bug worth dropping silently rather than storing). The value
    # itself is capped to the two provenance words the UI actually needs:
    # "photo" (read off a picture, not yet confirmed by a human eye) or
    # "typed" (entered by hand) -- anything else is dropped the same way.
    _META_VALUES = {"photo", "typed"}
    clean_meta = {str(k): str(v).strip() for k, v in (fields_meta or {}).items()
                 if str(k) in clean_fields and str(k) in kd["fields"]
                 and str(v).strip() in _META_VALUES}

    entry = {
        "op": "event",
        "id": uuid.uuid4().hex[:12],
        "vin": vin,
        "at": at_v,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "by": {"role": by_role, "name": (by_name or "").strip()[:200]},
        "category": category,
        "kind": kind,
        "fields": clean_fields,
        "fields_meta": clean_meta,
        "note": note,
        "media_ids": [str(m).strip() for m in (media_ids or []) if str(m).strip()],
        "odometer_km": odo,
        "confidence": "reported",
    }
    with _LOCK:
        _append(entry)
    return entry


def delete(id: str) -> dict[str, Any]:
    """Soft-delete: append a ``delete`` amendment. Never rewrites history."""
    eid = (id or "").strip()
    if not eid:
        raise ValueError("id is required")
    with _LOCK:
        rows = _raw_records()
        if not any(r.get("op") == "event" and r.get("id") == eid for r in rows):
            raise ValueError(f"no owner event with id {eid!r}")
        entry = {"op": "delete", "id": eid, "at": datetime.now().isoformat(timespec="seconds")}
        _append(entry)
    return entry


def restore(id: str) -> dict[str, Any]:
    """Undo a soft-delete: append a ``restore`` amendment. The Mobile page's
    own "Undo" action on the post-delete confirmation screen is the only
    caller today; kept here (not a second rewrite of the ``delete`` row)
    for the exact same append-only reason ``delete`` itself documents."""
    eid = (id or "").strip()
    if not eid:
        raise ValueError("id is required")
    with _LOCK:
        rows = _raw_records()
        if not any(r.get("op") == "event" and r.get("id") == eid for r in rows):
            raise ValueError(f"no owner event with id {eid!r}")
        entry = {"op": "restore", "id": eid, "at": datetime.now().isoformat(timespec="seconds")}
        _append(entry)
    return entry


def _clean_one_field(v: Any) -> Any:
    """Same stringify/cap/blank-drops-to-None rule :func:`add` applies to
    every ``fields`` value, reused by :func:`edit` so a hand edit is held to
    the same shape -- ``None`` means "clear this field"."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    sv = str(v).strip()
    return sv[:MAX_FIELD_TEXT] if sv else None


def _fold(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reduce raw ``event``/``delete``/``event_edit`` rows to one current
    view per event id, in append order: every ``event_edit`` for an id is
    applied on top of its ``event`` row in the order it was appended, and
    the folded view carries a ``deleted`` flag and an ``audit`` list (one
    entry per edit: ``at``, ``by``, ``changes``) -- never a rewrite of the
    original rows on disk."""
    deleted: dict[str, bool] = {}
    events: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    edits_by_id: dict[str, list[dict[str, Any]]] = {}
    for rec in rows:
        op = rec.get("op")
        rid = rec.get("id")
        if not rid:
            continue
        if op == "event":
            if rid in events:
                continue
            events[rid] = dict(rec)
            order.append(rid)
        elif op == "delete":
            # A dict toggled in append order (not a write-once set) so a
            # delete -> restore -> delete... history folds correctly
            # regardless of how many times it happened.
            deleted[rid] = True
        elif op == "restore":
            deleted[rid] = False
        elif op == "event_edit":
            edits_by_id.setdefault(rid, []).append(rec)

    out: dict[str, dict[str, Any]] = {}
    for rid in order:
        view = dict(events[rid])
        fields = dict(view.get("fields") or {})
        fields_meta = dict(view.get("fields_meta") or {})
        note = view.get("note", "")
        odometer_km = view.get("odometer_km")
        at = view.get("at")
        audit: list[dict[str, Any]] = []
        for e in edits_by_id.get(rid, []):
            changes = e.get("changes") or {}
            summary: dict[str, Any] = {}
            for k, ch in (changes.get("fields") or {}).items():
                old_v, new_v = ch.get("from"), ch.get("to")
                if new_v is None:
                    fields.pop(k, None)
                    fields_meta.pop(k, None)
                else:
                    fields[k] = new_v
                    if old_v != new_v:
                        # A value actually changed by hand -> no longer the
                        # unconfirmed photo read it may have started as.
                        fields_meta[k] = "typed"
                    # else: edit resubmitted the same value ("kept the
                    # photo value") -- existing fields_meta tag, if any,
                    # is left exactly as it was.
                summary[k] = {"from": old_v, "to": new_v}
            out_changes: dict[str, Any] = {}
            if summary:
                out_changes["fields"] = summary
            if "note" in changes:
                note = changes["note"].get("to", note)
                out_changes["note"] = changes["note"]
            if "odometer_km" in changes:
                odometer_km = changes["odometer_km"].get("to", odometer_km)
                out_changes["odometer_km"] = changes["odometer_km"]
            if "at" in changes:
                at = changes["at"].get("to", at)
                out_changes["at"] = changes["at"]
            audit.append({"at": e.get("at"), "by": e.get("by"), "changes": out_changes})

        view["fields"] = fields
        view["fields_meta"] = fields_meta
        view["note"] = note
        view["odometer_km"] = odometer_km
        view["at"] = at
        view["audit"] = audit
        view["edited_at"] = audit[-1]["at"] if audit else None
        view["deleted"] = deleted.get(rid, False)
        out[rid] = view
    return out


def edit(id: str, *, fields: Optional[dict[str, Any]] = None, note: Optional[str] = None,
        odometer_km: Optional[float] = None, at: Optional[str] = None,
        by_role: str = "owner", by_name: str = "") -> dict[str, Any]:
    """Append an ``event_edit`` amendment changing one or more of
    ``fields``/``note``/``odometer_km``/``at`` on an existing, non-deleted
    event. Never rewrites the original row.

    Raises ``ValueError`` on: no such event, the event is deleted, a key in
    ``fields`` that isn't one of this event's kind's real taxonomy fields,
    a bad ``odometer_km``/``at``, a note over :data:`MAX_NOTE`, or an edit
    that changes nothing at all. The API layer turns "no such event"/
    "deleted" into a 404 and everything else into a 400 -- see
    :func:`cuore.services.owner_events_bridge.edit`.
    """
    eid = (id or "").strip()
    if not eid:
        raise ValueError("id is required")
    by_role = (by_role or "owner").strip().lower()
    if by_role not in BY_ROLES:
        raise ValueError("by_role must be one of: " + ", ".join(BY_ROLES))

    with _LOCK:
        rows = _raw_records()
        current = _fold(rows).get(eid)
        if current is None:
            raise ValueError(f"no owner event with id {eid!r}")
        if current.get("deleted"):
            raise ValueError(f"owner event {eid!r} is deleted")

        kd = kind_def(current["category"], current["kind"])

        changes: dict[str, Any] = {}
        if fields:
            field_changes: dict[str, Any] = {}
            cur_fields = current.get("fields") or {}
            for k, v in fields.items():
                k = str(k)
                if k not in kd["fields"]:
                    raise ValueError(
                        f"unknown field {k!r} for kind {current['kind']!r}; use one of: "
                        + ", ".join(kd["fields"]))
                field_changes[k] = {"from": cur_fields.get(k), "to": _clean_one_field(v)}
            if field_changes:
                changes["fields"] = field_changes
        if note is not None:
            note_v = (note or "").strip()
            if len(note_v) > MAX_NOTE:
                raise ValueError(f"note must be {MAX_NOTE} characters or fewer")
            changes["note"] = {"from": current.get("note", ""), "to": note_v}
        if odometer_km is not None:
            try:
                odo_v: Optional[float] = float(odometer_km)
            except (TypeError, ValueError) as exc:
                raise ValueError("odometer_km must be numeric") from exc
            changes["odometer_km"] = {"from": current.get("odometer_km"), "to": odo_v}
        if at is not None:
            at_v = _parse_iso_or_date(at)
            changes["at"] = {"from": current.get("at"), "to": at_v}

        if not changes:
            raise ValueError("edit must change at least one of: fields, note, odometer_km, at")

        entry = {
            "op": "event_edit",
            "id": eid,
            "at": datetime.now().isoformat(timespec="seconds"),
            "by": {"role": by_role, "name": (by_name or "").strip()[:200]},
            "changes": changes,
        }
        _append(entry)
    return entry


def load(vin: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    """Owner-event rows for ``vin`` (or every vin when empty), oldest ``at``
    first, with every ``event_edit`` folded in (see :func:`_fold`). Deleted
    rows are dropped unless ``include_deleted``."""
    vin = (vin or "").strip()
    with _LOCK:
        rows = _raw_records()
    folded = _fold(rows)

    out: list[dict[str, Any]] = []
    for view in folded.values():
        if view["deleted"] and not include_deleted:
            continue
        if vin and view.get("vin") != vin:
            continue
        out.append(dict(view))
    out.sort(key=lambda r: r.get("at") or "")
    return out


__all__ = ["TAXONOMY", "PROMPT_RULES", "BY_ROLES", "MAX_NOTE", "MAX_FIELD_TEXT",
          "state_path", "kind_def", "add", "delete", "restore", "edit", "load"]


def recent_values(vin: str, kind: str, field: str, limit: int = 6) -> list[str]:
    """Distinct values typed before into a remembered free-text field, most
    recent first: this car's own events first, then the rest of the garage's
    (same shop, same shelf of filters). Attested records only; never a
    suggestion of what *should* be used."""
    seen: list[str] = []
    def take(recs: list[dict[str, Any]]) -> None:
        for e in reversed(recs):
            if e.get("kind") != kind:
                continue
            v = str((e.get("fields") or {}).get(field) or "").strip()
            if v and v.lower() not in {x.lower() for x in seen}:
                seen.append(v)
            if len(seen) >= limit:
                return
    take(load(vin))
    if len(seen) < limit:
        take([e for e in load() if e.get("vin") != vin])
    return seen[:limit]
