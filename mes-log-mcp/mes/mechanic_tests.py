"""Mechanic test catalogue: every shop-floor diagnostic test that applies to
the 2018 Alfa Romeo Stelvio 2.0T GME (Giorgio platform), cross-marked for
the Giulia 2.0T (same engine/platform family) and the Maserati Grecale 2.0T
(Giorgio-derived platform, same Stellantis GME-T4 engine family).

Same house rules as :mod:`mes.known_good` / :mod:`mes.systems`: nothing in
here is invented. Every ``pass_criteria`` row carries a ``source`` and a
``confidence`` --

* ``CONFIRMED``     -- stated in a manufacturer document (FCA/Stellantis
                       TechAuthority, DOT/FMVSS regulatory standard).
* ``CORROBORATED``  -- two independent sources agree, or lifted straight
                       from a ``mes.known_good`` row already carrying that
                       confidence for this exact channel.
* ``SINGLE-SOURCE``  -- one source, including a generic/industry-practice
                       rule of thumb used as an explicit, named fallback
                       (never confused with a manufacturer figure).
* ``UNKNOWN``       -- no sourced number exists; the car's own service
                       manual / TechAuthority is pointed to instead, and
                       ``spec`` is prose ("see service manual"), never a
                       guessed number. A numeric ``spec`` is never paired
                       with ``UNKNOWN`` -- enforced at load time below.

Four read-only lookups, the whole public surface:

* :func:`all_tests`        -- every test, as a list.
* :func:`test`              -- one test by id, or ``None``.
* :func:`tests_for_codes`   -- tests whose ``related_codes`` match any of
                               the given DTCs (prefix match, e.g. "P0455"
                               matches a related_codes entry "P04").
* :func:`tests_for_systems` -- tests touching any of the given
                               :mod:`mes.systems` system ids.

Research pass done 2026-10-08, same posture as ``known_good.py``'s own
research-pass note: public sources (OBD-II/repair-reference sites, DOT/SAE
standards, this repo's own ``mes.known_good``/``mes.systems`` sourced rows)
plus explicit, named industry-practice rules of thumb where no
manufacturer figure exists. No paywalled/bot-gated FCA TechAuthority
document was read for this pass -- every TechAuthority pointer below is a
"go get it", never a claim that document was read.
"""

from __future__ import annotations

from typing import Any, Optional

from .systems import CONFIDENCE_LEVELS, CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN
from .systems import SYSTEMS

#: Same wording as the rest of this package's UNKNOWN notes.
TECHAUTHORITY = "use the service manual, TechAuthority"

#: Generic/industry-practice rule-of-thumb source label, named explicitly
#: per instruction -- never confused with a Stelvio-specific or
#: manufacturer-sourced figure.
INDUSTRY_PRACTICE = "industry practice"

CAR_STATES = ("KOEO", "KOER", "cold", "hot", "driving", "key-off")

#: ``not_done`` is a display-only state (no result recorded yet) -- never a
#: value a caller posts. :data:`POSTABLE_RESULTS` is what a result-recording
#: call should validate against.
RESULTS = ("pass", "fail", "inconclusive", "not_possible", "not_done")
POSTABLE_RESULTS = ("pass", "fail", "inconclusive", "not_possible")

CATEGORIES = (
    "emissions", "intake_boost", "cooling", "fuel", "lubrication",
    "leak_detection", "mechanical_engine", "ignition", "electrical",
    "network", "brakes", "driveline", "exhaust", "inspection",
)

#: Models this catalogue cross-marks, beyond the Stelvio 2018 2.0T this
#: catalogue is built for -- every test defaults ``True`` for the Stelvio
#: (the catalogue's whole reason to exist) and is marked per-test for the
#: other two.
_MODELS = ("stelvio_2.0t_2018", "giulia_2.0t", "grecale_2.0t")

TESTS: dict[str, dict[str, Any]] = {}

_ORDER: list[str] = []


def _applies(giulia: bool = True, grecale: bool = True) -> dict[str, bool]:
    """``stelvio_2.0t_2018`` is always ``True`` -- this whole catalogue is
    built for that car. ``giulia``/``grecale`` default ``True`` (same
    engine family / Giorgio-derived platform) and are set ``False`` on the
    few tests that are genuinely Stelvio/FCA-procedure-specific."""
    return {"stelvio_2.0t_2018": True, "giulia_2.0t": giulia, "grecale_2.0t": grecale}


def _pc(parameter: str, spec: Any, unit: str, source: str, confidence: str) -> dict[str, Any]:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r} for pass_criteria {parameter!r}")
    if confidence == UNKNOWN and isinstance(spec, (int, float)):
        raise ValueError(f"pass_criteria {parameter!r} has a numeric spec with UNKNOWN "
                         "confidence -- never invent a number")
    return {"parameter": parameter, "spec": spec, "unit": unit,
           "source": source, "confidence": confidence}


def _t(id_: str, name: str, category: str, systems: list[str], applies_to: dict[str, bool],
      purpose: str, car_state: str, when_to_use: str, tools: list[str],
      procedure: list[str], pass_criteria: list[dict[str, Any]], fail_means: str,
      related_codes: list[str], supports_hypotheses: list[str],
      refutes_hypotheses: list[str], duration_min: int, safety: str = "",
      hazards: Optional[list[str]] = None) -> None:
    if id_ in TESTS:
        raise ValueError(f"duplicate test id {id_!r}")
    if category not in CATEGORIES:
        raise ValueError(f"bad category {category!r} for {id_!r}")
    for s in systems:
        if s not in SYSTEMS:
            raise ValueError(f"unknown system {s!r} for test {id_!r}")
    if car_state not in CAR_STATES:
        raise ValueError(f"bad car_state {car_state!r} for {id_!r}")
    for key in applies_to:
        if key not in _MODELS:
            raise ValueError(f"unknown model {key!r} in applies_to for {id_!r}")
    TESTS[id_] = {
        "id": id_, "name": name, "category": category, "systems": list(systems),
        "applies_to": dict(applies_to), "purpose": purpose, "car_state": car_state,
        "when_to_use": when_to_use, "tools": list(tools), "procedure": list(procedure),
        "pass_criteria": list(pass_criteria), "fail_means": fail_means,
        "related_codes": list(related_codes), "supports_hypotheses": list(supports_hypotheses),
        "refutes_hypotheses": list(refutes_hypotheses), "duration_min": duration_min,
        "safety": safety, "hazards": list(hazards or []),
    }
    _ORDER.append(id_)


# ===========================================================================
# Emissions / EVAP
# ===========================================================================

_t("evap_smoke", "EVAP smoke test", "emissions", ["evap"], _applies(),
  purpose="Find a leak in the fuel vapor system by filling it with visible/UV smoke "
          "under gentle pressure and watching for where it escapes.",
  car_state="key-off",
  when_to_use="P0442/P0455/P0456 or any EVAP small/large leak code, before replacing "
              "any EVAP part on a guess.",
  tools=["smoke machine", "EVAP service port adapter or purge line disconnect",
        "UV light (if using UV dye smoke)", "shop light / mirror"],
  procedure=[
      "Confirm fuel level is in the 15-85% window (vapor space needed to see smoke).",
      "Connect smoke machine to the EVAP system (purge line or service port), low "
      "pressure (~0.5-1 psi / per machine instructions).",
      "Cap the system and let smoke fill for 1-2 minutes.",
      "Inspect gas cap, filler neck, fuel tank seams, EVAP canister, purge/vent valve "
      "connections and hoses for escaping smoke.",
      "Note exact leak location(s); photograph for the job file.",
  ],
  pass_criteria=[_pc("visible leak", "none found", "", TECHAUTHORITY, UNKNOWN)],
  fail_means="A located, visible leak point identifies the failed component directly "
             "-- no further guessing needed for that leak.",
  related_codes=["P0442", "P0455", "P0456", "P0457"],
  supports_hypotheses=["EVAP leak"], refutes_hypotheses=["EVAP leak"],
  duration_min=20, safety="Use smoke machine per its own manual; do not exceed its "
                          "rated pressure -- EVAP components are not designed for "
                          "boost-level pressure.",
  hazards=["fuel vapor"])

