"""Three checks for the wiring / ground fault layer.

  1. The failure-type map, built from the REAL corpus and the real CUORE
     observation store (read-only), contains the known leads: BCM B101D-15 as
     a wiring-type circuit and ABS U1700-87 with its 10.6 V freeze frame as a
     low-voltage read; the FTB classes are right; GET /api/wiring serves it.
  2. The load-step preset is in the registry with BCM DID 1004, resolves to
     three pollable channels, its script covers 0-180 s with no gap, and the
     start/analysis routes exist.
  3. The load-step analysis flags a module that drops >0.3 V beyond the
     adapter on two steps and leaves a well-behaved one alone (synthetic series
     fed through the real CSV reader).

Touches no adapter and no running server: nothing here opens a port.

Run:
    .venv/Scripts/python.exe cuore/tests/check_wiring_ground.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-wiring-")
_REAL_STORE = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "cuore" / "observations.jsonl"
if _REAL_STORE.exists():
    os.environ["MES_LIVE_OBSERVATIONS"] = str(_REAL_STORE)   # read-only use

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


# --- 1. the wiring map on real data -------------------------------------------
from cuore.api import wiring as wiring_api  # noqa: E402
from cuore.services import wiring_bridge as wb  # noqa: E402

wmap = wiring_api.wiring(vin=VIN, table=False)
mods = {m["module"]: m for m in wmap["modules"]}
bcm_wiring = {r["code"] for r in mods.get("BCM", {}).get("circuits", []) if r["class"] == "wiring"}
abs_low = [f for f in wmap.get("low_voltage_frames", []) if f["module"] == "ABS" and f["code"] == "U1700-87"]
check("wiring map: real corpus parsed, BCM B101D-15 is wiring-class, ABS U1700-87 10.6 V low-voltage read, FTB classes right",
      wmap["sources"]["mes_logs_parsed"] > 0 and wmap["sources"]["dtc_sightings"] > 0
      and "B101D-15" in bcm_wiring
      and bool(abs_low) and abs_low[0]["voltage"] == 10.6
      and wb.classify_ftb("11") == wb.classify_ftb("15") == "wiring"
      and wb.classify_ftb("87") == "communication" and wb.classify_ftb("97") == "performance"
      and wb.classify_ftb("2F") == "signal_range" and wb.classify_ftb("00") == "other"
      and all(0.0 <= m["ground_suspect"]["score"] <= 1.0 for m in wmap["modules"])
      and len(wiring_api.wiring(vin=VIN, table=True)["rows"]) == len(wmap["modules"]),
      detail=f"sources={wmap['sources']} bcm_wiring={bcm_wiring} abs_low={abs_low}")

# --- 2. the preset, registry, script, routes -----------------------------------
from cuore.api import live as live_api  # noqa: E402
from cuore.live import channels as ch  # noqa: E402
from cuore.live import load_step as ls  # noqa: E402

desc = ls.describe()
resolved = [c.id for c in ch.resolve_channels(preset="load_step_voltage")]
script = desc["script"]
contiguous = (script[0]["t0"] == 0 and script[-1]["t1"] == desc["duration_s"] == 180
              and all(a["t1"] == b["t0"] for a, b in zip(script, script[1:])))
route_paths = {getattr(r, "path", "") for r in live_api.router.routes}
check("load-step preset: bcm_1004 + battery + PID 42 resolve, 180 s script contiguous, no missing channels, routes present",
      resolved == ["battery_voltage", "control_module_voltage", "bcm_1004"]
      and "bcm_1004" in ch.registry() and desc["missing_channels"] == []
      and contiguous and sum(1 for s in script if s["state"] == "on") == 7
      and {"/live/load-step", "/live/load-step/start", "/live/load-step/analysis",
           "/live/load-step/status", "/live/load-step/stop"} <= route_paths
      and "load_step_voltage" in ch.presets(),
      detail=f"resolved={resolved} contiguous={contiguous} routes={sorted(p for p in route_paths if 'load-step' in p)}")

# --- 3. the analysis on a synthetic recording, through the real CSV reader ---------
td = Path(tempfile.mkdtemp(prefix="cuore-check-wiring-csv-"))
csv_path = td / "live_load-step-voltage_synthetic.csv"
lines = ['"Time"\t"battery voltage"\t"control module voltage"\t"Battery voltage"\t"TAG"',
         '"sec"\t"V"\t"V"\t"V"\t" "']
bad_steps = {"headlights", "rear_defrost"}          # BCM loses an extra 0.5 V on these two
t = 0.0
while t < 180.0:
    st = next(s for s in script if s["t0"] <= t < s["t1"])
    on = st["state"] == "on"
    adapter = 14.40 - (0.20 if on else 0.0)                      # adapter sags 0.2 V under any load
    ecm = adapter - 0.10                                          # constant offset, same sag: fine
    bcm = adapter + 0.05 - (0.5 if (on and st["load"] in bad_steps) else 0.0)
    lines.append(f"{t:.3f}\t{adapter:.4f}\t{ecm:.4f}\t{round(bcm, 1):.4f}\t\"{st['state'].upper()} {st['load'] or '-'}\"")
    t += 0.25
csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
rows, side = ls.read_recording(csv_path)
res = ls.analyze(rows)
by_mod = {m["module"]: m for m in res["modules"]}
check("load-step analysis: BCM flagged on exactly the 2 bad steps (excess ~0.5 V), ECM clean, adapter drop 0.2 V",
      len(rows) > 600 and side == {}
      and sorted(by_mod["BCM"]["flagged_steps"]) == ["Headlights (low beam) ON", "Rear defrost ON"]
      and not by_mod["ECM"]["flagged_steps"]
      and abs(res["adapter"]["max_drop_v"] - 0.2) < 0.02
      and 0.4 <= by_mod["BCM"]["max_excess_v"] <= 0.6
      and "INFERENCE" in by_mod["BCM"]["verdict"],
      detail=str({k: (v["flagged_steps"], v["max_excess_v"]) for k, v in by_mod.items()}))

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
