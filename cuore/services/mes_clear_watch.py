"""Auto-record MES fault-code clears on the open job.

A clear done with MultiEcuScan lives only in its log (``SCAN_*.txt`` or
``FESLog_*.txt``), so the repair log never learned about it unless someone
typed it in -- and a clean re-read after an unrecorded clear looks like a
repair. :func:`sync` closes that gap: it looks at the MES log folder
(``mes.paths`` -- ``MES_LOG_DIRS`` / ``MES_LOG_DIR`` / the install default),
parses only the logs newer than the last sync, and for each one that holds a
clear marker adds a ``clear`` action to the VIN's open job, dated to the log's
own timestamp and naming what was cleared and which codes were present first.

The clear detection is the parsers' own (the same one ``mes.workup`` and
``mes.analysis`` use): a SCAN log has clear-phase module blocks
(``ScanLog.clear_results``), a FES log has ``clear_events``. Simulation FES
logs are skipped (not from a car); logs with no VIN, or another car's VIN, are
skipped (cannot be attributed).

Only clears from the day the job was opened onward belong to it: a log
dated (by its filename stamp) before that day is never added, so a first
sync, or one after the sync point is lost, cannot back-fill months of old
clears onto whichever job happens to be open (2026-10-26: 20 clears from
June to October landed on the shudder job that way).

Idempotent: an action's ``ref.id`` is the log's filename, and a log whose
filename is already on a ``clear`` action of ANY of this VIN's jobs
(retracted ones included) is never added again.
Cheap: one directory listing plus a ``stat`` per log; nothing is parsed
unless a log's mtime is newer than both the last synced one (kept per VIN in
``state_dir()/mes_clear_watch.json``) and the start of the job's opening
day. Nothing is recorded, and the sync point does not move, while the VIN
has no open job.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live.config import state_dir

from mes import analysis as analysis_mod  # noqa: E402
from mes import fes as fes_mod  # noqa: E402
from mes import paths as paths_mod  # noqa: E402
from mes import scan as scan_mod  # noqa: E402

#: A log touched this recently may still be open in MES; wait for the next sync
#: rather than read a half-written file (same value as ``mes.catalog``).
SETTLE_SECONDS = 3.0


def _state_path():
    return state_dir() / "mes_clear_watch.json"


def _load_state() -> dict[str, Any]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def _event_date(raw_stamp: str) -> Optional[str]:
    try:
        return datetime.strptime(raw_stamp, "%y%m%d%H%M").isoformat(timespec="seconds")
    except ValueError:
        return None


def _job_day_start(job: dict[str, Any]) -> Optional[datetime]:
    """Midnight of the day ``job`` was opened, or ``None`` if unreadable."""
    try:
        opened = datetime.fromisoformat(str(job.get("opened_at") or ""))
    except ValueError:
        return None
    return opened.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _recorded_logs(vin: str) -> set[str]:
    """Log filenames already on a clear action of any of ``vin``'s jobs."""
    from . import jobs_bridge          # lazy: jobs_bridge imports this module
    have: set[str] = set()
    for j in jobs_bridge.jobs_mod.load(vin):
        for a in list(j.get("actions", [])) + list(j.get("retracted_actions", [])):
            if a.get("kind") == "clear":
                have.add((a.get("ref") or {}).get("id"))
    return have


def _join(items: list[str]) -> str:
    return ", ".join(items) if items else "none listed in this log"


def _scan_clear(path, name: str, stamp: str, vin: str) -> Optional[str]:
    """Description of the clear in one SCAN log for ``vin``, else ``None``."""
    log = scan_mod.load_scan(path, timestamp=stamp)
    if not log.clear_results or (log.vin or "").strip().upper() != vin:
        return None
    last: dict[str, Any] = {}
    for m in log.clear_results:        # an incomplete first attempt is superseded
        last[m.key] = m
    cleared = [m.name for m in last.values() if (m.clear_result or "").upper() == "SUCCESS"]
    refused = [f"{m.name} ({', '.join(d.full for d in m.dtcs) or 'no codes listed'})"
               for m in last.values() if (m.clear_result or "").upper() != "SUCCESS"]
    before = [f"{m.abbrev}: {', '.join(d.full for d in m.dtcs)}"
              for m in log.phase_entries(scan_mod.PHASE_SCAN) if m.dtcs]
    text = (f"MES cleared fault codes ({name}). Modules cleared: {_join(cleared)}. "
            f"Codes present before the clear: {_join(before)}.")
    if refused:
        text += f" Modules that refused to clear: {'; '.join(refused)}."
    return text


def _fes_clear(path, name: str, stamp: str, vin: str) -> Optional[str]:
    """Description of the clear in one engineering-session log for ``vin``."""
    log = fes_mod.load_fes(path, timestamp=stamp)
    if (log.simulation or not log.clear_events
            or (log.vin or "").strip().upper() != vin):
        return None
    ca = analysis_mod.post_clear_assessment(log)
    cleared = list(ca.cleared) if ca else []
    returned = list(ca.returned) if ca else []
    uncleared = list(ca.uncleared) if ca else []
    text = (f"MES cleared fault codes ({name}, {log.ecu_description or log.vehicle or 'ECU'} "
            f"session, {log.clear_events} clear event(s)). Codes present before the clear: "
            f"{_join(cleared + returned + uncleared)}.")
    if returned:
        text += f" Came back after the clear: {', '.join(returned)}."
    if uncleared:
        text += f" Would not clear: {', '.join(uncleared)}."
    return text


def sync(vin: str) -> list[dict[str, Any]]:
    """Add a ``clear`` action to ``vin``'s open job for every new MES log that
    holds a clear. Returns the actions added (empty when nothing was new, or
    there is no open job). Never raises for a bad/unreadable log."""
    vin = (vin or "").strip().upper()
    if not vin:
        return []
    from . import jobs_bridge          # lazy: jobs_bridge imports this module
    job = jobs_bridge.jobs_mod.current(vin)
    if not job:
        return []

    state = _load_state()
    vins = state.setdefault("vins", {})
    last = float((vins.get(vin) or {}).get("last_mtime") or 0.0)
    day_start = _job_day_start(job)
    floor = max(last, day_start.timestamp() if day_start else 0.0)

    new: list[tuple[float, Any]] = []
    for p in paths_mod.iter_log_files():
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime > floor and mtime <= time.time() - SETTLE_SECONDS:
            new.append((mtime, p))
    if not new:
        return []

    have = _recorded_logs(vin)
    added: list[dict[str, Any]] = []
    progressed = last
    for mtime, p in sorted(new, key=lambda t: (t[0], t[1].name)):
        kind, stamp, _vehicle = paths_mod.classify_name(p.name)
        ev = _event_date(stamp)
        if day_start and ev and datetime.fromisoformat(ev) < day_start:
            progressed = mtime          # an older visit's log touched later: not this job's
            continue
        try:
            text = (_scan_clear if kind == "scan" else _fes_clear)(p, p.name, stamp, vin)
        except Exception:  # noqa: BLE001 -- an unparseable log is simply not a clear
            text = None
        if text and p.name not in have:
            try:
                added.append(jobs_bridge.add_action(
                    job["id"], "clear", text, event_date=ev,
                    ref={"kind": "observation", "id": p.name,
                         "label": f"MES clear in {p.name}"}))
            except Exception:  # noqa: BLE001 -- retry this log on the next sync
                break
            have.add(p.name)
        progressed = mtime
    if progressed > last:
        vins[vin] = {"last_mtime": progressed,
                     "synced_at": datetime.now().isoformat(timespec="seconds")}
        _save_state(state)
    return added


__all__ = ["sync"]
