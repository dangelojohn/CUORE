"""Pure rules behind the scan health report -- the document CUORE produces
after every from-car scan.

Nothing here touches the car, the log corpus, or the job/maintenance stores;
that assembly lives in ``cuore.services.scan_health_bridge``, which is the
only caller of this module. Kept here, not there, for the same reason
``mes.systems``/``mes.verdict`` live in this package rather than in
``cuore``: a rule that decides whether a reading is a fault should be
testable with a dict literal, with no FastAPI app, no state directory, and
no live link in the picture.

Three small tables and four functions:

* :data:`MODE06_MIDS` -- what a Mode 06 MID *means*, in plain language, and
  which system it belongs to. The ECM's own limits (read from the car) are
  CONFIRMED by definition -- that grade is assigned by
  :func:`mode06_confidence`, never looked up.
* :data:`PID_SYSTEM` / :data:`ECU_SYSTEM` -- PID name and module id to
  ``mes.systems`` key, for the handful of signals this project's live link
  actually logs (freeze-frame/live PID snapshots when a caller has them;
  per-module DTC presence otherwise).
* :data:`READINESS_MONITOR_SYSTEM` -- SAE readiness-monitor name to system
  key, used only as a last-resort "we have *a* reading, just no pass/fail
  spec for it" signal when nothing more specific (a DTC, a Mode 06 MID)
  addressed that system this scan. Several of these mappings are approximate
  (a monitor covers more than one system) and are labelled as such in
  :data:`READINESS_MONITOR_NOTE` -- never passed off as a precise reading.
* :func:`classify_system` -- one system's health for one scan.
* :func:`margin` -- "value is N.N× the limit", or ``None`` when the limit is
  zero/unusable.
* :func:`verdict` -- the scan's own headline state, from DTCs/readiness/
  Mode 06 only (never hand-written, never asserting a repair is proven).

Health values, exactly four plus the baseline:

* ``FAULT``        -- a Mode 06 MID failed, or an active DTC names this
                      system primary.
* ``OK``            -- every signal addressing this system passed, with a
                      spec to pass against.
* ``READING ONLY``  -- a value exists (a readiness-monitor completion flag,
                      most often) but no spec exists to grade it -- "no spec
                      on file", never a placeholder number.
* ``NOT ASSESSED``  -- the system has a live channel this platform exposes,
                      but it was not exercised under this scan's conditions
                      (e.g. boost, not read at idle).
* ``GAP``           -- nothing this scan touched addresses this system at
                      all. Most body/chassis/network systems land here until
                      a UDS module scan actually runs.
"""

from __future__ import annotations

from typing import Any, Optional

UNKNOWN_SPEC = "UNKNOWN — use the service manual (TechAuthority)"

FAULT = "FAULT"
OK = "OK"
READING_ONLY = "READING ONLY"
NOT_ASSESSED = "NOT ASSESSED"
GAP = "GAP"

HEALTH_STATES = (FAULT, OK, READING_ONLY, NOT_ASSESSED, GAP)

#: Grade for any band the ECM itself reported this scan (a Mode 06 MID/TID
#: limit) -- CONFIRMED by definition: it came off the car, not a reference.
MODE06_CONFIDENCE = "CONFIRMED"
MODE06_SOURCE = "the ECM's own Mode 06 limit, read from the car"


def mode06_confidence() -> tuple[str, str]:
    """``(confidence, source)`` for any Mode 06 MID/TID limit. A tiny
    function rather than a bare constant so every caller gets the pair
    together and can never quote one without the other."""
    return MODE06_CONFIDENCE, MODE06_SOURCE


# --- Mode 06 MID interpretation table ---------------------------------------
#
# Keyed by the two-hex-digit MID string, exactly as cuore.live.mode06 /
# mes.live_obs's observation ``data.results`` key it. ``name`` mirrors
# ``mid_name`` when the ECU supplied one; several MIDs in this platform's own
# logs come back with ``mid_name: null`` -- those are given a plain "Mode 06
# MID xx" label and routed to the best-guess system, flagged in ``note``.

