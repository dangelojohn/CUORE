"""Smoke checks for the routine-maintenance page, its JSON mirror, and the
service-hub card for it.

CUORE_STATE_DIR is pointed at a fresh tempdir BEFORE anything cuore/mes is
imported, so this never writes to the real state directory (never touches
C:\\ProgramData\\cuore). Uses ``cuore.app.create_app`` throughout, same
posture as ``cuore/tests/check_drivetrain_page.py`` -- the maintenance
routes were added directly onto ``cuore.web.service_routes``'s existing
router objects, which ``app.py`` already registers, so no ``app.py`` change
was needed for this feature either.

This exercises the real :mod:`mes.maintenance_specs` data (not a fixture --
that's what ``mes-log-mcp/tests/check_maintenance.py`` uses for the ledger
logic itself), so it only asserts on the documented shape (item keys,
UNKNOWN/TechAuthority honesty, due-table structure), never on specific
interval/part values that a later research-pass correction could change.

Run:
    .venv/Scripts/python.exe cuore/tests/check_maintenance_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-maintenance-page-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio this toolchain already knows about
TEST_VIN = "TESTVIN0000MNTPG"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())

from mes import maintenance_specs  # noqa: E402

ITEM_KEYS = list(maintenance_specs.ITEMS.keys())


# --- page: 200, due table, category cards --------------------------------------

r = client.get(f"/v/{VIN}/maintenance")
check("GET maintenance page responds 200", r.status_code == 200, str(r.status_code))
check("maintenance page shows the due-status table", "Due status" in r.text)
check("maintenance page lists every item's label",
      all(maintenance_specs.ITEMS[k]["label"] in r.text for k in ITEM_KEYS),
      str([k for k in ITEM_KEYS if maintenance_specs.ITEMS[k]["label"] not in r.text]))
check("maintenance page shows a status chip",
      any(s in r.text for s in ("overdue", "due soon", "never recorded", "interval unknown", "ok")))
check("maintenance page keeps an UNKNOWN item visible with the TechAuthority pointer",
      "UNKNOWN" in r.text and "TechAuthority" in r.text)
check("maintenance page links to the torque library",
      f"/v/{VIN}/torque" in r.text)


# --- item picker: GET with items= loads per-item fields + torque checklist -----

pick_keys = [k for k in ITEM_KEYS if maintenance_specs.ITEMS[k]["torque_keys"]][:1] or ITEM_KEYS[:1]
r_pick = client.get(f"/v/{VIN}/maintenance", params={"items": pick_keys})
check("item picker GET responds 200", r_pick.status_code == 200, str(r_pick.status_code))
check("item picker loads an action selector for the picked item",
      f"action_{pick_keys[0]}" in r_pick.text)


# --- form POST round trip -------------------------------------------------------

post_key = ITEM_KEYS[0]
post_data = {
    "selected_items": post_key,
    "date": "2026-09-26", "odometer_km": "52000", "technician": "Hank",
    f"record_item_{post_key}": "on",
    f"action_{post_key}": "replaced",
    f"part_brand_{post_key}": "Mopar",
    f"part_number_{post_key}": "68XXXXXXAA",
    f"condition_notes_{post_key}": "looked original, replaced anyway",
    f"measure_label_{post_key}_1": "voltage", f"measure_value_{post_key}_1": "12.6",
    "next_time_notes": "recheck fitment next visit",
}
post = client.post(f"/v/{TEST_VIN}/maintenance", data=post_data)
check("POST maintenance form responds 200", post.status_code == 200, str(post.status_code))
check("POST maintenance confirms it was recorded", "Recorded" in post.text)

get_after = client.get(f"/v/{TEST_VIN}/maintenance")
check("GET maintenance after posting shows the technician and part",
      "Hank" in get_after.text and "68XXXXXXAA" in get_after.text)
check("GET maintenance after posting shows the carried-forward next-time note",
      "recheck fitment next visit" in get_after.text)
check("GET maintenance after posting shows a last-done date in the due table",
      "2026-09-26" in get_after.text)

# a bad submission (no items at all) does not 500
bad_post = client.post(f"/v/{TEST_VIN}/maintenance", data={
    "date": "", "odometer_km": "not-a-number", "technician": "",
})
check("a maintenance submission with no items does not 500", bad_post.status_code == 200,
      str(bad_post.status_code))
check("a maintenance submission with no items shows the error on the page",
      "Not recorded" in bad_post.text)


# --- JSON API --------------------------------------------------------------

api_get = client.get(f"/api/vehicles/{TEST_VIN}/maintenance")
check("GET maintenance JSON responds 200", api_get.status_code == 200)
api_body = api_get.json()
check("maintenance JSON has items_by_category covering every real category",
      set(api_body["items_by_category"].keys()) == set(maintenance_specs.CATEGORIES))
check("maintenance JSON reflects the recorded item",
      api_body["last_maintenance"]["data"]["items"][0]["item_key"] == post_key,
      str(api_body.get("last_maintenance")))

api_due = client.get(f"/api/vehicles/{TEST_VIN}/maintenance/due")
check("GET maintenance due JSON responds 200", api_due.status_code == 200)
due_body = api_due.json()
check("maintenance due JSON covers every real item",
      {i["item_key"] for i in due_body["items"]} == set(ITEM_KEYS))
check("maintenance due JSON reflects the just-recorded item's last date",
      next(i for i in due_body["items"] if i["item_key"] == post_key)["last_date"] == "2026-09-26")

api_post_ok = client.post(f"/api/vehicles/{TEST_VIN}/maintenance", json={
    "date": "2026-09-27", "odometer_km": 52100, "technician": "Ivy",
    "items": [{"item_key": ITEM_KEYS[1], "action": "inspected_ok"}],
})
check("POST maintenance JSON responds 200", api_post_ok.status_code == 200, api_post_ok.text[:200])

# unknown item_key is rejected as a 400, never a 500
api_bad = client.post(f"/api/vehicles/{TEST_VIN}/maintenance", json={
    "date": "2026-09-27", "odometer_km": 52100, "technician": "Ivy",
    "items": [{"item_key": "not-a-real-item-key", "action": "replaced"}],
})
check("an unknown item_key JSON post is a 400, not a 500",
      api_bad.status_code == 400, str(api_bad.status_code))

# unknown action is likewise rejected, never a 500
api_bad_action = client.post(f"/api/vehicles/{TEST_VIN}/maintenance", json={
    "date": "2026-09-27", "odometer_km": 52100, "technician": "Ivy",
    "items": [{"item_key": ITEM_KEYS[0], "action": "not-a-real-action"}],
})
check("an unknown action JSON post is a 400, not a 500",
      api_bad_action.status_code == 400, str(api_bad_action.status_code))

# empty body is a 400, not a 500 (also confirms no path here ever 500s on
# missing required fields, mirroring check_service_page.py's equivalent check)
api_empty = client.post(f"/api/vehicles/{TEST_VIN}/maintenance", json={})
check("an empty maintenance JSON post is a 400, not a 500",
      api_empty.status_code == 400, str(api_empty.status_code))


# --- service hub card --------------------------------------------------------

r_hub = client.get(f"/v/{TEST_VIN}/service-hub")
check("GET service-hub page responds 200 after a maintenance record exists",
      r_hub.status_code == 200, str(r_hub.status_code))
check("service-hub shows the Routine maintenance card", "Routine maintenance" in r_hub.text)
check("service-hub links to /maintenance", f"/v/{TEST_VIN}/maintenance" in r_hub.text)
check("service-hub Routine maintenance card comes after Engine oil & service",
      r_hub.text.index("Engine oil &amp; service" if "Engine oil &amp; service" in r_hub.text
                       else "Engine oil & service") <
      r_hub.text.index("Routine maintenance"))

api_hub = client.get(f"/api/vehicles/{TEST_VIN}/service-hub")
check("GET service-hub JSON responds 200", api_hub.status_code == 200)
hub_body = api_hub.json()
check("service-hub JSON carries a maintenance section",
      "maintenance" in hub_body and "due" in hub_body["maintenance"])
check("service-hub JSON maintenance.last reflects the recorded visit",
      hub_body["maintenance"]["last"] is not None)


# --- vehicle bar / general-service page link this feature in --------------------

check("the general service page links to /maintenance",
      f"/v/{VIN}/maintenance" in client.get(f"/v/{VIN}/service").text)


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
