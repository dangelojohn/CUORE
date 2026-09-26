"""Reference data: 2018 Alfa Romeo Stelvio 2.0T (US) routine maintenance items.

Read-only reference data -- nothing here touches the corpus or the car. It
is the maintenance-item counterpart to ``mes.service_specs`` (torques,
oil/brakes ledger specs) and ``mes.drivetrain_specs`` (ZF 8HP/Q4/differential
deep dive): this module covers the recurring, mostly-owner-schedule items
(filters, spark plugs, coolant, brake fluid, belts, battery, wipers, fuel
filter, PCV, throttle body, boost hoses, washer fluid, A/C service, power
steering, hood/door lubrication).

Confidence levels (never invented -- an absent value is recorded as
UNKNOWN, never guessed):

* ``CONFIRMED``     -- an actual manufacturer document (owner's manual,
                       Mopar/FCA parts catalog, FCA/Alfa service
                       information, TechAuthority excerpt).
* ``CORROBORATED``  -- two independent non-manufacturer sources agree.
* ``SINGLE_SOURCE`` -- exactly one source found, not cross-checked.
* ``UNKNOWN``       -- nothing credible found. ``value`` is ``None``, never
                       a placeholder number -- ``notes``/``interval_note``
                       always points at the service manual.

Torque values are NOT duplicated here -- ``torque_keys`` on each item points
into ``mes.service_specs.TORQUES`` (e.g. ``spark_plug``) so there is exactly
one place a torque figure can drift out of date.

See ``docs/reference/STELVIO_20T_MAINTENANCE_SPECS.md`` for the
human-readable writeup with the same data and full source links.
"""

from __future__ import annotations

from typing import Any, Optional

# The 2018 US Stelvio owner's manual (the manufacturer document backing every
# CONFIRMED row below unless a row says otherwise), fetched directly from
# FCA/Mopar's own vehicle-info host. Its "Maintenance Plan (2.0 T4 MAir
# Engine)" table (pp. 213-217) and "Fluid Capacities" / "Fluids And
# Lubricants" tables (pp. 262-264) are the source for every OM_URL citation.
OM_URL = ("https://vehicleinfo.mopar.com/assets/publications/en-us/"
          "Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf")

CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNKNOWN = "UNKNOWN"

CONFIDENCE_LEVELS = (CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN)

TECHAUTHORITY = "use the service manual (TechAuthority)"

VEHICLE = ("2018 Alfa Romeo Stelvio 2.0T (GU), 2.0L GME-T4 MultiAir turbo, "
           "sales code EC2, US market, Q4 AWD, ZF 8HP automatic")

CATEGORIES: tuple[str, ...] = (
    "engine", "fluids", "filters", "ignition", "electrical", "body",
)

REQUIRED_KEYS: tuple[str, ...] = (
    "key", "label", "category",
    "interval_miles", "interval_km", "interval_months",
    "interval_note", "interval_confidence", "interval_source",
    "parts", "fluid", "torque_keys",
    "procedure", "checks", "post_service", "notes",
)

ITEM_ORDER: tuple[str, ...] = (
    "engine_air_filter", "cabin_air_filter", "spark_plugs",
    "ignition_coils_inspect", "coolant", "brake_fluid", "drive_belt",
    "battery_12v", "wipers", "fuel_filter", "pcv_system",
    "throttle_body_clean", "intake_boost_hoses_inspect", "washer_fluid",
    "a_c_cabin_service", "power_steering", "hood_and_door_lubrication",
)


ITEMS: dict[str, dict[str, Any]] = {}


def _part(name: Optional[str] = None, part_number: Optional[str] = None,
          confidence: str = UNKNOWN, source: Optional[str] = None,
          notes: str = "") -> dict[str, Any]:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r}")
    if not notes and confidence == UNKNOWN:
        notes = TECHAUTHORITY
    return {
        "name": name, "part_number": part_number, "confidence": confidence,
        "source": source, "notes": notes.strip(),
    }


def _fluid(spec: Optional[str] = None, capacity: Optional[float] = None,
           unit: Optional[str] = None, confidence: str = UNKNOWN,
           source: Optional[str] = None, notes: str = "") -> dict[str, Any]:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r}")
    if not notes and confidence == UNKNOWN:
        notes = TECHAUTHORITY
    return {
        "spec": spec, "capacity": capacity, "unit": unit,
        "confidence": confidence, "source": source, "notes": notes.strip(),
    }


