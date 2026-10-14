"""Checks for the additive ``GET /api/scans/search`` endpoint
(``cuore.api.scanlog``) -- the HTTP face of the same "search every CUORE
log" capability ``mes.cuore_log.search`` gives the MCP side (the two are
separate processes/venvs and deliberately do not import one another; see
``cuore.api.scanlog``'s own module comment).

Fixture: the real 2026-10-13 lines copied out of the production
``observations.jsonl``, never read from there again once copied and never
written back to -- same posture as ``cuore/tests/check_scanlog.py``.
``CUORE_STATE_DIR`` points at a throwaway directory set BEFORE ``cuore`` is
imported.

Run:
    .venv/Scripts/python.exe cuore/tests/check_cuore_log.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-cuore-log-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PROD_OBSERVATIONS = Path(r"C:\ProgramData\cuore\observations.jsonl")

# --- fixture, built before any cuore import reads the state dir ------------

if PROD_OBSERVATIONS.exists():
    real_lines = [l for l in PROD_OBSERVATIONS.read_text(encoding="utf-8").splitlines()
                 if '"at": "2026-10-13' in l]
else:
    real_lines = []

state_dir = Path(os.environ["CUORE_STATE_DIR"])
(state_dir / "observations.jsonl").write_text("\n".join(real_lines) + "\n", encoding="utf-8")
(state_dir / "owner_events.jsonl").write_text(
    json.dumps({"op": "event", "id": "oe1", "vin": "ZASFAKPN5J7B88115",
               "at": "2026-10-13T21:00:00", "by": {"role": "owner", "name": "test"},
               "category": "fuel", "kind": "fill_up", "fields": {}, "note": "U1713 noted by owner",
               "confidence": "reported"}) + "\n", encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.api import scanlog as scanlog_api  # noqa: E402

app = create_app()
existing_paths = {getattr(r, "path", None) for r in app.routes}
if "/api/scans/search" not in existing_paths and "/api/scans/{vin}" not in existing_paths:
    app.include_router(scanlog_api.router, prefix="/api")
client = TestClient(app)

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


print("=== setup ===")
check("real observation lines were found and copied", len(real_lines) > 0, "0 lines copied")

print("=== GET /api/scans/search ===")
r = client.get("/api/scans/search", params={"pattern": "U1713"})
check("status 200", r.status_code == 200, str(r.status_code))
body = r.json()
check("finds hits in both observations and owner_events",
     {m["source"] for m in body["matches"]} >= {"observations", "owner_events"},
     str(body["matches"]))
check("newest first", [m["at"] for m in body["matches"] if m["at"]]
     == sorted((m["at"] for m in body["matches"] if m["at"]), reverse=True))
check("each hit carries file/line/context",
     all("file" in m and "line" in m and "context" in m for m in body["matches"]),
     str(body["matches"])[:300])

r2 = client.get("/api/scans/search", params={"pattern": "U1713", "kinds": "owner_events"})
check("a kinds filter narrows the source",
     r2.json()["count"] >= 1 and all(m["source"] == "owner_events" for m in r2.json()["matches"]),
     str(r2.json()))

r3 = client.get("/api/scans/search", params={"pattern": "NOPE_NOT_PRESENT_ANYWHERE"})
check("no matches is a clean empty result, not an error",
     r3.status_code == 200 and r3.json()["count"] == 0, str(r3.json()))

r4 = client.get("/api/scans/search", params={"pattern": "U1713", "since": "2026-10-14"})
check("a since filter past every hit's date returns nothing",
     r4.json()["count"] == 0, str(r4.json()))

# The existing /{vin} route must still work: /search is a sibling, not a
# shadow of the dynamic {vin} path segment.
r5 = client.get("/api/scans/ZASFAKPN5J7B88115")
check("the existing /scans/{vin} route is unaffected", r5.status_code == 200, str(r5.status_code))

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
