"""Physical layout: elements, paths and interactions for the OTHER systems
on the 2018 Alfa Romeo Stelvio 2.0T (GU) -- everything in :mod:`mes.systems`
that is not electrical architecture (that is :mod:`mes.electrical`'s job).

Companion to :mod:`mes.electrical`: that module answers "where is the wire,
what feeds it, what should I meter"; this module answers "where is the
*part*, physically, in the car" for fuel, EVAP, air intake/boost, cooling,
lubrication, exhaust/emissions, transmission/driveline, brakes/ABS,
steering, suspension, body/comfort, ADAS sensors and HVAC.

Same element schema as :mod:`mes.electrical` on purpose -- a client that
already renders ``electrical.ELEMENTS`` rows can render these with no
special-casing: ``{kind, label, location: {zone, description, source,
confidence}, feeds, part_of_systems, tsb_refs, inspection_hint, notes}``.
``ZONES`` and the confidence vocabulary (``CONFIRMED``/``SINGLE_SOURCE``/
``INFERRED``/``UNKNOWN``) are imported from :mod:`mes.electrical` directly,
not re-typed, so both modules always agree on what a zone or a confidence
level means. ``KINDS`` is NOT imported: electrical's kind vocabulary
(fuse/relay/ground/connector/...) describes electrical hardware; this
module's elements are mechanical/hydraulic/pneumatic parts, so it defines
its own kind vocabulary below, following the same validation pattern.

House rule, unchanged from :mod:`mes.electrical`: no panel location, hose
routing detail or torque spec is ever invented. Where this repo's own docs
and TSBs do not say it, this module says ``UNKNOWN`` and points at the
service manual (TechAuthority).

Sources used here (nothing outside this repo's already-researched corpus):

* ``docs/research/EVAP_STELVIO.md`` -- canister siting, ESIM-vs-canister
  architecture, purge dual-path (off-boost manifold vacuum / on-boost
  ejector-tee), quick-connect check points, canister filter.
* ``docs/reference/GIORGIO_MODULE_MAP.md`` -- which modules exist and on
  which bus (network topology, not physical mounting -- physical location
  stays UNKNOWN unless some other source states it).
* ``mes.maintenance_specs`` -- intercooler's separate coolant circuit/
  reservoir, no serviceable fuel filter on the US gas 2.0T, coolant spec/
  capacity, EPB brake-fluid note.
* ``mes.drivetrain_specs`` -- ZF 8HP pan/filter (integrated, not separately
  serviceable), transfer case/differential drain-fill points, mounts.
* ``mes.parts`` -- part-level location strings already researched for the
  canister, ESIM, purge valve, quick-connect, turbo/intercooler hose, oil
  filter housing, drain plug, cabin air filter, TPMS sensor, drive belt.
* ``mes.systems`` -- the system component lists this module's
  ``part_of_systems`` values must stay inside (checked by this repo's own
  tests, not by this module at import time).
* ``mes.modules`` -- EPB/ABS integration note (EPB caliper actuators exist,
  but Giorgio's park-brake function is driven by the ABS/ESC module, not a
  standalone EPB controller).
"""

from __future__ import annotations

from typing import Any, Optional

from .electrical import (
    CONFIRMED, SINGLE_SOURCE, INFERRED, UNKNOWN, CONFIDENCE_LEVELS,
    TECHAUTHORITY, ZONES,
)
from . import electrical as _electrical

#: Used only in ``systems_interaction`` entries (cross-system relations),
#: never in an element's own ``location.confidence`` -- that field is
#: restricted to electrical.py's four-value vocabulary via ``_loc``'s
#: validation below. Mirrors ``mes.systems``' own confidence vocabulary,
#: which also distinguishes "two independent sourced findings agree" from
#: a single source.
CORROBORATED = "CORROBORATED"

#: This module's own kind vocabulary -- physical/mechanical/hydraulic/
#: pneumatic parts, distinct from electrical.KINDS (electrical hardware).
KINDS = (
    "tank", "cap", "line", "hose", "filter", "valve", "sensor", "pump",
    "reservoir", "housing", "component", "module", "mount",
)

_EVAP_DOC = "docs/research/EVAP_STELVIO.md"
_MODULE_MAP = "docs/reference/GIORGIO_MODULE_MAP.md"


def _loc(zone: str, description: str, source: str,
         confidence: str = UNKNOWN) -> dict[str, Any]:
    if zone not in ZONES:
        raise ValueError(f"unknown zone {zone!r}")
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"unknown confidence {confidence!r}")
    if confidence == UNKNOWN and TECHAUTHORITY not in description:
        description = description.rstrip(". ") + f". {TECHAUTHORITY}."
    return {"zone": zone, "description": description, "source": source,
            "confidence": confidence}


def _unknown_loc(note: str = "") -> dict[str, Any]:
    desc = "UNKNOWN -- not sourced in this repo's TSBs or docs."
    if note:
        desc += " " + note
    return _loc("unknown", desc, source="none", confidence=UNKNOWN)


