"""Mechanic feedback: a correction, a question, a confirmation, extra input,
or a disagreement, pinned to one fact cuore showed on one page.

The whole point: the mechanic makes the decisions, not the tool. Whenever
cuore shows a fact -- a DTC on the dossier, a fault-tree step, a parameter on
a chart -- the mechanic must be able to correct it, ask about it, confirm it,
add context to it, or flag disagreement, and later see whatever answer came
back. This module is the record of that exchange.

Append-only JSONL, same state directory :mod:`mes.notes` writes to
(``CUORE_STATE_DIR``, else ``%PROGRAMDATA%\\cuore``, else
``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``) -- kept independent of
``cuore`` so ``mes`` never imports it, same reasoning as ``mes.notes``,
``mes.dealer`` and ``mes.symptoms``.

Feedback is ATTESTED input from a person, never a car measurement. It must
never be fed into :mod:`mes.verdict` (the evidence gate) as evidence -- same
rule as :mod:`mes.symptoms`.

``add`` appends one line; ``answer`` and ``set_status`` overwrite
the stored row's ``answer``/``status``/``applied_note`` fields and rewrite
the whole file, the same one-row-per-id model :mod:`mes.dealer` uses, chosen
here (over :mod:`mes.notes`'s append-only amendment log) because a feedback
row has exactly one current answer and one current status -- there is no
history of prior answers worth keeping distinct from the current one.

One record shape, keyed by ``id``:

    {id, vin, at, author, kind, target: {page, section, item, label}, text,
     media_ids, status, answer, applied_note}

``kind`` is one of: correction | question | confirm | input | disagree.
``status`` is one of: open | answered | applied | dismissed.
``target`` says what fact this is about: ``page`` is the cuore page/route,
``section`` and ``item`` narrow it further (both optional, default ""),
``label`` is the fact text itself, capped at 200 characters so a target
reads at a glance.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import paths

KINDS = ("correction", "question", "confirm", "input", "disagree")
STATUSES = ("open", "answered", "applied", "dismissed")

MAX_TEXT = 4000
MAX_LABEL = 200


from .paths import memo_state_dir as _memo_state_dir  # noqa: E402


@_memo_state_dir
def state_dir() -> Path:
    """Mirror ``mes.notes.state_dir()``: same candidates, first writable wins."""
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
            probe = d / f".write-test-{os.getpid()}-{threading.get_ident()}"  # per-thread: a shared name raced (one thread unlinked another's probe -> OSError -> wrong state dir)
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return d
        except OSError:
            continue
    return Path.cwd()


def store_path() -> Path:
    return state_dir() / "feedback.jsonl"


def _target_key(target: dict[str, Any]) -> str:
    """``page|section|item`` -- what a caller matches a target on in
    :func:`counts`. Missing section/item are empty, not omitted, so the key
    always has exactly two pipes."""
    return "{}|{}|{}".format(target.get("page", "") or "",
                             target.get("section", "") or "",
                             target.get("item", "") or "")


def _read_all() -> list[dict[str, Any]]:
    return paths.read_jsonl(store_path())


def _write_all(rows: list[dict[str, Any]]) -> None:
    """Replace the file atomically (temp file + rename): the old ``open("w")``
    truncated the store first, so a crash mid-write lost every row."""
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    for attempt in range(40):  # a reader holding the file open blocks the rename on Windows
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.05)


def _validate_target(target: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    page = str(target.get("page", "")).strip()
    if not page:
        raise ValueError("target.page is required")
    label = str(target.get("label", "")).strip()
    if not label:
        raise ValueError("target.label is required")
    if len(label) > MAX_LABEL:
        raise ValueError(f"target.label must be {MAX_LABEL} characters or fewer")
    return {
        "page": page,
        "section": str(target.get("section", "") or "").strip(),
        "item": str(target.get("item", "") or "").strip(),
        "label": label,
    }


def add(vin: str, kind: str, target: dict[str, Any], text: str = "",
        author: str = "technician", media_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Validate, stamp and append one feedback row. Returns the stored record."""
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        raise ValueError("kind must be one of: " + ", ".join(KINDS))
    target_v = _validate_target(target)
    text = (text or "").strip()
    if len(text) > MAX_TEXT:
        raise ValueError(f"text must be {MAX_TEXT} characters or fewer")

    entry = {
        "id": uuid.uuid4().hex[:12],
        "vin": vin,
        "at": datetime.now().isoformat(timespec="seconds"),
        "author": (author or "technician").strip() or "technician",
        "kind": kind,
        "target": target_v,
        "text": text,
        "media_ids": [str(m).strip() for m in (media_ids or []) if str(m).strip()],
        "status": "open",
        "answer": None,
        "applied_note": None,
    }
    # Append, not read-all/rewrite: a rewrite loses a row another process
    # (CUORE server vs MCP server) added in between.
    paths.append_jsonl(store_path(), entry)
    return entry


