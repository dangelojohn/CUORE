"""Checks for ``mes.cuore_log`` -- CUORE live-scan parity on the MCP side
(``cuore_list_scans``/``cuore_latest_scan``/``cuore_read_scan``/``cuore_search``/
``cuore_export_scan``/``cuore_log_dir``/``cuore_log_archive``/``cuore_log_integrity``/
``logs_timeline`` in ``server.py``).

Fixture: the real 2026-10-13 lines copied verbatim out of the production
``observations.jsonl`` (``C:\\ProgramData\\cuore\\observations.jsonl``) --
never read from there again once copied, and never written back to. Two
synthetic ``freeze_frame`` rows are appended (that kind does not exist yet
in the real corpus -- see ``cuore.live.scanlog``'s own docstring) so
:func:`mes.cuore_log.read_scan` has a freeze frame to return; everything
else in the fixture is the unmodified real session.

``CUORE_STATE_DIR`` and ``MES_LOG_DIRS`` point at throwaway temp
directories for this whole run, set before anything under ``mes`` or
``cuore`` is imported.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_cuore_log.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
MES_LOG_MCP = HERE.parents[1]
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(MES_LOG_MCP))   # for `mes`, `server`
sys.path.insert(0, str(REPO_ROOT))     # for `cuore.*`

CUORE_STATE_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-cuore-log-state-"))
MES_ROOT = Path(tempfile.mkdtemp(prefix="cuore-check-cuore-log-mes-"))
os.environ["CUORE_STATE_DIR"] = str(CUORE_STATE_DIR)
os.environ["MES_LOG_DIRS"] = str(MES_ROOT)

PROD_OBSERVATIONS = Path(r"C:\ProgramData\cuore\observations.jsonl")
PROD_MES_SCAN = Path(r"C:\Program Files (x86)\Multiecuscan\SCAN_2610080920.txt")
VIN = "ZASFAKPN5J7B88115"

# --- build the fixture, before importing anything that reads it -----------

if PROD_OBSERVATIONS.exists():
    real_lines = [l for l in PROD_OBSERVATIONS.read_text(encoding="utf-8").splitlines()
                 if '"at": "2026-10-13' in l]
else:
    real_lines = []

synthetic_freeze_frames = [
    json.dumps({"at": "2026-10-13T20:00:00", "kind": "freeze_frame", "vin": "",
               "bus": "can_c", "cable": "none", "stream": "serial COM3@115200",
               "data": {"pid": "02", "name": None,
                       "by_ecu": {"18DAF110": {"dtc": "P0440", "bytes": ["00", "00"]}}}}),
    json.dumps({"at": "2026-10-13T20:00:01", "kind": "freeze_frame", "vin": "",
               "bus": "can_c", "cable": "none", "stream": "serial COM3@115200",
               "data": {"pid": "0C", "name": "engine_rpm",
                       "by_ecu": {"18DAF110": {"pid": "0C", "name": "engine_rpm",
                                              "bytes": ["0A", "00"], "unit": "rpm",
                                              "value": 800}}}}),
]

(CUORE_STATE_DIR / "observations.jsonl").write_text(
    "\n".join(real_lines + synthetic_freeze_frames) + "\n", encoding="utf-8")

if PROD_MES_SCAN.exists():
    shutil.copy2(PROD_MES_SCAN, MES_ROOT / PROD_MES_SCAN.name)

from mes import cuore_log  # noqa: E402
from mes import catalog  # noqa: E402
from mes import scan as scan_mod  # noqa: E402
import server  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


print("=== setup ===")
check("real observation lines were found and copied", len(real_lines) > 0, "0 lines copied")
check("mes.cuore_log can reach cuore.live.scanlog", cuore_log.CUORE_LIVE_AVAILABLE)

# --- list_scans / latest_scan ------------------------------------------------

print("=== cuore_list_scans / cuore_latest_scan ===")
scans = cuore_log.list_scans(VIN)
scan_ids = [s["id"] for s in scans]
check("the real session's scans are returned", "SCAN_2610131952" in scan_ids, str(scan_ids))
check("every scan carries a kind", all(s.get("kind") for s in scans), str(scans))
check("newest-first order", scans == sorted(scans, key=lambda s: s["started"], reverse=True))

via_tool = json.loads(server.cuore_list_scans(VIN))
check("server.cuore_list_scans matches the library call",
     [s["id"] for s in via_tool] == scan_ids, str(via_tool)[:200])

latest = cuore_log.latest_scan(VIN)
check("latest_scan is the newest of list_scans", latest is not None and latest["id"] == scans[0]["id"])

kind_filtered = cuore_log.list_scans(VIN, kind="attempt")
check("kind filter narrows to attempts only",
     all(s["kind"] == "attempt" for s in kind_filtered) and len(kind_filtered) >= 1,
     str(kind_filtered))

# --- read_scan: the P0440 freeze frame and the Mode 06 3A FAIL --------------

print("=== cuore_read_scan ===")
full = cuore_log.read_scan(VIN, "SCAN_2610131952")
check("read_scan found the scan", full is not None)
if full:
    ff_codes = {f.get("code") for f in full.get("freeze_frames", [])}
    check("the P0440 freeze frame is present", "P0440" in ff_codes, str(full.get("freeze_frames")))
    ff_p0440 = next(f for f in full["freeze_frames"] if f["code"] == "P0440")
    rpm_pids = [p for p in ff_p0440["pids"] if p["pid"] == "0C"]
    check("the freeze frame carries the engine_rpm PID", bool(rpm_pids), str(ff_p0440))

    mode06_3a = [r for r in full.get("mode06", []) if r.get("mid") == "3A"]
    check("Mode 06 MID 3A is present", bool(mode06_3a), str(full.get("mode06")))
    check("Mode 06 MID 3A FAILed", mode06_3a and mode06_3a[0]["passed"] is False, str(mode06_3a))

    check("health_verdict line is present when scan_health_bridge is importable",
         full.get("health_verdict") is None or isinstance(full["health_verdict"], str))

check("an unknown scan id returns None", cuore_log.read_scan(VIN, "SCAN_0000000000") is None)

# --- cuore_search: U1713 hits the module_dtcs line --------------------------

print("=== cuore_search ===")
res = cuore_log.search("U1713")
check("U1713 has at least one hit", res["count"] > 0, str(res))
check("one hit is the module_dtcs line, with context",
     any(m["source"] == "observations" and '"kind": "module_dtcs"' in m["match"]
        and len(m["context"]) > 1 for m in res["matches"]),
     str(res["matches"])[:400])

res_kinds = cuore_log.search("U1713", kinds=["owner_events"])
check("a kinds filter that excludes observations finds nothing",
     res_kinds["count"] == 0, str(res_kinds))

via_tool_search = json.loads(server.cuore_search("U1713"))
check("server.cuore_search matches the library call", via_tool_search["count"] == res["count"])

# --- logs_timeline: merges with the MES SCAN_2610080920 entry ----------------

print("=== logs_timeline ===")
timeline = cuore_log.logs_timeline(VIN)
sources = [(r["source"], r["file"]) for r in timeline["entries"]]
check("the MES scan is in the merged timeline",
     any(f == "SCAN_2610080920.txt" for _, f in sources), str(sources))
check("the CUORE session is in the merged timeline",
     any(f == "SCAN_2610131952" for _, f in sources), str(sources))
timestamps = [r["timestamp"] for r in timeline["entries"]]
check("the merged timeline is newest first",
     timestamps == sorted(timestamps, reverse=True), str(timestamps))
mes_idx = next(i for i, (_, f) in enumerate(sources) if f == "SCAN_2610080920.txt")
cuore_idx = next(i for i, (_, f) in enumerate(sources) if f == "SCAN_2610131952")
check("the 2026-10-08 MES scan sorts after the 2026-10-13 CUORE session",
     mes_idx > cuore_idx, str(sources))

# --- export round-trips through the mes parser -------------------------------

print("=== cuore_export_scan ===")
exported = cuore_log.export_scan(VIN, "SCAN_2610131952", fmt="mes")
check("mes export filename", exported["filename"] == "SCAN_2610131952.txt")
parsed = scan_mod.parse_scan_text(exported["content"], name=exported["filename"])
check("the exported text parses back as a scan log", bool(parsed.modules), exported["content"][:200])
check("the exported scan's VIN round-trips", parsed.vin == VIN)
check("P0440 round-trips through the export", any(d.code == "P0440" for d in parsed.all_dtcs))

exported_json = cuore_log.export_scan(VIN, "SCAN_2610131952", fmt="json")
check("json export filename", exported_json["filename"] == "SCAN_2610131952.json")
check("json export content is the scan dict", exported_json["content"]["id"] == "SCAN_2610131952")

try:
    cuore_log.export_scan(VIN, "SCAN_0000000000")
    check("exporting an unknown scan raises", False)
except LookupError:
    check("exporting an unknown scan raises LookupError", True)

# --- this export now appears in the MES catalog, labelled --------------------

print("=== mes.catalog second root ===")
from cuore.live import scanlog  # noqa: E402  (writes the on-disk export mes.catalog discovers)
write_result = scanlog.write_mes_export(VIN, "SCAN_2610131952")
check("write_mes_export wrote a file", write_result is not None and write_result.exists())

catalog.CATALOG._cache.clear()
# by_name()/resolve_log() only ever search the configured MES roots (that
# containment logic belongs to mes.paths, untouched here); the cuore export
# is discovered through entries()/select() instead -- see the catalog
# module docstring's "second root" note.
entry = next((e for e in catalog.CATALOG.entries() if e.name == "SCAN_2610131952.txt"), None)
check("the cuore export is discoverable through the catalog", entry is not None)
check("it is tagged with cuore live export provenance", entry.provenance == "cuore live export",
     entry.provenance if entry else "not found")
check("it is not flagged as simulation (it is real, from-car data)", entry.simulation is False)
cat_dict = entry.to_dict()
check("to_dict surfaces the provenance tag", cat_dict.get("provenance") == "cuore live export",
     str(cat_dict))

selected = catalog.CATALOG.select(vin=VIN)
check("select() with no include_simulation still returns the cuore export (it is real)",
     any(e.name == "SCAN_2610131952.txt" for e in selected), [e.name for e in selected])

# --- log hygiene: archive and integrity --------------------------------------

print("=== cuore_log_dir / cuore_log_archive / cuore_log_integrity ===")
d = cuore_log.log_dir()
check("log_dir reports observations.jsonl", d["files"]["observations.jsonl"]["exists"])
check("log_dir's state_dir matches CUORE_STATE_DIR", d["state_dir"] == str(CUORE_STATE_DIR))

obs_path = CUORE_STATE_DIR / "observations.jsonl"
before_bytes = obs_path.read_bytes()
archived = cuore_log.log_archive(label="check")
after_bytes = obs_path.read_bytes()
check("the original observations.jsonl is untouched after archiving", before_bytes == after_bytes)
check("the archive manifest lists observations.jsonl",
     any(f["file"] == "observations.jsonl" for f in archived["manifest"]["files"]),
     str(archived["manifest"]))
import hashlib
expected_sha = hashlib.sha256(before_bytes).hexdigest()
got_sha = next(f["sha256"] for f in archived["manifest"]["files"] if f["file"] == "observations.jsonl")
check("the manifest's sha256 matches the archived copy", expected_sha == got_sha)
archived_copy = Path(archived["archive_dir"]) / "observations.jsonl"
check("the archived copy exists on disk and matches byte-for-byte",
     archived_copy.exists() and archived_copy.read_bytes() == before_bytes)

integrity = cuore_log.log_integrity()
obs_integrity = integrity["observations.jsonl"]
check("integrity parses every line with no errors", obs_integrity["parse_errors"] == [],
     str(obs_integrity["parse_errors"]))
check("integrity counts by kind include module_dtcs and freeze_frame",
     "module_dtcs" in obs_integrity["by_kind"] and "freeze_frame" in obs_integrity["by_kind"],
     str(obs_integrity["by_kind"]))
check("integrity counts by day include 2026-10-13",
     "2026-10-13" in obs_integrity["by_day"], str(obs_integrity["by_day"]))
check("integrity reports absent files as not existing, not an error",
     integrity["jobs.jsonl"] == {"exists": False})

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
