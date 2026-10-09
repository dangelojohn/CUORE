"""Turns the raw workup dossier into the redesigned dossier page's contract.

MECHANIC_UX_REVIEW.md's R1/R4/R5/R6/R7/R8/R9 all boil down to the same
complaint: the knowledge in ``mes.workup`` is already senior-technician-grade
(family findings, chronic/returned classification, TSB cross-reference) but
the page made the mechanic excavate it from prose and raw dicts. Nothing here
re-derives that knowledge -- it only reshapes what ``mes_bridge.workup``
already returns (plus what the live link has observed) into the verdict,
checklists, code table, freeze-frame flags, deduplicated bulletins and
runnable blind-spot actions the template needs, so there is exactly one
place that decides what a status chip or a checklist step means.

``build_view`` is the only entry point. Everything else is a private helper.

Like every other file under ``cuore/services``, this is a *_bridge.py module,
so it is allowed to import ``mes_bridge`` (never the ``mes`` package itself --
nothing here needs to; the workup dict already carries what ``mes`` computed)
and the small read-only ``cuore.live`` surfaces (``store`` for live
observations, ``checklists`` for shop-ticked steps).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from . import cache, mes_bridge
from .errors import BridgeError
from ..live import checklists as checklist_store
from ..live import config as live_config
from ..live import store as live_store

#: EVAP monitor runs at 15-85% fuel; cited wherever a freeze frame needs
#: flagging. Matches the window ``mes`` itself states in verdict/fault-tree
#: text -- not re-derived, just applied to one more surface.
_EVAP_FUEL_WINDOW = (15.0, 85.0)
_EVAP_CODES = {"P0440", "P0441", "P0455", "P0456", "P1CEA"}

_SYSTEM_BY_LETTER = {"P": "engine", "C": "chassis", "B": "body", "U": "network"}

_STATUS_LABEL = {"ACTIVE": "Active", "CLEARED_UNVERIFIED": "Cleared, unverified",
                "STALE": "Stale"}

#: Freeze-frame parameters worth a mechanic's first glance, in the order
#: they should appear. Everything else still rides along in ``all``.
_KEY_FRAME_PARAMS = ["Fuel level", "Engine temperature", "Odometer",
                     "Vehicle speed", "Engine speed", "Air temperature"]

#: One checklist per family this corpus's fault trees and TSBs recognise
#: today. Transcribed once, here, from the family finding's own "reading"
#: text and the EVAP/network fault trees -- see MECHANIC_UX_REVIEW.md R4.
#: Keeping this as a table (not free-text parsing of ``reading``) is what
#: makes checklist step ids stable across a wording change in ``mes``.
FAMILY_STEPS: dict[str, list[dict[str, Any]]] = {
    "EVAP": [
        {"id": "evap-1", "text": "Inspect the recirculation-line quick-connect",
         "ref": "S2125000002"},
        {"id": "evap-2", "text": "Run the purge/vent valve KOEO actuator test",
         "ref": None},
        {"id": "evap-3", "text": "Check hose routing", "ref": "9100325"},
        {"id": "evap-4", "text": "Inspect the canister/ESIM", "ref": "9100471"},
        {"id": "evap-5", "text": "Run a smoke test to localise the leak",
         "ref": None},
        {"id": "evap-6", "text": "Verify with SLVT or Mode $06",
         "ref": "18-048-23"},
    ],
    "network": [
        {"id": "network-1", "text": "Check the supply: F82 fuse and BCM feeds",
         "ref": "S1808000005"},
        {"id": "network-2",
         "text": "Inspect connectors/grounds: XY201, G003A/B",
         "ref": "S2008000032"},
        {"id": "network-3",
         "text": "Inspect connector terminals for spread/backed-out pins",
         "ref": "S1708000262"},
    ],
}

_FAMILY_TITLES = {
    "EVAP": "EVAP: one system fault",
    "network": "Network: one power/bus event, not {n} separate faults",
}

#: EVAP was the first job this cuore app diagnosed, so it (and the network
#: cascade) got a hand-curated ``FAMILY_STEPS`` table above. Every other
#: family this car's history can throw -- misfire, fuel trim, cooling, body,
#: chassis, ADAS, or anything else SAE's DTC-prefix convention covers --
#: still needs an open-work card; :func:`_build_open_work` builds those
#: generically, grouping codes by the family below and pulling steps live
#: from ``mes_bridge.fault_tree`` (``mes.faulttree.tree_for`` -- the
#: hand-written tree when one exists, else a sourced generated one) instead
#: of a second hand-maintained step table. Patterns are checked in order;
#: the first match wins. Generalised from the same SAE J2012 prefix-range
#: convention ``mes.systems._sae_fallback`` already uses.
_GENERIC_FAMILY_RULES: tuple[tuple[re.Pattern, str, str], ...] = (
    (re.compile(r"^P030[0-9]$"), "misfire", "Misfire"),
    (re.compile(r"^P017[0-5]$"), "fuel_trim", "Fuel trim"),
    (re.compile(r"^P01(0[0-9]|1[0-9]|2[0-9])$"), "cooling",
     "Cooling / intake sensors"),
    (re.compile(r"^P0[67][0-9]{2}$"), "engine_management", "Engine management"),
    (re.compile(r"^P0[89][0-9]{2}$"), "transmission_driveline",
     "Transmission / driveline"),
    (re.compile(r"^C(141B|141C)$"), "adas", "ADAS (camera/radar)"),
    (re.compile(r"^C[0-9A-F]{4}$"), "chassis", "Chassis (brakes/steering/suspension)"),
    (re.compile(r"^B[0-9A-F]{4}$"), "body", "Body / comfort"),
    (re.compile(r"^U[0-9A-F]{4}$"), "network", "Network / communication"),
    (re.compile(r"^P[0-9A-F]{4}$"), "powertrain_other", "Powertrain (other)"),
)


def _generic_family_for(base: str) -> tuple[str, str] | None:
    """``(family_key, family_label)`` for a code with no hand-curated
    ``FAMILY_STEPS`` entry, or ``None`` for something that isn't a
    recognisable P/B/C/U code at all."""
    for pattern, key, label in _GENERIC_FAMILY_RULES:
        if pattern.match(base):
            return key, label
    return None


def _history_codes(dossier: dict[str, Any]) -> set[str]:
    """Every base code present anywhere in this car's own history -- the
    same ``chronic``/``returned_after_clear``/``seen_once`` buckets the code
    table reads -- so a generic open-work card can be offered for a family
    the TSB family-finding rule above doesn't recognise."""
    history = dossier.get("history") or {}
    out: set[str] = set()
    for bucket in ("chronic", "returned_after_clear", "seen_once"):
        for rec in history.get(bucket, []):
            b = _base(rec.get("dtc", ""))
            if b:
                out.add(b)
    return out


