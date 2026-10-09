"""Vehicle SYSTEMS as a correlational dimension, cutting across every DTC.

A code lookup answers "what fault is this"; it does not answer "what else on
this car shares a cause with it". This module adds that second axis: every
DTC is assigned to one or more ordered vehicle systems (``SYSTEMS``), with a
``depends_on`` graph recording which systems are documented as upstream of
which others (a BCM supply fault cascading into network U-codes, an EVAP
leak code that can trace back to the fuel tank/cap it shares with the fuel
system). ``mes.workup``/``mes.analysis`` already answer "what DTCs happened,
when, together" per vehicle; :func:`correlate` reuses that corpus data and
projects it onto the system graph.

Nothing here is invented. Every ``depends_on`` edge and every exact-code
system assignment carries a ``source`` -- either a citation (this project's
own ``mes.knowledge`` TSB table, ``mes.code_feel``, ``mes.parts``, or the
generic SAE J2012 DTC-prefix convention, named as generic every time it is
used) or, for a relationship nobody has sourced, ``confidence="UNKNOWN"``
with a note pointing at the service manual -- never a silently guessed
dependency. :func:`correlate` is equally careful with its own output: it
never asserts a dependency is *proven*, only that the corpus shows two
systems' codes appearing together, worded as "could be upstream", with the
session counts that back (or don't back) that reading.

Every ``depends_on`` edge also carries a ``technical`` dict (``carries``,
``path``, ``bus``, ``measure``, ``propagates``, ``tsb_refs``) -- the
electrical/physical mechanism behind the edge, not just the prose ``why``.
``carries``/``propagates`` are mandatory on every edge (what actually flows,
and what the failure looks like downstream); ``path`` (element ids from
``mes.electrical``/``mes.layout_systems``), ``bus`` (name/speed from
``cuore.live.buses``) and ``measure`` (a concrete test point, with a
numeric ``limit`` only when a TSB actually states one -- otherwise
``"UNKNOWN (TechAuthority)"``) are included only where this repo's own
sourced data supports them. Each SYSTEM also carries a ``technical`` dict
(``modules``, ``dids``, ``live_channels_with_bands``, ``components``,
``codes_owned``) -- same house rule: every value cites a source and
confidence, or says ``UNKNOWN`` and points at the service manual.

Confidence levels (same scale as the rest of this package):

* ``CONFIRMED``     -- stated in this repo's own sourced table (an FCA/Alfa
                       TSB in ``mes.knowledge``, or a documented part/DTC
                       definition) or the DTC's own SAE-defined meaning
                       (e.g. a P0300-04 misfire code by definition implicates
                       ignition and fuel delivery).
* ``CORROBORATED``  -- two independent sourced findings agree (e.g. the
                       U-code -> network assignment: SAE's communication-DTC
                       range, corroborated by ``mes.knowledge.match_codes``'
                       own network-cascade family rule).
* ``SINGLE-SOURCE``  -- one source, or a generic SAE range convention used as
                       a last-resort, explicitly generic fallback.
* ``UNKNOWN``       -- no sourced relationship found; recorded as such
                       rather than guessed.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNKNOWN = "UNKNOWN"

CONFIDENCE_LEVELS = (CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN)

#: Same wording as ``mes.code_feel``/``mes.parts``/``mes.maintenance_specs``,
#: so an UNKNOWN confidence always reads the same way across this package.
_UNKNOWN_NOTE = "not established in any source checked -- use the service manual (TechAuthority)"

#: Same note, for a ``technical.measure.limit`` with no TSB-stated number.
_UNKNOWN_LIMIT = "UNKNOWN (TechAuthority)"

#: Strip the failure-type byte: "P0456-00" -> "P0456". Mirrors
#: ``mes.knowledge.base_code`` / ``mes.code_feel.base_code``, reimplemented
#: here rather than imported so this module stays a standalone lookup table.
_BASE_RE = re.compile(r"^([PBCU][0-9A-F]{4})", re.IGNORECASE)


def base_code(code: str) -> str:
    m = _BASE_RE.match((code or "").strip().upper())
    return m.group(1) if m else (code or "").strip().upper()


# --- the system graph -------------------------------------------------------

def _tech(carries: str, propagates: str, *,
          path: Optional[list[str]] = None,
          bus: Optional[dict[str, Any]] = None,
          measure: Optional[dict[str, Any]] = None,
          tsb_refs: Optional[list[str]] = None) -> dict[str, Any]:
    """One ``depends_on`` edge's technical detail. ``carries`` (what flows:
    "12 V supply", "ground", "CAN data", "vacuum", "oil pressure", ...) and
    ``propagates`` (a plain sentence of the failure mode) are mandatory on
    every edge. ``path`` (element ids from :mod:`mes.electrical`/
    :mod:`mes.layout_systems`), ``bus`` ({"name", "speed", ...}, from
    :mod:`cuore.live.buses`) and ``measure`` ({"what", "where", "limit",
    "source", "confidence"}) are included only where this repo's own
    sourced data supports them -- never invented to fill the shape."""
    out: dict[str, Any] = {"carries": carries, "propagates": propagates}
    if path:
        out["path"] = list(path)
    if bus:
        out["bus"] = dict(bus)
    if measure:
        out["measure"] = dict(measure)
    if tsb_refs:
        out["tsb_refs"] = list(tsb_refs)
    return out


def _dep(system: str, why: str, confidence: str, source: Optional[str] = None,
         technical: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """One ``depends_on`` edge. Enforces the house rule at definition time:
    a non-UNKNOWN confidence must carry a real citation; an UNKNOWN one gets
    the standard note if the caller didn't supply one. ``technical`` (built
    with :func:`_tech`) is required -- every edge must say what it carries
    and how it propagates, even when that is all that's known."""
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r}")
    if confidence == UNKNOWN and not source:
        source = _UNKNOWN_NOTE
    if not source:
        raise ValueError(f"dependency on {system!r} has no source -- "
                          "mark confidence UNKNOWN or cite one")
    if not technical or "carries" not in technical or "propagates" not in technical:
        raise ValueError(f"dependency on {system!r} has no technical "
                          "dict with carries/propagates")
    return {"system": system, "why": why, "confidence": confidence,
            "source": source, "technical": technical}


def _system(key: str, label: str, components: list[str], *,
            live_channels: Optional[list[str]] = None,
            maintenance_items: Optional[list[str]] = None,
            parts: Optional[list[str]] = None,
            depends_on: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "components": list(components),
        "live_channels": list(live_channels or []),
        "maintenance_items": list(maintenance_items or []),
        "parts": list(parts or []),
        "depends_on": list(depends_on or []),
    }


#: Sources reused by several edges below, named once.
_S1808000005 = "mes.knowledge Bulletin S1808000005 (BCM power-feed/fuse F82 cascade into U-codes)"
_S2008000032 = "mes.knowledge Bulletin S2008000032 (connector XY201 / grounds G003A-B multi-module cascade)"
_S1708000262 = "mes.knowledge Bulletin S1708000262 REV. A (intermittent CAN-private/LIN codes -- spread terminals)"
_S2308000004 = "mes.knowledge Bulletin S2308000004 (cranks/no-start -- verify ECM/PCM B+ feeds and grounds)"
_S2008000078 = "mes.knowledge Bulletin S2008000078 REV. A (U0102 on RWD is a software/config fault, not a bus fault)"
_S1821000001 = "mes.knowledge Bulletin S1821000001 REV. A (AWD tyre-circumference mismatch causes driveline shudder)"
_EVAP_SOURCES = ("mes.parts esim/purge_valve (ECM-commanded solenoid/pump) + "
                 "mes.code_feel EVAP section + mes.knowledge EVAP bulletins "
                 "(S2125000002, 9100469/9100471, 18-030-17)")
_EVAP_FUEL_SOURCES = ("mes.code_feel EVAP section + carparts.com/fs1inc.com P0455/P0456 "
                      "writeups (EVAP shares the tank, fuel cap and fuel-level/pressure "
                      "signal path with the fuel system)")
_RFHUB_SOURCE = ("mes.electrical 'rfhub_module' entry (network address CONFIRMED "
                 "and documented to carry TPMS data, per GIORGIO_MODULE_MAP.md; "
                 "module identity as RFHUB itself is INFERRED, per that same entry)")

