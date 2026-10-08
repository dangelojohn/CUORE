"""Smoke checks for physical layout systems (mes.layout_systems).

Same posture as ``check_electrical.py``. Five checks, per the build spec:
1. element schema matches electrical.py's (same keys).
2. every location has a source, or is explicitly UNKNOWN.
3. P0455 physical path includes the canister and the ESIM, and merges in
   electrical.py's own hops (the electrical connector/ground elements).
4. P0171 path spans air_intake_boost and fuel in systems_interaction.
5. every element's part_of_systems keys exist in mes.systems.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mes-log-mcp
sys.path.insert(0, str(REPO_ROOT))                             # repo root (cuore)

from mes import electrical, layout_systems, systems  # noqa: E402

failures: list[str] = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


# --- 1. element schema matches electrical.py's ------------------------------
print("=== element schema parity ===")
elec_sample = next(iter(electrical.ELEMENTS.values()))
layout_sample = next(iter(layout_systems.ELEMENTS.values()))
expected_keys = set(elec_sample.keys())
bad_schema = []
for eid, e in layout_systems.ELEMENTS.items():
    if set(e.keys()) != expected_keys:
        bad_schema.append(f"{eid}: keys {sorted(e.keys())}")
check("every layout_systems element has electrical.py's exact key set",
      not bad_schema, "; ".join(bad_schema[:5]))
check("location sub-dict shape matches too",
      set(layout_sample["location"].keys()) ==
      set(elec_sample["location"].keys()))

# --- 2. every location has a source, or is UNKNOWN --------------------------
print("=== element location sourcing ===")
bad_loc = []
for eid, e in layout_systems.ELEMENTS.items():
    loc = e.get("location", {})
    conf = loc.get("confidence")
    src = loc.get("source")
    if conf is None or conf not in electrical.CONFIDENCE_LEVELS:
        bad_loc.append(f"{eid}: bad confidence {conf!r}")
        continue
    if conf == electrical.UNKNOWN:
        if "UNKNOWN" not in loc.get("description", ""):
            bad_loc.append(f"{eid}: UNKNOWN confidence but description "
                           "doesn't say so")
    else:
        if not src:
            bad_loc.append(f"{eid}: confidence {conf} but no source")
check("every element location sourced or UNKNOWN", not bad_loc,
      "; ".join(bad_loc[:5]))

# --- 3. P0455 physical path includes canister + ESIM, merges electrical -----
print("=== P0455 physical path ===")
p0455 = layout_systems.code_physical_path("P0455")
check("P0455 resolves to the evap family", p0455["family"] == "evap",
      str(p0455["family"]))
check("P0455 electrical_family is also evap (merge precondition)",
      p0455["electrical_family"] == "evap", str(p0455["electrical_family"]))

elems_by_domain = {}
for hop in p0455["path"]:
    elems_by_domain.setdefault(hop.get("domain"), []).append(hop["element"])

check("P0455 physical path includes the canister",
      "evap_canister" in elems_by_domain.get("physical", []),
      str(elems_by_domain.get("physical")))
check("P0455 physical path includes the (physical) ESIM",
      "esim" in elems_by_domain.get("physical", []),
      str(elems_by_domain.get("physical")))
check("P0455 path merges in electrical.py's own hops first",
      "esim_connector" in elems_by_domain.get("electrical", []) and
      elems_by_domain.get("electrical") and
      p0455["path"][0]["domain"] == "electrical",
      str(elems_by_domain.get("electrical")))

# a code with a failure-type byte should resolve the same way
p0455_byte = layout_systems.code_physical_path("P0455-00")
check("P0455-00 (failure byte) resolves the same as P0455",
      p0455_byte["family"] == "evap")

# a code outside every curated family must come back empty, not invented
unknown = layout_systems.code_physical_path("P9999")
check("unsourced code returns empty path, not invented data",
      unknown["family"] is None and unknown["electrical_family"] is None
      and unknown["path"] == [])

# --- 4. P0171 path spans air_intake_boost and fuel ---------------------------
print("=== P0171 fuel-trim path ===")
p0171 = layout_systems.code_physical_path("P0171")
check("P0171 resolves to the fuel_trim family", p0171["family"] == "fuel_trim",
      str(p0171["family"]))
interaction_systems = {i["system"] for i in p0171["systems_interaction"]}
check("P0171 systems_interaction spans air_intake_boost and fuel",
      {"air_intake_boost", "fuel"} <= interaction_systems,
      str(interaction_systems))
path_elements = [hop["element"] for hop in p0171["path"]]
check("P0171 path includes an air_intake_boost element and a fuel element",
      any(layout_systems.element(e) and "air_intake_boost" in
          layout_systems.element(e).get("part_of_systems", [])
          for e in path_elements if layout_systems.element(e))
      and any(layout_systems.element(e) and "fuel" in
              layout_systems.element(e).get("part_of_systems", [])
              for e in path_elements if layout_systems.element(e)),
      str(path_elements))

# --- 5. every element's part_of_systems keys exist in mes.systems -----------
print("=== part_of_systems cross-check against mes.systems ===")
system_keys = set(systems.SYSTEMS.keys())
bad_systems = []
for eid, e in layout_systems.ELEMENTS.items():
    for s in e.get("part_of_systems", []):
        if s not in system_keys:
            bad_systems.append(f"{eid}: {s!r} not in mes.systems.SYSTEMS")
check("every part_of_systems key exists in mes.systems.SYSTEMS",
      not bad_systems, "; ".join(bad_systems[:10]))

# bonus: elements(system=...) filter sanity
evap_elems = layout_systems.elements(system="evap")
check("elements(system='evap') returns at least the canister and ESIM",
      {"evap_canister", "esim"} <= {e["id"] for e in evap_elems},
      str([e["id"] for e in evap_elems]))

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
