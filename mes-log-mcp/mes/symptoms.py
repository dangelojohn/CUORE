"""Driver/mechanic symptom reports: what a human actually noticed, when.

The logs and the live link answer "what did the car's computer measure"; this
module answers "what did a person actually feel" -- "drives completely
normally", "rough idle cold", "smells like fuel after filling up". For EVAP
codes in particular the two answers are usually different: the fault is real
and the codes keep returning, but nobody driving the car has ever noticed
anything. That gap is the whole point of the timeline this store feeds --
``cuore.services.timeline_bridge`` correlates these reports against code
history to make the gap visible instead of assumed.

A symptom report is an ATTESTED claim, not a measurement the car made. It must
never be fed into :mod:`mes.verdict` (the evidence gate) as a measurement --
only a sensor reading, an actuator test, a freeze frame, a live read, a
dealer result or a technician note stands as evidence there. This module is
deliberately not imported by ``mes.verdict`` and nothing here should ever be
wired into it.

Append-only JSONL, same state directory :mod:`mes.notes` writes to
(``CUORE_STATE_DIR``, else ``%PROGRAMDATA%\\cuore``, else
``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``) -- kept independent of
``cuore`` so ``mes`` never imports it, same reasoning as ``mes.notes`` and
``mes.dealer``.

Two record shapes share one file, distinguished by ``op``:

* ``symptom`` -- {id, vin, at, odometer_km, reporter, tags, conditions,
  text, created_at}
* ``hide``    -- {id, at} -- marks a symptom hidden (soft delete)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

#: What a person can report feeling (or not feeling). ``other`` is the escape
#: hatch for anything this list does not name; ``drives_normally`` is the
#: finding that matters most for EVAP: a code is present and nothing was felt.
SYMPTOM_TAGS = (
    "drives_normally", "mil_on", "fuel_smell", "hard_start", "rough_idle",
    "hesitation", "loss_of_power", "hard_to_refuel", "noise", "vibration",
    "warning_message", "other",
)

#: Conditions the report happened under -- context that often explains why a
#: symptom shows up only sometimes (EVAP monitors care about fuel level and
#: cold starts for exactly this reason).
CONDITIONS = (
    "cold_start", "hot", "just_refuelled", "highway", "city", "idle", "rain",
)

REPORTERS = ("driver", "mechanic")

#: A report cannot claim both "nothing is wrong" and a specific drivability
#: complaint in the same breath -- one of these contradicts "drives_normally".
_DRIVABILITY_TAGS = frozenset({"rough_idle", "hesitation", "loss_of_power", "hard_start"})

MAX_TEXT = 4000


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
            probe = d / ".write-test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return d
        except OSError:
            continue
    return Path.cwd()


def store_path() -> Path:
    return state_dir() / "symptoms.jsonl"


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


def _parse_iso(at: str) -> None:
    """Raise ``ValueError`` if ``at`` is not a parseable ISO-ish timestamp."""
    s = (at or "").strip()
    if not s:
        raise ValueError("at is required (an ISO timestamp)")
    try:
        datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"at must be an ISO timestamp, got {at!r}") from exc


def _clean_tag_list(raw: Optional[list[str]], allowed: tuple[str, ...],
                    label: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"{label} must be a list")
    out: list[str] = []
    for t in raw:
        tag = str(t).strip().lower()
        if not tag:
            continue
        if tag not in allowed:
            raise ValueError(f"unknown {label} {tag!r}; use one of: " + ", ".join(allowed))
        if tag not in out:
            out.append(tag)
    return out


def add(vin: str, at: str, *, odometer_km: Optional[float] = None,
        reporter: str = "driver", tags: Optional[list[str]] = None,
        conditions: Optional[list[str]] = None, text: str = "") -> dict[str, Any]:
    """Validate, stamp and append one symptom report. Raises ``ValueError``."""
    vin = (vin or "").strip()
    if not vin:
        raise ValueError("vin is required")
    _parse_iso(at)
    reporter = (reporter or "driver").strip().lower()
    if reporter not in REPORTERS:
        raise ValueError("reporter must be one of: " + ", ".join(REPORTERS))

    tag_list = _clean_tag_list(tags, SYMPTOM_TAGS, "tag")
    cond_list = _clean_tag_list(conditions, CONDITIONS, "condition")

    if "drives_normally" in tag_list and (_DRIVABILITY_TAGS & set(tag_list)):
        clash = sorted(_DRIVABILITY_TAGS & set(tag_list))
        raise ValueError(
            "drives_normally cannot be combined with a drivability tag: "
            + ", ".join(clash))

    text = (text or "").strip()
    if len(text) > MAX_TEXT:
        raise ValueError(f"text must be {MAX_TEXT} characters or fewer")

    odo = None
    if odometer_km is not None and str(odometer_km).strip() != "":
        try:
            odo = float(odometer_km)
        except (TypeError, ValueError) as exc:
            raise ValueError("odometer_km must be numeric") from exc

    entry = {
        "op": "symptom",
        "id": uuid.uuid4().hex[:12],
        "vin": vin,
        "at": at.strip(),
        "odometer_km": odo,
        "reporter": reporter,
        "tags": tag_list,
        "conditions": cond_list,
        "text": text,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _append(entry)
    return entry


def hide(id: str) -> dict[str, Any]:
    """Append a hide amendment for symptom ``id``. Never rewrites history."""
    sid = (id or "").strip()
    if not sid:
        raise ValueError("id is required")
    found = any(r.get("op") == "symptom" and r.get("id") == sid for r in _raw_records())
    if not found:
        raise ValueError(f"no symptom with id {sid!r}")
    entry = {"op": "hide", "id": sid,
             "at": datetime.now().isoformat(timespec="seconds")}
    _append(entry)
    return entry


def load(vin: str = "", include_hidden: bool = False) -> list[dict[str, Any]]:
    """Symptom reports for ``vin`` (or every vin when empty), oldest ``at`` first.

    ``hidden`` records are dropped unless ``include_hidden``. Order is by the
    report's own ``at`` (when the symptom happened), not ``created_at`` (when
    it was logged) -- a symptom entered after the fact must still slot into
    the timeline at the moment it occurred.
    """
    vin = (vin or "").strip()
    hidden_ids: set[str] = set()
    symptoms: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for rec in _raw_records():
        op = rec.get("op")
        rid = rec.get("id")
        if not rid:
            continue
        if op == "symptom":
            if rid in symptoms:
                continue
            symptoms[rid] = dict(rec)
            order.append(rid)
        elif op == "hide":
            hidden_ids.add(rid)

    out: list[dict[str, Any]] = []
    for rid in order:
        rec = symptoms[rid]
        is_hidden = rid in hidden_ids
        if is_hidden and not include_hidden:
            continue
        if vin and rec.get("vin") != vin:
            continue
        view = dict(rec)
        view["hidden"] = is_hidden
        out.append(view)
    out.sort(key=lambda r: r.get("at") or "")
    return out


__all__ = ["SYMPTOM_TAGS", "CONDITIONS", "REPORTERS", "MAX_TEXT",
          "state_dir", "store_path", "add", "hide", "load"]
