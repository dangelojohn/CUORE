"""Known-good live-channel reference bands for the 2018 Alfa Romeo Stelvio 2.0T.

Backs the live-dashboard gauges (``cuore.live.layouts``, via
``cuore.services.known_good_bridge`` -- cuore never imports this module
directly) with a band per channel id from :mod:`cuore.live.channels`: what a
healthy reading looks like, what counts as a caution, and what counts as an
alarm, plus where every number came from.

Confidence levels reuse :mod:`mes.service_specs` verbatim -- same meaning,
same enforcement:

* ``CONFIRMED``     -- an actual manufacturer document.
* ``CORROBORATED``  -- two independent non-manufacturer sources agree.
* ``SINGLE_SOURCE`` -- exactly one source found, not cross-checked.
* ``UNKNOWN``       -- nothing credible found. ``normal``/``warn``/``alarm``
                       are all ``None``, never placeholder numbers --
                       ``notes`` always points at the service manual.

``generic: True`` marks a value that is a generic OBD-II/SAE/physics/
lead-acid-battery norm, not a Stelvio-specific spec -- allowed by
instruction, but never to be confused with a manufacturer figure. A value
that is Stelvio/Giulia-specific but sourced from a forum thread (not a
manufacturer document) is ``SINGLE_SOURCE`` or ``CORROBORATED`` with
``generic: False``.

Research pass done 2026-09-26, same pass and sourcing conventions as
``service_specs.py``: web search against public sources (stelvioforum.com,
giuliaforums.com, generic OBD-II/repair references), the 2018 Stelvio US
owner's manual (vehicleinfo.mopar.com), and this repo's own
``docs/reference/ZF8HP_SERVICE_DATA.md``. Two stelvioforum/giuliaforums
threads used here redirected to a bot-gate (``tollbit.<site>``) that could
not be resolved during this pass, so those rows are read via the search
engine's own summary of the thread, not the full text -- flagged in
``notes``, same as the precedent in ``service_specs.TORQUES``
(``caliper_slider_rear``). No paywalled/bot-gated FCA TechAuthority document
was reached -- every ``TECHAUTHORITY`` pointer is a "go get it", not a claim
that document was read.

The genuinely important gap this module is built to help close: no OEM or
corroborated figure exists anywhere in this research pass for EVAP purge
duty or vapor pressure on this platform (see ``commanded_evap_purge``,
``evap_vapor_pressure*`` below) -- exactly the channels that matter for this
car's chronic P0440/P0455/P0456 diagnosis. :func:`observed_ranges` exists so
this car's own logged behaviour can stand in for the spec that was never
published.

See ``docs/reference/STELVIO_20T_KNOWN_GOOD_VALUES.md`` for the
human-readable writeup with the same data and full source links.
"""

from __future__ import annotations

from typing import Any, Optional

from .catalog import CATALOG
from .errors import MesError
from .service_specs import (CONFIDENCE_LEVELS, CONFIRMED, CORROBORATED,  # noqa: F401
                            SINGLE_SOURCE, TECHAUTHORITY, UNKNOWN, VEHICLE)

_DIRECTIONS = ("above", "below", "both")

KNOWN_GOOD: dict[str, dict[str, Any]] = {}


def _band(name: str, value: Optional[tuple[float, float]]) -> Optional[list[float]]:
    if value is None:
        return None
    lo, hi = value
    if lo > hi:
        raise ValueError(f"{name} band must have lo <= hi, got {value!r}")
    return [float(lo), float(hi)]


def _kg(channel_id: str, name: str, unit: str, conditions: str, *,
        normal: Optional[tuple[float, float]] = None,
        warn: Optional[tuple[float, float]] = None,
        alarm: Optional[tuple[float, float]] = None,
        direction: str = "both", confidence: str = UNKNOWN,
        source: Optional[str] = None, notes: str = "",
        generic: bool = False) -> None:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r} for {channel_id!r}")
    if direction not in _DIRECTIONS:
        raise ValueError(f"bad direction {direction!r} for {channel_id!r}; "
                         f"one of {_DIRECTIONS}")
    if not notes and confidence == UNKNOWN:
        notes = TECHAUTHORITY
    KNOWN_GOOD[channel_id] = {
        "id": channel_id,
        "name": name,
        "unit": unit,
        "conditions": conditions,
        "normal": _band("normal", normal),
        "warn": _band("warn", warn),
        "alarm": _band("alarm", alarm),
        "direction": direction,
        "confidence": confidence,
        "source": source,
        "notes": notes.strip(),
        "generic": generic,
    }


