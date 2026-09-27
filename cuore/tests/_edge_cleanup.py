"""Stop every headless Edge process a test started.

Edge detaches from the process the test launches (the launcher exits and the
real browser, GPU and renderer processes live on), so Popen.terminate() alone
leaked the whole browser: 43 test runs left 266 msedge.exe processes running
(found 2026-09-26). Each test uses its own throwaway --user-data-dir, so
every process whose command line names that directory is ours to stop.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def kill_edge_profile(profile_dir: str | Path) -> int:
    """Kill every msedge.exe whose command line contains ``profile_dir``.
    Returns how many were stopped. Never touches the user's own Edge, whose
    command line does not name a temp test profile."""
    needle = str(profile_dir).replace("'", "''")
    ps = ("$n = '" + needle + "'; $k = 0; "
          "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
          "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($n) } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $k++ }; $k")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return int(out or 0)
    except Exception:  # noqa: BLE001 -- cleanup must never fail a test run
        return 0
