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
           readable=False, readable_note="no channel", last_read=None, values=[]),
    sensor("cam", "Reverse camera", "grey", None, system="Body", element_id="rev_cam", conf="UNKNOWN"),
    sensor("noel", "Rain sensor", "grey", "not_a_zone", system="Body"),
    sensor("iat", "Intake air temp", "green", "engine_bay",
           codes=[{"code": "P0098-00", "module": "ECM", "description": "Air temperature sensor", "state": "superseded",
                   "superseded_by": "not present in SCAN_X at 13:45 on 2026-10-25"}]),
    sensor("wsrl", "Wheel speed RL", "grey", "rear_left_wheel_well", side="left", system="Brakes", bus="can_ch",
           readable=False, readable_note="needs the grey cable", last_read=None, values=[],
           codes=[{"code": "C0035-00", "module": "ABS", "description": "Wheel speed RL", "state": "superseded",
                   "superseded_by": "not present in SCAN_X at 13:45 on 2026-10-25"}]),
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
check(empty.count("<svg") == 2 and empty.count("</svg>") == 2 and "sens-dot" not in empty,
      "side and top views render for an empty sensor list")
check(set(sensor_profile_svg.TOP_ZONES) == {z["id"] for z in sensor_profile_svg.ZONES},
      "every side-view zone has a top-view anchor")
tp = sensor_profile_svg.top_layout([
    {"id": "a", "zone": "engine_bay", "side": "left"}, {"id": "b", "zone": "engine_bay", "side": "right"},
    {"id": "c", "zone": "front_left_wheel_well"}, {"id": "d", "zone": "front_right_wheel_well"},
    {"id": "e", "zone": None}])
check(tp["a"][1] > 200 > tp["b"][1], "top view: left items below the centre line, right items above")
check(tp["c"][1] > 300 and tp["d"][1] < 100, "top view: left wheel at the bottom, right wheel at the top")
check("e" not in tp, "top view: unplaced item not drawn")
sv = sensor_profile_svg.profile_svg([{"id": "a", "zone": "engine_bay"}])
tv = sensor_profile_svg.top_svg([{"id": "a", "zone": "engine_bay"}])
import re as _re
xs = float(_re.search(r'class="sens-fill" cx="([\d.]+)"', sv).group(1))
xt = float(_re.search(r'class="sens-fill" cx="([\d.]+)"', tv).group(1))
check(abs(xs - xt) < 1, f"same front-to-back position in both views ({xs} vs {xt})")
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
from cuore.web import sensor_routes  # noqa: E402
from cuore.services import sensor_direct  # noqa: E402

JOB = {"codes": ["P0131", "C0035"], "syms": [{"text": "Rough idle and a lambda warning on cold start", "at": "2026-10-25T08:00", "id": "aa"}],
       "ctext": {"P0131": "O2 low", "C0035": "Wheel speed sensor rear left"}}
sensor_routes._job_inputs = lambda vin, dossier: (JOB["codes"], JOB["syms"], JOB["ctext"])
STRIP = {"port": "COM3", "baud": 115200, "mes_state": "not_running", "cable": "none", "buses_verified": 0, "buses_total": 3,
         "lock_holder": None, "error": None}
sensor_routes._status_strip = lambda: dict(STRIP)

r = client.get(f"/v/{VIN}/sensors")
html = r.text
check(r.status_code == 200, f"page 200 (got {r.status_code})")
ids = [s["id"] for s in SENSORS]

# the call, built from the open job, the codes and the sensor states
m = re.search(r'<p class="sens-call" id="sens-call">(.*?)</p>', html, re.S)
call_html = m.group(1) if m else ""
call_txt = re.sub(r"<[^>]+>", "", call_html)
check("Fault: #" in call_txt and call_txt.index("Wheel speed FL") < call_txt.index("Upstream O2") and 'href="#sensor-o2f"' in call_html,
      f"call names the faulty sensor and links its row ({call_txt[:80]})")