def _el(kind: str, label: str, location: dict[str, Any],
        feeds: Optional[list[str]] = None,
        part_of_systems: Optional[list[str]] = None,
        tsb_refs: Optional[list[str]] = None,
        inspection_hint: str = "", notes: str = "") -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    return {
        "kind": kind, "label": label, "location": location,
        "feeds": list(feeds or []),
        "part_of_systems": list(part_of_systems or []),
        "tsb_refs": list(tsb_refs or []),
        "inspection_hint": inspection_hint or "not specified -- visual "
                           "inspection for leaks, chafe, cracking or "
                           "restriction",
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# ELEMENTS
# ---------------------------------------------------------------------------

ELEMENTS: dict[str, dict[str, Any]] = {

    # --- fuel ----------------------------------------------------------------

    "fuel_tank": _el(
        "tank", "Fuel tank",
        _loc("underbody",
             "Not stated as a panel location by any source in this repo, "
             "but TSB 9100471's remedy instructs 'drop the Fuel Tank' to "
             "access the FDM lock ring -- a tank serviced by dropping it "
             "is, by the ordinary meaning of that procedure, underbody-"
             "mounted (every mainstream platform's drop-tank service is "
             "underbody). No exact position (fore/aft of the rear axle, "
             "etc.) is sourced.",
             source="TSB 9100471 (" + _EVAP_DOC + ")", confidence=INFERRED),
        part_of_systems=["fuel"],
        tsb_refs=["9100471"],
        inspection_hint="straps/skid-shield condition; fuel smell or "
                         "staining at the tank seams",
        notes="Houses the fuel pump/delivery module (FDM); see "
              "fuel_pump_module.",
    ),

    "fuel_pump_module": _el(
        "pump", "In-tank fuel pump / delivery module (FDM)",
        _unknown_loc("No TSB or doc in this repo gives the FDM's exact "
                      "orientation or access point beyond 'inside the "
                      "tank, reached by dropping it'."),
        part_of_systems=["fuel"],
        tsb_refs=["9100471", "25V586000"],
        inspection_hint="per TSB 9100471: after FDM service, verify the "
                         "internal vapour line is properly reconnected at "
                         "the FDM port -- a disconnected line here is the "
                         "documented fuel-flooding-into-canister failure "
                         "mode",
        notes="Subject to recall NHTSA 25V586000 / Mopar 93C (fuel pump "
              "may fail -> loss of fuel flow/drive power; interim letters "
              "Oct 2025, final remedy anticipated Jul 2026). The recall's "
              "flagship presentation is 'Service Electronic Throttle' / "
              "'Service Throttle Position' plus limp mode and stalling, "
              "NOT a fuel-specific message -- per " + _EVAP_DOC + " section 8.",
    ),

    "fuel_lines": _el(
        "line", "Fuel supply/return and vapour lines (tank to engine bay)",
        _unknown_loc("Routing from tank to rail is not diagrammed in any "
                      "source in this repo; only the EVAP-side vapour "
                      "line (tank-to-canister) is named, by TSB 9100471, "
                      "as a thing that can be 'kinked'."),
        part_of_systems=["fuel", "evap"],
        tsb_refs=["9100471"],
        inspection_hint="kinked/pinched vapour hose tank-to-canister per "
                         "9100471's diagnostic tree",
        notes="",
    ),

    "fuel_rail": _el(
        "component", "Fuel rail",
        _unknown_loc("No Stelvio/Giorgio-specific source in this repo "
                      "locates the rail; engine-bay mounting across the "
                      "injectors is the only thing assumable from the "
                      "injector entry below, not independently sourced "
                      "for the rail itself."),
        part_of_systems=["fuel"],
        inspection_hint="fuel pressure at the rail (DVOM/gauge or scan "
                         "tool PID) before condemning injectors",
        notes="",
    ),

    "fuel_injectors": _el(
        "component", "Fuel injectors",
        _unknown_loc("No TSB in this repo's knowledge base covers "
                      "injector location beyond the generic 'one per "
                      "cylinder' assumption used for the ignition coil "
                      "entry in mes.electrical; not independently sourced "
                      "for injectors."),
        part_of_systems=["fuel", "ignition"],
        inspection_hint="swap-test / resistance check per cylinder before "
                         "condemning; rule out fuel pressure and ignition "
                         "first per TSB 25V586000's symptom overlap",
        notes="Owner-reported DTCs alongside the 93C fuel pump recall "
              "include misfires P0300/P0302/P0303 (" + _EVAP_DOC +
              " section 8) -- a misfire diagnosis on this car should "
              "check fuel delivery before condemning injectors or coils.",
    ),

    "fuel_cap": _el(
        "cap", "Fuel filler cap",
        _unknown_loc("Not independently panel-located (it is external, "
                      "at the filler door) but no source gives a more "
                      "precise statement than that."),
        part_of_systems=["fuel", "evap"],
        tsb_refs=["9100469"],
        inspection_hint="seating/damage, but weight this LOW: "
                         "EVAP_STELVIO.md section 10 explicitly says 'do "
                         "not condemn the gas cap (low hit rate on this "
                         "platform)' -- one owner spent ~$144 on a dealer "
                         "cap with no change",
        notes="P0457 ('EVAP leak consistent with a loose, missing or "
              "faulty fuel cap') is the cap-specific code; see "
              "mes.code_feel.",
    ),

    "fuel_filler_neck": _el(
        "line", "Fuel filler neck",
        _unknown_loc("No TSB in this repo's knowledge base covers the "
                      "filler neck or an ORVR check valve inside it; "
                      "EVAP_STELVIO.md section 4 explicitly lists the "
                      "filler neck / ORVR check valve among parts with "
                      "ZERO field reports implicating them on Giulia/"
                      "Stelvio."),
        part_of_systems=["fuel", "evap"],
        inspection_hint="only if the canister/vent path is clear and "
                         "'pump clicks off during refuelling' persists -- "
                         "see evap_canister notes first, this is a low-"
                         "yield suspect",
        notes="",
    ),

    "fuel_filter_note": _el(
        "filter", "Fuel filter (none separately serviceable)",
        _loc("underbody",
             "Inside the fuel tank, integrated into the pump/delivery "
             "module -- not a stand-alone, separately replaceable part.",
             source="mes.maintenance_specs fuel_filter item "
                     "(stelvioforum.com threads 'Fuel Filter' / 'Fuel "
                     "Filter Service'; mes.service_specs notes it as "
                     "'integrated into the fuel pump module -- non-"
                     "serviceable except by')",
             confidence=SINGLE_SOURCE),
        part_of_systems=["fuel"],
        inspection_hint="not independently serviceable; a plugged "
                         "in-tank 'sock' filter is addressed by FDM/pump "
                         "replacement, not a filter swap",
        notes="Owner's-manual periodic-checks table's 'additional fuel "
              "filter (if equipped)' row is a different, VIN-specific "
              "item per mes.maintenance_specs -- not confirmed fitted "
              "here.",
    ),

    # --- evap ------------------------------------------------------------

    "evap_canister": _el(
        "component", "EVAP (fuel vapor) canister",
        _loc("rear_left_wheel_well",
             "Mopar P/N 68528496AA (one of four candidate suffixes in "
             "TSB 9100469) located 'behind the driver's-side rear wheel "
             "liner' per forum/retailer convergence; the charcoal bed "
             "stores tank vapour until the ECM purges it, and the vent "
             "function is integrated into the canister module on NA cars "
             "(not a separate valve).",
             source=_EVAP_DOC + " section 4; mes.parts evap_canister",
             confidence=SINGLE_SOURCE),
        part_of_systems=["evap", "fuel"],
        tsb_refs=["9100469", "9100468", "9100471", "P2422"],
        inspection_hint="check the canister FILTER first (TSB 9100468, "
                         "CONFIRMED, cheap, scheduled) before condemning "
                         "the canister; housing wet with liquid fuel is "
                         "the 9100471 flooding mode (not water)",
        notes="Field consensus ranks a plugged/saturated canister as the "
              "most likely EVAP fault on this platform (" + _EVAP_DOC +
              " section 4, 'most common problem a dealer repairs on "
              "Stelvios'). 'Pump clicks off during refuelling' + P2422 is "
              "close to pathognomonic for this. Distinguish from the ESIM "
              "before ordering -- TSB 9100469 warns against replacing the "
              "canister for an ESIM-only fault.",
    ),

    "evap_canister_filter": _el(
        "filter", "EVAP canister filter",
        _loc("rear_left_wheel_well",
             "Co-located with the canister it filters (same wheel-liner "
             "area); TSB 9100468 does not give a separate panel location "
             "from the canister itself.",
             source="TSB 9100468 (" + _EVAP_DOC + " section 3)",
             confidence=INFERRED),
        part_of_systems=["evap"],
        tsb_refs=["9100468", "25-009-24"],
        inspection_hint="check for restriction/blockage on the owner's-"
                         "manual schedule; replace if blocked -- cheap, "
                         "scheduled, precedes any canister-replacement "
                         "decision",
        notes="TSB 25-009-24: customer-paid Mopar Dual EVAP Filter kit "
              "exists for dusty operating conditions (mes.parts/"
              "EVAP_STELVIO.md section 0).",
    ),

    "esim": _el(
        "sensor", "Evaporative System Integrity Module (ESIM)",
        _loc("rear_left_wheel_well",
             "'In the EVAP line near the fuel vapor canister; distinct "
             "from the canister itself' -- TSB 9100469 establishes the "
             "ESIM as a separately serviceable part from the canister "
             "but does not restate the canister's own siting; INFERRED "
             "co-location because 9100471's remedy treats them as a "
             "replace-both unit.",
             source="mes.parts esim; TSB 9100469/9100471",
             confidence=INFERRED),
        part_of_systems=["evap"],
        tsb_refs=["9100469", "9100471", "9100325 Rev 1"],
        inspection_hint="a small electric pump/switch that pressurizes "
                         "the EVAP system and monitors for leaks -- test "
                         "electrically via mes.electrical's esim_connector "
                         "entry before condemning the part itself",
        notes="This element is the PHYSICAL sensor/pump; its connector "
              "and ground are catalogued in mes.electrical "
              "(esim_connector, esim_ground). See "
              "code_physical_path()'s merge behaviour.",
    ),

    "purge_valve": _el(
        "valve", "EVAP purge control valve / solenoid",
        _loc("engine_bay",
             "In the purge line between the canister and the intake/"
             "ejector tees; FCA's own labour operation names this "
             "assembly the 'Boost Vacuum Purge Tube Assembly'.",
             source="TSB 9100325 Rev 1 (" + _EVAP_DOC + " section 0/6); "
                     "mes.parts purge_valve",
             confidence=SINGLE_SOURCE),
        part_of_systems=["evap", "air_intake_boost"],
        tsb_refs=["9100325 Rev 1"],
        inspection_hint="KOEO actuator test (MES: 'Evaporation control "
                         "valve', engine OFF) confirms the valve clicks "
                         "before condemning it -- shop logs on this VIN "
                         "show 6/6 COMPLETED while P0456 was active, so "
                         "weight diagnosis toward canister/vent instead",
        notes="Field consensus: standalone purge-valve replacement is "
              "low-yield for these codes -- several owners report "
              "replacing it alone with no resolution.",
    ),

    "evap_vent_recirc_lines": _el(
        "line", "EVAP vent/recirculation lines",
        _unknown_loc("No exact routing diagram sourced; only the "
                      "recirculation line's quick-connect mid-point is "
                      "located (see evap_quick_connect) and the dual-"
                      "path purge architecture is reconstructed, not "
                      "OEM-diagrammed, per EVAP_STELVIO.md section 6."),
        part_of_systems=["evap"],
        tsb_refs=["S2125000002"],
        inspection_hint="smoke test to physically localise a leak -- "
                         "EVAP is low-pressure, do not over-pressurize",
        notes="Dual-path boost purge (reconstructed, LIKELY per "
              + _EVAP_DOC + " section 6): off-boost, manifold vacuum draws "
              "vapour straight into the intake manifold; on-boost, a "
              "check valve closes that path and boost is tapped from the "
              "CAC duct through an ejector tee (venturi) into the air "
              "cleaner / turbo inlet.",
    ),

    "evap_quick_connect": _el(
        "component", "EVAP recirculation-line quick-connect fitting",
        _loc("engine_bay",
             "Mid-point of the EVAP recirculation line; a related pair "
             "of quick connects also sit at the air cleaner cover "
             "(push-pull-push check per TSB 25-002-23).",
             source="STAR S2125000002; mes.parts evap_quick_connect",
             confidence=SINGLE_SOURCE),
        part_of_systems=["evap"],
        tsb_refs=["S2125000002", "25-002-23"],
        inspection_hint="⭐ the cheap first check FCA documents for "
                         "P0455/P0456/P0441/P1CEA, ahead of any deep "
                         "diagnosis: confirm it is fully seated and "
                         "latched, then re-run the wiTECH EVAP leak test "
                         "-- two minutes, free",
        notes="",
    ),

    "ejector_tee": _el(
        "component", "Ejector tee (clean-air duct, boost purge venturi)",
        _unknown_loc("Exact position within the clean-air duct is not "
                      "panel-diagrammed; only its functional role "
                      "(venturi in the on-boost purge path) and the "
                      "borescope-access instruction are sourced."),
        part_of_systems=["evap", "air_intake_boost"],
        tsb_refs=["S2125000003", "9100325 Rev 1"],
        inspection_hint="borescope for flow-restricting debris (STAR "
                         "S2125000003, P1CEA); directional blow-test one "
                         "side should be much harder to blow through "
                         "than the other -- a backwards-installed tee is "
                         "FCA precedent on a sibling 1.4L turbo engine",
        notes="Directional/orientation-sensitive; 'blockage/flash at the "
              "ports on the CAC duct and the air cleaner' is FCA's own "
              "listed possible cause for P1CEA.",
    ),

    # --- air_intake_boost --------------------------------------------------

    "engine_air_filter_housing": _el(
        "housing", "Engine air filter / airbox",
        _loc("engine_bay",
             "Air box ahead of the turbo intake.",
             source="mes.parts engine_air_filter", confidence=SINGLE_SOURCE),
        part_of_systems=["air_intake_boost"],
        inspection_hint="replace cartridge per the owner's-manual "
                         "schedule (mandatory at 30k/60k/90k mi per "
                         "mes.maintenance_specs)",
        notes="",
    ),

    "maf_map_iat_sensors": _el(
        "sensor", "Intake air metering (MAP/IAT; no MAF channel sourced)",
        _unknown_loc("mes.systems' air_intake_boost live_channels list "
                      "(intake_map, barometric_pressure, boost, "
                      "intake_air_temp, absolute_load, throttle_position) "
                      "names MAP/IAT/boost channels but no MAF channel; "
                      "INFERRED (not confirmed) that this engine meters "
                      "load via MAP rather than a separate airflow "
                      "sensor. Exact sensor panel positions are not "
                      "sourced."),
        part_of_systems=["air_intake_boost"],
        inspection_hint="MAP/IAT plausibility vs known-good at idle and "
                         "snap-throttle (mes.known_good); do not assume "
                         "a MAF exists on this engine without confirming "
                         "against a wiring diagram",
        notes="Table C in " + _MODULE_MAP + " lists DID 1935 'Intake air "
              "temp (post-turbo)' for the ECM -- UNVERIFIED on 2.0T, "
              "CONFIRMED only that the DID exists in the danardi78 "
              "catalogue.",
    ),

    "turbocharger": _el(
        "component", "Turbocharger",
        _unknown_loc("No Stelvio/Giorgio-specific TSB in this repo's "
                      "knowledge base locates or sizes the turbo; engine-"
                      "bay mounting is assumed from the hose-routing "
                      "entries around it, not independently sourced."),
        part_of_systems=["air_intake_boost", "exhaust_emissions"],
        inspection_hint="exhaust-driven; an exhaust-side restriction or "
                         "failing turbo housing can present as a boost/"
                         "MAP-sensor fault per mes.systems' "
                         "air_intake_boost<-exhaust_emissions dependency",
        notes="",
    ),

    "wastegate_vacuum_valves": _el(
        "valve", "Wastegate / boost-control vacuum valves",
        _unknown_loc("No TSB in this repo's knowledge base names a "
                      "wastegate actuator or vacuum valve location for "
                      "this engine."),
        part_of_systems=["air_intake_boost"],
        inspection_hint="",
        notes="",
    ),

    "intercooler_cac": _el(
        "component", "Charge air cooler (CAC) -- water-cooled intercooler",
        _loc("engine_bay",
             "Between the turbocharger, the water-cooled intercooler "
             "(CAC) and the throttle body -- an engine-bay charge-air "
             "path, not an air-to-air core in the bumper.",
             source="mes.parts turbo_intercooler_hose",
             confidence=SINGLE_SOURCE),
        part_of_systems=["air_intake_boost", "cooling"],
        inspection_hint="see cooling system's SEPARATE intercooler "
                         "coolant circuit/reservoir -- do not check only "
                         "the main engine coolant level",
        notes="Runs its OWN cooling circuit (1.4 US gal / 5.25 L), "
              "separate from the 8.8 L engine coolant circuit -- "
              "CONFIRMED, owner's manual Fluid Capacities table per "
              "mes.maintenance_specs.",
    ),

    "charge_hoses": _el(
        "hose", "Turbo / intercooler boost (charge-air) hoses",
        _loc("engine_bay",
             "Carries pressurized charge air between the turbo, the CAC "
             "and the throttle body; a commonly cited failure point per "
             "mes.parts, exact routing not diagrammed.",
             source="mes.parts turbo_intercooler_hose",
             confidence=SINGLE_SOURCE),
        part_of_systems=["air_intake_boost"],
        inspection_hint="boost-leak check (smoke or shop-air with soap "
                         "water) at every clamp before condemning the "
                         "turbo or a boost sensor",
        notes="",
    ),

    "throttle_body": _el(
        "component", "Throttle body",
        _unknown_loc("No TSB in this repo's knowledge base locates or "
                      "describes service procedure for the throttle "
                      "body beyond the generic maintenance item "
                      "'throttle_body_clean' in mes.maintenance_specs."),
        part_of_systems=["air_intake_boost"],
        inspection_hint="clean per mes.maintenance_specs "
                         "'throttle_body_clean' item",
        notes="NHTSA 25V586000's flagship symptom is 'Service Electronic "
              "Throttle' / 'Service Throttle Position' -- on this engine "
              "that message is traced to the fuel pump recall, NOT the "
              "throttle body itself (" + _EVAP_DOC + " section 8).",
    ),

    # --- cooling -------------------------------------------------------------

    "radiator": _el(
        "component", "Radiator",
        _unknown_loc("No TSB or doc in this repo locates or describes "
                      "the radiator beyond its membership in the "
                      "engine's main coolant circuit."),
        part_of_systems=["cooling"],
        inspection_hint="",
        notes="",
    ),

    "electronic_thermostat": _el(
        "valve", "Electronic (map-controlled) thermostat",
        _unknown_loc("Not independently sourced in this repo; 'electronic "
                      "thermostat' is named in this module's build spec "
                      "but no Stelvio-specific TSB or doc confirms its "
                      "location or control strategy."),
        part_of_systems=["cooling"],
        inspection_hint="",
        notes="",
    ),

    "water_pump": _el(
        "pump", "Engine water pump",
        _unknown_loc("No TSB or doc in this repo locates the water pump "
                      "or states whether it is mechanical or electric on "
                      "this engine."),
        part_of_systems=["cooling"],
        inspection_hint="",
        notes="",
    ),

    "coolant_expansion_tank": _el(
        "reservoir", "Engine coolant reservoir (expansion tank)",
        _loc("engine_bay",
             "Engine coolant reservoir, separate from the intercooler "
             "reservoir.",
             source="mes.parts coolant; mes.maintenance_specs coolant "
                     "item (2018 US owner's manual)",
             confidence=CONFIRMED),
        part_of_systems=["cooling"],
        inspection_hint="level at MIN/MAX; condition/colour for "
                         "contamination or oil intrusion",
        notes="Engine circuit capacity 8.8 L (2.3 US gal), CONFIRMED, "
              "owner's manual Fluid Capacities table. Single mandatory "
              "change at 150,000 mi / 240,000 km / 15 years, not a "
              "periodic-interval item. No sourced drain-plug location "
              "or bleed procedure for the 2.0T engine circuit.",
    ),

    "intercooler_expansion_tank": _el(
        "reservoir", "Intercooler coolant reservoir (separate circuit)",
        _loc("engine_bay",
             "A SEPARATE reservoir from the engine coolant reservoir, "
             "for the water-cooled intercooler's own circuit.",
             source="mes.maintenance_specs coolant item (2018 US owner's "
                     "manual Fluid Capacities table)",
             confidence=CONFIRMED),
        part_of_systems=["cooling", "air_intake_boost"],
        inspection_hint="check this level SEPARATELY from the main "
                         "engine coolant reservoir -- a common miss",
        notes="Capacity 1.4 US gal / 5.25 L, CONFIRMED.",
    ),

    "cooling_hoses": _el(
        "hose", "Engine coolant hoses",
        _unknown_loc("No TSB or doc in this repo names a specific "
                      "coolant hose failure point for this engine."),
        part_of_systems=["cooling"],
        inspection_hint="",
        notes="",
    ),

    "cooling_fans": _el(
        "component", "Electric cooling fan(s)",
        _unknown_loc("No TSB or doc in this repo locates or counts the "
                      "cooling fan(s) on this platform."),
        part_of_systems=["cooling"],
        inspection_hint="",
        notes="",
    ),

    # --- lubrication ---------------------------------------------------------

    "oil_pan_drain_plug": _el(
        "component", "Oil pan / drain plug",
        _loc("engine_bay",
             "Bottom of the oil pan.",
             source="mes.parts drain_plug_gasket", confidence=SINGLE_SOURCE),
        part_of_systems=["lubrication"],
        inspection_hint="drain-plug gasket replaced every oil change; "
                         "check for weeping/seepage at the plug",
        notes="",
    ),

    "oil_filter_housing": _el(
        "housing", "Cartridge oil filter housing",
        _loc("engine_bay",
             "Top of the engine, under a screw-off plastic housing cap.",
             source="mes.parts oil_filter", confidence=SINGLE_SOURCE),
        part_of_systems=["lubrication"],
        inspection_hint="cap O-ring condition; correct torque on "
                         "reassembly per mes.service_specs",
        notes="Cartridge-style filter, not a spin-on canister.",
    ),

    "oil_cooler": _el(
        "component", "Engine oil cooler",
        _unknown_loc("No TSB or doc in this repo locates or confirms an "
                      "oil cooler on this engine."),
        part_of_systems=["lubrication", "cooling"],
        inspection_hint="",
        notes="",
    ),

    "oil_pressure_level_sensors": _el(
        "sensor", "Oil pressure / level sensors",
        _unknown_loc("No TSB or doc in this repo locates these sensors; "
                      "mes.systems' lubrication live_channels lists only "
                      "engine_oil_temp, not a pressure or level channel, "
                      "so their existence as scanned PIDs on this car is "
                      "not confirmed either."),
        part_of_systems=["lubrication"],
        inspection_hint="",
        notes="",
    ),

    # --- exhaust_emissions ----------------------------------------------------

    "catalytic_converter": _el(
        "component", "Catalytic converter",
        _unknown_loc("No TSB or doc in this repo locates or counts the "
                      "catalyst(s) on this engine."),
        part_of_systems=["exhaust_emissions"],
        inspection_hint="",
        notes="A misfire dumps unburned fuel into the exhaust and can "
              "set secondary catalyst/O2 codes -- mes.systems' "
              "exhaust_emissions<-ignition dependency (SINGLE-SOURCE, "
              "generic emissions architecture, no Stelvio-specific TSB).",
    ),

    "o2_sensors": _el(
        "sensor", "Oxygen (O2/lambda) sensors",
        _unknown_loc("No TSB or doc in this repo locates or counts the "
                      "O2 sensors; mes.known_good notes a 'Lambda sensor "
                      "1 integrator' parameter exists in logs, confirming "
                      "the sensor's presence on the bus but not its "
                      "physical position."),
        part_of_systems=["exhaust_emissions"],
        inspection_hint="",
        notes="",
    ),

    "egr_solenoid": _el(
        "valve", "EGR solenoid/valve",
        _unknown_loc("No EGR component is named anywhere in this repo's "
                      "TSB catalogue, module map, parts catalogue or "
                      "actuator/modules list -- a full-text sweep of "
                      "mes.knowledge/mes.modules/mes.parts for 'EGR' "
                      "found nothing. This engine's fitment with EGR is "
                      "therefore NOT CONFIRMED; it is recorded here only "
                      "because the build spec names it, not because any "
                      "source confirms it exists on this car."),
        part_of_systems=["exhaust_emissions"],
        inspection_hint="confirm fitment before diagnosing -- do not "
                         "assume this engine has a discrete EGR solenoid",
        notes="Turbo MultiAir engines of this family are commonly "
              "reported (general industry knowledge, not a Stelvio-"
              "specific source) to omit a conventional EGR valve in "
              "favour of valve-timing-based internal EGR; that claim is "
              "NOT independently verified against any document in this "
              "repo and is flagged here as unverified, not asserted.",
    ),

    # --- transmission_driveline ------------------------------------------------

    "zf_8hp_transmission": _el(
        "component", "ZF 8HP50/75 automatic transmission",
        _unknown_loc("Transmission bell-housing/mounting position is not "
                      "panel-diagrammed in this repo; only its internal "
                      "service points (pan/filter, drain/fill plugs) are "
                      "sourced, via mes.drivetrain_specs."),
        part_of_systems=["transmission_driveline"],
        tsb_refs=[],
        inspection_hint="pan/filter is an INTEGRATED assembly, not "
                         "separately serviceable -- per "
                         "docs/reference/ZF8HP_SERVICE_DATA.md",
        notes="MES identifies it 'ZF 8HP50/75 Automatic Gearbox', header "
              "18DA18F1, CAN-C, no cable -- CONFIRMED network identity "
              "per " + _MODULE_MAP + "; physical mounting UNKNOWN here.",
    ),

    "transfer_case": _el(
        "component", "Magna Q4 active on-demand transfer case",
        _unknown_loc("No panel/underbody position sourced beyond "
                      "'driveline' at a plain-words level; drain/fill "
                      "plug torques are sourced (mes.drivetrain_specs) "
                      "but not the case's own mounting location."),
        part_of_systems=["transmission_driveline"],
        inspection_hint="drain/fill plug per mes.drivetrain_specs; the "
                         "rear differential's 26 Nm value is known, the "
                         "transfer case's own torque is NOT independently "
                         "confirmed (do not assume it is the same)",
        notes="DTCM module (Magna Q4 Transfer Case) answers on CAN-C, no "
              "cable -- CONFIRMED network identity per " + _MODULE_MAP +
              "; TA address 0x29 is UNVERIFIED (stelvio_scan only).",
    ),

    "propshaft": _el(
        "component", "Propshaft / driveshaft",
        _unknown_loc("Flange/centre-carrier nut torque is sourced "
                      "(mes.drivetrain_specs) but the propshaft's own "
                      "routing/mounting is not independently sourced for "
                      "this specific Q4 AWD application."),
        part_of_systems=["transmission_driveline"],
        inspection_hint="",
        notes="mes.drivetrain_specs flags that one torque source for "
              "'propshaft_flange_nut' may describe a different car/"
              "driveline, not this Stelvio's Q4 propshaft -- use the FCA "
              "service manual, not that figure, for a torque spec.",
    ),

    "differentials": _el(
        "component", "Front and rear differentials",
        _unknown_loc("Drain/fill plug torques are sourced per axle "
                      "(mes.drivetrain_specs); physical panel location "
                      "beyond 'front axle' / 'rear axle' is not further "
                      "diagrammed in this repo."),
        part_of_systems=["transmission_driveline"],
        inspection_hint="tyre-circumference mismatch on AWD causes "
                         "shudder/bind and can damage the transfer case "
                         "-- rule this out before condemning driveline "
                         "hardware (TSB S1821000001 REV. A)",
        notes="",
    ),

    "driveline_mounts": _el(
        "mount", "Engine and transmission mounts",
        _unknown_loc("Bolt torques are sourced (mes.drivetrain_specs: "
                      "engine_mount_bolts, longitudinal_mount_bolts, "
                      "trans_mount_bracket_fasteners) but exact mount "
                      "panel positions are not independently diagrammed "
                      "in this repo beyond 'aluminium block' / "
                      "'longitudinal (torque strut / dogbone)'."),
        part_of_systems=["transmission_driveline"],
        inspection_hint="Alfa Romeo specifies the longitudinal mount "
                         "itself must be replaced on removal, per "
                         "mes.drivetrain_specs -- do not reuse it",
        notes="",
    ),

    # --- brakes_abs -----------------------------------------------------------

    "abs_esc_module": _el(
        "module", "ABS/ESC module -- Continental MK C1",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module answers "
                      "on CAN-CH via the grey A6 cable, which is network "
                      "topology, not physical mounting; no panel location "
                      "sourced."),
        part_of_systems=["brakes_abs"],
        inspection_hint="",
        notes="Brake-by-wire architecture: this module hosts ABS, ESP/"
              "ESC, traction control and (per mes.modules) the Giorgio "
              "park-brake function -- there is no separate standalone "
              "EPB controller module despite 'EPB' appearing as its own "
              "MES entry; " + _MODULE_MAP + "'s own hygiene note flags "
              "EPB as 'yes' but never appearing in a scan or in MES's "
              "Stelvio list, concluding the park brake is driven by the "
              "ABS/ESC unit.",
    ),

    "epb_caliper_motors": _el(
        "component", "EPB (electric parking brake) rear caliper motors",
        _unknown_loc("No panel/caliper-internal location sourced beyond "
                      "'rear calipers' from mes.parts brake_pads_rear."),
        part_of_systems=["brakes_abs"],
        tsb_refs=[],
        inspection_hint="put the EPB into service mode before loosening "
                         "the caliper, per mes.service_specs "
                         "BRAKE_SPEC['epb_service_mode']",
        notes="Rear brakes use an electric parking brake with motorised "
              "caliper actuators per mes.service_specs.",
    ),

    "wheel_speed_sensors": _el(
        "sensor", "Wheel speed sensors",
        _unknown_loc("No TSB or doc in this repo locates these sensors "
                      "beyond their functional membership in the ABS/ESC "
                      "system."),
        part_of_systems=["brakes_abs"],
        inspection_hint="",
        notes="",
    ),

    # --- steering --------------------------------------------------------------

    "eps_motor_rack": _el(
        "component", "EPS (electric power steering) motor/rack",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms the EPS module's "
                      "network address (CAN-CH, grey A6, TA 0x2A) but "
                      "gives no panel/physical mounting location."),
        part_of_systems=["steering"],
        inspection_hint="",
        notes="ZF Electric Steering; also hosts the steering-angle "
              "sensor on Giorgio (mes.modules) -- there is no separate "
              "standalone steering-angle-sensor node.",
    ),

    "steering_column": _el(
        "component", "Steering column",
        _unknown_loc("No TSB or doc in this repo describes the column's "
                      "construction or service points beyond the "
                      "electric steering-lock (NBS) module's existence "
                      "per mes.modules."),
        part_of_systems=["steering"],
        inspection_hint="",
        notes="",
    ),

    # --- suspension --------------------------------------------------------------

    "shocks_struts": _el(
        "component", "Shocks/struts",
        _unknown_loc("No TSB or doc in this repo sourced for this "
                      "platform's suspension hardware."),
        part_of_systems=["suspension"],
        inspection_hint="",
        notes="",
    ),

    "control_arms_bushings": _el(
        "component", "Control arms and bushings",
        _unknown_loc("No TSB or doc in this repo sourced for this "
                      "platform's suspension hardware."),
        part_of_systems=["suspension"],
        inspection_hint="",
        notes="",
    ),

    "tires_wheels_tpms": _el(
        "sensor", "Tires/wheels and TPMS sensors",
        _loc("front_left_wheel_well",
             "Inside each wheel, mounted on the valve stem/rim -- one "
             "sensor per corner, read over UDS at RFHUB DIDs "
             "0x40B1-0x40B4 (FL/FR/RL/RR).",
             source="mes.parts tpms_sensor", confidence=SINGLE_SOURCE),
        part_of_systems=["suspension"],
        inspection_hint="live read via RFHUB DIDs before condemning a "
                         "sensor as dead",
        notes="This single element stands in for all four corners; the "
              "zone field names only the front-left as a representative "
              "location, per mes.electrical.ZONES' per-corner vocabulary.",
    ),

    # --- body_comfort -----------------------------------------------------------

    "window_riser_motor": _el(
        "component", "Window-riser motor (per door)",
        _unknown_loc("No TSB in mes.knowledge covers B1176; recorded "
                      "only at a plain-words level, mirroring "
                      "mes.electrical.window_riser_circuit: door module "
                      "-> window-motor circuit -> door harness connector "
                      "-> ground. No panel position or part number is "
                      "sourced."),
        part_of_systems=["body_comfort"],
        inspection_hint="wiggle test the door harness boot/grommet for "
                         "chafe where it flexes with the door -- generic "
                         "automotive-electrical knowledge, not a "
                         "Stelvio-specific sourced fact",
        notes="Physical counterpart to mes.electrical's "
              "window_riser_circuit element; see code_physical_path() "
              "for the B1176 merge.",
    ),

    "window_riser_switch": _el(
        "component", "Window-riser switch (door panel)",
        _unknown_loc("No TSB or doc in this repo locates or part-numbers "
                      "this switch."),
        part_of_systems=["body_comfort"],
        inspection_hint="",
        notes="",
    ),

    "bcm_physical": _el(
        "module", "BCM -- Body Computer Marelli 949 (gateway)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms network identity "
                      "(CAN-C, gateway to CAN-IHS) but not physical "
                      "mounting. Same module as mes.electrical's 'bcm' "
                      "element -- duplicated here only so a body_comfort "
                      "elements() filter returns something for the "
                      "module that drives most body-comfort functions."),
        part_of_systems=["body_comfort"],
        inspection_hint="see mes.electrical's bcm/f82/bcm_feed_20a/xy201/"
                         "g003a/g003b chain for the electrical side",
        notes="",
    ),

    # --- adas_sensors -----------------------------------------------------------

    "dasm_radar": _el(
        "sensor", "DASM -- driver assistance radar (Bosch)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module answers "
                      "on CAN-C with no cable (7/7 scans); no physical "
                      "mounting location (front bumper/grille area is "
                      "the conventional siting for this sensor type on "
                      "most platforms, but that is general automotive "
                      "knowledge, not sourced for this VIN)."),
        part_of_systems=["adas_sensors"],
        inspection_hint="",
        notes="",
    ),

    "half_camera": _el(
        "sensor", "HALF -- haptic lane-feedback camera (Bosch MFK2)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module answers "
                      "on CAN-CH via the grey A6 cable; no physical "
                      "mounting location sourced (windshield/mirror-area "
                      "siting is conventional for a forward camera of "
                      "this type but not confirmed for this car)."),
        part_of_systems=["adas_sensors"],
        inspection_hint="",
        notes="Named 'haptic lane feedback camera' by MES -- note the "
              "task framing that names it alongside ABS/brakes is a "
              "network-topology artefact (it shares the CAN-CH grey-A6 "
              "bus with ABS/EPS/ORC/AFLS/PAM) rather than a brakes_abs "
              "system membership; this module keeps it under "
              "adas_sensors to match mes.systems, not under brakes_abs.",
    ),

    # --- hvac -----------------------------------------------------------------

    "cabin_air_filter_housing": _el(
        "housing", "Cabin air filter housing",
        _loc("dash",
             "Behind the glovebox, in the HVAC intake housing.",
             source="mes.parts cabin_air_filter", confidence=SINGLE_SOURCE),
        part_of_systems=["hvac"],
        inspection_hint="replace per mes.maintenance_specs schedule",
        notes="",
    ),

    "ac_compressor": _el(
        "component", "A/C compressor",
        _unknown_loc("No TSB or doc in this repo locates the compressor "
                      "beyond its membership on the accessory drive belt "
                      "loop (mes.parts drive_belt: 'looped around the "
                      "crank, alternator, A/C compressor and tensioner "
                      "pulleys')."),
        part_of_systems=["hvac"],
        inspection_hint="",
        notes="",
    ),

    "blower_motor": _el(
        "component", "HVAC blower motor",
        _unknown_loc("No TSB or doc in this repo locates this part."),
        part_of_systems=["hvac"],
        inspection_hint="",
        notes="",
    ),

    "climate_control_module": _el(
        "module", "Climate control module (HVAC, TRW)",
        _unknown_loc("GIORGIO_MODULE_MAP.md lists HVAC among modules "
                      "that have NEVER answered on this car's own scans "
                      "(blue A5 / CAN-IHS bus never scanned) -- presence "
                      "is UNVERIFIED, not just un-located."),
        part_of_systems=["hvac"],
        inspection_hint="",
        notes="Per " + _MODULE_MAP + ": the blue A5 bus (CAN-IHS) has "
              "never been scanned on this car; HVAC's address/bus are "
              "database inference, not confirmed presence.",
    ),

    "refrigerant_circuit": _el(
        "line", "A/C refrigerant circuit",
        _unknown_loc("No TSB, charge spec or line-routing doc sourced in "
                      "this repo for this platform."),
        part_of_systems=["hvac"],
        inspection_hint="",
        notes="",
    ),

    # --- pcv ---------------------------------------------------------------

    "pcv_valve_housing": _el(
        "valve", "PCV valve / housing",
        _unknown_loc("No panel location sourced for this part; only a "
                      "candidate OEM number is known, not independently "
                      "verified against a parts catalogue or TSB in this "
                      "repo's own research pass."),
        part_of_systems=["pcv"],
        inspection_hint="check for oil in the breather hose/intake "
                         "runners; a stuck-open or clogged PCV can "
                         "present as a vacuum-leak-like lean condition",
        notes="Candidate OEM number 04893610AC -- UNSOURCED in this "
              "repo's own research pass (not cross-checked against "
              "mes.parts/TSB text); record as SINGLE-SOURCE/unverified, "
              "confirm at a Mopar parts counter before ordering.",
    ),

    "pcv_breather_hoses": _el(
        "hose", "PCV breather hoses (crankcase to intake)",
        _unknown_loc("No routing diagram sourced; mes.maintenance_specs "
                      "lists a generic 'pcv_system' maintenance key but "
                      "no panel-level hose routing for this engine."),
        part_of_systems=["pcv", "air_intake_boost"],
        inspection_hint="oil residue/collapse at the intake-side "
                         "connection; a cracked breather hose reads as "
                         "an unmetered-air leak, same symptom family as "
                         "P0171",
        notes="",
    ),

    # --- starting_charging ---------------------------------------------------

    "starter_motor": _el(
        "component", "Starter motor",
        _unknown_loc("No TSB or doc in this repo locates the starter; "
                      "S2308000004 ('cranks, no start') diagnoses the "
                      "battery/ECM feed-and-ground chain ahead of the "
                      "starter itself and never panel-locates the "
                      "starter."),
        part_of_systems=["starting_charging"],
        tsb_refs=["S2308000004"],
        inspection_hint="verify ALL ECM/PCM B+ feeds and grounds first "
                         "per S2308000004 before condemning the starter "
                         "on a cranks/no-start complaint",
        notes="",
    ),

    "alternator": _el(
        "component", "Alternator",
        _unknown_loc("No TSB or doc in this repo locates the alternator "
                      "beyond its membership on the accessory drive "
                      "belt loop (mes.parts drive_belt)."),
        part_of_systems=["starting_charging"],
        inspection_hint="",
        notes="Shares the accessory drive belt with the A/C compressor "
              "per mes.parts drive_belt.",
    ),

    "ibs_battery_sensor": _el(
        "sensor", "Intelligent Battery Sensor (IBS)",
        _unknown_loc("No panel location sourced; only its data path is "
                      "confirmed (BCM header 18DA40F1, DID 1005: SoC, "
                      "temp, voltage and current -- 'the ground-strap/"
                      "parasitic-draw instrument'; ECM DID 19BD 'IBS "
                      "state of charge', UNVERIFIED on 2.0T)."),
        part_of_systems=["starting_charging"],
        tsb_refs=["S2308000004"],
        inspection_hint="DID 1005 current field is the parasitic-draw "
                         "instrument -- read it before a manual draw "
                         "test, per " + _MODULE_MAP,
        notes="Presumably clamped to/near the 12V battery (conventional "
              "IBS mounting), but that specific claim is NOT sourced for "
              "this VIN -- physical co-location with battery_12v is "
              "INFERRED from the sensor's function, not stated by any "
              "document in this repo.",
    ),

    # --- valve_control (MultiAir) --------------------------------------------

    "multiair_unit": _el(
        "component", "MultiAir electrohydraulic valve-control unit",
        _unknown_loc("No TSB, service doc or parts entry in this repo "
                      "names a panel location, service procedure or part "
                      "number for the MultiAir unit on this engine. Its "
                      "existence is inferred only from the ECM's own "
                      "name in " + _MODULE_MAP + " ('Magneti Marelli IAW "
                      "10JA CF6/EOBD Injection') and the engine code "
                      "GME-T4/MultiAir named throughout this repo's "
                      "docs -- no independent confirmation of the unit's "
                      "mounting or oil-feed routing was found."),
        part_of_systems=["valve_control"],
        inspection_hint="",
        notes="MultiAir uses engine oil, under hydraulic-tappet pressure "
              "controlled by a solenoid per cylinder/bank, to actuate "
              "the intake valves electrohydraulically in place of a "
              "conventional intake camshaft profile -- general MultiAir "
              "architecture knowledge, NOT independently sourced for "
              "this specific Stelvio 2.0T in this repo.",
    ),

    "multiair_oil_feed": _el(
        "line", "MultiAir oil feed (from main lubrication circuit)",
        _unknown_loc("No TSB or doc in this repo sources this feed's "
                      "routing or a dedicated filter/pressure spec "
                      "separate from the engine's main oil system."),
        part_of_systems=["valve_control", "lubrication"],
        inspection_hint="oil condition/level affects valve-control "
                         "hydraulics on a MultiAir engine -- general "
                         "architecture knowledge, not independently "
                         "sourced for this car",
        notes="",
    ),

    # --- wheels_tpms (RFHUB + sensors) ---------------------------------------

    "rfhub_module_physical": _el(
        "module", "RFHUB -- radio frequency hub (Continental)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module's "
                      "network address (CAN-C, no cable, TA 0xC7) and "
                      "that it carries TPMS data; no physical mounting "
                      "location sourced."),
        part_of_systems=["wheels_tpms", "network"],
        inspection_hint="per-wheel pressure/temperature at DIDs "
                         "0x40B1-0x40B4 (FL/FR/RL/RR) before condemning "
                         "a TPMS sensor as dead",
        notes="Immobiliser hazard note from " + _MODULE_MAP + ": "
              "0x18DAC7F1 carries a documented immobiliser hazard if a "
              "BACCAble board is fitted -- none is fitted on this "
              "car, so reading TPMS is safe, but the warning is kept "
              "here too.",
    ),

    "tpms_sensors_per_wheel": _el(
        "sensor", "TPMS sensors (one per wheel)",
        _loc("front_left_wheel_well",
             "Inside each wheel, mounted on the valve stem/rim -- one "
             "sensor per corner, read over UDS at RFHUB DIDs "
             "0x40B1-0x40B4 (FL/FR/RL/RR).",
             source="mes.parts tpms_sensor", confidence=SINGLE_SOURCE),
        part_of_systems=["wheels_tpms", "suspension"],
        inspection_hint="live read via RFHUB DIDs before condemning a "
                         "sensor as dead",
        notes="Same physical part as this module's tires_wheels_tpms "
              "element; duplicated under the wheels_tpms key as well so "
              "an elements(system='wheels_tpms') filter returns it.",
    ),

    # --- restraints (airbag/ORC) ---------------------------------------------

    "orc_module": _el(
        "module", "ORC -- Occupant Restraint Controller (airbag)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module answers "
                      "on CAN-CH via the grey A6 cable (TA 0x50, "
                      "UNVERIFIED -- stelvio_scan only); MES itself lists "
                      "ORC as 'unsupported'. No physical mounting "
                      "location is sourced -- conventional ORC mounting "
                      "(centre tunnel/console) is general automotive "
                      "knowledge, NOT confirmed for this car."),
        part_of_systems=["restraints"],
        inspection_hint="never command this module or its squib "
                         "circuits without explicit human confirmation "
                         "-- " + _MODULE_MAP + "'s CAN-CH table warning "
                         "applies directly (airbag squibs live on this "
                         "bus)",
        notes="",
    ),

    # --- lighting --------------------------------------------------------------

    "afls_module": _el(
        "module", "AFLS -- Automotive Lighting adaptive headlights",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module answers "
                      "on CAN-CH via the grey A6 cable; no physical "
                      "mounting/panel location sourced beyond the "
                      "obvious (headlight assemblies)."),
        part_of_systems=["lighting"],
        inspection_hint="",
        notes="",
    ),

    "headlight_taillight_housings": _el(
        "component", "Headlight / taillight housings",
        _unknown_loc("No TSB or doc in this repo locates or part-numbers "
                      "these housings."),
        part_of_systems=["lighting"],
        inspection_hint="",
        notes="",
    ),

    # --- security_immobiliser -------------------------------------------------

    "sgw_module": _el(
        "module", "SGW -- Security Gateway",
        _unknown_loc("GIORGIO_MODULE_MAP.md states SGW's presence is "
                      "UNVERIFIED on this car -- MES never enumerates "
                      "it; bus/cable/location are therefore ALL unknown, "
                      "not just the physical siting."),
        part_of_systems=["security_immobiliser"],
        inspection_hint="confirm fitment before diagnosing -- do not "
                         "assume a standalone SGW exists on this car",
        notes="",
    ),

    "immobiliser_function": _el(
        "component", "Immobiliser function",
        _unknown_loc("No standalone immobiliser module/location is "
                      "sourced; the function is presumed folded into "
                      "the BCM/ECM pairing per common FCA architecture, "
                      "but that is NOT independently confirmed for this "
                      "car in this repo."),
        part_of_systems=["security_immobiliser"],
        inspection_hint="",
        notes=_MODULE_MAP + " flags a documented immobiliser hazard on "
              "address 0x18DAC7F1 if a BACCAble board is fitted -- none "
              "is fitted on this car; treat the warning as a standing "
              "caution, not a current fault.",
    ),

    # --- infotainment_cluster --------------------------------------------------

    "ipc_cluster": _el(
        "module", "IPC -- Instrument Panel Cluster (Continental)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module's "
                      "network address (CAN-C, no cable, TA 0x60) from "
                      "this car's own scans; physical mounting (behind "
                      "the dash binnacle, by ordinary convention) is NOT "
                      "independently sourced here."),
        part_of_systems=["infotainment_cluster"],
        inspection_hint="brightness DID 0x0104 for a quick live check",
        notes="",
    ),

    "infotainment_headunit": _el(
        "module", "ETM/EMCM/DSM -- infotainment head unit (AlfaConnect)",
        _unknown_loc("GIORGIO_MODULE_MAP.md lists this module among "
                      "those that have NEVER answered on this car's own "
                      "scans (blue A5 / CAN-IHS never scanned) -- "
                      "presence is UNVERIFIED, not just un-located."),
        part_of_systems=["infotainment_cluster"],
        inspection_hint="",
        notes="",
    ),

    "amplifier_module": _el(
        "module", "AMP -- audio amplifier",
        _unknown_loc("Same caveat as infotainment_headunit: CAN-IHS/"
                      "blue A5 never scanned on this car, presence "
                      "UNVERIFIED."),
        part_of_systems=["infotainment_cluster"],
        inspection_hint="",
        notes="",
    ),
}


