"""Smoke checks for mes.compare.live_vs_log.

Phase 1 builds a small synthetic log corpus (via MES_LOG_DIR) plus a
hand-written live-observations JSONL (via MES_LIVE_OBSERVATIONS) and exercises
every one of the six classes against it, including a "scripted" stream entry
that must be ignored.

Phase 2 points MES_LOG_DIR back at the real corpus (no override) and re-runs
live_vs_log against the SAME temp live observations, checking that the real
ECM EVAP codes (P0455/P0456/P0440) come back with a determinate class given
the fake live read: that read (2026-01-01, long before the real 2026-09-25
clear) predates the newest real clear, while the real corpus's newest ECM
read (the 20:28 post-clear FES session) is clean and postdates it -- so the
live evidence is stale and the log is believed: "logged_not_live".
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VIN = "ZASFAKPN5J7B88115"
failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def row_for(result, module, code):
    for m in result["modules"]:
        if m["module"] == module:
            for r in m["rows"]:
                if r["code"] == code:
                    return r
    return None


# --- build the synthetic log corpus -----------------------------------------
tmp_logs = tempfile.mkdtemp(prefix="mes_compare_logs_")

SCAN_A = f"""Dashboard / IPC (Instrument Panel Cluster)
Instrument Panel Test
ISO Code: 00 03 50 8B 14
VIN code: {VIN}
Hardware number: HW2 - Ver: 01
Software number: SW2 - Ver: 01
Errors found:
P0400-00 - Test IPC fault
"""

SCAN_B = f"""Engine / ECM
Some ECU
ISO Code: 00 01 50 40 18
VIN code: {VIN}
Hardware number: HW1 - Ver: 01
Software number: SW1 - Ver: 01

CLEARING STORED FAULT CODES...
"""

SCAN_C = f"""Engine / ECM
Magneti Marelli Test ECU
ISO Code: 00 01 50 40 18
VIN code: {VIN}
Hardware number: HW1 - Ver: 01
Software number: SW1 - Ver: 01
Errors found:
P0455-00 - Evaporation system leak
P0456-00 - Evaporation system leak
P0440-00 - Evaporation control valve

Gearbox / TCM (Automatic Transmission)
ZF Test Gearbox
ISO Code: 00 0B 50 AA 14
VIN code: {VIN}
Hardware number: HW3 - Ver: 01
Software number: SW3 - Ver: 01
Errors found:
P0200-00 - Test TCM fault

Body / BCM (Body Computer Module)
Body Computer Test
ISO Code: 00 00 70 7C 15
VIN code: {VIN}
Hardware number: HW4 - Ver: 01
Software number: SW4 - Ver: 01