check("Read now: #" in call_txt and "Intake air temp (P0098 history)" in call_txt,
      f"call: history code on a readable sensor -> 'Read now: #n name (P0098 history)' ({call_txt})")
check(chr(10) not in call_txt.strip() and "can't read" not in call_txt and "never read" not in call_txt and "grey cable" not in call_txt
      and "Wheel speed RL" not in call_txt, "call is ONE line: the can't-read-yet and never-read clauses are not in it")
why_txt = re.sub(r"<[^>]+>", "", html.split('id="sens-why"')[1].split("</details>")[0])
check("Wheel speed RL" in why_txt and "C0035 history" in why_txt and "needs the grey cable" in why_txt and "never read" not in call_txt
      and "no reading yet" in why_txt and "need the grey cable" in why_txt and "no live channel" in why_txt,
      "Why-these fold holds the can't-read-yet and never-read clauses")
check(html.index('id="sens-call"') < html.index('id="sens-go"') < html.index('id="sens-map"'), "Go-to chips and the map come right after the call")
check('id="sens-go"' in html and html.count('class="sens-gochip"') >= 2 and 'href="#sensor-iat"' in html.split('id="sens-go"')[1][:900],
      "Go-to chips link to the sensors in the call")
check('id="sens-why"' in html and "linked by name only" in html and "lambda" in html.split('id="sens-why"')[1][:1500],
      "Why-these fold lists the symptom link by name")
check(html.index('id="sens-call"') < html.index('id="sens-map"') < html.index('id="sens-actions"') < html.index('id="sens-list"'),
      "order: call, map, check action, list")
sensor_routes._job_inputs = lambda vin, dossier: ([], [], {})
t0 = client.get(f"/v/{VIN}/sensors").text
c0 = re.sub(r"<[^>]+>", "", re.search(r'<p class="sens-call" id="sens-call">(.*?)</p>', t0, re.S).group(1))
check("Fault:" in c0 and "Read now:" in c0, "call still built from sensor states with no open job")
sensor_routes._job_inputs = lambda vin, dossier: (JOB["codes"], JOB["syms"], JOB["ctext"])

# the single primary action, disabled with a visible reason when the car is not connected
check(html.count('class="sens-primary"') == 1 and ">Check all sensors<" in html, "one primary action: Check all sensors")
btn = re.search(r'<button type="submit" class="sens-primary"([^>]*)>', html).group(1)
check("disabled" in btn and "Live 0/3 buses verified" in html and "Connect to car" in html.split('id="sens-off"')[1][:300],
      "button disabled with the reason when no bus is verified")
STRIP.update(buses_verified=1)
t1 = client.get(f"/v/{VIN}/sensors").text
check("disabled" not in re.search(r'<button type="submit" class="sens-primary"([^>]*)>', t1).group(1) and 'id="sens-off"' not in t1,
      "button enabled when the car is connected")
STRIP.update(mes_state="connected")
t2 = client.get(f"/v/{VIN}/sensors").text
check("disabled" in re.search(r'<button type="submit" class="sens-primary"([^>]*)>', t2).group(1) and "MultiEcuScan has the adapter" in t2,
      "button disabled when MultiEcuScan holds the adapter")
STRIP.update(mes_state="not_running", buses_verified=0)
more = html.split('id="sens-more"')[1][:900]
check("/sensors/readings" in more and "readings.csv" in more and "/mes-parameters" in more and "/sensors/data" in more,
      "More row: All readings, CSV, MES parameter inventory, Owner data")
check("Last checked" in html, "last-checked line")

# no data entry on the mechanic's page
check("Add a normal range" not in html and "<form class=\"sens-form\"" not in html and 'name="source"' not in html,
      "no range form on /sensors")
check("Set location" not in html, "no Set location link on /sensors")

# rows: one per sensor, grouped by status, details on tap
rows_html = re.findall(r'<details class="sens-item" id="sensor-([^"]+)"', html)
check(sorted(rows_html) == sorted(ids), "one tappable row per sensor")
secs = re.findall(r'<section class="sens-sec" id="sens-sec-(\w+)"', html)
check(secs == ["attention", "never", "ok"], f"groups: needs attention, never read, OK ({secs})")


