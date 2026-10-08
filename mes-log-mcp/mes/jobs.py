"""The Job: one case per shop visit, aligning driver input, mechanic input,
test results and malfunctions into one logical flow.

Every other store in this package answers a narrow question -- what codes
were logged, what a driver felt, what a technician typed, what a dealer tool
read back. A Job is the thread that ties them together for one visit: the
driver's complaint in their own words, the hypotheses a mechanic is working
through (each with real evidence for/against, drawn from the stores above --
never invented), the actions taken, and how the repair was verified. This is
deliberately the MultiEcuScan shape -- vehicle -> module -> errors /
parameters / actuators / adjustments / info -> scan report -- applied to the
mechanic's own reasoning instead of just the car's data.

Append-only JSONL, same state directory convention as :mod:`mes.dealer` /
:mod:`mes.notes` (``CUORE_STATE_DIR``, else ``%PROGRAMDATA%\\cuore``, else
``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``) -- kept independent of
``cuore`` so ``mes`` never imports it.

History is never rewritten. Six record shapes share one file, distinguished
by ``op``:

* ``open``            -- {op, id, at, vin, technician, complaint}
* ``hypothesis_add``  -- {op, job_id, id, at, text, system, next_test}
* ``hypothesis_set``  -- {op, job_id, hyp_id, at, status?, next_test?}
* ``action_add``      -- {op, job_id, id, at, kind, text, ref}
* ``attach``          -- {op, job_id, at, hyp_id?, supports?, ref, link?}
* ``close``           -- {op, job_id, at, outcome, readiness_at?,
                          codes_returned?, verdict?}

:func:`load`/:func:`current`/:func:`get` fold these into the job shape
described in the module's design doc: ``{id, vin, opened_at, closed_at,
technician, complaint, status, outcome, hypotheses, actions, verification,
links}``. A ``ref`` is ``{"kind", "id", "label"}`` -- ``kind`` one of
``code | freeze_frame | actuator | live | inspection | symptom | note |
media | dealer | bulletin | feedback``.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

STATUSES = ("open", "verifying", "closed")
OUTCOMES = ("fixed", "not_fixed", "deferred")
HYP_STATUSES = ("open", "supported", "refuted", "confirmed")
ACTION_KINDS = ("test", "inspection", "repair", "part", "clear", "note")
REF_KINDS = ("code", "freeze_frame", "actuator", "live", "inspection",
            "symptom", "note", "media", "dealer", "bulletin", "feedback")

#: Which job-level link list a ref kind attaches to when no hypothesis is
#: named. A ref kind with no entry here can only be attached as hypothesis
#: evidence (attach() raises if asked to attach it bare to the job).
_LINK_BY_REF_KIND = {
    "symptom": "symptom_ids",
    "note": "note_ids",
    "media": "media_ids",
    "feedback": "feedback_ids",
    "dealer": "service_record_ids",
    "inspection": "inspection_ids",
}

LINK_LISTS = ("symptom_ids", "note_ids", "media_ids", "feedback_ids",
             "service_record_ids", "inspection_ids")


def state_dir() -> Path:
    """Mirror ``mes.dealer.state_dir()``: same candidates, first writable wins."""
    override = os.environ.get("CUORE_STATE_DIR")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    if os.environ.get("PROGRAMDATA"):
        candidates.append(Path(os.environ["PROGRAMDATA"], "cuore"))
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"], "cuore"))
    candidates.append(Path.home() / ".cuore")
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write-test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return d
        except OSError:
            continue
    return Path.cwd()


def store_path() -> Path:
    return state_dir() / "jobs.jsonl"


def _append(entry: dict[str, Any]) -> None:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _raw_records() -> list[dict[str, Any]]:
    p = store_path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _new_job(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rec["id"], "vin": rec["vin"], "opened_at": rec["at"],
        "closed_at": None, "technician": rec.get("technician") or "",
        "complaint": rec.get("complaint") or "", "status": "open",
        "outcome": None, "hypotheses": [], "actions": [],
        "verification": {"readiness_at": None, "codes_returned": [], "verdict": None},
        "links": {k: [] for k in LINK_LISTS},
    }


def _fold() -> dict[str, dict[str, Any]]:
    """Every record folded into current job state, keyed by job id, in the
    order jobs were opened. One bad/unknown-op line is skipped, never sinks
    the rest of the store -- same posture as ``mes.notes._raw_records``."""
    jobs: dict[str, dict[str, Any]] = {}
    for rec in _raw_records():
        op = rec.get("op")
        if op == "open":
            jid = rec.get("id")
            if not jid or jid in jobs:
                continue
            jobs[jid] = _new_job(rec)
            continue

        jid = rec.get("job_id")
        job = jobs.get(jid) if jid else None
        if job is None:
            continue

        if op == "hypothesis_add":
            job["hypotheses"].append({
                "id": rec["id"], "text": rec.get("text") or "",
                "system": rec.get("system") or "", "status": "open",
                "evidence_for": [], "evidence_against": [],
                "next_test": rec.get("next_test") or "",
            })
        elif op == "hypothesis_set":
            hyp = next((h for h in job["hypotheses"] if h["id"] == rec.get("hyp_id")), None)
            if hyp is None:
                continue
            if rec.get("status") is not None:
                hyp["status"] = rec["status"]
            if rec.get("next_test") is not None:
                hyp["next_test"] = rec["next_test"]
        elif op == "action_add":
            job["actions"].append({
                "at": rec["at"], "kind": rec.get("kind") or "note",
                "text": rec.get("text") or "", "ref": rec.get("ref"),
            })
        elif op == "attach":
            ref = rec.get("ref")
            hyp_id = rec.get("hyp_id")
            if hyp_id:
                hyp = next((h for h in job["hypotheses"] if h["id"] == hyp_id), None)
                if hyp is None:
                    continue
                bucket = "evidence_for" if rec.get("supports", True) else "evidence_against"
                if ref and ref not in hyp[bucket]:
                    hyp[bucket].append(ref)
            else:
                link = rec.get("link")
                if link in job["links"] and ref:
                    ids = job["links"][link]
                    if ref.get("id") not in ids:
                        ids.append(ref.get("id"))
        elif op == "close":
            job["status"] = "closed"
            job["closed_at"] = rec["at"]
            job["outcome"] = rec.get("outcome")
            v = job["verification"]
            if rec.get("readiness_at") is not None:
                v["readiness_at"] = rec["readiness_at"]
            if rec.get("codes_returned") is not None:
                v["codes_returned"] = rec["codes_returned"]
            if rec.get("verdict") is not None:
                v["verdict"] = rec["verdict"]
    return jobs


def _require_job(job_id: str) -> dict[str, Any]:
    jobs = _fold()
    job = jobs.get(job_id)
    if job is None:
        raise ValueError(f"no job with id {job_id!r}")
    return job


# --- the public surface -----------------------------------------------------


def open(vin: str, *, technician: str = "", complaint: str = "") -> dict[str, Any]:
    """Open a new job for this vehicle. Does not close any job already open
    on this VIN -- a car can have more than one open job in the store, though
    the UI only ever surfaces the newest via :func:`current`."""
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    rec = {"op": "open", "id": uuid.uuid4().hex[:12],
          "at": datetime.now().isoformat(timespec="seconds"),
          "vin": vin, "technician": (technician or "").strip(),
          "complaint": (complaint or "").strip()}
    _append(rec)
    return _new_job(rec)


def close(job_id: str, outcome: str, *, readiness_at: Optional[str] = None,
         codes_returned: Optional[list[str]] = None,
         verdict: Optional[str] = None) -> dict[str, Any]:
    """Close a job. ``outcome`` is required -- fixed | not_fixed | deferred --
    so a case can never be closed with no stated result."""
    outcome = (outcome or "").strip().lower()
    if outcome not in OUTCOMES:
        raise ValueError("outcome must be one of: " + ", ".join(OUTCOMES))
    job = _require_job(job_id)
    if job["status"] == "closed":
        raise ValueError(f"job {job_id!r} is already closed")
    rec: dict[str, Any] = {"op": "close", "job_id": job_id,
                           "at": datetime.now().isoformat(timespec="seconds"),
                           "outcome": outcome}
    if readiness_at is not None:
        rec["readiness_at"] = readiness_at
    if codes_returned is not None:
        rec["codes_returned"] = list(codes_returned)
    if verdict is not None:
        rec["verdict"] = verdict
    _append(rec)
    return _require_job(job_id)


def add_hypothesis(job_id: str, text: str, *, system: str = "",
                   next_test: str = "") -> dict[str, Any]:
    """Add a hypothesis to a job's ledger. Starts ``status="open"`` with no
    evidence -- evidence only ever arrives via :func:`attach`, so a
    hypothesis can never claim support it was not actually given."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    _require_job(job_id)
    hyp_id = uuid.uuid4().hex[:8]
    _append({"op": "hypothesis_add", "job_id": job_id, "id": hyp_id,
             "at": datetime.now().isoformat(timespec="seconds"),
             "text": text, "system": (system or "").strip(),
             "next_test": (next_test or "").strip()})
    job = _require_job(job_id)
    return next(h for h in job["hypotheses"] if h["id"] == hyp_id)


