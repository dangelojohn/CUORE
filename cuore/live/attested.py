"""Attested mechanic inputs: append-only JSONL log of what a mechanic typed
into an open-square UNKNOWN marker on a system page (a measurement, a
source citation, or a photo pointer) -- phase 3 of the Systems dive-in
(see ``docs/research/SYSTEMS_DIVE_IN_PLAN_2026-10-08.md``).

Same JSON-lines-under-``CUORE_STATE_DIR`` posture as
``mes.electrical_inspections`` / ``cuore.live.learned`` (see either for
why: one append-only file, one lock, never rewritten).

**These rows are not evidence.** A value a mechanic typed on the page is a
single, unverified claim -- it never becomes a "the car measured this"
fact and it never enters the evidence gate (``mes.evidence`` / whatever
module scores a hypothesis's proof) as a car measurement. The only thing
this module lets a caller do with a row is *display* it next to the
UNKNOWN marker it was filed against, stamped "Mechanic input <date> by
<who>" at confidence ``SINGLE-SOURCE (mechanic)`` -- a human claim, kept
separate from, and never overwriting, the knowledge-table value that is
still UNKNOWN. See ``cuore/web/templates/system.html`` for the footnote
that says the same thing in the UI, and
``cuore/services/system_detail_bridge.py`` for the one place this module
is read from.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir

_LOCK = threading.Lock()

#: The only three things a mechanic can file against an UNKNOWN marker:
#: a measured value, a citation for where a spec came from, or a photo
#: (the value is then a media id already uploaded via the media library).
KINDS = ("measured", "source", "photo-media-id")


def path() -> Path:
    return state_dir() / "attested.jsonl"


def _append(entry: dict[str, Any]) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _raw_records() -> list[dict[str, Any]]:
    p = path()
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
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def add(vin: str, system: str, fact_key: str, value: str, *, unit: str = "",
        source: str = "", by: str = "mechanic", kind: str = "measured"
        ) -> dict[str, Any]:
    """Record one attested input. Raises ``ValueError`` on a bad ``kind``
    or a missing required field -- the API layer turns that into a 400.

    Confidence is always ``SINGLE-SOURCE (mechanic)`` and is never
    upgraded here: this is one person's claim, not a corroborated fact.
    """
    vin = (vin or "").strip()
    system = (system or "").strip()
    fact_key = (fact_key or "").strip()
    value = (value or "").strip()
    kind = (kind or "").strip()
    if not vin:
        raise ValueError("vin is required")
    if not system:
        raise ValueError("system is required")
    if not fact_key:
        raise ValueError("fact_key is required")
    if not value:
        raise ValueError("value is required")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, got {kind!r}")

    entry = {
        "id": uuid.uuid4().hex, "vin": vin, "system": system, "fact_key": fact_key,
        "value": value, "unit": (unit or "").strip(), "source": (source or "").strip(),
        "by": (by or "mechanic").strip() or "mechanic", "kind": kind,
        "confidence": "SINGLE-SOURCE (mechanic)",
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    with _LOCK:
        _append(entry)
    return entry


def for_fact(vin: str, system: str, fact_key: str) -> list[dict[str, Any]]:
    """Every attested input filed against one fact, newest first."""
    with _LOCK:
        rows = _raw_records()
    hits = [r for r in rows if r.get("vin") == vin and r.get("system") == system
           and r.get("fact_key") == fact_key]
    hits.sort(key=lambda r: r.get("at") or "", reverse=True)
    return hits


def latest(vin: str, system: str, fact_key: str) -> Optional[dict[str, Any]]:
    hits = for_fact(vin, system, fact_key)
    return hits[0] if hits else None


def latest_by_fact(vin: str, system: str) -> dict[str, dict[str, Any]]:
    """``{fact_key: latest row}`` for every fact a mechanic has attested to
    on this VIN/system -- the one call ``system_detail_bridge`` needs to
    decorate a whole page of UNKNOWN markers in one pass."""
    with _LOCK:
        rows = _raw_records()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("vin") != vin or r.get("system") != system:
            continue
        fk = r.get("fact_key") or ""
        if not fk:
            continue
        if fk not in out or (r.get("at") or "") >= (out[fk].get("at") or ""):
            out[fk] = r
    return out


__all__ = ["path", "add", "for_fact", "latest", "latest_by_fact", "KINDS"]
