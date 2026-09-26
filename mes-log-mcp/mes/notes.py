"""Technician notes: append-only context on anything cuore found.

The corpus and the dealer store answer "what happened"; this module answers
"what does the technician know about it that nothing else captured" --
"purge valve replaced by me 2026-09-10", "this scan was taken right after a
battery disconnect", "smoke test done at 0.5 psi, no leak". Claude (and the
gate, and the fault tree) must see this or it is invisible context that only
lives in one person's head.

Append-only JSONL, same state directory :mod:`mes.dealer` writes to
(``CUORE_STATE_DIR``, else ``%PROGRAMDATA%\\cuore``, else
``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``) -- kept independent of
``cuore`` so ``mes`` never imports it, same reasoning as ``mes.dealer``.

History is never rewritten. Three record shapes share one file,
distinguished by ``op``:

* ``note``  -- {id, at, vin, target_kind, target_id, text, author, tags}
* ``edit``  -- {id, at, text} -- a new version of an existing note's text
* ``hide``  -- {id, at} -- marks a note hidden (soft delete)

:func:`load` folds these into the current view: latest text, prior versions
kept as ``history``, hidden notes dropped unless asked for.

``target_kind`` is one of:

* ``vehicle``     -- the car as a whole
* ``code``        -- a DTC, matched on its base code (``P0456`` matches a
                     note filed against ``P0456`` or ``P0456-00``)
* ``log``         -- one MES log file, by name
* ``observation`` -- one live-link observation, by its timestamp
* ``dealer``      -- one dealer (wiTECH) result, by its timestamp
* ``tree_step``   -- one fault-tree step, ``target_id`` like ``evap-leak:E7``
* ``component``   -- a free-text part name, e.g. ``ESIM``
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import knowledge

TARGET_KINDS = ("vehicle", "code", "log", "observation", "dealer",
                "tree_step", "component")

MAX_TEXT = 4000


def state_dir() -> Path:
    """Mirror ``mes.dealer.state_dir()``: same candidates, first writable wins."""
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
    return state_dir() / "notes.jsonl"


def _target_key(target_kind: str, target_id: str) -> str:
    """The value ``target_id`` is matched on for this kind. Codes match on
    their base code so a note filed against ``P0456`` also attaches to a
    ``P0456-00`` occurrence, and vice versa."""
    if target_kind == "code":
        return knowledge.base_code(target_id)
    return target_id


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


def _find_note(note_id: str) -> Optional[dict[str, Any]]:
    for rec in _raw_records():
        if rec.get("op") == "note" and rec.get("id") == note_id:
            return rec
    return None


def add(vin: str, text: str, target_kind: str, target_id: str = "",
        author: str = "technician", tags: Optional[list[str]] = None) -> dict[str, Any]:
    """Validate, stamp and append one note. Returns the stored record."""
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text must be {MAX_TEXT} characters or fewer")
    target_kind = (target_kind or "").strip().lower()
    if target_kind not in TARGET_KINDS:
        raise ValueError("target_kind must be one of: " + ", ".join(TARGET_KINDS))
    target_id = (target_id or "").strip()

    entry = {
        "op": "note",
        "id": uuid.uuid4().hex[:12],
        "at": datetime.now().isoformat(timespec="seconds"),
        "vin": vin,
        "target_kind": target_kind,
        "target_id": target_id,
        "text": text,
        "author": (author or "technician").strip() or "technician",
        "tags": [str(t).strip() for t in (tags or []) if str(t).strip()],
    }
    _append(entry)
    return entry


def edit(id: str, text: str) -> dict[str, Any]:
    """Append an amendment with new text for note ``id``. Never rewrites history."""
    note_id = (id or "").strip()
    if not note_id:
        raise ValueError("id is required")
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text must be {MAX_TEXT} characters or fewer")
    if _find_note(note_id) is None:
        raise ValueError(f"no note with id {note_id!r}")
    entry = {"op": "edit", "id": note_id,
             "at": datetime.now().isoformat(timespec="seconds"), "text": text}
    _append(entry)
    return entry


def hide(id: str) -> dict[str, Any]:
    """Append a hide amendment for note ``id``. Never rewrites history."""
    note_id = (id or "").strip()
    if not note_id:
        raise ValueError("id is required")
    if _find_note(note_id) is None:
        raise ValueError(f"no note with id {note_id!r}")
    entry = {"op": "hide", "id": note_id,
             "at": datetime.now().isoformat(timespec="seconds")}
    _append(entry)
    return entry


def load(vin: str = "", target_kind: Optional[str] = None,
         target_id: str = "", include_hidden: bool = False) -> list[dict[str, Any]]:
    """Notes resolved to their current text, oldest-created first.

    Each returned dict carries ``text``/``at`` as the CURRENT version, plus
    ``history`` (prior versions, oldest first, each ``{"text", "at"}``) and
    ``hidden``. Amendments to a note this filter would otherwise exclude
    (unknown id, e.g. from a corrupt line) are silently skipped rather than
    raising -- one bad line must not sink every note in the store.
    """
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for rec in _raw_records():
        rid = rec.get("id")
        op = rec.get("op")
        if not rid or op not in ("note", "edit", "hide"):
            continue
        if op == "note":
            if rid in by_id:
                continue  # duplicate id -- keep the first
            note = dict(rec)
            note["history"] = []
            note["hidden"] = False
            by_id[rid] = note
            order.append(rid)
        elif op == "edit":
            note = by_id.get(rid)
            if note is None:
                continue
            note["history"].append({"text": note["text"], "at": note["at"]})
            note["text"] = rec.get("text", note["text"])
            note["edited_at"] = rec.get("at")
        elif op == "hide":
            note = by_id.get(rid)
            if note is None:
                continue
            note["hidden"] = True

    wanted_key = _target_key(target_kind, target_id) if (target_kind and target_id) else target_id

    out: list[dict[str, Any]] = []
    for rid in order:
        note = by_id[rid]
        if note["hidden"] and not include_hidden:
            continue
        if vin and note.get("vin") != vin:
            continue
        if target_kind and note.get("target_kind") != target_kind:
            continue
        if target_id:
            if note.get("target_kind") == "code":
                if _target_key("code", note.get("target_id", "")) != wanted_key:
                    continue
            elif note.get("target_id") != target_id:
                continue
        out.append(note)
    return out


__all__ = ["TARGET_KINDS", "MAX_TEXT", "state_dir", "store_path",
          "add", "edit", "hide", "load"]