def sec_ids(name):
    body = re.search(rf'id="sens-sec-{name}".*?</section>', html, re.S).group(0)
    return re.findall(r'id="sensor-([^"]+)"', body)


att, nev, okk = sec_ids("attention"), sec_ids("never"), sec_ids("ok")
check(att[0] == "wssfl" and {"wssfl", "o2f", "iat", "wsrl"} <= set(att) and att.index("o2f") < att.index("wsrl") < att.index("iat"),
      f"needs attention: faults first, then sensors with a code ({att})")
check({"park", "cam", "noel"} <= set(nev) and not set(nev) & set(att), f"never read group ({nev})")
check("map" in okk and "wssfr" in okk and not set(okk) & set(att), "OK group holds the read sensors")
row = re.search(r'<details class="sens-item" id="sensor-map".*?</summary>', html, re.S).group(0)
check("sens-judged" in row and "OK - in range" in row, "judged OK row says in range")
row = re.search(r'<details class="sens-item" id="sensor-wssfr".*?</summary>', html, re.S).group(0)
check("sens-nojudge" in row and "not judged" in row and "OK - read, no range" not in row and "OK - in range" not in row,
      "not-judged OK is a distinct short chip: 'not judged'")
check("1.2 V" in re.search(r'<span class="sens-reading">([^<]*)</span>', row).group(1),
      "collapsed row shows the last reading with its unit")
check('title="2026-10-25T09:00:00"' in row and "Oct 25, 09:00" in row and "2026-10-25 09:00" not in row,
      "timestamps read 'Oct 25, 09:00' with the ISO kept in a title")
check("Oct 25, 09:00" in html.split('id="sens-actions"')[1][:700] and 'class="chip ' in row and "font: " not in row,
      "last-checked time is formatted; row chips use the app's chip class")
_sd = sensor_direct.reading_text({"values": [{"label": "O2", "value": {"lambda": 0.9931}, "unit": ""}]})
_sd2 = sensor_direct.reading_text({"values": [{"label": "Rail", "value": 6.07, "unit": "bar"}]})
check(_sd == "lambda 0.9931" and _sd2 == "6.07 bar", f"reading text: {_sd!r}, {_sd2!r}")
check(".sens-st.sens-nojudge" in open(Path(__file__).resolve().parents[1] / "web/static/sensors.css", encoding="utf-8").read(),
      "CSS gives the not-judged chip its own look")
row = re.search(r'<details class="sens-item" id="sensor-iat".*?</summary>', html, re.S).group(0)
check("history, no live fault" in row and "P0098-00" in row, "superseded code is shown as 'history, no live fault'")
check("(superseded)" not in html, "the word superseded is not shown")
for sid in ids:
    d = re.search(rf'<details class="sens-item" id="sensor-{sid}".*?</summary>', html, re.S).group(0)
    check(d.count('class="sens-line"') == 1, f"exactly one reason line on the row of {sid}")
body = re.search(r'id="sensor-o2f".*?</details>\s*(?=<details|</div>)', html, re.S).group(0)
check(body.count("Upstream O2 is orange") == 1, "the reason text is not repeated in the opened row")
check("Area: general knowledge" in html or "Area: from a source" in html, "short area chip")
check("How sure is this place?" in html and "fixture" in html, "long location text lives in a fold")
check("no normal range on record" in html and "fixture manual" in html, "range / no range shown in details")
check("/v/%s/code/P0131" % VIN in html, "code links to the base code page")
check("/v/%s/electrical?find=rev_cam" % VIN in html, "Electrical path link for the sensor with an element")
check("Not on the picture" in html and "Reverse camera" in html and "Rain sensor" in html, "unplaced sensors listed without editing links")
check('/static/sensors.css' in html, "sensors.css linked")
check("/v/%s/sensors" % VIN in html and ">Sensors<" in html, "Sensors tab in the tab strip")
check("style=" not in html.split('class="sens-page')[1], "no inline styles on the page")

