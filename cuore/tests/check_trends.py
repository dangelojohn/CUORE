"""Checks for drift/trend tracking across visits (cuore/services/trends.py, cuore/web/trends_routes.py).

Synthetic readings only (no car, no real state files): CUORE_STATE_DIR points at a throwaway
directory before cuore is imported. Proves that

  1. a falling series is flagged, with its sample count in the wording;
  2. too few samples gives "not enough data (N samples)" and no projection;
  3. non-comparable readings (engine running, not rested, invalid marker) are excluded, with reasons;
  4. values stored with the old ecm_195a decoding are re-decoded, not compared as they were;
  5. the page, the partial and the JSON route render.

Run:
    .venv/Scripts/python.exe cuore/tests/check_trends.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-trends-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import trends  # noqa: E402
from cuore.web import trends_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    print(f"  [{'ok' if cond else 'FAIL'}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def rd(at: datetime, q: str, value: float, unit: str, stream: str, **inline) -> dict:
    return trends._reading(at, q, value, unit, stream, inline=inline)


def by_id(result: dict, mid: str) -> dict:
    return next(m for m in result["metrics"] if m["id"] == mid)


D0 = datetime(2026, 9, 1, 8, 0, 0)

print("=== falling resting voltage is flagged, with its count ===")
volts = [12.6, 12.5, 12.45, 12.4, 12.3]
readings, activity = [], []
for i, v in enumerate(volts):
    t = D0 + timedelta(days=i * 4)
    activity += [t - timedelta(hours=14), t]            # car quiet overnight, then the visit starts
    readings.append(rd(t, "battery_v", v, "V", "BCM DID 0x1004", rpm=0.0))
activity.sort()
res = trends.compute(readings, activity)
m = by_id(res, "batt_rest_v")
print("   ", m["sentence"])
check("series has 5 daily points", m["n"] == 5, str(m["n"]))
check("status is a flag (drifting or worse)", m["status"] in ("drifting", "heading_to_limit", "shifted"), m["status"])
check("wording says falling, first -> last, and the visit count",
      "falling: 12.60 → 12.30 V over 5 visits" in m["sentence"], m["sentence"])
check("headline carries the same call", "falling: 12.60 → 12.30 V over 5 visits" in res["headline"]["text"],
      res["headline"]["text"])
check("slope is negative", m["series"][0]["slope_per_day"] < 0)
check("5 samples is under the projection minimum, so no 'reach the limit' claim",
      m["series"][0]["projection"] is None and "no projection yet" in m["series"][0]["projection_note"],
      str(m["series"][0].get("projection_note")))

print("=== projection appears only with enough samples and span ===")
more = list(readings)
for i, v in enumerate([12.25, 12.2], start=5):
    t = D0 + timedelta(days=i * 4)
    activity.append(t - timedelta(hours=14)); activity.append(t)
    more.append(rd(t, "battery_v", v, "V", "BCM DID 0x1004", rpm=0.0))
activity.sort()
m7 = by_id(trends.compute(more, activity), "batt_rest_v")
proj = m7["series"][0]["projection"]
check("7 samples over 24 days gives a projection", bool(proj) and proj.get("days") is not None, str(proj))
check("projection text states the sample count", bool(proj) and "from 7 samples over 24 days" in proj["text"],
      str(proj))
check("status is heading_to_limit", m7["status"] == "heading_to_limit", m7["status"])

print("=== too few samples ===")
few = readings[:3]
mf = by_id(trends.compute(few, activity), "batt_rest_v")
check("3 samples -> not_enough_data", mf["status"] == "not_enough_data", mf["status"])
check("wording is 'not enough data (3 samples'", "not enough data (3 samples" in mf["detail"], mf["detail"])
check("no projection with 3 samples", mf["series"][0]["projection"] is None)
res_few = trends.compute(few, activity)
check("headline says not enough data and names the most samples",
      "Not enough data" in res_few["headline"]["text"] and "is 3" in res_few["headline"]["text"],
      res_few["headline"]["text"])

print("=== non-comparable readings are excluded, with reasons ===")
mixed = list(readings)
t_run = D0 + timedelta(days=21)
mixed.append(rd(t_run, "battery_v", 14.4, "V", "BCM DID 0x1004", rpm=2000.0))                 # engine running
t_soon = D0 + timedelta(days=22)
activity2 = sorted(activity + [t_soon - timedelta(hours=1), t_soon])
mixed.append(rd(t_soon, "battery_v", 12.1, "V", "BCM DID 0x1004", rpm=0.0))                   # not rested
mixed.append(trends._reading(D0 + timedelta(days=23), "battery_v", None, "V", "BCM DID 0x1004",
                             inline={"rpm": 0.0}, excluded="invalid reading: raw -32768 = 'not available' marker"))
mm = by_id(trends.compute(mixed, activity2), "batt_rest_v")
s = mm["series"][0]
check("the 5 comparable points are unchanged (running, not-rested and invalid ones left out)", s["n"] == 5, str(s["n"]))
check("3 readings were excluded", s["excluded"]["count"] == 3, str(s["excluded"]))
reasons = " | ".join(r["reason"] for r in s["excluded"]["reasons"])
check("reason names the running engine", "engine running" in reasons, reasons)
check("reason names the missing rest", "not rested" in reasons, reasons)
check("reason names the invalid marker", "not available" in reasons, reasons)
check("the running reading lands in charging voltage instead",
      by_id(trends.compute(mixed, activity2), "batt_run_v")["series"][0]["n"] == 1)
mixed_streams = readings + [rd(D0 + timedelta(days=i * 4), "battery_v", v + 1.6, "V", "adapter ATRV at probe", rpm=0.0)
                            for i, v in enumerate(volts)]
check("two instruments are kept as two series, never averaged together",
      len(by_id(trends.compute(mixed_streams, activity), "batt_rest_v")["series"]) == 2)

print("=== old ecm_195a decoding is re-decoded, not compared as-is ===")
v_old, u_old, why_old = trends.clean_channel("ecm_195a", -32.77, "2026-10-13T20:09:08", "bar")
check("pre-fix value converted to mbar", why_old == "" and u_old == "mbar" and 900 < v_old < 1100, f"{v_old} {u_old} {why_old}")
v_na, _u, why_na = trends.clean_channel("ecm_1956", -32768, "2026-10-26T00:00:00", "mbar", "")
check("a 'not available' marker is excluded as invalid", v_na is None and "not available" in why_na, why_na)

print("=== page, partial and JSON render ===")
synthetic = trends.compute(more, activity)
synthetic.update(vin=VIN, generated_at="2026-10-26T00:00:00", sources_note="synthetic")
real_panel = trends.panel
trends.panel = lambda vin: synthetic                                   # the page is fed the synthetic result
app = create_app()
app.include_router(trends_routes.router)
client = TestClient(app)
page = client.get(f"/v/{VIN}/trends")
check("page responds 200", page.status_code == 200, str(page.status_code))
check("page leads with the one-line call", "falling: 12.60 → 12.20 V over 7 visits" in page.text
      or "12.20 V over 7 visits" in page.text, page.text[page.text.find("tr-headline"):][:300])
check("page has an inline SVG sparkline", "<svg class=\"tr-svg\"" in page.text)
check("axes are labelled in words", "Up is V; across is the day of the reading" in page.text)
check("status is a label as well as a colour", "heading toward limit" in page.text)
check("page shows which readings were excluded or the sources table", "Sources, one line per instrument" in page.text)
check("no template error on the page", "Traceback" not in page.text and "Jinja2" not in page.text)
api = client.get(f"/api/vehicles/{VIN}/trends")
check("JSON route responds 200 with the metrics", api.status_code == 200 and "metrics" in api.json())
trends.panel = real_panel

empty = TestClient(app).get(f"/v/{VIN}/trends")                        # real function, empty state dir
check("page renders with an empty state dir (honest empty state)", empty.status_code == 200
      and "Not enough data yet" in empty.text, str(empty.status_code))
check("empty state flags nothing (the MES corpus alone gives at most single points)",
      "falling:" not in empty.text and "heading toward limit" not in empty.text)

print("=== type scale: only --fs-md and larger in the new files ===")
sizes = []
for p in (ROOT / "cuore/web/static/trends.css", ROOT / "cuore/web/templates/_trends_panel.html",
          ROOT / "cuore/web/templates/trends.html"):
    sizes += re.findall(r"font-size\s*:\s*([^;}\"']+)", p.read_text(encoding="utf-8"))
bad = [s for s in sizes if not re.fullmatch(r"\s*var\(--fs-(md|lg|xl|2xl|3xl)\)\s*", s)]
check("every font-size is a --fs-md-or-larger token", not bad, str(bad))

print()
print(f"{checks - len(failures)}/{checks} checks passed")
sys.exit(1 if failures else 0)