# --- engine basics ------------------------------------------------------------

_kg("engine_rpm", "Engine RPM", "rpm",
    "hot idle (90+ C coolant), in Park/Neutral, no accessory load",
    normal=(700, 900), warn=(600, 1050), alarm=(400, 1300), direction="both",
    confidence=SINGLE_SOURCE,
    source="https://www.stelvioforum.com/threads/correct-idle-speed-and-service-alarm.18670/",
    notes="No published factory hot-idle RPM figure was located. Band is "
          "synthesized from forum reports (owners citing roughly 800 rpm "
          "warm idle on this platform's 2.0T/2.2D family; one Stelvio QV "
          "V6 owner reported ~1000 rpm, not used here as it is a different "
          "engine). The source thread redirected through a bot-gate "
          "(tollbit.stelvioforum.com) that could not be resolved during "
          "this pass -- read via the search engine's own summary only, not "
          "the full thread. Confirm against TechAuthority or this car's "
          "own MES-logged idle RPM (see observed_ranges).")

_kg("engine_coolant_temp", "Engine coolant temperature", "C",
    "warmed up, thermostat open, hot idle through cruise",
    normal=(88, 105), warn=(105, 115), alarm=(115, 130), direction="above",
    confidence=SINGLE_SOURCE,
    source="https://www.stelvioforum.com/threads/coolant-operating-temperature-2-0-engine.17855/",
    notes="Forum-reported range (~190-220 F / ~88-104 C) for this "
          "platform's 2.0T, read via a search-engine summary only -- the "
          "thread redirected through a bot-gate that could not be resolved "
          "during this pass. IMPORTANT CAVEAT from the same research: this "
          "platform's dashboard temperature gauge is reported to actually "
          "read engine OIL temperature, not coolant -- the PIDs here (Mode "
          "01 05h) are the legislated coolant sensor regardless of what "
          "the dash shows, but do not assume forum posters quoting 'the "
          "temp gauge' were describing this PID. No FCA document for "
          "either value was located. " + TECHAUTHORITY)

_kg("intake_air_temp", "Intake air temperature", "C",
    "any -- tracks ambient plus heat soak",
    direction="both", confidence=UNKNOWN,
    notes="No fixed 'normal' band is meaningful for IAT -- it tracks "
          "ambient air temperature and rises with under-hood heat soak at "
          "idle/after a hot shutdown, generically by tens of degrees C on "
          "any turbocharged engine, then falls back toward ambient once "
          "airflow resumes. No Stelvio-specific figure exists to compare "
          "against; use this car's own observed_ranges() alongside the "
          "ambient_air_temp PID read at the same moment. " + TECHAUTHORITY)

_kg("intake_map", "Intake manifold absolute pressure", "kPa",
    "hot idle, no load -- naturally-aspirated-idle vacuum regime (the "
    "turbo does not boost at idle)",
    normal=(20, 35), warn=(15, 45), alarm=(0, 60), direction="both",
    confidence=SINGLE_SOURCE, generic=True,
    source="https://engineerskill.blog/map-sensor-reading-at-idle",
    notes="Generic gasoline-engine idle-MAP guideline (20-35 kPa absolute "
          "at hot idle, no load), not Stelvio-specific -- but physically "
          "applicable at idle since the turbo is unspooled and the intake "
          "behaves like a naturally-aspirated engine's. Not valid once "
          "under load/boost -- see 'boost' below for that regime, which is "
          "UNKNOWN. Also varies with altitude/weather via barometric "
          "pressure; compare against barometric_pressure read at the same "
          "moment, not this fixed band, at elevation.")

