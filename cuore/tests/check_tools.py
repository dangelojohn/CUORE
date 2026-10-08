"""Checks for the mechanic-facing Tools catalogue (cuore/services/tools_bridge.py).

Run:
    .venv/Scripts/python.exe cuore/tests/check_tools.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-tools-")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.app import create_app  # noqa: E402
from cuore.services import tools_bridge  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


spec = create_app().openapi()
spec_ops = {(m.upper(), p) for p, methods in spec["paths"].items()
           for m in methods if m.lower() in ("get", "post", "put", "delete", "patch")}

no_port_state = tools_bridge.current_state("")
no_port_state.update(port=None, port_exists=False, mes_state="not_running",
                     cable="blue_a5", buses_verified=["can_c"])
cat_no_port = tools_bridge.catalogue(spec, no_port_state)

# 1. every spec operation is accounted for (curated or developer_only)
tools_by_id = {t["id"]: t for g in cat_no_port["groups"] for t in g["tools"]}
spec_ids = {f"{m} {p}" for m, p in spec_ops}
check("every spec operation appears in the catalogue", spec_ids <= set(tools_by_id),
     str(spec_ids - set(tools_by_id))[:300])

# 2. no HTTP catalogue tool performs a vehicle write: the spec itself has no
# clear/actuate/routine-run path (listing learned actuators is fine -- that's
# a read), and nothing in CURATED claims run="one_tap"/"form" for one.
write_paths = [p for _, p in spec_ops
              if "clear" in p.lower() or "/actuate" in p.lower() or "/routine" in p.lower()]
check("the spec has no clear/actuate/routine HTTP path", not write_paths, str(write_paths))
leaked = [tid for tid, t in tools_by_id.items()
         if t.get("method") and t["run"] != "not_from_here"
         and ("clear" in tid.lower() or "/actuate" in tid.lower() or "/routine" in tid.lower())]
check("no write operation leaked into the HTTP catalogue as runnable", not leaked, str(leaked))
write_group = next(g for g in cat_no_port["groups"] if g["id"] == "writes")
check("the writes group lists the 3 MCP-only cards, all not_from_here",
     len(write_group["tools"]) == 3 and
     all(t["run"] == "not_from_here" for t in write_group["tools"]))

# 3. enablement: no port -> needs-car tools disabled with a plain-words reason
probe = tools_by_id.get("POST /api/live/probe")
check("probe needs car and is disabled with no port",
     probe is not None and probe["enabled"] is False and bool(probe["disabled_reason"]))

port_state = dict(no_port_state, port="COM3", port_exists=True)
cat_with_port = tools_bridge.catalogue(spec, port_state)
probe2 = next(t for g in cat_with_port["groups"] for t in g["tools"]
             if t["id"] == "POST /api/live/probe")
check("probe enables once the port exists and mes is stopped", probe2["enabled"] is True)

# 4. shape_result renders DTC status words from the status byte
shaped = tools_bridge.shape_result(
    "GET /api/live/obd/dtcs",
    {"dtcs": [{"code": "P0456", "description": "EVAP small leak", "status": "0x09"}]})
check("shaped DTC carries readable status words",
     shaped["kind"] == "codes" and "test failed" in shaped["rows"][0]["status"]
     and "test failed this cycle" in shaped["rows"][0]["status"], str(shaped))

# 5. coverage numbers are internally consistent
cov = cat_no_port["coverage"]
check("coverage total matches the spec", cov["total_operations"] == len(spec_ops),
     f"{cov['total_operations']} vs {len(spec_ops)}")
check("curated + developer_only == total",
     cov["curated"] + cov["developer_only"] == cov["total_operations"], str(cov))

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
