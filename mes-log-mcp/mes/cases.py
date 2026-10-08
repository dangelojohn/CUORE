"""Case memory: so the next Stelvio with the same fault starts where the
last one finished, instead of from zero.

Every other store in this package answers one visit's own question --
:mod:`mes.jobs` the diagnostic thread, :mod:`mes.shop` the logistics,
:mod:`mes.tool_usage` what was actually used. This module is the one that
looks *across* visits: it folds one closed job (plus the real shop timing,
parts, tool-usage and symptom records that sit alongside it) into a portable
``Case``, and lets a later visit on a different car ask "has anything like
this happened before, on this model".

A Case is never presented as a diagnosis for the car in front of you -- only
as what happened on a *prior* car. Every summary sentence this module writes
is worded "on the last <model> with these codes ..." and the word "proven"
never appears in this module's output, by design (see :func:`match` /
:func:`prefill`).

Append-only JSONL, same state-directory convention as :mod:`mes.jobs` /
:mod:`mes.shop` / :mod:`mes.tool_usage` (``CUORE_STATE_DIR``, else
``%PROGRAMDATA%\\cuore``, else ``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``)
-- kept independent of ``cuore`` so ``mes`` never imports it. One row per
case, each a complete record (no folding/rewriting across rows): cases are
built once, from a closed job or from this project's own dossier, and
appended whole.

Every cross-module lookup (``mes.jobs``, ``mes.shop``, ``mes.tool_usage``,
``mes.service``, ``mes.symptoms``, ``mes.platform``, ``mes.systems``) is
imported lazily, inside the functions that need it -- same posture as
``mes.shop`` importing ``mes.jobs`` lazily -- so this module stays importable
and unit-testable on its own.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

OUTCOMES = ("fixed", "not_fixed", "released_unverified", "deferred")

#: This project's own Stelvio -- see memory ``project_stelvio_evap.md``.
VIN_STELVIO = "ZASFAKPN5J7B88115"

#: Loose mapping from a job action's ``kind`` (``mes.jobs.ACTION_KINDS``) to
#: the shop job-step number (``mes.shop.JOB_STEPS``) it most likely belongs
#: to, so a case's ``path`` can carry the real per-step minutes
#: ``mes.shop`` timed, next to what was actually done. Not sourced beyond
#: "what a mechanic would file it under" -- a reasonable default, not a
#: measured fact.
_ACTION_KIND_TO_STEP = {
    "test": 3, "inspection": 3, "repair": 5, "part": 5, "clear": 6, "note": 1,
}


def state_dir() -> Path:
    """Mirror ``mes.jobs.state_dir()``: same candidates, first writable wins."""
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
    return state_dir() / "cases.jsonl"


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


def _minutes_between(start: str, end: str) -> Optional[float]:
    try:
        t0 = datetime.fromisoformat(start)
        t1 = datetime.fromisoformat(end)
    except (ValueError, TypeError):
        return None
    return round((t1 - t0).total_seconds() / 60.0, 1)


def load(model: str = "") -> list[dict[str, Any]]:
    """Every case on file, oldest first, optionally filtered by model."""
    rows = _raw_records()
    if model:
        rows = [r for r in rows if r.get("model") == model]
    return rows


def get(case_id: str) -> Optional[dict[str, Any]]:
    """One case by id, or ``None``."""
    for r in _raw_records():
        if r.get("id") == case_id:
            return r
    return None


# --- building a Case from a closed job --------------------------------------


def _codes_from_job(job: dict[str, Any]) -> list[str]:
    """Every DTC this job actually touched: the verified-close readback,
    plus any evidence/action ref of kind ``"code"`` -- order preserved,
    never invented."""
    codes: list[str] = []

    def _add(c: Optional[str]) -> None:
        c = (c or "").strip().upper()
        if c and c not in codes:
            codes.append(c)

    for c in (job.get("verification") or {}).get("codes_returned") or []:
        _add(c)
    for h in job.get("hypotheses") or []:
        for ref in (h.get("evidence_for") or []) + (h.get("evidence_against") or []):
            if isinstance(ref, dict) and ref.get("kind") == "code":
                _add(ref.get("id"))
    for a in job.get("actions") or []:
        ref = a.get("ref")
        if isinstance(ref, dict) and ref.get("kind") == "code":
            _add(ref.get("id"))
    return codes


def _families_for_codes(codes: list[str]) -> list[str]:
    """Distinct primary vehicle systems (``mes.systems.systems_for_code``)
    these codes implicate -- e.g. ``["evap"]``, ``["network"]``."""
    from . import systems as systems_mod
    out: list[str] = []
    for c in codes:
        for row in systems_mod.systems_for_code(c):
            sys_key = row.get("system")
            if row.get("role") == "primary" and sys_key and sys_key != "UNKNOWN" and sys_key not in out:
                out.append(sys_key)
    return out


def _symptoms_summary(vin: str, job: dict[str, Any]) -> str:
    """What a person actually reported feeling, for the symptom ids this
    job linked -- an attested claim, never treated as a measurement (same
    caution ``mes.symptoms`` itself carries)."""
    from . import symptoms as symptoms_mod
    ids = set((job.get("links") or {}).get("symptom_ids") or [])
    if not ids:
        return ""
    rows = [s for s in symptoms_mod.load(vin, include_hidden=True) if s.get("id") in ids]
    if not rows:
        return ""
    parts = []
    for s in rows:
        tags = ", ".join(s.get("tags") or []) or "other"
        text = f" -- {s['text']}" if s.get("text") else ""
        parts.append(f"{s.get('reporter', '?')} reported {tags}{text}")
    return "; ".join(parts)


def _parts_used(vin: str, job: dict[str, Any]) -> list[dict[str, Any]]:
    """Parts fitted on this VIN's service ledger during this job's window
    (opened_at..closed_at, inclusive by date -- an open job's window runs
    to "now")."""
    from . import service as service_mod
    opened = (job.get("opened_at") or "")[:10]
    closed = (job.get("closed_at") or "")[:10]
    out: list[dict[str, Any]] = []
    for rec in service_mod.load(vin, kind="service"):
        date = (rec.get("data") or {}).get("date") or ""
        if opened and date and date < opened:
            continue
        if closed and date and date > closed:
            continue
        for p in (rec.get("data") or {}).get("parts") or []:
            out.append({"name": p.get("name", ""), "part_no": p.get("part_no", ""),
                       "qty": p.get("qty", 1)})
    return out


def _tools_and_pitfalls(vin: str, job_id: str) -> tuple[dict[str, list[str]], list[str]]:
    """``{used, flagged_wrong, bought}`` from this job's tool-usage reviews,
    plus the pitfall text they carry (a wrong tool's note, or a would-buy
    reason). ``bought`` is a would-buy name this shop's own inventory
    (``mes.tool_usage.have_status``) now shows as owned/on_order -- i.e. it
    was actually acted on, not just wished for."""
    from . import tool_usage as tool_usage_mod
    rows = [r for r in tool_usage_mod.load(vin=vin) if r.get("job_id") == job_id]
    used: list[str] = []
    flagged_wrong: list[str] = []
    bought: list[str] = []
    pitfalls: list[str] = []
    for r in rows:
        for t in r.get("tools_used") or []:
            name = t.get("tool")
            if name and name not in used:
                used.append(name)
            if t.get("was_right") == "no":
                if name and name not in flagged_wrong:
                    flagged_wrong.append(name)
                if t.get("note"):
                    pitfalls.append(t["note"])
        for b in r.get("would_buy") or []:
            name = b.get("name")
            if name and tool_usage_mod.have_status(name) in ("owned", "on_order") and name not in bought:
                bought.append(name)
            if b.get("why"):
                pitfalls.append(b["why"])
    return {"used": used, "flagged_wrong": flagged_wrong, "bought": bought}, pitfalls


def _path_and_minutes(vin: str, job: dict[str, Any]) -> tuple[list[dict[str, Any]], Optional[float]]:
    """The job's actions, grouped onto shop job-steps 1-7
    (``_ACTION_KIND_TO_STEP``), each annotated with the real minutes
    ``mes.shop`` timed for that step on the linked visit (if one exists).
    ``total_minutes`` sums those, falling back to opened_at..closed_at."""
    from . import shop as shop_mod
    visit = next((v for v in shop_mod.load(vin) if v.get("job_id") == job.get("id")), None)
    step_minutes: dict[int, float] = {}
    if visit:
        for st in visit.get("step_times") or []:
            if isinstance(st.get("minutes"), (int, float)):
                step_minutes[st["step"]] = step_minutes.get(st["step"], 0.0) + st["minutes"]

    by_step: dict[int, list[dict[str, Any]]] = {}
    for a in job.get("actions") or []:
        step = _ACTION_KIND_TO_STEP.get(a.get("kind"), 1)
        by_step.setdefault(step, []).append(a)

    path: list[dict[str, Any]] = []
    for step in sorted(set(by_step) | set(step_minutes)):
        acts = by_step.get(step) or []
        what = "; ".join(a.get("text", "") for a in acts) or shop_mod.STEP_LABELS.get(step, f"step {step}")
        result = "; ".join((a.get("ref") or {}).get("label") or a.get("kind", "") for a in acts)
        minutes = round(step_minutes[step], 1) if step in step_minutes else None
        path.append({"step": step, "what_was_done": what, "result": result, "minutes": minutes})

    total_minutes: Optional[float] = round(sum(step_minutes.values()), 1) if step_minutes else None
    if total_minutes is None:
        total_minutes = _minutes_between(job.get("opened_at", ""), job.get("closed_at", ""))
    return path, total_minutes


def _outcome_and_verification(vin: str, job: dict[str, Any]) -> tuple[str, Optional[str]]:
    """The visit's own sharper outcome (``released_unverified`` where the
    job only knows ``deferred``) if a linked visit exists, else the job's
    own outcome; plus a ``verified_by`` string only when the visit's
    release actually carried ``release.verified=True`` -- never guessed
    from the job alone."""
    from . import shop as shop_mod
    outcome = job.get("outcome") or "deferred"
    verified_by = None
    visit = next((v for v in shop_mod.load(vin) if v.get("job_id") == job.get("id")), None)
    if visit:
        if visit.get("outcome"):
            outcome = visit["outcome"]
        release = visit.get("release") or {}
        if release.get("verified"):
            verified_by = f"dossier verified at release ({visit.get('out_at')})"
    return outcome, verified_by


def case_from_job(vin: str, job_id: str) -> dict[str, Any]:
    """Build a Case from one closed (or still-open) job, pulling in the
    real shop timing, parts ledger, tool-usage and symptom records that sit
    alongside it. Raises ``ValueError`` if the job doesn't exist or isn't
    this VIN's."""
    from . import jobs as jobs_mod, platform as platform_mod
    job = jobs_mod.get(job_id)
    if job is None or job.get("vin") != vin:
        raise ValueError(f"no job {job_id!r} for vin {vin!r}")

    codes = _codes_from_job(job)
    families = _families_for_codes(codes)
    hypotheses = [
        {"text": h.get("text", ""), "final_status": h.get("status", "open"),
         "key_evidence": [e.get("label", "") for e in
                         (h.get("evidence_for") or []) + (h.get("evidence_against") or [])
                         if isinstance(e, dict) and e.get("label")]}
        for h in job.get("hypotheses") or []
    ]
    path, total_minutes = _path_and_minutes(vin, job)
    tools, tool_pitfalls = _tools_and_pitfalls(vin, job_id)
    outcome, verified_by = _outcome_and_verification(vin, job)
    repairs = [a.get("text", "") for a in job.get("actions") or [] if a.get("kind") == "repair"]

    pitfalls = list(tool_pitfalls)
    for h in job.get("hypotheses") or []:
        if h.get("status") == "refuted" and h.get("text"):
            pitfalls.append(f"ruled out: {h['text']}")

    return {
        "id": f"case-{job_id}",
        "vin": vin,
        "model": platform_mod.model_for_vin(vin),
        "families": families,
        "codes": codes,
        "complaint": job.get("complaint", ""),
        "symptoms_summary": _symptoms_summary(vin, job),
        "hypotheses": hypotheses,
        "path": path,
        "fixes_that_worked": repairs if outcome == "fixed" else [],
        "fixes_that_did_not": repairs if outcome == "not_fixed" else [],
        "parts_used": _parts_used(vin, job),
        "tools": tools,
        "pitfalls": pitfalls,
        "outcome": outcome,
        "verified_by": verified_by,
        "opened": job.get("opened_at"),
        "closed": job.get("closed_at"),
        "total_minutes": total_minutes,
        "synthetic_from_logs": False,
    }


