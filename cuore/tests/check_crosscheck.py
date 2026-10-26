"""Small check for sensor cross-checks (cuore.services.sensor_crosscheck, cuore.web.crosscheck_routes).

Synthetic readings only; the real rule table (cuore/data/sensor_crosschecks.json) is the one under test.
Proves: AGREE, DISAGREE, CONDITION NOT MET, time skew -> NOT RECORDED (never 0), an unconfirmed decoding
is labelled and never a plain AGREE, an invalid reading is not compared, unit scaling, the owner-stated cold
soak, recording rows, and that the page and JSON render.

Run:
    .venv/Scripts/python.exe cuore/tests/check_crosscheck.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-crosscheck-")
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cuore.services import sensor_crosscheck as sc  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
T = 1_800_000_000.0
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    print(("ok   " if cond else "FAIL ") + label + ("" if cond else f"  -- {detail}"))
    if not cond:
        failures.append(label)


def mk(**kv):
    """{key: (value, unit, t_offset_s)} -> Series."""
    s: sc.Series = {}
    for key, (val, unit, dt) in kv.items():
        k = key.replace("__", "@").replace("_dot_", ".")
        s[k] = [sc.Reading(k, T + dt, val, unit, "test")]
    return s


def run(series, rid, **kw):
    out = sc.evaluate(VIN, series=series, now=T + 60, **kw)
    return next(r for r in out["results"] if r["id"] == rid), out


# 1. AGREE (engine off, MAP 99 vs baro 100)
r, _ = run(mk(intake_map=(99, "kPa", 0), barometric_pressure=(100, "kPa", 1), engine_rpm=(0, "rpm", 0)),
           "map_vs_baro_engine_off")
check("AGREE: MAP 99 vs baro 100 kPa, engine off", r["status"] == sc.AGREE and r["diff"] == 1, str(r["status"]))

# 2. DISAGREE (the decoding-bug shape: one side far off)
r, out = run(mk(intake_map=(60, "kPa", 0), barometric_pressure=(100, "kPa", 1), engine_rpm=(0, "rpm", 0)),
             "map_vs_baro_engine_off")
check("DISAGREE: MAP 60 vs baro 100 kPa, engine off", r["status"] == sc.DISAGREE and r["diff"] == 40, str(r["status"]))
check("the directing call names the disagreement and an amount", "disagree" in out["call"] and "40" in out["call"], out["call"])
check("tolerance, basis and both timestamps are on the result",
      r["tolerance"]["abs"] == 3 and "physics" in r["basis"] and r["a"]["at"] and r["b"]["at"])

# 3. condition not met (engine running)
r, _ = run(mk(intake_map=(31, "kPa", 0), barometric_pressure=(100, "kPa", 1), engine_rpm=(795, "rpm", 0)),
           "map_vs_baro_engine_off")
check("CONDITION NOT MET: engine running (795 rpm)", r["status"] == sc.NOT_MET and "795" in r["reason"], r["status"])

# 4. time skew -> NOT RECORDED, value shown as not recorded, never 0
r, _ = run(mk(intake_map=(99, "kPa", 0), barometric_pressure=(100, "kPa", 120), engine_rpm=(0, "rpm", 0)),
           "map_vs_baro_engine_off")
check("NOT RECORDED: baro read 120 s after MAP (limit 10 s)", r["status"] == sc.NOT_REC, r["status"])
check("the missing side is None, not 0", r["b"]["value"] is None and r["diff"] is None)
r, _ = run(mk(intake_map=(99, "kPa", 0), engine_rpm=(0, "rpm", 0)), "map_vs_baro_engine_off")
check("NOT RECORDED: a side never read", r["status"] == sc.NOT_REC and r["b"]["value"] is None)
r, _ = run(mk(intake_map=(99, "kPa", 0), barometric_pressure=(100, "kPa", 1)), "map_vs_baro_engine_off")
check("NOT RECORDED (not 'engine off'): no RPM at that moment to tell", r["status"] == sc.NOT_REC and "condition" in r["reason"], r["reason"])

# 5. unconfirmed decoding is labelled
r, _ = run(mk(engine_coolant_temp=(60, "C", 0), ecm_1003=(61, "C", 2)), "coolant_pid_vs_ecm_1003")
check("UNCONFIRMED DECODING: values agree but ECM DID 1003 is unverified",
      r["status"] == sc.UNCONFIRMED and r["would_be"] == sc.AGREE and not r["b"]["confirmed"] and r["a"]["confirmed"], r["status"])
check("... and says the decoding is not confirmed", "not confirmed" in r["reason"].lower() or "NOT confirmed" in r["b"]["note"] or "not confirmed" in r["b"]["note"])
r, out = run(mk(engine_coolant_temp=(60, "C", 0), ecm_1003=(80, "C", 2)), "coolant_pid_vs_ecm_1003")
check("UNCONFIRMED DECODING with would_be DISAGREE when they differ", r["status"] == sc.UNCONFIRMED and r["would_be"] == sc.DISAGREE)
check("... the call mentions the unconfirmed decoding", "unconfirmed" in out["call"], out["call"])

# 6. invalid reading is never compared
r, _ = run(mk(ecm_195a=(-31764.0, "mbar", 0), barometric_pressure=(100, "kPa", 1), engine_rpm=(0, "rpm", 0)),
           "boost_abs_vs_baro_engine_off")
check("NOT RECORDED: an impossible reading (-31764 mbar) is not compared", r["status"] == sc.NOT_REC and "invalid" in r["reason"], r["reason"])

# 7. unit scaling (mbar -> kPa) and a confirmed pair
r, _ = run(mk(barometric_pressure=(100, "kPa", 0), ecm_1956=(1004, "mbar", 1)), "baro_pid_vs_ecm_1956")
check("AGREE with scaling: 100 kPa vs 1004 mbar (= 100.4 kPa)",
      r["status"] == sc.AGREE and abs(r["b"]["value"] - 100.4) < 1e-6 and r["b"]["converted"], str(r))
r, _ = run(mk(ecm_195a=(1001.0, "mbar", 0), ecm_1956=(1004.0, "mbar", 0), engine_rpm=(0, "rpm", 0)),
           "boost_abs_vs_ecm_1956_engine_off")
check("AGREE: boost DID 195A vs ambient DID 1956, engine off (both confirmed)", r["status"] == sc.AGREE, r["status"])

# 8. cold soak is owner-stated, never guessed
base = mk(engine_coolant_temp=(15, "C", 0), ambient_air_temp=(14, "C", 0), engine_rpm=(0, "rpm", 0))
r, _ = run(base, "coolant_vs_ambient_cold_soak")
check("CONDITION NOT MET: cold soak not stated", r["status"] == sc.NOT_MET and "soaked_h" in r["reason"], r["reason"])
r, _ = run(base, "coolant_vs_ambient_cold_soak", soaked_h=8)
check("AGREE: 8 h stated, coolant 15 vs ambient 14 C", r["status"] == sc.AGREE, r["status"])
r, _ = run(base, "coolant_vs_ambient_cold_soak", soaked_h=2)
check("CONDITION NOT MET: only 2 h stated", r["status"] == sc.NOT_MET)

# 9. recording: each row judged on its own
rows = []
for i, (m, b) in enumerate([(100, 100), (99, 100), (60, 100), (61, 100)]):
    rows.append({"type": "row", "t": i, "at": f"2026-10-26T10:00:0{i}+00:00", "v": {"intake_map": m, "barometric_pressure": b, "engine_rpm": 0}})
rec = {"id": "r1", "vin": VIN, "label": "t", "units": {"intake_map": "kPa", "barometric_pressure": "kPa", "engine_rpm": "rpm"},
       "channels": ["intake_map", "barometric_pressure", "engine_rpm"], "rows": rows}
out = sc.evaluate(VIN, recording="r1", recording_data=rec)
r = next(x for x in out["results"] if x["id"] == "map_vs_baro_engine_off")
check("recording: 2 of 4 rows beyond tolerance -> DISAGREE, rows counted", r["status"] == sc.DISAGREE and r["rows"]["evaluated"] == 4 and r["rows"]["disagree"] == 2, str(r.get("rows")))
r2 = next(x for x in out["results"] if x["id"] == "coolant_pid_vs_ecm_1003")
check("recording without the channels: NOT RECORDED", r2["status"] == sc.NOT_REC)
check("every rule has basis and tolerance basis; needs list is not empty",
      all(x["basis"] and x["tolerance"]["basis"] for x in out["results"]) and len(out["needs"]) >= 5)

# 10. page and JSON render (no car, state dir is empty)
from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402
from cuore.web import crosscheck_routes  # noqa: E402

app = create_app()
app.include_router(crosscheck_routes.router)
client = TestClient(app)
resp = client.get(f"/v/{VIN}/crosschecks")
check("page /v/{vin}/crosschecks renders 200 with the panel", resp.status_code == 200 and "cc-panel" in resp.text, str(resp.status_code))
check("page labels statuses with words (NOT RECORDED present on an empty state dir)", "NOT RECORDED" in resp.text)
resp = client.get(f"/api/vehicles/{VIN}/crosschecks")
j = resp.json() if resp.status_code == 200 else {}
check("JSON endpoint returns results, counts, call, needs", resp.status_code == 200 and j.get("results") and j.get("call") and j.get("needs"), str(resp.status_code))
check("JSON ?recording=<unknown> -> 404 with the reason", client.get(f"/api/vehicles/{VIN}/crosschecks?recording=nope").status_code == 404)

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(f"FAIL: {f}")
if failures:
    sys.exit(1)
