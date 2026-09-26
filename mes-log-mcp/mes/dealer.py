"""Dealer (wiTECH) results, recorded by hand and kept as evidence.

wiTECH has no API and this toolchain never reaches it -- the owner's dealer
account gets read by a technician on wiTECH's own screens, and the result has
to be typed in here to become evidence the gate or a fault tree can cite.
This is the only place that evidence enters the corpus.

Append-only JSONL, same state directory :mod:`mes.live_obs` reads
observations from (``CUORE_STATE_DIR``, else ``%PROGRAMDATA%\\cuore``, else
``%LOCALAPPDATA%\\cuore``, else ``~/.cuore``) -- unlike that module, writing
here is expected and is the whole point.

Each line: ``{"at": iso, "vin": ..., "kind": ..., "data": {...}, "note": ...,
"source": "technician-entered from wiTECH"}``.

Kinds:

* ``flash_check`` -- {module, current_part, new_part, flashed, part_after?}.
  ``current`` is derived: true when the installed part already matches what
  wiTECH says is current, or when it was flashed and the part number
  afterwards matches.
* ``slvt`` -- wiTECH's Small Leak Verification Test (TSB 18-048-23):
  {result: pass|fail, detail}.
* ``dtc_report`` -- {module, codes: [...], note}.
* ``recall_status`` -- {campaign, status: open|completed|not_applicable, date}.
* ``routine`` -- a named dealer-tool routine: {module, name, result}.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

KINDS = ("flash_check", "slvt", "dtc_report", "recall_status", "routine")


def state_dir() -> Path:
    """Mirror ``cuore.live.config.state_dir()``: same candidates, first
    writable wins. Kept independent of ``cuore`` so ``mes`` never imports it;
    see ``mes.live_obs.observations_path`` for the reader-side counterpart."""
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
    return state_dir() / "dealer_results.jsonl"


def _validate(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    """Normalise one kind's data, or raise ``ValueError`` naming what's missing."""
    if kind == "flash_check":
        module = str(data.get("module", "")).strip()
        current_part = str(data.get("current_part", "")).strip()
        new_part = str(data.get("new_part", "")).strip()
        if not module or not current_part or not new_part:
            raise ValueError("flash_check needs module, current_part and new_part")
        flashed = bool(data.get("flashed", False))
        part_after_raw = data.get("part_after")
        part_after = str(part_after_raw).strip() if part_after_raw else None
        current = (current_part == new_part) or (flashed and part_after == new_part)
        out: dict[str, Any] = {"module": module, "current_part": current_part,
                               "new_part": new_part, "flashed": flashed,
                               "current": current}
        if part_after:
            out["part_after"] = part_after
        return out

    if kind == "slvt":
        result = str(data.get("result", "")).strip().lower()
        if result not in ("pass", "fail"):
            raise ValueError("slvt needs result: pass|fail")
        return {"result": result, "detail": str(data.get("detail", "")).strip()}

    if kind == "dtc_report":
        module = str(data.get("module", "")).strip()
        codes = data.get("codes")
        if not module or not isinstance(codes, list):
            raise ValueError("dtc_report needs module and a codes list")
        return {"module": module,
                "codes": [str(c).strip() for c in codes if str(c).strip()],
                "note": str(data.get("note", "")).strip()}

    if kind == "recall_status":
        campaign = str(data.get("campaign", "")).strip()
        status = str(data.get("status", "")).strip().lower()
        if not campaign or status not in ("open", "completed", "not_applicable"):
            raise ValueError("recall_status needs campaign and "
                             "status: open|completed|not_applicable")
        return {"campaign": campaign, "status": status,
                "date": str(data.get("date", "")).strip()}

    if kind == "routine":
        module = str(data.get("module", "")).strip()
        name = str(data.get("name", "")).strip()
        if not module or not name:
            raise ValueError("routine needs module and name")
        return {"module": module, "name": name,
                "result": str(data.get("result", "")).strip()}

    raise ValueError(f"unknown dealer result kind {kind!r}; use one of: "
                     + ", ".join(KINDS))


def record(vin: str, kind: str, data: dict[str, Any], note: str = "") -> dict[str, Any]:
    """Validate, stamp and append one dealer result. Returns the stored entry."""
    vin = (vin or "").strip()
    kind = (kind or "").strip().lower()
    if not vin:
        raise ValueError("vin is required")
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    clean = _validate(kind, data)
    entry = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "vin": vin,
        "kind": kind,
        "data": clean,
        "note": (note or "").strip(),
        "source": "technician-entered from wiTECH",
    }
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load(vin: str = "", kind: Optional[str] = None) -> list[dict[str, Any]]:
    """Dealer results oldest-first, filtered by VIN and kind when given."""
    p = store_path()
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if vin and obj.get("vin") != vin:
            continue
        if kind and obj.get("kind") != kind:
            continue
        out.append(obj)
    return out


def latest(vin: str, kind: str, **match: Any) -> Optional[dict[str, Any]]:
    """Newest result of ``kind`` for ``vin``, optionally matching fields in ``data``."""
    for entry in reversed(load(vin, kind)):
        data = entry.get("data") or {}
        if all(data.get(k) == v for k, v in match.items()):
            return entry
    return None


__all__ = ["KINDS", "state_dir", "store_path", "record", "load", "latest"]
