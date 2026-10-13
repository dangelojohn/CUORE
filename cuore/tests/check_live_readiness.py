"""Offline dry-run for the first live OBD session (see
``docs/handbook/07-first-live-session.md``).

No car is connected when this runs. Everything here is checked without one:
COM-port enumeration (reports what it finds, never fails for a missing
COM3), the poller module's write-refusal guard, ``/api/health``, the
``/api/live*`` endpoints' honesty about "not connected" (never a fabricated
connected state), the Systems live overlay's not-connected labels, and the
readiness panel's from-car/demo-replay distinction.

Same posture as ``cuore/tests/check_live.py`` and ``check_systems_live.py``:
plain script, ``check(label, cond, detail)``, exit 1 on failure, no mocking
framework, a throwaway ``CUORE_STATE_DIR`` set before any cuore import. This
file never edits anything under ``cuore/live/`` or ``obd2-mcp/`` -- it only
calls the public functions there, same as ``check_live.py``'s own promise.

``CUORE_AUTOSTART=0`` and an unreachable ``CUORE_URL`` are set before
importing obd2-mcp's ``server`` module, so its tools fall back to the
in-process ``cuore.live.ops`` code (``_via``'s documented fallback) instead
of spawning a real cuore process or talking to one that happens to be
running on this machine already.

Run:
    .venv/Scripts/python.exe cuore/tests/check_live_readiness.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: state goes to a throwaway directory, never the
# bench's real evidence, and obd2-mcp's HTTP client must not reach (or
# start) a real cuore process.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-live-readiness-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)
os.environ["CUORE_AUTOSTART"] = "0"
os.environ["CUORE_URL"] = "http://127.0.0.1:1"  # connection refused, fast, never autostarted

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- the car this runbook is for

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


# ===========================================================================
# 1. COM port enumeration via obd2-mcp's list_ports -- report, never fail
#    for a missing COM3.
# ===========================================================================

print("=== obd2-mcp list_ports (offline) ===")

_spec = importlib.util.spec_from_file_location("obd2_server", ROOT / "obd2-mcp" / "server.py")
obd2_server = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(obd2_server)  # not __main__, so mcp.run() never fires

raw = obd2_server.list_ports()
check("list_ports() returns valid JSON", isinstance(raw, str))
parsed = json.loads(raw)
check("list_ports() result has 'ports'", "ports" in parsed, str(list(parsed)))
check("list_ports() result has 'mes_port'", "mes_port" in parsed, str(list(parsed)))
check("list_ports() ran in-process (cuore unreachable by design here)",
      str(parsed.get("served_by", "")).startswith("in-process fallback"),
      str(parsed.get("served_by")))

ports = parsed.get("ports") or []
devices = sorted(p.get("device", "") for p in ports)
has_com3 = "COM3" in devices
print(f"  -- COM3 {'found' if has_com3 else 'NOT found'} "
      f"(not a failure either way); ports seen: {devices or '(none)'}")
check("every listed port has a device string",
      all(isinstance(p.get("device"), str) and p.get("device") for p in ports), str(ports))


# ===========================================================================
# 2. the poller module imports, and refuses other adapter operations
#    (including both vehicle writes) while it holds the port.
# ===========================================================================

print("=== poller module: write-refusal guard ===")

from cuore.live import ops  # noqa: E402
from cuore.live import poller as poller_mod  # noqa: E402
from cuore.live.errors import Refused  # noqa: E402

check("clear_module_dtcs (vehicle write) is poller-guarded",
      "clear_module_dtcs" in ops._POLLER_GUARDED)
check("run_actuator (vehicle write) is poller-guarded",
      "run_actuator" in ops._POLLER_GUARDED)
check("obd_readiness (the readiness read itself) is poller-guarded",
      "obd_readiness" in ops._POLLER_GUARDED)


class _FakeHoldingPoller:
    """Duck-types just what ``ops._poller_active_guard`` calls -- no
    adapter, no thread, same posture as ``check_systems_live.py``'s
    ``FakePoller``."""

    def holds_adapter(self) -> bool:
        return True

    def is_active(self) -> bool:
        return True


_real_poller = poller_mod.poller()
try:
    poller_mod.set_poller(_FakeHoldingPoller())
    try:
        ops._poller_active_guard()
        guard_raised = False
    except Refused as e:
        guard_raised = True
        guard_message = str(e)
    check("_poller_active_guard refuses while the poller holds the adapter", guard_raised)
    if guard_raised:
        check("the refusal names live_session_stop as the way out",
              "live_session_stop" in guard_message or "session/stop" in guard_message,
              guard_message)
finally:
    poller_mod.set_poller(_real_poller)

check("a fresh, unstarted poller does not hold the adapter",
      poller_mod.poller().holds_adapter() is False)
check("a fresh, unstarted poller is not active",
      poller_mod.poller().is_active() is False)


# ===========================================================================
# 3-6. the FastAPI surface: /api/health, /api/live*, Systems live overlay --
# all with no adapter connected.
# ===========================================================================

print("=== FastAPI surface, no adapter connected ===")

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401  -- side effect: mes on sys.path
from cuore.app import create_app  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.services import systems_map_bridge  # noqa: E402

client = TestClient(create_app())

# --- 3. /api/health ---------------------------------------------------------

resp = client.get("/api/health")
check_eq("GET /api/health is 200", resp.status_code, 200)
health = resp.json()
check("health body has profile/version/corpus_reachable/cache",
      {"profile", "version", "corpus_reachable", "cache"} <= set(health), str(list(health)))

# --- 4. /api/capabilities and /api/live/status: honest, not fabricated -----

caps = client.get("/api/capabilities")
check_eq("GET /api/capabilities is 200", caps.status_code, 200)
cbody = caps.json()
adapter = cbody.get("adapter") or {}
check("adapter.present is a bool", isinstance(adapter.get("present"), bool), str(adapter))
check_eq("live_obd tracks adapter.present (no feature is advertised the adapter can't honour)",
         cbody["features"]["live_obd"], adapter["present"])
check_eq("live_can tracks adapter.present too",
         cbody["features"]["live_can"], adapter["present"])
check("adapter.note never claims a connection -- only ever 'port opened per operation...'",
      str(adapter.get("note", "")).startswith("port opened per operation"), str(adapter.get("note")))
check("adapter.note says the adapter was never probed in this process "
     "(no probe() call happened above)",
      "not probed yet" in str(adapter.get("note", "")), str(adapter.get("note")))

live_status = client.get("/api/live/status")
check_eq("GET /api/live/status is 200", live_status.status_code, 200)
lbody = live_status.json()
check("adapter_identity is honestly None (never probed)", lbody.get("adapter_identity") is None,
      str(lbody.get("adapter_identity")))
check("last_open is honestly None (never opened)", lbody.get("last_open") is None,
      str(lbody.get("last_open")))
mes = lbody.get("mes") or {}
check("mes state is one of the four honest values",
      mes.get("state") in ("not_running", "disconnected", "connected", "unknown"), str(mes))

# --- 5. /api/live/snapshot: the Live board's own data source, idle --------

snap = client.get("/api/live/snapshot")
check_eq("GET /api/live/snapshot is 200", snap.status_code, 200)
sbody = snap.json()
check_eq("Live board snapshot: active is False with no session running",
         sbody.get("active"), False)
check_eq("Live board snapshot: channels is empty, not fabricated values",
         sbody.get("channels"), {})

# --- 6. Systems live overlay: not-connected labels -------------------------


class _FakeIdlePoller:
    """Same duck-type ``check_systems_live.py`` uses for the idle case."""

    def is_active(self) -> bool:
        return False

    def snapshot(self) -> dict:
        return {"active": False, "channels": {}}

    def dtc_snapshot(self) -> dict:
        return {"codes": [], "first_seen": {}}


_real_poller2 = poller_mod.poller()
try:
    poller_mod.set_poller(_FakeIdlePoller())
    sys_live = client.get(f"/api/systems/{VIN}/live")
    check_eq("GET /api/systems/{vin}/live is 200", sys_live.status_code, 200)
    slbody = sys_live.json()
    check_eq("Systems live overlay: active is False", slbody.get("active"), False)
    scanner = (slbody.get("scanner") or "").lower()
    check("Systems live overlay: scanner label is honest about no session",
          "not running" in scanner or "disconnected" in scanner, slbody.get("scanner"))
    systems = slbody.get("systems") or {}
    check_eq("Systems live overlay: 25 system keys", len(systems), 25)
    bad_grade = [k for k, v in systems.items() if v.get("grade") != "none"]
    check("Systems live overlay: every grade is 'none' with no live session",
          not bad_grade, str(bad_grade))
finally:
    poller_mod.set_poller(_real_poller2)


# ===========================================================================
# 7. the readiness panel: demo/replay sources are never counted as from-car.
# ===========================================================================

print("=== readiness panel: from-car vs demo/replay ===")

check("is_from_car: real serial stream counts",
      live_store.is_from_car({"stream": "serial COM3@115200"}))
check("is_from_car: a recording of a real serial session counts",
      live_store.is_from_car({"stream": "recording(serial COM3@115200)"}))
check("is_from_car: demo source does not count",
      not live_store.is_from_car({"stream": "demo"}))
check("is_from_car: replay source does not count",
      not live_store.is_from_car({"stream": "replay stelvio_evap_demo.csv"}))
check("is_from_car: a scripted/test stream does not count",
      not live_store.is_from_car({"stream": "scripted"}))
check("is_from_car: no stream at all does not count",
      not live_store.is_from_car({}))

# Round-trip through the real store: a demo-sourced readiness observation is
# written, then confirmed absent from "from car" filtering -- the same
# filter dossier_bridge._latest_readiness applies when building the panel
# that feeds systems_map_bridge.system_states's VERIFIED_CLEAN promotion.
live_store.record_observation(
    "readiness", {"since_clear": {"monitors": [
        {"monitor": "Evaporative system", "complete": True}], "all_complete": True}},
    vin=VIN, bus="can_c", cable="none", stream="demo")

demo_obs = [o for o in live_store.recent_observations(50, vin=VIN, kind="readiness")
           if o.get("stream") == "demo"]
check("the demo readiness observation round-trips through the store", len(demo_obs) == 1,
      str(demo_obs))
if demo_obs:
    check("...but is not from the car, however complete its monitors claim to be",
          not live_store.is_from_car(demo_obs[0]), str(demo_obs[0]))

# A system can only reach VERIFIED_CLEAN from a from-car readiness read --
# confirm the live bridge's own panel-sourced flag agrees with is_from_car
# for this VIN right now (no real readiness read has ever happened here).
states = systems_map_bridge.system_states(VIN)
verified_clean = {k: v for k, v in states.items() if v.get("state") == "VERIFIED_CLEAN"}
check("no system is VERIFIED_CLEAN from a demo-only observation "
     "(the demo readiness row above must not have promoted anything)",
      not verified_clean, str(verified_clean))


# ===========================================================================
# report
# ===========================================================================

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