# one photo per sensor
fake_imgs = {"throttle": [{"photo_url": "/p/tb.webp", "part_url": "/part/1", "name": "Throttle Body"},
                          {"photo_url": "/p/tb.webp", "part_url": "/part/1", "name": "Throttle Body"},
                          {"photo_url": "/p/tb2.webp", "part_url": "/part/2", "name": "Throttle Body Gasket"}]}
_orig_photos = sensor_routes._photos
sensor_routes._photos = lambda key, limit=2: fake_imgs.get("throttle") if key in ("map", "o2f") else []
tp = client.get(f"/v/{VIN}/sensors").text
sensor_routes._photos = _orig_photos
check(tp.count('class="sens-photo-frame"') == 2 and tp.count('/p/tb.webp') == 2 and "/p/tb2.webp" not in tp,
      "one photo per sensor, duplicates dropped")
check("Mopar catalogue photo of the part type for: Upstream O2" in tp and "not this car" in tp, "photo labelled by the sensor's own name")
css = open(Path(__file__).resolve().parents[1] / "web/static/sensors.css", encoding="utf-8").read()
check(".sens-photo-frame" in css and "background: #f4f4f1" in css, "photo styles + neutral frame are in CSS")

# the car view: ONE view, Side / Top toggle, count markers, big targets
check(html.count('class="sv-wrap"') == 1 and 'id="sv-side"' in html and 'id="sv-top"' in html and 'class="sv-tabs"' in html,
      "one car view with a Side / Top toggle")
check(html.count("<svg") == 2 and html.count("sm-cluster") >= 2, "side and top drawings (toggled) with count markers")
side_svg = html.split('<svg')[1]
check('class="sm-mark sm-cluster' in side_svg and "Opens the list for this area" in side_svg and "?zone=engine_bay" in side_svg,
      "engine-bay cluster is a count marker that opens the filtered list")
check(re.search(r'sm-count"[^>]*>\s*(\d+)</text>', side_svg).group(1) == str(sum(1 for s in SENSORS if s["zone"] == "engine_bay")),
      "cluster count equals the sensors in that area")
check(re.findall(r'class="sm-hit"[^>]*r="(\d+)"', side_svg) and all(int(x) * 2 * 0.837 >= 44 for x in re.findall(r'class="sm-hit"[^>]*r="(\d+)"', html)),
      "every marker has a tap area of at least 44 px")
check("min-width: 720px" in css and "font: 600 19px" in css, "drawing keeps >= 0.84 scale and labels >= 16 px")
import math  # noqa: E402
for view in ("side", "top"):
    svg_v, groups_v = sensor_profile_svg.map_view_svg([{**s, "number": i} for i, s in enumerate(SENSORS, 1)], view)
    pts = [(g["x"], g["y"]) for g in groups_v]
    check(all(math.dist(a, b) >= 54 for i, a in enumerate(pts) for b in pts[i + 1:]), f"{view} view: tap areas never overlap")
tv_labels = re.findall(r'class="sm-label" x="([\d.]+)" y="([\d.]+)" text-anchor="(\w+)">([^<]+)<', sensor_profile_svg.map_view_svg(
    [{**s, "number": i} for i, s in enumerate(SENSORS, 1)], "top")[0])
boxes = []
for x, y, ta, tx in tv_labels:
    w = 0.56 * 19 * len(tx) + 6
    x = float(x)
    x0 = x - w / 2 if ta == "middle" else x if ta == "start" else x - w
    boxes.append((x0, float(y) - 19, x0 + w, float(y) + 6))
check(all(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1] for i, a in enumerate(boxes) for b in boxes[i + 1:]),
      "top view: no two labels overlap")