#: Electrical-path element ids, as named in mes.electrical.ELEMENTS, reused
#: here only as plain string references (never re-derived) for depends_on
#: edges whose path a sourced TSB actually spells out.
_BCM_SUPPLY_PATH = ["bcm", "f82", "bcm_feed_20a"]
_BCM_CONNECTOR_GROUND_PATH = ["xy201", "g003a", "g003b"]
_BCM_FULL_PATH = _BCM_SUPPLY_PATH + _BCM_CONNECTOR_GROUND_PATH

#: cuore.live.buses facts, restated as plain data (never imported -- this
#: module stays standalone) so a depends_on edge's ``bus`` field can cite
#: the actual pins/bitrate/confidence cuore.live.buses.py sources.
_BUS_CAN_C = {"name": "CAN-C", "speed": "500 kbit/s", "pins": "6/14",
              "confidence": "confirmed", "source": "cuore.live.buses CAN_C"}
_BUS_CAN_IHS = {"name": "CAN-IHS", "speed": "125 kbit/s", "pins": "3/11",
                "confidence": "confirmed", "source": "cuore.live.buses CAN_IHS"}
_BUS_CAN_CH = {"name": "CAN-CH", "speed": "500 kbit/s (inferred)", "pins": "12/13",
               "confidence": "inferred", "source": "cuore.live.buses CAN_CH"}