def element(elem_id: str) -> Optional[dict[str, Any]]:
    """One element by id, with its own id folded in, or ``None``."""
    e = ELEMENTS.get(elem_id)
    if e is None:
        return None
    out = dict(e)
    out["id"] = elem_id
    return out


def elements(system: Optional[str] = None) -> list[dict[str, Any]]:
    """Every element, or only those whose ``part_of_systems`` includes
    ``system`` (a key from :mod:`mes.systems`)."""
    if system is None:
        return [element(eid) for eid in ELEMENTS]
    return [element(eid) for eid, e in ELEMENTS.items()
            if system in e.get("part_of_systems", [])]


# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

def _hop(elem_id: str, role: str) -> dict[str, str]:
    return {"element": elem_id, "role": role}


_EVAP_PHYSICAL_PATH = [
    _hop("fuel_cap", "cap"),
    _hop("fuel_tank", "tank"),
    _hop("fuel_lines", "vapour_line"),
    _hop("evap_canister", "canister"),
    _hop("esim", "integrity_sensor"),
    _hop("evap_vent_recirc_lines", "vent"),
    _hop("evap_quick_connect", "quick_connect"),
    _hop("purge_valve", "purge_valve"),
    _hop("ejector_tee", "boost_purge_tee"),
    _hop("throttle_body", "intake"),
]

