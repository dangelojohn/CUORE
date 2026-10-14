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

2026-10-14 marque-port fix: :func:`known_good_for` and :func:`sourced_band`
take an optional ``vin``. Omitted (``""``, the default), they are exactly
as before -- every row, regardless of marque -- so every existing caller
that does not pass one (``cuore.live.layouts``, ``cuore/web/systems_routes.py``,
etc.) is unaffected. Given a ``vin``, a row whose ``mes.known_good``
``applies_to`` does not cover that VIN's platform (:func:`mes.known_good.
applies_to_vin`) is treated exactly like a missing row -- ``None`` -- so a
Stelvio-forum-sourced citation never reaches a Maserati/Ferrari VIN's
pages. :func:`bands_for_vin` and the vin-aware path through
:func:`known_good_payload` are the bulk equivalent, used by
``cuore/api/known_good.py``.
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


def bands_for_vin(vin: str) -> dict[str, dict[str, Any]]:
    """Every channel's row that applies to this VIN's marque/platform --
    see :func:`mes.known_good.bands_for_vin`. A row tagged for a platform
    this VIN cannot be confirmed to share (e.g. a Stelvio-forum citation
    on a Maserati VIN this project cannot place on a specific model) is
    left out entirely, same as a channel with no row at all."""
    return known_good_mod.bands_for_vin(vin)


def known_good_for(channel_id: str, vin: str = "") -> Optional[dict[str, Any]]:
    """One channel's raw row, or ``None`` if this library has nothing for
    it at all (distinct from a documented UNKNOWN row, which is returned).

    Pass ``vin`` to also gate on marque/platform: a row whose
    ``applies_to`` does not cover ``vin`` (:func:`mes.known_good.
    applies_to_vin`) comes back ``None``, same as a missing row. Omitted,
    this is exactly today's unfiltered lookup.
    """
    row = known_good_mod.known_good(channel_id)
    if row is None:
        return None
    if vin and not known_good_mod.applies_to_vin(row, vin):
        return None
    return row


def sourced_band(channel_id: str, vin: str = "") -> Optional[dict[str, Any]]:
    """The widget-ready band for one channel, or ``None``.

    ``None`` when this library has no row for ``channel_id``, when its
    only row is ``UNKNOWN``, or -- given a ``vin`` -- when the row does
    not apply to that VIN's marque/platform (see :func:`known_good_for`).
    Callers (gauge layouts) must never render an UNKNOWN row's absent
    numbers, or another platform's row, as if they were this car's real
    min/max. Otherwise: ``{"min", "max", "warn", "alarm", "confidence",
    "source", "note", "generic"}``, where ``min``/``max`` come from the
    row's ``normal`` band (``None`` if the row sets no normal band even at
    non-UNKNOWN confidence) and ``warn``/``alarm`` are passed through as
    ``[lo, hi]`` pairs or ``None``, matching ``cuore.live.layouts``' own
    band shape.
    """
    row = known_good_for(channel_id, vin=vin)
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

    With no ``vin``, ``channels`` is every row, unfiltered (today's
    behaviour). Given a ``vin``, ``channels`` is gated to
    :func:`bands_for_vin` instead -- a row tagged for a platform this VIN
    cannot be confirmed to share is left out entirely, same as a channel
    with no row at all, so e.g. a Stelvio-forum citation never reaches a
    Maserati/Ferrari VIN's response. ``observed_ranges`` is added
    alongside it -- kept as a separate top-level key (``observed``), never
    merged into ``channels``, so a client can never mistake an observed
    percentile for a sourced spec.
    """
    out: dict[str, Any] = {"channels": all_known_good()}
    if vin.strip():
        out["vin"] = vin
        out["channels"] = bands_for_vin(vin)
        out["observed"] = known_good_mod.observed_ranges(vin)
    return out


__all__ = ["all_known_good", "bands_for_vin", "known_good_for", "sourced_band",
          "observed_ranges", "known_good_payload"]
