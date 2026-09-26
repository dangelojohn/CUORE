"""Smoke checks for the per-vehicle dashboard: the page and its JSON route.

Same posture as ``cuore/tests/check_api.py``: ``CUORE_STATE_DIR`` is pointed
at a throwaway directory BEFORE cuore is imported (so no real dealer/live
state is touched -- and, incidentally, so the live-status section renders its
honest "nothing recorded yet" empty state). The MES log corpus is NOT
overridden -- this VIN's real corpus (chronic P0456) is the fixture.

Run:
    .venv/Scripts/python.exe cuore/tests/check_dashboard_page.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-dashboard-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

VIN = "ZASFAKPN5J7B88115"           # the Stelvio -- real corpus, chronic P0456
NO_SUCH_VIN = "1C4RJFAG0JC000001"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


client = TestClient(create_app())

print("=== page ===")
page = client.get(f"/v/{VIN}/dashboard")
check("dashboard page responds 200", page.status_code == 200, str(page.status_code))
svg_count = len(re.findall(r"<svg\b", page.text))
check("page embeds at least 3 <svg> charts", svg_count >= 3, str(svg_count))
for heading in ("Code timeline", "Repairs", "Live status", "Modules", "Odometer"):
    check(f"page has a {heading!r} section", heading in page.text)
for col in ("First", "Last", "Sessions", "When", "Kind", "What", "Result", "Tracked", "Codes"):
    check(f"a table header {col!r} is present", col in page.text)
check("vbar links to the dashboard tab", f"/v/{VIN}/dashboard" in page.text)
check("no template error leaked onto the page", "Jinja2" not in page.text
      and "Traceback" not in page.text)

print("=== JSON route ===")
data = client.get(f"/api/vehicles/{VIN}/dashboard")
check("JSON route responds 200", data.status_code == 200, str(data.status_code))
body = data.json()
check("JSON has the six top-level sections", {
    "summary", "code_timeline", "repairs_and_tests", "live_status",
    "modules", "odometer_series"} <= set(body), str(list(body)))
check("JSON summary vin matches", body["summary"]["vin"] == VIN)
check("JSON and page agree on chronic_count",
      str(body["summary"]["chronic_count"]) in page.text)

print("=== unknown VIN ===")
missing_page = client.get(f"/v/{NO_SUCH_VIN}/dashboard")
check("unknown VIN page does not 500", missing_page.status_code < 500,
      str(missing_page.status_code))
check("unknown VIN page is a 404", missing_page.status_code == 404,
      str(missing_page.status_code))
missing_json = client.get(f"/api/vehicles/{NO_SUCH_VIN}/dashboard")
check("unknown VIN JSON route is a 404, not a 500", missing_json.status_code == 404,
      str(missing_json.status_code))

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
