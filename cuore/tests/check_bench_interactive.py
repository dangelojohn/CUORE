"""Checks for the two interactive Bench partials (live proof + fault map), synthetic state in a temp CUORE_STATE_DIR.

  1. live_proof: bands present (fuel 15-85 window), in/out state, "Not recorded" (value None, never 0) for a channel
     with no reading, an unconfirmed label on the vapour-pressure channel, "connect to see live" when no session
  2. live_proof with an open session snapshot: the live value wins, marked live, outside-window state
  3. fault_map: the fault's dependency elements are highlighted (and only those), unplaced ones are listed, a
     similar fault's own elements get the second class, markers are 44 px, every element has a card
  4. no-JS output: details.fold with all cards, marker href -> card, "Electrical path for:" and "Open in layout"
  5. routes: both 200, unknown ?fault= -> 404, unknown VIN still renders
  6. type scale: only var(--fs-*) font sizes in the new css and partials
  7. JS (headless Edge, if present): a fake EventSource drives the markers; error -> back-off 2,4,8,16,32 s then stop

Run:  .venv/Scripts/python.exe cuore/tests/check_bench_interactive.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-benchint-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401
from cuore.app import create_app  # noqa: E402
from cuore.services import bench_interactive as bi, cache, layout_bridge  # noqa: E402
from cuore.web import bench_interactive_routes as bir  # noqa: E402

VIN = "TESTVIN0000000004"
WEB = ROOT / "cuore" / "web"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


FLAGS = {"testFailed": True, "pendingDTC": False, "confirmedDTC": True, "testFailedSinceLastClear": True,
         "warningIndicatorRequested": False}


def obs(kind, at, data, vin=VIN):
    with open(Path(STATE) / "observations.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": at, "kind": kind, "vin": vin, "stream": "serial COM3@115200", "data": data}) + "\n")
    cache.clear()


obs("module_dtcs", "2026-10-20T10:00:00", {"ecu": "ECM", "error": None, "nrc": None,
                                           "dtcs": [{"code": "P0440-00", "flags": FLAGS}]})
# a saved live snapshot: fuel and trim recorded, purge and vapour pressure never recorded
with open(Path(STATE) / "live_snapshots.jsonl", "w", encoding="utf-8") as f:
    f.write(json.dumps({"id": "snap_test_1", "at": "2026-10-20T10:05:00", "layout": "x", "page": "x", "source": "live",
                        "values": {"fuel_level": {"value": 50, "unit": "%"}, "short_fuel_trim_b1": {"value": 3.5, "unit": "%"}},
                        "note": ""}) + "\n")
    f.write(json.dumps({"id": "snap_demo", "at": "2026-10-21T10:05:00", "layout": "x", "page": "x", "source": "demo",
                        "values": {"fuel_level": {"value": 1, "unit": "%"}}, "note": ""}) + "\n")
cache.clear()

# --- 1. live proof, no session
OFF = {"active": False, "channels": {}}
p = bi.live_proof(VIN, snapshot=OFF)
check(p["fault"] and p["fault"]["code"] == "P0440", f"top present fault P0440: {p['fault']}")
rows = {r["channel"]: r for r in p["rows"]}
check(2 <= len(rows) <= 4 and "fuel_level" in rows and "commanded_evap_purge" in rows, f"rows {sorted(rows)}")
fuel = rows["fuel_level"]
check(fuel["band"] and (fuel["band"]["lo"], fuel["band"]["hi"]) == (15.0, 85.0) and fuel["band_pos"] == [15.0, 85.0], "fuel band 15-85 on a 0-100 scale")
check(fuel["value"] == 50.0 and fuel["state"] == "in" and fuel["pos"] == 50.0, f"fuel 50 in window: {fuel['state']} {fuel['value']}")
check(fuel["origin"].startswith("saved live snapshot snap_test_1") and fuel["age"] and fuel["age"] != "live", "fuel: saved snapshot origin and age (demo snapshot ignored)")
purge = rows["commanded_evap_purge"]
check(purge["value"] is None and purge["state"] == "missing" and purge["state_text"] == "Not recorded" and purge["pos"] is None
      and purge["value_text"] == "", "missing channel: not recorded, value None, never 0")
vp = rows.get("evap_vapor_pressure")
check(vp is not None and vp["unconfirmed"] and vp["state"] == "missing", "vapour pressure labelled unconfirmed and not recorded")
check(not p["connected"] and "connect to see live" in p["connect_text"].lower(), "no session: says connect to see live")
check(rows["short_fuel_trim_b1"]["band"] is not None and rows["short_fuel_trim_b1"]["state"] == "in", "trim row uses the sourced generic band")

# --- 2. live session snapshot wins
ON = {"active": True, "channels": {"fuel_level": {"value": 91.2, "unit": "%", "alarm": "ok", "last_error": None},
                                   "commanded_evap_purge": {"value": 0.0, "unit": "%", "alarm": "ok", "last_error": None},
                                   "evap_vapor_pressure": {"value": None, "unit": "Pa", "alarm": "ok", "last_error": "no data"}}}
pl = bi.live_proof(VIN, snapshot=ON)
rl = {r["channel"]: r for r in pl["rows"]}
check(pl["connected"] and rl["fuel_level"]["live"] and rl["fuel_level"]["state"] == "out" and "above" in rl["fuel_level"]["state_text"], "live fuel 91.2 -> outside window (above)")
check(rl["commanded_evap_purge"]["value"] == 0.0 and rl["commanded_evap_purge"]["state"] == "no_band", "a real 0 % purge is a value (no band), not 'not recorded'")
check(rl["evap_vapor_pressure"]["value"] is None and rl["evap_vapor_pressure"]["state"] == "missing", "live None stays not recorded")
check(bi.live_proof(VIN, snapshot={"active": True, "channels": {"fuel_level": {"value": 10.0}}})["rows"][0]["state_text"].endswith("(below)"), "below window")

# --- 3. fault map
fm = bi.fault_map(VIN, "code:ECM:P0440")
want = {h["id"] for h in layout_bridge.code_path("P0440")["path"]}
got = {i["id"] for i in fm["items"] if i["on_fault"]}
check(want and got == want, f"dependency elements = the code path ({len(got)} of {len(want)})")
check(all(i["which"] in ("fault", "both") for i in fm["items"] if i["on_fault"]), "fault elements use the fault class")
side_ids = {m["id"] for m in fm["side"]["marks"]}
check({"purge_valve", "esim"} <= side_ids, f"engine bay / rear-left elements drawn on the side view: {sorted(side_ids)}")
un = {i["id"] for i in fm["unplaced"]}
check("ecm" in un and "ecm" not in side_ids | {m["id"] for m in fm["top"]["marks"]}, "unknown-zone module is listed, not drawn")
check(fm["fault"]["path_href"] == f"/v/{VIN}/electrical?code=P0440", "link to the full electrical path")
check(all(i["layout_href"].endswith("#el-" + i["id"]) and "/electrical?code=P0440" in i["layout_href"] for i in fm["items"]), "Open in layout hrefs")
check(all("measurement" in i and "inspection" in i for i in fm["items"]), "cards carry last measurement / inspection fields")
# second colour: a similar fault with elements the fault does not have
other = layout_bridge.code_path("P0171")["path"]
extra = {h["id"] for h in other} - want
bi_sim = bi._similar_codes
bi._similar_codes = lambda vin, key, limit=4: [{"key": "code:ECM:P0171", "code": "P0171", "label": "P0171", "status": "history"}]
fm2 = bi.fault_map(VIN, "code:ECM:P0440")
bi._similar_codes = bi_sim
sim_only = {i["id"] for i in fm2["items"] if i["which"] == "similar"}
check(extra and sim_only == extra, f"similar-fault-only elements get the second class ({len(sim_only)} of {len(extra)})")
check(all(i["num"].startswith("S") for i in fm2["items"] if i["which"] == "similar"), "similar elements are numbered S1.. (label, not colour alone)")
check(any(i["which"] == "both" for i in fm2["items"]) or not (want & {h["id"] for h in other}), "shared elements marked both")
check(any("S1" in l["mark"] for l in fm2["legend"]) and all(l["text"] for l in fm2["legend"]), "legend has label text for each colour")
check(bi.fault_map(VIN, "code:ECM:P9999") is None, "unknown fault key -> None")
check(bi.fault_map("NOSUCHVIN00000001")["fault"] is None, "unknown VIN -> no fault, no exception")

# --- 4/5. routes and no-JS output
app = create_app()
app.include_router(bir.router)
client = TestClient(app)
r = client.get(f"/v/{VIN}/bench/proof")
check(r.status_code == 200 and "Not recorded" in r.text and "connect to see live" in r.text.lower() and 'data-live="0"' in r.text, "proof route 200, server-rendered snapshot")
check('class="bi-bandlabel"' in r.text and "shaded: EVAP window 15-85 %" in r.text, "proof renders the band label")
r2 = client.get(f"/v/{VIN}/bench/fault-map")
html = r2.text
check(r2.status_code == 200, "fault-map route 200")
check('<details class="fold bf-fold"' in html and " open>" in html.split('<details class="fold bf-fold"')[1][:80], "details.fold listing, open by default (no JS)")
check(all(f'id="bf-card-{i["id"]}"' in html for i in fm["items"]), "every element has a card without JS")
check(all(f'href="#bf-card-{m["id"]}"' in html for m in fm["side"]["marks"]), "markers link to their cards")
check("Electrical path for: " in html and "Open in layout" in html, "Electrical path for: and Open in layout present")
check(client.get(f"/v/{VIN}/bench/fault-map?fault=code:ECM:P0440").status_code == 200, "?fault= known -> 200")
check(client.get(f"/v/{VIN}/bench/fault-map?fault=code:ECM:P0999").status_code == 404, "?fault= unknown -> 404")
check(client.get("/v/NOSUCHVIN00000001/bench/proof").status_code == 200 and client.get("/v/NOSUCHVIN00000001/bench/fault-map").status_code == 200, "unknown VIN renders")

# --- 6. type scale, 44 px
css = (WEB / "static" / "bench_interactive.css").read_text(encoding="utf-8")
css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
sizes = re.findall(r"font-size\s*:\s*([^;}\n]+)", css_nc)
check(sizes and all(re.fullmatch(r"var\(--fs-(xs|sm|md|lg|xl|2xl|3xl)\)", s.strip()) and "xs" not in s and "sm" not in s for s in sizes), f"css font sizes are --fs-md and up: {set(sizes)}")
for tpl in ("_bench_live_proof.html", "_bench_fault_map.html"):
    t = (WEB / "templates" / tpl).read_text(encoding="utf-8")
    check("font-size" not in t and "<style" not in t, f"{tpl}: no inline sizes")
check(re.search(r"\.bf-stage > \.bf-mark \{[^}]*width: 44px; height: 44px", css_nc) is not None, "markers are 44 px")
check("overflow-x" not in css_nc and "min-width: 4" not in css_nc.replace("min-width: 44px", "").replace("min-width: 88px", ""), "no horizontal-scroll constructs")

# --- 7. the script, in headless Edge with a fake EventSource
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if os.path.exists(EDGE):
    frag = client.get(f"/v/{VIN}/bench/proof").text.replace('data-live="0"', 'data-live="1"')
    frag = re.sub(r"<script[^>]*></script>|<link[^>]*>", "", frag)
    fmap_html = re.sub(r"<script[^>]*></script>|<link[^>]*>", "", html)
    js = (WEB / "static" / "bench_interactive.js").read_text(encoding="utf-8")
    harness = f"""<!doctype html><html><body>{frag}{fmap_html}<pre id="out"></pre>
