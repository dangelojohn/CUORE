"""Performance checks for GET /v/{vin}/job and GET /v/{vin}.

``cuore.services.{dossier_bridge,jobs_bridge,flow_bridge}`` each used to call
``mes_bridge.workup`` directly and re-evaluate the fault tree per open-work
code on every render, bypassing the memoised workup
``cuore.web.routes._dossier`` already builds -- seconds of FES re-parsing on
a real corpus, repeated two or three times in a single job-page render. They
now share that cache (and a new one for the rest of
``dossier_bridge.build_view``, keyed on vin + newest MES-log mtime + newest
state-file mtime) -- see each module's own comments.

Same posture as ``check_jobs_page.py``/``check_flow.py``: ``CUORE_STATE_DIR``
is pointed at a throwaway directory BEFORE cuore is imported, so writes here
never touch real shop state; the real MES corpus on this machine (the
Stelvio, VIN below -- 17 logs, chronic EVAP codes) is the fixture for render
cost, since a synthetic corpus would never reproduce the FES-parsing cost
being guarded against here.

Two checks:
  1. A warm render of /v/{vin}/job, and of /v/{vin}, completes in under 1.5
     seconds -- down from 9-12s and 4.6s respectively before caching.
  2. Adding a symptom report after the cache is warm still shows up on the
     next render -- the new state-file mtime in the cache key must
     invalidate the build, not just the MES-log mtime.

Run:
    .venv/Scripts/python.exe cuore/tests/check_perf.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-perf-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from mes import symptoms as symptoms_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, 17 logs, chronic EVAP codes

BUDGET_S = 1.5

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())

# A job must be open for the page to render its full stepper body (step 1
# alone renders with no job) -- same seeding check_jobs_page.py's screenshot
# server does.
client.post(f"/v/{VIN}/job/open",
           data={"technician": "tester", "complaint": "CEL, smells like gas"},
           follow_redirects=True)


# --- 1. warm renders stay under budget --------------------------------------

client.get(f"/v/{VIN}/job")  # cold: fills every cache this page touches

t0 = time.perf_counter()
warm_job = client.get(f"/v/{VIN}/job")
job_elapsed = time.perf_counter() - t0
check("warm GET /v/{vin}/job responds 200", warm_job.status_code == 200,
      str(warm_job.status_code))
check(f"warm GET /v/{{vin}}/job renders in under {BUDGET_S}s",
      job_elapsed < BUDGET_S, f"{job_elapsed:.3f}s")

t0 = time.perf_counter()
warm_dossier = client.get(f"/v/{VIN}")
dossier_elapsed = time.perf_counter() - t0
check("warm GET /v/{vin} responds 200", warm_dossier.status_code == 200,
      str(warm_dossier.status_code))
check(f"warm GET /v/{{vin}} renders in under {BUDGET_S}s",
      dossier_elapsed < BUDGET_S, f"{dossier_elapsed:.3f}s")

print(f"warm job: {job_elapsed:.3f}s, warm dossier: {dossier_elapsed:.3f}s")


# --- 2. a new symptom invalidates the cache and shows up --------------------

marker = "check_perf marker symptom -- smells faintly of victory"
symptoms_mod.add(VIN, "2026-01-01T09:00:00", reporter="driver", text=marker)

# ?step=2 forces the full "complaint & symptoms" screen (the symptom list
# the marker must appear in) regardless of which step the flow currently
# considers current.
after = client.get(f"/v/{VIN}/job?step=2")
check("the symptom-added page still responds 200", after.status_code == 200,
      str(after.status_code))
check("the job page reflects a symptom added after the cache was warmed",
      marker in after.text, after.text[:500])


# --- report ------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
