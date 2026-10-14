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

import re
from typing import Any, Optional

from . import dtc as dtc_mod

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


# --- module DTC status -> active/history/never-listed ----------------------
#
# A UDS module answers "every code it tracks", not "every fault on the
# car" -- the ECM alone reports hundreds, nearly all of them the
# ``testNotCompletedThisOperationCycle``-only placeholder (this platform's
# own ``module_dtcs`` reads: status ``64``). The status *flags* a module
# read already decodes (``cuore.live.obd``'s own ``flags`` dict) say which
# of the rest are a fault right now versus a fault on file from before:
#
# * ``testFailed`` true  -- failing on this very read -> ``"active"``.
# * ``confirmedDTC`` or ``pendingDTC`` true (``testFailed`` false) -- the
#   module has this on file, but it is not failing right now ->
#   ``"history"``.
# * neither -- the ``testNotCompletedThisOperationCycle``-only placeholder
#   (or an empty/unset status) -- ``None``, never surfaced as a finding.

def module_dtc_category(flags: Optional[dict[str, Any]]) -> Optional[str]:
    """``"active"`` / ``"history"`` / ``None`` for one module DTC record's
    own decoded status flags. See the section note above for the rule."""
    flags = flags or {}
    if flags.get("testFailed"):
        return "active"
    if flags.get("confirmedDTC") or flags.get("pendingDTC"):
        return "history"
    return None


def _split_code(code: str) -> tuple[str, Optional[str]]:
    """``"U1713-2F"`` -> ``("U1713", "2F")``; a code with no failure-type
    suffix comes back with ``None`` for it, never a guessed byte."""
    code = (code or "").strip()
    if "-" in code:
        base, ftb = code.rsplit("-", 1)
        return base, ftb or None
    return code, None


def module_active_reading(entries: list[dict[str, Any]]) -> str:
    """One FAULT row's reading for every module DTC ``"active"`` on this
    system this scan -- the module, the code, and the failure-type byte's
    own decoded meaning (:func:`mes.dtc.failure_type`), never a hand-written
    guess at what the code means. ``entries`` is ``[{"code", "module"}, ...]``."""
    parts: list[str] = []
    for e in entries:
        code = e.get("code", "")
        module = e.get("module", "")
        _, ftb = _split_code(code)
        ft = dtc_mod.failure_type(ftb)
        meaning = ft.text if ft else "failure-type byte not decoded"
        parts.append(f"{module}: {code} ACTIVE -- {meaning}")
    return "; ".join(parts)


def module_history_reading(entries: list[dict[str, Any]]) -> str:
    """One OK row's reading for every module DTC that is ``"history"`` on
    this system this scan (on file, not currently failing). ``entries`` is
    ``[{"code", "module"}, ...]``."""
    codes = "; ".join(f"{e.get('module', '')}: {e.get('code', '')}" for e in entries)
    return f"{codes} -- history since last clear, not failing now"


def network_active_issue(entries: list[dict[str, Any]]) -> Optional[str]:
    """One "what to check next" issue line for an ACTIVE network-system
    module DTC this scan (``entries`` as :func:`module_active_reading`
    takes them; ``None`` when there are none). Points at the documented
    upstream check on this project's own system graph
    (``mes.systems.SYSTEMS["network"]``'s own ``depends_on`` edge: BCM
    power feeds and chassis grounds are a documented, sourced lead for
    multi-module U-code cascades) rather than the bus itself, which is
    where a cascade like this gets chased first and wastes the most time."""
    if not entries:
        return None
    first = entries[0]
    code, module = first.get("code", ""), first.get("module", "")
    return (f"{module}: {code} (network) ACTIVE this scan -- check BCM supply "
           "and grounds first, then the bus (mes.systems network system's "
           "own documented depends_on edge). Do not clear codes before it.")


