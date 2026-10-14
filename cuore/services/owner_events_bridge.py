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

# Best-effort: the scan-done message (see ``messages`` below) reads the
# from-car live-scan surfaces -- ``cuore.live.scanlog``'s own grouping and
# ``cuore.services.scan_health_bridge``'s report -- plus ``mes.live_obs``/
# ``mes.scan_health`` directly, for the one piece (which Mode 06 MID failed)
# the report's own public row does not carry. None of this is required for
# the rest of the module: a corpus with no live link yet, or either import
# failing, simply means no scan-done message and no live-scan contribution
# to :func:`_active_codes` -- never an error on this page.
try:
    from . import scanlog_bridge  # noqa: E402
except Exception:  # noqa: BLE001
    scanlog_bridge = None  # type: ignore[assignment]
try:
    from . import scan_health_bridge  # noqa: E402
except Exception:  # noqa: BLE001
    scan_health_bridge = None  # type: ignore[assignment]
try:
    from mes import live_obs as live_obs_mod  # noqa: E402
    from mes import scan_health as scan_health_mod  # noqa: E402
except Exception:  # noqa: BLE001
    live_obs_mod = None  # type: ignore[assignment]
    scan_health_mod = None  # type: ignore[assignment]

# Best-effort: a ``fluids / driveline_fluid`` report also mirrors into
# ``mes.service`` (category ``drivetrain``) -- see
# :func:`_driveline_fluid_to_ledger`. Defensive import for the same reason
# as the two blocks above: this is an extra hand-off, never required for
# the owner event itself to save.
try:
    from mes import service as service_mod  # noqa: E402
except Exception:  # noqa: BLE001
    service_mod = None  # type: ignore[assignment]

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


#: Re-exported for any existing caller that imported this name from here --
#: the table itself now lives on the store (:data:`cuore.live.owner_events.
#: PROMPT_RULES`), next to :data:`cuore.live.owner_events.TAXONOMY`.
PROMPT_RULES = store.PROMPT_RULES

#: ``fluids / driveline_fluid``'s ``which`` value -> the ``mes.service``
#: drivetrain (section, job) it mirrors onto (see :func:`_driveline_fluid_
#: to_ledger`). "differential" has no front/rear choice on the phone form,
#: so it best-effort-defaults to the front job -- the mirrored record's own
#: ``considerations_next`` says so, it is never silently assumed correct.
_DRIVELINE_FLUID_TARGET: dict[str, tuple[str, str]] = {
    "transmission": ("transmission", "transmission_fluid_service"),
    "transfer case": ("transfer_case", "transfer_case_service"),
    "differential": ("differentials", "differential_service_front"),
}


def _driveline_fluid_to_ledger(vin: str, fields: dict[str, Any], at: Optional[str],
                               odometer_km: Optional[float], by_role: str,
                               by_name: str) -> None:
    """Best-effort mirror of a phone-reported driveline-fluid event into
    ``mes.service`` (category ``drivetrain``) -- the ledger stays the one
    source the drivetrain sheet reads, so a mechanic's own sheet also
    picks up what an owner/driver reported from the phone. Called *in
    addition to* the normal ``owner_events.jsonl`` row, never instead of
    it (contrast ``delegate_to_symptoms`` above, which replaces storage).
    Never raises: a missing odometer reading (required by the ledger,
    optional on the phone form) or any other validation gap simply means
    no ledger mirror for this one report, not a failed save of the owner
    event itself, which has already happened by the time this runs.
    """
    if service_mod is None or not vin.strip():
        return
    target = _DRIVELINE_FLUID_TARGET.get(str(fields.get("which", "")).strip().lower())
    if target is None or odometer_km is None:
        return
    section, job = target
    parts = []
    pan_part = str(fields.get("pan_filter_part_no", "")).strip()
    if pan_part:
        parts.append({"name": "pan/filter", "part_no": pan_part, "qty": 1})
    data: dict[str, Any] = {
        "section": section, "job": job,
        "date": (at or datetime.now().isoformat(timespec="seconds"))[:10],
        "odometer_km": odometer_km,
        "technician": (by_name or by_role or "owner"),
        "fluid": {"brand": fields.get("brand", ""), "spec": fields.get("fluid_spec", "")},
        "quantity_added_l": fields.get("qty"),
        "fluid_temp_c": fields.get("fill_temp_c"),
        "parts_replaced": parts,
        "discoveries": [f"method: {fields['method']}"] if fields.get("method") else [],
        "considerations_next": (
            ["owner reported 'differential' without front/rear -- confirm "
             "which unit before relying on this mirrored record"]
            if section == "differentials" else []),
    }
    try:
        service_mod.record_drivetrain(vin, data)
    except Exception:  # noqa: BLE001 -- best-effort mirror, never blocks the owner event
        pass


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
        rec = store.add(vin, category, kind, at=at, by_role=by_role, by_name=by_name,
                        fields=fields, note=note, media_ids=media_ids,
                        odometer_km=odometer_km, fields_meta=fields_meta)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    if category == "fluids" and kind == "driveline_fluid":
        _driveline_fluid_to_ledger(vin, fields or {}, at, odometer_km, by_role, by_name)
    return rec


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


