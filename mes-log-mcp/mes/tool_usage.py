"""What a mechanic actually used, at release: the learning loop for
:mod:`mes.tools_kb`.

``mes.tools_kb`` answers "what should I bring to this job/step". This module
answers the next question, after the work is done: what did the mechanic
actually use, was it right, what's missing, and what would he buy instead
next time -- so the *next* identical job on this (or any) car shows that
learning first, instead of the same cold recommendation every time.

Append-only JSONL, same state-directory convention as :mod:`mes.jobs`/
:mod:`mes.dealer`/:mod:`mes.notes` (``CUORE_STATE_DIR``, else
``%PROGRAMDATA%\\cuore``, else ``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``)
-- kept independent of ``cuore`` so ``mes`` never imports it, and independent
of ``mes.jobs``'s own store (a different file, ``tool_usage.jsonl``) so one
feature's history never has to be folded out of the other's.

One row per review, each a complete record (nothing folded across rows --
unlike ``mes.jobs``, there is no running state to rebuild, so this is a
flat read, not a fold):

    {id, vin, job_id, step, at, by,
     tools_used: [{tool, was_right: yes|no|unsure, note}],
     missing_tools: [text], would_buy: [{name, why}], time_min}

``tool`` in ``tools_used`` is either a key into ``mes.tools_kb.TOOLS`` or
free text (a tool the catalogue doesn't know yet) -- never validated against
the catalogue here, since a mechanic naming a tool CUORE doesn't have is
exactly the signal this module exists to capture, not an error.
"""

from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

WAS_RIGHT_VALUES = ("yes", "no", "unsure")

#: Garage tool inventory: a simple owned/not-owned list, independent of any
#: one vehicle/job -- "have it" or not, nothing more granular.
INVENTORY_STATUSES = ("owned", "not_owned")


def state_dir() -> Path:
    """Mirror ``mes.jobs.state_dir()``: same candidates, first writable wins."""
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
    return state_dir() / "tool_usage.jsonl"


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