def _item(key: str, label: str, category: str, *,
          interval_miles: Optional[int] = None,
          interval_km: Optional[int] = None,
          interval_months: Optional[int] = None,
          interval_note: str = "",
          interval_confidence: str = UNKNOWN,
          interval_source: Optional[str] = None,
          parts: Optional[list[dict[str, Any]]] = None,
          fluid: Optional[dict[str, Any]] = None,
          torque_keys: Optional[list[str]] = None,
          procedure: Optional[list[str]] = None,
          checks: Optional[list[str]] = None,
          post_service: Optional[list[str]] = None,
          notes: str = "") -> None:
    if category not in CATEGORIES:
        raise ValueError(f"bad category {category!r}")
    if interval_confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {interval_confidence!r}")
    if not interval_note and interval_confidence == UNKNOWN:
        interval_note = TECHAUTHORITY
    ITEMS[key] = {
        "key": key,
        "label": label,
        "category": category,
        "interval_miles": interval_miles,
        "interval_km": interval_km,
        "interval_months": interval_months,
        "interval_note": interval_note.strip(),
        "interval_confidence": interval_confidence,
        "interval_source": interval_source,
        "parts": parts or [],
        "fluid": fluid,
        "torque_keys": torque_keys or [],
        "procedure": procedure or [],
        "checks": checks or [],
        "post_service": post_service or [],
        "notes": notes.strip(),
    }


# --- items, in the specified order (initially UNKNOWN/None throughout;
#     filled in by the research pass below) ---------------------------------

_item(
    "engine_air_filter", "Engine air filter", "filters",
    interval_miles=30000, interval_km=48000, interval_months=36,
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual 'Maintenance Plan (2.0 T4 MAir Engine)' row "
        "'Replace air cleaner cartridge': mandatory at 30,000/60,000/90,000/"
        "120,000/150,000 miles (3/6/9/12/15 years) -- every 30,000 miles or "
        "3 years, whichever comes first. Severe-duty override (footnote, "
        "shared with the cabin filter): dusty-area use requires replacement "
        "every 10,000 miles (16,000 km) instead."),
    parts=[_part(
        name="Engine air filter (2.0L, non-Quadrifoglio)",
        part_number="68301538AA", confidence=CORROBORATED,
        source="https://www.moparonlineparts.com/sku/68301538aa.html",
        notes="Cross-referenced consistently across Mopar Online Parts, "
              "madnessautoworks, AW Italian Auto Parts, and aftermarket "
              "equivalents (WIX WA11084, Champion CA12953, Fram XA10670, "
              "PurolatorAir A11523, Premium Guard PA99467) for 2018-2020 "
              "Stelvio/Giulia 2.0L non-QV. Confirm no running change for "
              "later model years at a parts counter by VIN.")],
    procedure=["Release the air box clips/screws and lift the lid.",
               "Note the pleated element's orientation before removing it.",
               "Wipe out the air box; fit the new element the same way "
               "round.",
               "Reseat the lid and clips; confirm the intake duct/MAF "
               "connector is fully seated."],
    checks=["Filter element condition (oil/dust contamination -- heavy "
            "oiling can point at a recent intake leak or PCV oil-"
            "carryover)", "Air box and duct clips for cracks"],
    post_service=["None required -- no relearn/adaptation needed for an "
                  "air filter change."],
    notes="The owner's manual has no row literally labelled 'engine air "
          "filter' -- this is its 'air cleaner cartridge' row.",
)