_t("intake_boost_smoke_leak", "Intake/boost leak smoke test", "intake_boost",
  ["air_intake_boost"], _applies(),
  purpose="Find an air leak between the throttle body/MAF and the turbo/intercooler "
          "piping using smoke under light vacuum or low pressure.",
  car_state="key-off",
  when_to_use="Rough idle, lean fuel trims, boost-related codes, or a whistle/hiss "
              "under load.",
  tools=["smoke machine", "intake blanking plate or adapter"],
  procedure=[
      "Block the intake tract at the throttle body (or feed smoke in through a vacuum "
      "port with the engine off).",
      "Fill the tract with smoke at low pressure.",
      "Inspect every clamp, boot, intercooler seam and sensor o-ring for escaping smoke.",
      "Note exact leak location(s).",
  ],
  pass_criteria=[_pc("visible leak", "none found", "", TECHAUTHORITY, UNKNOWN)],
  fail_means="A located leak point explains lean trims/rough idle/boost loss directly.",
  related_codes=["P0171", "P0101", "P0299", "P0106"],
  supports_hypotheses=["intake leak", "boost leak"],
  refutes_hypotheses=["intake leak", "boost leak"],
  duration_min=20, hazards=[])

_t("purge_vent_actuation", "EVAP purge/vent solenoid actuation check", "emissions",
  ["evap"], _applies(),
  purpose="Confirm the purge and vent solenoids actually open/close on command, "
          "rather than assuming the commanded state matches reality.",
  car_state="KOEO",
  when_to_use="Before condemning a purge or vent valve on a code alone -- commanded "
              "vs. actual state mismatches are a common root cause.",
  tools=["scan tool with bidirectional control (MCP actuator control)",
        "stethoscope or hand on the valve body"],
  procedure=[
      "Command the purge solenoid open via the MCP actuator-control interface; "
      "listen/feel for the valve clicking.",
      "Command the vent solenoid closed, then open; listen/feel for each transition.",
      "Read back commanded vs. observed state if the scan tool reports both.",
  ],
  pass_criteria=[_pc("actuation on command", "valve clicks/moves on each command",
                     "", TECHAUTHORITY, UNKNOWN)],
  fail_means="A valve that does not actuate on command is the fault, independent of "
             "any smoke result.",
  related_codes=["P0443", "P0446", "P0449", "P1443"],
  supports_hypotheses=["EVAP leak", "EVAP valve stuck"],
  refutes_hypotheses=["EVAP valve stuck"],
  duration_min=10,
  safety="HTTP surface is read-only; this test is only available through the MCP "
         "actuator-control tool, never through the HTTP job/tests API -- it writes a "
         "live command to the car.",
  hazards=[])