#: Ordered as given: the "natural" reading order for a dossier, roughly
#: supply -> network -> the engine's own systems -> driveline -> chassis ->
#: comfort/sensor/HVAC extras.
SYSTEMS: dict[str, dict[str, Any]] = {
    "electrical_supply": _system(
        "electrical_supply", "Electrical supply",
        ["12V battery", "alternator", "chassis/engine grounds", "fuses",
         "BCM power feeds"],
        live_channels=["battery_voltage"],
        maintenance_items=["battery_12v"],
        parts=["battery_12v"],
        depends_on=[],
    ),
    "network": _system(
        "network", "Network / CAN buses",
        ["CAN-C", "CAN-IHS", "CAN-CH", "gateway modules", "BCM"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("electrical_supply",
                 "BCM power feeds and chassis grounds are a documented root "
                 "cause of multi-module U-code cascades, not per-module bus "
                 "faults.",
                 CONFIRMED, f"{_S1808000005}; {_S2008000032}; {_S1708000262}",
                 technical=_tech(
                     "12 V supply",
                     "Low supply voltage at the BCM makes several modules "
                     "drop off CAN at once: U-codes on many modules "
                     "simultaneously, not one module's own bus fault.",
                     path=_BCM_FULL_PATH,
                     measure={"what": "voltage drop", "where": "G003A to battery negative",
                              "limit": _UNKNOWN_LIMIT, "source": "S2008000032",
                              "confidence": SINGLE_SOURCE},
                     tsb_refs=["S1808000005", "S2008000032", "S1708000262"],
                 )),
        ],
    ),
    "ignition": _system(
        "ignition", "Ignition",
        ["spark plugs", "ignition coils", "crank/cam position sensors"],
        live_channels=["engine_rpm"],
        maintenance_items=["spark_plugs", "ignition_coils_inspect"],
        parts=["spark_plug", "ignition_coil"],
        depends_on=[
            _dep("electrical_supply",
                 "Coils and the igniter driver need a stable B+ supply; a "
                 "no-start/cranks-only complaint is diagnosed by verifying "
                 "ECM/PCM B+ feeds and grounds before suspecting ignition "
                 "parts.",
                 CONFIRMED, _S2308000004,
                 technical=_tech(
                     "12 V supply",
                     "A weak ECM/PCM B+ feed or ground starves the coil "
                     "driver circuit: cranks-but-no-start, or random "
                     "misfire codes, rather than a single bad coil.",
                     measure={"what": "voltage drop", "where": "ECM/PCM B+ feed to battery positive",
                              "limit": _UNKNOWN_LIMIT, "source": "S2308000004",
                              "confidence": SINGLE_SOURCE},
                     tsb_refs=["S2308000004"],
                 )),
        ],
    ),
    "fuel": _system(
        "fuel", "Fuel",
        ["fuel tank", "fuel pump", "fuel pressure sensor", "fuel filter",
         "injectors", "fuel cap"],
        live_channels=["fuel_level"],
        maintenance_items=["fuel_filter"],
        parts=[],
        depends_on=[
            _dep("electrical_supply",
                 "The fuel pump and injectors are electrically driven, so a "
                 "weak supply/ground can present as a fuel-delivery fault.",
                 UNKNOWN,
                 technical=_tech(
                     "12 V supply",
                     "A weak supply/ground to the fuel pump driver can look "
                     "like a fuel-delivery fault (lean/rich trim codes) "
                     "rather than a pump or injector failure.",
                 )),
        ],
    ),
    "evap": _system(
        "evap", "EVAP (evaporative emissions)",
        ["ESIM", "purge valve", "canister", "vent valve", "fuel cap",
         "vapor lines", "recirculation-line quick-connect"],
        live_channels=["commanded_evap_purge", "evap_vapor_pressure",
                      "evap_vapor_pressure_abs", "fuel_level"],
        maintenance_items=[],
        parts=["esim", "purge_valve", "evap_canister", "evap_quick_connect"],
        depends_on=[
            _dep("electrical_supply",
                 "The ESIM and purge valve are ECM-commanded electrical "
                 "components (a leak-detection pump and a solenoid); a weak "
                 "supply/ground can disrupt the self-test they rely on.",
                 SINGLE_SOURCE, _EVAP_SOURCES,
                 technical=_tech(
                     "12 V supply",
                     "A weak supply/ground to the ESIM or purge-valve "
                     "solenoid disrupts the EVAP self-test, setting a leak "
                     "code (P0440/P0455/P0456) even with no actual leak.",
                     path=["esim_connector", "esim_ground"],
                 )),
            _dep("fuel",
                 "EVAP shares the tank, fuel cap and fuel-level/pressure "
                 "signal path with the fuel system; a fuel-cap or tank-side "
                 "fault can present as an EVAP leak code.",
                 CORROBORATED, _EVAP_FUEL_SOURCES,
                 technical=_tech(
                     "fuel vapor pressure",
                     "A loose fuel cap or tank-side fault changes vapor "
                     "pressure the ESIM reads, setting an EVAP leak code "
                     "that is really a fuel-side mechanical issue.",
                 )),
        ],
    ),
    "air_intake_boost": _system(
        "air_intake_boost", "Air intake / boost",
        ["intake tract", "MAP sensor", "turbocharger", "intercooler",
         "boost hoses", "throttle body"],
        live_channels=["intake_map", "barometric_pressure", "boost",
                      "ecm_195a", "intake_air_temp", "absolute_load",
                      "throttle_position"],
        maintenance_items=["engine_air_filter", "throttle_body_clean",
                           "intake_boost_hoses_inspect"],
        parts=["engine_air_filter", "turbo_intercooler_hose"],
        depends_on=[
            _dep("exhaust_emissions",
                 "The turbocharger is driven by exhaust gas, so an "
                 "exhaust-side restriction or a failing turbo housing can "
                 "present as a boost/MAP-sensor fault.",
                 SINGLE_SOURCE,
                 "general turbocharger architecture (exhaust-driven turbine) "
                 "-- no GU/Stelvio-specific TSB citation found",
                 technical=_tech(
                     "exhaust gas",
                     "An exhaust-side restriction or failing turbo housing "
                     "shows up as low boost / a MAP-sensor plausibility "
                     "code, not a boost-circuit electrical fault.",
                 )),
        ],
    ),
    "cooling": _system(
        "cooling", "Cooling",
        ["radiator", "coolant", "water pump", "thermostat", "cooling fan"],
        live_channels=["engine_coolant_temp"],
        maintenance_items=["coolant"],
        parts=["coolant"],
        depends_on=[],
    ),
    "lubrication": _system(
        "lubrication", "Lubrication (oil)",
        ["oil pump", "oil filter", "oil pressure/level sensors"],
        live_channels=["engine_oil_temp"],
        maintenance_items=[],
        parts=["engine_oil", "oil_filter", "drain_plug_gasket"],
        depends_on=[],
    ),
    "exhaust_emissions": _system(
        "exhaust_emissions", "Exhaust / emissions",
        ["catalytic converter", "O2 sensors", "exhaust manifold",
         "turbo exhaust housing"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("ignition",
                 "A misfire dumps unburned fuel into the exhaust and can "
                 "set secondary catalyst/O2 codes.",
                 SINGLE_SOURCE,
                 "general emissions-system architecture -- no GU/Stelvio-"
                 "specific TSB citation found",
                 technical=_tech(
                     "unburned fuel / combustion gas",
                     "A misfire dumps unburned fuel into the exhaust, "
                     "overheating and fouling the catalyst/O2 sensors: a "
                     "secondary catalyst-efficiency code that traces back "
                     "to the ignition-side misfire, not the catalyst.",
                 )),
        ],
    ),
    "transmission_driveline": _system(
        "transmission_driveline", "Transmission / driveline",
        ["ZF 8HP transmission", "Q4 transfer case", "differentials",
         "driveshafts", "valve body"],
        live_channels=["tcm_04fe", "tcm_0518"],
        maintenance_items=[],
        parts=["transmission_fluid", "transfer_case_fluid"],
        depends_on=[
            _dep("network",
                 "U0102 'lost communication with transfer case' can be an "
                 "ECM software/configuration fault (AWD software on a RWD "
                 "build) rather than a transfer-case hardware or bus fault.",
                 CONFIRMED, _S2008000078,
                 technical=_tech(
                     "CAN data",
                     "An ECM software/configuration mismatch (AWD cal on a "
                     "RWD build) presents as a transfer-case 'lost "
                     "communication' code with no actual bus or hardware "
                     "fault.",
                     bus=_BUS_CAN_C,
                     tsb_refs=["S2008000078"],
                 )),
            _dep("suspension",
                 "Tyre circumference mismatch on AWD causes shudder/bind and "
                 "can damage the transfer case; this is ruled out before any "
                 "driveline hardware is condemned.",
                 CONFIRMED, _S1821000001,
                 technical=_tech(
                     "driveline mechanical coupling",
                     "A tyre-circumference mismatch on AWD binds the "
                     "driveline, presenting as a transfer-case shudder/"
                     "damage complaint that is actually a tire/suspension "
                     "issue.",
                     tsb_refs=["S1821000001"],
                 )),
        ],
    ),
    "brakes_abs": _system(
        "brakes_abs", "Brakes / ABS",
        ["brake pads", "rotors", "calipers", "ABS/ESC modulator",
         "wheel speed sensors", "EPB"],
        live_channels=[],
        maintenance_items=["brake_fluid"],
        parts=["brake_pads_front", "brake_pads_rear", "brake_rotor_front",
              "brake_rotor_rear", "brake_fluid"],
        depends_on=[
            _dep("electrical_supply",
                 "The ABS/ESC modulator and wheel-speed sensors are "
                 "electrically supplied module hardware, like the other "
                 "modules that cascade from a BCM supply fault.",
                 UNKNOWN,
                 technical=_tech(
                     "12 V supply",
                     "A weak supply/ground to the ABS/ESC modulator could "
                     "present as a brake-system module fault, like other "
                     "modules that cascade from a BCM supply fault -- not "
                     "corroborated for this module specifically.",
                 )),
        ],
    ),
    "steering": _system(
        "steering", "Steering",
        ["EPS motor/rack", "steering angle sensor", "steering column"],
        live_channels=[],
        maintenance_items=["power_steering"],
        parts=[],
        depends_on=[
            _dep("electrical_supply",
                 "EPS is an electrically driven power-steering system; a "
                 "weak supply affects assist.",
                 UNKNOWN,
                 technical=_tech(
                     "12 V supply",
                     "A weak supply to the EPS motor/rack reduces or drops "
                     "power-assist, presenting as a steering-effort "
                     "complaint rather than a rack/motor failure.",
                 )),
        ],
    ),
    "suspension": _system(
        "suspension", "Suspension",
        ["shocks/struts", "springs", "control arms", "bushings",
         "tires/wheels"],
        live_channels=[],
        maintenance_items=[],
        parts=["tpms_sensor"],
        depends_on=[],
    ),
    "body_comfort": _system(
        "body_comfort", "Body / comfort",
        ["BCM", "door/window modules", "central locking",
         "interior lighting", "wipers"],
        live_channels=[],
        maintenance_items=["wipers", "hood_and_door_lubrication"],
        parts=["wiper_blades"],
        depends_on=[
            _dep("network",
                 "Most body-module codes gateway through the BCM onto the "
                 "vehicle's CAN/LIN buses; an intermittent bus/terminal "
                 "fault can present as a body-module fault.",
                 SINGLE_SOURCE, _S1708000262,
                 technical=_tech(
                     "CAN data",
                     "An intermittent bus/terminal fault on the gatewayed "
                     "buses presents as a body-module (door/window/"
                     "locking) fault rather than a bus fault.",
                     bus=_BUS_CAN_IHS,
                     tsb_refs=["S1708000262"],
                 )),
            _dep("electrical_supply",
                 "BCM supply-side faults (e.g. fuse F82) are documented to "
                 "cascade into multiple module/body symptoms.",
                 CONFIRMED, _S1808000005,
                 technical=_tech(
                     "12 V supply",
                     "A BCM supply-side fault (fuse F82) cascades into "
                     "multiple body-module symptoms at once (locks, "
                     "windows, lighting) rather than one module failing.",
                     path=_BCM_SUPPLY_PATH,
                     measure={"what": "voltage drop", "where": "fuse F82 to BCM power feed",
                              "limit": _UNKNOWN_LIMIT, "source": "S1808000005",
                              "confidence": SINGLE_SOURCE},
                     tsb_refs=["S1808000005"],
                 )),
        ],
    ),
    "adas_sensors": _system(
        "adas_sensors", "ADAS / sensors",
        ["forward camera", "radar", "park-assist sensors",
         "driver-assist ECU"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("network",
                 "ADAS/chassis-module codes often ride the same gatewayed "
                 "CAN buses as other modules affected by bus/supply events.",
                 UNKNOWN,
                 technical=_tech(
                     "CAN data",
                     "A bus/supply event affecting other gatewayed modules "
                     "could present as an ADAS-sensor communication fault "
                     "-- not corroborated for this system specifically.",
                     bus=_BUS_CAN_CH,
                 )),
        ],
    ),
    "hvac": _system(
        "hvac", "HVAC",
        ["A/C compressor", "blower motor", "cabin air filter",
         "climate control module", "refrigerant circuit"],
        live_channels=[],
        maintenance_items=["cabin_air_filter", "a_c_cabin_service"],
        parts=["cabin_air_filter"],
        depends_on=[],
    ),
    "pcv": _system(
        "pcv", "PCV (crankcase ventilation)",
        ["crankcase breather", "PCV valve/housing", "breather hoses",
         "intake connection"],
        live_channels=[],
        maintenance_items=["pcv_system"],
        parts=[],
        depends_on=[
            _dep("lubrication",
                 "The PCV system vents the crankcase that the lubrication "
                 "system pressurizes with combustion blow-by; a "
                 "lubrication-side fault (excess blow-by, overfill) can "
                 "overwhelm the PCV valve/hoses.",
                 SINGLE_SOURCE,
                 "general PCV system architecture (crankcase ventilation "
                 "draws from the lubrication system's crankcase) -- no "
                 "GU/Stelvio-specific TSB citation found",
                 technical=_tech(
                     "crankcase blow-by gas",
                     "Excess blow-by or an oil overfill overwhelms the PCV "
                     "valve/hoses, presenting as a PCV-side fault that "
                     "actually originates in the lubrication system.",
                 )),
            _dep("air_intake_boost",
                 "The PCV valve/hoses route crankcase vapor into the "
                 "intake tract under vacuum; a stuck-open valve or split "
                 "hose is a documented source of unmetered air (a vacuum "
                 "leak) that can present as a lean or boost-side fault.",
                 SINGLE_SOURCE,
                 "general PCV system architecture (crankcase-to-intake "
                 "vacuum connection) -- no GU/Stelvio-specific TSB "
                 "citation found",
                 technical=_tech(
                     "vacuum",
                     "A stuck-open PCV valve or split hose is an unmetered-"
                     "air (vacuum) leak into the intake tract: a lean or "
                     "boost-side fault that traces back to the PCV system.",
                 )),
        ],
    ),
    "engine_management": _system(
        "engine_management", "Engine management (ECM / sensors)",
        ["ECM", "crank/cam position sensors", "ECM-internal diagnostics"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("electrical_supply",
                 "The ECM/PCM itself needs a stable B+ feed and ground; a "
                 "cranks/no-start complaint is diagnosed by verifying "
                 "ECM/PCM B+ feeds and grounds before suspecting an "
                 "ECM-internal fault.",
                 CONFIRMED, _S2308000004,
                 technical=_tech(
                     "ground",
                     "A poor ECM/PCM ground presents as a cranks/no-start "
                     "or an erratic ECM-internal code, not an ECM hardware "
                     "failure.",
                     measure={"what": "voltage drop", "where": "ECM/PCM ground to battery negative",
                              "limit": _UNKNOWN_LIMIT, "source": "S2308000004",
                              "confidence": SINGLE_SOURCE},
                     tsb_refs=["S2308000004"],
                 )),
        ],
    ),
    "valve_control": _system(
        "valve_control", "Valve control (MultiAir / cam phasing)",
        ["MultiAir solenoid/actuator", "camshaft position actuator",
         "cam phaser", "camshaft position sensors"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("lubrication",
                 "MultiAir/cam-phasing actuators are oil-pressure-"
                 "actuated; low oil pressure or dirty oil is a documented "
                 "cause of camshaft-actuator timing faults on "
                 "oil-pressure-actuated valve systems in general.",
                 SINGLE_SOURCE,
                 "general MultiAir/cam-phaser architecture (oil-pressure-"
                 "actuated) -- no GU/Stelvio-specific TSB citation found",
                 technical=_tech(
                     "oil pressure",
                     "Low oil pressure or dirty oil starves the MultiAir/"
                     "cam-phaser actuator, setting a camshaft timing/"
                     "actuator code that traces back to lubrication, not "
                     "the actuator itself.",
                 )),
        ],
    ),
    "starting_charging": _system(
        "starting_charging", "Starting / charging",
        ["starter motor", "DBSM (dual battery switch module)",
         "stop-start system", "alternator/charging circuit"],
        live_channels=[],
        maintenance_items=["battery_12v"],
        parts=["battery_12v"],
        depends_on=[
            _dep("electrical_supply",
                 "A cranks/no-start or stop-start-disabled complaint is "
                 "diagnosed by verifying ECM/PCM B+ feeds and grounds "
                 "before suspecting the starter or DBSM hardware.",
                 CONFIRMED, _S2308000004,
                 technical=_tech(
                     "12 V supply",
                     "A weak B+ feed or ground presents as a cranks/no-"
                     "start or stop-start-disabled complaint rather than a "
                     "starter or DBSM hardware failure.",
                     tsb_refs=["S2308000004"],
                 )),
        ],
    ),
    "security_immobiliser": _system(
        "security_immobiliser", "Security / immobiliser",
        ["immobiliser (BCM-hosted)", "WIN (wireless ignition node)",
         "RFHUB (passive entry / keyfob)", "PROXI master"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("network",
                 "Immobiliser functions are hosted on the BCM, which is "
                 "also the documented B-CAN/C-CAN gateway; an intermittent "
                 "bus/terminal fault can present as a security-module "
                 "fault.",
                 SINGLE_SOURCE, _S1708000262,
                 technical=_tech(
                     "CAN data",
                     "An intermittent bus/terminal fault on the BCM's "
                     "gatewayed buses can present as a security/"
                     "immobiliser fault, since the immobiliser is hosted "
                     "on the BCM.",
                     bus=_BUS_CAN_C,
                     tsb_refs=["S1708000262"],
                 )),
            _dep("electrical_supply",
                 "BCM supply-side faults (e.g. fuse F82) are documented to "
                 "cascade into multiple module/body symptoms, and the "
                 "immobiliser is hosted on the BCM.",
                 CONFIRMED, _S1808000005,
                 technical=_tech(
                     "12 V supply",
                     "A BCM supply-side fault (fuse F82) can disable the "
                     "BCM-hosted immobiliser along with other BCM-hosted "
                     "functions, not just one security component.",
                     path=_BCM_SUPPLY_PATH,
                     tsb_refs=["S1808000005"],
                 )),
        ],
    ),
    "infotainment_cluster": _system(
        "infotainment_cluster", "Infotainment / cluster",
        ["IPC (instrument panel cluster)", "Uconnect head unit",
         "radio/navigation/media modules"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("network",
                 "Infotainment/cluster modules gateway through the BCM "
                 "onto the vehicle's CAN/LIN buses; an intermittent bus/"
                 "terminal fault can present as an infotainment/cluster "
                 "fault.",
                 SINGLE_SOURCE, _S1708000262,
                 technical=_tech(
                     "CAN data",
                     "An intermittent bus/terminal fault presents as an "
                     "infotainment/cluster fault (blank screen, dropped "
                     "gauges) rather than a bus fault.",
                     bus=_BUS_CAN_C,
                     tsb_refs=["S1708000262"],
                 )),
            _dep("electrical_supply",
                 "BCM supply-side faults (e.g. fuse F82) are documented to "
                 "cascade into multiple module symptoms, infotainment/"
                 "cluster included.",
                 CONFIRMED, _S1808000005,
                 technical=_tech(
                     "12 V supply",
                     "A BCM supply-side fault cascades into infotainment/"
                     "cluster symptoms along with other module symptoms, "
                     "not an IPC/head-unit hardware failure.",
                     path=_BCM_SUPPLY_PATH,
                     tsb_refs=["S1808000005"],
                 )),
        ],
    ),
    "lighting": _system(
        "lighting", "Lighting",
        ["headlamps", "taillamps", "turn signal/marker lamps",
         "AFLS/AHLM/AHBM lighting modules"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("electrical_supply",
                 "Lamps and lighting-control modules are electrical "
                 "loads; a weak supply/ground can present as a lighting "
                 "fault.",
                 UNKNOWN,
                 technical=_tech(
                     "12 V supply",
                     "A weak supply/ground to a lamp or lighting-control "
                     "module presents as a lighting fault -- not "
                     "corroborated for this car specifically.",
                 )),
        ],
    ),
    "wheels_tpms": _system(
        "wheels_tpms", "Wheels / TPMS",
        ["TPMS sensors", "RFHUB (TPMS RF receive)"],
        live_channels=[],
        maintenance_items=[],
        parts=["tpms_sensor"],
        depends_on=[
            _dep("network",
                 "TPMS data is received over the network by the RFHUB, "
                 "whose network address is confirmed in this project's "
                 "own module map (module identity as RFHUB itself is "
                 "inferred).",
                 SINGLE_SOURCE, _RFHUB_SOURCE,
                 technical=_tech(
                     "CAN data",
                     "A bus/supply fault reaching the RFHUB drops TPMS "
                     "data from the network, presenting as a TPMS fault "
                     "that is really a network-side issue.",
                     bus=_BUS_CAN_C,
                 )),
        ],
    ),
    "restraints": _system(
        "restraints", "Restraints (airbags / ORC)",
        ["ORC (occupant restraint controller)", "airbags",
         "pretensioners", "OCM (occupant classification)",
         "SIS (side-impact satellite sensors)"],
        live_channels=[],
        maintenance_items=[],
        parts=[],
        depends_on=[
            _dep("electrical_supply",
                 "The ORC and its satellite sensors are electrically "
                 "supplied safety modules; a weak supply/ground could "
                 "affect them like other modules, but no sourced "
                 "restraints-specific cascade was found.",
                 UNKNOWN,
                 technical=_tech(
                     "12 V supply",
                     "A weak supply/ground to the ORC or its satellite "
                     "sensors could present as a restraints fault, like "
                     "other modules affected by a supply fault -- not "
                     "corroborated for restraints specifically.",
                 )),
        ],
    ),
}


