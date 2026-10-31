"""Checks for the CUORE vs MES stored-code comparison (``cuore/services/code_compare.py``, parity page).

Fixtures are RECORDED data from the Stelvio, 2026-10-31: the ECM 19 02 FF record bytes from the
00:36:41 read (P0456-00 status 0x4D, P0458-00 status 0x40 "not tested") and the ECM block of MES's
SCAN_2610310042 (P0456-00). Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_code_compare.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-compare-")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live.obd import decode_uds_dtc_block  # noqa: E402
from cuore.services import code_compare as cc, modules_bridge  # noqa: E402
from mes import scan  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


# 1. the recorded bytes: P0456 is parsed and is "stored"; the tracked-only code is not.
recs = decode_uds_dtc_block("59 02 CF 04 56 00 4D 04 58 00 40".split())
stored = {r["code"] for r in recs if r["status"] & cc.STORED_MASK}
check(stored == {"P0456-00"}, f"recorded ECM bytes -> stored {stored}")
check(recs[0]["status"] == 0x4D and recs[0]["flags"]["pendingDTC"] and recs[0]["flags"]["confirmedDTC"],
      "0x4D is pending + confirmed + testFailed")

# 2. the recorded MES scan block parses to the same code
TEXT = ("Scan vehicle for available modules and check each module for errors...\n\nEngine / ECM\n"
        "Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)\nISO Code: 00 01 50 40 18\n"
        "VIN code: ZASFAKPN5J7B88115\nHardware number: MM10JAHW232 - Ver: 00\n"
        "Software number: P235QB39 - Ver: 0000\nErrors found:\nP0456-00 - Evaporation system leak\n")
mes_codes = {d.full for d in scan.parse_scan_text(TEXT, name="SCAN_2610310042.txt").modules[0].dtcs}
check(mes_codes == {"P0456-00"}, f"recorded MES block -> {mes_codes}")

# 3. the rule
T0 = datetime(2026, 10, 31, 0, 36, 41)


def c(at=T0, codes=("P0456-00",), mod="ECM"):
    return {"module": mod, "at": at, "codes": set(codes), "tracked": 120}


def m(start, codes=("P0456-00",), end=None, cleared=False, mod="ECM"):
    return {"module": mod, "start": start, "end": end or start, "codes": set(codes),
            "source": "SCAN_x.txt", "cleared": cleared}


def one(cu, me):
    return cc.compare_reads(cu, me)["modules"][0]


r = one([c()], [m(T0 + timedelta(seconds=120))])
check(r["status"] == "MATCHED" and r["both"] == ["P0456-00"], "2 min apart, same codes -> MATCHED")
r = one([c()], [m(T0 + timedelta(seconds=301))])
check(r["status"] == "NOT COMPARED" and r["both"] == ["P0456-00"] and "not a match" in r["why"],
      "301 s apart -> NOT COMPARED, lists shown but not a match")
r = one([c()], [m(T0 + timedelta(seconds=300))])
check(r["status"] == "MATCHED", "exactly 5 min is still inside the window")
r = one([c()], [m(T0 + timedelta(seconds=60), codes=("P0456-00", "P0440-00"))])
check(r["status"] == "DIFFERENT" and r["mes_only"] == ["P0440-00"] and r["cuore_only"] == [], "MES-only code -> DIFFERENT")
r = one([c(codes=("P0456-00", "P0455-00"))], [m(T0)])
check(r["status"] == "DIFFERENT" and r["cuore_only"] == ["P0455-00"], "CUORE-only code -> DIFFERENT")
r = one([c()], [m(T0 - timedelta(seconds=100), end=T0 + timedelta(seconds=900))])
check(r["status"] == "MATCHED" and r["gap_s"] == 0, "CUORE read inside the MES session window -> gap 0")
r = one([c()], [m(T0 - timedelta(seconds=100), cleared=True)])
check(r["status"] == "NOT COMPARED" and "erased" in r["why"], "MES cleared after opening: later CUORE read cannot match")
r = one([c(at=T0 - timedelta(seconds=200))], [m(T0 - timedelta(seconds=100), cleared=True)])
check(r["status"] == "MATCHED", "CUORE read before the MES clear still compares")
r = one([], [m(T0)])
check(r["status"] == "NOT COMPARED" and "no answered" in r["why"], "no CUORE read -> NOT COMPARED")
r = one([c()], [])
check(r["status"] == "NOT COMPARED" and "no MES log" in r["why"], "no MES log -> NOT COMPARED")
res = cc.compare_reads([c(), c(mod="BCM", codes=())], [m(T0), m(T0 + timedelta(hours=1), mod="BCM", codes=())])
check(res["counts"] == {"MATCHED": 1, "DIFFERENT": 0, "NOT COMPARED": 1}, f"counts {res['counts']}")
# the nearest pair wins when a module has several reads
r = one([c(at=T0 - timedelta(days=5)), c()], [m(T0 + timedelta(seconds=30))])
check(r["status"] == "MATCHED" and r["cuore_at"] == "2026-10-31 00:36:41", "nearest pair chosen")

# 4. an old failed attempt says its date and that it is not today's state
now = datetime(2026, 10, 31, 12, 0, 0)
note = modules_bridge._age_note("2026-09-25T20:07:24", now)
check("2026-09-25" in note and "35 days ago" in note and "not the state today" in note, f"old note: {note}")
check(modules_bridge._age_note("2026-10-31T08:00:00", now) == "", "a same-day failure gets no 'old' note")
check(modules_bridge._age_note("garbage", now) == "", "unparseable time -> no note")

# 5. the page renders the section (real files on disk, read-only)
try:
    from fastapi.testclient import TestClient
    from cuore.app import create_app
    VIN = "ZASFAKPN5J7B88115"
    page = TestClient(create_app(), follow_redirects=False).get(f"/v/{VIN}/parity")
    check(page.status_code == 200 and 'id="code-compare"' in page.text and "NOT COMPARED" in page.text,
          "parity page carries the comparison section")
except Exception as exc:  # noqa: BLE001
    failures.append(f"page: {exc!r}")

if failures:
    print("FAIL:", *failures, sep="\n  ")
    sys.exit(1)
print(f"all {passed} checks passed")
