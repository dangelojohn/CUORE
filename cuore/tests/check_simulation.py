"""Checks for the simulated connection and the read-only port suggestion.
Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_simulation.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore_sim_check_")
os.environ["CUORE_STATE_DIR"] = STATE
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import ops, poller as poller_mod, store  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def tree() -> set[str]:
    return {str(p.relative_to(STATE)) for p in Path(STATE).rglob("*") if p.is_file()}


# --- port suggestion: pure, from a listed fixture, opens nothing
fixture = [
    {"device": "COM1", "description": "Communications Port (COM1)", "hwid": "ACPI\PNP0501"},
    {"device": "COM3", "description": "vLinker FS (COM3)", "hwid": "USB VID:PID=0403:6001"},
]
s = ops.suggest_port(fixture)
check(s is not None and s["device"] == "COM3" and "vlinker" in s["reason"].lower(), f"suggests COM3 ({s})")
check(ops.suggest_port([]) is None, "empty list -> None")
check(ops.suggest_port(fixture[:1]) is None, "no adapter in list -> None")

# --- simulation
app = create_app()
with TestClient(app) as c:
    before = tree()
    check(c.get("/live").status_code == 200, "live page renders")
    r = c.post("/api/live/session/start", json={"channels": ["engine_rpm", "vehicle_speed"],
                                                "simulation": True})
    check(r.status_code == 200 and r.json().get("simulation") is True and r.json().get("active"),
          f"simulated session started ({r.status_code} {r.text[:120]})")
    time.sleep(1.5)
    snap = c.get("/api/live/snapshot")
    check(snap.status_code == 200 and "engine_rpm" in snap.text, "snapshot has fixture values")
    page = c.get("/live")
    check("SIMULATION" in page.text and "not the car" in page.text, "banner on the live page")
    check("SIMULATION" in c.get("/").text, "banner on another page")
    c.post("/api/live/session/stop")
    check("SIMULATION" not in c.get("/live").text, "banner gone after stop")
    new = tree() - before
    check(not any("observ" in n.lower() or "audit" in n.lower() for n in new), f"no observation/audit files ({new})")
    check(store.recent_observations(50) == [] if hasattr(store, "recent_observations") else True, "store empty")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
