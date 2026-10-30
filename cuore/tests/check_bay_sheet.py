"""Checks for the Bay sheet (cuore/services/bay_sheet.py, cuore/web/bay_sheet_routes.py).

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_bay_sheet.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_bay_check_")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import arrive_ready, bay_sheet  # noqa: E402
from cuore.web import bay_sheet_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
OTHER = "ZASFAKPN5J7B00000"
fails: list[str] = []
n = 0


def check(name: str, ok: bool) -> None:
    global n
    n += 1
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


import serial  # noqa: E402
_orig = serial.Serial.__init__


def _boom(*a, **k):
    raise AssertionError("adapter opened")


serial.Serial.__init__ = _boom

app = create_app()
app.include_router(bay_sheet_routes.router)
c = TestClient(app)

# empty state
r = c.get(f"/v/{VIN}/bay-sheet")
t = r.text
check("empty state renders", r.status_code == 200 and "Bay sheet" in t)
check("empty state names no code / no test", "No open code on record" in t and "No test recorded" in t)
check("empty state still has a next action", 'id="next"' in t and "Next: Start a job" in t)

# seed a job: hypothesis with evidence on both sides + an action test
from mes import jobs  # noqa: E402
j = jobs.open(VIN, technician="t", complaint="shudder when pulling away")
jobs.add_hypothesis(j["id"], "Torque converter lock-up shudder", system="transmission",
                    next_test="Check TCM software level before any flash", codes=["P0455"])
hid = jobs.get(j["id"])["hypotheses"][0]["id"]
jobs.add_action(j["id"], "test", "Smoke test EVAP", ref={"result": "pass"})
for side, lab in (("for", "TCM adaptation read"), ("against", "Fluid level check")):
    try:
        jobs.add_evidence(j["id"], hid, side, {"kind": "test", "label": lab, "id": lab[:3]})
    except Exception as e:  # noqa: BLE001
        print("evidence seeding note:", e)

r = c.get(f"/v/{VIN}/bay-sheet?job={j['id']}")
t = r.text
check("renders with seeded job", r.status_code == 200)
ids = [t.find(f'id="{s}"') for s in ("header", "codes", "done", "prepare", "safety", "closeout", "footer")]
check("sections in order", all(i > 0 for i in ids) and ids == sorted(ids))
check("next action present", 'id="next"' in t and "Next: " in t)
check("action test shown with its result", "Smoke test EVAP" in t and "pass" in t)
s = bay_sheet.build(VIN, j["id"])
res = {x["text"]: x["result"] for x in s["tests"]}
check("evidence_for = supports", res.get("TCM adaptation read") == "supports the hypothesis")
check("evidence_against = contradicts", res.get("Fluid level check") == "contradicts the hypothesis")
check("codes capped and rest counted", len(s["codes"]) <= bay_sheet.MAX_CODES and s["more_codes"] >= 0)
ar = arrive_ready.build(VIN)
check("equipment and parts come from arrive_ready", s["equipment"] == ar["equipment"] and s["parts"] == ar["parts"])
check("bulletins come from arrive_ready", s["bulletins"] == ar["bulletins"][:bay_sheet.MAX_BULLETINS])
check("check-by-VIN wording", "Check by VIN" in t)
check("never says open recall", "open recall" not in t.lower() and "recall free" not in t.lower())
check("proof box with ticks and signature", all(x in t for x in ("Codes re-read", "Monitors complete", "Road test", "Customer informed"))
      and "Technician signature" in t)
check("proof state shown", "Proof state:" in t)
check("print CSS hides nav, menu, overlay", "@media print" in t and ".intro-overlay" in t and ".menu-btn" in t and "header.top" in t)
body = t.split('<div class="bay">')[1].split('<div class="foot">')[0]
check("no script in the sheet", "<script" not in body and "onclick" not in body)
check("job url printed big", f"/v/{VIN}/bay-sheet?job={j['id']}" in t and 'class="url' in t)
check("no QR claim", "No QR code" in t)
serial.Serial.__init__ = _orig
print(f"\n{n - len(fails)}/{n} passed")
sys.exit(1 if fails else 0)
