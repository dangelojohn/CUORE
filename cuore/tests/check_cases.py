"""Checks for case memory: ``mes.cases`` (``case_from_job``, ``match``,
``prefill``) and its thin pass-throughs in ``cuore.services.cases_bridge``.

``CUORE_STATE_DIR`` is pointed at a fresh tempdir BEFORE anything cuore/mes
is imported, so this never touches the real state directory (which, as of
this change, carries one real seeded case for the project Stelvio -- see
``mes.cases.seed_default``). Every fixture job here is built directly
through ``mes.jobs``/``mes.tool_usage``, same as ``check_jobs_page.py``'s
fixtures, so each case is built from a real (if synthetic-for-the-test) job
record, never hand-written.

``cuore/api/cases.py`` is not registered on ``cuore.app.create_app`` (this
task's scope excludes ``app.py``), so wording/ranking checks go straight
through ``mes.cases`` and ``cuore.services.cases_bridge`` rather than HTTP --
same posture as the module itself being the one place every rule (code
overlap, "never proven" wording) actually lives.

Five checks:
  1. ``case_from_job`` builds a case from a fixture job with actions and a
     tool-usage review (codes, tools used, and a path all land).
  2. ``match`` ranks the case whose codes overlap the query first.
  3. ``prefill`` returns hypotheses, tools and pitfalls from the matched case.
  4. Every wording surface says "last Stelvio" (or the model name) and
     never "proven".
  5. A VIN that doesn't resolve to the Stelvio model gets no matches, even
     though Stelvio cases are on file.

Run:
    .venv/Scripts/python.exe cuore/tests/check_cases.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-cases-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore import bootstrap  # noqa: F401,E402 -- side effect: puts `mes` on sys.path
from cuore.services import cases_bridge  # noqa: E402

from mes import cases as cases_mod  # noqa: E402
from mes import jobs as jobs_mod  # noqa: E402
from mes import tool_usage as tool_usage_mod  # noqa: E402

VIN_A = "ZASFAKPN5J7B88115"  # the project Stelvio -- real WMI prefix
VIN_B = "ZASFAKPN5J7B00002"  # a second Stelvio (same WMI prefix), prior case
VIN_QUERY = "ZASFAKPN5J7B00003"  # a third Stelvio asking "has this happened before"
VIN_OTHER_MODEL = "ZN6AKPN5J7B00004"  # does not resolve to any model

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def build_fixture_job(vin: str, codes: list[str], *, outcome: str,
                      refuted_text: str = "ruled this out") -> str:
    """A real job, closed, with a code-bearing action, a refuted
    hypothesis and a tool-usage review with one wrong tool -- everything
    ``case_from_job`` is supposed to pick up."""
    job = jobs_mod.open(vin, technician="tester", complaint="CEL, EVAP codes")
    job_id = job["id"]
    hyp = jobs_mod.add_hypothesis(job_id, refuted_text, system="evap")
    jobs_mod.set_hypothesis(job_id, hyp["id"], status="refuted")
    jobs_mod.add_action(job_id, "test", "smoke tested recirc line",
                        ref={"kind": "code", "id": codes[0], "label": f"{codes[0]} present"})
    jobs_mod.add_action(job_id, "repair", "replaced purge valve")
    tool_usage_mod.add(vin, "evap_smoke_test", job_id=job_id, by="tester",
                       tools_used=[{"tool": "smoke_machine", "was_right": "yes"},
                                  {"tool": "wrong_gauge", "was_right": "no",
                                   "note": "wrong_gauge reads low, don't trust it"}],
                       would_buy=[{"name": "borescope", "why": "would have found it faster"}])
    jobs_mod.close(job_id, outcome, codes_returned=codes)
    return job_id


# --- 1. case_from_job builds from a fixture job with actions and tools -----

job_a_id = build_fixture_job(VIN_A, ["P0440"], outcome="fixed")
case_a = cases_mod.case_from_job(VIN_A, job_a_id)

check("case carries the code from the fixture job", "P0440" in case_a["codes"], str(case_a["codes"]))
check("case resolved the EVAP family", "evap" in case_a["families"], str(case_a["families"]))
check("case model resolved to stelvio", case_a["model"] == "stelvio", case_a["model"])
check("case path is non-empty (built from job actions)", len(case_a["path"]) > 0, str(case_a["path"]))
check("case tools.used carries the fixture's tool", "smoke_machine" in case_a["tools"]["used"],
     str(case_a["tools"]))
check("case tools.flagged_wrong carries the wrong one", "wrong_gauge" in case_a["tools"]["flagged_wrong"],
     str(case_a["tools"]))
check("case outcome is fixed", case_a["outcome"] == "fixed", case_a["outcome"])

recorded_a = cases_mod.record_case(VIN_A, job_a_id)
check("record_case persists the case", cases_mod.get(recorded_a["id"]) is not None)
again = cases_mod.record_case(VIN_A, job_a_id)
check("record_case is idempotent (no duplicate row)",
     len([r for r in cases_mod._raw_records() if r["id"] == recorded_a["id"]]) == 1)


# --- 2. match ranks a same-codes case first ---------------------------------

job_b_id = build_fixture_job(VIN_B, ["P0300"], outcome="not_fixed", refuted_text="misfire, not EVAP")
cases_mod.record_case(VIN_B, job_b_id)

matches = cases_mod.match(VIN_QUERY, ["P0440"])
check("match found both prior Stelvio cases", len(matches) >= 2, str([m["id"] for m in matches]))
check("the overlapping-codes case (P0440) ranks first",
     bool(matches) and matches[0]["id"] == recorded_a["id"], str(matches[:1]))
check("the non-overlapping case (P0300) ranks lower",
     [m["id"] for m in matches].index(recorded_a["id"]) <
     [m["id"] for m in matches].index(cases_mod.get(f"case-{job_b_id}")["id"]))
check("the top match carries a similarity score", isinstance(matches[0].get("similarity"), float),
     str(matches[0].get("similarity")))


# --- 3. prefill returns hypotheses + tools + pitfalls -----------------------

prefill = cases_mod.prefill(VIN_QUERY, ["P0440"])
check("prefill matched a case", prefill.get("matched_case") == recorded_a["id"], str(prefill))
check("prefill returned at least one hypothesis", len(prefill["hypotheses"]) > 0, str(prefill["hypotheses"]))
check("prefill hypothesis carries prior_final_status",
     prefill["hypotheses"] and "prior_final_status" in prefill["hypotheses"][0], str(prefill["hypotheses"]))
check("prefill returned tools to have ready", len(prefill["tools"]) > 0, str(prefill["tools"]))
check("prefill tool rows carry a have/not_available status",
     prefill["tools"] and "have" in prefill["tools"][0], str(prefill["tools"]))
check("prefill returned pitfalls", len(prefill["pitfalls"]) > 0, str(prefill["pitfalls"]))

bridge_prefill = cases_bridge.prefill(VIN_QUERY, ["P0440"])
check("cases_bridge.prefill agrees with mes.cases.prefill",
     bridge_prefill.get("matched_case") == prefill.get("matched_case"), str(bridge_prefill))


# --- 4. wording: "last Stelvio" / model name, never "proven" ---------------

blob = json.dumps(prefill).lower() + json.dumps(matches).lower()
check('wording names "stelvio" (the model)', "stelvio" in blob, blob[:200])
check('summary reads "on the last stelvio ..."',
     bool(matches) and "last stelvio" in matches[0]["what_to_expect"].lower(),
     matches[0].get("what_to_expect") if matches else "no matches")
check('the word "proven" never appears anywhere in the output', "proven" not in blob)


# --- 5. a different model's case is not matched -----------------------------

other_model_matches = cases_bridge.match(VIN_OTHER_MODEL, ["P0440"])
check("a VIN resolving to no known model gets no matches",
     other_model_matches["matches"] == [], str(other_model_matches))
check("...even though Stelvio cases with that exact code are on file",
     any("P0440" in c.get("codes", []) for c in cases_mod.load(model="stelvio")))
check('the word "cause" never appears anywhere in the output', "cause" not in blob)


# --- 6. close-out fields: confirmed hypothesis, tests, parts fitted,
#        verification state, outcome text -----------------------------------

VIN_D = "ZASFAKPN5J7B00007"  # a fourth Stelvio -- close-out fixture

job_d = jobs_mod.open(VIN_D, technician="tester", complaint="CEL, misfire")
job_d_id = job_d["id"]
hyp_d = jobs_mod.add_hypothesis(job_d_id, "purge valve stuck open", system="evap")
jobs_mod.set_hypothesis(job_d_id, hyp_d["id"], status="supported")
jobs_mod.add_evidence(job_d_id, hyp_d["id"], "for",
                      {"kind": "test", "id": "t1", "label": "purge valve bench test",
                       "result": "fail"})
jobs_mod.set_hypothesis(job_d_id, hyp_d["id"], status="confirmed")
jobs_mod.add_action(job_d_id, "part", "replaced purge valve",
                    ref={"kind": "dealer", "id": "p1", "label": "purge valve PN 12345"})
# close() with no readiness_at -- the readiness was never actually read
# off the car at release, so verification_state must say so.
jobs_mod.close(job_d_id, "fixed", codes_returned=[])
case_d = cases_mod.case_from_job(VIN_D, job_d_id)

check("confirmed_hypothesis carries the confirmed one, with its evidence",
     case_d["confirmed_hypothesis"] is not None
     and case_d["confirmed_hypothesis"]["text"] == "purge valve stuck open"
     and "purge valve bench test" in case_d["confirmed_hypothesis"]["evidence_summary"],
     str(case_d.get("confirmed_hypothesis")))
check("tests recorded carries the bench test with its result",
     any(t["text"] == "purge valve bench test" and t["result"] == "fail"
        for t in case_d["tests"]), str(case_d["tests"]))
check("parts_fitted carries the part action",
     any("purge valve" in p["text"] for p in case_d["parts_fitted"]), str(case_d["parts_fitted"]))
check("outcome_text reads a plain 'Fixed', never 'proven'/'cause'",
     case_d["outcome_text"] == "Fixed", case_d["outcome_text"])
check("a job whose readiness was never read off the car produces 'released unverified'",
     "released unverified" in case_d["verification_state"].lower(), case_d["verification_state"])

recorded_d1 = cases_bridge.record_case(VIN_D, job_d_id)
recorded_d2 = cases_bridge.record_case(VIN_D, job_d_id)
check("closing (recording) the same job twice yields one case id",
     recorded_d1["id"] == recorded_d2["id"]
     and len([r for r in cases_mod._raw_records() if r["id"] == recorded_d1["id"]]) == 1,
     str([recorded_d1["id"], recorded_d2["id"]]))

case_d_refuted = cases_mod.case_from_job(VIN_A, job_a_id)["refuted_hypotheses"]
check("refuted_hypotheses carries the ruled-out hypothesis text",
     any(h["text"] == "ruled this out" for h in case_d_refuted), str(case_d_refuted))


# --- 7. a real case outranks the synthetic seed, and the wording carries
#        the close date -----------------------------------------------------

VIN_SEED = "ZASFAKPN5J7B00008"   # carries only a synthetic seed case
VIN_E = "ZASFAKPN5J7B00009"      # a real, overlapping-codes case
cases_mod._append(cases_mod._synthetic_evap_case(VIN_SEED))
job_e_id = build_fixture_job(VIN_E, ["P0440"], outcome="fixed", refuted_text="not this either")
recorded_e = cases_bridge.record_case(VIN_E, job_e_id)

matches_e = cases_mod.match(VIN_QUERY, ["P0440"])
check("a real job-derived case ranks above the synthetic seed",
     bool(matches_e) and not matches_e[0].get("synthetic_from_logs"), str(matches_e[:1]))
check('wording carries "(closed <date>)"',
     bool(matches_e) and "(closed " in matches_e[0]["what_to_expect"], str(matches_e[:1]))


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(f"  FAIL: {f}")
sys.exit(1 if failures else 0)
