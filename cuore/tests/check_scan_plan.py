"""Checks for the owner's ten-scan plan (``mes.scan_plan``,
``cuore.services.scan_plan_bridge``, ``cuore.web.scan_plan_routes``).

Same posture as ``cuore/tests/check_scanlog.py`` (the fixture lines below
for the 2026-10-13 baseline scan are copied from that suite's own fixture
at the time this was written, not imported -- each check_*.py owns its own
throwaway corpus): ``CUORE_STATE_DIR`` points at a fresh directory BEFORE
cuore is imported, every observation is a hand-built fixture appended
straight to ``observations.jsonl`` with a real ``stream="serial COM3@..."``
value, and nothing here opens COM3 or touches a live adapter endpoint. One
thing this fixture adds that check_scanlog.py's does not: a synthetic
``clear_evidence`` observation dated 2026-10-14, the "last clear" the
owner's own row-1 spec text is written against ("the one we still owe
since the 14 Oct clear").

Run:
    .venv/Scripts/python.exe cuore/tests/check_scan_plan.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-scan-plan-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import scan_plan_routes  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.services import scan_plan_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real VIN used across this suite's fixtures

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


app = create_app()
existing_paths = {getattr(r, "path", None) for r in app.routes}
if "/v/{vin}/scan-plan" not in existing_paths:
    app.include_router(scan_plan_routes.router)
client = TestClient(app)


def _write(at: datetime, kind: str, data: dict, *, vin: str = "",
          stream: str = "serial COM3@115200") -> None:
    entry = {"at": at.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "vin": vin,
             "bus": "can_c", "cable": "none", "stream": stream, "data": data}
    with live_store.observations_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ===========================================================================
# Fixture: one complete scan on 2026-10-13 (same shape check_scanlog.py's
# own OLDER fixture uses), then a synthetic clear the following day with no
# scan since -- the exact case the owner's row-1 spec text describes.
# ===========================================================================

OLDER = datetime(2026, 10, 13, 18, 0, 0)
_write(OLDER, "obd_dtcs", {"kind": "stored", "dtcs": [], "by_ecu": {"18DAF110": []}})
_write(OLDER + timedelta(minutes=1), "readiness",
      {"since_clear": {"mil_on": False, "stored_dtc_count": 0,
                        "monitors": [{"monitor": "Evaporative system", "supported": True,
                                      "complete": True}],
                        "all_complete": True}}, vin=VIN)
_write(OLDER + timedelta(minutes=2), "scan_coverage", {
    "scan_id": "SCAN_" + OLDER.strftime("%y%m%d%H%M"), "vin": VIN, "cable": "none",
    "buses_attempted": ["can_c"], "duration_s": 12.0, "steps": [],
    "coverage": [{"bus": "can_c", "module": m, "category": "answered", "why": None,
                  "active": 0, "history": 0, "not_run": 0}
                for m in ("ECM", "IPC", "TCM", "DTCM", "ESM")],
    "counts": {"active": 0, "history": 0, "not_run": 0},
}, vin=VIN)
_write(OLDER + timedelta(minutes=3), "freeze_frame",
      {"pid": "2F", "name": "fuel_level",
       "by_ecu": {"18DAF110": {"pid": "2F", "name": "fuel_level", "bytes": ["6B"],
                                "unit": "%", "value": 42.0}}}, vin=VIN)

# The synthetic 14 Oct clear -- the last clear this car has on file, with no
# scan at all since.
CLEAR = datetime(2026, 10, 14, 9, 0, 0)
_write(CLEAR, "clear_evidence", {"ecu": "ECM", "active": [], "tracked": 0,
                                 "file": "synthetic-fixture"}, vin=VIN)


# ===========================================================================
# Before a post-clear scan: row 1 is "due" with the owner's own wording
# shape -- fuel ok, monitors not run since the clear.
# ===========================================================================

plan = scan_plan_bridge.build_plan(VIN)
check("the plan always renders exactly 10 rows", len(plan["rows"]) == 10,
      str(len(plan["rows"])))
check("rows are numbered 1 through 10 in the owner's own order",
      [r["n"] for r in plan["rows"]] == list(range(1, 11)),
      str([r["n"] for r in plan["rows"]]))

row1 = plan["rows"][0]
check("row 1 is the baseline row", row1["id"] == "baseline", str(row1["id"]))
check("row 1 is 'due' (no scan has run since the clear)", row1["status"] == "due",
      str(row1["status"]))
check("row 1's own Connect-to-car button points at the guided-scan wizard",
      row1.get("connect_href") == f"/v/{VIN}/scan", str(row1.get("connect_href")))
check("row 1's blocker text reports the fuel reading on file and the 14 Oct clear",
      row1.get("why") == "fuel 42 % ok / monitors not run since the 14 Oct clear",
      str(row1.get("why")))

check("every later row is 'blocked' (row 1 is the single gating hold-up) or "
      "itself an optional row still shown 'due'",
      all(r["status"] in ("blocked", "due") for r in plan["rows"][1:]),
      str([(r["id"], r["status"]) for r in plan["rows"][1:]]))


# ===========================================================================
# A complete scan taken after the clear, with fuel in-window and every
# monitor run, marks row 1 done -- with that scan's own id and date, never
# "proven".
# ===========================================================================

AFTER_CLEAR = datetime(2026, 10, 15, 10, 0, 0)
_write(AFTER_CLEAR, "obd_dtcs", {"kind": "stored", "dtcs": [], "by_ecu": {"18DAF110": []}},
      vin=VIN)
_write(AFTER_CLEAR + timedelta(minutes=1), "readiness",
      {"since_clear": {"mil_on": False, "stored_dtc_count": 0,
                        "monitors": [{"monitor": "Evaporative system", "supported": True,
                                      "complete": True}],
                        "all_complete": True}}, vin=VIN)
_write(AFTER_CLEAR + timedelta(minutes=2), "scan_coverage", {
    "scan_id": "SCAN_" + AFTER_CLEAR.strftime("%y%m%d%H%M"), "vin": VIN, "cable": "none",
    "buses_attempted": ["can_c"], "duration_s": 12.0, "steps": [],
    "coverage": [{"bus": "can_c", "module": m, "category": "answered", "why": None,
                  "active": 0, "history": 0, "not_run": 0}
                for m in ("ECM", "IPC", "TCM", "DTCM", "ESM")],
    "counts": {"active": 0, "history": 0, "not_run": 0},
}, vin=VIN)
_write(AFTER_CLEAR + timedelta(minutes=3), "freeze_frame",
      {"pid": "2F", "name": "fuel_level",
       "by_ecu": {"18DAF110": {"pid": "2F", "name": "fuel_level", "bytes": ["6B"],
                                "unit": "%", "value": 50.0}}}, vin=VIN)
AFTER_CLEAR_ID = AFTER_CLEAR.strftime("SCAN_%y%m%d%H%M")

plan2 = scan_plan_bridge.build_plan(VIN)
row1_b = plan2["rows"][0]
check("row 1 is marked done once a complete scan runs after the clear with "
      "fuel in-window and every monitor complete",
      row1_b["status"] == "done", str(row1_b["status"]))
check("the done row carries that scan's own id", row1_b.get("scan_id") == AFTER_CLEAR_ID,
      str(row1_b.get("scan_id")))
check("the done row carries that scan's own date", row1_b.get("date") == AFTER_CLEAR.strftime(
      "%Y-%m-%dT%H:%M:%S"), str(row1_b.get("date")))
check("the word 'proven' is never used anywhere in the plan",
      not any("proven" in (r.get("why") or "").lower() for r in plan2["rows"]))

row2_b = plan2["rows"][1]
check("row 2 (Test A + ESIM commanded test) becomes the new 'due' row",
      row2_b["status"] == "due", str(row2_b["status"]))
check("row 2's why names the missing tests",
      "Test A" in (row2_b.get("why") or "") and "ESIM commanded" in (row2_b.get("why") or ""),
      str(row2_b.get("why")))
check("row 2 carries deep links to both tests",
      bool(row2_b.get("test_links")) and len(row2_b["test_links"]) == 2,
      str(row2_b.get("test_links")))

check("every row after row 2 is now blocked, naming row 2 as the hold-up",
      all(r["status"] == "blocked" and "Test A" in r.get("why", "")
         for r in plan2["rows"][2:]),
      str([(r["id"], r["status"], r.get("why")) for r in plan2["rows"][2:]]))

check("scan_plan() chip still counts only complete scans (2 of 10 now)",
      plan2["scan_plan"] == {"count": 2, "total": 10}, str(plan2["scan_plan"]))


# ===========================================================================
# HTTP: TestClient only, never COM3 / a live adapter endpoint.
# ===========================================================================

r = client.get(f"/v/{VIN}/scan-plan")
check("GET /v/{vin}/scan-plan is 200", r.status_code == 200, str(r.status_code))
check("the page renders all 10 rows' titles",
      all(row["title"] in r.text for row in plan2["rows"]), "")
check("the page shows a Connect to car button for the due row",
      "Connect to car" in r.text, "")
check("the page shows the done row's own scan id", AFTER_CLEAR_ID in r.text, "")


print(f"\n{checks} checks, {len(failures)} failures")
if failures:
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
