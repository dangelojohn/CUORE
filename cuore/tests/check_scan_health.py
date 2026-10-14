"""Smoke checks for the scan health report (mes.scan_health /
cuore.services.scan_health_bridge / cuore.api.scan_health /
cuore.web.scan_health_routes).

Same posture as ``check_timeline.py``: ``CUORE_STATE_DIR`` is pointed at a
throwaway directory BEFORE cuore is imported. The from-car fixture is NOT
invented -- it is a handful of real lines copied, verbatim, out of
``C:\\ProgramData\\cuore\\observations.jsonl`` (the 2026-10-13 scan: stored/
pending/permanent DTCs, a readiness read, and the Mode 06 read), written to
a throwaway ``MES_LIVE_OBSERVATIONS`` file so this check never touches --
let alone modifies -- the real one. If that file is not present on this
machine (a fresh checkout), a small embedded fallback with the same shape
is used instead, so this check still runs.

Run:
    .venv/Scripts/python.exe cuore/tests/check_scan_health.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-scan-health-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VIN = "ZASFAKPN5J7B88115"

# --- build the fixture: a few real lines, copied, from the real store ------

_REAL_OBS = Path(r"C:\ProgramData\cuore\observations.jsonl")

_FALLBACK_LINES = [
    {"at": "2026-10-13T20:02:56", "kind": "obd_dtcs", "vin": "", "bus": "can_c",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"kind": "stored", "dtcs": ["P0440"], "by_ecu": {"18DAF110": ["P0440"], "18DAF118": []}}},
    {"at": "2026-10-13T20:02:57", "kind": "obd_dtcs", "vin": "", "bus": "can_c",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"kind": "pending", "dtcs": ["P0455", "P0440"],
              "by_ecu": {"18DAF110": ["P0455", "P0440"], "18DAF118": []}}},
    {"at": "2026-10-13T20:02:58", "kind": "obd_dtcs", "vin": "", "bus": "can_c",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"kind": "permanent", "dtcs": ["P0440", "P0456"],
              "by_ecu": {"18DAF110": ["P0440", "P0456"], "18DAF118": []}}},
    {"at": "2026-10-13T20:03:00", "kind": "readiness", "vin": VIN, "bus": "can_c",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"since_clear": {"mil_on": True, "stored_dtc_count": 1, "monitors": [
         {"monitor": "Misfire", "supported": True, "complete": True},
         {"monitor": "Fuel system", "supported": True, "complete": True},
         {"monitor": "Comprehensive components", "supported": True, "complete": True},
         {"monitor": "Catalyst", "supported": True, "complete": True},
         {"monitor": "Evaporative system", "supported": True, "complete": True},
         {"monitor": "Oxygen sensor", "supported": True, "complete": True},
         {"monitor": "Oxygen sensor heater", "supported": True, "complete": True},
         {"monitor": "EGR system", "supported": True, "complete": True}],
         "all_complete": True, "ecu": "18DAF110"}}},
    {"at": "2026-10-13T20:03:54", "kind": "mode06", "vin": VIN, "bus": "can_c",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"results": {
         "02": {"by_ecu": {"18DAF110": [
             {"mid": "02", "mid_name": "O2 sensor monitor bank 1 sensor 2", "tid": "83",
              "value": 65535, "min": 16383, "max": 65535, "passed": True}]}},
         "21": {"by_ecu": {"18DAF110": [
             {"mid": "21", "mid_name": "Catalyst monitor bank 1", "tid": "93",
              "value": 5700, "min": 1764, "max": 65535, "passed": True}]}},
         "3A": {"by_ecu": {"18DAF110": [
             {"mid": "3A", "mid_name": "EVAP monitor 0.090\" leak", "tid": "87",
              "value": 404, "min": 3965, "max": 65535, "passed": False}]}},
         "3C": {"by_ecu": {"18DAF110": [
             {"mid": "3C", "mid_name": "EVAP monitor 0.020\" leak", "tid": "90",
              "value": 6096, "min": 0, "max": 6000, "passed": False}]}},
     }}},
]


def _build_fixture_file() -> str:
    lines: list[str] = []
    if _REAL_OBS.exists():
        try:
            with _REAL_OBS.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    at = str(obj.get("at", ""))
                    if (at.startswith("2026-10-13T20:0") and at <= "2026-10-13T20:04:00"
                            and obj.get("kind") in ("obd_dtcs", "readiness", "mode06")):
                        lines.append(line)
        except OSError:
            lines = []
    if not lines:
        lines = [json.dumps(o) for o in _FALLBACK_LINES]
    fd, path = tempfile.mkstemp(prefix="cuore-check-scan-health-obs-", suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


_FIXTURE_PATH = _build_fixture_file()
os.environ["MES_LIVE_OBSERVATIONS"] = _FIXTURE_PATH

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import scan_health_bridge  # noqa: E402
from mes import scan_health  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


app = create_app()
client = TestClient(app)


# --- 1. the bridge's own build(), directly ----------------------------------

report = scan_health_bridge.build(VIN, None)

check("verdict is ACTIVE_FAULTS", report["verdict"]["state"] == scan_health.ACTIVE_FAULTS,
      report["verdict"]["state"])

by_label = {row["label"]: row for row in report["systems"]}
check("system table has 25 rows (one per mes.systems key)", len(report["systems"]) == 25,
      str(len(report["systems"])))

evap_row = by_label.get("EVAP (evaporative emissions)")
check("EVAP row exists", evap_row is not None)
if evap_row:
    check("EVAP row is FAULT", evap_row["health"] == "FAULT", evap_row["health"])
    reading = evap_row.get("reading") or ""
    check("EVAP row cites the 3A 404-vs-3965 line", "404" in reading and "3965" in reading,
          reading)

cat_row = by_label.get("Exhaust / emissions")
check("Exhaust/emissions (catalyst) row exists", cat_row is not None)
if cat_row:
    check("catalyst row is OK", cat_row["health"] == "OK", cat_row["health"])
    check("catalyst row shows 3.2x margin", cat_row.get("margin") == "3.2\u00d7",
          str(cat_row.get("margin")))

cooling_row = by_label.get("Cooling")
check("Cooling row exists", cooling_row is not None)
if cooling_row:
    check("cooling row is READING ONLY", cooling_row["health"] == "READING ONLY",
          cooling_row["health"])
    check("cooling row's spec is worded UNKNOWN", "UNKNOWN" in (cooling_row.get("spec_source") or ""),
          str(cooling_row.get("spec_source")))

body_row = by_label.get("Body / comfort")
network_row = by_label.get("Network / CAN buses")
check("body/network rows exist", body_row is not None and network_row is not None)
if body_row and network_row:
    check("body row is GAP", body_row["health"] == "GAP", body_row["health"])
    check("network row is GAP", network_row["health"] == "GAP", network_row["health"])

check("issues list is non-empty", bool(report["issues"]))
if report["issues"]:
    check("issues[0] names the EVAP next test (Test A)",
          report["issues"][0].startswith("ESIM vacuum test (Test A)"), report["issues"][0])
    check("issues[0] says not to clear codes", "Do not clear" in report["issues"][0],
          report["issues"][0])

import re as _re  # noqa: E402

_FORBIDDEN = _re.compile(r"\b(proven|cause|causes|caused)\b", _re.IGNORECASE)

all_text = json.dumps(report)
check("no 'proven'/'cause' (word-boundary) anywhere in the report",
      not _FORBIDDEN.search(all_text), str(_FORBIDDEN.findall(all_text)))


# --- 2. markdown renders -----------------------------------------------------

md = scan_health_bridge.markdown(VIN, None)
check("markdown is non-empty", bool(md.strip()))
check("markdown has a Verdict section", "## Verdict" in md)
check("markdown has no 'proven'/'cause' (word-boundary)", not _FORBIDDEN.search(md))


# --- 3. the HTTP surface -----------------------------------------------------

api_resp = client.get(f"/api/scans/{VIN}/latest/health")
check("GET /api/scans/{vin}/latest/health -> 200", api_resp.status_code == 200,
      str(api_resp.status_code))

md_resp = client.get(f"/api/scans/{VIN}/latest/health.md")
check("GET .../health.md -> 200", md_resp.status_code == 200, str(md_resp.status_code))
check(".../health.md body is non-empty", bool(md_resp.text.strip()))

bad_resp = client.get(f"/api/scans/{VIN}/not-a-real-scan/health")
check("GET .../{unknown scan}/health -> 404", bad_resp.status_code == 404,
      str(bad_resp.status_code))

page_resp = client.get(f"/v/{VIN}/health")
check("GET /v/{vin}/health -> 200", page_resp.status_code == 200, str(page_resp.status_code))
check("page shows the verdict label", "Active fault" in page_resp.text or "ACTIVE" in page_resp.text)


# --- 4. no from-car observations at all: page says so, 200, never 500 ------

_empty_fd, _empty_path = tempfile.mkstemp(prefix="cuore-check-scan-health-empty-", suffix=".jsonl")
os.close(_empty_fd)
os.environ["MES_LIVE_OBSERVATIONS"] = _empty_path
try:
    # Same (real, corpus-backed) VIN as every other check here -- a vehicle
    # that exists but has never been scanned from the car, not a vehicle
    # that does not exist at all (that is a 404, a different case, covered
    # above by the unknown-scan-id check).
    empty_resp = client.get(f"/v/{VIN}/health")
    check("no-scan page responds 200, not 500", empty_resp.status_code == 200,
          str(empty_resp.status_code))
    check("no-scan page says so", "no scan on file" in empty_resp.text.lower(),
          empty_resp.text[:2000])
finally:
    os.environ["MES_LIVE_OBSERVATIONS"] = _FIXTURE_PATH


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(f"FAIL: {f}")
if failures:
    sys.exit(1)
