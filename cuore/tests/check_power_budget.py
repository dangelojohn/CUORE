"""Checks for the power and ground budget (feature #6): record a measured
voltage drop, read it back, judge it against cuore/data/voltage_drop_limits.json,
before/after text, bad numbers refused, and the page renders.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_power_budget.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-powerbudget-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import power_budget as pb  # noqa: E402
from cuore.web import power_budget_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'ok' if cond else 'FAIL'}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


app = create_app()
if not any(getattr(r, "path", "") == "/v/{vin}/power-budget" for r in app.routes):
    app.include_router(power_budget_routes.router)
client = TestClient(app)

# 0. nothing measured: G003A first, with the directing call
r0 = client.get(f"/v/{VIN}/power-budget")
check("page renders (200) with nothing measured", r0.status_code == 200, str(r0.status_code))
check("G003A call to measure before cleaning",
      "not measured yet" in r0.text and "before cleaning" in r0.text and "G003A" in r0.text)
check("unmeasured segment says Not measured, not 0 V", "Not measured" in r0.text and "0.000 V" not in r0.text)

# 1. record + read back
rec = pb.record(VIN, "g003a", volts="0.42", condition="running_loads", preset="p0",
                tag="before cleaning", by="test", meter="test meter")
back = pb.measurements(VIN, "g003a")
check("measurement recorded and read back",
      len(back) == 1 and back[0]["id"] == rec["id"] and back[0]["volts"] == 0.42
      and back[0]["to_point"] == "Battery negative post" and back[0]["tag"] == "before cleaning")
check("other VIN sees nothing", pb.measurements("OTHERVIN123", "g003a") == [])

# 2. verdict uses the limit table
lim = pb.limits()["sides"]["ground"]
panel = pb.panel(VIN, "g003a")
seg = panel["segments"][0]
check("0.42 V on a ground is over the limit table's ground limit",
      0.42 > lim["watch_max"] and seg["verdict"]["key"] == "over", seg["verdict"]["key"])
check("judge: good / watch / over / engine-off boundaries",
      pb.judge(lim["good_max"], "ground", "running")["key"] == "good"
      and pb.judge(lim["watch_max"], "ground", "running")["key"] == "watch"
      and pb.judge(lim["watch_max"] + 0.001, "ground", "running")["key"] == "over"
      and pb.judge(0.9, "ground", "engine_off")["key"] == "no_load")
check("verdict carries its basis text", "outside fact" in seg["limit"]["basis"])
check("call asks for the after-cleaning reading", "Clean it" in panel["call"]["text"])

# 3. before / after comparison
pb.record(VIN, "g003a", volts="0.05", condition="running_loads", preset="p0", tag="after cleaning")
panel2 = pb.panel(VIN, "g003a")
cmp_rows = [r["compare"] for r in panel2["segments"][0]["readings"] if r["compare"]]
check("before/after text", cmp_rows and cmp_rows[0]["text"] == "0.42 V before cleaning → 0.05 V after",
      str(cmp_rows and cmp_rows[0]["text"]))
check("after reading is now the latest verdict (good)",
      panel2["segments"][0]["verdict"]["key"] == "good" or panel2["segments"][0]["headline"] is not None)

# 4. bad numbers refused, nothing written
n = len(pb.measurements(VIN))
bad = ["nan", "inf", "-inf", "-0.1", "abc", "", "99", "1e999"]
refused = 0
for b in bad:
    try:
        pb.record(VIN, "g003a", volts=b, condition="running", preset="p0")
    except ValueError:
        refused += 1
check("NaN / inf / negative / text / blank / absurd volts all refused", refused == len(bad), f"{refused}/{len(bad)}")
for kw, label in [(dict(condition="bogus"), "unknown condition"),
                  (dict(element="nope"), "unknown element"),
                  (dict(tag="whenever"), "unknown tag")]:
    args = dict(volts="0.1", condition="running", preset="p0")
    args.update(kw)
    el = args.pop("element", "g003a")
    try:
        pb.record(VIN, el, **args)
        ok = False
    except ValueError:
        ok = True
    check(f"{label} refused", ok)
check("refusals wrote nothing", len(pb.measurements(VIN)) == n)

# 5. form POST: bad number redirects back with an error; good one saves
post_bad = client.post(f"/v/{VIN}/power-budget/measure", data={
    "element": "g003a", "preset": "p0", "condition": "running", "volts": "nan"},
    follow_redirects=False)
check("bad POST -> 303 with error=", post_bad.status_code == 303 and "error=" in post_bad.headers["location"],
      str(post_bad.status_code))
post_ok = client.post(f"/v/{VIN}/power-budget/measure", data={
    "element": "g003a", "preset": "p0", "condition": "wiggle", "volts": "0,31",
    "redirect_to": "https://evil.example/x"}, follow_redirects=False)
check("good POST -> 303 to a local page with saved=1 (foreign redirect ignored)",
      post_ok.status_code == 303 and post_ok.headers["location"].startswith("/v/")
      and "saved=1" in post_ok.headers["location"], post_ok.headers.get("location", ""))

# 6. pages + JSON
page = client.get(f"/v/{VIN}/power-budget")
check("overview lists the measured path with before/after and limits",
      page.status_code == 200 and "0.42 V before cleaning" in page.text and "Reference limits" in page.text)
elem = client.get(f"/v/{VIN}/power-budget/g003a?saved=1")
check("element page renders with form and saved note",
      elem.status_code == 200 and 'name="volts"' in elem.text and "Measurement saved" in elem.text)
check("unknown element page is 404", client.get(f"/v/{VIN}/power-budget/nope").status_code == 404)
api = client.get(f"/api/vehicles/{VIN}/power-budget")
j = api.json() if api.status_code == 200 else {}
check("JSON endpoint lists the path and its readings",
      api.status_code == 200 and j.get("paths") and j["paths"][0]["segments"][0]["readings"], str(api.status_code))

# 7. embeddable partial through the Jinja global
tpl = power_budget_routes._shared_templates.env.from_string(
    '{% with pb = power_budget_panel(vin, "g003a") %}{% include "_power_budget_panel.html" %}{% endwith %}')
html = tpl.render(vin=VIN, static_url=lambda n: "/static/" + n)
check("partial renders via power_budget_panel()", "pb-panel" in html and "Frame ground G003A" in html)

print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