_kg("barometric_pressure", "Barometric (atmospheric) pressure", "kPa",
    "any -- plausibility check on the sensor, not a vehicle health check",
    normal=(95, 105), warn=(90, 108), alarm=(80, 115), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://en.wikipedia.org/wiki/Atmospheric_pressure",
    notes="Standard sea-level pressure is 101.325 kPa; day-to-day station "
          "pressure at typical driving elevations commonly runs "
          "~95-105 kPa (physics/meteorology reference, not "
          "Stelvio-specific). A reading well outside this band at low "
          "elevation indicates a sensor fault rather than weather; at high "
          "elevation a lower reading is expected and normal.")

_kg("boost", "Boost (MAP - baro, computed)", "kPa",
    "under load/acceleration",
    direction="above", confidence=UNKNOWN,
    notes="No credible peak-boost figure was found for this platform's "
          "stock 2.0T GME-T4. One search turned up mutually inconsistent "
          "numbers on the same page (an OBD2-port-readable ceiling of "
          "~22 psi / ~152 kPa gauge quoted alongside a claimed ~25 psi "
          "actual peak and a ~2.5 bar turbo hardware rating that reads as "
          "an upgrade-turbo capability, not the stock boost target) -- not "
          "corroborating, not adopted as a spec. Do not set an alarm band "
          "from this. Cross-check against the unverified ecm_195a DID "
          "instead, and against this car's own observed_ranges() under "
          "boost. " + TECHAUTHORITY)

_kg("ecm_195a", "Boost pressure (ECM DID 0x195A)", "bar",
    "under load/acceleration",
    direction="above", confidence=UNKNOWN,
    notes="The DID formula itself is UNVERIFIED on this 2.0T (danardi78 "
          "catalog, confirmed only on a diesel Giulia) -- see "
          "cuore/live/did_catalog.py / addressing.py. No peak-boost figure "
          "to compare it against exists either (see 'boost' above). "
          "Cross-check readings against the computed 'boost' channel "
          "before trusting either. " + TECHAUTHORITY)

# --- fuel trims / O2 / load / throttle ----------------------------------------

_FUEL_TRIM_NOTE = (
    "Generic OBD-II fuel-trim guideline, not Stelvio-specific: within "
    "roughly +/-10% is considered in-spec across multiple independent "
    "repair-reference sources; long-term trim beyond roughly +/-20% is "
    "widely described as indicating a serious fuel-system or sensor fault. "
    "Requires closed-loop operation (warm engine) to mean anything.")

_kg("short_fuel_trim_b1", "Short-term fuel trim, bank 1", "%",
    "closed loop, warm engine, steady idle or cruise",
    normal=(-10, 10), warn=(-15, 15), alarm=(-20, 20), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://www.obd-codes.com/faq/fuel-trims.php",
    notes=_FUEL_TRIM_NOTE)

_kg("long_fuel_trim_b1", "Long-term fuel trim, bank 1", "%",
    "closed loop, warm engine, steady idle or cruise",
    normal=(-10, 10), warn=(-15, 15), alarm=(-20, 20), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://www.obd-codes.com/faq/fuel-trims.php",
    notes=_FUEL_TRIM_NOTE)

_kg("short_fuel_trim_b2", "Short-term fuel trim, bank 2", "%",
    "closed loop, warm engine, steady idle or cruise",
    normal=(-10, 10), warn=(-15, 15), alarm=(-20, 20), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://www.obd-codes.com/faq/fuel-trims.php",
    notes=_FUEL_TRIM_NOTE + " CAVEAT: this engine (GME-T4) is an inline-4 "
          "with a single exhaust bank; a legislated scan tool must still "
          "expose Bank 2 PIDs, but there may be no physical second bank to "
          "measure. A Bank 2 reading pinned at 0% (or otherwise static) is "
          "consistent with 'not applicable to this engine', not "
          "necessarily a fault -- confirm which is true for this ECU "
          "before treating a Bank 2 deviation as meaningful.")

_kg("long_fuel_trim_b2", "Long-term fuel trim, bank 2", "%",
    "closed loop, warm engine, steady idle or cruise",
    normal=(-10, 10), warn=(-15, 15), alarm=(-20, 20), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://www.obd-codes.com/faq/fuel-trims.php",
    notes=_FUEL_TRIM_NOTE + " Same single-exhaust-bank caveat as "
          "short_fuel_trim_b2.")

