"""Bridge to ``mes.experience`` -- the only module in ``cuore`` that imports
it.

``mes.experience`` (built in parallel by another agent, may not exist yet)
exposes ``for_code(code)``, ``for_family(family)``, ``for_job(job)`` and
``all()``, each returning a list of link dicts: ``{id, keys, title, url,
source, kind, covers, vehicle_fit, date, reputation, verified_at,
verified_how}``.

:func:`links_for` is the one entry point every page/route uses: it calls
whichever of those three lookups apply, merges the results, de-duplicates
(by ``id``, falling back to ``url``), scores each surviving link and sorts
by that score, descending.

Score = relevance + importance:

* relevance -- which lookup(s) found the link: exact code match 100,
  family match 60, job match 40, plus a vehicle-fit bonus (exact model
  +30, sibling platform +10, generic/unknown +0) when ``vin`` resolves a
  model via ``mes.platform.model_for_vin``. A link found by more than one
  lookup keeps the highest relevance (and that lookup's reason).
* importance -- reputation (high +20, medium +10), kind (how_to_video
  +15, teardown +12, forum_thread +10, sound_reference +8, owner_report
  +5), and recency (+1 per year since 2020, capped at +6).

Each link gets a ``score`` (int) and a short ``reason`` string built from
the same signals (e.g. ``"exact code, this model, hands-on video"``) so a
page can explain the ranking, not just show it.

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
presented as this car's own experience, and (see above) a smaller
vehicle-fit bonus than an exact-model match.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any, Optional

#: relevance points by which lookup found the link, and the reason phrase
#: that lookup contributes.
_RELEVANCE = {
    "code": (100, "exact code"),
    "family": (60, "family match"),
    "job": (40, "job match"),
}

#: vehicle-fit bonus points + reason phrase, by fit tier.
_VEHICLE_FIT_EXACT = (30, "this model")
_VEHICLE_FIT_SIBLING = (10, "sibling model: verify fit")

#: reputation points, lower-cased reputation value -> points.
_REPUTATION_SCORE = {"high": 20, "medium": 10}

#: importance points + reason phrase, by ``kind``.
_KIND_SCORE = {
    "how_to_video": (15, "hands-on video"),
    "teardown": (12, "teardown"),
    "forum_thread": (10, "forum thread"),
    "sound_reference": (8, "sound reference"),
    "owner_report": (5, "owner report"),
}

#: recency cap: at most this many points, one per year since _RECENCY_BASE.
_RECENCY_BASE_YEAR = 2020
_RECENCY_CAP = 6


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


def _sibling_model_names(model: Optional[str]) -> set[str]:
    """Lower-cased sibling model names for ``model`` (e.g. ``"giulia"``,
    ``"grecale"``), via ``mes.platform.siblings``. Empty set on any
    failure or when ``model`` is falsy -- never raises."""
    if not model:
        return set()
    try:
        from mes import platform as platform_mod  # noqa: PLC0415
        return {str(s.get("model") or "").lower() for s in platform_mod.siblings(model)}
    except Exception:  # noqa: BLE001
        return set()


def _recency_score(value: Any) -> int:
    s = str(value or "")[:10]
    try:
        year = _date.fromisoformat(s).year
    except ValueError:
        return 0
    return max(0, min(_RECENCY_CAP, year - _RECENCY_BASE_YEAR))


def _vehicle_fit_score(vehicle_fit: Any, model: Optional[str],
                        sibling_models: set[str]) -> tuple[int, Optional[str]]:
    if not model or not vehicle_fit:
        return 0, None
    vf_lower = str(vehicle_fit).lower()
    if model in vf_lower:
        return _VEHICLE_FIT_EXACT
    if any(sib in vf_lower for sib in sibling_models):
        return _VEHICLE_FIT_SIBLING
    return 0, None


def _score_link(link: dict[str, Any], via: str, model: Optional[str],
                 sibling_models: set[str]) -> dict[str, Any]:
    """Return a copy of ``link`` with ``score`` (int) and ``reason`` (str)
    added, scored per the module docstring."""
    scored = dict(link)
    reasons: list[str] = []

    relevance, relevance_reason = _RELEVANCE[via]
    reasons.append(relevance_reason)

    vf_score, vf_reason = _vehicle_fit_score(scored.get("vehicle_fit"), model, sibling_models)
    if vf_reason:
        reasons.append(vf_reason)

    reputation = str(scored.get("reputation") or "").lower()
    rep_score = _REPUTATION_SCORE.get(reputation, 0)

    kind = scored.get("kind") or ""
    kind_score, kind_reason = _KIND_SCORE.get(kind, (0, None))
    if kind_reason:
        reasons.append(kind_reason)

    recency_score = _recency_score(scored.get("date"))

    scored["score"] = relevance + vf_score + rep_score + kind_score + recency_score
    scored["reason"] = ", ".join(reasons)
    return scored


def links_for(*, code: Optional[str] = None, family: Optional[str] = None,
              job: Optional[str] = None, vin: Optional[str] = None) -> dict[str, Any]:
    """Merged, de-duplicated, scored and ordered (highest score first)
    experience links for whichever of ``code``/``family``/``job`` are
    given. ``{"links": [...], "count": n}``, always -- an empty list
    (never an exception) when ``mes.experience`` is unavailable, nothing
    was given, or the lookup itself failed. Each link in the result
    carries a ``score`` (int) and a ``reason`` (str) -- see module
    docstring for how both are built.

    ``vin``, if given, resolves a model via ``mes.platform.model_for_vin``
    and threads ``include_siblings=True`` through so any sourced
    sibling-platform entries (flagged ``sibling_of``/``verify_fit`` by
    ``mes.experience``) are included too, each labeled "from <Model>
    experience: verify fit", and scored with the smaller sibling
    vehicle-fit bonus rather than the exact-model one.
    """
    experience = _experience_module()
    if experience is None:
        return {"links": [], "count": 0}

    model = _model_for_vin(vin)
    include_siblings = bool(model)
    sibling_models = _sibling_model_names(model)

    collected: list[tuple[dict[str, Any], str]] = []
    try:
        if code:
            for link in experience.for_code(code, include_siblings=include_siblings) or []:
                collected.append((link, "code"))
        if family:
            for link in experience.for_family(family, include_siblings=include_siblings) or []:
                collected.append((link, "family"))
        if job:
            for link in experience.for_job(job, include_siblings=include_siblings) or []:
                collected.append((link, "job"))
    except Exception:  # noqa: BLE001 -- a data-module hiccup must never 500 a page
        return {"links": [], "count": 0}

    best: dict[str, dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []
    for link, via in collected:
        scored = _score_link(link, via, model, sibling_models)
        key = str(link.get("id") or link.get("url") or "")
        if not key:
            unkeyed.append(scored)
            continue
        existing = best.get(key)
        if existing is None or scored["score"] > existing["score"]:
            best[key] = scored

    deduped = list(best.values()) + unkeyed
    deduped.sort(key=lambda l: -l["score"])

    for link in deduped:
        sibling_of = link.get("sibling_of")
        if sibling_of:
            link["label"] = f"from {str(sibling_of).title()} experience: verify fit"
    return {"links": deduped, "count": len(deduped)}


__all__ = ["links_for"]
