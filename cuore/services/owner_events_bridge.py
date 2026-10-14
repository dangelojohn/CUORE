"""HTTP face of :mod:`cuore.live.owner_events` ("Tell CUORE") plus everything
that needs to reach outside that store: the 25-key systems graph (for
``events_for_system``), this car's own DTC history (for ``correlate``), and
the mechanic feedback/inbox store (for ``messages`` -- CUORE's own questions
to the owner, and the mechanic's, share that one inbox).

Same posture as every other ``cuore/services/*_bridge.py``: the only place
that imports ``mes`` directly for this feature, so the data contract can be
reviewed and tested on its own.

**Every value this module returns is ATTESTED, never a car measurement.**
``correlate`` in particular must never say a reported event *caused* a code
-- only that the two are near each other in time, worded "owner-reported,
possible link" everywhere it is shown.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import mes_bridge, systems_bridge
from .errors import BadRequest, NotFound
from ..live import owner_events as store

from mes import feedback as feedback_mod  # noqa: E402
from mes import symptoms as symptoms_mod  # noqa: E402

#: The inbox "page" every CUORE-generated and mechanic-asked owner question
#: is filed under, in the same ``mes.feedback`` store the rest of cuore
#: already uses for mechanic corrections/questions/confirms. Keeping these
#: on their own page namespace means ``messages()`` below is just "feedback
#: filed against the owner page", and a mechanic can ask the owner something
#: today with the exact same ``feedback_add`` call the Inbox page already
#: offers -- no second messaging system.
MESSAGE_PAGE = "owner"

CORRELATION_WINDOW_DAYS = 14

#: code family -> the CUORE-generated questions worth asking the owner when
#: a code in that family is active. Keyed by the systems-graph key the code
#: implicates (see ``mes.systems.systems_for_code``), not by a second,
#: hand-rolled code list -- so this rides on the one sourced mapping cuore
#: already has rather than forking a copy of it.
#:
#: Each entry is ``(question_id, text)``; ``question_id`` is part of the
#: dedup key in :func:`messages` so the same question is never refiled for
#: the same code twice.
_BASE_RE = re.compile(r"^([PBCU][0-9A-F]{4})", re.IGNORECASE)


def _base_code(code: str) -> str:
    """Strip a module suffix (``"P0456-00"`` -> ``"P0456"``), same rule
    ``timeline_bridge._base`` uses -- codes are correlated and matched on
    the base code, never on which module happened to report it."""
    m = _BASE_RE.match((code or "").strip().upper())
    return m.group(1) if m else (code or "").strip().upper()


PROMPT_RULES: dict[str, list[tuple[str, str]]] = {
    "evap": [
        ("evap_fillup_recent", "Did you fill up in the last 2 days? Was the cap clicked "
                               "until it clicked?"),
        ("evap_short_trips", "Is this car mostly short trips lately (under ~15 minutes)?"),
    ],
    "electrical_supply": [
        ("elec_recent_work", "Any battery work, jump start, or aftermarket electrical "
                             "fitted recently (dashcam, lights, audio, tracker)?"),
    ],
    "starting_charging": [
        ("start_conditions", "When it's hard to start, is that cold, hot, or after the "
                             "car has been sitting a while?"),
    ],
    "security_immobiliser": [
        ("security_recent", "Any key fob battery change, module work, or anything unusual "
                            "around the doors/locks recently?"),
    ],
}


# --- plain pass-through: add/list/delete/taxonomy ----------------------------


def taxonomy() -> dict[str, Any]:
    """The full category/kind table -- the one source the mobile form, the
    API's validation, and the history page all read."""
    return {"categories": store.TAXONOMY}