_kg("o2_b1s1_voltage", "O2 sensor, bank 1 sensor 1, voltage", "V",
    "closed loop, warm engine -- should be actively oscillating, not static",
    normal=(0.1, 0.9), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://www.fluke.com/en-us/learn/blog/digital-multimeters/how-to-monitor-oxygen-sensor-voltage-with-a-multimeter",
    notes="Generic narrowband-O2 guideline, not Stelvio-specific: a "
          "healthy sensor in closed loop cycles between roughly 0.1 V "
          "(lean) and 0.9 V (rich), crossing ~0.45 V several times per "
          "second. No warn/alarm band is set deliberately -- the "
          "diagnostic signature of a failing sensor is a value that stops "
          "switching (pinned near one voltage) rather than a value outside "
          "this range at any single instant; compare successive samples, "
          "the same way mes.params.ParamSeries.stats() flags a 'static' "
          "parameter.")

_kg("throttle_position", "Throttle position", "%",
    "any -- tracks driver/ECU input, not a health check",
    normal=(0, 100), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://en.wikipedia.org/wiki/OBD-II_PIDs",
    notes="0-100% is simply this Mode 01 PID's defined output range (SAE "
          "J1979), not a diagnostic band -- there is no 'abnormal' "
          "throttle position in isolation. No warn/alarm band is "
          "meaningful; use this alongside engine_rpm/vehicle_speed to spot "
          "an implausible combination (e.g. high throttle with no RPM "
          "response) rather than as a threshold on its own.")

_kg("absolute_load", "Calculated engine load", "%",
    "any -- tracks driving conditions, not a health check",
    normal=(0, 100), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://en.wikipedia.org/wiki/OBD-II_PIDs",
    notes="Same treatment as throttle_position: 0-100% is the PID's "
          "defined range, not a fault band.")

# --- electrical -----------------------------------------------------------

_kg("battery_voltage", "Battery voltage", "V",
    "engine running, alternator charging (see notes for the engine-off "
    "resting spec)",
    normal=(13.5, 14.7), warn=(12.0, 15.0), alarm=(11.0, 15.5),
    direction="both", confidence=CORROBORATED, generic=True,
    source="https://www.firestonecompleteautocare.com/blog/batteries/car-battery-voltage/",
    notes="Generic 12V lead-acid charging-system guideline, not "
          "Stelvio-specific: engine running/alternator charging, "
          "~13.5-14.7 V is normal; below that the charging system is "
          "under-delivering, above ~15 V suggests a regulator fault. "
          "ENGINE OFF, battery rested >30 min: ~12.2-12.8 V is a healthy "
          "resting charge, below ~12.0 V is discharged (same generic "
          "sources) -- do not compare a running reading against this "
          "resting band or vice versa. A brief dip toward ~10 V during "
          "cranking is normal, not a fault. No FCA-specific charging "
          "voltage spec was located for this platform.")

# --- fuel / EVAP (P0440/P0455/P0456 job) --------------------------------------

_kg("fuel_level", "Fuel level", "%",
    "any -- tank level, not a health check",
    normal=(0, 100), direction="both",
    confidence=CORROBORATED, generic=True,
    source="https://en.wikipedia.org/wiki/OBD-II_PIDs",
    notes="0-100% is the PID's defined range; there is no 'abnormal' fuel "
          "level. Included here because EVAP vapor-pressure behavior is "
          "read relative to fuel level (a near-full or near-empty tank "
          "changes expected vapor-space pressure response) on the EVAP job "
          "preset -- see commanded_evap_purge / evap_vapor_pressure*.")

_EVAP_NOTE = (
    "No OEM or corroborated figure for this quantity was found anywhere "
    "in this research pass or in service_specs.py/did_catalog.py -- this "
    "platform exposes no readable EVAP-specific UDS DID (the vent/purge "
    "actuator is a RoutineControl-only ESIM routine, refused by this "
    "project's read-only safety gate; see cuore/live/did_catalog.py). "
    "This is exactly the channel that matters for this car's chronic "
    "P0440/P0455/P0456 diagnosis (see project_stelvio_evap notes), and "
    "exactly the case observed_ranges() exists for: this car's own logged "
    "behaviour is the only baseline available until a TechAuthority figure "
    "is obtained.")