def _clean_tools_used(tools_used: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out = []
    for t in tools_used or []:
        name = (t.get("tool") or "").strip() if isinstance(t, dict) else ""
        if not name:
            continue
        was_right = (t.get("was_right") or "unsure").strip().lower()
        if was_right not in WAS_RIGHT_VALUES:
            was_right = "unsure"
        out.append({"tool": name, "was_right": was_right, "note": (t.get("note") or "").strip()})
    return out


def _clean_would_buy(would_buy: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out = []
    for b in would_buy or []:
        name = (b.get("name") or "").strip() if isinstance(b, dict) else ""
        if not name:
            continue
        out.append({"name": name, "why": (b.get("why") or "").strip()})
    return out


def add(vin: str, step: str, *, job_id: str = "", by: str = "",
       tools_used: Optional[list[dict[str, Any]]] = None,
       missing_tools: Optional[list[str]] = None,
       would_buy: Optional[list[dict[str, Any]]] = None,
       time_min: Optional[float] = None) -> dict[str, Any]:
    """Record one tool-usage review. ``vin`` and ``step`` are required --
    everything else may be empty (a review that found nothing wrong and
    nothing worth buying is still a real, useful review)."""
    vin = (vin or "").strip()
    step = (step or "").strip()
    if not vin:
        raise ValueError("vin is required")
    if not step:
        raise ValueError("step is required")
    rec = {
        "id": uuid.uuid4().hex[:12], "vin": vin, "job_id": (job_id or "").strip(),
        "step": step, "at": datetime.now().isoformat(timespec="seconds"),
        "by": (by or "").strip(),
        "tools_used": _clean_tools_used(tools_used),
        "missing_tools": [m.strip() for m in (missing_tools or []) if (m or "").strip()],
        "would_buy": _clean_would_buy(would_buy),
        "time_min": time_min,
    }
    _append(rec)
    return rec


def load(vin: Optional[str] = None, step: Optional[str] = None) -> list[dict[str, Any]]:
    """Every review, oldest first, optionally filtered by VIN and/or step."""
    rows = _raw_records()
    if vin:
        rows = [r for r in rows if r.get("vin") == vin]
    if step:
        rows = [r for r in rows if r.get("step") == step]
    return rows


def learn(step: str, *, vin: Optional[str] = None) -> dict[str, Any]:
    """Aggregate every review for ``step`` (optionally scoped to one ``vin``
    first, falling back to every vehicle if that VIN has none yet -- the
    whole point is that a lesson learned on one car should show up on the
    next identical job on *any* Stelvio, not just the same VIN) into:

      {step, review_count,
       top_tools: [{tool, used_count, right_count, wrong_count, unsure_count}],
       flagged_wrong: [{tool, count, notes: [str]}],
       buy_suggestions: [{name, count, why: [str]}],
       missing_tools: [{text, count}]}

    Returns zeroed/empty structures (never ``None``/an error) when nothing
    has been recorded yet -- an empty lesson is a valid, honest answer.
    """
    step = (step or "").strip()
    rows = load(vin=vin, step=step) if vin else []
    scope = "vin" if rows else "all"
    if not rows:
        rows = load(step=step)

    tool_counts: Counter[str] = Counter()
    right_counts: Counter[str] = Counter()
    wrong_counts: Counter[str] = Counter()
    unsure_counts: Counter[str] = Counter()
    wrong_notes: dict[str, list[str]] = {}
    buy_counts: Counter[str] = Counter()
    buy_why: dict[str, list[str]] = {}
    missing_counts: Counter[str] = Counter()

    for r in rows:
        for t in r.get("tools_used", []):
            name = t["tool"]
            tool_counts[name] += 1
            if t["was_right"] == "yes":
                right_counts[name] += 1
            elif t["was_right"] == "no":
                wrong_counts[name] += 1
                if t.get("note"):
                    wrong_notes.setdefault(name, []).append(t["note"])
            else:
                unsure_counts[name] += 1
        for m in r.get("missing_tools", []):
            missing_counts[m] += 1
        for b in r.get("would_buy", []):
            buy_counts[b["name"]] += 1
            if b.get("why"):
                buy_why.setdefault(b["name"], []).append(b["why"])

    top_tools = [
        {"tool": name, "used_count": n, "right_count": right_counts.get(name, 0),
         "wrong_count": wrong_counts.get(name, 0), "unsure_count": unsure_counts.get(name, 0)}
        for name, n in tool_counts.most_common()
    ]
    flagged_wrong = [
        {"tool": name, "count": n, "notes": wrong_notes.get(name, [])}
        for name, n in wrong_counts.most_common() if n > 0
    ]
    buy_suggestions = [
        {"name": name, "count": n, "why": buy_why.get(name, [])}
        for name, n in buy_counts.most_common()
    ]
    missing = [{"text": text, "count": n} for text, n in missing_counts.most_common()]

    return {
        "step": step, "review_count": len(rows), "scope": scope,
        "top_tools": top_tools, "flagged_wrong": flagged_wrong,
        "buy_suggestions": buy_suggestions, "missing_tools": missing,
    }


# --- garage tool inventory: a simple owned / not-owned list ----------------
#
# A second, independent append-only store (``tool_inventory.jsonl``): each
# ``inventory_set`` call is one more record of whether the shop has a tool;
# "current" is the most recent record per tool key, same last-wins-by-
# timestamp posture as everything else here. Garage-wide, not per-vehicle --
# a torque wrench doesn't belong to one car. Deliberately just two states --
# not a full asset ledger (no location, no restock tracking): "have it" is
# the one fact :func:`mes.tools_kb.recommend`'s caller needs to decide
# whether a required tool's decision card should show.


def inventory_store_path() -> Path:
    return state_dir() / "tool_inventory.jsonl"


def _inventory_append(entry: dict[str, Any]) -> None:
    p = inventory_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _inventory_raw_records() -> list[dict[str, Any]]:
    p = inventory_store_path()
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


def inventory_set(tool: str, status: str, *, note: str = "") -> dict[str, Any]:
    """Record whether the shop has this tool right now -- "owned" or
    "not_owned" (a ``mes.tools_kb.TOOLS`` key, or free text for a tool the
    catalogue doesn't know yet)."""
    tool = (tool or "").strip()
    if not tool:
        raise ValueError("tool is required")
    status = (status or "").strip().lower()
    if status not in INVENTORY_STATUSES:
        raise ValueError("status must be one of: " + ", ".join(INVENTORY_STATUSES))
    rec = {"tool": tool, "status": status, "at": datetime.now().isoformat(),
          "note": (note or "").strip()}
    _inventory_append(rec)
    return rec


def inventory_list() -> dict[str, dict[str, Any]]:
    """Every tool with a recorded status, keyed by tool, each the most
    recent record for that tool (last-wins by file order, which is
    chronological since this store is append-only)."""
    current: dict[str, dict[str, Any]] = {}
    for rec in _inventory_raw_records():
        tool = rec.get("tool")
        if tool:
            current[tool] = rec
    return current


def inventory_get(tool: str) -> Optional[dict[str, Any]]:
    """The current inventory record for one tool, or ``None`` if its status
    has never been set (an honest "unknown", not a guessed default)."""
    return inventory_list().get(tool)


def have_status(tool: str) -> str:
    """What the shop has for this tool key right now -- the single answer
    ``cuore.services.tools_kb_bridge`` annotates each recommended tool row
    with. One of ``INVENTORY_STATUSES`` ("owned"/"not_owned") or "unknown"
    (never recorded)."""
    inv = inventory_get((tool or "").strip())
    return inv["status"] if inv else "unknown"


__all__ = ["WAS_RIGHT_VALUES", "INVENTORY_STATUSES",
          "state_dir", "store_path", "add", "load", "learn",
          "inventory_store_path", "inventory_set", "inventory_list", "inventory_get",
          "have_status"]