<script>
var delays = [], made = [], out = {{}};
window.requestAnimationFrame = function (f) {{ f(); return 1; }};
var realST = window.setTimeout; window.setTimeout = function (f, ms) {{ delays.push(ms); return 1; }};
window.EventSource = function (u) {{ this.url = u; this.closed = false; made.push(this); }};
window.EventSource.prototype.close = function () {{ this.closed = true; }};
</script>
<script>{js}</script>
<script>
document.addEventListener('DOMContentLoaded', function () {{
try {{
  var es = made[0]; out.url = es.url;
  es.onopen();
  es.onmessage({{data: JSON.stringify({{t: 1, channel: "fuel_level", value: 91.2, unit: "%"}})}});
  var li = document.querySelector('.bi-row[data-channel="fuel_level"]');
  out.fuel = li.querySelector('[data-role=value]').textContent; out.cls = li.className;
  out.state = li.querySelector('[data-role=state-text]').textContent; out.left = li.querySelector('[data-role=marker]').style.left;
  es.onmessage({{data: JSON.stringify({{t: 2, channel: "fuel_level", value: 50, unit: "%"}})}});
  out.state2 = li.querySelector('[data-role=state-text]').textContent;
  es.onmessage({{data: JSON.stringify({{t: 3, channel: "fuel_level", value: "junk"}})}});
  out.after_junk = li.querySelector('[data-role=value]').textContent;
  for (var i = 0; i < 6; i++) {{ es.onerror(); }}
  out.delays = delays.slice(); out.closed_first = es.closed; out.status = document.getElementById("bi-stream").textContent;
  var m = document.querySelector('a.bf-mark[data-card]'); out.fold_open_before = document.getElementById("bf-fold").hasAttribute("open");
}} catch (x) {{ out.err = String(x); }}
document.getElementById("out").textContent = JSON.stringify(out);
}});
</script></body></html>"""
    hp = Path(STATE) / "harness.html"
    hp.write_text(harness, encoding="utf-8")
    proc = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={STATE}/edge",
                           "--virtual-time-budget=3000", "--dump-dom", hp.as_uri()], capture_output=True, text=True, timeout=90)
    m = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout, re.S)
    res = json.loads(re.sub(r"&quot;", '"', re.sub(r"&amp;", "&", m.group(1)))) if m else {}
    check(bool(res) and "err" not in res, f"harness ran: {res or proc.stderr[-300:]}")
    check(res.get("url", "").startswith("/api/live/stream"), "subscribes to the existing SSE stream")
    check(res.get("fuel") == "91.2 %" and "s-out" in res.get("cls", "") and res.get("state", "").startswith("Outside window") and res.get("left") == "91.2%", f"marker moved in place: {res}")
    check(res.get("state2") == "In window", f"state follows the next sample: {res}")
    check(res.get("after_junk") == "50 %", "an unreadable sample never becomes 0")
    check(res.get("delays") == [2000, 4000, 8000, 16000, 32000], f"back-off 2,4,8,16,32 s then stop: {res.get('delays')}")
    check("closed" in res.get("status", "").lower(), f"says the stream closed: {res.get('status')}")
    check(res.get("closed_first") is True, "the errored stream is closed (no EventSource auto-reconnect)")
    check(res.get("fold_open_before") is False, "JS collapses the fold (cards show on tap)")
else:
    print("note: Edge not found, JS harness skipped")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
