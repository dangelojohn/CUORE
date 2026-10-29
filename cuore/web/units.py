"""Display units (km/mi). Stored values stay metric; only rendering changes.
Setting lives in <state_dir>/ui_settings.json as {"units": "metric"|"imperial"}."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..live.config import state_dir

KM_PER_MI = 1.609344


def settings_path() -> Path:
    return state_dir() / "ui_settings.json"


def load_settings() -> dict[str, Any]:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get_units() -> str:
    return "imperial" if load_settings().get("units") == "imperial" else "metric"


def set_units(units: str) -> str:
    units = "imperial" if units == "imperial" else "metric"
    data = load_settings()
    data["units"] = units
    settings_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    return units


def dist(value_km: Any) -> str:
    """142289 -> '142,289 km' (or '88,415 mi' when imperial)."""
    try:
        v = float(value_km)
    except (TypeError, ValueError):
        return ""
    if get_units() == "imperial":
        return f"{round(v / KM_PER_MI):,} mi"
    return f"{round(v):,} km"


def speed(kmh: Any) -> str:
    try:
        v = float(kmh)
    except (TypeError, ValueError):
        return ""
    if get_units() == "imperial":
        return f"{round(v / KM_PER_MI):,} mph"
    return f"{round(v):,} km/h"


def dist_unit() -> str:
    return "mi" if get_units() == "imperial" else "km"