def _vin_or_untagged(entry: dict[str, Any], vin: str) -> bool:
    """Same single-car-install convention ``cuore.services.scan_health_
    bridge._vin_matches`` already documents: a live-scan read's own ``vin``
    field is blank more often than not (Mode 03/06 reads, mostly), so an
    untagged read is kept for this vin rather than dropped."""
    v = entry.get("vin") or ""
    return v in ("", vin)


def _live_active_codes(vin: str) -> set[str]:
    """Base codes this car's live-scan link (``mes.live_obs``) currently
    carries, independent of the MES log catalog :func:`_active_codes`
    already reads: the newest ``obd_dtcs`` read of each kind (stored/
    pending/permanent -- by definition the car's current answer, no flags
    to grade), plus any UDS module DTC whose own status flags still read
    ``"active"`` (never a bare history bit) per
    ``mes.scan_health.module_dtc_category``. Best-effort: no live link, or
    no reads yet, is an empty set, never an error -- the "Scan done"
    message and these prompts share this one reason a quiet car shows
    nothing."""
    if live_obs_mod is None or scan_health_mod is None:
        return set()
    try:
        obs = live_obs_mod.load(from_car_only=True)
    except Exception:  # noqa: BLE001
        return set()

    out: set[str] = set()
    latest_dtc: dict[str, list[str]] = {}
    for o in obs:
        if o.get("kind") != "obd_dtcs" or not _vin_or_untagged(o, vin):
            continue
        data = o.get("data") or {}
        k = data.get("kind")
        if k in ("stored", "pending", "permanent"):
            latest_dtc[k] = list(data.get("dtcs") or [])
    for codes in latest_dtc.values():
        out.update(_base_code(c) for c in codes)

    latest_module: dict[str, dict[str, Any]] = {}
    for o in obs:
        if o.get("kind") != "module_dtcs" or not _vin_or_untagged(o, vin):
            continue
        data = o.get("data") or {}
        ecu = data.get("ecu")
        if ecu and not data.get("error"):
            latest_module[ecu] = data
    for data in latest_module.values():
        for rec in data.get("dtcs") or []:
            code = rec.get("code")
            if code and scan_health_mod.module_dtc_category(rec.get("flags")) == "active":
                out.add(_base_code(code))

    out.discard("")
    return out


def _active_codes(vin: str) -> list[str]:
    """Base codes (module suffix stripped) this car currently carries that
    are not simply cleared -- chronic, returned-after-clear, recurring, or
    a plain uncleared seen-once from the MES log catalog, plus whatever the
    live-scan link (:func:`_live_active_codes`) currently shows. Normalized
    to the base code so a prompt filed here lines up with :func:`correlate`'s
    own base-code keys."""
    try:
        data = mes_bridge.extract_dtcs(vin=vin)
        codes = {_base_code(d["dtc"]) for d in data.get("dtcs", [])
                if d.get("severity") != "cleared"}
    except Exception:  # noqa: BLE001
        codes = set()
    codes |= _live_active_codes(vin)
    codes.discard("")
    return sorted(codes)


def _families_for_code(code: str) -> set[str]:
    try:
        hits = systems_bridge.systems_for_code(code)
    except Exception:  # noqa: BLE001
        return set()
    return {h.get("system") for h in hits if h.get("system")}


