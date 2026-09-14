"""Smoke checks for the evidence gate.

The real corpus is the fixture: chronic P0456, six COMPLETED purge-valve
actuations, freeze frames for all three EVAP codes. The gate must verify
citations against those facts and refuse everything it cannot verify.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
MECH = ("canister charcoal bed saturated so the vent path is blocked, "
        "holding pressure and failing both leak monitors")
DISC = ("KOEO actuator test on the purge valve completed with an audible "
        "click, exonerating the purge side")
failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def gate(**kw):
    args = dict(vin=VIN, codes="P0456", component="", mechanism="",
                measurements="", disconfirming_test="")
    args.update(kw)
    return json.loads(server.diagnosis_verdict(**args))


print("=== refusals ===")
g = gate(component="purge solenoid")
check("bare guess is NOT CONFIRMED", g["verdict"] == "NOT CONFIRMED")
check("missing criteria named",
      set(g["missing"]) == {"mechanism", "measurement", "disconfirmation"})
check("chronic P0456 auto-satisfies 'demonstrated'",
      g["criteria"]["demonstrated"]["met"])
check("next test pulled from the fault tree",
      "E1" in (g["criteria"]["measurement"]["next_test"] or ""))
check("purge-solenoid warning fires",
      any("low-yield" in w for w in g.get("component_warnings", [])))
check("plain answer says guessing", "guessing" in g["plain_answer"])

d = gate(component="canister", mechanism=MECH, disconfirming_test=DISC,
         measurements=json.dumps([{"type": "dtc", "code": "P0456"}]))
check("a DTC is not a measurement", d["verdict"] == "NOT CONFIRMED"
      and "not a measurement" in
      d["criteria"]["measurement"]["checked"][0]["note"])

f = gate(component="canister", mechanism=MECH, disconfirming_test=DISC,
         measurements=json.dumps(
             [{"type": "actuator", "operation": "Nonexistent thing"}]))
check("fabricated citation comes back not_found and fails the gate",
      f["verdict"] == "NOT CONFIRMED"
      and f["criteria"]["measurement"]["checked"][0]["status"] == "not_found")

short = gate(component="canister", mechanism="canister",
             disconfirming_test=DISC,
             measurements=json.dumps([{"type": "freeze_frame",
                                       "code": "P0456"}]))
check("a part name is not a mechanism",
      not short["criteria"]["mechanism"]["met"])

print("=== confirmation ===")
m = json.dumps([
    {"type": "actuator", "operation": "Evaporation control valve"},
    {"type": "freeze_frame", "code": "P0456"},
    {"type": "manual",
     "description": "smoke test showed smoke at the canister housing seam"},
])
c = gate(codes="P0455 P0440 P0456", component="vapor canister",
         mechanism=MECH, measurements=m, disconfirming_test=DISC)
check("full evidence is CONFIRMED", c["verdict"] == "CONFIRMED", c)
st = [x["status"] for x in c["criteria"]["measurement"]["checked"]]
check("actuator + freeze frame verified in corpus, smoke attested",
      st == ["verified", "attested"] or st == ["verified", "verified",
                                               "attested"], st)
check("verified actuator carries its logged outcome",
      c["criteria"]["measurement"]["checked"][0]["found"]["outcome"]
      == "COMPLETED")
check("canister/ESIM caution shown even when confirmed",
      any("9100469" in w for w in c.get("component_warnings", [])))
check("confirmed answer points at repair verification",
      "verify the repair" in c["plain_answer"])

print("=== input handling ===")
check("empty codes is an error", "error" in gate(codes=""))
check("empty vin is an error",
      "error" in json.loads(server.diagnosis_verdict(
          vin="", codes="P0456")))
plain = gate(component="canister", mechanism=MECH, disconfirming_test=DISC,
             measurements="smoke poured out of the filler neck union")
check("bare-string measurement treated as one manual attestation",
      plain["criteria"]["measurement"]["met"]
      and plain["criteria"]["measurement"]["checked"][0]["status"]
      == "attested")
unknown = gate(codes="P9999", component="canister", mechanism=MECH,
               disconfirming_test=DISC,
               measurements=json.dumps([{"type": "freeze_frame",
                                         "code": "P0456"}]))
check("never-seen code fails 'demonstrated'",
      not unknown["criteria"]["demonstrated"]["met"])

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("all checks passed")
