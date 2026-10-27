"""Checks for the two interactive Tests partials (live band + test map), synthetic state in a temp CUORE_STATE_DIR.

  1. live_band, synthetic definition + fake snapshot: bands drawn, marker inside / outside, "Not recorded" (value
     None, never 0) for a missing channel, meter reading, a lone-number criterion draws no band, prose criterion skipped
  2. one-tap record: the rendered form posts to the existing result route with the measured value and its source
  3. test_map: the right elements highlighted (the related code's path), unplaced ones listed, cards, links
  4. routes: both 200, unknown test id 404, no-JS output complete
  5. type scale / 44 px / no horizontal scroll constructs
  6. JS (headless Edge, if present): fake EventSource; PASS locks until 3 s in band; FAIL only outside; stamp()

Run:  .venv/Scripts/python.exe cuore/tests/check_tests_interactive.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from html import unescape
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-testsint-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401
from cuore.app import create_app  # noqa: E402
from cuore.services import cache, layout_bridge, tests_bridge, tests_interactive as ti  # noqa: E402
from cuore.web import tests_interactive_routes as tir  # noqa: E402

VIN = "TESTVIN0000000005"
WEB = ROOT / "cuore" / "web"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


# a saved live snapshot: only the short trim was ever recorded
with open(Path(STATE) / "live_snapshots.jsonl", "w", encoding="utf-8") as f:
    f.write(json.dumps({"id": "snap_test_1", "at": "2026-10-20T10:05:00", "layout": "x", "page": "x", "source": "live",
                        "values": {"short_fuel_trim_b1": {"value": 3.5, "unit": "%"}}, "note": ""}) + "\n")
cache.clear()

SYN = {"id": "synthetic_trim", "name": "Synthetic trim check", "systems": ["evap"], "related_codes": ["P0440"],
       "pass_criteria": [
           {"parameter": "short_fuel_trim_b1", "spec": [-10, 10], "unit": "%", "source": "synthetic", "confidence": "CORROBORATED"},
           {"parameter": "long_fuel_trim_b1", "spec": [-10, 10], "unit": "%", "source": "synthetic", "confidence": "CORROBORATED"},
           {"parameter": "charging voltage", "spec": [13.5, 14.7], "unit": "V", "source": "synthetic", "confidence": "CORROBORATED"},
           {"parameter": "parasitic draw", "spec": 50, "unit": "mA", "source": "industry practice", "confidence": "SINGLE-SOURCE"},
           {"parameter": "feel", "spec": "see service manual", "unit": "", "source": "x", "confidence": "UNKNOWN"}]}
OFF = {"active": False, "channels": {}}
ON = {"active": True, "channels": {"short_fuel_trim_b1": {"value": 3.5}, "long_fuel_trim_b1": {"value": 42.0}}}

# --- 1. live band
lb = ti.live_band(VIN, "synthetic_trim", snapshot=OFF, test_def=SYN)
rows = {r["parameter"]: r for r in lb["readings"]}
check(set(rows) == {"short_fuel_trim_b1", "long_fuel_trim_b1", "charging voltage", "parasitic draw"}, f"readings (prose skipped): {sorted(rows)}")
s = rows["short_fuel_trim_b1"]
check(s["kind"] == "live" and s["band"] == {"lo": -10.0, "hi": 10.0} and s["state"] == "in" and s["value"] == 3.5
      and s["origin"].startswith("saved live snapshot snap_test_1"), f"saved value inside band: {s['state']} {s['value']} {s['origin']}")
check(s["band_pos"][0] < s["pos"] < s["band_pos"][1], "marker position inside the shaded band")
l = rows["long_fuel_trim_b1"]
check(l["value"] is None and l["state"] == "missing" and l["state_text"] == "Not recorded" and l["pos"] is None and l["value_text"] == "",
      "channel with no reading: not recorded, never 0")
m = rows["charging voltage"]
check(m["kind"] == "meter" and m["has_band"] and m["value"] is None and m["state"] == "missing", "meter reading: band, no value yet")
p = rows["parasitic draw"]
check(p["kind"] == "meter" and not p["has_band"] and "does not say whether" in p["criterion"], "lone number: no band, direction not guessed")
check(not lb["connected"] and "connect to see live" in lb["connect_text"].lower(), "no session: says connect to see live")
lo = ti.live_band(VIN, "synthetic_trim", snapshot=ON, test_def=SYN)
ro = {r["parameter"]: r for r in lo["readings"]}
check(lo["connected"] and ro["short_fuel_trim_b1"]["live"] and ro["short_fuel_trim_b1"]["state"] == "in", "live value inside band")
check(ro["long_fuel_trim_b1"]["state"] == "out" and "above" in ro["long_fuel_trim_b1"]["state_text"] and ro["long_fuel_trim_b1"]["pos"] == 100.0,
      "live 42 outside the band (above), marker clamped to the scale end")
check(ti.live_band(VIN, "no_such_test") is None, "unknown test -> None")
ti_t = ti.live_band(VIN, "esim_vacuum_test_a", snapshot=OFF)
check(ti_t is not None and ti_t["readings"] == [] and "no numeric pass criterion" in ti_t["note"], "test with only prose criteria: honest note, no bars")

# --- 4/2. routes and the rendered partial
app = create_app()
app.include_router(tir.router)
client = TestClient(app)
r = client.get(f"/v/{VIN}/tests/fuel_trim_o2_observation/live")
html = r.text
check(r.status_code == 200 and 'class="tl-band"' in html and "pass band -10.0 to 10.0" in html.replace("-10 to 10", "-10.0 to 10.0"), "live route 200 with the band")
check("Not recorded" in html and "not recorded" in html, "long trim never read -> not recorded text")
check("Record PASS" in html and "Record FAIL" in html and html.count('name="result"') == 2, "normal PASS / FAIL present without JS")
form = re.search(r'<form class="tl-form" method="post" action="([^"]+)"', html)
check(form and form.group(1) == f"/v/{VIN}/tests/fuel_trim_o2_observation/result", "form posts to the existing result route")
hv = re.search(r'name="value" value="([^"]*)" data-role="hvalue"', html)
rs = re.search(r'name="reason" value="([^"]*)"', html)
check(hv and hv.group(1) == "3.5", f"snapshot value attached: {hv and hv.group(1)}")
check(rs and "saved live snapshot snap_test_1" in unescape(rs.group(1)) and "short_fuel_trim_b1" in rs.group(1), f"source attached: {rs and rs.group(1)}")
# the one-tap record: post exactly what the form carries
post = client.post(form.group(1), data={"value": hv.group(1), "unit": "%", "reason": unescape(rs.group(1)), "result": "pass"}, follow_redirects=False)
ent = tests_bridge._result_entry(VIN, "fuel_trim_o2_observation")
check(post.status_code == 303 and ent["result"] == "pass" and ent["value"] == 3.5 and ent["unit"] == "%"
      and "saved live snapshot" in ent["reason"], f"one-tap record stored value + source: {post.status_code} {ent}")
check("Latest recorded: pass" in client.get(f"/v/{VIN}/tests/fuel_trim_o2_observation/live").text, "latest recorded result shown")
mh = client.get(f"/v/{VIN}/tests/charging_voltage_ripple_test/live").text
check('data-role="meter" name="value"' in mh and "Measured value (V)" in mh and "tl-bar" in mh, "meter test: band + numeric field named value")
check(client.get(f"/v/{VIN}/tests/no_such_test/live").status_code == 404 and client.get(f"/v/{VIN}/tests/no_such_test/map").status_code == 404,
      "unknown test id -> 404 on both routes")

# --- 3. test map
tm = ti.test_map(VIN, "synthetic_trim", test_def=SYN)
want = {h["id"] for h in layout_bridge.code_path("P0440")["path"]}
got = {i["id"] for i in tm["items"]}
check(want and got == want, f"highlighted elements = the related code's path ({len(got)} of {len(want)})")
side_ids = {x["id"] for x in tm["side"]["marks"]}
check({"purge_valve", "esim"} <= side_ids, f"placed elements drawn: {sorted(side_ids)}")
un = {i["id"] for i in tm["unplaced"]}
check("ecm" in un and "ecm" not in side_ids | {x["id"] for x in tm["top"]["marks"]}, "unknown-zone module listed as unplaced, not drawn")
check(all("measurement" in i and "inspection" in i and i["layout_href"].endswith("#el-" + i["id"]) for i in tm["items"]), "cards carry last measurement + Open in layout href")
check(tm["path"]["href"] == f"/v/{VIN}/electrical?code=P0440" and tm["path"]["label"] == tm["items"][0]["label"], "Electrical path for: link")
check(ti.test_map(VIN, "no_such_test") is None, "map: unknown test -> None")
none_def = {"id": "synthetic_none", "name": "No elements", "systems": ["no_such_system"], "related_codes": [], "pass_criteria": []}
check(ti.test_map(VIN, "synthetic_none", test_def=none_def)["items"] == [], "no known element -> nothing highlighted")
mr = client.get(f"/v/{VIN}/tests/evap_test_a_esim_switch/map")
mh2 = mr.text
check(mr.status_code == 200 and "Electrical path for: " in mh2 and "Open in layout" in mh2, "map route 200 with path + layout links")
check('<details class="fold tm-fold" open>' in mh2 and "Not placed on the drawing" in mh2, "no-JS: details listing open; unplaced listed")
mm = ti.test_map(VIN, "evap_test_a_esim_switch")
check(all(f'id="tm-card-evap_test_a_esim_switch-{i["id"]}"' in mh2 for i in mm["items"]) and
      all(f'href="#tm-card-evap_test_a_esim_switch-{x["id"]}"' in mh2 for x in mm["side"]["marks"]), "every element has a card, markers link to them")
# warm speed
t0 = time.perf_counter()
ti.test_map(VIN, "evap_test_a_esim_switch"); ti.live_band(VIN, "fuel_trim_o2_observation", snapshot=OFF)
check(time.perf_counter() - t0 < 0.3, f"warm builders < 0.3 s ({time.perf_counter() - t0:.3f})")

# --- 5. type scale, 44 px
css = (WEB / "static" / "tests_interactive.css").read_text(encoding="utf-8")
css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
sizes = re.findall(r"font-size\s*:\s*([^;}\n]+)", css_nc)
check(sizes and all(re.fullmatch(r"var\(--fs-(md|lg|xl|2xl|3xl)\)", x.strip()) for x in sizes), f"css font sizes are --fs-md and up: {set(sizes)}")
for tpl in ("_tests_live.html", "_tests_map.html"):
    t = (WEB / "templates" / tpl).read_text(encoding="utf-8")
    check("font-size" not in t and "<style" not in t, f"{tpl}: no inline sizes")
check(re.search(r"\.ti-btn \{[^}]*min-height: 44px", css_nc) and re.search(r"\.tm-stage > \.tm-mark \{[^}]*width: 44px; height: 44px", css_nc)
      and re.search(r"\.tl-input \{[^}]*min-height: 44px", css_nc), "buttons, inputs and markers are 44 px")
check("overflow-x" not in css_nc and "min-width: 4" not in css_nc.replace("min-width: 44px", "").replace("min-width: 88px", ""), "no horizontal-scroll constructs")

# --- 6. the script, in headless Edge with a fake EventSource and a controllable clock
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if os.path.exists(EDGE):
    frag = re.sub(r"<script[^>]*></script>|<link[^>]*>", "", client.get(f"/v/{VIN}/tests/fuel_trim_o2_observation/live").text)
    frag = frag.replace('data-live="0"', 'data-live="1"')
    frag_map = re.sub(r"<script[^>]*></script>|<link[^>]*>", "", mh2)
    js = (WEB / "static" / "tests_interactive.js").read_text(encoding="utf-8")
    harness = f"""<!doctype html><html><body>{frag}{frag_map}<pre id="out"></pre>
