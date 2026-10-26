"""Engine-oil level model for the 2018 Stelvio 2.0T: dipstick / measured-fill /
drain-volume readings turned into litres in the sump and "% full".

Pure maths, no I/O -- the owner-entered readings are stored by
``cuore.live.owner_events`` (category ``fluids``, kind ``oil_level``) and the
dashboard card is built by ``cuore.services.oil_level_bridge``.

Quantities and where they come from:

* ``CAPACITY_L`` -- 5.2 L (5.5 US qt) with filter, read from
  ``mes.service_specs.OIL_SPEC["capacity_with_filter_qt"]`` (AMSOIL engine-code
  lookup, SINGLE-SOURCE; see STELVIO_20T_SERVICE_SPECS.md). Oil 0W-30, MS-13340.
* ``DIPSTICK_RANGE_L`` -- litres between the dipstick MIN and MAX marks.
  **ASSUMED 1.0 L -- measure once: fill from MIN to MAX and record the
  volume.** No source in this repo gives it for this engine. Override with the
  ``CUORE_OIL_DIPSTICK_RANGE_L`` environment variable once measured.

Model (the dipstick MAX mark is taken to be a full fill, i.e. capacity)::

    sump_l           = capacity - (1 - position_pct / 100) * dipstick_range
    pct_of_capacity  = sump_l / capacity * 100
    pct_between      = position_pct          (0 = MIN mark, 100 = MAX mark)

For ``measured_fill`` (litres poured into a drained engine) and
``drain_volume`` (litres that came out) the litres ARE the sump quantity, and
the dipstick position is derived back from them. These are owner-reported
numbers (confidence "reported"), never car measurements.
"""

from __future__ import annotations

import math
import os
from typing import Any, Optional

from . import service_specs

METHODS = ("dipstick", "measured_fill", "drain_volume")
METHOD_LABEL = {"dipstick": "dipstick", "measured_fill": "measured fill",
                "drain_volume": "drain volume (before-change)"}
L_PER_US_QT = 0.946353

CAPACITY_SOURCE = service_specs.OIL_SPEC["capacity_with_filter_qt"]["source"]
CAPACITY_L: float = float(service_specs.OIL_SPEC["capacity_with_filter_qt"]["value_l"])

_DEFAULT_RANGE_L = 1.0
RANGE_NOTE = ("ASSUMED -- measure once: fill from MIN to MAX and record the volume")


def dipstick_range_l() -> float:
    """MIN-to-MAX litres: ``CUORE_OIL_DIPSTICK_RANGE_L`` if set and sane, else 1.0."""
    try:
        v = float(os.environ.get("CUORE_OIL_DIPSTICK_RANGE_L", ""))
        if v > 0:
            return v
    except ValueError:
        pass
    return _DEFAULT_RANGE_L


def range_is_assumed() -> bool:
    return dipstick_range_l() == _DEFAULT_RANGE_L and not os.environ.get(
        "CUORE_OIL_DIPSTICK_RANGE_L")


def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool) or str(v).strip() == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None  # "nan"/"inf" are not readings


def validate(fields: dict[str, Any]) -> list[str]:
    """Problems with one reading's ``fields`` ([] when fine)."""
    errs: list[str] = []
    method = str(fields.get("method") or "").strip()
    if method not in METHODS:
        errs.append("method must be one of: " + ", ".join(METHODS))
        return errs
    pos, lit = _num(fields.get("dipstick_position_pct")), _num(fields.get("litres"))
    if fields.get("dipstick_position_pct") not in (None, "") and pos is None:
        errs.append("dipstick_position_pct must be a number")
    if fields.get("litres") not in (None, "") and lit is None:
        errs.append("litres must be a number")
    if method == "dipstick" and pos is None:
        errs.append("a dipstick reading needs dipstick_position_pct (0 = MIN mark, 100 = MAX mark)")
    if method != "dipstick" and (lit is None or lit < 0):
        errs.append(f"a {method.replace('_', ' ')} reading needs litres (0 or more)")
    return errs


def compute(fields: dict[str, Any], *, capacity_l: Optional[float] = None,
            range_l: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Sump quantity and percentages for one reading; ``None`` if unusable."""
    cap = CAPACITY_L if capacity_l is None else capacity_l
    rng = dipstick_range_l() if range_l is None else range_l
    if validate(fields):
        return None
    method = str(fields["method"]).strip()
    if method == "dipstick":
        pos = _num(fields.get("dipstick_position_pct"))
        sump = cap - (1 - pos / 100.0) * rng
    else:
        sump = _num(fields.get("litres"))
        pos = (1 - (cap - sump) / rng) * 100.0
    pct_cap = sump / cap * 100.0
    return {
        "method": method,
        "sump_l": round(sump, 2),
        "sump_qt": round(sump / L_PER_US_QT, 2),
        "pct_of_capacity": round(pct_cap, 1),
        "pct_between": round(pos, 1),
        "over_full": pos > 100.0,
        "below_min": pos < 0.0,
        "capacity_l": cap,
        "capacity_qt": round(cap / L_PER_US_QT, 2),
        "dipstick_range_l": rng,
    }


__all__ = ["METHODS", "METHOD_LABEL", "CAPACITY_L", "CAPACITY_SOURCE", "RANGE_NOTE",
           "L_PER_US_QT", "dipstick_range_l", "range_is_assumed", "validate", "compute"]
