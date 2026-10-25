"""Checks for the codes page column sort (``/v/{vin}/codes?sort=&dir=``).

  1. ``_sort_code_rows`` orders by each column, flips with ``dir``, keeps
     rows with no value last both ways, and keeps diagnosis order on ties.
  2. An unknown ``sort`` leaves the diagnosis order untouched.
  3. The page renders for every column and direction, marks the sorted
     heading with ``aria-sort``, and the system chips carry the sort.

Run:
    .venv/Scripts/python.exe cuore/tests/check_codes_sort.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import routes  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


ROWS = [
    {"dtc": "P0456", "severity": "returned", "system_bucket": "EVAP", "modules": ["ECM"],
     "descriptions": ["EVAP small leak"], "sessions": 9, "first_seen": "2025-01-01",
     "last_seen": "2026-10-20", "distance_span_km": 9000},
    {"dtc": "U1713", "severity": "seen-once", "system_bucket": "Network", "modules": ["BCM"],
     "descriptions": ["CAN C bus"], "sessions": 1, "first_seen": "2026-10-13",
     "last_seen": "2026-10-13", "distance_span_km": None},
    {"dtc": "B1176", "severity": "chronic", "system_bucket": "Body", "modules": ["ABS"],
     "descriptions": [], "sessions": 4, "first_seen": "2026-02-01",
     "last_seen": "", "distance_span_km": 300},
]


def codes(sort: str, d: str = "") -> list[str]:
    out, _, _ = routes._sort_code_rows(list(ROWS), sort, d)
    return [r["dtc"] for r in out]


check(codes("") == ["P0456", "U1713", "B1176"], "empty sort keeps diagnosis order")
check(codes("bogus") == ["P0456", "U1713", "B1176"], "unknown sort keeps diagnosis order")
check(codes("module") == ["B1176", "U1713", "P0456"], "module A-Z")
check(codes("module", "desc") == ["P0456", "U1713", "B1176"], "module Z-A")
check(codes("state") == ["P0456", "B1176", "U1713"], "state: returned, chronic, seen-once")
check(codes("state", "desc") == ["U1713", "B1176", "P0456"], "state reversed")
check(codes("last") == ["P0456", "U1713", "B1176"], "last newest first, blank last")
check(codes("last", "asc") == ["U1713", "P0456", "B1176"], "last oldest first, blank still last")
check(codes("distance", "asc") == ["B1176", "P0456", "U1713"], "distance: None last")
check(codes("description")[-1] == "B1176", "no description goes last")
check(codes("sessions") == ["P0456", "B1176", "U1713"], "sessions most first")
check(codes("system") == ["P0456", "U1713", "B1176"], "system in bucket order")
check(routes._sort_code_rows(list(ROWS), "last", "")[2] == "desc", "dates open newest first")
check(routes._sort_code_rows(list(ROWS), "code", "sideways")[2] == "asc", "bad dir falls back")

client = TestClient(create_app())
VIN = "ZASFAKPN5J7B88115"
for key in routes._CODE_SORTS:
    for d in ("asc", "desc"):
        r = client.get(f"/v/{VIN}/codes?sort={key}&dir={d}")
        check(r.status_code == 200, f"page {key} {d} -> {r.status_code}")
        want = "ascending" if d == "asc" else "descending"
        check(f'aria-sort="{want}"' in r.text, f"aria-sort on {key} {d}")
r = client.get(f"/v/{VIN}/codes?sort=module&dir=asc&system=Network")
check("system=Body&amp;sort=module&amp;dir=asc" in r.text or "system=Body&sort=module&dir=asc" in r.text,
      "system chips keep the sort")
check("Back to diagnosis order" in r.text, "reset link shown when sorted")
r = client.get(f"/v/{VIN}/codes")
check(r.status_code == 200 and "aria-sort" not in r.text, "default page has no sorted column")

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