# markers: every one labelled (or in the legend), labels next to their own marker, right side not stacked on left
_items = [{**s, "number": i} for i, s in enumerate(SENSORS, 1)]
for view in ("side", "top"):
    _svg, _gs = sensor_profile_svg.map_view_svg(_items, view)
    for g in _gs:
        if not g["label"]:
            continue
        b = g["box"]
        own = sensor_profile_svg._box_dist(b, g["x"], g["y"])
        check(own <= 70, f"{view}: label '{g['label']}' is within 70 px of its marker ({own:.0f})")
        check(all(sensor_profile_svg._box_dist(b, o["x"], o["y"]) > own for o in _gs if o is not g),
              f"{view}: label '{g['label']}' is nearer its own marker than any other")
    _full = sensor_map_html = sensor_profile_svg.sensor_map(_items)
    for g in _gs:
        check(bool(g["label"]) or g["name"] in _full, f"{view}: marker '{g['name']}' has a label or a legend entry")
_sg = sensor_profile_svg.map_view_svg(_items, "side")[1]
check(not any(i.get("side") == "right" or str(i["zone"]).endswith("right_wheel_well") for g in _sg for i in g["items"]),
      "side view: right-side items are not drawn on top of the left ones")
check("+ right side: see Top" in sensor_profile_svg.sensor_map(_items) and "Front wheel wells (1)" in sensor_profile_svg.sensor_map(_items),
      "side view: always-visible '+ right side: see Top' note per area")
_big = [{"id": f"x{i}", "label": "x", "zone": z, "side": "left", "status": "green", "number": i}
        for i, z in enumerate(sensor_profile_svg.ZONE_BY_ID, 1)]
