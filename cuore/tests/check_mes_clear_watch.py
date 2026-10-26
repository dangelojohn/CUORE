"""Checks for cuore.services.mes_clear_watch (MES clears auto-recorded on the open job).

Throwaway ``CUORE_STATE_DIR`` and ``MES_LOG_DIR`` so nothing real is read or
written; the log fixtures are synthetic MES SCAN transcripts.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_mes_clear_watch.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

LOGS = Path(tempfile.mkdtemp(prefix="cuore-check-clearwatch-logs-"))
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-clearwatch-state-")
os.environ["MES_LOG_DIR"] = str(LOGS)
os.environ.pop("MES_LOG_DIRS", None)
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.services import jobs_bridge, mes_clear_watch  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


ECM_BLOCK = f"""Engine / ECM
Magneti Marelli Test ECU
ISO Code: 00 01 50 40 18
VIN code: {VIN}
Hardware number: HW1 - Ver: 01
Software number: SW1 - Ver: 01
"""
SCAN_WITH_CLEAR = (ECM_BLOCK + "Errors found:\nP0455-00 - Evaporation system leak\n"
                   "P0456-00 - Evaporation system leak\n\n"
                   "CLEARING STORED FAULT CODES...\n\n"
                   "Engine / ECM\nMagneti Marelli Test ECU\nISO Code: 00 01 50 40 18\nSUCCESS\n")
SCAN_NO_CLEAR = ECM_BLOCK + "Errors found:\nP0455-00 - Evaporation system leak\n"


def put(name: str, text: str, age_s: float) -> None:
    p = LOGS / name
    p.write_text(text, encoding="utf-8")
    t = time.time() - age_s
    os.utime(p, (t, t))


def clears(job_id: str) -> list[dict]:
    return [a for a in jobs_bridge.get_job(job_id)["actions"] if a.get("kind") == "clear"]


def stamp(dt: datetime) -> str:
    return dt.strftime("%y%m%d%H%M")


NOW = datetime.now().replace(second=0, microsecond=0)
TODAY_LOG = f"SCAN_{stamp(NOW)}.txt"        # NOW, so it never falls on yesterday
OLD_LOG = f"SCAN_{stamp(NOW - timedelta(days=30))}.txt"

job = jobs_bridge.open_job(VIN, complaint="EVAP codes")

# An older visit's log (dated a month back) that was copied or touched just
# now: its mtime is new, but its own date is before the job was opened.
put(OLD_LOG, SCAN_WITH_CLEAR, 180)
put(TODAY_LOG, SCAN_WITH_CLEAR, 120)
added = mes_clear_watch.sync(VIN)
rec = clears(job["id"])
check("a log dated before the job's opening day is never added, however new its mtime "
      "(no back-filling old clears onto the open job)",
      all((a["ref"] or {}).get("id") != OLD_LOG for a in rec), str(rec))
check("a new MES log with a clear adds one clear action: ref id = filename, event_date = "
      "the log's timestamp, text names the module and the codes present before the clear",
      len(added) == 1 and len(rec) == 1
      and (rec[0]["ref"] or {}).get("id") == TODAY_LOG
      and rec[0]["event_date"] == NOW.isoformat(timespec="seconds")
      and "Engine / ECM" in rec[0]["text"] and "P0455-00" in rec[0]["text"]
      and "P0456-00" in rec[0]["text"], str(rec))

again = mes_clear_watch.sync(VIN)
(Path(os.environ["CUORE_STATE_DIR"]) / "mes_clear_watch.json").unlink()   # forget the sync point
forced = mes_clear_watch.sync(VIN)
check("the same log again (and again after the sync point is lost) adds no duplicate",
      again == [] and forced == [] and len(clears(job["id"])) == 1,
      f"{again} {forced} {len(clears(job['id']))}")

put(f"SCAN_{stamp(NOW + timedelta(minutes=1))}.txt", SCAN_NO_CLEAR, 60)
none = mes_clear_watch.sync(VIN)
check("a newer log without a clear adds nothing",
      none == [] and len(clears(job["id"])) == 1, str(none))

# A second open job: a log already recorded on the first job is not added
# to it again, even with the sync point lost.
job2 = jobs_bridge.open_job(VIN, complaint="shudder")
(Path(os.environ["CUORE_STATE_DIR"]) / "mes_clear_watch.json").unlink()
other = mes_clear_watch.sync(VIN)
check("a log already on a clear action of another of this VIN's jobs is not added again",
      other == [] and clears(job2["id"]) == [], f"{other} {clears(job2['id'])}")

# Retracting an action: it leaves the repair log, stays on record with the
# reason, and a later sync does not bring it back.
first = clears(job["id"])[0]
r = jobs_bridge.retract_action(job["id"], first["id"], "recorded on the wrong job")
j = jobs_bridge.get_job(job["id"])
check("a retracted action leaves actions and is kept under retracted_actions with its reason",
      r["action_id"] == first["id"] and clears(job["id"]) == []
      and any(a["id"] == first["id"] and a["retract_reason"] == "recorded on the wrong job"
              for a in j["retracted_actions"]), str(j["retracted_actions"]))
(Path(os.environ["CUORE_STATE_DIR"]) / "mes_clear_watch.json").unlink()
back = mes_clear_watch.sync(VIN)
check("a retracted clear's log is not re-added by a later sync",
      back == [] and clears(job["id"]) == [] and clears(job2["id"]) == [], str(back))
try:
    jobs_bridge.retract_action(job["id"], first["id"], "again")
    check("retracting an action that is no longer on the job is refused", False)
except Exception as exc:  # noqa: BLE001
    check("retracting an action that is no longer on the job is refused",
          type(exc).__name__ == "BadRequest", repr(exc))

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