Body / RFHUB (Radio Frequency Hub Module)
RFHUB Test
ISO Code: 00 41 50 89 15
VIN code: {VIN}
Hardware number: HW5 - Ver: 01
Software number: SW5 - Ver: 01
Errors found:
P0500-00 - Test RFHUB fault
"""

(Path(tmp_logs) / "SCAN_2601010000.txt").write_text(SCAN_A, encoding="utf-8")
(Path(tmp_logs) / "SCAN_2601010003.txt").write_text(SCAN_B, encoding="utf-8")
(Path(tmp_logs) / "SCAN_2601010010.txt").write_text(SCAN_C, encoding="utf-8")

# newest_clear (from SCAN_2601010003.txt) = 2026-01-01 00:03:00
#   IPC   log @ 00:00 (stale) / live @ 00:02 (stale)      -> stale_both
#   ECM   log @ 00:10 (fresh, P0455/P0456/P0440) / live @ 00:15 (fresh, active)
#                                                          -> live_and_logged
#   TCM   log @ 00:10 (P0200) / live @ 00:16 (clean, newer)-> logged_not_live
#   BCM   log @ 00:10 (clean) / live @ 00:17 (P0300 active, newer) -> live_not_logged
#   RFHUB log @ 00:10 (P0500) / no live read               -> no_live_read
#   DASM  no log / live @ 00:18 (P0600 active)             -> no_log

live_lines = [
    {"at": "2026-01-01T00:02:00", "kind": "module_dtcs", "vin": VIN,
     "stream": "serial COM3@115200",
     "data": {"ecu": "IPC", "codes": ["P0400-00"],
              "dtcs": [{"code": "P0400-00", "status": 13}]}},
    {"at": "2026-01-01T00:16:00", "kind": "module_dtcs", "vin": VIN,
     "stream": "serial COM3@115200",
     "data": {"ecu": "TCM", "codes": [], "dtcs": []}},
    {"at": "2026-01-01T00:17:00", "kind": "module_dtcs", "vin": VIN,
     "stream": "serial COM3@115200",
     "data": {"ecu": "BCM", "codes": ["P0300-00"],
              "dtcs": [{"code": "P0300-00", "status": 13}]}},
    {"at": "2026-01-01T00:18:00", "kind": "module_dtcs", "vin": VIN,
     "stream": "serial COM3@115200",
     "data": {"ecu": "DASM", "codes": ["P0600-00"],
              "dtcs": [{"code": "P0600-00", "status": 13}]}},
    {"at": "2026-01-01T00:15:00", "kind": "module_dtcs", "vin": VIN,
     "stream": "serial COM3@115200",
     "data": {"ecu": "ECM", "codes": ["P0455-00", "P0456-00", "P0440-00"],
              "dtcs": [{"code": "P0455-00", "status": 13},
                       {"code": "P0456-00", "status": 13},
                       {"code": "P0440-00", "status": 13}]}},
    # scripted -- must be ignored even though it is last in the file (and
    # would otherwise look like the newest ECM read, claiming it clean).
    {"at": "2026-01-01T00:20:00", "kind": "module_dtcs", "vin": VIN,
     "stream": "scripted",
     "data": {"ecu": "ECM", "codes": [], "dtcs": []}},
]

tmp_live = tempfile.NamedTemporaryFile(
    prefix="mes_compare_live_", suffix=".jsonl", delete=False, mode="w",
    encoding="utf-8")
for obj in live_lines:
    tmp_live.write(json.dumps(obj) + "\n")
tmp_live.close()

_orig_log_dir = os.environ.get("MES_LOG_DIR")
_orig_log_dirs = os.environ.get("MES_LOG_DIRS")
_orig_live = os.environ.get("MES_LIVE_OBSERVATIONS")

os.environ.pop("MES_LOG_DIRS", None)
os.environ["MES_LOG_DIR"] = tmp_logs
os.environ["MES_LIVE_OBSERVATIONS"] = tmp_live.name

from mes import compare  # noqa: E402  (import after env vars are set)

print("=== synthetic corpus: every class ===")
result = compare.live_vs_log(VIN)
check("newest_clear picked up from SCAN_2601010003.txt",
      result["newest_clear"] == "2026-01-01 00:03:00", result["newest_clear"])

r = row_for(result, "IPC", "P0400-00")
check("IPC P0400 -> stale_both", r and r["class"] == "stale_both", r)

for code in ("P0455-00", "P0456-00", "P0440-00"):
    r = row_for(result, "ECM", code)
    check(f"ECM {code} -> live_and_logged (scripted entry ignored)",
          r and r["class"] == "live_and_logged", r)

r = row_for(result, "TCM", "P0200-00")
check("TCM P0200 -> logged_not_live", r and r["class"] == "logged_not_live", r)

r = row_for(result, "BCM", "P0300-00")
check("BCM P0300 -> live_not_logged", r and r["class"] == "live_not_logged", r)

r = row_for(result, "RFHUB", "P0500-00")
check("RFHUB P0500 -> no_live_read", r and r["class"] == "no_live_read", r)

r = row_for(result, "DASM", "P0600-00")
check("DASM P0600 -> no_log", r and r["class"] == "no_log", r)

check("summary counts every class once",
      result["summary"] == {"stale_both": 1, "live_and_logged": 3,
                            "logged_not_live": 1, "live_not_logged": 1,
                            "no_live_read": 1, "no_log": 1},
      result["summary"])

print("\n=== module filter ===")
only_ecm = compare.live_vs_log(VIN, module="ECM")
check("module filter narrows to one module",
      [m["module"] for m in only_ecm["modules"]] == ["ECM"],
      only_ecm["modules"])

# --- phase 2: real corpus, same fake live observations ----------------------
os.environ.pop("MES_LOG_DIR", None)
os.environ.pop("MES_LOG_DIRS", None)

print("\n=== real corpus + fake live observations ===")
real = compare.live_vs_log(VIN)
check("real newest_clear is the 2026-09-25 20:27 scan clear",
      real["newest_clear"] == "2026-09-25 20:27:00", real["newest_clear"])

for code in ("P0455-00", "P0456-00", "P0440-00"):
    r = row_for(real, "ECM", code)
    check(f"real corpus ECM {code} -> logged_not_live "
          f"(fake live predates the real clear; the real post-clear FES read "
          f"is clean)",
          r and r["class"] == "logged_not_live", r)
    reading = (r or {}).get("reading", "").lower()
    check(f"real corpus ECM {code}: a re-read after a clear is never called a pass",
          "passed" not in reading.replace("absent is not passed", "")
          and "not that the fault is fixed" in reading, reading)

# --- restore environment -----------------------------------------------------
if _orig_log_dir is None:
    os.environ.pop("MES_LOG_DIR", None)
else:
    os.environ["MES_LOG_DIR"] = _orig_log_dir
if _orig_log_dirs is None:
    os.environ.pop("MES_LOG_DIRS", None)
else:
    os.environ["MES_LOG_DIRS"] = _orig_log_dirs
if _orig_live is None:
    os.environ.pop("MES_LIVE_OBSERVATIONS", None)
else:
    os.environ["MES_LIVE_OBSERVATIONS"] = _orig_live

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("all checks passed")