# --- per-SYSTEM technical enrichment ----------------------------------------
#
# modules/dids/components below cite only what this repo's own modules have
# actually sourced (cuore.live.buses' modules_seen tuples, cuore.live.
# did_catalog's EXTRA_DIDS, mes.electrical/mes.layout_systems element
# locations); every system not named gets an empty list rather than a
# guessed entry. live_channels_with_bands is filled from mes.known_good,
# imported lazily (same lazy-import posture correlate() already uses) so a
# knowledge-table miss can never break module import.

#: Bus module codes this project has actually observed/placed per the
#: sourced ``modules_seen`` tuples in cuore.live.buses -- not every module
#: on the car, only the ones with a system this file already models.
_MODULES_BY_SYSTEM: dict[str, list[dict[str, str]]] = {
    "network": [
        {"code": "BCM", "bus": "CAN-C", "confidence": "confirmed"},
        {"code": "RFHUB", "bus": "CAN-C", "confidence": "confirmed"},
        {"code": "IPC", "bus": "CAN-C", "confidence": "confirmed"},
        {"code": "TCM", "bus": "CAN-C", "confidence": "confirmed"},
        {"code": "ABS", "bus": "CAN-CH", "confidence": "inferred"},
        {"code": "EPS", "bus": "CAN-CH", "confidence": "inferred"},
        {"code": "ORC", "bus": "CAN-CH", "confidence": "inferred"},
    ],
    "engine_management": [{"code": "ECM", "bus": "CAN-C", "confidence": "confirmed"}],
    "transmission_driveline": [{"code": "TCM", "bus": "CAN-C", "confidence": "confirmed"}],
    "body_comfort": [{"code": "BCM", "bus": "CAN-C", "confidence": "confirmed"}],
    "infotainment_cluster": [{"code": "IPC", "bus": "CAN-C", "confidence": "confirmed"}],
    "security_immobiliser": [{"code": "BCM", "bus": "CAN-C", "confidence": "confirmed"}],
    "wheels_tpms": [{"code": "RFHUB", "bus": "CAN-C", "confidence": "confirmed"}],
    "brakes_abs": [{"code": "ABS", "bus": "CAN-CH", "confidence": "inferred"}],
    "steering": [{"code": "EPS", "bus": "CAN-CH", "confidence": "inferred"}],
    "restraints": [{"code": "ORC", "bus": "CAN-CH", "confidence": "inferred"}],
    "adas_sensors": [{"code": "PAM", "bus": "CAN-CH", "confidence": "inferred"}],
    "lighting": [{"code": "AFLS", "bus": "CAN-CH", "confidence": "inferred"}],
}
_MODULES_SOURCE = "cuore.live.buses CAN_C/CAN_CH.modules_seen (sourced observations, not a full module list)"