def _mid(mid: str, name: str, system: str, fail: str, *,
         next_test: Optional[str] = None, note: str = "",
         priority: int = 50) -> dict[str, Any]:
    """``priority`` breaks ties when more than one MID maps to the same
    system (``exhaust_emissions`` carries both the catalyst and the O2
    sensor monitor) -- lower shows first, so the most central test for that
    system's own name (the catalyst, for "Exhaust / emissions") is the one
    a reading/margin gets shown against, not whichever MID happened to
    answer first in the ECU's own reply order."""
    return {"mid": mid, "name": name, "system": system, "fail_meaning": fail,
            "next_test": next_test, "note": note, "priority": priority}


MODE06_MIDS: dict[str, dict[str, Any]] = {
    "02": _mid("02", "O2 sensor monitor", "exhaust_emissions",
              "the oxygen sensor's response-time or signal-amplitude "
              "self-test failed",
              next_test="fuel_trim_o2_observation"),
    "21": _mid("21", "Catalyst monitor", "exhaust_emissions",
              "the catalyst's own efficiency self-test failed",
              priority=1),
    "31": _mid("31", "EGR monitor", "evap",
              "the EGR flow self-test failed",
              note="mes.systems has no standalone EGR system -- P04xx "
                   "(EVAP and EGR alike) is this project's own 'evap' "
                   "bucket (see mes.systems._sae_fallback prefix2=='04'); "
                   "reused here for the matching Mode 06 MID, not a new "
                   "finding"),
    "35": _mid("35", "VVT monitor", "valve_control",
              "a MultiAir/cam-phasing timing self-test failed"),
    "39": _mid("39", "EVAP monitor (cap off / gross leak)", "evap",
              "the gross-leak (cap-off) self-test failed",
              next_test="evap_smoke"),
    "3A": _mid("3A", "EVAP monitor 0.090\" leak", "evap",
              "the large-leak self-test failed: the system did not read "
              "sealed within the required time",
              next_test="esim_vacuum_test_a", priority=1),
    "3C": _mid("3C", "EVAP monitor 0.020\" leak", "evap",
              "the small-leak self-test exceeded its time limit",
              next_test="esim_vacuum_test_a", priority=2),
    "3D": _mid("3D", "EVAP purge flow monitor", "evap",
              "the purge-flow self-test failed",
              next_test="purge_vent_actuation"),
    "41": _mid("41", "Mode 06 MID 41", "engine_management",
              "an ECM-internal self-test failed",
              note="this ECU reports no mid_name for 41 -- routed to the "
                   "generic engine_management bucket, not a sourced "
                   "identification"),
    "42": _mid("42", "Mode 06 MID 42", "engine_management",
              "an ECM-internal self-test failed",
              note="this ECU reports no mid_name for 42 -- routed to the "
                   "generic engine_management bucket, not a sourced "
                   "identification"),
    "81": _mid("81", "Mode 06 MID 81", "evap",
              "an EVAP-pattern self-test failed",
              next_test="purge_vent_actuation",
              note="this ECU reports no mid_name for 81, but its TIDs "
                   "share MID 3D's purge-flow UASID/limit pattern -- "
                   "routed to evap as a lead, not a sourced identification"),
    "A2": _mid("A2", "Misfire monitor cylinder 1", "ignition",
              "cylinder 1 logged misfires above the ECM's limit",
              next_test="misfire_counters"),
    "A3": _mid("A3", "Misfire monitor cylinder 2", "ignition",
              "cylinder 2 logged misfires above the ECM's limit",
              next_test="misfire_counters"),
    "A4": _mid("A4", "Misfire monitor cylinder 3", "ignition",
              "cylinder 3 logged misfires above the ECM's limit",
              next_test="misfire_counters"),
    "A5": _mid("A5", "Misfire monitor cylinder 4", "ignition",
              "cylinder 4 logged misfires above the ECM's limit",
              next_test="misfire_counters"),
}


# --- PID / module / readiness-monitor to system -----------------------------

