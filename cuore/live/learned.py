"""Persistence for DID mappings learned by watching wiTECH's own traffic.

Same JSON-file-beside-lock-file pattern as :mod:`store` (see that module for
why: Phase 3 replaces this with the spec's SQLite store, the interface
stays). Kept separate from ``store.py`` because these entries are a
different kind of fact -- not an address this tool confirmed by asking the
car, but a DID/field meaning inferred from correlating wiTECH's requests
against what a technician read off its screen. Every entry is stamped with
that provenance and it is never upgraded to a stronger confidence here.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir

_LOCK = threading.Lock()

#: The only confidence value this module ever writes.
CONFIDENCE = "learned from wiTECH capture"


def path() -> Path:
    return state_dir() / "learned_dids.json"


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


def _field_key(module_code: str, did: str, field: Optional[dict[str, Any]]) -> tuple[str, str, str]:
    return (module_code.upper(), did.upper(), json.dumps(field or {}, sort_keys=True))


def accept(vin: str, module_code: str, did: str, name: str, field: dict[str, Any],
          scale: Optional[float] = None, offset: Optional[float] = None,
          unit: Optional[str] = None, evidence: Optional[list[dict[str, Any]]] = None
          ) -> dict[str, Any]:
    """Record an accepted mapping for ``vin``.

    ``field`` is the byte-level location within the DID's payload, e.g.
    ``{"offset": 2, "bit": 0}`` or ``{"offset": 0, "width": "byte"}`` --
    whatever :func:`learn.correlate` reported for the chosen candidate.
    Replaces any prior *accepted* entry for the same ``(module_code, did,
    field)`` on this VIN; rejected entries and other fields are kept.
    """
    entry = {
        "module": module_code.upper(), "did": did.upper(), "name": name, "field": field,
        "scale": scale, "offset": offset, "unit": unit, "evidence": evidence or [],
        "confidence": CONFIDENCE, "status": "accepted",
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    key = _field_key(module_code, did, field)
    with _LOCK:
        data = _load()
        entries = data.setdefault(vin, [])
        entries[:] = [e for e in entries
                     if not (e.get("status") == "accepted"
                             and _field_key(e.get("module", ""), e.get("did", ""),
                                            e.get("field")) == key)]
        entries.append(entry)
        _save(data)
    return entry


def reject(vin: str, module_code: str, did: str, field: Optional[dict[str, Any]] = None,
          reason: str = "") -> dict[str, Any]:
    """Record that a candidate mapping was looked at and turned down."""
    entry = {
        "module": module_code.upper(), "did": did.upper(), "field": field,
        "confidence": CONFIDENCE, "status": "rejected", "reason": reason,
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    with _LOCK:
        data = _load()
        data.setdefault(vin, []).append(entry)
        _save(data)
    return entry


def learned(vin: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
    """All learned entries, or just ``vin``'s (``{vin: [...]}``, ``[]`` if none)."""
    with _LOCK:
        data = _load()
    if vin is None:
        return data
    return {vin: data.get(vin, [])}


__all__ = ["path", "accept", "reject", "learned", "CONFIDENCE"]
