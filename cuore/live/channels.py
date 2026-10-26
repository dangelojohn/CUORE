"""The live-data channel model: a registry of everything the poller can sample.

A channel is ``{id, name, unit, source}``. Four source kinds:

* ``pid``    -- a Mode 01 PID (hex), decoded by :func:`obd.decode_pid`.
* ``did``    -- a module code + UDS DID (hex) + CarScanner formula, evaluated
  with :func:`readall.eval_formula`. Every catalogued DID for ECM, TCM, BCM,
  IPC and RFHUB (:func:`did_catalog.all_dids`) is included, at its recorded
  confidence. A DID whose formula answers with several named fields (the
  RFHUB tire DIDs: ``pressure=...; temp=...``) is expanded into one channel
  per field, sharing the one DID read.
* ``computed`` -- an arithmetic expression over other channel ids, evaluated
  by the small safe evaluator below (no ``eval()`` anywhere in this module).
* ``battery``  -- adapter ``ATRV``.
* ``probe``    -- a serial-input source that is not the OBD adapter: the ESIM
  switch probe (:mod:`cuore.live.esim_probe`, ``CUORE_ESIM_PROBE_PORT``, or
  ``sim`` for a scripted trace). Read-only, never on COM3.

:func:`available_channels` returns the whole registry; :func:`presets`
groups channel ids for one-click starts on this car.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from . import did_catalog
from .addressing import by_code
from .errors import BadCommand
from .obd import PIDS_BY_HEX

FAST_HZ = 5.0
MED_HZ = 1.0
SLOW_HZ = 0.5

#: PIDs worth sampling quickly -- the ones that change fast enough to matter
#: for a live dashboard (RPM, speed, throttle). ``throttle_b``/
#: ``accel_pedal_d``/``accel_pedal_e`` (new J1979 PIDs 47/49/4A) are added
#: here on the same reasoning as ``throttle_position`` -- pedal/throttle
#: position tracks driver input in real time. Harmless if the decoder for
#: one of these names has not landed in ``cuore.live.obd`` yet: this set is
#: just names, consulted only once the matching PID channel exists.
_FAST_PIDS = {"engine_rpm", "vehicle_speed", "throttle_position",
             "throttle_b", "accel_pedal_d", "accel_pedal_e"}
#: Slow-moving readings: temperatures, ambient/barometric pressure, fuel level.
#: ``intake_air_temp_b1`` (PID 68), ``egr_temp`` (PID 6B) and
#: ``catalyst_temp_b1s1`` (PID 3C) are new J1979 temperature PIDs added on
#: the same reasoning as ``intake_air_temp``/``engine_oil_temp`` above.
_SLOW_PIDS = {"engine_coolant_temp", "intake_air_temp", "ambient_air_temp",
             "barometric_pressure", "fuel_level", "engine_oil_temp",
             "intake_air_temp_b1", "egr_temp", "catalyst_temp_b1s1"}

#: Modules whose catalogued DIDs are worth exposing as channels.
DID_MODULES: tuple[str, ...] = ("ECM", "TCM", "BCM", "IPC", "RFHUB")


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    unit: str
    kind: str                       # "pid" | "did" | "computed" | "battery" | "probe"
    bus: str                        # "can_c" | "can_ihs" | "can_ch" | ""
    confidence: str
    default_rate_hz: float
    pid: str = ""
    module: str = ""
    did: int = 0
    formula: str = ""
    field: str = ""                 # sub-field name for a multi-field DID formula
    expr: str = ""
    depends_on: tuple[str, ...] = ()
    note: str = ""
    untrusted: bool = False         # decodes to junk on at least one car: never plot as a value

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id, "name": self.name, "unit": self.unit, "kind": self.kind,
            "bus": self.bus, "confidence": self.confidence,
            "default_rate_hz": self.default_rate_hz,
        }
        if self.kind == "pid":
            out["pid"] = self.pid
        elif self.kind == "did":
            out["module"] = self.module
            out["did"] = f"{self.did:04X}"
            if self.formula:
                out["formula"] = self.formula
            if self.field:
                out["field"] = self.field
        elif self.kind == "computed":
            out["expr"] = self.expr
            out["depends_on"] = list(self.depends_on)
        if self.note:
            out["note"] = self.note
        if self.untrusted:
            out["untrusted"] = True
        return out


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "field"


def _pid_rate(name: str) -> float:
    if name in _FAST_PIDS:
        return FAST_HZ
    if name in _SLOW_PIDS:
        return SLOW_HZ
    return MED_HZ


#: PIDs whose reply decodes to nonsense on a measured car. Channel id -> why.
UNTRUSTED_PIDS: dict[str, str] = {
    "egr_temperature": "PID 6B returned 2699.2 C on the 2018 Stelvio 2.0T (18DAF110, "
                       "2026-10-14) -- junk. Do not plot as a temperature.",
}


def _pid_channels() -> list[Channel]:
    return [
        Channel(id=spec.name, name=spec.name.replace("_", " "), unit=spec.unit,
               kind="pid", bus="can_c", confidence=("untrusted" if spec.name in UNTRUSTED_PIDS
                                                   else "legislated"),
               default_rate_hz=_pid_rate(spec.name), pid=spec.pid,
               note=UNTRUSTED_PIDS.get(spec.name, spec.description),
               untrusted=spec.name in UNTRUSTED_PIDS)
        for spec in PIDS_BY_HEX.values()
    ]


def _battery_channel() -> Channel:
    return Channel(id="battery_voltage", name="battery voltage", unit="V",
                   kind="battery", bus="can_c", confidence="legislated",
                   default_rate_hz=SLOW_HZ)


def _multi_field_names(formula: str) -> Optional[list[str]]:
    """Field names of a real multi-field formula (``a=...; b=...``).

    Distinguishes an actual multi-clause CarScanner formula from the
    ``"multi-field"`` sentinel some catalog rows use in place of a real,
    machine-parseable formula (e.g. the BCM IBS composite DID, whose fields
    are only described in prose) -- those get a single undecoded channel.
    """
    if not formula or formula == "multi-field":
        return None
    if ";" not in formula and "=" not in formula:
        return None
    names: list[str] = []
    for clause in formula.split(";"):
        clause = clause.strip()
        if not clause or "=" not in clause:
            return None
        name, _, _expr = clause.partition("=")
        name = name.strip()
        if not name:
            return None
        names.append(name)
    return names or None


def _did_channels() -> list[Channel]:
    out: list[Channel] = []
    for code in DID_MODULES:
        ecu = by_code(code)
        bus = ecu.bus_key if ecu else "can_c"
        for spec in did_catalog.all_dids(code, include_diesel=False):
            base_id = f"{code.lower()}_{spec.did:04x}"
            fields = _multi_field_names(spec.formula)
            if fields:
                for fname in fields:
                    out.append(Channel(
                        id=f"{base_id}_{_slug(fname)}", name=f"{spec.name} ({fname})",
                        unit=spec.unit, kind="did", bus=bus, confidence=spec.confidence,
                        default_rate_hz=MED_HZ, module=code, did=spec.did,
                        formula=spec.formula, field=fname, note=spec.note))
            else:
                formula = "" if spec.formula == "multi-field" else spec.formula
                out.append(Channel(
                    id=base_id, name=spec.name, unit=spec.unit, kind="did", bus=bus,
                    confidence=spec.confidence, default_rate_hz=MED_HZ, module=code,
                    did=spec.did, formula=formula, note=spec.note))
    return out


#: Sentinel used by a placeholder channel's ``did`` field to mean "no real
#: DID exists -- never poll this". A real catalogued DID is always nonzero,
#: so 0 is safe as a deliberate "unknown" marker (see :func:`resolve_channels`,
#: which refuses to add any channel using this sentinel to a poll list).
UNKNOWN_DID = 0

#: ``cuore.live.did_catalog``'s own research note: the EVAP vent/canister
#: actuator is exposed on this car as an "ESIM" (Evaporative System
#: Integrity Monitor) UDS 0x31 RoutineControl, not a readable DID -- and
#: RoutineControl is a write service, refused outright by
#: ``assert_read_only_uds`` before a byte leaves the adapter. There is no
#: DID to catalogue, so this is a documented placeholder, not a real
#: channel: present in the registry (so it is visible and self-explaining
#: rather than silently missing) but never pollable (``did=UNKNOWN_DID``;
#: :func:`resolve_channels` refuses it) and never added to any preset.
def _placeholder_channels() -> list[Channel]:
    return [
        Channel(id="esim_status", name="ESIM status (no readable DID)", unit="",
               kind="did", bus="can_c", confidence="unknown_did",
               default_rate_hz=SLOW_HZ, module="ECM", did=UNKNOWN_DID,
               note="ESIM (Evaporative System Integrity Monitor) is exposed only "
                    "as a UDS 0x31 RoutineControl, not a readable DID, per "
                    "cuore.live.did_catalog's own research note -- refused by "
                    "assert_read_only_uds before a byte leaves the adapter. "
                    "Placeholder only: resolve_channels() refuses to poll it."),
    ]


def _computed_channels() -> list[Channel]:
    return [
        Channel(id="boost", name="boost (MAP - baro)", unit="kPa", kind="computed",
               bus="can_c", confidence="computed", default_rate_hz=MED_HZ,
               expr="intake_map - barometric_pressure",
               depends_on=("intake_map", "barometric_pressure"),
               note="derived from the two legislated PIDs; compare against the "
                    "ECM absolute boost DID 195A (mbar, minus 1956 for gauge)"),
    ]


def _builtin_channels() -> list[Channel]:
    from . import esim_probe  # local: keeps the probe module out of import-time cycles
    return (_pid_channels() + _did_channels() + [_battery_channel()]
           + _computed_channels() + _placeholder_channels() + esim_probe.channels())


def builtin_channel_ids() -> set[str]:
    """Ids of every channel this project ships with -- excludes saved custom channels.

    :mod:`ui_store` uses this (not :func:`registry`) to decide whether a
    submitted custom channel id collides with something built-in -- as
    opposed to an existing custom channel of the same id simply being
    re-saved, which must be allowed.
    """
    return {c.id for c in _builtin_channels()}


def available_channels() -> list[Channel]:
    """Every channel this project knows how to sample, including saved custom ones."""
    from . import ui_store  # local: ui_store imports this module; avoid a cycle at import time
    return _builtin_channels() + ui_store.load_custom_channels()


_REGISTRY: Optional[dict[str, Channel]] = None


def registry() -> dict[str, Channel]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = {c.id: c for c in available_channels()}
    return _REGISTRY


def invalidate_registry() -> None:
    """Force the next :func:`registry`/:func:`by_id` call to recompute.

    Called after custom channels are saved so a running dashboard sees new
    custom channels (and formula/expr edits to existing ones) without a
    process restart.
    """
    global _REGISTRY
    _REGISTRY = None


def by_id(channel_id: str) -> Channel:
    ch = registry().get(channel_id)
    if ch is None:
        raise BadCommand(f"unknown channel id {channel_id!r}")
    return ch


#: One-click starts. Every id here must resolve through :func:`by_id`; a
#: mismatch would be a bug in this file, not caller input, so it is not
#: guarded -- :func:`resolve_channels` raising KeyError on a typo here during
#: development is preferable to silently dropping a channel from a preset.
PRESETS: dict[str, tuple[str, ...]] = {
    "engine_basics": ("engine_rpm", "vehicle_speed", "engine_coolant_temp",
                      "intake_air_temp", "absolute_load", "throttle_position",
                      "battery_voltage"),
    "boost": ("intake_map", "barometric_pressure", "boost", "ecm_195a"),
    "evap_job": ("commanded_evap_purge", "fuel_level", "evap_vapor_pressure",
                "evap_vapor_pressure_abs", "engine_coolant_temp", "intake_air_temp"),
    "transmission": ("tcm_04fe", "tcm_0518"),
    "tpms": ("rfhub_40b1_pressure", "rfhub_40b1_temp", "rfhub_40b2_pressure",
            "rfhub_40b2_temp", "rfhub_40b3_pressure", "rfhub_40b3_temp",
            "rfhub_40b4_pressure", "rfhub_40b4_temp"),
    # Deliberately omits "esim_status": no DID exists for it (see
    # _placeholder_channels), and resolve_channels() refuses to poll it --
    # a preset listing it would make this whole preset unresolvable.
    "evap_test_a": ("fuel_level", "commanded_evap_purge", "evap_vapor_pressure_abs",
                    "engine_rpm", "engine_coolant_temp"),
    # Load-step voltage test (see RECORDING_PRESETS / cuore.live.load_step and
    # docs/maintenance/LOAD_STEP_VOLTAGE_TEST.md). Order matters: it is the CSV
    # column order the analysis falls back on when no sidecar file is present.
    # battery_voltage = adapter ATRV at the OBD port; control_module_voltage =
    # Mode 01 PID 42 (the first ECU to answer, the ECM); bcm_1004 = BCM
    # "Battery voltage" DID (A/10, unverified formula -- but it read 14.5 V on
    # 2026-10-23 against ATRV 14.5 V). ecm_1955 is deliberately NOT here: it
    # answered requestOutOfRange (NRC 31) on this car on 2026-10-23.
    "load_step_voltage": ("battery_voltage", "control_module_voltage", "bcm_1004"),
    # ESIM switch probe during a drive cycle (docs/hardware/ESIM_SWITCH_PROBE.md):
    # the three probe channels first (they are the point), then PID 2E purge
    # duty, 06 short-term fuel trim, 0C RPM, 0D vehicle speed, 2F fuel level --
    # the context the EVAP monitor's conditions depend on. Needs
    # CUORE_ESIM_PROBE_PORT (a COM port other than COM3, or "sim").
    "esim_switch_watch": ("esim_switch_state", "esim_signal_mV", "esim_ref_mV",
                          "commanded_evap_purge", "short_fuel_trim_b1", "engine_rpm",
                          "vehicle_speed", "fuel_level"),
    # Passive purge-trim EVAP test (cuore.live.purge_trim,
    # docs/maintenance/PURGE_TRIM_TEST.md). Mode 01 only, read-only. PID 2E is
    # the ECM's COMMANDED purge %, not measured flow. The EVAP vapour-pressure
    # PID is deliberately absent: this car's ESIM system has no pressure sensor.
    # PID 04 (calculated load) has no decoder in cuore.live.obd, so the
    # supported PID 43 absolute_load stands in for "load". CSV column order.
    "purge_trim": ("commanded_evap_purge", "short_fuel_trim_b1", "long_fuel_trim_b1",
                   "engine_rpm", "intake_map", "absolute_load", "engine_coolant_temp",
                   "fuel_level", "ambient_air_temp"),
}

#: Presets that are scripted, timed recordings rather than open-ended polls.
#: ``rate_hz`` is a REQUEST: the poller has no upper clamp (only a 0.02 s idle
#: tick), so a large value means "as fast as the adapter loop can go"; the
#: achieved rate per channel is what ``live_session_status`` reports and what
#: the analysis uses (it works on timestamps, not sample counts).
LOAD_STEP_LOADS: tuple[tuple[str, str, str], ...] = (
    ("headlights", "Headlights (low beam)", "Switch the headlights ON (low beam)."),
    ("high_beam", "High beam", "Switch the HIGH BEAM on (headlights stay on)."),
    ("rear_defrost", "Rear defrost", "Press REAR DEFROST on."),
    ("blower_max", "Blower fan MAX", "Set the blower to MAXIMUM (A/C may be on or off; keep it the same for the whole test)."),
    ("heated_seats", "Heated seats HIGH", "Switch BOTH heated seats to HIGH."),
    ("brake_pedal", "Brake pedal held", "Press and HOLD the brake pedal firmly (car in P, handbrake on)."),
)


def _load_step_script() -> tuple[dict[str, Any], ...]:
    steps: list[dict[str, Any]] = [
        {"t0": 0, "t1": 20, "state": "baseline", "load": None, "label": "Baseline",
         "instruction": "Engine idling, charger OFF, every load OFF. Hands off everything."}]
    t = 20
    for lid, name, how in LOAD_STEP_LOADS:
        steps.append({"t0": t, "t1": t + 10, "state": "on", "load": lid,
                      "label": f"{name} ON", "instruction": how})
        steps.append({"t0": t + 10, "t1": t + 20, "state": "off", "load": lid,
                      "label": f"{name} OFF", "instruction": f"Switch it OFF again: {name}."})
        t += 20
    steps.append({"t0": t, "t1": t + 20, "state": "on", "load": "all",
                  "label": "ALL loads ON",
                  "instruction": "Headlights + rear defrost + blower MAX + both heated seats ON together "
                                 "(release the brake pedal)."})
    steps.append({"t0": t + 20, "t1": t + 40, "state": "recovery", "load": None,
                  "label": "All OFF (recovery)", "instruction": "Everything OFF. Hands off; recording ends at 3:00."})
    return tuple(steps)


RECORDING_PRESETS: dict[str, dict[str, Any]] = {
    "load_step_voltage": {
        "name": "Load-step voltage test",
        "preset": "load_step_voltage",
        "duration_s": 180,
        "rate_hz": 50.0,
        "read_only": True,
        "preconditions": ("Engine idling, battery charger/maintainer disconnected, parked outdoors "
                          "or ventilated, handbrake on, car in P, all loads off."),
        "settle_s": 3.0,
        "reference_window_s": 6.0,
        "excess_drop_limit_v": 0.3,
        "script": _load_step_script(),
        "doc": "docs/maintenance/LOAD_STEP_VOLTAGE_TEST.md",
    },
    # Drive-cycle watch, no script: the driver drives, the probe logs whether
    # the ECM's EVAP test ever closes the ESIM switch. Rows are written at the
    # probe's 20 Hz; the PIDs ride along at their own rates.
    "esim-switch-watch": {
        "name": "ESIM switch watch (drive cycle)",
        "preset": "esim_switch_watch",
        "duration_s": 3600,
        "rate_hz": 20.0,
        "rates_hz": {"esim_switch_state": 20.0, "esim_signal_mV": 20.0, "esim_ref_mV": 20.0,
                     "commanded_evap_purge": 2.0, "short_fuel_trim_b1": 1.0,
                     "engine_rpm": 2.0, "vehicle_speed": 2.0, "fuel_level": 0.2},
        "read_only": True,
        "preconditions": ("ESIM probe fitted and bench-validated (docs/hardware/ESIM_SWITCH_PROBE.md); "
                          "CUORE_ESIM_PROBE_PORT set to the probe's port (never COM3), or 'sim' to "
                          "rehearse. Never clear codes before or during the drive."),
        "script": (),
        "doc": "docs/hardware/ESIM_SWITCH_PROBE.md",
    },
    "purge_trim": {
        "name": "Purge-trim EVAP test (passive)",
        "preset": "purge_trim",
        "duration_s": 240,
        "rate_hz": 10.0,
        # per-channel requests (Hz); the poller serves them as fast as the adapter loop allows
        "rates_hz": {"commanded_evap_purge": 10.0, "short_fuel_trim_b1": 10.0, "engine_rpm": 10.0,
                     "long_fuel_trim_b1": 2.0, "intake_map": 5.0, "absolute_load": 5.0,
                     "engine_coolant_temp": 0.5, "fuel_level": 0.5, "ambient_air_temp": 0.2},
        "read_only": True,
        "preconditions": ("Engine idling and fully warm, battery charger/maintainer disconnected, "
                          "parked outdoors or ventilated, handbrake on, car in P, A/C and all loads off. "
                          "Do not touch the throttle. The ECM opens the purge valve by itself when its "
                          "conditions allow; the test only watches."),
        "on_threshold_pct": 1.0,
        "dip_window_s": 10.0,
        "dip_baseline_s": 5.0,
        "dip_response_pct": 3.0,
        "script": ({"t0": 0, "t1": 240, "state": "watch", "load": None, "label": "Idle, hands off",
                    "instruction": ("Engine idling warm, charger OFF, no loads (lights, A/C, defrost, "
                                    "blower, seats OFF). Do not touch the throttle or any switch. "
                                    "Recording ends at 4:00.")},),
        "doc": "docs/maintenance/PURGE_TRIM_TEST.md",
    },
}


def recording_presets() -> dict[str, dict[str, Any]]:
    """Scripted recording presets as plain dicts (script tuples to lists)."""
    return {k: {**v, "script": [dict(s) for s in v["script"]],
                "channels": list(PRESETS.get(v["preset"], ()))}
            for k, v in RECORDING_PRESETS.items()}


#: Offerable channel groups that are not one-click polls (their items mix
#: channels, Mode 06 monitors and manual readings). ``evidence`` is "evidence"
#: (can support a conclusion) or "weak" (trend hint only). Intake-valve
#: deposits on a DI engine cannot be computed from any data -- borescope only.
CHANNEL_GROUPS: dict[str, dict[str, Any]] = {
    "deposit_risk_trend": {
        "name": "Intake-valve deposit risk (trend proxies)",
        "note": "Direct-injection engine: deposits are not calculable from data; "
                "borescope is the only direct check. Compare like with like "
                "(same coolant temp, RPM, load).",
        "items": (
            {"label": "Per-cylinder misfire counts, cold start", "source": "mode06",
             "obdmids": ("A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "AA", "AB", "AC", "AD"),
             "evidence": "evidence"},
            {"label": "Warm-idle LTFT at same coolant temp", "source": "channel",
             "channels": ("long_fuel_trim_b1", "engine_coolant_temp"), "evidence": "weak"},
            {"label": "Volumetric-efficiency ratio MAF vs MAP/RPM at fixed RPM/load",
             "source": "channel", "channels": ("maf", "intake_map", "engine_rpm"),
             "evidence": "weak"},
            {"label": "Oil consumption / catch-can volume per km", "source": "manual",
             "evidence": "weak"},
        ),
    },
}


def channel_groups() -> dict[str, dict[str, Any]]:
    """Group definitions as plain dicts (tuples to lists) for the live board."""
    return {k: {**g, "items": [{**i, **{f: list(v) for f, v in i.items()
                                        if isinstance(v, tuple)}} for i in g["items"]]}
            for k, g in CHANNEL_GROUPS.items()}


def presets() -> dict[str, list[dict[str, Any]]]:
    reg = registry()
    return {name: [reg[cid].to_dict() for cid in ids if cid in reg]
            for name, ids in PRESETS.items()}


# ===========================================================================
# per-bus capture presets -- what a bypass cable unlocks, catalogue only
# ===========================================================================
#
# Distinct from PRESETS above: those are active-poll channel groups for the
# dashboard (a Mode 01 PID or a UDS DID the adapter is asked for at a rate).
# These describe what a *bus capture* (passive listen, see
# :mod:`cuore.live.buscapture`) is worth starting on CAN-IHS/CAN-CH once a
# bypass cable is declared. Every wanted item resolves against
# :data:`did_catalog.BROADCAST_SIGNALS` (public passive-signal research) or
# an accepted :mod:`cuore.live.learned` broadcast entry for the VIN -- never
# invented. An item with neither is reported ``"unknown_did"`` and is never
# polled or implied to exist.

#: ``bus``/``cable`` say what :func:`cuore.live.buses.route_for` must allow
#: before this preset may start. ``wanted`` is ``(label, signal_name)``;
#: ``signal_name`` is a ``did_catalog.BROADCAST_SIGNALS`` ``"signal"`` value,
#: or ``None`` when no public broadcast-signal source was found for it (the
#: item is still listed, as ``"unknown_did"``, never silently dropped).
BUS_CAPTURE_PRESETS: dict[str, dict[str, Any]] = {
    "chassis_a6": {
        "bus": "can_ch", "cable": "grey_a6",
        "name": "Chassis / ADAS (CAN-CH)",
        "wanted": (
            ("Wheel speed FL", "WHEEL_SPEED_FL"),
            ("Wheel speed FR", "WHEEL_SPEED_FR"),
            ("Wheel speed RL", "WHEEL_SPEED_RL"),
            ("Wheel speed RR", "WHEEL_SPEED_RR"),
            ("Brake pressure", None),
            ("Steering angle", "STEERING_ANGLE"),
            ("Yaw rate", "YAW_RATE"),
        ),
    },
    "body_a5": {
        "bus": "can_ihs", "cable": "blue_a5",
        "name": "Body / comfort (CAN-IHS)",
        "wanted": (
            ("HVAC temperature", None),
            ("Battery monitor", None),
            ("Driver door state", None),
            ("Passenger door state", None),
        ),
    },
}


def bus_capture_preset(name: str, vin: str = "") -> dict[str, Any]:
    """One bus-capture preset: its bus/cable requirement and every wanted
    item resolved against the broadcast-signal catalogue, then (for anything
    the catalogue does not cover) this VIN's accepted learned broadcast
    signals. Never invents a scale or a channel for an item neither source
    has -- that item comes back ``status: "unknown_did"``."""
    spec = BUS_CAPTURE_PRESETS.get(name)
    if spec is None:
        raise BadCommand(f"unknown bus-capture preset {name!r}; one of "
                         f"{sorted(BUS_CAPTURE_PRESETS)}")
    by_signal = {s["signal"]: s for s in did_catalog.BROADCAST_SIGNALS}
    learned_by_name: dict[str, Any] = {}
    if vin:
        from . import learned as learned_mod
        for e in learned_mod.learned_broadcast(vin, bus=spec["bus"]).get(vin, []):
            learned_by_name[(e.get("name") or "").lower()] = e

    items: list[dict[str, Any]] = []
    for label, signal_key in spec["wanted"]:
        sig = by_signal.get(signal_key) if signal_key else None
        learned_entry = learned_by_name.get(label.lower())
        if sig is not None:
            items.append({
                "label": label, "status": "known", "signal": signal_key,
                "can_id": sig["can_id"], "unit": sig.get("unit", ""),
                "confidence": sig.get("confidence", "unverified"),
                "source": sig.get("source", ""), "note": sig.get("note", ""),
            })
        elif learned_entry is not None:
            items.append({
                "label": label, "status": "learned", "can_id": learned_entry.get("id"),
                "field": learned_entry.get("field"), "scale": learned_entry.get("scale"),
                "note": "learned, unscaled",
            })
        else:
            items.append({"label": label, "status": "unknown_did",
                          "note": "no DID or broadcast signal in the catalogue, and nothing "
                                  "learned yet for this VIN -- not polled"})
    return {"preset": name, "name": spec["name"], "bus": spec["bus"],
           "cable_required": spec["cable"], "items": items}


def resolve_channels(channel_ids: Optional[list[str]] = None, preset: str = "") -> list[Channel]:
    """``channel_ids`` and/or a named preset, deduplicated, computed channels'
    dependencies pulled in automatically so they are always polled too."""
    chosen: list[str] = []
    if preset and preset not in PRESETS and preset.replace("-", "_") in PRESETS:
        preset = preset.replace("-", "_")   # "esim-switch-watch" == "esim_switch_watch"
    if preset:
        if preset not in PRESETS:
            raise BadCommand(f"unknown preset {preset!r}; one of {sorted(PRESETS)}")
        chosen.extend(PRESETS[preset])
    for cid in (channel_ids or []):
        if cid not in chosen:
            chosen.append(cid)
    if not chosen:
        raise BadCommand("pass channels=[...] or preset=...")

    result: list[Channel] = []
    seen: set[str] = set()

    def add(cid: str) -> None:
        if cid in seen:
            return
        ch = by_id(cid)
        if ch.kind == "did" and ch.did == UNKNOWN_DID:
            raise BadCommand(
                f"channel {cid!r} has no readable DID ({ch.note or 'unknown DID'}); "
                "it cannot be polled")
        seen.add(cid)
        for dep in ch.depends_on:
            add(dep)
        result.append(ch)

    for cid in chosen:
        add(cid)
    return result


# ===========================================================================
# the computed-channel evaluator: arithmetic over channel ids, no eval()
# ===========================================================================

class ComputedError(Exception):
    """Raised for anything outside the safe arithmetic grammar below."""


_OPS = frozenset("+-*/()")


def _tokenize_expr(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in _OPS:
            tokens.append((c, c))
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            seen_dot = False
            while j < n and (text[j].isdigit() or (text[j] == "." and not seen_dot)):
                seen_dot = seen_dot or text[j] == "."
                j += 1
            tokens.append(("NUM", text[i:j]))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(("ID", text[i:j]))
            i = j
            continue
        raise ComputedError(f"unsupported character {c!r} in expression {text!r}")
    return tokens


# AST nodes: ("num", value) | ("ref", channel_id) | ("unary", op, node)
# | ("binop", op, left, right)

class _ExprParser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> tuple[Optional[str], Optional[str]]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _advance(self) -> tuple[Optional[str], Optional[str]]:
        tok = self._peek()
        self.pos += 1
        return tok

    def _expect(self, kind: str) -> None:
        got, _ = self._advance()
        if got != kind:
            raise ComputedError(f"expected {kind!r}, found {got!r}")

    def parse(self):
        node = self._expr()
        if self.pos != len(self.tokens):
            raise ComputedError(f"unexpected trailing input at token {self.pos}")
        return node

    def _expr(self):
        node = self._term()
        while self._peek()[0] in ("+", "-"):
            op, _ = self._advance()
            node = ("binop", op, node, self._term())
        return node

    def _term(self):
        node = self._factor()
        while self._peek()[0] in ("*", "/"):
            op, _ = self._advance()
            node = ("binop", op, node, self._factor())
        return node

    def _factor(self):
        kind, _ = self._peek()
        if kind in ("+", "-"):
            self._advance()
            return ("unary", kind, self._factor())
        return self._primary()

    def _primary(self):
        kind, val = self._advance()
        if kind == "NUM":
            return ("num", float(val))
        if kind == "ID":
            return ("ref", val)
        if kind == "(":
            node = self._expr()
            self._expect(")")
            return node
        raise ComputedError(f"unexpected token {kind!r}")


def _eval_node(node, values: dict[str, float]) -> float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "ref":
        v = values.get(node[1])
        if v is None:
            raise ComputedError(f"expression references unavailable channel {node[1]!r}")
        return v
    if kind == "unary":
        v = _eval_node(node[2], values)
        return -v if node[1] == "-" else v
    if kind == "binop":
        op = node[1]
        left = _eval_node(node[2], values)
        right = _eval_node(node[3], values)
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise ComputedError("division by zero")
            return left / right
    raise ComputedError(f"malformed AST node {node!r}")  # pragma: no cover - defensive


def eval_expr(expr: str, values: dict[str, float]) -> float:
    """Evaluate a computed-channel expression over ``{channel_id: value}``.

    Arithmetic only (``+ - * /``, parentheses, unary minus, numbers and
    channel-id identifiers) -- there is no ``eval()`` anywhere in this
    module, so an expression outside the grammar simply cannot execute.
    """
    text = expr.strip()
    if not text:
        raise ComputedError("empty expression")
    try:
        return _eval_node(_ExprParser(_tokenize_expr(text)).parse(), values)
    except (ValueError, RecursionError) as exc:   # lone "." number; absurd paren nesting
        raise ComputedError(f"malformed expression {text[:80]!r}: {exc}") from exc


__all__ = ["Channel", "available_channels", "registry", "invalidate_registry",
          "builtin_channel_ids", "by_id", "PRESETS", "presets",
          "RECORDING_PRESETS", "recording_presets", "LOAD_STEP_LOADS",
          "BUS_CAPTURE_PRESETS", "bus_capture_preset", "UNTRUSTED_PIDS",
          "CHANNEL_GROUPS", "channel_groups",
          "resolve_channels", "ComputedError", "eval_expr", "DID_MODULES",
          "FAST_HZ", "MED_HZ", "SLOW_HZ", "UNKNOWN_DID"]
