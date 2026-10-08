"""Per-sheet print-offset calibration for the label-printing feature.

A given printer's own feed/registration error on a given Avery sheet is
consistent run to run, so rather than re-measuring it on every print, a
mechanic measures it once -- print the test grid
(:func:`cuore.labels.render.generate_test_grid_pdf`), measure the real-world
offset in mm against a real sheet, enter it on the labels page's
"Calibrate" panel -- and every later render for that exact
``(template_id, printer_name)`` pair applies it automatically. Still
overridable per print: :mod:`cuore.services.labels_bridge` only falls back
to the saved calibration when the caller does not pass an explicit offset.

Same JSON-file-beside-lock pattern as :mod:`cuore.live.learned` (see that
module's docstring for the rationale -- a future store swap changes the
backing, not this interface).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir

_LOCK = threading.Lock()


def path() -> Path:
    return state_dir() / "label_calibration.json"


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


def _key(template_id: str, printer_name: str) -> str:
    return f"{(template_id or '').strip()}::{(printer_name or '').strip()}"


def save(template_id: str, printer_name: str, offset_x_mm: float, offset_y_mm: float,
        note: str = "") -> dict[str, Any]:
    """Record (or replace) the calibration for this ``(template_id,
    printer_name)`` pair -- the mechanic's own measurement off a printed
    test grid. Raises ``ValueError`` if either id is blank."""
    template_id = (template_id or "").strip()
    printer_name = (printer_name or "").strip()
    if not template_id:
        raise ValueError("template_id is required")
    if not printer_name:
        raise ValueError("printer_name is required")
    entry = {
        "template_id": template_id,
        "printer_name": printer_name,
        "offset_x_mm": float(offset_x_mm),
        "offset_y_mm": float(offset_y_mm),
        "note": (note or "").strip(),
        "verified_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _LOCK:
        data = _load()
        data[_key(template_id, printer_name)] = entry
        _save(data)
    return entry


def get(template_id: str, printer_name: str) -> Optional[dict[str, Any]]:
    """The saved calibration for this ``(template_id, printer_name)`` pair,
    or ``None`` if it has never been calibrated (including when
    ``printer_name`` is blank -- there is nothing to key on)."""
    if not (printer_name or "").strip():
        return None
    with _LOCK:
        data = _load()
    return data.get(_key(template_id, printer_name))


def for_template(template_id: str) -> list[dict[str, Any]]:
    """Every calibration saved for ``template_id``, across printers --
    newest first, for display (e.g. "calibrated on <printer> <date>")."""
    template_id = (template_id or "").strip()
    with _LOCK:
        data = _load()
    rows = [e for e in data.values() if e.get("template_id") == template_id]
    rows.sort(key=lambda e: e.get("verified_at", ""), reverse=True)
    return rows


def all_calibrations() -> dict[str, Any]:
    """Every saved calibration, keyed internally -- for the API/debug view."""
    with _LOCK:
        return _load()


__all__ = ["path", "save", "get", "for_template", "all_calibrations"]