#: First 8 catalogued DID names, module=ECM, from cuore.live.did_catalog
#: EXTRA_DIDS (the only module that catalog adds beyond addressing.DIDS).
#: Confidence matches that source exactly -- danardi78, diesel-tested,
#: UNVERIFIED on this car's petrol 2.0T.
_ECM_DID_NAMES = [
    "Fuel tank level", "Time since start (engine-on timer)", "Engine oil level",
    "Intake manifold temperature (pre-intercooler)", "Throttle position, sensor 1",
    "Throttle position, sensor 2", "Throttle position, sensor 3",
    "Wastegate / overboost valve position",
]
_DIDS_SOURCE = ("cuore.live.did_catalog EXTRA_DIDS, module=ECM (danardi78, "
               "tested on diesel Giulia -- confidence=unverified on this "
               "car's petrol 2.0T)")
_DIDS_BY_SYSTEM: dict[str, list[dict[str, str]]] = {
    "engine_management": [{"name": n, "confidence": "unverified", "source": _DIDS_SOURCE}
                          for n in _ECM_DID_NAMES],
}

#: Zone/confidence for the handful of components this repo's own
#: mes.electrical / mes.layout_systems elements actually place; every other
#: component label below falls back to zone="unknown" -- never guessed.
_COMPONENT_ZONES: dict[str, tuple[str, str, str]] = {
    "fuses": ("trunk", SINGLE_SOURCE,
              "mes.electrical 'f82' element (TSB S1808000005, rear PDC)"),
    "esim": ("rear_left_wheel_well", SINGLE_SOURCE,
             "mes.electrical 'esim_connector' element (TSB 9100469/9100471 "
             "+ EVAP_STELVIO.md; co-location with the canister is INFERRED "
             "there, restated here as SINGLE-SOURCE in this module's own "
             "4-value scale)"),
    "fuel tank": ("underbody", SINGLE_SOURCE,
                  "mes.layout_systems 'fuel_tank' element (TSB 9100471 "
                  "'drop the Fuel Tank' to access the FDM lock ring)"),
}


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _component_entry(label: str) -> dict[str, Any]:
    zone, confidence, source = _COMPONENT_ZONES.get(
        label.lower(), ("unknown", UNKNOWN, _UNKNOWN_NOTE))
    return {"id": _slug(label), "label": label, "zone": zone,
            "confidence": confidence, "source": source}


def _live_channel_band(channel_id: str) -> dict[str, Any]:
    """One system's ``live_channels`` entry resolved to its known-good band
    via :mod:`mes.known_good`, imported lazily (never at module scope) so a
    knowledge-table miss can never break this module's own import."""
    try:
        from . import known_good as _known_good
        row = _known_good.known_good(channel_id)
    except Exception:  # noqa: BLE001 -- enrichment is a nice-to-have, never fatal
        row = None
    if not row:
        return {"channel": channel_id, "normal": None, "warn": None,
                "confidence": UNKNOWN, "source": _UNKNOWN_NOTE}
    return {"channel": channel_id, "normal": row.get("normal"), "warn": row.get("warn"),
            "confidence": row.get("confidence", UNKNOWN),
            "source": row.get("source") or "mes.known_good"}


for _sys_key, _row in SYSTEMS.items():
    _row["technical"] = {
        "modules": [dict(m, source=_MODULES_SOURCE) for m in _MODULES_BY_SYSTEM.get(_sys_key, [])],
        "dids": list(_DIDS_BY_SYSTEM.get(_sys_key, [])),
        "live_channels_with_bands": [_live_channel_band(ch) for ch in _row["live_channels"]],
        "components": [_component_entry(c) for c in _row["components"]],
        "codes_owned": [],  # filled below, once _EXACT_RULES exists
    }


def systems() -> dict[str, dict[str, Any]]:
    """Every system in the graph, in reading order."""
    return SYSTEMS


# --- code -> system(s) -------------------------------------------------------

#: Generic (not vehicle-specific) SAE J2012 range-convention sources, named
#: as generic every time they are the only thing backing an assignment.
_SAE_SOURCE = ("SAE J2012 DTC prefix/range convention (generic category, "
              "not vehicle-specific -- informational fallback only)")
_SAE_SOURCE_P06 = ("SAE J2012 P06xx range (Computer & Auxiliary Outputs -- "
                   "ECM/PCM internal); mapped to 'engine_management' "
                   "(a documented approximation, not a sourced fact)")
_SAE_SOURCE_CHASSIS = ("SAE J2012 C-prefix range (chassis: brakes/steering/"
                       "suspension); mapped to 'brakes_abs' as the default "
                       "chassis bucket (a documented approximation -- a "
                       "specific C-code may actually be steering or "
                       "suspension)")
_SAE_SOURCE_BODY = "SAE J2012 B-prefix range (body)"
_U_CODE_SOURCE = ("SAE J2012 U-prefix range (network/communication), "
                  "corroborated by mes.knowledge.match_codes' own network-"
                  "cascade family rule (3+ lost-communication U-codes)")

