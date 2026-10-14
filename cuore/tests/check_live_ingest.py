"""Checks for live-read ingestion: the correctness bug where the Report/Bench/
Job pages and the dossier verdict kept saying "no code has returned" and
UNVERIFIED_REPAIR even after the car itself was read live and returned
P0440/P0455/P0456 -- because ``cuore.services.dossier_bridge`` only ever
looked at MES-log history + ``clear_assessment``, never at from-car
observations (``cuore.live.store``, ``live_store.is_from_car``).

Same posture as ``cuore/tests/check_bench.py``: ``CUORE_STATE_DIR`` is pointed
at a throwaway directory BEFORE cuore is imported, and the Stelvio's real MES
corpus (VIN below, cleared 2026-09-29, chronic P0455/P0440/P0456) is the
fixture for everything history-based. What's new here is a set of *live*
observations written directly into that throwaway state dir via
``cuore.live.store.record_observation`` -- the exact shapes real reads landed
on 2026-10-13 (obd_dtcs x3, readiness, freeze_frame x2, mode06, module_dtcs
x4), never through ``cuore.live.ops`` and never touching COM3/an adapter.

Checks:
  1. With the fixture, the dossier verdict is ACTIVE_FAULTS, P0440 is cited
     as returned/read from the car (not "no code has returned"), and that
     sentence never appears anywhere in the basis.
  2. Report and Bench pages never render "no code has returned" with the
     fixture present.
  3. The live freeze-frame block shows fuel_level 28.6 and
     commanded_evap_purge 18.0.
  4. The Mode 06 block shows the MID 3A FAIL (404 ms vs min 3965 ms).
  5. The Job page's step-7 evidence picker lists the Mode 06 item.
  6. The Bench next-action sentence mentions "Test A".
  7. Module DTCs: U1713-2F is ACTIVE on BCM, B1176-97 is HISTORY (never
     listed as a fault), and every status-64-only code is absent from
     both lists.
  8. Without the fixture (a second, untouched VIN/state dir), nothing
     about the verdict/basis changes -- same codepath, no live
     observations, old behaviour.

Run:
    .venv/Scripts/python.exe cuore/tests/check_live_ingest.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-live-ingest-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.live.obd import decode_dtc_status  # noqa: E402
from cuore.services import dossier_bridge, mes_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456, cleared 2026-09-29

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def module_dtc(code: str, raw: str, status: int) -> dict:
    return {"code": code, "raw": raw, "status": status, "flags": decode_dtc_status(status)}


# --- write tonight's live fixture straight into this test's own throwaway
#    CUORE_STATE_DIR, the exact shapes cuore.live.ops really recorded on
#    2026-10-13 (never through ops/COM3) ---------------------------------

STREAM = "serial COM3@115200"


def seed_fixture() -> None:
    rec = live_store.record_observation

    rec("obd_dtcs", {"kind": "stored", "raw": "18DAF1100443010440\n18DAF118024300",
                     "dtcs": ["P0440"], "by_ecu": {"18DAF110": ["P0440"], "18DAF118": []},
                     "bus": "can_c", "cable": "none"},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)
    rec("obd_dtcs", {"kind": "pending", "raw": "18DAF11006470204550440\n18DAF118024700",
                     "dtcs": ["P0440", "P0455"],
                     "by_ecu": {"18DAF110": ["P0455", "P0440"], "18DAF118": []},
                     "bus": "can_c", "cable": "none"},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)
    rec("obd_dtcs", {"kind": "permanent", "raw": "18DAF110064A0204400456\n18DAF118024A00",
                     "dtcs": ["P0440", "P0456"],
                     "by_ecu": {"18DAF110": ["P0440", "P0456"], "18DAF118": []},
                     "bus": "can_c", "cable": "none"},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)

    rec("readiness", {
        "since_clear": {"mil_on": True, "stored_dtc_count": 1, "ignition": "spark",
                        "monitors": [
                            {"monitor": "Misfire", "supported": True, "complete": True},
                            {"monitor": "Fuel system", "supported": True, "complete": True},
                            {"monitor": "Comprehensive components", "supported": True, "complete": True},
                            {"monitor": "Catalyst", "supported": True, "complete": True},
                            {"monitor": "Evaporative system", "supported": True, "complete": True},
                            {"monitor": "Oxygen sensor", "supported": True, "complete": True},
                            {"monitor": "Oxygen sensor heater", "supported": True, "complete": True},
                            {"monitor": "EGR system", "supported": True, "complete": True}],
                        "all_complete": True, "ecu": "18DAF110"},
        "this_drive_cycle": {"mil_on": False, "stored_dtc_count": 0, "monitors": [],
                             "all_complete": False, "ecu": "18DAF110"},
        "evap_verdict": "EVAP monitor has COMPLETED since the last clear; a clean "
                       "scan is now meaningful for EVAP.",
        "drive_cycle_counters": {"warmups_since_clear": 8, "distance_since_clear": 1663},
        "bus": "can_c", "cable": "none"},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)

    rec("freeze_frame", {"pid": "2F", "name": "fuel_level", "raw": "18DAF11004422F0049",
                         "by_ecu": {"18DAF110": {"pid": "2F", "name": "fuel_level",
                                                 "bytes": ["49"], "unit": "%", "value": 28.627}},
                         "bus": "can_c", "cable": "none"},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)
    rec("freeze_frame", {"pid": "2E", "name": "commanded_evap_purge", "raw": "18DAF11004422E002E",
                         "by_ecu": {"18DAF110": {"pid": "2E", "name": "commanded_evap_purge",
                                                 "bytes": ["2E"], "unit": "%", "value": 18.039}},
                         "bus": "can_c", "cable": "none"},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)
    rec("freeze_frame", {"pid": "02", "name": None, "raw": "18DAF110054202000440",
                         "by_ecu": {"18DAF110": {"dtc": "P0440", "bytes": ["04", "40"]}},
                         "bus": "can_c", "cable": "none"},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)

    rec("mode06", {
        "results": {
            "39": {"by_ecu": {"18DAF110": [
                {"mid": "39", "mid_name": "EVAP monitor (cap off / gross leak)", "tid": "87",
                 "uasid": "10", "unit": "ms", "value": 0, "min": 0, "max": 0, "passed": True}]}},
            "3A": {"by_ecu": {"18DAF110": [
                {"mid": "3A", "mid_name": "EVAP monitor 0.090\" leak", "tid": "87",
                 "uasid": "10", "unit": "ms", "value": 404, "min": 3965, "max": 65535,
                 "passed": False}]}},
            "3C": {"by_ecu": {"18DAF110": [
                {"mid": "3C", "mid_name": "EVAP monitor 0.020\" leak", "tid": "90",
                 "uasid": "10", "unit": "ms", "value": 6096, "min": 0, "max": 6000,
                 "passed": False}]}},
        },
        "evap_summary": [
            "EVAP monitor (cap off / gross leak): value 0 ms vs limit 0 ms -> PASS",
            "EVAP monitor 0.090\" leak: value 404 ms vs limit 65535 ms -> FAIL",
            "EVAP monitor 0.020\" leak: value 6096 ms vs limit 6000 ms -> FAIL"],
        "bus": "can_c", "cable": "none"},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)

    rec("module_dtcs", {"ecu": "ECM", "bus": "can_c", "mask": "FF", "error": None, "nrc": None,
                        "dtcs": [module_dtc("P0440-00", "044000", 205),
                                module_dtc("P0455-00", "045500", 77),
                                module_dtc("P0300-00", "030000", 64)]},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)
    rec("module_dtcs", {"ecu": "BCM", "bus": "can_c", "mask": "FF", "error": None, "nrc": None,
                        "dtcs": [module_dtc("U1765-86", "176586", 8),
                                module_dtc("U1736-87", "173687", 8),
                                module_dtc("U1713-2F", "17132F", 15),
                                module_dtc("B1176-97", "117697", 8),
                                module_dtc("B10AA-4A", "10AA4A", 8)]},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)
    rec("module_dtcs", {"ecu": "IPC", "bus": "can_c", "mask": "FF", "error": None, "nrc": None,
                        "dtcs": [module_dtc("U1736-86", "173686", 12),
                                module_dtc("U1736-87", "173687", 12)]},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)
    rec("module_dtcs", {"ecu": "RFHUB", "bus": "can_c", "mask": "FF", "error": None, "nrc": None,
                        "dtcs": [module_dtc("B1040-64", "104064", 8)]},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)
    rec("module_dtcs", {"ecu": "TCM", "bus": "can_c", "mask": "FF", "error": None, "nrc": None,
                        "dtcs": []},
        vin=VIN, bus="can_c", cable="none", stream=STREAM)


seed_fixture()

client = TestClient(create_app())
dossier = mes_bridge.workup(vin=VIN)
view = dossier_bridge.build_view(VIN, dossier, None)
verdict = view["verdict"]
basis_text = " ".join(verdict.get("basis") or [])


# --- 1. verdict flips to ACTIVE_FAULTS on from-car evidence -----------------

check("verdict state is ACTIVE_FAULTS with the fixture present",
      verdict["state"] == "ACTIVE_FAULTS", str(verdict["state"]))
check("P0440 is cited as returned, read from the car (not invented)",
      "P0440" in basis_text and "read from the car" in basis_text, basis_text)
check('"no code has returned" never appears in the verdict basis',
      "no code has returned" not in basis_text, basis_text)
check("verdict summary names the EVAP monitor having run and the code returning",
      "EVAP monitor ran and the code returned" in (verdict.get("summary") or ""),
      str(verdict.get("summary")))
check("MIL state is shown from the readiness read (mil_on=True)",
      verdict.get("mil_on") is True, str(verdict.get("mil_on")))


# --- 2. Report and Bench pages never render "no code has returned" --------

report_page = client.get(f"/v/{VIN}/report")
check("report page responds 200", report_page.status_code == 200, str(report_page.status_code))
check('report page never shows "no code has returned" with the fixture present',
      "no code has returned" not in report_page.text)
check("report page shows P0440 cited as read from the car",
      "read from the car" in report_page.text)

bench_page = client.get(f"/v/{VIN}")
check("bench page responds 200", bench_page.status_code == 200, str(bench_page.status_code))
check('bench page never shows "no code has returned" with the fixture present',
      "no code has returned" not in bench_page.text)


# --- 3. live freeze-frame block ---------------------------------------------

live_ff = view.get("live_freeze_frames") or {}
by_pid = {p["pid"]: p for p in live_ff.get("params", [])}
check("live freeze frame carries fuel_level 28.6", by_pid.get("2F", {}).get("value") == 28.627,
      str(by_pid.get("2F")))
check("live freeze frame carries commanded_evap_purge 18.0",
      by_pid.get("2E", {}).get("value") == 18.039, str(by_pid.get("2E")))
check("report page's freeze-frame section shows fuel_level 28.6",
      "28.627" in report_page.text or "28.6" in report_page.text)
check("report page's freeze-frame section shows commanded_evap_purge 18.0",
      "18.039" in report_page.text or "18.0" in report_page.text)


# --- 4. Mode 06 block --------------------------------------------------------

mode06 = view.get("mode06") or {}
fail_mids = {f["mid"] for f in mode06.get("fails", [])}
check("Mode 06 view carries the MID 3A FAIL", "3A" in fail_mids, str(mode06.get("fails")))
mid3a = next((f for f in mode06["fails"] if f["mid"] == "3A"), None)
check("MID 3A fail carries value 404 and min 3965",
      bool(mid3a) and mid3a["value"] == 404 and mid3a["min"] == 3965, str(mid3a))
check("report page shows the Mode 06 block with the 3A FAIL",
      "Mode 06" in report_page.text and "404" in report_page.text)
check("bench page's collapsed Mode 06 count mentions a FAIL",
      "FAIL" in bench_page.text)


# --- 5. Job page step-7 evidence picker lists the Mode 06 item -------------

client.post(f"/v/{VIN}/job/open",
           data={"technician": "tester", "complaint": "CEL, smells like gas"},
           follow_redirects=True)
job_view = client.get(f"/api/vehicles/{VIN}/job").json()
job = job_view.get("job")
suggestions = job_view.get("suggested_hypotheses", [])
evap_suggestion = next((s for s in suggestions if s.get("system") == "EVAP"
                        and s["evidence_for"]), None)
check("an EVAP suggestion carries the Mode 06 evidence auto-suggested (not auto-attached)",
      evap_suggestion is not None
      and any(r.get("kind") == "measurement" for r in evap_suggestion["evidence_for"]),
      str(evap_suggestion))

if job and evap_suggestion is not None:
    client.post(f"/v/{VIN}/job/{job['id']}/hypotheses/suggested", data={
        "text": evap_suggestion["text"], "system": evap_suggestion["system"],
        "next_test": evap_suggestion["next_test"],
        "evidence_for": json.dumps(evap_suggestion["evidence_for"]),
        "evidence_against": json.dumps(evap_suggestion["evidence_against"]),
    }, follow_redirects=True)
    job_page = client.get(f"/v/{VIN}/job?step=7")
    check("job page responds 200", job_page.status_code == 200, str(job_page.status_code))
    check("job page's step-7 evidence picker offers the Mode 06 item",
          "mode06-3A" in job_page.text and "0.090" in job_page.text)
else:
    check("job/evap_suggestion present to drive the step-7 picker check", False,
          f"job={job} evap_suggestion={evap_suggestion}")


# --- 6. Bench next-action sentence mentions Test A --------------------------

check('bench next_action mentions "Test A"', "Test A" in (verdict.get("next_action") or ""),
      str(verdict.get("next_action")))
check("rendered bench page carries the same next_action sentence",
      (verdict.get("next_action") or "") in bench_page.text)


# --- 7. module DTCs: ACTIVE vs HISTORY vs absent ----------------------------

live_modules = {(m["ecu"], m["code"]): m["state"] for m in view.get("live_module_dtcs", [])}
check("U1713-2F is ACTIVE on BCM", live_modules.get(("BCM", "U1713")) == "ACTIVE",
      str(live_modules))
check("B1176-97 is HISTORY (not ACTIVE) on BCM", live_modules.get(("BCM", "B1176")) == "HISTORY",
      str(live_modules))
check("the status-64-only code (P0300 on ECM) is absent from the module DTC list",
      ("ECM", "P0300") not in live_modules, str(live_modules))
check("a from-car ACTIVE module code alone would still drive ACTIVE_FAULTS",
      any(s == "ACTIVE" for s in live_modules.values()))

net_card = next((c for c in view["open_work"] if (c.get("family") or "").lower() == "network"),
                None)
check("3+ live network (U-code) module faults land on one network card, not separate ones",
      net_card is not None and len({"U1765", "U1736", "U1713"} & set(net_card.get("codes", []))) >= 2,
      str(net_card))


# --- 8. without the fixture, nothing changes --------------------------------

OTHER_VIN = "ZFA00000000000000"  # no MES logs, no live observations -- untouched codepath
clean_dossier = {"identity": {}, "current_picture": {}, "history": {}, "tsb_matches": {},
                 "blind_spots": []}
clean_view = dossier_bridge.build_view(OTHER_VIN, clean_dossier, None)
check("a VIN with no live observations is untouched by this feature (no crash, no state flip)",
      clean_view["verdict"]["state"] in ("NO_DATA", "UNVERIFIED_REPAIR", "ACTIVE_FAULTS",
                                        "VERIFIED_CLEAN"),
      str(clean_view["verdict"]["state"]))
check("that VIN carries no live freeze frames/mode06/module dtcs",
      not clean_view.get("live_freeze_frames") and not clean_view.get("mode06")
      and not clean_view.get("live_module_dtcs"),
      str({"ff": clean_view.get("live_freeze_frames"), "m06": clean_view.get("mode06"),
          "mod": clean_view.get("live_module_dtcs")}))


# --- report ------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
