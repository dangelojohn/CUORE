"""Checks for /settings: radios, POST units, odometer renders mi. Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_settings_page.py"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_settings_check_")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import units  # noqa: E402

failures: list[str] = []


def check(cond: bool, label: str) -> None:
    if not cond:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
c = TestClient(create_app())
r = c.get("/settings")
check(r.status_code == 200, "GET /settings 200")
check('value="metric"' in r.text and 'value="imperial"' in r.text, "both radios")
check('value="metric" checked' in r.text, "metric default")
check("exists: " in r.text and "State directory" in r.text, "folders shown")
check('href="/settings"' in r.text, "nav link")
check(units.dist(142289) == "142,289 km" and units.speed(100) == "100 km/h", "metric filters")
before = c.get(f"/v/{VIN}")
r = c.post("/settings", data={"units": "imperial"}, follow_redirects=False)
check(r.status_code == 303 and r.headers.get("location") == "/settings", "POST 303 to /settings")
r = c.get("/settings")
check('value="imperial" checked' in r.text, "imperial selected")
check(units.dist(142289) == "88,414 mi" and units.speed(100) == "62 mph", "imperial filters")
after = c.get(f"/v/{VIN}")
check(after.status_code == 200, "vehicle page 200")
check(" mi" in after.text, "vehicle page odometer in mi")
if " km</span>" in before.text:
    check(" km</span>" not in after.text, "no km odometer after switch")
if failures:
    print("FAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("check_settings_page: all passed")
