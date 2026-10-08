"""Bridge to ``mes.experience`` -- the only module in ``cuore`` that imports
it.

``mes.experience`` (built in parallel by another agent, may not exist yet)
exposes ``for_code(code)``, ``for_family(family)``, ``for_job(job)`` and
``all()``, each returning a list of link dicts: ``{id, keys, title, url,
source, kind, covers, vehicle_fit, date, reputation, verified_at,
verified_how}``.

:func:`links_for` is the one entry point every page/route uses: it calls
whichever of those three lookups apply, merges the results, de-duplicates
(by ``id``, falling back to ``url``), and orders them the way every "Others'
experience" card wants: highest reputation first, then how-to videos ahead
of everything else at equal reputation, then newest within a tie.

The import is lazy (inside the function, not at module load) and every
failure -- ``mes.experience`` not existing yet, or raising anything at
all -- degrades to an empty result rather than ever raising out of this
module. That is what lets every page using this bridge render "No
experience links yet" instead of a 500 while the data agent's module is
still landing.

An optional ``vin`` on :func:`links_for` resolves that VIN's model via
``mes.platform.model_for_vin`` and, when a model is found, passes
``include_siblings=True`` into ``mes.experience`` so pages can also surface
any sourced sibling-platform (Grecale/Levante) entries -- each one is given
a ``label`` of "from <Model> experience: verify fit" rather than being
presented as this car's own experience. ``mes.experience`` currently has no
entry tagged for a sibling model (see its module docstring), so this is
plumbing with nothing to show yet, not a behavior change.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any, Optional

#: reputation values ranked low-to-high priority (lower sorts first)
_REPUTATION_RANK = {"high": 0, "medium": 1}

#: kind values ranked low-to-high priority (lower sorts first)
_KIND_RANK = {"how_to_video": 0}


def _experience_module() -> Any:
    try:
        from mes import experience  # noqa: PLC0415 -- deliberately lazy, see module docstring
        return experience
    except ImportError:
        return None


def _model_for_vin(vin: Optional[str]) -> Optional[str]:
    """Best-effort model name for ``vin``, or ``None`` on any failure/VIN
    not recognised -- never raises, same degrade-to-empty rule as the rest
    of this module."""
    if not vin:
        return None
    try:
        from mes import platform as platform_mod  # noqa: PLC0415
        model = platform_mod.model_for_vin(vin)
    except Exception:  # noqa: BLE001
        return None
    return None if model == "UNKNOWN" else model


def _date_ordinal(value: Any) -> int:
    """Sortable "newest first" key. Unparseable/missing dates sort last."""
    s = str(value or "")[:10]
    try:
        return _date.fromisoformat(s).toordinal()
    except ValueError:
        return 0


def _sort_key(link: dict[str, Any]) -> tuple[int, int, int]:
    reputation_rank = _REPUTATION_RANK.get((link.get("reputation") or "").lower(), 2)
    kind_rank = _KIND_RANK.get(link.get("kind") or "", 1)
    return (reputation_rank, kind_rank, -_date_ordinal(link.get("date")))


def links_for(*, code: Optional[str] = None, family: Optional[str] = None,
              job: Optional[str] = None, vin: Optional[str] = None) -> dict[str, Any]:
    """Merged, de-duplicated, ordered experience links for whichever of
    ``code``/``family``/``job`` are given. ``{"links": [...], "count": n}``,
    always -- an empty list (never an exception) when ``mes.experience``
    is unavailable, nothing was given, or the lookup itself failed.

    ``vin``, if given, resolves a model via ``mes.platform.model_for_vin``
    and threads ``include_siblings=True`` through so any sourced
    sibling-platform entries (flagged ``sibling_of``/``verify_fit`` by
    ``mes.experience``) are included too, each labeled "from <Model>
    experience: verify fit".
    """
    experience = _experience_module()
    if experience is None:
        return {"links": [], "count": 0}

    include_siblings = bool(_model_for_vin(vin))

    collected: list[dict[str, Any]] = []
    try:
        if code:
            collected += list(experience.for_code(code, include_siblings=include_siblings) or [])
        if family:
            collected += list(experience.for_family(family, include_siblings=include_siblings) or [])
        if job:
            collected += list(experience.for_job(job, include_siblings=include_siblings) or [])
    except Exception:  # noqa: BLE001 -- a data-module hiccup must never 500 a page
        return {"links": [], "count": 0}

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for link in collected:
        key = str(link.get("id") or link.get("url") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(link)

    deduped.sort(key=_sort_key)
    for link in deduped:
        sibling_of = link.get("sibling_of")
        if sibling_of:
            link["label"] = f"from {str(sibling_of).title()} experience: verify fit"
    return {"links": deduped, "count": len(deduped)}


__all__ = ["links_for"]
