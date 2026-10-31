"""The liveboard: a read-only, at-a-glance board of live channels grouped by
system, each value graded against :mod:`mes.known_good`, with a short
sourced recommendation -- built so a passenger (never the driver) can watch
the car safely while someone else drives.

Three things this module does, and nothing else:

* :func:`board` -- the channel layout for one VIN: every ``can_c`` channel
  (the poller serves no other bus), grouped into a fixed set of plain
  categories, each with its per-channel poll rate and its sourced
  known-good band, if it has one.
* :func:`evaluate` / :func:`snapshot_recommendations` -- grade a live value
  (or a whole snapshot of them) against that same sourced band. Never
  invents a limit: a channel with no sourced row, or only a documented
  ``UNKNOWN`` one, always grades ``"unknown"``.
* :func:`attach_snapshot_to_job` -- score a saved liveboard snapshot
  against the vehicle's current job: an out-of-range reading becomes
  evidence for (or seeds) a matching open hypothesis, an in-range reading
  becomes evidence against one, and a fuel level inside the EVAP
  verification window becomes evidence that an EVAP hypothesis can actually
  be checked right now.
* :func:`freeze_capture_start` / :func:`freeze_capture_status` /
  :func:`freeze_capture_stop` / :func:`freeze_capture_save` /
  :func:`freeze_capture_discard` -- the Freeze frame panel's own read-then-
  save flow: Mode 03 stored codes, then every supported PID's freeze frame
  and a Mode 01 snapshot of the same PIDs, plus readiness, read in a
  background thread so Stop can cut it short; held server-side for 30
  minutes (unsaved) so Save works as a plain HTML form post, with no
  client-held payload. See that group's own docstrings for the on-disk
  observation shapes, which deliberately mirror ``cuore.live.ops``'s own
  per-call return shapes (not a bespoke one) so :mod:`cuore.live.scanlog`'s
  existing cluster-builders -- read, never edited here -- pick them up with
  no changes on that side.

Reuses :mod:`cuore.services.known_good_bridge` for every band (never touches
``mes.known_good`` directly -- that module's docstring reserves it to
``known_good_bridge`` alone) and :mod:`mes.systems` for the channel-to-system
mapping every grouping/evidence decision here is built on. ``mes.jobs`` is
touched directly for the one write path (:func:`attach_snapshot_to_job`),
the same posture ``cuore.services.jobs_bridge`` uses for the rest of the Job
workflow -- this module owns only the live-telemetry side of that ledger.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live import capture as capture_mod
from ..live import channels as channels_mod
from ..live import chassis_decode
from ..live.buses import CAN_CH, routes_for
from ..live import ops as live_ops
from ..live import store as live_store
from ..live.errors import LiveError
from . import known_good_bridge
from .errors import BadRequest, NotFound

try:  # additive: MES-recording-sourced channels, never required for the board
    from . import mes_recordings_bridge
except Exception:  # noqa: BLE001
    mes_recordings_bridge = None

from mes import jobs as jobs_mod  # noqa: E402
from mes import systems as systems_mod  # noqa: E402
from mes.service_specs import TECHAUTHORITY  # noqa: E402

try:  # defensive: this module is being built in parallel by another agent
    from ..live import scanlog as scanlog_mod
except Exception:  # noqa: BLE001 -- Save must still work with a bare computed id
    scanlog_mod = None

NOTICE = "Read-only session. In motion, a passenger operates this page."

GROUP_ORDER: tuple[str, ...] = (
    "temperatures", "speed_rpm", "pressure_boost", "voltage",
    "fuel_air", "emissions", "gearbox", "tyres", "probe", "other",
)

GROUP_LABELS: dict[str, str] = {
    "temperatures": "Temperatures",
    "speed_rpm": "Speed & RPM",
    "pressure_boost": "Pressure & boost",
    "voltage": "Voltage",
    "fuel_air": "Fuel & air",
    "emissions": "Emissions",
    "gearbox": "Gearbox",
    "tyres": "Tyres",
    "probe": "ESIM probe (external, serial)",
    "other": "Other",
}

#: Recommendation text this module can speak with authority -- lifted
#: straight from the sourced ``mes.known_good`` row's own notes for the two
#: channels where this research pass already settled on plain wording.
#: Every other out-of-range channel falls back to the generic, still-sourced
#: "outside the sourced range (source)" line built in :func:`evaluate`.
_SPECIFIC_TEXT: dict[str, dict[str, str]] = {
    "engine_coolant_temp": {
        "excessive": "Too hot: stop and check coolant level, fans and thermostat",
        "moderate": "Running warm: watch coolant level, fans and thermostat",
    },
    "battery_voltage": {
        "excessive": "Charging low: alternator/belt/grounds",
        "moderate": "Charging low: alternator/belt/grounds",
    },
}

#: The EVAP job's own fuel-level verification window (see
#: ``mes.known_good.fuel_level``'s notes: vapor-pressure behaviour is read
#: relative to fuel level, and a near-full/near-empty tank is not a usable
#: reading for that check).
_FUEL_CHANNEL = "fuel_level"
_FUEL_VERIFY_WINDOW = (15.0, 85.0)


# ===========================================================================
# channel -> system
# ===========================================================================

_SYSTEM_BY_CHANNEL: Optional[dict[str, str]] = None


def _channel_system_map() -> dict[str, str]:
    global _SYSTEM_BY_CHANNEL
    if _SYSTEM_BY_CHANNEL is None:
        out: dict[str, str] = {}
        for sys_key, sys_def in systems_mod.SYSTEMS.items():
            for cid in sys_def.get("live_channels", []):
                out.setdefault(cid, sys_key)  # first system to claim a channel wins
        _SYSTEM_BY_CHANNEL = out
    return _SYSTEM_BY_CHANNEL


def channel_system(channel_id: str) -> Optional[str]:
    """The :mod:`mes.systems` key whose ``live_channels`` names this
    channel, or ``None`` if no system claims it."""
    return _channel_system_map().get(channel_id)


# ===========================================================================
# 1. board: channel layout, grouped, rated, banded
# ===========================================================================

def _classify(ch: Any) -> str:
    if ch.kind == "probe":
        return "probe"
    name = (ch.name or "").lower()
    unit = (ch.unit or "").strip().lower()
    if unit in ("c", "deg c") or "temp" in name:
        return "temperatures"
    if unit == "rpm" or "rpm" in name:
        return "speed_rpm"
    if unit in ("km/h", "mph") or "speed" in name:
        return "speed_rpm"
    if unit in ("kpa", "psi", "bar") or "pressure" in name or "boost" in name or "map" in name:
        return "pressure_boost"
    if unit == "v" or "voltage" in name or "state of charge" in name:
        return "voltage"
    if "lambda" in name or "o2" in name or "purge" in name or "evap" in name:
        return "emissions"
    if ch.module == "TCM" or "gearbox" in name or "transmission" in name or "gear" in name:
        return "gearbox"
    if ch.module == "RFHUB" or "tyre" in name or "tire" in name:
        return "tyres"
    if unit == "%" and any(k in name for k in ("fuel", "throttle", "load")):
        return "fuel_air"
    return "other"


def _board_band(channel_id: str, vin: str = "") -> Optional[dict[str, Any]]:
    """The widget-ready band plus its ``direction`` -- ``sourced_band``
    itself omits ``direction`` (gauges don't need it); the liveboard's own
    per-channel recommendation does, so it is added back here from the raw
    row. ``None`` for anything ``sourced_band`` would also call ``None``
    (no row, only a documented UNKNOWN one, or -- given ``vin`` -- a row
    that does not apply to this VIN's marque/platform)."""
    band = known_good_bridge.sourced_band(channel_id, vin=vin)
    if band is None:
        return None
    row = known_good_bridge.known_good_for(channel_id, vin=vin) or {}
    return {
        "normal": band.get("normal"),
        "warn": band.get("warn"),
        "alarm": band.get("alarm"),
        "direction": row.get("direction"),
        "confidence": band.get("confidence"),
        "source": band.get("source"),
    }


def board(vin: str = "") -> dict[str, Any]:
    """The liveboard layout: every ``can_c`` channel, grouped, rated and
    banded, plus two kinds of read-only extras that are never polled: MES-
    recording-sourced channels (:data:`recording_channels`, not
    per-vehicle) and this vehicle's own learned-but-unscaled TCM DIDs
    (:data:`learned_did_channels`, from :func:`cuore.live.fullscan`'s
    discovery sweep -- this is the one part of the board that is actually
    per-``vin``; every sourced band here is otherwise the same reference
    regardless of which car is asked about)."""
    channels = [c for c in channels_mod.available_channels()
                if c.bus == "can_c" or c.kind == "probe"]
    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUP_ORDER}
    rates: dict[str, float] = {}
    all_ids: list[str] = []
    for ch in channels:
        entry = {
            "id": ch.id, "name": ch.name, "unit": ch.unit,
            "rate_hz": ch.default_rate_hz,
            "band": _board_band(ch.id, vin=vin),
            "system": channel_system(ch.id),
        }
        by_group[_classify(ch)].append(entry)
        # A placeholder with no readable DID (e.g. esim_status, a 0x31
        # routine only) is shown but never polled: resolve_channels()
        # refuses it, and one refused id fails the whole session start.
        if ch.kind == "did" and ch.did == channels_mod.UNKNOWN_DID:
            continue
        rates[ch.id] = ch.default_rate_hz
        all_ids.append(ch.id)
    groups = [{"id": g, "label": GROUP_LABELS[g], "channels": by_group[g]}
             for g in GROUP_ORDER if by_group[g]]
    # Recording-sourced channels (kind "recording", source "MES") are never
    # polled -- deliberately kept out of all_channel_ids/rates, which drive
    # the live poller, and out of groups/by_group, which are "this bus is
    # live right now" by construction. Listed separately so a page can
    # still show them (labelled "from MES recording ...", never mixed into
    # a gauge that implies a live reading) without the poller ever seeing
    # one of these ids. See cuore.services.mes_recordings_bridge.
    recording_channels: list[dict[str, Any]] = []
    if mes_recordings_bridge is not None:
        try:
            recording_channels = mes_recordings_bridge.transmission_recording_channels()
        except Exception:  # noqa: BLE001 -- the live board must render with or without these
            recording_channels = []
    # Learned-but-unscaled TCM DIDs (cuore.live.fullscan's read-only
    # discovery sweep, cuore.live.learned.record_did_answer): raw bytes
    # only, never a meaning, so the board must show these as "learned,
    # unscaled -- name it while watching MES", never alongside a graded
    # value that implies a decoded one.
    learned_did_channels: list[dict[str, Any]] = []
    if vin:
        try:
            from ..live import learned as learned_mod
            rows = learned_mod.learned_did_discovery(vin, module="TCM").get(vin, [])
            learned_did_channels = [{
                "id": f"tcm_did_{r.get('did', '').lower()}",
                "name": f"TCM DID {r.get('did')}", "kind": "did", "module": "TCM",
                "scale": "unknown", "bytes": r.get("bytes") or [],
                "system": "transmission_driveline", "at": r.get("at"),
                "label": "learned, unscaled -- name it while watching MES",
            } for r in rows]
        except Exception:  # noqa: BLE001 -- the live board must render with or without these
            learned_did_channels = []
    return {"groups": groups, "all_channel_ids": all_ids, "rates": rates,
           "notice": NOTICE, "recording_channels": recording_channels,
           "learned_did_channels": learned_did_channels}


# ===========================================================================
# 2 & 3. evaluate / snapshot_recommendations
# ===========================================================================

def _grade(value: float, normal: Optional[list[float]], alarm: Optional[list[float]],
          direction: str) -> str:
    """Inside the sourced normal band = ok; between normal and alarm =
    moderate; beyond alarm = excessive; no normal band at all = unknown.

    Graded on the side(s) ``direction`` says matter: only the high side for
    "above" (e.g. coolant temp), only the low side for "below", both sides
    for "both" (e.g. battery voltage, which is unhealthy too high or too
    low) -- using the row's own normal/alarm numbers on whichever side is
    violated, never a gauge-only simplification.
    """
    if not normal:
        return "unknown"
    lo, hi = normal
    a_lo, a_hi = (alarm or (None, None))
    if direction == "above":
        if value <= hi:
            return "ok"
        return "excessive" if (a_hi is not None and value > a_hi) else "moderate"
    if direction == "below":
        if value >= lo:
            return "ok"
        return "excessive" if (a_lo is not None and value < a_lo) else "moderate"
    # "both": either side of the normal envelope is graded the same way
    if lo <= value <= hi:
        return "ok"
    if value < lo:
        return "excessive" if (a_lo is not None and value < a_lo) else "moderate"
    return "excessive" if (a_hi is not None and value > a_hi) else "moderate"


def _channel_name(channel_id: str) -> str:
    try:
        return channels_mod.by_id(channel_id).name
    except Exception:  # noqa: BLE001 -- grading must work for any id a caller sends
        return channel_id


def evaluate(channel_id: str, value: float, vin: str = "") -> dict[str, Any]:
    """Grade one live value against its sourced known-good band.

    ``sourced_band`` gates whether this channel has anything usable at all
    (``None`` for no row, or a documented UNKNOWN one); the raw row's own
    ``normal``/``alarm``/``direction`` -- not the gauge-shaped band, which
    nulls warn/alarm for a "both"-direction row -- drive the actual grade,
    since a two-sided row like battery voltage is still graded on both
    sides here. Never invents a limit.

    Pass ``vin`` to also gate on marque/platform (:func:`mes.known_good.
    bands_for_vin`): a channel whose only row does not apply to this VIN
    grades "unknown" exactly like a channel with no row at all, but with
    wording that says so -- distinct from the plain "nothing sourced
    anywhere" text used when the row is missing/UNKNOWN regardless of vin.
    """
    name = _channel_name(channel_id)
    gate = known_good_bridge.sourced_band(channel_id, vin=vin)
    if gate is None:
        if vin and known_good_bridge.sourced_band(channel_id) is not None:
            # A sourced band exists, just not for this VIN's marque/
            # platform -- never say "no sourced reference range" here,
            # that would imply nothing was ever researched for it.
            return {"level": "unknown",
                    "text": f"No reference band on file for this model for "
                            f"{name} -- {TECHAUTHORITY}."}
        return {"level": "unknown",
                "text": f"No sourced reference range for {name}; the sourced-range "
                        "check cannot be made."}
    row = known_good_bridge.known_good_for(channel_id, vin=vin) or {}
    direction = row.get("direction") or "both"
    level = _grade(float(value), row.get("normal"), row.get("alarm"), direction)
    source = row.get("source") or "sourced range"
    if level == "ok":
        text = f"Within the sourced normal range ({source})."
    else:
        text = _SPECIFIC_TEXT.get(channel_id, {}).get(level) or \
            f"Outside the sourced range ({source})."
    return {"level": level, "text": text}


_LEVEL_ORDER = {"excessive": 0, "moderate": 1, "unknown": 2, "ok": 3}


def snapshot_recommendations(values: dict[str, float], vin: str = "") -> list[dict[str, Any]]:
    """Every value in ``values`` (``{channel_id: value}``), graded, excessive
    first. Pass ``vin`` to grade against that VIN's marque/platform-gated
    bands (see :func:`evaluate`); omitted, grading is unfiltered as before."""
    out: list[dict[str, Any]] = []
    for cid, value in values.items():
        try:
            ch = channels_mod.by_id(cid)
            name, unit = ch.name, ch.unit
        except Exception:  # noqa: BLE001 -- grade whatever id was actually sent
            name, unit = cid, ""
        ev = evaluate(cid, value, vin=vin)
        out.append({"id": cid, "name": name, "value": value, "unit": unit,
                   "level": ev["level"], "text": ev["text"]})
    out.sort(key=lambda r: _LEVEL_ORDER.get(r["level"], 9))
    return out


# ===========================================================================
# 4. attach_snapshot_to_job: score a saved snapshot against the current job
# ===========================================================================

def _live_ref(snapshot_id: str, name: str, value: float, unit: str, level: str,
             source: str) -> dict[str, Any]:
    unit_s = f" {unit}" if unit else ""
    return {"kind": "live", "id": snapshot_id,
            "label": f"{name} {value:g}{unit_s}: {level} ({source})"}


def attach_snapshot_to_job(vin: str, snapshot_id: str,
                           values: dict[str, float]) -> dict[str, Any]:
    """Score one saved liveboard snapshot against the vehicle's current job.

    For every channel graded ``excessive`` or ``moderate``
    (:func:`evaluate`), mapped to a system via :func:`channel_system`
    (built from ``mes.systems.SYSTEMS[*]["live_channels"]``): attach a
    ``live`` evidence ref to a matching OPEN hypothesis if one exists, else
    seed a new suggested hypothesis for that system with the ref already
    attached. A value graded ``ok`` on a system that already has an open
    hypothesis is attached as evidence AGAINST it. A fuel level inside the
    EVAP verification window is attached as evidence FOR an open EVAP
    hypothesis specifically, regardless of fuel's own generic system
    mapping. One job action records the pass as a whole. Raises
    :class:`~cuore.services.errors.BadRequest` if there is no open job for
    this VIN -- nothing here opens one.
    """
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    job = jobs_mod.current(vin)
    if job is None:
        raise NotFound(f"no open job for {vin!r}; open one before attaching live evidence")
    job_id = job["id"]

    def _open_hyp(sys_key: str) -> Optional[dict[str, Any]]:
        current = jobs_mod.get(job_id)
        want = sys_key.strip().lower()
        for h in current.get("hypotheses", []):
            if h.get("status") == "open" and (h.get("system") or "").strip().lower() == want:
                return h
        return None

    recs = snapshot_recommendations(values, vin=vin)
    out_of_range = 0
    attached: list[dict[str, Any]] = []
    new_hypotheses: list[dict[str, Any]] = []

    for rec in recs:
        cid, level, value = rec["id"], rec["level"], rec["value"]
        row = known_good_bridge.known_good_for(cid, vin=vin) or {}
        source = row.get("source") or "sourced range"

        if cid == _FUEL_CHANNEL and _FUEL_VERIFY_WINDOW[0] <= value <= _FUEL_VERIFY_WINDOW[1]:
            evap_hyp = _open_hyp("evap")
            if evap_hyp is not None:
                ref = {"kind": "live", "id": snapshot_id,
                      "label": f"Fuel level {value:g}% in the "
                               f"{_FUEL_VERIFY_WINDOW[0]:g}-{_FUEL_VERIFY_WINDOW[1]:g}% "
                               "window: verification possible"}
                jobs_mod.attach(job_id, ref, hyp_id=evap_hyp["id"], supports=True)
                attached.append({"hyp_id": evap_hyp["id"], "ref": ref})

        if level in ("excessive", "moderate"):
            out_of_range += 1
            sys_key = channel_system(cid)
            if sys_key is None:
                continue
            ref = _live_ref(snapshot_id, rec["name"], value, rec["unit"], level, source)
            hyp = _open_hyp(sys_key)
            if hyp is not None:
                jobs_mod.attach(job_id, ref, hyp_id=hyp["id"], supports=True)
                attached.append({"hyp_id": hyp["id"], "ref": ref})
            else:
                label = systems_mod.SYSTEMS.get(sys_key, {}).get("label", sys_key)
                text = f"{label}: live {rec['name']} out of range"
                next_test = row.get("notes") or ""
                new_hyp = jobs_mod.add_hypothesis(job_id, text, system=sys_key,
                                                  next_test=next_test)
                jobs_mod.attach(job_id, ref, hyp_id=new_hyp["id"], supports=True)
                new_hypotheses.append(new_hyp)
                attached.append({"hyp_id": new_hyp["id"], "ref": ref})
        elif level == "ok":
            sys_key = channel_system(cid)
            if sys_key is None:
                continue
            hyp = _open_hyp(sys_key)
            if hyp is not None:
                ref = _live_ref(snapshot_id, rec["name"], value, rec["unit"], level, source)
                jobs_mod.attach(job_id, ref, hyp_id=hyp["id"], supports=False)
                attached.append({"hyp_id": hyp["id"], "ref": ref})

    action_ref = {"kind": "live", "id": snapshot_id,
                 "label": f"{out_of_range} value(s) out of range"}
    jobs_mod.add_action(job_id, "test",
                        f"Live snapshot {snapshot_id}: {out_of_range} values out of range",
                        ref=action_ref)

    return {"job_id": job_id, "out_of_range": out_of_range,
           "attached": attached, "new_hypotheses": new_hypotheses}


# ===========================================================================
# 5. Freeze frame: capture (Start/Stop), status, Save to the CUORE log,
#    Discard
# ===========================================================================
#
# Owner's ask: capture a full freeze frame (every stored code's Mode 03,
# every PID in the ECM's supported bitmap via Mode 02, a Mode 01 snapshot
# of the same PIDs, and readiness) with Start/Stop, hold it unsaved on the
# page, then Save it into the CUORE log as from-car observations.
#
# Every ``cuore.live.ops`` call this makes (``obd_dtcs``, ``obd_supported_pids``,
# ``obd_readiness``, ``obd_pid``, ``obd_freeze_frame``) is already wrapped
# with the poller guard and the MES-connected guard (``_obd_session``/
# ``_poller_active_guard`` in that module) -- nothing here re-implements
# those refusals, the first ``obd_dtcs`` call below simply surfaces them
# (as the existing ``Refused``/``LinkUnavailable`` text) before any
# background work starts.
#
# A capture is held server-side (``_CAPTURES``, keyed by capture id) for
# ``_CAPTURE_TTL`` so Save can be a plain HTML form post of just the id --
# no client-held payload -- and so Start/Stop can run the actual reads in a
# background thread with a cancel flag, cut short cleanly by Stop.
#
# On Save, the raw per-call ``ops`` results captured are written through
# unchanged via :func:`cuore.live.store.record_observation` under kinds
# ``"obd_dtcs"``, ``"freeze_frame"`` (one per PID read, same shape
# ``ops.obd_freeze_frame`` already returns) and ``"pid"`` (one per PID,
# same shape ``ops.obd_pid`` already returns), plus ``"readiness"`` --
# deliberately the same shapes :mod:`cuore.live.scanlog` already clusters
# into browsable scans (see that module's ``_build_dtcs``/
# ``_build_freeze_frames``/``_build_pids``/``_build_readiness``), so the
# Scans area shows this capture with no changes to that module. ``stream``
# is stamped ``"serial (freeze frame capture)"`` on every row -- this path
# never has a demo/synthetic source, every reading came from a live
# ``ops`` call against the real adapter or this capture would already have
# been refused -- which satisfies ``store.is_from_car`` (its own check is
# just "does ``stream`` start with ``serial``").

#: How long an unsaved capture is held before it is reaped. Long enough for
#: a mechanic to read the panel and decide, short enough this never
#: accumulates into a real memory leak on a shop PC left running.
_CAPTURE_TTL = timedelta(minutes=30)

_CAP_LOCK = threading.Lock()
_CAPTURES: dict[str, dict[str, Any]] = {}


def _reap_expired() -> None:
    cutoff = datetime.now() - _CAPTURE_TTL
    with _CAP_LOCK:
        dead = [cid for cid, c in _CAPTURES.items()
               if _parse_iso(c.get("started_at")) is not None
               and _parse_iso(c["started_at"]) < cutoff]
        for cid in dead:
            _CAPTURES.pop(cid, None)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _get_capture(capture_id: str) -> dict[str, Any]:
    _reap_expired()
    with _CAP_LOCK:
        cap = _CAPTURES.get(capture_id)
    if cap is None:
        raise NotFound(f"no freeze-frame capture {capture_id!r} (never existed, already "
                       "discarded/saved and cleared, or past its 30-minute hold)")
    return cap


def _union_pids(by_ecu_pids: dict[str, list[str]]) -> list[str]:
    """Every PID seen in any ECU's supported bitmap, in first-seen order,
    deduplicated -- one Mode 01/Mode 02 read per PID covers every ECU that
    answers it (``ops.obd_pid``/``ops.obd_freeze_frame`` broadcast and
    return every responding ECU's value in one call), so there is no
    reason to re-read a PID twice because two ECUs both support it."""
    seen: set[str] = set()
    out: list[str] = []
    for pids in by_ecu_pids.values():
        for p in pids:
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _frame_tables(cap: dict[str, Any]) -> list[dict[str, Any]]:
    """The panel's own display shape: one table per (stored code, ECU),
    each a list of ``{pid, name, value, unit}`` rows -- built from the raw
    per-PID ``ops.obd_freeze_frame`` results, never stored twice. Mode 02
    only ever has one stored frame per ECU regardless of how many codes
    are stored (a real OBD2 limitation, not a bug here), so every code
    shares the same rows -- the table is still shown under each code's own
    heading, since that is what "the full freeze frame for this code"
    means on the car."""
    by_ecu: dict[str, dict[str, dict[str, Any]]] = {}
    for r in cap.get("freeze_raw", []):
        pid, name = r.get("pid"), r.get("name")
        for ecu, val in (r.get("by_ecu") or {}).items():
            if not isinstance(val, dict):
                continue
            by_ecu.setdefault(ecu, {})[pid] = {
                "pid": pid, "name": name or val.get("name"),
                "value": val.get("value"), "unit": val.get("unit"),
            }
    codes = cap.get("codes") or [None]
    tables: list[dict[str, Any]] = []
    for code in codes:
        for ecu, pid_map in by_ecu.items():
            tables.append({"code": code, "ecu": ecu,
                           "rows": [pid_map[p] for p in sorted(pid_map)]})
    return tables


def _pids_table(cap: dict[str, Any]) -> list[dict[str, Any]]:
    """The Mode 01 snapshot's own display shape, same per-ECU grouping as
    :func:`_frame_tables` (but one reading, not one per code)."""
    by_ecu: dict[str, dict[str, dict[str, Any]]] = {}
    for r in cap.get("pid_raw", []):
        pid, name = r.get("pid"), r.get("name")
        for ecu, val in (r.get("by_ecu") or {}).items():
            if not isinstance(val, dict):
                continue
            by_ecu.setdefault(ecu, {})[pid] = {
                "pid": pid, "name": name or val.get("name"),
                "value": val.get("value"), "unit": val.get("unit"),
            }
    return [{"ecu": ecu, "rows": [pid_map[p] for p in sorted(pid_map)]}
           for ecu, pid_map in by_ecu.items()]


def _public(cap: dict[str, Any]) -> dict[str, Any]:
    """Everything the panel needs, minus internal bookkeeping (lock-free
    snapshot read of the mutable fields; the thread only ever appends/sets,
    never removes, so a read mid-capture is safe to show as "so far")."""
    return {
        "id": cap["id"], "vin": cap["vin"], "status": cap["status"],
        "partial": cap["partial"], "started_at": cap["started_at"],
        "finished_at": cap.get("finished_at"), "codes": cap.get("codes") or [],
        "dtcs_by_ecu": (cap.get("dtcs_raw") or {}).get("by_ecu", {}),
        "readiness": cap.get("readiness_raw"),
        "frame_tables": _frame_tables(cap), "pids_table": _pids_table(cap),
        "note": cap.get("note") or "", "saved": cap.get("saved", False),
        "saved_scan_id": cap.get("saved_scan_id"), "error": cap.get("error"),
    }


def _run_capture(capture_id: str) -> None:
    """The background thread body: every PID in the supported bitmap, read
    for the Mode 01 snapshot and then the Mode 02 freeze frame, checking
    the cancel flag between every single adapter call so Stop takes effect
    within one read, not one whole pass."""
    with _CAP_LOCK:
        cap = _CAPTURES.get(capture_id)
    if cap is None:
        return
    cancel = cap["_cancel"]

    def cut() -> bool:
        if cancel.is_set():
            cap["partial"] = True
            return True
        return False

    try:
        if cut():
            return
        supported = live_ops.obd_supported_pids()
        by_ecu_pids = {hdr: list(info.get("pids") or [])
                       for hdr, info in (supported.get("by_ecu") or {}).items()}
        cap["supported_pids"] = by_ecu_pids
        all_pids = _union_pids(by_ecu_pids)

        if cut():
            return
        cap["readiness_raw"] = live_ops.obd_readiness()

        for pid in all_pids:
            if cut():
                return
            cap["pid_raw"].append(live_ops.obd_pid(pid))

        for pid in all_pids:
            if cut():
                return
            cap["freeze_raw"].append(live_ops.obd_freeze_frame(pid))
    except LiveError as e:
        cap["status"], cap["error"] = "error", str(e)
    except Exception as e:  # noqa: BLE001 -- the thread must never die silently
        cap["status"], cap["error"] = "error", str(e)
    finally:
        if cap["status"] == "running":
            cap["status"] = "done"
        cap["finished_at"] = datetime.now().isoformat(timespec="seconds")


def freeze_capture_start(vin: str) -> dict[str, Any]:
    """Start (or restart) a freeze-frame capture for ``vin``: Mode 03
    stored codes read synchronously (so a poller/MES refusal comes back
    immediately, before anything else runs), then -- if any code is
    stored -- supported PIDs, readiness, Mode 01 snapshot and every PID's
    Mode 02 freeze frame read in a background thread. Raises whatever
    :func:`cuore.live.ops.obd_dtcs` raises (``Refused``, ``LinkUnavailable``,
    ...) unchanged; nothing here adds a second guard."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required to start a freeze-frame capture")
    _reap_expired()

    dtcs_result = live_ops.obd_dtcs(kind="stored")
    now = datetime.now()
    cap_id = "ffcap_" + uuid.uuid4().hex[:12]
    cap: dict[str, Any] = {
        "id": cap_id, "vin": vin, "status": "running", "partial": False,
        "started_at": now.isoformat(timespec="seconds"), "finished_at": None,
        "bus": dtcs_result.get("bus") or "", "cable": dtcs_result.get("cable") or "",
        "stream": "serial (freeze frame capture)",
        "codes": sorted(dtcs_result.get("dtcs") or []), "dtcs_raw": dtcs_result,
        "supported_pids": {}, "freeze_raw": [], "pid_raw": [], "readiness_raw": None,
        "note": "", "saved": False, "saved_scan_id": None, "error": None,
        "_cancel": threading.Event(),
    }
    if not cap["codes"]:
        cap["status"] = "done"
        cap["finished_at"] = now.isoformat(timespec="seconds")
        cap["note"] = "No stored codes right now; nothing to capture a freeze frame for."
        with _CAP_LOCK:
            _CAPTURES[cap_id] = cap
        return _public(cap)

    with _CAP_LOCK:
        _CAPTURES[cap_id] = cap
    thread = threading.Thread(target=_run_capture, args=(cap_id,), daemon=True,
                              name="cuore-freeze-capture")
    cap["_thread"] = thread
    thread.start()
    return _public(cap)


def freeze_capture_status(vin: str, capture_id: str) -> dict[str, Any]:
    """Poll one capture's progress. Raises :class:`NotFound` for an unknown,
    expired, or already-discarded id; :class:`BadRequest` for a capture id
    that belongs to a different VIN (never leaks one car's readings onto
    another's page)."""
    cap = _get_capture(capture_id)
    if cap["vin"] != (vin or "").strip():
        raise BadRequest(f"capture {capture_id!r} was not taken for {vin!r}")
    return _public(cap)


def freeze_capture_stop(vin: str, capture_id: str) -> dict[str, Any]:
    """Signal the background thread to stop after its current read; already-
    read data is kept and the capture ends ``partial``."""
    cap = _get_capture(capture_id)
    if cap["vin"] != (vin or "").strip():
        raise BadRequest(f"capture {capture_id!r} was not taken for {vin!r}")
    cap["_cancel"].set()
    return _public(cap)


def freeze_capture_discard(vin: str, capture_id: str) -> dict[str, Any]:
    """Drop an unsaved capture outright -- nothing was ever written to the
    CUORE log, so there is nothing more to undo than forgetting the id."""
    cap = _get_capture(capture_id)
    if cap["vin"] != (vin or "").strip():
        raise BadRequest(f"capture {capture_id!r} was not taken for {vin!r}")
    with _CAP_LOCK:
        _CAPTURES.pop(capture_id, None)
    return {"id": capture_id, "discarded": True}


def freeze_capture_save(vin: str, capture_id: str, note: str = "") -> dict[str, Any]:
    """Save a finished capture into the CUORE log as from-car observations,
    and hand back the scan id the Scans area (``/v/{vin}/scans/<id>``)
    will show it under.

    Refuses (:class:`BadRequest`) a capture that is still ``"running"`` --
    Stop it or wait first -- and a capture id that belongs to a different
    VIN. Saving twice is a no-op that returns the same scan id rather than
    writing the same readings into the log again.
    """
    vin = (vin or "").strip()
    cap = _get_capture(capture_id)
    if cap["vin"] != vin:
        raise BadRequest(f"capture {capture_id!r} was not taken for {vin!r}")
    if cap["status"] == "running":
        raise BadRequest("this capture is still running; Stop it or wait for it to "
                         "finish before Save")
    if cap.get("saved"):
        return {"id": capture_id, "scan_id": cap["saved_scan_id"], "already_saved": True,
               "scans_url": f"/v/{vin}/scans/{cap['saved_scan_id']}"}

    common = dict(vin=vin, bus=cap.get("bus") or "", cable=cap.get("cable") or "",
                  stream=cap.get("stream") or "serial")
    if cap.get("dtcs_raw"):
        live_store.record_observation("obd_dtcs", cap["dtcs_raw"], **common)
    for r in cap.get("freeze_raw", []):
        live_store.record_observation("freeze_frame", r, **common)
    for r in cap.get("pid_raw", []):
        live_store.record_observation("pid", r, **common)
    if cap.get("readiness_raw"):
        live_store.record_observation("readiness", cap["readiness_raw"], **common)

    started = _parse_iso(cap["started_at"]) or datetime.now()
    id_fmt = getattr(scanlog_mod, "ID_FMT", "SCAN_%y%m%d%H%M")
    scan_id = started.strftime(id_fmt)
    if scanlog_mod is not None:
        try:  # best-effort: land on whatever id the real cluster actually got
            if scanlog_mod.get_scan(vin, scan_id) is None:
                scans = scanlog_mod.list_scans(vin)
                if scans:
                    scan_id = scans[0]["id"]
        except Exception:  # noqa: BLE001 -- Save must still succeed either way
            pass

    cap["saved"], cap["saved_scan_id"] = True, scan_id
    if note:
        cap["note"] = note
    return {"id": capture_id, "scan_id": scan_id, "already_saved": False,
           "scans_url": f"/v/{vin}/scans/{scan_id}"}


# --- CAN-CH passive panel source -----------------------------------------------
#
# Read-only: a short receive-only listen (passive session, STCMM 0, nothing is
# ever transmitted) on the 11-bit CAN-CH broadcast route, decoded through the
# Giorgio DBC (cuore/data/dbc/fca_giorgio.dbc). Needs the grey A6 cable
# declared; with any other cable the answer is "unavailable", not an error.

def _passive_listen(seconds: float, state_note: str = "") -> dict[str, Any]:
    """One passive 2 s listen on CAN-CH over the STP 33 route (the seam the
    tests replace)."""
    routes = [r for r in routes_for(CAN_CH, "grey_a6") if r.stn_protocol == "33"]
    if not routes:
        raise BadRequest("no 11-bit (STP 33) route for CAN-CH")
    lk = live_ops.link()
    with lk.session("chassis_passive", bus=CAN_CH, passive=True, route=routes[0]) as sess:
        return capture_mod.listen(sess, seconds=seconds, max_frames=2000,
                                  persist_raw=True, state_note=state_note)


def chassis_passive(seconds: float = 2.0, state_note: str = "") -> dict[str, Any]:
    cable = (live_ops.cable_state() or {}).get("cable")
    if cable != "grey_a6":
        return {"available": False, "cable": cable, "bus": CAN_CH.key,
                "reason": "the grey A6 cable must be fitted and declared to listen on CAN-CH",
                "messages": {}, "unknown_ids": {},
                "confidence": chassis_decode.dbc_mod.UNVERIFIED_LABEL}
    seconds = max(0.5, min(float(seconds), 5.0))
    cap = _passive_listen(seconds, state_note) if state_note else _passive_listen(seconds)
    out = chassis_decode.decode_capture(cap.get("frames") or [],
                                        seconds=cap.get("seconds") or seconds)
    out.update({"available": True, "cable": cable, "bus": CAN_CH.key,
                "passive": True, "listen_seconds": cap.get("seconds"),
                "error": cap.get("error"), "source": "fca_giorgio.dbc (opendbc, MIT)",
                "raw_capture_file": cap.get("raw_capture_file"),
                "state_note": state_note})
    return out


__all__ = ["NOTICE", "GROUP_ORDER", "GROUP_LABELS", "channel_system", "board",
          "evaluate", "snapshot_recommendations", "attach_snapshot_to_job",
          "freeze_capture_start", "freeze_capture_status", "freeze_capture_stop",
          "freeze_capture_save", "freeze_capture_discard", "chassis_passive"]