def add(vin: str, category: str, kind: str, *, at: Optional[str] = None,
        by_role: str = "owner", by_name: str = "", fields: Optional[dict[str, Any]] = None,
        note: str = "", media_ids: Optional[list[str]] = None,
        odometer_km: Optional[float] = None,
        fields_meta: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Record one owner event. Raises :class:`BadRequest` on invalid input.

    ``incidents / noise_smell_vibration`` is the one kind this function
    does not store in ``owner_events.jsonl`` at all: it hands off to
    ``mes.symptoms`` (the same store the mechanic-vs-driver timeline reads)
    so a driver's "rough idle cold" report shows up in exactly one place,
    not two. See the taxonomy entry's ``delegate_to_symptoms`` flag.
    """
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        kd = store.kind_def(category, kind)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc

    if kd.get("relevance", {}).get("delegate_to_symptoms"):
        f = fields or {}
        text = " ".join(str(f.get(k, "")).strip() for k in ("description", "when")
                        if f.get(k)).strip()
        try:
            rec = symptoms_mod.add(
                vin, at or datetime.now().isoformat(timespec="seconds"),
                odometer_km=odometer_km,
                reporter="mechanic" if by_role == "mechanic" else "driver",
                tags=["other"], text=text or note)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc
        rec = dict(rec)
        rec["category"], rec["kind"], rec["confidence"] = category, kind, "reported"
        rec["delegated_to"] = "mes.symptoms"
        return rec

    try:
        return store.add(vin, category, kind, at=at, by_role=by_role, by_name=by_name,
                         fields=fields, note=note, media_ids=media_ids,
                         odometer_km=odometer_km, fields_meta=fields_meta)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def _symptom_as_event(vin: str, rec: dict[str, Any]) -> dict[str, Any]:
    """A ``mes.symptoms`` row, reshaped to look like an owner_events row, so
    a caller never has to know the noise/smell/vibration kind lives in a
    different store."""
    return {
        "op": "event", "id": rec.get("id"), "vin": vin, "at": rec.get("at"),
        "recorded_at": rec.get("created_at"),
        "by": {"role": rec.get("reporter") or "driver", "name": ""},
        "category": "incidents", "kind": "noise_smell_vibration",
        "fields": {"description": rec.get("text") or "", "tags": rec.get("tags") or []},
        "note": rec.get("text") or "", "media_ids": [], "odometer_km": rec.get("odometer_km"),
        "confidence": "reported", "deleted": bool(rec.get("hidden")),
        "delegated_to": "mes.symptoms",
    }


def list_events(vin: str, *, include_deleted: bool = False) -> dict[str, Any]:
    """Every owner event for this VIN, oldest first -- the owner_events
    store plus that one symptoms-delegated kind, merged into one timeline."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    events = store.load(vin, include_deleted=include_deleted)
    try:
        symptom_recs = symptoms_mod.load(vin, include_hidden=include_deleted)
    except Exception:  # noqa: BLE001 -- a missing corpus must not break the page
        symptom_recs = []
    events += [_symptom_as_event(vin, r) for r in symptom_recs]
    events.sort(key=lambda e: e.get("at") or "")
    return {"vin": vin, "events": events}


def delete(id: str) -> dict[str, Any]:
    try:
        return store.delete(id)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def restore(id: str) -> dict[str, Any]:
    """Undo a soft-delete -- the Mobile page's "Undo" on the post-delete
    confirmation screen."""
    try:
        return store.restore(id)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def edit(vin: str, id: str, patch: dict[str, Any], by: str = "owner",
        by_name: str = "") -> dict[str, Any]:
    """Apply one edit (``patch`` may carry ``fields``/``note``/
    ``odometer_km``/``at``) to an existing owner event on ``vin``.

    Raises :class:`NotFound` (404) when ``id`` doesn't resolve to a
    non-deleted event on this ``vin`` -- checked here, against this VIN's
    own event list, rather than left to ``cuore.live.owner_events.edit``,
    so an id that belongs to a *different* vin 404s the same as an unknown
    one rather than leaking cross-vehicle existence. Raises
    :class:`BadRequest` (400) for a bad key/value in ``patch`` (e.g. a field
    not in this event's kind's taxonomy) -- the one case the store layer
    itself still catches.
    """
    if not vin.strip():
        raise BadRequest("a VIN is required")
    current = next((e for e in store.load(vin, include_deleted=True) if e.get("id") == id), None)
    if current is None or current.get("deleted"):
        raise NotFound(f"no owner event with id {id!r}")
    try:
        return store.edit(id, fields=patch.get("fields"), note=patch.get("note"),
                          odometer_km=patch.get("odometer_km"), at=patch.get("at"),
                          by_role=by, by_name=by_name)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def events_for_system(vin: str, key: str) -> dict[str, Any]:
    """Owner events whose kind touches systems-graph key ``key``."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    key = (key or "").strip()
    out = []
    for e in list_events(vin)["events"]:
        try:
            kd = store.kind_def(e["category"], e["kind"])
        except (ValueError, KeyError):
            continue
        if key in kd.get("systems", []):
            out.append(e)
    return {"vin": vin, "system": key, "events": out}


# --- correlation against this car's own DTC history --------------------------


def _code_occurrences(vin: str) -> list[dict[str, Any]]:
    """Every (code, timestamp, kind) worth correlating against: the first
    occurrence of each code this car has ever logged, plus every
    "returned after clear" occurrence -- the two moments a mechanic actually
    cares whether something changed beforehand."""
    try:
        dossier = mes_bridge.workup(vin=vin)
    except Exception:  # noqa: BLE001 -- no corpus yet must not break the page
        return []
    history = dossier.get("history") or {}
    out: list[dict[str, Any]] = []
    for bucket in ("chronic", "returned_after_clear", "seen_once"):
        for rec in history.get(bucket, []):
            code = _base_code(rec.get("dtc") or "")
            occs = sorted(rec.get("occurrences", []), key=lambda o: o.get("timestamp") or "")
            if not occs:
                continue
            out.append({"code": code, "at": occs[0].get("timestamp"), "event_kind": "first_occurrence"})
            for occ in occs:
                if occ.get("status") == "returned":
                    out.append({"code": code, "at": occ.get("timestamp"), "event_kind": "return"})
    return out


def correlate(vin: str) -> dict[str, Any]:
    """For each code's first occurrence and each return-after-clear on this
    car, every owner-reported event in the 14 days before it.

    Never says "cause" -- every entry is labelled ``"owner-reported,
    possible link"``. This is a timing coincidence surfaced for a mechanic
    to judge, not a conclusion.
    """
    if not vin.strip():
        raise BadRequest("a VIN is required")
    events = list_events(vin)["events"]
    window = timedelta(days=CORRELATION_WINDOW_DAYS)

    def _dt(s: Any) -> Optional[datetime]:
        if not s:
            return None
        text = str(s).strip().replace("T", " ")
        if len(text) == 10:
            text += " 00:00:00"
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    correlations = []
    for occ in _code_occurrences(vin):
        odt = _dt(occ["at"])
        if odt is None:
            continue
        nearby = []
        for e in events:
            edt = _dt(e.get("at"))
            if edt is None:
                continue
            if edt <= odt and (odt - edt) <= window:
                nearby.append(e)
        if nearby:
            correlations.append({
                "code": occ["code"], "occurrence_at": occ["at"], "event_kind": occ["event_kind"],
                "owner_events": nearby, "note": "owner-reported, possible link",
            })
    return {"vin": vin, "window_days": CORRELATION_WINDOW_DAYS, "correlations": correlations}


# --- messages: CUORE prompts + the mechanic's own asks, one inbox -----------


def _active_codes(vin: str) -> list[str]:
    """Base codes (module suffix stripped) this car currently carries that
    are not simply cleared -- chronic, returned-after-clear, recurring, or
    a plain uncleared seen-once. Normalized to the base code so a prompt
    filed here lines up with :func:`correlate`'s own base-code keys."""
    try:
        data = mes_bridge.extract_dtcs(vin=vin)
    except Exception:  # noqa: BLE001
        return []
    return sorted({_base_code(d["dtc"]) for d in data.get("dtcs", [])
                  if d.get("severity") != "cleared"})


def _families_for_code(code: str) -> set[str]:
    try:
        hits = systems_bridge.systems_for_code(code)
    except Exception:  # noqa: BLE001
        return set()
    return {h.get("system") for h in hits if h.get("system")}


def _ensure_prompts_filed(vin: str) -> None:
    """Generate-on-read: file any CUORE prompt that doesn't already exist
    for this (vin, code, question_id). Idempotent -- safe to call on every
    ``messages()`` read."""
    existing = feedback_mod.load(vin, status=None)
    existing_keys = {(r["target"].get("section"), r["target"].get("item"))
                    for r in existing if r.get("target", {}).get("page") == MESSAGE_PAGE}
    for code in _active_codes(vin):
        for family in _families_for_code(code):
            for qid, text in PROMPT_RULES.get(family, []):
                if (code, qid) in existing_keys:
                    continue
                try:
                    feedback_mod.add(vin, "question",
                                     {"page": MESSAGE_PAGE, "section": code, "item": qid,
                                      "label": f"{code}: {text}"[:200]},
                                     text=text, author="cuore")
                except ValueError:
                    continue
                existing_keys.add((code, qid))


def messages(vin: str) -> dict[str, Any]:
    """Questions for the owner: CUORE's own code-triggered prompts (filed
    fresh on this read, deduped) plus anything a mechanic has already asked
    on the same ``owner`` page -- one inbox, oldest open first."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    _ensure_prompts_filed(vin)
    rows = [r for r in feedback_mod.load(vin, status=None)
           if r.get("target", {}).get("page") == MESSAGE_PAGE]
    rows.sort(key=lambda r: (r.get("status") != "open", r.get("at") or ""))
    return {"vin": vin, "messages": rows}


def reply_message(id: str, text: str, by: str = "owner") -> dict[str, Any]:
    """The owner's (or mechanic's) reply to one message -- recorded as the
    feedback row's answer, same ``mes.feedback`` lifecycle every other
    answered question in cuore already uses."""
    try:
        return feedback_mod.answer(id, by, text)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


__all__ = ["MESSAGE_PAGE", "CORRELATION_WINDOW_DAYS", "PROMPT_RULES",
          "taxonomy", "add", "list_events", "delete", "restore", "edit",
          "events_for_system", "correlate", "messages", "reply_message"]