def set_hypothesis(job_id: str, hyp_id: str, *, status: Optional[str] = None,
                   next_test: Optional[str] = None) -> dict[str, Any]:
    """Change a hypothesis's status and/or its next test. Evidence is never
    touched here -- see :func:`attach`."""
    if status is not None and status not in HYP_STATUSES:
        raise ValueError("status must be one of: " + ", ".join(HYP_STATUSES))
    job = _require_job(job_id)
    if not any(h["id"] == hyp_id for h in job["hypotheses"]):
        raise ValueError(f"no hypothesis {hyp_id!r} on job {job_id!r}")
    rec: dict[str, Any] = {"op": "hypothesis_set", "job_id": job_id, "hyp_id": hyp_id,
                           "at": datetime.now().isoformat(timespec="seconds")}
    if status is not None:
        rec["status"] = status
    if next_test is not None:
        rec["next_test"] = next_test
    _append(rec)
    job = _require_job(job_id)
    return next(h for h in job["hypotheses"] if h["id"] == hyp_id)


def add_action(job_id: str, kind: str, text: str, *,
              ref: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Record one action taken against this job: a test, an inspection, a
    repair, a part, a clear, or a free-text note."""
    kind = (kind or "").strip().lower()
    if kind not in ACTION_KINDS:
        raise ValueError("kind must be one of: " + ", ".join(ACTION_KINDS))
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    _require_job(job_id)
    at = datetime.now().isoformat(timespec="seconds")
    _append({"op": "action_add", "job_id": job_id, "id": uuid.uuid4().hex[:8],
             "at": at, "kind": kind, "text": text, "ref": ref})
    return {"at": at, "kind": kind, "text": text, "ref": ref}


def attach(job_id: str, ref: dict[str, Any], *, hyp_id: Optional[str] = None,
          supports: bool = True, link: Optional[str] = None) -> dict[str, Any]:
    """Attach one real record as evidence.

    With ``hyp_id``: the ref becomes evidence for (``supports=True``) or
    against (``supports=False``) that hypothesis. Without ``hyp_id``: the
    ref's id is recorded on the job's own ``links`` under the list that
    matches ``ref["kind"]`` (or the explicit ``link`` override) -- raises if
    that ref kind has no job-level link list, since those kinds (code,
    freeze_frame, actuator, live, bulletin) only make sense as evidence tied
    to a specific hypothesis.

    Never invents a ref -- callers (``cuore.services.jobs_bridge`` in
    particular) must pass a ref that points at a real record.
    """
    if not isinstance(ref, dict) or not ref.get("kind") or not ref.get("id"):
        raise ValueError('ref must be a dict with at least "kind" and "id"')
    if ref["kind"] not in REF_KINDS:
        raise ValueError("ref kind must be one of: " + ", ".join(REF_KINDS))
    job = _require_job(job_id)

    if hyp_id:
        if not any(h["id"] == hyp_id for h in job["hypotheses"]):
            raise ValueError(f"no hypothesis {hyp_id!r} on job {job_id!r}")
        _append({"op": "attach", "job_id": job_id, "hyp_id": hyp_id,
                 "supports": bool(supports), "ref": ref,
                 "at": datetime.now().isoformat(timespec="seconds")})
    else:
        target_link = link or _LINK_BY_REF_KIND.get(ref["kind"])
        if target_link not in LINK_LISTS:
            raise ValueError(
                f"ref kind {ref['kind']!r} has no job-level link list; "
                "attach it to a hypothesis instead")
        _append({"op": "attach", "job_id": job_id, "link": target_link, "ref": ref,
                 "at": datetime.now().isoformat(timespec="seconds")})
    return _require_job(job_id)


def load(vin: str = "") -> list[dict[str, Any]]:
    """Every job, oldest-opened first, optionally filtered by VIN."""
    jobs = sorted(_fold().values(), key=lambda j: j["opened_at"])
    if vin:
        jobs = [j for j in jobs if j["vin"] == vin]
    return jobs


def get(job_id: str) -> Optional[dict[str, Any]]:
    """One job by id, or ``None``."""
    return _fold().get(job_id)


def current(vin: str) -> Optional[dict[str, Any]]:
    """The newest not-closed job for this VIN, or ``None``. "Current" means
    "what a mechanic walking up to this car right now would be working on" --
    a closed case is history, not the active thread."""
    vin = (vin or "").strip()
    if not vin:
        return None
    open_jobs = [j for j in load(vin) if j["status"] != "closed"]
    return open_jobs[-1] if open_jobs else None


__all__ = ["STATUSES", "OUTCOMES", "HYP_STATUSES", "ACTION_KINDS", "REF_KINDS",
          "LINK_LISTS", "state_dir", "store_path", "open", "close",
          "add_hypothesis", "set_hypothesis", "add_action", "attach",
          "load", "get", "current"]
