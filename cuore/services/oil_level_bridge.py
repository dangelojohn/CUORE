"""Data for the vehicle dashboard's "Oil level" card.

Readings are ordinary owner events (category ``fluids``, kind ``oil_level``,
stored by :mod:`cuore.live.owner_events`, so "Tell CUORE" on the phone and the
card's own form write the same rows). The maths lives in :mod:`mes.oil_level`.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live import owner_events as store
from . import owner_events_bridge

from mes import oil_level as model  # noqa: E402

HISTORY = 5
#: Bar axis runs 0 .. AXIS_MAX_PCT % of capacity so an over-full reading is visible.
AXIS_MAX_PCT = 110.0


def readings(vin: str) -> list[dict[str, Any]]:
    """This VIN's oil-level readings, oldest first, each with its computed model."""
    rows = []
    for e in store.load(vin):
        if e.get("category") != "fluids" or e.get("kind") != "oil_level":
            continue
        m = model.compute(e.get("fields") or {})
        if m is None:
            continue
        rows.append({"id": e.get("id"), "at": e.get("at"), "date": str(e.get("at") or "")[:10],
                     "odometer_km": e.get("odometer_km"), "method": m["method"],
                     "note": e.get("note") or "", "by": (e.get("by") or {}).get("role"),
                     "fields": e.get("fields") or {}, **m})
    rows.sort(key=lambda r: (str(r["at"]), str(r["id"])))
    return rows


def add(vin: str, *, date_: Optional[str] = None, odometer_km: Optional[float] = None,
        method: str = "dipstick", dipstick_position_pct: Any = None, litres: Any = None,
        note: str = "", by_role: str = "owner") -> dict[str, Any]:
    fields = {"method": method, "dipstick_position_pct": dipstick_position_pct,
              "litres": litres}
    return owner_events_bridge.add(
        vin, "fluids", "oil_level", at=date_ or date.today().isoformat(), by_role=by_role,
        fields={k: v for k, v in fields.items() if v not in (None, "")},
        note=note, odometer_km=odometer_km)


def card(vin: str) -> dict[str, Any]:
    rows = readings(vin)
    latest = rows[-1] if rows else None
    if latest:
        latest = {**latest,
                  "fill_pct": round(max(0.0, min(AXIS_MAX_PCT, latest["pct_of_capacity"]))
                                    / AXIS_MAX_PCT * 100, 1)}
    cap, rng = model.CAPACITY_L, model.dipstick_range_l()
    return {
        "latest": latest,
        "history": list(reversed(rows[-HISTORY:])),
        "count": len(rows),
        "capacity_l": cap,
        "capacity_qt": round(cap / model.L_PER_US_QT, 2),
        "capacity_source": model.CAPACITY_SOURCE,
        "dipstick_range_l": rng,
        "range_assumed": model.range_is_assumed(),
        "range_note": model.RANGE_NOTE,
        "min_tick_pct": round((cap - rng) / cap * 100 / AXIS_MAX_PCT * 100, 1),
        "max_tick_pct": round(100 / AXIS_MAX_PCT * 100, 1),
        "methods": [{"key": k, "label": model.METHOD_LABEL[k]} for k in model.METHODS],
        "today": date.today().isoformat(),
    }