_EVAP_PHYSICAL_INTERACTION = [
    {"system": "fuel",
     "how": "Tank, filler neck and cap integrity are the leak-path half "
            "of every EVAP code; the vapour line between tank and "
            "canister is explicitly named as a kink point in TSB "
            "9100471's diagnostic tree.",
     "confidence": CORROBORATED, "source": "TSB 9100471; " + _EVAP_DOC},
    {"system": "air_intake_boost",
     "how": "The on-boost purge path taps boost from the CAC duct "
            "through the ejector tee into the air cleaner/turbo inlet -- "
            "a shared physical path with the intake/boost system, not "
            "just a shared electrical controller.",
     "confidence": SINGLE_SOURCE, "source": _EVAP_DOC + " section 6"},
]

_EVAP_PHYSICAL_INSPECT_STEPS = [
    {"element": "evap_quick_connect",
     "what": "fully seated and latched at the recirculation-line "
             "mid-point",
     "how": "visual + push-pull-push, then re-run wiTECH EVAP leak test",
     "source": "STAR S2125000002"},
    {"element": "evap_canister_filter",
     "what": "restriction or blockage",
     "how": "visual/physical check per owner's-manual schedule",
     "source": "TSB 9100468"},
    {"element": "evap_canister",
     "what": "housing wet with liquid fuel (flooding), not water",
     "how": "visual", "source": "TSB 9100471"},
    {"element": "ejector_tee",
     "what": "flow-restricting debris; directional blow test",
     "how": "borescope + blow test", "source": "STAR S2125000003"},
    {"element": "fuel_lines",
     "what": "kinked/pinched vapour hose tank-to-canister",
     "how": "visual", "source": "TSB 9100471"},
]

