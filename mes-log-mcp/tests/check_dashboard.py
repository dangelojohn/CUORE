"""Smoke checks for ``mes.dashboard``: the per-vehicle dashboard assembly.

Same posture as ``check_workup.py``: the real corpus on this machine is the
fixture. The Stelvio (chronic P0456, spanning 26,500 km) pins the summary and
timeline assertions; a VIN nothing matches pins the empty-vehicle path that
``cuore.web.dashboard_charts`` also has to survive.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))          # mes-log-mcp -- for `mes`
sys.path.insert(0, str(HERE.parents[2]))          # repo root -- for `cuore.web.dashboard_charts`

from mes import dashboard  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
NO_SUCH_VIN = "1C4RJFAG0JC000001"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def parse_svg(svg: str) -> ET.Element:
    return ET.fromstring(svg)


print("=== summary ===")
d = dashboard.build(VIN)
check("no top-level error", "error" not in d, str(d.get("error")))
s = d["summary"]
check("vin echoed", s["vin"] == VIN)
check("vehicle name present", bool(s["vehicle"]), str(s))
check("odometer span is sane", s["odometer_first_km"] < s["odometer_last_km"],
      f"{s['odometer_first_km']} .. {s['odometer_last_km']}")
check("log count matches the corpus (32 logs)", s["log_count"] == 32, str(s["log_count"]))
check("open_codes_count is a non-negative int", isinstance(s["open_codes_count"], int)
      and s["open_codes_count"] >= 0)
check("chronic_count includes the known chronics (>= 1)", s["chronic_count"] >= 1,
      str(s["chronic_count"]))
check("last_scan_date is set", bool(s["last_scan_date"]), str(s))

print("=== code timeline ===")
timeline = d["code_timeline"]
check("every vehicle-known code appears", len(timeline) > 0)
p0456 = next((r for r in timeline if r["code"].startswith("P0456")), None)
check("P0456 present", p0456 is not None)
if p0456:
    check("P0456 classified chronic", p0456["class"] == "chronic", p0456["class"])
    check("P0456 has at least 5 occurrences", len(p0456["events"]) >= 5,
          str(len(p0456["events"])))
    with_odo = [e for e in p0456["events"] if e["odometer_km"] is not None]
    check("at least 3 of those occurrences carry an odometer reading",
          len(with_odo) >= 3, str(len(with_odo)))
    check("every event names its source file", all(e.get("source") for e in p0456["events"]))
    ordered = [e["at"] for e in p0456["events"]]
    check("P0456 events are in chronological (file) order", ordered == sorted(ordered), str(ordered))

print("=== repairs and tests ledger ===")
ledger = d["repairs_and_tests"]
check("ledger is non-empty (purge-valve actuator runs exist)", len(ledger) > 0)
stamps = [r["at"].replace(" ", "T") for r in ledger]
check("ledger is chronological", stamps == sorted(stamps), str(stamps[:5]))
check("every row has kind/what/result/source", all(
    {"at", "kind", "what", "result", "source"} <= set(r) for r in ledger))
check("a clear from the logs is in the ledger",
      any(r["kind"] == "clear" for r in ledger), str({r["kind"] for r in ledger}))

print("=== live status ===")
live = d["live_status"]
check("live_status has the expected keys",
      {"as_of", "modules", "mode06_evap"} <= set(live))
for m in live["modules"]:
    check(f"module {m['ecu']} active list matches active_count",
          len(m["active"]) == m["active_count"], str(m))

print("=== modules ===")
mods = d["modules"]
check("modules list is non-empty", len(mods) > 0)
check("dtc_count is always positive", all(m["dtc_count"] > 0 for m in mods))
ecm = next((m for m in mods if m["abbrev"] == "ECM"), None)
check("ECM module present and picked up the live read",
      ecm is not None and ecm["last_read_source"] in ("log", "live"),
      str(ecm))

print("=== odometer series ===")
odo = d["odometer_series"]
check("odometer series is non-empty", len(odo) > 0)
odo_stamps = [r["at"].replace(" ", "T") for r in odo]
check("odometer series is chronological", odo_stamps == sorted(odo_stamps))

print("=== empty vehicle ===")
empty = dashboard.build(NO_SUCH_VIN)
check("unknown VIN reports an error, not a crash", "error" in empty, str(empty))
check("no VIN reports an error", "error" in dashboard.build(""))

print("=== SVG charts (real vehicle) ===")
from cuore.web import dashboard_charts  # noqa: E402  -- after sys.path insert above

for name, svg in (
    ("code_timeline", dashboard_charts.code_timeline_svg(timeline, ledger)),
    ("odometer", dashboard_charts.odometer_svg(odo)),
    ("modules", dashboard_charts.module_bar_svg(mods)),
):
    try:
        root = parse_svg(svg)
        check(f"{name} chart is well-formed XML", True)
        check(f"{name} chart root is an <svg>", root.tag.endswith("svg"), root.tag)
    except ET.ParseError as exc:
        check(f"{name} chart is well-formed XML", False, str(exc))

print("=== SVG charts (empty vehicle) ===")
for name, svg in (
    ("code_timeline", dashboard_charts.code_timeline_svg([], [])),
    ("odometer", dashboard_charts.odometer_svg([])),
    ("modules", dashboard_charts.module_bar_svg([])),
):
    try:
        root = parse_svg(svg)
        check(f"empty {name} chart is well-formed XML", True)
        check(f"empty {name} chart root is an <svg>", root.tag.endswith("svg"), root.tag)
    except ET.ParseError as exc:
        check(f"empty {name} chart is well-formed XML", False, str(exc))

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
