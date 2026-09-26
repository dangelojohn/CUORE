"""Checks for the compact (default) views of analyze_scan and workup, and for
the vehicle:// resources.

Runs against the real corpus (the Stelvio's history is the fixture, same as
check_workup.py) so the size and content assertions mean something -- a
compact view is only interesting relative to what MES actually logged for
this car.

Same style as the other files in this folder: plain script, ``check()``,
exit 1 on failure.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_compact.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from mes import analysis, compact, scan, workup as workup_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def check_eq(label, got, want):
    check(label, got == want, f"got {got!r} want {want!r}")


def _norm(obj):
    """Round-trip through JSON so tuple/float/etc. differences do not trip
    an equality check that only cares about the JSON actually sent over the
    wire."""
    return json.loads(json.dumps(obj, default=str))


# ===========================================================================
# rebuild the full (detail=True) outputs directly from the library, so the
# tool's detail=True path can be compared against something compaction never
# touched
# ===========================================================================

full_workup_direct = workup_mod.build(vin=VIN)

from mes import catalog as catalog_mod  # noqa: E402
scan_entry = catalog_mod.resolve_or_latest("", kind="scan", vin=VIN)
_scan_log = scan.load_scan(scan_entry.path, timestamp=scan_entry.timestamp)
_full_scan_direct = _scan_log.to_dict()
_by_module = {m.name: m.dtcs for m in _scan_log.modules if m.dtcs}
_event = analysis.detect_network_event(_by_module)
if _event:
    _full_scan_direct["network_event"] = _event.to_dict()
_full_scan_direct["modules_by_priority"] = analysis.module_report(_scan_log.all_dtcs)
if _scan_log.aborted:
    _full_scan_direct["note"] = (
        "Scan aborted before reaching any module - the adapter or vehicle "
        "connection failed. This file cannot be attributed to a vehicle.")


print("=== detail=True is byte-for-byte the old, uncompacted structure ===")
check_eq("workup detail=True matches mes.workup.build directly",
         json.loads(server.workup(vin=VIN, detail=True)), _norm(full_workup_direct))
check_eq("analyze_scan detail=True matches the un-compacted assembly",
         json.loads(server.analyze_scan(vin=VIN, detail=True)), _norm(_full_scan_direct))

print("=== compact workup ===")
compact_workup_raw = server.workup(vin=VIN)  # detail defaults to False
compact_workup_size = len(compact_workup_raw.encode("utf-8"))
d = json.loads(compact_workup_raw)
print(f"  compact workup size: {compact_workup_size} bytes")
check(f"compact workup is under 12 KB ({compact_workup_size} bytes)",
      compact_workup_size < 12_000)

full_chronic = {r["dtc"] for r in full_workup_direct["history"]["chronic"]}
compact_chronic = {r["dtc"] for r in d["history"]["chronic"]}
check("every chronic code from the full dossier survives compaction",
      full_chronic and full_chronic == compact_chronic,
      f"full={full_chronic} compact={compact_chronic}")
check("chronic entries carry the compact fields, not the occurrence list",
      all("occurrences" not in r and "dtc" in r and "sessions" in r
          for r in d["history"]["chronic"]))
check("current_picture DTCs are reduced to dtc/description/status",
      all(set(x) <= {"dtc", "description", "status"}
          for x in d["current_picture"].get("latest_session", {}).get("dtcs", [])))
if d["current_picture"].get("freeze_frames"):
    allowed = set(compact.FREEZE_FRAME_KEYS)
    check("freeze frames are trimmed to the short parameter list",
          all(set(ff) <= allowed for ff in d["current_picture"]["freeze_frames"].values()),
          d["current_picture"]["freeze_frames"])
check("tsb_matches per_code entries are just bulletin + title",
      all(set(b) == {"bulletin", "title"}
          for bullets in d["tsb_matches"]["per_code"].values() for b in bullets))
check("already_attempted is grouped, not one row per run",
      len(d["already_attempted"]) <= len(full_workup_direct["already_attempted"]))
check("already_attempted groups carry kind/operation/outcome/count/first/last",
      all(set(g) == {"kind", "operation", "outcome", "count", "first", "last"}
          for g in d["already_attempted"]))
check("blind_spots pass through unchanged",
      d["blind_spots"] == full_workup_direct["blind_spots"])

print("=== compact scan ===")
compact_scan_raw = server.analyze_scan(vin=VIN)  # detail defaults to False
compact_scan_size = len(compact_scan_raw.encode("utf-8"))
sd = json.loads(compact_scan_raw)
print(f"  compact scan size: {compact_scan_size} bytes "
      f"(full: {len(json.dumps(_norm(_full_scan_direct)).encode('utf-8'))} bytes)")
listed_with_codes = {m["module"] for m in sd["modules"]}
listed_clean = set(sd["clean_modules"])
check("no module is listed twice (with-codes vs. clean are disjoint)",
      listed_with_codes.isdisjoint(listed_clean),
      listed_with_codes & listed_clean)
full_with_codes = {m["module"] for m in _full_scan_direct["modules"] if m["dtcs"]}
full_clean = {m["module"] for m in _full_scan_direct["modules"] if not m["dtcs"]}
check_eq("every module with codes in the full scan is listed exactly once, compact",
         listed_with_codes, full_with_codes)
check_eq("every clean module in the full scan is named exactly once, compact",
         listed_clean, full_clean)
check("compact scan modules carry only module/ecu/dtcs",
      all(set(m) == {"module", "ecu", "dtcs"} for m in sd["modules"]))
check("compact scan DTCs are reduced to dtc/description/status",
      all(set(x) <= {"dtc", "description", "status"}
          for m in sd["modules"] for x in m["dtcs"]))
if "clear_results" in sd:
    check("clear_results is a flat {module: result} map",
          all(isinstance(v, str) for v in sd["clear_results"].values()))
if "priority" in sd:
    check("priority is a bare ordered name list",
          all(isinstance(x, str) for x in sd["priority"]))

print("=== vehicle:// resources ===")
resources = server.mcp._resource_manager.list_resources()
templates = server.mcp._resource_manager.list_templates()
check("vehicle://index is a registered static resource",
      any(str(r.uri) == "vehicle://index" for r in resources),
      [str(r.uri) for r in resources])
check("vehicle://{vin}/dossier is a registered resource template",
      any(t.uri_template == "vehicle://{vin}/dossier" for t in templates),
      [t.uri_template for t in templates])

index = json.loads(server.vehicle_index())
check("vehicle index lists this VIN",
      any(v.get("vin") == VIN for v in index.get("vehicles") or []),
      [v.get("vin") for v in index.get("vehicles") or []])

dossier = json.loads(server.vehicle_dossier(VIN))
check_eq("the dossier resource matches the compact workup tool",
         dossier, d)

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("all checks passed")
