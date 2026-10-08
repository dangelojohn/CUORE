"""Shop-visible checklist state: has a family-finding step been ticked off.

Same shape of small store as ``cuore.live.store`` (one JSON file, guarded by
a lock, read-modify-write) but kept in its own module rather than added to
that one: this is dossier state (what has a technician done about an open
finding), not live-link state (what the car itself has said).

``vin -> step_id -> {done, done_at, done_by}``. Shared across whoever reads
this state dir, not per-browser -- ticking a step off on the shop tablet must
show up on the office terminal too, which is why this is a file beside
``addresses.json`` and not ``localStorage``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import state_dir

_LOCK = threading.Lock()


def path() -> Path:
    return state_dir() / "checklists.json"


def _load() -> dict[str, Any]:
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict[str, Any]) -> None:
    try:
        path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def get(vin: str) -> dict[str, Any]:
    """``{step_id: {done, done_at, done_by, outcome, note}}`` recorded for
    this VIN. ``outcome``/``note`` are ``None`` on an entry recorded before
    the bench's outcome capture landed, or on a step that was undone."""
    with _LOCK:
        return dict(_load().get(vin, {}))


def set_step(vin: str, step_id: str, done: bool, by: str = "",
            outcome: str | None = None, note: str | None = None) -> dict[str, Any]:
    """Record one step's state. Returns the stored entry for that step.

    ``outcome`` is one of ``"ok"``/``"fault_found"``/``"skipped"``, or
    ``None`` -- the bench page's own evidence gate: a job whose end state is
    an evidence gate cannot be told apart from "ticked and ignored" with a
    bare done/undone flag. Un-ticking a step (``done=False``, the bench's
    "undo") clears both, the same way ``done_at``/``done_by`` already reset
    to ``None`` -- an undone step carries no stale outcome.

    Leaves any ``result``/``reason``/``value``/``unit``/``hypothesis_id``/
    ``media_ids`` already recorded by :func:`set_result` on this step alone
    -- the bench's simple done/outcome toggle and the job page's test-result
    sheet (JOB_UX_FIXES_2026-10-08.md #3) are two different controls over
    the same per-step entry, and neither one's write should erase what the
    other recorded.
    """
    with _LOCK:
        data = _load()
        entry = data.setdefault(vin, {})
        prev = dict(entry.get(step_id) or {})
        entry[step_id] = {
            **prev,
            "done": bool(done),
            "done_at": datetime.now().isoformat(timespec="seconds") if done else None,
            "done_by": (by.strip() or None) if (done and by.strip()) else None,
            "outcome": (outcome or None) if done else None,
            "note": ((note or "").strip() or None) if done else None,
        }
        _save(data)
        return dict(entry[step_id])


#: Step 6 "result sheet" outcomes (JOB_UX_FIXES_2026-10-08.md #3) -- distinct
#: from the bench's own ok/fault_found/skipped ``outcome`` above. Only
#: pass/fail count as hypothesis test evidence (see
#: ``cuore.services.jobs_bridge.add_test_evidence``).
RESULTS = ("pass", "fail", "inconclusive", "not_possible")


def set_result(vin: str, step_id: str, result: str | None, *, reason: str = "",
               value: float | None = None, unit: str = "",
               hypothesis_id: str | None = None,
               media_ids: list[str] | None = None, by: str = "") -> dict[str, Any]:
    """Record a test result on one checklist row.

    Layered onto the same per-step entry :func:`set_step` writes, merging in
    rather than overwriting -- a result never clears an outcome/note
    :func:`set_step` already recorded, and vice versa. A row with a non-None
    ``result`` counts as done in its own right: a tech who records pass/fail
    has, in fact, done the step, so this also flips ``done``/``done_at``
    (and ``done_by`` when ``by`` is given) the same way ticking the box
    would -- but setting ``result=None`` (clearing a result) never un-does a
    step that was otherwise already ticked.
    """
    if result is not None and result not in RESULTS:
        raise ValueError("result must be one of: " + ", ".join(RESULTS) + ", or None")
    with _LOCK:
        data = _load()
        entry = data.setdefault(vin, {})
        prev = dict(entry.get(step_id) or {})
        now = datetime.now().isoformat(timespec="seconds")
        prev["result"] = result
        prev["reason"] = (reason or "").strip() or None
        prev["value"] = value
        prev["unit"] = (unit or "").strip() or None
        prev["hypothesis_id"] = (hypothesis_id or "").strip() or None
        prev["media_ids"] = list(media_ids) if media_ids else []
        if result is not None:
            prev["done"] = True
            prev["done_at"] = now
            if by.strip():
                prev["done_by"] = by.strip()
            else:
                prev.setdefault("done_by", None)
        entry[step_id] = prev
        _save(data)
        return dict(entry[step_id])


__all__ = ["path", "get", "set_step", "set_result", "RESULTS"]