_FUEL_TRIM_PHYSICAL_PATH = [
    _hop("engine_air_filter_housing", "airbox"),
    _hop("maf_map_iat_sensors", "intake_metering"),
    _hop("charge_hoses", "intake_leak_point"),
    _hop("throttle_body", "intake_leak_point"),
    _hop("fuel_injectors", "fuel_delivery"),
    _hop("fuel_rail", "fuel_pressure"),
]

_FUEL_TRIM_PHYSICAL_INTERACTION = [
    {"system": "air_intake_boost",
     "how": "A vacuum/boost-side intake leak (hose, gasket, throttle "
            "body seal) admits unmetered air and reads as lean fuel "
            "trim; large enough leaks can sometimes be heard as a hiss "
            "under the hood.",
     "confidence": CORROBORATED, "source": "mes.code_feel P0171 entry "
            "(carista.com, oreillyauto.com, foxwelldiag.com)"},
    {"system": "fuel",
     "how": "Fuel-delivery-side causes (weak pump pressure, a dirty/"
            "failing injector) present identically to an intake-leak "
            "lean condition and must be differentiated by fuel pressure "
            "testing, not assumed.",
     "confidence": CORROBORATED, "source": "mes.code_feel P0171 entry"},
]

_FUEL_TRIM_PHYSICAL_INSPECT_STEPS = [
    {"element": "charge_hoses",
     "what": "unmetered-air leaks at every clamp/joint downstream of the "
             "intake metering point",
     "how": "smoke test or shop-air + soap water",
     "source": "mes.code_feel P0171 entry"},
    {"element": "fuel_rail",
     "what": "fuel pressure at idle and under load",
     "how": "gauge/DVOM or scan-tool PID, before condemning injectors",
     "source": "mes.code_feel P0171 entry"},
]

