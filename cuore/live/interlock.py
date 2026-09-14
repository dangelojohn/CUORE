"""The MES interlock: is MultiEcuScan running, and does it hold the adapter?

Two signals, both readable without elevation even though MES runs elevated:

* the process list, via ``tasklist``;
* the text of MES's own status label, read with ``GetWindowTextW`` across the
  integrity boundary. ``Disconnected`` means the port is free from MES's side;
  anything starting ``Connected``/``Connecting`` means it is not.

Plus an advisory lock file so two cuore or obd2 processes warn each other.
MES does not honour the lock, which is why the label check exists.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import IS_WINDOWS, state_dir
from .errors import LinkUnavailable

MES_EXE = "Multiecuscan.exe"


def mes_pids() -> list[int]:
    if not IS_WINDOWS:
        return []
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {MES_EXE}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.strip().split('","')]
        if len(parts) >= 2 and parts[0].lower() == MES_EXE.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def _window_texts_for_pids(pids: set[int]) -> list[str]:
    if not IS_WINDOWS or not pids:
        return []
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    texts: list[str] = []
    buf = ctypes.create_unicode_buffer(512)

    def grab(hwnd: int) -> None:
        if user32.GetWindowTextW(hwnd, buf, 512) > 0:
            texts.append(buf.value)

    def child_cb(hwnd, _l):
        grab(hwnd)
        return True

    child_proc = WNDENUMPROC(child_cb)

    def top_cb(hwnd, _l):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            grab(hwnd)
            user32.EnumChildWindows(hwnd, child_proc, 0)
        return True

    user32.EnumWindows(WNDENUMPROC(top_cb), 0)
    return texts


def mes_status() -> dict[str, Any]:
    """``state`` is not_running, disconnected, connected or unknown."""
    pids = mes_pids()
    if not pids:
        return {"running": False, "pids": [], "state": "not_running", "label": None}
    label, state = None, "unknown"
    for t in _window_texts_for_pids(set(pids)):
        s = t.strip()
        if s == "Disconnected":
            label, state = s, "disconnected"
            break
        if s.startswith(("Connected", "Connecting")):
            label, state = s, "connected"
            break
    return {"running": True, "pids": pids, "state": state, "label": label}


# --- advisory lock file -----------------------------------------------------

def lock_path() -> Path:
    return state_dir() / "adapter.lock"


def _pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if not IS_WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def read_lock() -> Optional[dict[str, Any]]:
    p = lock_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    data["stale"] = not _pid_alive(int(data.get("pid", -1)))
    data["path"] = str(p)
    return data


def acquire(port: str, purpose: str, process: str = "cuore") -> None:
    existing = read_lock()
    if existing and not existing["stale"] and existing.get("pid") != os.getpid():
        raise LinkUnavailable(
            f"adapter lock held by pid {existing.get('pid')} ({existing.get('process', '?')}: "
            f"{existing.get('purpose', '?')} on {existing.get('port', '?')} since "
            f"{existing.get('since', '?')}). Lock file: {existing['path']}")
    payload = {"pid": os.getpid(), "port": port, "purpose": purpose, "process": process,
               "since": datetime.now().isoformat(timespec="seconds")}
    try:
        lock_path().write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # advisory only; the serial open is the real arbiter


def release() -> None:
    p = lock_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("pid") == os.getpid():
            p.unlink()
    except (OSError, ValueError):
        pass


def blocked_by() -> Optional[str]:
    """One sentence for ``AdapterInfo.blocked_by``, or None when the port looks free."""
    ms = mes_status()
    if ms["state"] == "connected":
        return f"MultiEcuScan is connected ({ms['label']}, pids {ms['pids']})"
    lock = read_lock()
    if lock and not lock["stale"] and lock.get("pid") != os.getpid():
        return (f"{lock.get('process', 'another process')} pid {lock.get('pid')} holds the "
                f"adapter for {lock.get('purpose', '?')}")
    return None


__all__ = ["MES_EXE", "mes_pids", "mes_status", "lock_path", "read_lock", "acquire",
           "release", "blocked_by"]
