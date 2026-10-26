"""Minimal checks for the fault board data side (synthetic state in a temp CUORE_STATE_DIR).

  1. importance order: safety active, then MIL, then permanent, active ...; resolved last
  2. times cleared / returned after clear counted from a clear action + later reads
  3. mark_fixed -> verifying with the one-line proof rule; undo retracts the action
  4. a later read with the code -> active again, flagged returned_after_fix (counted)
  5. proven-fixed only with a clean read after warm-ups (computed, not set)
  6. symptom: mark_fixed adds the 'resolved' note, undo hides it
  7. the POSTs redirect (and refuse an off-site return_to); the partial renders with shared 'fold' groups

Run:  .venv/Scripts/python.exe cuore/tests/check_fault_board.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-faultboard-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore import bootstrap  # noqa: E402,F401
from cuore.services import cache, fault_board as fb, jobs_bridge  # noqa: E402
from mes import jobs as jobs_mod, symptoms as symptoms_mod, notes as notes_mod  # noqa: E402

VIN = "TESTVIN0000000001"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def flags(**kw):
    base = {"testFailed": False, "pendingDTC": False, "confirmedDTC": False, "testFailedSinceLastClear": False,
            "warningIndicatorRequested": False}
    base.update(kw)
    return base


def obs(kind, at, data, vin=VIN):
    with open(Path(STATE) / "observations.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": at, "kind": kind, "vin": vin, "stream": "serial COM3@115200", "data": data}) + "\n")
    cache.clear()


def module(ecu, at, dtcs):
    obs("module_dtcs", at, {"ecu": ecu, "error": None, "nrc": None,
                            "dtcs": [{"code": c + "-00", "flags": f} for c, f in dtcs]})


def permanent(at, codes):
    obs("obd_dtcs", at, {"kind": "permanent", "dtcs": codes, "by_ecu": {"18DAF110": codes}})


def readiness(at, evap_done, warmups):
    obs("readiness", at, {"since_clear": {"mil_on": False, "all_complete": evap_done, "monitors": [
        {"monitor": "Evaporative system", "supported": True, "complete": evap_done}]},
        "drive_cycle_counters": {"warmups_since_clear": warmups}})


def card(key):
    return {x["key"]: x for x in fb.board(VIN, JOB)}[key]


T = "2026-10-01T10:00:00"
module("ECM", "2026-10-01T09:00:00", [("P0171", flags(confirmedDTC=True))])           # seen, later cleared
module("ECM", T, [("P0456", flags(testFailed=True, confirmedDTC=True)),
                  ("P0300", flags(testFailed=True, confirmedDTC=True, warningIndicatorRequested=True))])
module("ABS", T, [("C1234", flags(testFailed=True, confirmedDTC=True))])
module("BCM", T, [("B1000", flags(testFailed=True, confirmedDTC=True))])
permanent(T, ["P0456"])
readiness(T, False, 1)
JOB = jobs_bridge.open_job(VIN, technician="t", complaint="check")["id"]
jobs_mod.add_action(JOB, "clear", "MES cleared stored codes in ECM at 2026-10-01 09:30", event_date="2026-10-01T09:30:00")
module("ECM", "2026-10-02T12:00:00", [("P0171", flags(confirmedDTC=True, testFailedSinceLastClear=True)),
                                      ("P0456", flags(testFailed=True, confirmedDTC=True)),
                                      ("P0300", flags(testFailed=True, confirmedDTC=True, warningIndicatorRequested=True))])
sid = symptoms_mod.add(VIN, "2026-10-01T08:00:00", tags=["fuel_smell"], text="Fuel smell after filling")["id"]
sid2 = symptoms_mod.add(VIN, "2026-09-01T08:00:00", tags=[], text="Old rattle, since fixed")["id"]
notes_mod.add(VIN, f"Rattle was a loose heat shield. Resolves symptom {sid2}", "vehicle", tags=["resolved"])
cache.clear()

# 1. importance
cards = fb.board(VIN, JOB)
keys = [c["key"] for c in cards]
order = {k: i for i, k in enumerate(keys)}
check(order["code:ABS:C1234"] < order["code:ECM:P0300"] < order["code:ECM:P0456"] < order["code:BCM:B1000"],
      f"safety < MIL < permanent < active, got {keys}")
check(keys[-1] == f"symptom:{sid2}" and cards[-1]["status"] == "resolved", "resolved last")
by = {c["key"]: c for c in cards}
check(by["code:ECM:P0456"]["status"] == "permanent" and by["code:ECM:P0456"]["importance"]["reason"], "permanent + reason")
# 2. clear/return counting
p = by["code:ECM:P0171"]
check(p["times_cleared"] == 1 and p["times_returned_after_clear"] == 1,
      f"cleared/returned {p['times_cleared']}/{p['times_returned_after_clear']}")
check(by["code:ECM:P0456"]["times_cleared"] == 0, "P0456 first seen after the clear: not counted")
check(all(c["evidence"]["status"] for c in cards), "status evidence ids present")
check(len(fb.group_by(fb.sort_by(cards, "importance"), "status")) >= 3, "group_by status")

# 3. mark_fixed -> verifying; undo retracts
fb.mark_fixed(VIN, "code:ECM:P0456", JOB, by="mech")
c = card("code:ECM:P0456")
check(c["status"] == "verifying" and c["verification"]["rule"].startswith("Proof: clean read after the EVAP monitor completes"),
      f"verifying + rule ({c['status']})")
check(bool(c["verification"]["needs"]), "verification lists what is still needed")
check(fb.mark_fixed(VIN, "code:ECM:P0456", JOB)["already"], "mark_fixed idempotent")
fb.undo_fixed(VIN, "code:ECM:P0456", JOB, by="mech")
j = jobs_mod.get(JOB)
check(any(a.get("retract_reason") == "undone by mechanic" for a in j["retracted_actions"]), "undo retracts with reason")
check(card("code:ECM:P0456")["status"] == "permanent", "undo restores status")

# 4. returned after fix
fb.mark_fixed(VIN, "code:ECM:P0456", JOB)
module("ECM", "2099-01-01T00:00:00", [("P0456", flags(testFailed=True, confirmedDTC=True))])
c = card("code:ECM:P0456")
check(c["status"] in ("active", "permanent") and c["returned_after_fix"] and c["returned_after_fix_count"] == 1,
      f"returned after fix flagged ({c['status']}, {c['returned_after_fix']})")

# 5. proven-fixed is computed from evidence
fb.mark_fixed(VIN, "code:ABS:C1234", JOB)
check(card("code:ABS:C1234")["status"] == "verifying", "C1234 verifying before evidence")
jobs_mod.add_action(JOB, "clear", "Cleared ABS", event_date="2099-01-01T01:00:00")
readiness("2099-01-01T02:00:00", True, 5)
module("ABS", "2099-01-01T03:00:00", [])
c = card("code:ABS:C1234")
check(c["status"] == "proven-fixed", f"proven-fixed after clean read ({c['status']}: {c['verification']})")

# 6. symptom resolve via note
fb.mark_fixed(VIN, f"symptom:{sid}", JOB, by="mech")
tagged = [n for n in notes_mod.load(VIN) if "resolved" in n["tags"] and sid in n["text"]]
check(card(f"symptom:{sid}")["status"] == "resolved" and tagged, "symptom resolved via tagged note")
fb.undo_fixed(VIN, f"symptom:{sid}", JOB)
check(card(f"symptom:{sid}")["status"] == "active" and not [n for n in notes_mod.load(VIN) if sid in n["text"]],
      "undo hides the note")

# 7. routes + partial
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from cuore.web import fault_board_routes  # noqa: E402

app = FastAPI()
app.state.settings = types.SimpleNamespace(token="")
app.include_router(fault_board_routes.router)
cl = TestClient(app)
r = cl.post(f"/v/{VIN}/fault-board/fixed", data={"fault_key": "code:BCM:B1000", "job_id": JOB,
                                                  "return_to": f"/v/{VIN}/job?sort=code"}, follow_redirects=False)
check(r.status_code == 303 and r.headers["location"].startswith(f"/v/{VIN}/job?sort=code&msg="),
      f"fixed redirects {r.status_code} {r.headers.get('location')}")
check(card("code:BCM:B1000")["status"] == "verifying", "POST fixed took effect")
r = cl.post(f"/v/{VIN}/fault-board/undo", data={"fault_key": "code:BCM:B1000", "return_to": "//evil.example/x"},
            follow_redirects=False)
check(r.status_code == 303 and r.headers["location"].startswith(f"/v/{VIN}/job"),
      f"off-site return_to refused: {r.headers.get('location')}")
r = cl.get(f"/api/vehicles/{VIN}/fault-board?sort=newest&group=related&job={JOB}")
check(r.status_code == 200 and r.json()["total"] >= 6 and r.json()["groups"], "JSON endpoint")

from jinja2 import Environment, FileSystemLoader  # noqa: E402
tpl = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parents[1] / "web" / "templates")), autoescape=True)
for g in ("none", "related", "status"):
    html = tpl.get_template("_fault_board.html").render(fb=fb.fault_board_context(VIN, JOB, "importance", g))
    check('class="fold fb-group"' in html and 'class="fold"' in html and ">Fixed<" in html
          and "Ordered by priority, then most recent" in html, f"partial renders ({g})")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