def record_case(vin: str, job_id: str) -> dict[str, Any]:
    """Build a Case from this job and append it to the store (idempotent --
    a case already on file for this job id is returned as-is, not
    duplicated).

    This is the hook ``mes.jobs.close`` should call on every close, so a
    case lands the moment a job finishes. It is **not** wired there: this
    task's scope excludes editing ``mes/jobs.py`` (and
    ``cuore/services/jobs_bridge.py``, which is the other place a close
    passes through). Until one of those calls this function, cases from
    real jobs only appear when something else calls ``record_case``
    explicitly (e.g. a script, or a future change to either of those two
    files by whoever owns them).
    """
    case = case_from_job(vin, job_id)
    if any(r.get("id") == case["id"] for r in _raw_records()):
        return case
    _append(case)
    return case


def _synthetic_evap_case(vin: str = VIN_STELVIO) -> dict[str, Any]:
    """The seed case for this project's own Stelvio when no Job record
    exists yet: built from the EVAP diagnosis dossier (memory
    ``project_stelvio_evap.md``) instead of ``mes.jobs`` -- three smoke
    tests came back sealed, every EVAP part the fault tree named was
    replaced, and P0440 returned after every clear; the verdict on file is
    an ECM calibration issue (TSB 18-030-17), never independently verified.
    Labelled ``synthetic_from_logs=True`` so nobody mistakes this for a
    job-derived case.
    """
    from . import platform as platform_mod
    model = platform_mod.model_for_vin(vin)
    return {
        "id": f"case-synthetic-{vin}",
        "vin": vin,
        "model": model if model != platform_mod.UNKNOWN else "stelvio",
        "families": ["evap"],
        "codes": ["P0440", "P0441", "P0455", "P0456"],
        "complaint": "CEL, EVAP codes",
        "symptoms_summary": "mechanic reported drives_normally -- no symptom driver could feel",
        "hypotheses": [
            {"text": "EVAP leak somewhere in the purge/vent/canister circuit",
             "final_status": "refuted",
             "key_evidence": ["3 clean smoke tests (system sealed)",
                             "EVAP parts replaced, P0440 returned after clear"]},
            {"text": "ECM calibration issue, not a physical leak (TSB 18-030-17)",
             "final_status": "open",
             "key_evidence": ["codes return after every clear despite a sealed, "
                             "parts-replaced system"]},
        ],
        "path": [
            {"step": 3, "what_was_done": "smoke test x3 (recirc line, purge/vent, canister)",
             "result": "sealed, no leak found each time", "minutes": None},
            {"step": 5, "what_was_done": "replaced EVAP-related parts per fault tree",
             "result": "P0440 returned after clear", "minutes": None},
        ],
        "fixes_that_worked": [],
        "fixes_that_did_not": ["replacing EVAP parts (purge/vent/canister circuit)"],
        "parts_used": [],
        "tools": {"used": ["smoke machine"], "flagged_wrong": [], "bought": []},
        "pitfalls": ["a sealed system with 3 clean smoke tests still returned P0440 after "
                    "every clear -- the leak hypothesis was exhausted before the ECM "
                    "calibration one (TSB 18-030-17) was tried"],
        "outcome": "not_fixed",
        "verified_by": None,
        "opened": None,
        "closed": None,
        "total_minutes": None,
        "synthetic_from_logs": True,
    }


