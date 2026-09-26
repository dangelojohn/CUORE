"""The only module in CUORE that imports :mod:`mes.known_good`.

Mirrors the pattern ``mes_bridge.py`` and ``service_bridge.py`` already use:
every route (and, here, the built-in gauge layouts) reaches the known-good
reference bands and this car's own MES-observed ranges only through this
file, so ``cuore/live/layouts.py`` (gauge min/max/warn/alarm) and
``cuore/api/known_good.py`` (the JSON endpoint) cannot drift apart, and
neither re-implements the confidence rules or banding data that live in
``mes.known_good`` and are unit-tested there.

Nothing here invents a number: :func:`sourced_band` returns ``None`` for a
channel this library has nothing for, *or* whose only row is UNKNOWN --
an unsourced band must never reach a gauge looking like a real one.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from .errors import BadRequest

from mes import known_good as known_good_mod  # noqa: E402


def all_known_good() -> dict[str, dict[str, Any]]:
    """Every channel this library has a row for (including documented
    UNKNOWN rows) -- backs the ``channels`` key of the JSON endpoint."""
    return known_good_mod.all_known_good()


def known_good_for(channel_id: str) -> Optional[dict[str, Any]]:
    """One channel's raw row, or ``None`` if this library has nothing for
    it at all (distinct from a documented UNKNOWN row, which is returned)."""
    return known_good_mod.known_good(channel_id)


def sourced_band(channel_id: str) -> Optional[dict[str, Any]]:
    """The widget-ready band for one channel, or ``None``.

    ``None`` when this library has no row for ``channel_id``, or when its
    only row is ``UNKNOWN`` -- callers (gauge layouts) must never render an
    UNKNOWN row's absent numbers as if they were a real min/max. Otherwise:
    ``{"min", "max", "warn", "alarm", "confidence", "source", "note",
    "generic"}``, where ``min``/``max`` come from the row's ``normal`` band
    (``None`` if the row sets no normal band even at non-UNKNOWN
    confidence) and ``warn``/``alarm`` are passed through as ``[lo, hi]``
    pairs or ``None``, matching ``cuore.live.layouts``' own band shape.
    """
    row = known_good_mod.known_good(channel_id)
    if row is None or row.get("confidence") == known_good_mod.UNKNOWN:
        return None
    # Two traps, fixed 2026-09-26:
    # 1. A "normal" range is an operating range, not a gauge scale. Using it
    #    as min/max made the RPM dial 700-900 rpm. Scale stays the caller's.
    # 2. Gauge widgets treat a value INSIDE a warn/alarm band as warn/alarm.
    #    Rows with direction "both" describe an acceptable envelope (outside
    #    = bad), and are often condition-specific (hot idle only), so passing
    #    them through made idle RPM read ALARM and 3,000 rpm read OK. Only
    #    one-sided rows ("above" / "below") map onto widget bands.
    normal = row.get("normal")
    one_sided = row.get("direction") in ("above", "below")
    unit = row.get("unit") or ""
    bits = []
    if normal:
        bits.append(f"Normal {normal[0]:g}-{normal[1]:g} {unit}".strip())
    if row.get("conditions"):
        bits.append(f"({row['conditions']})")
    bits.append(f"[{row.get('confidence')}{', generic' if row.get('generic') else ''}]")
    if row.get("notes"):
        bits.append(row["notes"])
    return {
        "min": None,
        "max": None,
        "warn": row.get("warn") if one_sided else None,
        "alarm": row.get("alarm") if one_sided else None,
        "normal": normal,
        "confidence": row.get("confidence"),
        "source": row.get("source"),
        "note": " ".join(bits) or None,
        "generic": bool(row.get("generic", False)),
    }


def observed_ranges(vin: str) -> dict[str, Any]:
    """This VIN's own MES-logged percentiles per channel -- never a spec,
    always labelled "observed on this car" by the caller."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return known_good_mod.observed_ranges(vin)


def known_good_payload(vin: str = "") -> dict[str, Any]:
    """The full ``/api/live/known-good`` response.

    Always includes every channel's reference band. Adds this VIN's
    observed_ranges alongside it when a VIN is given -- kept as a separate
    top-level key (``observed``), never merged into ``channels``, so a
    client can never mistake an observed percentile for a sourced spec.
    """
    out: dict[str, Any] = {"channels": all_known_good()}
    if vin.strip():
        out["vin"] = vin
        out["observed"] = known_good_mod.observed_ranges(vin)
    return out


__all__ = ["all_known_good", "known_good_for", "sourced_band", "observed_ranges",
          "known_good_payload"]
