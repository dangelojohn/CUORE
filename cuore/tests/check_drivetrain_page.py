"""Smoke checks for the drivetrain section pages, the service hub, and their
JSON mirror -- plus a check that the real app now serves the service-agent
routes at all (``app.py`` did not register them until this feature).

CUORE_STATE_DIR is pointed at a fresh tempdir BEFORE anything cuore/mes is
imported, so this never writes to the real state directory. Uses
``cuore.app.create_app`` throughout, same posture as
``cuore/tests/check_dashboard_page.py`` -- unlike ``check_service_page.py``
(written before this feature registered the service routers on the real
app), there is no need here to build a standalone app.

Run:
    .venv/Scripts/python.exe cuore/tests/check_drivetrain_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-drivetrain-page-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio this toolchain already knows about
TEST_VIN = "TESTVIN0000DRVPG"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())

SECTIONS = ("transmission", "transfer_case", "differentials", "driveline", "mounts")


# --- the real app now serves the service-agent routes -----------------------

check("real app serves /oil-change", client.get(f"/v/{VIN}/oil-change").status_code == 200)
check("real app serves /brakes-tires", client.get(f"/v/{VIN}/brakes-tires").status_code == 200)
check("real app serves /torque", client.get(f"/v/{VIN}/torque").status_code == 200)
check("real app serves /service-hub", client.get(f"/v/{VIN}/service-hub").status_code == 200)


# --- every drivetrain section page: 200, specs + torque table ---------------

for section in SECTIONS:
    r = client.get(f"/v/{VIN}/drivetrain/{section}")
    check(f"GET drivetrain/{section} responds 200", r.status_code == 200, str(r.status_code))
    check(f"drivetrain/{section} shows a confidence badge",
          any(c in r.text for c in ("CONFIRMED", "CORROBORATED", "SINGLE-SOURCE", "UNKNOWN")))
    check(f"drivetrain/{section} keeps an UNKNOWN row visible with TechAuthority",
          "UNKNOWN" in r.text and "TechAuthority" in r.text)

# a bad section 404s rather than 500ing
r_bad = client.get(f"/v/{VIN}/drivetrain/not-a-real-section")
check("an unknown drivetrain section does not 500", r_bad.status_code == 404, str(r_bad.status_code))

# transmission-specific content
r_tm = client.get(f"/v/{VIN}/drivetrain/transmission")
check("transmission page shows the 30-50 C fill window",
      "30-50" in r_tm.text or "30&deg;" in r_tm.text.replace("&#176;", "deg"))
check("transmission page shows the adaptation relearn reminder",
      "adaptation relearn" in r_tm.text.lower())
check("transmission page mentions TSB 21-035-20",
      "21-035-20" in r_tm.text)
check("transmission page mentions the live gearbox oil temp read (DID 04FE)",
      "04FE" in r_tm.text or "0x04FE" in r_tm.text)
check("transmission page shows a CONFIRMED torque row (pan bolts)",
      "CONFIRMED" in r_tm.text and "pan" in r_tm.text.lower())
check("transmission page visibly marks a cross-platform BMW row",
      "BMW" in r_tm.text)

# differentials: separate front/rear sub-sections
r_diff = client.get(f"/v/{VIN}/drivetrain/differentials")
check("differentials page shows a front sub-section", "Front differential" in r_diff.text)
check("differentials page shows a rear sub-section", "Rear differential" in r_diff.text)


# --- job selector: plain GET, loads that job's steps + torque checklist -----

r_job = client.get(f"/v/{VIN}/drivetrain/transmission",
                   params={"job": "transmission_fluid_service"})
check("job selector GET responds 200", r_job.status_code == 200)
check("job selector loads the job's steps",
      "Job steps" in r_job.text and "pan/filter" in r_job.text.lower())
check("job selector loads the job's torque checklist",
      "Torque checklist" in r_job.text)

r_job_diff = client.get(f"/v/{VIN}/drivetrain/differentials",
                        params={"job": "differential_service_rear"})
check("differentials job selector accepts the rear job",
      "differential_service_rear".replace("_", " ") in r_job_diff.text.lower()
      or "rear diff" in r_job_diff.text.lower())


# --- form post round trip ----------------------------------------------------

post = client.post(f"/v/{TEST_VIN}/drivetrain/transmission", data={
    "job": "transmission_fluid_service",
    "date": "2026-09-26", "odometer_km": "52000", "technician": "Hank",
    "fluid_brand": "Mopar", "fluid_spec": "68218925AA",
    "quantity_drained_l": "9.0", "quantity_added_l": "9.2",
    "fluid_color": "red", "fluid_smell": "normal",
    "fluid_temp_c": "40",
    "adaptation_done": "on", "adaptation_tool": "MES",
    "part_name": "pan/filter assembly", "part_no": "68XXXXXXAA", "part_qty": "1",
    "torque_transmission_pan_bolts": "10",
    "considerations_next": "recheck for weep at the pan gasket",
})
check("POST drivetrain form responds 200", post.status_code == 200, str(post.status_code))
check("POST drivetrain confirms it was recorded", "Recorded" in post.text)

get_after = client.get(f"/v/{TEST_VIN}/drivetrain/transmission")
check("GET drivetrain after posting shows the technician and part",
      "Hank" in get_after.text and "68XXXXXXAA" in get_after.text)
check("GET drivetrain after posting shows carried-forward considerations",
      "recheck for weep" in get_after.text)

# a fluid temp outside the 30-50 C window is flagged on the page
post_hot = client.post(f"/v/{TEST_VIN}/drivetrain/transmission", data={
    "job": "transmission_fluid_service",
    "date": "2026-09-27", "odometer_km": "52100", "technician": "Hank",
    "fluid_temp_c": "70",
})
check("POST with an out-of-window fluid temp responds 200", post_hot.status_code == 200)
get_hot_after = client.get(f"/v/{TEST_VIN}/drivetrain/transmission")
check("out-of-window fluid temp flag shows on the page",
      "outside the 30-50" in get_hot_after.text)

# validation failure surfaces as a page error, not a 500
bad_post = client.post(f"/v/{TEST_VIN}/drivetrain/mounts", data={
    "date": "", "odometer_km": "not-a-number", "technician": "",
})
check("a bad drivetrain submission does not 500", bad_post.status_code == 200,
      str(bad_post.status_code))
check("a bad drivetrain submission shows the error on the page",
      "Not recorded" in bad_post.text)


# --- service hub --------------------------------------------------------------

r_hub = client.get(f"/v/{TEST_VIN}/service-hub")
check("GET service-hub page responds 200", r_hub.status_code == 200, str(r_hub.status_code))
for label in ("Engine oil", "Brakes, wheels", "Transmission", "Transfer case",
             "Differentials", "Driveline", "Mounts", "EVAP", "Torque library"):
    check(f"service-hub shows the {label!r} card", label in r_hub.text)
check("service-hub links to oil-change and general service",
      f"/v/{TEST_VIN}/oil-change" in r_hub.text and f"/v/{TEST_VIN}/service" in r_hub.text)
check("service-hub links to brakes-tires",
      f"/v/{TEST_VIN}/brakes-tires" in r_hub.text)
for section in SECTIONS:
    check(f"service-hub links to drivetrain/{section}",
          f"/v/{TEST_VIN}/drivetrain/{section}" in r_hub.text)
check("service-hub links to the fault tree and dashboard for EVAP",
      f"/v/{TEST_VIN}/tree" in r_hub.text and f"/v/{TEST_VIN}/dashboard" in r_hub.text)
check("service-hub links to the torque library",
      f"/v/{TEST_VIN}/torque" in r_hub.text)
check("service-hub shows the transmission card's flag after the hot-fluid post",
      "outside the 30-50" in r_hub.text)

# the Service tab in the vehicle bar points at the hub
check("the vehicle bar carries a Service tab to the hub",
      f"/v/{VIN}/service-hub" in client.get(f"/v/{VIN}/oil-change").text)


# --- JSON API ----------------------------------------------------------------

api_hub = client.get(f"/api/vehicles/{TEST_VIN}/service-hub")
check("GET service-hub JSON responds 200", api_hub.status_code == 200)
hub_body = api_hub.json()
check("service-hub JSON has one entry per drivetrain section",
      set(hub_body["drivetrain"].keys()) == set(SECTIONS), str(hub_body.get("drivetrain", {})))
check("service-hub JSON reflects the recorded transmission service",
      hub_body["drivetrain"]["transmission"]["last"] is not None)

api_get = client.get(f"/api/vehicles/{TEST_VIN}/drivetrain/transmission")
check("GET drivetrain JSON responds 200", api_get.status_code == 200)
check("drivetrain JSON bundles specs/jobs/history",
      {"specs", "jobs", "history"} <= set(api_get.json().keys()))

api_post = client.post(f"/api/vehicles/{TEST_VIN}/drivetrain/differentials", json={
    "job": "differential_service_rear", "date": "2026-09-26", "odometer_km": 52200,
    "technician": "Ivan", "fluid": {"brand": "Petronas"},
    "torques_applied": {"rear_diff_fill_plug": 26},
})
check("POST drivetrain JSON responds 200", api_post.status_code == 200, api_post.text[:200])
check("POST drivetrain JSON records the given section",
      api_post.json()["data"]["section"] == "differentials")

api_bad = client.post(f"/api/vehicles/{TEST_VIN}/drivetrain/transmission", json={
    "job": "not-a-real-job", "date": "2026-09-26", "odometer_km": 1, "technician": "x",
})
check("a bad drivetrain JSON post is a 400, not a 500", api_bad.status_code == 400,
      str(api_bad.status_code))

api_bad_section = client.get(f"/api/vehicles/{TEST_VIN}/drivetrain/not-a-real-section")
check("an unknown drivetrain section JSON GET is a 404, not a 500",
      api_bad_section.status_code == 404, str(api_bad_section.status_code))


# --- service hub shows MES-logged service events -----------------------------

from cuore.services import service_bridge as _sb  # noqa: E402

_orig = _sb._mes_service_events
_sb._mes_service_events = lambda vin: [{"operation": "Oil change", "date": "2026-09-15",
                                        "outcome": "COMPLETED", "source": "logged in MES"}]
try:
    r_hub = client.get(f"/v/{TEST_VIN}/service-hub")
    check("service hub lists an MES-logged oil change when no cuore record exists",
          "Logged in MES" in r_hub.text and "Oil change, 2026-09-15" in r_hub.text)
finally:
    _sb._mes_service_events = _orig


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