_item(
    "cabin_air_filter", "Cabin air filter", "filters",
    interval_miles=20000, interval_km=32000, interval_months=24,
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual 'Replace the passenger compartment cleaner' row: "
        "MANDATORY at 20,000/40,000/60,000/80,000/100,000/120,000/140,000 "
        "miles (2/4/6/8/10/12/14 years) -- every 20,000 miles or 2 years. "
        "RECOMMENDED (not mandatory) check/replace at the intervening "
        "10,000-mile odd points (10k/30k/50k/70k/90k/110k/130k/150k). "
        "Severe-duty override (same footnote as the engine air filter): "
        "dusty-area use requires replacement every 10,000 miles "
        "(16,000 km)."),
    parts=[_part(
        name="Cabin air filter", part_number="68444656AA",
        confidence=SINGLE_SOURCE,
        source="https://www.moparonlineparts.com/part-model/alfa-romeo-stelvio-cabin-air-filter.html",
        notes="Three different Mopar part numbers turned up across "
              "retailer listings for nominally the same 2018-2025 Stelvio "
              "cabin filter -- 68444656AA, 68392124AA, and (a separate "
              "search) 68320112AA -- with no documented year/trim split. "
              "Confirm the correct number for this VIN at a Mopar parts "
              "counter before ordering.")],
    procedure=["Locate the cabin filter housing (commonly behind the "
               "glovebox on this platform).",
               "Release the housing cover and slide the old filter out, "
               "noting airflow-direction arrows.",
               "Fit the new filter with the same orientation; reseat the "
               "cover."],
    checks=["Airflow-direction arrow orientation", "Debris/leaf litter in "
            "the housing", "Musty-odor complaints (may indicate a filter "
            "overdue for replacement or evaporator contamination)"],
    post_service=["None required."],
    notes="",
)

_item(
    "spark_plugs", "Spark plugs", "ignition",
    interval_miles=30000, interval_km=48000, interval_months=None,
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual 'Maintenance Plan' row 'Spark plug replacement': "
        "mandatory at 30,000/60,000/90,000/120,000/150,000 miles. Its own "
        "footnote: 'The spark plug change interval is mileage-based only. "
        "Yearly intervals do not apply.' -- deliberately no interval_months "
        "value here, not an oversight."),
    parts=[_part(
        name="Spark plug (2.0L, set of 4)",
        part_number="NGK 90219 (ILZKR7G7G) / Mopar 68292346AA",
        confidence=CORROBORATED,
        source="https://www.ngk.com/ngk-90219-ilzkr7g7g-laser-iridium-spark-plug",
        notes="NGK's own listing plus multiple independent parts "
              "retailers (PartsGeek, Alfa Corsa, Eurocompulsion, "
              "madnessautoworks) agree on NGK 90219 / Mopar 68292346AA for "
              "the 2018-2024 2.0L. Gap: NGK's own spec sheet gives "
              "0.028 in (0.7 mm); a second, less authoritative listing "
              "gave 0.026 in -- plugs ship pre-gapped from the factory, "
              "verify with a gap tool before installing rather than "
              "trusting either figure blindly."),
    ],
    torque_keys=["spark_plug"],
    procedure=["Remove the engine cover and disconnect each ignition coil "
               "connector.",
               "Remove the coil retaining bolt/screw and pull each coil "
               "straight up.",
               "Blow out the plug wells before removing plugs to keep "
               "debris out of the cylinder.",
               "Remove and inspect each plug; gap-check new plugs before "
               "installing even though they ship pre-gapped.",
               "Torque to spec (see mes.service_specs TORQUES['spark_plug'])"
               " and reinstall coils/connectors."],
    checks=["Electrode wear/color per cylinder (uneven wear across "
            "cylinders can point at a cylinder-specific issue)",
            "Thread condition in the aluminum head on removal"],
    post_service=["No relearn required. Do not add anti-seize unless the "
                  "plug maker specifies it -- it changes effective seating "
                  "torque on this aluminum head (see the spark_plug torque "
                  "row's own notes in mes.service_specs)."],
    notes="",
)

_item(
    "ignition_coils_inspect", "Ignition coils (inspect)", "ignition",
    interval_confidence=UNKNOWN,
    interval_note=(
        "Not listed as a scheduled item anywhere in the 2018 US owner's "
        "manual maintenance plan -- coils on this engine are inspected/"
        "diagnosed on symptoms (misfire codes), not replaced on a fixed "
        "interval. " + TECHAUTHORITY),
    torque_keys=["coil_pack_bolt"],
    checks=["Misfire/DTC history per cylinder",
            "Coil boot condition and carbon tracking",
            "Spark plug well for oil intrusion (a common cause of coil "
            "boot arcing on MultiAir-family engines)"],
    procedure=["Disconnect the coil connector and remove its retaining "
               "bolt/screw before pulling it straight up off the plug."],
    notes="No sourced part number for this pass; do not order a coil "
          "speculatively -- confirm the failing cylinder via live misfire "
          "counters first.",
)

