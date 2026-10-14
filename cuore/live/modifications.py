"""Per-VIN ledger of **modifications actually done** to a car -- the
RECORD half of the owner's 2026-10-14 decision: CUORE diagnoses, it never
codes or configures the car itself; a modification is done in MES/wiTECH
(or, rarely, the car's own menu -- see ``mes.modifications.epb_service_mode``)
via a handoff card, and then RECORDED here with who/when/from->to/backup/
verification, so diagnostics elsewhere in CUORE can know the car is
non-stock (:func:`cuore.services.modifications_bridge.non_stock`).

**This is an attested record of a human's action, never a car
measurement** -- same posture as :mod:`cuore.live.owner_events` and
:mod:`cuore.live.attested`: a row here says a mechanic/dealer/owner typed
that something was done, with a tool, a before/after, and (ideally) a
verification step. It does not re-derive, re-check or re-read the car's
own configuration -- there is no DID for most of these writes (see the
paddle-shift research pass) to check it against even if CUORE wanted to.

Append-only JSONL under ``cuore.live.config.state_dir()``
(``CUORE_STATE_DIR``, same precedence as every other small store in this
package), one file, ``modifications.jsonl``, four record shapes
distinguished by ``op`` -- the exact same append-only/fold/audit pattern
:mod:`cuore.live.owner_events` already uses, reused here rather than
reinvented:

* ``record`` -- {op, id, vin, at (recorded_at), mod_id, free_text,
  done_at, by: {role, name}, tool, from_value, to_value, backup,
  verification: {how, when, result}, proxi_realigned, notes, media_ids}
* ``delete`` -- {op, id, at} -- soft delete (the record stays on disk,
  just hidden from :func:`load` unless ``include_deleted``)
* ``restore`` -- {op, id, at} -- undoes a ``delete``, folded in append
  order so a delete/restore/delete... history reads correctly regardless
  of how many times it happened
* ``record_edit`` -- {op, id, at, by, changes: {field: {from, to}}} --
  never rewrites the original ``record`` row; :func:`load` folds every
  ``record_edit`` onto its ``record`` in append order and keeps the
  folded result's ``audit`` list (one entry per edit: who, when, what
  changed) for the UI's disclosure, exactly as ``owner_events._fold`` does.

Either ``mod_id`` (a :mod:`mes.modifications` catalogue id) or ``free_text``
(a modification not in the catalogue -- "fitted an aftermarket turbo
inlet pipe") must be given; this module does not itself validate ``mod_id``
against the catalogue (catalogue-agnostic by design, same split
``owner_events`` keeps from ``mes.feedback`` -- validation against the
catalogue, when wanted, belongs to
:mod:`cuore.services.modifications_bridge`, which is the one place that
imports both this module and ``mes.modifications``).
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

MAX_NOTE = 4000
MAX_TEXT = 500

#: Who did it, or who is recording it -- same spirit as
#: ``owner_events.BY_ROLES``, tailored to this feature (a modification is
#: usually a mechanic's or a dealer's doing, occasionally the owner's own).
BY_ROLES = ("mechanic", "dealer", "owner")

#: What tool performed the write -- "other" covers a physical part swap or
#: anything not MES/wiTECH/dealer-equipment.
TOOLS = ("MES", "wiTECH", "dealer", "other")


def state_path() -> Path:
    return state_dir() / "modifications.jsonl"


def _append(entry: dict[str, Any]) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _raw_records() -> list[dict[str, Any]]:
    p = state_path()
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


def _parse_iso_or_date(at: Optional[str]) -> str:
    s = (at or "").strip()
    if not s:
        return datetime.now().isoformat(timespec="seconds")
    try:
        datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"at must be an ISO date or timestamp, got {at!r}") from exc
    return s


def _clean_text(v: Any, limit: int = MAX_TEXT) -> str:
    if v is None:
        return ""
    return str(v).strip()[:limit]


_EDITABLE_FIELDS = (
    "mod_id", "free_text", "done_at", "tool", "from_value", "to_value",
    "backup", "verification_how", "verification_when",
    "verification_result", "proxi_realigned", "notes",
)


def add(vin: str, *, mod_id: str = "", free_text: str = "",
        done_at: Optional[str] = None, by_role: str = "mechanic",
        by_name: str = "", tool: str = "MES", from_value: str = "",
        to_value: str = "", backup: str = "none",
        verification_how: str = "", verification_when: str = "",
        verification_result: str = "", proxi_realigned: Optional[bool] = None,
        notes: str = "", media_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Record one modification done to ``vin``. Raises ``ValueError`` on:
    no vin, neither ``mod_id`` nor ``free_text`` given, a bad ``by_role``/
    ``tool``/``done_at``, or a note over :data:`MAX_NOTE`."""
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    mod_id = _clean_text(mod_id, 200)
    free_text = _clean_text(free_text, MAX_TEXT)
    if not mod_id and not free_text:
        raise ValueError("either mod_id or free_text is required")

    by_role = (by_role or "mechanic").strip().lower()
    if by_role not in BY_ROLES:
        raise ValueError("by_role must be one of: " + ", ".join(BY_ROLES))

    tool = (tool or "MES").strip()
    if tool not in TOOLS:
        raise ValueError("tool must be one of: " + ", ".join(TOOLS))

    notes = (notes or "").strip()
    if len(notes) > MAX_NOTE:
        raise ValueError(f"notes must be {MAX_NOTE} characters or fewer")

    done_at_v = _parse_iso_or_date(done_at)

    proxi_v: Optional[bool] = None
    if proxi_realigned is not None:
        proxi_v = bool(proxi_realigned)

    entry = {
        "op": "record",
        "id": uuid.uuid4().hex[:12],
        "vin": vin,
        "at": datetime.now().isoformat(timespec="seconds"),  # recorded_at
        "mod_id": mod_id,
        "free_text": free_text,
        "done_at": done_at_v,
        "by": {"role": by_role, "name": _clean_text(by_name, 200)},
        "tool": tool,
        "from_value": _clean_text(from_value),
        "to_value": _clean_text(to_value),
        "backup": _clean_text(backup) or "none",
        "verification": {
            "how": _clean_text(verification_how),
            "when": _clean_text(verification_when),
            "result": _clean_text(verification_result),
        },
        "proxi_realigned": proxi_v,
        "notes": notes,
        "media_ids": [str(m).strip() for m in (media_ids or []) if str(m).strip()],
    }
    with _LOCK:
        _append(entry)
    return entry


