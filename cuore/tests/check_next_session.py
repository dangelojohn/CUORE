"""Checks for the "Next connection" plan (services/next_session.py, page + bench panel).

Run: .venv/Scripts/python.exe cuore/tests/check_next_session.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-next-session-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.services import next_session  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []


def check(label: str, cond: bool) -> None:
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        failures.append(label)


v = next_session.view(VIN)
check("seed loads 8 steps, 0 done", bool(v) and v["total"] == 8 and v["done"] == 0)
check("seed file written to state dir", (Path(STATE) / "next_session_plan.json").exists())
check("other VIN has no plan", next_session.view("0" * 17) is None)

next_session.mark(VIN, "battery-label", True)
v = next_session.view(VIN)
check("mark done: 1 done, sorted last", v["done"] == 1 and v["steps"][-1]["id"] == "battery-label")
next_session.mark(VIN, "battery-label", False)
check("undo: 0 done", next_session.view(VIN)["done"] == 0)

# auto-detect: RFHUB answered in a scan_coverage observation on the latest day
entry = {"at": "2026-10-27T07:00:00", "kind": "scan_coverage", "vin": VIN, "bus": "can_c",
         "cable": "none", "stream": "serial COM3@115200",
         "data": {"buses_attempted": ["can_c"],
                  "coverage": [{"bus": "can_c", "module": "RFHUB", "category": "answered"}]}}
with live_store.observations_path().open("a", encoding="utf-8") as f:
    f.write(json.dumps(entry) + "\n")
v = next_session.view(VIN)
rf = next(s for s in v["steps"] if s["id"] == "rfhub-first")
check("RFHUB step auto-detected done", rf["done"] and rf["done_how"] == "auto" and rf["done_at"] == "2026-10-27")
next_session.mark(VIN, "rfhub-first", False)
check("manual undo beats auto", not next(s for s in next_session.view(VIN)["steps"] if s["id"] == "rfhub-first")["done"])

client = TestClient(create_app())
r = client.get(f"/v/{VIN}/next-session")
check("page renders with summary and Done buttons",
      r.status_code == 200 and "Next connection" in r.text and "steps (" in r.text and ">Done<" in r.text)
r = client.post(f"/v/{VIN}/next-session/can-captures", data={"action": "done", "return_to": f"/v/{VIN}"},
                follow_redirects=False)
check("POST done redirects back to the home", r.status_code == 303 and r.headers["location"] == f"/v/{VIN}")
r = client.get(f"/v/{VIN}")
check("home panel shows count", r.status_code == 200 and "Next connection — 8 steps (1 done)" in r.text
      and 'id="bench-next-session"' in r.text)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