#: question id -> its chips, flattened once from :data:`PROMPT_RULES` --
#: what :func:`messages` attaches to an unanswered CUORE row so the page
#: can render one-tap buttons, and what :func:`reply_message` matches a
#: reply's exact text against to decide whether to also create an owner
#: event. Built once at import time; ``PROMPT_RULES`` is static config, not
#: something any caller mutates at runtime.
_CHIPS_BY_QID: dict[str, list[dict[str, Any]]] = {
    q["id"]: q.get("chips") or []
    for family in PROMPT_RULES.values() for q in family
}


def _ensure_prompts_filed(vin: str) -> None:
    """Generate-on-read: file any CUORE prompt that doesn't already exist
    for this (vin, code, question_id). Idempotent -- safe to call on every
    ``messages()`` read."""
    existing = feedback_mod.load(vin, status=None)
    existing_keys = {(r["target"].get("section"), r["target"].get("item"))
                    for r in existing if r.get("target", {}).get("page") == MESSAGE_PAGE}
    for code in _active_codes(vin):
        for family in _families_for_code(code):
            for q in PROMPT_RULES.get(family, []):
                qid, text = q["id"], q["text"]
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


# --- messages: the "Scan done" note -----------------------------------------
#
# A plain-language, owner-facing note generated on read from the newest
# from-car scan (``scanlog_bridge.list_scans`` for which scan and when,
# ``scan_health_bridge.build`` for what it found) -- filed into the same
# inbox as the code prompts above, deduped per scan id the same way a code
# prompt is deduped per (code, question id), so a page visit never refiles
# the same scan twice. Either bridge failing to import, or this vin having
# no scan on file, means no scan-done message -- never an error.
#
# Wording rules (owner-facing, graded): never "cause" or "fixed" -- a
# failed self-test is reported, not diagnosed; one line per system this
# scan's own verdict marks FAULT; a "What you can do" line only when EVAP
# is among them (the one family with owner-actionable habits); the closing
# line is always the same "please don't clear the light" request, since a
# cleared code erases the evidence this whole page exists to keep.

_MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: EVAP's own Mode 06 leak-test family (``mes.scan_health.MODE06_MIDS``) ->
#: the plain-language leak-size word for "<word> test failed".
_EVAP_LEAK_MID_SIZE = {"39": "cap-off", "3A": "large-leak", "3C": "small-leak"}

#: ``mes.mechanic_tests`` id -> a short owner-facing name for the "Next:"
#: line. A ``next_test`` id not in this table falls back to a generic
#: phrase rather than guessing a name for a test this table doesn't know.
_NEXT_TEST_PLAIN = {
    "esim_vacuum_test_a": "the ESIM switch test",
    "evap_smoke": "a smoke test to find the leak",
    "purge_vent_actuation": "a check that the EVAP valves open and close correctly",
    "fuel_trim_o2_observation": "a fuel-trim/oxygen-sensor check",
    "misfire_counters": "a misfire check",
}

_EVAP_WHAT_YOU_CAN_DO = (
    "What you can do: keep the fuel level between about 1/4 and 3/4 tank, "
    "click the fuel cap until it clicks, and don't keep topping off after "
    "the pump stops on its own."
)


def _format_scan_at(at: Optional[str]) -> str:
    """``"2026-10-13T20:59:23"`` -> ``"13 Oct 20:59"`` -- no year (today's
    scan), no seconds (an owner doesn't need them)."""
    text = str(at or "").strip().replace("T", " ")
    try:
        dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return text or "an unknown time"
    return f"{dt.day} {_MONTH_ABBR[dt.month - 1]} {dt.strftime('%H:%M')}"


def _mode06_fail_rows(vin: str) -> list[dict[str, Any]]:
    """Every Mode 06 row that failed on this car's newest ``mode06`` live
    read, with its own MID id kept on the row -- read directly off
    ``mes.live_obs`` because the row ``scan_health_bridge.build``'s own
    systems table returns does not carry the MID (see
    ``mes.scan_health.classify_system``'s return shape). Used only to add
    the EVAP leak-size/next-test detail onto a system the report has
    *already* marked FAULT, never to decide FAULT/OK on its own."""
    if live_obs_mod is None:
        return []
    try:
        obs = live_obs_mod.load(from_car_only=True)
    except Exception:  # noqa: BLE001
        return []
    latest = None
    for o in obs:
        if o.get("kind") == "mode06" and _vin_or_untagged(o, vin):
            latest = o.get("data") or {}
    if not latest:
        return []
    out: list[dict[str, Any]] = []
    for mid, entry in (latest.get("results") or {}).items():
        for ecu_rows in (entry.get("by_ecu") or {}).values():
            for r in ecu_rows or []:
                if r.get("passed") is False:
                    out.append({**r, "mid": r.get("mid", mid)})
    return out