_kg("commanded_evap_purge", "Commanded EVAP purge duty", "%",
    "purge-monitor test conditions (see mes.faulttree for this platform's "
    "EVAP isolation sequence)",
    direction="both", confidence=UNKNOWN, notes=_EVAP_NOTE)

_kg("evap_vapor_pressure", "EVAP system vapor pressure", "Pa",
    "purge-monitor test conditions",
    direction="both", confidence=UNKNOWN, notes=_EVAP_NOTE)

_kg("evap_vapor_pressure_abs", "EVAP system vapor pressure, absolute", "kPa",
    "purge-monitor test conditions",
    direction="both", confidence=UNKNOWN, notes=_EVAP_NOTE)

# --- transmission (ZF 8HP) -----------------------------------------------------

_kg("tcm_04fe", "Gearbox (ZF 8HP) fluid temperature", "C",
    "normal driving, fluid warmed up -- NOT the 30-50 C fill-check window",
    normal=(80, 100), warn=(100, 120), alarm=(120, 150), direction="above",
    confidence=SINGLE_SOURCE, generic=True,
    source="https://www.dodgedurango.net/threads/normal-zf-transmission-operating-temp-for-2019-gt.89031/",
    notes="Generic ZF 8HP guideline attributed to ZF technical support in "
          "one owner forum thread (80-100 C / 176-212 F normal, 120 C+ "
          "risking overheat/module damage) -- not Stelvio-specific, and "
          "the OEM (here FCA/Alfa) writes the actual software thresholds, "
          "which may differ. Do not confuse this normal-driving band with "
          "the CONFIRMED 30-50 C fluid-fill-check window documented in "
          "docs/reference/ZF8HP_SERVICE_DATA.md (service_specs.py "
          "transmission_fill_plug) -- that is a static service procedure "
          "temperature, not a driving range. Also note: the DID formula "
          "itself (A-40, danardi78) is UNVERIFIED on this 2.0T's TCM -- "
          "treat any absolute reading with that additional caveat.")

# --- tyres (TPMS via RFHUB) ----------------------------------------------------

_TPMS_NOTE = (
    "Tyre pressure is fitment- and load-dependent and MUST be read from "
    "this VIN's own door-jamb placard, not assumed from any published "
    "figure. One SINGLE-SOURCE, 19-inch-fitment-only aggregator figure "
    "was found (front 207 kPa/30 psi/2.07 bar, rear 228 kPa/33 psi/2.28 "
    "bar -- service_specs.BRAKE_SPEC['tire_pressure_kpa']), sourced to a "
    "HaynesPro-derived listing that could not be re-verified against the "
    "manufacturer placard image (image-based PDF, no extractable text) "
    "and is not known to match this VIN's actual wheel option -- kept "
    "UNKNOWN here rather than treated as a spec. RFHUB DID formulas "
    "(pressure/temp) are themselves UNVERIFIED (danardi78 catalog). " +
    TECHAUTHORITY)

for _corner in ("fl", "fr", "rl", "rr"):
    _did = {"fl": "40b1", "fr": "40b2", "rl": "40b3", "rr": "40b4"}[_corner]
    _kg(f"rfhub_{_did}_pressure", f"Tire pressure, {_corner.upper()}", "bar",
        "cold tyres, before driving (placard condition)",
        direction="both", confidence=UNKNOWN, notes=_TPMS_NOTE)
    _kg(f"rfhub_{_did}_temp", f"Tire temperature, {_corner.upper()}", "C",
        "any -- rises with driving; no fixed 'normal' exists",
        direction="above", confidence=UNKNOWN,
        notes="Tyre temperature rises with driving/load and has no fixed "
              "placard-style spec; compare corner-to-corner (a single hot "
              "corner suggests drag/underinflation) rather than against an "
              "absolute number. " + TECHAUTHORITY)
del _corner, _did


