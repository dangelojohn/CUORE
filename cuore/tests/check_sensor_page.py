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

# the call: ONE line, the one sensor to look at first and why (layout changed: was "Fault: #n ..., Read now: ...")
m = re.search(r'<a class="sens-call sens-call-link" id="sens-call" href="#sensor-([^"]+)">(.*?)</a>', html, re.S)
call_id, call_txt = (m.group(1), re.sub(r"<[^>]+>", "", m.group(2))) if m else ("", "")
check(call_id == "wssfl" and call_txt.startswith("Wheel speed FL:"),
      f"call names the top sensor (the dead one) and links its row ({call_id}: {call_txt[:80]})")
check(chr(10) not in call_txt.strip() and "grey cable" not in call_txt and "Wheel speed RL" not in call_txt,
      "call is ONE line: the can't-read-yet and never-read clauses are not in it")
why_txt = re.sub(r"<[^>]+>", "", html.split('id="sens-why"')[1].split("</details>")[0])
check("Wheel speed RL" in why_txt and "C0035 history" in why_txt and "needs the grey cable" in why_txt and "never read" not in call_txt
      and "no reading yet" in why_txt and "need the grey cable" in why_txt and "no live channel" in why_txt,
      "Why-this fold holds the can't-read-yet and never-read clauses")
check("Also needs a look" in why_txt and "Upstream O2" in why_txt and "Row order" in why_txt, "Why-this fold says what else needs a look and the row order")
check(html.index('id="sens-state"') < html.index('id="sens-call"') < html.index('id="sens-go"') < html.index('id="sens-list"'),
      "order: state line, call, Go-to chips, rows")
_go = html.split('id="sens-go"')[1].split("</nav>")[0]
check(html.count('class="sens-gochip"') >= 4 and "/job" in _go and "/crosschecks" in _go and "readings.csv" in _go
      and "/electrical\"" in _go and "Electrical path for Reverse camera" in _go,
      "Go-to chips: Job, Cross-checks, Electrical path for <sensor>, Data / CSV, Layout")
check('id="sens-why"' in html and "linked by name only" in html and "lambda" in html.split('id="sens-why"')[1][:2500],
      "Why-this fold lists the symptom link by name")
check(html.index('id="sens-call"') < html.index('id="sens-list"') < html.index('id="sens-actions"') < html.index('id="sens-map"'),
      "order: call, rows, check action (disabled: below the rows), the outline map below")
sensor_routes._job_inputs = lambda vin, dossier: ([], [], {})
t0 = client.get(f"/v/{VIN}/sensors").text
check('id="sens-call"' in t0 and "Wheel speed FL" in re.sub(r"<[^>]+>", "", re.search(r'id="sens-call"[^>]*>(.*?)</a>', t0, re.S).group(1)),
      "call still built from sensor states with no open job")
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
rows_html = re.findall(r'<details class="fold sens-item sens-prow" id="sensor-([^"]+)"', html)
check(sorted(rows_html) == sorted(ids), "one tappable row per sensor")
secs = re.findall(r'<details class="fold sens-grp sens-grp-(\w+)" id="sens-sec-\w+"( open)?', html)
check([g for g, _ in secs] == ["fault", "nodata", "ok"], f"groups (layout changed: priority groups, not attention/never/OK): {secs}")
check(dict(secs) == {"fault": " open", "nodata": "", "ok": ""}, "fault group starts open; No data and OK start folded")
check("OK \u2014 6 sensors" in html and "No data \u2014 " in html and "Fault or code on it (" in html, "group summaries say label + count")


def sec_ids(name):
    body = re.search(rf'id="sens-sec-{name}".*?(?=id="sens-sec-|id="sens-actions"|id="sens-cc"|id="sens-map")', html, re.S).group(0)
    return re.findall(r'id="sensor-([^"]+)"', body)


att, nev, okk = sec_ids("fault"), sec_ids("nodata"), sec_ids("ok")
check(att[0] == "wssfl" and {"wssfl", "o2f"} <= set(att) and att.index("wssfl") < att.index("o2f") and "iat" not in att,
      f"fault group: the dead sensor first, then the faulty one; a history code is not a fault ({att})")
