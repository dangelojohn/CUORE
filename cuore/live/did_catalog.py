"""Public-source UDS DIDs for the Giorgio platform, beyond what
``addressing.DIDS`` already encodes.

Source of truth for THIS module: the 2026-09-26 research pass across public
Giulia/Stelvio reverse-engineering projects (see
``docs/reference/STELVIO_READABLE_ITEMS.md`` for the full writeup):

* danardi78/Alfaromeo-Giulia-Stelvio-PIDs (GitHub) -- a CarScanner PID/DID
  export built and tested on the author's own Giulia 2.2 JTDm (diesel). The
  README states outright: "Those parameters are tested on my diesel version
  of Giulia, so maybe that some of that are not applicable and not working
  on 2.0L and 2.9L [petrol]." Every entry here sourced from it is therefore
  UNVERIFIED on this car's 2.0T GME-T4 engine, never CONFIRMED, and every
  diesel-specific group (DPF, EGR, common-rail injection timing, glow
  plugs) is skipped entirely rather than encoded with a ``diesel_only``
  flag, per instruction: this is a petrol car.
* ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3 and
  Simple_OBD2_for_AlfaRomeoGiulia (GitHub) -- confirmed against the
  author's own 2019 Giulia 2.0L petrol, but the published formulas overlap
  exactly with the danardi78/addressing.py rows already encoded (RPM,
  boost, gear, oil temp, coolant temp, battery voltage); nothing new to add
  here, but they corroborate that danardi78's formulas for those signals
  are not diesel-only.
* giuliaforums.com custom-PID thread -- paywalled/anti-scrape at the time of
  this research pass (HTTP 402 on fetch); not incorporated. Flagged as an
  unresolved source, not silently dropped.
* AlfaOBD / MultiEcuScan forum material on EVAP -- the vent valve /
  charcoal-canister actuator is exposed as an "ESIM" (Evaporative System
  Integrity Monitor) *routine* (UDS 0x31 RoutineControl), not a readable
  DID, and behind the SGW bypass on 2017+ cars. It cannot appear in this
  read-only catalog: RoutineControl is on ``safety.WRITE_SERVICES`` and is
  refused by ``assert_read_only_uds`` before a byte leaves the adapter. No
  public source was found giving a plain-read (0x22) EVAP DID -- tank
  pressure, purge duty, or canister state -- for this platform. The best
  EVAP-relevant *readable* items on this car remain the legislated Mode 01
  PIDs already in ``obd.py``: ``2E`` commanded_evap_purge, ``2F``
  fuel_level, ``32``/``53`` evap_vapor_pressure(_abs), plus the readiness
  monitor bit (``obd.evap_verdict``).
* commaai/opendbc ``fca_giorgio.dbc`` -- passive broadcast CAN signals
  (11-bit decimal IDs, not UDS DIDs/targets). These require no request at
  all; they are listened to, never queried. Kept separately in
  ``BROADCAST_SIGNALS`` per instruction. No EVAP/fuel signal was found in
  it. Includes the ``MAYBE_VOLTAGE`` signal at message 0xF1 that
  ``GIORGIO_MODULE_MAP.md`` Q9 asks about -- still UNVERIFIED, needs a DVOM
  check.
* BACCAble (gaucho1978/BACCAble) -- the tool's own README documents no
  broadcast ID catalog; its danardi78-derived DID list squats target 0xBA
  (``18DABAF1``), which ``GIORGIO_MODULE_MAP.md`` and ``addressing.py``
  already forbid (``RESERVED_TARGETS``) because of the immobiliser hazard.
  Those BACCAble-header rows are deliberately NOT encoded here at all --
  not even as UNVERIFIED -- because the target itself must never be used
  from this project, formula content aside.

Every entry below is genuinely new relative to ``addressing.DIDS`` (checked
by (module, did) pair at import time, see ``_check_no_overlap``). Nothing
here is invented: every DID/formula pair is quoted from a public source
listed above and in the docs page. Confidence is never upgraded past what
that source supports, and per the module confidence rules, nothing here is
CONFIRMED on this car.

Stdlib only.
"""

