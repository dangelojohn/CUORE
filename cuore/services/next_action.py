"""The Bench's single "Next action" card.

``next_action(...)`` is a pure function over small plain dicts; ``gather(vin)``
is the only impure part and reads existing stores (live poller, open job, fault
board, Next-connection plan). No new data, no invented steps: every title/why
is text already on file, and ``source`` names which rule fired and with what ids.

Rules, first match wins:
  1 live session or simulation running  -> finish or stop it (/live)
  2 open job + top fault-board card has a next test that needs no car -> that test
  3 first not-done Next-connection step -> that step with its preconditions
  4 open job with no evidence           -> read the car (connect flow)
  5 nothing open                        -> start a job (/start)
"""
from __future__ import annotations

import re
from typing import Any, Optional

# A next test needs no car when it is an inspection or a question, and does not
# mention anything that needs the adapter.
_NO_CAR = re.compile(r"\b(inspect\w*|visual\w*|ask|owner|question|look|photograph\w*|smell|listen)\b", re.I)
_NEEDS_CAR = re.compile(r"\b(scan|read|mode ?0?\w|live|connect\w*|clear\w*|drive|cold soak|ignition|key[- ]on|engine running|adapter|CAN|PID|DID)\b", re.I)


def _no_car_test(text: str) -> bool:
    return bool(_NO_CAR.search(text or "")) and not _NEEDS_CAR.search(text or "")


def _needs_list(text: str) -> list[str]:
    return [p.strip(" .") for p in re.split(r"[;,]\s+|\.\s+", text or "") if p.strip(" .")]


def next_action(vin: str, live: Optional[dict], job: Optional[dict],
                top_card: Optional[dict], plan: Optional[dict]) -> dict[str, Any]:
    live = live or {}
    if live.get("active") or live.get("simulation"):
        what = "simulation" if live.get("simulation") else "live session"
        return {"title": "Finish or stop the live session",
                "why": f"A {what} is running; nothing else on the car is safe to start until it ends.",
                "href": "/live", "link_label": "Open live session",
                "needs": ["Nothing new: the session is already running"],
                "source": f"rule 1: live poller active ({what})"}
    if job and top_card:
        nt = top_card.get("next_test") or {}
        text = (nt.get("text") or "").strip()
        if text and _no_car_test(text):
            return {"title": text,
                    "why": f"Next test for {top_card.get('label') or top_card.get('code') or 'the top fault'}, "
                           "the top fault on the board; it needs no car.",
                    "href": top_card.get("href") or f"/v/{vin}/job", "link_label": "Open fault",
                    "needs": ["No car needed"],
                    "source": f"rule 2: job {job.get('id')}, fault {top_card.get('key')}, "
                              f"test from {nt.get('source') or 'board'}"}
    step = next((s for s in (plan or {}).get("steps") or [] if not s.get("done")), None)
    if step:
        return {"title": step.get("title") or step.get("id"),
                "why": step.get("why") or "First step of the Next-connection plan not yet done.",
                "href": step.get("href") or step.get("link") or f"/v/{vin}/scan",
                "link_label": step.get("link_label") or "Open step",
                "needs": _needs_list(step.get("preconditions") or "") or ["Preconditions not recorded"],
                "source": f"rule 3: Next-connection step {step.get('id')} "
                          f"(order {step.get('order')}); plan source: {step.get('source') or 'plan'}"}
    if job and not job.get("has_evidence"):
        return {"title": "Read the car",
                "why": f"Job {job.get('id')} is open but has no evidence yet; a read of the car gives it some.",
                "href": f"/v/{vin}/scan", "link_label": "Connect and read",
                "needs": ["Adapter connected to the OBD port", "MES closed"],
                "source": f"rule 4: job {job.get('id')} has no evidence"}
    return {"title": "Start a job",
            "why": "Nothing is open for this car.",
            "href": "/start", "link_label": "Start a job",
            "needs": ["The customer's complaint"],
            "source": "rule 5: no open job, no live session, no plan step left"}


def gather(vin: str, plan: Optional[dict] = None) -> dict[str, Any]:
    """Collect the plain inputs from existing stores and run the rules. Never raises."""
    live: dict[str, Any] = {}
    try:
        from ..live import ops
        s = ops.live_session_status()
        active = bool(s.get("active"))
        live = {"active": active, "simulation": active and bool(s.get("simulation"))}
    except Exception:  # noqa: BLE001
        pass
    job = None
    try:
        from mes import jobs as jobs_mod
        j = jobs_mod.current(vin)
        if j:
            ev = any(h.get("evidence_for") or h.get("evidence_against") for h in j.get("hypotheses") or [])
            ev = ev or any((j.get("links") or {}).get(k) for k in (j.get("links") or {}))
            job = {"id": j.get("id"), "has_evidence": bool(ev)}
    except Exception:  # noqa: BLE001
        pass
    top = None
    if job:
        try:
            from . import fault_board
            cards = fault_board.board(vin)
            top = cards[0] if cards else None
        except Exception:  # noqa: BLE001
            pass
    return next_action(vin, live, job, top, plan)
