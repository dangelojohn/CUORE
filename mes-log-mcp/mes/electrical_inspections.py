"""Electrical inspection records: append-only JSONL log of what a
technician actually found at one electrical element (fuse, ground,
connector...) on one vehicle.

Same posture and same state directory as :mod:`mes.notes` / :mod:`mes.dealer`
(``CUORE_STATE_DIR``, else ``%PROGRAMDATA%\\cuore``, else
``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``) -- kept independent of
``cuore`` so ``mes`` never imports it.

Rows: ``{id, vin, element, at, by, condition, note, media_ids}`` where
``condition`` is one of :data:`CONDITIONS`. History is never rewritten --
there is no edit/hide here (unlike notes), only new append-only findings;
:func:`latest` answers "what's the most recent finding at this element on
this VIN".
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

CONDITIONS = (
    "ok", "corroded", "chafed", "loose", "water", "repaired", "replaced",
    "not_found",
)


def state_dir() -> Path:
    """Mirror ``mes.notes.state_dir()``/``mes.dealer.state_dir()``: same
    candidates, first writable wins."""
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
    return state_dir() / "electrical_inspections.jsonl"


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


def add(vin: str, element: str, condition: str, by: str = "technician",
        note: str = "", media_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Validate, stamp and append one inspection record. Returns it."""
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    element = (element or "").strip()
    if not element:
        raise ValueError("element is required")
    condition = (condition or "").strip().lower()
    if condition not in CONDITIONS:
        raise ValueError("condition must be one of: " + ", ".join(CONDITIONS))

    entry = {
        "id": uuid.uuid4().hex[:12],
        "vin": vin,
        "element": element,
        "at": datetime.now().isoformat(timespec="seconds"),
        "by": (by or "technician").strip() or "technician",
        "condition": condition,
        "note": (note or "").strip(),
        "media_ids": [str(m).strip() for m in (media_ids or []) if str(m).strip()],
    }
    _append(entry)
    return entry


def load(vin: str = "", element: str = "") -> list[dict[str, Any]]:
    """All inspection records, optionally filtered, oldest first."""
    out = []
    for rec in _raw_records():
        if "id" not in rec or "element" not in rec:
            continue
        if vin and rec.get("vin") != vin:
            continue
        if element and rec.get("element") != element:
            continue
        out.append(rec)
    return out


def latest(vin: str, element: str) -> Optional[dict[str, Any]]:
    """The most recent inspection record for this VIN+element, or ``None``.

    ``load`` returns rows oldest first (insertion order). ``at`` has
    only second-level precision, so two adds in the same second tie --
    breaking ties by insertion order (last one wins) keeps this correct
    under ``max``'s left-to-right scan, which otherwise keeps the
    *first* of equal elements.
    """
    rows = load(vin=vin, element=element)
    if not rows:
        return None
    return max(enumerate(rows), key=lambda pair: (pair[1].get("at", ""), pair[0]))[1]


__all__ = ["CONDITIONS", "state_dir", "store_path", "add", "load", "latest"]