#: Exact-code rules, checked before any family/range fallback. Each entry's
#: ``systems`` are the PRIMARY systems for every code it lists. This is the
#: "CODE_RULES" table a SYSTEM's own ``technical.codes_owned`` is derived
#: from below -- never hand-duplicated, so the two can never drift apart.
_EXACT_RULES: tuple[dict[str, Any], ...] = (
    {"codes": ("P0440", "P0441", "P0455", "P0456", "P0457", "P1CEA"),
     "systems": ("evap",), "confidence": CONFIRMED,
     "source": ("mes.knowledge BULLETINS (S2125000002, 9100469/9100471, "
               "9100468, 9100325, 18-048-23, 18-030-17) + mes.code_feel "
               "EVAP section")},
    {"codes": ("P0300", "P0301", "P0302", "P0303", "P0304"),
     "systems": ("ignition", "fuel"), "confidence": CONFIRMED,
     "source": ("SAE J2012 misfire-code definition (a cylinder misfire by "
               "definition implicates spark and fuel delivery) + "
               "mes.code_feel misfire fallback entry")},
    {"codes": ("P0171", "P0172"),
     "systems": ("fuel", "air_intake_boost"), "confidence": CONFIRMED,
     "source": ("SAE J2012 fuel-trim code definition (System Too Lean/Rich "
               "implicates fuel delivery and air-metering/intake leaks)")},
    {"codes": ("B1040", "U1700"),
     "systems": ("network",), "confidence": CONFIRMED,
     "source": ("mes.knowledge Bulletin S1808000005 (BCM power/comms "
               "cascade) -- B1040/U1700 are BCM communications codes")},
    {"codes": ("B1176",),
     "systems": ("body_comfort",), "confidence": SINGLE_SOURCE,
     "source": "generic body-module DTC definition (B1176); no GU/Stelvio-specific TSB found"},
    {"codes": ("C141B", "C141C"),
     "systems": ("adas_sensors",), "confidence": SINGLE_SOURCE,
     "source": "generic chassis/ADAS DTC definition (C141B/C141C); no GU/Stelvio-specific TSB found"},
    {"codes": ("C104B",),
     "systems": ("brakes_abs",), "confidence": SINGLE_SOURCE,
     "source": "generic chassis DTC definition (C104B, ABS/ESC range); no GU/Stelvio-specific TSB found"},
    {"codes": ("P0098", "P00F5", "P105E", "P1189"),
     "systems": ("air_intake_boost",), "confidence": CONFIRMED,
     "source": ("SAE J2012 IAT2/boost-pressure sensor circuit code "
               "definitions (P0098/P00F5/P105E/P1189)")},
    {"codes": ("P0010", "P0011", "P0012", "P0013", "P0014"),
     "systems": ("valve_control",), "confidence": CONFIRMED,
     "source": ("SAE J2012 camshaft position actuator/timing code "
               "definitions ('A'/'B' camshaft actuator circuit and timing "
               "over-advanced/over-retarded) -- generic SAE definition, "
               "not vehicle-specific")},
)

#: Filled now that _EXACT_RULES exists: every system's technical.codes_owned
#: is exactly the codes _EXACT_RULES names it primary for -- derived, not
#: hand-maintained, so the two tables can never disagree.
for _sys_key, _rule in ((s, r) for r in _EXACT_RULES for s in r["systems"]):
    SYSTEMS[_sys_key]["technical"]["codes_owned"].extend(
        c for c in _rule["codes"] if c not in SYSTEMS[_sys_key]["technical"]["codes_owned"])

#: Keyword fallback for P1xxx (manufacturer-defined) codes, and for B-codes
#: (body) that need routing to a more specific body-adjacent system before
#: falling back to the generic body bucket, with no exact entry above:
#: matched against the code's own description text, never guessed from the
#: code number alone. First match wins.
_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("evap", "purge", "canister", "vent valve", "esim"), "evap"),
    (("crankcase",), "pcv"),
    (("multiair", "vvt", "variable valve", "cam phase"), "valve_control"),
    (("turbo", "boost", "charge air", "supercharg", "map sensor"), "air_intake_boost"),
    (("misfire", "ignition coil", "spark"), "ignition"),
    (("airbag", "air bag", "restraint", "occupant restraint"), "restraints"),
    (("headlamp", "headlight", "taillamp", "tail lamp", "turn signal",
      "lamp", "bulb"), "lighting"),
    (("injector", "fuel pump", "fuel pressure", "fuel rail", "fuel trim"), "fuel"),
    (("transmission", "shift", "gear ratio", "clutch", "valve body", "tcm"), "transmission_driveline"),
    (("communication", "network", "can bus", " bus "), "network"),
    (("battery", "charging system", "alternator", "voltage"), "electrical_supply"),
    (("coolant", "thermostat", "radiator", "overheat"), "cooling"),
    (("oil pressure", "oil level", "lubrication"), "lubrication"),
    (("catalyst", "oxygen sensor", "o2 sensor", "exhaust"), "exhaust_emissions"),
    (("brake", "abs", "stability"), "brakes_abs"),
    (("steering",), "steering"),
    (("suspension", "shock", "strut"), "suspension"),
    (("hvac", "air condition", "blower", "climate"), "hvac"),
    (("body control", "door module", "window", "central lock"), "body_comfort"),
    (("camera", "radar", "lane", "park assist"), "adas_sensors"),
)

_KEYWORD_SOURCE = ("description keyword match (manufacturer P1xxx code, or "
                   "a B-code, with no exact entry); the keyword list itself "
                   "is this module's own best-effort mapping, not an "
                   "external citation -- treat as a lead")


def _keyword_system(description: str) -> Optional[str]:
    d = (description or "").lower()
    if not d:
        return None
    for keywords, sys_key in _KEYWORDS:
        if any(k in d for k in keywords):
            return sys_key
    return None


def _sae_fallback(base: str) -> Optional[dict[str, Any]]:
    """The SAE J2012 prefix/range convention, as a generic last resort."""
    if len(base) < 3:
        return None
    letter, rest = base[0], base[1:]
    if letter == "P":
        prefix2 = rest[:2]
        if prefix2 == "01":
            return {"systems": ("fuel", "air_intake_boost"),
                    "confidence": SINGLE_SOURCE, "source": _SAE_SOURCE}
        if prefix2 == "03":
            return {"systems": ("ignition",),
                    "confidence": SINGLE_SOURCE, "source": _SAE_SOURCE}
        if prefix2 == "04":
            return {"systems": ("evap",),
                    "confidence": SINGLE_SOURCE, "source": _SAE_SOURCE}
        if prefix2 == "05":
            return {"systems": ("air_intake_boost", "electrical_supply"),
                    "confidence": SINGLE_SOURCE, "source": _SAE_SOURCE}
        if prefix2 == "06":
            return {"systems": ("engine_management",),
                    "confidence": SINGLE_SOURCE, "source": _SAE_SOURCE_P06}
        if prefix2 in ("07", "08", "09"):
            return {"systems": ("transmission_driveline",),
                    "confidence": SINGLE_SOURCE, "source": _SAE_SOURCE}
        return None
    if letter == "C":
        return {"systems": ("brakes_abs",),
                "confidence": SINGLE_SOURCE, "source": _SAE_SOURCE_CHASSIS}
    if letter == "B":
        return {"systems": ("body_comfort",),
                "confidence": SINGLE_SOURCE, "source": _SAE_SOURCE_BODY}
    if letter == "U":
        return {"systems": ("network",),
                "confidence": CORROBORATED, "source": _U_CODE_SOURCE}
    return None


def systems_for_code(code: str, description: str = "") -> list[dict[str, Any]]:
    """Every system this code implicates: primaries first, then whatever
    systems the primaries' own ``depends_on`` names as upstream.

    Resolution order: exact-code table, then "any U-code is network" (a
    family rule, not a guess -- see ``_U_CODE_SOURCE``), then a P1xxx or
    B-code description-keyword match, then the generic SAE range fallback,
    then give up honestly (one ``UNKNOWN`` row naming no system).

    A code's primary system(s) automatically pull in their declared
    ``depends_on`` edges as ``role="upstream"`` rows, so (for example) every
    EVAP code always carries electrical_supply and fuel upstream without
    that having to be hand-maintained per code here too.
    """
    base = base_code(code)
    primaries: list[tuple[Optional[str], str, str]] = []  # (system, confidence, source)

    matched = False
    for rule in _EXACT_RULES:
        if base in rule["codes"]:
            for sys_key in rule["systems"]:
                primaries.append((sys_key, rule["confidence"], rule["source"]))
            matched = True
            break

    if not matched and base.startswith("U"):
        primaries.append(("network", CORROBORATED, _U_CODE_SOURCE))
        matched = True

    if not matched and (base.startswith("P1") or base.startswith("B")):
        sys_key = _keyword_system(description)
        if sys_key:
            primaries.append((sys_key, SINGLE_SOURCE, _KEYWORD_SOURCE))
            matched = True

    if not matched:
        fb = _sae_fallback(base)
        if fb:
            for sys_key in fb["systems"]:
                primaries.append((sys_key, fb["confidence"], fb["source"]))
            matched = True

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not matched:
        out.append({"system": "UNKNOWN", "role": "primary",
                   "confidence": UNKNOWN, "source": _UNKNOWN_NOTE})
        return out

    for sys_key, confidence, source in primaries:
        if sys_key in seen:
            continue
        seen.add(sys_key)
        out.append({"system": sys_key, "role": "primary",
                   "confidence": confidence, "source": source})

    for sys_key, _conf, _src in primaries:
        sys_def = SYSTEMS.get(sys_key)
        if sys_def is None:
            continue
        for dep in sys_def["depends_on"]:
            if dep["system"] in seen:
                continue
            seen.add(dep["system"])
            out.append({"system": dep["system"], "role": "upstream",
                       "confidence": dep["confidence"], "source": dep["source"]})
    return out