_MISFIRE_PHYSICAL_PATH = [
    _hop("fuel_injectors", "fuel_delivery"),
    _hop("fuel_pump_module", "fuel_supply"),
    _hop("catalytic_converter", "secondary_effect"),
    _hop("o2_sensors", "secondary_effect"),
]

_MISFIRE_PHYSICAL_INTERACTION = [
    {"system": "fuel",
     "how": "Owner-reported DTCs alongside the 93C fuel pump recall "
            "include misfires P0300/P0302/P0303 -- fuel delivery is a "
            "documented real-world cause of misfire codes on this "
            "specific VIN population, not a generic assumption.",
     "confidence": CORROBORATED, "source": _EVAP_DOC + " section 8"},
    {"system": "exhaust_emissions",
     "how": "A misfire dumps unburned fuel into the exhaust and can set "
            "secondary catalyst/O2 codes.",
     "confidence": SINGLE_SOURCE,
     "source": "general emissions-system architecture -- no GU/Stelvio-"
               "specific TSB citation found"},
]

_MISFIRE_PHYSICAL_INSPECT_STEPS = [
    {"element": "fuel_pump_module",
     "what": "fuel pressure/flow -- rule out the 93C recall condition",
     "how": "scan-tool PID or gauge", "source": _EVAP_DOC + " section 8"},
    {"element": "fuel_injectors",
     "what": "swap-test between cylinders",
     "how": "physical swap + rescan", "source": "none -- TechAuthority"},
]

