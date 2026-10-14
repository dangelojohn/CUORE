"""Checks for the scan log (``cuore.live.scanlog``, ``cuore.services.scanlog_bridge``,
``cuore.api.scanlog``, ``cuore.web.scanlog_routes``).

Answers the owner's question "does CUORE have a log area to save the freeze
frame data?" -- it did not; this groups the from-car rows already appended
to ``observations.jsonl`` into browsable scans on read. Nothing here is a
second copy of the truth and nothing here opens COM3 or calls a live
adapter endpoint: every observation below is a hand-built fixture appended
straight to a throwaway ``observations.jsonl`` (same posture as
``cuore/tests/check_detail.py``/``check_dossier_view.py``), tagged with a
real ``stream="serial COM3@115200"`` value so ``is_from_car`` accepts it the
same way a real bench read would.

Same posture as ``cuore/tests/check_dossier_view.py``: ``CUORE_STATE_DIR``
points at a throwaway directory BEFORE cuore is imported, and this app's own
router may not be wired into ``create_app()`` yet elsewhere in a concurrent
edit -- it is included defensively if missing.

Run:
    .venv/Scripts/python.exe cuore/tests/check_scanlog.py
    .venv/Scripts/python.exe cuore/tests/check_screens.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-scanlog-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.api import scanlog as scanlog_api  # noqa: E402
from cuore.web import scanlog_routes  # noqa: E402
from cuore.live import scanlog, store as live_store  # noqa: E402
from cuore.services import scanlog_bridge  # noqa: E402
from cuore.services.errors import NotFound  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real VIN used across this suite's fixtures

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


app = create_app()
existing_paths = {getattr(r, "path", None) for r in app.routes}
if "/api/scans/{vin}" not in existing_paths:
    app.include_router(scanlog_api.router, prefix="/api")
if "/v/{vin}/scans" not in existing_paths:
    app.include_router(scanlog_routes.router)
client = TestClient(app)


def _write(at: datetime, kind: str, data: dict, *, vin: str = "",
          stream: str = "serial COM3@115200") -> None:
    entry = {"at": at.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "vin": vin,
             "bus": "can_c", "cable": "none", "stream": stream, "data": data}
    with live_store.observations_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ===========================================================================
# Fixture: one older, clean scan; one newer scan with findings; one
# demo/replay row that must never surface as a scan of its own.
# ===========================================================================

OLDER = datetime(2026, 10, 13, 18, 0, 0)
_write(OLDER, "obd_dtcs", {"kind": "stored", "dtcs": [], "by_ecu": {"18DAF110": []}})
_write(OLDER + timedelta(minutes=1), "readiness",
      {"since_clear": {"mil_on": False, "stored_dtc_count": 0,
                        "monitors": [{"monitor": "Evaporative system", "supported": True,
                                      "complete": True}],
                        "all_complete": True}}, vin=VIN)
# A full/guided scan's own scan_coverage observation, same cluster (within
# WINDOW of the readiness read above): CAN-C swept (5 modules answered),
# IHS/CH never attempted -- the exact coverage line the owner's own spec
# quotes.
_write(OLDER + timedelta(minutes=2), "scan_coverage", {
    "scan_id": "SCAN_" + OLDER.strftime("%y%m%d%H%M"), "vin": VIN, "cable": "none",
    "buses_attempted": ["can_c"], "duration_s": 12.0, "steps": [],
    "coverage": [{"bus": "can_c", "module": m, "category": "answered", "why": None,
                  "active": 0, "history": 0, "not_run": 0}
                for m in ("ECM", "IPC", "TCM", "DTCM", "ESM")],
    "counts": {"active": 0, "history": 0, "not_run": 0},
}, vin=VIN)

# A demo/replay read, timestamped well clear of either real window (>15 min
# from both), tagged with a non-serial stream -- is_from_car() must reject
# it outright, so it must never become a scan, and P9999 must never appear
# anywhere in the scan log.
_write(OLDER + timedelta(hours=1), "obd_dtcs", {"kind": "stored", "dtcs": ["P9999"]},
      vin=VIN, stream="demo")

# A manual, single-purpose read (Codes/Live/Tests, not a guided/full scan)
# more than 15 min clear of both real windows -- its own "partial" scan:
# still a scan (counted by scan_plan), but with no scan_coverage observation
# at all.
PARTIAL = OLDER + timedelta(minutes=40)
_write(PARTIAL, "freeze_frame",
      {"pid": "02", "name": None, "by_ecu": {"18DAF110": {"dtc": "P0128", "bytes": ["00", "00"]}}},
      vin=VIN)
PARTIAL_ID = PARTIAL.strftime(scanlog.ID_FMT)

NEWER = datetime(2026, 10, 13, 20, 0, 0)
_write(NEWER, "obd_dtcs",
      {"kind": "stored", "dtcs": ["P0440"], "by_ecu": {"18DAF110": ["P0440"]}})
_write(NEWER + timedelta(minutes=3), "obd_dtcs",
      {"kind": "pending", "dtcs": ["P0455"], "by_ecu": {"18DAF110": ["P0455"]}})
_write(NEWER + timedelta(minutes=6), "readiness",
      {"since_clear": {"mil_on": True, "stored_dtc_count": 1,
                        "monitors": [{"monitor": "Evaporative system", "supported": True,
                                      "complete": True}],
                        "all_complete": True}}, vin=VIN)
_write(NEWER + timedelta(minutes=9), "mode06",
      {"results": {"3A": {"by_ecu": {"18DAF110": [
          {"mid": "3A", "mid_name": "EVAP leak monitor", "tid": "91", "uasid": "30",
           "unit": "ms", "value": 100, "min": 0, "max": 50, "passed": False}]}}},
       "evap_summary": ["EVAP leak monitor: value 100 ms vs limit 50 ms -> FAIL"]}, vin=VIN)
_write(NEWER + timedelta(minutes=12), "freeze_frame",
      {"pid": "02", "name": None, "by_ecu": {"18DAF110": {"dtc": "P0440", "bytes": ["00", "00"]}}})
_write(NEWER + timedelta(minutes=13), "freeze_frame",
      {"pid": "2F", "name": "fuel_level",
       "by_ecu": {"18DAF110": {"pid": "2F", "name": "fuel_level", "bytes": ["6B"],
                                "unit": "%", "value": 42.0}}})
# A guided scan: CAN-C (6 modules, one ACTIVE) and CAN-IHS (2 modules) swept,
# CAN-CH never attempted.
_write(NEWER + timedelta(minutes=14), "scan_coverage", {
    "scan_id": "SCAN_" + NEWER.strftime("%y%m%d%H%M"), "vin": VIN, "cable": "blue_a5",
    "buses_attempted": ["can_c", "can_ihs"], "duration_s": 40.0, "steps": [],
    "coverage": ([{"bus": "can_c", "module": m, "category": "answered", "why": None,
                  "active": 1 if m == "ECM" else 0, "history": 0, "not_run": 0}
                 for m in ("ECM", "IPC", "TCM", "DTCM", "ESM", "BCM")]
                + [{"bus": "can_ihs", "module": m, "category": "answered", "why": None,
                   "active": 0, "history": 0, "not_run": 0}
                  for m in ("RFHUB", "DASM")]),
    "counts": {"active": 1, "history": 0, "not_run": 0},
    "guided": True, "guided_status": "done",
}, vin=VIN)

NEWER_ID = NEWER.strftime(scanlog.ID_FMT)
OLDER_ID = OLDER.strftime(scanlog.ID_FMT)


# ===========================================================================
# cuore.live.scanlog -- direct
# ===========================================================================

scans = scanlog.list_scans(VIN)
check("exactly 3 scans are grouped for this VIN (older, partial, newer)",
      len(scans) == 3, str(len(scans)))
check("newest scan listed first", bool(scans) and scans[0]["id"] == NEWER_ID,
      str([s["id"] for s in scans]))
check("no scan carries the demo-stream P9999 code",
      not any("P9999" in s["dtcs"]["stored"] for s in scans), str(scans))

newest = scanlog.get_scan(VIN, NEWER_ID)
check("newest scan found by id", newest is not None)
if newest:
    check("newest scan has stored P0440", newest["dtcs"]["stored"] == ["P0440"],
          str(newest["dtcs"]))
    check("newest scan has pending P0455", newest["dtcs"]["pending"] == ["P0455"],
          str(newest["dtcs"]))
    check("MIL is on", newest["mil"] is True, str(newest["mil"]))

    mode06_3a = next((r for r in newest["mode06"] if r["mid"] == "3A"), None)
    check("Mode 06 3A is present", mode06_3a is not None, str(newest["mode06"]))
    check("Mode 06 3A FAILed", bool(mode06_3a) and mode06_3a["passed"] is False,
          str(mode06_3a))

    ff = next((f for f in newest["freeze_frames"] if f["code"] == "P0440"), None)
    check("a P0440 freeze frame is present", ff is not None, str(newest["freeze_frames"]))
    fuel = next((p for p in (ff or {}).get("pids", []) if p["pid"] == "2F"), None)
    check("the freeze frame lists the fuel_level PID", fuel is not None, str(ff))
    check("its name is sentence-cased", bool(fuel) and fuel["name"] == "Fuel level",
          str(fuel))
    check("its value round-trips", bool(fuel) and fuel["value"] == 42.0, str(fuel))

older = scanlog.get_scan(VIN, OLDER_ID)
check("older scan found by id", older is not None)
if older:
    check("older scan has no stored codes", older["dtcs"]["stored"] == [], str(older["dtcs"]))
    check("older scan is not partial (it has a scan_coverage observation)",
          older["partial"] is False, str(older["partial"]))
    check("older scan's coverage line matches the owner's own spec wording",
          older["coverage"]["line"] ==
          "CAN-C 5 modules · IHS not scanned (blue A5) · CH not scanned (grey A6)",
          str((older.get("coverage") or {}).get("line")))

check("newest scan's coverage shows the IHS pass (guided scan)",
      bool(newest) and "IHS 2 modules" in (newest["coverage"] or {}).get("line", ""),
      str((newest or {}).get("coverage")))
check("newest scan is not partial", bool(newest) and newest["partial"] is False)

partial = scanlog.get_scan(VIN, PARTIAL_ID)
check("the manual freeze-panel-only scan is found by id", partial is not None)
if partial:
    check("it has no scan_coverage observation -> coverage is None",
          partial["coverage"] is None, str(partial["coverage"]))
    check("it is labelled partial", partial["partial"] is True, str(partial["partial"]))

check("unknown scan id resolves to None", scanlog.get_scan(VIN, "SCAN_0000000000") is None)
check("a different VIN sees no scans", scanlog.list_scans("UNKNOWNVIN0000000") == [])


# --- scan plan (the "Scan n of 10" chip) --------------------------------------

plan = scanlog.scan_plan(VIN)
check("scan_plan counts every scan, guided/full and partial alike",
      plan == {"count": 3, "total": 10}, str(plan))
check("a vehicle with no scans plans 0 of 10",
      scanlog.scan_plan("UNKNOWNVIN0000000") == {"count": 0, "total": 10})


# --- diff --------------------------------------------------------------------

d = scanlog.diff(VIN, OLDER_ID, NEWER_ID)
check("diff between the two scans exists", d is not None)
if d:
    check("diff reports P0440 added (stored)", d["codes"]["stored"]["added"] == ["P0440"],
          str(d["codes"]))
    check("diff reports a Mode 06 3A change", any(c["mid"] == "3A" for c in d["mode06_changes"]),
          str(d["mode06_changes"]))
    check("diff reports a readiness/MIL change",
          any(c["monitor"] == "MIL" for c in d["readiness_changes"]),
          str(d["readiness_changes"]))
    check("diff reports the coverage change (IHS now swept)",
          bool(d["coverage_changes"]) and "IHS 2 modules" in d["coverage_changes"][0]["after"],
          str(d["coverage_changes"]))
    check("diff reports no status_changes between these two (no code moved bucket)",
          d["status_changes"] == [], str(d["status_changes"]))
check("diff against an unknown scan id returns None", scanlog.diff(VIN, OLDER_ID, "SCAN_x") is None)


# --- MES export ----------------------------------------------------------------

mes_text = scanlog.export_mes_text(newest)
# cuore.bootstrap (imported as a side effect of cuore.app, above) already put
# mes-log-mcp's own "mes" package on sys.path -- the one place that happens,
# per that module's own docstring.
from mes import scan as mes_scan  # noqa: E402

parsed = mes_scan.parse_scan_text(mes_text, name=f"{NEWER_ID}.txt")
all_codes = {d.code for d in parsed.all_dtcs}
check("the MES export parses", parsed is not None)
check("the MES export's codes include P0440", "P0440" in all_codes, str(all_codes))
check("the MES export's codes include P0455", "P0455" in all_codes, str(all_codes))

written = scanlog.write_mes_export(VIN, NEWER_ID)
check("write_mes_export wrote under CUORE_STATE_DIR/scans/<vin>/, never MES's own folder",
      written is not None and "scans" in written.parts and VIN in written.parts,
      str(written))


# ===========================================================================
# cuore.services.scanlog_bridge
# ===========================================================================

try:
    scanlog_bridge.scan(VIN, "SCAN_0000000000")
    check("bridge raises NotFound for an unknown scan id", False)
except NotFound:
    check("bridge raises NotFound for an unknown scan id", True)

export_json = scanlog_bridge.export(VIN, NEWER_ID, "json")
check("bridge json export carries the scan's own id",
      export_json["content"]["id"] == NEWER_ID, str(export_json["content"].get("id")))
export_mes = scanlog_bridge.export(VIN, NEWER_ID, "mes")
check("bridge mes export is text containing the stored code",
      "P0440" in export_mes["content"], export_mes["content"][:200])

check("bridge scan_plan matches cuore.live.scanlog.scan_plan",
      scanlog_bridge.scan_plan(VIN) == {"count": 3, "total": 10},
      str(scanlog_bridge.scan_plan(VIN)))


# ===========================================================================
# HTTP: TestClient only, never COM3 / a live adapter endpoint
# ===========================================================================

r = client.get(f"/api/scans/{VIN}")
check("GET /api/scans/{vin} is 200", r.status_code == 200, str(r.status_code))
check("it lists all 3 scans", len(r.json()["scans"]) == 3, str(r.json()))

r = client.get(f"/api/scans/{VIN}/{NEWER_ID}")
check("GET /api/scans/{vin}/{id} is 200", r.status_code == 200, str(r.status_code))

r = client.get(f"/api/scans/{VIN}/diff", params={"a": OLDER_ID, "b": NEWER_ID})
check("GET /api/scans/{vin}/diff is 200", r.status_code == 200, str(r.status_code))
check("it reports P0440 added", r.json()["codes"]["stored"]["added"] == ["P0440"], str(r.json()))

r = client.get(f"/api/scans/{VIN}/{NEWER_ID}/export", params={"fmt": "json"})
check("export?fmt=json is 200", r.status_code == 200, str(r.status_code))
r = client.get(f"/api/scans/{VIN}/{NEWER_ID}/export", params={"fmt": "mes"})
check("export?fmt=mes is 200", r.status_code == 200, str(r.status_code))
check("the mes export body round-trips through the real parser",
      "P0440" in {d.code for d in mes_scan.parse_scan_text(r.text).all_dtcs}, r.text[:200])

r = client.get(f"/api/scans/{VIN}/SCAN_0000000000")
check("GET of an unknown scan is 404", r.status_code == 404, str(r.status_code))

r = client.get(f"/v/{VIN}/scans")
check("GET /v/{vin}/scans page is 200", r.status_code == 200, str(r.status_code))
check("the list page shows the newest scan's stored code",
      "P0440" in r.text, "P0440 not in page body")
check("the list page shows the scan plan chip (3 scans on file, out of 10)",
      "Scan 3 of 10" in r.text, "'Scan 3 of 10' not in page body")
check("the list page marks the manual scan partial",
      "partial" in r.text, "'partial' not in page body")
check("the list page offers a per-scan Health report link",
      f"/v/{VIN}/scans/{NEWER_ID}/health" in r.text,
      "no Health report link for the newest scan")
check("the list page offers a compare picker (two selects + a Compare button)",
      '<select name="a"' in r.text and '<select name="b"' in r.text
      and "Compare</button>" in r.text,
      "compare picker not found on the list page")

r = client.get(f"/v/{VIN}/scans/{NEWER_ID}")
check("GET /v/{vin}/scans/{id} page is 200", r.status_code == 200, str(r.status_code))
check("the detail page shows the fuel_level freeze frame",
      "Fuel level" in r.text, "Fuel level not in page body")
check("the detail page shows the Mode 06 FAIL chip", "FAIL" in r.text, "FAIL not in page body")
check("the detail page shows its own coverage line",
      "IHS 2 modules" in r.text, "coverage line not on the detail page")
# The nearest EARLIER scan to NEWER is the manual partial scan (18:40),
# not the older full scan (18:00) -- "previous" is nearest, not "first".
check("the detail page offers a compare-with-previous section, linking the "
      "nearest earlier scan",
      PARTIAL_ID in r.text, "nearest-previous scan id not linked from the detail page")

r = client.get(f"/v/{VIN}/scans/SCAN_0000000000")
check("GET /v/{vin}/scans/{unknown id} page is 404", r.status_code == 404, str(r.status_code))


# --- the diff page, its own route ---------------------------------------------

r = client.get(f"/v/{VIN}/scans/diff", params={"a": OLDER_ID, "b": NEWER_ID})
check("GET /v/{vin}/scans/diff is 200", r.status_code == 200, str(r.status_code))
check("the diff page shows the added stored code", "P0440" in r.text, r.text[:200])
check("the diff page shows the Mode 06 flip", "FAIL" in r.text, r.text[:200])
check("the diff page shows the coverage change", "IHS 2 modules" in r.text, r.text[:200])

r = client.get(f"/v/{VIN}/scans/diff", params={"a": OLDER_ID, "b": "SCAN_0000000000"})
check("GET /v/{vin}/scans/diff with an unknown scan id is 404",
      r.status_code == 404, str(r.status_code))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