check({"park", "cam", "noel", "wsrl"} <= set(nev) and not set(nev) & set(att), f"no-data group ({nev})")
check("map" in okk and "wssfr" in okk and "iat" in okk and not set(okk) & set(att), "OK group holds the read sensors (a history code stays OK)")
row = re.search(r'<details class="fold sens-item sens-prow" id="sensor-map".*?</summary>', html, re.S).group(0)
check("sens-judged" in row and "\u2713 OK" in row and "101 kPa" in row, "judged OK row: reading, OK chip")
row = re.search(r'<details class="fold sens-item sens-prow" id="sensor-wssfr".*?</summary>', html, re.S).group(0)
full = re.search(r'<details class="fold sens-item sens-prow" id="sensor-wssfr".*?</dl>', html, re.S).group(0)
check("sens-nojudge" in row and "\u2713 OK" in row and "not judged" in full and "OK - in range" not in row,
      "not-judged OK keeps the word OK with its own dashed look; 'not judged' is in the opened row")
check("1.2 V" in re.search(r'<span class="sens-reading">([^<]*)</span>', row).group(1),
      "collapsed row shows the last reading with its unit")
check('title="2026-10-25T09:00:00"' in row and "Oct 25, 09:00" in full and "2026-10-25 09:00" not in full and 'class="sens-age"' in row,
      "row shows an age; the ISO time is a title; the opened row reads 'Oct 25, 09:00'")
check("Oct 25, 09:00" in html.split('id="sens-actions"')[1][:700] and 'class="chip ' in row and "font: " not in row,
      "last-checked time is formatted; row chips use the app's chip class")
_sd = sensor_direct.reading_text({"values": [{"label": "O2", "value": {"lambda": 0.9931}, "unit": ""}]})
_sd2 = sensor_direct.reading_text({"values": [{"label": "Rail", "value": 6.07, "unit": "bar"}]})
check(_sd == "lambda 0.9931" and _sd2 == "6.07 bar", f"reading text: {_sd!r}, {_sd2!r}")
check(".sens-st.sens-nojudge" in open(Path(__file__).resolve().parents[1] / "web/static/sensors.css", encoding="utf-8").read(),
      "CSS gives the not-judged chip its own look")
row = re.search(r'<details class="fold sens-item sens-prow" id="sensor-iat".*?</summary>', html, re.S).group(0)
full = re.search(r'<details class="fold sens-item sens-prow" id="sensor-iat".*?</dl>', html, re.S).group(0)
check("P0098 history" in row and "history, no live fault" in full and "P0098-00" in full, "superseded code is shown as 'P0098 history' and, opened, 'history, no live fault'")
check("(superseded)" not in html, "the word superseded is not shown")
for sid in ids:
    d = re.search(rf'<details class="fold sens-item sens-prow" id="sensor-{sid}".*?</details>', html, re.S).group(0)
    check(d.count('class="sens-why-line"') == 1 and d.count('<time class="sens-age"') == 1 and d.count('class="sens-name"') == 1,
          f"one name, one age and one reason line on the row of {sid}")
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
check(html.count('class="sv-wrap"') == 1 and 'id="sv-side"' in html and 'id="sv-top"' in html and 'id="sv-front"' in html
      and 'class="sv-tabs"' in html, "one car view with a Side / Top / Front toggle")
body_html = html.split("</header>", 1)[-1]  # the Menu's tile icons are svgs too
check(body_html.count("<svg") == 4 and html.count("sm-cluster") >= 3, "side, top, front and rear drawings (toggled) with count markers")
side_svg = body_html.split('<svg')[1]
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
n_rows = len(re.findall(r'<details class="fold sens-item sens-prow"', r.text))
check(r.status_code == 200 and n_rows == 1, f"status filter narrows the list (rows={n_rows})")
check("sens-dim" in r.text and not re.search(r'sm-single sens-red sens-dim', r.text) and "sm-single sens-red" in r.text,
      "status filter dims the markers with nothing to show, keeps the matching one")