def _primary_systems(code: str, description: str = "") -> list[str]:
    return [e["system"] for e in systems_for_code(code, description)
            if e["role"] == "primary" and e["system"] != "UNKNOWN"]


# --- corpus correlation -----------------------------------------------------

def correlate(vin: str) -> dict[str, Any]:
    """Project one vehicle's whole DTC corpus onto the system graph.

    Built from :func:`mes.analysis.dtc_history` (the same per-occurrence
    file/timestamp data :func:`mes.workup.build` uses) plus
    ``mes.workup.build`` itself for the current-picture open codes and the
    latest clear assessment, used only to classify each system's
    ``status``. Simulation logs are excluded (``dtc_history``'s default).

    Returns ``{"error": ...}`` if no logs match this VIN -- never a
    half-empty dossier.
    """
    from . import analysis, workup as workup_mod

    history = analysis.dtc_history(vin=vin)
    if not history:
        return {"error": "no logs match", "vin": vin}

    primary_map: dict[str, list[str]] = {}
    for code, rec in history.items():
        descr = rec.descriptions[0] if rec.descriptions else ""
        primary_map[code] = _primary_systems(code, descr)

    # --- per-session (per-file) system sets ---------------------------------
    session_codes: dict[str, set[str]] = {}
    for code, rec in history.items():
        for occ in rec.occurrences:
            fname = occ.get("file")
            if not fname:
                continue
            session_codes.setdefault(fname, set()).add(code)
    session_systems: dict[str, set[str]] = {
        fname: {s for c in codes for s in primary_map.get(c, [])}
        for fname, codes in session_codes.items()
    }
    total_sessions = len(session_systems)

    # --- current picture, for status classification only -------------------
    try:
        dossier = workup_mod.build(vin=vin)
    except Exception:  # noqa: BLE001 -- status is a nice-to-have, never fatal
        dossier = {}
    cp = dossier.get("current_picture", {}) if isinstance(dossier, dict) else {}
    latest = cp.get("latest_session") or {}
    open_codes = {d.get("dtc") for d in latest.get("dtcs", []) if d.get("dtc")}
    clear = cp.get("clear_assessment") or {}
    cleared_codes = set(clear.get("codes_cleared") or [])

    # --- by_system -----------------------------------------------------------
    by_system: list[dict[str, Any]] = []
    for sys_key in SYSTEMS:
        codes_here = sorted(c for c, syss in primary_map.items() if sys_key in syss)
        if not codes_here:
            by_system.append({"system": sys_key, "codes": [], "sessions": 0,
                              "first": None, "last": None, "status": "clean"})
            continue
        sessions_here = sum(1 for syss in session_systems.values() if sys_key in syss)
        firsts = [history[c].first_seen for c in codes_here if history[c].first_seen]
        lasts = [history[c].last_seen for c in codes_here if history[c].last_seen]
        if open_codes & set(codes_here):
            status = "active"
        elif cleared_codes & set(codes_here):
            status = "cleared_unverified"
        else:
            status = "stale"
        by_system.append({
            "system": sys_key, "codes": codes_here, "sessions": sessions_here,
            "first": min(firsts) if firsts else None,
            "last": max(lasts) if lasts else None,
            "status": status,
        })

    # --- co-occurrence, pairs with >= 2 shared sessions only ----------------
    active = [row["system"] for row in by_system if row["sessions"] > 0]
    co_occurrence: list[dict[str, Any]] = []
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            sessions_a = sum(1 for syss in session_systems.values() if a in syss)
            sessions_b = sum(1 for syss in session_systems.values() if b in syss)
            together = sum(1 for syss in session_systems.values()
                           if a in syss and b in syss)
            if together < 2:
                continue
            expected = (sessions_a * sessions_b) / total_sessions if total_sessions else 0
            lift = round(together / expected, 2) if expected else None
            label_a, label_b = SYSTEMS[a]["label"], SYSTEMS[b]["label"]
            reading = (
                f"{label_a} and {label_b} codes appeared together in "
                f"{together} of {total_sessions} session(s) ({sessions_a} had "
                f"{label_a} codes, {sessions_b} had {label_b} codes); lift "
                f"{lift if lift is not None else 'n/a'} -- correlation only, "
                "could point at a shared cause or be coincidental overlap."
            )
            co_occurrence.append({"a": a, "b": b, "sessions_together": together,
                                   "sessions_a": sessions_a, "sessions_b": sessions_b,
                                   "lift": lift, "reading": reading})

    # --- chains: depends_on edges, with corpus evidence where it exists ------
    chains: list[dict[str, Any]] = []
    for row in by_system:
        sys_key = row["system"]
        if row["sessions"] == 0:
            continue
        deps = SYSTEMS[sys_key]["depends_on"]
        if not deps:
            continue
        possible_upstream = []
        for dep in deps:
            evidence = None
            for co in co_occurrence:
                if {co["a"], co["b"]} == {sys_key, dep["system"]}:
                    evidence = (f"{co['sessions_together']} of {total_sessions} "
                               f"session(s) with {SYSTEMS[sys_key]['label']} codes "
                               f"also carried {SYSTEMS[dep['system']]['label']} "
                               f"codes (lift {co['lift']}) -- could be upstream, "
                               "not proven.")
                    break
            possible_upstream.append({"system": dep["system"], "why": dep["why"],
                                      "evidence": evidence})
        chains.append({"issue": f"{SYSTEMS[sys_key]['label']} codes",
                       "possible_upstream": possible_upstream})

    # --- findings, plain dated sentences -------------------------------------
    today = date.today().isoformat()
    findings: list[str] = []
    for row in by_system:
        if row["sessions"] == 0:
            continue
        findings.append(
            f"{today}: {SYSTEMS[row['system']]['label']} shows "
            f"{len(row['codes'])} code(s) across {row['sessions']} "
            f"session(s) ({row['first']} to {row['last']}), status={row['status']}."
        )
    for co in co_occurrence:
        findings.append(f"{today}: {co['reading']}")
    if not findings:
        findings.append(f"{today}: no DTCs found for {vin} across the corpus.")

    return {
        "vin": vin,
        "by_system": by_system,
        "co_occurrence": co_occurrence,
        "chains": chains,
        "findings": findings,
    }


# --- shared system vocabulary: free text -> one of the 25 SYSTEMS keys -----
#
# Every other store that carries a "system" string (mes.jobs hypotheses,
# mes.mechanic_tests test rows, the dossier's generic open-work family
# keys, a liveboard channel's system, the electrical layout's own small tag
# set) should mean the same 25 keys this module defines. This section is
# the one place that resolves free text to a key -- additive to the SYSTEMS
# graph above, never changing it.

