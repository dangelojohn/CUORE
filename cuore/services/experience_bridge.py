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

**Driver/mechanic-added links** (added 2026-10-14, answering the owner's own
complaint: *"I need to add Others' experiences input data from driver and
mechanic ... I am unable to modify these fields"*) -- :mod:`cuore.live.
experience_inputs` is the append-only store a "+ Add what you found" form
writes to. :func:`links_for` merges that store's rows for the same
code/family/job (and ``vin``, when given -- see that module's own docstring
for exactly how vin-less rows are treated as universal) into the same
``links`` list the curated table produces, shaped identically plus
``curated`` (bool), ``found_by`` ``{role, name}``, ``found_at``, ``note``,
``rating``, ``verified`` ``{status, at, method}``, ``flags`` and
``worked_count`` -- so one template loop renders both.

Sort order changed with this merge: links are now bucketed by **tier**
before score -- curated rows (hand-verified by definition, see
``mes.experience``'s own docstring) are tier 0; a mechanic-added row
verified reachable is tier 1; a driver-added row verified reachable is tier
2; everything else (owner/cuore-added, or anything not verified) is tier 3,
last. Only within a tier does the existing relevance/importance ``score``
still decide order -- the four ``?exp=`` views on the card re-filter this
same tiered-then-scored list, so "relevant" always means "curated, then
mechanic, then driver, then the rest," never a plain score sort across
roles.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any, Optional

from ..live import experience_inputs as _inputs_store
from .errors import BadRequest, NotFound

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


#: a user-picked ``kind`` (cuore.live.experience_inputs.KINDS) reuses the
#: curated table's own importance points via this mapping onto _KIND_SCORE's
#: keys; anything not listed (article/manual/photo/note) scores like
#: owner_report.
_INPUT_KIND_SCORE_KEY = {"video": "how_to_video", "forum": "forum_thread", "audio": "sound_reference"}

#: rating adjustment -- a driver/mechanic's own "did this help" signal,
#: on top of the same importance points a curated row earns.
_RATING_SCORE = {"helped": 5, "unsure": 0, "wrong": -25}

#: role chip label shown on the card -- curated rows are stamped with the
#: "cuore" role at merge time (see :func:`_curated_as_link`) so one lookup
#: covers every row.
ROLE_LABELS = {"cuore": "CUORE curated", "mechanic": "Mechanic", "driver": "Driver", "owner": "Owner"}


def _tier(link: dict[str, Any]) -> int:
    """0 curated, 1 mechanic (verified reachable), 2 driver (verified
    reachable), 3 everything else (owner/cuore-added, or not verified) --
    see module docstring for why this bucket comes before ``score``."""
    if link.get("curated"):
        return 0
    role = (link.get("found_by") or {}).get("role")
    verified_ok = (link.get("verified") or {}).get("status") == "verified"
    if not verified_ok:
        return 3
    if role == "mechanic":
        return 1
    if role == "driver":
        return 2
    return 3


def _score_input(view: dict[str, Any], via: str) -> dict[str, Any]:
    """Shape one folded :mod:`cuore.live.experience_inputs` row into the
    same dict shape a curated link has, with ``score``/``reason`` built
    from the same relevance+importance signals plus the rating adjustment
    only a user-added row carries."""
    relevance, relevance_reason = _RELEVANCE[via]
    reasons = [relevance_reason]

    kind = view.get("kind") or "note"
    kind_key = _INPUT_KIND_SCORE_KEY.get(kind, "owner_report")
    kind_score, kind_reason = _KIND_SCORE.get(kind_key, (5, "owner report"))
    reasons.append(kind_reason)

    verified_ok = (view.get("verified") or {}).get("status") == "verified"
    rep_score = _REPUTATION_SCORE["medium"] if verified_ok else 0
    if verified_ok:
        reasons.append("verified reachable")

    rating = view.get("rating") or "unsure"
    rating_score = _RATING_SCORE.get(rating, 0)
    if rating == "helped":
        reasons.append("reported: helped")
    elif rating == "wrong":
        reasons.append("reported: wrong")

    recency_score = _recency_score(view.get("found_at"))

    found_by = dict(view.get("found_by") or {})
    return {
        "id": view.get("id"),
        "title": view.get("title") or view.get("url"),
        "url": view.get("url"),
        "source": _host_of_for_source(view.get("url", "")),
        "kind": kind,
        "covers": "",
        "date": (view.get("found_at") or "")[:10],
        "reputation": "medium" if verified_ok else "",
        "verified_at": (view.get("verified") or {}).get("at", ""),
        "verified_how": (view.get("verified") or {}).get("method", ""),
        "curated": False,
        "found_by": found_by,
        "found_at": view.get("found_at"),
        "note": view.get("note", ""),
        "rating": rating,
        "verified": view.get("verified") or {},
        "score": relevance + kind_score + rep_score + rating_score + recency_score,
        "reason": ", ".join(reasons),
    }


def _host_of_for_source(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except ValueError:
        return ""


def _curated_as_link(scored: dict[str, Any]) -> dict[str, Any]:
    """Stamp a curated (``mes.experience``) row, already scored by
    :func:`_score_link`, with the fields the merged shape needs: ``curated``
    True and a ``found_by``/``found_at`` that render through the same
    "Found by <role> ... <date>" chip every row uses."""
    scored = dict(scored)
    scored["curated"] = True
    scored["found_by"] = {"role": "cuore", "name": "CUORE curated"}
    scored["found_at"] = scored.get("verified_at") or scored.get("date") or ""
    scored["note"] = scored.get("covers", "")
    scored["rating"] = "helped"
    scored["verified"] = {"status": "verified" if scored.get("verified_at") else "unverified",
                          "at": scored.get("verified_at", ""), "method": scored.get("verified_how", "")}
    return scored


def _attach_feedback(link: dict[str, Any]) -> dict[str, Any]:
    """Best-effort: attach ``flags`` and ``worked_count`` from
    :mod:`cuore.live.experience_inputs`. Never raises -- a store hiccup just
    means those two fields come back empty/zero."""
    link = dict(link)
    lid = str(link.get("id") or "")
    try:
        link["flags"] = _inputs_store.flags_for(lid) if lid else []
    except Exception:  # noqa: BLE001
        link["flags"] = []
    try:
        link["worked_count"] = len(_inputs_store.worked_for(lid)) if lid else 0
    except Exception:  # noqa: BLE001
        link["worked_count"] = 0
    return link


def _matching_inputs(*, code: Optional[str], family: Optional[str], job: Optional[str],
                     vin: Optional[str]) -> list[tuple[dict[str, Any], str]]:
    """User-added rows (:mod:`cuore.live.experience_inputs`) whose scope
    matches ``code``/``family``/``job``, each paired with the field that
    matched (same ``via`` vocabulary the curated lookups use). Best-effort:
    a store hiccup degrades to no user rows, same posture as everything
    else in this module."""
    try:
        rows = _inputs_store.load(vin or "")
    except Exception:  # noqa: BLE001
        return []
    out: list[tuple[dict[str, Any], str]] = []
    for view in rows:
        scope = view.get("scope") or {}
        if code and scope.get("code") == code:
            out.append((view, "code"))
        elif family and scope.get("family") == family:
            out.append((view, "family"))
        elif job and scope.get("job") == job:
            out.append((view, "job"))
    return out


def links_for(*, code: Optional[str] = None, family: Optional[str] = None,
              job: Optional[str] = None, vin: Optional[str] = None,
              include_inputs: bool = True) -> dict[str, Any]:
    """Merged, de-duplicated, tiered-then-scored experience links (curated
    plus driver/mechanic-added -- see module docstring) for whichever of
    ``code``/``family``/``job`` are given. ``{"links": [...], "count": n,
    "counts": {role: n}}``, always -- never an exception, even when
    ``mes.experience`` is unavailable (user-added rows still render) or
    nothing was given at all (empty list). Each link carries a ``score``
    (int) and a ``reason`` (str); ``counts`` tallies curated vs. mechanic vs.
    driver vs. other for the section header ("12 curated - 3 mechanic").

    ``vin``, if given, resolves a model via ``mes.platform.model_for_vin``
    and threads ``include_siblings=True`` through so any sourced
    sibling-platform entries (flagged ``sibling_of``/``verify_fit`` by
    ``mes.experience``) are included too, each labeled "from <Model>
    experience: verify fit", and scored with the smaller sibling
    vehicle-fit bonus rather than the exact-model one. It also scopes which
    user-added rows are eligible (plus any vin-less/universal ones -- see
    :mod:`cuore.live.experience_inputs`).

    Pass ``include_inputs=False`` to get the curated-only legacy behaviour.
    """
    experience = _experience_module()
    model = _model_for_vin(vin)
    include_siblings = bool(model)
    sibling_models = _sibling_model_names(model)

    collected: list[tuple[dict[str, Any], str]] = []
    if experience is not None:
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
            collected = []

    best: dict[str, dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []
    for link, via in collected:
        scored = _curated_as_link(_score_link(link, via, model, sibling_models))
        key = str(link.get("id") or link.get("url") or "")
        if not key:
            unkeyed.append(scored)
            continue
        existing = best.get(key)
        if existing is None or scored["score"] > existing["score"]:
            best[key] = scored

    curated_links = list(best.values()) + unkeyed

    user_links: list[dict[str, Any]] = []
    if include_inputs:
        for view, via in _matching_inputs(code=code, family=family, job=job, vin=vin):
            if view.get("id"):
                user_links.append(_score_input(view, via))

    for link in curated_links:
        sibling_of = link.get("sibling_of")
        if sibling_of:
            link["label"] = f"from {str(sibling_of).title()} experience: verify fit"

    merged = [_attach_feedback(link) for link in curated_links + user_links]
    merged.sort(key=lambda l: (_tier(l), -l["score"]))

    counts = _inputs_store.counts_by_role(user_links) if include_inputs else {}
    counts["curated"] = len(curated_links)

    return {"links": merged, "count": len(merged), "counts": counts}


# --------------------------------------------------------------------------
# write path: thin wrappers over cuore.live.experience_inputs, translating
# ValueError (bad caller input) to BadRequest the way every other bridge's
# write path does for its own store (e.g. owner_events_bridge for
# cuore.live.owner_events). "Not found" is distinguished from "bad input"
# so the API can return 404 vs. 400.
# --------------------------------------------------------------------------

def add_input(**kwargs: Any) -> dict[str, Any]:
    try:
        return _inputs_store.add_input(**kwargs)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def edit_input(id: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return _inputs_store.edit_input(id, **kwargs)
    except ValueError as exc:
        msg = str(exc)
        if "no experience input" in msg:
            raise NotFound(msg) from exc
        raise BadRequest(msg) from exc


def delete_input(id: str) -> dict[str, Any]:
    try:
        return _inputs_store.delete_input(id)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


def restore_input(id: str) -> dict[str, Any]:
    try:
        return _inputs_store.restore_input(id)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


def list_inputs(vin: str = "", *, role: Optional[str] = None,
                scope_field: Optional[str] = None, scope_value: Optional[str] = None,
                include_deleted: bool = False) -> dict[str, Any]:
    rows = _inputs_store.load(vin, include_deleted=include_deleted, role=role,
                              scope_field=scope_field, scope_value=scope_value)
    return {"vin": vin, "inputs": rows, "count": len(rows)}


def flag_curated(target_id: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return _inputs_store.flag_curated(target_id, **kwargs)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def mark_worked(target_id: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return _inputs_store.mark_worked(target_id, **kwargs)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def export_for_curation(vin: str = "", *, role: str = "mechanic",
                        rating: str = "helped") -> dict[str, Any]:
    return {"vin": vin, "export": _inputs_store.export_for_curation(vin, role=role, rating=rating)}


__all__ = ["links_for", "ROLE_LABELS", "add_input", "edit_input", "delete_input",
          "restore_input", "list_inputs", "flag_curated", "mark_worked",
          "export_for_curation"]
