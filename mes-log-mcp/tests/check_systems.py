"""Smoke checks for mes.systems: the vehicle-systems graph, code -> system
assignment, and the real-corpus correlation.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_systems.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_MES_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _MES_ROOT.parent
sys.path.insert(0, str(_MES_ROOT))
sys.path.insert(0, str(_REPO_ROOT))

from mes import systems  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio this toolchain already knows about

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


print("=== every depends_on edge is sourced or UNKNOWN ===")
for sys_key, row in systems.SYSTEMS.items():
    for dep in row["depends_on"]:
        has_source = bool(dep.get("source"))
        check(f"{sys_key} -> {dep['system']} has a source",
              has_source, str(dep))
        if dep["confidence"] == systems.UNKNOWN:
            check(f"{sys_key} -> {dep['system']} UNKNOWN carries the standard note",
                  "TechAuthority" in dep["source"] or "not established" in dep["source"],
                  dep["source"])
        else:
            check(f"{sys_key} -> {dep['system']} non-UNKNOWN is not the placeholder note",
                  dep["source"] != systems._UNKNOWN_NOTE, dep["source"])

print("=== systems() ===")
all_systems = systems.systems()
check("25 systems in the graph", len(all_systems) == 25, str(len(all_systems)))
check("every system has at least one component",
      all(row["components"] for row in all_systems.values()))

print("=== pcv (new system) ===")
pcv_deps = systems.SYSTEMS["pcv"]["depends_on"]
check("pcv exists with a sourced or UNKNOWN depends_on",
      bool(pcv_deps) and all(bool(d.get("source")) for d in pcv_deps),
      str(pcv_deps))

crankcase_code = systems.systems_for_code("P1C44", "Crankcase ventilation valve stuck open")
check("a 'crankcase' description routes to pcv",
      any(e["system"] == "pcv" for e in crankcase_code), crankcase_code)

print("=== systems_for_code ===")
p0455 = systems.systems_for_code("P0455")
check("P0455 has an evap primary row",
      any(e["system"] == "evap" and e["role"] == "primary" for e in p0455), p0455)
check("P0455 has electrical_supply upstream",
      any(e["system"] == "electrical_supply" and e["role"] == "upstream" for e in p0455),
      p0455)
check("P0455 has fuel upstream",
      any(e["system"] == "fuel" and e["role"] == "upstream" for e in p0455), p0455)

p0455_suffix = systems.systems_for_code("P0455-00")
check("failure byte ignored (P0455-00 same as P0455)",
      {(e["system"], e["role"]) for e in p0455_suffix} ==
      {(e["system"], e["role"]) for e in p0455}, p0455_suffix)

u1713 = systems.systems_for_code("U1713")
check("U1713 -> network", any(e["system"] == "network" for e in u1713), u1713)

misfire = systems.systems_for_code("P0302")
check("P0302 misfire -> ignition + fuel primaries",
      {"ignition", "fuel"} <= {e["system"] for e in misfire if e["role"] == "primary"},
      misfire)

unknown_code = systems.systems_for_code("P9999")
check("an unrouteable code returns one honest UNKNOWN row",
      unknown_code == [{"system": "UNKNOWN", "role": "primary",
                        "confidence": systems.UNKNOWN,
                        "source": systems._UNKNOWN_NOTE}],
      unknown_code)

p1_keyword = systems.systems_for_code("P1C00", "EVAP purge control circuit malfunction")
check("P1xxx keyword match (evap) when no exact entry exists",
      any(e["system"] == "evap" for e in p1_keyword), p1_keyword)

print("=== correlate (real corpus) ===")
result = systems.correlate(VIN)
check("no error for the known VIN", "error" not in result, str(result))
by_system = {row["system"]: row for row in result.get("by_system", [])}
check("by_system covers every system key",
      set(by_system) == set(systems.SYSTEMS), str(set(by_system)))
check("evap present with >= 4 sessions",
      by_system.get("evap", {}).get("sessions", 0) >= 4,
      str(by_system.get("evap")))
check("network present with >= 4 sessions",
      by_system.get("network", {}).get("sessions", 0) >= 4,
      str(by_system.get("network")))
check("at least one co-occurrence row",
      len(result.get("co_occurrence", [])) >= 1, str(result.get("co_occurrence")))
check("co-occurrence rows only for pairs sharing >= 2 sessions",
      all(row["sessions_together"] >= 2 for row in result.get("co_occurrence", [])))
check("findings is a non-empty list of strings",
      bool(result.get("findings")) and all(isinstance(f, str) for f in result["findings"]))
_label_to_key = {v["label"]: k for k, v in systems.SYSTEMS.items()}
check("chains only built for systems with sessions > 0",
      all(by_system[_label_to_key[c["issue"].rsplit(" codes", 1)[0]]]["sessions"] > 0
          for c in result.get("chains", [])))

unknown_vin = systems.correlate("NOPE123NOTREAL0000")
check("unknown VIN is an error, not an empty graph", "error" in unknown_vin, str(unknown_vin))

print("=== technical enrichment ===")
_sourced_measures = []
for sys_key, row in systems.SYSTEMS.items():
    for dep in row["depends_on"]:
        tech = dep.get("technical")
        check(f"{sys_key} -> {dep['system']} technical has carries+propagates",
              bool(tech) and bool(tech.get("carries")) and bool(tech.get("propagates")),
              str(tech))
        if tech and tech.get("measure") and tech["measure"].get("source"):
            _sourced_measures.append((sys_key, dep["system"]))
check("at least 3 edges have a sourced measure",
      len(_sourced_measures) >= 3, str(_sourced_measures))

net_elec = next(d for d in systems.SYSTEMS["network"]["depends_on"]
                if d["system"] == "electrical_supply")
check("network -> electrical_supply measure reads 'Measure: ... G003A to battery negative'",
      net_elec["technical"]["measure"]["where"] == "G003A to battery negative"
      and net_elec["technical"]["measure"]["source"] == "S2008000032",
      str(net_elec["technical"]["measure"]))

check("every system's technical.codes_owned matches _EXACT_RULES exactly",
      all(set(row["technical"]["codes_owned"]) ==
          {c for r in systems._EXACT_RULES if sys_key in r["systems"] for c in r["codes"]}
          for sys_key, row in systems.SYSTEMS.items()))

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print(f"all {checks} checks passed")
