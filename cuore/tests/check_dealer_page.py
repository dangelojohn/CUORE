"""Smoke checks for dealer (wiTECH) results: the JSON route and the page.

Same posture as ``cuore/tests/check_live_vs_log.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported, so nothing here
ever touches the bench's real dealer results store. The MES log corpus is NOT
overridden -- this VIN's real corpus (chronic P0456) is the fixture for the
dossier/tab checks, same posture as ``cuore/tests/check_api.py``.

Run:
    .venv/Scripts/python.exe cuore/tests/check_dealer_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: dealer results go to a throwaway directory, never
# the bench's real evidence store.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-dealer-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import mes_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0456
OTHER_VIN = "1C4RJFAG0JC000001"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())


# --- JSON route: empty, then record, then list ------------------------------

empty = client.get(f"/api/vehicles/{VIN}/dealer-results")
check("empty list responds 200", empty.status_code == 200, str(empty.status_code))
check("empty list has no results", empty.json()["results"] == [], str(empty.json()))

bad = client.post(f"/api/vehicles/{VIN}/dealer-results",
                  json={"kind": "slvt", "data": {"result": "maybe"}})
check("invalid slvt result is rejected", bad.status_code == 400, str(bad.status_code))

bad_kind = client.post(f"/api/vehicles/{VIN}/dealer-results",
                       json={"kind": "not_a_kind", "data": {}})
check("unknown kind is rejected", bad_kind.status_code == 400, str(bad_kind.status_code))

flash = client.post(f"/api/vehicles/{VIN}/dealer-results", json={
    "kind": "flash_check",
    "data": {"module": "ECM", "current_part": "68123456AA",
             "new_part": "68123456AB", "flashed": False},
    "note": "recall visit",
})
check("flash_check recorded", flash.status_code == 200, str(flash.text))
check("flash_check response carries derived current=False",
      flash.json()["data"]["current"] is False, str(flash.json()))

slvt = client.post(f"/api/vehicles/{VIN}/dealer-results", json={
    "kind": "slvt", "data": {"result": "fail", "detail": "measured leak"},
})
check("slvt recorded", slvt.status_code == 200, str(slvt.text))

other = client.post(f"/api/vehicles/{OTHER_VIN}/dealer-results", json={
    "kind": "slvt", "data": {"result": "pass"},
})
check("other VIN's result recorded independently", other.status_code == 200, str(other.text))

listed = client.get(f"/api/vehicles/{VIN}/dealer-results")
check("list responds 200 after recording", listed.status_code == 200)
rows = listed.json()["results"]
check("list has exactly this VIN's two records", len(rows) == 2, str(rows))
check("list excludes the other VIN", all(r["vin"] == VIN for r in rows))
check("each record carries the technician-entered source",
      all(r["source"] == "technician-entered from wiTECH" for r in rows))

listed_other = client.get(f"/api/vehicles/{OTHER_VIN}/dealer-results")
check("other VIN's list is independent", len(listed_other.json()["results"]) == 1)


# --- page: GET then POST ------------------------------------------------------

page = client.get(f"/v/{VIN}/dealer")
check("dealer page responds 200", page.status_code == 200, str(page.status_code))
check("dealer page shows the recorded flash check", "68123456AA" in page.text)
check("dealer page shows the recorded SLVT fail", "fail" in page.text)
check("dealer page links to the gate", f"/v/{VIN}/gate" in page.text)

posted = client.post(f"/v/{VIN}/dealer", data={
    "kind": "recall_status", "campaign": "25V586000", "status": "open",
    "date": "2026-01-01", "note": "checked at counter",
})
check("posting a recall_status form responds 200", posted.status_code == 200,
      str(posted.status_code))
check("posted recall shows up on the rendered page", "25V586000" in posted.text)

bad_form = client.post(f"/v/{VIN}/dealer", data={"kind": "slvt", "result": "maybe"})
check("a bad form submission responds 200 with an error, not a 500",
      bad_form.status_code == 200, str(bad_form.status_code))
check("the page surfaces the validation error", "slvt needs result" in bad_form.text
      or "Not recorded" in bad_form.text, bad_form.text[:2000])

after = mes_bridge.dealer_results(VIN)["results"]
check("service layer sees everything the page recorded", len(after) == 3, str(after))
kinds = sorted(r["kind"] for r in after)
check("recorded kinds are flash_check, recall_status, slvt",
      kinds == ["flash_check", "recall_status", "slvt"], str(kinds))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