def seed_default(vin: str = VIN_STELVIO) -> dict[str, Any]:
    """Make sure this VIN has at least one case on record, so the next
    Stelvio with the same fault has somewhere to start from. Idempotent: if
    a case for this VIN is already on file, returns the newest one
    untouched. Otherwise builds a case from this VIN's newest closed job if
    one exists, else seeds the synthetic dossier case
    (``synthetic_from_logs=True``)."""
    existing = [r for r in _raw_records() if r.get("vin") == vin]
    if existing:
        return existing[-1]
    from . import jobs as jobs_mod
    closed = [j for j in jobs_mod.load(vin) if j.get("status") == "closed"]
    case = case_from_job(vin, closed[-1]["id"]) if closed else _synthetic_evap_case(vin)
    _append(case)
    return case


# --- matching and prefill ----------------------------------------------------


def match(vin: str, codes: list[str]) -> list[dict[str, Any]]:
    """Prior cases for this VIN's model (never this VIN's own cases -- a
    "prior" case means a different car), ranked by: outcome
    fixed-and-verified first, then code overlap, then family overlap. Each
    result carries ``similarity`` (code-overlap ratio), ``code_overlap``,
    ``family_overlap`` and a ``what_to_expect`` sentence worded "on the
    last <model> with these codes ..." -- never claiming this car's fix is
    proven, only reporting what a prior one did.

    Returns ``[]`` for a model this module has no sourced cases for yet --
    never a guess across models.
    """
    from . import platform as platform_mod, systems as systems_mod
    model = platform_mod.model_for_vin(vin)
    if not model or model == platform_mod.UNKNOWN:
        return []
    subject = model[:1].upper() + model[1:]

    given = {c.strip().upper() for c in (codes or []) if c.strip()}
    given_families: set[str] = set()
    for c in given:
        for row in systems_mod.systems_for_code(c):
            if row.get("role") == "primary" and row.get("system") != "UNKNOWN":
                given_families.add(row["system"])

    scored: list[tuple[int, int, int, dict[str, Any]]] = []
    for case in load(model=model):
        if case.get("vin") == vin:
            continue
        case_codes = {c.upper() for c in case.get("codes") or []}
        overlap = len(given & case_codes)
        fam_overlap = len(given_families & set(case.get("families") or []))
        verified_rank = 1 if case.get("outcome") == "fixed" and case.get("verified_by") else 0
        scored.append((verified_rank, overlap, fam_overlap, case))
    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)

    out = []
    for verified_rank, overlap, fam_overlap, case in scored:
        case_codes = {c.upper() for c in case.get("codes") or []}
        union = len(given | case_codes) or 1
        similarity = round(overlap / union, 2)
        verified_clause = (f", verified ({case['verified_by']})" if case.get("verified_by")
                          else ", not independently verified")
        what = (f"On the last {subject} with these codes: outcome was "
               f"{case.get('outcome')}{verified_clause}.")
        out.append({**case, "similarity": similarity, "code_overlap": overlap,
                   "family_overlap": fam_overlap, "what_to_expect": what})
    return out


