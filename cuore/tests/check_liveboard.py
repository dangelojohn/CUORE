"""Checks for the liveboard: ``cuore.services.liveboard_bridge`` and
``cuore/api/liveboard.py``.

Same posture as ``cuore/tests/check_live_ui_api.py``/``check_jobs_page.py``:
plain script, no mocking framework, ``CUORE_STATE_DIR`` pointed at a
throwaway directory BEFORE anything is imported so this never touches the
bench's real job ledger.

Seven checks:
  1. ``board`` groups ``engine_coolant_temp`` under "temperatures" and
     ``battery_voltage`` under "voltage".
  2. A coolant value above its sourced alarm grades "excessive" with text
     mentioning coolant.
  3. A channel with no sourced band grades "unknown".
  4. ``rates`` has engine RPM polled faster than coolant temperature.
  5. ``GET /api/liveboard/{vin}`` returns 200.
  6. A snapshot with coolant above its alarm creates a "cooling" hypothesis
     on the current job with a "live" evidence ref, and a second snapshot
     attaches to that same hypothesis rather than duplicating it.
  7. A fuel level inside the 15-85% window adds evidence_for on an open
     EVAP hypothesis.

Run:
    .venv/Scripts/python.exe cuore/tests/check_liveboard.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-liveboard-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401  -- side effect: mes on sys.path
from cuore.app import create_app  # noqa: E402
from cuore.services import liveboard_bridge  # noqa: E402

from mes import jobs as jobs_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want, extra: str = "") -> None:
    detail = f"got {got!r} want {want!r}"
    if extra:
        detail += f" ({extra})"
    check(label, got == want, detail)


# --- 1. board grouping ------------------------------------------------------

board = liveboard_bridge.board(VIN)

group_of = {}
for g in board["groups"]:
    for ch in g["channels"]:
        group_of[ch["id"]] = g["id"]

check_eq("coolant grouped under temperatures", group_of.get("engine_coolant_temp"), "temperatures")
check_eq("battery grouped under voltage", group_of.get("battery_voltage"), "voltage")
check("board lists all_channel_ids", len(board["all_channel_ids"]) > 0)
check("board carries the read-only notice", "passenger" in board["notice"].lower())


# --- 2. coolant above alarm -> excessive, text mentions coolant ------------

hot = liveboard_bridge.evaluate("engine_coolant_temp", 140.0)
check_eq("coolant 140C grades excessive", hot["level"], "excessive")
check("coolant excessive text mentions coolant", "coolant" in hot["text"].lower(), hot["text"])


# --- 3. no band -> unknown --------------------------------------------------

unknown = liveboard_bridge.evaluate("intake_air_temp", 25.0)
check_eq("IAT (no sourced band) grades unknown", unknown["level"], "unknown")


# --- 4. rates: rpm faster than coolant --------------------------------------

rpm_hz = board["rates"].get("engine_rpm")
coolant_hz = board["rates"].get("engine_coolant_temp")
check("rpm and coolant both rated", rpm_hz is not None and coolant_hz is not None,
     f"rpm={rpm_hz!r} coolant={coolant_hz!r}")
if rpm_hz is not None and coolant_hz is not None:
    check("rpm polled faster than coolant", rpm_hz > coolant_hz,
         f"rpm={rpm_hz} coolant={coolant_hz}")


# --- 5. API 200 --------------------------------------------------------------

app = create_app()
client = TestClient(app)
resp = client.get(f"/api/liveboard/{VIN}")
check_eq("GET /api/liveboard/{vin} status", resp.status_code, 200, resp.text[:200])
if resp.status_code == 200:
    body = resp.json()
    check("API board response has groups", "groups" in body and len(body["groups"]) > 0)


# --- 6. snapshot -> job: cooling hypothesis seeded then reused -------------

job = jobs_mod.open(VIN, technician="check_liveboard", complaint="overheating test")
job_id = job["id"]

result1 = liveboard_bridge.attach_snapshot_to_job(VIN, "snap_cooling_1",
                                                  {"engine_coolant_temp": 140.0})
check_eq("first hot snapshot: 1 value out of range", result1["out_of_range"], 1)
check("first hot snapshot created a new hypothesis", len(result1["new_hypotheses"]) == 1,
     repr(result1))

job_after1 = jobs_mod.get(job_id)
cooling_hyps = [h for h in job_after1["hypotheses"]
               if (h.get("system") or "").strip().lower() == "cooling"]
check_eq("exactly one cooling hypothesis after first snapshot", len(cooling_hyps), 1)
if cooling_hyps:
    hyp = cooling_hyps[0]
    check_eq("cooling hypothesis starts open", hyp["status"], "open")
    live_refs = [r for r in hyp["evidence_for"] if r.get("kind") == "live"]
    check("cooling hypothesis has a live evidence ref", len(live_refs) == 1, repr(hyp))
    check("live ref points at the snapshot id",
         any(r.get("id") == "snap_cooling_1" for r in live_refs))

result2 = liveboard_bridge.attach_snapshot_to_job(VIN, "snap_cooling_2",
                                                  {"engine_coolant_temp": 150.0})
check("second hot snapshot creates no new hypothesis", len(result2["new_hypotheses"]) == 0,
     repr(result2))

job_after2 = jobs_mod.get(job_id)
cooling_hyps2 = [h for h in job_after2["hypotheses"]
                if (h.get("system") or "").strip().lower() == "cooling"]
check_eq("still exactly one cooling hypothesis after second snapshot", len(cooling_hyps2), 1)
if cooling_hyps2:
    live_refs2 = [r for r in cooling_hyps2[0]["evidence_for"] if r.get("kind") == "live"]
    check_eq("cooling hypothesis now has two live refs", len(live_refs2), 2)


# --- 7. in-window fuel level -> evidence_for on an open EVAP hypothesis ----

evap_hyp = jobs_mod.add_hypothesis(job_id, "EVAP: test hypothesis", system="EVAP")
result3 = liveboard_bridge.attach_snapshot_to_job(VIN, "snap_fuel_1", {"fuel_level": 50.0})

job_after3 = jobs_mod.get(job_id)
evap_now = next(h for h in job_after3["hypotheses"] if h["id"] == evap_hyp["id"])
verify_refs = [r for r in evap_now["evidence_for"]
              if "verification possible" in (r.get("label") or "").lower()]
check("in-window fuel level adds a verification-possible ref to the EVAP hypothesis",
     len(verify_refs) == 1, repr(evap_now))
check("fuel snapshot-to-job ran without error", isinstance(result3, dict))


# --- summary -----------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
