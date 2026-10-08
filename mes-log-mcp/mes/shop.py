"""One car at a time: the visit register around a Job, from intake to
release.

Where :mod:`mes.jobs` is the thread tying one visit's diagnostic reasoning
together, this module is the thread tying that visit to a car physically in
the shop -- when it came in, who's on it, how long each diagnostic step
actually took, and how it went back out.

CUORE advises and records here; it does not manage. Release never blocks on
an unmet checklist item -- it shows the mechanic the evidence for each item
(verification in particular is derived from the dossier verdict, never a
box the mechanic ticks) and lets him release with one tap, recording
whatever reason he gives for releasing a car that was not yet verified.

Same append-only JSONL convention as :mod:`mes.jobs` -- same state directory
candidates (``CUORE_STATE_DIR``, else ``%PROGRAMDATA%\\cuore``, else
``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``), independent of ``cuore`` so
``mes`` never imports it. History is never rewritten; four record shapes
share one file, distinguished by ``op``:

* ``intake``      -- {op, id, at, vin, vehicle, complaint, technician, job_id}
* ``step_start``  -- {op, visit_id, at, step}
* ``step_end``    -- {op, visit_id, at, step, minutes}
* ``release``     -- {op, visit_id, at, release, reason?, outcome}

:func:`load`/:func:`get` fold these into the visit shape described in the
module's design doc: ``{id, vin, vehicle, in_at, out_at, technician,
complaint, status, job_id, outcome, step_times, release}``.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

STATUSES = ("in", "out")

#: WMI (VIN positions 1-4) -> make, decoded as the last-resort fallback when
#: a caller opens a visit with no name at all. This module stays independent
#: of ``cuore`` (see module docstring), so it has no access to the MES
#: corpus's own vehicle list or dossier identity -- those richer lookups
#: belong to ``cuore.services.shop_bridge.resolve_vehicle_name``, which is
#: what callers should normally pass in as ``vehicle``. This is just enough
#: to guarantee a known VIN is never recorded with no name at all. Model is
#: always reported as "UNKNOWN" -- never guessed.
_WMI_MAKES: dict[str, str] = {
    "ZASF": "Alfa Romeo",
    "ZN6": "Maserati",
    "ZN7": "Maserati",
}


def _decode_wmi(vin: str) -> str:
    vin = (vin or "").strip().upper()
    for prefix in sorted(_WMI_MAKES, key=len, reverse=True):
        if vin.startswith(prefix):
            return _WMI_MAKES[prefix]
    return ""


def _fallback_vehicle_name(vin: str) -> str:
    """Never "" for a non-empty VIN: a WMI-decoded make (model "UNKNOWN"),
    or, failing that, the VIN itself -- a visit must never carry no name at
    all once its VIN is known."""
    make = _decode_wmi(vin)
    return f"{make} UNKNOWN" if make else vin

#: The release checklist's recorded booleans -- shown with their evidence,
#: never a gate on release. ``notes`` rides alongside as free text.
#: ``verified`` is deliberately not here: it is never mechanic-ticked, only
#: derived from the dossier verdict (see :func:`release`).
RELEASE_CHECKS = ("report_printed", "labels_printed", "parts_logged",
                  "tools_reviewed")

#: Job stepper steps 1-7, same numbering as ``job.html``'s jump row --
#: 1 Complaint, 2 Scan & codes, 3 Tests & inspections, 4 Hypotheses,
#: 5 Actions, 6 Verify, 7 Outcome. Timing rides on these purely so the store
#: has it on file; no page currently surfaces it.
JOB_STEPS = (1, 2, 3, 4, 5, 6, 7)
STEP_LABELS = {
    1: "Complaint & symptoms", 2: "Scan & codes", 3: "Tests & inspections",
    4: "Hypotheses", 5: "Repair actions", 6: "Verify", 7: "Outcome & handover",
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
    return state_dir() / "shop_visits.jsonl"


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


def _new_visit(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rec["id"], "vin": rec["vin"], "vehicle": rec.get("vehicle") or "",
        "in_at": rec["at"], "out_at": None,
        "technician": rec.get("technician") or "",
        "complaint": rec.get("complaint") or "",
        "status": "in", "job_id": rec.get("job_id"), "outcome": None,
        "step_times": [],
        "release": {"verified": False, "report_printed": False,
                   "labels_printed": False, "parts_logged": False,
                   "tools_reviewed": False, "notes": ""},
    }


def _fold() -> dict[str, dict[str, Any]]:
    """Every record folded into current visit state, keyed by visit id, in
    the order visits were taken in. One bad/unknown-op line is skipped,
    never sinks the rest of the store -- same posture as ``mes.jobs._fold``."""
    visits: dict[str, dict[str, Any]] = {}
    for rec in _raw_records():
        op = rec.get("op")
        if op == "intake":
            vid = rec.get("id")
            if not vid or vid in visits:
                continue
            visits[vid] = _new_visit(rec)
            continue

        vid = rec.get("visit_id")
        visit = visits.get(vid) if vid else None
        if visit is None:
            continue

        if op == "step_start":
            visit["step_times"].append({
                "step": rec.get("step"), "started_at": rec["at"],
                "ended_at": None, "minutes": None,
            })
        elif op == "step_end":
            open_entry = next((s for s in reversed(visit["step_times"])
                              if s["step"] == rec.get("step") and s["ended_at"] is None),
                             None)
            if open_entry is None:
                continue
            open_entry["ended_at"] = rec["at"]
            open_entry["minutes"] = rec.get("minutes")
        elif op == "release":
            visit["release"] = rec.get("release") or visit["release"]
            visit["status"] = "out"
            visit["out_at"] = rec["at"]
            visit["outcome"] = rec.get("outcome")
    return visits


def _require_visit(visit_id: str) -> dict[str, Any]:
    visits = _fold()
    visit = visits.get(visit_id)
    if visit is None:
        raise ValueError(f"no visit with id {visit_id!r}")
    return visit


def _minutes_between(start: str, end: str) -> float:
    try:
        t0 = datetime.fromisoformat(start)
        t1 = datetime.fromisoformat(end)
    except ValueError:
        return 0.0
    return round((t1 - t0).total_seconds() / 60.0, 1)


# --- the public surface -----------------------------------------------------


def intake(vin: str, complaint: str = "", *, technician: str = "",
          vehicle: str = "") -> dict[str, Any]:
    """Start this car: register the visit and open a linked Job in one step.

    Imports :mod:`mes.jobs` lazily (not at module load) so this module can be
    unit-tested with a stubbed job store without importing the real one.
    """
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    vehicle = (vehicle or "").strip() or _fallback_vehicle_name(vin)
    from mes import jobs as jobs_mod
    job = jobs_mod.open(vin, technician=technician, complaint=complaint)
    rec = {"op": "intake", "id": uuid.uuid4().hex[:12],
          "at": datetime.now().isoformat(timespec="seconds"),
          "vin": vin, "vehicle": vehicle,
          "complaint": (complaint or "").strip(),
          "technician": (technician or "").strip(), "job_id": job["id"]}
    _append(rec)
    return _new_visit(rec)


def start_step(visit_id: str, step: int) -> dict[str, Any]:
    """Begin timing one job step (1-7). Store-only -- no page currently
    surfaces this; it exists so the data is on file if something later
    wants it. Any step already open for this visit with no end yet is left
    as-is -- :func:`end_step` closes the newest matching one."""
    if step not in JOB_STEPS:
        raise ValueError("step must be one of: " + ", ".join(map(str, JOB_STEPS)))
    _require_visit(visit_id)
    _append({"op": "step_start", "visit_id": visit_id,
            "at": datetime.now().isoformat(timespec="seconds"), "step": step})
    return _require_visit(visit_id)


def end_step(visit_id: str, step: int) -> dict[str, Any]:
    if step not in JOB_STEPS:
        raise ValueError("step must be one of: " + ", ".join(map(str, JOB_STEPS)))
    visit = _require_visit(visit_id)
    open_entry = next((s for s in reversed(visit["step_times"])
                      if s["step"] == step and s["ended_at"] is None), None)
    if open_entry is None:
        raise ValueError(f"no open timer for step {step} on visit {visit_id!r}")
    at = datetime.now().isoformat(timespec="seconds")
    minutes = _minutes_between(open_entry["started_at"], at)
    _append({"op": "step_end", "visit_id": visit_id, "at": at, "step": step,
            "minutes": minutes})
    return _require_visit(visit_id)


def release(visit_id: str, checks: dict[str, Any], *,
           dossier_verified: Optional[bool] = None,
           reason: Optional[str] = None,
           outcome: Optional[str] = None,
           codes_returned: Optional[list[str]] = None,
           verdict: Optional[str] = None) -> dict[str, Any]:
    """Release the car -- advises and records, never blocks. The checklist
    in :data:`RELEASE_CHECKS` is recorded as given; none of it gates release.

    ``dossier_verified`` is the ground truth for whether the repair is
    verified -- this module has no access to the dossier itself, so a
    caller (normally ``cuore.services.shop_bridge``) passes whether the
    car's dossier verdict is actually ``VERIFIED_CLEAN``. Correctness over
    speed: a mechanic cannot tick a box to make a car verified, only proof
    from the car does that. When the car is released without that proof,
    ``release.unverified_override`` records whatever ``reason`` the
    mechanic gave (may be empty -- a reason is recorded when given, never
    required), and the visit's outcome becomes ``"released_unverified"``
    instead of ``"fixed"``, for the dossier to show afterwards.

    Closes the linked Job (if it is still open) via :mod:`mes.jobs`. The
    Job's own outcome vocabulary (fixed | not_fixed | deferred) has no
    "released_unverified" entry, so that case closes the Job as
    ``deferred`` while the visit itself keeps the sharper outcome.
    """
    visit = _require_visit(visit_id)
    if visit["status"] == "out":
        raise ValueError(f"visit {visit_id!r} is already out")

    verified = bool(dossier_verified)
    release_state = {c: bool(checks.get(c)) for c in RELEASE_CHECKS}
    release_state["verified"] = verified
    release_state["notes"] = (checks.get("notes") or "").strip()
    reason = (reason or "").strip()
    at = datetime.now().isoformat(timespec="seconds")

    unverified_override = reason if not verified else None
    if unverified_override:
        release_state["unverified_override"] = unverified_override

    resolved_outcome = outcome or (
        "fixed" if verified else "released_unverified")
    job_outcome = "deferred" if resolved_outcome == "released_unverified" else resolved_outcome

    job_id = visit.get("job_id")
    if job_id:
        from mes import jobs as jobs_mod
        job = jobs_mod.get(job_id)
        if job is not None and job["status"] != "closed":
            try:
                jobs_mod.close(job_id, job_outcome, codes_returned=codes_returned,
                               verdict=verdict)
            except ValueError:
                pass  # already closed between the read above and here

    rec: dict[str, Any] = {"op": "release", "visit_id": visit_id, "at": at,
                           "release": release_state, "outcome": resolved_outcome}
    if reason:
        rec["reason"] = reason
    _append(rec)
    return _require_visit(visit_id)


def load(vin: str = "") -> list[dict[str, Any]]:
    """Every visit, oldest-in first, optionally filtered by VIN."""
    visits = sorted(_fold().values(), key=lambda v: v["in_at"])
    if vin:
        visits = [v for v in visits if v["vin"] == vin]
    return visits


def get(visit_id: str) -> Optional[dict[str, Any]]:
    return _fold().get(visit_id)


def current(vin: str) -> Optional[dict[str, Any]]:
    """The newest not-out visit for this VIN, or ``None``."""
    vin = (vin or "").strip()
    if not vin:
        return None
    open_visits = [v for v in load(vin) if v["status"] != "out"]
    return open_visits[-1] if open_visits else None


__all__ = ["STATUSES", "RELEASE_CHECKS", "JOB_STEPS", "STEP_LABELS",
          "state_dir", "store_path", "intake", "start_step",
          "end_step", "release", "load", "get", "current"]
