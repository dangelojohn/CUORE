"""Run Claude Code headless for "Ask Claude here" (read-only, one at a time).

The prompt goes in on stdin; the CLI is limited to read-only mes-log MCP
tools. Every obd2 tool, shell, file-edit and web tool is denied, as are the
mes-log tools that write. Jobs live in memory; one runs at a time (lock).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

REPO_DIR = Path(__file__).resolve().parents[2]
TIMEOUT_S = 300
FALLBACK_CLI = Path.home() / ".local" / "bin" / "claude.exe"

ALLOWED_TOOLS = [
    "mcp__mes-log__notes", "mcp__mes-log__dtc_history", "mcp__mes-log__job_current",
    "mcp__mes-log__cuore_read_scan", "mcp__mes-log__cuore_list_scans",
    "mcp__mes-log__cuore_latest_scan", "mcp__mes-log__symptoms",
    "mcp__mes-log__dtc_description", "mcp__mes-log__systems_for_code",
    "mcp__mes-log__workup", "mcp__mes-log__get_freeze_frame",
    "mcp__mes-log__failure_type", "mcp__mes-log__module_info",
    "mcp__mes-log__experience_links", "mcp__mes-log__fault_tree",
]
DISALLOWED_TOOLS = [
    "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent",
    "mcp__obd2",  # whole server: nothing may touch the car
    "mcp__mes-log__add_note", "mcp__mes-log__edit_note", "mcp__mes-log__hide_note",
    "mcp__mes-log__add_symptom", "mcp__mes-log__hide_symptom",
    "mcp__mes-log__job_open", "mcp__mes-log__job_add_action",
    "mcp__mes-log__job_add_evidence", "mcp__mes-log__job_add_hypothesis",
    "mcp__mes-log__job_set_hypothesis", "mcp__mes-log__job_edit_hypothesis",
    "mcp__mes-log__job_delete_hypothesis", "mcp__mes-log__job_undelete_hypothesis",
    "mcp__mes-log__job_remove_evidence", "mcp__mes-log__feedback_add",
    "mcp__mes-log__feedback_answer", "mcp__mes-log__record_dealer_result",
    "mcp__mes-log__electrical_inspection_add", "mcp__mes-log__tool_inventory_set",
    "mcp__mes-log__tool_usage_add", "mcp__mes-log__tool_learn",
    "mcp__mes-log__shop_intake", "mcp__mes-log__shop_release",
]

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def cli_path() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    return str(FALLBACK_CLI) if FALLBACK_CLI.exists() else None


def available() -> bool:
    return cli_path() is not None


def build_command(cli: str) -> list[str]:
    return [cli, "-p", "--output-format", "json", "--no-session-persistence",
            "--permission-mode", "dontAsk",
            "--allowedTools", ",".join(ALLOWED_TOOLS),
            "--disallowedTools", ",".join(DISALLOWED_TOOLS)]


def parse_output(stdout: str) -> str:
    """The answer text from ``--output-format json`` (falls back to raw text)."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return stdout.strip()
    if isinstance(data, list):  # some versions return the event array
        data = next((d for d in reversed(data) if isinstance(d, dict) and "result" in d), {})
    if isinstance(data, dict):
        if data.get("is_error"):
            return "Claude reported an error: " + str(data.get("result") or "unknown")
        return str(data.get("result") or "").strip()
    return str(data)


def _run(job_id: str, prompt: str) -> None:
    job = _jobs[job_id]
    try:
        cli = cli_path()
        if not cli:
            raise FileNotFoundError("claude CLI not found")
        proc = subprocess.run(build_command(cli), input=prompt, capture_output=True,
                              text=True, encoding="utf-8", timeout=TIMEOUT_S,
                              cwd=str(REPO_DIR))
        if proc.returncode != 0 and not (proc.stdout or "").strip():
            job.update(state="error",
                       error=(proc.stderr or "claude exited with an error").strip()[:500])
        else:
            job.update(state="done", answer=parse_output(proc.stdout))
    except subprocess.TimeoutExpired:
        job.update(state="error", error=f"Timed out after {TIMEOUT_S // 60} minutes.")
    except Exception as exc:  # noqa: BLE001
        job.update(state="error", error=f"{type(exc).__name__}: {exc}"[:500])
    finally:
        job["finished"] = time.time()
        _lock.release()


def start(prompt: str, *, wait: bool = False) -> dict[str, Any]:
    """Start a run -> ``{"job_id"}`` or ``{"busy": True}`` / ``{"unavailable": True}``."""
    if not available():
        return {"unavailable": True}
    if not _lock.acquire(blocking=False):
        return {"busy": True}
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {"state": "running", "started": time.time(), "answer": "", "error": ""}
    for old in [k for k, v in _jobs.items()
                if v.get("finished") and time.time() - v["finished"] > 3600]:
        _jobs.pop(old, None)
    try:
        t = threading.Thread(target=_run, args=(job_id, prompt), daemon=True)
        t.start()
    except Exception:
        _lock.release()
        raise
    if wait:
        t.join()
    return {"job_id": job_id}


def status(job_id: str) -> dict[str, Any] | None:
    j = _jobs.get(job_id)
    return dict(j) if j else None
