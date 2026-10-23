"""Read-only loader for the coloured adapter-cable catalogue.

``cuore/data/adapter_cables.json`` is **external reference, not a CUORE
reading**: it was compiled from vendor listings, official tool pages and
owner forums (see ``docs/research/ADAPTER_CABLES.md``). Nothing in it was
measured on the reference car and it is never proof of anything. Each row
keeps its own ``confidence`` and ``sources``.

Only two cables are ever driven live by CUORE -- ``blue_a5`` and
``grey_a6``, the values in :data:`cuore.live.buses.CABLES`. Each catalogue
row carries ``live_route``: that value for the A5 / A6 rows, ``None`` for
every other. This module adds no routes and never imports the live layer
beyond the cable names, so the catalogue cannot widen what CUORE transmits.

Safety, repeated here because this is the file a later change would touch:

* Never open a bus at a rate other than its own. On 2026-10-14 three ~2 s
  receive-only windows on CAN-CH at 250k/125k lit the AIRBAG lamp with a
  chime on the reference car. A catalogue row with a blank or "not stated"
  bitrate is not a licence to try one.
* Never short pins 1 and 9 on Giulia or Stelvio (see ``PIN_1_9_WARNING``).

Pure file read: nothing here touches the car, the adapter or a serial port.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..live.buses import CABLES, PIN_1_9_WARNING

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "adapter_cables.json"

LABEL = "external reference, not a CUORE reading"

WRONG_BITRATE_WARNING = (
    "Never open a bus at a rate other than its own. On 2026-10-14 three ~2 s "
    "receive-only windows on CAN-CH at 250k/125k lit the AIRBAG lamp with a chime "
    "on the reference car. CAN-CH is 500k only; CAN-IHS is 125k only."
)


def load() -> list[dict[str, Any]]:
    """Every catalogue row, as stored. Raises on a missing or damaged file
    rather than guessing."""
    with _DATA_FILE.open(encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise ValueError("adapter_cables.json must be a list of rows")
    return rows


def by_brand(brand: str) -> list[dict[str, Any]]:
    """Rows whose ``brands`` text mentions ``brand`` (case-insensitive substring).
    An empty ``brand`` returns every row."""
    needle = (brand or "").strip().lower()
    rows = load()
    if not needle:
        return rows
    return [r for r in rows if needle in str(r.get("brands") or "").lower()]


def for_cable(cable: str) -> Optional[dict[str, Any]]:
    """The row for a cable value as used in ``cuore.live.buses`` (``blue_a5``,
    ``grey_a6``), or ``None``. ``"none"`` and any unknown value return ``None``."""
    if cable not in CABLES or cable == "none":
        return None
    for r in load():
        if r.get("live_route") == cable:
            return r
    return None


def payload(brand: str = "") -> dict[str, Any]:
    """The JSON shape served by ``GET /api/cables``."""
    rows = by_brand(brand)
    return {
        "label": LABEL,
        "brand_filter": brand or None,
        "live_routes": [c for c in CABLES if c != "none"],
        "warnings": [WRONG_BITRATE_WARNING, PIN_1_9_WARNING],
        "count": len(rows),
        "cables": rows,
    }