_item(
    "coolant", "Engine coolant", "fluids",
    interval_miles=150000, interval_km=240000, interval_months=180,
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual 'Maintenance Plan' marks a single mandatory "
        "coolant change at 150,000 miles (240,000 km) / 15 years -- a "
        "long-life OAT fill, not a periodic service item at normal "
        "intervals. The monthly/600-mile 'Periodic Checks' item is a "
        "level/top-off check only, not a change."),
    fluid=_fluid(
        spec="FCA/Alfa MS.90032 (CUNA NC956-16, ASTM D3306) OAT coolant, "
             "used at 50% concentration; NOT mixable with different-"
             "formulation coolants; a 60% product / 40% distilled-water "
             "mix is recommended for particularly harsh climates",
        capacity=8.8, unit="L", confidence=CONFIRMED, source=OM_URL,
        notes="Owner's manual 'Fluid Capacities' table: engine cooling "
              "system 2.3 US gal / 8.8 L. This is the ENGINE circuit only "
              "-- the water-cooled intercooler on this turbo engine has "
              "its OWN separate cooling circuit at 1.4 US gal / 5.25 L, "
              "not included in this figure. Independently, stelvioforum/"
              "Petronas Paraflu UP threads name the same MS.90032 spec, "
              "corroborating spec identity even though the manual is now "
              "the primary CONFIRMED source for both spec and capacity."),
    torque_keys=[],
    checks=["Level at the engine coolant reservoir (MIN/MAX)",
            "Level at the SEPARATE intercooler coolant reservoir",
            "Condition/color for contamination or oil intrusion"],
    procedure=["Recover coolant into a clean container if reusing.",
               "Drain the engine circuit (drain point/plug not sourced "
               "this pass -- see notes).",
               "Refill with MS.90032-spec coolant only; do not mix "
               "formulations.",
               "Bleed per the correct procedure for this engine (not "
               "sourced this pass) and verify final level cold."],
    post_service=["No relearn needed. No sourced bleed procedure or "
                  "drain-plug location for the 2.0T engine circuit this "
                  "pass -- " + TECHAUTHORITY],
    notes="Remember the intercooler circuit is a SEPARATE fill/bleed from "
          "the engine circuit on this engine.",
)

_item(
    "brake_fluid", "Brake fluid", "fluids",
    interval_months=24, interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual footnote on the Maintenance Plan: 'The brake fluid "
        "replacement has to be done every two years, irrespective of the "
        "mileage.' No mileage bullet/mark appears in the table for this "
        "row -- it is purely calendar-based. This is a firmer source than "
        "mes.service_specs.BRAKE_SPEC['fluid_change_interval'], which is "
        "still recorded there as SINGLE-SOURCE forum-only; that module is "
        "out of scope for this pass and has not been updated to match."),
    fluid=_fluid(
        spec="DOT 4, FCA spec MS.90039", capacity=0.9, unit="L",
        confidence=CONFIRMED, source=OM_URL,
        notes="Owner's manual 'Fluids And Lubricants' table gives DOT 4 / "
              "MS.90039 explicitly. 'Fluid Capacities' table gives the "
              "hydraulic brake circuit at 0.9 US qt / 0.9 L -- reservoir + "
              "lines, not a drain-and-refill service quantity."),
    torque_keys=[],
    checks=["Fluid color/clarity", "Moisture content if a test kit is "
            "available", "Reservoir level vs MIN/MAX -- also monitored by "
            "the INSUFFICIENT BRAKE FLUID/ELECTRIC PARK BRAKE telltale per "
            "the owner's manual"],
    post_service=["Bleed all four corners plus the ABS/ESC modulator. On "
                  "EPB-equipped rear calipers, put the EPB into service "
                  "mode before disturbing the rear circuit -- see "
                  "mes.service_specs.BRAKE_SPEC['epb_service_mode']."],
)

