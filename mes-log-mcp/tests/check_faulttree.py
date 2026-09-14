"""Smoke checks for the fault-isolation trees.

The real corpus is the fixture for the VIN-annotation checks: this Stelvio's
logs demonstrably contain six COMPLETED purge-valve actuations, so the
evidence hook must find them and say so.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from mes import faulttree  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


print("=== tree structure ===")
for tree in faulttree.TREES:
    check(f"{tree.key}: every step sourced",
          all(s.source for s in tree.steps + tree.verification))
    check(f"{tree.key}: every step names its tools and expected result",
          all(s.tools and s.expect for s in tree.steps))
    check(f"{tree.key}: has do-not list", len(tree.do_not) >= 2)

evap = faulttree.EVAP_LEAK
check("EVAP tree starts with the FCA-first quick-connect",
      evap.steps[0].id == "E1" and "S2125000002" in evap.steps[0].source)
check("KOEO caution present on the actuator step",
      any(s.id == "E3" and "OFF" in s.caution for s in evap.steps))
check("verification refuses the road test",
      any("road test" in s.test.lower() or "road test" in s.source.lower()
          for s in evap.verification))
check("parts-cannon guards present",
      any("purge solenoid alone" in d for d in evap.do_not))

print("=== routing ===")
check("failure byte tolerated",
      faulttree.trees_for(["P0456-00"]) == faulttree.trees_for(["P0456"]))
check("P1CEA routes to its own tree",
      [t.key for t in faulttree.trees_for(["P1CEA"])] == ["p1cea-boost-purge"])
both = faulttree.evaluate(["P0456", "P1CEA"])
check("both trees + ordering note when leak and flow codes coexist",
      len(both["trees"]) == 2 and "ordering_note" in both)
miss = faulttree.evaluate(["U0100"])
check("uncovered code errors and lists what exists",
      "error" in miss and miss["available"])

print("=== VIN evidence annotation (real corpus) ===")
d = json.loads(server.fault_tree(codes="P0455 P0440-00 P0456", vin=VIN))
ev = d.get("vehicle_evidence", [])
check("purge-valve history found and attached to E3",
      any(e["step"] == "E3" and "COMPLETED 6" in e["finding"] for e in ev), ev)
check("no evidence block without a VIN",
      "vehicle_evidence" not in json.loads(
          server.fault_tree(codes="P0456")))

print("=== server listing ===")
l = json.loads(server.fault_tree())
check("no-arg lists both trees",
      {t["tree"] for t in l["available"]}
      == {"evap-leak", "p1cea-boost-purge"})

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("all checks passed")
