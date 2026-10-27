"""The "Next connection" plan: what to do the next time the car is connected.

Steps live in ``CUORE_STATE_DIR/next_session_plan.json`` (editable by the
owner or Claude). The file is seeded once from
``cuore/data/next_session_plan_default.json`` when its VIN matches. Done
state is stored in the same file per step (``done``, ``done_at``); writes
are atomic (temp file + replace).

Auto-detection (CUORE's own data only, never invented):
  * ``rfhub-first``  done when the newest connection day has an RFHUB
    module answering in a ``scan_coverage`` observation.
  * ``service-dids`` done when ``service_dids.results`` has a recorded run.
A manual Done/Undo always wins over auto-detection: Undo stores
``done: false`` explicitly so a detected step stays open until re-marked.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..live.config import state_dir

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "next_session_plan_default.json"
FILE_NAME = "next_session_plan.json"


def plan_path() -> Path:
    return state_dir() / FILE_NAME


def _read(p: Path) -> Optional[dict[str, Any]]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _write(data: dict[str, Any]) -> None:
    p = plan_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".nsp-", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load(vin: str) -> Optional[dict[str, Any]]:
    """The stored plan for this VIN, seeding it from the repo default if absent.
    ``None`` when there is no plan for this VIN."""
    data = _read(plan_path())
    if data is None:
        seed = _read(DEFAULT_PATH)
        if seed is None or seed.get("vin") != vin:
            return None
        try:
            _write(seed)
        except OSError:
            pass
        data = seed
    return data if data.get("vin") == vin else None


# --- auto-detection ----------------------------------------------------------


def _obs(vin: str) -> list[dict[str, Any]]:
    try:
        from ..live import store
        return store.recent_observations(2000, vin=vin)
    except Exception:  # noqa: BLE001 -- the plan must render without the store
        return []


def _rfhub_read_on_latest_day(vin: str) -> Optional[str]:
    rows = _obs(vin)
    days = sorted({str(r.get("at") or "")[:10] for r in rows if r.get("at")})
    if not days:
        return None
    day = days[-1]
    for r in rows:
        if str(r.get("at") or "")[:10] != day or r.get("kind") != "scan_coverage":
            continue
        for c in (r.get("data") or {}).get("coverage") or []:
            if str(c.get("module", "")).upper() == "RFHUB" and c.get("category") == "answered":
                return day
    return None


def _service_dids_done(vin: str) -> Optional[str]:
    try:
        from ..live import service_dids
        r = service_dids.results(vin)
    except Exception:  # noqa: BLE001
        return None
    return str(r.get("at") or "")[:10] if r.get("ran") else None


_AUTO = {"rfhub-first": _rfhub_read_on_latest_day, "service-dids": _service_dids_done}


# --- view / mutation ---------------------------------------------------------


def view(vin: str, live: bool = False) -> Optional[dict[str, Any]]:
    data = load(vin)
    if data is None:
        return None
    rows: list[dict[str, Any]] = []
    for s in data.get("steps") or []:
        done, at = bool(s.get("done")), s.get("done_at")
        how = "manual" if done else None
        if "done" not in s and s.get("id") in _AUTO:
            day = _AUTO[s["id"]](vin)
            if day:
                done, at, how = True, day, "auto"
        rows.append({**s, "done": done, "done_at": at, "done_how": how,
                     "href": str(s.get("link") or "").replace("{vin}", vin)})
    rows.sort(key=lambda r: (r["done"], r.get("order", 999)))
    n_done = sum(1 for r in rows if r["done"])
    return {"vin": vin, "title": data.get("title") or "Next connection", "steps": rows,
            "total": len(rows), "done": n_done, "live": bool(live),
            "summary": f"Next connection — {len(rows)} steps ({n_done} done)"}


def mark(vin: str, step_id: str, done: bool, now: Optional[datetime] = None) -> bool:
    """Mark a step done (``done=True``) or undo it. False if no such step."""
    data = load(vin)
    if data is None:
        return False
    for s in data.get("steps") or []:
        if s.get("id") == step_id:
            s["done"] = bool(done)
            s["done_at"] = (now or datetime.now()).strftime("%Y-%m-%d") if done else None
            _write(data)
            return True
    return False


__all__ = ["load", "view", "mark", "plan_path"]
