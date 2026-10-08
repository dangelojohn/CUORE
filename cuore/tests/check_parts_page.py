"""Smoke checks for the parts catalog: the JSON API, the ``/v/{vin}/parts``
page, and the part cards embedded on ``code.html``/``maintenance.html``.

``CUORE_STATE_DIR`` is pointed at a fresh tempdir BEFORE anything cuore/mes
is imported (same posture as ``check_maintenance_page.py``). Neither
``cuore.web.parts_routes`` nor ``cuore.api.parts`` is wired into
``cuore.app`` yet -- ``app.py`` is owned by another agent -- so this
includes them itself if ``create_app()`` did not already pick them up (same
posture as ``check_timeline_page.py``).

``mes-log-mcp/mes/parts.py`` landed before this was finished, so these
assertions are against its real data (``esim``/``purge_valve``, both tagged
P0455/P0456; ``oil_filter``'s real ``filter_cap`` torque spec) rather than
``cuore.services.parts_bridge``'s own fixture -- that fixture only matters
if ``mes.parts`` ever fails to import, which these checks can't force, so
it is exercised by that bridge module's own docstring/shape, not here.

Run:
    .venv/Scripts/python.exe cuore/tests/check_parts_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-parts-page-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import parts_routes  # noqa: E402
from cuore.api import parts as parts_api  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0456

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def _app_with_router():
    app = create_app()
    if not any(getattr(r, "path", "") == "/v/{vin}/parts" for r in app.routes):
        app.include_router(parts_routes.router)
    if not any(getattr(r, "path", "") == "/api/parts" for r in app.routes):
        app.include_router(parts_api.router, prefix="/api")
    return app


client = TestClient(_app_with_router())


# === 1. API: list / key / 404 ==============================================

r = client.get("/api/parts")
check("list responds 200", r.status_code == 200, str(r.status_code))
body = r.json()
check("list has parts + count", "parts" in body and body["count"] == len(body["parts"]))
check("esim is in the catalog", any(p["key"] == "esim" for p in body["parts"]))

r = client.get("/api/parts/esim")
check("get by key responds 200", r.status_code == 200, str(r.status_code))
part = r.json()
check("key is folded into the record", part.get("key") == "esim", str(part.get("key")))
check("resolved torque row present for its torque_keys",
      bool(part.get("torques")) and part["torques"][0]["key"] == "evap_esim_mount",
      str(part.get("torques")))

r = client.get("/api/parts/oil_filter")
check("a real, sourced torque value resolves (filter_cap, not UNKNOWN)",
      r.json()["torques"][0]["value"] is not None, str(r.json()["torques"]))

r = client.get("/api/parts/no-such-part-key")
check("unknown key is a 404", r.status_code == 404, str(r.status_code))

r = client.get("/api/parts/for-code/P0455")
check("for-code groups esim and purge_valve", {"esim", "purge_valve"} <=
      {p["key"] for p in r.json()["parts"]}, str(r.json()))


# === 2. the parts page: 200, cards, search =================================

r = client.get(f"/v/{VIN}/parts")
check("parts page responds 200", r.status_code == 200, str(r.status_code))
check("page has the search form", 'name="q"' in r.text)
check("page lists a part card", "Evaporative System Integrity Module" in r.text)

r = client.get(f"/v/{VIN}/parts?q=purge")
check("search narrows results", "purge valve" in r.text.lower()
      and "brake pads" not in r.text.lower())


# === 3. code page P0455 shows ESIM/purge parts =============================

r = client.get(f"/v/{VIN}/code/P0455")
check("code page responds 200", r.status_code == 200, str(r.status_code))
check("code page shows the ESIM part", "Evaporative System Integrity Module" in r.text)
check("code page shows the purge valve part", "EVAP purge valve" in r.text)


# === 4. maintenance page renders part cards =================================

r = client.get(f"/v/{VIN}/maintenance")
check("maintenance page responds 200", r.status_code == 200, str(r.status_code))
check("maintenance page renders a part card for an item (real OEM number)",
      "68301538AA" in r.text, "engine_air_filter part card not found")


# === bonus: oil_change.html / brakes_tires.html also render part cards ====

r = client.get(f"/v/{VIN}/oil-change")
check("oil-change page responds 200", r.status_code == 200, str(r.status_code))
check("oil-change page renders the oil filter part card", "Engine oil filter" in r.text)

r = client.get(f"/v/{VIN}/brakes-tires")
check("brakes-tires page responds 200", r.status_code == 200, str(r.status_code))
check("brakes-tires page renders a front brake pad part card", "Front brake pads" in r.text)


# === 5. price shows "as of" =================================================

parts_page_text = client.get(f"/v/{VIN}/parts").text
check("a priced part on the page carries its as-of date",
      "as of" in parts_page_text and "2026-10-07" in parts_page_text)


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(" -", f)
if failures:
    sys.exit(1)
