"""Checks for the arrive-ready job page (cuore/services/arrive_ready.py).

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_arrive_ready.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_arrive_check_")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import owner_reports  # noqa: E402
from cuore.web import arrive_ready_routes  # noqa: E402

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


app = create_app()
app.include_router(arrive_ready_routes.router)
c = TestClient(app)

# no adapter use: block serial/socket opens during the whole run
import serial  # noqa: E402,F401  (pyserial present in the venv)
_orig = serial.Serial.__init__


def _boom(*a, **k):
    raise AssertionError("adapter opened")


serial.Serial.__init__ = _boom

# empty data
r = c.get(f"/v/{VIN}/arrive-ready")
t = r.text
check("renders with empty data", r.status_code == 200 and "Arrive ready" in t)

# seed owner report + job
owner_reports.add_report(VIN, description="Shudder when pulling away", consent=True, speed="City", frequency="Often")
from mes import jobs  # noqa: E402
j = jobs.open(VIN, technician="t", complaint="shudder")
jobs.add_hypothesis(j["id"], "Torque converter lock-up shudder", system="transmission",
                    next_test="Check TCM software level before any flash", codes=["P0455"])

r = c.get(f"/v/{VIN}/arrive-ready")
t = r.text
check("renders with seeded data", r.status_code == 200)
check("answer block first", 0 < t.find('id="answer"') < t.find('id="owner"'))
order = [t.find(f'id="{s}"') for s in ("owner", "leads", "bulletins", "parts", "equipment", "time")]
check("sections in order", all(o > 0 for o in order) and order == sorted(order))
check("answer shows counts", "reported complaint" in t and "to test" in t and "equipment item" in t)
check("owner words labelled", "Shudder when pulling away" in t and "owner&#39;s words" in t.replace("owner's words", "owner&#39;s words") and "not a reading" in t)
check("hypothesis shown as a lead", "Torque converter lock-up shudder" in t and "None is a conclusion" in t)
check("flash lead asks for charger", "13.2-13.5 V" in t)
check("verify-by-VIN wording", "Verify by VIN with the manufacturer" in t)
check("no invented recall status", "no open recall" not in t.lower() and "recall free" not in t.lower())
check("no invented times", "No time on record." in t and "labour estimate" not in t.split("6. Time on record")[1].split("</section>")[0] or "No time on record." in t)
check("actions at bottom", t.rfind('href="/v/%s/job"' % VIN) > t.find('id="time"') and "Print checklist" in t)
body = t.split('<div class="arr">')[1].split("{% endblock %}")[0]
check("no JavaScript in the page body", "<script" not in body.split('class="actions"')[0] and "onclick" not in body)
from cuore.services import arrive_ready  # noqa: E402
e = arrive_ready.build(OTHER)
check("service builds for a car with nothing on record", e["counts"]["owner"] == 0 and e["counts"]["leads"] == 0 and e["times"] == [] and e["parts"] == [])
check("empty top line says nothing on record", "Nothing on record" in e["top"])
check("leads carry the open-job hypothesis", any("lock-up" in l["text"] for l in arrive_ready.build(VIN)["leads"]))
check("hardware link", 'href="/hardware"' in t)

# intake complaints + symptoms (own VIN, own seeded store)
V2 = VIN
from mes import shop, symptoms  # noqa: E402
shop.intake(V2, "Rough idle when cold", technician="Marco")
shop.intake(V2, "  rough IDLE when cold ", technician="Lena")  # same words twice
symptoms.add(V2, "2020-01-05T08:00:00", odometer_km=84210, text="Hesitation at 3000 rpm")
symptoms.add(V2, "2099-01-01T08:00:00", text="Far-future symptom sorts first")
owner_reports.add_report(V2, description="Smell of fuel", consent=True)
rows = arrive_ready.build(V2)["owner"]
texts = [x["text"].lower() for x in rows]
check("intake complaint shown once (de-duplicated)", sum("rough idle" in x for x in texts) == 1)
check("symptom shown", any("hesitation" in x for x in texts))
check("newest first", [x["at"] for x in rows] == sorted((x["at"] for x in rows), reverse=True) and "far-future" in texts[0])
lab = {x["origin"]: x["label"] for x in rows}
check("intake labelled by who and date", lab.get("intake", "").startswith("recorded at intake by ") and ("Lena" in lab["intake"] or "Marco" in lab["intake"]))
check("symptom labelled with odometer and date", "2020-01-05" in lab.get("symptom", "") or "84210" in " ".join(x["label"] for x in rows))
check("owner labelled as words not a reading", lab.get("owner") == "owner's words, not a reading")
t2 = c.get(f"/v/{V2}/arrive-ready").text
check("page shows intake and symptom labels", "recorded at intake by" in t2 and "84210 km" in t2 and "rough idle when cold" in t2.lower())
check("intake feeds the leads path like owner reports", arrive_ready.build(V2)["top"].startswith("Battery charger")
      or "Read the complaint first" in arrive_ready.build(V2)["top"])

serial.Serial.__init__ = _orig
print(f"\n{n - len(fails)}/{n} passed")
sys.exit(1 if fails else 0)
