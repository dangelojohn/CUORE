"""HTTP face of :mod:`mes.feedback` -- the mechanic's corrections, questions,
confirmations, input and disagreement on facts cuore shows.

Kept as its own bridge module rather than folded into
``cuore.services.mes_bridge`` so this feature's surface can be reviewed and
tested on its own; it follows the same translate-ValueError-to-BadRequest
convention ``mes_bridge`` uses for ``mes.notes``.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from .errors import BadRequest

from mes import feedback as feedback_mod  # noqa: E402


def add(vin: str, kind: str, target: dict[str, Any], text: str = "",
       author: str = "technician", media_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Record one piece of mechanic feedback. Raises BadRequest on invalid input."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return feedback_mod.add(vin, kind, target, text=text, author=author,
                                media_ids=media_ids)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def load(vin: str, status: str = "") -> dict[str, Any]:
    """Feedback rows for this VIN, oldest first, optionally filtered by status."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return {"vin": vin, "feedback": feedback_mod.load(vin, status=status or None)}
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def answer(id: str, text: str, by: str = "claude") -> dict[str, Any]:
    """Answer one feedback row. Moves it to status "answered"."""
    try:
        return feedback_mod.answer(id, by, text)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def set_status(id: str, status: str, note: str = "") -> dict[str, Any]:
    """Set a feedback row's status. ``note`` is optional context."""
    try:
        return feedback_mod.set_status(id, status, note=note or None)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def counts(vin: str, targets: list[str]) -> dict[str, Any]:
    """Per-target tallies (open/answered/confirms/corrections) for the given
    ``page|section|item`` keys."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return {"vin": vin, "counts": feedback_mod.counts(vin, targets)}


__all__ = ["add", "load", "answer", "set_status", "counts"]