def _generic_tree_steps(code: str, vin: str) -> list[dict[str, Any]]:
    """The first tree's steps for one code, via ``mes_bridge.fault_tree`` --
    the hand-written tree when ``mes.faulttree.tree_for`` has one, else its
    sourced generated tree. Never raises: a lookup failure just means no
    generic card gets built for that code."""
    try:
        result = mes_bridge.fault_tree(code, vin=vin)
    except Exception:
        return []
    trees = result.get("trees") or []
    return trees[0].get("steps") or [] if trees else []


# --- small shared helpers --------------------------------------------------


def _base(code: str) -> str:
    """"P0440-00" -> "P0440". Same rule as ``mes.knowledge.base_code``,
    reimplemented here rather than imported so this module never touches the
    ``mes`` package directly."""
    code = (code or "").strip().upper()
    return code.split("-", 1)[0] if "-" in code else code


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", (text or "").strip()).strip("-")


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _short_date(ts: str | None, with_time: bool = False) -> str | None:
    dt = _parse_ts(ts)
    if dt is None:
        return None
    fmt = "%d %b %H:%M" if with_time else "%d %b"
    if dt.year != datetime.now().year:
        fmt += " '%y"
    return dt.strftime(fmt)


def _num(display: Any) -> float | None:
    """Pull the leading number out of a display string like "93.73 %"."""
    if display is None:
        return None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(display))
    return float(m.group(1)) if m else None


def _state_fingerprint() -> float:
    """Newest mtime across this app's mutable state files.

    Checklists, jobs, shop visits, symptoms, notes, dealer results, tool
    usage, live observations and the rest are all flat files sitting
    directly under one shared directory -- every ``mes.*``/``cuore.live``
    state module mirrors ``cuore.live.config.state_dir()`` (see each
    module's own ``state_dir()`` docstring). Folded into
    :func:`build_view`'s cache key so a ticked checklist step or a freshly
    logged symptom invalidates the cached open-work/freeze-frame/attempted
    build the same way a new MES log invalidates ``mes_bridge.newest_mtime``
    -- no separate invalidation hook, same reasoning as ``cuore.services.cache``
    itself.
    """
    try:
        d = live_config.state_dir()
        return max((p.stat().st_mtime for p in d.iterdir() if p.is_file()), default=0.0)
    except OSError:
        return 0.0


def live_available(live_status: dict[str, Any] | None) -> bool:
    """Is the adapter reachable right now -- a port configured, and neither
    MultiEcuScan nor another process holding it.

    Same read ``base.html``'s live strip and ``/live`` already make of
    ``live_ops.status()``: ``mes_state == "connected"`` means MES has the
    port, and a ``lock_holder`` other than this process means something else
    does. Used both to grey out the dossier's own action buttons and by
    ``/v/{vin}/verify`` to decide whether it is safe to actually read.
    """
    if not live_status or live_status.get("error"):
        return False
    if not live_status.get("port"):
        return False
    if live_status.get("mes_state") == "connected":
        return False
    holder = live_status.get("lock_holder")
    if holder and holder != "cuore":
        return False
    return True


# --- the last clear ---------------------------------------------------------


def _clear_info(dossier: dict[str, Any]
                ) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """(cleared_at full timestamp, cleared_by file, the clear_assessment dict).

    ``current_picture.clear_assessment`` comes from two different shapes in
    ``mes.workup``: a scan-based clear carries its own ``cleared_at``/
    ``source``; a clear inside the anchored FES session itself carries
    neither, because *that session* is the clear -- so its timestamp/file are
    read off ``latest_session`` instead.
    """
    cp = dossier.get("current_picture") or {}
    ca = cp.get("clear_assessment")
    if not ca:
        return None, None, None
    cleared_at = ca.get("cleared_at")
    cleared_by = ca.get("source")
    if not cleared_at:
        latest = cp.get("latest_session") or {}
        cleared_at = latest.get("timestamp")
        cleared_by = latest.get("file")
    return cleared_at, cleared_by, ca


