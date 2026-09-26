"""Smoke checks for mes.maintenance_specs.

Plain script style, like check_service.py: no test framework, no corpus/state
dependency -- this module is pure data plus a couple of lookup functions.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_maintenance_specs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mes import maintenance_specs as m  # noqa: E402
from mes import service_specs  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


REQUIRED_KEYS = set(m.REQUIRED_KEYS)
TORQUE_KEYS = {t["key"] for t in service_specs.TORQUES}


# --- shape: item() / items_by_category() -------------------------------------

check("ITEM_ORDER has the 17 specified keys, in order",
      list(m.ITEM_ORDER) == [
          "engine_air_filter", "cabin_air_filter", "spark_plugs",
          "ignition_coils_inspect", "coolant", "brake_fluid", "drive_belt",
          "battery_12v", "wipers", "fuel_filter", "pcv_system",
          "throttle_body_clean", "intake_boost_hoses_inspect",
          "washer_fluid", "a_c_cabin_service", "power_steering",
          "hood_and_door_lubrication",
      ], list(m.ITEM_ORDER))

check("ITEMS has exactly one entry per ITEM_ORDER key",
      set(m.ITEMS.keys()) == set(m.ITEM_ORDER),
      str(set(m.ITEMS.keys()) ^ set(m.ITEM_ORDER)))

try:
    m.item("not-a-real-item")
    check("item() raises KeyError on an unknown key", False)
except KeyError:
    check("item() raises KeyError on an unknown key", True)

by_cat = m.items_by_category()
check("items_by_category covers every declared category",
      set(by_cat.keys()) == set(m.CATEGORIES))
check("items_by_category is a partition -- every item appears exactly once "
      "total",
      sum(len(v) for v in by_cat.values()) == len(m.ITEM_ORDER))
for cat, rows in by_cat.items():
    for row in rows:
        check(f"items_by_category['{cat}'] rows are actually tagged {cat}",
              row["category"] == cat, row["key"])


# --- per-item structural + honesty invariants --------------------------------

for key in m.ITEM_ORDER:
    it = m.item(key)

    check(f"{key}: has exactly the required keys, no more/fewer",
          set(it.keys()) == REQUIRED_KEYS,
          str(set(it.keys()) ^ REQUIRED_KEYS))
    check(f"{key}: key field matches its ITEMS key", it["key"] == key)
    check(f"{key}: category is one of the declared categories",
          it["category"] in m.CATEGORIES, it["category"])
    check(f"{key}: interval_confidence is a known confidence level",
          it["interval_confidence"] in m.CONFIDENCE_LEVELS,
          it["interval_confidence"])

    # UNKNOWN interval must point at the service manual.
    if it["interval_confidence"] == m.UNKNOWN:
        check(f"{key}: UNKNOWN interval_confidence carries the "
              "TechAuthority pointer in interval_note",
              m.TECHAUTHORITY in it["interval_note"], it["interval_note"])

    # Any non-None interval value must be backed by a source and a real
    # (non-UNKNOWN) confidence -- never a bare number floating unsourced.
    interval_values_given = any(
        it[f] is not None
        for f in ("interval_miles", "interval_km", "interval_months")
    )
    if interval_values_given:
        check(f"{key}: a stated interval value has a non-UNKNOWN confidence",
              it["interval_confidence"] != m.UNKNOWN)
        check(f"{key}: a stated interval value has a source",
              it["interval_source"] is not None)

    # parts: each entry internally consistent.
    check(f"{key}: parts is a list", isinstance(it["parts"], list))
    for i, p in enumerate(it["parts"]):
        label = f"{key}.parts[{i}]"
        check(f"{label}: confidence is a known level",
              p["confidence"] in m.CONFIDENCE_LEVELS, p["confidence"])
        if p["confidence"] == m.UNKNOWN:
            check(f"{label}: UNKNOWN part carries the TechAuthority pointer",
                  m.TECHAUTHORITY in p["notes"], p["notes"])
        if p["part_number"] is not None:
            check(f"{label}: a stated part_number has a non-UNKNOWN "
                  "confidence", p["confidence"] != m.UNKNOWN)
            check(f"{label}: a stated part_number has a source",
                  p["source"] is not None)

    # fluid: None, or internally consistent.
    if it["fluid"] is not None:
        f = it["fluid"]
        label = f"{key}.fluid"
        check(f"{label}: confidence is a known level",
              f["confidence"] in m.CONFIDENCE_LEVELS, f["confidence"])
        if f["confidence"] == m.UNKNOWN:
            check(f"{label}: UNKNOWN fluid carries the TechAuthority "
                  "pointer", m.TECHAUTHORITY in f["notes"], f["notes"])
        if f["spec"] is not None or f["capacity"] is not None:
            check(f"{label}: a stated spec/capacity has a non-UNKNOWN "
                  "confidence", f["confidence"] != m.UNKNOWN)
            check(f"{label}: a stated spec/capacity has a source",
                  f["source"] is not None)

    # torque_keys must resolve into mes.service_specs's own torque table --
    # this module never duplicates a torque value, only points at one.
    check(f"{key}: torque_keys is a list", isinstance(it["torque_keys"], list))
    for tk in it["torque_keys"]:
        check(f"{key}: torque_key {tk!r} exists in mes.service_specs.TORQUES",
              tk in TORQUE_KEYS, tk)

    for field in ("procedure", "checks", "post_service"):
        check(f"{key}.{field} is a list", isinstance(it[field], list))
        check(f"{key}.{field} entries are all strings",
              all(isinstance(x, str) for x in it[field]))

    check(f"{key}.notes is a string", isinstance(it["notes"], str))
    check(f"{key}.label is a non-empty string",
          isinstance(it["label"], str) and bool(it["label"]))


# --- spot-checks on the most load-bearing, best-sourced rows ------------------

sp = m.item("spark_plugs")
check("spark_plugs reuses the existing service_specs torque key rather than "
      "duplicating a value",
      sp["torque_keys"] == ["spark_plug"])
check("spark_plugs interval is CONFIRMED (owner's manual)",
      sp["interval_confidence"] == m.CONFIRMED)
check("spark_plugs interval is mileage-only (owner's manual says yearly "
      "intervals do not apply)",
      sp["interval_miles"] == 30000 and sp["interval_months"] is None)

coolant = m.item("coolant")
check("coolant fluid capacity is CONFIRMED from the owner's manual",
      coolant["fluid"]["confidence"] == m.CONFIRMED
      and coolant["fluid"]["capacity"] == 8.8)

brake_fluid = m.item("brake_fluid")
check("brake_fluid interval is calendar-only (no mileage figure)",
      brake_fluid["interval_miles"] is None
      and brake_fluid["interval_months"] == 24
      and brake_fluid["interval_confidence"] == m.CONFIRMED)

power_steering = m.item("power_steering")
check("power_steering correctly records there is no serviceable fluid",
      power_steering["fluid"] is None)

battery = m.item("battery_12v")
check("battery_12v reuses both existing service_specs torque keys",
      set(battery["torque_keys"]) == {"battery_terminal", "battery_hold_down"})

fuel_filter = m.item("fuel_filter")
check("fuel_filter records no serviceable-on-schedule filter (lifetime "
      "in-tank unit)",
      fuel_filter["interval_miles"] is None
      and fuel_filter["interval_confidence"] != m.UNKNOWN)


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
