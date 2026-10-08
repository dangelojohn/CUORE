"""Smoke checks for the vehicle-systems API: ``/api/systems*``, fed by
``cuore.services.systems_bridge`` -> ``mes.systems``.

``cuore.api.systems`` is not wired into ``cuore.app`` yet -- ``app.py`` is
owned by another agent -- so this includes it itself if ``create_app()``
did not already pick it up (same posture as ``check_parts_page.py``).

Run:
    .venv/Scripts/python.exe cuore/tests/check_systems_api.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-systems-api-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.api import systems as systems_api  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic EVAP + network history

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")
    print(f"  [{'ok' if condition else 'FAIL'}] {label}")


def _app_with_router():
    app = create_app()
    if not any(getattr(r, "path", "") == "/api/systems" for r in app.routes):
        app.include_router(systems_api.router, prefix="/api")
    return app


client = TestClient(_app_with_router())


print("=== /api/systems ===")
r = client.get("/api/systems")
check("list responds 200", r.status_code == 200, str(r.status_code))
body = r.json()
check("list has systems + count", "systems" in body and body["count"] == len(body["systems"]))
check("evap is in the graph", any(s["key"] == "evap" for s in body["systems"]))

print("=== /api/systems/for-code/{code} ===")
r = client.get("/api/systems/for-code/P0455")
check("for-code responds 200", r.status_code == 200, str(r.status_code))
body = r.json()
check("P0455 evap primary present",
      any(s["system"] == "evap" and s["role"] == "primary" for s in body["systems"]),
      str(body))
check("P0455 electrical_supply upstream present",
      any(s["system"] == "electrical_supply" and s["role"] == "upstream"
          for s in body["systems"]),
      str(body))

r = client.get("/api/systems/for-code/U1713")
check("U1713 maps to network",
      any(s["system"] == "network" for s in r.json()["systems"]), str(r.json()))

print("=== /api/vehicles/{vin}/systems ===")
r = client.get(f"/api/vehicles/{VIN}/systems")
check("vehicle systems responds 200", r.status_code == 200, str(r.status_code))
body = r.json()
by_system = {row["system"]: row for row in body.get("by_system", [])}
check("evap sessions >= 4", by_system.get("evap", {}).get("sessions", 0) >= 4,
      str(by_system.get("evap")))
check("network sessions >= 4", by_system.get("network", {}).get("sessions", 0) >= 4,
      str(by_system.get("network")))
check("at least one co-occurrence row", len(body.get("co_occurrence", [])) >= 1)

r = client.get("/api/vehicles/NOPE123NOTREAL0000/systems")
check("unknown VIN is a 404", r.status_code == 404, str(r.status_code))

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print(f"all {checks} checks passed")
