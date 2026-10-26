"""Checks for the sensor health page (``/v/{vin}/sensors``) and its profile SVG.

Uses fixtures in place of ``cuore.services.sensor_health`` (never touches the
car). Also writes a self-contained HTML copy of the fixture page for a
headless-Chrome screenshot (path via ``--html``, default under the scratchpad).

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_sensor_page.py
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def sensor(id_, label, status, zone, side="centre", conf="SOURCED", system="Engine", **kw):
    d = {"id": id_, "label": label, "system": system, "module": "ECM", "bus": "CAN-IHS",
         "channels": ["value"], "readable": True, "readable_note": "", "element_id": None,
         "zone": zone, "side": side, "location_confidence": conf, "location_source": "fixture",
         "status": status, "reasons": [f"{label} is {status}"], "last_read": "2026-10-25T09:00:00",
         "values": [{"channel": "value", "label": "Reading", "value": 1.2, "unit": "V",
                     "read_at": "2026-10-25T09:00:00", "range": None, "in_range": None}],
         "codes": []}
    d.update(kw)
    return d


SENSORS = [
    sensor("map", "Manifold pressure", "green", "engine_bay",
           values=[{"channel": "value", "label": "MAP", "value": 101, "unit": "kPa", "read_at": "t",
                    "range": {"min": 20, "max": 110, "unit": "kPa", "source": "fixture manual"}, "in_range": True}]),
    sensor("o2f", "Upstream O2", "orange", "under_car_exhaust", system="Exhaust",
           codes=[{"code": "P0131-00", "module": "ECM", "description": "O2 low", "state": "stored"}]),
    sensor("wssfl", "Wheel speed FL", "red", "front_left_wheel_well", side="left", system="Brakes"),
    sensor("wssfr", "Wheel speed FR", "green", "front_right_wheel_well", side="right", system="Brakes"),
    sensor("park", "Parking sensor", "grey", "front_bumper", conf="INFERRED", system="Body",
           readable=False, readable_note="needs the grey cable"),
    sensor("cam", "Reverse camera", "grey", None, system="Body", element_id="rev_cam", conf="UNKNOWN"),
    sensor("noel", "Rain sensor", "grey", "not_a_zone", system="Body"),
] + [sensor(f"eb{i}", f"Engine bay probe {i}", ["green", "orange", "grey"][i % 3], "engine_bay") for i in range(8)]

CALLS: dict[str, list] = {"check": [], "range": []}
MODE = {"check": "ok"}


def fake_health(vin):
    counts = {k: sum(1 for s in SENSORS if s["status"] == k) for k in ("green", "orange", "red", "grey")}
    return {"vin": vin, "checked_at": "2026-10-25T09:00:00", "sensors": list(SENSORS), "counts": counts,
            "unplaced": [s["id"] for s in SENSORS if not s["zone"]]}


def fake_check_all(vin):
    if MODE["check"] == "mes":
        raise RuntimeError("MultiEcuScan is connected - adapter busy")
    if MODE["check"] == "refused":
        return {"ok": False, "refused": True, "error": "another live session holds the adapter"}
    CALLS["check"].append(vin)
    return {"ok": True, "refused": False, "checked": len(SENSORS), "read": 2}


def fake_readings(vin):
    return {"vin": vin, "checks": ["2026-10-25T19:56:26", "2026-10-26T09:10:00"], "rows": [
        {"at": "2026-10-25T19:56:26", "sensor_ids": ["coolant_temp"], "sensors": ["Coolant temperature"],
         "channel": "engine_coolant_temp", "part": "", "name": "Coolant temp", "unit": "C", "value": 53, "error": None},
        {"at": "2026-10-26T09:10:00", "sensor_ids": ["coolant_temp"], "sensors": ["Coolant temperature"],
         "channel": "engine_coolant_temp", "part": "", "name": "Coolant temp", "unit": "C", "value": 88, "error": None},
        {"at": "2026-10-26T09:10:00", "sensor_ids": ["o2_b1s1"], "sensors": ["Upstream O2"],
         "channel": "o2_b1s1_wide_range", "part": "lambda", "name": "O2 wide", "unit": "", "value": 0.993, "error": None},
        {"at": "2026-10-26T09:10:00", "sensor_ids": ["oil_temp"], "sensors": ["Oil temperature"],
         "channel": "engine_oil_temp", "part": "", "name": "Oil temp", "unit": "C", "value": None, "error": "no data"}]}


def fake_add_range(model, sensor_id, channel, min, max, unit, source, by):
    if not str(source).strip():
        raise ValueError("source is required")
    CALLS["range"].append((model, sensor_id, channel, min, max, unit, source, by))


fake = types.ModuleType("cuore.services.sensor_health")
fake.health, fake.check_all, fake.add_range = fake_health, fake_check_all, fake_add_range
fake.readings = fake_readings
import cuore.services as _svc  # noqa: E402

sys.modules["cuore.services.sensor_health"] = fake
_svc.sensor_health = fake

from cuore.app import create_app  # noqa: E402
from cuore.web import sensor_profile_svg  # noqa: E402

client = TestClient(create_app(), follow_redirects=False)
VIN = "ZASFAKPN5J7B88115"

# --- the SVG on its own -------------------------------------------------
empty = sensor_profile_svg.render([])
check(empty.startswith("<svg") and empty.rstrip().endswith("</svg>") and "sens-dot" not in empty,
      "svg renders for an empty sensor list")
pos, unplaced = sensor_profile_svg.layout(SENSORS)
check(set(unplaced) == {"cam", "noel"}, "unknown / missing zone -> unplaced")
pts = list(pos.values())
check(all((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 >= 18 ** 2
          for i, a in enumerate(pts) for b in pts[i + 1:]), "no two dots overlap")
check(all(0 < x < 860 and 0 < y < 360 for x, y in pts), "all dots inside the viewBox")

# --- generic renderer (fuse page reuse) -------------------------------------
fz = ["fuse_box_engine_bay", "fuse_box_interior", "fuse_box_rear"]
check(all(z in sensor_profile_svg.ZONE_ANCHORS for z in fz), "ZONE_ANCHORS has the three fuse-box zones")
fitems = [{"id": f"F{i}", "label": f"Fuse {i}", "status": "green", "zone": z, "side": "centre",
           "location_confidence": "INFERRED", "number": i} for i, z in enumerate(fz, 1)]
fsvg = sensor_profile_svg.profile_svg(fitems, href_prefix="fuse-", legend=[("green", "OK")])
check(all(f'href="#fuse-F{i}"' in fsvg for i in (1, 2, 3)) and fsvg.count("sens-fill") == 4,
      "profile_svg places fuse-box items with href_prefix fuse-")
check(len(sensor_profile_svg.layout(fitems)[0]) == 3, "fuse-box zones place dots")

# --- the page -----------------------------------------------------------
r = client.get(f"/v/{VIN}/sensors")
html = r.text
check(r.status_code == 200, f"page 200 (got {r.status_code})")
for k in ("green", "orange", "red", "grey"):
    check(f"sens-dot sens-{k}" in html, f"dot class sens-{k} present")
ids = [s["id"] for s in SENSORS]
hrefs = set(re.findall(r'<a class="sens-dot[^"]*" href="#(sensor-[^"]+)"', html))
check(hrefs == {f"sensor-{i}" for i in ids if i not in ("cam", "noel")}, "dots link to the placed sensors")
check(all(f'id="{h}"' in html for h in hrefs), "every dot anchor has a list row")
check("Unplaced (2)" in html and "Reverse camera" in html and "Rain sensor" in html, "unplaced tray lists both")
check("/v/%s/electrical?find=rev_cam" % VIN in html, "Set location link for the unplaced sensor with an element")
check("location not sourced yet" in html, "plain text when no element id")
check('class="sens-ring"' in html, "INFERRED sensor gets a dashed ring")
check(">R</text>" in html and ">L</text>" in html, "L and R tags drawn")
check("Check all sensors (read-only)" in html and "Last checked" in html, "check button and last-checked line")
check("/v/%s/code/P0131" % VIN in html, "code links to the base code page")
check("no range yet" in html and "fixture manual" in html, "range / no range shown")
check("e.g. service manual page, TechAuthority, measured on this car" in html, "source placeholder")
check('/static/sensors.css' in html, "sensors.css linked")
check("/v/%s/sensors" % VIN in html and ">Sensors<" in html, "Sensors tab in the tab strip")

r = client.get(f"/v/{VIN}/sensors?status=red")
n_rows = len(re.findall(r'<article class="sens-row"', r.text))
dimmed = len(re.findall(r'sens-dot sens-\w+ sens-dim', r.text))
check(r.status_code == 200 and n_rows == 1, f"status filter narrows the list (rows={n_rows})")
check(dimmed == len(pos) - 1, f"status filter dims the other dots ({dimmed})")
r = client.get(f"/v/{VIN}/sensors?system=Brakes")
check(len(re.findall(r'<article class="sens-row"', r.text)) == 2, "system filter narrows the list")
r = client.get(f"/v/{VIN}/sensors?status=bogus")
check(len(re.findall(r'<article class="sens-row"', r.text)) == len(SENSORS), "bad status ignored")

# --- check / range posts --------------------------------------------------
r = client.post(f"/v/{VIN}/sensors/check")
loc = unquote(r.headers.get("location", ""))
check(r.status_code == 303 and loc.startswith(f"/v/{VIN}/sensors?msg=Checked {len(SENSORS)} sensors: 2 gave a value"),
      f"check POST redirects with count ({loc})")
MODE["check"] = "refused"
loc = unquote(client.post(f"/v/{VIN}/sensors/check").headers.get("location", ""))
check("Could not check: another live session" in loc and "Checked" not in loc, f"refused sweep is not reported as checked ({loc})")
MODE["check"] = "ok"
CALLS["check"].clear()
client.post(f"/v/{VIN}/sensors/check")

# --- readings comparison + CSV ---------------------------------------------
r = client.get(f"/v/{VIN}/sensors/readings")
check(r.status_code == 200 and "Sensor readings" in r.text, "readings page renders")
rp = r.text
head = rp[rp.index("<thead>"):rp.index("</thead>")]
check(head.index("2026-10-26") < head.index("2026-10-25"), "newest check column first")
check(">88<" in rp and ">53<" in rp and ">35<" in rp, "both values and their change shown")
check("lambda" in rp and "no data" in rp, "multi-part values and errors shown")
check("readings.csv" in rp, "page links the CSV")
r = client.get(f"/v/{VIN}/sensors/readings.csv")
body = r.content.decode("utf-8-sig")
check(r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
      and "attachment" in r.headers.get("content-disposition", ""), "CSV downloads")
check(body.splitlines()[0].startswith("check_at,sensor,sensor_id,channel,part") and len(body.strip().splitlines()) == 5,
      "CSV has header plus one line per reading")
check("2026-10-25T19:56:26,Coolant temperature,coolant_temp,engine_coolant_temp,,Coolant temp,53,C," in body,
      "CSV line carries the saved value")
check("/sensors/readings" in client.get(f"/v/{VIN}/sensors").text, "sensor page links the readings page")
check(CALLS["check"] == [VIN], "check_all called once")
MODE["check"] = "mes"
r = client.post(f"/v/{VIN}/sensors/check")
loc = unquote(r.headers.get("location", ""))
check(r.status_code == 303 and "MultiEcuScan is connected" in loc and "Close MultiEcuScan" in loc,
      f"check POST explains MES-connected ({loc})")
page = client.get(r.headers["location"]).text
check("MultiEcuScan is connected" in page, "msg shown on the page")

form = {"sensor_id": "map", "channel": "value", "min": "20", "max": "110", "unit": "kPa", "source": ""}
r = client.post(f"/v/{VIN}/sensors/range", data=form)
check(r.status_code == 303 and "source" in unquote(r.headers["location"]).lower() and not CALLS["range"],
      "range POST with empty source -> error msg, nothing saved")
form["source"] = "service manual p.12"
r = client.post(f"/v/{VIN}/sensors/range", data=form)
check(CALLS["range"] == [("stelvio-2018-2.0", "map", "value", 20.0, 110.0, "kPa", "service manual p.12", "technician")],
      "range POST calls add_range with model/by")
check("saved" in unquote(r.headers["location"]).lower(), "range POST success msg")

# --- fixture HTML + screenshots -----------------------------------------
if "--html" in sys.argv:
    out = Path(sys.argv[sys.argv.index("--html") + 1])
    from cuore.web.static_version import STATIC_DIR  # noqa: E402

    page = client.get(f"/v/{VIN}/sensors").text

    def inline(m):
        f = STATIC_DIR / m.group(1)
        return f"<style>{f.read_text(encoding='utf-8')}</style>" if f.exists() else ""

    page = re.sub(r'<link[^>]*href="/static/([^"?]+)[^"]*"[^>]*>', inline, page)
    page = re.sub(r"<script[^>]*src=[^>]*></script>", "", page)
    out.write_text(page, encoding="utf-8")
    print("wrote", out)

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
