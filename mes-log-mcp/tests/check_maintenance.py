"""Smoke checks for mes.service's ``maintenance`` kind.

No mocks, no real corpus needed for the ledger itself -- CUORE_STATE_DIR is
pointed at a fresh tempdir BEFORE anything is imported, so this never
touches the real state directory (never writes to C:\\ProgramData\\cuore).

``mes.maintenance_specs.ITEMS`` is monkeypatched to a small, fixed fixture
before every check that exercises validation/due-date logic, so none of
this depends on the real (research-pass-dependent) item data -- a later
correction to a real interval or part number can never break this file.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_maintenance.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-maintenance-")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mes import maintenance_specs, service  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio this toolchain already knows about
TEST_VIN = "TESTVIN0000MAINT"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- fixture: a small, self-contained ITEMS, independent of real research ---

FIXTURE_ITEMS = {
    "engine_air_filter": {
        "key": "engine_air_filter", "label": "Engine air filter",
        "category": "filters",
        "interval_miles": 30000, "interval_km": 48280, "interval_months": 24,
        "interval_note": "", "interval_confidence": "CORROBORATED",
        "interval_source": "fixture",
        "parts": [{"name": "air filter element", "part_number": "FIX-001",
                  "confidence": "SINGLE-SOURCE", "source": "fixture", "notes": ""}],
        "fluid": None,
        "torque_keys": [],
        "procedure": ["Release housing clips", "Swap element", "Reseat housing"],
        "checks": ["Check for debris in housing"],
        "post_service": [],
        "notes": "",
    },
    "spark_plugs": {
        "key": "spark_plugs", "label": "Spark plugs", "category": "ignition",
        "interval_miles": 60000, "interval_km": 96560, "interval_months": None,
        "interval_note": "", "interval_confidence": "CORROBORATED",
        "interval_source": "fixture",
        "parts": [{"name": "spark plug", "part_number": "FIX-SP1",
                  "confidence": "CORROBORATED", "source": "fixture", "notes": ""}],
        "fluid": None,
        "torque_keys": ["spark_plug"],  # real mes.service_specs key -- exercises the join
        "procedure": ["Remove coils", "Remove plugs", "Gap and install new plugs",
                     "Torque plugs", "Reinstall coils"],
        "checks": ["Inspect coil boots"],
        "post_service": ["Clear any stored misfire codes"],
        "notes": "",
    },
    "battery_12v": {
        "key": "battery_12v", "label": "12V battery", "category": "electrical",
        "interval_miles": None, "interval_km": None, "interval_months": None,
        "interval_note": "use the service manual (TechAuthority)",
        "interval_confidence": "UNKNOWN", "interval_source": None,
        "parts": [], "fluid": None, "torque_keys": ["battery_terminal"],
        "procedure": ["Test battery", "Replace if below spec"],
        "checks": ["Load test", "Check terminal corrosion"],
        "post_service": ["Confirm no battery-saver faults after reconnect"],
        "notes": "",
    },
    "coolant": {
        "key": "coolant", "label": "Engine coolant", "category": "fluids",
        "interval_miles": None, "interval_km": None, "interval_months": 60,
        "interval_note": "", "interval_confidence": "SINGLE-SOURCE",
        "interval_source": "fixture",
        "parts": [], "fluid": {"spec": "FIX-OAT", "capacity": 7.0, "unit": "L",
                               "confidence": "SINGLE-SOURCE", "source": "fixture", "notes": ""},
        "torque_keys": [], "procedure": ["Drain", "Refill", "Bleed"],
        "checks": ["Freeze point test"], "post_service": ["Bleed cooling system"],
        "notes": "",
    },
}


_REAL_ITEMS = maintenance_specs.ITEMS  # the real module's dict object, kept to restore later


def _install_fixture() -> None:
    """Replace the module attribute (not mutate the real dict in place) so
    the untouched real ``ITEMS`` object can simply be reassigned back."""
    maintenance_specs.ITEMS = dict(FIXTURE_ITEMS)


def _restore_real_items() -> None:
    maintenance_specs.ITEMS = _REAL_ITEMS


_install_fixture()


# --- validation ----------------------------------------------------------------

try:
    service.record_maintenance(TEST_VIN, {})
    check("empty maintenance data is rejected", False)
except ValueError:
    check("empty maintenance data is rejected", True)

try:
    service.record_maintenance(TEST_VIN, {
        "date": "2026-09-26", "odometer_km": 40000, "technician": "Alice",
        "items": [],
    })
    check("maintenance with no items is rejected", False)
except ValueError:
    check("maintenance with no items is rejected", True)

try:
    service.record_maintenance(TEST_VIN, {
        "date": "2026-09-26", "odometer_km": 40000, "technician": "Alice",
        "items": [{"item_key": "not_a_real_item", "action": "replaced"}],
    })
    check("an unknown item_key is rejected", False)
except ValueError as exc:
    check("an unknown item_key is rejected", True, str(exc))

try:
    service.record_maintenance(TEST_VIN, {
        "date": "2026-09-26", "odometer_km": 40000, "technician": "Alice",
        "items": [{"item_key": "engine_air_filter", "action": "not_a_real_action"}],
    })
    check("an unknown action is rejected", False)
except ValueError:
    check("an unknown action is rejected", True)

try:
    service.record_maintenance("", {
        "date": "2026-09-26", "odometer_km": 40000, "technician": "Alice",
        "items": [{"item_key": "engine_air_filter", "action": "replaced"}],
    })
    check("missing vin is rejected", False)
except ValueError:
    check("missing vin is rejected", True)


# --- record / torque checklist / flags ------------------------------------------

r1 = service.record_maintenance(TEST_VIN, {
    "date": "2026-09-01", "odometer_km": 40000, "technician": "Alice",
    "items": [
        {"item_key": "engine_air_filter", "action": "replaced",
         "part_brand": "Mopar", "part_number": "FIX-001"},
        {"item_key": "spark_plugs", "action": "replaced",
         "part_brand": "NGK", "part_number": "FIX-SP1"},
    ],
    "torques_applied": {"spark_plug": 19.5},
    "next_time_notes": ["watch for a slight misfire on cold start"],
})
check("record_maintenance returns an id", bool(r1.get("id")))
check("record stores both items", len(r1["data"]["items"]) == 2)
check("torque checklist covers the spark_plug key from spark_plugs' torque_keys",
      any(t["key"] == "spark_plug" for t in r1["data"]["torque_checklist"]["rows"]))
check("a correctly-applied, sourced torque produces no flag",
      not r1["data"]["torque_checklist"]["flags"], str(r1["data"]["torque_checklist"]["flags"]))
check("post-service step not confirmed done is flagged (spark plugs replaced, "
      "misfire-code clear not confirmed)",
      any("Clear any stored misfire codes" in f for f in r1["data"]["flags"]), str(r1["data"]["flags"]))

r2 = service.record_maintenance(TEST_VIN, {
    "date": "2026-09-10", "odometer_km": 40500, "technician": "Bob",
    "items": [{"item_key": "battery_12v", "action": "inspected_needs_attention",
              "condition_notes": "cranking amps low, replace soon",
              "measurements": {"voltage": 11.9}}],
})
check("an inspected_needs_attention item is flagged with its condition notes",
      any("needs attention" in f and "cranking amps low" in f for f in r2["data"]["flags"]),
      str(r2["data"]["flags"]))
check("measurements free-dict is stored as given",
      r2["data"]["items"][0]["measurements"] == {"voltage": 11.9})
check("an item with no torque_keys produces an empty torque checklist without error",
      r2["data"]["torque_checklist"]["rows"] == []
      or all(t["key"] == "battery_terminal" for t in r2["data"]["torque_checklist"]["rows"]))

r3 = service.record_maintenance(TEST_VIN, {
    "date": "2026-09-15", "odometer_km": 41000, "technician": "Carol",
    "items": [{"item_key": "spark_plugs", "action": "replaced"}],
    "post_service_done": ["Clear any stored misfire codes"],
})
check("confirming a post-service step suppresses its flag",
      not any("post-service step not done" in f for f in r3["data"]["flags"]), str(r3["data"]["flags"]))


# --- last_maintenance_item -------------------------------------------------

last_ea = service.last_maintenance_item(TEST_VIN, "engine_air_filter")
check("last_maintenance_item finds the item inside a multi-item record",
      last_ea is not None and last_ea["odometer_km"] == 40000 and last_ea["date"] == "2026-09-01")
check("last_maintenance_item returns the item's own sub-record",
      last_ea["item"]["part_number"] == "FIX-001")

last_sp = service.last_maintenance_item(TEST_VIN, "spark_plugs")
check("last_maintenance_item returns the NEWEST record covering that item",
      last_sp["odometer_km"] == 41000, str(last_sp))

check("last_maintenance_item on an item never recorded returns None",
      service.last_maintenance_item(TEST_VIN, "coolant") is None)

check("last_maintenance_item on an unknown VIN never raises",
      service.last_maintenance_item("NOSUCHVIN0000000", "engine_air_filter") is None)


# --- maintenance_due ---------------------------------------------------------

due = service.maintenance_due(TEST_VIN, current_odometer_km=41500)
by_key = {i["item_key"]: i for i in due["items"]}

check("maintenance_due covers every fixture item",
      set(by_key) == set(FIXTURE_ITEMS), str(set(by_key)))

check("an item with a fully UNKNOWN interval is interval_unknown even though recorded",
      by_key["battery_12v"]["status"] == "interval_unknown", str(by_key["battery_12v"]))

check("an item never recorded, with a known interval, is never_recorded",
      by_key["coolant"]["status"] == "never_recorded", str(by_key["coolant"]))

check("engine_air_filter next-due-km is last odometer + interval_km",
      by_key["engine_air_filter"]["next_due_odometer_km"] == 40000 + 48280,
      str(by_key["engine_air_filter"]))
# last recorded at 40000 km, interval 48280 km -> due at 88280 km; current
# odometer 41500 km is nowhere near due.
check("an item far from its next-due km is ok",
      by_key["engine_air_filter"]["status"] == "ok", str(by_key["engine_air_filter"]))

# spark_plugs last recorded (newest) at 41000 km, interval 96560 km -> due
# at 137560 km -- still "ok" at 41500 current.
check("spark_plugs due status uses the newest record's odometer",
      by_key["spark_plugs"]["next_due_odometer_km"] == 41000 + 96560, str(by_key["spark_plugs"]))

# --- due-soon / overdue by km, on a fresh VIN so the numbers are exact -------

DUE_VIN = "TESTVIN0000MDUE1"
service.record_maintenance(DUE_VIN, {
    "date": "2026-01-01", "odometer_km": 10000, "technician": "Dana",
    "items": [{"item_key": "engine_air_filter", "action": "replaced"}],
})
# interval_km = 48280 -> due at 58280.
due_far = service.maintenance_due(DUE_VIN, current_odometer_km=10100)
check("far from due-by-km is ok",
      {i["item_key"]: i for i in due_far["items"]}["engine_air_filter"]["status"] == "ok")

due_soon = service.maintenance_due(DUE_VIN, current_odometer_km=58280 - 1000)
check("within MAINTENANCE_DUE_SOON_KM of due-by-km is due_soon",
      {i["item_key"]: i for i in due_soon["items"]}["engine_air_filter"]["status"] == "due_soon")

due_over = service.maintenance_due(DUE_VIN, current_odometer_km=58280 + 500)
check("past due-by-km is overdue",
      {i["item_key"]: i for i in due_over["items"]}["engine_air_filter"]["status"] == "overdue")

# --- due-soon / overdue by date ------------------------------------------------
# coolant's fixture interval is 60 months with no km component. Rather than
# approximate month-length in days, use the module's own (calendar-exact)
# _add_months in reverse to pick a recorded date whose +60-months date lands
# exactly where each check needs it.

DATE_VIN = "TESTVIN0000MDUE2"
today = datetime.now().date()
target_due_soon = (today + timedelta(days=20)).isoformat()  # inside the 30-day window
recorded_date = service._add_months(target_due_soon, -60)
service.record_maintenance(DATE_VIN, {
    "date": recorded_date, "odometer_km": 5000, "technician": "Erin",
    "items": [{"item_key": "coolant", "action": "flushed"}],
    "post_service_done": ["Bleed cooling system"],
})
due_date = service.maintenance_due(DATE_VIN)
check("within MAINTENANCE_DUE_SOON_DAYS of due-by-date is due_soon",
      {i["item_key"]: i for i in due_date["items"]}["coolant"]["status"] == "due_soon",
      str(due_date))

OVERDUE_VIN = "TESTVIN0000MDUE3"
target_overdue = (today - timedelta(days=30)).isoformat()  # already passed
recorded_overdue = service._add_months(target_overdue, -60)
service.record_maintenance(OVERDUE_VIN, {
    "date": recorded_overdue, "odometer_km": 5000, "technician": "Frank",
    "items": [{"item_key": "coolant", "action": "flushed"}],
})
due_overdue = service.maintenance_due(OVERDUE_VIN)
check("past due-by-date is overdue",
      {i["item_key"]: i for i in due_overdue["items"]}["coolant"]["status"] == "overdue",
      str(due_overdue))

check("maintenance_due on an unknown VIN never raises and reports never_recorded/interval_unknown",
      all(i["status"] in ("never_recorded", "interval_unknown")
          for i in service.maintenance_due("NOSUCHVIN0000000")["items"]))


# --- amendment (ledger is never rewritten) -------------------------------------

before = service.load(TEST_VIN, "maintenance")
before_count = len(before)
service.amend(TEST_VIN, r1["id"], {"odometer_km": 40010}, note="typo: odometer misread")
after = service.load(TEST_VIN, "maintenance")
amended = next(r for r in after if r["id"] == r1["id"])
check("amendment changes the merged view", amended["data"]["odometer_km"] == 40010)
check("amending does not add or remove records", len(after) == before_count)


# --- real ITEMS (unpatched): interface shape sanity, must never raise -------

_restore_real_items()

check("maintenance_specs.ITEMS is non-empty", len(maintenance_specs.ITEMS) > 0)
check("every real maintenance item has the required keys",
      all(set(maintenance_specs.REQUIRED_KEYS) <= set(row.keys())
          for row in maintenance_specs.ITEMS.values()))
check("every real maintenance item with UNKNOWN interval has None km/miles/months",
      all((row["interval_km"] is None and row["interval_miles"] is None
          and row["interval_months"] is None)
          for row in maintenance_specs.ITEMS.values()
          if row["interval_confidence"] == maintenance_specs.UNKNOWN))

try:
    real_due = service.maintenance_due(VIN)
    real_checklist = service.maintenance_checklist(VIN)
    check("maintenance_due on the real corpus VIN does not raise", True)
    check("maintenance_checklist on the real corpus VIN does not raise", True)
    check("maintenance_checklist groups items by category",
          set(real_checklist["items_by_category"].keys()) == set(maintenance_specs.CATEGORIES))
except Exception as exc:  # noqa: BLE001
    check("maintenance_due/maintenance_checklist on the real corpus VIN does not raise",
          False, repr(exc))

try:
    service.record_maintenance(VIN, {
        "date": "2026-09-26", "odometer_km": 1, "technician": "x",
        "items": [{"item_key": "not-a-real-item", "action": "replaced"}],
    })
    check("an unknown item_key against the real ITEMS is rejected", False)
except ValueError:
    check("an unknown item_key against the real ITEMS is rejected", True)


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
