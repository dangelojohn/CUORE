"""Small persistent state: address confirmations per VIN.

A JSON file beside the lock file. Phase 3 replaces this with the SQLite store
from the spec; the interface stays.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import state_dir

_LOCK = threading.Lock()


def path() -> Path:
    return state_dir() / "addresses.json"


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


def confirmed_targets(vin: str) -> dict[str, int]:
    """``{module_code: target}`` confirmed on this VIN."""
    with _LOCK:
        entry = _load().get(vin, {})
    return {code: int(rec["target"], 16) for code, rec in entry.items()}


def confirm_target(vin: str, code: str, target: int, source: str = "discover") -> None:
    with _LOCK:
        data = _load()
        data.setdefault(vin, {})[code] = {
            "target": f"{target:02X}", "source": source,
            "at": datetime.now().isoformat(timespec="seconds")}
        _save(data)


def all_confirmations() -> dict[str, Any]:
    with _LOCK:
        return _load()


# --- observations: what the car said, when, so the evidence gate can cite it --

def observations_path() -> Path:
    import os
    env = os.environ.get("MES_LIVE_OBSERVATIONS")
    return Path(env) if env else state_dir() / "observations.jsonl"


def record_observation(kind: str, data: dict[str, Any], *, vin: str = "",
                       bus: str = "", cable: str = "", stream: str = "") -> None:
    """Append one observation. Never raises; the read itself must not fail on I/O.

    ``stream`` names what produced it (``serial COM3@115200``, ``scripted``,
    ``playback ...``). Only serial observations are evidence about a car;
    anything else is a test or a replay and :func:`is_from_car` says so.
    """
    entry = {"at": datetime.now().isoformat(timespec="seconds"), "kind": kind,
             "vin": vin or "", "bus": bus, "cable": cable, "stream": stream,
             "data": data}
    try:
        with _LOCK:
            with observations_path().open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def is_from_car(entry: dict[str, Any]) -> bool:
    """True only for an observation read from a real serial link."""
    s = str(entry.get("stream") or "")
    return s.startswith("serial") or s.startswith("recording(serial")


def recent_observations(n: int = 50, vin: str = "", kind: str = "") -> list[dict[str, Any]]:
    p = observations_path()
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if vin and obj.get("vin") != vin:  # untagged reads never match a named car
            continue
        if kind and obj.get("kind") != kind:
            continue
        out.append(obj)
    return out[-n:]


__all__ = ["path", "confirmed_targets", "confirm_target", "all_confirmations",
           "observations_path", "record_observation", "recent_observations", "is_from_car"]
