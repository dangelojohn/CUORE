"""Smoke checks for the "what would the driver feel?" knowledge table.

No state directory needed -- ``mes.code_feel`` is a read-only lookup table,
not a store.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from mes import code_feel  # noqa: E402
from mes.symptoms import SYMPTOM_TAGS  # noqa: E402

failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


REQUIRED_CODES = ["P0440", "P0441", "P0455", "P0456", "P0457", "P1CEA",
                  "B1176", "C141B", "C141C", "P0300", "P0301", "P0302",
                  "P0303", "P0304", "P0171", "P0172"]

print("=== coverage ===")
for code in REQUIRED_CODES:
    entry = code_feel.lookup(code)
    check(f"{code} is tabulated", entry is not None)

print("=== every non-UNKNOWN entry has a source ===")
for code in REQUIRED_CODES:
    entry = code_feel.lookup(code)
    if entry is None:
        continue
    if entry["confidence"] == code_feel.UNKNOWN:
        check(f"{code} UNKNOWN entry points at the service manual",
              "TechAuthority" in entry.get("notes", "") or "TechAuthority" in entry.get("feel", ""))
    else:
        check(f"{code} ({entry['confidence']}) has a non-empty source",
              bool((entry.get("source") or "").strip()), entry)

print("=== tags are valid SYMPTOM_TAGS ===")
for code in REQUIRED_CODES:
    entry = code_feel.lookup(code)
    if entry is None:
        continue
    for field in ("expect", "not_expected"):
        bad = [t for t in entry.get(field, []) if t not in SYMPTOM_TAGS]
        check(f"{code}.{field} only uses SYMPTOM_TAGS", not bad, str(bad))

print("=== exact-code resolution strips the failure-type byte ===")
check("P0456-00 resolves the same as P0456",
      code_feel.lookup("P0456-00") == code_feel.lookup("P0456"))

print("=== family fallback ===")
u_entry = code_feel.lookup("U0199")  # not individually tabulated
check("an untabulated U-code falls back to the network family",
      u_entry is not None and u_entry["matched"] == "family:network")
check("network fallback has a source", bool((u_entry or {}).get("source", "").strip()))

misfire_entry = code_feel.lookup("P0305")  # cylinder 5, not individually tabulated
check("an untabulated P03xx falls back to the misfire family",
      misfire_entry is not None and misfire_entry["matched"] == "family:misfire")

check("a code with no entry and no family falls back to the generic "
      "SAE-prefix entry, UNKNOWN confidence, instead of nothing",
      code_feel.lookup("P9999") is not None
      and code_feel.lookup("P9999")["matched"] == "generic:sae"
      and code_feel.lookup("P9999")["confidence"] == code_feel.UNKNOWN)
check("something that isn't a P/B/C/U code at all still returns None",
      code_feel.lookup("XYZZY") is None)

print("=== EVAP family: no drivability symptom expected ===")
drivability = {"rough_idle", "hesitation", "loss_of_power", "hard_start"}
for code in ("P0440", "P0441", "P0455", "P0456", "P0457", "P1CEA"):
    entry = code_feel.lookup(code)
    not_expected = set(entry.get("not_expected", []))
    expect = set(entry.get("expect", []))
    check(f"{code} does not expect a drivability symptom",
          not (expect & drivability), str(entry))

print("=== MCP tool ===")
tool_result = json.loads(server.dtc_feel("P0455"))
check("dtc_feel tool returns a sourced P0455 entry",
      tool_result is not None and tool_result["confidence"] != code_feel.UNKNOWN)
unknown_tool = json.loads(server.dtc_feel("P9999"))
check("dtc_feel tool returns the generic SAE fallback for nothing "
      "tabulated, not null",
      unknown_tool is not None and unknown_tool["confidence"] == "UNKNOWN")
not_a_code_tool = json.loads(server.dtc_feel("XYZZY"))
check("dtc_feel tool returns null for something that isn't a P/B/C/U code",
      not_a_code_tool is None)

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