# --- readiness, read from the car -------------------------------------------


def _latest_readiness(vin: str, after: str | None) -> dict[str, Any] | None:
    """The newest readiness observation from the car itself, after ``after``.

    A read taken before the clear says nothing about the car now -- the same
    reasoning ``mes.verdict._last_clear`` already applies to live DTC reads.
    """
    try:
        obs = live_store.recent_observations(200, vin=vin, kind="readiness")
    except Exception:  # noqa: BLE001 -- a broken store must never break the verdict
        return None
    best = None
    for o in obs:
        if not live_store.is_from_car(o):
            continue
        at = o.get("at") or ""
        if after and at <= after:
            continue
        if best is None or at > (best.get("at") or ""):
            best = o
    return best


def readiness_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a live ``ops.obd_readiness()`` read for ``/v/{vin}/verify``.

    ``verify.html`` destructures ``result.at`` / ``result.evap_monitor`` /
    ``result.all_complete`` / ``result.monitors`` explicitly (never the raw
    dict) -- this is the one place that produces that flat shape from the
    nested ``since_clear``/``monitors`` payload ``ops.obd_readiness``
    returns, so the page and the verdict's own ``readiness`` sub-object
    agree on what "the EVAP monitor is complete" means.
    """
    since = raw.get("since_clear") or {}
    monitors = since.get("monitors") or []
    evap = next((m for m in monitors if m.get("monitor") == "Evaporative system"), None)
    return {
        "at": datetime.now().isoformat(timespec="seconds"),
        "evap_monitor": bool(evap and evap.get("complete")),
        "all_complete": bool(since.get("all_complete")),
        "monitors": [{"name": m.get("monitor"), "complete": bool(m.get("complete"))}
                     for m in monitors],
    }


def fuel_status(freeze_frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Current fuel % and EVAP-window state, for the bench's live fuel gate.

    Reads the same EVAP freeze-frame "Fuel level" reading the verdict's own
    ``next_action`` sentence already quotes (:func:`_fuel_out_of_window`
    scans the same frames but only returns a value when the reading is
    flagged out-of-window) -- never a second, disagreeing number. ``level``
    is ``None`` (UNKNOWN) when no EVAP freeze frame carries a fuel reading;
    nothing here is ever invented.
    """
    lo, hi = _EVAP_FUEL_WINDOW
    for ff in freeze_frames:
        for p in ff.get("key") or []:
            if p.get("name") != "Fuel level":
                continue
            level = _num(p.get("value"))
            if level is None:
                continue
            in_window = lo <= level <= hi
            direction = None if in_window else ("below" if level < lo else "above")
            return {"level": level, "window": [lo, hi], "in_window": in_window,
                    "direction": direction}
    return {"level": None, "window": [lo, hi], "in_window": None, "direction": None}


def readiness_panel(vin: str, dossier: dict[str, Any]) -> dict[str, Any]:
    """The bench's monitor-readiness panel: the latest from-car readiness
    observation since the last clear, or an honest "no readiness read yet".

    Reuses :func:`_latest_readiness` -- the same observation the verdict
    itself reads -- so the bench panel and the verdict can never disagree
    about what the car's own monitors last said.
    """
    cleared_at, _cleared_by, _ca = _clear_info(dossier)
    obs = _latest_readiness(vin, cleared_at)
    if obs is None:
        return {"at": None, "monitors": [], "all_complete": None,
                "note": "no readiness read yet"}
    data = obs.get("data") or {}
    since = data.get("since_clear") or {}
    monitors = since.get("monitors") or []
    return {
        "at": obs.get("at"),
        "monitors": [{"name": m.get("monitor"), "complete": bool(m.get("complete"))}
                     for m in monitors],
        "all_complete": bool(since.get("all_complete")) if monitors else None,
        "note": None if monitors else "readiness read, but no monitor list decoded",
    }


def _evap_from_readiness(obs: dict[str, Any] | None) -> dict[str, Any] | None:
    if obs is None:
        return None
    data = obs.get("data") or {}
    since = data.get("since_clear") or {}
    monitors = since.get("monitors") or []
    evap = next((m for m in monitors if m.get("monitor") == "Evaporative system"), None)
    if not monitors:
        state = None
    elif evap is None:
        state = "not_supported"
    else:
        state = "complete" if evap.get("complete") else "incomplete"
    return {"at": obs.get("at"), "evap_monitor": state,
            "all_complete": bool(since.get("all_complete"))}


# --- verdict -----------------------------------------------------------------


def _verdict_actions(vin: str, enabled: bool) -> list[dict[str, Any]]:
    hint = "" if enabled else "connect the car (ELM327 on COM3)"
    return [
        {"label": "Verify repair", "kind": "readiness", "href": f"/v/{vin}/verify",
         "enabled": enabled, "hint": hint},
        {"label": "EVAP fault tree", "kind": "link", "href": f"/v/{vin}/tree",
         "enabled": True, "hint": ""},
        {"label": "Evidence gate", "kind": "link", "href": f"/v/{vin}/gate",
         "enabled": True, "hint": ""},
    ]