#: Mode 01 PID name (as cuore.live.obd / mes.known_good spell it) -> system
#: key, for the freeze-frame/live PID snapshot a caller may have on hand.
#: Not every ``mes.known_good`` channel is listed -- only ones with an
#: obvious single home system.
PID_SYSTEM: dict[str, str] = {
    "engine_coolant_temp": "cooling",
    "short_fuel_trim_b1": "fuel",
    "long_fuel_trim_b1": "fuel",
    "short_fuel_trim_b2": "fuel",
    "long_fuel_trim_b2": "fuel",
    "commanded_afr": "fuel",
    "fuel_level": "fuel",
    "intake_map": "air_intake_boost",
    "maf": "air_intake_boost",
    "throttle_position": "air_intake_boost",
    "absolute_load": "air_intake_boost",
    "barometric_pressure": "air_intake_boost",
    "boost": "air_intake_boost",
    "intake_air_temp": "air_intake_boost",
    "engine_rpm": "ignition",
    "timing_advance": "ignition",
    "control_module_voltage": "electrical_supply",
    "battery_voltage": "electrical_supply",
    "commanded_evap_purge": "evap",
    "evap_vapor_pressure": "evap",
    "evap_vapor_pressure_abs": "evap",
    "engine_oil_temp": "lubrication",
    "tcm_04fe": "transmission_driveline",
    "tcm_0518": "transmission_driveline",
}

#: UDS module id (as ``mes.live_obs``/the live link's ``by_ecu``/``ecu`` keys
#: spell it) -> system key, for a module that answered a DTC query (even
#: with an empty result) -- that is a real "we asked, it answered" reading,
#: distinct from a system nothing this scan touched at all.
ECU_SYSTEM: dict[str, str] = {
    "ECM": "engine_management",
    "TCM": "transmission_driveline",
    "BCM": "body_comfort",
    "ABS": "brakes_abs",
    "EPS": "steering",
    "ORC": "restraints",
    "RFHUB": "wheels_tpms",
    "IPC": "infotainment_cluster",
}

#: SAE J1979 readiness-monitor name -> system key, used only when no DTC or
#: Mode 06 MID already addressed that system this scan. A monitor completion
#: flag is a real reading ("this test has run since the last clear") but
#: carries no pass/fail number, so it only ever yields READING ONLY, never
#: OK/FAULT on its own -- several of these are approximate (one monitor
#: covers more circuits than the one system listed) and are flagged in
#: :data:`READINESS_MONITOR_NOTE`.
READINESS_MONITOR_SYSTEM: dict[str, str] = {
    "Misfire": "ignition",
    "Fuel system": "fuel",
    "Comprehensive components": "cooling",
    "Catalyst": "exhaust_emissions",
    "Evaporative system": "evap",
    "Oxygen sensor": "exhaust_emissions",
    "Oxygen sensor heater": "exhaust_emissions",
    "EGR system": "evap",
}

READINESS_MONITOR_NOTE = {
    "Comprehensive components": (
        "the Comprehensive Components monitor covers many circuits, not "
        "cooling specifically -- used here only because this platform's "
        "live link logs no coolant-temperature PID/DID to grade against a "
        "spec; the completion flag is a real reading, just not a "
        "coolant-specific one"),
}


def margin(value: Optional[float], limit: Optional[float]) -> Optional[str]:
    """``"N.N×"`` for ``value`` against ``limit``, or ``None`` when the
    limit is missing or zero (a ratio against zero is not a number)."""
    if value is None or limit is None or limit == 0:
        return None
    try:
        return f"{value / limit:.1f}×"
    except (TypeError, ZeroDivisionError):
        return None


#: A Mode 06 row carries ``min``/``max``, not a single ``limit`` -- the ECU's
#: own reply shape (see ``cuore.live.mode06``/``mes.live_obs``). 65535 is
#: this format's own "no upper bound" sentinel, so:
#:
#: * ``max`` at/above the sentinel -> a ">= min" style test; the threshold
#:   worth quoting/dividing by is ``min``.
#: * ``min`` is zero (and ``max`` is not the sentinel) -> a "<= max" style
#:   test; the threshold is ``max``.
#: * both bounds are real, finite, and nonzero -> a genuine two-sided band
#:   (e.g. the O2 sensor's mV reading); no single ratio describes that, so
#:   this returns ``None`` rather than pick one side arbitrarily.
_SENTINEL_MAX = 65535


def _threshold(row: dict[str, Any]) -> Optional[float]:
    lo, hi = row.get("min"), row.get("max")
    if hi is not None and hi >= _SENTINEL_MAX:
        return lo
    if not lo:
        return hi
    return None


def _mid_priority(row: dict[str, Any]) -> int:
    meta = MODE06_MIDS.get(str(row.get("mid") or ""))
    return meta["priority"] if meta else 50