def delete(id: str) -> dict[str, Any]:
    """Soft-delete: append a ``delete`` amendment. Never rewrites history."""
    eid = (id or "").strip()
    if not eid:
        raise ValueError("id is required")
    with _LOCK:
        rows = _raw_records()
        if not any(r.get("op") == "record" and r.get("id") == eid for r in rows):
            raise ValueError(f"no modification record with id {eid!r}")
        entry = {"op": "delete", "id": eid, "at": datetime.now().isoformat(timespec="seconds")}
        _append(entry)
    return entry


def restore(id: str) -> dict[str, Any]:
    """Undo a soft-delete: append a ``restore`` amendment."""
    eid = (id or "").strip()
    if not eid:
        raise ValueError("id is required")
    with _LOCK:
        rows = _raw_records()
        if not any(r.get("op") == "record" and r.get("id") == eid for r in rows):
            raise ValueError(f"no modification record with id {eid!r}")
        entry = {"op": "restore", "id": eid, "at": datetime.now().isoformat(timespec="seconds")}
        _append(entry)
    return entry


def _fold(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Same reduction ``owner_events._fold`` performs, for this store's own
    four ops -- one current view per record id, in append order."""
    deleted: dict[str, bool] = {}
    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    edits_by_id: dict[str, list[dict[str, Any]]] = {}
    for rec in rows:
        op = rec.get("op")
        rid = rec.get("id")
        if not rid:
            continue
        if op == "record":
            if rid in records:
                continue
            records[rid] = dict(rec)
            order.append(rid)
        elif op == "delete":
            deleted[rid] = True
        elif op == "restore":
            deleted[rid] = False
        elif op == "record_edit":
            edits_by_id.setdefault(rid, []).append(rec)

    out: dict[str, dict[str, Any]] = {}
    for rid in order:
        view = dict(records[rid])
        audit: list[dict[str, Any]] = []
        for e in edits_by_id.get(rid, []):
            changes = e.get("changes") or {}
            for field, ch in changes.items():
                new_v = ch.get("to")
                if field == "verification_how":
                    view.setdefault("verification", {})["how"] = new_v
                elif field == "verification_when":
                    view.setdefault("verification", {})["when"] = new_v
                elif field == "verification_result":
                    view.setdefault("verification", {})["result"] = new_v
                else:
                    view[field] = new_v
            audit.append({"at": e.get("at"), "by": e.get("by"), "changes": changes})
        view["audit"] = audit
        view["edited_at"] = audit[-1]["at"] if audit else None
        view["deleted"] = deleted.get(rid, False)
        out[rid] = view
    return out


def edit(id: str, *, by_role: str = "mechanic", by_name: str = "",
        **fields: Any) -> dict[str, Any]:
    """Append a ``record_edit`` amendment changing one or more fields of an
    existing, non-deleted record. ``fields`` keys must be a subset of
    :data:`_EDITABLE_FIELDS`. Raises ``ValueError`` on: no such record, the
    record is deleted, an unknown field key, or an edit that changes
    nothing."""
    eid = (id or "").strip()
    if not eid:
        raise ValueError("id is required")
    by_role = (by_role or "mechanic").strip().lower()
    if by_role not in BY_ROLES:
        raise ValueError("by_role must be one of: " + ", ".join(BY_ROLES))

    unknown = [k for k in fields if k not in _EDITABLE_FIELDS]
    if unknown:
        raise ValueError("unknown field(s) for edit: " + ", ".join(unknown)
                         + "; use one of: " + ", ".join(_EDITABLE_FIELDS))

    with _LOCK:
        rows = _raw_records()
        current = _fold(rows).get(eid)
        if current is None:
            raise ValueError(f"no modification record with id {eid!r}")
        if current.get("deleted"):
            raise ValueError(f"modification record {eid!r} is deleted")

        changes: dict[str, Any] = {}
        for field, new_v in fields.items():
            if field == "tool" and new_v not in TOOLS:
                raise ValueError("tool must be one of: " + ", ".join(TOOLS))
            if field == "proxi_realigned":
                old_v = current.get("proxi_realigned")
                new_v = None if new_v is None else bool(new_v)
            elif field in ("verification_how", "verification_when", "verification_result"):
                key = field.split("_", 1)[1]
                old_v = (current.get("verification") or {}).get(key)
                new_v = _clean_text(new_v)
            elif field == "done_at":
                old_v = current.get("done_at")
                new_v = _parse_iso_or_date(new_v)
            elif field == "notes":
                old_v = current.get("notes")
                new_v = (new_v or "").strip()
                if len(new_v) > MAX_NOTE:
                    raise ValueError(f"notes must be {MAX_NOTE} characters or fewer")
            else:
                old_v = current.get(field)
                new_v = _clean_text(new_v, 200 if field == "mod_id" else MAX_TEXT)
            if old_v != new_v:
                changes[field] = {"from": old_v, "to": new_v}

        if not changes:
            raise ValueError("edit must change at least one field")

        entry = {
            "op": "record_edit",
            "id": eid,
            "at": datetime.now().isoformat(timespec="seconds"),
            "by": {"role": by_role, "name": _clean_text(by_name, 200)},
            "changes": changes,
        }
        _append(entry)
    return entry


def load(vin: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    """Modification records for ``vin`` (or every vin when empty), newest
    ``done_at``/``at`` first -- this feature's own "This car" feed is
    read newest-first, unlike ``owner_events.load``'s oldest-first (a
    modification history is read like a changelog, most recent change on
    top). Deleted rows are dropped unless ``include_deleted``."""
    vin = (vin or "").strip()
    with _LOCK:
        rows = _raw_records()
    folded = _fold(rows)

    out: list[dict[str, Any]] = []
    for view in folded.values():
        if view["deleted"] and not include_deleted:
            continue
        if vin and view.get("vin") != vin:
            continue
        out.append(dict(view))
    out.sort(key=lambda r: r.get("done_at") or r.get("at") or "", reverse=True)
    return out


def status(vin: str) -> dict[str, Any]:
    """``{"status": "stock"|"modified", "count": n}`` for ``vin`` -- the
    plain fact, computed from this ledger alone (no catalogue lookup; see
    :mod:`cuore.services.modifications_bridge` for the richer summary with
    catalogue names and owner-reported entries merged in)."""
    rows = load(vin)
    return {"status": "modified" if rows else "stock", "count": len(rows)}


__all__ = ["BY_ROLES", "TOOLS", "MAX_NOTE", "MAX_TEXT", "state_path",
          "add", "delete", "restore", "edit", "load", "status"]
