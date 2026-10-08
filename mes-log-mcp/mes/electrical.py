"""Electrical architecture: elements, circuits and inspection records for the
2018 Alfa Romeo Stelvio 2.0T (GU).

Companion to :mod:`mes.parts` and :mod:`mes.knowledge`: this module answers
"where is it, what feeds it, what should I look at" at a plain-words level,
for the technician standing at the car with a multimeter, not a pinout
diagram. It is deliberately conservative about what it claims to know.

Confidence levels (same posture as :mod:`mes.parts` -- never invented):

* ``CONFIRMED``     -- a manufacturer document (TSB, module map built from
                       this car's own scans) states it directly.
* ``SINGLE_SOURCE`` -- one source (usually a TSB) names the element but not
                       every detail about it (e.g. a TSB names a connector
                       but not its panel location).
* ``INFERRED``       -- reasoned from sourced facts, with the reasoning
                       stated (e.g. "the ESIM is co-located with the
                       canister per TSB 9100469's framing").
* ``UNKNOWN``        -- nothing credible sourced. ``location.description``
                       is literally the word "UNKNOWN" plus the
                       TechAuthority pointer; never a guessed zone, never a
                       guessed pin or connector number.

House rule, non-negotiable: no connector id, pin number or panel location
is ever invented. Where a TSB or the module map does not say it, this module
says ``UNKNOWN`` and points at the service manual.

Sources used here:

* ``mes.knowledge`` (TSB_CATALOGUE transcription) -- S1808000005 (BCM power
  feeds / fuse F82), S2008000032 (connector XY201, grounds G003A/G003B),
  S1708000262 (spread/pushed-out terminals), S2308000004 (B+/ground
  verification), 9100471/9100469/9100325 (EVAP canister/ESIM/purge hardware).
* ``docs/research/EVAP_STELVIO.md`` -- canister/ESIM physical siting
  ("behind the driver's-side rear wheel liner"), purge-path architecture.
* ``docs/reference/GIORGIO_MODULE_MAP.md`` -- which modules exist on this
  car and which bus they answer on. This file is a *network* map, not a
  *physical* one: it confirms a module is real and reachable, but says
  nothing about where it is bolted in the car, so module physical location
  is UNKNOWN throughout unless some other source (a TSB) says otherwise.
"""

from __future__ import annotations

from typing import Any, Optional

CONFIRMED = "CONFIRMED"
SINGLE_SOURCE = "SINGLE-SOURCE"
INFERRED = "INFERRED"
UNKNOWN = "UNKNOWN"

CONFIDENCE_LEVELS = (CONFIRMED, SINGLE_SOURCE, INFERRED, UNKNOWN)

TECHAUTHORITY = "use the service manual (TechAuthority) wiring diagrams"

ZONES = (
    "engine_bay", "cabin_driver", "cabin_passenger", "dash", "trunk",
    "underbody", "rear_left_wheel_well", "rear_right_wheel_well",
    "front_left_wheel_well", "front_right_wheel_well", "unknown",
)

KINDS = (
    "fuse_box", "fuse", "relay", "ground", "connector", "splice",
    "harness_section", "module", "battery", "alternator",
)

_MODULE_MAP = "docs/reference/GIORGIO_MODULE_MAP.md"
_EVAP_DOC = "docs/research/EVAP_STELVIO.md"
_KNOWLEDGE = "mes-log-mcp/mes/knowledge.py (TSB_CATALOGUE transcription)"


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
                           "inspection for corrosion, chafe, water ingress",
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# ELEMENTS
# ---------------------------------------------------------------------------