from __future__ import annotations

from .addressing import DIDS, DidSpec

# --- new UDS DIDs, ECM (header 18DA10F1) only ------------------------------
#
# Every module other than ECM in danardi78's CSV (TCM, BCM, IPC, EPS, RFHUB)
# has already been fully transcribed into addressing.DIDS; there was nothing
# left over for those modules. No public DID data was found for DTCM, ESM,
# DASM, ABS, ORC, AFLS, PAM, HALF, or any CAN-IHS module -- see the doc page.

EXTRA_DIDS: tuple[DidSpec, ...] = (
    DidSpec(
        module="ECM",
        did=0x1001,
        name="Fuel tank level",
        formula="A*100/255",
        unit="%",
        source="danardi78 (tested on Giulia 2.2 JTDm diesel)",
        confidence="unverified",
        note=("source also lists 'A*53/255' for the same DID in litres (53 L tank "
              "assumed); an EVAP-monitor precondition (fuel level gates the monitor), "
              "not itself an EVAP signal"),
    ),
    DidSpec(
        module="ECM",
        did=0x1009,
        name="Time since start (engine-on timer)",
        formula="((A*256)+B)/4",
        unit="min",
        source="danardi78",
        confidence="unverified",
        note="generic ECU housekeeping counter, not diesel-specific",
    ),
    DidSpec(
        module="ECM",
        did=0x3A41,
        name="Engine oil level",
        formula="(A*256+B)/1000",
        unit="L",
        source="danardi78",
        confidence="unverified",
        note="source labels this row '(benz)', i.e. explicitly the petrol variant",
    ),
    DidSpec(
        module="ECM",
        did=0x3A58,
        name="Intake manifold temperature (pre-intercooler)",
        formula="A-40",
        unit="°C",
        source="danardi78",
        confidence="unverified",
        note=("source vehicle is diesel; the 2.0T also has an intercooler but this "
              "DID is untested on it"),
    ),
    DidSpec(
        module="ECM",
        did=0x1924,
        name="Throttle position, sensor 1",
        formula="((A*256)+B)/655.35",
        unit="%",
        source="danardi78",
        confidence="unverified",
        note="electronic throttle body; applicable in principle to a turbo petrol engine",
    ),
    DidSpec(
        module="ECM",
        did=0x1925,
        name="Throttle position, sensor 2",
        formula="((A*256)+B)/655.35",
        unit="%",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x1926,
        name="Throttle position, sensor 3",
        formula="((A*256)+B)*100/24576",
        unit="%",
        source="danardi78",
        confidence="unverified",
        note="different scale than sensors 1/2 in the source; unresolved which reading is authoritative",
    ),
    DidSpec(
        module="ECM",
        did=0x193A,
        name="Wastegate / overboost valve position",
        formula="(((SIGNED(A)*256)+B))/100",
        unit="",
        source="danardi78",
        confidence="unverified",
        note="turbo boost-control actuator, directly relevant to the 2.0T's turbo",
    ),
    DidSpec(
        module="ECM",
        did=0x193C,
        name="Air mass measured",
        formula="((A*256)+B)/3",
        unit="mg/c",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x193D,
        name="Air mass required",
        formula="((A*256)+B)/3",
        unit="mg/c",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x1959,
        name="Boost pressure required (target)",
        formula="((A*256+B)-32768)/1000-1",
        unit="bar",
        source="danardi78",
        confidence="unverified",
        note=("distinct DID from the measured boost 0x195A already in addressing.DIDS; "
              "the same source also lists DID 0x1942 as a second, differently-formulaed "
              "'boost required' row (and, separately, as fuel consumption) -- an internal "
              "conflict in the source, so 0x1942 is not encoded at all; 0x1959 is kept "
              "because it is unambiguous and matches 0x195A's units"),
    ),
    DidSpec(
        module="ECM",
        did=0x195B,
        name="Boost pressure sensor (raw voltage)",
        formula="((A*256)+B)/10000",
        unit="V",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x1956,
        name="Ambient / barometric air pressure",
        formula="(A*256+B)-32768",
        unit="mbar",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x192F,
        name="A/C refrigerant pressure",
        formula="((A*256)+B)/100",
        unit="bar",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x192B,
        name="Cruise control target speed",
        formula="(((A*256)+B+1)/128)+2",
        unit="km/h",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x1B00,
        name="Start&Stop status",
        formula="A",
        unit="",
        source="danardi78",
        confidence="unverified",
        note="stop-start is fitted to the petrol 2.0T",
    ),
    DidSpec(
        module="ECM",
        did=0x1B02,
        name="Start&Stop request",
        formula="A",
        unit="",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x1923,
        name="Clutch / torque-converter status",
        formula="A",
        unit="",
        source="danardi78",
        confidence="unverified",
        note="danardi78's own car is a diesel; meaning on the ZF 8HP torque-converter automatic is unclear",
    ),
    DidSpec(
        module="ECM",
        did=0x2001,
        name="Odometer",
        formula="((((A*256)+B)*256)+C)/10",
        unit="km",
        source="danardi78",
        confidence="unverified",
    ),
    DidSpec(
        module="ECM",
        did=0x2003,
        name="Number of ECU programming events",
        formula="A",
        unit="",
        source="danardi78",
        confidence="unverified",
        note="anti-tamper / service-history value",
    ),
    DidSpec(
        module="ECM",
        did=0x2005,
        name="Maximum RPM recorded (over-rev log)",
        formula="A",
        unit="rpm",
        source="danardi78",
        confidence="unverified",
    ),
)