_item(
    "drive_belt", "Drive (serpentine) belt", "engine",
    interval_miles=36000, interval_km=60000, interval_months=48,
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual footnote on the Maintenance Plan: non-dusty areas, "
        "recommended max 36,000 miles (60,000 km), and regardless of "
        "mileage replace every 4 years. Dusty/demanding use (cold "
        "climates, town use, long periods of idling): advised max 18,000 "
        "miles (30,000 km), replace every 2 years regardless of mileage. "
        "This item's interval_miles/interval_km/interval_months record the "
        "NORMAL-duty figure; treat 18,000 mi / 30,000 km / 24 months as "
        "the floor for a car used hard."),
    parts=[_part(
        name="Accessory (serpentine) drive belt", part_number="68326261AA",
        confidence=SINGLE_SOURCE,
        source="https://awitalian.com/product/alfa-romeo-giulia-stelvio-serpentine-drive-belt-68326261aa/",
        notes="Single aftermarket-retailer listing for the 2018-2022 2.0L; "
              "not cross-checked against a second retailer or a "
              "Mopar-direct listing this pass.")],
    checks=["Visible cracking, glazing, or fraying",
            "Tensioner/idler pulley play and noise",
            "Correct routing per the underhood belt-routing decal"],
    procedure=["Relieve the tensioner (per the underhood routing decal) "
               "and slip the belt off the accessory pulleys.",
               "Inspect the tensioner and idler pulleys for play/noise "
               "before reusing them.",
               "Route the new belt per the decal; release the tensioner "
               "slowly onto the belt."],
    post_service=["None required."],
)

_item(
    "battery_12v", "12V battery", "electrical",
    interval_miles=10000, interval_km=16000, interval_months=12,
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual 'Maintenance Plan' row 'Check battery charge "
        "status with the proper instrument' is MANDATORY at every one of "
        "the 10,000-mile/1-year columns -- i.e. every service visit. "
        "Outright battery REPLACEMENT has no fixed FCA interval -- it is "
        "condition/age driven (load-test failure), not scheduled."),
    parts=[_part(
        name="12V battery (factory-fit EFB standard; AGM on some builds/"
             "replacements; BCI Group 94R / H7)",
        part_number="Mopar BBH8A001AA (AGM, reported to cross to Group "
                     "94R)",
        confidence=SINGLE_SOURCE,
        source="https://www.stelvioforum.com/threads/mopar-replacement-battery.9201/",
        notes="Group-size naming is inconsistent across sources (94R vs "
              "H7 vs 49/H8 all used loosely by different posters for what "
              "is described as the same physical battery) -- confirm "
              "physical dimensions/terminal layout against the battery "
              "actually fitted before ordering, not just a group code. If "
              "the car left the factory with AGM (Start/Stop-equipped), "
              "do not downgrade to a plain flooded/EFB battery on "
              "replacement.")],
    torque_keys=["battery_terminal", "battery_hold_down"],
    checks=["Charge status/state of health with a proper tester (owner's "
            "manual wording)", "Terminal corrosion/tightness",
            "Hold-down clamp secure"],
    post_service=[
        "No explicit 'register battery replacement' procedure was found "
        "for this platform: a stelvioforum thread ('Register Battery "
        "Replacement') reports MES/wiTECH have no such function here "
        "(unlike some other FCA-group platforms) -- the charging-system "
        "monitor recalibrates itself over a period of hours after "
        "reconnection, with no separate registration step to run.",
        "After any battery disconnect, expect to reset the clock and "
        "re-run any one-touch window/sunroof auto-up/down "
        "initialization.",
    ],
    notes=(
        "CORRECTION to the common assumption of a main+auxiliary battery "
        "pair on Start/Stop cars: research this pass (alfaowner.com "
        "'second battery location'; giuliaforums.com 'is there really a "
        "separate battery for start/stop') found this platform uses a "
        "SINGLE 12V battery (trunk-mounted, under the floor panel) for "
        "both normal electrical loads and the Start/Stop system -- no "
        "second/auxiliary battery is documented for the Stelvio. If a "
        "specific VIN is found to have one, that is new information to "
        "update here, not something to assume. Also note: this vehicle's "
        "own owner's manual uses the acronym 'IBS' for the unrelated "
        "'Integrated Brake System' -- do not confuse that with an "
        "'Intelligent Battery Sensor', a term used loosely for this kind "
        "of battery-monitor topic on other platforms but not confirmed to "
        "apply here by name."
    ),
)