def network_bus_event_note(live_u_code_count: int) -> Optional[str]:
    """One hedged "what the measurement tells us" sentence when three or
    more *live* (non-placeholder: ``"active"`` or ``"history"``, never a
    bare status-64) U-codes are on file this scan -- ``None`` below that
    count. Reuses this project's own existing family-level judgement
    (``mes.analysis``'s module docstring: "A network event is one fault,
    not five... several modules each report only 'missing message' or
    'erratic' against *other* modules, that is one power or bus event")
    rather than inventing new wording for the same finding; see
    :func:`mes.analysis.detect_network_event` for the corpus-grounded,
    multi-module version of this same judgement."""
    if live_u_code_count < 3:
        return None
    return (f"{live_u_code_count} live U-codes on file this scan, across more "
           "than one module -- this project's own network-event finding "
           "(mes.analysis: several modules each reporting only a "
           "communication fault against other modules is usually one power "
           "or bus event, not several separate module failures) applies "
           "here; see mes.analysis.detect_network_event for the "
           "corpus-grounded version of this same judgement.")


# --- scan_coverage -> GAP row wording ---------------------------------------

#: A raw Python exception class name (``FileNotFoundError``, ``LinkUnavailable``,
#: ...), either bare (``"LinkUnavailable: could not open ..."``) or in its own
#: ``repr()`` form (``"FileNotFoundError(2, '...', None, 2)"``) -- the two
#: shapes a driver/adapter failure actually raises as a string onto a
#: ``scan_coverage`` row's ``why``. Matched, never guessed at, so a plain
#: mechanic-language ``why`` (``"skipped, needs grey A6 cable"``) never false-
#: positives into this branch.
_EXCEPTION_REPR_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Unavailable)\s*[:(]")

#: A serial port name, when the exception text happens to carry one -- folded
#: into the mechanic wording so "reconnect and rescan" still names the port,
#: without rendering the exception around it.
_PORT_RE = re.compile(r"\bCOM\d+\b", re.IGNORECASE)


def _looks_like_raw_exception(why: str) -> bool:
    """True when ``why`` is (or contains) a raw Python exception class name
    and/or its own ``repr()`` -- never a plain-English reason this project's
    own ``cuore.live.fullscan`` already writes."""
    return bool(_EXCEPTION_REPR_RE.search(why))


def _adapter_not_reachable_text(why: str) -> str:
    """Mechanic wording for a raw adapter/link exception, in place of the
    exception string itself (see :func:`_looks_like_raw_exception`) -- the
    port name is kept when the exception text carries one, the exception's
    own class name/args/repr are not."""
    port = _PORT_RE.search(why)
    if port:
        return f"Adapter not reachable on {port.group(0).upper()} during this scan -- reconnect and rescan."
    return "Adapter not reachable during this scan -- reconnect and rescan."


def coverage_gap_text(category: Optional[str], why: Optional[str]) -> str:
    """One GAP row's reading, taken verbatim from a ``scan_coverage``
    observation's own ``why`` for that module -- never rephrased or
    invented, with one exception (literally): ``cuore.live.fullscan``'s own
    coverage rows already write ``why`` as a complete reason in two
    different shapes for the normal case -- a cable-gated module reads
    ``"needs grey A6 cable"`` / ``"skipped, needs <cable>"``, an unaddressed
    module reads ``"no known address: run discovery"`` -- both already read
    as a full sentence fragment and are shown as-is. But when the adapter/
    driver itself failed to open the link, ``why`` is instead a raw Python
    exception string (``"LinkUnavailable: ... FileNotFoundError(2, '...',
    None, 2)."``) -- see N3 in ``docs/research/MECHANIC_REVIEW_5_2026-10-14.md``:
    that must never reach a mechanic's issue list verbatim, so it is mapped
    to plain mechanic wording (:func:`_adapter_not_reachable_text`) instead.
    A ``"not_reachable"`` row whose ``why`` is some other (non-exception)
    string still gets the existing ``"not reachable -- "`` prefix so the row
    reads as a sentence."""
    why = (why or "").strip()
    category = category or ""
    if not why:
        return category.replace("_", " ") or "not read this scan"
    lowered = why.lower()
    if lowered.startswith("skipped") or lowered.startswith("no known address"):
        return why
    if _looks_like_raw_exception(why):
        return _adapter_not_reachable_text(why)
    if category == "not_reachable":
        return f"not reachable -- {why}"
    return why


# --- Mode 09 (calibration IDs / CVNs / IUPR) --------------------------------
#
# Shape matches ``cuore.live.mode09.read_mode09``'s own return value, as
# written onto the ``mode09`` observation by ``cuore.live.fullscan``:
# ``{"mode09": {"results": {"04": {ecu: {"calibration_ids": [...]}}, "06":
# {ecu: {"cvns": [...]}}, "08": {ecu: {"monitors": {"EVAP": {"numerator",
# "denominator", "completion_rate"}}}}}}, "gaps": [...], "gap_reason": ...}``.
# Every field is read defensively -- this install's own mode09 reads on
# file answer nothing yet (every PID comes back in ``gaps``), and that is
# reported as an absence (``{}`` / ``None``), never a placeholder number.

def mode09_header_extras(mode09_obs: Optional[dict[str, Any]]) -> dict[str, Any]:
    """``{"calibration_ids": [...], "cvns": [...]}`` for whichever of PID
    04/06 actually answered this scan -- keys omitted (not ``None``/``[]``)
    when that PID did not answer, so a caller can test with a plain ``in``
    check rather than distinguishing "answered empty" from "did not
    answer"."""
    out: dict[str, Any] = {}
    if not mode09_obs:
        return out
    results = (mode09_obs.get("mode09") or {}).get("results") or {}
    cal_ids: list[str] = []
    for entry in (results.get("04") or {}).values():
        cal_ids.extend(entry.get("calibration_ids") or [])
    if cal_ids:
        out["calibration_ids"] = cal_ids
    cvns: list[str] = []
    for entry in (results.get("06") or {}).values():
        cvns.extend(entry.get("cvns") or [])
    if cvns:
        out["cvns"] = cvns
    return out


def evap_iupr(mode09_obs: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The EVAP monitor's own in-use-performance-tracking numerator/
    denominator/completion_rate (PID 08), when the ECM actually answered
    it this scan -- ``None`` otherwise (this install's own mode09 reads on
    file answer nothing yet)."""
    if not mode09_obs:
        return None
    results = (mode09_obs.get("mode09") or {}).get("results") or {}
    for entry in (results.get("08") or {}).values():
        evap = (entry.get("monitors") or {}).get("EVAP")
        if evap:
            return evap
    return None


def margin(value: Optional[float], limit: Optional[float]) -> Optional[str]:
    """``"N.N×"`` for ``value`` against ``limit``, or ``None`` when the
    limit is missing or zero (a ratio against zero is not a number)."""
    if value is None or limit is None or limit == 0:
        return None
    try:
        return f"{value / limit:.1f}×"
    except (TypeError, ZeroDivisionError):
        return None


def symmetric_margin(value: Optional[float], half: Optional[float],
                     unit: str = "") -> Optional[str]:
    """``"+3.1% of ±10%"`` -- the margin phrasing for a known-good band
    that is symmetric around zero (``mes.known_good``'s fuel-trim rows: a
    ``normal`` of ``(-10, 10)``, ``direction="both"``). A ratio
    (:func:`margin`'s own "N.N×") means nothing for a band centred on
    zero -- 3.1 / 10 reads as "0.3×", which hides the one number a
    technician actually wants: how much headroom is left inside the ±
    band. ``half`` is the band's own half-width (``10`` for ±10%), not the
    raw value -- callers pass ``kg["normal"][1]`` directly."""
    if value is None or half is None or half == 0:
        return None
    return f"{value:+g}{unit} of ±{half:g}{unit}"


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
    """"name: value V, limit {min|max} L -- PASS/FAIL" -- the single-sided
    threshold from :func:`_threshold` named by which bound it actually is,
    never a hardcoded "vs limit" that reads as a min when the real limit is
    a max (Review #6 item 3: TID 90 is a max-limit test, 6096 vs 0..6000 --
    ``cuore.services.dossier_bridge._mode06_fail_label`` renders the same
    row from the live link in this exact shape; this is the MES-log/Scans
    side of the same text). Falls back to showing both bounds for a
    genuine two-sided band, where no single threshold applies."""
    name = row.get("mid_name") or ("MID " + str(row.get("mid")))
    value = row.get("value")
    verdict = None
    if row.get("passed") is True:
        verdict = "PASS"
    elif row.get("passed") is False:
        verdict = "FAIL"
    limit = _threshold(row)
    if limit is not None:
        hi = row.get("max")
        sentinel_max = isinstance(hi, (int, float)) and hi >= _SENTINEL_MAX
        bound = "min" if sentinel_max else "max"
        text = f"{name}: value {value}, limit {bound} {limit}"
    else:
        text = f"{name}: value {value} (min {row.get('min')}, max {row.get('max')})"
    return f"{text} -- {verdict}" if verdict else text


def mode06_reading(row: dict[str, Any]) -> str:
    """Public wrapper on :func:`_mode06_reading`."""
    return _mode06_reading(row)


def classify_system(system_key: str, *,
                    mode06_rows: Optional[list[dict[str, Any]]] = None,
                    dtc_fault: bool = False,
                    module_active: Optional[list[dict[str, Any]]] = None,
                    module_history: Optional[list[dict[str, Any]]] = None,
                    pid_reading: Optional[dict[str, Any]] = None,
                    known_good_row: Optional[dict[str, Any]] = None,
                    ecu_answered: bool = False,
                    readiness_reading: Optional[dict[str, Any]] = None,
                    coverage_text: Optional[str] = None,
                    ) -> dict[str, Any]:
    """One system's health for one scan.

    Resolution order, most specific evidence first:

    1. Any Mode 06 row for this system that failed, ``dtc_fault`` true (an
       active DTC's primary system is this one), or ``module_active``
       (a UDS module DTC ``"active"`` on this system -- see
       :func:`module_dtc_category`) -> ``FAULT``. The reading quotes the
       Mode 06 row when there is one, else the module DTC(s)
       (:func:`module_active_reading`), else nothing (a plain
       stored/pending/permanent DTC with neither).
    2. A Mode 06 row for this system, all passed -> ``OK``, with a margin
       when the row carries numeric value/limit.
    3. ``module_history`` (a UDS module DTC on file for this system but
       not failing now) -> ``OK``, reading from
       :func:`module_history_reading` -- real evidence that the module was
       read, distinct from a module answering with nothing on file at all
       (tier 6, below).
    4. A PID/DID reading with a known-good band (confidence != UNKNOWN) --
       inside the normal band is ``OK`` (margin as :func:`symmetric_margin`
       for a band symmetric around zero such as fuel trim, else as
       :func:`margin`'s ratio against whichever bound it is closer to),
       outside is ``FAULT``.
    5. A PID/DID reading with no usable band, or a readiness-monitor
       completion flag -- ``READING ONLY``, spec rendered as
       :data:`UNKNOWN_SPEC`.
    6. A module answered a DTC query for this system (even with nothing
       found) -- ``OK``, noted as engine-OBD/UDS-DTC-only, not a full
       live-channel check.
    7. Nothing above applies -- ``GAP``, with ``coverage_text`` (a
       ``scan_coverage`` observation's own wording for this system's
       module, via :func:`coverage_gap_text`) as the reading when one
       exists, else ``None``.
    """
    rows = mode06_rows or []
    failed = sorted((r for r in rows if r.get("passed") is False), key=_mid_priority)
    passed = sorted((r for r in rows if r.get("passed") is True), key=_mid_priority)

    if failed or dtc_fault or module_active:
        row = failed[0] if failed else None
        if row is not None:
            reading = _mode06_reading(row)
        elif module_active:
            reading = module_active_reading(module_active)
        else:
            reading = None
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

    if module_history:
        return {"system": system_key, "health": OK,
                "reading": module_history_reading(module_history),
                "spec_confidence": None, "spec_source": None, "margin": None}

    if pid_reading is not None:
        value = pid_reading.get("value")
        unit = pid_reading.get("unit", "")
        kg = known_good_row
        if kg and kg.get("confidence") != "UNKNOWN" and kg.get("normal") and value is not None:
            lo, hi = kg["normal"]
            ok = lo <= value <= hi
            m: Optional[str] = None
            if ok:
                if kg.get("direction") == "both" and lo is not None and hi is not None and lo == -hi:
                    m = symmetric_margin(value, hi, unit)
                elif hi:
                    m = margin(value, hi)
                elif lo:
                    m = margin(value, lo)
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

    return {"system": system_key, "health": GAP, "reading": coverage_text,
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
    "READINESS_MONITOR_NOTE", "margin", "symmetric_margin", "mode06_threshold",
    "mode06_reading", "module_dtc_category", "module_active_reading",
    "module_history_reading", "network_active_issue", "network_bus_event_note",
    "coverage_gap_text", "mode09_header_extras", "evap_iupr",
    "classify_system",
    "ACTIVE_FAULTS", "VERIFIED_CLEAN", "UNVERIFIED_REPAIR", "NO_DATA", "verdict",
]