_bs = sensor_profile_svg.map_view_svg(_big, "side")[1]
check(len(_bs) >= 12 and sum(1 for g in _bs if g["label"]) >= len(_bs) // 2, f"side view with every area used: labels fit ({sum(1 for g in _bs if g['label'])}/{len(_bs)})")

# filters
r = client.get(f"/v/{VIN}/sensors?status=red")
n_rows = len(re.findall(r'<details class="sens-item"', r.text))
check(r.status_code == 200 and n_rows == 1, f"status filter narrows the list (rows={n_rows})")
check("sens-dim" in r.text and not re.search(r'sm-single sens-red sens-dim', r.text) and "sm-single sens-red" in r.text,
      "status filter dims the markers with nothing to show, keeps the matching one")
r = client.get(f"/v/{VIN}/sensors?system=Brakes")
check(len(re.findall(r'<details class="sens-item"', r.text)) == 3, "system filter narrows the list")
r = client.get(f"/v/{VIN}/sensors?zone=engine_bay")
check(len(re.findall(r'<details class="sens-item"', r.text)) == sum(1 for s in SENSORS if s["zone"] == "engine_bay")
      and "Showing: Engine bay" in r.text and 'id="sens-showing"' in r.text and "clear</a>" in r.text,
      "area (cluster) filter narrows the list and shows 'Showing: Engine bay - clear'")
check('id="sens-showing"' not in client.get(f"/v/{VIN}/sensors").text, "no Showing chip without a filter")
check("Showing: Dead / not responding, Brakes" in client.get(f"/v/{VIN}/sensors?status=red&system=Brakes").text,
      "Showing chip names status and system filters")
_q = client.get(f"/v/{VIN}/sensors?q=wheel").text
check(_q.index('id="sens-results"') < _q.index('id="sens-call"') < _q.index('id="sens-go"'), "with ?q= the matches come first, above the call")
r = client.get(f"/v/{VIN}/sensors?status=bogus")
check(len(re.findall(r'<details class="sens-item"', r.text)) == len(SENSORS), "bad status ignored")
a_chips = html.count('class="sens-chip ')
check(a_chips >= 4 and "min-height: var(--tap, 44px); padding: 4px 14px" in css, "status chips are 44 px")

# the owner page keeps the data entry, and its POSTs still work
od = client.get(f"/v/{VIN}/sensors/data")
check(od.status_code == 200 and od.text.count("Add a normal range") == len(SENSORS), "owner page has a range form on every sensor")
check("Set location" in od.text and "/v/%s/electrical?find=rev_cam" % VIN in od.text, "owner page has Set location")
check("e.g. service manual page, TechAuthority, measured on this car" in od.text and 'name="back" value="data"' in od.text,
      "owner page range form posts back to the owner page")
r = client.post(f"/v/{VIN}/sensors/range", data={"sensor_id": "map", "channel": "value", "min": "1", "max": "2", "unit": "kPa",
                                                 "source": "bench", "back": "data"})
check(r.status_code == 303 and r.headers["location"].startswith(f"/v/{VIN}/sensors/data?msg="), "range POST from the owner page returns there")
CALLS["range"].clear()

# direct(): call logic on its own
rows_ = sensor_direct.direct([s for s in SENSORS], {s["id"]: i for i, s in enumerate(SENSORS, 1)}, [], {}, [])
check(rows_["rows"]["map"]["kind"] == "ok_judged" and rows_["rows"]["wssfr"]["kind"] == "ok_nojudge", "kinds: judged vs not judged")
quiet = sensor_direct.direct([sensor("a", "Alpha", "green", "roof")], {"a": 1}, [], {}, [])
check(quiet["call"] == "All 1 sensors read; nothing flagged.", f"quiet call ({quiet['call']})")

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

# --- page search -----------------------------------------------------------
def srch(qs):
    t = client.get(f"/v/{VIN}/sensors{qs}").text
    sec = re.search(r'id="sens-results".*?</section>', t, re.S)
    return t, (sec.group(0) if sec else "")


t, sec = srch("?q=wssfl")
check('href="#sensor-wssfl"' in sec and "1 match for" in sec, "search by id jumps to the sensor card")
check('id="sensor-wssfl"' in t and 'id="sens-search"' in t and 'type="search"' in t, "search box + card present")
t, sec = srch("?q=oxygen")
check('href="#sensor-o2f"' in sec, "synonym oxygen finds the O2 sensor")
t, sec = srch("?q=lambda")
check('href="#sensor-o2f"' in sec, "synonym lambda finds the O2 sensor")
t, sec = srch("?q=kpa")
check('href="#sensor-map"' in sec and "o2f" not in sec, "unit kPa finds the manifold pressure sensor")
t, sec = srch("?q=pressure")
check('href="#sensor-map"' in sec, "synonym pressure finds manifold pressure")
t, sec = srch("?q=P0131")
check('href="#sensor-o2f"' in sec, "attached code finds the sensor")
t, sec = srch("?q=dead")
check('href="#sensor-wssfl"' in sec and "wssfr" not in sec, "status word dead finds the red sensor")
t, sec = srch("?q=abs")
check('href="#sensor-wssfl"' in sec and 'href="#sensor-wssfr"' in sec, "synonym abs finds the wheel sensors")
t, sec = srch("?q=wheel+brakes")
check("wssfl" in sec and "map" not in sec.replace("wheel", ""), "two words must both hit")
t, sec = srch("?q=engine+bay")
check("#sensor-eb0" in sec and "#sensor-map" in sec, "zone words found")
t, sec = srch("?q=zzzz")
check("No match for" in sec and "Try a part or system word" in sec and "Clear search" in t, "no-match hint + clear link")
t, sec = srch("?q=<script>alert(1)</script>")
check("<script>alert(1)" not in t and "&lt;script&gt;" in t, "query is escaped")
t, sec = srch("?q=wheel&status=red")
check('href="#sensor-wssfl"' in sec and "wssfr" not in sec and 'name="status" value="red"' in t, "q combined with status filter")
t, sec = srch("?q=wheel&system=Engine")
check("No match for" in sec and "filter is also on" in sec, "q combined with system filter, no hit")
t, sec = srch("?q=wheel")
check("status=red&amp;q=wheel" in t or "status=red&q=wheel" in t, "status chips keep q")
check(client.get(f"/v/{VIN}/sensors?q=" + "x" * 500).status_code == 200, "long q is safe")
check('id="sens-results"' not in client.get(f"/v/{VIN}/sensors").text, "no results block without q")

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