def _verdict_summary(state: str, open_work: list[dict[str, Any]],
                     cleared_at: str | None, dossier: dict[str, Any]) -> str:
    if open_work:
        codes = open_work[0]["codes"][:3]
    else:
        chronic = (dossier.get("history") or {}).get("chronic") or []
        codes = sorted({_base(r.get("dtc", "")) for r in chronic})[:3]
    code_str = "/".join(codes) if codes else "the logged codes"
    cleared_short = _short_date(cleared_at) if cleared_at else None

    if state == "NO_DATA":
        return "No MES logs on file for this vehicle."
    if state == "ACTIVE_FAULTS":
        return f"{code_str} active now -- not cleared, not resolved."
    if state == "VERIFIED_CLEAN":
        return f"{code_str} cleared {cleared_short}; EVAP monitor ran clean. Repair verified."
    return f"{code_str} cleared {cleared_short}; monitors have not re-run. Not proof of repair."


def _build_verdict(vin: str, dossier: dict[str, Any], live_status: dict[str, Any] | None,
                   open_work: list[dict[str, Any]]) -> dict[str, Any]:
    identity = dossier.get("identity") or {}
    enabled = live_available(live_status)

    if not identity.get("log_count"):
        return {"state": "NO_DATA", "label": "No data",
                "summary": "No MES logs on file for this vehicle.",
                "basis": ["no logs matched this VIN"],
                "cleared_at": None, "cleared_by": None, "readiness": None,
                "actions": _verdict_actions(vin, enabled)}

    cp = dossier.get("current_picture") or {}
    history = dossier.get("history") or {}
    cleared_at, cleared_by, clear_assessment = _clear_info(dossier)

    basis: list[str] = []
    active = False

    latest_session = cp.get("latest_session") or {}
    if (cleared_at and latest_session.get("timestamp")
            and latest_session.get("timestamp") > cleared_at
            and latest_session.get("dtcs")):
        active = True
        basis.append(f"newest session ({latest_session['timestamp']}) holds DTCs "
                     f"after the {cleared_at} clear")

    latest_scan = cp.get("latest_scan") or {}
    if (cleared_at and latest_scan.get("timestamp")
            and latest_scan.get("timestamp") > cleared_at
            and latest_scan.get("modules_with_faults")):
        active = True
        basis.append(f"newest scan ({latest_scan['timestamp']}) holds DTCs "
                     f"after the {cleared_at} clear")

    returned_in_session = (clear_assessment or {}).get("codes_returned_in_session") or []
    if returned_in_session:
        active = True
        basis.append("codes returned in the clearing session: "
                     + ", ".join(returned_in_session))

    uncleared = (clear_assessment or {}).get("codes_that_would_not_clear") or []
    if uncleared:
        active = True
        basis.append("codes would not clear: " + ", ".join(uncleared))

    if history.get("returned_after_clear"):
        active = True
        basis.append("returned after a clear: " + ", ".join(
            sorted(_base(r.get("dtc", "")) for r in history["returned_after_clear"])))

    readiness = None
    if cleared_at:
        readiness = _evap_from_readiness(_latest_readiness(vin, cleared_at))

    if active:
        state, label = "ACTIVE_FAULTS", "Active faults"
    elif cleared_at is None:
        if history.get("chronic"):
            state, label = "ACTIVE_FAULTS", "Active faults"
            basis.append("chronic codes on file and no clear recorded")
        else:
            state, label = "NO_DATA", "No data"
            basis.append("no open codes and no clear on file")
    elif readiness and readiness.get("evap_monitor") == "complete":
        state, label = "VERIFIED_CLEAN", "Verified clean"
        basis.append(f"EVAP monitor complete on a live read at {readiness['at']}, "
                     f"no code has returned since the {cleared_at} clear")
    else:
        state, label = "UNVERIFIED_REPAIR", "Unverified repair"
        basis.append(f"last clear {cleared_at} ({cleared_by or 'unknown source'}); "
                     f"no code has returned")
        if readiness is None:
            basis.append("no readiness read from the car since the clear")
        else:
            basis.append(f"readiness read at {readiness['at']} -- EVAP monitor "
                         f"{readiness.get('evap_monitor') or 'unknown'}")

    return {
        "state": state, "label": label,
        "summary": _verdict_summary(state, open_work, cleared_at, dossier),
        "basis": basis,
        "cleared_at": cleared_at.split(" ")[0] if cleared_at else None,
        "cleared_by": cleared_by,
        "readiness": readiness,
        "actions": _verdict_actions(vin, enabled),
    }


# --- verdict.next_action -- the one-sentence "what do I do right now" -------
#
# Added for the bench page (cuore/services/bench_bridge.py): a mechanic
# landing on a car should not have to read the verdict's basis list and the
# open-work cards to work out what to actually do next. Nothing here is a
# new judgement -- it just combines the verdict state already computed above
# with the same fuel-out-of-window flag :func:`_build_freeze_frames` already
# derives and the same open-work steps :func:`_build_open_work` already
# orders, into the one sentence (plus a short ``blocker`` label and the
# ``next_step_id`` it points at) the bench page's headline needs.


