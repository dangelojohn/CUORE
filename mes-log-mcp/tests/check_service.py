"""Smoke checks for mes.service / mes.service_specs.

No mocks, no real corpus needed for the ledger itself -- CUORE_STATE_DIR is
pointed at a fresh tempdir BEFORE anything is imported, so this never
touches the real state directory. next_oil_change's MES-corroboration path
is exercised against whatever the real corpus does or doesn't have (it must
never raise either way); everything else uses a synthetic VIN.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_service.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-service-")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mes import service, service_specs  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio this toolchain already knows about

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- service_specs: shape and honesty rules ---------------------------------

check("CATEGORIES is non-empty", len(service_specs.CATEGORIES) > 0)
check("every category has a label",
      all(c in service_specs.CATEGORY_LABELS for c in service_specs.CATEGORIES))
check("oil_change torques include drain_plug and filter_cap",
      {"drain_plug", "filter_cap"} <= {t["key"] for t in
      service_specs.torques_for_category("oil_change")})
check("every torque row has a confidence in the known set",
      all(t["confidence"] in service_specs.CONFIDENCE_LEVELS
          for t in service_specs.TORQUES))
check("every UNKNOWN torque has value None (never invented)",
      all(t["value"] is None for t in service_specs.TORQUES
          if t["confidence"] == service_specs.UNKNOWN))
check("every UNKNOWN torque points at TechAuthority",
      all(service_specs.TECHAUTHORITY in t["notes"] for t in service_specs.TORQUES
          if t["confidence"] == service_specs.UNKNOWN))
check("checklist_for accepts a single category",
      len(service_specs.checklist_for("oil_change")) ==
      len(service_specs.torques_for_category("oil_change")))
check("checklist_for accepts a list and de-duplicates",
      len(service_specs.checklist_for(["oil_change", "wheels"])) ==
      len(service_specs.torques_for_categories(["oil_change", "wheels"])))
check("search_torques never drops UNKNOWN rows",
      any(t["confidence"] == service_specs.UNKNOWN
          for t in service_specs.search_torques(category="suspension")))
check("search_torques text search matches on component name",
      any("spark plug" in t["component"].lower()
          for t in service_specs.search_torques(q="spark")))
check("BRAKE_SPEC has pad_min_mm and tire_pressure_kpa",
      "pad_min_mm" in service_specs.BRAKE_SPEC and
      "tire_pressure_kpa" in service_specs.BRAKE_SPEC)
check("oil_change_specs bundles oil/filters/interval/torques",
      {"oil", "filters", "drain_plug", "drain_plug_washer", "interval", "torques"} <=
      set(service_specs.oil_change_specs().keys()))
check("brake_wheel_tire_specs bundles brake/tpms/torques",
      {"brake", "tpms", "torques"} <= set(service_specs.brake_wheel_tire_specs().keys()))


# --- mes.service: validation ------------------------------------------------

try:
    service.record_oil_change(VIN, {})
    check("empty oil_change data is rejected", False)
except ValueError:
    check("empty oil_change data is rejected", True)

try:
    service.record_oil_change("", {"date": "2026-01-01", "odometer_km": 1,
                                   "oil": {"brand": "x", "viscosity": "x"},
                                   "quantity_added_l": 1,
                                   "filter": {"part_no": "x"}, "technician": "x"})
    check("missing vin is rejected", False)
except ValueError:
    check("missing vin is rejected", True)

try:
    service.record_service(VIN, {"date": "2026-01-01", "odometer_km": 1,
                                 "category": "not-a-real-category",
                                 "work_done": "x", "technician": "x"})
    check("bad category is rejected", False)
except ValueError as exc:
    check("bad category is rejected", True, str(exc))


# --- mes.service: record / load / torque checklist --------------------------

TEST_VIN = "TESTVIN00000SVC1"

r1 = service.record_oil_change(TEST_VIN, {
    "date": "2026-09-01", "odometer_km": 40000,
    "oil": {"brand": "Mopar", "viscosity": "0W-30", "spec": "MS-13340"},
    "quantity_added_l": 5.2,
    "filter": {"brand": "Mopar", "part_no": "4892339BE"},
    "torques_applied": {"drain_plug": 20, "filter_cap": 25, "wheel_lug": 121,
                        "spark_plug": 19.5},
    "technician": "Alice",
    "considerations_next": ["watch for a slow oil weep at the pan", "check PCV"],
})
check("record_oil_change returns an id", bool(r1.get("id")))
flags1 = r1["data"]["torque_checklist"]["flags"]
# "undertray" is genuinely UNKNOWN in service_specs (no sourced torque) and
# is part of the oil_change checklist, so it is *expected* to always carry
# a flag (missing, here, since it was not supplied) -- the honest-data
# equivalent of "no flags" is "no flag other than the UNKNOWN-spec one".
check("every correctly-applied, sourced torque produces no flag",
      all(f.split(":")[0] == "Undertray / belly-pan / splash-shield fasteners"
          for f in flags1),
      str(flags1))

check("considerations from the last oil change are carried forward",
      "watch for a slow oil weep at the pan" in
      service.oil_change_checklist(TEST_VIN)["carried_forward_considerations"])

r2 = service.record_oil_change(TEST_VIN, {
    "date": "2026-09-15", "odometer_km": 48000,
    "oil": {"brand": "Mopar", "viscosity": "0W-30"},
    "quantity_added_l": 5.2,
    "filter": {"brand": "Mopar", "part_no": "4892339BE"},
    "torques_applied": {"drain_plug": 999, "wheel_lug": 121, "undertray": 5},
    "technician": "Bob",
})
flags2 = r2["data"]["torque_checklist"]["flags"]
check("an out-of-spec torque is flagged deviating",
      any("outside spec" in f for f in flags2), str(flags2))
check("a missing torque is flagged missing",
      any("no torque value recorded" in f for f in flags2), str(flags2))
check("an UNKNOWN-spec torque, when applied, is flagged unknown_spec",
      any("UNKNOWN spec" in f for f in flags2), str(flags2))

last = service.last_oil_change(TEST_VIN)
check("last_oil_change returns the newest record", last["data"]["odometer_km"] == 48000)

records = service.load(TEST_VIN, "oil_change")
check("load returns both oil_change records", len(records) == 2)

# --- ledger amendment: history is never rewritten ---------------------------

before = service.load(TEST_VIN, "oil_change")
before_raw_count = len(before)
service.amend(TEST_VIN, r1["id"], {"odometer_km": 40010}, note="typo: odometer misread")
after = service.load(TEST_VIN, "oil_change")
amended = next(r for r in after if r["id"] == r1["id"])
check("amendment changes the merged view", amended["data"]["odometer_km"] == 40010)
check("amendment keeps the amendment trail", len(amended.get("amendments", [])) == 1)
check("amending does not add or remove records", len(after) == before_raw_count)
# the underlying store must still contain the ORIGINAL value on its own line
raw_lines = service.store_path().read_text(encoding="utf-8").splitlines()
import json as _json
original_line = next(_json.loads(l) for l in raw_lines
                     if _json.loads(l).get("id") == r1["id"] and _json.loads(l).get("op") == "record")
check("the original record line is untouched by the amendment",
      original_line["data"]["odometer_km"] == 40000)

# --- next oil change ---------------------------------------------------------

nxt = service.next_oil_change(TEST_VIN)
check("next_oil_change is known once a change is on record", nxt["known"] is True)
check("next_oil_change adds the interval in km to the last odometer",
      nxt["next_due_odometer_km"] == 48000 + service_specs.SERVICE_INTERVAL["km"])

empty_vin_next = service.next_oil_change("NOSUCHVIN0000000")
check("next_oil_change on an unknown vehicle never raises",
      empty_vin_next["known"] is False)

# next_oil_change / oil_change_checklist against the real corpus VIN must
# never raise, whatever the corpus does or doesn't contain for it.
try:
    real_next = service.next_oil_change(VIN)
    real_checklist = service.oil_change_checklist(VIN)
    check("next_oil_change on the real corpus VIN does not raise", True)
    check("oil_change_checklist on the real corpus VIN does not raise", True)
    check("oil_change_checklist carries specs with sources",
          "oil" in real_checklist["specs"])
except Exception as exc:  # noqa: BLE001
    check("next_oil_change/oil_change_checklist on the real corpus VIN does not raise",
          False, repr(exc))

checklist = service.oil_change_checklist(TEST_VIN)
check("carried-forward considerations track the NEWEST oil change, not an "
      "older one (r2 supplied none, so the list is now empty)",
      checklist["carried_forward_considerations"] == [])


# --- general service ----------------------------------------------------------

sr = service.record_service(TEST_VIN, {
    "date": "2026-09-20", "odometer_km": 48500, "category": "suspension",
    "work_done": "replaced front sway bar end links",
    "parts": [{"name": "sway bar end link", "part_no": "68245678AA", "qty": 2}],
    "torques_applied": {},
    "technician": "Carol",
})
check("record_service returns an id", bool(sr.get("id")))
check("service torque checklist flags every suspension fastener as missing "
      "when nothing was applied",
      len(sr["data"]["torque_checklist"]["flags"]) ==
      len(service_specs.torques_for_category("suspension")))


# --- brakes / wheels / tyres --------------------------------------------------

bwt = service.record_brakes_wheels_tires(TEST_VIN, {
    "date": "2026-09-22", "odometer_km": 49000, "technician": "Dave",
    "corners": {
        # FL: front rotor minimum IS sourced (25.5 mm) -- 24.0 mm must flag.
        "FL": {"pad_thickness_mm": {"inner": 6.0, "outer": 6.2},
              "rotor_thickness_mm": 24.0,
              "tread_depth_mm": {"inside": 6.0, "middle": 6.1, "outside": 6.0},
              "pressure_set_kpa": 207},
        # RL: rear rotor minimum is UNKNOWN -- this exercises the "recorded,
        # but no sourced minimum to check it against" branch instead.
        "RL": {"pad_thickness_mm": {"inner": 1.5, "outer": 1.6},
              "rotor_thickness_mm": 20.0,
              "tread_depth_mm": {"inside": 1.0, "middle": 3.0, "outside": 5.0},
              "pressure_set_kpa": 300},
    },
    "torques_applied": {"wheel_lug": 121},
})
check("record_brakes_wheels_tires returns an id", bool(bwt.get("id")))
flags3 = bwt["data"]["flags"]
check("a rotor below the sourced (front) minimum is flagged",
      any("FL rotor" in f and "below" in f for f in flags3), str(flags3))
check("a rotor with no sourced (rear) minimum is flagged as unchecked, "
      "not silently passed",
      any("RL rotor" in f and "no sourced minimum" in f for f in flags3), str(flags3))
check("tread below the legal minimum is flagged",
      any("below legal minimum" in f for f in flags3), str(flags3))
check("uneven tread wear (inside vs outside) is flagged",
      any("uneven wear" in f for f in flags3), str(flags3))
check("a pressure deviation from the placard target is flagged",
      any("deviates from placard target" in f for f in flags3), str(flags3))
check("tread_depth_32nds is computed alongside mm",
      bwt["data"]["corners"]["RL"]["tread_depth_32nds"]["inside"] is not None)

bchk = service.brakes_wheels_tires_checklist(TEST_VIN)
check("brakes_wheels_tires_checklist returns specs with brake/tpms/torques",
      {"brake", "tpms", "torques"} <= set(bchk["specs"].keys()))
check("brakes_wheels_tires_checklist torque checklist covers brakes+wheels",
      any(t["key"] == "wheel_lug" for t in bchk["torque_checklist"]))


# --- drivetrain ---------------------------------------------------------------

from mes import drivetrain_specs  # noqa: E402

check("DRIVETRAIN_SECTIONS matches drivetrain_specs.SECTIONS keys",
      set(service.DRIVETRAIN_SECTIONS) == set(drivetrain_specs.SECTIONS.keys()))

try:
    service.record_drivetrain(TEST_VIN, {"date": "2026-09-25", "odometer_km": 1,
                                         "job": "x", "technician": "x"})
    check("drivetrain with no section is rejected", False)
except ValueError:
    check("drivetrain with no section is rejected", True)

try:
    service.record_drivetrain(TEST_VIN, {"date": "2026-09-25", "odometer_km": 1,
                                         "section": "not-a-real-section",
                                         "job": "x", "technician": "x"})
    check("bad drivetrain section is rejected", False)
except ValueError as exc:
    check("bad drivetrain section is rejected", True, str(exc))

try:
    service.record_drivetrain(TEST_VIN, {"date": "2026-09-25", "odometer_km": 1,
                                         "section": "transmission",
                                         "job": "not-a-real-job", "technician": "x"})
    check("a job not belonging to the section is rejected", False)
except ValueError as exc:
    check("a job not belonging to the section is rejected", True, str(exc))

# transmission fluid temp inside the 30-50 C window: no window flag
dt_ok = service.record_drivetrain(TEST_VIN, {
    "date": "2026-09-25", "odometer_km": 51000, "technician": "Erin",
    "section": "transmission", "job": "transmission_fluid_service",
    "fluid": {"brand": "Mopar", "part_no": "68218925AA"},
    "quantity_drained_l": 9.0, "quantity_added_l": 9.2,
    "fluid_condition": {"color": "red", "smell": "normal"},
    "fluid_temp_c": 40,
    "adaptation_relearn": {"done": False},
    "torques_applied": {"transmission_pan_bolts": 10},
})
check("a fluid temp inside the 30-50 C window raises no window flag",
      dt_ok["data"]["fill_window_flag"] is None, str(dt_ok["data"]["fill_window_flag"]))
check("transmission torque checklist honours a correctly-applied CONFIRMED spec",
      not any(r["flag"] for r in dt_ok["data"]["torque_checklist"]["rows"]
              if r["key"] == "transmission_pan_bolts"))

# transmission fluid temp outside the window: flagged
dt_hot = service.record_drivetrain(TEST_VIN, {
    "date": "2026-09-26", "odometer_km": 51500, "technician": "Erin",
    "section": "transmission", "job": "transmission_fluid_service",
    "fluid": {"brand": "Mopar"}, "fluid_temp_c": 70,
})
check("a fluid temp outside the 30-50 C window is flagged",
      dt_hot["data"]["fill_window_flag"] is not None
      and "outside the 30-50" in dt_hot["data"]["fill_window_flag"])
check("the fill-window flag is folded into data.flags",
      dt_hot["data"]["fill_window_flag"] in dt_hot["data"]["flags"])

# a non-transmission section never gets the fill-window check even if given a temp
dt_diff = service.record_drivetrain(TEST_VIN, {
    "date": "2026-09-26", "odometer_km": 51600, "technician": "Frank",
    "section": "differentials", "job": "differential_service_rear",
    "fluid": {"brand": "Petronas"}, "fluid_temp_c": 90,
    "torques_applied": {"rear_diff_fill_plug": 26},
})
check("fluid temp outside 30-50 on a non-transmission section is not flagged",
      dt_diff["data"]["fill_window_flag"] is None)

# torque checklist for a job comes from mes.drivetrain_specs's own JOBS/TORQUES
rows = service.build_drivetrain_torque_checklist("transmission", "transmission_fluid_service")
check("build_drivetrain_torque_checklist includes the job's torque_ref rows",
      any(r["key"] == "transmission_pan_bolts" for r in rows))
check("build_drivetrain_torque_checklist de-duplicates torque_ref keys",
      len(rows) == len({r["key"] for r in rows}))

dt_missing = service.record_drivetrain(TEST_VIN, {
    "date": "2026-09-26", "odometer_km": 51700, "technician": "Grace",
    "section": "transmission", "job": "transmission_fluid_service",
    "fluid": {}, "torques_applied": {},
})
check("a missing torque on a drivetrain job is flagged missing",
      any("no torque value recorded" in f for f in dt_missing["data"]["torque_checklist"]["flags"]))

check("last_drivetrain returns the newest record for that section",
      service.last_drivetrain(TEST_VIN, "transmission")["id"] == dt_missing["id"])
check("drivetrain_history only returns records for the requested section",
      all(e["data"]["section"] == "transmission"
          for e in service.drivetrain_history(TEST_VIN, "transmission")))

dchk = service.drivetrain_section_checklist(TEST_VIN, "transmission")
check("drivetrain_section_checklist bundles specs/jobs/history",
      {"specs", "jobs", "history", "last_service"} <= set(dchk.keys()))
check("drivetrain_section_checklist specs match drivetrain_specs.SECTIONS",
      dchk["specs"] is drivetrain_specs.SECTIONS["transmission"])

try:
    service.drivetrain_section_checklist(TEST_VIN, "not-a-real-section")
    check("drivetrain_section_checklist rejects an unknown section", False)
except ValueError:
    check("drivetrain_section_checklist rejects an unknown section", True)

# differentials section checklist exposes separate front/rear sub-sections
diff_chk = service.drivetrain_section_checklist(TEST_VIN, "differentials")
check("differentials checklist exposes front and rear sub-sections",
      "front" in diff_chk["specs"] and "rear" in diff_chk["specs"])


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
# --- regression 2026-09-26: month arithmetic never yields impossible dates ----
from mes.service import _add_months as _am  # noqa: E402
for _src, _n, _want in (("2026-01-31", 1, "2026-02-28"), ("2024-01-31", 1, "2024-02-29"),
                         ("2025-12-31", 2, "2026-02-28"), ("2026-08-31", 6, "2027-02-28"),
                         ("2026-09-15", 12, "2027-09-15"), ("2026-03-31", 1, "2026-04-30")):
    check(f"_add_months({_src}, {_n}) == {_want}", _am(_src, _n) == _want, str(_am(_src, _n)))

print("OK")
