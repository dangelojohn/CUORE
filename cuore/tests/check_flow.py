"""Checks for the 12-step mechanic flow: ``cuore.services.flow_bridge`` and
``cuore/api/flow.py``.

Same posture as the other ``check_*`` scripts: ``CUORE_STATE_DIR`` is pointed
at a throwaway directory BEFORE anything from ``mes``/``cuore`` is imported,
so this never touches the real corpus. Five checks:

  1. No visit on file -> current step 1, href "/start".
  2. After intake + a symptom report -> current step 3 or 4 (verdict is not
     independently knowable; it counts done only once scan & codes does).
  3. After intake, a symptom, a car-sourced observation, a hypothesis
     confirmed, and part + repair actions -> current step 10, with the
     readiness blocker named in its "why".
  4. A mocked VERIFIED_CLEAN verdict plus a full release -> current step 12.
  5. Every step's href starts with "/", checked through the live
     GET /api/vehicles/{vin}/flow route (``cuore/api/flow.py`` mounted on a
     throwaway app, since ``cuore/app.py`` itself is left untouched here).

Run:
    .venv/Scripts/python.exe cuore/tests/check_flow.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
from unittest import mock

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-flow-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401
from cuore.config import Settings  # noqa: E402
from cuore.services import flow_bridge, shop_bridge  # noqa: E402
from cuore.api import flow as flow_api  # noqa: E402

from mes import jobs as jobs_mod  # noqa: E402
from mes import shop as shop_mod  # noqa: E402
from mes import symptoms as symptoms_mod  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.live import checklists as checklist_store  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- check 1: no visit -------------------------------------------------------

VIN_EMPTY = "ZFLOWTESTEMPTY0001"
state = flow_bridge.flow_state(VIN_EMPTY)
check("1a. no visit -> current step 1", state["current"] == 1, str(state["current"]))
check("1b. no visit -> step 1 href is /start",
     next(s["href"] for s in state["steps"] if s["n"] == 1) == "/start",
     next(s["href"] for s in state["steps"] if s["n"] == 1))
check("1c. no visit -> visit is None", state["visit"] is None)

# --- check 2: intake + symptom -----------------------------------------------

VIN_2 = "ZFLOWTESTINTAKE002"
visit2 = shop_mod.intake(VIN_2, complaint="check engine light")
symptoms_mod.add(VIN_2, visit2["in_at"], reporter="driver", text="light on")
state2 = flow_bridge.flow_state(VIN_2)
check("2. intake + symptom -> current step 3 or 4", state2["current"] in (3, 4),
     str(state2["current"]))

# --- check 3: through a repair action ---------------------------------------
# VIN_3 is fictional -- no real MES logs ever back it, so its dossier verdict
# would genuinely be NO_DATA (step 3 rightly not done then). A verdict is
# mocked here, same as check 4 below, purely so this synthetic VIN can stand
# in for a car whose corpus verdict says UNVERIFIED_REPAIR -- the actual
# step-3/NO_DATA rule itself is covered on the real VIN in check 6.

VIN_3 = "ZFLOWTESTREPAIR003"
visit3 = shop_mod.intake(VIN_3, complaint="EVAP codes")
symptoms_mod.add(VIN_3, visit3["in_at"], reporter="driver", text="smells of fuel")
live_store.record_observation("scan", {"dtcs": ["P0455"]}, vin=VIN_3,
                              stream="serial COM3@115200")
job3_id = visit3["job_id"]
hyp3 = jobs_mod.add_hypothesis(job3_id, "EVAP: ESIM signal path", system="EVAP")
# A hypothesis must be supported by a passed/failed test before it can be
# confirmed (mes.jobs.RuleViolation, JOB_UX_FIXES_2026-10-08.md #1) -- a
# direct open -> confirmed jump with no evidence is refused, not allowed.
jobs_mod.add_evidence(job3_id, hyp3["id"], "for",
                      {"kind": "test", "id": "smoke-1",
                       "label": "smoke test: pass", "result": "pass"})
jobs_mod.set_hypothesis(job3_id, hyp3["id"], status="supported")
jobs_mod.set_hypothesis(job3_id, hyp3["id"], status="confirmed")
jobs_mod.add_action(job3_id, "part", "ordered ESIM connector")
jobs_mod.add_action(job3_id, "repair", "replaced ESIM connector")
# Step 6 (Tests & inspections) now counts checklist rows with a *result*
# over every row this VIN's open-work exposes (JOB_UX_FIXES_2026-10-08.md
# #4) -- VIN_3 is fictional with no real open-work, so checklist_step_ids
# is mocked to name one real row, and that row is given a passed result,
# the same way a real smoke test would be recorded on step 6.
checklist_store.set_result(VIN_3, "evap-smoke-1", "pass", reason="clean")
fake_view3 = {"verdict": {"state": "UNVERIFIED_REPAIR",
                         "summary": "P0455 cleared 1 Oct; monitors have not re-run. "
                                    "Not proof of repair."},
             "open_work": [], "codes": [], "attempted": []}
with mock.patch.object(flow_bridge.dossier_bridge, "build_view", return_value=fake_view3), \
     mock.patch.object(flow_bridge.dossier_bridge, "checklist_step_ids",
                       return_value={"evap-smoke-1"}):
    state3 = flow_bridge.flow_state(VIN_3)
check("3a. through a repair action -> current step 10", state3["current"] == 10,
     str(state3["current"]))
current_step3 = next(s for s in state3["steps"] if s["n"] == 10)
check("3b. step 10's why names the readiness blocker",
     "readiness" in current_step3["why"].lower(), current_step3["why"])

# --- check 4: VERIFIED_CLEAN + a full release --------------------------------

VIN_4 = "ZFLOWTESTRELEASE004"
visit4 = shop_mod.intake(VIN_4, complaint="EVAP codes")
symptoms_mod.add(VIN_4, visit4["in_at"], reporter="driver", text="smells of fuel")
live_store.record_observation("scan", {"dtcs": ["P0455"]}, vin=VIN_4,
                              stream="serial COM3@115200")
job4_id = visit4["job_id"]
hyp4 = jobs_mod.add_hypothesis(job4_id, "EVAP: ESIM signal path", system="EVAP")
jobs_mod.add_evidence(job4_id, hyp4["id"], "for",
                      {"kind": "test", "id": "smoke-1",
                       "label": "smoke test: pass", "result": "pass"})
jobs_mod.set_hypothesis(job4_id, hyp4["id"], status="supported")
jobs_mod.set_hypothesis(job4_id, hyp4["id"], status="confirmed")
jobs_mod.add_action(job4_id, "part", "ordered ESIM connector")
jobs_mod.add_action(job4_id, "repair", "replaced ESIM connector")
checklist_store.set_result(VIN_4, "evap-smoke-1", "pass", reason="clean")
shop_mod.release(visit4["id"], {
    "verified": True, "report_printed": True, "labels_printed": True,
    "parts_logged": True, "tools_reviewed": True, "notes": "fixed",
})
fake_view = {"verdict": {"state": "VERIFIED_CLEAN", "label": "Verified clean"},
            "open_work": [], "codes": [], "attempted": []}
with mock.patch.object(flow_bridge.dossier_bridge, "build_view", return_value=fake_view), \
     mock.patch.object(flow_bridge.dossier_bridge, "checklist_step_ids",
                       return_value={"evap-smoke-1"}):
    state4 = flow_bridge.flow_state(VIN_4)
check("4. VERIFIED_CLEAN + full release -> current step 12", state4["current"] == 12,
     str(state4["current"]))

# --- check 5: hrefs, through the live API route ------------------------------

app = FastAPI()
app.state.settings = Settings()
app.include_router(flow_api.router, prefix="/api")
client = TestClient(app)

resp = client.get(f"/api/vehicles/{VIN_3}/flow")
check("5a. GET /api/vehicles/{vin}/flow -> 200", resp.status_code == 200, str(resp.status_code))
body = resp.json()
bad_hrefs = [s["href"] for s in body.get("steps", []) if not s["href"].startswith("/")]
check("5b. every step href starts with /", not bad_hrefs, str(bad_hrefs))
check("5c. current_vehicle() returns a VIN string or None",
     flow_bridge.current_vehicle() is None or isinstance(flow_bridge.current_vehicle(), str))

# --- check 6: real VIN -- pre-intake MES evidence still counts, and the ----
# visit gets a real vehicle name even though /start was never told one.

VIN_STELVIO = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic EVAP codes
visit_stelvio = shop_bridge.intake(VIN_STELVIO, complaint="EVAP check")
symptoms_mod.add(VIN_STELVIO, visit_stelvio["in_at"], reporter="driver",
                 text="smells of fuel")
state_stelvio = flow_bridge.flow_state(VIN_STELVIO)
step3 = next(s for s in state_stelvio["steps"] if s["n"] == 3)
step4 = next(s for s in state_stelvio["steps"] if s["n"] == 4)

check("6a. real VIN, pre-intake MES logs -> step 3 (verdict) is done",
     step3["status"] == "done", str(step3))
check("6b. real VIN, pre-intake MES logs -> step 4 (scan & codes) is done",
     step4["status"] == "done", str(step4))
check("6c. step 3's why names the verdict, never 'verdict not computed'",
     "not computed" not in step3["why"].lower(), step3["why"])
check("6d. step 4's why names a date or says codes were read since intake",
     "since intake" in step4["why"].lower()
     or bool(re.search(r"\d{1,2} [A-Za-z]{3}", step4["why"])),
     step4["why"])

check("6e. the visit's vehicle name resolves to something containing "
     "'Stelvio', never left blank or '(unnamed vehicle)'",
     bool(visit_stelvio.get("vehicle")) and "stelvio" in visit_stelvio["vehicle"].lower(),
     str(visit_stelvio.get("vehicle")))

# --- summary ------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    for f in failures:
        print("FAIL:", f)
    sys.exit(1)
print("OK")