ELEMENTS: dict[str, dict[str, Any]] = {

    "battery": _el(
        "battery", "12V battery",
        _unknown_loc("Giorgio-platform cars (Giulia/Stelvio) are commonly "
                     "reported to carry the 12V battery in the cargo "
                     "area, but this has not been confirmed against a "
                     "TechAuthority diagram or this car's own service "
                     "history, so it is not asserted here."),
        feeds=["f82", "bcm_feed_20a", "ecm"],
        part_of_systems=["charging", "network", "cranking"],
        tsb_refs=["S2308000004", "S1408000384"],
        inspection_hint="terminal corrosion, loose clamp/strap, parasitic "
                         "draw (BCM DID 1005 current field on this car's "
                         "own module map)",
        notes="S2308000004 ('cranks, no start'): verify ALL ECM/PCM B+ "
              "feeds and grounds -- the battery and its cabling are the "
              "first hop on any no-start or multi-module-dark complaint.",
    ),

    "ecm": _el(
        "module", "ECM/PCM -- Magneti Marelli IAW 10JA",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module's network "
                      "address (CAN-C, TA 0x10) from this car's own scans, "
                      "but is a bus map, not a physical-location document; "
                      "it says nothing about where the ECM is bolted."),
        feeds=[],
        part_of_systems=["evap", "network", "misfire", "cranking"],
        tsb_refs=["18-030-17 REV. B", "S2308000004"],
        inspection_hint="B+ and ground feeds per S2308000004 before any "
                         "sensor/actuator circuit is condemned",
        notes="Network identity (header 18DA10F1, TA 0x10) is CONFIRMED "
              "per " + _MODULE_MAP + "; physical mounting is UNKNOWN here.",
    ),

    "bcm": _el(
        "module", "BCM -- Body Computer Marelli 949 (gateway)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module's network "
                      "address and that it gateways CAN-C to CAN-IHS, but "
                      "is a bus map, not a physical-location document."),
        feeds=[],
        part_of_systems=["network", "evap", "lighting"],
        tsb_refs=["S1808000005", "S2008000032", "S1708000262"],
        inspection_hint="power feeds first (F82, standalone 20A fuse), "
                         "then the XY201 connector and frame grounds "
                         "G003A/G003B, then terminal condition",
        notes="S1808000005: 'A BCM losing its feed drops off the bus and "
              "everything gatewaying through it throws U-codes.' Network "
              "identity (header 18DA40F1, TA 0x40, gateway role) is "
              "CONFIRMED per " + _MODULE_MAP + ".",
    ),

    "f82": _el(
        "fuse", "Fuse F82 (A901 circuit)",
        _loc("trunk",
             "Named by TSB as being in the 'rear PDC' (rear power "
             "distribution center); the TSB does not specify which panel "
             "or cavity within the rear PDC, so only the general area "
             "(rear of car, consistent with a trunk-area fuse box on this "
             "platform) is recorded -- not a specific physical spot.",
             source="TSB S1808000005", confidence=SINGLE_SOURCE),
        feeds=["bcm"],
        part_of_systems=["network"],
        tsb_refs=["S1808000005"],
        inspection_hint="check fuse condition and seating; this is the "
                         "named BCM supply fuse on GU/Stelvio per the TSB",
        notes="S1808000005: 'on GU/Stelvio inspect fuse F82 in the rear "
              "PDC (A901 circuit)'.",
    ),

    "bcm_feed_20a": _el(
        "fuse", "Standalone 20A fuse (BCM power feed)",
        _unknown_loc("TSB names this fuse's rating and role but not its "
                      "panel location."),
        feeds=["bcm"],
        part_of_systems=["network"],
        tsb_refs=["S1808000005"],
        inspection_hint="inspect for a blown or loose fuse alongside F82",
        notes="S1808000005: 'Inspect all BCM power feeds including the "
              "standalone 20A fuse.'",
    ),

    "xy201": _el(
        "connector", "Inline connector XY201",
        _unknown_loc("TSB names this connector by id but gives no panel "
                      "location and no pin numbers -- none are invented "
                      "here."),
        feeds=[],
        part_of_systems=["network"],
        tsb_refs=["S2008000032"],
        inspection_hint="securing/seating -- TSB's fix was 'securing inline "
                         "connector XY201', no parts replaced",
        notes="S2008000032: multi-module warning cascade resolved by "
              "securing XY201 and cleaning G003A/G003B; NHTSA scope is "
              "2020 Stelvio, GU circuitry shared but verify applicability "
              "to this VIN/model year before treating as a known fix.",
    ),

    "g003a": _el(
        "ground", "Frame ground G003A",
        _loc("underbody",
             "TSB calls these 'frame grounds', which on this platform "
             "family means a body/chassis ground point, not an "
             "under-hood or in-cabin ground; exact body location is not "
             "given by the TSB.",
             source="TSB S2008000032", confidence=SINGLE_SOURCE),
        feeds=[],
        part_of_systems=["network"],
        tsb_refs=["S2008000032"],
        inspection_hint="clean to bare metal, check torque/tightness",
        notes="Paired with G003B; TSB fix was cleaning both, no parts.",
    ),

    "g003b": _el(
        "ground", "Frame ground G003B",
        _loc("underbody",
             "Same sourcing and caveats as G003A -- see that entry.",
             source="TSB S2008000032", confidence=SINGLE_SOURCE),
        feeds=[],
        part_of_systems=["network"],
        tsb_refs=["S2008000032"],
        inspection_hint="clean to bare metal, check torque/tightness",
        notes="Paired with G003A.",
    ),

    "esim_connector": _el(
        "connector", "ESIM connector / harness run",
        _loc("rear_left_wheel_well",
             "The vapor canister assembly (Mopar 68528496AA) is reported "
             "'behind the driver's-side rear wheel liner' (US LHD = left "
             "side); TSB 9100469 establishes the ESIM (Evaporative System "
             "Integrity Module detector) as a separately serviceable part "
             "from the canister but does not itself restate the canister's "
             "siting. INFERRED: the ESIM and its connector/harness run are "
             "co-located with the canister because they are described and "
             "serviced as a unit in 9100471 ('replace BOTH canister and "
             "ESIM'). The exact connector id/pin-out is not sourced -- "
             "none is invented.",
             source=_EVAP_DOC + " + TSB 9100469/9100471", confidence=INFERRED),
        feeds=[],
        part_of_systems=["evap"],
        tsb_refs=["9100469", "9100471", "9100325 Rev 1"],
        inspection_hint="connector seating/corrosion, and -- per 9100471 -- "
                         "whether the canister/ESIM housing is wet with "
                         "liquid fuel (flooding mode, not a simple "
                         "electrical fault)",
        notes="9100471: fuel flooding traced to a disconnected internal "
              "vapor line at the FDM port, not a water-ingress TSB (none "
              "found in a full-text sweep per EVAP_STELVIO.md).",
    ),

    "esim_ground": _el(
        "ground", "ESIM ground point",
        _unknown_loc("No TSB or doc in this repo identifies the ESIM's "
                      "own ground point; it is placed in the same zone as "
                      "the ESIM connector only because that is the nearest "
                      "sourced landmark, not because the ground point "
                      "itself has been confirmed there."),
        feeds=[],
        part_of_systems=["evap"],
        tsb_refs=[],
        inspection_hint="voltage-drop test ESIM ground circuit before "
                         "condemning the sensor itself",
        notes="",
    ),

    "purge_valve_connector": _el(
        "connector", "Purge control valve connector",
        _loc("engine_bay",
             "9100325 Rev 1 covers purge hose routing at the ejector "
             "tees, purge solenoid and intake -- all engine-bay items, "
             "which places the purge solenoid/valve in the engine bay. "
             "The connector's own pin-out/id is not given by the TSB.",
             source="TSB 9100325 Rev 1", confidence=INFERRED),
        feeds=[],
        part_of_systems=["evap"],
        tsb_refs=["9100325 Rev 1"],
        inspection_hint="hose routing at ejector tees per 9100325; "
                         "actuator test (Evaporation control valve) via "
                         "MES/wiTECH before condemning the valve",
        notes="Shop log evidence (EVAP_STELVIO.md): 6/6 purge actuator "
              "tests COMPLETED while P0456 was active -- the valve "
              "actuated correctly, so a connector/wiring fault is not "
              "supported by that evidence either; this is a hardware "
              "leak-path problem more often than an electrical one.",
    ),

    "abs_module": _el(
        "module", "ABS/ESC module -- Continental MK C1",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module answers "
                      "on CAN-CH via the grey A6 cable, which is network "
                      "topology, not physical mounting."),
        feeds=[], part_of_systems=["network", "chassis"],
        tsb_refs=[], inspection_hint="",
        notes="CAN-CH/grey-A6 address CONFIRMED per " + _MODULE_MAP + "; "
              "physical location UNKNOWN here.",
    ),

    "half_module": _el(
        "module", "HALF -- haptic lane-feedback camera (Bosch MFK2)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module answers "
                      "on CAN-CH via the grey A6 cable; no physical "
                      "location is given."),
        feeds=[], part_of_systems=["network", "adas"],
        tsb_refs=[], inspection_hint="",
        notes="CAN-CH/grey-A6 address CONFIRMED per " + _MODULE_MAP + ".",
    ),

    "dasm_module": _el(
        "module", "DASM -- driver assistance radar (Bosch)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module answers "
                      "on CAN-C with no cable (7/7 scans); no physical "
                      "location is given."),
        feeds=[], part_of_systems=["network", "adas"],
        tsb_refs=[], inspection_hint="",
        notes="CAN-C address CONFIRMED per " + _MODULE_MAP + ".",
    ),

    "rfhub_module": _el(
        "module", "RFHUB -- radio frequency hub (Continental)",
        _unknown_loc("GIORGIO_MODULE_MAP.md confirms this module's "
                      "network address (and that it carries TPMS data); "
                      "no physical location is given."),
        feeds=[], part_of_systems=["network", "tpms"],
        tsb_refs=[], inspection_hint="",
        notes="Address CONFIRMED, identity as RFHUB is INFERRED, per "
              + _MODULE_MAP + ".",
    ),

    "window_riser_circuit": _el(
        "harness_section", "Window-riser motor circuit (B1176 family)",
        _unknown_loc("No TSB in this repo's knowledge base (mes.knowledge) "
                      "covers B1176. Recorded only at a plain-words level: "
                      "door module -> window-motor circuit -> door harness "
                      "connector -> ground. No connector id or pin number "
                      "is sourced, so none is given."),
        feeds=[], part_of_systems=["body"],
        tsb_refs=[], inspection_hint="wiggle test the door harness boot/"
                         "grommet for chafe where it flexes with the door",
        notes="Door-harness flex points are a generic chafe risk on any "
              "platform; this is general automotive-electrical knowledge, "
              "not a Stelvio-specific sourced fact.",
    ),

    "ignition_coil_connector": _el(
        "connector", "Ignition coil connector (per cylinder)",
        _unknown_loc("No misfire-specific TSB is present in "
                      "mes.knowledge for this platform; plain-words only."),
        feeds=[], part_of_systems=["misfire"],
        tsb_refs=[], inspection_hint="connector seating, coil boot "
                         "condition, swap-test between cylinders",
        notes="",
    ),

    "chassis_sensor_connector": _el(
        "connector", "Chassis sensor connector (C141B/C141C family)",
        _unknown_loc("No TSB in mes.knowledge covers C141B/C141C; nothing "
                      "specific is sourced about which sensor or "
                      "connector these codes implicate on this car."),
        feeds=[], part_of_systems=["chassis"],
        tsb_refs=[], inspection_hint="",
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


def elements_for_system(system_key: str) -> list[dict[str, Any]]:
    return [element(eid) for eid, e in ELEMENTS.items()
            if system_key in e.get("part_of_systems", [])]


# ---------------------------------------------------------------------------
# CIRCUITS
# ---------------------------------------------------------------------------

def _hop(elem_id: str, role: str) -> dict[str, str]:
    return {"element": elem_id, "role": role}


_EVAP_PATH = [
    _hop("ecm", "controller"),
    _hop("purge_valve_connector", "connector"),
    _hop("esim_connector", "connector"),
    _hop("esim_ground", "ground"),
]

_EVAP_SYSTEMS_INTERACTION = [
    {"system": "fuel",
     "how": "Tank, filler neck and cap integrity are the leak-path half of "
            "every EVAP code; electrical diagnosis alone cannot clear a "
            "leak-path fault.",
     "confidence": SINGLE_SOURCE, "source": "knowledge.py EVAP family"},
    {"system": "evap",
     "how": "Canister/ESIM hardware condition (flooding, filter "
            "restriction) per 9100471/9100468.",
     "confidence": CONFIRMED, "source": "TSB 9100471, 9100468"},
    {"system": "network",
     "how": "ESIM supply/ground is a BCM/ECM-fed circuit; a chronic EVAP "
            "code does not by itself implicate the vehicle network, but a "
            "coincident U-code cascade would point there instead.",
     "confidence": INFERRED, "source": "reasoned from module feed map"},
    {"system": "ecm_calibration",
     "how": "The PCM flash family (18-030-17 REV. B) lists P0440/P0441/"
            "P0455/P0456 among fixed DTCs -- check calibration level "
            "before condemning any hardware or wiring.",
     "confidence": CONFIRMED, "source": "TSB 18-030-17 REV. B"},
]

_EVAP_INSPECT_STEPS = [
    {"element": "purge_valve_connector",
     "what": "hose routing and connector seating at the ejector tees",
     "how": "visual + wiggle test", "source": "TSB 9100325 Rev 1"},
    {"element": "esim_connector",
     "what": "connector corrosion/seating; housing wet with fuel",
     "how": "visual", "source": "TSB 9100471"},
    {"element": "esim_ground",
     "what": "ground integrity",
     "how": "voltage-drop test", "source": "none -- TechAuthority"},
]

_NETWORK_PATH = [
    _hop("f82", "supply"),
    _hop("bcm_feed_20a", "protection"),
    _hop("bcm", "controller"),
    _hop("xy201", "connector"),
    _hop("g003a", "ground"),
    _hop("g003b", "ground"),
]

_NETWORK_SYSTEMS_INTERACTION = [
    {"system": "network",
     "how": "Every module gatewaying through the BCM drops off the bus "
            "when its supply or ground is compromised, producing a "
            "multi-code cascade that looks like many module faults but is "
            "one electrical event.",
     "confidence": CONFIRMED, "source": "TSB S1808000005"},
]

_NETWORK_INSPECT_STEPS = [
    {"element": "f82", "what": "fuse condition/seating",
     "how": "visual + continuity", "source": "TSB S1808000005"},
    {"element": "bcm_feed_20a", "what": "fuse condition/seating",
     "how": "visual + continuity", "source": "TSB S1808000005"},
    {"element": "xy201", "what": "connector seating",
     "how": "visual + wiggle test", "source": "TSB S2008000032"},
    {"element": "g003a", "what": "ground cleanliness/torque",
     "how": "visual + voltage-drop test", "source": "TSB S2008000032"},
    {"element": "g003b", "what": "ground cleanliness/torque",
     "how": "visual + voltage-drop test", "source": "TSB S2008000032"},
]

_B1176_PATH = [_hop("bcm", "controller"), _hop("window_riser_circuit", "component")]
_B1176_SYSTEMS_INTERACTION = [
    {"system": "body",
     "how": "Door-module/window-motor circuit at a plain-words level "
            "only -- no TSB sourced for this code.",
     "confidence": UNKNOWN, "source": "none"},
]
_B1176_INSPECT_STEPS = [
    {"element": "window_riser_circuit",
     "what": "door harness boot/grommet for chafe",
     "how": "wiggle test", "source": "none -- TechAuthority"},
]

_CHASSIS_PATH = [_hop("bcm", "controller"),
                 _hop("chassis_sensor_connector", "connector")]
_CHASSIS_SYSTEMS_INTERACTION = [
    {"system": "chassis",
     "how": "No TSB sourced for C141B/C141C; electrical path is a "
            "generic supply/controller/connector guess at the family "
            "level, not a specific diagnosis.",
     "confidence": UNKNOWN, "source": "none"},
]
_CHASSIS_INSPECT_STEPS = [
    {"element": "chassis_sensor_connector",
     "what": "connector seating/corrosion",
     "how": "visual", "source": "none -- TechAuthority"},
]

_MISFIRE_PATH = [_hop("battery", "supply"), _hop("ecm", "controller"),
                 _hop("ignition_coil_connector", "connector")]
_MISFIRE_SYSTEMS_INTERACTION = [
    {"system": "misfire",
     "how": "Coil/injector circuit condition is the electrical half of a "
            "misfire; mechanical causes (compression, fuel delivery) are "
            "outside this module's scope.",
     "confidence": UNKNOWN, "source": "none"},
]
_MISFIRE_INSPECT_STEPS = [
    {"element": "ignition_coil_connector",
     "what": "connector seating, swap-test between cylinders",
     "how": "visual + swap test", "source": "none -- TechAuthority"},
]

EVAP_CODES = frozenset({"P0440", "P0441", "P0455", "P0456", "P1CEA"})
_NETWORK_EXPLICIT = frozenset({"U0100", "U1765", "U1960", "U2054", "B1040"})
CHASSIS_CODES = frozenset({"C141B", "C141C"})
MISFIRE_CODES = frozenset({"P0300", "P0301", "P0302", "P0303", "P0304"})


def _is_network_code(base: str) -> bool:
    if base in _NETWORK_EXPLICIT:
        return True
    if base.startswith("U17") and len(base) == 5:
        try:
            n = int(base[1:], 16)
        except ValueError:
            return False
        return 0x1700 <= n <= 0x1716
    return False


def _family_for(base: str) -> Optional[str]:
    if base in EVAP_CODES:
        return "evap"
    if _is_network_code(base):
        return "network"
    if base == "B1176":
        return "b1176"
    if base in CHASSIS_CODES:
        return "chassis"
    if base in MISFIRE_CODES:
        return "misfire"
    return None


_FAMILY_DATA = {
    "evap": (_EVAP_PATH, _EVAP_SYSTEMS_INTERACTION, _EVAP_INSPECT_STEPS),
    "network": (_NETWORK_PATH, _NETWORK_SYSTEMS_INTERACTION,
                _NETWORK_INSPECT_STEPS),
    "b1176": (_B1176_PATH, _B1176_SYSTEMS_INTERACTION, _B1176_INSPECT_STEPS),
    "chassis": (_CHASSIS_PATH, _CHASSIS_SYSTEMS_INTERACTION,
                _CHASSIS_INSPECT_STEPS),
    "misfire": (_MISFIRE_PATH, _MISFIRE_SYSTEMS_INTERACTION,
                _MISFIRE_INSPECT_STEPS),
}

#: Kept for API symmetry with mes.knowledge.base_code -- accepts a failure
#: byte suffix ("P0456-00") and strips it.
def _base(code: str) -> str:
    c = code.strip().upper()
    if "-" in c:
        c = c.split("-", 1)[0]
    return c


def code_electrical_path(code: str) -> dict[str, Any]:
    """The electrical path for one DTC, with element details inlined.

    Returns ``{code, family, path, systems_interaction, inspect_steps}``.
    ``family`` is ``None`` and ``path``/``systems_interaction``/
    ``inspect_steps`` are empty when the code is not one this module has
    curated data for -- callers should treat that as "no electrical path
    known", not as an error.
    """
    base = _base(code)
    family = _family_for(base)
    if family is None:
        return {"code": base, "family": None, "path": [],
                "systems_interaction": [], "inspect_steps": [],
                "note": "no curated electrical path for this code -- "
                        + TECHAUTHORITY}
    path_hops, interactions, steps = _FAMILY_DATA[family]
    path: list[dict[str, Any]] = []
    for hop in path_hops:
        el = element(hop["element"])
        path.append({"element": hop["element"], "role": hop["role"],
                     "details": el,
                     "source": (el or {}).get("location", {}).get("source"),
                     "confidence": (el or {}).get("location", {}).get(
                         "confidence")})
    return {"code": base, "family": family, "path": path,
            "systems_interaction": interactions,
            "inspect_steps": steps}


__all__ = [
    "CONFIRMED", "SINGLE_SOURCE", "INFERRED", "UNKNOWN", "CONFIDENCE_LEVELS",
    "TECHAUTHORITY", "ZONES", "KINDS", "ELEMENTS",
    "element", "elements_for_system", "code_electrical_path",
    "EVAP_CODES", "CHASSIS_CODES", "MISFIRE_CODES",
]
