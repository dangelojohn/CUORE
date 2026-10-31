"""Checks for the end-to-end decode flow (cuore.live.decode_flow). Fakes only: no car, no COM port.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_decode_flow.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
TMP = Path(tempfile.mkdtemp(prefix="cuore-decode-flow-"))
MESDIR = TMP / "mes_export"
MESDIR.mkdir()
os.environ["CUORE_STATE_DIR"] = str(TMP)
os.environ["MES_CSV_DIR"] = str(MESDIR)

from cuore.live import channels as chmod  # noqa: E402
from cuore.live import decode_flow as df  # noqa: E402
from cuore.live import did_catalog  # noqa: E402
from cuore.live.errors import BadCommand, Refused  # noqa: E402

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


def write_csv(path, cols, times, tags):
    lines = ["\t".join(f'"{n}"' for n in ["Time"] + [c[0] for c in cols] + ["TAG"]),
             "\t".join(f'"{u}"' for u in ["sec"] + [c[1] for c in cols] + [" "])]
    for i, t in enumerate(times):
        lines.append("\t".join([f"{t:.3f}"] + [f"{c[2][i]:.4f}" for c in cols] + [f'"{tags.get(i, "")}"']))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# states: tag 1 (0-19 s) rpm 0, tag 3 (20-49 s) rpm 800 idle; IBS charge 80 then 82
def sig(t, a, b): return a if t < 20 else b
times = [float(i) for i in range(0, 50)]
tags = {0: "TAG 1: key on", 20: "TAG 3: warm idle"}
rpm_v = [sig(t, 0, 800) + (t % 3) for t in times]
ibs_v = [sig(t, 80, 82) + (t % 2) * 0.1 for t in times]
mes_cols = [("Engine speed", "rpm", rpm_v), ("IBS Battery charge status", "%", ibs_v)]
# CUORE: ecm_19bd decodes 2x too high (wrong scale), rpm right
cu_cols = [(reg["engine_rpm"].name, "rpm", rpm_v), (reg["ecm_19bd"].name, reg["ecm_19bd"].unit, [v * 2 for v in ibs_v])]

check(df.newest_mes_csv() is None, "no MES CSV -> None")
try:
    df.propose(VIN)
    check(False, "propose without MES CSV refused")
except BadCommand as e:
    check("MES" in str(e), "propose without MES CSV refused")

mes_path = MESDIR / "graph_a.csv"
write_csv(mes_path, mes_cols, times, tags)
time.sleep(0.05)
write_csv(MESDIR / "graph_b.csv", mes_cols, times, tags)       # newest
found = df.newest_mes_csv()
check(found and found["name"] == "graph_b.csv", "newest MES CSV found by itself")
check(df.newest_cuore_recording() is None, "no CUORE recording yet")
try:
    df.propose(VIN)
    check(False, "propose without CUORE recording refused")
except BadCommand:
    check(True, "propose without CUORE recording refused")

# --- recording: refused while MES runs; channels follow the MES columns -------------------
class FakeOps:
    started = None
    def live_session_start(self, channels=None, vin="", **k): FakeOps.started = channels; return {"active": True}
    def live_record_start(self, name=""): return {"recording": "x.csv", "name": name}
    def live_record_stop(self): return {"stopped": True}
    def live_session_stop(self): return {"stopped": True}
class FakeInterlock:
    def __init__(self, running): self.running = running
    def mes_status(self): return {"running": self.running}

try:
    df.record_start(VIN, ops=FakeOps(), interlock=FakeInterlock(True))
    check(False, "record refused while MES runs")
except Refused:
    check(True, "record refused while MES runs")
r = df.record_start(VIN, ops=FakeOps(), interlock=FakeInterlock(False))
check(set(FakeOps.started) == {"engine_rpm", "ecm_1000", "ecm_19bd"}, "records exactly the channels MES recorded: " + str(FakeOps.started))
check(r["mes_csv"].endswith("graph_b.csv"), "record uses the newest MES CSV")
check(df.record_stop(ops=FakeOps())["recording"]["stopped"], "record stop")

# --- the CUORE recording made straight after ----------------------------------------------
(TMP / "recordings").mkdir()
cu_path = TMP / "recordings" / "live_decode-confirm_20261102-100000.csv"
write_csv(cu_path, cu_cols, times, tags)
p = df.propose(VIN)
rows = {c["channel"]: c for c in p["channels"]}
check(p["mode"] == "static" and p["applied"] is False, "paired by tag, nothing applied")
check(rows["engine_rpm"]["proposal"] == "confirmed" and rows["engine_rpm"]["samples"] == 2, "rpm proposed confirmed with sample count")
check(rows["ecm_19bd"]["proposal"] == "rejected" and rows["ecm_19bd"]["agreement"] == 0.0, "2x IBS disagreeing certain pairing proposed rejected")
check(rows["ecm_1009"]["proposal"] == "candidate" and rows["ecm_1009"]["samples"] == 0, "no data -> candidate")
check(not did_catalog.is_confirmed("ecm_19bd"), "proposal alone confirms nothing")

# --- a person decides ----------------------------------------------------------------------
before = df.status()
ecm = next(m for m in before["modules"] if m["module"] == "ECM")
check(ecm["total"] >= 133 and "of 133 confirmed" in before["headline"], "status says N of 133 confirmed: " + before["headline"])
rj = df.reject(VIN, p["run_id"], "ecm_19bd", "doubled")
check(rj["rejected"] == "ecm_19bd" and not did_catalog.is_confirmed("ecm_19bd"), "reject changes no confidence")
check(df.status()["modules"][0]["rejected"] >= 1, "status counts the rejection")
try:
    df.accept(VIN, p["run_id"], "ecm_1009")
    check(False, "no_data cannot be accepted")
except BadCommand:
    check(True, "no_data cannot be accepted")

# accept a confirmed channel of a fresh pair: IBS right this time
cu2 = TMP / "recordings" / "live_decode-confirm_20261102-110000.csv"
write_csv(cu2, [(reg["engine_rpm"].name, "rpm", rpm_v), (reg["ecm_19bd"].name, reg["ecm_19bd"].unit, ibs_v)], times, tags)
os.utime(cu2, (time.time() + 5, time.time() + 5))
p2 = df.propose(VIN)
r19 = next(c for c in p2["channels"] if c["channel"] == "ecm_19bd")
check(r19["proposal"] == "confirmed", "IBS charge proposed confirmed when scale agrees")
df.accept(VIN, p2["run_id"], "ecm_19bd")
check(did_catalog.is_confirmed("ecm_19bd") and chmod.registry()["ecm_19bd"].confidence == "confirmed", "accepted -> confirmed in registry")
st = df.status()
check(next(m for m in st["modules"] if m["module"] == "ECM")["confirmed"] == ecm["confirmed"] + 1, "status count rose by one")
check(st["modules"][0]["module"] == "ECM" and all("of" in l for l in st["lines"]), "plain per-module lines")
check("ecm_19bd" not in json.loads((TMP / "decode_flow.json").read_text())["rejected"], "accept clears the earlier rejection")

# --- Live / Gauges / board show it ---------------------------------------------------------
from cuore.web import liveboard_view as lv  # noqa: E402
check(lv.conf_word({"id": "ecm_19bd"}) == "scale confirmed against MES", "board shows confirmed")
check(lv.conf_word({"id": "ecm_1009"}) != "scale confirmed against MES", "board does not for unconfirmed")
from cuore.web import live_dashboard_routes as ldr  # noqa: E402
try:
    now = ldr._now_view(VIN)
    check("of 133 confirmed" in now.get("decode", ""), "Gauges now-block carries the status line")
except Exception as e:  # noqa: BLE001
    check(False, f"now view: {e}")

print(f"passed {passed}, failed {len(failures)}")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