def _first_unchecked_step(open_work: list[dict[str, Any]]
                          ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The first not-yet-done step across every open-work card, in the same
    order the cards themselves are already in (curated families first, then
    the generic ones) -- ``(card, step)``, or ``(None, None)`` if every step
    on file is ticked."""
    for card in open_work:
        for step in card.get("steps") or []:
            if not step.get("done"):
                return card, step
    return None, None


def _step_bit(step: dict[str, Any] | None) -> str | None:
    """"<step text> (<bulletin>)" -- the fragment both the ACTIVE_FAULTS and
    fuel-blocked UNVERIFIED_REPAIR sentences below quote verbatim."""
    if step is None:
        return None
    bulletin = step.get("ref") or "no bulletin on file"
    return f"{step['text']} ({bulletin})"


def _fuel_out_of_window(freeze_frames: list[dict[str, Any]]
                        ) -> tuple[float, str, float] | None:
    """``(level, "above"/"below", threshold)`` for the first EVAP freeze-frame
    fuel reading outside :data:`_EVAP_FUEL_WINDOW` -- the same flag
    :func:`_build_freeze_frames` already set on that reading -- or ``None``
    when no freeze frame carries that flag."""
    lo, hi = _EVAP_FUEL_WINDOW
    for ff in freeze_frames:
        for p in ff.get("key") or []:
            if p.get("name") != "Fuel level" or not p.get("flag"):
                continue
            level = _num(p.get("value"))
            if level is None:
                continue
            return level, ("below" if level < lo else "above"), (lo if level < lo else hi)
    return None


def _verdict_next_action(verdict: dict[str, Any], open_work: list[dict[str, Any]],
                         freeze_frames: list[dict[str, Any]]
                         ) -> tuple[str, str, str | None]:
    """``(next_action sentence, blocker label, next_step_id)`` for one
    verdict. Never raises -- a missing open-work step or freeze frame just
    means a shorter sentence, not a broken one."""
    state = verdict.get("state")
    _card, step = _first_unchecked_step(open_work)
    step_id = step.get("id") if step else None
    bit = _step_bit(step)

    if state == "UNVERIFIED_REPAIR":
        fuel = _fuel_out_of_window(freeze_frames)
        if fuel is not None:
            level, direction, threshold = fuel
            sentence = (f"Cannot verify yet: the EVAP monitor will not run {direction} "
                       f"{threshold:g} % fuel (set at {level:g} %). Burn fuel into the "
                       f"{_EVAP_FUEL_WINDOW[0]:g}-{_EVAP_FUEL_WINDOW[1]:g} % window, then "
                       f"complete a drive cycle.")
            if bit:
                sentence += f" Meanwhile: {bit}."
            return sentence, "fuel out of window", step_id
        sentence = ("Cannot verify yet: no readiness read since the clear. Read "
                    "readiness once the drive cycle completes.")
        if bit:
            sentence += f" Meanwhile: {bit}."
        return sentence, "awaiting drive cycle", step_id

    if state == "ACTIVE_FAULTS":
        if bit:
            return f"Start with {bit}.", "active faults", step_id
        return "Active faults on file -- open the codes to begin.", "active faults", None

    if state == "VERIFIED_CLEAN":
        readiness = verdict.get("readiness") or {}
        date = _short_date(readiness.get("at")) or verdict.get("cleared_at") or "the last read"
        return f"Verified by readiness read on {date}: release.", "none", None

    return "Read the car.", "no data", None


# --- open work (family findings as a checklist) -----------------------------


def _family_refs(codes: list[str], per_code: dict[str, Any],
                 reading: str) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for code in codes:
        for b in per_code.get(code, []):
            num = b.get("bulletin")
            if num and num not in seen:
                seen[num] = {"label": num, "href": f"#tsb-{_slug(num)}"}
    for doc in re.findall(r"docs/\S+?\.md", reading or ""):
        if doc not in seen:
            seen[doc] = {"label": doc, "href": None}
    return list(seen.values())


def _build_open_work(vin: str, dossier: dict[str, Any],
                     checklist: dict[str, Any]) -> list[dict[str, Any]]:
    tsb = dossier.get("tsb_matches") or {}
    findings = tsb.get("family_findings") or []
    per_code = tsb.get("per_code") or {}
    cards = []
    covered_codes: set[str] = set()
    for f in findings:
        family = f.get("family") or ""
        steps_def = FAMILY_STEPS.get(family)
        if not steps_def:
            continue  # no checklist table for this family yet
        codes = [c.upper() for c in (f.get("codes") or [])]
        covered_codes.update(codes)
        steps = []
        done = 0
        for s in steps_def:
            st = checklist.get(s["id"]) or {}
            is_done = bool(st.get("done"))
            done += int(is_done)
            steps.append({
                "id": s["id"], "text": s["text"], "ref": s["ref"],
                "ref_href": f"#tsb-{_slug(s['ref'])}" if s["ref"] else None,
                "done": is_done, "done_at": st.get("done_at"),
                "done_by": st.get("done_by"),
            })
        title = _FAMILY_TITLES.get(family, f"{family}: one system fault")
        if "{n}" in title:
            title = title.format(n=len(codes))
        cards.append({
            "family": family, "title": title, "codes": codes, "steps": steps,
            "refs": _family_refs(codes, per_code, f.get("reading", "")),
            "progress": {"done": done, "total": len(steps_def)},
        })

    # Every other family this car's own history shows, grouped by the
    # generic SAE-range classification above, with steps pulled live from
    # mes.faulttree via mes_bridge.fault_tree -- so EVAP keeps being the
    # richest, hand-curated example, but a misfire, fuel-trim, cooling,
    # body, chassis or ADAS code (or any other family) still gets a
    # sourced, actionable card instead of nothing.
    remaining = sorted(_history_codes(dossier) - covered_codes)
    groups: dict[str, list[str]] = {}
    labels: dict[str, str] = {}
    for code in remaining:
        fam = _generic_family_for(code)
        if fam is None:
            continue
        key, label = fam
        groups.setdefault(key, []).append(code)
        labels[key] = label
    for family_key in sorted(groups):
        codes = sorted(set(groups[family_key]))
        tree_steps = _generic_tree_steps(codes[0], vin)[:6]
        if not tree_steps:
            continue
        steps = []
        done = 0
        for i, s in enumerate(tree_steps):
            step_id = f"{family_key}-{i + 1}"
            st = checklist.get(step_id) or {}
            is_done = bool(st.get("done"))
            done += int(is_done)
            text = s.get("title") or s.get("test") or "Step"
            if s.get("test") and s.get("test") != text:
                text = f"{text}: {s['test']}"
            steps.append({
                "id": step_id, "text": text, "ref": s.get("source"),
                "ref_href": None,
                "done": is_done, "done_at": st.get("done_at"),
                "done_by": st.get("done_by"),
            })
        label = labels.get(family_key, family_key)
        title = (f"{label}: one open issue" if len(codes) == 1
                 else f"{label}: {len(codes)} codes, one system")
        cards.append({
            "family": family_key, "title": title, "codes": codes,
            "steps": steps, "refs": [],
            "progress": {"done": done, "total": len(steps)},
            "generic": True,
        })
    return cards


def _family_map(dossier: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in (dossier.get("tsb_matches") or {}).get("family_findings", []):
        for c in f.get("codes", []):
            out[c.upper()] = f.get("family")
    return out


# --- the code table -----------------------------------------------------------


def _code_status(base: str, last_seen: str | None, cleared_at: str | None,
                 codes_cleared: set[str], codes_returned: set[str],
                 codes_uncleared: set[str], last_findings: set[str],
                 last_findings_ts: str | None, recent_ts: list[str]) -> str:
    if base in codes_returned or base in codes_uncleared:
        return "ACTIVE"
    if cleared_at and last_seen and last_seen > cleared_at:
        return "ACTIVE"
    if base in last_findings and not (cleared_at and last_findings_ts
                                      and cleared_at >= last_findings_ts):
        return "ACTIVE"
    if cleared_at and base in codes_cleared and (not last_seen or last_seen <= cleared_at):
        return "CLEARED_UNVERIFIED"
    if cleared_at is None and last_seen and last_seen in recent_ts[:3]:
        return "ACTIVE"
    return "STALE"


def _code_rows(vin: str, dossier: dict[str, Any], cleared_at: str | None,
              clear_assessment: dict[str, Any] | None, recent_ts: list[str],
              family_map: dict[str, str]
              ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    history = dossier.get("history") or {}
    cp = dossier.get("current_picture") or {}
    last_findings_session = cp.get("last_session_with_findings") or {}
    last_findings = {_base(d.get("code") or d.get("dtc") or "")
                     for d in last_findings_session.get("dtcs", [])}
    last_findings_ts = last_findings_session.get("timestamp")

    codes_cleared = {_base(c) for c in (clear_assessment or {}).get("codes_cleared", [])}
    codes_returned = {_base(c) for c in
                      (clear_assessment or {}).get("codes_returned_in_session", [])}
    codes_uncleared = {_base(c) for c in
                       (clear_assessment or {}).get("codes_that_would_not_clear", [])}

    rows: list[dict[str, Any]] = []
    for bucket in ("chronic", "returned_after_clear", "seen_once"):
        for rec in history.get(bucket, []):
            full = rec.get("dtc", "")
            base = _base(full)
            last_seen = rec.get("last_seen")
            status = _code_status(base, last_seen, cleared_at, codes_cleared,
                                  codes_returned, codes_uncleared, last_findings,
                                  last_findings_ts, recent_ts)
            distance = rec.get("distance_span_km")
            rows.append({
                "code": base, "dtc": full,
                "description": (rec.get("descriptions") or [""])[0],
                "system": _SYSTEM_BY_LETTER.get(base[:1], base[:1] if base else None),
                "bucket": bucket,
                "status": status, "status_label": _STATUS_LABEL[status],
                "sessions": rec.get("sessions"),
                "last_seen_short": _short_date(last_seen),
                "last_seen": last_seen, "first_seen": rec.get("first_seen"),
                "distance_km": round(distance) if distance is not None else None,
                "href": f"/v/{vin}/code/{base}",
                "family": family_map.get(base),
            })

    counts = {"chronic": 0, "seen_once": 0, "returned_after_clear": 0,
             "active": 0, "stale": 0}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
        if r["status"] == "ACTIVE":
            counts["active"] += 1
        elif r["status"] == "STALE":
            counts["stale"] += 1
    return rows, counts


# --- already attempted -------------------------------------------------------


def _build_attempted(vin: str) -> list[dict[str, Any]]:
    try:
        data = mes_bridge.actuator_history(vin=vin)
    except BridgeError:
        return []
    note = data.get("note")
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for r in data.get("runs", []):
        key = (r.get("operation"), r.get("outcome"))
        g = groups.setdefault(key, {"operation": r.get("operation"),
                                    "kind": r.get("kind"), "outcome": r.get("outcome"),
                                    "reason": None, "rows": []})
        g["rows"].append(r)
        if r.get("reason") and not g["reason"]:
            g["reason"] = r.get("reason")

    out = []
    for g in groups.values():
        times = sorted(r.get("timestamp") for r in g["rows"] if r.get("timestamp"))
        reason = g["reason"]
        footnote = note if (reason and note and "engine running" in reason.lower()) else None
        out.append({
            "operation": g["operation"], "kind": g["kind"], "outcome": g["outcome"],
            "count": len(g["rows"]),
            "first_short": _short_date(times[0]) if times else None,
            "last_short": _short_date(times[-1]) if times else None,
            "reason": reason, "reason_chip": reason, "footnote": footnote,
            "rows": g["rows"],
        })
    out.sort(key=lambda g: (g["outcome"] != "FAILED TO EXECUTE", g["operation"] or ""))
    return out


# --- freeze frames -------------------------------------------------------------


def _build_freeze_frames(vin: str, dossier: dict[str, Any]) -> list[dict[str, Any]]:
    cp = dossier.get("current_picture") or {}
    target_ts = ((cp.get("last_session_with_findings") or {}).get("timestamp")
                or (cp.get("latest_session") or {}).get("timestamp"))
    if not target_ts:
        return []
    try:
        data = mes_bridge.freeze_frames(vin=vin)
    except BridgeError:
        return []

    odo_last = (dossier.get("identity") or {}).get("odometer_last_km")
    out = []
    for f in data.get("frames", []):
        if f.get("timestamp") != target_ts:
            continue
        ff = f.get("freeze_frame") or {}
        base = _base(f.get("dtc", ""))
        key = []
        for name in _KEY_FRAME_PARAMS:
            if name not in ff:
                continue
            value = ff[name]
            flag = None
            if name == "Fuel level" and base in _EVAP_CODES:
                level = _num(value)
                lo, hi = _EVAP_FUEL_WINDOW
                if level is not None and (level < lo or level > hi):
                    bound = f"below {lo:g} %" if level < lo else f"above {hi:g} %"
                    flag = f"{bound}: EVAP monitor could not run"
            key.append({"name": name, "value": value, "flag": flag})
        odo_frame = _num(ff.get("Odometer"))
        set_km_ago = (round(odo_last - odo_frame)
                     if odo_last is not None and odo_frame is not None else None)
        out.append({
            "code": f.get("dtc"), "key": key, "set_km_ago": set_km_ago,
            "all": [{"name": n, "value": v} for n, v in ff.items()],
        })
    return out


# --- blind spots as actions ----------------------------------------------------


def _blind_spot_action(vin: str, closes_it: str, enabled: bool) -> dict[str, Any]:
    low = (closes_it or "").lower()
    hint = "" if enabled else "connect the car (ELM327 on COM3)"
    if "read_readiness" in low:
        return {"label": "Read readiness", "kind": "readiness",
                "href": f"/v/{vin}/verify", "enabled": enabled, "hint": hint}
    if "read_permanent_dtcs" in low:
        return {"label": "Read permanent DTCs", "kind": "permanent", "href": None,
                "enabled": enabled, "hint": hint}
    if "mode06" in low or "send_raw" in low:
        return {"label": "Read Mode $06", "kind": "mode06", "href": None,
                "enabled": enabled, "hint": hint}
    if "already closed" in low:
        return {"label": "Answered", "kind": "link", "href": f"/v/{vin}/dealer",
                "enabled": True, "hint": ""}
    if "witech" in low or "dealer" in low:
        return {"label": "Dealer / wiTECH", "kind": "dealer", "href": f"/v/{vin}/dealer",
                "enabled": True, "hint": ""}
    return {"label": "Manual check", "kind": "manual", "href": None,
            "enabled": True, "hint": ""}


def _build_blind_spots(vin: str, dossier: dict[str, Any],
                       live_status: dict[str, Any] | None) -> list[dict[str, Any]]:
    enabled = live_available(live_status)
    out = []
    for bs in dossier.get("blind_spots", []):
        out.append({
            "question": bs.get("question", ""),
            "why": bs.get("why_unknown", ""),
            "action": _blind_spot_action(vin, bs.get("closes_it", ""), enabled),
        })
    return out


# --- bulletins, deduplicated ---------------------------------------------------


def _supersedes(action: str) -> str | None:
    m = re.search(r"[Ss]upersed(?:es|ed)\s+([A-Za-z0-9.\-]+)", action or "")
    return m.group(1).rstrip(".") if m else None


def _build_bulletins(dossier: dict[str, Any],
                     open_work: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tsb = dossier.get("tsb_matches") or {}
    per_code = tsb.get("per_code") or {}
    relevant = {c for card in open_work for c in card["codes"]}

    by_num: dict[str, dict[str, Any]] = {}
    for code, matches in per_code.items():
        for b in matches:
            num = b.get("bulletin")
            if not num:
                continue
            entry = by_num.setdefault(num, {
                "id": num, "anchor": f"tsb-{_slug(num)}", "title": b.get("title"),
                "action": b.get("action"), "caution": b.get("caution"),
                "codes": set(), "superseded": _supersedes(b.get("action", "")),
                "source": b.get("source"), "relevance": 0,
            })
            entry["codes"].update(b.get("dtcs") or [code])
            if code.upper() in relevant:
                entry["relevance"] += 1

    out = []
    for entry in by_num.values():
        entry["codes"] = sorted(entry["codes"])
        out.append(entry)
    out.sort(key=lambda e: (-e["relevance"], e["id"]))
    return out


# --- latest session/scan -------------------------------------------------------


def _build_latest(dossier: dict[str, Any]) -> dict[str, Any]:
    cp = dossier.get("current_picture") or {}
    ls = cp.get("latest_session") or {}
    sc = cp.get("latest_scan") or {}
    return {
        "session_short": _short_date(ls.get("timestamp"), with_time=True),
        "session_file": ls.get("file"), "ecu": ls.get("ecu"),
        "scan_short": (_short_date(sc.get("timestamp"), with_time=True)
                       if sc.get("timestamp") else None),
        "scan_file": sc.get("file"),
    }


# --- checklist step ids, for the API's validation ----------------------------


def checklist_step_ids(vin: str, dossier: dict[str, Any]) -> set[str]:
    """Every checklist step id this vehicle's open-work cards expose.

    Used by the checklist API to reject a step id that is not actually on
    this car's dossier -- a step id is only meaningful in the context of the
    family finding it belongs to.

    This used to call ``_build_open_work(vin, dossier, {})`` fresh every
    time -- a second, uncached re-evaluation of the fault tree per code
    (``_generic_tree_steps`` -> ``mes_bridge.fault_tree`` -> real FES
    parsing) on top of the one ``build_view`` already pays for and caches.
    The checklist dict passed in only ever flips each step's own
    ``done``/``done_at``/``done_by``, never which step ids exist (see
    ``_build_open_work``'s body), so this is a pure function of
    ``(vin, dossier)`` and can share ``build_view``'s own
    ``dossier_view_core`` cache entry instead of building a second,
    checklist-blind copy of the same open-work list -- correct because the
    cache key (vin, newest MES-log mtime, newest state-file mtime) is the
    same staleness criteria either caller needs: a new log or any state
    file change invalidates it, same as ``build_view`` itself. Called from
    request paths that never built that core (e.g. checklist POST
    handlers), so it still has to build it the first time; callers that
    already called ``build_view`` this request (or the last one, if nothing
    changed) get a cache hit instead of a second fault-tree pass.
    """
    core = cache.get_or_build(
        ("dossier_view_core", vin, mes_bridge.newest_mtime(vin), _state_fingerprint()),
        lambda: _build_view_core(vin, dossier),
    )
    return {s["id"] for card in core["open_work"] for s in card["steps"]}


# --- the one entry point -----------------------------------------------------


def _build_view_core(vin: str, dossier: dict[str, Any]) -> dict[str, Any]:
    """Everything :func:`build_view` needs except the verdict and blind
    spots, which also read ``live_status`` and are cheap enough (no file
    I/O beyond what ``dossier`` already carries) to compute fresh on every
    call. Split out purely so it can be memoised -- see ``build_view``.
    """
    checklist = checklist_store.get(vin)
    open_work = _build_open_work(vin, dossier, checklist)

    family_map = _family_map(dossier)
    try:
        recent_ts = [e.get("timestamp") for e in
                    mes_bridge.list_logs(vin=vin, limit=3)["logs"]]
    except BridgeError:
        recent_ts = []
    cleared_at, _cleared_by, clear_assessment = _clear_info(dossier)
    codes, code_counts = _code_rows(vin, dossier, cleared_at, clear_assessment,
                                    recent_ts, family_map)

    return {
        "open_work": open_work,
        "codes": codes,
        "code_counts": code_counts,
        "attempted": _build_attempted(vin),
        "freeze_frames": _build_freeze_frames(vin, dossier),
        "bulletins": _build_bulletins(dossier, open_work),
        "latest": _build_latest(dossier),
        "provenance_note": dossier.get("provenance_note", ""),
    }


def build_view(vin: str, dossier: dict[str, Any],
              live_status: dict[str, Any] | None) -> dict[str, Any]:
    """Everything the redesigned dossier page needs, computed once.

    ``dossier`` is the workup dict (``mes_bridge.workup(vin=vin)``);
    ``live_status`` is the same shape ``base.html``'s live strip already
    renders (``port``, ``mes_state``, ``lock_holder``, ...), or ``None`` when
    the caller has not computed it. Nothing here mutates either argument or
    touches the car -- nothing here writes anything at all.

    The dossier, job and flow pages between them call this several times
    per render (the Job page alone calls it twice: once for its own
    suggested-hypothesis evidence, once for the page body) and the open-work
    cards alone re-evaluate a fault tree per code, parsing FES logs directly
    -- seconds of work on a real corpus. Everything but the verdict and
    blind spots is pulled from :func:`_build_view_core`, memoised on (vin,
    newest MES-log mtime, newest state-file mtime) exactly like
    ``cuore.web.routes._dossier`` already memoises the workup itself, so a
    second call in the same request (or the next request, until a log or a
    state file changes) costs a dict lookup instead of a re-evaluation. The
    verdict and blind spots stay outside that cache because they depend on
    ``live_status``, which varies request to request and is not part of the
    key.
    """
    core = cache.get_or_build(
        ("dossier_view_core", vin, mes_bridge.newest_mtime(vin), _state_fingerprint()),
        lambda: _build_view_core(vin, dossier),
    )
    verdict = _build_verdict(vin, dossier, live_status, core["open_work"])
    next_action, blocker, next_step_id = _verdict_next_action(
        verdict, core["open_work"], core["freeze_frames"])
    verdict["next_action"] = next_action
    verdict["blocker"] = blocker
    verdict["next_step_id"] = next_step_id
    blind_spots = _build_blind_spots(vin, dossier, live_status)
    return {"verdict": verdict, "blind_spots": blind_spots, **core}


__all__ = ["build_view", "checklist_step_ids", "live_available", "readiness_result",
           "fuel_status", "readiness_panel", "FAMILY_STEPS"]
