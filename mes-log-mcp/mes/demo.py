"""Which VINs are invented demonstration cars (never evidence, never learning).

The demo cars are described by one JSON file each under ``cuore/data/demo_cars/<VIN>.json``.
This module only answers "is this VIN one of them?" so every store that learns across cars
(cases, case memory, field quality, tool learn) can leave them out. ``mes`` never imports
``cuore``; the folder is found relative to this file. Rule 11 (docs/project/RULES.md): test and
demo content is never evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parents[2] / "cuore" / "data" / "demo_cars"


def demo_vins() -> frozenset[str]:
    try:
        return frozenset(p.stem.upper() for p in DIR.glob("*.json") if len(p.stem) == 17)
    except OSError:
        return frozenset()


def is_demo_vin(vin: Any) -> bool:
    return str(vin or "").strip().upper() in demo_vins()


def is_demo_record(rec: Any) -> bool:
    """A stored record that is tagged ``demo`` or belongs to a demo VIN."""
    return isinstance(rec, dict) and (rec.get("demo") is True or is_demo_vin(rec.get("vin")))
