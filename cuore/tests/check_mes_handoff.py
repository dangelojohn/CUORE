"""Checks for the MES-vs-CUORE capability matrix, the knowledge table it is
generated from, the MES handoff cards (Tests page + job page step 6), and
MES-log import into a "Scans, source MES" entry with a health report.

Same posture as ``cuore/tests/check_marque_port.py``: ``CUORE_STATE_DIR``
and ``MES_LOG_DIR`` are both pointed at throwaway directories BEFORE
``cuore`` (and therefore ``mes``) is imported, and a synthetic
``SCAN_2610080920.txt`` is written into that throwaway MES root -- this
check is fully self-contained and does not touch the real MultiEcuScan
install or the real Stelvio corpus.

Five groups of checks:
  1. The knowledge table (``mes.mes_functions``) has at least 25 functions,
     every one with a non-empty ``source``, and no duplicate ids.
  2. ``cuore.services.mes_handoff_bridge.card``/``find_for_test`` renders a
     handoff card for ``esim_commanded_vent_test`` with its MES menu path
     and at least one prerequisite -- and never claims to write to the car
     (``writes_to_car`` is always ``False``).
  3. ``GET /api/tests/mes-handoff/candidates`` returns >=25 functions;
     ``GET /api/tests/mes-handoff/by-test/esim_commanded_vent_test`` returns
     that same card over HTTP.
  4. Recording a test result still round-trips (regression on the existing
     ``POST /api/tests/{vin}/{test_id}/result`` contract this feature sits
     beside, never replaces).
  5. Importing the synthetic ``SCAN_2610080920.txt`` (via the bridge
     directly, and again via ``POST /api/tests/{vin}/mes-import``) yields a
     "Scans" entry tagged ``source.kind == "MES"`` with a non-empty health
     report line, and ``GET /api/tests/{vin}/mes-scans`` lists it back; the
     Tests page and job page step 6 both render the handoff include marker.

Run:
    .venv/Scripts/python.exe cuore/tests/check_mes_handoff.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- same fixture VIN every other check uses

_STATE_DIR = tempfile.mkdtemp(prefix="cuore-check-mes-handoff-state-")
_MES_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-mes-handoff-logs-"))

os.environ["CUORE_STATE_DIR"] = _STATE_DIR
os.environ["MES_LOG_DIR"] = str(_MES_DIR)
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LOG_DIRS", None)

_SCAN_NAME = "SCAN_2610080920.txt"
(_MES_DIR / _SCAN_NAME).write_text(
    "Engine / ECM (Engine Control Module)\n"
    "Bosch MED17 ECM\n"
    "ISO Code: 01 02 03 04 05\n"
    f"VIN code: {VIN}\n"
    "Hardware number: 1234 - Ver: 01\n"
    "Software number: 5678 - Ver: 01\n"
    "Errors found:\n"
    "P0455-00 - Evaporative Emission System Leak Detected (large leak)\n",
    encoding="utf-8",
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import mes_handoff_bridge  # noqa: E402

from mes import mes_functions  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


# ===========================================================================
# 1. the knowledge table
# ===========================================================================

print("=== mes_functions knowledge table ===")
fns = mes_functions.all_functions()
check("at least 25 MES functions catalogued", len(fns) >= 25, str(len(fns)))
check("no duplicate ids", len({f["id"] for f in fns}) == len(fns))
no_source = [f["id"] for f in fns if not (f.get("source") or "").strip()]
check("every function has a non-empty source", not no_source, str(no_source))
bad_kind = [f["id"] for f in fns if f["kind"] not in mes_functions.KINDS]
check("every function's kind is one of KINDS", not bad_kind, str(bad_kind))
check("function() returns None for an unknown id",
     mes_functions.function("not-a-real-id") is None)
check("esim_commanded_vent_test is in the catalogue (cross-ref to "
     "mechanic_tests.py)", mes_functions.function("esim_commanded_vent_test")
     is not None)

# ===========================================================================
# 2. handoff card rendering
# ===========================================================================

print("=== handoff card: esim_commanded_vent_test ===")
card = mes_handoff_bridge.find_for_test("esim_commanded_vent_test")
check("a handoff card was found for esim_commanded_vent_test", card is not None)
if card is not None:
    check("the card names the MES menu path", "Actuators" in card["menu_path"],
         card["menu_path"])
    check("the card carries at least one prerequisite",
         len(card["prerequisites"]) >= 1, str(card["prerequisites"]))
    check("the card never claims to write to the car",
         card["writes_to_car"] is False)
    check("the card names a source", bool((card.get("source") or "").strip()))

check("find_for_test returns None for a test with no MES-only counterpart",
     mes_handoff_bridge.find_for_test("not-a-real-test-id") is None)
check("find_for_text matches a function by free-text name",
     mes_handoff_bridge.find_for_text("Service interval reset") is not None)

# ===========================================================================
# 3. HTTP surface
# ===========================================================================

print("=== HTTP: /api/tests/mes-handoff/* ===")
client = TestClient(create_app())

cands = client.get("/api/tests/mes-handoff/candidates")
check("candidates responds 200", cands.status_code == 200, str(cands.status_code))
cand_fns = cands.json().get("functions", [])
check("candidates returns >=25 functions", len(cand_fns) >= 25, str(len(cand_fns)))

by_test = client.get("/api/tests/mes-handoff/by-test/esim_commanded_vent_test")
check("by-test responds 200", by_test.status_code == 200, str(by_test.status_code))
by_test_handoff = by_test.json().get("handoff")
check("by-test returns a non-null handoff card", by_test_handoff is not None)
if by_test_handoff is not None:
    check("by-test's card matches the bridge's own card id",
         by_test_handoff["id"] == "esim_commanded_vent_test", str(by_test_handoff))

by_text = client.get("/api/tests/mes-handoff/by-text", params={"text": "service interval reset"})
check("by-text responds 200", by_text.status_code == 200, str(by_text.status_code))
check("by-text returns a non-null handoff card", by_text.json().get("handoff") is not None)

# ===========================================================================
# 4. regression: recording a test result still works
# ===========================================================================

print("=== regression: POST /api/tests/{vin}/{test_id}/result ===")
result_resp = client.post(
    f"/api/tests/{VIN}/esim_commanded_vent_test/result",
    json={"result": "inconclusive", "reason": "no wiTECH on hand this visit"},
)
check("recording a result still responds 200", result_resp.status_code == 200,
     str(result_resp.status_code))
check("the recorded result round-trips",
     result_resp.json().get("result") == "inconclusive", str(result_resp.json()))

tests_page = client.get(f"/v/{VIN}/tests")
check("the Tests page still responds 200", tests_page.status_code == 200,
     str(tests_page.status_code))
check("the Tests page wires in the MES handoff include",
     'id="mes-handoff-root"' in tests_page.text)

# ===========================================================================
# 5. MES log import -> a Scans entry, source MES, with a health report
# ===========================================================================

print("=== MES log import ===")
scan = mes_handoff_bridge.import_mes_log(VIN, _SCAN_NAME)
check("the imported scan is tagged source.kind == MES",
     scan.get("source", {}).get("kind") == "MES", str(scan.get("source")))
check("the imported scan carries the DTC the fixture log has",
     "P0455-00" in scan["dtcs"]["stored"], str(scan["dtcs"]))
line = mes_handoff_bridge.health_line(scan)
check("a non-empty health report line was produced", bool(line.strip()), repr(line))

listed = mes_handoff_bridge.list_mes_scans(VIN)
check("list_mes_scans shows the imported scan",
     any(s["id"] == scan["id"] for s in listed), str(listed))

import_resp = client.post(f"/api/tests/{VIN}/mes-import", json={"name": _SCAN_NAME})
check("POST mes-import responds 200", import_resp.status_code == 200,
     str(import_resp.status_code))
import_body = import_resp.json()
check("the HTTP import also tags source.kind == MES",
     import_body.get("scan", {}).get("source", {}).get("kind") == "MES",
     str(import_body))
check("the HTTP import returns a non-empty health_line",
     bool((import_body.get("health_line") or "").strip()), str(import_body))

scans_resp = client.get(f"/api/tests/{VIN}/mes-scans")
check("GET mes-scans responds 200", scans_resp.status_code == 200,
     str(scans_resp.status_code))
scans_body = scans_resp.json()
check("mes-scans lists at least one scan with source MES",
     any(s.get("source", {}).get("kind") == "MES" for s in scans_body.get("scans", [])),
     str(scans_body))
check("mes-scans returns a parallel non-empty health line per scan",
     len(scans_body.get("lines", [])) == len(scans_body.get("scans", []))
     and all((l or "").strip() for l in scans_body.get("lines", [])),
     str(scans_body))

# a VIN mismatch is rejected, not silently filed under the wrong car
try:
    mes_handoff_bridge.import_mes_log("ZN661XUA9JX000001", _SCAN_NAME)
    check("importing a log for the wrong VIN raises", False)
except Exception as exc:  # noqa: BLE001
    check("importing a log for the wrong VIN raises BadRequest",
         "VIN" in str(exc), str(exc))

print("=== job page step 6 wires in the MES handoff include ===")
open_resp = client.post(f"/v/{VIN}/job/open",
                        data={"technician": "tester", "complaint": "CEL"},
                        follow_redirects=True)
check("opening a case responds 200", open_resp.status_code == 200,
     str(open_resp.status_code))
job_step6 = client.get(f"/v/{VIN}/job", params={"step": "6"})
check("job page step 6 responds 200", job_step6.status_code == 200,
     str(job_step6.status_code))
check("job page step 6 wires in the MES handoff include",
     'id="mes-handoff-root"' in job_step6.text)

# ===========================================================================
print(f"\n{checks} checks, {len(failures)} failures")
if failures:
    for f in failures:
        print(f"FAILED: {f}")
    sys.exit(1)
print("All checks passed.")
