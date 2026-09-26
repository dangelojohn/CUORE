"""Smoke checks for the service pages (oil change, service, brakes/wheels/
tyres, torque library) and their JSON mirror.

CUORE_STATE_DIR is pointed at a fresh tempdir BEFORE anything cuore/mes is
imported, so this never writes to the real state directory. ``app.py`` is
owned by another agent and does not register this router, so this test
builds its own minimal FastAPI app around ``cuore.web.service_routes`` --
same settings/dependency wiring ``cuore.app.create_app`` uses, just without
the routers this feature doesn't touch.

Run:
    .venv/Scripts/python.exe cuore/tests/check_service_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-service-page-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: F401,E402
from cuore.config import load as load_settings  # noqa: E402
from cuore.services.errors import BridgeError  # noqa: E402
from cuore.web import service_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio this toolchain already knows about
TEST_VIN = "TESTVIN00000PAGE"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = load_settings()

    @app.exception_handler(BridgeError)
    async def _bridge_error(request: Request, exc: BridgeError):
        return JSONResponse(status_code=exc.status,
                            content={"error": type(exc).__name__, "detail": str(exc)})

    app.include_router(service_routes.router)
    app.include_router(service_routes.api_router, prefix="/api")
    return app


client = TestClient(build_app())


# --- oil change page ----------------------------------------------------------

r = client.get(f"/v/{VIN}/oil-change")
check("GET oil-change page responds 200", r.status_code == 200, str(r.status_code))
check("oil-change page renders the viscosity spec",
      "0W-30" in r.text or "Viscosity" in r.text)
check("oil-change page shows a confidence badge",
      "CONFIRMED" in r.text or "CORROBORATED" in r.text or "SINGLE-SOURCE" in r.text)
check("oil-change page shows the next-due verdict up top",
      "Next oil change" in r.text)

# round trip: submit a real form post, then confirm it shows up
post = client.post(f"/v/{TEST_VIN}/oil-change", data={
    "date": "2026-09-26", "odometer_km": "50000",
    "oil_brand": "Mopar", "oil_viscosity": "0W-30", "oil_spec": "MS-13340",
    "quantity_added_l": "5.2",
    "filter_brand": "Mopar", "filter_part_no": "4892339BE",
    "torque_drain_plug": "20", "torque_filter_cap": "25",
    "torque_wheel_lug": "121", "torque_spark_plug": "19.5",
    "technician": "Alice",
    "considerations_next": "watch the rear main seal",
})
check("POST oil-change form responds 200", post.status_code == 200, str(post.status_code))
check("POST oil-change confirms it was recorded", "Recorded" in post.text)

get_after = client.get(f"/v/{TEST_VIN}/oil-change")
check("GET oil-change after posting shows the last change",
      "Alice" in get_after.text and "4892339BE" in get_after.text)

# validation failure surfaces as a page error, not a 500
bad_post = client.post(f"/v/{TEST_VIN}/oil-change", data={
    "date": "", "odometer_km": "not-a-number", "oil_brand": "", "oil_viscosity": "",
    "quantity_added_l": "", "filter_part_no": "", "technician": "",
})
check("a bad oil-change submission does not 500", bad_post.status_code == 200,
      str(bad_post.status_code))
check("a bad oil-change submission shows the error on the page",
      "Not recorded" in bad_post.text)


# --- general service page ------------------------------------------------

r = client.get(f"/v/{VIN}/service")
check("GET service page responds 200", r.status_code == 200, str(r.status_code))

r_cat = client.get(f"/v/{VIN}/service", params={"category": "suspension"})
check("GET service page with a category shows its torque checklist",
      "Torque checklist" in r_cat.text and "Tie rod end nut" in r_cat.text)

post_svc = client.post(f"/v/{TEST_VIN}/service", data={
    "date": "2026-09-26", "odometer_km": "50100", "category": "suspension",
    "work_done": "replaced front sway bar end links", "technician": "Bob",
    "part_name": "sway bar end link", "part_no": "68245678AA", "part_qty": "2",
})
check("POST service form responds 200", post_svc.status_code == 200)
check("POST service confirms it was recorded", "Recorded" in post_svc.text)
check("service page lists the new record", "sway bar end links" in post_svc.text)


# --- brakes / wheels / tyres page ------------------------------------------

r = client.get(f"/v/{VIN}/brakes-tires")
check("GET brakes-tires page responds 200", r.status_code == 200, str(r.status_code))
check("brakes-tires page mentions the EPB service mode",
      "service mode" in r.text.lower())
check("brakes-tires page mentions live TPMS read-only",
      "TPMS" in r.text)

corner_data = {
    "date": "2026-09-26", "odometer_km": "50200", "technician": "Carol",
    "RL_pad_inner": "1.5", "RL_pad_outer": "1.6", "RL_rotor_thickness": "20",
    "RL_tread_inside": "1.0", "RL_tread_middle": "3.0", "RL_tread_outside": "5.0",
    "RL_pressure_set": "300",
    "torque_wheel_lug": "121",
}
post_bwt = client.post(f"/v/{TEST_VIN}/brakes-tires", data=corner_data)
check("POST brakes-tires form responds 200", post_bwt.status_code == 200)
check("POST brakes-tires confirms it was recorded", "Recorded" in post_bwt.text)

get_bwt_after = client.get(f"/v/{TEST_VIN}/brakes-tires")
check("brakes-tires page shows the carried-forward verdict flags after saving",
      "below legal minimum" in get_bwt_after.text or "uneven wear" in get_bwt_after.text)


# --- torque library page --------------------------------------------------

r = client.get(f"/v/{VIN}/torque")
check("GET torque page responds 200", r.status_code == 200, str(r.status_code))
check("torque page lists a CONFIRMED row (ZF 8HP pan bolts)",
      "CONFIRMED" in r.text)
check("torque page keeps UNKNOWN rows visible with a TechAuthority pointer",
      "UNKNOWN" in r.text and "TechAuthority" in r.text)

r_q = client.get(f"/v/{VIN}/torque", params={"q": "spark"})
check("torque page search filters by component text",
      "Spark plugs" in r_q.text)

r_cat2 = client.get(f"/v/{VIN}/torque", params={"category": "evap"})
check("torque page search filters by category",
      "EVAP canister" in r_cat2.text and "Wheel lug bolts" not in r_cat2.text)
# (the category <select> always lists every category as an <option>, so the
# negative assertion above checks a torque-row component name, not a label
# that legitimately appears in the picker regardless of the filter.)


# --- JSON API ----------------------------------------------------------------

api_records = client.get(f"/api/vehicles/{TEST_VIN}/service-records")
check("GET service-records JSON responds 200", api_records.status_code == 200)
body = api_records.json()
check("service-records JSON lists what was recorded above",
      body["vin"] == TEST_VIN and len(body["records"]) >= 3, str(body.get("records", []))[:200])

api_post = client.post(f"/api/vehicles/{TEST_VIN}/service-records", json={
    "kind": "oil_change",
    "data": {
        "date": "2026-10-01", "odometer_km": 58000,
        "oil": {"brand": "Mopar", "viscosity": "0W-30"},
        "quantity_added_l": 5.2,
        "filter": {"brand": "Mopar", "part_no": "4892339BE"},
        "technician": "Dana",
    },
})
check("POST service-records JSON responds 200", api_post.status_code == 200,
      api_post.text[:200])

api_next = client.get(f"/api/vehicles/{TEST_VIN}/oil-change/next")
check("GET oil-change/next JSON responds 200", api_next.status_code == 200)
check("oil-change/next JSON reflects the newest recorded change",
      api_next.json().get("last_oil_change_odometer_km") == 58000,
      str(api_next.json()))

api_torque = client.get(f"/api/vehicles/{TEST_VIN}/torque", params={"category": "wheels"})
check("GET torque JSON responds 200", api_torque.status_code == 200)
check("torque JSON includes the wheel lug spec",
      any(t["key"] == "wheel_lug" for t in api_torque.json()["torques"]))

api_bad = client.post(f"/api/vehicles/{TEST_VIN}/service-records", json={
    "kind": "oil_change", "data": {},
})
check("a bad JSON record post is a 400, not a 500", api_bad.status_code == 400,
      str(api_bad.status_code))


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
