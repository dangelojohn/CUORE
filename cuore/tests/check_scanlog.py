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

# A demo/replay read, timestamped well clear of either real window (>15 min
# from both), tagged with a non-serial stream -- is_from_car() must reject
# it outright, so it must never become a scan, and P9999 must never appear
# anywhere in the scan log.
_write(OLDER + timedelta(hours=1), "obd_dtcs", {"kind": "stored", "dtcs": ["P9999"]},
      vin=VIN, stream="demo")

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

NEWER_ID = NEWER.strftime(scanlog.ID_FMT)
OLDER_ID = OLDER.strftime(scanlog.ID_FMT)


# ===========================================================================
# cuore.live.scanlog -- direct
# ===========================================================================

scans = scanlog.list_scans(VIN)
check("exactly 2 scans are grouped for this VIN", len(scans) == 2, str(len(scans)))
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

check("unknown scan id resolves to None", scanlog.get_scan(VIN, "SCAN_0000000000") is None)
check("a different VIN sees no scans", scanlog.list_scans("UNKNOWNVIN0000000") == [])


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


# ===========================================================================
# HTTP: TestClient only, never COM3 / a live adapter endpoint
# ===========================================================================

r = client.get(f"/api/scans/{VIN}")
check("GET /api/scans/{vin} is 200", r.status_code == 200, str(r.status_code))
check("it lists both scans", len(r.json()["scans"]) == 2, str(r.json()))

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

r = client.get(f"/v/{VIN}/scans/{NEWER_ID}")
check("GET /v/{vin}/scans/{id} page is 200", r.status_code == 200, str(r.status_code))
check("the detail page shows the fuel_level freeze frame",
      "Fuel level" in r.text, "Fuel level not in page body")
check("the detail page shows the Mode 06 FAIL chip", "FAIL" in r.text, "FAIL not in page body")
check("the detail page offers a compare-with-previous section",
      OLDER_ID in r.text, "previous scan id not linked from the detail page")

r = client.get(f"/v/{VIN}/scans/SCAN_0000000000")
check("GET /v/{vin}/scans/{unknown id} page is 404", r.status_code == 404, str(r.status_code))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
