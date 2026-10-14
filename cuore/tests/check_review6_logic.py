"""Checks for EXTERNAL_REVIEW_6_2026-10-14.md's LOGIC items (1-5):

  1. One data date -- a live read is a scan session: "returned -- erased
     and set again" for P0440/P0455, "data through" uses the newest live
     read, a live-only code (U1736) joins the Codes list, and the KOEO
     "MES running" precondition agrees with the Scanner strip.
  2. The fuel gate: PID $2F first, else the newest freeze frame, always
     timestamped/sourced; a stale reading warns, it does not block.
  3. Mode $06 FAIL text names whichever bound (min/max) was exceeded.
  4. The evidence picker's data: recorded test results (step 6 + Tests)
     exposed for the picker, and the step-6 "create a hypothesis inline"
     POST path.
  5. Knowledge: the Body group splits comms-type codes from mechanical
     ones, C104B gets a brake-hydraulic step, TSB 9100471 is wired to the
     EVAP codes it actually covers, and a seen-once code past 180 days is
     left out of open work.

Same posture as ``cuore/tests/check_dossier_view.py``/``check_jobs_rules.py``:
``CUORE_STATE_DIR`` is a throwaway directory, the real MES log corpus on this
machine (VIN below) is the fixture for everything from-log, and the real
``observations.jsonl``'s own 2026-10-13 lines (read-only; never modified) are
copied into that throwaway state dir for everything from-car -- the exact
scenario the review names: P0440/P0455 cleared 2026-10-08 09:20 by MES, read
back stored/active from the car 2026-10-13 20:02-20:24.

Run:
    .venv/Scripts/python.exe cuore/tests/check_review6_logic.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-review6-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import checklists as checklist_store  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.services import bench_bridge, dossier_bridge, jobs_bridge, mes_bridge  # noqa: E402

from mes import faulttree, knowledge, mechanic_tests, symptoms as symptoms_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, cleared 2026-10-08 09:20

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


# ===========================================================================
# From-car fixture: the real observations.jsonl's own 2026-10-13 lines,
# copied (never modified) into this test's own throwaway state dir.
# ===========================================================================

_REAL_OBSERVATIONS = Path(r"C:\ProgramData\cuore\observations.jsonl")
if _REAL_OBSERVATIONS.exists():
    _lines = [ln for ln in _REAL_OBSERVATIONS.read_text(encoding="utf-8").splitlines()
             if '"2026-10-13' in ln]
else:
    _lines = []
if _lines:
    (Path(os.environ["CUORE_STATE_DIR"]) / "observations.jsonl").write_text(
        "\n".join(_lines) + "\n", encoding="utf-8")
HAVE_REAL_OBS = bool(_lines)
print(f"({len(_lines)} real 2026-10-13 observation lines loaded)" if HAVE_REAL_OBS
     else "(no real observations.jsonl on this machine -- live-read checks skipped)")


client = TestClient(create_app())


# ===========================================================================
# 3. Mode $06: FAIL text names whichever bound was exceeded
# ===========================================================================

label = dossier_bridge._mode06_fail_label(
    "3C", 'EVAP 0.020" leak', 6096, "ms", 0, 6000, "2026-10-13")
check("3a. a max-limit FAIL names 'limit max', not 'limit min'",
     "limit max 6000" in label and "vs min" not in label, label)
check("3b. the FAIL text still carries the value and the verdict", "6096" in label and
     "FAIL" in label, label)

from mes import scan_health  # noqa: E402

reading = scan_health.mode06_reading({"mid_name": "EVAP 0.020\" leak", "mid": "3C",
                                      "value": 6096, "min": 0, "max": 6000,
                                      "passed": False})
check("3c. mes.scan_health's own text matches dossier_bridge's (same wording)",
     "limit max 6000" in reading and reading.endswith("FAIL"), reading)

min_label = dossier_bridge._mode06_fail_label("3A", "EVAP large-leak test", 2, "mV",
                                              10, 65535, "2026-10-13")
check("3d. a sentinel-max (no real upper bound) test names 'limit min'",
     "limit min 10" in min_label, min_label)


# ===========================================================================
# 1. One data date + live reads as scan sessions (real corpus + real 13 Oct
#    observations)
# ===========================================================================

dossier = mes_bridge.workup(vin=VIN)
view = dossier_bridge.build_view(VIN, dossier, None)

if HAVE_REAL_OBS:
    check("1a. identity.last_log is bumped to the newest live read (2026-10-13)",
         (dossier["identity"].get("last_log") or "").startswith("2026-10-13"),
         str(dossier["identity"].get("last_log")))

    codes_by_base = {r["code"]: r for r in view["codes"]}
    # P0455 is one of the four codes the 2026-10-08 09:20 MES clear actually
    # cleared (``clear_assessment.codes_cleared``) -- and the car itself
    # reported it stored/active again at 2026-10-13 20:02-20:24, after that
    # clear. That is exactly "returned -- erased and set again".
    p0455 = codes_by_base.get("P0455")
    check("1b. P0455 is ACTIVE (read back from the car after the MES clear)",
         bool(p0455) and p0455["status"] == "ACTIVE", str(p0455))
    check("1c. P0455's status_detail says 'returned -- erased ... set again ...'",
         bool(p0455) and "returned --" in (p0455.get("status_detail") or "")
         and "erased" in (p0455.get("status_detail") or "")
         and "set again" in (p0455.get("status_detail") or ""), str(p0455))

    p0440 = codes_by_base.get("P0440")
    check("1d. P0440 is ACTIVE too (the car itself reports it now)",
         bool(p0440) and p0440["status"] == "ACTIVE", str(p0440))

    check("1e. step 4 (Codes) and the Verdict agree: both say active now",
         view["verdict"]["state"] == "ACTIVE_FAULTS"
         and p0455 is not None and p0455["status"] == "ACTIVE",
         str((view["verdict"]["state"], p0455)))

    u1736 = codes_by_base.get("U1736")
    check("1f. U1736 (read live, never logged to a file) is on the Codes list",
         u1736 is not None and u1736["bucket"] == "live_only", str(u1736))

    # 5a. Body group split: B1040 (RFHUB, FTB 64 -- a comms code per this
    # car's own 2026-10-13 module sweep) and B1176 (BCM, FTB 97 -- a real
    # mechanical window-regulator fault) must not land on the same card.
    b1040_card = next((c for c in view["open_work"] if "B1040" in c.get("codes", [])), None)
    b1176_card = next((c for c in view["open_work"] if "B1176" in c.get("codes", [])), None)
    check("5a1. B1040 (comms FTB) is grouped as body_comms",
         bool(b1040_card) and b1040_card["family"] == "body_comms", str(b1040_card))
    check("5a2. B1176 (mechanical FTB) is grouped as plain body, not body_comms",
         bool(b1176_card) and b1176_card["family"] == "body", str(b1176_card))
    check("5a3. B1040 and B1176 are on two different cards",
         bool(b1040_card) and bool(b1176_card) and b1040_card is not b1176_card,
         str((b1040_card, b1176_card)))
else:
    check("1/5a. skipped (no real observations.jsonl on this machine)", True)


# ===========================================================================
# 2. Fuel gate: PID $2F first, else freeze frame, always timestamped, and a
#    stale reading warns rather than blocks.
# ===========================================================================

_stale_ff = [{"code": "P0455-00", "key": [{"name": "Fuel level", "value": "93.73 %",
                                          "flag": "above 85 %: EVAP monitor could not run"}],
             "timestamp": "2026-09-25 12:00:00"}]

status_stale = dossier_bridge.fuel_status(_stale_ff, vin="NO-SUCH-VIN-AT-ALL",
                                          readiness_at="2026-10-13 20:03:00")
check("2a. the gate carries its own timestamp and source",
     status_stale["at"] == "2026-09-25 12:00:00" and "freeze frame" in (status_stale["source"] or ""),
     str(status_stale))
check("2b. a reading older than the newest readiness read is flagged stale",
     status_stale["stale"] is True, str(status_stale))

status_fresh = dossier_bridge.fuel_status(_stale_ff, vin="NO-SUCH-VIN-AT-ALL",
                                          readiness_at="2026-09-01 00:00:00")
check("2c. the same reading is NOT stale against an older readiness read",
     status_fresh["stale"] is False, str(status_fresh))

next_action, blocker, _ = dossier_bridge._verdict_next_action(
    "NO-SUCH-VIN-AT-ALL", {"state": "UNVERIFIED_REPAIR", "readiness": {"at": "2026-10-13 20:03:00"}},
    [], _stale_ff, None)
check("2d. a stale fuel reading warns ('verify fuel reading'), it does not hard-block",
     blocker == "verify fuel reading", str((next_action, blocker)))
check("2e. the warning sentence names the date and tells the mechanic to verify",
     "verify" in next_action.lower() and "2026-09-25" in next_action, next_action)

# A live PID $2F read, newer than the freeze frame, takes priority over it.
live_store.record_observation(
    "pids_snapshot", {"by_ecu": {"ECM": {"2F": {"name": "fuel_level", "value": 20.8, "unit": "%"}}}},
    vin=VIN, stream="serial COM3@115200")
status_live = dossier_bridge.fuel_status([], vin=VIN)
check("2f. a live PID $2F read is used over an (absent) freeze frame, with its own source",
     status_live["level"] == 20.8 and status_live["source"] == "PID $2F, read from the car",
     str(status_live))
check("2g. 20.8% is inside the 15-85% EVAP window",
     status_live["in_window"] is True, str(status_live))


# ===========================================================================
# 5. Knowledge: C104B brake-hydraulic step, TSB 9100471 wired to EVAP codes,
#    stale single-session demotion.
# ===========================================================================

c104b_tree = faulttree.tree_for("C104B")
check("5b1. C104B's tree leads with a brake fluid / hydraulic leak inspection",
     any("brake fluid" in s.title.lower() or "hydraulic leak" in s.title.lower()
         for s in c104b_tree.steps),
     str([s.title for s in c104b_tree.steps]))
check("5b2. that step cites the real mechanic_tests brake hydraulic test",
     any("brake_hydraulic_pressure_bleed" in s.source for s in c104b_tree.steps),
     str([s.source for s in c104b_tree.steps]))
check("5b3. mes.mechanic_tests actually has that test",
     mechanic_tests.test("brake_hydraulic_pressure_bleed") is not None)

p0455_bulletins = {b.number for b in knowledge.tsb_for("P0455")}
check("5d. TSB 9100471 (flooded canister) is wired to the EVAP codes it covers",
     "9100471" in p0455_bulletins, str(p0455_bulletins))

_old_dossier = {"history": {
    "chronic": [], "returned_after_clear": [],
    "seen_once": [
        {"dtc": "P1234-00", "last_seen": "2025-01-01 00:00:00"},  # > 180 days old
        {"dtc": "P5678-00", "last_seen": "2026-10-01 00:00:00"},  # recent
    ],
}}
_stale_codes = dossier_bridge._history_codes(_old_dossier)
check("5e1. a single-session code last seen > 180 days ago is left out of open work",
     "P1234" not in _stale_codes, str(_stale_codes))
check("5e2. a recent single-session code is still included",
     "P5678" in _stale_codes, str(_stale_codes))

_chronic_old_dossier = {"history": {
    "chronic": [{"dtc": "P9999-00", "last_seen": "2024-01-01 00:00:00"}],
    "returned_after_clear": [], "seen_once": [],
}}
check("5e3. a chronic code is never demoted by age alone",
     "P9999" in dossier_bridge._history_codes(_chronic_old_dossier))


# ===========================================================================
# 1g. Bench: the KOEO "MES running" precondition agrees with the Scanner
#     label (same mes_state, same wording).
# ===========================================================================

live_not_running = {"mes_state": "not_running", "port": "COM3", "lock_holder": None}
preconds = bench_bridge._preconditions("run the KOEO actuator test", live_not_running, False)
check("1g1. the Scanner label for a not-running MES is 'Not running'",
     bench_bridge.scanner_label(live_not_running) == "Not running",
     bench_bridge.scanner_label(live_not_running))
check("1g2. the KOEO precondition's label matches that same wording",
     preconds and preconds[0]["label"] == "MES not running", str(preconds))
check("1g3. that precondition is correctly unmet (MES is not running)",
     preconds and preconds[0]["ok"] is False, str(preconds))

live_connected = {"mes_state": "connected", "port": "COM3", "lock_holder": "MultiEcuScan"}
preconds_ok = bench_bridge._preconditions("run the KOEO actuator test", live_connected, False)
check("1g4. when MES is connected, the precondition label says so and is met",
     preconds_ok and preconds_ok[0]["label"] == "MES connected" and preconds_ok[0]["ok"] is True,
     str(preconds_ok))


# ===========================================================================
# 4. Evidence picker data + step 6 "create a hypothesis inline"
# ===========================================================================

evap_card = next((c for c in view["open_work"] if c["family"] == "EVAP"), None)
step_id = evap_card["steps"][0]["id"] if evap_card else None
check("4a. this VIN has a real EVAP checklist step to record a result against",
     step_id is not None, str(evap_card))

if step_id:
    checklist_store.set_result(VIN, step_id, "fail", value=6096, unit="ms", by="tester")
    view2 = dossier_bridge.build_view(VIN, mes_bridge.workup(vin=VIN), None)
    candidates = jobs_bridge.evidence_candidates(VIN, view2)
    rows = candidates["test_results"]
    recorded = next((r for r in rows if r["step_id"] == step_id), None)
    check("4b. the recorded step-6 result is offered as an evidence candidate",
         recorded is not None, str(rows))
    check("4c. it carries a ready-to-POST kind=test ref",
         bool(recorded) and recorded["ref"]["kind"] == "test"
         and recorded["ref"]["result"] == "fail", str(recorded))
    check("4d. it is not yet linked to any hypothesis",
         bool(recorded) and recorded["linked_hypothesis_id"] is None, str(recorded))

    flagged_in_evidence = any(
        any(k.get("flag") for k in f.get("key") or [])
        for f in candidates["freeze_frames"])
    check("4f. no condition-flagged freeze frame leaks into the evidence group",
         not flagged_in_evidence, str(candidates["freeze_frames"]))

    # Step-6 "pick OR create a hypothesis inline" -- jobs_bridge half.
    job = jobs_bridge.open_job(VIN, technician="tester", complaint="")
    new_hyp = jobs_bridge.add_test_evidence_new_hypothesis(
        VIN, "EVAP: created inline from a test result", step_id,
        "Smoke test: fail", "fail", job_id=job["id"])
    check("4g. add_test_evidence_new_hypothesis creates a real hypothesis",
         bool(new_hyp) and new_hyp.get("text") == "EVAP: created inline from a test result",
         str(new_hyp))
    job_after = jobs_bridge.get_job(job["id"]) if new_hyp else None
    hyp_after = next((h for h in (job_after or {}).get("hypotheses", [])
                      if h["id"] == new_hyp["id"]), None) if new_hyp else None
    check("4h. the test result was attached to the new hypothesis as evidence",
         bool(hyp_after) and any(e.get("kind") == "test" and e.get("result") == "fail"
                                 for e in hyp_after.get("evidence_for", [])),
         str(hyp_after))

    # Step-6 "pick OR create" -- the API half (hypothesis_text, no
    # hypothesis_id): the checklist result POST creates AND links in one
    # request.
    job2 = jobs_bridge.open_job(VIN, technician="tester", complaint="")
    api_resp = client.post(
        f"/api/vehicles/{VIN}/checklist/{step_id}/result",
        json={"result": "pass", "hypothesis_text": "EVAP: created via the API",
             "hypothesis_system": "EVAP", "supports": "for"})
    check("4i. the create-and-link POST responds 200", api_resp.status_code == 200,
         api_resp.text)
    body = api_resp.json()
    check("4j. the response carries the newly-created hypothesis",
         bool(body.get("hypothesis", {}).get("id")), str(body))
    if body.get("hypothesis", {}).get("id"):
        job2_view = client.get(f"/api/vehicles/{VIN}/job/{job2['id']}").json()
        hyp2 = next((h for h in job2_view["job"]["hypotheses"]
                    if h["id"] == body["hypothesis"]["id"]), None)
        check("4k. that hypothesis carries the test's own pass evidence",
             bool(hyp2) and any(e.get("kind") == "test" and e.get("result") == "pass"
                                for e in hyp2.get("evidence_for", [])), str(hyp2))


# ===========================================================================
# 1d. Step 1's complaint falls back to the symptom log when empty.
# ===========================================================================

vin_for_symptom = VIN
job3 = jobs_bridge.open_job(vin_for_symptom, technician="tester", complaint="")
symptoms_mod.add(vin_for_symptom, "2026-10-14", reporter="driver",
                 text="Strong fuel smell after fill-up; pump nozzle clicks off early.")
view3 = jobs_bridge.build_job_view(vin_for_symptom, job3["id"])
check("1d1. an empty job complaint falls back to the newest symptom report",
     view3["job"]["complaint"] == "Strong fuel smell after fill-up; pump nozzle clicks off early.",
     str(view3["job"].get("complaint")))

job4 = jobs_bridge.open_job(vin_for_symptom, technician="tester", complaint="Typed complaint")
view4 = jobs_bridge.build_job_view(vin_for_symptom, job4["id"])
check("1d2. a complaint the mechanic actually typed is left alone",
     view4["job"]["complaint"] == "Typed complaint", str(view4["job"].get("complaint")))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