def _plain_system_line(vin: str, sys_key: str, sys_label: str) -> tuple[str, Optional[str]]:
    """``(owner-facing sentence, next-step phrase or None)`` for one system
    this scan's own verdict marks FAULT. EVAP's own leak-test family gets
    its sourced plain wording (see :data:`_EVAP_LEAK_MID_SIZE`); every other
    system gets a plain, still-sourced-by-name generic sentence -- never
    "cause"/"fixed"."""
    if sys_key == "evap" and scan_health_mod is not None:
        for row in _mode06_fail_rows(vin):
            mid = str(row.get("mid") or "")
            size = _EVAP_LEAK_MID_SIZE.get(mid)
            if not size:
                continue
            sentence = ("The engine computer's own test says the fuel-vapour "
                       f"system is not holding vacuum ({size} test failed).")
            meta = scan_health_mod.MODE06_MIDS.get(mid) or {}
            next_id = meta.get("next_test")
            return sentence, (_NEXT_TEST_PLAIN.get(next_id, "a further test")
                              if next_id else None)
        return ("The engine computer's own test flags the fuel-vapour (EVAP) "
                "system.", None)
    return (f"The engine computer's own test flags the {sys_label.lower()} system.",
           None)


def _scan_done_text(vin: str) -> Optional[tuple[str, str]]:
    """``(scan_id, message text)`` for the newest from-car scan on file, or
    ``None`` when ``scanlog_bridge`` didn't import or this vin has no scan
    on file yet. ``scan_health_bridge``'s report is read best-effort for
    the verdict detail -- missing it still gives the "scan done" line and
    the closing request, just no per-system detail."""
    if scanlog_bridge is None:
        return None
    try:
        scans = scanlog_bridge.list_scans(vin).get("scans") or []
    except Exception:  # noqa: BLE001
        return None
    if not scans:
        return None
    newest = scans[0]  # newest first, per cuore.live.scanlog.list_scans
    try:
        plan = scanlog_bridge.scan_plan(vin)
    except Exception:  # noqa: BLE001
        plan = {"count": "?", "total": 10}
    when = _format_scan_at(newest.get("ended") or newest.get("started"))
    # Honesty fix (2026-10-14): the opening line must never claim "Scan n
    # of 10 done" for the newest cluster unless THAT cluster was itself a
    # complete scan -- see cuore.live.scanlog's own "Scan plan honesty"
    # docstring section for what "complete"/"partial"/"attempt" mean.
    # ``plan['count']`` (only complete scans) is still named in the
    # partial/attempt cases so the owner always sees how many real scans
    # are on file, never just a bare "it didn't work".
    status = newest.get("status") or "partial"
    if status == "complete":
        lines = [f"Scan {plan['count']} of {plan['total']} done {when}."]
    elif status == "attempt":
        lines = [f"Scan attempt {when} -- the adapter could not be reached "
                f"(no module answered). {plan['count']} of {plan['total']} "
                f"complete scans on file so far."]
    else:
        lines = [f"Partial scan {when} (not a full bus sweep). {plan['count']} of "
                f"{plan['total']} complete scans on file so far."]

    report = None
    if scan_health_bridge is not None:
        try:
            report = scan_health_bridge.build(vin)
        except Exception:  # noqa: BLE001
            report = None

    fail_rows = [r for r in (report or {}).get("systems") or [] if r.get("health") == "FAULT"]
    try:
        labels = systems_bridge.systems()
    except Exception:  # noqa: BLE001
        labels = {}
    next_phrase: Optional[str] = None
    for row in fail_rows:
        sys_key = row.get("system") or ""
        sys_label = (labels.get(sys_key) or {}).get("label") or sys_key.replace("_", " ")
        sentence, nxt = _plain_system_line(vin, sys_key, sys_label)
        lines.append(sentence)
        next_phrase = next_phrase or nxt

    if report is not None:
        if not fail_rows:
            lines.append("Nothing failed.")
        elif len(fail_rows) == 1:
            lines.append("Nothing else failed.")
    if next_phrase:
        lines.append(f"Next: the mechanic runs {next_phrase}.")
    if any(r.get("system") == "evap" for r in fail_rows):
        lines.append(_EVAP_WHAT_YOU_CAN_DO)
    lines.append("Please don't clear the light.")
    return str(newest.get("id") or ""), " ".join(lines)


