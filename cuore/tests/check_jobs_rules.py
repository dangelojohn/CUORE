"""Checks for the guided-diagnostics rules added to the Job workflow --
JOB_UX_FIXES_2026-10-08.md items #1 (confirm gate), #2 (evidence
add/remove/edit/delete), #3 (test results -> auto evidence), #4 (honest
step state), and #11 (suggestion dedupe/rank).

Same posture as ``cuore/tests/check_jobs_page.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported, and the real MES
corpus on this machine (the Stelvio, VIN below -- chronic EVAP codes) is the
fixture wherever real open-work/checklist data is needed.

Six checks:
  1. POSTing ``confirmed`` straight from ``open`` is refused: HTTP 409 with
     ``{"detail": ..., "next_test": ...}`` in the body.
  2. A passed test linked as evidence_for -> ``supported`` is allowed ->
     ``confirmed`` is allowed, with ``confirmed_by``/``confirmed_at``
     recorded from the ``by``/server time given.
  3. Unresolved evidence_against blocks confirm even with a passed test on
     file; resolving it then allows the confirm.
  4. Soft-delete sets ``deleted: true`` without erasing history; undelete
     clears it.
  5. Step 6 (Tests & inspections) reports ``not_started`` 0/N with no
     checklist results on file, and ``in_progress`` after exactly one.
  6. ``jobs_bridge.dedupe_suggestions`` reduces 8 suggestions that share one
     ``next_test`` to a single card listing all 8 codes.

Run:
    .venv/Scripts/python.exe cuore/tests/check_jobs_rules.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-jobsrules-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import dossier_bridge, flow_bridge, jobs_bridge, mes_bridge  # noqa: E402

from mes import jobs as jobs_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())


def _open_job_with_hypothesis(text: str) -> tuple[str, dict]:
    client.post(f"/v/{VIN}/job/open", data={"technician": "tester", "complaint": "EVAP"},
               follow_redirects=True)
    job = client.get(f"/api/vehicles/{VIN}/job").json()["job"]
    hyp = client.post(f"/api/jobs/{job['id']}/hypotheses",
                      json={"text": text, "system": "EVAP"}).json()
    return job["id"], hyp


# --- 1. open -> confirmed is refused ----------------------------------------

job1_id, hyp1 = _open_job_with_hypothesis("Cracked EVAP purge line at canister (test 1)")
resp1 = client.post(f"/api/jobs/{job1_id}/hypotheses/{hyp1['id']}/status",
                    json={"status": "confirmed"})
check("1a. open -> confirmed is refused with 409", resp1.status_code == 409,
     str(resp1.status_code))
body1 = resp1.json()
check("1b. the 409 body carries a top-level detail reason", bool(body1.get("detail")), str(body1))
check("1c. the 409 body carries a top-level next_test key (possibly '')",
     "next_test" in body1, str(body1))
view1 = client.get(f"/api/vehicles/{VIN}/job/{job1_id}").json()
hyp1_after = next(h for h in view1["job"]["hypotheses"] if h["id"] == hyp1["id"])
check("1d. the hypothesis's status never actually changed", hyp1_after["status"] == "open",
     str(hyp1_after))


# --- 2. pass test linked -> supported -> confirmed, by/at recorded ---------

job2_id, hyp2 = _open_job_with_hypothesis("Cracked EVAP purge line at canister (test 2)")
ev_resp = client.post(f"/api/jobs/{job2_id}/hypotheses/{hyp2['id']}/evidence", json={
    "action": "add", "side": "for",
    "ref": {"kind": "test", "id": "evap-smoke-1", "label": "Smoke test: pass", "result": "pass"},
})
check("2a. adding a passed-test evidence_for ref responds 200",
     ev_resp.status_code == 200, str(ev_resp.status_code))

supported_resp = client.post(f"/api/jobs/{job2_id}/hypotheses/{hyp2['id']}/status",
                             json={"status": "supported"})
check("2b. open -> supported is allowed", supported_resp.status_code == 200,
     str(supported_resp.status_code))

confirm_resp = client.post(f"/api/jobs/{job2_id}/hypotheses/{hyp2['id']}/status",
                           json={"status": "confirmed", "by": "tester-2"})
check("2c. supported -> confirmed is allowed once a passed test is linked",
     confirm_resp.status_code == 200, str(confirm_resp.text))
if confirm_resp.status_code == 200:
    confirmed_hyp = confirm_resp.json()
    check("2d. confirmed_by is recorded", confirmed_hyp.get("confirmed_by") == "tester-2",
         str(confirmed_hyp))
    check("2e. confirmed_at is recorded", bool(confirmed_hyp.get("confirmed_at")),
         str(confirmed_hyp))
    check("2f. status is now confirmed", confirmed_hyp.get("status") == "confirmed",
         str(confirmed_hyp))


# --- 3. unresolved evidence_against blocks confirm --------------------------

job3_id, hyp3 = _open_job_with_hypothesis("Cracked EVAP purge line at canister (test 3)")
client.post(f"/api/jobs/{job3_id}/hypotheses/{hyp3['id']}/evidence", json={
    "action": "add", "side": "for",
    "ref": {"kind": "test", "id": "evap-smoke-2", "label": "Smoke test: pass", "result": "pass"},
})
against_resp = client.post(f"/api/jobs/{job3_id}/hypotheses/{hyp3['id']}/evidence", json={
    "action": "add", "side": "against",
    "ref": {"kind": "dealer", "id": "slvt-1", "label": "SLVT pass -- contradicts hardware fault"},
})
check("3a. adding an evidence_against ref responds 200",
     against_resp.status_code == 200, str(against_resp.status_code))
client.post(f"/api/jobs/{job3_id}/hypotheses/{hyp3['id']}/status", json={"status": "supported"})

blocked_resp = client.post(f"/api/jobs/{job3_id}/hypotheses/{hyp3['id']}/status",
                           json={"status": "confirmed"})
check("3b. confirming with unresolved evidence_against is refused (409)",
     blocked_resp.status_code == 409, str(blocked_resp.status_code))
check("3c. the refusal names 'unresolved'",
     "unresolved" in blocked_resp.json().get("detail", "").lower(),
     str(blocked_resp.json()))

resolve_resp = client.post(f"/api/jobs/{job3_id}/hypotheses/{hyp3['id']}/evidence", json={
    "action": "resolve", "ref_id": "slvt-1", "resolved": True,
})
check("3d. resolving the evidence_against ref responds 200",
     resolve_resp.status_code == 200, str(resolve_resp.status_code))

confirm3_resp = client.post(f"/api/jobs/{job3_id}/hypotheses/{hyp3['id']}/status",
                            json={"status": "confirmed"})
check("3e. confirming now succeeds once the evidence_against is resolved",
     confirm3_resp.status_code == 200, str(confirm3_resp.text))


# --- 4. soft delete + undelete ----------------------------------------------

job4_id, hyp4 = _open_job_with_hypothesis("A hypothesis to delete and undelete")
del_resp = client.delete(f"/api/jobs/{job4_id}/hypotheses/{hyp4['id']}")
check("4a. deleting a hypothesis responds 200", del_resp.status_code == 200, str(del_resp.text))

job4_after_delete = jobs_mod.get(job4_id)
hyp4_deleted = next(h for h in job4_after_delete["hypotheses"] if h["id"] == hyp4["id"])
check("4b. deleted is true, text is still on file (soft delete, not erased)",
     hyp4_deleted["deleted"] is True and hyp4_deleted["text"] == hyp4["text"],
     str(hyp4_deleted))

undel_resp = client.post(f"/api/jobs/{job4_id}/hypotheses/{hyp4['id']}/undelete")
check("4c. undeleting responds 200", undel_resp.status_code == 200, str(undel_resp.text))
job4_after_undelete = jobs_mod.get(job4_id)
hyp4_undeleted = next(h for h in job4_after_undelete["hypotheses"] if h["id"] == hyp4["id"])
check("4d. deleted is false again after undelete", hyp4_undeleted["deleted"] is False,
     str(hyp4_undeleted))


# --- 5. step 6 state: not_started 0/N, then in_progress after one ----------

try:
    dossier5 = mes_bridge.workup(vin=VIN)
    step_ids = dossier_bridge.checklist_step_ids(VIN, dossier5)
except Exception as exc:  # noqa: BLE001
    step_ids = set()
    check("5. real-corpus checklist steps resolved for step 6's progress", False, str(exc))

if step_ids:
    state5 = flow_bridge.flow_state(VIN)
    step6 = next(s for s in state5["steps"] if s["n"] == 6)
    check("5a. step 6 is not_started with 0 results recorded",
         step6["state"] == "not_started" and step6["progress"]["done"] == 0,
         str(step6))
    check("5b. step 6's progress total matches the real checklist step count",
         step6["progress"]["total"] == len(step_ids), str(step6))

    one_step = sorted(step_ids)[0]
    result_resp = client.post(f"/api/vehicles/{VIN}/checklist/{one_step}/result",
                              json={"result": "pass", "reason": "clean"})
    check("5c. recording one test result responds 200",
         result_resp.status_code == 200, str(result_resp.text))

    state5b = flow_bridge.flow_state(VIN)
    step6b = next(s for s in state5b["steps"] if s["n"] == 6)
    if len(step_ids) > 1:
        check("5d. step 6 is in_progress after exactly one result, with >1 step",
             step6b["state"] == "in_progress" and step6b["progress"]["done"] == 1,
             str(step6b))
    else:
        check("5d. step 6 is complete after its only result",
             step6b["state"] == "complete" and step6b["progress"]["done"] == 1,
             str(step6b))
else:
    check("5. skipped: no real checklist steps resolved for this VIN", False,
         "see check above")


# --- 6. suggestion dedupe reduces 8 duplicates to 1 -------------------------

codes = ["B1029", "B102E", "B1040", "B1176", "B1181", "B1182", "B1183", "B1184"]
dupe_suggestions = [
    {"text": f"{code}: upstream network check", "system": "network",
     "evidence_for": [{"kind": "code", "id": code, "label": f"{code} on file"}],
     "evidence_against": [],
     "next_test": "Check F82 fuse/BCM supply and the connectors/grounds this "
                  "fault tree cites before chasing individual codes."}
    for code in codes
]
merged = jobs_bridge.dedupe_suggestions(dupe_suggestions)
check("6a. 8 duplicate-next_test suggestions collapse to 1",
     len(merged) == 1, str(len(merged)))
if merged:
    card = merged[0]
    check("6b. the merged card lists all 8 codes",
         all(code in card.get("codes", []) for code in codes), str(card))
    check("6c. the merged card's text names the codes",
         all(code in card.get("text", "") for code in codes), card.get("text"))
    check("6d. the merged card keeps the shared evidence_for (8 code refs)",
         len(card.get("evidence_for", [])) == len(codes), str(card.get("evidence_for")))


# --- summary ------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    for f in failures:
        print("FAIL:", f)
    sys.exit(1)
print("OK")
