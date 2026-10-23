"""Checks for the adapter-cable catalogue (cuore/data/adapter_cables.json,
cuore/services/adapter_cables_bridge.py, GET /api/cables and /cables).

Pure file reads and a TestClient; nothing opens a serial port.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_adapter_cables.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-cables-")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live.buses import CABLES  # noqa: E402
from cuore.services import adapter_cables_bridge as bridge  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# 1. loader: only A5/A6 are live-drivable, lookups use the buses.py cable value
rows = bridge.load()
live = {r["id"]: r["live_route"] for r in rows if r["live_route"]}
check("only A5/A6 have a live_route", live == {"A5": "blue_a5", "A6": "grey_a6"}, str(live))
check("live_route values are real CABLES", all(v in CABLES for v in live.values()))
check("for_cable maps buses.py values", bridge.for_cable("blue_a5")["id"] == "A5"
      and bridge.for_cable("grey_a6")["id"] == "A6"
      and bridge.for_cable("none") is None)
check("brand filter", {r["id"] for r in bridge.by_brand("maserati")} == {"SGW-12+8"}
      and len(bridge.by_brand("")) == len(rows))
check("every row keeps confidence and sources", all("confidence" in r and "sources" in r for r in rows))

# 2. API and page are read-only and carry the label and both warnings
client = TestClient(create_app())
r = client.get("/api/cables")
body = r.json() if r.status_code == 200 else {}
check("GET /api/cables", r.status_code == 200 and body.get("count") == len(rows)
      and "external reference" in body.get("label", "")
      and any("AIRBAG" in w for w in body.get("warnings", []))
      and any("pins 1 and 9" in w for w in body.get("warnings", [])), str(r.status_code))
page = client.get("/cables")
check("GET /cables page", page.status_code == 200 and "External reference, not a CUORE reading" in page.text
      and "blue_a5" in page.text and "grey_a6" in page.text, str(page.status_code))
check("no write verbs", client.post("/api/cables").status_code in (404, 405))

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
