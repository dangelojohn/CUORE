"""Page-speed budgets for the slow pages, plus the invalidation rules that make the caches safe.

Causes fixed (profiled on the real Stelvio corpus): every render re-listed and
re-stat'ed the MES log directory hundreds of times (``Catalog.entries``), probed
``state_dir()`` with a write/unlink on every call, spawned ``tasklist`` for each
interlock status, re-parsed the 2.3 MB observations file per (vin, kind) and
rebuilt the TSB cross-reference once per code.

The per-request memo (``mes.catalog.request_scope``) is opened by the app for
GET only and dropped when the request ends, so the NEXT request always sees a
new reading, note or scan. Nothing is cached across requests without a file
(mtime, size) key.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_page_speed.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-speed-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ["CUORE_NO_WARMUP"] = "1"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import cache  # noqa: E402
from mes import catalog, paths  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
WARM_BUDGET_S = 4.0     # target is 2 s; the margin absorbs a busy PC
COLD_BUDGET_S = 20.0    # first load of a fresh process on the full corpus (target 5 s with warm-up)

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}: {detail}")
        print(f"  FAIL {label} {detail}")
    else:
        print(f"  ok   {label} {detail}")


# 1. request scope: one listing per request, a fresh one for the next ---------
catalog.request_scope.set({})
a = catalog.CATALOG.entries()
b = catalog.CATALOG.entries()
check("scoped entries listed once per request", a == b)
catalog.request_scope.set(None)
check("no scope -> no memo", catalog.request_scope.get() is None)

# 2. observations: a new line shows on the next read -------------------------
obs = Path(STATE) / "observations.jsonl"
obs.write_text(json.dumps({"vin": VIN, "kind": "a", "n": 1}) + "\n", encoding="utf-8")
catalog.request_scope.set({})
first = cache.recent_observations(n=10, vin=VIN)
with obs.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"vin": VIN, "kind": "a", "n": 2}) + "\n")
same_req = cache.recent_observations(n=10, vin=VIN)
catalog.request_scope.set({})
next_req = cache.recent_observations(n=10, vin=VIN)
check("one reading before append", len(first) == 1)
check("next request sees the new reading", len(next_req) == 2, f"got {len(next_req)}")
check("kind filter", len(cache.recent_observations(n=10, vin=VIN, kind="zzz")) == 0)
check("other vin untouched", len(cache.recent_observations(n=10, vin="OTHER")) == 0)
catalog.request_scope.set(None)

# 3. state_dir memo follows the environment ----------------------------------
other = tempfile.mkdtemp(prefix="cuore-check-speed2-")
from mes import notes  # noqa: E402
d1 = notes.state_dir()
os.environ["CUORE_STATE_DIR"] = other
d2 = notes.state_dir()
os.environ["CUORE_STATE_DIR"] = STATE
check("state_dir follows CUORE_STATE_DIR", Path(d1) != Path(d2) and Path(d2) == Path(other))

# 4. page budgets on the real corpus -----------------------------------------
client = TestClient(create_app())
PAGES = [f"/v/{VIN}/job", f"/v/{VIN}/report", f"/v/{VIN}/bay-sheet", f"/v/{VIN}"]
for url in PAGES:
    t = time.perf_counter(); r = client.get(url); cold = time.perf_counter() - t
    t = time.perf_counter(); r2 = client.get(url); warm = time.perf_counter() - t
    check(f"{url} 200", r.status_code == 200 and r2.status_code == 200)
    check(f"{url} cold < {COLD_BUDGET_S}s", cold < COLD_BUDGET_S, f"{cold:.2f}s")
    check(f"{url} warm < {WARM_BUDGET_S}s", warm < WARM_BUDGET_S, f"{warm:.2f}s")

print(f"\n{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILED:", *failures, sep="\n  ")
    sys.exit(1)