<script>
var made = [], out = {{}}, clock = 1000000;
Date.now = function () {{ return clock; }};
window.requestAnimationFrame = function (f) {{ f(); return 1; }};
window.setTimeout = function () {{ return 1; }}; window.setInterval = function () {{ return 1; }};
window.EventSource = function (u) {{ this.url = u; this.closed = false; made.push(this); }};
window.EventSource.prototype.close = function () {{ this.closed = true; }};
</script>
<script>{js}</script>
<script>
document.addEventListener('DOMContentLoaded', function () {{
try {{
  var root = document.querySelector('.tl'), b = root.__tl, es = made[0];
  out.locked0 = [b.pass.disabled, b.fail.disabled];
  es.onopen();
  function send(ch, v) {{ es.onmessage({{data: JSON.stringify({{t: 1, channel: ch, value: v, unit: "%"}})}}); }}
  send("short_fuel_trim_b1", 2); send("long_fuel_trim_b1", 1);
  out.t0 = [b.pass.disabled, b.fail.disabled];
  clock += 2000; b.refresh(); out.t2 = b.pass.disabled;
  clock += 1500; b.refresh(); out.t35 = b.pass.disabled; out.fail_in = b.fail.disabled;
  send("short_fuel_trim_b1", 25);
  out.out = [b.pass.disabled, b.fail.disabled];
  send("short_fuel_trim_b1", "junk"); out.junk = root.querySelector('[data-param=short_fuel_trim_b1] [data-role=value]').textContent;
  send("short_fuel_trim_b1", 4); out.reset = b.pass.disabled;
  b.stamp(); out.hv = b.hvalue.value; out.reason = b.reason.value;
  out.url = es.url;
  for (var i = 0; i < 6; i++) es.onerror();
  out.err = [b.pass.disabled, b.fail.disabled, document.querySelector('[data-role=stream]').textContent];
  var tm = document.querySelector('.tm'); out.fold_open = tm.querySelector('.tm-fold').hasAttribute('open');
  var a = tm.querySelector('a.tm-mark[data-card]'); a.click(); out.pop_open = !tm.querySelector('.tm-pop').hidden;
}} catch (x) {{ out.exc = String(x); }}
document.getElementById("out").textContent = JSON.stringify(out);
}});
</script></body></html>"""
    hp = Path(STATE) / "harness.html"
    hp.write_text(harness, encoding="utf-8")
    proc = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={STATE}/edge",
                           "--virtual-time-budget=3000", "--dump-dom", hp.as_uri()], capture_output=True, text=True, timeout=90)
    mo = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout, re.S)
    res = json.loads(unescape(mo.group(1))) if mo else {}
    check(bool(res) and "exc" not in res, f"harness ran: {res or proc.stderr[-300:]}")
    check(res.get("locked0") == [True, True], f"locked while connected: {res.get('locked0')}")
    check(res.get("t0") == [True, True] and res.get("t2") is True, f"PASS still locked before 3 s: {res.get('t0')} {res.get('t2')}")
    check(res.get("t35") is False and res.get("fail_in") is True, f"PASS unlocks after 3 s in band, FAIL stays off: {res.get('t35')} {res.get('fail_in')}")
    check(res.get("out") == [True, False], f"outside the band: PASS off, FAIL offered: {res.get('out')}")
    check(res.get("junk") == "25 %", f"unreadable sample never becomes 0: {res.get('junk')}")
    check(res.get("reset") is True, "leaving and re-entering the band restarts the 3 s hold")
    check(res.get("hv") == "4" and "short_fuel_trim_b1 4 %" in res.get("reason", "") and "live from the open session" in res.get("reason", ""), f"stamp: {res.get('hv')} / {res.get('reason')}")
    check(res.get("url", "").startswith("/api/live/stream"), "subscribes to the existing SSE stream")
    check(res.get("err", [0, 0, ""])[:2] == [True, True], "stream error re-locks PASS and FAIL")
    check(res.get("fold_open") is False and res.get("pop_open") is True, "JS: fold collapsed, tap shows the card inline")
else:
    print("note: Edge not found, JS harness skipped")

print(f"{passed} passed, {len(failures)} failed")
for f_ in failures:
    print("FAIL:", f_)
sys.exit(1 if failures else 0)