def prefill(vin: str, codes: list[str]) -> dict[str, Any]:
    """A suggested starting point for a new job on this VIN, built from the
    single best-matching prior case (``match``'s top result), never
    asserted as this car's answer: suggested hypotheses (prior text, prior
    final_status, key evidence), an ordered path with each step's prior
    minutes, tools to have ready (merged with this shop's current
    have/not_available status via ``mes.tool_usage.have_status``), parts
    likely needed, known pitfalls, and total expected minutes.

    Returns an honest empty prefill (not an error) when no prior case
    matches.
    """
    from . import platform as platform_mod, tool_usage as tool_usage_mod
    model = platform_mod.model_for_vin(vin)
    subject = model[:1].upper() + model[1:] if model and model != platform_mod.UNKNOWN else "car"

    matches = match(vin, codes)
    if not matches:
        return {
            "vin": vin, "model": model, "matched_case": None, "similarity": None,
            "summary": f"no prior {subject} case on file for these codes yet",
            "hypotheses": [], "path": [], "tools": [], "parts": [],
            "pitfalls": [], "expected_minutes": None,
        }

    best = matches[0]
    hypotheses = [
        {"text": h.get("text", ""), "prior_final_status": h.get("final_status", "open"),
         "key_evidence": h.get("key_evidence") or []}
        for h in best.get("hypotheses") or []
    ]
    path = [
        {"step": p.get("step"), "what_was_done": p.get("what_was_done", ""),
         "expected_minutes": p.get("minutes")}
        for p in best.get("path") or []
    ]
    tools = [{"tool": name, "have": tool_usage_mod.have_status(name)}
            for name in (best.get("tools") or {}).get("used") or []]

    return {
        "vin": vin, "model": model, "matched_case": best.get("id"),
        "similarity": best.get("similarity"), "summary": best.get("what_to_expect"),
        "hypotheses": hypotheses, "path": path, "tools": tools,
        "parts": best.get("parts_used") or [], "pitfalls": best.get("pitfalls") or [],
        "expected_minutes": best.get("total_minutes"),
    }


__all__ = ["OUTCOMES", "VIN_STELVIO", "state_dir", "store_path", "load", "get",
          "case_from_job", "record_case", "seed_default", "match", "prefill"]