_t("esim_vacuum_test_a", "ESIM vacuum test (Test A)", "emissions", ["evap"],
  _applies(grecale=False),
  purpose="FCA's own leak-detection-pump (ESIM) self-test procedure, Test A -- "
          "exercises the pump's own vacuum/pressure switch logic rather than a "
          "manual smoke fill.",
  car_state="KOEO",
  when_to_use="When the EVAP leak-detection pump itself is suspect (no leak found by "
              "smoke, but a P0455/0456 persists), or to corroborate a smoke-test "
              "result.",
  tools=["scan tool with FCA/Stellantis ESIM test routine support"],
  procedure=[
      "Confirm fuel level is in the EVAP-verification window (15-85%).",
      "Run the scan tool's ESIM Test A routine per its on-screen steps.",
      "Record the pass/fail result the routine itself reports.",
  ],
  pass_criteria=[_pc("ESIM Test A result", "see service manual", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="A failed Test A points at the leak-detection pump assembly itself, not "
             "necessarily a leak elsewhere in the system.",
  related_codes=["P0455", "P0456", "P2450", "P2451"],
  supports_hypotheses=["EVAP leak", "ESIM signal path"],
  refutes_hypotheses=["ESIM signal path"],
  duration_min=10, hazards=[])

_t("fuel_trim_o2_observation", "Fuel trim / O2 sensor observation", "fuel",
  ["fuel", "engine_management"], _applies(),
  purpose="Watch live short/long-term fuel trim and O2 sensor voltage to spot a lean "
          "or rich condition and whether the O2 sensor is actively switching.",
  car_state="hot",
  when_to_use="Any suspected intake/EVAP/fuel-delivery leak, or a misfire with no "
              "obvious mechanical cause -- read before and after a repair to confirm "
              "trims recovered.",
  tools=["scan tool (live PIDs)"],
  procedure=[
      "Warm engine to closed-loop operation.",
      "Record short- and long-term fuel trim, bank 1 (and bank 2 if the platform "
      "reports it) at idle and at a steady 2000 rpm.",
      "Record O2 sensor voltage; confirm it is actively switching, not static.",
  ],
  pass_criteria=[
      _pc("short_fuel_trim_b1", [-10, 10], "%",
         "https://www.obd-codes.com/faq/fuel-trims.php", CORROBORATED),
      _pc("long_fuel_trim_b1", [-10, 10], "%",
         "https://www.obd-codes.com/faq/fuel-trims.php", CORROBORATED),
      _pc("o2_b1s1_voltage switching", "actively cycling ~0.1-0.9 V, not static", "V",
         "https://www.fluke.com/en-us/learn/blog/digital-multimeters/"
         "how-to-monitor-oxygen-sensor-voltage-with-a-multimeter", CORROBORATED),
  ],
  fail_means="Trim beyond roughly +/-20% (same generic band) or a static O2 voltage "
             "points at an unmetered air/fuel leak or a failing sensor, not yet "
             "isolated to a part.",
  related_codes=["P0171", "P0172", "P0174", "P0175", "P0300"],
  supports_hypotheses=["intake leak", "EVAP leak", "fuel delivery fault"],
  refutes_hypotheses=["intake leak", "fuel delivery fault"],
  duration_min=10, hazards=[])

_t("misfire_counters", "Misfire counter review", "ignition",
  ["ignition", "engine_management"], _applies(),
  purpose="Read the ECM's per-cylinder misfire counters to see which cylinder(s) are "
          "actually misfiring, rather than guessing from a generic P0300.",
  car_state="driving",
  when_to_use="P0300 or any per-cylinder misfire code, before swapping coils/plugs/"
              "injectors.",
  tools=["scan tool (Mode $06 or manufacturer-specific misfire data)"],
  procedure=[
      "Clear counters if the tool allows, or note current values.",
      "Drive through the condition that triggers the complaint (idle, load, cruise).",
      "Read counters again; compare per-cylinder counts.",
  ],
  pass_criteria=[_pc("misfire count", "0 or negligible, evenly low across cylinders",
                     "counts", TECHAUTHORITY, UNKNOWN)],
  fail_means="One cylinder dominating the count points at that cylinder's ignition/"
             "injector/mechanical path; counts spread evenly across all cylinders "
             "points at a common-cause fault (fuel pressure, vacuum leak).",
  related_codes=["P0300", "P0301", "P0302", "P0303", "P0304"],
  supports_hypotheses=["misfire, single cylinder", "misfire, all cylinders"],
  refutes_hypotheses=[],
  duration_min=15, hazards=[])

# ===========================================================================
# Cooling
# ===========================================================================

_t("cooling_system_pressure_test", "Cooling system pressure test", "cooling",
  ["cooling"], _applies(),
  purpose="Pressurize the cooling system cold to find external leaks (hoses, "
          "radiator, water pump, head gasket externally) without running the engine.",
  car_state="cold",
  when_to_use="Any coolant loss with no visible puddle, low-coolant warning, or "
              "before condemning a head gasket on overheating alone.",
  tools=["cooling system pressure tester with radiator-cap adapter"],
  procedure=[
      "Engine cold. Remove cap, fit the pressure tester.",
      "Pump to the cap's rated pressure (see cap markings / service manual).",
      "Hold for 2 minutes; watch the gauge and every hose/fitting/the water pump "
      "weep hole.",
      "A pressure drop with no visible external leak raises suspicion of an internal "
      "leak (head gasket, cracked head/block) -- follow with the block (combustion-"
      "gas) test.",
  ],
  pass_criteria=[_pc("pressure drop over 2 min", "<10%", "%", INDUSTRY_PRACTICE,
                     SINGLE_SOURCE)],
  fail_means="A visible external leak identifies the failed part directly; a drop "
             "with no visible leak is evidence for an internal leak.",
  related_codes=["P0217"],
  supports_hypotheses=["coolant loss", "head gasket"],
  refutes_hypotheses=["head gasket"],
  duration_min=20, safety="Cooling system may still be warm/pressurized from a prior "
                          "drive -- let it cool fully before opening.",
  hazards=["hot coolant"])

_t("radiator_cap_test", "Radiator cap pressure test", "cooling", ["cooling"], _applies(),
  purpose="Confirm the cap itself holds its rated pressure before condemning the "
          "system -- a weak cap causes coolant loss/boil-over that looks like a "
          "system leak.",
  car_state="cold",
  when_to_use="Coolant loss with no obvious system leak, or before reusing a cap "
              "after any other cooling work.",
  tools=["cooling system pressure tester with cap adapter"],
  procedure=[
      "Fit the cap alone to the tester's cap adapter.",
      "Pump until the cap releases; read the release pressure.",
      "Compare to the cap's own rated/stamped pressure.",
  ],
  pass_criteria=[_pc("release pressure vs. rated", "see service manual / cap marking",
                     "", TECHAUTHORITY, UNKNOWN)],
  fail_means="A cap that releases well below its rated pressure is the leak/boil-"
             "over cause by itself -- replace it before re-testing the system.",
  related_codes=["P0217"],
  supports_hypotheses=["coolant loss"], refutes_hypotheses=["coolant loss"],
  duration_min=5, hazards=["hot coolant"])

_t("coolant_block_test", "Coolant combustion-gas (block) test", "cooling",
  ["cooling", "engine_management"], _applies(),
  purpose="Chemically detect combustion gases (CO2) bubbling into the coolant -- the "
          "classic head-gasket/cracked-head check.",
  car_state="hot",
  when_to_use="Suspected internal coolant leak (white exhaust smoke, chronic "
              "overheating, coolant loss with no external leak, oil/coolant cross-"
              "contamination).",
  tools=["block tester (combustion-leak detection fluid + bulb)"],
  procedure=[
      "Engine warm, coolant level correct.",
      "Fit the tester over the radiator/expansion-tank neck, below the fill line, "
      "without touching coolant.",
      "Squeeze the bulb to draw vapor through the fluid; run the engine at idle/"
      "light load for the tool's specified time.",
      "Watch the fluid colour change (blue -> yellow typically indicates CO2 present).",
  ],
  pass_criteria=[_pc("fluid colour change", "no change (stays blue/green)", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="A positive colour change is strong evidence of combustion gas in the "
             "coolant -- head gasket or cracked head/block, not a hose/radiator leak.",
  related_codes=["P0217"],
  supports_hypotheses=["head gasket"], refutes_hypotheses=["head gasket"],
  duration_min=10, hazards=["hot coolant", "hot engine surfaces"])

# ===========================================================================
# Fuel
# ===========================================================================

_t("fuel_pressure_test", "Fuel pressure test (low side + high side)", "fuel",
  ["fuel"], _applies(),
  purpose="Confirm the low-pressure (tank-to-pump) and high-pressure (direct-"
          "injection rail) fuel systems are each within spec, read live rather than "
          "assumed from a code.",
  car_state="KOER",
  when_to_use="Hard start, stumble under load, lean trims with no leak found, or any "
              "fuel-pressure-related code.",
  tools=["scan tool (live fuel pressure PIDs, low and high side)",
        "mechanical fuel pressure gauge (low side, if the PID is suspect)"],
  procedure=[
      "Low side: read the scan-tool low-pressure PID at idle and under load; cross-"
      "check with a mechanical gauge at the test port if the PID reading is in "
      "doubt.",
      "High side: read the DI rail pressure PID at idle, under load, and watch its "
      "response during a quick throttle blip.",
      "Compare both to spec (see service manual -- this platform's DI rail target "
      "varies with load and is not a single fixed number).",
  ],
  pass_criteria=[_pc("low-side pressure", "see service manual", "", TECHAUTHORITY,
                     UNKNOWN),
                _pc("high-side (DI rail) pressure", "see service manual", "",
                    TECHAUTHORITY, UNKNOWN)],
  fail_means="Low side out of spec points at the in-tank pump/filter/regulator; "
             "high side out of spec (with a good low side) points at the high-"
             "pressure pump or rail components.",
  related_codes=["P0087", "P0088", "P0191", "P0192", "P0193", "P1093"],
  supports_hypotheses=["fuel delivery fault"], refutes_hypotheses=["fuel delivery fault"],
  duration_min=20, safety="Direct-injection rail pressure is very high -- never "
                          "loosen a high-pressure fitting with the system "
                          "pressurized or the engine running.",
  hazards=["fuel pressure", "fuel"])

_t("injector_balance_test", "Injector balance / contribution test", "fuel",
  ["fuel", "engine_management"], _applies(),
  purpose="Compare each injector's actual contribution to combustion (via fuel "
          "trim shift or a dedicated balance-test routine) to find a weak or "
          "clogged injector.",
  car_state="KOER",
  when_to_use="A misfire isolated to one cylinder after ignition components are "
              "already confirmed good.",
  tools=["scan tool with injector balance/contribution test support"],
  procedure=[
      "Run the scan tool's injector balance/contribution routine if the platform "
      "supports it (cuts each injector in turn, measures RPM drop or fuel-trim "
      "shift).",
      "If no dedicated routine exists, swap the suspect injector with a known-good "
      "one and see if the misfire follows the part.",
  ],
  pass_criteria=[_pc("contribution across cylinders", "even across all cylinders", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="One cylinder contributing noticeably less (or the misfire following "
             "the swapped part) identifies that injector.",
  related_codes=["P0301", "P0302", "P0303", "P0304", "P0263", "P0266"],
  supports_hypotheses=["misfire, single cylinder"], refutes_hypotheses=[],
  duration_min=20, hazards=["fuel pressure"])

# ===========================================================================
# Lubrication
# ===========================================================================

_t("oil_pressure_test", "Oil pressure test (PID + mechanical gauge)", "lubrication",
  ["lubrication"], _applies(),
  purpose="Confirm actual oil pressure rather than trusting a low-oil-pressure "
          "warning or a suspect sender/PID alone.",
  car_state="hot",
  when_to_use="Low oil pressure warning/code, knocking noise, or before any major "
              "engine work to establish a baseline.",
  tools=["scan tool (oil pressure PID, if supported)",
        "mechanical oil pressure gauge (adapts to the sender port)"],
  procedure=[
      "Warm engine to normal operating temperature.",
      "Read the scan-tool oil pressure PID at idle and at a steady 2500-3000 rpm, "
      "if the ECM reports one.",
      "Cross-check with a mechanical gauge at the sender port -- the PID can be "
      "wrong if the sender itself is marginal.",
  ],
  pass_criteria=[_pc("oil pressure, hot idle and 3000 rpm", "see service manual", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="Low pressure confirmed on the mechanical gauge (not just the PID) "
             "points at the pump, bearings, or oil pickup/level -- a genuine "
             "mechanical concern, stop driving the car until resolved.",
  related_codes=["P0520", "P0521", "P0522", "P0523"],
  supports_hypotheses=["low oil pressure"], refutes_hypotheses=["low oil pressure"],
  duration_min=15, safety="A confirmed low mechanical reading means the engine "
                          "should not be driven further until the cause is found.",
  hazards=["hot engine surfaces", "hot oil"])

_t("oil_uv_dye_leak", "Oil UV-dye leak test", "leak_detection",
  ["lubrication"], _applies(),
  purpose="Find the exact source of an external oil leak using UV dye and a UV "
          "light, instead of guessing from a general wet-underside appearance.",
  car_state="driving",
  when_to_use="Any oil leak where the source isn't obvious from a visual alone.",
  tools=["UV dye (oil-compatible)", "UV light", "shop light"],
  procedure=[
      "Add the manufacturer-specified amount of UV dye to the oil (or use pre-dyed "
      "oil).",
      "Drive the car normally for a day or more to circulate the dye and let the "
      "leak show.",
      "With the car on a lift, scan every seal/gasket/fitting with the UV light in "
      "a darkened area.",
      "Note the exact glowing point(s); clean and re-check after the repair to "
      "confirm the leak stopped.",
  ],
  pass_criteria=[_pc("UV glow at seal/gasket", "none found", "", TECHAUTHORITY, UNKNOWN)],
  fail_means="A glowing point identifies the exact leaking seal/gasket/fitting.",
  related_codes=[], supports_hypotheses=["oil leak"], refutes_hypotheses=["oil leak"],
  duration_min=30, hazards=["hot oil", "UV light exposure -- wear UV-blocking glasses"])

# ===========================================================================
# Cooling / A-C leak detection
# ===========================================================================

_t("coolant_uv_dye_leak", "Coolant UV-dye leak test", "leak_detection",
  ["cooling"], _applies(),
  purpose="Find the exact source of a coolant leak using UV dye, especially a slow "
          "leak with no visible puddle.",
  car_state="driving",
  when_to_use="Coolant loss with no leak found by the pressure test, or to confirm a "
              "repair stopped a known small leak.",
  tools=["UV dye (coolant-compatible)", "UV light"],
  procedure=[
      "Add UV dye to the coolant per the dye manufacturer's dosage.",
      "Drive/idle the car through a full warm-up and cool-down cycle to circulate "
      "the dye.",
      "Inspect every hose, clamp, radiator seam, heater core and water pump with "
      "the UV light.",
      "Note the exact glowing point(s).",
  ],
  pass_criteria=[_pc("UV glow at hose/seam/pump", "none found", "", TECHAUTHORITY,
                     UNKNOWN)],
  fail_means="A glowing point identifies the exact leaking component.",
  related_codes=["P0217"], supports_hypotheses=["coolant loss"],
  refutes_hypotheses=["coolant loss"], duration_min=30,
  hazards=["hot coolant", "UV light exposure -- wear UV-blocking glasses"])

_t("ac_uv_dye_leak_and_pressures", "A/C UV-dye leak test and system pressures",
  "leak_detection", ["hvac"], _applies(),
  purpose="Find a refrigerant leak with UV dye and confirm the A/C system's high/"
          "low-side pressures are within spec for ambient conditions.",
  car_state="driving",
  when_to_use="Weak or no A/C cooling, or a low-refrigerant warning.",
  tools=["UV dye (A/C-compatible, pre-charged in refrigerant or injected)", "UV light",
        "manifold gauge set"],
  procedure=[
      "Connect the manifold gauge set to the high- and low-side service ports.",
      "Run the A/C on max cold, record high- and low-side pressures against the "
      "pressure/temperature chart for the ambient temperature.",
      "If dye is already in the system (or inject it), run the system, then scan "
      "every fitting/condenser/evaporator-drain area with the UV light.",
  ],
  pass_criteria=[
      _pc("high/low side pressure vs. P/T chart", "see service manual / refrigerant "
          "P-T chart", "", TECHAUTHORITY, UNKNOWN),
      _pc("UV glow at fitting/component", "none found", "", TECHAUTHORITY, UNKNOWN),
  ],
  fail_means="Pressures outside the P/T-chart band point at charge level or a "
             "component (compressor, expansion valve); a UV glow identifies the "
             "exact leak point.",
  related_codes=[], supports_hypotheses=["A/C leak", "A/C charge fault"],
  refutes_hypotheses=["A/C leak", "A/C charge fault"], duration_min=30,
  safety="R-1234yf (or R-134a on older stock) requires certified recovery/charging "
         "equipment -- never vent refrigerant to atmosphere.",
  hazards=["refrigerant", "high pressure", "UV light exposure"])

# ===========================================================================
# Mechanical engine
# ===========================================================================

_t("compression_test", "Compression test", "mechanical_engine",
  ["engine_management"], _applies(),
  purpose="Measure each cylinder's cranking compression to find a mechanical "
          "problem (valve, ring, head gasket) a scan tool can't see directly.",
  car_state="KOEO",
  when_to_use="Low power, rough idle with no electrical cause found, or before any "
              "major engine work to establish a baseline.",
  tools=["compression tester (threaded gauge, per spark-plug-hole thread)",
        "disable fuel/ignition per service manual procedure"],
  procedure=[
      "Warm engine, then disable fuel delivery and ignition per the service "
      "manual's cranking-compression procedure.",
      "Remove all spark plugs; fit the gauge to cylinder 1.",
      "Crank through 4-5 compression strokes (throttle held open); record the "
      "highest steady reading.",
      "Repeat for every cylinder.",
  ],
  pass_criteria=[
      _pc("absolute compression", "see service manual", "psi", TECHAUTHORITY, UNKNOWN),
      _pc("cylinder-to-cylinder variation", 10, "%", INDUSTRY_PRACTICE, SINGLE_SOURCE),
  ],
  fail_means="Any cylinder reading more than ~10% below the others points at that "
             "cylinder's valves/rings/head gasket; low on all cylinders points at a "
             "timing or common mechanical fault.",
  related_codes=["P0300", "P0301", "P0302", "P0303", "P0304"],
  supports_hypotheses=["misfire, single cylinder", "low compression"],
  refutes_hypotheses=["low compression"], duration_min=30,
  safety="Fuel and ignition must be disabled per the service manual before "
         "cranking with plugs out.",
  hazards=["moving car -- do not crank with transmission in gear"])

_t("relative_compression_test", "Relative compression test (starter current / scan "
  "tool)", "mechanical_engine", ["engine_management", "starting_charging"], _applies(),
  purpose="A quicker, no-plugs-out alternative to a full compression test: compares "
          "the starter's current/RPM signature cylinder-to-cylinder while cranking "
          "on a healthy, fueled engine.",
  car_state="KOEO",
  when_to_use="Quick screen for an obvious low-compression cylinder before committing "
              "to a full compression/leak-down test.",
  tools=["scan tool with relative-compression routine, or a current clamp + scope on "
        "the starter feed"],
  procedure=[
      "Disable fuel/ignition only if the chosen tool's routine requires it; many "
      "scan-tool routines crank the engine as-is.",
      "Run the routine (or crank while logging starter current); it reports a "
      "relative value per cylinder based on the load dip as each piston compresses.",
      "Compare the per-cylinder values.",
  ],
  pass_criteria=[_pc("cylinder-to-cylinder variation", 10, "%", INDUSTRY_PRACTICE,
                     SINGLE_SOURCE)],
  fail_means="A cylinder standing out from the rest is a candidate for a full "
             "compression or leak-down test to confirm.",
  related_codes=["P0300", "P0301", "P0302", "P0303", "P0304"],
  supports_hypotheses=["misfire, single cylinder", "low compression"],
  refutes_hypotheses=["low compression"], duration_min=10, hazards=[])

_t("cylinder_leak_down_test", "Cylinder leak-down test", "mechanical_engine",
  ["engine_management"], _applies(),
  purpose="Pressurize each cylinder at TDC with shop air to find and identify "
          "exactly where a low-compression cylinder is leaking (rings, intake "
          "valve, exhaust valve, head gasket).",
  car_state="KOEO",
  when_to_use="After a compression or relative-compression test flags a weak "
              "cylinder -- to tell rings from valves from head gasket.",
  tools=["leak-down tester", "shop air supply", "way to hold the crank at TDC "
        "(socket on the crank bolt)"],
  procedure=[
      "Remove the spark plug for the cylinder under test; bring that cylinder to "
      "TDC on the compression stroke.",
      "Fit the leak-down tester, apply shop air, and read the leakage percentage.",
      "Listen at the throttle body (intake valve leak), the exhaust pipe (exhaust "
      "valve leak), the oil fill (ring leak) and the radiator neck (head gasket "
      "leak) for escaping air.",
  ],
  pass_criteria=[
      _pc("leak-down percentage", 10, "%", INDUSTRY_PRACTICE, SINGLE_SOURCE),
      _pc("leak-down percentage, borderline", [10, 20], "%", INDUSTRY_PRACTICE,
          SINGLE_SOURCE),
  ],
  fail_means="Over ~20% leakage is a real concern; where the air is heard escaping "
             "from identifies rings vs. intake valve vs. exhaust valve vs. head "
             "gasket directly.",
  related_codes=["P0300", "P0301", "P0302", "P0303", "P0304"],
  supports_hypotheses=["low compression", "head gasket"],
  refutes_hypotheses=["head gasket"], duration_min=30,
  hazards=["shop air pressure -- cylinder can rotate off TDC under pressure"])

_t("intake_vacuum_gauge_test", "Intake vacuum gauge test", "mechanical_engine",
  ["air_intake_boost", "engine_management"], _applies(),
  purpose="A quick, broad mechanical-health check at idle using a vacuum gauge on a "
          "manifold port -- steady vacuum vs. fluctuating/low vacuum points toward "
          "different fault families before any teardown.",
  car_state="hot",
  when_to_use="Rough idle or low power with no code pointing anywhere specific.",
  tools=["vacuum gauge", "manifold vacuum port/adapter"],
  procedure=[
      "Warm engine, connect vacuum gauge to a manifold vacuum port.",
      "Read steady idle vacuum; note any needle flutter, slow drift, or rhythmic "
      "drop.",
      "Briefly snap the throttle open/closed and watch the gauge's response.",
  ],
  pass_criteria=[_pc("steady idle vacuum", [17, 21], "inHg", INDUSTRY_PRACTICE,
                     SINGLE_SOURCE)],
  fail_means="Low and steady = worn rings/late timing; needle fluttering rapidly = "
             "worn valve guides or weak spring; a periodic drop = a leaking valve "
             "on one cylinder; slowly drifting down = restricted exhaust.",
  related_codes=[], supports_hypotheses=["low compression", "exhaust restriction"],
  refutes_hypotheses=[], duration_min=10, hazards=[])

_t("crankcase_vacuum_pcv_test", "Crankcase vacuum / PCV system test", "mechanical_engine",
  ["pcv"], _applies(),
  purpose="Confirm the PCV/crankcase ventilation system is holding its designed "
          "slight vacuum and not venting oil mist or pressurizing the crankcase.",
  car_state="hot",
  when_to_use="Oil consumption with no external leak found, oil in the intake "
              "piping, or a whistling/hissing noise from the valve cover area.",
  tools=["manometer or vacuum gauge on the oil fill cap/dipstick tube",
        "smoke machine (to find a leaking PCV hose)"],
  procedure=[
      "Warm engine at idle; connect the gauge in place of the oil fill cap "
      "(temporarily) or at a dedicated test point.",
      "Read the crankcase pressure/vacuum.",
      "If pressurized rather than under slight vacuum, smoke-test the PCV hoses/"
      "valve for a stuck-open or disconnected path.",
  ],
  pass_criteria=[_pc("crankcase pressure", "slight vacuum, not positive pressure",
                     "inH2O", INDUSTRY_PRACTICE, SINGLE_SOURCE)],
  fail_means="A pressurized (not vacuum) crankcase points at a stuck/plugged PCV "
             "valve or excessive blow-by (ring wear) -- correlate with the "
             "compression/leak-down results.",
  related_codes=["P0520"], supports_hypotheses=["low compression", "PCV fault"],
  refutes_hypotheses=["PCV fault"], duration_min=15, hazards=["hot engine surfaces"])

_t("borescope_cylinder_inspection", "Borescope cylinder inspection", "inspection",
  ["engine_management"], _applies(),
  purpose="Directly see a cylinder's bore, valves and piston crown through the "
          "spark plug hole, without removing the head -- confirms (or rules out) "
          "what a compression/leak-down number only implies.",
  car_state="KOEO",
  when_to_use="A low-compression or high leak-down cylinder, to see the actual "
              "damage (scored bore, burnt valve, carbon buildup) before committing "
              "to teardown.",
  tools=["borescope (camera + light, sized for the spark plug hole)"],
  procedure=[
      "Remove the spark plug for the cylinder of interest.",
      "Insert the borescope; rotate the crank by hand to view the bore wall through "
      "a full stroke, and view the piston crown and visible valve faces at TDC.",
      "Photograph/video anything notable for the job file.",
  ],
  pass_criteria=[_pc("visible bore/valve/piston damage", "none found", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="Visible scoring, a burnt valve, or a cracked piston directly confirms "
             "the mechanical fault the other tests only inferred.",
  related_codes=["P0300", "P0301", "P0302", "P0303", "P0304"],
  supports_hypotheses=["low compression"], refutes_hypotheses=["low compression"],
  duration_min=20, hazards=[])

# ===========================================================================
# Ignition
# ===========================================================================

_t("coil_plug_swap_test", "Ignition: coil/plug swap test", "ignition",
  ["ignition"], _applies(),
  purpose="Move a suspect coil (and/or plug) to a different cylinder and see if the "
          "misfire follows the part -- the cheapest way to confirm an ignition "
          "component before buying a new one.",
  car_state="KOEO",
  when_to_use="A single-cylinder misfire, after the injector balance test has not "
              "already pointed at fuel delivery.",
  tools=["basic hand tools"],
  procedure=[
      "Note which cylinder is misfiring (from misfire counters or a rough-idle "
      "cylinder-drop test).",
      "Swap that cylinder's coil (and/or plug) with a known-good cylinder's.",
      "Clear misfire counters if possible; run the engine through the same "
      "condition and re-check which cylinder now misfires.",
  ],
  pass_criteria=[_pc("misfire location after swap", "follows the swapped part, or "
                     "does not", "", TECHAUTHORITY, UNKNOWN)],
  fail_means="If the misfire moves to the new cylinder with the swapped part, that "
             "part is confirmed faulty; if it stays on the original cylinder, the "
             "coil/plug is cleared and the fault is elsewhere (injector, "
             "mechanical).",
  related_codes=["P0300", "P0301", "P0302", "P0303", "P0304", "P0351", "P0352"],
  supports_hypotheses=["misfire, single cylinder"], refutes_hypotheses=[],
  duration_min=15, hazards=[])

_t("cam_crank_correlation_test", "Cam/crank correlation check (scan tool)", "ignition",
  ["ignition", "valve_control"], _applies(),
  purpose="Read the ECM's live cam and crank position signals together to confirm "
          "they stay correlated -- this engine has no distributor and no "
          "field-adjustable timing, so this is a sensor/chain-stretch check, not a "
          "timing adjustment.",
  car_state="KOER",
  when_to_use="A cam/crank correlation code, or a no-start/hard-start with good fuel "
              "and spark otherwise confirmed.",
  tools=["scan tool (live cam/crank position PIDs, or correlation DTC detail)"],
  procedure=[
      "Note: this engine has no distributor; ignition timing is computer-controlled "
      "and not mechanically adjustable -- this test checks sensor correlation, it "
      "does not set timing.",
      "Read live cam and crank position PIDs (or the correlation fault's freeze "
      "frame/detail) while cranking or running.",
      "Confirm the reported phase relationship is within the ECM's expected window.",
  ],
  pass_criteria=[_pc("cam/crank correlation", "within ECM's expected window", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="A confirmed correlation fault points at a stretched timing chain, a "
             "slipped phaser, or a failing cam/crank sensor -- not a timing "
             "adjustment, since none is possible on this engine.",
  related_codes=["P0016", "P0017", "P0018", "P0019"],
  supports_hypotheses=["cam/crank correlation fault"],
  refutes_hypotheses=["cam/crank correlation fault"], duration_min=15, hazards=[])

_t("spark_plug_read", "Spark plug read", "ignition", ["ignition"], _applies(),
  purpose="Read the deposits/condition on a removed spark plug for evidence of "
          "running condition -- rich, lean, oil fouling, pre-ignition.",
  car_state="KOEO",
  when_to_use="Any misfire investigation, or routine health check during other "
              "ignition work.",
  tools=["socket set", "good light", "reference chart for deposit colour/condition"],
  procedure=[
      "Remove the plug(s) of interest; keep track of which cylinder each came from.",
      "Inspect electrode gap, deposit colour, and any oil/fuel fouling or mechanical "
      "damage.",
      "Compare findings across cylinders.",
  ],
  pass_criteria=[_pc("deposit condition", "tan/grey, no fouling or damage", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="Oil fouling points at rings/valve seals on that cylinder; black sooty "
             "fouling points at rich/weak-spark; a damaged electrode confirms a "
             "mechanical ignition fault.",
  related_codes=["P0300", "P0301", "P0302", "P0303", "P0304"],
  supports_hypotheses=["misfire, single cylinder", "low compression"],
  refutes_hypotheses=[], duration_min=15, hazards=[])

# ===========================================================================
# Electrical
# ===========================================================================

_t("battery_load_conductance_test", "Battery load/conductance test", "electrical",
  ["starting_charging"], _applies(),
  purpose="Confirm the battery itself can deliver cranking current (load test) or "
          "estimate its health non-invasively (conductance tester) -- separate from "
          "a simple resting-voltage check.",
  car_state="key-off",
  when_to_use="Slow crank, a battery warning, or before condemning the charging "
              "system -- a weak battery can masquerade as an alternator problem.",
  tools=["battery load tester or conductance/CCA tester"],
  procedure=[
      "Let the battery rest (no charge/load) for at least 30 minutes if recently "
      "driven.",
      "Run the tester per its instructions; it reports a pass/fail or a CCA/SOH "
      "figure against the battery's rating.",
  ],
  pass_criteria=[_pc("tester result", "see tester/battery rating", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="A failed load/conductance test condemns the battery itself, "
             "regardless of what the charging system reads.",
  related_codes=["P0560", "P0620", "P0621", "P0622"],
  supports_hypotheses=["weak battery"], refutes_hypotheses=["weak battery"],
  duration_min=10, safety="Battery acid and hydrogen gas -- no open flame/sparks "
                          "near the battery.",
  hazards=["battery acid", "hydrogen gas"])

_t("charging_voltage_ripple_test", "Charging voltage and ripple test", "electrical",
  ["starting_charging", "electrical_supply"], _applies(),
  purpose="Confirm the alternator is actually charging within spec and that its "
          "AC ripple is low -- a failing diode can charge at a plausible voltage "
          "while still damaging the battery/electronics with ripple.",
  car_state="hot",
  when_to_use="A battery or charging warning, intermittent electrical gremlins, or "
              "before condemning the battery for repeated failure.",
  tools=["multimeter (DC volts and AC ripple)", "or scan tool live battery voltage "
        "PID"],
  procedure=[
      "Engine running, no major accessory load, measure DC voltage at the battery "
      "terminals.",
      "Switch the meter to AC volts (same leads) to read ripple.",
      "Repeat with headlights/blower/rear defrost on to check under load.",
  ],
  pass_criteria=[
      _pc("charging voltage", [13.5, 14.7], "V",
         "https://www.firestonecompleteautocare.com/blog/batteries/"
         "car-battery-voltage/", CORROBORATED),
      _pc("AC ripple", "low, no significant AC component", "V", INDUSTRY_PRACTICE,
          SINGLE_SOURCE),
  ],
  fail_means="Voltage outside the 13.5-14.7 V band points at the regulator/"
             "alternator/belt/connections; high AC ripple with in-range DC voltage "
             "still points at a failing alternator diode.",
  related_codes=["P0560", "P0620", "P0621", "P0622", "P0625", "P0626"],
  supports_hypotheses=["charging system fault"],
  refutes_hypotheses=["charging system fault"], duration_min=10, hazards=[])

_t("parasitic_draw_test", "Parasitic draw test", "electrical",
  ["electrical_supply"], _applies(),
  purpose="Measure the current the car still draws once every module is asleep, to "
          "find a module staying awake and draining the battery overnight.",
  car_state="key-off",
  when_to_use="A battery that goes dead overnight/over a few days with no other "
              "cause found.",
  tools=["multimeter with mA current clamp or in-line fused amp meter",
        "patience -- modules take time to go to sleep"],
  procedure=[
      "Close all doors, remove the key/fob from range, let the car sit undisturbed "
      "long enough for every module to reach sleep (often 20-40 minutes).",
      "Break the negative battery cable and insert the meter in series (or use a "
      "non-invasive current clamp).",
      "Read the steady-state draw once it settles.",
      "If high, pull fuses one at a time (per the fuse chart) to isolate which "
      "circuit is drawing.",
  ],
  pass_criteria=[_pc("parasitic draw, modules asleep", 50, "mA", INDUSTRY_PRACTICE,
                     SINGLE_SOURCE)],
  fail_means="A draw above ~50 mA after sleep points at a module failing to sleep; "
             "pulling fuses isolates which circuit.",
  related_codes=[], supports_hypotheses=["parasitic draw"],
  refutes_hypotheses=["parasitic draw"], duration_min=60,
  safety="Breaking the battery cable can cause a spark -- keep away from fuel/"
         "battery gas.",
  hazards=["battery acid", "hydrogen gas"])

_t("voltage_drop_grounds_feeds_test", "Voltage-drop test on grounds and feeds",
  "electrical", ["electrical_supply"], _applies(),
  purpose="Find a high-resistance connection (corroded ground, loose feed) that a "
          "simple continuity check misses, by measuring voltage drop under load.",
  car_state="KOER",
  when_to_use="An intermittent electrical fault, dim lights, slow accessories, or "
              "any circuit suspected of a bad connection rather than a dead "
              "component.",
  tools=["multimeter (DC volts)"],
  procedure=[
      "With the circuit under its normal working load (e.g. headlights on, starter "
      "cranking), measure voltage drop across each connection in the circuit "
      "(battery negative to chassis, chassis to engine block, connector to "
      "connector) rather than at rest.",
      "Work from the source toward the load, noting where the drop jumps.",
  ],
  pass_criteria=[_pc("voltage drop per connection", "near 0 V (a few hundred mV at "
                     "most under load)", "V", INDUSTRY_PRACTICE, SINGLE_SOURCE)],
  fail_means="A connection showing a larger-than-expected drop under load is the "
             "high-resistance point -- clean/repair that connection specifically.",
  related_codes=[], supports_hypotheses=["ground/feed fault"],
  refutes_hypotheses=["ground/feed fault"], duration_min=20, hazards=[])

# ===========================================================================
# Network
# ===========================================================================

_t("can_bus_resistance_test", "CAN bus resistance test", "network", ["network"],
  _applies(),
  purpose="Confirm the CAN bus's termination resistors are intact and the bus wiring "
          "has no short/open, by measuring resistance between CAN-H and CAN-L with "
          "the key off.",
  car_state="key-off",
  when_to_use="A U-code (network communication fault), a module that won't "
              "communicate, or before condemning a specific module for a network "
              "issue.",
  tools=["multimeter (resistance)", "access to the bus at the OBD connector or a "
        "module connector"],
  procedure=[
      "Key off, all modules asleep (let the car sit a few minutes).",
      "Measure resistance between CAN-H and CAN-L at the OBD connector (pins 6 and "
      "14 on the standard bus).",
      "If out of spec, isolate by disconnecting modules/segments one at a time and "
      "re-measuring.",
  ],
  pass_criteria=[_pc("CAN-H to CAN-L resistance, key off", 60, "ohm",
                     INDUSTRY_PRACTICE, SINGLE_SOURCE)],
  fail_means="A reading far above 60 ohm suggests an open/missing termination "
             "resistor or module; far below suggests a short in the bus wiring.",
  related_codes=["U0100", "U0101", "U0121", "U0140", "U0155"],
  supports_hypotheses=["network fault"], refutes_hypotheses=["network fault"],
  duration_min=15, hazards=[])

# ===========================================================================
# Intake / boost mechanical
# ===========================================================================

_t("turbo_wastegate_actuator_check", "Turbo wastegate/actuator check", "intake_boost",
  ["air_intake_boost"], _applies(),
  purpose="Confirm the wastegate actuator moves freely and holds the commanded "
          "position, rather than assuming a boost code is the turbo itself.",
  car_state="KOEO",
  when_to_use="Underboost/overboost codes, or sluggish boost response.",
  tools=["hand-operated vacuum/pressure pump (for a vacuum/pneumatic actuator) or "
        "scan tool bidirectional control (for an electronic actuator)",
        "visual access to the wastegate linkage"],
  procedure=[
      "With the engine off, apply vacuum/pressure (or command the electronic "
      "actuator via the scan tool) and watch the wastegate arm move smoothly through "
      "its full travel.",
      "Check for binding, a seized rod end, or excessive play in the linkage.",
      "Check the actuator holds position without leaking down (vacuum/pneumatic "
      "type).",
  ],
  pass_criteria=[_pc("full smooth travel, holds position", "yes", "", TECHAUTHORITY,
                     UNKNOWN)],
  fail_means="Binding, excess play, or a leaking actuator identifies the wastegate "
             "assembly as the fault, independent of any boost-pressure number.",
  related_codes=["P0243", "P0245", "P0299", "P0234"],
  supports_hypotheses=["boost leak", "turbo fault"],
  refutes_hypotheses=["turbo fault"], duration_min=20, hazards=[])

_t("boost_leak_test", "Boost leak test (pressurized)", "intake_boost",
  ["air_intake_boost"], _applies(),
  purpose="Pressurize the charge-air piping (post-turbo, through the intercooler) "
          "with shop air/a dedicated boost-leak tester to find a leak that only "
          "shows up under positive pressure, not under the lighter smoke-machine "
          "pressure used on the intake test.",
  car_state="key-off",
  when_to_use="Underboost code or sluggish power with the intake smoke test clean, "
              "or after any charge-pipe/intercooler work.",
  tools=["boost leak tester (regulated shop air + gauge, blanks off the charge "
        "piping)"],
  procedure=[
      "Disconnect the charge piping at the turbo outlet and at the throttle body; "
      "fit the blanking plates.",
      "Pressurize to a moderate test pressure (well below peak boost -- per tool "
      "instructions) and watch the gauge for a sustained drop.",
      "Listen/feel along every clamp, the intercooler, and any sensor boss for "
      "escaping air.",
  ],
  pass_criteria=[_pc("pressure held, no audible leak", "yes", "", TECHAUTHORITY,
                     UNKNOWN)],
  fail_means="A sustained pressure drop or an audible leak identifies the exact "
             "failed joint/intercooler seam under real boost pressure.",
  related_codes=["P0234", "P0299"], supports_hypotheses=["boost leak"],
  refutes_hypotheses=["boost leak"], duration_min=20,
  safety="Do not exceed the charge piping's rated pressure -- plastic end tanks on "
         "the intercooler can split.",
  hazards=["pressurized air"])

# ===========================================================================
# Exhaust
# ===========================================================================

_t("exhaust_back_pressure_test", "Exhaust back-pressure test", "exhaust",
  ["exhaust_emissions"], _applies(),
  purpose="Measure exhaust back-pressure to confirm (or rule out) a restricted "
          "catalytic converter or exhaust as the cause of a power loss.",
  car_state="hot",
  when_to_use="Power loss with a slowly drifting-down vacuum reading, or a "
              "suspected plugged catalytic converter.",
  tools=["exhaust back-pressure gauge (threads into an O2 sensor boss or a drilled "
        "test point)"],
  procedure=[
      "Warm engine; fit the back-pressure gauge ahead of the suspect restriction "
      "(e.g. in the pre-cat O2 boss).",
      "Read back-pressure at idle and at a steady higher RPM/load.",
  ],
  pass_criteria=[
      _pc("back-pressure at idle", 1.5, "psi", INDUSTRY_PRACTICE, SINGLE_SOURCE),
      _pc("back-pressure at ~2500 rpm", 3.0, "psi", INDUSTRY_PRACTICE, SINGLE_SOURCE),
  ],
  fail_means="Back-pressure rising well above these generic figures, especially "
             "under load, points at a restricted catalytic converter or muffler.",
  related_codes=["P0420", "P0430"], supports_hypotheses=["exhaust restriction"],
  refutes_hypotheses=["exhaust restriction"], duration_min=15,
  hazards=["hot exhaust components"])

# ===========================================================================
# Brakes
# ===========================================================================

_t("brake_fluid_moisture_boiling_point", "Brake fluid moisture/boiling point test",
  "brakes", ["brakes_abs"], _applies(),
  purpose="Check brake fluid condition directly -- moisture content and/or boiling "
          "point -- rather than guessing fluid age from a service interval alone.",
  car_state="key-off",
  when_to_use="Soft/long brake pedal with no obvious leak or air in the lines, or "
              "routine health check before brake service.",
  tools=["brake fluid moisture tester (electronic probe) or a boiling-point tester"],
  procedure=[
      "Sample fluid from the reservoir (moisture tester) or a bleeder (boiling-"
      "point tester), per the tester's own instructions.",
      "Read the moisture percentage or wet boiling point reported.",
  ],
  pass_criteria=[
      _pc("moisture content", 3, "%", INDUSTRY_PRACTICE, SINGLE_SOURCE),
      _pc("wet boiling point, DOT 4", 155, "C", "DOT/FMVSS 116 minimum wet boiling "
          "point standard for DOT 4 fluid", CORROBORATED),
  ],
  fail_means="Moisture above ~3% or a wet boiling point below the DOT 4 minimum "
             "means the fluid itself is the cause of a soft/fading pedal -- flush "
             "and replace before condemning any brake hardware.",
  related_codes=[], supports_hypotheses=["brake fluid condition"],
  refutes_hypotheses=["brake fluid condition"], duration_min=10,
  hazards=["brake fluid is caustic -- avoid skin/eye/paint contact"])

_t("brake_hydraulic_pressure_bleed", "Brake hydraulic pressure test / bleed", "brakes",
  ["brakes_abs"], _applies(),
  purpose="Measure actual line pressure at each wheel and bleed the system properly "
          "to confirm the hydraulic circuit (not just the fluid) is delivering "
          "even, full pressure.",
  car_state="key-off",
  when_to_use="Uneven braking, a pedal that sinks slowly, or after any brake "
              "component replacement.",
  tools=["brake pressure gauge set (adapts to bleeder screws)", "bleeder/vacuum "
        "bleeder or a second person to pump the pedal"],
  procedure=[
      "Fit pressure gauges at each wheel's bleeder (or one at a time).",
      "Have an assistant apply steady pedal pressure; read each wheel's line "
      "pressure and compare side to side.",
      "Bleed each wheel in the sequence the service manual specifies until the "
      "fluid is clear of air and pressure is even.",
  ],
  pass_criteria=[_pc("line pressure, side to side", "even, see service manual for "
                     "absolute spec", "", TECHAUTHORITY, UNKNOWN)],
  fail_means="A wheel reading noticeably lower pressure than its opposite number "
             "points at that circuit (caliper, hose, or a restriction) rather than "
             "the master cylinder.",
  related_codes=[], supports_hypotheses=["brake hydraulic fault"],
  refutes_hypotheses=["brake hydraulic fault"], duration_min=30,
  hazards=["brake fluid is caustic"])

# ===========================================================================
# Driveline / inspection / listening
# ===========================================================================

_t("transfer_case_diff_oil_inspection", "Transfer-case and differential oil level/"
  "condition inspection", "driveline", ["transmission_driveline"], _applies(),
  purpose="Check the AWD transfer-case and differential oil level and condition -- "
          "low or contaminated fluid is a common, overlooked cause of driveline "
          "noise/wear on a Q4 (AWD) car.",
  car_state="cold",
  when_to_use="Driveline noise, vibration, or as part of any driveline complaint "
              "workup before suspecting a bearing/gear fault.",
  tools=["fill-plug tools", "drain pan", "fresh fluid of the correct spec on hand"],
  procedure=[
      "With the car level, remove the fill plug on the transfer case (and rear "
      "differential); confirm fluid is at the plug's lower edge.",
      "Inspect the fluid drawn for colour/smell/metal particles.",
      "Top up or replace per the service manual if low or contaminated.",
  ],
  pass_criteria=[_pc("fluid level and condition", "at fill level, clean", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="Low fluid points at a leak to find; metal particles or a burnt smell "
             "point at internal wear needing further teardown/inspection.",
  related_codes=[], supports_hypotheses=["driveline fault"],
  refutes_hypotheses=["driveline fault"], duration_min=20, hazards=["used gear oil"])

_t("driveline_play_check", "Driveline play check", "driveline",
  ["transmission_driveline"], _applies(),
  purpose="Physically check for play/clunk in the driveshaft, CV joints and "
          "differential mounts -- a direct mechanical check, not a code-driven one.",
  car_state="key-off",
  when_to_use="A clunk on acceleration/deceleration or gear changes, or driveline "
              "vibration.",
  tools=["pry bar", "lift/jack and stands"],
  procedure=[
      "With the car safely supported, grip and attempt to rock each driveshaft/CV "
      "joint and the differential mount by hand/pry bar.",
      "Have an assistant rock the car forward/back in gear (parking brake off, "
      "wheels chocked) while you listen/feel at suspect joints for a clunk.",
  ],
  pass_criteria=[_pc("detectable play/clunk", "none", "", TECHAUTHORITY, UNKNOWN)],
  fail_means="Detectable play at a specific joint/mount identifies that component "
             "as the source of the clunk/vibration.",
  related_codes=[], supports_hypotheses=["driveline fault"],
  refutes_hypotheses=["driveline fault"], duration_min=20,
  safety="Car must be properly supported on stands, never on a jack alone, while "
         "anyone is under or near it.",
  hazards=["car on stands -- crush hazard if not properly supported"])

_t("wheel_bearing_play_check", "Wheel bearing play check", "driveline",
  ["suspension"], _applies(),
  purpose="Physically check for axial/radial play in each wheel bearing -- a "
          "growling noise that changes with cornering load is often blamed on tires "
          "when it's actually a bearing.",
  car_state="key-off",
  when_to_use="A speed-dependent growl/hum that changes when weaving/cornering, or "
              "routine suspension inspection.",
  tools=["lift/jack and stands", "pry bar or dial indicator"],
  procedure=[
      "Raise the wheel off the ground; grip at 12 and 6 o'clock and rock in/out, "
      "feeling/listening for play or a grinding feel while spinning the wheel by "
      "hand.",
      "For a precise check, mount a dial indicator on the hub and measure axial "
      "play while pushing/pulling the wheel.",
  ],
  pass_criteria=[_pc("detectable play", "none", "", TECHAUTHORITY, UNKNOWN)],
  fail_means="Detectable play or roughness while spinning identifies that corner's "
             "bearing as the noise source.",
  related_codes=[], supports_hypotheses=["wheel bearing fault"],
  refutes_hypotheses=["wheel bearing fault"], duration_min=15,
  safety="Car must be properly supported on stands while a wheel is off the ground "
         "and being handled.",
  hazards=["car on stands -- crush hazard if not properly supported"])

_t("listening_test_chassis_ears", "Listening test (chassis ears / stethoscope)",
  "inspection", ["suspension", "transmission_driveline", "engine_management"],
  _applies(),
  purpose="Pinpoint the exact source of a noise by listening at individual "
          "suspected points (bearing, strut mount, driveline joint) with a "
          "mechanic's stethoscope, or by clipping chassis-ear microphones at several "
          "points and driving the car to record which one picks up the noise.",
  car_state="driving",
  when_to_use="Any noise complaint where a visual/physical check hasn't already "
              "pinned the exact source.",
  tools=["mechanic's stethoscope (stationary noises)", "chassis ears (clip-on mics "
        "+ switch box, for noises only present while driving)",
        "phone/recorder for an audio clip"],
  procedure=[
      "For a stationary/idle noise: use the stethoscope at each suspected "
      "component in turn.",
      "For a driving noise: clip a chassis-ear microphone at each suspected point "
      "(bearings, exhaust hangers, driveline), then drive the car through the "
      "condition that produces the noise, switching between channels to find which "
      "one is loudest.",
      "Record a short audio clip of the isolated noise for the job file.",
  ],
  pass_criteria=[_pc("isolated noise source", "see audio clip / job note", "",
                     TECHAUTHORITY, UNKNOWN)],
  fail_means="The channel/location picking up the noise identifies the exact "
             "component -- attach the audio clip as evidence rather than relying on "
             "a written description alone.",
  related_codes=[], supports_hypotheses=["unexplained noise"],
  refutes_hypotheses=["unexplained noise"], duration_min=30, hazards=[])


def all_tests() -> list[dict[str, Any]]:
    """Every test in catalogue order."""
    return [dict(TESTS[i]) for i in _ORDER]


def test(id_: str) -> Optional[dict[str, Any]]:
    """One test by id, or ``None`` if unknown."""
    t = TESTS.get(id_)
    return dict(t) if t is not None else None


def _base_code(code: str) -> str:
    code = (code or "").strip().upper()
    return code[:5] if len(code) >= 5 else code


def tests_for_codes(codes: list[str]) -> list[dict[str, Any]]:
    """Tests whose ``related_codes`` match any of ``codes`` -- a related_codes
    entry matches if it is a prefix of (or equal to) the base code (e.g. a
    related_codes entry ``"P04"`` matches a given code ``"P0455-00"``;
    ``"P0300"`` matches only ``"P0300"``/``"P03000x"``)."""
    bases = [_base_code(c) for c in codes if c]
    out: list[dict[str, Any]] = []
    for i in _ORDER:
        t = TESTS[i]
        for rel in t["related_codes"]:
            rel_u = rel.strip().upper()
            if any(b.startswith(rel_u) for b in bases):
                out.append(dict(t))
                break
    return out


def tests_for_systems(ids: list[str]) -> list[dict[str, Any]]:
    """Tests touching any of the given :mod:`mes.systems` system ids."""
    want = {s.strip().lower() for s in ids if s}
    return [dict(TESTS[i]) for i in _ORDER if want & set(TESTS[i]["systems"])]


__all__ = ["TESTS", "CATEGORIES", "CAR_STATES", "RESULTS", "POSTABLE_RESULTS",
          "TECHAUTHORITY", "INDUSTRY_PRACTICE", "all_tests", "test",
          "tests_for_codes", "tests_for_systems"]