r = client.get(f"/v/{VIN}/sensors?system=Brakes")
check(len(re.findall(r'<details class="fold sens-item sens-prow"', r.text)) == 3, "system filter narrows the list")
r = client.get(f"/v/{VIN}/sensors?zone=engine_bay")
check(len(re.findall(r'<details class="fold sens-item sens-prow"', r.text)) == sum(1 for s in SENSORS if s["zone"] == "engine_bay")
      and "Showing: Engine bay" in r.text and 'id="sens-showing"' in r.text and "clear</a>" in r.text,
      "area (cluster) filter narrows the list and shows 'Showing: Engine bay - clear'")
check('id="sens-showing"' not in client.get(f"/v/{VIN}/sensors").text, "no Showing chip without a filter")
check("Showing: Dead / not responding, Brakes" in client.get(f"/v/{VIN}/sensors?status=red&system=Brakes").text,
      "Showing chip names status and system filters")
_q = client.get(f"/v/{VIN}/sensors?q=wheel").text
check(_q.index('id="sens-results"') < _q.index('id="sens-call"') < _q.index('id="sens-go"'), "with ?q= the matches come first, above the call")
r = client.get(f"/v/{VIN}/sensors?status=bogus")
check(len(re.findall(r'<details class="fold sens-item sens-prow"', r.text)) == len(SENSORS), "bad status ignored")
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

# --- readings render cleanly; "not available" markers are not shown as readings ----------------------
_o2 = sensor_direct.reading_text({"values": [{"label": "o2 b1s1 wide range", "value": {"lambda": 0.99316, "current_mA": 0.0},
                                              "unit": "lambda/mA"}]})
check(_o2 == "lambda 0.9932, current 0 mA", f"multi-part unit per part: {_o2!r}")
_iat = sensor_direct.reading_text({"values": [{"label": "iat", "unit": "C", "value": {"bitmap": 3, "bank1_sensor1": 26,
                                                                                   "bank1_sensor2": 29}}]})
check(_iat == "sensor 1 26 °C, sensor 2 29 °C", f"bitmap hidden, sensor labels: {_iat!r}")
check(sensor_direct.human_label("throttle position b") == "Throttle position, sensor B", "human label")
_bad = {"values": [{"label": "Boost pressure", "value": -32.767, "unit": "bar", "invalid": "raw -32768 = 'not available' marker"}],
        "status": "grey", "no_valid": True, "readable": True, "reasons": ["No valid reading"], "codes": []}
check(sensor_direct.reading_text(_bad) == "", "sentinel is not shown as a reading")
_row = sensor_direct.sensor_row(_bad)
check(_row["chip"] == "No valid reading" and "not available" in _row["line"] and "32.7" not in _row["reading"],
      "grey row says no valid reading")
_ok = dict(SENSORS[0]); _ok["status"] = "grey"; _ok["no_valid"] = True
_ok["values"] = [dict(_ok["values"][0], value=-32.767, unit="bar", invalid="raw -32768 = 'not available' marker")]
_old = _svc.sensor_health.health
_svc.sensor_health.health = lambda vin: {"vin": vin, "checked_at": None, "sensors": [_ok], "counts": {"green": 0, "orange": 0, "red": 0, "grey": 1}, "unplaced": []}
_pg = client.get(f"/v/{VIN}/sensors").text
_svc.sensor_health.health = _old
check("raw -32768 = &#39;not available&#39; marker" in _pg or "raw -32768 = 'not available' marker" in _pg, "raw marker in detail")
check("-32.767 bar</span>" not in _pg.split('class="sens-reading"')[-1][:80] if 'class="sens-reading"' in _pg else True,
      "collapsed row shows no sentinel number")

_sus = {"values": [{"label": "Throttle position, sensor 2", "value": 0.39, "unit": "%", "invalid": "", "suspect": "disagrees"}],
        "status": "grey", "suspect": True, "readable": True, "codes": [],
        "reasons": ["Suspect - check decoding: Throttle position, sensor 2: disagrees."]}
_sr = sensor_direct.sensor_row(_sus)
check(_sr["chip"] == "Suspect - check decoding" and _sr["kind"] == "never" and _sr["reading"] == "" and "Suspect" in _sr["line"],
      "suspect row: neutral chip, no number in the collapsed row")

