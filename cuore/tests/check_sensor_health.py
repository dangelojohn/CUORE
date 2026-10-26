"""Checks for the sensor-health backend (``cuore.services.sensor_health``).

  * every colour (green / orange / red / grey) and its reason text
  * never read -> grey; CAN-CH sensors (readable:false) -> grey
  * range precedence (technician beats history), source labels, and the
    30-sample floor for the car's own history
  * add_range rejects an empty source
  * registry: unique ids, every channel id exists, zones are known
  * check_all with a monkeypatched live layer (no COM3): writes
    sensor_checks.jsonl; refuses cleanly when the live layer raises the
    MultiEcuScan-connected error and then writes nothing

Run:
    .venv/Scripts/python.exe cuore/tests/check_sensor_health.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TMP = Path(tempfile.mkdtemp(prefix="cuore-sensor-health-"))
os.environ["CUORE_STATE_DIR"] = str(TMP)

from cuore.live import errors as live_errors  # noqa: E402
from cuore.live import ops as live_ops  # noqa: E402
from cuore.live.channels import available_channels  # noqa: E402
from cuore.services import sensor_health as sh  # noqa: E402
from cuore.services.errors import BadRequest  # noqa: E402
from cuore.web.electrical_svg import ZONES  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
from datetime import datetime  # noqa: E402

NOW = datetime(2026, 10, 26, 12, 0, 0)
EVIDENCE: list = []
sh._scan_evidence = lambda: EVIDENCE      # no real MES logs touched


def H(now=NOW):
    return sh.health(VIN, now=now)


failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def write(name: str, text: str) -> None:
    (TMP / name).write_text(text, encoding="utf-8")


def jl(*objs) -> str:
    return "".join(json.dumps(o) + "\n" for o in objs)


def by_id(h: dict) -> dict:
    return {s["id"]: s for s in h["sensors"]}


# --- registry --------------------------------------------------------------
reg = sh.registry()
ids = [r["id"] for r in reg]
check(len(ids) == len(set(ids)) and len(ids) > 20, "registry ids unique")
known = {c.id for c in available_channels()}
check(all(ch in known for r in reg for ch in r["channels"]), "every registry channel exists")
zones = {z["id"] for z in ZONES} | {"front_bumper", "windscreen", "cabin_dash", "under_car_exhaust",
                                    "fuel_tank", "rear_bumper", "roof"}
check(all(r["zone"] is None or r["zone"] in zones for r in reg), "zones are known ids")
check(all(r["location_confidence"] in ("SOURCED", "INFERRED", "GENERAL", "UNKNOWN") for r in reg), "confidence values")
check(all("GENERAL KNOWLEDGE" in r["location_source"] for r in reg if r["location_confidence"] == "GENERAL"),
      "every general-knowledge area says so in its source text")
check(all((r["zone"] is None) == (r["location_confidence"] == "UNKNOWN") for r in reg),
      "no zone <=> UNKNOWN confidence")
check(all(r["location_source"] for r in reg), "every row carries a location_source")
check(all(not r["readable"] for r in reg if r["bus"] == "can_ch"), "CAN-CH rows are not readable")
check(all(r["readable"] for r in reg if r["channels"] and r["bus"] == "can_c"), "channel rows on CAN-C readable")

# --- fixtures ----------------------------------------------------------------
write("fullscan_last.json", json.dumps({
    "scan_id": "SCAN_2610241321", "vin": VIN,
    "coverage": [
        {"bus": "can_c", "module": "ECM", "category": "answered", "why": None, "active": 0},
        {"bus": "can_c", "module": "BCM", "category": "answered", "why": None, "active": 0},
        {"bus": "can_c", "module": "RFHUB", "category": "answered", "why": None, "active": 0},
        {"bus": "can_c", "module": "TCM", "category": "not_reachable", "why": "no known address", "active": 0},
        {"bus": "can_ch", "module": "ABS", "category": "not_reachable", "why": "needs grey A6 cable",
         "active": 0}]}))


def snap(at, **vals):
    return {"id": "s" + at, "at": at, "values": {k: {"value": v, "unit": "u"} for k, v in vals.items()}}


write("live_snapshots.jsonl", jl(snap("2026-10-20T10:00:00", engine_coolant_temp=90, intake_map=100,
                                      fuel_level=50, ecm_3a41=4.0, engine_oil_temp=95)))
write("sensor_checks.jsonl", jl({"at": "2026-10-25T09:00:00", "vin": VIN,
                                 "values": {"ecm_130a": 2.0},
                                 "errors": {"ecm_3a41": "no reply"},
                                 "modules_answered": {"ECM": True}}))

DTCS = [
    {"dtc": "P1189-00", "descriptions": ["Intake pressure sensor"], "modules": ["Engine / ECM"],
     "last_seen": "2026-10-25 08:00:00", "statuses_seen": ["stored"],
     "occurrences": [{"timestamp": "2026-10-25 08:00:00", "status": "stored"}]},
    {"dtc": "P0462-13", "descriptions": ["Fuel level sensor circuit"], "modules": ["Engine / ECM"],
     "last_seen": "2026-10-25 08:00:00", "statuses_seen": ["stored"],
     "occurrences": [{"timestamp": "2026-10-25 08:00:00", "status": "stored"}]},
    {"dtc": "P0116-00", "descriptions": ["Coolant temperature sensor"], "modules": ["Engine / ECM"],
     "last_seen": "2026-06-01 08:00:00", "statuses_seen": ["stored"],
     "occurrences": [{"timestamp": "2026-06-01 08:00:00", "status": "stored"}]},
    {"dtc": "P0117-00", "descriptions": ["Oil temperature sensor"], "modules": ["Engine / ECM"],
     "last_seen": "2026-10-25 08:00:00", "statuses_seen": ["stored", "cleared"],
     "occurrences": [{"timestamp": "2026-10-25 08:00:00", "status": "cleared"}]},
]
sh._load_dtcs = lambda vin: DTCS          # no MES logs touched

h = H()
S = by_id(h)
check(S["fuel_level"]["status"] == "red", "open-circuit code -> red")
check(any("open circuit" in r for r in S["fuel_level"]["reasons"]), "red reason names the failure type")
check(S["map_sensor"]["status"] == "orange", "non-circuit code -> orange")
check(S["map_sensor"]["codes"] and S["map_sensor"]["codes"][0]["code"] == "P1189-00", "code listed on sensor")
check(S["coolant_temp"]["status"] == "green", "stale code superseded by later clean scan -> green")
check(S["coolant_temp"]["codes"][0]["state"] == "superseded", "superseded state shown")
check(S["oil_temp"]["status"] == "green", "cleared code does not colour")
check(S["oil_pressure"]["status"] == "green" and S["oil_pressure"]["last_read"] == "2026-10-25T09:00:00",
      "green from sensor check value, last_read set")
check(S["oil_level"]["status"] == "grey" and any("Did not answer this time" in r for r in S["oil_level"]["reasons"]),
      "every channel timed out -> grey, not red")
check(S["gearbox_oil_temp"]["status"] == "red" and any("did not answer" in r for r in S["gearbox_oil_temp"]["reasons"]),
      "module not answering -> red")
check(S["ac_pressure"]["status"] == "grey" and any("Never read" in r for r in S["ac_pressure"]["reasons"]),
      "never read -> grey")
check(S["wheel_speed_fl"]["status"] == "grey" and not S["wheel_speed_fl"]["readable"], "CAN-CH sensor -> grey")
check(any("CAN-CH" in r for r in S["wheel_speed_fl"]["reasons"]), "grey reason says CAN-CH cable")
check(h["counts"] == {k: sum(1 for s in h["sensors"] if s["status"] == k) for k in ("green", "orange", "red", "grey")}
      and sum(h["counts"].values()) == len(reg), "counts add up")
check(set(h["unplaced"]) == {r["id"] for r in reg if r["zone"] is None}, "unplaced lists zone-less ids")
check(h["checked_at"] == "2026-10-25T09:00:00" and h["vin"] == VIN, "checked_at / vin")
check(S["fuel_level"]["values"][0]["range"] is None and S["fuel_level"]["values"][0]["in_range"] is None,
      "no range -> in_range None")

# orange from a channel that errored while another answered
write("sensor_checks.jsonl", jl({"at": "2026-10-25T09:00:00", "vin": VIN,
                                 "values": {"ecm_130a": 2.0, "engine_oil_temp": 95},
                                 "errors": {"ecm_3a41": "no reply"}, "modules_answered": {"ECM": True}},
                                {"at": "2026-10-25T09:05:00", "vin": VIN, "values": {"engine_coolant_temp": 90},
                                 "errors": {"ecm_1003": "timeout"}, "modules_answered": {"ECM": True}}))
S = by_id(H())
check(S["coolant_temp"]["status"] == "green" and any("Did not answer this time" in r for r in S["coolant_temp"]["reasons"]),
      "one channel timed out, other answered -> green with the failure listed")

# "no data" = the car does not offer that channel: never a fault colour
write("sensor_checks.jsonl", jl({"at": "2026-10-25T09:00:00", "vin": VIN,
                                 "values": {"engine_coolant_temp": 90},
                                 "errors": {"ecm_1003": "no data", "engine_oil_temp": "no data"},
                                 "modules_answered": {"ECM": True, "TCM": False}}))
S = by_id(H())
check(S["coolant_temp"]["status"] == "green" and any("gives no data" in r for r in S["coolant_temp"]["reasons"]),
      "no-data channel next to a read one -> green, listed")
check(S["oil_temp"]["status"] == "grey" and any("gives no data" in r for r in S["oil_temp"]["reasons"]),
      "only no-data channels -> grey")
check(S["gearbox_oil_temp"]["status"] != "red" or any("last full scan" in r for r in S["gearbox_oil_temp"]["reasons"]),
      "a sensor check with no answers never makes a module red by itself")

# --- stale reads ---------------------------------------------------------------
S = by_id(H(now=datetime(2026, 11, 20)))
check(S["coolant_temp"]["status"] == "grey" and S["coolant_temp"]["stale"] is True
      and S["coolant_temp"]["last_read"] and S["coolant_temp"]["values"], "old read -> grey, stale, values kept")
check("not current health" in S["coolant_temp"]["reasons"][0] and "days ago" in S["coolant_temp"]["reasons"][0],
      "stale reason text")
check(by_id(H())["coolant_temp"]["stale"] is False, "recent read not stale")
check(S["fuel_level"]["status"] == "red", "current red code applies even when the read is stale")
check(sh.STALE_AFTER_DAYS == 7, "STALE_AFTER_DAYS is 7")

# --- superseded codes: later MES scan / UDS read ----------------------------------
DTCS.append({"dtc": "C141B-97", "descriptions": ["Camera blinded"], "modules": ["Other / DASM (Driver)"],
             "last_seen": "2026-10-24 13:16:00", "statuses_seen": ["stored"],
             "occurrences": [{"timestamp": "2026-10-24 13:16:00", "status": "stored"}]})
check(by_id(H())["adas_camera"]["status"] == "orange", "stored camera code -> orange before later evidence")
EVIDENCE.append({"at": "2026-10-25T13:45:00", "label": "SCAN_2610251345",
                 "modules": {"DASM": set(), "ECM": {"P1189-00"}}})
S = by_id(H())
check(S["adas_camera"]["status"] == "grey" and S["adas_camera"]["codes"][0]["state"] == "superseded",
      "later MES scan lists module without the code -> superseded")
check(any("not present in SCAN_2610251345 at 13:45" in r for r in S["adas_camera"]["reasons"]),
      "reason names the scan evidence")
check(S["map_sensor"]["status"] == "orange", "later scan still listing the code keeps it")
EVIDENCE.clear()
write("observations.jsonl", jl({"at": "2026-10-25T13:35:00", "kind": "module_dtcs",
                                "data": {"ecu": "DASM", "error": None, "codes": []}}))
S = by_id(H())
check(S["adas_camera"]["codes"][0]["state"] == "superseded"
      and "CUORE module DTC read" in S["adas_camera"]["codes"][0]["superseded_by"], "UDS read supersedes")
write("observations.jsonl", jl({"at": "2026-10-25T13:35:00", "kind": "module_dtcs",
                                "data": {"ecu": "DASM", "error": "timeout", "codes": []}}))
check(by_id(H())["adas_camera"]["codes"][0]["state"] == "stored", "failed UDS read does not supersede")
write("observations.jsonl", "")

# --- ranges ----------------------------------------------------------------
try:
    sh.add_range("stelvio-2018-2.0", "coolant_temp", "engine_coolant_temp", 70, 110, "C", "   ", "t")
    check(False, "add_range rejects empty source")
except BadRequest:
    check(True, "add_range rejects empty source")
check(not (TMP / "sensor_ranges.jsonl").exists(), "rejected range not written")
for bad in (("nope", "engine_coolant_temp"), ("coolant_temp", "intake_map")):
    try:
        sh.add_range("stelvio-2018-2.0", bad[0], bad[1], 0, 1, "C", "src")
        check(False, f"add_range rejects {bad}")
    except BadRequest:
        check(True, f"add_range rejects {bad}")

# 29 samples -> no history range; 30 -> history range
vals = [80 + i * 0.5 for i in range(29)]
write("live_snapshots.jsonl", jl(*[snap(f"2026-10-{1 + i // 3:02d}T10:{i % 60:02d}:00", engine_coolant_temp=v)
                                   for i, v in enumerate(vals)]))
write("sensor_checks.jsonl", "")
S = by_id(H())
check(S["coolant_temp"]["values"][0]["range"] is None, "29 samples -> no history range")
vals.append(90.0)
write("live_snapshots.jsonl", jl(*[snap(f"2026-10-{1 + i // 3:02d}T10:{i % 60:02d}:00", engine_coolant_temp=v)
                                   for i, v in enumerate(vals)]))
S = by_id(H())
rg = S["coolant_temp"]["values"][0]["range"]
check(rg is not None and rg["kind"] == "history" and "30 samples" in rg["source"]
      and "this car's own history" in rg["source"], "30 samples -> labelled history range")
check(S["coolant_temp"]["values"][0]["in_range"] is True, "latest value inside history range")
# latest value far outside history -> orange
write("sensor_checks.jsonl", jl({"at": "2026-12-01T00:00:00", "vin": VIN, "values": {"engine_coolant_temp": 140},
                                 "errors": {}, "modules_answered": {"ECM": True}}))
S = by_id(H())
check(S["coolant_temp"]["status"] == "orange" and S["coolant_temp"]["values"][0]["in_range"] is False,
      "outside history range -> orange")
# technician range wins and is labelled
rec = sh.add_range("stelvio-2018-2.0", "coolant_temp", "engine_coolant_temp", 60, 150, "C",
                   "workshop manual p.12", "tech")
S = by_id(H())
rg = S["coolant_temp"]["values"][0]["range"]
check(rg["kind"] == "technician" and "workshop manual p.12" in rg["source"] and rg["min"] == 60,
      "technician range beats history, labelled with its source")
check(S["coolant_temp"]["values"][0]["in_range"] is True and S["coolant_temp"]["status"] == "green",
      "value inside technician range -> green")
check(rec["model_key"] == "stelvio-2018-2.0", "range keyed by model")

# --- check_all with a fake live layer ---------------------------------------
calls: list[str] = []


def fake_start(channels=None, **kw):
    calls.append("start")
    assert all(c.bus == "can_c" for c in available_channels() if c.id in channels), "only CAN-C requested"
    return {}


def fake_snapshot():
    calls.append("snapshot")
    chans = {}
    for c in available_channels():
        chans[c.id] = {"value": None, "unit": "", "last_error": "no reply"}
    chans["engine_coolant_temp"] = {"value": 91, "unit": "C", "last_error": None}
    return {"active": True, "channels": chans}


live_ops.live_session_start = fake_start
live_ops.live_snapshot = fake_snapshot
live_ops.live_session_stop = lambda: calls.append("stop") or {}
write("sensor_checks.jsonl", "")
res = sh.check_all(VIN, timeout_s=2, poll_s=0.01)
rows = [json.loads(x) for x in (TMP / "sensor_checks.jsonl").read_text(encoding="utf-8").splitlines()]
check(res["ok"] and len(rows) == 1, "check_all appends one record")
check(set(rows[0]) == {"at", "vin", "values", "errors", "modules_answered"}, "record shape")
check(rows[0]["values"] == {"engine_coolant_temp": 91} and "ecm_130a" in rows[0]["errors"], "values and errors split")
check(rows[0]["modules_answered"].get("ECM") is True and rows[0]["modules_answered"].get("TCM") is False,
      "modules_answered from channel results")
check(calls[0] == "start" and calls[-1] == "stop", "session started then released")
check(res["checked"] > 0 and res["read"] == 1, "check_all reports sensors checked and how many gave a value")
rd = sh.readings(VIN)
check(rd["checks"] == [rows[0]["at"]], "readings lists each saved check")
cool = [r for r in rd["rows"] if r["channel"] == "engine_coolant_temp"]
check(len(cool) == 1 and cool[0]["value"] == 91 and "coolant_temp" in cool[0]["sensor_ids"] and cool[0]["error"] is None,
      "readings row carries value and owning sensor")
check(any(r["channel"] == "ecm_130a" and r["error"] == "no reply" for r in rd["rows"]), "readings keeps errors")
write("sensor_checks.jsonl", jl({"at": "2026-10-25T09:00:00", "vin": VIN,
                                 "values": {"o2_b1s1_wide_range": {"lambda": 0.99, "current_mA": 0.0}},
                                 "errors": {}, "modules_answered": {"ECM": True}}))
parts = {r["part"]: r["value"] for r in sh.readings(VIN)["rows"] if r["channel"] == "o2_b1s1_wide_range"}
check(parts == {"lambda": 0.99, "current_mA": 0.0}, "multi-part value split into one row per part")
check(not any(c.startswith("ecm_") and False for c in rows[0]["values"]) and
      all(ch in known for ch in list(rows[0]["values"]) + list(rows[0]["errors"])), "only registry channels")

before = (TMP / "sensor_checks.jsonl").read_text(encoding="utf-8")


def mes_connected(channels=None, **kw):
    raise live_errors.LinkUnavailable("MultiEcuScan is connected and holds the adapter")


live_ops.live_session_start = mes_connected
stopped: list[int] = []
live_ops.live_session_stop = lambda: stopped.append(1) or {}
res = sh.check_all(VIN, timeout_s=2, poll_s=0.01)
check(res["ok"] is False and res["refused"] is True and "MultiEcuScan" in res["error"], "MES connected -> clean refusal")
check((TMP / "sensor_checks.jsonl").read_text(encoding="utf-8") == before, "refusal writes nothing")
check(not stopped, "refused sweep does not stop someone else's session")

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
