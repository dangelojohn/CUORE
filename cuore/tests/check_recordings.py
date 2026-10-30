"""Checks for drive recordings (services/recordings.py + /v/{vin}/recordings).

A fake live layer stands in for the poller: the recording service's only two
touch points (_status, _snapshot) are replaced, so nothing here can reach an
adapter. CUORE_STATE_DIR is a throwaway directory.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_recordings.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="cuore-rec-")
os.environ["CUORE_STATE_DIR"] = _tmp
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import recordings as R  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
live = {"active": False, "n": 0, "boom": False, "calls": 0}


def fake_status():
    return {"active": live["active"],
            "channels": [{"id": "rpm"}, {"id": "speed"}, {"id": "evil<b>"}] if live["active"] else []}


def fake_snapshot():
    live["calls"] += 1
    if live["boom"]:
        raise RuntimeError("adapter gone")
    live["n"] += 1
    n = live["n"]
    return {"active": live["active"], "channels": {
        "rpm": {"value": 800 + n * 10, "unit": "rpm"},
        "speed": {"value": float(n % 7), "unit": "km/h"},
        "evil<b>": {"value": None if n % 2 else 1.5, "unit": "<i>x</i>"}}}


R._status, R._snapshot = fake_status, fake_snapshot
client = TestClient(create_app(), follow_redirects=False)

# 1. refused without a session
try:
    R.start(VIN, ["rpm"], "x")
    check(False, "start refused without a live session")
except R.RecordingError as e:
    check("No live session" in str(e), "start refused without a live session, with the reason")
check(R.current() is None and R.list(VIN) == [], "nothing created by a refused start")
p = client.get(f"/v/{VIN}/recordings")
check(p.status_code == 200 and "No live session - start one on the Live board" in p.text, "page shows why no recording")
check("Start recording" not in p.text and f"/v/{VIN}/recordings/start" not in p.text, "no Start control without a session")
r = client.post(f"/v/{VIN}/recordings/start", data={"label": "x"})
check(r.status_code == 303 and "No%20live%20session" in r.headers["location"], "POST start without session redirects with the reason")

# 2. start / stop writes header + timestamped rows
live["active"] = True
out = R.start(VIN, ["rpm", "speed"], "EVAP proof drive", rate_hz=10)
time.sleep(0.6)
check(R.current() is not None and R.current()["rows"] >= 2, "sampler running and counting rows")
try:
    R.start(VIN, ["rpm"], "again")
    check(False, "second start refused")
except R.RecordingError:
    check(True, "second start refused while recording")
st = R.stop()
check(st["stopped"] and st["rows"] >= 3 and st["reason"] == "stopped", "stop reports rows and reason")
f = Path(_tmp) / "recordings" / VIN / (out["id"] + ".jsonl")
lines = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
hd = lines[0]
check(hd["type"] == "header" and hd["label"] == "EVAP proof drive" and hd["channels"] == ["rpm", "speed"]
      and hd["units"] == {"rpm": "rpm", "speed": "km/h"} and hd["rate_hz"] == 10 and hd["vin"] == VIN, "header content")
rows = [x for x in lines if x["type"] == "row"]
check(len(rows) == st["rows"] and lines[-1]["type"] == "end", "rows then end line")
check(all(re.match(r"\d{4}-\d\d-\d\dT", x["at"]) for x in rows) and [x["t"] for x in rows] == sorted(x["t"] for x in rows)
      and rows[-1]["t"] > rows[0]["t"], "every row has ISO time and rising seconds")
check(set(rows[0]["v"]) == {"rpm", "speed"}, "only selected channels stored")
check(R.stop()["stopped"] is False, "stop with nothing running is harmless")
check(live["calls"] >= len(rows), "samples came from the (fake) live snapshot only")
try:
    R.start(VIN, ["nope"], "")
    check(False, "unknown channel refused")
except R.RecordingError as e:
    check("nope" in str(e), "channel not in the live session refused")

# 3. max duration
o2 = R.start(VIN, None, "short", rate_hz=10, max_s=0.35)
time.sleep(0.9)
check(R.current() is None, "max duration ends the recording")
r2 = R.load(VIN, o2["id"])
check(r2["end_reason"] == "max_duration" and r2["n_rows"] >= 2 and len(r2["channels"]) == 3, "max_duration reason, all channels by default")

# 4. stop on session stop
o3 = R.start(VIN, ["rpm"], "sess", rate_hz=10)
time.sleep(0.25)
live["active"] = False
time.sleep(0.4)
check(R.current() is None and R.load(VIN, o3["id"])["end_reason"] == "session_stopped", "session stop ends the recording")

# 5. error stops
live["active"] = True
o4 = R.start(VIN, ["rpm"], "err", rate_hz=10)
time.sleep(0.15)
live["boom"] = True
time.sleep(0.4)
live["boom"] = False
check(R.current() is None and R.load(VIN, o4["id"])["end_reason"].startswith("error: RuntimeError"), "snapshot error ends the recording with the reason")

# 6. list / load / traversal
ids = [r["id"] for r in R.list(VIN)]
check(len(ids) == 4 and set(ids) >= {out["id"], o2["id"], o3["id"], o4["id"]}, "list returns all four")
check(R.list(VIN)[0]["start"] >= R.list(VIN)[-1]["start"], "list newest first")
check(R.load(VIN, "missing") is None, "load missing is None")
try:
    R.load(VIN, "../../x")
    check(False, "id traversal refused")
except R.RecordingError:
    check(True, "id traversal refused")
(Path(_tmp) / "recordings" / VIN / "torn.jsonl").write_text(
    '{"type":"header","id":"torn","channels":["rpm"],"units":{},"start":"2026-01-01T00:00:00"}\n'
    '{"type":"row","t":1,"at":"a","v":{"rpm":1}}\n{"type":"ro', encoding="utf-8")
tr = R.load(VIN, "torn")
check(tr["n_rows"] == 1 and tr["end_reason"] == "interrupted", "torn file loads, marked interrupted")
(Path(_tmp) / "recordings" / VIN / "torn.jsonl").unlink()

# 7. pages
p = client.get(f"/v/{VIN}/recordings")
check(p.status_code == 200 and "EVAP proof drive" in p.text and "Saved recordings" in p.text, "list page shows label")
check(f"/v/{VIN}/recordings/{out['id']}.csv" in p.text, "list links CSV")
check("Start recording" in p.text and "Live session running, 3 channels" in p.text
      and "evil&lt;b&gt;" in p.text and "evil<b>" not in p.text, "start control shown with live session; names escaped")
r = client.post(f"/v/{VIN}/recordings/start", data={"label": "via page", "channels": ["rpm", "speed"]})
check(r.status_code == 303 and "started" in r.headers["location"] and R.current() is not None, "POST start begins recording")
time.sleep(0.2)
p = client.get(f"/v/{VIN}/recordings")
check("Recording: " in p.text and "elapsed, 2 channels" in p.text and "Stop recording" in p.text, "call line while recording")
r = client.post(f"/v/{VIN}/recordings/stop")
check(r.status_code == 303 and R.current() is None, "POST stop ends recording")

g = client.get(f"/v/{VIN}/recordings/{o2['id']}")
check(g.status_code == 200, "graph page 200")
check(g.text.count('<svg class="rg"') == 3, "one chart per channel")
check(g.text.count('class="rg-line rg-a"') >= 2, "line drawn per numeric channel")
check("min " in g.text and "max " in g.text and "avg " in g.text and "rpm" in g.text and "km/h" in g.text,
      "min/max/avg and units shown")
check("evil&lt;b&gt;" in g.text and "evil<b>" not in g.text and "<i>x</i>" not in g.text, "channel names and units escaped on graph")
check("rg-axis" in g.text, "shared time axis")
check(client.get(f"/v/{VIN}/recordings/nope").status_code == 404, "unknown recording 404")
check(client.get(f"/v/{VIN}/recordings/..%2Fx").status_code in (404, 422), "traversal id not served")

cmp = client.get(f"/v/{VIN}/recordings/{out['id']}?vs={o2['id']}")
check(cmp.status_code == 200 and 'class="rg-line rg-b"' in cmp.text and 'class="rg-line rg-a"' in cmp.text,
      "compare overlays two series")
check("only in the compared recording" in cmp.text and cmp.text.count('class="rc-chart"') == 3,
      "compare: union of channels, notes channel missing in one")
check("Compared (dashed)" in cmp.text, "compare legend")
check(client.get(f"/v/{VIN}/recordings/{out['id']}?vs=zzz").status_code == 200, "unknown vs ignored")

# 8. CSV
c = client.get(f"/v/{VIN}/recordings/{out['id']}.csv")
check(c.status_code == 200 and c.headers["content-type"].startswith("text/csv")
      and out["id"] in c.headers["content-disposition"], "CSV headers")
tbl = list(csv.reader(io.StringIO(c.text)))
check(tbl[0] == ["time_iso", "seconds", "rpm (rpm)", "speed (km/h)"], "CSV header columns")
check(len(tbl) - 1 == st["rows"] and re.match(r"\d{4}-", tbl[1][0]) and float(tbl[-1][1]) >= float(tbl[1][1]),
      "CSV row count and time columns")
t3 = list(csv.reader(io.StringIO(client.get(f"/v/{VIN}/recordings/{o2['id']}.csv").text)))
check(t3[0][4] == "evil<b> (<i>x</i>)" and "" in [r_[4] for r_ in t3[1:]], "CSV: odd names kept as text, empty cell for missing value")
from cuore.web import recordings_routes as RR  # noqa: E402
check(RR._cell("=1+1") == "'=1+1" and RR._cell(None) == "" and RR._cell(3.5) == 3.5, "CSV formula-injection guard")
check(client.get(f"/v/{VIN}/recordings/nope.csv").status_code == 404, "CSV unknown 404")

# 9. links
lb = client.get(f"/v/{VIN}/liveboard")
check(lb.status_code == 200 and f"/v/{VIN}/recordings" in lb.text and 'id="lb-record"' in lb.text,
      "Live board has Record + Recordings link")
from cuore.web import nav_items as _nav  # noqa: E402
check(any(i["key"] == "recordings" and not i["primary"] for i in _nav.ITEMS),
      "Recordings in the Menu sheet, not the visible row")

print(f"{passed}/{passed + len(failures)} checks passed")
for f_ in failures:
    print("FAIL:", f_)
sys.exit(1 if failures else 0)
