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
from . import dossier_bridge, mes_bridge
from .errors import BadRequest

try:
    from . import timeline_bridge
except Exception:  # noqa: BLE001 -- the flow must still render without it
    timeline_bridge = None

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
        dossier = mes_bridge.workup(vin=vin)
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
    log_since_intake = bool(identity.get("log_count")) and (
        in_at is None or _after(latest_log_ts, in_at) or latest_log_ts is None)
    observed_since_intake = _any_car_observation_after(vin, in_at)
    done[4] = bool(log_since_intake or observed_since_intake)
    why[4] = ("codes read since intake" if done[4]
             else "no observation or MES log since intake")

    # step 3 (verdict) is not independently knowable -- it counts done
    # exactly when step 4 (scan & codes) has data, per the flow's own rule.
    done[3] = done[4]
    why[3] = ("verdict computed from codes on file" if done[3]
             else "no codes read yet; verdict not computed")

    done[5] = bool(hypotheses)
    why[5] = (f"{len(hypotheses)} hypothesis(es) on file" if hypotheses
             else "no hypothesis recorded yet")

    attempted = dossier_view.get("attempted") or []
    done[6] = bool(attempted) or observed_since_intake
    why[6] = ("inspection, actuator run, or live observation on file" if done[6]
             else "no inspection, actuator run, or live observation since intake")

    confirmed = [h for h in hypotheses if h.get("status") == "confirmed"]
    done[7] = bool(confirmed)
    why[7] = ("a hypothesis confirmed" if confirmed
             else "no hypothesis confirmed yet")

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

    blocked_on_parts = bool(visit) and visit.get("status") == "waiting_parts"
    first_not_done = next((n for n, *_ in _STEPS if not done[n]), 12)

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

        if n == first_not_done:
            status = "blocked" if blocked_on_parts else "current"
        elif done[n]:
            status = "done"
        else:
            status = "todo"

        job_step = _FLOW_TO_JOB_STEP.get(n)
        est_min = step_averages.get(job_step) if job_step else None

        steps.append({
            "n": n, "key": key, "title": title, "href": href,
            "status": status, "why": why[n], "est_min": est_min,
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


__all__ = ["flow_state", "current_vehicle"]
