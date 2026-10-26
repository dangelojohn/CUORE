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
    # module_dtcs / scan_coverage / mode09 -- same shape as this VIN's own
    # real 2026-10-13T20:24:25 (module_dtcs) / 20:59:23 (scan_coverage,
    # mode09) observations, trimmed to the records the checks below
    # actually exercise. Flags only (status int omitted, same as real
    # module_dtcs reads) -- testFailed true is ACTIVE, confirmedDTC/
    # pendingDTC true with testFailed false is history, neither is the
    # status-64-only placeholder that must never be listed.
    {"at": "2026-10-13T20:24:25", "kind": "module_dtcs", "vin": VIN, "bus": "can_c",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"ecu": "BCM", "bus": "can_c", "mask": "FF", "error": None, "nrc": None,
              "dtcs": [
                  {"code": "U1713-2F", "raw": "19022F", "flags": {
                      "testFailed": True, "testFailedThisOperationCycle": True,
                      "pendingDTC": True, "confirmedDTC": True,
                      "testNotCompletedSinceLastClear": False,
                      "testFailedSinceLastClear": False,
                      "testNotCompletedThisOperationCycle": False,
                      "warningIndicatorRequested": False}},
                  {"code": "U1765-86", "raw": "190286", "flags": {
                      "testFailed": False, "testFailedThisOperationCycle": False,
                      "pendingDTC": False, "confirmedDTC": True,
                      "testNotCompletedSinceLastClear": False,
                      "testFailedSinceLastClear": False,
                      "testNotCompletedThisOperationCycle": False,
                      "warningIndicatorRequested": False}},
                  {"code": "B1176-97", "raw": "110297", "flags": {
                      "testFailed": False, "testFailedThisOperationCycle": False,
                      "pendingDTC": False, "confirmedDTC": True,
                      "testNotCompletedSinceLastClear": False,
                      "testFailedSinceLastClear": False,
                      "testNotCompletedThisOperationCycle": False,
                      "warningIndicatorRequested": False}},
                  {"code": "B10AA-4A", "raw": "10024A", "flags": {
                      "testFailed": False, "testFailedThisOperationCycle": False,
                      "pendingDTC": False, "confirmedDTC": True,
                      "testNotCompletedSinceLastClear": False,
                      "testFailedSinceLastClear": False,
                      "testNotCompletedThisOperationCycle": False,
                      "warningIndicatorRequested": False}},
                  {"code": "U1772-87", "raw": "190287", "flags": {
                      "testFailed": False, "testFailedThisOperationCycle": False,
                      "pendingDTC": False, "confirmedDTC": False,
                      "testNotCompletedSinceLastClear": False,
                      "testFailedSinceLastClear": False,
                      "testNotCompletedThisOperationCycle": True,
                      "warningIndicatorRequested": False}},
              ]}},
    {"at": "2026-10-13T20:24:25", "kind": "module_dtcs", "vin": VIN, "bus": "can_c",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"ecu": "RFHUB", "bus": "can_c", "mask": "FF", "error": None, "nrc": None,
              "dtcs": [
                  {"code": "B1040-64", "raw": "904064", "flags": {
                      "testFailed": False, "testFailedThisOperationCycle": False,
                      "pendingDTC": False, "confirmedDTC": True,
                      "testNotCompletedSinceLastClear": False,
                      "testFailedSinceLastClear": False,
                      "testNotCompletedThisOperationCycle": False,
                      "warningIndicatorRequested": False}},
              ]}},
    {"at": "2026-10-13T20:59:23", "kind": "scan_coverage", "vin": VIN, "bus": "",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"scan_id": "SCAN_2610132059", "vin": VIN, "cable": "none",
              "buses_attempted": ["can_c", "can_ihs"], "coverage": [
                  {"bus": "can_ch", "module": "EPS", "category": "not_reachable",
                   "why": "needs grey A6 cable", "active": 0, "history": 0, "not_run": 0},
                  {"bus": "can_ch", "module": "ABS", "category": "not_reachable",
                   "why": "needs grey A6 cable", "active": 0, "history": 0, "not_run": 0},
              ], "counts": {"active": 0, "history": 0, "not_run": 0}}},
    {"at": "2026-10-13T20:59:23", "kind": "mode09", "vin": VIN, "bus": "can_c",
     "cable": "none", "stream": "serial COM3@115200",
     "data": {"mode09": {}, "gaps": [
         "calibration IDs (PID 04)", "CVNs (PID 06)", "ECU names (PID 0A)",
         "in-use performance tracking / IUPR (PID 08)"],
         "gap_reason": "PID not answered by the ECM"}},
]