_B1176_PHYSICAL_PATH = [
    _hop("bcm_physical", "controller"),
    _hop("window_riser_switch", "switch"),
    _hop("window_riser_motor", "motor"),
]
_B1176_PHYSICAL_INTERACTION = [
    {"system": "body_comfort",
     "how": "Door-module/window-motor circuit at a plain-words level "
            "only -- no TSB sourced for this code.",
     "confidence": UNKNOWN, "source": "none"},
]
_B1176_PHYSICAL_INSPECT_STEPS = [
    {"element": "window_riser_motor",
     "what": "door harness boot/grommet for chafe",
     "how": "wiggle test", "source": "none -- TechAuthority"},
]

#: Reuse electrical.py's exact code sets so the two modules never disagree
#: about which codes belong to which family.
EVAP_CODES = _electrical.EVAP_CODES
MISFIRE_CODES = _electrical.MISFIRE_CODES
FUEL_TRIM_CODES = frozenset({"P0171", "P0172"})


def _base(code: str) -> str:
    c = code.strip().upper()
    if "-" in c:
        c = c.split("-", 1)[0]
    return c


def _family_for(base: str) -> Optional[str]:
    if base in EVAP_CODES:
        return "evap"
    if base in FUEL_TRIM_CODES:
        return "fuel_trim"
    if base in MISFIRE_CODES:
        return "misfire"
    if base == "B1176":
        return "b1176"
    return None