_item(
    "wipers", "Wiper blades", "body",
    interval_months=12, interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual: 'The life of the windshield wiper blades varies "
        "according to the usage frequency. In any case, it is advised to "
        "replace the blades approximately once a year.' No mileage figure "
        "given."),
    parts=[
        _part(name="Front wiper blades (driver 26in/660mm, passenger "
                    "18in/460mm)",
              part_number=None, confidence=CORROBORATED,
              source="https://autopadre.com/wiper-size/alfa-romeo-stelvio",
              notes="Sizes corroborated across multiple independent "
                    "wiper-fitment databases (autopadre, "
                    "windshieldwipers.com, allwipersize.com, "
                    "wipersizechart.com) for 2018-2026. No confidently-"
                    "sourced Mopar OEM part number found this pass -- "
                    "candidates seen (68462474AA, 68357040AA) were listed "
                    "for a REAR wiper arm/blade assembly, not the front "
                    "blades, and were not clearly confirmed for this "
                    "model year. Confirm at a parts counter by VIN."),
        _part(name="Rear wiper blade (13in/330mm)",
              part_number=None, confidence=CORROBORATED,
              source="https://autopadre.com/wiper-size/alfa-romeo-stelvio",
              notes="Same corroboration as the front blades. "
                    "68462474AA/68357040AA were seen for a rear wiper arm/"
                    "blade listing but not confirmed for this VIN's model "
                    "year -- confirm before ordering."),
    ],
    checks=["Blade edge for cracking/tearing", "Chatter/streaking/noise",
            "Rain-sensor auto-wipe operation"],
    procedure=["Activate the windshield-wiper 'service position' function "
               "(owner's manual) before replacing blades for easier "
               "access.",
               "Release the hook/pinch-tab retainer per blade type and "
               "slide the old blade off the arm.",
               "Fit the new blade until it clicks/locks; lower the arm "
               "back onto the glass."],
    post_service=["None."],
)

_item(
    "fuel_filter", "Fuel filter", "filters",
    interval_confidence=CORROBORATED,
    interval_source="https://www.stelvioforum.com/threads/fuel-filter.10613/",
    interval_note=(
        "No separate serviceable fuel filter on the US gas 2.0T: forum "
        "consensus (independent stelvioforum threads 'Fuel Filter' and "
        "'Fuel Filter Service') describes an in-tank fuel filter 'sock' "
        "integrated into the fuel pump module -- non-serviceable except by "
        "replacing the whole module, and with no scheduled replacement "
        "interval. This is corroborated by the owner's manual itself, "
        "which lists a SEPARATE maintenance-plan row, 'Replace the "
        "additional fuel filter (if equipped)', mandatory every 10,000 "
        "miles -- the 'if equipped' phrasing implies that additional, "
        "serviceable filter is NOT fitted to every variant, and nothing "
        "in this research pass found evidence the US gas 2.0T carries it. "
        "Deliberately no interval_miles/km/months here -- this is a "
        "lifetime, non-serviceable-on-schedule item as best "
        "established, not an unresearched gap."),
    notes="Do not confuse this with the owner's manual's own 'additional "
          "fuel filter (if equipped)' row -- if a specific VIN is "
          "confirmed to have that filter fitted, its interval is every "
          "10,000 miles per the manual, which would supersede the note "
          "above for that car.",
)

_item(
    "pcv_system", "PCV (crankcase ventilation) system", "engine",
    interval_confidence=UNKNOWN,
    interval_note=(
        "Not listed in the owner's manual maintenance plan -- no "
        "scheduled interval; PCV components on this engine are treated as "
        "inspect/replace-on-failure (oil consumption, rough idle, "
        "crankcase-pressure DTCs). " + TECHAUTHORITY),
    parts=[_part(
        name="PCV valve/housing", part_number="04893610AC",
        confidence=SINGLE_SOURCE,
        source="https://www.alfaromeofiatpartsusa.com/oem-parts/mopar-genuine-oem-pcv-valve-alfa-romeo-giulia-stelvio-jeep-dodge-hornet-wrangler-compass-cherokee-4893610ac",
        notes="Listed as a shared Mopar part across Giulia/Stelvio 2.0L "
              "(2018-2026) plus several Jeep/Dodge products -- plausible "
              "for a corporate-parts-bin PCV valve, but not independently "
              "cross-checked against a second retailer this pass. Do NOT "
              "use 68324751AA -- that is the 2.9L V6 (Quadrifoglio) PCV "
              "valve and housing, a different part for a different "
              "engine.")],
    checks=["Oil residue/oil consumption pointing at PCV oil-carryover",
            "Rough/unstable idle or a lean DTC that could indicate a "
            "stuck-open valve or a split hose",
            "Crankcase breather hose condition"],
)

