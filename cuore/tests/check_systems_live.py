"""Checks for the Systems map's live overlay (Phase 4 of the dive-in plan,
``docs/research/SYSTEMS_DIVE_IN_PLAN_2026-10-08.md``):
``GET /api/systems/{vin}/live``, backed by
``cuore.services.systems_map_bridge.live_state``/``new_live_codes``.

Same posture as ``cuore/tests/check_systems_map_api.py``/
``check_liveboard.py``: plain script, ``CUORE_STATE_DIR`` pointed at a
throwaway directory BEFORE cuore/mes is imported, the Stelvio's real MES
corpus is the fixture for the VIN itself. No real adapter session exists in
a test process, so the live poller is stood in for with a small fake object
(``FakePoller``, same posture as ``check_live_data.py``'s hand-written fake
``Stream`` -- no mocking framework) passed to
``cuore.live.poller.set_poller`` -- the same seam ``check_live_data.py``
itself uses to install a fresh poller per check.

Three checks:
  1. No live session (the real process-wide poller, untouched): the
     endpoint responds 200 with 25 system keys, every grade "none", an
     honest (not-connected) scanner label, and no new codes.
  2. A fixture live snapshot (coolant hot, same 140C fixture
     ``check_liveboard.py`` uses) makes the cooling system's grade
     "excessive" and carries that channel's value/unit.
  3. A synthetic new DTC (P0304, not in this VIN's own corpus-derived
     ``system_states``) maps to its system (ignition, via the SAE P03xx
     fallback) and appears in ``new_codes`` exactly once per call, not
     twice, even across two consecutive polls.

Run:
    .venv/Scripts/python.exe cuore/tests/check_systems_live.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-systems-live-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401  -- side effect: mes on sys.path
from cuore.app import create_app  # noqa: E402
from cuore.live import poller as poller_mod  # noqa: E402
from cuore.services import systems_map_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"           # the Stelvio -- real corpus

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def check_eq(label: str, got, want) -> None:
    check(label, got == want, f"got {got!r} want {want!r}")


class FakePoller:
    """Duck-types just the three methods ``systems_map_bridge.live_state``/
    ``new_live_codes`` call on the real ``cuore.live.poller.LivePoller`` --
    no adapter, no thread, same posture as ``check_live_data.py``'s
    hand-written fake ``Stream``."""

    def __init__(self, active: bool = False, channels: dict | None = None,
                codes: list[str] | None = None, first_seen: dict | None = None) -> None:
        self._active = active
        self._channels = channels or {}
        self._codes = codes or []
        self._first_seen = first_seen or {}

    def is_active(self) -> bool:
        return self._active

    def snapshot(self) -> dict:
        return {"active": self._active, "channels": self._channels}

    def dtc_snapshot(self) -> dict:
        return {"codes": sorted(self._codes), "first_seen": dict(self._first_seen)}


app = create_app()
client = TestClient(app)


# --- 1. no live session ----------------------------------------------------

print("=== no live session ===")
poller_mod.set_poller(FakePoller(active=False))

resp = client.get(f"/api/systems/{VIN}/live")
check_eq("GET /api/systems/{vin}/live status (idle)", resp.status_code, 200)
body = resp.json()
check("body has active/scanner/systems/new_codes",
      {"active", "scanner", "systems", "new_codes"} <= set(body), str(list(body)))
check_eq("active is False", body.get("active"), False)
systems = body.get("systems") or {}
check_eq("25 system keys", len(systems), 25)
bad_grade = [k for k, v in systems.items() if v.get("grade") != "none"]
check("every grade is 'none' with no live session", not bad_grade, str(bad_grade))
bad_shape = [k for k, v in systems.items()
             if not {"grade", "value", "unit", "channel"} <= set(v)]
check("every system row has grade/value/unit/channel", not bad_shape, str(bad_shape))
scanner = (body.get("scanner") or "").lower()
check("scanner label is honest about no session running",
      "not running" in scanner or "disconnected" in scanner, body.get("scanner"))
check_eq("no new codes with no live session", body.get("new_codes"), [])


# --- 2. fixture live snapshot: coolant hot -> cooling grades excessive ----

print("=== fixture live snapshot ===")
poller_mod.set_poller(FakePoller(
    active=True,
    channels={"engine_coolant_temp": {"value": 140.0, "unit": "C", "alarm": "ok"}},
))

resp2 = client.get(f"/api/systems/{VIN}/live")
check_eq("GET /api/systems/{vin}/live status (active)", resp2.status_code, 200)
body2 = resp2.json()
check_eq("active is True", body2.get("active"), True)
cooling = (body2.get("systems") or {}).get("cooling") or {}
check_eq("cooling grade reflects the hot coolant channel", cooling.get("grade"), "excessive")
check_eq("cooling row carries the coolant value", cooling.get("value"), 140.0)
check_eq("cooling row carries the coolant channel id", cooling.get("channel"), "engine_coolant_temp")
check("active scanner label says connected",
      "connected" in (body2.get("scanner") or "").lower(), body2.get("scanner"))

# a system with no live channel reading at all still grades "none", not
# a fabricated "ok" or "unknown"
other = next((v for k, v in (body2.get("systems") or {}).items()
             if k != "cooling" and v.get("grade") != "none"), None)
check("a system with no live reading grades 'none', not invented",
      other is None, str(other))


# --- 3. synthetic new DTC maps to its system, once not twice --------------

print("=== synthetic new DTC ===")
known_codes: set[str] = set()
for row in systems_map_bridge.system_states(VIN).values():
    known_codes.update(row.get("codes") or [])

NEW_CODE = "P0304"   # SAE P03xx fallback -> ignition; a misfire code this
                     # EVAP-focused car's own corpus should not already carry
check(f"{NEW_CODE} is not already in this VIN's known codes "
     "(test assumption)", NEW_CODE not in known_codes, str(sorted(known_codes)))

poller_mod.set_poller(FakePoller(
    active=True,
    channels={"engine_coolant_temp": {"value": 90.0, "unit": "C", "alarm": "ok"}},
    codes=[NEW_CODE],
    first_seen={NEW_CODE: "2026-10-08T12:00:00"},
))

resp3 = client.get(f"/api/systems/{VIN}/live")
check_eq("GET /api/systems/{vin}/live status (new code)", resp3.status_code, 200)
body3 = resp3.json()
new_codes = body3.get("new_codes") or []
check_eq(f"{NEW_CODE} appears exactly once in new_codes", len(new_codes), 1)
if new_codes:
    entry = new_codes[0]
    check_eq("the new code is the synthetic one", entry.get("code"), NEW_CODE)
    check("the new code maps to the ignition system",
         "ignition" in (entry.get("systems") or []), str(entry))
    check_eq("the new code's since is the poller's own first_seen timestamp",
            entry.get("since"), "2026-10-08T12:00:00")

# a second poll must not duplicate the same code either
resp4 = client.get(f"/api/systems/{VIN}/live")
body4 = resp4.json()
new_codes4 = body4.get("new_codes") or []
check_eq(f"{NEW_CODE} still appears exactly once on a second poll, not twice",
         len(new_codes4), 1)


# --- summary -----------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
