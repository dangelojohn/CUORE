"""Smoke checks for mes.tools_kb and mes.tool_usage.

Plain script style, like check_maintenance_specs.py: no test framework.
mes.tool_usage writes to CUORE_STATE_DIR, so that is pointed at a throwaway
directory before anything is imported -- same posture as
cuore/tests/check_jobs_page.py.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_tools_kb.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="mes-check-tools-kb-")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mes import tool_usage  # noqa: E402
from mes import tools_kb  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- 1. recommend("oil_change") includes a torque wrench with the drain-plug
#        torque key, resolved to the sourced 20 Nm spec ------------------------

oil_rows = tools_kb.recommend("oil_change")
check("oil_change recommends at least one tool", len(oil_rows) > 0, str(oil_rows))

torque_rows = [r for r in oil_rows if r["tool_info"]["kind"] == "torque"
              and "drain_plug" in r["torque_keys"]]
check("oil_change includes a torque-kind tool carrying the drain_plug torque key",
      len(torque_rows) == 1, str(oil_rows))
if torque_rows:
    drain_specs = [t for t in torque_rows[0]["torques"] if t["key"] == "drain_plug"]
    check("that row's resolved torques include the drain plug at 20 Nm",
          len(drain_specs) == 1 and drain_specs[0]["value"] == 20
          and drain_specs[0]["unit"] == "Nm", str(drain_specs))


# --- 2. turbo_replacement's line-fitting tool is UNKNOWN sized, with the
#        TechAuthority note ---------------------------------------------------

turbo_rows = tools_kb.recommend("turbo_replacement")
check("turbo_replacement recommends at least one tool", len(turbo_rows) > 0, str(turbo_rows))

flare_rows = [r for r in turbo_rows if r["tool"] == "flare_nut_wrench_set"]
check("turbo_replacement includes the flare-nut wrench set", len(flare_rows) == 1,
      str(turbo_rows))
if flare_rows:
    ti = flare_rows[0]["tool_info"]
    check("its spec is explicitly UNKNOWN, not a guessed size",
          ti["confidence"] == "UNKNOWN" and ti["spec"] is not None
          and "UNKNOWN" in ti["spec"], str(ti))
    check("its spec points at confirming on the car / service manual (TechAuthority)",
          "confirm on the car" in ti["spec"] and "TechAuthority" in ti["spec"], str(ti))
    check("the row's own note calls out the risk of the wrong tool adding hours",
          "hours" in flare_rows[0]["note"].lower(), flare_rows[0]["note"])


# --- 3. usage add -> learn aggregates was_right=no and would_buy ------------

VIN = "ZASFAKPN5J7B88115"
tool_usage.add(VIN, "turbo_replacement", job_id="j1",
               tools_used=[{"tool": "flare_nut_wrench_set", "was_right": "no",
                            "note": "rounded the fitting"}],
               would_buy=[{"name": "crowfoot_flare_set", "why": "avoid rounding fittings"}])
tool_usage.add(VIN, "turbo_replacement", job_id="j2",
               tools_used=[{"tool": "flare_nut_wrench_set", "was_right": "yes"}])

learned = tool_usage.learn("turbo_replacement", vin=VIN)
check("learn() reports 2 reviews for this step/vin", learned["review_count"] == 2,
      str(learned))
wrong = {f["tool"]: f for f in learned["flagged_wrong"]}
check("flagged_wrong includes the flare-nut wrench set flagged wrong once",
      wrong.get("flare_nut_wrench_set", {}).get("count") == 1, str(learned))
check("the wrong-flag carries the mechanic's own note",
      "rounded the fitting" in wrong.get("flare_nut_wrench_set", {}).get("notes", []),
      str(learned))
buy = {b["name"]: b for b in learned["buy_suggestions"]}
check("buy_suggestions includes the crowfoot set with its stated reason",
      buy.get("crowfoot_flare_set", {}).get("count") == 1
      and "avoid rounding fittings" in buy.get("crowfoot_flare_set", {}).get("why", []),
      str(learned))


# --- summary ------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