# Safety net, mirroring service_specs.TORQUES: every UNKNOWN row must point
# at TechAuthority even if its own notes were specific enough that the
# pointer looks redundant. Idempotent.
for _row in KNOWN_GOOD.values():
    if _row["confidence"] == UNKNOWN and TECHAUTHORITY not in (_row.get("notes") or ""):
        _row["notes"] = (_row["notes"] + " " if _row["notes"] else "") + TECHAUTHORITY
del _row


def known_good(channel_id: str) -> Optional[dict[str, Any]]:
    """One channel's band, or ``None`` if this module has nothing for it."""
    row = KNOWN_GOOD.get(channel_id)
    return dict(row) if row is not None else None


def all_known_good() -> dict[str, dict[str, Any]]:
    """Every channel this module has a band (or a documented UNKNOWN) for."""
    return {cid: dict(row) for cid, row in KNOWN_GOOD.items()}


# ===========================================================================
# observed_ranges: what this car's own MES logs actually show
# ===========================================================================

#: channel id -> case-insensitive substrings to match against MES parameter/
#: CSV column names. The first alias that matches a name in a given log wins
#: for that log; a channel absent from every log it's checked against is
#: simply left out of observed_ranges()'s result.
PARAM_ALIASES: dict[str, tuple[str, ...]] = {
    "engine_rpm": ("engine speed",),
    "engine_coolant_temp": ("engine temperature", "coolant temp"),
    "intake_air_temp": ("intake air temp", "air temperature"),
    "intake_map": ("manifold absolute pressure", "map"),
    "barometric_pressure": ("barometric", "atmospheric pressure"),
    "short_fuel_trim_b1": ("short term fuel trim", "short fuel trim"),
    "long_fuel_trim_b1": ("long term fuel trim", "long fuel trim"),
    # No "o2_b1s1_voltage" entry: this car's FES logs name lambda-system
    # parameters ("Lambda control", "Lambda sensor N integrator", "Lambda 1
    # signal (Pre/After-Cat.)") rather than a plain "oxygen sensor voltage"
    # -- none of them is confidently the same Mode 01 PID 14h quantity (a
    # trial match pulled in "Lambda sensor 1 integrator", a fuel-trim-like
    # dimensionless value around 1.0, not a 0-1 V signal). Left unmapped
    # rather than risk mislabeling a different quantity as this channel's
    # voltage.
    "throttle_position": ("throttle position",),
    "absolute_load": ("calculated load", "engine load"),
    "battery_voltage": ("battery voltage",),
    "fuel_level": ("fuel level",),
    "commanded_evap_purge": ("evap purge", "purge duty", "canister purge"),
    "evap_vapor_pressure": ("vapor pressure", "tank pressure"),
    "evap_vapor_pressure_abs": ("vapor pressure", "tank pressure"),
    "tcm_04fe": ("gearbox oil temp", "transmission oil temp",
                "transmission fluid temp"),
}


#: Qualifier words that mean a name containing an alias is a *different*
#: signal from the plain one wanted here (a maximum, a target, a derived
#: rate) -- "Max. engine speed time" contains the alias "engine speed" but
#: is not the RPM channel. Disqualified names are used only if nothing else
#: matches at all, never preferred over a clean match.
_DISQUALIFIERS = ("max.", "max ", "maximum", "min.", "min ", "minimum",
                  "desired", "target", "limit", "derivative", "variation",
                  "over-rev", "time", "counter", "average", "avg")


def _best_match(names: list[str], alias: str) -> Optional[str]:
    """The name best matching ``alias`` (a lowercase substring), or ``None``.

    Prefers, in order: an exact case-insensitive match; the shortest clean
    (non-disqualified) substring match, on the theory that the plain signal
    name is shorter than any qualified variant of it; then, only if nothing
    clean matched, the shortest disqualified match rather than nothing.
    """
    candidates = [n for n in names if alias in n.lower()]
    if not candidates:
        return None
    for n in candidates:
        if n.lower() == alias:
            return n
    clean = [n for n in candidates
            if not any(d in n.lower() for d in _DISQUALIFIERS)]
    pool = clean or candidates
    return min(pool, key=len)