def _norm_text(text: Optional[str]) -> str:
    """Lowercase, punctuation/underscores collapsed to single spaces,
    trimmed -- the one normalisation :func:`normalize_system` and every
    table below it is compared through, so "EVAP", "evap_system" and
    "Evap System" all land on the same string."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").strip().lower()).strip()


#: systems-graph key -> [electrical-layout tag, ...]. mes.electrical.
#: ELEMENTS carry their own small tag vocabulary (``part_of_systems``),
#: built independently of this module's 25-key graph and not a 1:1 match --
#: this is the one canonical map between the two. Previously duplicated as
#: cuore.services.system_detail_bridge's own local ``_ELEMENT_TAGS_FOR``
#: (same shape, same values); this is now the single source both that file
#: and cuore.services.electrical_bridge.elements_for_system read from, so
#: the two vocabularies can never drift apart. A systems-graph key with no
#: entry here simply has no electrical-layout elements tagged for it --
#: not a gap, the documented overlap mes.electrical's own callers already
#: note.
ELEMENT_TAGS_FOR: dict[str, list[str]] = {
    "evap": ["evap"], "network": ["network"], "lighting": ["lighting"],
    "brakes_abs": ["chassis"], "adas_sensors": ["adas"],
    "body_comfort": ["body"], "starting_charging": ["charging", "cranking"],
    "engine_management": ["misfire"], "wheels_tpms": ["tpms"],
}

#: Free text/aliases this project's own data actually produces, each
#: resolved to one of the 25 SYSTEMS keys -- checked only after an exact
#: key/label match fails (see :func:`normalize_system`). Never fuzzy --
#: an alias not listed here (and not an exact key/label) resolves to
#: ``None``, same house rule as every other lookup in this module.
ALIASES: dict[str, str] = {
    # dossier_bridge's generic open-work family keys
    # (_GENERIC_FAMILY_RULES) and the hand-curated "EVAP"/"network"
    # hypothesis-suggestion system strings -- jobs_bridge compares a
    # hypothesis's own system against these, so they need the same
    # resolution as everything else here.
    "fuel_trim": "fuel", "fuel trim": "fuel",
    "powertrain_other": "engine_management",
    "powertrain (other)": "engine_management",
    "chassis": "brakes_abs",
    "adas": "adas_sensors",
    "body": "body_comfort",

    # free text a mechanic or a form might actually type for EVAP
    "evap system": "evap", "evaporative system": "evap",
    "evaporative emissions": "evap", "evaporative emissions system": "evap",

    # SAE J1979 Mode 01 PID 01 OBD-II monitor names (cuore.live.obd's
    # _CONTINUOUS/_SPARK/_COMPRESSION tables) -- restated here so free text
    # naming a monitor ("the O2 heater monitor") also resolves. See
    # MONITOR_TO_SYSTEM below for the dedicated, exact-name table
    # system_states()-style callers should actually use for readiness data;
    # these are the same assignments, just reachable as free text too.
    "fuel system": "fuel",
    "comprehensive components": "engine_management",
    "comprehensive component": "engine_management",
    "catalyst": "exhaust_emissions", "cat": "exhaust_emissions",
    "heated catalyst": "exhaust_emissions",
    "secondary air system": "exhaust_emissions", "secondary air": "exhaust_emissions",
    "a c refrigerant": "hvac", "ac refrigerant": "hvac",
    "oxygen sensor": "exhaust_emissions", "o2 sensor": "exhaust_emissions",
    "oxygen sensor heater": "exhaust_emissions", "o2 heater": "exhaust_emissions",
    "egr system": "exhaust_emissions", "egr": "exhaust_emissions",
    "egr vvt system": "valve_control",
    "nmhc catalyst": "exhaust_emissions",
    "nox scr monitor": "exhaust_emissions",
    "boost pressure": "air_intake_boost",
    "exhaust gas sensor": "exhaust_emissions",
    "pm filter": "exhaust_emissions",
}

# Electrical-layout tags are also valid aliases for their system key (e.g.
# "cranking" -> "starting_charging") -- merged in rather than hand-copied so
# the two tables can never disagree. ``setdefault``: an explicit entry
# above (there are none that overlap today) would always win.
for _tag_key, _tags in ELEMENT_TAGS_FOR.items():
    for _tag in _tags:
        ALIASES.setdefault(_tag, _tag_key)

_ALIASES_NORM: dict[str, str] = {_norm_text(k): v for k, v in ALIASES.items()}
_LABEL_NORM_TO_KEY: dict[str, str] = {_norm_text(v["label"]): k for k, v in SYSTEMS.items()}


def normalize_system(text: Optional[str]) -> Optional[str]:
    """Resolve free text to one of the 25 :data:`SYSTEMS` keys, or ``None``.

    Checked in order: (1) an exact key, case/punctuation-insensitive (e.g.
    "Air intake / boost" -> ``air_intake_boost``), (2) an exact label match
    (e.g. "EVAP (evaporative emissions)" -> ``evap``), (3) the
    :data:`ALIASES` table (electrical-layout tags, OBD-II monitor names,
    and the free-text/family-name spellings this project's own forms and
    dossier families actually produce). No fuzzy matching beyond that --
    unrecognised text (or empty/whitespace-only text) returns ``None``
    rather than a guess.
    """
    norm = _norm_text(text)
    if not norm:
        return None
    key_form = norm.replace(" ", "_")
    if key_form in SYSTEMS:
        return key_form
    if norm in _LABEL_NORM_TO_KEY:
        return _LABEL_NORM_TO_KEY[norm]
    return _ALIASES_NORM.get(norm)


# --- OBD-II readiness monitor -> system key (per-system VERIFIED_CLEAN) ----
#
# SAE J1979 Mode 01 PID 01 monitor names, exactly as cuore.live.obd's
# decode_readiness() produces them (_CONTINUOUS/_SPARK/_COMPRESSION), mapped
# to the systems-graph key that monitor's completeness speaks to. Not every
# system has a monitor; a key absent from monitors_for_system's output has
# none at all -- that absence is itself the fact cuore.services.
# systems_map_bridge.system_states() needs (a system with no monitor can
# never earn VERIFIED_CLEAN from a monitor read, only from a clean car scan
# after the clear), never guessed. Ambiguous SAE categories (O2/O2-heater
# could read as fuel-trim or exhaust-sensor; EGR/VVT combines an emissions
# and a valve-timing monitor on compression-ignition ECUs) are resolved to
# the single most directly-affected system, documented inline -- not a
# sourced fact, this module's own best-effort reading, same posture as
# mes.systems._KEYWORDS above.
MONITOR_TO_SYSTEM: dict[str, str] = {
    "Misfire": "ignition",
    "Fuel system": "fuel",
    "Comprehensive components": "engine_management",
    "Catalyst": "exhaust_emissions",
    "Heated catalyst": "exhaust_emissions",
    "Evaporative system": "evap",
    "Secondary air system": "exhaust_emissions",
    "A/C refrigerant": "hvac",
    "Oxygen sensor": "exhaust_emissions",  # O2 sensor itself: exhaust-side component
    "Oxygen sensor heater": "exhaust_emissions",
    "EGR system": "exhaust_emissions",
    "NMHC catalyst": "exhaust_emissions",
    "NOx/SCR monitor": "exhaust_emissions",
    "Boost pressure": "air_intake_boost",
    "Exhaust gas sensor": "exhaust_emissions",
    "PM filter": "exhaust_emissions",
    "EGR/VVT system": "valve_control",  # combined diesel bit -- VVT half chosen
}
_MONITOR_TO_SYSTEM_NORM: dict[str, str] = {_norm_text(k): v for k, v in MONITOR_TO_SYSTEM.items()}


def system_for_monitor(name: Optional[str]) -> Optional[str]:
    """The systems-graph key an OBD-II readiness monitor's completeness
    speaks to, or ``None`` for a monitor name this table doesn't
    recognise."""
    return _MONITOR_TO_SYSTEM_NORM.get(_norm_text(name))


def monitors_for_system(key: str) -> list[str]:
    """Every OBD-II monitor name (as :func:`cuore.live.obd.decode_readiness`
    produces it) that speaks to ``key`` -- empty when this system has no
    monitor at all, the fact ``system_states()`` needs to keep a
    no-monitor system at CLEARED_UNVERIFIED instead of inventing a
    VERIFIED_CLEAN it has no readiness evidence for."""
    return [name for name, sys_key in MONITOR_TO_SYSTEM.items() if sys_key == key]


__all__ = ["SYSTEMS", "systems", "systems_for_code", "correlate", "base_code",
           "CONFIRMED", "CORROBORATED", "SINGLE_SOURCE", "UNKNOWN",
           "ALIASES", "ELEMENT_TAGS_FOR", "normalize_system",
           "MONITOR_TO_SYSTEM", "system_for_monitor", "monitors_for_system"]
