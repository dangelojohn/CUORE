"""Bridge from the prototype procedure screens to the dry-run harness.

The prototype modules must not import anything under the live layer (their own test enforces it), so the one
import of ``procedure_dry_run`` lives here, as ``replay_bridge`` does for the CSV code. The dry run is offline:
real gate, real replay logic, an in-memory fake transport, no adapter (see ``cuore/live/procedure_dry_run.py``).

A capture file for a prototype procedure is ``<state dir>/procedure_captures/<proc>.json`` (a dict with
``frames``, ``bitrate``, ``name``, ``pre``, ``post``; see procedure_dry_run.load). No file -> None and the
prototype keeps its hand-written simulator.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

#: simulator fault -> scripted reply for the dry run, so the screen's fault buttons still do something.
FAULT_REPLIES: dict[str, dict[Any, Any]] = {
    "no_proof": {2: "nrc:22"},                 # the module refuses the actuation
    "ambiguous_proof": {"stop": "no_reply"},   # no stop acknowledgement
}


def capture_path(proc: str) -> Optional[Path]:
    try:
        from ..live.config import state_dir
        p = state_dir() / "procedure_captures" / f"{proc}.json"
        return p if p.is_file() else None
    except Exception:  # noqa: BLE001 -- no state dir = no capture
        return None


def report_for(proc: str, faults: set[str]) -> Optional[dict[str, Any]]:
    """dry_run report for ``proc`` if a capture exists (replies scripted from the sim faults), else None."""
    p = capture_path(proc)
    if p is None:
        return None
    from ..live import procedure_dry_run
    replies: dict[Any, Any] = {}
    for f in sorted(faults):
        replies.update(FAULT_REPLIES.get(f, {}))
    try:
        return procedure_dry_run.dry_run(str(p), fake_replies=replies or None)
    except Exception as e:  # noqa: BLE001 -- a bad capture file must not break the screen
        return {"gate": {"passed": False, "status": "failed", "reasons": [f"capture unreadable: {e}"]},
                "steps": [], "would_send": [], "would_send_text": "", "warnings": [], "verdict": "UNCLEAR",
                "verdict_line": f"Capture file {p.name} could not be read: {e}", "ran": False}
