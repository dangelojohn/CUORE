"""Checks for the interactive Sensors outline partial, synthetic state in a temp CUORE_STATE_DIR.

  1. icon colour/shape class follows validity: Invalid / Suspect / Unconfirmed / Not recorded / OK, with a legend
     that names every state
  2. selecting a sensor: it and its cross-check partners are flagged, the card lists the partner readings with an
     agree / disagree word, and the expected band is drawn with an in-band / out-of-band status
  3. a missing value is "Not recorded" (value None, never 0); a channel with no band says "no band on record"
  4. a live snapshot wins over the saved value and re-judges it; no session says "connect to see live"
  5. no-JS output: details.fold with every card, markers link to ?sensor=, links (electrical path, open in layout, CSV)
  6. routes: 200, ?sensor= selects, unknown sensor -> 404, unknown VIN still renders
  7. type scale / 44 px / no horizontal-scroll constructs in the new css and partial
  8. JS (headless Edge, if present): a tap shows the card and highlights partners; a fake EventSource moves the
     marker; junk never becomes 0; an invalid sample is not judged; error -> back-off 2,4,8,16,32 s then stop

Run:  .venv/Scripts/python.exe cuore/tests/check_sensors_interactive.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-sensint-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401
from cuore.app import create_app  # noqa: E402
from cuore.services import cache, sensor_health, sensors_interactive as si  # noqa: E402
from cuore.web import sensors_interactive_routes as sir  # noqa: E402

VIN = "TESTVIN0000000007"
WEB = ROOT / "cuore" / "web"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


GENERAL = "GENERAL KNOWLEDGE (outside fact): area only"


def sensor(sid, label, channels, zone, system="engine", side=None, element=None, codes=()):
    return {"id": sid, "label": label, "system": system, "module": "ECM", "bus": "can_c", "channels": channels,
            "readable": True, "readable_note": "", "element_id": element, "zone": zone, "side": side,
            "location_confidence": "GENERAL" if zone else "UNKNOWN", "location_source": GENERAL if zone else "",
            "code_match": {"descriptions": [], "codes": list(codes)}}


SENSORS = [
    sensor("coolant_temp", "Coolant temperature sensor", ["engine_coolant_temp", "ecm_1003"], "engine_bay"),
    sensor("map_sensor", "MAP sensor", ["intake_map"], "engine_bay", element="maf_map_iat_sensors", codes=["P0106"]),
    sensor("baro_pressure", "Barometric pressure sensor", ["barometric_pressure"], "engine_bay"),
    sensor("fuel_level", "Fuel level sensor", ["fuel_level"], "fuel_tank", system="fuel"),
    sensor("boost_pressure", "Boost pressure sensor", ["ecm_195b"], "engine_bay"),
    sensor("oil_pressure", "Oil pressure sensor", ["ecm_130a"], "engine_bay"),
    sensor("ambient_air_temp", "Ambient air temperature sensor", ["ambient_air_temp"], "engine_bay"),
    sensor("tpms_fr", "Tyre pressure, front right", [], "wheel_fr", system="chassis", side="right"),
    sensor("humidity_sensor", "Humidity sensor", [], None, system="climate"),
]
REG = Path(STATE) / "sensors_test.json"
REG.write_text(json.dumps({"model": "test", "note": "", "side_profile_zones": [], "sensors": SENSORS}), encoding="utf-8")
sensor_health.REGISTRY_PATH = REG

NOW = datetime.now()


def iso(dt):
    return dt.isoformat(timespec="seconds")


def write_checks(rows):
    with open(Path(STATE) / "sensor_checks.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    cache.clear()


# an older check with the engine stopped (MAP and baro agree), then the newest check with the engine running
T1, T2 = NOW - timedelta(hours=5), NOW - timedelta(hours=3)
write_checks([
    {"at": iso(T1), "vin": VIN, "values": {"engine_rpm": 0, "intake_map": 100.0, "barometric_pressure": 100.0},
     "errors": {}, "modules_answered": {"ECM": True}},
    {"at": iso(T2), "vin": VIN,
     "values": {"engine_rpm": 800, "engine_coolant_temp": 95, "intake_map": 50.0, "barometric_pressure": 100.0,
                "fuel_level": -32768, "ecm_195b": 0.01, "ecm_130a": 2.3},
     "errors": {"ecm_1003": "no reply within 30s"}, "modules_answered": {"ECM": True}},
])

# --- 1. validity classes
m = si.outline(VIN)
by = {c["id"]: c for c in m["sensors"]}
check(by["coolant_temp"]["state"] == "ok", f"coolant OK: {by['coolant_temp']['state']} {by['coolant_temp']['why']}")
check(by["fuel_level"]["state"] == "invalid", f"fuel: -32768 marker is Invalid: {by['fuel_level']['state']} {by['fuel_level']['why']}")
check(by["boost_pressure"]["state"] == "suspect", f"195b under 0.1 V is Suspect: {by['boost_pressure']['state']} {by['boost_pressure']['why']}")
check(by["oil_pressure"]["state"] == "unconfirmed", f"unverified decoding only is Unconfirmed: {by['oil_pressure']['state']}")
check(by["ambient_air_temp"]["state"] == "not_recorded" and by["humidity_sensor"]["state"] == "not_recorded", "no reading = Not recorded")
check(by["map_sensor"]["state"] == "ok", f"map OK (valid reading): {by['map_sensor']['state']}")
labels = [l["label"] for l in m["legend"]]
check(labels == ["Invalid", "Suspect", "Unconfirmed", "Not recorded", "OK"], f"legend labels {labels}")
check(sum(l["n"] for l in m["legend"]) == len(SENSORS), "legend counts add up to the sensor count")
check(len({c["glyph"] for c in m["sensors"] if c["state"] != "not_recorded"}) == 4, "each state has its own glyph")
side_marks = {k["id"]: k for k in m["views"]["side"]["marks"]}
top_marks = {k["id"]: k for k in m["views"]["top"]["marks"]}
check(all(side_marks[i]["state"] == by[i]["state"] for i in side_marks), "side marks carry the sensor's validity")
check("tpms_fr" not in side_marks and "tpms_fr" in top_marks, "right-side sensor is on the Top view only")
check("humidity_sensor" in {c["id"] for c in m["unplaced"]} and "humidity_sensor" not in side_marks | top_marks, "no-zone sensor is listed, not drawn")
# 44 px targets never overlap: positions are % of a 400 px reference stage
import itertools  # noqa: E402
from cuore.services import sensors_interactive as _si  # noqa: E402
for view, w, h in (("side", 400.0, None), ("top", 400.0, None)):
    pts = [(k["left"], k["top"]) for k in m["views"][view]["marks"]]
    check(all(0 <= x <= 100 and 0 <= y <= 100 for x, y in pts), f"{view}: marks inside the stage")
html_all = None

# --- 1b. placement: every target near its zone anchor, crowded zone = one cluster, no overlap
from cuore.web import sensor_profile_svg as _sp  # noqa: E402
_syn = [{"id": f"x{i}", "n": i + 1, "zone": "engine_bay", "zone_id": "engine_bay", "side": None, "zone_label": "Engine bay",
         "state": st} for i, st in enumerate(["ok", "unconfirmed", "invalid", "ok", "not_recorded", "suspect"])]
_syn += [{"id": "w1", "n": 7, "zone": "roof", "zone_id": "roof", "side": None, "zone_label": "Roof", "state": "ok"}]
_pl = _si._place(_syn, "side")
_cl = [k for k in _pl["marks"] if k["count"] > 1]
check(len(_cl) == 1 and _cl[0]["count"] == 6 and _cl[0]["id"] == "x2" and sorted(_cl[0]["ids"]) == sorted(f"x{i}" for i in range(6)),
      f"6 sensors in one zone -> ONE cluster, count 6, worst (invalid) is its link: {_cl}")
check(set(_pl["ids"]) == {x["id"] for x in _syn} and not _pl["unfit"], "cluster members count as placed")
for view in ("side", "top"):
    pl = _si._place(m_sens := [{"id": c["id"], "n": c["n"], "zone": c["zone"], "zone_id": c["zone_id"], "side": c.get("side"),
                                "state": c["state"], "zone_label": c["zone_label"]} for c in m["sensors"]], view)
    pw = 400.0
    ph = (_sp._VB_H if view == "side" else _sp._TOP_H) + 2 * _si._PAD_Y[view]
    ph *= pw / (_sp._VB_W if view == "side" else _sp._TOP_W)
    pts = [(k["left"] / 100 * pw, k["top"] / 100 * ph) for k in pl["marks"]]
    check(all(((px - k["anchor"][0]) ** 2 + (py - k["anchor"][1]) ** 2) ** .5 <= _si.MAX_ANCHOR_D + 1
              for (px, py), k in zip(pts, pl["marks"])), f"{view}: every target within {_si.MAX_ANCHOR_D} px of its zone anchor")
    check(all(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5 >= 44 for i, a in enumerate(pts) for b in pts[i + 1:]),
          f"{view}: no two targets overlap")
check(all(((a["px"][0] - b["px"][0]) ** 2 + (a["px"][1] - b["px"][1]) ** 2) ** .5 >= 44
          for i, a in enumerate(_pl["marks"]) for b in _pl["marks"][i + 1:]), "synthetic crowd: no overlap")
check(_si._PAD_Y["side"] <= 40 and _si._PAD_Y["top"] <= 40, "padding is small: no sky/ground band for stray marks")
_cm = [k for k in si.outline(VIN)["views"]["side"]["marks"] if k["cluster"]]
check(all(k["members"] and k["count"] == len(k["members"]) for k in _cm), "outline() cluster marks carry their member cards")

# --- 2. selecting a sensor
sel = si.outline(VIN, "map_sensor", snapshot={"active": False, "channels": {}})
card = sel["selected_card"]
check(sel["selected"] == "map_sensor" and card and card["id"] == "map_sensor", "selected card is map_sensor")
check("baro_pressure" in card["partners"], f"cross-check partner found: {card['partners']}")
sm = {i: k for k in sel["views"]["side"]["marks"] for i in k["ids"]}   # a crowded zone is one cluster mark
check(sm["map_sensor"]["sel"] and sm["baro_pressure"]["partner"] and not (sm["coolant_temp"]["partner"] and sm["coolant_temp"] is not sm["baro_pressure"]), "selected + partner flagged, others not")
words = {r["word"] for r in card["rules"]}
check(card["rules"] and words <= set(si.RULE_WORD.values()) and words & {"Agree", "Disagree", "Unconfirmed decoding", "Condition not met", "Not recorded"}, f"partner rule words {words}")
mrow = card["rows"][0]
check(mrow["band"] and (mrow["band"]["lo"], mrow["band"]["hi"]) == (20.0, 35.0), f"known-good band for MAP: {mrow['band']}")
check(mrow["value"] == 50.0 and mrow["state"] == "out" and "above" in mrow["state_text"], f"MAP 50 kPa at 800 rpm is out of band: {mrow['state']} {mrow['state_text']}")
check(mrow["band"]["applies"] is True, "idle band applies: engine speed was recorded in the same check")
check(mrow["age"] and mrow["age"] != "live", f"age shown: {mrow['age']}")
inb = si.outline(VIN, "coolant_temp", snapshot={"active": False, "channels": {}})["selected_card"]["rows"][0]
check(inb["band"] is None and inb["state"] == "no_band" and inb["state_text"] == "No band on record",
      f"platform-gated band: none for a VIN of unknown platform -> 'No band on record': {inb['state_text']}")
# the old check (engine stopped): the idle band is NOT applied to a stopped engine
# --- 3. missing value, no band
cool = si.outline(VIN, "coolant_temp", snapshot={"active": False, "channels": {}})["selected_card"]
miss = [r for r in cool["rows"] if r["channel"] == "ecm_1003"][0]
check(miss["value"] is None and miss["missing"] and miss["state"] == "missing" and miss["state_text"] == "Not recorded" and miss["value_text"] == "", "missing channel: Not recorded, value None, never 0")
check(all(not (r["missing"] and r["value"] == 0) for c in m["sensors"] for r in c["rows"]), "no missing row has value 0")
oil = si.outline(VIN, "oil_pressure", snapshot={"active": False, "channels": {}})["selected_card"]["rows"][0]
check(oil["validity"] == "unconfirmed" and oil["state"] in ("not_judged", "no_band"), f"unconfirmed value is not judged: {oil['state_text']}")
inv = si.outline(VIN, "fuel_level", snapshot={"active": False, "channels": {}})["selected_card"]["rows"][0]
check(inv["validity"] == "invalid" and inv["state"] in ("not_judged", "no_band") and inv["pos"] is None, f"invalid value is not plotted: {inv['state_text']}")
check(by["tpms_fr"]["rows"] == [], "sensor with no live channel has no rows")

# --- 4. live snapshot
ON = {"active": True, "channels": {"intake_map": {"value": 30.0, "unit": "kPa", "alarm": "ok", "last_error": None},
                                   "engine_rpm": {"value": 760.0, "unit": "rpm"}}}
live = si.outline(VIN, "map_sensor", snapshot=ON)
lr = live["selected_card"]["rows"][0]
check(live["connected"] and lr["live"] and lr["value"] == 30.0 and lr["state"] == "in" and lr["age"] == "live", f"live value wins and is judged: {lr['state_text']}")
off = si.outline(VIN, "map_sensor", snapshot={"active": False, "channels": {}})
check(not off["connected"] and "connect to see live" in off["connect_text"].lower(), "no session: says connect to see live")
lj = si.outline(VIN, "map_sensor", snapshot={"active": True, "channels": {"intake_map": {"value": None}}})["selected_card"]["rows"][0]
check(not lj["live"] and lj["value"] == 50.0, "a live None never replaces the saved value")
lz = si.outline(VIN, "map_sensor", snapshot={"active": True, "channels": {"intake_map": {"value": 30.0}, "engine_rpm": {"value": 3000}}})["selected_card"]["rows"][0]
check(lz["state"] == "not_judged", f"idle band not applied at 3000 rpm: {lz['state_text']}")
check(si.outline(VIN, "no_such_sensor") is None, "unknown sensor -> None")

# --- 5/6. routes and no-JS output
app = create_app()
app.include_router(sir.router)
client = TestClient(app)
r0 = client.get(f"/v/{VIN}/sensors/outline")
check(r0.status_code == 200, f"route 200 ({r0.status_code})")
t0 = time.time()
r = client.get(f"/v/{VIN}/sensors/outline?sensor=map_sensor")
warm = time.time() - t0
html = r.text
check(r.status_code == 200 and warm < 0.3, f"?sensor= 200, warm render {warm:.3f}s < 0.3 s")
check('<details class="fold si-fold"' in html and " open>" in html.split('<details class="fold si-fold"')[1][:80], "details.fold, open by default (no JS)")
check(all(f'id="si-card-{c["id"]}"' in html for c in m["sensors"]), "every sensor has a card without JS")
check('class="si-pop" id="si-pop"' in html and "hidden" not in html.split('id="si-pop"')[1][:80], "?sensor= opens the card inline")
check("hidden" in r0.text.split('id="si-pop"')[1][:80], "no selection: the card area is hidden")
check('href="/v/' + VIN + '/sensors/outline?sensor=map_sensor#si-pop"' in html, "markers link to ?sensor=<id> (no JS)")
check("is-sel" in html and "is-partner" in html, "selected and partner rings in the markup")
check(all(f'si-st-{k}' in html for k in ("invalid", "suspect", "unconfirmed", "not_recorded", "ok")), "every validity class is rendered")
for word in ("Invalid", "Suspect", "Unconfirmed", "Not recorded", "OK"):
    check(f"<b>{word}</b>" in html, f"legend names {word}")
check("Electrical path for:" in html and "Open in layout" in html and "readings.csv" in html, "links: electrical path, open in layout, CSV")
check("in band" in html.lower() or "out of band" in html.lower(), "band status in words")
check("Out of band (above)" in html and "expected 20 to 35 kPa" in html, "band bar label and status")
check("Not recorded" in html and "connect to see live" in html.lower() and 'data-live="0"' in html, "snapshot: connect to see live, data-live=0")
check(client.get(f"/v/{VIN}/sensors/outline?sensor=nope").status_code == 404, "unknown sensor -> 404")
check(client.get("/v/NOSUCHVIN00000001/sensors/outline").status_code == 200, "unknown VIN renders")
check("sensors_interactive_outline" in sir.templates.env.globals, "Jinja global registered on import")

# --- 7. type scale, 44 px, no horizontal scroll
css = (WEB / "static" / "sensors_interactive.css").read_text(encoding="utf-8")
css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
sizes = re.findall(r"font-size\s*:\s*([^;}\n]+)", css_nc)
check(sizes and all(re.fullmatch(r"var\(--fs-(md|lg|xl|2xl|3xl)\)", s.strip()) for s in sizes), f"css font sizes are --fs-md and up: {set(sizes)}")
tpl = (WEB / "templates" / "_sensors_interactive.html").read_text(encoding="utf-8")
check("font-size" not in tpl and "<style" not in tpl, "partial: no inline sizes")
check(re.search(r"\.si-mark \{[^}]*width: 44px; height: 44px", css_nc) is not None, "markers are 44 px")
check(re.search(r"\.si-pl, \.si-btn \{[^}]*min-height: 44px", css_nc) is not None, "links and buttons are 44 px")
check("overflow-x" not in css_nc and "white-space: nowrap" not in css_nc, "no horizontal-scroll constructs")
check("var(--fam-chassis)" in css_nc and "dashed" in css_nc and "var(--sev-returned)" in css_nc, "colour tokens (light/dark from the theme)")
js = (WEB / "static" / "sensors_interactive.js").read_text(encoding="utf-8")
check("document.hidden" in js and "BACKOFF_S" in js and "EventSource" in js, "JS: pause when hidden, back-off, SSE")

# --- 8. the script, in headless Edge with a fake EventSource
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if os.path.exists(EDGE):
    frag = re.sub(r"<script[^>]*></script>|<link[^>]*>", "", html.replace('data-live="0"', 'data-live="1"'))
    harness = f"""<!doctype html><html><body>{frag}<pre id="out"></pre>