# --- Bench-screen layout: priority rows, the one-line call, two states, one-tap inspection -----------------------------
_pn = {"inv": 1, "sus": 2, "unc": 3, "map": 4, "baro": 5, "nod": 6, "good": 7}
_psens = [
    sensor("good", "Good sensor", "green", "roof", last_read="2026-10-25T10:00:00"),
    sensor("nod", "Silent sensor", "grey", "roof", readable=False, last_read=None, values=[]),
    sensor("baro", "Barometric sensor", "green", "roof", channels=["barometric_pressure"], last_read="2026-10-25T09:30:00"),
    sensor("map", "MAP sensor", "green", "roof", channels=["intake_map"], element_id="map_el", last_read="2026-10-25T09:00:00"),
    sensor("unc", "Fuel level sensor", "green", "roof", channels=["ecm_1001"], last_read="2026-10-25T11:00:00"),
    sensor("sus", "Throttle B", "grey", "roof", suspect=True, last_read="2026-10-25T08:00:00",
           reasons=["Suspect - check decoding: Throttle B: disagrees with throttle A."]),
    sensor("inv", "Boost sensor", "grey", "roof", no_valid=True, last_read="2026-10-25T07:00:00",
           reasons=["No valid reading for Boost: raw -32768 = not available marker."],
           values=[{"channel": "value", "label": "Boost", "value": -32.7, "unit": "bar", "invalid": "raw -32768 = not available marker",
                    "read_at": "t", "range": None, "in_range": None}]),
]
_cc = [{"status": "DISAGREE", "title": "MAP vs barometric pressure, engine off", "unit": "kPa", "would_be": "", "tolerance": {"text": "within 10 kPa"},
        "condition_text": "engine stopped (RPM 0)", "suspects": "suspect MAP (PID 0B); Barometric (PID 33) agrees elsewhere", "reason": "",
        "sides": [{"key": "intake_map", "label": "MAP (PID 0B)", "value": 32.0, "confirmed": True},
                  {"key": "barometric_pressure", "label": "Barometric (PID 33)", "value": 100.0, "confirmed": True}]},
       {"status": "UNCONFIRMED DECODING", "title": "Fuel level: PID 2F vs ECM DID 1001", "unit": "%", "would_be": "AGREE", "tolerance": {"text": "within 5 %"},
        "condition_text": "none (always applies)", "suspects": "", "reason": "",
        "sides": [{"key": "fuel_level", "label": "Fuel level (PID 2F)", "value": 50.0, "confirmed": True},
                  {"key": "ecm_1001", "label": "Fuel tank level (ECM DID 1001)", "value": 49.0, "confirmed": False}]}]
_prow = sensor_direct.direct(_psens, _pn, [], {}, [])["rows"]
_pr = sensor_direct.priority_rows(_psens, _prow, _pn, _cc)
check([x["s"]["id"] for x in _pr][:4] == ["inv", "sus", "unc", "map"],
      f"row order: invalid, suspect, unconfirmed decoding, cross-check disagreement ({[x['s']['id'] for x in _pr]})")
check([x["group"] for x in _pr] == ["invalid", "suspect", "suspect", "crosscheck", "crosscheck", "nodata", "ok"]
      and [x["word"] for x in _pr] == ["Invalid", "Suspect", "Unconfirmed decoding", "Suspect", "Suspect", "Not recorded", "OK"],
      f"groups and the shared validity words ({[(x['group'], x['word']) for x in _pr]})")
check(_pr[3]["s"]["id"] == "map" and _pr[3]["sub"] < _pr[4]["sub"], "cross-check: the sensor the check names as the culprit comes first")
check(_pr[0]["reading"] == "no valid value" and _pr[5]["reading"] == "no channel", "no value is shown as a number: invalid / no channel reasons instead")
_pc = sensor_direct.page_call(_pr, {"counts": {"total": 2, "DISAGREE": 1}})
check(_pc["sid"] == "map" and _pc["text"].startswith("MAP sensor: MAP (PID 0B) 32 kPa vs Barometric (PID 33) 100 kPa disagree at engine stopped (RPM 0)")
      and "check its connector" in _pc["text"] and _pc["eid"] == "map_el", f"call: a disagreeing cross-check names the sensor ({_pc['text']})")