def load(vin: str = "", status: Optional[str] = None,
        target: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Feedback rows, oldest first. ``vin`` and ``status`` filter exactly;
    ``target`` (a dict with any of page/section/item) filters on whichever of
    those keys it supplies, leaving the rest unconstrained."""
    if status is not None and status not in STATUSES:
        raise ValueError("status must be one of: " + ", ".join(STATUSES))
    from . import demo
    out = []
    for row in _read_all():
        if vin and row.get("vin") != vin:
            continue
        if not vin and demo.is_demo_record(row):   # rule 11: a demo car's feedback never counts in the totals
            continue
        if status and row.get("status") != status:
            continue
        if target:
            row_t = row.get("target", {})
            if "page" in target and row_t.get("page") != target["page"]:
                continue
            if "section" in target and row_t.get("section") != target["section"]:
                continue
            if "item" in target and row_t.get("item") != target["item"]:
                continue
        out.append(row)
    return out


def _find(id: str) -> tuple[list[dict[str, Any]], int]:
    rows = _read_all()
    for i, row in enumerate(rows):
        if row.get("id") == id:
            return rows, i
    raise ValueError(f"no feedback with id {id!r}")


def answer(id: str, by: str, text: str) -> dict[str, Any]:
    """Record an answer to feedback ``id`` and move it to status ``answered``."""
    id = (id or "").strip()
    if not id:
        raise ValueError("id is required")
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text must be {MAX_TEXT} characters or fewer")
    with paths._append_lock(store_path()):  # no add() may land between read and rewrite
        rows, i = _find(id)
        rows[i]["answer"] = {"at": datetime.now().isoformat(timespec="seconds"),
                             "by": (by or "claude").strip() or "claude", "text": text}
        rows[i]["status"] = "answered"
        _write_all(rows)
    return rows[i]


def set_status(id: str, status: str, note: Optional[str] = None) -> dict[str, Any]:
    """Move feedback ``id`` to a new status, optionally recording why
    (typically used with ``applied``, to say what was changed)."""
    id = (id or "").strip()
    if not id:
        raise ValueError("id is required")
    status = (status or "").strip().lower()
    if status not in STATUSES:
        raise ValueError("status must be one of: " + ", ".join(STATUSES))
    with paths._append_lock(store_path()):
        rows, i = _find(id)
        rows[i]["status"] = status
        if note is not None:
            note = note.strip()
            rows[i]["applied_note"] = note or None
        _write_all(rows)
    return rows[i]


def counts(vin: str, targets: list[str]) -> dict[str, dict[str, int]]:
    """Per-target tallies for the given ``page|section|item`` keys: how many
    rows are ``open``, how many ``answered``, and how many of each are a
    ``confirm`` vs. a ``correction`` -- the two are counted separately even
    when filed against the exact same target."""
    wanted = set(targets or [])
    out = {key: {"open": 0, "answered": 0, "confirms": 0, "corrections": 0}
          for key in wanted}
    for row in _read_all():
        if vin and row.get("vin") != vin:
            continue
        key = _target_key(row.get("target", {}))
        if key not in out:
            continue
        if row.get("status") == "open":
            out[key]["open"] += 1
        elif row.get("status") == "answered":
            out[key]["answered"] += 1
        if row.get("kind") == "confirm":
            out[key]["confirms"] += 1
        elif row.get("kind") == "correction":
            out[key]["corrections"] += 1
    return out


__all__ = ["KINDS", "STATUSES", "MAX_TEXT", "MAX_LABEL", "state_dir", "store_path",
          "add", "load", "answer", "set_status", "counts"]
