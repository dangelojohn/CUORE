"""Bay sheet: one page per car/job that travels with the car. Pure view-model.

Every value comes from an existing service: next_action (the Bench's Next action), fault_board (ranked
codes), mechanic_plan_bridge (remaining steps), warranty_pack (tests with results, the evidence-side rule),
arrive_ready (equipment, parts, bulletins) and the job store (proof state). Nothing is invented: a missing
source shows as empty, a recall's status is never stated (CUORE only knows what is recorded).
No adapter, no network.
"""
from __future__ import annotations

from typing import Any, Optional

MAX_CODES = 8
MAX_STEPS = 6
MAX_BULLETINS = 8
CHECK_BY_VIN = "Check by VIN with the manufacturer: CUORE does not know a recall's or campaign's status for this VIN."
TICKS = ("Codes re-read", "Monitors complete", "Road test", "Customer informed")
SAFETY_RULES = (
    "Do not clear codes before they are read and recorded: clearing resets the proof evidence.",
    "Listen-only first: no request goes to the car until the adapter is checked.",
)


def _s(x: Any) -> str:
    return str(x or "").strip()


def _job(vin: str, job_id: str) -> Optional[dict[str, Any]]:
    try:
        from mes import jobs
        j = jobs.get(job_id) if job_id else None
        if j is None or j.get("vin") != vin:
            j = jobs.current(vin)
        return j
    except Exception:  # noqa: BLE001
        return None


def _codes(vin: str, job: Optional[dict]) -> tuple[list[dict], int, list[dict]]:
    try:
        from . import fault_board
        cards = fault_board.sort_by(fault_board.board(vin, (job or {}).get("id")), "importance")
    except Exception:  # noqa: BLE001
        return [], 0, []
    now = [c for c in cards if fault_board.tier_of(c) == "now"]
    rows = [{"code": _s(c.get("code")), "label": _s(c.get("label")), "label_src": _s(c.get("description_source")), "status": _s(c.get("status")),
             "module": _s(c.get("module")), "safety": bool(c.get("safety")),
             "test": _s((c.get("next_test") or {}).get("text")), "href": c.get("href") or ""} for c in now]
    return rows[:MAX_CODES], max(0, len(rows) - MAX_CODES), cards


def _tests(job: Optional[dict]) -> list[dict]:
    if not job:
        return []
    try:
        from . import warranty_pack
        items = warranty_pack._compose({"job": job})["tests"]
    except Exception:  # noqa: BLE001
        return []
    out = []
    for i in items:
        res = _s((i.get("data") or {}).get("result"))
        out.append({"at": _s(i.get("at"))[:16].replace("T", " "), "text": _s(i.get("text")), "result": res or "no result recorded",
                    "by": _s(i.get("by")), "source": _s(i.get("source"))})
    return out


def _todo(vin: str, job: Optional[dict]) -> list[dict]:
    if not job:
        return []
    try:
        from . import mechanic_plan_bridge as m
        plans = m.plans_for_job(vin, job)
    except Exception:  # noqa: BLE001
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for p in plans.values():
        for s in p.get("steps") or []:
            t = _s(s.get("title"))
            if s.get("done") or not t or t in seen:
                continue
            seen.add(t)
            out.append({"title": t, "detail": _s(s.get("detail"))[:160]})
    return out


def _proof(job: Optional[dict], cards: list[dict]) -> dict[str, Any]:
    v = (job or {}).get("verification") or {}
    fixed = [{"code": _s(c.get("code")), "status": _s(c.get("status")),
              "rule": _s((c.get("verification") or {}).get("rule")),
              "needs": (c.get("verification") or {}).get("needs"), "met": (c.get("verification") or {}).get("met")}
             for c in cards if c.get("fixed")]
    if v.get("verdict") or v.get("readiness_at") or fixed or (job or {}).get("outcome"):
        state = _s(v.get("verdict")) or ("; ".join(f"{f['code']} {f['status']}" for f in fixed)) or "recorded, no verdict stated"
    else:
        state = "No proof of repair recorded."
    return {"state": state, "outcome": _s((job or {}).get("outcome")), "readiness_at": _s(v.get("readiness_at")),
            "codes_returned": list(v.get("codes_returned") or []), "fixed": fixed, "ticks": list(TICKS)}


def build(vin: str, job_id: str = "", *, bar: Optional[dict] = None, verdict: Optional[dict] = None,
          url: str = "") -> dict[str, Any]:
    vin = _s(vin).upper()
    job = _job(vin, job_id)
    from . import arrive_ready, next_action
    try:
        na = next_action.gather(vin)
    except Exception:  # noqa: BLE001
        na = {"title": "Start a job", "why": "Nothing is open for this car.", "needs": [], "source": "fallback"}
    codes, more_codes, cards = _codes(vin, job)
    try:
        ar = arrive_ready.build(vin)
    except Exception:  # noqa: BLE001
        ar = {"equipment": {"charger": [], "witech": [], "bypass": []}, "parts": [], "bulletins": [], "platform": "",
              "verify": arrive_ready.VERIFY, "owner": []}
    bar = bar or {}
    v = verdict or {}
    safety = [f"Safety-related fault on the board: {c['code']} {c['label']}".strip() for c in codes if c["safety"]]
    safety += [f"Safety hypothesis on the job: {_s(h.get('text'))[:100]}" for h in (job or {}).get("hypotheses") or []
               if h.get("safety") and not h.get("deleted")]
    safety += list(SAFETY_RULES)
    if ar["equipment"]["charger"]:
        safety.append("Battery support on the car (13.2-13.5 V) before any flash or procedure.")
    bl = ar["bulletins"]
    try:
        from . import session_read
        sess = session_read.build(vin, who=_s((job or {}).get("technician")))
    except Exception:  # noqa: BLE001
        sess = {"has": False, "who": ""}
    return {
        "session": sess,
        "vin": vin, "job": job, "url": url or f"/v/{vin}/bay-sheet",
        "header": {"name": _s(bar.get("name")) or "(unnamed vehicle)", "odo": bar.get("odo_last"),
                   "odo_date": _s(bar.get("last_log"))[:10], "verdict": _s(v.get("label")),
                   "verdict_state": _s(v.get("state")), "summary": _s(v.get("summary")),
                   "complaint": _s((job or {}).get("complaint")),
                   "owner_words": [o["text"] for o in ar.get("owner") or []][:1]},
        "next": {"title": na.get("title"), "why": na.get("why"), "needs": na.get("needs") or [], "source": na.get("source")},
        "codes": codes, "more_codes": more_codes,
        "tests": _tests(job), "todo": _todo(vin, job)[:MAX_STEPS],
        "equipment": ar["equipment"], "parts": ar["parts"], "platform": ar.get("platform", ""),
        "bulletins": bl[:MAX_BULLETINS], "more_bulletins": max(0, len(bl) - MAX_BULLETINS),
        "check_by_vin": CHECK_BY_VIN, "safety": safety, "proof": _proof(job, cards),
    }
