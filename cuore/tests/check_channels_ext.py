"""Checks for the J1979-extension live channels (PIDs 13, 15, 1C, 2C, 2D,
34, 3C, 40, 41, 47, 49, 4A, 54, 59, 60, 68, 6B, 70, 72) being wired into
``cuore.live.channels``, ``mes.systems`` and ``cuore.services.liveboard_bridge``
alongside the decoders another pass is adding to ``cuore.live.obd``.

Same posture as ``check_live_data.py``/``check_liveboard.py``: plain script,
``check(label, cond, detail)``, exit 1 on failure, throwaway state dir.

This file does NOT depend on the decoders already existing in
``cuore.live.obd`` -- the ``mes.systems``/preset/grading checks below are
true regardless, and a channel whose decoder hasn't landed yet is reported
as a skipped "pending decoder" note rather than a failure (see
``PENDING_NOTES`` below), per the coordination note in the task: register
the channel's system/grading wiring now, treat a missing decoder as
pending, not broken.

Four groups of checks:
  1. Every new channel name has a system key, and that key is one of the
     25 in ``mes.systems.SYSTEMS``.
  2. The ``evap_test_a`` preset exists and resolves to real channels.
  3. Grading returns "unknown" for channels with no sourced ``known_good``
     row (evap vapor pressure abs, fuel rail abs pressure, catalyst temp).
  4. No channel with an unknown DID (``esim_status``) is pollable: it is
     not in the registry's "did==0" classified as unknown, it is absent
     from every preset, and ``resolve_channels`` refuses it outright.

Run:
    .venv/Scripts/python.exe cuore/tests/check_channels_ext.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-channels-ext-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from cuore import bootstrap  # noqa: E402,F401  -- side effect: mes on sys.path
from cuore.live import channels as channels_mod  # noqa: E402
from cuore.live.errors import BadCommand  # noqa: E402
from cuore.services import liveboard_bridge  # noqa: E402

from mes import systems as systems_mod  # noqa: E402

failures: list[str] = []
checks = 0
pending_notes: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want, extra: str = "") -> None:
    detail = f"got {got!r} want {want!r}"
    if extra:
        detail += f" ({extra})"
    check(label, got == want, detail)


def pending(channel_id: str, why: str) -> None:
    pending_notes.append(f"{channel_id}: {why}")


# --- the 19 new J1979-extension channel names -------------------------------
# PIDs: 13, 15, 1C, 2C, 2D, 34, 3C, 40, 41, 47, 49, 4A, 54, 59, 60, 68, 6B,
# 70, 72 -- names per the task's coordination note (another pass owns the
# decoders in cuore.live.obd; this file only owns the system/preset/grading
# wiring in cuore.live.channels / mes.systems / liveboard_bridge).
NEW_CHANNELS = (
    "o2_sensors_present", "o2_b1s2_voltage", "obd_standard", "commanded_egr",
    "egr_error", "o2_wr_lambda_b1s1", "catalyst_temp_b1s1",
    "monitor_status_this_cycle", "throttle_b", "accel_pedal_d",
    "accel_pedal_e", "evap_vapor_pressure_abs", "fuel_rail_abs_pressure",
    "intake_air_temp_b1", "egr_temp", "boost_pressure_commanded",
    "boost_pressure_actual", "wastegate_commanded", "wastegate_actual",
)

#: Channels with no sourced mes.known_good row -- must always grade
#: "unknown", never a numeric band (no TSB/spec backs a number for them;
#: "boost at idle ~atmospheric" is not a spec either).
UNSOURCED_CHANNELS = ("evap_vapor_pressure_abs", "fuel_rail_abs_pressure",
                      "catalyst_temp_b1s1")


# --- 1. every new channel has a system key, one of the 25 ------------------

channel_to_system: dict[str, str] = {}
for sys_key, sys_def in systems_mod.SYSTEMS.items():
    for cid in sys_def.get("live_channels", []):
        channel_to_system.setdefault(cid, sys_key)

check_eq("SYSTEMS has exactly 25 keys", len(systems_mod.SYSTEMS), 25)

for cid in NEW_CHANNELS:
    sys_key = channel_to_system.get(cid)
    check(f"{cid} has a system key", sys_key is not None, repr(sys_key))
    if sys_key is not None:
        check(f"{cid}'s system key is one of the 25", sys_key in systems_mod.SYSTEMS,
             sys_key)

# spot-check a few assignments the task called out explicitly
check_eq("catalyst_temp_b1s1 -> exhaust_emissions",
        channel_to_system.get("catalyst_temp_b1s1"), "exhaust_emissions")
check_eq("commanded_egr -> exhaust_emissions (the key ALIASES already uses for egr)",
        channel_to_system.get("commanded_egr"), "exhaust_emissions")
check_eq("boost_pressure_commanded -> air_intake_boost",
        channel_to_system.get("boost_pressure_commanded"), "air_intake_boost")
check_eq("wastegate_actual -> air_intake_boost",
        channel_to_system.get("wastegate_actual"), "air_intake_boost")
check_eq("intake_air_temp_b1 -> air_intake_boost",
        channel_to_system.get("intake_air_temp_b1"), "air_intake_boost")
check_eq("fuel_rail_abs_pressure -> fuel",
        channel_to_system.get("fuel_rail_abs_pressure"), "fuel")
check_eq("throttle_b -> engine_management",
        channel_to_system.get("throttle_b"), "engine_management")
check_eq("accel_pedal_d -> engine_management",
        channel_to_system.get("accel_pedal_d"), "engine_management")
check_eq("esim_status -> evap",
        channel_to_system.get("esim_status"), "evap")

# Does the decoder/channel itself exist yet in the registry? Pending, not a
# failure, if not -- the other pass's obd.py edit hasn't landed for this name.
reg = channels_mod.registry()
for cid in NEW_CHANNELS:
    if cid not in reg:
        pending(cid, "no decoder yet in cuore.live.obd (PIDS_BY_HEX) -- "
                     "channel not yet auto-registered; system/grading wiring "
                     "above is in place regardless")
    else:
        ch = reg[cid]
        check(f"{cid} registers as a pid channel", ch.kind == "pid", ch.kind)


# --- 2. evap_test_a preset exists and resolves ------------------------------

check("evap_test_a preset is defined", "evap_test_a" in channels_mod.PRESETS)
EXPECTED_EVAP_TEST_A = ("fuel_level", "commanded_evap_purge", "evap_vapor_pressure_abs",
                        "engine_rpm", "engine_coolant_temp")
check_eq("evap_test_a preset channel list", channels_mod.PRESETS.get("evap_test_a"),
        EXPECTED_EVAP_TEST_A)

resolved = channels_mod.resolve_channels(preset="evap_test_a")
resolved_ids = {c.id for c in resolved}
check_eq("evap_test_a resolves to its 5 channels, no more/fewer",
        resolved_ids, set(EXPECTED_EVAP_TEST_A))

all_presets = channels_mod.presets()
check("evap_test_a present in presets() output", "evap_test_a" in all_presets)
if "evap_test_a" in all_presets:
    check_eq("presets() renders evap_test_a's full channel count",
            len(all_presets["evap_test_a"]), len(EXPECTED_EVAP_TEST_A))

# the ESIM switch channel: no DID exists, so it must be absent from every preset
for name, ids in channels_mod.PRESETS.items():
    check(f"preset {name!r} does not include the unknown-DID esim_status channel",
         "esim_status" not in ids)


# --- 3. grading returns "unknown" for unsourced channels --------------------

for cid in UNSOURCED_CHANNELS:
    ev = liveboard_bridge.evaluate(cid, 123.0)
    check_eq(f"{cid} (no sourced known_good row) grades unknown", ev["level"], "unknown")


# --- 4. no channel polls a DID marked unknown -------------------------------

esim = channels_mod.by_id("esim_status")
check_eq("esim_status is a did-kind channel", esim.kind, "did")
check_eq("esim_status carries the UNKNOWN_DID sentinel", esim.did, channels_mod.UNKNOWN_DID)
check("esim_status's note documents why it has no DID",
     "RoutineControl" in esim.note and "placeholder" in esim.note.lower(), esim.note)

raised = False
try:
    channels_mod.resolve_channels(channel_ids=["esim_status"])
except BadCommand:
    raised = True
check("resolve_channels refuses to poll esim_status (unknown DID)", raised)

# every other registered did-kind channel must carry a real (nonzero) DID --
# UNKNOWN_DID is reserved for documented placeholders only, never a real one
# slipping through unflagged.
for cid, ch in reg.items():
    if ch.kind == "did" and ch.did == channels_mod.UNKNOWN_DID:
        check(f"{cid} with UNKNOWN_DID is explicitly marked confidence=unknown_did",
             ch.confidence == "unknown_did", ch.confidence)
        raised_any = False
        try:
            channels_mod.resolve_channels(channel_ids=[cid])
        except BadCommand:
            raised_any = True
        check(f"resolve_channels refuses to poll {cid} (unknown DID)", raised_any)


# --- summary -----------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if pending_notes:
    print("PENDING (decoder not yet landed in cuore.live.obd -- skipped, not failed):")
    for note in pending_notes:
        print(f"  - {note}")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
