"""Checks for the sibling-platform bus-topology research
(``mes.platform.BUS_TOPOLOGY`` / ``cuore.live.buses.SIBLING_PLATFORM_BUSES``,
added 2026-10-14; see
``docs/research/SIBLING_PLATFORMS_BUS_TOPOLOGY_2026-10-14.md`` for the full
sourced writeup this test backs).

Plain script style, like ``check_live.py``/``mes-log-mcp/tests/
check_platform.py``: no test framework, exit 1 on failure.

Three things this file checks:
  1. ``mes.platform.bus_topology_for(model)`` returns a dict with a
     ``confidence`` on every fact, for each of Grecale, Levante and
     Purosangue -- and ``None`` for anything else.
  2. A Levante-family VIN prefix (``ZN6...``) maps to the "maserati"
     marque via ``mes.platform.marque_for_vin``, and that marque's
     sibling model (``"levante"``) has a reachable topology entry --
     i.e. the VIN-to-platform-family path actually connects to this
     research, without ``model_for_vin`` being made to guess Levante vs.
     Grecale (it still correctly returns UNKNOWN for that ambiguous WMI).
  3. This car's own Giorgio routes (``cuore.live.buses.CAN_C``/
     ``CAN_IHS``/``CAN_CH``: pins, bitrates, routes) are byte-for-byte
     unchanged by the additive ``SIBLING_PLATFORM_BUSES`` data, and that
     new dict is empty and never consulted for a Giorgio VIN.

Run:
    .venv/Scripts/python.exe cuore/tests/check_platform.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore import bootstrap  # noqa: F401,E402 -- side effect: puts mes-log-mcp on sys.path
from cuore.live import buses  # noqa: E402
from cuore.live.buses import CAN_C, CAN_CH, CAN_IHS  # noqa: E402
from mes import platform as pf  # noqa: E402 -- needs bootstrap to have run

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


SIBLING_MODELS = ("grecale", "levante", "purosangue")

# --- 1. bus_topology_for() returns a confidence-graded dict per model -------

print("=== bus_topology_for() for each sibling platform ===")
for model in SIBLING_MODELS:
    topo = pf.bus_topology_for(model)
    check(f"bus_topology_for({model!r}) returns a dict", isinstance(topo, dict), str(topo))
    if not isinstance(topo, dict):
        continue
    check(f"bus_topology_for({model!r}) is non-empty", len(topo) > 0)
    for fact_name, fact in topo.items():
        check(f"{model}.{fact_name} is a dict with a confidence",
              isinstance(fact, dict) and "confidence" in fact, str(fact))
        if isinstance(fact, dict):
            check(f"{model}.{fact_name}.confidence is a valid level",
                  fact.get("confidence") in pf.CONFIDENCE_LEVELS, fact.get("confidence"))
            check(f"{model}.{fact_name}: non-UNKNOWN has a source",
                  fact.get("confidence") == pf.UNKNOWN or bool((fact.get("source") or "").strip()),
                  str(fact))
            check(f"{model}.{fact_name}: UNKNOWN has an explanatory note "
                  "(never a silent blank)",
                  fact.get("confidence") != pf.UNKNOWN or bool((fact.get("note") or "").strip()),
                  str(fact))

print("=== bus_topology_for() is None for everything else ===")
check('bus_topology_for("stelvio") is None (lives in cuore.live.buses instead)',
      pf.bus_topology_for("stelvio") is None)
check('bus_topology_for("bugatti") is None', pf.bus_topology_for("bugatti") is None)
check('bus_topology_for("") is None', pf.bus_topology_for("") is None)

print("=== Grecale's own pin/bitrate facts stay UNKNOWN, not copied from Stelvio ===")
grecale_topo = pf.bus_topology_for("grecale") or {}
check("grecale.obd_pins_can_c is UNKNOWN (not inferred from shared Giorgio platform)",
      grecale_topo.get("obd_pins_can_c", {}).get("confidence") == pf.UNKNOWN,
      str(grecale_topo.get("obd_pins_can_c")))

print("=== Levante's chassis code (M161) is CORROBORATED, sourced ===")
levante_topo = pf.bus_topology_for("levante") or {}
chassis = levante_topo.get("chassis_code", {})
check("levante.chassis_code == 'M161'", chassis.get("value") == "M161", str(chassis))
check("levante.chassis_code is CORROBORATED", chassis.get("confidence") == pf.CORROBORATED, str(chassis))
check("levante.chassis_code has a source", bool((chassis.get("source") or "").strip()))

# --- 2. a Levante-family VIN prefix maps to the maserati marque, which  -----
#        reaches the levante topology entry ---------------------------------

print("=== Levante-family VIN (ZN6...) maps to its platform family ===")
LEVANTE_VIN = "ZN661XUA9JX000001"  # same synthetic fixture VIN as check_marque_port.py
check('marque_for_vin("ZN661XUA9JX000001") == "maserati"',
      pf.marque_for_vin(LEVANTE_VIN) == "maserati", pf.marque_for_vin(LEVANTE_VIN))
check("model_for_vin() still correctly refuses to guess Levante vs. Grecale "
      "for this ambiguous ZN6 WMI (UNKNOWN, not a guess)",
      pf.model_for_vin(LEVANTE_VIN) == pf.UNKNOWN, pf.model_for_vin(LEVANTE_VIN))
check("the 'levante' platform entry this VIN's marque belongs to has a "
      "reachable bus-topology entry (bus_topology_for('levante') is not None)",
      pf.bus_topology_for("levante") is not None)

# --- 3. Giorgio routes unchanged; sibling bus data is additive and inert ---

print("=== Giorgio routes (CAN_C / CAN_IHS / CAN_CH) unchanged ===")
check("CAN_C.pins == (6, 14)", CAN_C.pins == (6, 14), str(CAN_C.pins))
check("CAN_C.bitrate == 500000", CAN_C.bitrate == 500000, str(CAN_C.bitrate))
check("CAN_C.id_bits == 29", CAN_C.id_bits == 29, str(CAN_C.id_bits))
check("CAN_IHS.pins == (3, 11)", CAN_IHS.pins == (3, 11), str(CAN_IHS.pins))
check("CAN_IHS.bitrate == 125000", CAN_IHS.bitrate == 125000, str(CAN_IHS.bitrate))
check("CAN_CH.pins == (12, 13)", CAN_CH.pins == (12, 13), str(CAN_CH.pins))
check("CAN_CH.bitrate == 500000", CAN_CH.bitrate == 500000, str(CAN_CH.bitrate))
check("CAN_CH.transmit_needs_confirmation is True", CAN_CH.transmit_needs_confirmation is True)

r_ihs_a5 = buses.route_for(CAN_IHS, "blue_a5")
check("route_for(CAN_IHS, blue_a5).bitrate_override == 125000 (unchanged)",
      (r_ihs_a5.bitrate_override if r_ihs_a5 else None) == 125000)
check("BUSES has exactly can_c/can_ihs/can_ch (no sibling bus leaked in)",
      set(buses.BUSES.keys()) == {"can_c", "can_ihs", "can_ch"}, str(buses.BUSES.keys()))

print("=== SIBLING_PLATFORM_BUSES is additive, empty by design, and inert ===")
check("SIBLING_PLATFORM_BUSES is a dict", isinstance(buses.SIBLING_PLATFORM_BUSES, dict))
check("SIBLING_PLATFORM_BUSES is empty this pass (no fact cleared CORROBORATED "
      "at the pin/bitrate level -- see the research doc)",
      buses.SIBLING_PLATFORM_BUSES == {}, str(buses.SIBLING_PLATFORM_BUSES))
check("sibling_platform_bus('levante', 'can_c') is None (nothing to select yet)",
      buses.sibling_platform_bus("levante", "can_c") is None)
check("sibling_platform_bus('grecale', 'can_c') is None",
      buses.sibling_platform_bus("grecale", "can_c") is None)
check("sibling_platform_bus('purosangue', 'can_c') is None",
      buses.sibling_platform_bus("purosangue", "can_c") is None)
check("a Giorgio VIN's own buses never resolve through sibling_platform_bus "
      "(selection is marque_for_vin/model_for_vin -> BUSES only)",
      buses.sibling_platform_bus("stelvio", "can_c") is None)


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