def _quantile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation percentile over an already-sorted list."""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _fes_numbers(vin: str, aliases: tuple[str, ...]
                 ) -> tuple[list[float], str, set[str]]:
    """Numeric samples for one channel, pooled across this VIN's FES logs."""
    from . import fes as fes_mod  # local: keep this module importable even
                                  # if fes.py's optional deps are absent

    numbers: list[float] = []
    unit = ""
    sources: set[str] = set()
    try:
        entries = CATALOG.select(vin=vin, kind="fes", include_simulation=False)
    except Exception:
        return numbers, unit, sources
    for entry in entries:
        if entry.parse_error:
            continue
        try:
            log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
        except MesError:
            continue
        names = log.param_names()
        for alias in aliases:
            match = _best_match(names, alias)
            if not match:
                continue
            series = log.series(match)
            nums = series.numbers
            if nums:
                numbers.extend(nums)
                unit = unit or series.unit
                sources.add(entry.name)
            break
    return numbers, unit, sources


def _csv_numbers(aliases: tuple[str, ...]) -> tuple[list[float], str, set[str]]:
    """Numeric samples for one channel, pooled across every CSV recording
    found on this install. CSV recordings carry no VIN of their own (see
    mes.csvlog), so this pools in regardless of the ``vin`` asked for --
    reasonable on a single-car install, flagged in the docstring for a
    multi-car one."""
    from . import csvlog

    numbers: list[float] = []
    unit = ""
    sources: set[str] = set()
    try:
        recs = csvlog.list_recordings()
    except Exception:
        return numbers, unit, sources
    for rec_info in recs:
        name = rec_info.get("file")
        if not name or rec_info.get("parse_error"):
            continue
        try:
            rec = csvlog.load_named(name)
        except MesError:
            continue
        col_names = [c.name for c in rec.columns]
        for alias in aliases:
            match = _best_match(col_names, alias)
            if not match:
                continue
            col = rec.find_column(match)
            nums = [v for _, v in rec.numbers(str(col.index))]
            if nums:
                numbers.extend(nums)
                unit = unit or col.unit
                sources.add(name)
            break
    return numbers, unit, sources


def observed_ranges(vin: str) -> dict[str, Any]:
    """Per-channel percentiles observed on this car's own MES logs.

    Not a spec -- see :data:`KNOWN_GOOD` for that; label any value from here
    "observed on this car", never as a spec, per instruction. Pools:

    * every non-simulated FES session log for ``vin`` (:mod:`mes.fes`,
      selected through :data:`mes.catalog.CATALOG`), matched against
      :data:`PARAM_ALIASES` by loose case-insensitive substring against the
      parameter names actually printed in each log; and
    * every CSV graph recording found on this install (:mod:`mes.csvlog`) --
      pooled in regardless of ``vin`` since a CSV recording carries none of
      its own (see :func:`_csv_numbers`).

    Percentiles (p10/p50/p90) use linear interpolation
    (:func:`_quantile`) over the pooled, sorted sample; :mod:`mes.params`
    supplies the typed ``ParamSeries``/``ParamValue`` machinery both log
    kinds are read through. A channel with no matching parameter in any log
    checked is simply absent from the result -- never reported as a zero or
    a guess.
    """
    if not vin.strip():
        raise ValueError("a VIN is required")
    out: dict[str, Any] = {}
    for channel_id, aliases in PARAM_ALIASES.items():
        fes_nums, fes_unit, fes_sources = _fes_numbers(vin, aliases)
        csv_nums, csv_unit, csv_sources = _csv_numbers(aliases)
        nums = fes_nums + csv_nums
        if not nums:
            continue
        nums.sort()
        out[channel_id] = {
            "n": len(nums),
            "unit": fes_unit or csv_unit,
            "min": nums[0],
            "p10": round(_quantile(nums, 0.10), 4),
            "p50": round(_quantile(nums, 0.50), 4),
            "p90": round(_quantile(nums, 0.90), 4),
            "max": nums[-1],
            "sources": {
                "fes_logs": sorted(fes_sources),
                "csv_recordings": sorted(csv_sources),
            },
        }
    return out


__all__ = [
    "KNOWN_GOOD", "known_good", "all_known_good", "PARAM_ALIASES",
    "observed_ranges", "VEHICLE",
]
