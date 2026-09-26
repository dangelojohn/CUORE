"""Smoke checks for the fault-isolation trees.

The real corpus is the fixture for the VIN-annotation checks: this Stelvio's
logs demonstrably contain several COMPLETED purge-valve actuations (the exact
count grows as the corpus does -- do not hardcode it), so the evidence hook
must find them and say so.
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
miss = faulttree.evaluate(["P0300"])
check("uncovered code errors and lists what exists",
      "error" in miss and miss["available"])

print("=== network cascade tree ===")
net_codes = ["U1711-2F", "U1712-2F", "U1713-2F", "U1716-2F", "U2054-87",
             "U0100-87", "B1040-64"]
for c in net_codes:
    check(f"{c} routes to the network-cascade tree",
          [t.key for t in faulttree.trees_for([c])] == ["network-cascade"],
          c)
network = faulttree.NETWORK_CASCADE
check("network tree's first step is a verification, not a repair",
      "rescan" in network.steps[0].test.lower()
      and "replace" not in network.steps[0].if_abnormal.lower())
check("network tree pulls DTC EX before any clearing step",
      any("dtc ex" in s.test.lower() for s in network.steps[:3]))
check("network tree reads the brake module on CAN-CH before parts work",
      any("grey a6" in s.test.lower() and "abs" in s.test.lower()
          for s in network.steps[:3]))
check("network tree follows knowledge.py's own supply->ground->terminal "
      "order",
      [s.id for s in network.steps if "S1808000005" in s.source
       or "S2008000032" in s.source or "S1708000262" in s.source] ==
      ["N5", "N6", "N7"])

print("=== DASM/HALF private-CAN tree ===")
check("C141C routes to the dasm-half tree",
      [t.key for t in faulttree.trees_for(["C141C-86"])]
      == ["dasm-half-private-can"])
check("C141B routes to the dasm-half tree (code itself unsourced, flagged "
      "in framing)",
      [t.key for t in faulttree.trees_for(["C141B-97"])]
      == ["dasm-half-private-can"])
dasm_half = faulttree.DASM_HALF_LINK
check("dasm-half tree's general-practice step is clearly labelled as such",
      any("not sourced" in s.source.lower() for s in dasm_half.steps))

print("=== sourcing hygiene across all trees ===")
check("no step source is empty or a TODO placeholder",
      all(s.source.strip() and "todo" not in s.source.lower()
          for t in faulttree.TREES for s in t.steps + t.verification))

print("=== VIN evidence annotation (real corpus) ===")
d = json.loads(server.fault_tree(codes="P0455 P0440-00 P0456", vin=VIN))
ev = d.get("vehicle_evidence", [])
check("purge-valve history found and attached to E3",
      any(e["step"] == "E3" and "COMPLETED" in e["finding"]
          and "actuator test" in e["finding"] for e in ev), ev)
check("no evidence block without a VIN",
      "vehicle_evidence" not in json.loads(
          server.fault_tree(codes="P0456")))

dn = json.loads(server.fault_tree(
    codes="U1711-2F U1712-2F U1713-2F U0100-87", vin=VIN))
evn = dn.get("vehicle_evidence", [])
check("network-cascade VIN evidence attached to N1",
      any(e["step"] == "N1" for e in evn), evn)

dd = json.loads(server.fault_tree(codes="C141C-86", vin=VIN))
evd = dd.get("vehicle_evidence", [])
check("dasm-half VIN evidence attached to D1",
      any(e["step"] == "D1" for e in evd), evd)

print("=== server listing ===")
l = json.loads(server.fault_tree())
check("no-arg lists all four trees",
      {t["tree"] for t in l["available"]}
      == {"evap-leak", "p1cea-boost-purge", "network-cascade",
          "dasm-half-private-can"})

print()

# --- dealer flash check (step E8) -------------------------------------------
_evap = next(tr for tr in faulttree.TREES if tr.key == "evap-leak")
_e8 = next((st for st in _evap.steps if st.id == "E8"), None)
check("evap-leak has the dealer flash check as step E8", _e8 is not None)
check("E8 cites the PCM flash family", _e8 is not None and "18-030-17" in _e8.source)
check("E8 says FCA publishes no calibration numbers",
      _e8 is not None and "no calibration numbers" in _e8.source)
_ev = faulttree.evaluate(["P0455", "P0456", "P0440"], vin="ZASFAKPN5J7B88115")
_e8ev = [e for e in _ev.get("vehicle_evidence", []) if e.get("step") == "E8"]
check("this VIN's evaluate carries an E8 finding", bool(_e8ev), str(_ev.get("vehicle_evidence")))
check("the E8 finding names the installed supplier software P235QB39",
      bool(_e8ev) and "P235QB39" in _e8ev[0]["finding"], _e8ev[0]["finding"] if _e8ev else "")
check("the E8 finding includes the dealer request with the VIN",
      bool(_e8ev) and "wiTECH ECU flash check on VIN ZASFAKPN5J7B88115" in _e8ev[0]["finding"])

if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("all checks passed")