_item(
    "throttle_body_clean", "Throttle body cleaning", "engine",
    interval_confidence=UNKNOWN,
    interval_note=(
        "No scheduled throttle-body-cleaning interval in the owner's "
        "manual -- this engine's factory maintenance plan does not list "
        "it. Aftermarket/forum guidance around 60,000 miles, or 'clean if "
        "symptomatic' (hesitation, carbon buildup), was found but not "
        "traced to a specific, checkable source -- treat as unsourced "
        "shop practice, not an OEM figure. " + TECHAUTHORITY),
    checks=["Idle quality / hesitation complaints",
            "Visible carbon on the throttle plate and bore"],
    post_service=["An electronic throttle body relearn/adaptation is "
                  "commonly required after cleaning or replacing the "
                  "throttle body on Alfa Romeo platforms generally -- "
                  "confirm the exact MES/wiTECH procedure before "
                  "returning the car; not independently verified against "
                  "a Stelvio-specific source this pass."],
)

_item(
    "intake_boost_hoses_inspect", "Intake / boost hoses (inspect)", "engine",
    interval_confidence=UNKNOWN,
    interval_note=(
        "No scheduled inspection interval for the intake/boost (charge-"
        "air) hoses in the owner's manual -- inspection is symptom-driven "
        "(underboost DTCs such as P0299/P0236, a whistling/whooshing "
        "noise, boost coming in later in the rev range). "
        + TECHAUTHORITY),
    parts=[_part(
        name="Turbo-to-intercooler hose (a commonly cited failure point "
             "on this engine family)",
        part_number="00500536260", confidence=SINGLE_SOURCE,
        source="https://www.go-parts.com/garage/engine-intake-manifold-alfa-romeo-stelvio-quadrifoglio-alfa-romeo-giulia-2017-2024",
        notes="Single aftermarket-parts-vendor article; plastic/rubber "
              "charge pipes on this engine are reported prone to cracking "
              "from heat and vibration. Not cross-checked against a Mopar "
              "listing this pass.")],
    checks=["Flex/scrunch-test each hose by hand for cracks or soft "
            "spots", "Smoke test if a leak is suspected but not visible",
            "Clamp tightness at each joint"],
)

_item(
    "washer_fluid", "Washer fluid", "fluids",
    interval_miles=600, interval_km=1000, interval_months=1,
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual 'Periodic Checks': check and top off windshield "
        "washer fluid level every month or every 600 miles (1,000 km) or "
        "before long trips. This is a TOP-OFF check, not a 'change' "
        "interval -- washer fluid is not periodically drained/replaced."),
    fluid=_fluid(
        spec="CUNA NC 956-11, FCA spec MS.90043; usable diluted or "
             "undiluted", capacity=4.1, unit="L", confidence=CONFIRMED,
        source=OM_URL,
        notes="Owner's manual 'Fluid Capacities' (1.1 US gal / 4.1 L) and "
              "'Fluids And Lubricants' (spec MS.90043) tables."),
    checks=["Reservoir level", "Nozzle spray pattern/aim",
            "Headlight washer operation, if equipped"],
    post_service=["None."],
)

_item(
    "a_c_cabin_service", "A/C system / cabin service (R-1234yf)", "fluids",
    interval_months=12, interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual: 'To ensure the best possible performance, the "
        "air conditioning system must be checked and undergo maintenance "
        "at an authorized dealer at the beginning of the summer.' Annual, "
        "seasonal -- no mileage figure. The manual also warns not to use "
        "chemicals to clean the A/C system (may damage internal "
        "components, not covered by warranty) and to use only approved "
        "refrigerants/compressor lubricants."),
    fluid=_fluid(
        spec="R-1234yf refrigerant only -- NEVER R-134a or R-12, which "
             "are incompatible with this system's components",
        capacity=535, unit="g", confidence=CORROBORATED,
        source="https://top-refrigerants.com/en/r134a-r1234yf-vehicle-refrigerant-quantity-table",
        notes="Refrigerant TYPE (R-1234yf) is CONFIRMED directly from the "
              "owner's manual's 'Fluids And Lubricants' table, which "
              "lists no charge weight. Charge weight (535 +/-20 g) is "
              "from an industry refrigerant-quantity reference (chassis "
              "code 949, MY 12.16 on), corroborated by a second "
              "aggregator (originaldiag.com) independently citing ~530 g "
              "-- neither is an FCA document, so this is CORROBORATED at "
              "the aggregator level, not CONFIRMED. Verify against the "
              "underhood A/C system label on this specific car before "
              "charging. Compressor oil type/amount not sourced this "
              "pass."),
    checks=["Cooling performance / vent temperature",
            "Refrigerant charge (dealer evacuate-and-weigh, not a sight "
            "glass)",
            "Cabin/pollen filter condition -- often serviced together, "
            "see the cabin_air_filter item"],
    notes="Compressor oil type/amount not sourced this pass -- confirm "
          "via TechAuthority before opening the system.",
)

