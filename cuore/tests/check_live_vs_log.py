"""Smoke checks for the live-vs-log JSON route and page.

Same posture as ``cuore/tests/check_live.py``: CUORE_STATE_DIR and
MES_LIVE_OBSERVATIONS are pointed at throwaway temp paths BEFORE cuore is
imported, so nothing here ever touches the bench's real observation store.
The log corpus itself is NOT overridden -- the real MES corpus for this VIN
is the fixture, same posture as ``cuore/tests/check_api.py``. The expected
newest_clear and the synthetic live read's timestamp are both derived from
the real corpus at run time (not hardcoded dates), so this keeps passing as
more real logs land for this VIN.

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

# `mes` lives in a hyphenated directory next to `cuore` and is not itself
# importable without this -- same fix cuore.bootstrap applies for the app
# itself, done by hand here so this can inspect the corpus before any cuore
# import.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "mes-log-mcp"))

from datetime import datetime, timedelta  # noqa: E402
from mes.catalog import CATALOG  # noqa: E402
from mes.fes import CLEARING_RE  # noqa: E402


def _real_newest_clear(vin: str) -> str | None:
    """Independently derive the newest clear timestamp from the real corpus.

    Re-implemented here rather than calling ``mes.verdict._last_clear``, so
    this is a structural check (the newest log with the MES clear marker)
    and not a tautology against the function the route relies on. Tracks
    the real corpus as more real logs are added, instead of a pinned date.
    """
    newest = None
    for entry in CATALOG.select(vin=vin):
        if entry.parse_error:
            continue
        try:
            text = Path(entry.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(CLEARING_RE.match(line.strip()) for line in text.splitlines()):
            ts = str(entry.timestamp)
            if newest is None or ts > newest:
                newest = ts
    return newest


def _after_newest_log(vin: str) -> str:
    """An ISO timestamp strictly after every real log for this VIN.

    Keeps the synthetic live read newer than the whole corpus (clears
    included) as more real logs land, so it stays classified as
    live_not_logged instead of drifting into logged_not_live once new logs
    overtake a date picked by hand.
    """
    entries = CATALOG.select(vin=vin)
    newest = entries[0].timestamp if entries else "2026-01-01 00:00:00"
    dt = datetime.strptime(newest, "%Y-%m-%d %H:%M:%S")
    return (dt + timedelta(days=1)).isoformat()


# A fake, real-link-shaped ECM read, timestamped after every real log for
# this VIN (including the newest clear and whatever post-clear re-read
# follows it) -- so it should classify as live_not_logged: active live,
# newer than a log that does not list it.
_live_lines = [
    {"at": _after_newest_log(VIN), "kind": "module_dtcs", "vin": VIN,
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
expected_clear = _real_newest_clear(VIN)
check("newest_clear is the newest clear-marked log in the real corpus",
      bool(expected_clear) and body.get("newest_clear") == expected_clear,
      f"{body.get('newest_clear')} != {expected_clear}")

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
