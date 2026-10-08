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
    """
    with _LOCK:
        data = _load()
        entry = data.setdefault(vin, {})
        entry[step_id] = {
            "done": bool(done),
            "done_at": datetime.now().isoformat(timespec="seconds") if done else None,
            "done_by": (by.strip() or None) if (done and by.strip()) else None,
            "outcome": (outcome or None) if done else None,
            "note": ((note or "").strip() or None) if done else None,
        }
        _save(data)
        return dict(entry[step_id])


__all__ = ["path", "get", "set_step"]