def _ensure_scan_done_filed(vin: str) -> None:
    """Generate-on-read, deduped per scan id -- the same posture
    :func:`_ensure_prompts_filed` takes per (code, question id), so a page
    visit never refiles the same scan's note twice."""
    result = _scan_done_text(vin)
    if result is None:
        return
    scan_id, text = result
    if not scan_id:
        return
    existing = feedback_mod.load(vin, status=None)
    already = any(r.get("target", {}).get("page") == MESSAGE_PAGE
                 and r.get("target", {}).get("section") == "scan"
                 and r.get("target", {}).get("item") == scan_id
                 for r in existing)
    if already:
        return
    try:
        feedback_mod.add(vin, "question",
                         {"page": MESSAGE_PAGE, "section": "scan", "item": scan_id,
                          "label": text[:200]},
                         text=text, author="cuore")
    except ValueError:
        pass


def messages(vin: str) -> dict[str, Any]:
    """Questions for the owner: the "Scan done" note for the newest scan
    (filed fresh on this read, deduped per scan id), CUORE's own code-
    triggered prompts (filed fresh, deduped per code+question), plus
    anything a mechanic has already asked on the same ``owner`` page -- one
    inbox, oldest open first. An unanswered CUORE-authored row carries its
    own ``chips`` (one-tap answers; empty when the question has none) for
    the page to render as buttons."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    _ensure_scan_done_filed(vin)
    _ensure_prompts_filed(vin)
    rows = [dict(r) for r in feedback_mod.load(vin, status=None)
           if r.get("target", {}).get("page") == MESSAGE_PAGE]
    for r in rows:
        if r.get("status") == "open" and r.get("author") == "cuore":
            r["chips"] = _CHIPS_BY_QID.get(r.get("target", {}).get("item") or "", [])
        else:
            r["chips"] = []
    rows.sort(key=lambda r: (r.get("status") != "open", r.get("at") or ""))
    return {"vin": vin, "messages": rows}


def _event_for_reply(row: dict[str, Any], text: str) -> Optional[dict[str, Any]]:
    """The chip (if any) this reply's exact text matches, for this row's
    question -- ``None`` when the row isn't a CUORE prompt with chips, or
    the text doesn't match one of them (a free-typed reply, most often)."""
    if row.get("target", {}).get("page") != MESSAGE_PAGE:
        return None
    qid = row.get("target", {}).get("item") or ""
    text_norm = text.strip().lower()
    for chip in _CHIPS_BY_QID.get(qid, []):
        if chip.get("label", "").strip().lower() == text_norm:
            return chip
    return None


def reply_message(id: str, text: str, by: str = "owner") -> dict[str, Any]:
    """The owner's (or mechanic's) reply to one message -- recorded as the
    feedback row's answer, same ``mes.feedback`` lifecycle every other
    answered question in cuore already uses.

    When ``text`` is an exact match for one of this message's own one-tap
    chips (see :data:`PROMPT_RULES`), and that chip names a category/kind,
    this also files the matching owner event -- the one-tap answer reuses
    this module's own :func:`add`, never a second write path. A chip with
    no category (e.g. "none of these"), or a free-typed reply that matches
    no chip, only records the reply -- same as it always has."""
    try:
        row = next((r for r in feedback_mod.load(status=None) if r.get("id") == id), None)
        answered = feedback_mod.answer(id, by, text)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    if row is not None:
        chip = _event_for_reply(row, text)
        if chip and chip.get("category") and chip.get("kind"):
            try:
                add(row.get("vin", ""), chip["category"], chip["kind"], by_role=by,
                   fields=chip.get("fields") or {},
                   note=f"from a reply to a CUORE message: {text}"[:store.MAX_NOTE])
            except BadRequest:
                pass  # the reply itself is still recorded; a bad chip mapping must not 400 it
    return answered


__all__ = ["MESSAGE_PAGE", "CORRELATION_WINDOW_DAYS", "PROMPT_RULES",
          "taxonomy", "add", "list_events", "delete", "restore", "edit",
          "events_for_system", "correlate", "messages", "reply_message"]
