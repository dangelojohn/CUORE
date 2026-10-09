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

History is never rewritten. Record shapes share one file, distinguished by
``op``:

* ``open``                -- {op, id, at, vin, technician, complaint}
* ``hypothesis_add``      -- {op, job_id, id, at, text, system, system_text,
                              next_test, codes?, likelihood?, by?}. ``system``
                              is ``mes.systems.normalize_system(system_text)``
                              (or ``""``) resolved at write time; a record
                              from before this field existed has no
                              ``system_text`` at all -- :func:`_fold`
                              re-resolves those from the old free-text
                              ``system`` value on every read instead (never
                              rewriting the log itself).
* ``hypothesis_set``      -- {op, job_id, hyp_id, at, status?, next_test?, by?}
* ``hypothesis_edit``     -- {op, job_id, hyp_id, at, text?, system?,
                              system_text?, codes?, likelihood?, next_test?,
                              by?} -- same ``system``/``system_text`` pairing
                              and pre-``system_text`` migration as
                              ``hypothesis_add``.
* ``hypothesis_delete``   -- {op, job_id, hyp_id, at, by?}
* ``hypothesis_undelete`` -- {op, job_id, hyp_id, at, by?}
* ``action_add``          -- {op, job_id, id, at, kind, text, ref}
* ``attach``              -- {op, job_id, at, hyp_id?, supports?, ref, link?, by?}
* ``evidence_remove``     -- {op, job_id, hyp_id, at, side, ref_id, ref_kind?, by?}
* ``evidence_resolve``    -- {op, job_id, hyp_id, at, ref_id, ref_kind?, resolved, by?}
* ``close``                -- {op, job_id, at, outcome, readiness_at?,
                              codes_returned?, verdict?}

:func:`load`/:func:`current`/:func:`get` fold these into the job shape
described in the module's design doc: ``{id, vin, opened_at, closed_at,
technician, complaint, status, outcome, hypotheses, actions, verification,
links}``. A ``ref`` is ``{"kind", "id", "label", "result"?, "resolved"?}`` --
``kind`` one of ``code | freeze_frame | actuator | live | inspection |
symptom | note | media | dealer | bulletin | feedback | test | observation``.

