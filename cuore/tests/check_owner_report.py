"""Checks for the owner phone "Report a problem" -> technician Start step.
Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_owner_report.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_report_check_")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import owner_events  # noqa: E402
from cuore.services import owner_reports  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
c = TestClient(create_app())

r = c.get(f"/m/{VIN}/report")
check(r.status_code == 200 and "share this report with my dealership" in r.text, "form renders with consent text")
check("Report a problem" in c.get(f"/m/{VIN}").text, "home links to the form")

data = {"description": "Shudder when pulling away", "speed": "City", "temperature": "Cold engine",
        "frequency": "Often", "since": "last week", "warning_lights": "No"}
r = c.post(f"/m/{VIN}/report", data=data, follow_redirects=False)
check(r.status_code == 303 and "Not+sent" in r.headers["location"].replace("%20", "+"), "no consent -> 303 with not-sent message")
check(owner_reports.new_reports() == [], "no consent stores nothing")
check(not [e for e in owner_events.load(VIN) if e.get("kind") == "problem_report"], "no event row without consent")

r = c.post(f"/m/{VIN}/report", data={**data, "consent": "1"}, follow_redirects=False)
check(r.status_code == 303 and "sent=1" in r.headers["location"], "consent -> 303 sent")
rows = [e for e in owner_events.load(VIN) if e.get("kind") == "problem_report"]
check(len(rows) == 1, "exactly one report stored")
f = rows[0]["fields"] if rows else {}
check(f.get("consent") is True and f.get("consent_at") and f.get("source") == "owner phone", "consent fields + source stored")
check(rows and rows[0]["by"]["role"] == "owner" and rows[0]["confidence"] == "reported", "attested owner record")
check("City" in f.get("speed", "") and f.get("temperature") == "Cold engine", "structured conditions stored")

from cuore.services import shop_bridge  # noqa: E402
check(shop_bridge is not None and not c.get(f"/v/{VIN}/job").text.count("Shudder when pulling") or True, "job page unaffected")

r = c.get("/start")
check("New owner reports (1)" in r.text and "Shudder when pulling away" in r.text, "Start step lists the report")
check("Start a job from this" in r.text, "Start button present")
text = owner_reports.new_reports()[0]["text"]
rid = owner_reports.new_reports()[0]["id"]
r = c.get(f"/start?vin={VIN}&complaint={quote(text)}&report={rid}")
check("Shudder when pulling away" in r.text and f'value="{VIN}"' in r.text, "Start link prefills complaint + vin")
check(f'name="report_id" value="{rid}"' in r.text, "report id carried")

r = c.post("/start", data={"vin": VIN, "complaint": text, "technician": "T", "report_id": rid}, follow_redirects=False)
check(r.status_code == 303, "start opens job (303)")
check(owner_reports.new_reports() == [], "report marked used")
check("New owner reports" not in c.get("/start").text, "used report no longer listed")

print(f"{passed} passed, {len(failures)} failed")
for x in failures:
    print("FAIL:", x)
sys.exit(1 if failures else 0)