def mode06_threshold(row: dict[str, Any]) -> Optional[float]:
    """Public wrapper on :func:`_threshold` -- the single number worth
    quoting/dividing by for one Mode 06 row, or ``None`` for a genuine
    two-sided band. ``cuore.services.scan_health_bridge`` uses this rather
    than reaching into ``min``/``max`` itself."""
    return _threshold(row)


def _mode06_reading(row: dict[str, Any]) -> str:
    name = row.get("mid_name") or ("MID " + str(row.get("mid")))
    limit = _threshold(row)
    if limit is not None:
        return f"{name}: {row.get('value')} vs limit {limit}"
    return f"{name}: {row.get('value')} (min {row.get('min')}, max {row.get('max')})"


def mode06_reading(row: dict[str, Any]) -> str:
    """Public wrapper on :func:`_mode06_reading`."""
    return _mode06_reading(row)


def classify_system(system_key: str, *,
                    mode06_rows: Optional[list[dict[str, Any]]] = None,
                    dtc_fault: bool = False,
                    pid_reading: Optional[dict[str, Any]] = None,
                    known_good_row: Optional[dict[str, Any]] = None,
                    ecu_answered: bool = False,
                    readiness_reading: Optional[dict[str, Any]] = None
                    ) -> dict[str, Any]:
    """One system's health for one scan.

    Resolution order, most specific evidence first:

    1. Any Mode 06 row for this system that failed, or ``dtc_fault`` true
       (an active DTC's primary system is this one) -> ``FAULT``.
    2. A Mode 06 row for this system, all passed -> ``OK``, with a margin
       when the row carries numeric value/limit.
    3. A PID/DID reading with a known-good band (confidence != UNKNOWN) --
       inside the normal band is ``OK`` (with margin against whichever
       bound it is closer to), outside is ``FAULT``.
    4. A PID/DID reading with no usable band, or a readiness-monitor
       completion flag -- ``READING ONLY``, spec rendered as
       :data:`UNKNOWN_SPEC`.
    5. A module answered a DTC query for this system (even with nothing
       found) -- ``OK``, noted as engine-OBD/UDS-DTC-only, not a full
       live-channel check.
    6. Nothing above applies -- ``GAP``.
    """
    rows = mode06_rows or []
    failed = sorted((r for r in rows if r.get("passed") is False), key=_mid_priority)
    passed = sorted((r for r in rows if r.get("passed") is True), key=_mid_priority)

    if failed or dtc_fault:
        row = failed[0] if failed else None
        reading = _mode06_reading(row) if row is not None else None
        return {"system": system_key, "health": FAULT, "reading": reading,
                "spec_confidence": MODE06_CONFIDENCE if row is not None else None,
                "spec_source": MODE06_SOURCE if row is not None else None,
                "margin": None}

    if passed:
        row = passed[0]
        m = margin(row.get("value"), _threshold(row))
        reading = _mode06_reading(row)
        return {"system": system_key, "health": OK, "reading": reading,
                "spec_confidence": MODE06_CONFIDENCE, "spec_source": MODE06_SOURCE,
                "margin": m}

    if pid_reading is not None:
        value = pid_reading.get("value")
        unit = pid_reading.get("unit", "")
        kg = known_good_row
        if kg and kg.get("confidence") != "UNKNOWN" and kg.get("normal") and value is not None:
            lo, hi = kg["normal"]
            ok = lo <= value <= hi
            dist_lo = abs(value - lo) if lo else None
            dist_hi = abs(hi - value) if hi else None
            m = margin(value, hi) if ok and hi else margin(value, lo) if ok and lo else None
            return {"system": system_key, "health": OK if ok else FAULT,
                    "reading": f"{value}{unit}",
                    "spec_confidence": kg.get("confidence"), "spec_source": kg.get("source"),
                    "margin": m}
        return {"system": system_key, "health": READING_ONLY,
                "reading": f"{value}{unit}",
                "spec_confidence": "UNKNOWN", "spec_source": UNKNOWN_SPEC,
                "margin": None}

    if readiness_reading is not None:
        mon = readiness_reading.get("monitor")
        complete = readiness_reading.get("complete")
        note = READINESS_MONITOR_NOTE.get(mon, "")
        reading = f"{mon} monitor: {'complete' if complete else 'NOT complete'} since last clear"
        if note:
            reading += f" ({note})"
        return {"system": system_key, "health": READING_ONLY, "reading": reading,
                "spec_confidence": "UNKNOWN", "spec_source": UNKNOWN_SPEC,
                "margin": None}

    if ecu_answered:
        return {"system": system_key, "health": OK,
                "reading": "module answered; no DTCs (engine-OBD query only, "
                          "not a full UDS/live-channel check)",
                "spec_confidence": None, "spec_source": None, "margin": None}

    return {"system": system_key, "health": GAP, "reading": None,
            "spec_confidence": None, "spec_source": None, "margin": None}


