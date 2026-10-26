"""Intermittent-fault correlator: a shared condition is found and counted, too few events
say so (and still list them), another VIN's / a non-car event is never used, and the page renders.

Synthetic data only, in a temp state dir. Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_intermittent.py
"""
import json, os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
tmp = tempfile.mkdtemp(prefix="cuore-check-intermittent-")
os.environ["CUORE_STATE_DIR"] = tmp
os.environ.pop("MES_LIVE_OBSERVATIONS", None)

VIN, OTHER = "ZZZSYNTHVIN000001", "ZZZOTHERVIN000002"
fails = []
def check(ok, label):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        fails.append(label)

def snap(vin, dtc, at, volts, startups, optime, stream="serial COM3@115200"):
    ids = [{"did": "1008", "name": "Operating time", "value": optime, "unit": "min", "confidence": "high"},
           {"did": "200A", "name": "Startups counter", "value": startups, "unit": None, "confidence": "high"},
           {"did": "1004", "name": "Battery voltage", "value": volts, "unit": "V", "confidence": "medium"}]
    return {"at": at, "kind": "dtc_detail", "vin": vin, "stream": stream,
            "data": {"ecu": "BCM", "dtc": dtc, "snapshot": {"records": [{"record_number": 0, "identifiers": ids}]}}}

rows = []
# U0100: 5 real events, 3 of them below 12.0 V
for i, v in enumerate([11.5, 11.8, 11.9, 12.6, 13.9]):
    rows.append(snap(VIN, "U0100-87", f"2026-10-0{i+1}T10:00:00", v, 1000 + i, 5000 + i))
rows.append(snap(OTHER, "U0100-87", "2026-10-07T10:00:00", 11.0, 2000, 6000))                  # other car
rows.append(snap(VIN, "U0100-87", "2026-10-08T10:00:00", 11.0, 3000, 7000, stream="fake"))    # not from the car
rows.append(snap(VIN, "U0100-87", "2026-10-09T10:00:00", 11.5, 1000, 5000))                    # same occurrence read twice
# U0200: only 2 events
for i in range(2):
    rows.append(snap(VIN, "U0200-00", f"2026-10-1{i}T10:00:00", 11.0, 1500 + i, 5500 + i))
(Path(tmp) / "observations.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

from cuore.services import cache, intermittent
cache.clear()

r = intermittent.analyze(VIN, "U0100")
check(r["n_events"] == 5, f"5 events for this VIN only (other VIN, non-car stream and a re-read duplicate dropped): {r['n_events']}")
low = next((l for l in r["lines"] if l["condition"] == "battery_v" and l["band"] == "low"), None)
check(low is not None and (low["n"], low["m"]) == (3, 5), f"low-voltage line counted 3 of 5: {low and (low['n'], low['m'])}")
check(low is not None and low["text"] == "3 of 5 set events: battery below 12.0 V", f"line text: {low and low['text']}")
check(low is not None and len(low["event_ids"]) == 3 and all(i in {e["id"] for e in r["events"]} for i in low["event_ids"]),
      "the line names the events behind it")
check(r["lines"] and r["lines"][0]["n"] / r["lines"][0]["m"] >= r["lines"][-1]["n"] / r["lines"][-1]["m"], "strongest first")
check(r["hint"] is not None and "3 of 5" in r["hint"]["text"] and "not a proven cause" in r["hint"]["caveat"],
      f"hint is a pattern with a caveat: {r['hint'] and r['hint']['text']}")
check(all(e["vin"] == VIN for e in [{"vin": VIN}]) and not any("2000" in json.dumps(e) for e in r["events"]), "other VIN's counter absent")

t = intermittent.analyze(VIN, "U0200")
check(t["n_events"] == 2 and not t["enough"] and t["headline"] == "too few events to correlate (2)", f"too-few wording: {t['headline']}")
check(len(t["events"]) == 2 and t["lines"] == [] and t["hint"] is None, "too few: events still listed, no lines, no hint")

n = intermittent.analyze(VIN, "U0999")
check(n["n_events"] == 0 and n["headline"] == "too few events to correlate (0)", "no events at all is not a pattern")

miss = intermittent.condition_values(intermittent.load_bands(), [("Battery voltage", "12.1 V", "")])
check("coolant_c" not in miss and miss["battery_v"]["value"] == 12.1, "an absent field is absent (not 0)")

# page + partial + JSON
from fastapi.testclient import TestClient
from cuore.app import create_app
from cuore.web import intermittent_routes
intermittent_routes._dossier = lambda vin: {}
app = create_app()
app.include_router(intermittent_routes.router)
c = TestClient(app)
p = c.get(f"/v/{VIN}/intermittent/U0100")
check(p.status_code == 200 and "3 of 5 set events: battery below 12.0 V" in p.text and "Pattern in the records" in p.text,
      f"code page renders with the line and hint ({p.status_code})")
check("not recorded" in p.text and "intermittent.css" in p.text, "page shows 'not recorded' cells and loads its css")
p2 = c.get(f"/v/{VIN}/intermittent/U0200")
check(p2.status_code == 200 and "Too few events to correlate (2)" in p2.text and "E2" in p2.text, "too-few page lists the events")
ov = c.get(f"/v/{VIN}/intermittent")
check(ov.status_code == 200 and "U0100" in ov.text and "U0200" in ov.text, "overview lists both codes")
j = c.get(f"/api/vehicles/{VIN}/intermittent/U0100")
check(j.status_code == 200 and j.json()["n_events"] == 5 and j.json()["lines"][0]["n"] >= 2, "JSON route")
check(c.get(f"/api/vehicles/{VIN}/intermittent/!!").status_code == 400, "a bad code is a 400")
check(c.get(f"/api/vehicles/{OTHER}/intermittent/U0100").json()["n_events"] == 1, "the other car sees only its own event")

print("all green" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
