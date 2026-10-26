"""Read-only loader for a vehicle's facts quick-view.

The facts live in ``docs/vehicles/<VIN>/data/vehicle_facts.json`` -- marque and
vehicle specifics stay in data, never in templates or code. Every row carries
a ``source`` and ``date``. A vehicle without the file gets ``None`` and the
page says so. Pure file read: nothing here touches the car or the adapter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
_VIN_RE = re.compile(r"^[A-Z0-9]{11,17}$")


def facts_path(vin: str) -> Optional[Path]:
    if not _VIN_RE.match(vin or ""):
        return None
    return REPO_ROOT / "docs" / "vehicles" / vin / "data" / "vehicle_facts.json"


def load(vin: str) -> Optional[dict[str, Any]]:
    p = facts_path(vin)
    if p is None or not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _by_key(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["key"]: r for s in data.get("sections", []) for r in s.get("rows", []) if r.get("key")}


def summary(vin: str) -> Optional[dict[str, Any]]:
    """The few rows the landing page card shows, in the file's order."""
    data = load(vin)
    if not data:
        return None
    rows = _by_key(data)
    return {"rows": [rows[k] for k in data.get("summary_keys", []) if k in rows]}


def nav_label(vin: Optional[str] = None) -> str:
    """Header link text: the file's ``nav_label`` (e.g. "Stelvio facts"), else "Facts" (also when no vehicle is chosen)."""
    # Only the vehicle's own facts file may name it. With no vehicle chosen yet
    # (/start) or none on file, stay marque-neutral rather than borrowing
    # another car's label (a Maserati page must never say "Stelvio facts").
    data = load(vin) if vin else None
    label = (data or {}).get("nav_label")
    return label if isinstance(label, str) and label.strip() else "Facts"


def first_vin_with_facts() -> Optional[str]:
    base = REPO_ROOT / "docs" / "vehicles"
    if not base.is_dir():
        return None
    for d in sorted(base.iterdir()):
        if (d / "data" / "vehicle_facts.json").is_file():
            return d.name
    return None
