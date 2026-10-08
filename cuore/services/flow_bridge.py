"""The mechanic flow: one fixed 12-step order laid over whatever real
records exist for a VIN, so a technician (or the home page, for the car
presently in the bay) can see "what's next" without hunting across pages.

Nothing here is a new source of truth -- it only reads :mod:`mes.shop` and
:mod:`mes.jobs` (both still landing, so imported lazily and degraded to
``None`` if either is missing or broken) plus the bridges that already
answer the dossier/job/symptom/media/feedback questions, and folds them into
one ordered step list. Done/current/todo/blocked is derived from real
records only -- never inferred from UI state.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache, dossier_bridge, mes_bridge
from .errors import BadRequest

try:
    from . import timeline_bridge
except Exception:  # noqa: BLE001 -- the flow must still render without it
    timeline_bridge = None

try:
    from ..live import checklists as checklist_store
except Exception:  # noqa: BLE001
    checklist_store = None

try:
    from ..live import store as live_store
except Exception:  # noqa: BLE001
    live_store = None


def _shop_mod() -> Any:
    """``mes.shop`` is still landing -- import lazily, degrade to ``None``."""
    try:
        from mes import shop as shop_mod
        return shop_mod
    except Exception:  # noqa: BLE001
        return None


def _jobs_mod() -> Any:
    """``mes.jobs`` likewise."""
    try:
        from mes import jobs as jobs_mod
        return jobs_mod
    except Exception:  # noqa: BLE001
        return None


#: n, key, title, button_label -- href is built per-VIN in _href().
_STEPS: list[tuple[int, str, str, str]] = [
    (1, "intake", "Intake", "Start intake"),
    (2, "symptoms", "Complaint & symptoms", "Record symptoms"),
    (3, "verdict", "Verdict", "Open verdict"),
    (4, "scan", "Scan & codes", "Scan the car"),
    (5, "understand", "Understand the fault", "Review the code"),
    (6, "tests", "Tests & inspections", "Run tests"),
    (7, "hypotheses", "Hypotheses", "Confirm hypothesis"),
    (8, "plan", "Plan the repair", "Plan the repair"),
    (9, "repair", "Repair", "Log repair"),
    (10, "verify", "Verify", "Read readiness"),
    (11, "document", "Document", "Print report"),
    (12, "release", "Release", "Release the car"),
]

#: Flow step n -> the shop's own job-stepper step number (1-7), used to pull
#: a learned average minutes out of ``mes.shop.board()``. Steps with no
#: direct counterpart (intake, verdict, understand, plan, release) get no
#: estimate rather than a misleading one.
_FLOW_TO_JOB_STEP = {2: 1, 4: 2, 6: 3, 7: 4, 9: 5, 10: 6, 11: 7}


def _norm_ts(ts: Optional[str]) -> str:
    """Normalize an ISO-ish timestamp ("...T..." or "... ...") to a
    space-separated, lexicographically-comparable form."""
    return (ts or "").replace("T", " ")[:19]


def _short_date(ts: Optional[str]) -> str:
    """"4 Oct"-style date out of an ISO-ish timestamp, for a why-text that
    tells a mechanic how stale a piece of evidence is. ``""`` when ``ts``
    does not parse -- never raises, since a why-string must still render."""
    from datetime import datetime

    norm = _norm_ts(ts)
    if not norm:
        return ""
    try:
        dt = datetime.fromisoformat(norm)
    except ValueError:
        return norm[:10]
    return f"{dt.day} {dt.strftime('%b')}"


def _after(ts: Optional[str], since: Optional[str]) -> bool:
    if not ts or not since:
        return False
    return _norm_ts(ts) >= _norm_ts(since)


def _href(template: str, vin: str) -> str:
    return template.format(vin=vin)


def _step_averages(shop_mod: Any) -> dict[int, float]:
    if shop_mod is None:
        return {}
    try:
        return shop_mod.board().get("today", {}).get("step_averages", {}) or {}
    except Exception:  # noqa: BLE001 -- a broken board must never break the flow
        return {}


def _symptoms(vin: str) -> list[dict[str, Any]]:
    if timeline_bridge is None:
        return []
    try:
        return timeline_bridge.symptoms(vin)["symptoms"]
    except Exception:  # noqa: BLE001
        return []


def _any_car_observation_after(vin: str, since: Optional[str]) -> bool:
    if live_store is None or not since:
        return False
    try:
        obs = live_store.recent_observations(200, vin=vin)
    except Exception:  # noqa: BLE001
        return False
    return any(live_store.is_from_car(o) and _after(o.get("at"), since) for o in obs)


def step_registry() -> list[dict[str, Any]]:
    """Every flow step's ``{n, key, title}``, oldest-first -- the data a
    content cross-reference like "the step 7 Hypotheses review"
    (JOB_UX_FIXES_2026-10-08.md #10) is generated from, instead of a
    hard-coded number baked into template copy."""
    return [{"n": n, "key": key, "title": title} for n, key, title, _ in _STEPS]


def step_link(key: str) -> Optional[dict[str, Any]]:
    """One step's ``{n, key, title}`` by its key (e.g. ``"hypotheses"``), or
    ``None`` for an unknown key -- ``step_link('review')``-style content
    cross-references resolve through this, never a hard-coded step number."""
    return next(({"n": n, "key": k, "title": t} for n, k, t, _ in _STEPS if k == key), None)


def _tri_state(done_n: int, total_n: int) -> str:
    """not_started / in_progress / complete from a real (done, total) pair
    -- never "complete" with 0 done, and never "complete" with no criteria
    to have met (total == 0 means nothing is on file yet, i.e. not started,
    not vacuously done)."""
    if total_n <= 0 or done_n <= 0:
        return "not_started"
    if done_n >= total_n:
        return "complete"
    return "in_progress"


def _checklist_progress(vin: str, dossier: dict[str, Any]) -> tuple[int, int]:
    """Step 6 (Tests & inspections): checklist rows that carry a *result*
    (JOB_UX_FIXES_2026-10-08.md #3's result sheet, not the bench's bare
    done flag) over every checklist row this vehicle's open-work exposes."""
    if checklist_store is None:
        return (0, 0)
    try:
        step_ids = dossier_bridge.checklist_step_ids(vin, dossier)
    except Exception:  # noqa: BLE001
        return (0, 0)
    if not step_ids:
        return (0, 0)
    try:
        entries = checklist_store.get(vin)
    except Exception:  # noqa: BLE001
        entries = {}
    done = sum(1 for sid in step_ids if (entries.get(sid) or {}).get("result") is not None)
    return (done, len(step_ids))


def _hypothesis_progress(hypotheses: list[dict[str, Any]]) -> tuple[int, int]:
    """Step 7 (Hypotheses): non-deleted hypotheses whose status has moved
    past ``open`` (supported/refuted/confirmed all count) over every
    non-deleted hypothesis on the job."""
    active = [h for h in hypotheses if not h.get("deleted")]
    if not active:
        return (0, 0)
    done = sum(1 for h in active if h.get("status") != "open")
    return (done, len(active))


def current_vehicle() -> Optional[str]:
    """The VIN of the car currently in the bay -- the newest visit whose
    status is not ``"out"`` -- or ``None`` when nothing is in, or the shop
    board itself is not available yet. Lets the home page show *a* flow
    without the caller having to already know which VIN to ask for."""
    shop_mod = _shop_mod()
    if shop_mod is None:
        return None
    try:
        visits = shop_mod.load()
    except Exception:  # noqa: BLE001
        return None
    open_visits = [v for v in visits if v.get("status") != "out"]
    if not open_visits:
        return None
    return sorted(open_visits, key=lambda v: v.get("in_at") or "")[-1].get("vin")


def flow_state(vin: str) -> dict[str, Any]:
    """Everything the flow widget needs for this VIN, computed once."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")

    shop_mod = _shop_mod()
    jobs_mod = _jobs_mod()

    visit = None
    if shop_mod is not None:
        try:
            visit = shop_mod.current(vin)
            if visit is None:
                visits_for_vin = shop_mod.load(vin)
                visit = visits_for_vin[-1] if visits_for_vin else None
        except Exception:  # noqa: BLE001
            visit = None

    job = None
    if jobs_mod is not None:
        try:
            job = jobs_mod.current(vin)
            if job is None:
                jobs_for_vin = jobs_mod.load(vin)
                job = jobs_for_vin[-1] if jobs_for_vin else None
        except Exception:  # noqa: BLE001
            job = None

    try:
        # Same cache key ``cuore.web.routes._dossier`` and
        # ``cuore.services.jobs_bridge._cached_workup`` use (vin, newest
        # MES-log mtime), so all three share one entry instead of each
        # re-running ``mes_bridge.workup`` -- seconds of FES re-parsing on a
        # real corpus.
        dossier = cache.get_or_build(
            ("workup", vin, mes_bridge.newest_mtime(vin)),
            lambda: mes_bridge.workup(vin=vin),
        )
    except Exception:  # noqa: BLE001
        dossier = {}
    try:
        dossier_view = dossier_bridge.build_view(vin, dossier, None)
    except Exception:  # noqa: BLE001
        dossier_view = {"verdict": None, "open_work": [], "codes": [],
                        "attempted": []}

    verdict = dossier_view.get("verdict") or {}
    step_averages = _step_averages(shop_mod)

    in_at = visit.get("in_at") if visit else None
    hypotheses = (job or {}).get("hypotheses", [])
    actions = (job or {}).get("actions", [])

    # --- per-step done/why, independent of ordering -----------------------

    done: dict[int, bool] = {}
    why: dict[int, str] = {}

    done[1] = visit is not None
    why[1] = (f"visit open (status: {visit['status']})" if visit
             else "no visit open for this VIN")

    symptoms = _symptoms(vin)
    done[2] = bool(symptoms)
    why[2] = (f"{len(symptoms)} symptom report(s) on file" if symptoms
             else "no symptom recorded")

    cp = dossier.get("current_picture") or {}
    identity = dossier.get("identity") or {}
    latest_log_ts = ((cp.get("latest_session") or {}).get("timestamp")
                     or (cp.get("latest_scan") or {}).get("timestamp"))
    has_any_log = bool(identity.get("log_count"))
    log_since_intake = has_any_log and (
        in_at is None or _after(latest_log_ts, in_at) or latest_log_ts is None)
    observed_since_intake = _any_car_observation_after(vin, in_at)
    # Evidence that predates intake still counts -- a VIN with any
    # session/scan on file has had its codes read, full stop. A read taken
    # since intake just upgrades the why-text to say so; it is never what
    # makes this step done versus not.
    done[4] = bool(has_any_log or observed_since_intake)
    if log_since_intake or observed_since_intake:
        why[4] = "codes read since intake"
    elif has_any_log:
        why[4] = (f"codes from MES logs, newest {_short_date(latest_log_ts)}; "
                 "read the car again to refresh")
    else:
        why[4] = "no observation or MES log on file for this VIN"

    # step 3 (verdict) counts done whenever dossier_bridge actually produced
    # a verdict -- NO_DATA means none; anything else means one was computed,
    # even from evidence that predates intake. Never show "verdict not
    # computed" once a real verdict exists; its own summary sentence is the
    # why-text, so post-intake reads upgrade it automatically.
    verdict_state = verdict.get("state")
    done[3] = bool(verdict_state) and verdict_state != "NO_DATA"
    why[3] = ((verdict.get("summary") or "verdict computed from codes on file")
             if done[3] else "no codes read yet; verdict not computed")

    # Step 5 (Understand the fault): "viewed" cannot be known, so this is
    # complete when either a hypothesis exists (the mechanic has engaged
    # with the evidence enough to propose one) or the mechanic took the
    # explicit "understood" action (kind="understand" -- see mes.jobs);
    # not_started otherwise. No in_progress state for this one -- it is a
    # binary review, not a count of rows (JOB_UX_FIXES_2026-10-08.md #4).
    understood_actions = [a for a in actions if a.get("kind") == "understand"]
    step5_complete = bool(hypotheses) or bool(understood_actions)
    done[5] = step5_complete
    state: dict[int, str] = {5: "complete" if step5_complete else "not_started"}
    progress: dict[int, dict[str, int]] = {5: {"done": 1 if step5_complete else 0, "total": 1}}
    why[5] = ("a hypothesis is on file" if hypotheses
             else "marked understood" if understood_actions
             else "no hypothesis recorded yet, and the fault has not been marked understood")

    # Step 6 (Tests & inspections): real criteria is checklist rows that
    # carry a *result* (#3's result sheet) over every row this vehicle's
    # open-work exposes -- never "green" just because something, anything,
    # was logged (#4's bug: 0/22 showed as done).
    checklist_done, checklist_total = _checklist_progress(vin, dossier)
    state[6] = _tri_state(checklist_done, checklist_total)
    progress[6] = {"done": checklist_done, "total": checklist_total}
    done[6] = state[6] == "complete"
    why[6] = (f"{checklist_done}/{checklist_total} test result(s) recorded" if checklist_total
             else "no checklist steps on file for this vehicle yet")

    # Step 7 (Hypotheses): non-deleted hypotheses whose status has moved
    # past open (supported/refuted/confirmed) over every non-deleted
    # hypothesis -- not just "one confirmed", since a job can legitimately
    # carry several hypotheses that must each be worked through.
    hyp_done, hyp_total = _hypothesis_progress(hypotheses)
    state[7] = _tri_state(hyp_done, hyp_total)
    progress[7] = {"done": hyp_done, "total": hyp_total}
    done[7] = state[7] == "complete"
    why[7] = (f"{hyp_done}/{hyp_total} hypothesis(es) resolved beyond open" if hyp_total
             else "no hypothesis recorded yet")

    part_actions = [a for a in actions if a.get("kind") == "part"]
    done[8] = bool(part_actions)
    why[8] = ("parts/tools recorded on the job" if part_actions
             else "no parts or tools recorded on the job")

    repair_actions = [a for a in actions if a.get("kind") == "repair"]
    done[9] = bool(repair_actions)
    why[9] = ("a repair action recorded" if repair_actions
             else "no repair action recorded")

    done[10] = verdict.get("state") == "VERIFIED_CLEAN"
    if done[10]:
        why[10] = "verdict VERIFIED_CLEAN: readiness proves the repair"
    elif verdict.get("state") == "UNVERIFIED_REPAIR":
        why[10] = "verdict UNVERIFIED_REPAIR: no readiness read since the clear"
    else:
        why[10] = "no readiness read proving the repair yet"

    release = (visit or {}).get("release") or {}
    done[11] = bool(release.get("report_printed") and release.get("labels_printed"))
    why[11] = ("report and labels printed" if done[11]
              else "report/labels not yet printed")

    done[12] = bool(visit) and visit.get("status") == "out"
    why[12] = ("visit released" if done[12] else "visit not yet released")

    # --- fold into ordered steps, pick current/blocked ---------------------

    # Every step not already given an explicit tri-state above (5/6/7) is
    # binary -- complete once its own done[n] flag is true, not_started
    # otherwise. No step is ever reported "complete" with 0 done.
    for n in (1, 2, 3, 4, 8, 9, 10, 11, 12):
        state[n] = "complete" if done[n] else "not_started"
        progress[n] = {"done": 1 if done[n] else 0, "total": 1}

    blocked_on_parts = bool(visit) and visit.get("status") == "waiting_parts"
    # Job UX run 2, R2: "job progress" is the first step the tech hasn't
    # even started -- not the first step that isn't 100% done. A tri-state
    # step (6/7) sitting at "in_progress" (1 of 22 tests, say) has real
    # work on file and must not pin the chip there forever; only
    # "not_started" blocks forward progress. Same `state` dict the step
    # summaries themselves render from, so this can never disagree with
    # what's on screen (R2's "same criteria as the step summaries").
    first_not_done = next((n for n, *_ in _STEPS if state.get(n) == "not_started"), 12)

    steps: list[dict[str, Any]] = []
    for n, key, title, button_label in _STEPS:
        href_template = {
            1: "/start",
            2: "/v/{vin}/job#step-2",
            3: "/v/{vin}",
            4: "/v/{vin}/codes",
            5: "/v/{vin}/job#step-5",
            6: "/v/{vin}/job#step-6",
            7: "/v/{vin}/job#step-7",
            8: "/v/{vin}/job#step-8",
            9: "/v/{vin}/job#step-9",
            10: "/v/{vin}/job#step-10",
            11: "/v/{vin}/job#step-11",
            12: "/v/{vin}/release",
        }[n]
        href = _href(href_template, vin)

        # "status" is kept for old consumers, but derived from "state" --
        # never independently computed -- so the two can never disagree.
        if n == first_not_done:
            status = "blocked" if blocked_on_parts else "current"
        elif state[n] == "complete":
            status = "done"
        else:
            status = "todo"

        job_step = _FLOW_TO_JOB_STEP.get(n)
        est_min = step_averages.get(job_step) if job_step else None

        steps.append({
            "n": n, "key": key, "title": title, "href": href,
            "status": status, "state": state[n], "progress": progress[n],
            "why": why[n], "est_min": est_min,
        })

    current_n = first_not_done
    current_step = next(s for s in steps if s["n"] == current_n)
    next_obj = {"n": current_step["n"], "title": current_step["title"],
               "href": current_step["href"],
               "button_label": [b for a, _, _, b in _STEPS if a == current_n][0]}

    blockers = [s["why"] for s in steps if s["status"] == "blocked"]
    if blocked_on_parts and why[first_not_done] not in blockers:
        blockers.append("waiting on parts")

    return {
        "steps": steps,
        "current": current_n,
        "next": next_obj,
        "visit": ({"status": visit["status"],
                  "minutes_in": (None if not in_at else
                                round((_minutes_now(in_at)), 1)),
                  "promised_at": visit.get("promised_at")}
                 if visit else None),
        "job": ({"id": job["id"], "status": job["status"]} if job else None),
        "blockers": blockers,
    }


def _minutes_now(in_at: str) -> float:
    from datetime import datetime
    try:
        t0 = datetime.fromisoformat(in_at)
    except ValueError:
        return 0.0
    return (datetime.now() - t0).total_seconds() / 60.0


__all__ = ["flow_state", "current_vehicle", "step_registry", "step_link"]
