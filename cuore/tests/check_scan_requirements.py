"""Checks for "what CUORE must capture at every scan"
(``cuore/data/scan_requirements.json``, ``cuore.services.scan_requirements_bridge``
and the block on the guided-scan page).

Same posture as check_scan_plan.py: ``CUORE_STATE_DIR`` points at a fresh
directory BEFORE cuore is imported, every observation is a hand-built fixture
appended straight to ``observations.jsonl`` with a real ``serial`` stream tag
and an explicit timestamp, and nothing here opens COM3.

Four checks:
  1. the requirement list loads and is well-formed;
  2. a fake scan that captured everything has no gaps;
  3. a NO DATA scan gets the tool-fault reason on every legislated gap, and
     UDS reads that worked are not blamed on the route;
  4. mechanic_input items are always "needs mechanic", never failures (in the
     bridge result and on the rendered scan page).

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_scan_requirements.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-scan-req-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import store as live_store  # noqa: E402
from cuore.live.config import state_dir  # noqa: E402
from cuore.services import scan_requirements_bridge as bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
ECM = "18DAF110"
STREAM = "serial COM3@115200"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def _write(at: datetime, kind: str, data: dict, *, vin: str = VIN) -> None:
    entry = {"at": at.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "vin": vin,
             "bus": "can_c", "cable": "none", "stream": STREAM, "data": data}
    with live_store.observations_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _scan_id(t: datetime) -> str:
    return "SCAN_" + t.strftime("%y%m%d%H%M")


def _fake_scan(t0: datetime, *, no_data: bool) -> str:
    """One CAN-C guided-scan segment in the shapes fullscan records. With
    ``no_data`` every legislated (OBD) read comes back empty, as on
    2026-10-19, while the UDS reads still work."""
    sid = _scan_id(t0)
    at = lambda s: t0 + timedelta(seconds=s)  # noqa: E731

    if no_data:
        _write(at(5), "readiness", {
            "since_clear": {"error": "could not decode readiness response", "raw": "NO DATA"},
            "this_drive_cycle": {"error": "could not decode readiness response",
                                 "raw": "NO DATA"}})
        _write(at(8), "mode06", {"supported": {}, "results": {
            "3A": {"warning": "NO DATA"}, "3C": {"warning": "NO DATA"}}})
        _write(at(10), "pids_snapshot", {"by_ecu": {}})
        for kind in ("stored", "pending", "permanent"):
            _write(at(12), "obd_dtcs", {"dtc_kind": kind, "kind": kind, "raw": "NO DATA",
                                        "warning": "no ECU answered (NO DATA)"})
        _write(at(14), "mode09", {"mode09": {"raw": {}, "results": {
            "04": {"warning": "NO DATA"}, "06": {"warning": "NO DATA"}}},
            "gaps": ["calibration IDs (PID 04)"]})
    else:
        _write(at(5), "readiness", {
            "since_clear": {"ecu": ECM, "mil_on": True, "all_complete": False, "monitors": []},
            "this_drive_cycle": {"ecu": ECM, "mil_on": True, "monitors": []}})
        rec = [{"mid": "3A", "value": 404, "min": 3965, "max": 65535, "passed": False}]
        _write(at(8), "mode06", {"supported": {ECM: ["3A", "3C"]}, "results": {
            "3A": {"by_ecu": {ECM: rec}}, "3C": {"by_ecu": {ECM: rec}}}})
        reading = lambda v: {"name": "x", "value": v, "unit": ""}  # noqa: E731
        _write(at(10), "pids_snapshot", {"by_ecu": {ECM: {
            "46": reading(14), "2F": reading(91.8), "42": reading(14.2),
            "1F": reading(74), "30": reading(4), "31": reading(9)}}})
        for kind in ("stored", "pending", "permanent"):
            _write(at(12), "obd_dtcs", {"dtc_kind": kind, "kind": kind, "raw": "...",
                                        "dtcs": ["P0440"], "by_ecu": {ECM: ["P0440"]}})
        _write(at(14), "mode09", {"mode09": {"raw": {}, "results": {
            "04": {ECM: {"calibration_ids": ["P235QB39"]}},
            "06": {ECM: {"cvns": ["AB12CD34"]}}}}, "gaps": []})

    _write(at(20), "module_dtcs", {"ecu": "ECM", "bus": "can_c", "dtcs": [
        {"code": "P0440", "status": 0xCD, "flags": []},
        {"code": "P0455", "status": 0x4D, "flags": []},
        {"code": "P0456", "status": 0x4D, "flags": []}]})
    _write(at(22), "module_dtcs", {"ecu": "BCM", "bus": "can_c", "dtcs": [
        {"code": "U1713-2F", "status": 0x0F, "flags": []}]})
    _write(at(24), "module_identity", {"ecu": "ECM", "bus": "can_c", "fields": {
        "F188": {"ascii": "52170619", "bytes": ["35"]},
        "F194": {"ascii": "P235QB39", "bytes": ["50"]},
        "F187": {"ascii": "04861961", "bytes": ["30"]}}})
    for ecu, did in (("BCM", "1004"), ("BCM", "1005"), ("ECM", "19BD")):
        _write(at(26), "did", {"ecu": ecu, "bus": "can_c", "did": did, "bytes": ["90"]})
    _write(at(28), "evap_bundle", {"scan_id": sid, "codes": [
        {"code": "P0440", "status": 0xCD, "snapshot_decoded": {"fuel_level_pct": 91.8}},
        {"code": "P0455", "status": 0x4D, "snapshot_decoded": {"fuel_level_pct": 55.7}},
        {"code": "P0456", "status": 0x4D, "snapshot_decoded": {"fuel_level_pct": 62.7}}],
        "mode06": {}, "readiness": {}})
    steps = ([{"step": "obd_readiness", "ok": True}, {"step": "obd_mode06", "ok": True}]
             if not no_data else [])
    _write(at(40), "scan_coverage", {"scan_id": sid, "vin": VIN, "steps": steps,
                                     "coverage": [], "counts": {}})
    return sid


# ===========================================================================
# 1. the requirement list loads and is well-formed
# ===========================================================================
cfg = bridge.load()
rows = cfg["requirements"]
ids = [r["id"] for r in rows]
mech = [r for r in rows if r["source"] == "mechanic_input"]
machine = [r for r in rows if r["source"] != "mechanic_input"]
wanted_ids = {"readiness", "mode06_evap", "pids_enabling", "ecm_dtcs", "evap_bundle",
              "ecm_identity", "ibs_dids", "bcm_dtcs", "mes_clear_sync",
              "esim_switch_state", "esim_wire_voltage", "esim_fit", "slvt_result"}
check("1. requirement list loads and is well-formed",
      cfg["default_vin"] == VIN
      and len(ids) == len(set(ids)) and wanted_ids <= set(ids)
      and all(r["label"] and r["why"] and r["source"] in bridge.SOURCES for r in rows)
      and all(r["evidence_kind"].get("check") in bridge.CHECKERS for r in machine)
      and len(mech) == 4 and all(r["not_capturable_reason"] for r in mech)
      and "docs/research/CEL_2026-10-19_DIAGNOSIS.md" in cfg["silent_reason"],
      f"ids={ids} source/check problems="
      f"{[r['id'] for r in machine if r['evidence_kind'].get('check') not in bridge.CHECKERS]}")

# ===========================================================================
# 2. a fake scan with everything captured has no gaps
# ===========================================================================
T_GOOD = datetime(2026, 10, 19, 0, 23, 0)
good_id = _fake_scan(T_GOOD, no_data=False)
# the MES clear sync stamped after the scan began (mes_clear_watch.json)
(state_dir() / "mes_clear_watch.json").write_text(json.dumps({"vins": {VIN: {
    "last_mtime": 1.0, "synced_at": (T_GOOD + timedelta(minutes=10)).isoformat(
        timespec="seconds")}}}), encoding="utf-8")
good = bridge.check(good_id, VIN)
check("2. a scan that captured everything has no gaps",
      good["gaps"] == [] and good["captured"] == good["required"] == len(machine)
      and {m["id"] for m in good["met"]} == {r["id"] for r in machine}
      and good["summary"].startswith(f"Captured {len(machine)} of {len(machine)} required"),
      f"gaps={good['gaps']} not_applicable={good['not_applicable']}")

# ===========================================================================
# 3. NO DATA readiness -> a gap with the tool-fault reason
# ===========================================================================
T_BAD = datetime(2026, 10, 19, 12, 0, 0)
bad_id = _fake_scan(T_BAD, no_data=True)
bad = bridge.check(bad_id, VIN)
gap = {g["id"]: g for g in bad["gaps"]}
legislated = [r["id"] for r in machine if r["source"] == "legislated"]
tool_fault = cfg["silent_reason"]
uds_ok = {"ecm_dtcs", "bcm_dtcs", "ecm_identity", "ibs_dids", "evap_bundle"}
check("3. NO DATA readiness is a gap with the tool-fault reason",
      gap.get("readiness", {}).get("reason") == tool_fault
      and tool_fault.startswith("legislated route silent (tool fault, see docs/research/CEL_")
      and all(gap.get(i, {}).get("reason") == tool_fault for i in legislated)
      and uds_ok <= {m["id"] for m in bad["met"]}
      and not any(g["reason"] == tool_fault for g in bad["gaps"] if g["id"] not in legislated),
      f"gaps={ {k: v['reason'] for k, v in gap.items()} } met={[m['id'] for m in bad['met']]}")

# ===========================================================================
# 4. mechanic_input items are "needs mechanic", never failures
# ===========================================================================
mech_ids = {r["id"] for r in mech}
nm = {n["id"]: n for n in good["needs_mechanic"]}
nm_bad = {n["id"] for n in bad["needs_mechanic"]}
empty = bridge.check("SCAN_2701010101", VIN)  # a scan with no observations at all
page_ok = True
page_detail = ""
try:
    from fastapi.testclient import TestClient  # noqa: E402
    from cuore.app import create_app  # noqa: E402

    (state_dir() / "fullscan_guided.json").write_text(json.dumps({
        "scan_id": good_id, "vin": VIN, "started": T_GOOD.isoformat(timespec="seconds"),
        "stream": STREAM, "cable": "none", "status": "done", "pending_index": None,
        "segments": [{"n": i + 1, "cable": c, "bus": b, "status": "done", "why": None}
                     for i, (c, b) in enumerate([("none", "can_c"), ("blue_a5", "can_ihs"),
                                                 ("grey_a6", "can_ch"), ("none", "can_c")])],
        "steps": [], "coverage": [], "session_opens": 0}), encoding="utf-8")
    html = TestClient(create_app()).get(f"/v/{VIN}/scan")
    page_ok = (html.status_code == 200 and f"Captured {len(machine)} of {len(machine)} required" in html.text
               and "Needs mechanic (4)" in html.text and "SLVT" in html.text)
    page_detail = f"{html.status_code} {html.text[html.text.find('Required at every'):][:400]!r}"
except Exception as e:  # noqa: BLE001
    page_ok, page_detail = False, f"{type(e).__name__}: {e}"
check("4. mechanic_input items are 'needs mechanic', never failures",
      set(nm) == mech_ids and nm_bad == mech_ids
      and {n["id"] for n in empty["needs_mechanic"]} == mech_ids
      and all(n["status"] == "needs mechanic" and n["reason"] for n in nm.values())
      and not (mech_ids & {g["id"] for g in good["gaps"] + bad["gaps"] + empty["gaps"]})
      and not (mech_ids & {m["id"] for m in good["met"]})
      and empty["required"] == len(machine) and len(empty["gaps"]) == len(machine)
      and page_ok,
      page_detail)

print(f"\n{checks} checks, {len(failures)} failed")
if failures:
    print("FAILED: " + "; ".join(failures))
    sys.exit(1)
print("all green")
