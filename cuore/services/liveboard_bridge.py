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

Reuses :mod:`cuore.services.known_good_bridge` for every band (never touches
``mes.known_good`` directly -- that module's docstring reserves it to
``known_good_bridge`` alone) and :mod:`mes.systems` for the channel-to-system
mapping every grouping/evidence decision here is built on. ``mes.jobs`` is
touched directly for the one write path (:func:`attach_snapshot_to_job`),
the same posture ``cuore.services.jobs_bridge`` uses for the rest of the Job
workflow -- this module owns only the live-telemetry side of that ledger.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live import channels as channels_mod
from . import known_good_bridge
from .errors import BadRequest, NotFound

from mes import jobs as jobs_mod  # noqa: E402
from mes import systems as systems_mod  # noqa: E402

NOTICE = "Read-only session. In motion, a passenger operates this page."

GROUP_ORDER: tuple[str, ...] = (
    "temperatures", "speed_rpm", "pressure_boost", "voltage",
    "fuel_air", "emissions", "gearbox", "tyres", "other",
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
    if unit == "v" or "voltage" in name:
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


def _board_band(channel_id: str) -> Optional[dict[str, Any]]:
    """The widget-ready band plus its ``direction`` -- ``sourced_band``
    itself omits ``direction`` (gauges don't need it); the liveboard's own
    per-channel recommendation does, so it is added back here from the raw
    row. ``None`` for anything ``sourced_band`` would also call ``None``
    (no row, or only a documented UNKNOWN one)."""
    band = known_good_bridge.sourced_band(channel_id)
    if band is None:
        return None
    row = known_good_bridge.known_good_for(channel_id) or {}
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
    banded. ``vin`` is accepted (and reserved for a future per-vehicle
    override) but not required -- every band here is the same sourced
    reference regardless of which car is asked about."""
    channels = [c for c in channels_mod.available_channels() if c.bus == "can_c"]
    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUP_ORDER}
    rates: dict[str, float] = {}
    all_ids: list[str] = []
    for ch in channels:
        entry = {
            "id": ch.id, "name": ch.name, "unit": ch.unit,
            "rate_hz": ch.default_rate_hz,
            "band": _board_band(ch.id),
            "system": channel_system(ch.id),
        }
        by_group[_classify(ch)].append(entry)
        rates[ch.id] = ch.default_rate_hz
        all_ids.append(ch.id)
    groups = [{"id": g, "label": GROUP_LABELS[g], "channels": by_group[g]}
             for g in GROUP_ORDER if by_group[g]]
    return {"groups": groups, "all_channel_ids": all_ids, "rates": rates,
           "notice": NOTICE}


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


def evaluate(channel_id: str, value: float) -> dict[str, Any]:
    """Grade one live value against its sourced known-good band.

    ``sourced_band`` gates whether this channel has anything usable at all
    (``None`` for no row, or a documented UNKNOWN one); the raw row's own
    ``normal``/``alarm``/``direction`` -- not the gauge-shaped band, which
    nulls warn/alarm for a "both"-direction row -- drive the actual grade,
    since a two-sided row like battery voltage is still graded on both
    sides here. Never invents a limit.
    """
    name = _channel_name(channel_id)
    gate = known_good_bridge.sourced_band(channel_id)
    if gate is None:
        return {"level": "unknown",
                "text": f"No sourced reference range for {name}; the sourced-range "
                        "check cannot be made."}
    row = known_good_bridge.known_good_for(channel_id) or {}
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


def snapshot_recommendations(values: dict[str, float]) -> list[dict[str, Any]]:
    """Every value in ``values`` (``{channel_id: value}``), graded, excessive
    first."""
    out: list[dict[str, Any]] = []
    for cid, value in values.items():
        try:
            ch = channels_mod.by_id(cid)
            name, unit = ch.name, ch.unit
        except Exception:  # noqa: BLE001 -- grade whatever id was actually sent
            name, unit = cid, ""
        ev = evaluate(cid, value)
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

    recs = snapshot_recommendations(values)
    out_of_range = 0
    attached: list[dict[str, Any]] = []
    new_hypotheses: list[dict[str, Any]] = []

    for rec in recs:
        cid, level, value = rec["id"], rec["level"], rec["value"]
        row = known_good_bridge.known_good_for(cid) or {}
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


__all__ = ["NOTICE", "GROUP_ORDER", "GROUP_LABELS", "channel_system", "board",
          "evaluate", "snapshot_recommendations", "attach_snapshot_to_job"]