_item(
    "power_steering", "Power steering (EPS)", "fluids",
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual 'Technical Specifications > Steering' states: "
        "'Rack and pinion with electric power steering.' No power-"
        "steering-fluid entry appears anywhere in the 'Fluids And "
        "Lubricants' or 'Fluid Capacities' tables (contrast with the "
        "brake/coolant/washer-fluid rows, which ARE listed there). THERE "
        "IS NO HYDRAULIC POWER-STEERING FLUID ON THIS CAR -- do not add "
        "or attempt to bleed one. The Enhanced Accident Response System "
        "procedure's own step, 'Cut off battery power to the ... Electric "
        "power steering', further confirms it is electrically, not "
        "hydraulically, actuated. No scheduled maintenance item -- "
        "deliberately no interval_miles/km/months here."),
    checks=["EPS-related warning lights/DTCs -- steering assist is tied "
            "to 12V system health; a weak/failing battery has been "
            "reported (stelvioforum) to cause intermittent 'power "
            "steering disabled' warnings on this platform"],
    notes="Listed for completeness since 'power steering fluid' is "
          "commonly and incorrectly assumed to be a serviceable item on "
          "this car -- there is nothing to service.",
)

_item(
    "hood_and_door_lubrication", "Hood and door hinge/latch lubrication",
    "body",
    interval_miles=20000, interval_km=32000, interval_months=24,
    interval_confidence=CONFIRMED, interval_source=OM_URL,
    interval_note=(
        "Owner's manual 'Maintenance Plan' row 'Check cleanliness of hood "
        "and luggage compartment locks, cleanliness and lubrication of "
        "linkage': mandatory at 20,000/40,000/60,000/80,000/100,000/"
        "120,000/140,000 miles (2/4/6/8/10/12/14 years) -- every 20,000 "
        "miles or 2 years. The manual's own wording covers the HOOD and "
        "LIFTGATE/LUGGAGE-COMPARTMENT lock linkage specifically -- it "
        "does NOT separately call out DOOR hinges/latches on this "
        "schedule; treat door-hinge lubrication as good practice, not a "
        "documented FCA interval. Under the manual's 'Heavy Usage' "
        "conditions (dusty roads, short cold-start trips, extended "
        "idling/long low-speed driving, long inactivity), this check is "
        "called out to be done 'more often than indicated in the "
        "Scheduled Servicing Plan' with no specific alternate mileage "
        "given."),
    procedure=["Clean the hood and liftgate/luggage-compartment lock "
               "mechanisms and strikers.",
               "Apply a light machine oil or lithium grease to the lock "
               "linkage and hinges (specific product not called out by "
               "the owner's manual).",
               "Cycle the hood/liftgate through several full open/close "
               "cycles to work lubricant into the mechanism."],
    checks=["Lock/latch operation (full engagement, no double-pull)",
            "Hinge squeak or binding", "Corrosion at the striker or "
            "latch"],
    post_service=["None."],
    notes="See interval_note for the hood/liftgate-vs-door-hinge scope "
          "caveat -- door hinges specifically are not this manual's own "
          "documented item.",
)


def item(key: str) -> dict[str, Any]:
    """Return the item dict for ``key``. Raises ``KeyError`` if unknown."""
    return dict(ITEMS[key])


def items_by_category() -> dict[str, list[dict[str, Any]]]:
    """All items grouped by category, each group in ``ITEM_ORDER`` order."""
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for key in ITEM_ORDER:
        row = ITEMS[key]
        out[row["category"]].append(dict(row))
    return out


__all__ = [
    "CONFIRMED", "CORROBORATED", "SINGLE_SOURCE", "UNKNOWN",
    "CONFIDENCE_LEVELS", "TECHAUTHORITY", "VEHICLE", "CATEGORIES",
    "REQUIRED_KEYS", "ITEM_ORDER", "ITEMS", "item", "items_by_category",
]
