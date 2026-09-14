# Adapted from stelvio_scan (MIT): src/stelvio_scan/audit.py
"""JSONL audit log for live adapter operations.

Every connect, disconnect, OBD request, and clear-DTC operation is appended
as a single JSON line to a per-machine log file. Useful for shop liability —
proves what the tool did and when.

Log location (first writable wins, cached after the first call):
  1. `CUORE_AUDIT_PATH` env var, if set (exact file path, used verbatim).
  2. %PROGRAMDATA%\\cuore\\audit.jsonl
  3. %LOCALAPPDATA%\\cuore\\audit.jsonl
  4. ~/.cuore/audit.jsonl

Threadsafe: a single module-level lock guards file writes since the adapter
may run on a worker thread while other code logs from the main thread.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

__all__ = ["log_path", "record", "read_recent"]

_LOCK = threading.Lock()
_LOG_PATH: Path | None = None

_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB — rotate before exceeding this.


def _candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        candidates.append(Path(program_data) / "cuore")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "cuore")
    candidates.append(Path.home() / ".cuore")
    return candidates


def log_path() -> Path:
    """Return the path the audit log writes to. Resolved and cached on
    first use — see the module docstring for the resolution order."""
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH

    override = os.environ.get("CUORE_AUDIT_PATH")
    if override:
        p = Path(override)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        _LOG_PATH = p
        return _LOG_PATH

    last_error: OSError | None = None
    for d in _candidate_dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            last_error = e
            continue
        _LOG_PATH = d / "audit.jsonl"
        return _LOG_PATH

    # Nothing could be created (extremely unlikely) — fall back to cwd
    # rather than raising, since record()/read_recent() must never raise.
    log.warning("audit log_path: no candidate directory could be created (%s)", last_error)
    _LOG_PATH = Path("audit.jsonl")
    return _LOG_PATH


def _rotate_if_needed(path: Path) -> None:
    """If the log has grown past _MAX_BYTES, roll it to audit.1.jsonl
    (overwriting any previous .1) before the next append."""
    try:
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            rotated = path.with_name("audit.1.jsonl")
            try:
                if rotated.exists():
                    rotated.unlink()
            except OSError:
                pass
            path.rename(rotated)
    except OSError:
        pass


def record(event: str, **fields: Any) -> None:
    """Append a JSON-line event to the audit log. Never raises — if the log
    is unavailable for any reason, we drop the entry and log a warning."""
    try:
        now = time.time()
        entry: dict[str, Any] = {
            "ts": now,
            "iso": datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"),
            "event": event,
        }
        # Stringify non-JSON-serialisable bytes.
        for k, v in fields.items():
            if isinstance(v, bytes):
                entry[k] = v.hex().upper()
            else:
                entry[k] = v
        line = json.dumps(entry, default=str)
        with _LOCK:
            path = log_path()
            _rotate_if_needed(path)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        log.warning("audit record failed: %s", e)


def read_recent(n: int = 100) -> list[dict[str, Any]]:
    """Read the last n entries from the log. Returns oldest-first."""
    try:
        path = log_path()
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    except Exception as e:
        log.warning("audit read failed: %s", e)
        return []