_pc2 = sensor_direct.page_call([x for x in _pr if x["group"] != "crosscheck"], None)
check(_pc2["sid"] == "inv" and "Invalid" in _pc2["text"], f"call without a disagreement: the top invalid sensor ({_pc2['text']})")
_pc3 = sensor_direct.page_call([x for x in _pr if x["group"] == "ok"], None)
check(_pc3["text"].startswith("All 1 sensors read plausibly") and "last read" in _pc3["text"] and _pc3["sid"] == "",
      f"call when everything is fine ({_pc3['text']})")
check(sensor_direct.age_text(54000) == "15 h ago" and sensor_direct.age_text(30) == "just now" and sensor_direct.age_text(None) == "never",
      "age phrases")

# the two states
check("<b>Not connected</b> &mdash; tap Connect to car (top of page). Values are from Oct 25, 09:00." in html,
      "not connected: the state line says so and names the date of the values")
STRIP.update(buses_verified=1)
sensor_routes._live_values = lambda: {"value": {"value": 1.5, "unit": "V"}}
tc = client.get(f"/v/{VIN}/sensors").text
check("<b>Connected</b>" in tc and tc.count('class="chip ok sens-live"') == len(SENSORS)
      and "1.5 V" in tc and "live</span>" in tc and 'data-connected="1"' in tc,
      "connected: state line, a live chip + live value on polled sensors, ages tick")
check('data-age="' not in re.search(r'<details class="fold sens-item sens-prow" id="sensor-map".*?</summary>', tc, re.S).group(0), "a live row has no ticking age")
sensor_routes._live_values = lambda: {}
tc2 = client.get(f"/v/{VIN}/sensors").text
check('class="chip ok sens-live"' not in tc2 and 'data-age="' in tc2, "connected without a live session: no live chip, ages still tick")
STRIP.update(buses_verified=0)
check('data-connected="0"' in html and "setInterval" in html, "script ticks only when connected (flag in markup)")

# one-tap inspection on the sensor's electrical element, no typing, never a value edit
_insp: list = []
from cuore.services import electrical_bridge  # noqa: E402
_orig_add = electrical_bridge.add_inspection
electrical_bridge.add_inspection = lambda vin, element, condition, by="technician", note="", media_ids=None: _insp.append((vin, element, condition, by, note)) or {}
check(html.count('class="sens-one"') == 1 and "Checked OK" in html, "Checked OK button only on sensors that have an electrical element")
r = client.post(f"/v/{VIN}/sensors/inspect", data={"sensor_id": "cam", "element": "hacked", "condition": "loose"})
check(r.status_code == 303 and _insp == [(VIN, "rev_cam", "ok", "mechanic", "Checked OK from the Sensors page (one tap)")]
      and "Recorded" in unquote(r.headers["location"]) and r.headers["location"].endswith("#sensor-cam"),
      f"inspect POST records condition ok on the registry's element, ignoring any element/condition in the form ({_insp})")
_insp.clear()
r = client.post(f"/v/{VIN}/sensors/inspect", data={"sensor_id": "map"})
check(r.status_code == 303 and not _insp and "Not recorded" in unquote(r.headers["location"]), "no element: nothing recorded, says so")
electrical_bridge.add_inspection = _orig_add

# value history per sensor, and a CSV per sensor
rh = client.get(f"/v/{VIN}/sensors/readings?sensor=oil_temp").text
check("Oil temperature" in rh and "Coolant temperature" not in rh and "Sensor readings: Oil temperature" in rh, "readings page filters to one sensor")
cv = client.get(f"/v/{VIN}/sensors/readings.csv?sensor=coolant_temp").content.decode("utf-8-sig")
check(len(cv.strip().splitlines()) == 3 and "Oil temperature" not in cv, "CSV filters to one sensor")
check('href="/v/%s/sensors/readings?sensor=map"' % VIN in html and 'readings.csv?sensor=map"' in html, "each row links its value history and its CSV")

# type scale: the new rules use --fs-* tokens only
_newcss = css.split("Sensors page, Bench-screen layout")[1]
check(not re.search(r"font-size:\s*[\d.]+(px|rem)", _newcss), "new CSS: no literal font sizes")

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