def _check_no_overlap() -> None:
    existing = {(d.module, d.did) for d in DIDS}
    dupes = [(d.module, f"{d.did:04X}") for d in EXTRA_DIDS if (d.module, d.did) in existing]
    if dupes:
        raise AssertionError(f"did_catalog.EXTRA_DIDS duplicates addressing.DIDS: {dupes}")


_check_no_overlap()


# --- passive broadcast CAN signals (no request; listen only) --------------
#
# From commaai/opendbc's fca_giorgio.dbc (public, reverse-engineered from a
# Giorgio-platform car for openpilot; PR #1251). Message IDs are the
# 11-bit decimal/hex CAN IDs used on the broadcast bus -- these are NOT UDS
# targets and carry no request/response pair; a passive listen (STCMM 0)
# is the only way to read them, matching the module map's "broadcast CAN
# IDs are passive" note. Which physical bus (CAN-C vs CAN-CH) each message
# rides is UNVERIFIED here; opendbc does not distinguish buses and this car
# has not been probed for them. No EVAP- or fuel-system broadcast signal
# was found anywhere in the DBC. Many raw signals in the DBC are still named
# "NEW_SIGNAL_n" / "UNKNOWN_n" by its own authors -- i.e. even the upstream
# project marks them as not fully reverse-engineered; only meaningfully
# named signals are reproduced below. This is a representative subset, not
# the full ~150-signal file; see the DBC itself for the rest.
BROADCAST_SIGNALS: tuple[dict, ...] = (
    {"can_id": "0xDE", "message": "EPS_1", "signal": "STEERING_ANGLE",
     "start_bit": 5, "length": 14, "scale": 0.1, "offset": -716.8, "unit": "deg",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified",
     "note": "matches danardi78/addressing.py DA2AF1 22083C steering angle in kind, not value"},
    {"can_id": "0xDE", "message": "EPS_1", "signal": "STEERING_RATE",
     "start_bit": 19, "length": 12, "scale": 0.5, "offset": -1000, "unit": "deg/s",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xEE", "message": "ABS_1", "signal": "WHEEL_SPEED_FL",
     "start_bit": 7, "length": 13, "scale": 0.017, "offset": 0, "unit": "m/s",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xEE", "message": "ABS_1", "signal": "WHEEL_SPEED_FR",
     "start_bit": 10, "length": 13, "scale": 0.017, "offset": 0, "unit": "m/s",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xEE", "message": "ABS_1", "signal": "WHEEL_SPEED_RL",
     "start_bit": 29, "length": 13, "scale": 0.017, "offset": 0, "unit": "m/s",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xEE", "message": "ABS_1", "signal": "WHEEL_SPEED_RR",
     "start_bit": 32, "length": 13, "scale": 0.017, "offset": 0, "unit": "m/s",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xF1", "message": "NEW_MSG_F1", "signal": "MAYBE_VOLTAGE",
     "start_bit": 18, "length": 10, "scale": 0.02, "offset": 0, "unit": "",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified",
     "note": ("this is GIORGIO_MODULE_MAP.md Q9's '0x0F1.MAYBE_VOLTAGE'; upstream itself "
              "has not named it with confidence, validate against a DVOM before trusting it "
              "as battery voltage")},
    {"can_id": "0xFC", "message": "ENGINE_1", "signal": "ENGINE_RPM",
     "start_bit": 7, "length": 14, "scale": 1, "offset": 0, "unit": "rev/min",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xFC", "message": "ENGINE_1", "signal": "ACCEL_PEDAL",
     "start_bit": 20, "length": 8, "scale": 0.4, "offset": 0, "unit": "percent",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xFE", "message": "ABS_2", "signal": "LONG_ACCEL",
     "start_bit": 7, "length": 12, "scale": 0.01, "offset": -20.48, "unit": "m/s2",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xFE", "message": "ABS_2", "signal": "LATERAL_ACCEL",
     "start_bit": 11, "length": 12, "scale": 0.01, "offset": -20.48, "unit": "m/s2",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0xFE", "message": "ABS_2", "signal": "YAW_RATE",
     "start_bit": 31, "length": 12, "scale": -0.0014, "offset": 2.86, "unit": "rad/s",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0x101", "message": "ABS_6", "signal": "VEHICLE_SPEED",
     "start_bit": 15, "length": 11, "scale": 0.017, "offset": 0, "unit": "m/s",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0x106", "message": "EPS_2", "signal": "DRIVER_TORQUE",
     "start_bit": 23, "length": 11, "scale": 1, "offset": -1024, "unit": "",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0x73E", "message": "BCM_1", "signal": "LEFT_TURN_STALK",
     "start_bit": 17, "length": 1, "scale": 1, "offset": 0, "unit": "",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0x73E", "message": "BCM_1", "signal": "RIGHT_TURN_STALK",
     "start_bit": 16, "length": 1, "scale": 1, "offset": 0, "unit": "",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0x5A2", "message": "ACC_1", "signal": "HUD_SPEED",
     "start_bit": 7, "length": 8, "scale": 1, "offset": 0, "unit": "km/h",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
    {"can_id": "0x5A2", "message": "ACC_1", "signal": "CRUISE_STATUS",
     "start_bit": 22, "length": 2, "scale": 1, "offset": 0, "unit": "",
     "source": "opendbc fca_giorgio.dbc", "confidence": "unverified"},
)


def all_dids(module: str, *, include_diesel: bool = False) -> list[DidSpec]:
    """``addressing.dids_for(module)`` plus this module's ``EXTRA_DIDS``,
    de-duplicated by (module, did). ``addressing.DIDS`` wins any collision
    (there should be none; see ``_check_no_overlap``)."""
    from .addressing import dids_for

    base = dids_for(module, include_diesel=include_diesel)
    seen = {(d.module, d.did) for d in base}
    extra = [d for d in EXTRA_DIDS
             if d.module == module and (d.module, d.did) not in seen
             and (include_diesel or not d.diesel_only)]
    return base + extra


__all__ = ["EXTRA_DIDS", "BROADCAST_SIGNALS", "all_dids"]
