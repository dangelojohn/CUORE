"""J1979 decoding: PIDs with formulas, 2-byte and 3-byte DTCs, readiness.

Pure functions over byte lists. The two readiness layouts (spark and
compression ignition) are both here because a diesel Stelvio reports the
non-continuous monitors under different bit names, and decoding it with the
spark table gives confident nonsense.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .errors import BadCommand

HEX_DIGITS = frozenset("0123456789ABCDEF")


def _u16(d: list[int]) -> int:
    return (d[0] << 8) | d[1]


def _s16(d: list[int]) -> int:
    v = _u16(d)
    return v - 65536 if v & 0x8000 else v


@dataclass(frozen=True)
class PID:
    pid: str                                  # hex, two chars
    name: str
    unit: str
    n_bytes: int
    decode: Callable[[list[int]], float]
    description: str = ""


_PID_LIST: tuple[PID, ...] = (
    PID("05", "engine_coolant_temp", "C", 1, lambda d: d[0] - 40),
    PID("06", "short_fuel_trim_b1", "%", 1, lambda d: d[0] / 1.28 - 100),
    PID("07", "long_fuel_trim_b1", "%", 1, lambda d: d[0] / 1.28 - 100),
    PID("08", "short_fuel_trim_b2", "%", 1, lambda d: d[0] / 1.28 - 100),
    PID("09", "long_fuel_trim_b2", "%", 1, lambda d: d[0] / 1.28 - 100),
    PID("0A", "fuel_pressure", "kPa", 1, lambda d: d[0] * 3),
    PID("0B", "intake_map", "kPa", 1, lambda d: d[0]),
    PID("0C", "engine_rpm", "rpm", 2, lambda d: _u16(d) / 4),
    PID("0D", "vehicle_speed", "km/h", 1, lambda d: d[0]),
    PID("0E", "timing_advance", "deg", 1, lambda d: d[0] / 2 - 64),
    PID("0F", "intake_air_temp", "C", 1, lambda d: d[0] - 40),
    PID("10", "maf", "g/s", 2, lambda d: _u16(d) / 100),
    PID("11", "throttle_position", "%", 1, lambda d: d[0] * 100 / 255),
    PID("14", "o2_b1s1_voltage", "V", 1, lambda d: d[0] / 200),
    PID("1F", "runtime_since_start", "s", 2, _u16),
    PID("21", "distance_with_mil", "km", 2, _u16),
    PID("23", "fuel_rail_pressure", "kPa", 2, lambda d: _u16(d) * 10),
    PID("2E", "commanded_evap_purge", "%", 1, lambda d: d[0] * 100 / 255),
    PID("2F", "fuel_level", "%", 1, lambda d: d[0] * 100 / 255),
    PID("30", "warmups_since_clear", "count", 1, lambda d: d[0]),
    PID("31", "distance_since_clear", "km", 2, _u16),
    PID("32", "evap_vapor_pressure", "Pa", 2, lambda d: _s16(d) / 4),
    PID("33", "barometric_pressure", "kPa", 1, lambda d: d[0]),
    PID("42", "control_module_voltage", "V", 2, lambda d: _u16(d) / 1000),
    PID("43", "absolute_load", "%", 2, lambda d: _u16(d) * 100 / 255),
    PID("44", "commanded_afr", "ratio", 2, lambda d: _u16(d) * 2 / 65536),
    PID("46", "ambient_air_temp", "C", 1, lambda d: d[0] - 40),
    PID("51", "fuel_type", "code", 1, lambda d: d[0]),
    PID("52", "ethanol_percent", "%", 1, lambda d: d[0] * 100 / 255),
    PID("53", "evap_vapor_pressure_abs", "kPa", 2, lambda d: _u16(d) / 200),
    PID("5C", "engine_oil_temp", "C", 1, lambda d: d[0] - 40),
    PID("5E", "engine_fuel_rate", "L/h", 2, lambda d: _u16(d) / 20),

    # --- Added 2026-10-13: 46-supported/25-decoded gap from the live 18DAF110
    # read. Every entry below is SAE J1979 (CORROBORATED) -- the standard
    # Mode 01 PID table -- except 70/72 (boost/wastegate control), whose
    # sub-field byte layout is this module's best reconstruction from the
    # commonly published J1979-2 diesel-PID tables and was not independently
    # cross-checked against a live multi-frame capture from this car (72 had
    # no raw reply captured on the bench run that prompted this change).
    PID("13", "o2_sensors_present", "bitmap", 1, lambda d: _decode_o2_present(d)),
    PID("15", "o2_b1s2_voltage_trim", "V/%", 2, lambda d: _decode_o2_voltage_trim(d)),
    PID("1C", "obd_standard", "enum", 1, lambda d: _decode_obd_standard(d)),
    PID("2C", "commanded_egr", "%", 1, lambda d: d[0] * 100 / 255),
    PID("2D", "egr_error", "%", 1, lambda d: (d[0] - 128) * 100 / 128),
    PID("34", "o2_b1s1_wide_range", "lambda/mA", 4, lambda d: _decode_o2_wide_range(d)),
    PID("3C", "catalyst_temp_b1s1", "C", 2, lambda d: _u16(d) / 10 - 40),
    PID("40", "pids_supported_41_60", "bitmap", 4, lambda d: _decode_supported_block("40", d)),
    PID("41", "monitor_status_drive_cycle", "bitmap", 4,
        lambda d: _monitor_table(d[0], d[1], d[2], d[3])),
    PID("47", "throttle_position_b", "%", 1, lambda d: d[0] * 100 / 255),
    PID("49", "accelerator_pedal_d", "%", 1, lambda d: d[0] * 100 / 255),
    PID("4A", "accelerator_pedal_e", "%", 1, lambda d: d[0] * 100 / 255),
    # 4D/4E/7F: SAE J1979 run-time counters. NOT supported by the 2018 Stelvio
    # ECM (18DAF110; 0x40 bitmap lacks 4D/4E, 0x60 bitmap advertises only
    # 68/6B/70/72, measured 2026-10-14/15) -- decoded for cars that do.
    PID("4D", "minutes_run_with_mil", "min", 2, _u16),
    PID("4E", "minutes_since_codes_cleared", "min", 2, _u16),
    PID("54", "evap_vapor_pressure_signed", "kPa", 2, lambda d: _s16(d) / 1000),
    PID("59", "fuel_rail_pressure_abs", "kPa", 2, lambda d: _u16(d) * 10),
    PID("60", "pids_supported_61_80", "bitmap", 4, lambda d: _decode_supported_block("60", d)),
    PID("7F", "engine_run_time", "s", 13, lambda d: _decode_engine_run_time(d)),
    PID("68", "intake_air_temp_sensors", "C", 1, lambda d: _decode_iat_sensors(d)),
    PID("6B", "egr_temperature", "C", 3, lambda d: _decode_egr_temp(d)),
    PID("70", "boost_pressure_control", "kPa", 1, lambda d: _decode_boost_control(d)),
    PID("72", "wastegate_control", "%", 1, lambda d: _decode_wastegate_control(d)),
)

PIDS_BY_HEX: dict[str, PID] = {p.pid: p for p in _PID_LIST}
PIDS_BY_NAME: dict[str, PID] = {p.name: p for p in _PID_LIST}


def resolve_pid(pid: str) -> tuple[str, Optional[PID]]:
    """``(hex, PID or None)`` from a friendly name or a one- or two-digit hex PID."""
    key = pid.strip()
    if key in PIDS_BY_NAME:
        return PIDS_BY_NAME[key].pid, PIDS_BY_NAME[key]
    hx = key.upper().replace("0X", "")
    if len(hx) == 1:
        hx = "0" + hx
    if len(hx) != 2 or any(c not in HEX_DIGITS for c in hx):
        raise BadCommand(f"{pid!r} is neither a friendly PID name nor a 2-digit hex PID")
    return hx, PIDS_BY_HEX.get(hx)


def decode_pid(hex_pid: str, spec: Optional[PID], data: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"pid": hex_pid, "name": spec.name if spec else None, "bytes": data}
    if spec is None:
        out["unit"] = "raw"
        return out
    out["unit"] = spec.unit
    if len(data) < spec.n_bytes:
        out["error"] = f"expected at least {spec.n_bytes} data byte(s), got {len(data)}"
        return out
    try:
        value = spec.decode([int(b, 16) for b in data])
        out["value"] = round(value, 3) if isinstance(value, float) else value
    except (ValueError, IndexError) as e:
        out["error"] = f"decode failed: {e}"
    return out


#: ISO 15031-5 Table O2 sensors present bitmap (PID 0x13), bit -> (bank, sensor).
_O2_PRESENT_BITS: tuple[tuple[int, str], ...] = (
    (0, "bank1_sensor1"), (1, "bank1_sensor2"), (2, "bank1_sensor3"), (3, "bank1_sensor4"),
    (4, "bank2_sensor1"), (5, "bank2_sensor2"), (6, "bank2_sensor3"), (7, "bank2_sensor4"),
)


def _decode_o2_present(d: list[int]) -> dict[str, bool]:
    """PID 0x13: which of the up to 8 O2 sensors are present."""
    byte = d[0]
    return {name: bool(byte & (1 << bit)) for bit, name in _O2_PRESENT_BITS}


def _decode_o2_voltage_trim(d: list[int]) -> dict[str, Any]:
    """PID 0x15 (and the 0x14-0x1B family): sensor voltage + short term fuel
    trim. 0xFF in the trim byte means the sensor is not used for trim.
    """
    voltage = round(d[0] / 200, 3)
    trim_raw = d[1]
    trim = None if trim_raw == 0xFF else round(trim_raw / 1.28 - 100, 3)
    return {"voltage_V": voltage, "stft_pct": trim}


#: SAE J1979 Table "OBD requirements to which the vehicle is designed" (PID 0x1C).
_OBD_STANDARDS: dict[int, str] = {
    0x01: "OBD-II (California ARB)", 0x02: "OBD (Federal EPA)",
    0x03: "OBD and OBD-II", 0x04: "OBD-I", 0x05: "Not OBD compliant",
    0x06: "EOBD", 0x07: "EOBD and OBD-II", 0x08: "EOBD and OBD",
    0x09: "EOBD, OBD and OBD II", 0x0A: "JOBD", 0x0B: "JOBD and OBD II",
    0x0C: "JOBD and EOBD", 0x0D: "JOBD, EOBD, and OBD II",
    0x11: "Engine Manufacturer Diagnostics (EMD)",
    0x12: "Engine Manufacturer Diagnostics Enhanced (EMD+)",
    0x13: "Heavy Duty On-Board Diagnostics (Child/Partial) (HD OBD-C)",
    0x14: "Heavy Duty On-Board Diagnostics (HD OBD)",
    0x15: "World Wide Harmonized OBD (WWH OBD)",
    0x17: "Heavy Duty Euro OBD Stage I without NOx control (HD EOBD-I)",
    0x18: "Heavy Duty Euro OBD Stage I with NOx control (HD EOBD-I N)",
    0x19: "Heavy Duty Euro OBD Stage II without NOx control (HD EOBD-II)",
    0x1A: "Heavy Duty Euro OBD Stage II with NOx control (HD EOBD-II N)",
    0x1C: "Brazil OBD Phase 1 (OBDBr-1)", 0x1D: "Brazil OBD Phase 2 (OBDBr-2)",
    0x1E: "Korean OBD (KOBD)", 0x1F: "India OBD I (IOBD I)",
    0x20: "India OBD II (IOBD II)",
    0x21: "Heavy Duty Euro OBD Stage VI (HD EOBD-IV)",
}


def _decode_obd_standard(d: list[int]) -> dict[str, Any]:
    code = d[0]
    return {"code": code, "standard": _OBD_STANDARDS.get(code, f"reserved/unassigned (0x{code:02X})")}


def _decode_o2_wide_range(d: list[int]) -> dict[str, float]:
    """PIDs 0x34-0x3B: wide-range O2 sensor equivalence ratio (lambda) + current."""
    ab = _u16(d[0:2])
    cd = _u16(d[2:4])
    return {"lambda": round(ab / 32768, 5), "current_mA": round(cd / 256 - 128, 3)}


def _decode_supported_block(base: str, d: list[int]) -> dict[str, Any]:
    """Shared by PIDs 0x40/0x60: same supported-bitmap convention as PID 0x00."""
    hexs = [format(b, "02X") for b in d]
    supported, more = decode_supported_pids(base, hexs)
    return {"supported": supported, "has_next": more}


#: PID 0x68 (Intake Air Temperature Sensor): a presence bitmap byte followed
#: by one raw-minus-40-degC byte per present sensor, in bit order.
_IAT_SENSOR_BITS: tuple[tuple[int, str], ...] = (
    (0, "bank1_sensor1"), (1, "bank1_sensor2"), (4, "bank2_sensor1"), (5, "bank2_sensor2"),
)


def _decode_iat_sensors(d: list[int]) -> dict[str, Any]:
    bitmap = d[0]
    out: dict[str, Any] = {"bitmap": bitmap}
    idx = 1
    for bit, name in _IAT_SENSOR_BITS:
        if bitmap & (1 << bit):
            out[name] = d[idx] - 40 if idx < len(d) else None
            idx += 1
    return out


#: PID 0x6B (Exhaust Gas Recirculation Temperature): presence bitmap byte,
#: then one 2-byte ((raw)/10 - 40) degC field per bank, in bit order -- the
#: same scaling as catalyst temperature (PID 0x3C).
_EGR_TEMP_BANKS: tuple[tuple[int, str], ...] = ((0, "bank1"), (1, "bank2"))


def _decode_egr_temp(d: list[int]) -> dict[str, Any]:
    bitmap = d[0]
    out: dict[str, Any] = {"bitmap": bitmap}
    idx = 1
    for bit, name in _EGR_TEMP_BANKS:
        if bitmap & (1 << bit):
            out[f"egr_temp_{name}_C"] = (round(_u16(d[idx:idx + 2]) / 10 - 40, 3)
                                          if idx + 1 < len(d) else None)
            idx += 2
    return out


def _u32(d: list[int]) -> int:
    return (d[0] << 24) | (d[1] << 16) | (d[2] << 8) | d[3]


def _decode_engine_run_time(d: list[int]) -> dict[str, Any]:
    """PID 0x7F (Engine Run Time), 13 bytes per SAE J1979: A = info byte,
    B-E total, F-I idle, J-M with PTO engaged -- each a 32-bit count of seconds.
    """
    return {"info": d[0], "total_s": _u32(d[1:5]), "idle_s": _u32(d[5:9]),
            "pto_s": _u32(d[9:13])}


def _decode_boost_control(d: list[int]) -> dict[str, Any]:
    """PID 0x70 (Boost Pressure Control): status byte + commanded/actual boost
    pressure, 2 bytes each. Byte layout per commonly published J1979-2
    diesel-PID tables; the 0.01 kPa/count scaling is this module's best
    reconstruction, not corroborated against a live capture from this car.
    """
    out: dict[str, Any] = {"status": d[0]}
    if len(d) >= 3:
        out["commanded_boost_kPa"] = round(_u16(d[1:3]) * 0.01, 3)
    if len(d) >= 5:
        out["actual_boost_kPa"] = round(_u16(d[3:5]) * 0.01, 3)
    return out


def _decode_wastegate_control(d: list[int]) -> dict[str, Any]:
    """PID 0x72 (Wastegate Control): status byte + commanded/actual wastegate
    position, 1 byte each (same 0-255 -> 0-100% scaling as throttle/pedal
    position). No raw reply from this car was captured to corroborate against.
    """
    out: dict[str, Any] = {"status": d[0]}
    if len(d) >= 2:
        out["commanded_pct"] = round(d[1] * 100 / 255, 3)
    if len(d) >= 3:
        out["actual_pct"] = round(d[2] * 100 / 255, 3)
    return out


def decode_supported_pids(base: str, data: list[str]) -> tuple[list[str], bool]:
    """PIDs marked supported in a ``41 <base> A B C D`` bitmap, and whether the next block exists."""
    if len(data) < 4:
        return [], False
    bits = int("".join(data[:4]), 16)
    start = int(base, 16)
    supported = [format(start + 1 + i, "02X") for i in range(32) if bits & (1 << (31 - i))]
    return supported, bool(bits & 1)


# --- DTCs ----------------------------------------------------------------

def dtc_from_two_bytes(a: str, b: str) -> Optional[str]:
    """ISO 15031-6 two-byte code -> ``P0456``; None for the ``00 00`` filler."""
    if a == "00" and b == "00":
        return None
    try:
        high = int(a[0], 16)
    except (ValueError, IndexError):
        return None
    return f"{'PCBU'[high >> 2]}{format(high & 0x3, 'X')}{a[1]}{b}"


def decode_obd_dtcs(payload: list[str]) -> list[str]:
    """DTCs from a Mode 03/07/0A payload that starts with the response byte.

    On CAN the response byte is followed by a count byte; on K-line it is
    not. Parity of the remaining byte count decides.
    """
    if not payload:
        return []
    rest = payload[1:]
    if len(rest) % 2:
        rest = rest[1:]
    out: list[str] = []
    for i in range(0, len(rest) - 1, 2):
        code = dtc_from_two_bytes(rest[i], rest[i + 1])
        if code:
            out.append(code)
    return out


def dtc_from_three_bytes(high: str, middle: str, low: str) -> str:
    """UDS three-byte DTC -> the MES vocabulary ``P0456-00`` (code dash failure type)."""
    base = dtc_from_two_bytes(high, middle) or "P0000"
    return f"{base}-{low.upper()}"


#: ISO 14229 D.2 DTC status bits.
DTC_STATUS_BITS: tuple[tuple[int, str], ...] = (
    (0, "testFailed"), (1, "testFailedThisOperationCycle"), (2, "pendingDTC"),
    (3, "confirmedDTC"), (4, "testNotCompletedSinceLastClear"),
    (5, "testFailedSinceLastClear"), (6, "testNotCompletedThisOperationCycle"),
    (7, "warningIndicatorRequested"),
)


def decode_dtc_status(byte: int) -> dict[str, bool]:
    return {name: bool(byte & (1 << bit)) for bit, name in DTC_STATUS_BITS}


def decode_uds_dtc_block(data: list[str]) -> list[dict[str, Any]]:
    """``59 02 <mask> (<H> <M> <L> <status>)*`` -> one record per code, padding skipped."""
    out: list[dict[str, Any]] = []
    if len(data) < 3 or data[0] != "59":
        return out
    body = data[3:]
    for i in range(0, len(body) - 3, 4):
        h, m, l, s = body[i], body[i + 1], body[i + 2], body[i + 3]
        if h == "00" and m == "00" and l == "00":
            continue
        status = int(s, 16)
        out.append({"code": dtc_from_three_bytes(h, m, l), "raw": f"{h}{m}{l}",
                    "status": status, "flags": decode_dtc_status(status)})
    return out


# --- readiness --------------------------------------------------------------

_CONTINUOUS = ((0, 4, "Misfire"), (1, 5, "Fuel system"), (2, 6, "Comprehensive components"))

_SPARK = ((0, "Catalyst"), (1, "Heated catalyst"), (2, "Evaporative system"),
          (3, "Secondary air system"), (4, "A/C refrigerant"), (5, "Oxygen sensor"),
          (6, "Oxygen sensor heater"), (7, "EGR system"))

_COMPRESSION = ((0, "NMHC catalyst"), (1, "NOx/SCR monitor"), (2, "reserved"),
                (3, "Boost pressure"), (4, "reserved"), (5, "Exhaust gas sensor"),
                (6, "PM filter"), (7, "EGR/VVT system"))


def _monitor_table(a: int, b: int, c: int, d: int) -> dict[str, Any]:
    """Shared by PID 01 (since-clear readiness) and PID 41 (this-drive-cycle
    monitor status): same 4-byte layout, picking spark vs. compression-ignition
    monitor names from byte B bit 3.
    """
    compression = bool(b & 0x08)
    table = _COMPRESSION if compression else _SPARK
    monitors: list[dict[str, Any]] = []
    for sup_bit, inc_bit, name in _CONTINUOUS:
        if b & (1 << sup_bit):
            monitors.append({"monitor": name, "supported": True,
                             "complete": not (b & (1 << inc_bit))})
    for bit, name in table:
        if name != "reserved" and c & (1 << bit):
            monitors.append({"monitor": name, "supported": True,
                             "complete": not (d & (1 << bit))})
    return {
        "mil_on": bool(a & 0x80),
        "stored_dtc_count": a & 0x7F,
        "ignition": "compression" if compression else "spark",
        "monitors": monitors,
        "all_complete": all(m["complete"] for m in monitors) if monitors else None,
    }


def decode_readiness(pairs: list[str], response_byte: str = "41") -> Optional[dict[str, Any]]:
    """Decode a Mode 01 PID 01 / 41 payload; picks the layout from byte B bit 3."""
    idx = None
    for i in range(len(pairs) - 1):
        if pairs[i] == response_byte and pairs[i + 1] in ("01", "41"):
            idx = i + 2
            break
    if idx is None:
        return None
    try:
        data = [int(x, 16) for x in pairs[idx:idx + 4]]
    except ValueError:
        return None
    if len(data) < 4:
        return None
    a, b, c, d = data
    return _monitor_table(a, b, c, d)


def evap_verdict(readiness: dict[str, Any]) -> Optional[str]:
    monitors = readiness.get("monitors") or []
    evap = next((m for m in monitors if m["monitor"] == "Evaporative system"), None)
    if evap is None:
        return ("This ECU does not report an evaporative system monitor."
                if monitors else None)
    if evap["complete"]:
        return ("EVAP monitor has COMPLETED since the last clear; a clean scan is now "
                "meaningful for EVAP.")
    return ("EVAP monitor has NOT run since the last clear. Absence of an EVAP code right "
            "now carries no information. Complete the drive cycle first.")


__all__ = ["PID", "PIDS_BY_HEX", "PIDS_BY_NAME", "resolve_pid", "decode_pid",
           "decode_supported_pids", "dtc_from_two_bytes", "decode_obd_dtcs",
           "dtc_from_three_bytes", "DTC_STATUS_BITS", "decode_dtc_status",
           "decode_uds_dtc_block", "decode_readiness", "evap_verdict", "_monitor_table"]
