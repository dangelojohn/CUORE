"""Checks for the decoding-confirmation kit (cuore.live.decode_confirm). Offline: a small fixture MES
graph CSV and a fake CUORE live-session CSV in a temp state dir; never touches the car or real logs.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_decode_confirm.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TMP = Path(tempfile.mkdtemp(prefix="cuore-decode-confirm-"))
os.environ["CUORE_STATE_DIR"] = str(TMP)

from cuore.live import channels as chmod  # noqa: E402
from cuore.live import decode_confirm as dc  # noqa: E402
from cuore.live import did_catalog  # noqa: E402
from cuore.live.errors import BadCommand  # noqa: E402
from cuore.live.readall import eval_formula  # noqa: E402
from cuore.services import sensor_health as sh  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
reg = chmod.registry()


def write_csv(path: Path, cols: list[tuple[str, str, list[float]]], times: list[float], tags: dict | None = None) -> None:
    lines = ["\t".join(f'"{n}"' for n in ["Time"] + [c[0] for c in cols] + ["TAG"]),
             "\t".join(f'"{u}"' for u in ["sec"] + [c[1] for c in cols] + [" "])]
    for i, t in enumerate(times):
        lines.append("\t".join([f"{t:.3f}"] + [("" if c[2][i] is None else f"{c[2][i]:.4f}") for c in cols] + [f'"{(tags or {}).get(i, "")}"']))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# real-time signals (t = seconds since CUORE start): a rev ramp, boost bump, throttle in degrees
def rpm(t): return 800 + 1700 * min(1, max(0, (t - 10) / 10)) if t < 40 else 800
def boost(t): return 990 + 600 * math.sin(min(max(t - 10, 0), 30) / 30 * math.pi)
def thr_deg(t): return 2 + 28 * min(1, max(0, (t - 10) / 10)) if t < 40 else 2


cu_t = [i * 0.5 for i in range(0, 121)]                 # 0..60 s, CUORE rows every 0.5 s
cu_cols = [
    (reg["engine_rpm"].name, "rpm", [rpm(t) for t in cu_t]),
    (reg["ecm_1000"].name, "rpm", [rpm(t) for t in cu_t]),
    (reg["ecm_195a"].name, "mbar", [boost(t) for t in cu_t]),
    (reg["ecm_1925"].name, "%", [thr_deg(t) * 100 / 655.35 for t in cu_t]),           # raw = deg*100
    (reg["ecm_1959"].name, "bar", [(round(boost(t)) - 32768) / 1000 - 1 for t in cu_t]),  # raw is plain mbar
    (reg["ecm_195b"].name, "V", [0.03 for _ in cu_t]),
]
REC = TMP / "recordings"
REC.mkdir()
cu_path = REC / "live_decode-confirm_20261102-100000.csv"
write_csv(cu_path, cu_cols, cu_t)

# MES graph CSV: its own clock started 2 s after CUORE's; samples every 1 s
mes_t = [float(i) for i in range(0, 56)]
mes_cols = [
    ("Engine speed", "rpm", [rpm(t + 2) for t in mes_t]),
    ("Boost pressure", "mbar", [boost(t + 2) for t in mes_t]),
    ("Throttle position (Track 2)", "deg.", [thr_deg(t + 2) for t in mes_t]),
    ("Desired boost pressure", "mbar", [boost(t + 2) for t in mes_t]),
    ("Boost pressure signal", "V", [1.2 + 0.001 * t for t in mes_t]),
]
mes_path = TMP / "mes_graph_fixture.csv"
write_csv(mes_path, mes_cols, mes_t)

# --- the alias file -----------------------------------------------------------------
al = dc.load_aliases()
pairs = al["pairs"]
check(all(a["channel"] in reg for a in pairs), "every aliased channel exists in the registry")
check(all(a["certainty"] in ("certain", "candidate") for a in pairs), "certainty is certain|candidate")
check(all(a.get("note") for a in pairs if a["certainty"] == "certain"), "every certain pair carries its justification")
cands = {a["channel"] for a in pairs if a["certainty"] == "candidate"}
check({"ecm_1925", "ecm_1926", "ecm_195b", "ecm_1959"} <= cands, "four suspect DIDs are candidates")
check({u["channel"] for u in al["unpaired"]} == {"ecm_1009", "egr_temperature"}, "1009 and PID 6B listed as unpaired")

# --- a run (MES start declared 3 s late: the engine-speed lag search must find it) ----------------
r = dc.run(VIN, str(mes_path), str(cu_path), mode="timestamp", mes_start="2026-11-02T10:00:05")
rows = {c["channel"]: c for c in r["channels"]}
check(abs(r["timing"]["lag_s"] - (-3.0)) <= 0.5 and r["timing"]["lag_source"] == "engine_speed", "lag found on engine speed")
check(rows["engine_rpm"]["verdict"] == "confirmed" and rows["ecm_1000"]["verdict"] == "confirmed", "rpm channels confirmed")
check(rows["ecm_195a"]["verdict"] == "confirmed" and rows["ecm_195a"]["samples"] >= 50, "boost confirmed with sample count")
check(rows["ecm_1925"]["verdict"] == "wrong_scale" and rows["ecm_1925"]["transform"]["name"] == "raw_over_100_degrees"
      and rows["ecm_1925"]["pairing"] == "candidate", "throttle 2 -> wrong_scale, degrees proposed, candidate pairing")
check(abs(rows["ecm_1925"]["transform"]["a"] - 6.5535) < 1e-6, "proposed degrees scale is 6.5535")
check(rows["ecm_1959"]["verdict"] == "wrong_scale" and rows["ecm_1959"]["transform"]["name"] in ("raw_counts", "offset_dropped"),
      "1959 -> wrong_scale, unsigned raw (offset removed)")
check(rows["ecm_195b"]["verdict"] == "ambiguous", "195B constant 0.03 V vs moving MES voltage -> ambiguous")
check(rows["ecm_1926"]["verdict"] == "no_data" and "no column" in rows["ecm_1926"]["reason"], "missing CUORE column -> no_data")
check(rows["ecm_1009"]["verdict"] == "no_data" and rows["egr_temperature"]["verdict"] == "no_data", "unpaired suspects -> no_data")
check(r["summary"].get("confirmed", 0) >= 3, "summary counts verdicts")
saved = TMP / "decode_confirm" / f"{r['run_id']}.json"
check(saved.is_file() and json.loads(saved.read_text(encoding="utf-8"))["run_id"] == r["run_id"], "run saved under decode_confirm/")
check([x["run_id"] for x in dc.list_runs(VIN)["runs"]] == [r["run_id"]], "list_runs shows it")

# a constant MES value can never confirm
flat = TMP / "mes_flat.csv"
write_csv(flat, [("Engine speed", "rpm", [750.0] * 56)], mes_t)
rf = dc.run(VIN, str(flat), str(cu_path), mode="timestamp", mes_start="2026-11-02T10:00:02", lag_s=0.0)
check({c["channel"]: c for c in rf["channels"]}["engine_rpm"]["verdict"] == "ambiguous", "static MES value -> ambiguous")
# a text session log has no timestamps: refuse without an interval
txt = TMP / "FESLog_2611021000_x.txt"
txt.write_text("(Multiecuscan 5.4)\n11/2/2026 10:00:00 AM\n\nREADING PARAMETERS:\nEngine speed: 750 rpm\n", encoding="utf-8")
try:
    dc.run(VIN, str(txt), str(cu_path), mode="timestamp")
    check(False, "text log without interval refused")
except BadCommand:
    check(True, "text log without interval refused")

# --- static mode: one adapter, the two logs made one after the other and cut by tag number ---------------
def cond(t):   # tag 1: 0-20 s engine off pedal up; tag 2: 20-40 s pedal down; tag 3: 40-60 s idle
    return (0, 2.0) if t < 20 else (0, 80.0) if t < 40 else (750, 2.0)


st_cu_t = [float(i) for i in range(0, 61)]
st_cu_path = REC / "live_static_20261102-110000.csv"
write_csv(st_cu_path, [(reg["engine_rpm"].name, "rpm", [cond(t)[0] for t in st_cu_t]),
                       (reg["ecm_1925"].name, "%", [cond(t)[1] * 100 / 655.35 for t in st_cu_t])], st_cu_t,
          {0: "TAG 1: ign on", 20: "TAG 2: pedal down", 40: "TAG 3: idle"})
st_me_t = [float(i) * 2 for i in range(0, 31)]
st_me_path = TMP / "mes_static_fixture.csv"
write_csv(st_me_path, [("Engine speed", "rpm", [cond(t)[0] for t in st_me_t]),
                       ("Throttle position (Track 2)", "deg.", [cond(t)[1] for t in st_me_t])], st_me_t,
          {0: "1", 10: "2", 20: "3"})
rs = dc.run(VIN, str(st_me_path), str(st_cu_path))
sr = {c["channel"]: c for c in rs["channels"]}
check(rs["mode"] == "static" and rs["tags"]["mes"] == [1, 2, 3] and sr["engine_rpm"]["verdict"] == "confirmed"
      and sr["engine_rpm"]["samples"] == 3, "static: engine speed confirmed across 3 tagged conditions")
check(sr["ecm_1925"]["verdict"] == "wrong_scale" and sr["ecm_1925"]["transform"]["name"] == "raw_over_100_degrees",
      "static: throttle 2 wrong_scale (degrees) from tags 1 and 2")
rn = dc.run(VIN, str(txt), str(st_cu_path))
check({c["channel"]: c for c in rn["channels"]}["engine_rpm"]["verdict"] == "no_data"
      and "no tags" in {c["channel"]: c for c in rn["channels"]}["engine_rpm"]["reason"], "static: MES text log without tags -> no_data 'no tags'")

# --- accept -> override file -> catalogue + sensor health ---------------------------------------
check(sh.suspect_reason("ecm_1925", 1.5, {}) != "", "1925 suspect before acceptance")
try:
    dc.accept(VIN, r["run_id"], "ecm_1925")
    check(False, "candidate pairing needs confirm_pairing")
except BadCommand:
    check(True, "candidate pairing needs confirm_pairing")
for ch, why in (("ecm_195b", "ambiguous"), ("ecm_1009", "no_data")):
    try:
        dc.accept(VIN, r["run_id"], ch)
        check(False, f"{why} cannot be accepted")
    except BadCommand:
        check(True, f"{why} cannot be accepted")
out = dc.accept(VIN, r["run_id"], "ecm_1925", confirm_pairing=True)
spec = next(d for d in did_catalog.all_dids("ECM") if d.did == 0x1925)
check(spec.confidence == "confirmed" and spec.unit == "deg", "override applied: confirmed, degrees")
check(abs(eval_formula(spec.formula, [0x03, 0xE8]) - 10.0) < 1e-3, "overridden formula decodes raw 1000 as 10 deg")
check(next(d for d in did_catalog.EXTRA_DIDS if d.did == 0x1925).confidence == "unverified", "shipped catalogue row untouched")
check(sh.suspect_reason("ecm_1925", 1.5, {}) == "", "suspect flag dropped once confirmed")
check(sh.suspect_reason("ecm_1926", 1.5, {}) != "", "other suspects keep their flag")
check(reg is not chmod.registry() and chmod.registry()["ecm_1925"].confidence == "confirmed", "registry rebuilt after accept")
dc.accept(VIN, r["run_id"], "ecm_1000")
check(did_catalog.is_confirmed("ecm_1000") and (TMP / "did_overrides.json").is_file(), "identity confirm stored in did_overrides.json")
check(len(dc.get_run(r["run_id"])["accepted"]) == 2, "acceptances noted in the run file")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