# --- verdict: the scan's own headline state ---------------------------------
#
# Same four-state vocabulary cuore.services.dossier_bridge._build_verdict
# uses for the whole-vehicle dossier (ACTIVE_FAULTS / VERIFIED_CLEAN /
# UNVERIFIED_REPAIR / NO_DATA), computed independently and from a single
# scan's own DTC/readiness/Mode 06 data only -- never the log corpus, never
# hand-written. The two are allowed to agree without one importing the
# other: this module has no cuore dependency at all.

ACTIVE_FAULTS = "ACTIVE_FAULTS"
VERIFIED_CLEAN = "VERIFIED_CLEAN"
UNVERIFIED_REPAIR = "UNVERIFIED_REPAIR"
NO_DATA = "NO_DATA"

_VERDICT_LABELS = {ACTIVE_FAULTS: "Active fault", VERIFIED_CLEAN: "Verified clean",
                   UNVERIFIED_REPAIR: "Unverified repair", NO_DATA: "No data"}


def verdict(*, stored: Optional[list[str]] = None, pending: Optional[list[str]] = None,
           permanent: Optional[list[str]] = None,
           readiness: Optional[dict[str, Any]] = None,
           mode06_fail_rows: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """The scan's headline state, computed from this scan's own DTCs,
    readiness monitors and Mode 06 results only.

    ``readiness`` is the ``since_clear`` block (``{"monitors": [...],
    "all_complete": bool}``) when a readiness observation was read this
    scan, else ``None``.
    """
    stored = stored or []
    pending = pending or []
    permanent = permanent or []
    mode06_fail_rows = mode06_fail_rows or []
    basis: list[str] = []

    if stored or permanent:
        state = ACTIVE_FAULTS
        if stored:
            basis.append(f"stored: {', '.join(stored)}")
        if pending:
            basis.append(f"pending: {', '.join(pending)}")
        if permanent:
            basis.append(f"permanent: {', '.join(permanent)}")
        if mode06_fail_rows:
            basis.append(f"{len(mode06_fail_rows)} Mode 06 test(s) failed this scan")
        if readiness and readiness.get("all_complete"):
            basis.append("every readiness monitor has completed since the last "
                         "clear -- this is a live, measured fault, not a code "
                         "waiting on a monitor")
    elif pending:
        state = UNVERIFIED_REPAIR
        basis.append(f"pending only: {', '.join(pending)} -- not yet confirmed")
    elif readiness is not None:
        if readiness.get("all_complete"):
            state = VERIFIED_CLEAN
            basis.append("no stored/pending/permanent codes and every readiness "
                         "monitor has completed since the last clear")
        else:
            state = UNVERIFIED_REPAIR
            basis.append("no stored/pending/permanent codes, but at least one "
                         "readiness monitor has not completed since the last "
                         "clear -- not proof of repair yet")
    else:
        state = NO_DATA
        basis.append("no DTC or readiness read this scan")

    return {"state": state, "label": _VERDICT_LABELS[state], "basis": basis}


__all__ = [
    "FAULT", "OK", "READING_ONLY", "NOT_ASSESSED", "GAP", "HEALTH_STATES",
    "UNKNOWN_SPEC", "MODE06_CONFIDENCE", "MODE06_SOURCE", "mode06_confidence",
    "MODE06_MIDS", "PID_SYSTEM", "ECU_SYSTEM", "READINESS_MONITOR_SYSTEM",
    "READINESS_MONITOR_NOTE", "margin", "mode06_threshold", "mode06_reading",
    "classify_system",
    "ACTIVE_FAULTS", "VERIFIED_CLEAN", "UNVERIFIED_REPAIR", "NO_DATA", "verdict",
]