Hypothesis status follows a guided-diagnostics path -- ``open -> supported ->
confirmed``, plus ``refuted`` from any state (see JOB_UX_FIXES_2026-10-08.md
#1): jumping ``open -> confirmed`` directly, or confirming with no
passed/failed test evidence or with unresolved evidence against, raises
:class:`RuleViolation` rather than silently letting a tech confirm a root
cause the evidence does not support.
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
LIKELIHOODS = ("low", "med", "high")
ACTION_KINDS = ("test", "inspection", "repair", "part", "clear", "note", "understand")
REF_KINDS = ("code", "freeze_frame", "actuator", "live", "inspection",
            "symptom", "note", "media", "dealer", "bulletin", "feedback",
            "test", "observation")
TEST_RESULTS = ("pass", "fail", "inconclusive", "not_possible")

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


def _normalize_system(text: Optional[str]) -> Optional[str]:
    """``mes.systems.normalize_system``, imported lazily (never at module
    scope) so a knowledge-table issue in that module can never break
    adding/editing a hypothesis -- same posture as
    ``mes.electrical_bridge``'s own lazy, guarded imports. Returns ``None``
    for blank/unrecognised text, same as the function it wraps."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        from . import systems as systems_mod
        return systems_mod.normalize_system(text)
    except Exception:  # noqa: BLE001
        return None


class RuleViolation(Exception):
    """A hypothesis-status transition (or confirmation) that the
    guided-diagnostics rule in JOB_UX_FIXES_2026-10-08.md #1 refuses: ``open``
    can never jump straight to ``confirmed``, and ``confirmed`` always needs
    >=1 passed/failed test result for it and 0 unresolved evidence against it.

    ``reason`` is the human-readable message; ``next_test`` (``""`` when the
    hypothesis has none recorded) is the hypothesis's own next test, so a
    caller can show "Next: <test>" alongside the refusal without a second
    lookup -- the API layer maps this onto HTTP 409 with both in the body.
    """

    def __init__(self, reason: str, next_test: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.next_test = next_test or ""


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


def _hyp(job: dict[str, Any], hyp_id: Optional[str]) -> Optional[dict[str, Any]]:
    return next((h for h in job["hypotheses"] if h["id"] == hyp_id), None)


def _audit(hyp: dict[str, Any], at: str, by: Any, action: str, detail: str) -> None:
    hyp.setdefault("audit", []).append({"at": at, "by": by, "action": action,
                                        "detail": detail})


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
            at = rec["at"]
            # Migration (JOB_UX_FIXES-era records predate system_text): an
            # old-shape record has no "system_text" key at all (raw text
            # lived in "system" itself); a current-shape one always has
            # "system_text", even "" for no system given. Either way the
            # key is re-resolved here, on read, from whichever raw text
            # exists -- never rewritten in the log itself, and re-run every
            # fold so an ALIASES table improvement benefits old records too.
            raw_system = rec.get("system_text")
            if raw_system is None:
                raw_system = rec.get("system") or ""
            job["hypotheses"].append({
                "id": rec["id"], "text": rec.get("text") or "",
                "system": _normalize_system(raw_system) or "",
                "system_text": raw_system, "status": "open",
                "evidence_for": [], "evidence_against": [],
                "next_test": rec.get("next_test") or "",
                "codes": list(rec.get("codes") or []),
                "likelihood": rec.get("likelihood"),
                "updated_at": at, "deleted": False,
                "confirmed_by": None, "confirmed_at": None,
                "audit": [{"at": at, "by": rec.get("by"), "action": "created",
                          "detail": rec.get("text") or ""}],
            })
        elif op == "hypothesis_set":
            hyp = _hyp(job, rec.get("hyp_id"))
            if hyp is None:
                continue
            at = rec["at"]
            old_status = hyp["status"]
            if rec.get("status") is not None:
                hyp["status"] = rec["status"]
                if rec["status"] == "confirmed":
                    hyp["confirmed_by"] = rec.get("by")
                    hyp["confirmed_at"] = at
                _audit(hyp, at, rec.get("by"), "status",
                      f"{old_status} -> {rec['status']}")
            if rec.get("next_test") is not None:
                hyp["next_test"] = rec["next_test"]
            hyp["updated_at"] = at
        elif op == "hypothesis_edit":
            hyp = _hyp(job, rec.get("hyp_id"))
            if hyp is None:
                continue
            at = rec["at"]
            changed = []
            for field in ("text", "next_test"):
                if rec.get(field) is not None:
                    hyp[field] = rec[field]
                    changed.append(field)
            # Same migration-safe resolution as hypothesis_add: an edit
            # record carries "system_text" (current shape) going forward,
            # but a record written before that existed still only has
            # "system" -- either way, re-resolve from whichever is there.
            raw_system = rec.get("system_text")
            if raw_system is None:
                raw_system = rec.get("system")
            if raw_system is not None:
                hyp["system_text"] = raw_system
                hyp["system"] = _normalize_system(raw_system) or ""
                changed.append("system")
            if rec.get("codes") is not None:
                hyp["codes"] = list(rec["codes"])
                changed.append("codes")
            if rec.get("likelihood") is not None:
                hyp["likelihood"] = rec["likelihood"]
                changed.append("likelihood")
            hyp["updated_at"] = at
            if changed:
                _audit(hyp, at, rec.get("by"), "edited", ", ".join(changed))
        elif op == "hypothesis_delete":
            hyp = _hyp(job, rec.get("hyp_id"))
            if hyp is None:
                continue
            hyp["deleted"] = True
            hyp["updated_at"] = rec["at"]
            _audit(hyp, rec["at"], rec.get("by"), "deleted", "")
        elif op == "hypothesis_undelete":
            hyp = _hyp(job, rec.get("hyp_id"))
            if hyp is None:
                continue
            hyp["deleted"] = False
            hyp["updated_at"] = rec["at"]
            _audit(hyp, rec["at"], rec.get("by"), "undeleted", "")
        elif op == "action_add":
            job["actions"].append({
                "at": rec["at"], "kind": rec.get("kind") or "note",
                "text": rec.get("text") or "", "ref": rec.get("ref"),
            })
        elif op == "attach":
            ref = rec.get("ref")
            hyp_id = rec.get("hyp_id")
            if hyp_id:
                hyp = _hyp(job, hyp_id)
                if hyp is None:
                    continue
                supports = rec.get("supports", True)
                bucket = "evidence_for" if supports else "evidence_against"
                if ref and ref not in hyp[bucket]:
                    hyp[bucket].append(ref)
                    hyp["updated_at"] = rec["at"]
                    label = (ref or {}).get("label") or (ref or {}).get("id")
                    _audit(hyp, rec["at"], rec.get("by"), "evidence_added",
                          f"{'for' if supports else 'against'}: {label}")
            else:
                link = rec.get("link")
                if link in job["links"] and ref:
                    ids = job["links"][link]
                    if ref.get("id") not in ids:
                        ids.append(ref.get("id"))
        elif op == "evidence_remove":
            hyp = _hyp(job, rec.get("hyp_id"))
            if hyp is None:
                continue
            bucket = "evidence_for" if rec.get("side") == "for" else "evidence_against"
            ref_id = rec.get("ref_id")
            ref_kind = rec.get("ref_kind")
            before = len(hyp[bucket])
            hyp[bucket] = [r for r in hyp[bucket] if not (
                r.get("id") == ref_id and (ref_kind is None or r.get("kind") == ref_kind))]
            if len(hyp[bucket]) != before:
                hyp["updated_at"] = rec["at"]
                _audit(hyp, rec["at"], rec.get("by"), "evidence_removed",
                      f"{rec.get('side')}: {ref_id}")
        elif op == "evidence_resolve":
            hyp = _hyp(job, rec.get("hyp_id"))
            if hyp is None:
                continue
            ref_id = rec.get("ref_id")
            ref_kind = rec.get("ref_kind")
            resolved = bool(rec.get("resolved", True))
            touched = False
            for r in hyp["evidence_against"]:
                if r.get("id") == ref_id and (ref_kind is None or r.get("kind") == ref_kind):
                    r["resolved"] = resolved
                    touched = True
            if touched:
                hyp["updated_at"] = rec["at"]
                _audit(hyp, rec["at"], rec.get("by"),
                      "evidence_resolved" if resolved else "evidence_unresolved",
                      str(ref_id))
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


def _require_hyp(job: dict[str, Any], hyp_id: str) -> dict[str, Any]:
    hyp = _hyp(job, hyp_id)
    if hyp is None:
        raise ValueError(f"no hypothesis {hyp_id!r} on job {job['id']!r}")
    return hyp


# --- the confirm-gate (JOB_UX_FIXES_2026-10-08.md #1) -----------------------


def _require_confirm_evidence(hyp: dict[str, Any]) -> None:
    passing = [r for r in hyp["evidence_for"]
              if r.get("kind") == "test" and r.get("result") in ("pass", "fail")]
    if not passing:
        raise RuleViolation(
            "Needs a passed/failed test result linked before this hypothesis "
            "can be confirmed.", hyp.get("next_test") or "")
    unresolved = [r for r in hyp["evidence_against"] if not r.get("resolved")]
    if unresolved:
        raise RuleViolation(
            "Cannot confirm: there is unresolved evidence against this "
            "hypothesis.", hyp.get("next_test") or "")


def _validate_status_transition(hyp: dict[str, Any], new_status: str) -> None:
    cur = hyp["status"]
    if new_status == "refuted":
        return  # refuted is allowed from any state
    if new_status == cur:
        return  # idempotent no-op
    if new_status == "confirmed":
        if cur == "open":
            raise RuleViolation(
                "Hypothesis must be supported before it can be confirmed -- "
                "jumping from open to confirmed is not allowed.",
                hyp.get("next_test") or "")
        if cur != "supported":
            raise RuleViolation(f"Cannot confirm a hypothesis in status {cur!r}.",
                                hyp.get("next_test") or "")
        _require_confirm_evidence(hyp)
        return
    if new_status == "supported":
        if cur != "open":
            raise RuleViolation(
                f"Cannot move a {cur!r} hypothesis back to 'supported'.",
                hyp.get("next_test") or "")
        return
    if new_status == "open":
        raise RuleViolation(f"Cannot move a {cur!r} hypothesis back to 'open'.",
                            hyp.get("next_test") or "")


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
                   next_test: str = "", codes: Optional[list[str]] = None,
                   likelihood: Optional[str] = None,
                   by: Optional[str] = None) -> dict[str, Any]:
    """Add a hypothesis to a job's ledger. Starts ``status="open"`` with no
    evidence -- evidence only ever arrives via :func:`add_evidence`, so a
    hypothesis can never claim support it was not actually given."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    if likelihood is not None and likelihood not in LIKELIHOODS:
        raise ValueError("likelihood must be one of: " + ", ".join(LIKELIHOODS))
    _require_job(job_id)
    hyp_id = uuid.uuid4().hex[:8]
    system_text = (system or "").strip()
    _append({"op": "hypothesis_add", "job_id": job_id, "id": hyp_id,
             "at": datetime.now().isoformat(timespec="seconds"),
             "text": text, "system": _normalize_system(system_text) or "",
             "system_text": system_text,
             "next_test": (next_test or "").strip(),
             "codes": [c.strip() for c in (codes or []) if c and c.strip()],
             "likelihood": likelihood, "by": (by or "").strip() or None})
    job = _require_job(job_id)
    return _require_hyp(job, hyp_id)


def set_hypothesis(job_id: str, hyp_id: str, *, status: Optional[str] = None,
                   next_test: Optional[str] = None,
                   by: Optional[str] = None) -> dict[str, Any]:
    """Change a hypothesis's status and/or its next test.

    Status follows ``open -> supported -> confirmed``, plus ``refuted`` from
    any state. Jumping ``open -> confirmed``, or confirming without >=1
    passed/failed test evidence_for or with any unresolved evidence_against,
    raises :class:`RuleViolation` instead of saving. Evidence itself is never
    touched here -- see :func:`add_evidence`/:func:`remove_evidence`.
    """
    if status is not None and status not in HYP_STATUSES:
        raise ValueError("status must be one of: " + ", ".join(HYP_STATUSES))
    job = _require_job(job_id)
    hyp = _require_hyp(job, hyp_id)
    if status is not None:
        _validate_status_transition(hyp, status)
    rec: dict[str, Any] = {"op": "hypothesis_set", "job_id": job_id, "hyp_id": hyp_id,
                           "at": datetime.now().isoformat(timespec="seconds")}
    if status is not None:
        rec["status"] = status
    if next_test is not None:
        rec["next_test"] = next_test
    if by is not None:
        rec["by"] = (by or "").strip() or None
    _append(rec)
    job = _require_job(job_id)
    return _require_hyp(job, hyp_id)


def edit_hypothesis(job_id: str, hyp_id: str, *, text: Optional[str] = None,
                    system: Optional[str] = None, codes: Optional[list[str]] = None,
                    likelihood: Optional[str] = None,
                    next_test: Optional[str] = None,
                    by: Optional[str] = None) -> dict[str, Any]:
    """Edit a hypothesis's own fields -- never its status or evidence, which
    go through :func:`set_hypothesis`/:func:`add_evidence` so the confirm
    gate can never be bypassed by editing around it."""
    if likelihood is not None and likelihood not in LIKELIHOODS:
        raise ValueError("likelihood must be one of: " + ", ".join(LIKELIHOODS))
    job = _require_job(job_id)
    _require_hyp(job, hyp_id)
    rec: dict[str, Any] = {"op": "hypothesis_edit", "job_id": job_id, "hyp_id": hyp_id,
                           "at": datetime.now().isoformat(timespec="seconds"),
                           "by": (by or "").strip() or None}
    if text is not None:
        text = text.strip()
        if not text:
            raise ValueError("text cannot be blank")
        rec["text"] = text
    if system is not None:
        system_text = system.strip()
        rec["system_text"] = system_text
        rec["system"] = _normalize_system(system_text) or ""
    if codes is not None:
        rec["codes"] = [c.strip() for c in codes if c and c.strip()]
    if likelihood is not None:
        rec["likelihood"] = likelihood
    if next_test is not None:
        rec["next_test"] = next_test.strip()
    if len(rec) <= 5:  # only op/job_id/hyp_id/at/by -- nothing to actually change
        raise ValueError("at least one field must be given to edit_hypothesis")
    _append(rec)
    job = _require_job(job_id)
    return _require_hyp(job, hyp_id)


def delete_hypothesis(job_id: str, hyp_id: str, *, by: Optional[str] = None) -> dict[str, Any]:
    """Soft-delete a hypothesis -- sets ``deleted: true``, never removes its
    history. See :func:`undelete_hypothesis` for the undo."""
    job = _require_job(job_id)
    _require_hyp(job, hyp_id)
    _append({"op": "hypothesis_delete", "job_id": job_id, "hyp_id": hyp_id,
             "at": datetime.now().isoformat(timespec="seconds"),
             "by": (by or "").strip() or None})
    return _require_job(job_id)


def undelete_hypothesis(job_id: str, hyp_id: str, *, by: Optional[str] = None) -> dict[str, Any]:
    """Undo :func:`delete_hypothesis`."""
    job = _require_job(job_id)
    _require_hyp(job, hyp_id)
    _append({"op": "hypothesis_undelete", "job_id": job_id, "hyp_id": hyp_id,
             "at": datetime.now().isoformat(timespec="seconds"),
             "by": (by or "").strip() or None})
    return _require_job(job_id)


def add_action(job_id: str, kind: str, text: str, *,
              ref: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Record one action taken against this job: a test, an inspection, a
    repair, a part, a clear, an explicit "understood the fault" mark, or a
    free-text note."""
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
          supports: bool = True, link: Optional[str] = None,
          by: Optional[str] = None) -> dict[str, Any]:
    """Attach one real record as evidence.

    With ``hyp_id``: the ref becomes evidence for (``supports=True``) or
    against (``supports=False``) that hypothesis. Without ``hyp_id``: the
    ref's id is recorded on the job's own ``links`` under the list that
    matches ``ref["kind"]`` (or the explicit ``link`` override) -- raises if
    that ref kind has no job-level link list, since those kinds (code,
    freeze_frame, actuator, live, bulletin) only make sense as evidence tied
    to a specific hypothesis.

    Never invents a ref -- callers (``cuore.services.jobs_bridge`` in
    particular) must pass a ref that points at a real record. See also
    :func:`add_evidence`, the same operation named for item #2's evidence
    picker.
    """
    if not isinstance(ref, dict) or not ref.get("kind") or not ref.get("id"):
        raise ValueError('ref must be a dict with at least "kind" and "id"')
    if ref["kind"] not in REF_KINDS:
        raise ValueError("ref kind must be one of: " + ", ".join(REF_KINDS))
    job = _require_job(job_id)

    if hyp_id:
        _require_hyp(job, hyp_id)
        _append({"op": "attach", "job_id": job_id, "hyp_id": hyp_id,
                 "supports": bool(supports), "ref": ref,
                 "by": (by or "").strip() or None,
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


def add_evidence(job_id: str, hyp_id: str, side: str, ref: dict[str, Any], *,
                 by: Optional[str] = None) -> dict[str, Any]:
    """Attach one real record as evidence for (``side="for"``) or against
    (``side="against"``) a hypothesis -- the "+ Evidence for/against" picker
    from JOB_UX_FIXES_2026-10-08.md #2. Thin wrapper over :func:`attach`."""
    if side not in ("for", "against"):
        raise ValueError("side must be 'for' or 'against'")
    return attach(job_id, ref, hyp_id=hyp_id, supports=(side == "for"), by=by)


def remove_evidence(job_id: str, hyp_id: str, side: str, ref_id: Any, *,
                    ref_kind: Optional[str] = None,
                    by: Optional[str] = None) -> dict[str, Any]:
    """Remove one evidence ref (matched by id, and kind when given) from a
    hypothesis's evidence_for/against list."""
    if side not in ("for", "against"):
        raise ValueError("side must be 'for' or 'against'")
    job = _require_job(job_id)
    _require_hyp(job, hyp_id)
    _append({"op": "evidence_remove", "job_id": job_id, "hyp_id": hyp_id,
             "side": side, "ref_id": ref_id, "ref_kind": ref_kind,
             "at": datetime.now().isoformat(timespec="seconds"),
             "by": (by or "").strip() or None})
    job = _require_job(job_id)
    return _require_hyp(job, hyp_id)


def resolve_evidence(job_id: str, hyp_id: str, ref_id: Any, *,
                     ref_kind: Optional[str] = None, resolved: bool = True,
                     by: Optional[str] = None) -> dict[str, Any]:
    """Mark one evidence_against ref resolved (or unresolved) in place -- the
    confirm gate (#1) only ever cares about *unresolved* evidence_against, so
    this lets a mechanic clear a concern without re-attaching the ref."""
    job = _require_job(job_id)
    hyp = _require_hyp(job, hyp_id)
    if not any(r.get("id") == ref_id for r in hyp["evidence_against"]):
        raise ValueError(f"no evidence_against ref {ref_id!r} on hypothesis {hyp_id!r}")
    _append({"op": "evidence_resolve", "job_id": job_id, "hyp_id": hyp_id,
             "ref_id": ref_id, "ref_kind": ref_kind, "resolved": bool(resolved),
             "at": datetime.now().isoformat(timespec="seconds"),
             "by": (by or "").strip() or None})
    job = _require_job(job_id)
    return _require_hyp(job, hyp_id)


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


__all__ = ["STATUSES", "OUTCOMES", "HYP_STATUSES", "LIKELIHOODS", "ACTION_KINDS",
          "REF_KINDS", "TEST_RESULTS", "LINK_LISTS", "RuleViolation",
          "state_dir", "store_path", "open", "close",
          "add_hypothesis", "set_hypothesis", "edit_hypothesis",
          "delete_hypothesis", "undelete_hypothesis",
          "add_action", "attach", "add_evidence", "remove_evidence",
          "resolve_evidence", "load", "get", "current"]