#: Speculative kinds this install's live link has never actually logged
#: yet (``mes.scan_health``'s own module docstring already says so --
#: "pid"/"freeze_frame"/"pids_snapshot" are anticipated shapes, not
#: produced by today's link) -- so there is no real line to copy for the
#: fuel-trim/charging-voltage checks below. Added unconditionally (real
#: file present or not), clearly marked as fabricated via its own
#: ``stream`` text rather than pretending to be a copied line.
_SYNTHETIC_PID_LINES = [
    {"at": "2026-10-13T20:03:55", "kind": "pids_snapshot", "vin": VIN, "bus": "can_c",
     "cable": "none",
     "stream": "serial COM3@115200 (synthetic fixture line -- no real "
              "pids_snapshot/pid observation exists for this VIN yet; see "
              "mes.scan_health's own module docstring)",
     "data": {"readings": {
         "short_fuel_trim_b1": {"value": 3.1, "unit": "%"},
         "battery_voltage": {"value": 14.0, "unit": "V"},
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
                    kind = obj.get("kind")
                    if not at.startswith("2026-10-13"):
                        continue
                    if (kind in ("obd_dtcs", "readiness", "mode06")
                            and at <= "2026-10-13T20:04:00"):
                        lines.append(line)
                    elif kind in ("module_dtcs", "scan_coverage", "mode09"):
                        lines.append(line)
        except OSError:
            lines = []
    if not lines:
        lines = [json.dumps(o) for o in _FALLBACK_LINES]
    lines.extend(json.dumps(o) for o in _SYNTHETIC_PID_LINES)
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
    # Module codes (U1713-2F ACTIVE on BCM; U1765-86/B1176-97/B10AA-4A
    # history-only) now fill these rows instead of leaving them GAP.
    check("network row is FAULT", network_row["health"] == "FAULT", network_row["health"])
    net_reading = network_row.get("reading") or ""
    check("network row cites U1713-2F", "U1713-2F" in net_reading, net_reading)
    check("network row cites the FTB 2F meaning (signal erratic)",
          "signal erratic" in net_reading, net_reading)

    check("body row is OK (history only, nothing active)",
          body_row["health"] == "OK", body_row["health"])
    body_reading = body_row.get("reading") or ""
    check("body row lists B1176-97 as history", "B1176-97" in body_reading, body_reading)
    check("body row says 'history'", "history" in body_reading, body_reading)

fuel_row = by_label.get("Fuel")
check("Fuel row exists", fuel_row is not None)
if fuel_row:
    check("fuel row is OK (3.1% is inside the +/-10% trim band)",
          fuel_row["health"] == "OK", fuel_row["health"])
    check("fuel row shows the trim margin text", fuel_row.get("margin") == "+3.1% of ±10%",
          str(fuel_row.get("margin")))

charging_row = by_label.get("Electrical supply")
check("Electrical supply row exists", charging_row is not None)
if charging_row:
    check("charging row is OK (14.0 V is inside the 13.5-14.7 V band)",
          charging_row["health"] == "OK", charging_row["health"])
    check("charging row shows 14.0 V", "14.0" in (charging_row.get("reading") or ""),
          str(charging_row.get("reading")))

steering_row = by_label.get("Steering")
check("Steering row exists", steering_row is not None)
if steering_row:
    check("steering row is GAP (EPS needs the grey A6 cable)",
          steering_row["health"] == "GAP", steering_row["health"])
    steering_reading = steering_row.get("reading") or ""
    check("steering row carries the scan_coverage wording verbatim",
          "needs grey A6 cable" in steering_reading and "not reachable" in steering_reading,
          steering_reading)

check("issues list has at least 2 entries", len(report["issues"]) >= 2, str(report["issues"]))
if len(report["issues"]) >= 2:
    check("issues[1] names U1713 (network, after the EVAP active fault)",
          "U1713" in report["issues"][1], report["issues"][1])

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


# --- 5. transmission row reads a MES recording's ATF temperature ----------

_CSV_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-scan-health-csv-"))
_csv_content = ('"Time"\t"Gearbox oil temperature"\t"TAG"\n'
               '"sec"\t"C"\t" "\n'
               '0.00\t35.0000\t""\n'
               '1.00\t38.0000\t""\n')
(_CSV_DIR / "rec.csv").write_bytes(b"\xff\xfe" + _csv_content.encode("utf-16-le"))
os.environ["MES_CSV_DIR"] = str(_CSV_DIR)

report_tx = scan_health_bridge.build(VIN, None)
tx_row = {row["label"]: row for row in report_tx["systems"]}.get("Transmission / driveline")
check("Transmission / driveline row exists", tx_row is not None)
if tx_row:
    tx_reading = tx_row.get("reading") or ""
    check("transmission row cites the MES-recorded ATF temperature",
         "38" in tx_reading and "MES recording" in tx_reading, tx_reading)

from cuore.services import liveboard_bridge  # noqa: E402

board = liveboard_bridge.board(VIN)
rec_by_id = {c["id"]: c for c in board.get("recording_channels", [])}
check("liveboard recording_channels has the ATF recording channel",
     "rec_atf_temp" in rec_by_id, list(rec_by_id))
if "rec_atf_temp" in rec_by_id:
    atf_ch = rec_by_id["rec_atf_temp"]
    check("ATF recording channel is kind 'recording' from source 'MES'",
         atf_ch.get("kind") == "recording" and atf_ch.get("source") == "MES", atf_ch)
    check("ATF recording channel value is the last sample (38.0)",
         atf_ch.get("value") == 38.0, str(atf_ch.get("value")))
    check("ATF recording channel is never in the polled channel list",
         "rec_atf_temp" not in board.get("all_channel_ids", []))


# A Mode 09 read where no PID answered is stored as {"04": {"warning":
# "NO DATA"}, ...} on this car -- a string where an ECU entry would be.
# That shape made /health a 500 (2026-10-26).
from mes import scan_health as _sh  # noqa: E402
_nodata = {"mode09": {"results": {p: {"warning": "NO DATA"} for p in ("04", "06", "08", "0A")}}}
check("a Mode 09 read with every PID 'NO DATA' gives no header extras and no IUPR, not a crash",
      _sh.mode09_header_extras(_nodata) == {} and _sh.evap_iupr(_nodata) is None)


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(f"FAIL: {f}")
if failures:
    sys.exit(1)
