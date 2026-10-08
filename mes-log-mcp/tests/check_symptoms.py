"""Smoke checks for driver/mechanic symptom reports.

Same posture as ``check_notes.py``: ``CUORE_STATE_DIR`` is pointed at a
throwaway directory before anything under ``mes`` (or ``server``) is
imported, so this suite never touches the real bench's symptom reports.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="mes-check-symptoms-")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from mes import symptoms  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
OTHER_VIN = "1C4RJFAG0JC000001"
failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


print("=== store: validation ===")
try:
    symptoms.add("", "2026-09-25T20:02:00")
    check("empty vin rejected", False)
except ValueError:
    check("empty vin rejected", True)

try:
    symptoms.add(VIN, "")
    check("empty at rejected", False)
except ValueError:
    check("empty at rejected", True)

try:
    symptoms.add(VIN, "2026-09-25T20:02:00", reporter="owner")
    check("unknown reporter rejected", False)
except ValueError:
    check("unknown reporter rejected", True)

try:
    symptoms.add(VIN, "2026-09-25T20:02:00", tags=["not_a_tag"])
    check("unknown tag rejected", False)
except ValueError as exc:
    check("unknown tag rejected", "unknown tag" in str(exc))

try:
    symptoms.add(VIN, "2026-09-25T20:02:00", conditions=["not_a_condition"])
    check("unknown condition rejected", False)
except ValueError as exc:
    check("unknown condition rejected", "unknown condition" in str(exc))

try:
    symptoms.add(VIN, "2026-09-25T20:02:00", tags=["drives_normally", "rough_idle"])
    check("drives_normally + rough_idle rejected", False)
except ValueError as exc:
    check("drives_normally + rough_idle rejected", "drives_normally" in str(exc))

try:
    symptoms.add(VIN, "2026-09-25T20:02:00", tags=["drives_normally", "hesitation"])
    check("drives_normally + hesitation rejected", False)
except ValueError:
    check("drives_normally + hesitation rejected", True)

# a non-drivability tag may ride alongside drives_normally without complaint
ok_combo = symptoms.add(VIN, "2026-09-25T20:02:00", tags=["drives_normally", "warning_message"])
check("drives_normally + a non-drivability tag is accepted",
      ok_combo["tags"] == ["drives_normally", "warning_message"])
symptoms.hide(ok_combo["id"])

print("=== store: add / hide / load ===")
s1 = symptoms.add(VIN, "2026-09-25T18:00:00", odometer_km=141900, reporter="driver",
                  tags=["drives_normally"], conditions=["highway"],
                  text="no complaints, drove fine")
check("add stamps id/vin/at", bool(s1.get("id")) and s1["vin"] == VIN
      and s1["at"] == "2026-09-25T18:00:00")
check("add keeps tags/conditions/text", s1["tags"] == ["drives_normally"]
      and s1["conditions"] == ["highway"] and "drove fine" in s1["text"])
check("add stamps created_at", bool(s1.get("created_at")))

s2 = symptoms.add(VIN, "2026-09-02T09:00:00", reporter="mechanic",
                  tags=["rough_idle", "hard_start"], conditions=["cold_start"])
s3 = symptoms.add(OTHER_VIN, "2026-01-01T00:00:00", tags=["mil_on"])

loaded = symptoms.load(VIN)
check("load filters by vin", {s["id"] for s in loaded} == {s1["id"], s2["id"]})
check("load is oldest-'at'-first", [s["id"] for s in loaded] == [s2["id"], s1["id"]])
check("other VIN's symptom does not leak in", s3["id"] not in {s["id"] for s in loaded})

hidden = symptoms.hide(s2["id"])
check("hide stamps id", hidden["id"] == s2["id"])
after_hide = symptoms.load(VIN)
check("hidden symptom excluded by default", s2["id"] not in {s["id"] for s in after_hide})
with_hidden = symptoms.load(VIN, include_hidden=True)
check("include_hidden=True surfaces it, flagged hidden",
      any(s["id"] == s2["id"] and s["hidden"] for s in with_hidden))

try:
    symptoms.hide("nonexistent-id")
    check("hide on unknown id rejected", False)
except ValueError:
    check("hide on unknown id rejected", True)

print("=== MCP tools ===")
rec = json.loads(server.add_symptom(vin=VIN, at="2026-09-26T08:00:00",
                                    tags="drives_normally", conditions="highway"))
check("add_symptom tool records", rec["vin"] == VIN and rec["tags"] == ["drives_normally"])

listed = json.loads(server.symptoms(vin=VIN))
check("symptoms tool lists what was recorded",
      listed["vin"] == VIN and any(s["id"] == rec["id"] for s in listed["symptoms"]))

hidden_tool = json.loads(server.hide_symptom(id=rec["id"]))
check("hide_symptom tool records the hide", hidden_tool["id"] == rec["id"])

after_hide_tool = json.loads(server.symptoms(vin=VIN))
check("hidden symptom excluded from the default tool listing",
      not any(s["id"] == rec["id"] for s in after_hide_tool["symptoms"]))

bad = json.loads(server.add_symptom(vin=VIN, at=""))
check("add_symptom tool surfaces validation errors", "error" in bad)

bad_tag = json.loads(server.add_symptom(vin=VIN, at="2026-09-26T08:00:00", tags="not_a_tag"))
check("add_symptom tool surfaces tag validation errors", "error" in bad_tag)

bad_combo = json.loads(server.add_symptom(vin=VIN, at="2026-09-26T08:00:00",
                                          tags="drives_normally,rough_idle"))
check("add_symptom tool rejects drives_normally+rough_idle", "error" in bad_combo)

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
