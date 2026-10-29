"""Fixture values for a SIMULATED live session (no car, no adapter).

Python port of the drive-cycle profiles in web/static/liveboard.js (the same
numbers the gauges demo shows). Pure functions; nothing here touches a port.
"""
from __future__ import annotations

import math
import zlib
from typing import Any


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _throttle(t: float) -> float:
    return _clamp(0.12 + 0.5 * (0.5 + 0.5 * math.sin(t / 14)) + 0.18 * math.sin(t / 3.1)
                  + 0.05 * math.sin(t * 2.7), 0, 1)


_PROFILES = {
    "engine_rpm": lambda t, d: 780 + d * 4600 + 60 * math.sin(t * 3),
    "vehicle_speed": lambda t, d: _clamp(8 + d * 150 + 10 * math.sin(t / 9), 0, 220),
    "throttle_position": lambda t, d: d * 100,
    "engine_load": lambda t, d: _clamp(d * 90 + 5, 0, 100),
    "intake_map": lambda t, d: 30 + d * 130,
    "barometric_pressure": lambda t, d: 99.5,
    "boost": lambda t, d: max(0.0, d - 0.55) * 20,
    "intake_air_temp": lambda t, d: 24 + 2 * math.sin(t / 60),
    "ambient_air_temp": lambda t, d: 21 + math.sin(t / 120),
    "engine_coolant_temp": lambda t, d: min(92, 20 + t * 0.35) + math.sin(t / 20),
    "engine_oil_temp": lambda t, d: min(105, 22 + t * 0.3) + math.sin(t / 17),
    "battery_voltage": lambda t, d: 14.1 + 0.15 * math.sin(t / 5) - d * 0.05,
    "fuel_level": lambda t, d: _clamp(78 - t / 240, 0, 100),
}


def demo_value(channel_id: str, t: float) -> float:
    d = _throttle(t)
    fn = _PROFILES.get(channel_id)
    if fn:
        return round(fn(t, d), 2)
    seed = (zlib.crc32(channel_id.encode()) % 1000) / 1000 * 6.28
    if "temp" in channel_id:
        return round(40 + 10 * math.sin(t / 25 + seed), 2)
    return round(30 + 5 * math.sin(t / 6 + seed), 2)
