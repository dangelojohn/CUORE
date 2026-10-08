"""Checks for the Systems map state API (Phase 2 of the dive-in plan,
``docs/research/SYSTEMS_DIVE_IN_PLAN_2026-10-08.md``):
``GET /api/systems/{vin}/state``, backed by
``cuore.services.systems_map_bridge``.

Same posture as ``cuore/tests/check_dashboard_page.py``: ``CUORE_STATE_DIR``
is pointed at a throwaway directory BEFORE cuore/mes is imported, and the
MES log corpus is NOT overridden -- the Stelvio's real corpus is the
fixture.

Run:
    .venv/Scripts/python.exe cuore/tests/check_systems_map_api.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-systems-map-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services.systems_map_bridge import ALLOWED_STATES  # noqa: E402

VIN = "ZASFAKPN5J7B88115"           # the Stelvio -- real corpus
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


client = TestClient(create_app())

print("=== known VIN ===")
resp = client.get(f"/api/systems/{VIN}/state")
check("endpoint responds 200", resp.status_code == 200, str(resp.status_code))
body = resp.json()
check("body has systems/edges/sessions", {"systems", "edges", "sessions"} <= set(body),
      str(list(body)))

systems = body.get("systems") or {}
check("25 system keys", len(systems) == 25, str(len(systems)))

bad_state = [k for k, v in systems.items() if v.get("state") not in ALLOWED_STATES]
check("every state is in the allowed set", not bad_state, str(bad_state))

bad_shape = [k for k, v in systems.items()
             if "open_code_count" not in v or "codes" not in v]
check("every system row has open_code_count and codes", not bad_shape, str(bad_shape))

edges = body.get("edges") or []
check("there are edges", len(edges) > 0, str(len(edges)))
bad_edges = [e for e in edges if "lift" not in e or "sessions_together" not in e]
check("every edge carries lift and sessions_together", not bad_edges, str(bad_edges[:3]))

depends_on_hits = []
for e in edges:
    for v in e.values():
        if isinstance(v, str) and "depends on" in v.lower():
            depends_on_hits.append(e)
            break
check("no edge text contains 'depends on'", not depends_on_hits, str(depends_on_hits[:3]))

sessions = body.get("sessions") or []
check("sessions is a non-empty ordered list for a car with history", len(sessions) > 0,
      str(len(sessions)))
bad_sessions = [s for s in sessions if "id" not in s or "when" not in s or "systems_fired" not in s]
check("every session row has id/when/systems_fired", not bad_sessions, str(bad_sessions[:3]))
whens = [s.get("when") for s in sessions if s.get("when")]
check("sessions are ordered by time", whens == sorted(whens), "")

print("=== unknown VIN ===")
missing = client.get(f"/api/systems/{NO_SUCH_VIN}/state")
check("unknown VIN still responds 200 (empty-but-valid shape)",
      missing.status_code == 200, str(missing.status_code))
mbody = missing.json()
msystems = mbody.get("systems") or {}
check("unknown VIN still has 25 keys", len(msystems) == 25, str(len(msystems)))
check("unknown VIN systems are all NO_DATA",
      all(v.get("state") == "NO_DATA" for v in msystems.values()),
      str({k: v.get("state") for k, v in msystems.items() if v.get("state") != "NO_DATA"}))
check("unknown VIN has no sessions", (mbody.get("sessions") or []) == [], "")
check("unknown VIN edges list is still a valid (possibly non-empty) list",
      isinstance(mbody.get("edges"), list), "")

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