<script>
var delays = [], made = [], out = {{}};
window.requestAnimationFrame = function (f) {{ f(); return 1; }};
window.setTimeout = function (f, ms) {{ delays.push(ms); return 1; }};
window.EventSource = function (u) {{ this.url = u; this.closed = false; made.push(this); }};
window.EventSource.prototype.close = function () {{ this.closed = true; }};
</script>
<script>{js}</script>
<script>
document.addEventListener('DOMContentLoaded', function () {{
try {{
  var es = made[0]; out.url = es.url; es.onopen();
  out.fold_open = document.getElementById("si-fold").hasAttribute("open");
  var tap = function (id) {{ return document.querySelector('.si-stage > a.si-mark[data-sensor="' + id + '"]') || document.querySelector('.si-members a[data-sensor="' + id + '"]'); }};
  var mk = tap('coolant_temp');
  out.mk_pre = mk.className;
  mk.click();
  out.pop_hidden = document.getElementById("si-pop").hidden;
  out.pop_title = document.querySelector("#si-pop .si-ch").textContent.trim();
  out.sel = document.querySelectorAll(".si-stage > .si-mark.is-sel").length;
  var mp = tap('map_sensor'); mp.click();
  out.partner = document.querySelector('.si-stage > a.si-mark[data-sensor="baro_pressure"], .si-stage > a.si-mark[data-members~="baro_pressure"]').className.indexOf("is-partner") > -1;
  out.sel_after = document.querySelector('.si-stage > a.si-mark[data-sensor="map_sensor"], .si-stage > a.si-mark[data-members~="map_sensor"]').className.indexOf("is-sel") > -1;
  es.onmessage({{data: JSON.stringify({{t: 1, channel: "engine_rpm", value: 760, unit: "rpm"}})}});
  es.onmessage({{data: JSON.stringify({{t: 2, channel: "intake_map", value: 30, unit: "kPa"}})}});
  var li = document.querySelector('#si-pop .si-row[data-channel="intake_map"]');
  out.val = li.querySelector('[data-role=value]').textContent; out.state = li.querySelector('[data-role=state-text]').textContent;
  out.left = li.querySelector('[data-role=marker]').style.left; out.age = li.querySelector('[data-role=age]').textContent;
  es.onmessage({{data: JSON.stringify({{t: 3, channel: "intake_map", value: "junk"}})}});
  out.after_junk = li.querySelector('[data-role=value]').textContent;
  es.onmessage({{data: JSON.stringify({{t: 4, channel: "intake_map", value: 60, unit: "kPa"}})}});
  out.state_out = li.querySelector('[data-role=state-text]').textContent;
  es.onmessage({{data: JSON.stringify({{t: 5, channel: "intake_map", value: -32768, unit: "kPa"}})}});
  out.state_na = li.querySelector('[data-role=state-text]').textContent; out.marker_hidden = li.querySelector('[data-role=marker]').hidden;
  es.onmessage({{data: JSON.stringify({{t: 6, channel: "engine_rpm", value: 3000, unit: "rpm"}})}});
  es.onmessage({{data: JSON.stringify({{t: 7, channel: "intake_map", value: 30, unit: "kPa"}})}});
  out.state_rpm = li.querySelector('[data-role=state-text]').textContent;
  for (var i = 0; i < 6; i++) {{ es.onerror(); }}
  out.delays = delays.slice(); out.closed_first = es.closed; out.status = document.getElementById("si-stream").textContent;
  document.querySelector("#si-pop .si-pop-close").click(); out.closed_pop = document.getElementById("si-pop").hidden;
  out.sel_cleared = document.querySelectorAll(".si-stage > .si-mark.is-sel, .si-stage > .si-mark.is-partner").length;
}} catch (x) {{ out.err = String(x); }}
document.getElementById("out").textContent = JSON.stringify(out);
}});
</script></body></html>"""
    hp = Path(STATE) / "harness.html"
    hp.write_text(harness, encoding="utf-8")
    proc = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={STATE}/edge",
                           "--virtual-time-budget=3000", "--dump-dom", hp.as_uri()], capture_output=True, text=True, timeout=90)
    mo = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout, re.S)
    res = json.loads(re.sub(r"&quot;", '"', re.sub(r"&amp;", "&", mo.group(1)))) if mo else {}
    check(bool(res) and "err" not in res, f"harness ran: {res or proc.stderr[-300:]}")
    check(res.get("url", "").startswith("/api/live/stream"), "subscribes to the existing SSE stream")
    check(res.get("fold_open") is False, "JS collapses the fold (cards show on tap)")
    check(res.get("pop_hidden") is False and "Coolant temperature" in res.get("pop_title", "") and res.get("sel", 0) >= 1, f"a tap shows the card and ring: {res}")
    check(res.get("partner") is True and res.get("sel_after") is True, "a tap highlights the sensor and its partner")
    check(res.get("val") == "30 kPa" and res.get("state") == "In band" and res.get("left", "").startswith("55.5") and res.get("age") == "live", f"marker moved in place: {res}")
    check(res.get("after_junk") == "30 kPa", "an unreadable sample never becomes 0")
    check(res.get("state_out", "").startswith("Out of band (above)"), f"next sample is judged: {res.get('state_out')}")
    check(res.get("state_na", "").startswith("Not judged: invalid") and res.get("marker_hidden") is True, f"a not-available marker is invalid, not plotted: {res.get('state_na')}")
    check(res.get("state_rpm", "").startswith("Not judged: this band is for"), f"idle band not applied at 3000 rpm: {res.get('state_rpm')}")
    check(res.get("delays") == [2000, 4000, 8000, 16000, 32000], f"back-off 2,4,8,16,32 s then stop: {res.get('delays')}")
    check("closed" in res.get("status", "").lower() and res.get("closed_first") is True, f"says the stream closed, errored stream closed: {res.get('status')}")
    check(res.get("closed_pop") is True and res.get("sel_cleared") == 0, "Close hides the card and clears the rings")
else:
    print("note: Edge not found, JS harness skipped")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
