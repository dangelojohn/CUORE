"""Checks for the Tests surface (``/v/{vin}/tests``, ``/api/tests/*``).

Same posture as ``cuore/tests/check_jobs_rules.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported, and the real MES
corpus on this machine (the Stelvio, VIN below -- chronic EVAP codes) is the
fixture wherever real open-work/code data is needed. Against the real
FastAPI app, via TestClient -- no Edge/CDP needed for this page.

Four groups of checks:
  1. The mechanic-test catalogue (``mes.mechanic_tests``) has at least 30
     tests; every ``pass_criteria`` row's confidence is one of the allowed
     CONFIDENCE_LEVELS, and no row pairs a numeric ``spec`` with
     ``UNKNOWN`` confidence (never invent a number).
  2. ``GET /v/{vin}/tests`` responds 200, carries the "Tests" tab link and
     a PASS/FAIL button pair for every catalogue test.
  3. ``POST /api/tests/{vin}/{test_id}/result`` with ``result="fail"``
     responds 200, the page then shows that test's row as FAIL, and the
     result is on file in ``cuore.live.checklists`` under
     ``step_id = "test:<test_id>"``; an invalid ``result`` value responds
     400.
  4. No regression: ``check_jobs_rules.py`` and ``check_live_dashboard_page.py``
     both still pass, run as subprocesses against this same venv.

Run:
    .venv/Scripts/python.exe cuore/tests/check_tests_page.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-tests-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import checklists as checklist_store  # noqa: E402

from mes import mechanic_tests  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

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
# 1. the catalogue itself
# ===========================================================================

print("=== catalogue ===")
catalog = mechanic_tests.all_tests()
check("catalogue has at least 30 tests", len(catalog) >= 30, str(len(catalog)))
check("catalogue has no duplicate ids", len({t["id"] for t in catalog}) == len(catalog))

bad_confidence: list[str] = []
numeric_unknown: list[str] = []
for t in catalog:
    for pc in t["pass_criteria"]:
        if pc["confidence"] not in mechanic_tests.CONFIDENCE_LEVELS:
            bad_confidence.append(f"{t['id']}:{pc['parameter']}")
        if pc["confidence"] == mechanic_tests.UNKNOWN and isinstance(pc["spec"], (int, float)):
            numeric_unknown.append(f"{t['id']}:{pc['parameter']}")
check("every pass_criteria confidence is one of CONFIDENCE_LEVELS",
     not bad_confidence, str(bad_confidence))
check("no pass_criteria pairs a numeric spec with UNKNOWN confidence",
     not numeric_unknown, str(numeric_unknown))
check("tests_for_codes finds EVAP tests for P0455", any(
    t["id"] == "evap_smoke" for t in mechanic_tests.tests_for_codes(["P0455"])))
check("tests_for_systems finds EVAP tests for system 'evap'", any(
    t["id"] == "evap_smoke" for t in mechanic_tests.tests_for_systems(["evap"])))
check("test() returns None for an unknown id", mechanic_tests.test("not-a-real-id") is None)


# ===========================================================================
# 2. the page
# ===========================================================================

print("=== page ===")
client = TestClient(create_app())

page = client.get(f"/v/{VIN}/tests")
check("tests page responds 200", page.status_code == 200, str(page.status_code))
check("tests page shows the Tests tab link", f'href="/v/{VIN}/tests"' in page.text)
check("no template error leaked onto the page",
     "Jinja2" not in page.text and "Traceback" not in page.text)

missing_buttons = [t["id"] for t in catalog
                  if f'value="pass"' not in page.text or f'id="test-{t["id"]}"' not in page.text]
check("every test has a row anchor on the page", not missing_buttons, str(missing_buttons[:5]))
check("the page carries PASS/FAIL buttons", 'value="pass"' in page.text and 'value="fail"' in page.text)
check("the page carries Inconclusive/Not possible buttons",
     'value="inconclusive"' in page.text and 'value="not_possible"' in page.text)

catalog_resp = client.get("/api/tests/catalog")
check("GET /api/tests/catalog responds 200", catalog_resp.status_code == 200,
     str(catalog_resp.status_code))
check("GET /api/tests/catalog carries every test", len(catalog_resp.json().get("tests", [])) == len(catalog))

view_resp = client.get(f"/api/tests/{VIN}")
check("GET /api/tests/{vin} responds 200", view_resp.status_code == 200, str(view_resp.status_code))
view = view_resp.json()
check("the view's total matches the catalogue size", view.get("total") == len(catalog), str(view.get("total")))
check("the view carries a counts dict with not_done == total before any result",
     view.get("counts", {}).get("not_done") == len(catalog), str(view.get("counts")))


# ===========================================================================
# 3. recording a result
# ===========================================================================

print("=== recording a result ===")
test_id = "evap_smoke"
fail_resp = client.post(f"/api/tests/{VIN}/{test_id}/result",
                        json={"result": "fail", "reason": "smoke at purge valve",
                              "by": "tester"})
check("POSTing a fail result responds 200", fail_resp.status_code == 200, str(fail_resp.text))
check("the response reports result=fail", fail_resp.json().get("result") == "fail",
     str(fail_resp.json()))

on_file = checklist_store.get(VIN).get(f"test:{test_id}")
check("the result is on file under step_id 'test:<id>'",
     on_file is not None and on_file.get("result") == "fail", str(on_file))

page_after = client.get(f"/v/{VIN}/tests")
check("the page now shows that row as FAIL",
     f'id="test-{test_id}"' in page_after.text and "ts-result-fail" in page_after.text)

bad_resp = client.post(f"/api/tests/{VIN}/{test_id}/result", json={"result": "bogus"})
check("an invalid result value responds 400", bad_resp.status_code == 400,
     str(bad_resp.status_code))

unknown_test_resp = client.post(f"/api/tests/{VIN}/not-a-real-id/result",
                                json={"result": "pass"})
check("POSTing to an unknown test id responds 400", unknown_test_resp.status_code == 400,
     str(unknown_test_resp.status_code))

# a result naming a hypothesis attaches evidence -- open a job/hypothesis first
client.post(f"/v/{VIN}/job/open", data={"technician": "tester", "complaint": "EVAP"},
           follow_redirects=True)
job = client.get(f"/api/vehicles/{VIN}/job").json()["job"]
hyp = client.post(f"/api/jobs/{job['id']}/hypotheses",
                  json={"text": "EVAP leak at purge valve", "system": "evap"}).json()
evid_resp = client.post(f"/api/tests/{VIN}/{test_id}/result",
                        json={"result": "fail", "reason": "smoke confirmed",
                              "hypothesis_id": hyp["id"], "supports": "for",
                              "by": "tester"})
check("recording a result with a hypothesis_id responds 200", evid_resp.status_code == 200,
     str(evid_resp.text))
job_view = client.get(f"/api/vehicles/{VIN}/job/{job['id']}").json()
hyp_after = next(h for h in job_view["job"]["hypotheses"] if h["id"] == hyp["id"])
check("the hypothesis gained a 'test' evidence_for ref from the test result",
     any(r.get("kind") == "test" and r.get("id") == f"test:{test_id}"
        for r in hyp_after.get("evidence_for", [])),
     str(hyp_after.get("evidence_for")))


# ===========================================================================
# 4. no regressions in the other step-6/live checks
# ===========================================================================

print("=== no regressions ===")
PYTHON = sys.executable

for script in ("check_jobs_rules.py", "check_live_dashboard_page.py"):
    path = Path(__file__).resolve().parent / script
    result = subprocess.run([PYTHON, str(path)], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=300)
    ok = result.returncode == 0
    check(f"{script} still passes", ok,
         (result.stdout[-1500:] + result.stderr[-1500:]) if not ok else "")


# ===========================================================================
# summary
# ===========================================================================

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    for f in failures:
        print("FAIL:", f)
    sys.exit(1)
print("OK")
