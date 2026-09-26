"""Smoke checks for dealer (wiTECH) results as evidence.

The dealer store is append-only JSONL kept beside cuore's other state. This
suite must never touch the real bench's evidence, so ``CUORE_STATE_DIR`` is
pointed at a throwaway directory before anything under ``mes`` (or
``server``) is imported -- ``mes.dealer.state_dir()`` reads the env var
directly and creates/writes there.

The real corpus (chronic P0456 on this VIN) backs the gate/tree/workup
integration checks; the dealer store itself is exercised entirely against the
temp directory.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Before any mes/server import: dealer results must land in a throwaway
# directory, never the bench's real evidence store.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="mes-check-dealer-")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from mes import dealer, faulttree, verdict, workup  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
OTHER_VIN = "1C4RJFAG0JC000001"
failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


print("=== store: validation ===")
try:
    dealer.record(VIN, "flash_check", {"module": "ECM"})
    check("flash_check missing fields rejected", False)
except ValueError as exc:
    check("flash_check missing fields rejected", "flash_check needs" in str(exc))

try:
    dealer.record(VIN, "slvt", {"result": "maybe"})
    check("slvt bad result rejected", False)
except ValueError:
    check("slvt bad result rejected", True)

try:
    dealer.record(VIN, "not_a_kind", {})
    check("unknown kind rejected", False)
except ValueError as exc:
    check("unknown kind rejected", "unknown dealer result kind" in str(exc))

try:
    dealer.record("", "slvt", {"result": "pass"})
    check("empty vin rejected", False)
except ValueError:
    check("empty vin rejected", True)

print("=== store: record / load / latest ===")
e1 = dealer.record(VIN, "flash_check",
                   {"module": "ECM", "current_part": "68123456AA",
                    "new_part": "68123456AB", "flashed": False}, note="first check")
check("record stamps at/source", e1.get("at") and
      e1.get("source") == "technician-entered from wiTECH")
check("flash_check derives current=False when parts differ and not flashed",
      e1["data"]["current"] is False)

e2 = dealer.record(VIN, "flash_check",
                   {"module": "ECM", "current_part": "68123456AA",
                    "new_part": "68123456AB", "flashed": True,
                    "part_after": "68123456AB"})
check("flash_check derives current=True when flashed to the new part",
      e2["data"]["current"] is True)

e3 = dealer.record(VIN, "flash_check",
                   {"module": "ECM", "current_part": "68123456AB",
                    "new_part": "68123456AB"})
check("flash_check derives current=True when already matching",
      e3["data"]["current"] is True)

slvt_fail = dealer.record(VIN, "slvt", {"result": "fail", "detail": "measured 0.030 in"})
dealer.record(VIN, "dtc_report", {"module": "ECM", "codes": ["P0456"], "note": "confirmed"})
dealer.record(VIN, "recall_status", {"campaign": "25V586000", "status": "open"})
dealer.record(VIN, "routine", {"module": "ABS", "name": "Phonic Wheel Replacement",
                               "result": "OK"})
dealer.record(OTHER_VIN, "slvt", {"result": "pass"})

loaded = dealer.load(VIN)
check("load returns only this VIN's records", all(r["vin"] == VIN for r in loaded))
check("load excludes other VINs", not any(r["vin"] == OTHER_VIN for r in loaded))
check("load(kind=) filters", len(dealer.load(VIN, "slvt")) == 1)

newest_flash = dealer.latest(VIN, "flash_check", module="ECM")
check("latest returns the newest flash_check", newest_flash["data"]["current_part"] == "68123456AB"
      and newest_flash["data"]["new_part"] == "68123456AB")
check("latest respects data-field matching",
      dealer.latest(VIN, "flash_check", module="BCM") is None)

print("=== gate: dealer measurement ===")
MECH = ("canister charcoal bed saturated so the vent path is blocked, "
       "holding pressure and failing both leak monitors")
DISC = ("KOEO actuator test on the purge valve completed with an audible "
       "click, exonerating the purge side")

g_slvt = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="vapor canister", mechanism=MECH,
    disconfirming_test=DISC,
    measurements=json.dumps([{"type": "dealer", "kind": "slvt"}])))
slvt_check = g_slvt["criteria"]["measurement"]["checked"][0]
check("gate accepts a dealer slvt cite as verified", slvt_check["status"] == "verified")
check("gate surfaces the SLVT FAIL result", "FAIL" in slvt_check["note"])
check("full evidence with a dealer cite is CONFIRMED", g_slvt["verdict"] == "CONFIRMED", g_slvt)

g_flash = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="vapor canister", mechanism=MECH,
    disconfirming_test=DISC,
    measurements=json.dumps([{"type": "dealer", "kind": "flash_check", "module": "ECM"}])))
flash_check = g_flash["criteria"]["measurement"]["checked"][0]
check("gate accepts a dealer flash_check cite as verified", flash_check["status"] == "verified")

g_missing = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="vapor canister", mechanism=MECH,
    disconfirming_test=DISC,
    measurements=json.dumps([{"type": "dealer", "kind": "routine", "module": "TCM"}])))
missing_check = g_missing["criteria"]["measurement"]["checked"][0]
check("gate reports not_found for a dealer cite with no matching record",
      missing_check["status"] == "not_found")

g_bad_kind = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="vapor canister", mechanism=MECH,
    disconfirming_test=DISC,
    measurements=json.dumps([{"type": "dealer", "kind": "nonsense"}])))
bad_kind_check = g_bad_kind["criteria"]["measurement"]["checked"][0]
check("gate rejects an unknown dealer kind", bad_kind_check["status"] == "rejected")

unknown_type = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="x", mechanism=MECH, disconfirming_test=DISC,
    measurements=json.dumps([{"type": "totally_unknown"}])))
check("unknown measurement type lists dealer as a valid option",
      "dealer" in unknown_type["criteria"]["measurement"]["checked"][0]["note"])

print("=== fault tree: E8/V2 annotation ===")
tree_current = faulttree.evaluate(["P0456"], vin=VIN)
e8_findings = [e for e in tree_current.get("vehicle_evidence", []) if e["step"] == "E8"]
check("E8 carries a dealer flash_check finding",
      any("Dealer flash check" in e["finding"] for e in e8_findings))
check("E8 finding for the newest flash reports current, not newer-available",
      any("ECM is current" in e["finding"] for e in e8_findings))
v2_findings = [e for e in tree_current.get("vehicle_evidence", []) if e["step"] == "V2"]
check("V2 carries the SLVT finding", any("SLVT" in e["finding"] for e in v2_findings)
      and any("FAIL" in e["finding"] for e in v2_findings))

# A fresh VIN with only a "newer calibration available" flash check.
NEWER_VIN = "ZFA0000000000newr"
dealer.record(NEWER_VIN, "flash_check",
             {"module": "ECM", "current_part": "AAA", "new_part": "BBB", "flashed": False})
tree_newer = faulttree.evaluate(["P0456"], vin=NEWER_VIN)
e8_newer = [e for e in tree_newer.get("vehicle_evidence", []) if e["step"] == "E8"]
check("E8 finding for an outdated ECM reports a newer calibration available",
      any("newer calibration available" in e["finding"] for e in e8_newer))

print("=== workup: already_attempted + calibration blind spot ===")
dossier = workup.build(vin=VIN)
dealer_attempts = [a for a in dossier["already_attempted"] if a.get("kind") == "dealer"]
check("already_attempted includes dealer records",
      len(dealer_attempts) >= 5)
check("already_attempted dealer rows carry operation/outcome/timestamp",
      all({"operation", "outcome", "timestamp"} <= set(a) for a in dealer_attempts))
check("SLVT attempt reports fail as its outcome",
      any(a["operation"].startswith("dealer SLVT") and a["outcome"] == "fail"
          for a in dealer_attempts))

blind = next((b for b in dossier["blind_spots"]
             if b["question"] == "Is the ECM on the latest calibration?"), None)
check("calibration blind spot present", blind is not None)
check("calibration blind spot answered from the recorded flash check",
      blind is not None and "Answered by dealer flash check" in blind["why_unknown"])
check("calibration blind spot says already closed",
      blind is not None and blind["closes_it"] == "already closed (technician-entered from wiTECH)")

print("=== MCP tools ===")
rec = json.loads(server.record_dealer_result(
    vin=VIN, kind="slvt", data_json=json.dumps({"result": "pass"}), note="via MCP tool"))
check("record_dealer_result tool records", rec["kind"] == "slvt" and rec["note"] == "via MCP tool")

listed = json.loads(server.dealer_results(vin=VIN))
check("dealer_results tool lists what was recorded",
      listed["vin"] == VIN and any(r["note"] == "via MCP tool" for r in listed["results"]))

bad = json.loads(server.record_dealer_result(vin=VIN, kind="slvt", data_json="{}"))
check("record_dealer_result tool surfaces validation errors", "error" in bad)


print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