_FAMILY_DATA = {
    "evap": (_EVAP_PHYSICAL_PATH, _EVAP_PHYSICAL_INTERACTION,
             _EVAP_PHYSICAL_INSPECT_STEPS),
    "fuel_trim": (_FUEL_TRIM_PHYSICAL_PATH, _FUEL_TRIM_PHYSICAL_INTERACTION,
                  _FUEL_TRIM_PHYSICAL_INSPECT_STEPS),
    "misfire": (_MISFIRE_PHYSICAL_PATH, _MISFIRE_PHYSICAL_INTERACTION,
                _MISFIRE_PHYSICAL_INSPECT_STEPS),
    "b1176": (_B1176_PHYSICAL_PATH, _B1176_PHYSICAL_INTERACTION,
              _B1176_PHYSICAL_INSPECT_STEPS),
}


def code_physical_path(code: str) -> dict[str, Any]:
    """The physical path for one DTC: electrical hops first (from
    :func:`mes.electrical.code_electrical_path`, when that module has a
    curated family for this code), then this module's physical hops.

    Returns ``{code, family, electrical_family, path, systems_interaction,
    inspect_steps}``. ``path`` entries carry a ``domain`` of
    ``"electrical"`` or ``"physical"`` so a caller can still tell the two
    apart after merging. A code with no curated physical family still
    returns any electrical-only path rather than an error; a code with
    neither returns an empty path with a note.
    """
    base = _base(code)
    elec = _electrical.code_electrical_path(base)
    merged_path: list[dict[str, Any]] = []
    for hop in elec.get("path", []):
        h = dict(hop)
        h["domain"] = "electrical"
        merged_path.append(h)

    family = _family_for(base)
    interactions = list(elec.get("systems_interaction", []))
    steps = list(elec.get("inspect_steps", []))

    if family is None:
        if not merged_path:
            return {"code": base, "family": None,
                    "electrical_family": elec.get("family"),
                    "path": [], "systems_interaction": [],
                    "inspect_steps": [],
                    "note": "no curated physical or electrical path for "
                            "this code -- " + TECHAUTHORITY}
        return {"code": base, "family": None,
                "electrical_family": elec.get("family"),
                "path": merged_path, "systems_interaction": interactions,
                "inspect_steps": steps,
                "note": "no curated physical path for this code -- only "
                        "the electrical path is known"}

    path_hops, phys_interactions, phys_steps = _FAMILY_DATA[family]
    for hop in path_hops:
        el = element(hop["element"])
        merged_path.append({
            "element": hop["element"], "role": hop["role"], "details": el,
            "source": (el or {}).get("location", {}).get("source"),
            "confidence": (el or {}).get("location", {}).get("confidence"),
            "domain": "physical",
        })
    interactions = interactions + phys_interactions
    steps = steps + phys_steps

    return {"code": base, "family": family,
            "electrical_family": elec.get("family"),
            "path": merged_path, "systems_interaction": interactions,
            "inspect_steps": steps}


def all_paths() -> dict[str, Any]:
    """Every code this module (or electrical.py) has a curated path for,
    with its resolved physical path -- a dossier-builder convenience so a
    caller doesn't have to enumerate the code sets itself."""
    codes = sorted(EVAP_CODES | MISFIRE_CODES | FUEL_TRIM_CODES
                   | {"B1176"} | _electrical.CHASSIS_CODES)
    return {c: code_physical_path(c) for c in codes}


__all__ = [
    "CONFIRMED", "SINGLE_SOURCE", "INFERRED", "UNKNOWN", "CONFIDENCE_LEVELS",
    "TECHAUTHORITY", "ZONES", "KINDS", "ELEMENTS",
    "element", "elements", "code_physical_path", "all_paths",
    "EVAP_CODES", "MISFIRE_CODES", "FUEL_TRIM_CODES",
]
