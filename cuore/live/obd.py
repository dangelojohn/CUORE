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
           "decode_uds_dtc_block", "decode_readiness", "evap_verdict"]
