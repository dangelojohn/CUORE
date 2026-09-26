"""Smoke checks for the live-vs-log JSON route and page.

Same posture as ``cuore/tests/check_live.py``: CUORE_STATE_DIR and
MES_LIVE_OBSERVATIONS are pointed at throwaway temp paths BEFORE cuore is
imported, so nothing here ever touches the bench's real observation store.
The log corpus itself is NOT overridden -- the real MES corpus for this VIN
is the fixture, same posture as ``cuore/tests/check_api.py``.

Run:
    .venv/Scripts/python.exe cuore/tests/check_live_vs_log.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: observations and address store go to a throwaway
# directory, never the bench's real evidence.
_state_dir = tempfile.mkdtemp(prefix="cuore-check-livevslog-state-")
_live_obs = Path(tempfile.mkdtemp(prefix="cuore-check-livevslog-obs-")) / "observations.jsonl"
os.environ["CUORE_STATE_DIR"] = _state_dir
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ["MES_LIVE_OBSERVATIONS"] = str(_live_obs)

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, real EVAP codes

# A fake, real-link-shaped ECM read, timestamped after every real log for
# this VIN (including the 2026-09-25 20:27 clear and the 20:28 post-clear
# re-read) -- so it should classify as live_not_logged: active live, newer
# than a log that does not list it.
_live_lines = [
    {"at": "2026-09-26T00:00:00", "kind": "module_dtcs", "vin": VIN,
     "stream": "serial COM3@115200",
     "data": {"ecu": "ECM", "codes": ["P0455-00"],
              "dtcs": [{"code": "P0455-00", "status": 13}]}},
]
_live_obs.parent.mkdir(parents=True, exist_ok=True)
with _live_obs.open("w", encoding="utf-8") as f:
    for obj in _live_lines:
        f.write(json.dumps(obj) + "\n")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())


# --- JSON route --------------------------------------------------------------

resp = client.get(f"/api/vehicles/{VIN}/live-vs-log")
check("json route responds 200", resp.status_code == 200, str(resp.status_code))
body = resp.json()
check("vin echoed", body.get("vin") == VIN, str(body.get("vin")))
check("newest_clear is the real 2026-09-25 20:27 scan clear",
      body.get("newest_clear") == "2026-09-25 20:27:00", str(body.get("newest_clear")))

ecm = next((m for m in body.get("modules", []) if m["module"] == "ECM"), None)
check("ECM module present in the report", ecm is not None)
if ecm:
    row = next((r for r in ecm["rows"] if r["code"] == "P0455-00"), None)
    check("fake live ECM P0455 row present", row is not None, str(ecm["rows"]))
    if row:
        check("fake live ECM P0455 classifies as live_not_logged",
              row["class"] == "live_not_logged", str(row))
        check("reading mentions the MES scan",
              "MES scan" in row["reading"], row["reading"])

resp_filtered = client.get(f"/api/vehicles/{VIN}/live-vs-log", params={"module": "ECM"})
check("json route with module filter responds 200",
      resp_filtered.status_code == 200, str(resp_filtered.status_code))
filtered_body = resp_filtered.json()
check("module filter narrows the JSON route to ECM only",
      [m["module"] for m in filtered_body.get("modules", [])] == ["ECM"],
      str(filtered_body.get("modules")))

resp_bad = client.get("/api/vehicles//live-vs-log")
check("empty vin does not 500", resp_bad.status_code in (400, 404, 422),
      str(resp_bad.status_code))


# --- HTML page ----------------------------------------------------------------

page = client.get(f"/v/{VIN}/live-vs-log")
check("page responds 200", page.status_code == 200, str(page.status_code))
check("page shows the VIN", VIN in page.text)
check("page shows the fake ECM code", "P0455-00" in page.text)
check("page renders the live_not_logged class",
      "live not logged" in page.text, page.text.count("live not logged"))

page_filtered = client.get(f"/v/{VIN}/live-vs-log", params={"module": "ECM"})
check("filtered page responds 200",
      page_filtered.status_code == 200, str(page_filtered.status_code))
check("filtered page still shows the fake ECM code", "P0455-00" in page_filtered.text)

print(f"{checks} checks, {len(failures)} failures")
if failures:
    for f in failures:
        print(f"  FAIL: {f}")
    sys.exit(1)
print("all checks passed")
