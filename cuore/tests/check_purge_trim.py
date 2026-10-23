"""Three checks for the passive purge-trim EVAP test.

  1. The preset resolves to the nine read-only Mode 01 channels (PID 2E and 2F
     among them, no EVAP pressure channel), the 240 s script is contiguous,
     the four /api/live/purge-trim routes and the page /v/<vin>/purge-trim
     exist, and the page renders without opening the adapter.
  2. Analysis on synthetic recordings, through the real CSV reader: purge opens
     and STFT dips -> "response" (labelled INFERENCE); purge opens and STFT does
     not move -> inconclusive, never "purge dead".
  3. Purge never leaves 0 % -> the exact "ECM did not command purge" message;
     PID 2E absent -> trims-only, inconclusive.

Touches no adapter and no running server: nothing here opens a port.

Run:
    .venv/Scripts/python.exe cuore/tests/check_purge_trim.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-purge-")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(label + (f" -- {detail}" if detail else ""))


from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402
from cuore.live import channels as ch  # noqa: E402
from cuore.live import purge_trim as pt  # noqa: E402

# --- 1. preset, registry, script, routes, page ----------------------------------
EXPECT = ["commanded_evap_purge", "short_fuel_trim_b1", "long_fuel_trim_b1", "engine_rpm", "intake_map",
          "absolute_load", "engine_coolant_temp", "fuel_level", "ambient_air_temp"]
desc = pt.describe()
resolved = [c.id for c in ch.resolve_channels(preset="purge_trim")]
script = desc["script"]
app = create_app()
paths = set(app.openapi().get("paths", {}))
client = TestClient(app)
page = client.get(f"/v/{VIN}/purge-trim")
st = pt.status()
check("purge-trim preset: 9 read-only channels (PID 2E + 2F, no pressure channel), 240 s script, 4 routes, page renders, idle status",
      resolved == EXPECT and desc["missing_channels"] == [] and not any("pressure" in c for c in resolved)
      and all(ch.registry()[c].kind == "pid" for c in resolved)
      and ch.registry()["commanded_evap_purge"].pid == "2E" and ch.registry()["fuel_level"].pid == "2F"
      and script[0]["t0"] == 0 and script[-1]["t1"] == desc["duration_s"] == 240
      and {"/api/live/purge-trim/start", "/api/live/purge-trim/stop", "/api/live/purge-trim/status",
           "/api/live/purge-trim/analysis"} <= paths
      and page.status_code == 200 and "Purge-trim EVAP test" in page.text and "pt-start" in page.text
      and st.get("running") is False,
      detail=f"resolved={resolved} page={page.status_code} status={st}")


# --- synthetic recordings through the real CSV reader ---------------------------------
def make_csv(name: str, columns: list[str], fn) -> Path:
    p = Path(tempfile.mkdtemp(prefix="cuore-check-purge-csv-")) / name
    lines = ["\t".join(['"Time"'] + [f'"{c}"' for c in columns] + ['"TAG"']),
             "\t".join(['"sec"'] + ['"x"'] * len(columns) + ['" "'])]
    t = 0.0
    while t < 240.0:
        vals = fn(t)
        lines.append("\t".join([f"{t:.3f}"] + [("" if vals.get(c) is None else f"{vals[c]:.3f}") for c in columns]
                               + ['"WATCH -"']))
        t += 0.1
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # like a real run, the sidecar records the column order (a recording without 2E needs it)
    p.with_suffix(".json").write_text(json.dumps({"columns": columns, "ended": "x", "aborted": False}),
                                      encoding="utf-8")
    return p


def series(purge_fn, dip: float):
    def f(t: float) -> dict:
        purge = purge_fn(t)
        # STFT sits at +1.0; with purge open it falls by `dip` over 3 s, then recovers slowly
        stft = 1.0 + (0.4 if int(t * 10) % 7 == 0 else -0.2)
        if purge >= 1.0 and dip:
            stft -= dip * min(1.0, (t - 100.0) / 3.0) if t >= 100.0 else 0.0
        return {"commanded_evap_purge": purge, "short_fuel_trim_b1": stft, "long_fuel_trim_b1": 2.0,
                "engine_rpm": 800.0 + (10 if int(t) % 2 else 0), "intake_map": 35.0, "absolute_load": 22.0,
                "engine_coolant_temp": 90.0, "fuel_level": 46.0, "ambient_air_temp": 8.0}
    return f


open_at_100 = lambda t: 0.0 if t < 100.0 else (35.0 if t < 140.0 else 0.0)   # noqa: E731
r_dip = pt.analyze(pt.read_recording(make_csv("live_purge-trim_a.csv", EXPECT, series(open_at_100, 6.0)))[0])
r_flat = pt.analyze(pt.read_recording(make_csv("live_purge-trim_b.csv", EXPECT, series(open_at_100, 0.0)))[0])
check("purge-trim analysis: opening + 6 % STFT dip -> response labelled INFERENCE; opening + no dip -> inconclusive, not 'dead'",
      r_dip["mode"] == "purge_commanded" and len(r_dip["events"]) == 1 and r_dip["events"][0]["response"]
      and r_dip["events"][0]["steady"] and r_dip["events"][0]["dip_pct"] <= -5.0
      and r_dip["verdict"].startswith("INFERENCE") and r_dip["on"]["stft_mean"] < r_dip["off"]["stft_mean"] - 1.0
      and r_flat["events"][0]["response"] is False and "inconclusive" in r_flat["verdict"]
      and "dead" not in r_flat["verdict"].replace("non-flowing", ""),
      detail=f"dip={r_dip.get('events')} {r_dip['verdict']} | flat={r_flat['verdict']}")

# --- 3. purge never commanded; PID 2E absent ----------------------------------------------
r_zero = pt.analyze(pt.read_recording(make_csv("live_purge-trim_c.csv", EXPECT, series(lambda t: 0.0, 0.0)))[0])
no2e = [c for c in EXPECT if c != "commanded_evap_purge"]
r_no = pt.analyze(pt.read_recording(make_csv("live_purge-trim_d.csv", no2e, series(open_at_100, 6.0)))[0])
check("purge-trim analysis: 2E stuck at 0 -> exact 'ECM did not command purge' message; 2E absent -> trims-only, inconclusive",
      r_zero["mode"] == "not_commanded" and r_zero["verdict"].startswith(pt.NOT_COMMANDED)
      and "inconclusive" in r_zero["verdict"] and "purge dead" not in r_zero["verdict"]
      and r_no["mode"] == "trims_only" and "inconclusive" in r_no["verdict"] and "excursions" in r_no
      and len(r_no["excursions"]["excursions"]) >= 1,
      detail=f"zero={r_zero['verdict']} | no2e={r_no['verdict']} {r_no.get('excursions')}")

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
