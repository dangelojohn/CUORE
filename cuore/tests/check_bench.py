"""Smoke checks for the bench page (``GET /v/{vin}``, cuore/services/bench_bridge.py,
cuore/web/bench_routes.py, cuore/web/templates/bench.html).

Same posture as ``cuore/tests/check_dossier_page.py``: ``CUORE_STATE_DIR``
pointed at a throwaway directory before cuore is imported, the Stelvio's
real corpus as the fixture (chronic P0455/P0440/P0456, cleared 2026-09-29,
never re-verified -- see project_stelvio_evap.md). No mocks: the five checks
below all run against the real app and the real corpus.

Five checks:
  1. ``GET /v/{vin}`` responds 200, the status line names the Stelvio (and
     never "(unnamed vehicle)"), and the old dossier still answers at
     ``/v/{vin}/dossier``.
  2. The verdict's ``next_action`` sentence mentions the 85% EVAP fuel
     ceiling and cites a real bulletin for this VIN.
  3. Exactly up to 3 next-action cards render, and at least one carries a
     real part number.
  4. ``/v/{vin}/dossier`` still responds 200 (the route this file's own
     sibling, check_dossier_page.py, now hits instead of the bare path).
  5. A 400px CDP screenshot: the first next-action card's bounding box top
     is inside the viewport (< 800px) and the page has no horizontal
     overflow at that width.

Run:
    .venv/Scripts/python.exe cuore/tests/check_bench.py
"""

from __future__ import annotations

import itertools
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-bench-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# MES_LOG_DIR: an isolated copy of the real corpus, frozen before this
# suite's own 2026-10-13 live-scan fixture (SCAN_AT below) -- same posture
# as check_mil.py's ``_place_scan`` and check_review6_logic.py. Without
# this, a later real scan landing in the corpus (e.g. 2026-10-14 08:59's
# SCAN_2610140859.txt) becomes the newest log, newer than SCAN_AT, and
# silently flips the "which clock is newer" check below even though the
# real logic (pick whichever read is actually newest) is working exactly
# as intended.
_REAL_MES_DIR = Path(r"C:\Program Files (x86)\MultiEcuScan")
_MES_LOG_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-bench-logs-"))
os.environ["MES_LOG_DIR"] = str(_MES_LOG_DIR)
_SCENARIO_CUTOFF = "261013"  # YYMMDD -- this suite's own scenario cutoff
if _REAL_MES_DIR.exists():
    for _f in _REAL_MES_DIR.iterdir():
        if not _f.is_file():
            continue
        _m = re.search(r"_(\d{6})\d{4}", _f.name)
        if _m and _m.group(1) > _SCENARIO_CUTOFF:
            continue
        shutil.copyfile(_f, _MES_LOG_DIR / _f.name)

from fastapi.testclient import TestClient  # noqa: E402
from markupsafe import escape as _escape  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import checklists as checklist_store  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.services import bench_bridge, mes_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

# --- Last scan card fixture: one guided scan, dated "right now" (never a
# hard-coded calendar date -- the N1 check below is specifically about
# today's live scan beating an older MES-log date, so the fixture must
# always actually be today, whatever day this runs), so the bench's own
# "Scan n of 10" chip reads "Scan 1 of 10" and the coverage line matches
# the owner's own spec wording exactly. Hand-built and appended to a
# throwaway observations.jsonl (CUORE_STATE_DIR above), same posture as
# cuore/tests/check_scanlog.py's own fixture -- never COM3, never the real
# C:\ProgramData\cuore\observations.jsonl. -------------------------------

SCAN_AT = datetime.now().replace(microsecond=0)
SCAN_ID = "SCAN_" + SCAN_AT.strftime("%y%m%d%H%M")


def _write_obs(at: datetime, kind: str, data: dict, *, stream: str = "serial COM3@115200") -> None:
    entry = {"at": at.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "vin": VIN,
             "bus": "can_c", "cable": "none", "stream": stream, "data": data}
    with live_store.observations_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


#: No ``obd_dtcs`` observation here on purpose: a live DTC read for this
#: VIN would merge into the dossier's own live overlay and shift the
#: verdict this suite's other checks depend on (85% fuel wording,
#: CLEARED_UNVERIFIED) -- the scan_coverage observation alone is already
#: enough to produce one scan with a coverage line (empty DTC buckets on
#: the scan itself, which is fine: the card's own "active/history" grouping
#: is exercised directly in cuore/tests/check_scanlog.py).
_write_obs(SCAN_AT, "scan_coverage", {
    "scan_id": SCAN_ID, "vin": VIN, "cable": "none", "buses_attempted": ["can_c"],
    "duration_s": 10.0, "steps": [],
    "coverage": [{"bus": "can_c", "module": m, "category": "answered", "why": None,
                 "active": 0, "history": 0, "not_run": 0}
                for m in ("ECM", "IPC", "TCM", "DTCM", "ESM")],
    "counts": {"active": 0, "history": 0, "not_run": 0},
})

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())


# --- build_bench() directly ------------------------------------------------

bench = bench_bridge.build_bench(VIN)
check("vehicle name is never the unnamed placeholder",
      bench["vehicle"] != "(unnamed vehicle)" and bool(bench["vehicle"]), str(bench["vehicle"]))
check("vehicle name names the Stelvio", "Stelvio" in bench["vehicle"], str(bench["vehicle"]))
check("vin_tail is the VIN's last 6 characters", bench["vin_tail"] == VIN[-6:],
      str(bench["vin_tail"]))
# LAYOUT CHANGE (bench UX review 2026-10-26): the roster is no longer capped at 3;
# every step is numbered "Step n of N" and the page leads with the next undone one.
check("every step is numbered n of N",
      all(a.get("n") == i and a.get("of") == len(bench["next_actions"]) for i, a in enumerate(bench["next_actions"], 1)),
      str([(a.get("n"), a.get("of")) for a in bench["next_actions"]]))
_undone = [a for a in bench["next_actions"] if not a["done"]]
check("the lead step is the first READY undone step (never a done one)",
      (bench["next_step"] is None and not _undone)
      or (bench["next_step"] is not None and not bench["next_step"]["done"]
          and bench["next_step"] is next((a for a in _undone if a["state"] == "READY"), _undone[0])),
      str(bench["next_step"] and bench["next_step"]["step_id"]))
check("at most 6 shortcuts", len(bench["shortcuts"]) <= 6, str(len(bench["shortcuts"])))

# --- Last scan card (bench_bridge.last_scan_summary) -----------------------

last_scan = bench.get("last_scan")
check("bench carries a last_scan summary for this VIN", last_scan is not None, str(last_scan))
if last_scan:
    check("last_scan id matches the fixture scan", last_scan["id"] == SCAN_ID,
          str(last_scan["id"]))
    check("last_scan plan chip reads 'Scan 1 of 10' (one scan on file)",
          last_scan["plan"] == {"count": 1, "total": 10}, str(last_scan["plan"]))
    check("last_scan is not partial (it has a scan_coverage observation)",
          last_scan["partial"] is False, str(last_scan["partial"]))
    check("last_scan's coverage line matches the owner's own spec wording",
          last_scan["coverage_line"] ==
          "CAN-C 5 modules · IHS not scanned (blue A5) · CH not scanned (grey A6)",
          str(last_scan["coverage_line"]))
    check("last_scan source names the adapter", last_scan["source"] == "serial COM3@115200",
          str(last_scan["source"]))
    check("last_scan has no 'compare with previous' link (only one scan on file)",
          last_scan["compare_href"] is None, str(last_scan["compare_href"]))


# --- 1. the real route: GET /v/{vin} is the bench, GET /v/{vin}/dossier is
#    still the full dossier -----------------------------------------------

page = client.get(f"/v/{VIN}")
check("bench page responds 200", page.status_code == 200, str(page.status_code))
check("bench status line names the Stelvio", "Stelvio" in page.text)
check("bench status line never shows the unnamed placeholder",
      "(unnamed vehicle)" not in page.text)
_bcss = re.search(r"\.bench-go \{[^}]*\}", page.text).group(0)
check("Go-to chip strip wraps instead of scrolling", "flex-wrap: wrap" in _bcss and "overflow-x" not in _bcss, _bcss)
_card = page.text.split('class="bench-card"')[1] if 'class="bench-card"' in page.text else ""
# LAYOUT CHANGE: status chip, then the title, then the one-tap OK / Fault found / Skip buttons
# (the Save button and the dead "Mark done" tick are gone).
check("lead step: status chip, then title, then the three one-tap buttons",
      (not _card) or (_card.find("bench-state-badge") < _card.find("bench-card-text") < _card.find("bench-onetap")),
      "order")
check("one-tap outcome buttons are 44 px controls", ".bench-onetap .btn { min-height: 44px" in page.text)
check("no Save button and no Mark done tick on the bench", ">Save</button>" not in page.text
      and "bench-check" not in page.text and "Mark done" not in page.text)
check("no Fixed row is hidden in the Last scan fold (one Faults list)", "Standing &middot; work on now" not in page.text
      and 'id="bench-worknow-row"' not in page.text)
check("Faults list has a Fixed (or Undo) form per present fault",
      page.text.count(f'action="/v/{VIN}/fault-board/fixed"') == len([f for f in bench["faults"] if f["can_fix"]])
      and page.text.count(f'action="/v/{VIN}/fault-board/undo"') == len([f for f in bench["faults"] if not f["can_fix"] and f["can_undo"]]),
      str(len(bench["faults"])))
check("Fixed is a 44 px control", ".bench-fixed-btn { min-height: 44px" in page.text)
# unit checks on the pure pieces (the fixture corpus may carry no present fault)
_views = [{"kind": "code", "status": "permanent", "key": "code:ECM:P0440", "code": "P0440", "module": "ECM",
           "label": "Permanent", "mark": "!", "chip": "returned", "returned": False,
           "last_seen_text": "14 h ago · 2026-10-26", "present_text": "first seen 60 d ago · present since 2026-10-23 (3 d)",
           "can_fix": True, "can_undo": False},
          {"kind": "code", "status": "history", "key": "code:ECM:P0455", "code": "P0455", "module": "ECM",
           "label": "Stored history", "mark": "", "chip": "plain", "returned": False, "last_seen_text": "3 d ago",
           "present_text": "", "can_fix": True, "can_undo": False},
          {"kind": "code", "status": "verifying", "key": "code:ECM:P0456", "code": "P0456", "module": "ECM",
           "label": "Verifying", "mark": "~", "chip": "chronic", "returned": False, "last_seen_text": "1 d ago · x",
           "present_text": "", "can_fix": False, "can_undo": True}]
_f = bench_bridge._faults(VIN, _views)
check("Faults keep present, permanent and verifying only (history stays on the Job page)",
      [x["name"] for x in _f] == ["P0440", "P0456"], str([x["name"] for x in _f]))
check("a fault row carries module, last seen, present N d and its electrical path link",
      _f[0]["module"] == "ECM" and _f[0]["seen"] == "14 h ago" and _f[0]["present"] == "present 3 d"
      and _f[0]["path_href"] == f"/v/{VIN}/electrical?code=P0440", str(_f[0]))
check("a verifying fault offers Undo, not Fixed", _f[1]["can_undo"] and not _f[1]["can_fix"])
_banner = {"is_blocker": False, "action": "x"}
check("the call: no blocker + connected -> the top fault",
      bench_bridge.call_line(_banner, {"level": None}, True, _f).startswith("P0440 permanent"),
      bench_bridge.call_line(_banner, {"level": None}, True, _f))
check("the call: not connected is a blocker ahead of the top fault",
      bench_bridge.call_line(_banner, {"level": None}, False, _f).startswith("Not connected"))
check("the call: the fuel gate blocker still comes first",
      bench_bridge.call_line({"is_blocker": True, "action": "x"},
                             {"level": 93.7, "window": [15, 85], "direction": "above"}, False, _f).startswith("Fuel 93.7 %"))
check("each code fault links its electrical path",
      all(f["path_href"] in page.text for f in bench["faults"] if f["path_href"]))
_first_code_fault = next((f["name"] for f in bench["faults"] if f["kind"] == "code"), None)
check("Go-to System chip follows the TOP fault (first code fault), not shortcuts[0]",
      bench["top_fault_code"] == _first_code_fault, f"{bench['top_fault_code']} vs {_first_code_fault}")
check("the System: chip renders in the Go-to row", "System:" in page.text.split('aria-label="Go to"')[1].split("</nav>")[0])
check("bench rows are full width, min 44 px", ".bench-card {" in page.text and "width: 100%; min-height: 44px" in page.text)
check("bench status line carries the VIN tail",
      VIN[-6:] in page.text, VIN[-6:])

check("the Last scan card shows the scan id", SCAN_ID in page.text, "scan id not on page")
check("the Last scan card shows the scan plan chip 'Scan 1 of 10'",
      "Scan 1 of 10" in page.text, "'Scan 1 of 10' not on page")
check("the Last scan card shows the coverage wording",
      "CAN-C 5 modules" in page.text and "not scanned" in page.text,
      "coverage wording not on page")
check("the Last scan card links Open scan and Health report",
      f'href="/v/{VIN}/scans/{SCAN_ID}"' in page.text
      and f'href="/v/{VIN}/scans/{SCAN_ID}/health"' in page.text,
      "Last scan card links missing")


# --- mechanic-first polish (review_bench_job_codes_live.md) -----------------
import re as _re
_call_m = _re.search(r'<p class="bench-next-action">(.*?)</p>', page.text, _re.S)
_call = _re.sub(r"\s+", " ", _call_m.group(1)).strip() if _call_m else ""
check("the call renders as ONE line (single paragraph, no newline)", bool(_call) and len(_call) <= 120, _call)
_fg = bench["fuel_gate"]
if _fg.get("level") is not None and _fg.get("direction") == "above":
    check("the one-line call carries the fuel gate readout",
          _call.startswith("Fuel ") and " % - burn below " in _call and "drive cycle" in _call, _call)
    check("litres-to-burn reads 'n/a - tank capacity not sourced' (no bare UNKNOWN)",
          "litres to burn: n/a - tank capacity not sourced" in page.text
          and "litres to burn: UNKNOWN" not in page.text)
check("the call's Why? is a 44 px / 16 px fold",
      "min-height: 44px" in page.text and ".bench-why summary" in page.text)
check("last scan is collapsed to one summary line inside a closed fold",
      bench["last_scan_line"].startswith("Last scan ")
      and '<details class="bench-lastscan">' in page.text
      and f"<summary>{bench['last_scan_line']}</summary>" in page.text,
      str(bench["last_scan_line"]))
check("scan links sit under one 'Scan' drill-down in the Go-to row",
      'class="bench-scan"' in page.text and 'aria-label="Go to"' in page.text
      and page.text.count(">Scan</summary>") == 1)
check("task rows carry a READY/BLOCKED chip",
      bool(_re.search(r'bench-state-badge state-(ready|blocked)">(READY|BLOCKED)</span>', page.text)))
_blocked = [a for a in bench["next_actions"] if a["state"] == "BLOCKED"]
if _blocked:
    check("a BLOCKED row states its reason in the row text",
          any((a["blocked_reason"] or "") in page.text for a in _blocked))
    check("a BLOCKED row states the unblock step", any(a.get("unblock") for a in _blocked)
          and "to unblock:" in page.text)
check("unknown tools are not asked inline ('unknown: ask' is gone)", "unknown: ask" not in page.text)
if any(a["tools"] for a in bench["next_actions"]) or bench["job_tools"]:
    check("tools sit in a collapsed 'Tools' fold", "bench-tools-fold" in page.text and "<summary>Tools (" in page.text)
check("the resume row no longer repeats the vehicle bar's scanner state",
      "Scanner:" not in page.text.split('class="bench-resume"')[-1].split("bench-gates")[0])
check("done-by is auto-filled from the open job's technician when known (no typing on the one-tap form)",
      (not bench["technician"]) or ('name="by" value=' in page.text))
check("code legend has explicit separators", (not bench["shortcuts"]) or "bench-legend-sep" in page.text)


# --- N1 (MECHANIC_REVIEW_4_SCANS_HEALTH_2026-10-13.md): the resume card's
# own "last scan ... ago"/stale flag must track whichever clock is newer --
# the live scan above (SCAN_AT, dated today) or the MES-log-derived
# current_picture (this VIN's real corpus tops out 2026-10-08/2026-10-04,
# days before SCAN_AT) -- never silently answer from the older MES-log
# clock alone while a same-day live scan is named one card above it.
resume = bench["resume"]
check("resume card's last_scan_at is the live scan's own timestamp (today), "
      "not an older MES-log date",
      resume["last_scan_at"] == SCAN_AT.strftime("%Y-%m-%dT%H:%M:%S"),
      f"{resume['last_scan_at']!r} vs live scan {SCAN_AT.isoformat()!r}")
check("resume card is not flagged stale when today's live scan is the newest read",
      bench["scan_stale"] is False, str(bench["scan_stale"]))
check("resume card's 'last scan ... ago' wording does not say days ago "
      "when the live scan itself was today",
      "d ago" not in resume["last_scan_relative"], resume["last_scan_relative"])
check("no 'stale (> 24 h)' badge renders on the page next to today's live scan",
      "stale (&gt; 24 h)" not in page.text and "stale (> 24 h)" not in page.text,
      "stale badge found on page despite today's live scan")

dossier_page = client.get(f"/v/{VIN}/dossier")
check("the old dossier still responds 200 at /v/{vin}/dossier",
      dossier_page.status_code == 200, str(dossier_page.status_code))
check("the old dossier page still shows its own verdict card",
      'class="chip-verdict' in dossier_page.text)
check("the bench page is not the same page as the dossier",
      'id="verdict"' not in page.text)


# --- 2. verdict.next_action mentions 85% and a real bulletin --------------

next_action = bench["verdict"]["next_action"] or ""
check("next_action is a non-empty sentence", bool(next_action.strip()), next_action)
check("next_action mentions the 85% EVAP fuel ceiling", "85" in next_action, next_action)

all_bulletins = {
    b for card in (bench_bridge.dossier_bridge.build_view(
        VIN, bench_bridge.mes_bridge.workup(vin=VIN), None)["open_work"])
    for step in card.get("steps", []) for b in [step.get("ref")] if b
}
check("next_action cites one of this VIN's real bulletins",
      any(b in next_action for b in all_bulletins), f"{next_action!r} vs {all_bulletins}")
check("next_action also appears on the rendered bench page", next_action in page.text)


# --- 3. next-action cards carry at least one real part number -------------

check("at least one next action is offered", len(bench["next_actions"]) > 0,
      str(bench["next_actions"]))
any_part_number = (
    any(p.get("number") for a in bench["next_actions"] for p in a.get("parts", []))
    or any(p.get("number") for p in bench.get("job_parts", [])))
check("at least one next action (or the job-level shared list) carries a real "
      "part number", any_part_number,
      str([a.get("parts") for a in bench["next_actions"]] + [bench.get("job_parts")]))
# LAYOUT CHANGE: one form per READY undone step (3 submit buttons) and one Undo form per done step.
_ready_undone = [a for a in bench["next_actions"] if not a["done"] and a["state"] == "READY"]
_done_n = len([a for a in bench["next_actions"] if a["done"]])
_done_action = 'action="/v/' + VIN + '/bench/done"'
check("every READY step posts its one-tap outcome to the bench's own route; done steps post Undo",
      page.text.count(_done_action) == len(_ready_undone) + _done_n,
      f"{page.text.count(_done_action)} vs {len(_ready_undone)}+{_done_n}")
check("each one-tap form has OK, Fault found and Skip submit buttons",
      page.text.count('name="outcome" value="ok"') == len(_ready_undone)
      and page.text.count('name="outcome" value="fault_found"') == len(_ready_undone)
      and page.text.count('name="outcome" value="skipped"') == len(_ready_undone))

for a in bench["next_actions"]:
    check(f"step {a['step_id']} text is on the page", str(_escape(a["text"])) in page.text)
    for p in a.get("parts", []):
        if p.get("number"):
            check(f"part number {p['number']} is on the page", p["number"] in page.text)
for p in bench.get("job_parts", []):
    if p.get("number"):
        check(f"job-level shared part number {p['number']} is on the page",
              p["number"] in page.text)


# --- ticking a real checklist step from the bench's own form works -------

if bench["next_actions"]:
    step_id = bench["next_actions"][0]["step_id"]
    toggled = client.post(f"/v/{VIN}/checklist", data={"step_id": step_id, "done": "1"},
                          follow_redirects=False)
    check("ticking a step from the bench's own form is accepted",
          toggled.status_code == 303, str(toggled.status_code))
    # leave it as we found it
    client.post(f"/v/{VIN}/checklist", data={"step_id": step_id, "done": "0"})


# --- BENCH_UX_SPEC_2026-10-08.md: the six check-list items ----------------

# 1. resume card present with "last scan" and "N of M done"
check("the one-line last-scan summary is shown (resume row no longer repeats it)", "Last scan " in page.text)
check("the resume card shows the N of M done progress",
      f"{bench['progress']['done']} of {bench['progress']['total']} done" in page.text,
      f"{bench['progress']}")

# 2. a task expands to show "Pass =" and a procedure step
sourced = next((a for a in bench["next_actions"] if a["detail"]["procedure"]["test"]), None)
check("at least one task has a sourced fault-tree procedure step",
      sourced is not None, str([a["detail"] for a in bench["next_actions"]]))
if sourced:
    check("that task's procedure step text is on the page",
          sourced["detail"]["procedure"]["test"] in page.text)
    check('that task shows a "Pass = ..." line on the page',
          f"Pass = {sourced['detail']['pass_line']}" in page.text)

# 3. mark done with outcome "fault found" stores the note and shows DONE
if bench["next_actions"]:
    fault_step_id = bench["next_actions"][0]["step_id"]
    finding = "bench check: smoke test shows a leak at the recirculation line"
    marked = client.post(f"/v/{VIN}/bench/done",
                         data={"step_id": fault_step_id, "done": "1",
                               "outcome": "fault_found", "note": finding, "by": "check_bench"},
                         follow_redirects=False)
    check("marking a task done with an outcome is accepted (303)",
          marked.status_code == 303, str(marked.status_code))
    after_done = client.get(f"/v/{VIN}")
    check("the task row shows DONE after marking it done",
          f'data-task-id="{fault_step_id}" data-state="done"' in after_done.text,
          after_done.text.count('data-state="done"'))
    check("the fault-found finding note is shown on the page",
          finding in after_done.text)
    notes_after = mes_bridge.notes(VIN)
    check("the fault-found finding was also filed as a mechanic note (mes.notes)",
          any(finding in (n.get("text") or "") for n in notes_after.get("notes", [])),
          str(notes_after.get("notes")))

    # undo: un-ticking (no "done" field at all, matching real checkbox semantics)
    # clears the outcome/note and leaves the step not-done again.
    undone = client.post(f"/v/{VIN}/bench/done",
                         data={"step_id": fault_step_id, "note": ""},
                         follow_redirects=False)
    check("undoing a marked-done task is accepted (303)",
          undone.status_code == 303, str(undone.status_code))
    check("undo cleared the stored outcome",
          checklist_store.get(VIN).get(fault_step_id, {}).get("outcome") is None,
          str(checklist_store.get(VIN).get(fault_step_id)))

# 4. preconditions show MES status
# Review #6 item 1: the precondition's own label now tracks the same
# mes_state/scanner_label() the "Scanner:" strip shows (was a static "MES
# running" that read backwards -- "BLOCKED: MES running" -- whenever MES
# was in fact not running), so the label text here is "MES " + whatever
# scanner_label() currently says, not a fixed string.
mes_task = next((a for a in bench["next_actions"]
                 if any(p["label"].startswith("MES ") for p in a["preconditions"])), None)
check("at least one task declares a live MES precondition",
      mes_task is not None, str([a["preconditions"] for a in bench["next_actions"]]))
if mes_task:
    mes_precond = next(p for p in mes_task["preconditions"] if p["label"].startswith("MES "))
    check("the precondition's label matches the Scanner strip's own wording",
          mes_precond["label"] == f"MES {bench_bridge.scanner_label(bench['live_status']).lower()}",
          str(mes_precond))
    check("the MES precondition label is shown on the page", mes_precond["label"] in page.text)

# 5. every task row carries data-task-id; READY rows have labelled one-tap buttons
#    (LAYOUT CHANGE: the checkbox + "Mark done" label are replaced by OK / Fault found / Skip)
for a in bench["next_actions"]:
    check(f"task row {a['step_id']} carries data-task-id",
          f'data-task-id="{a["step_id"]}"' in page.text)
    if a["state"] == "READY" and not a["done"]:
        check(f"task row {a['step_id']}'s OK button is labelled with its task title",
              f'aria-label="OK: {_escape(a["text"])}"' in page.text)

# 5b. one-tap save: a plain POST records the outcome, redirects with ?saved=, the page shows
#     "Saved ... Undo", and Undo (a POST without "done") puts the step back.
if _ready_undone:
    _one = _ready_undone[0]["step_id"]
    _r = client.post(f"/v/{VIN}/bench/done", data={"step_id": _one, "done": "1", "outcome": "ok"},
                     follow_redirects=False)
    check("one-tap OK is a plain POST that redirects with ?saved=",
          _r.status_code == 303 and f"saved={_one}" in _r.headers.get("location", ""),
          _r.headers.get("location", ""))
    _after = client.get(_r.headers.get("location", f"/v/{VIN}"))
    check("the Saved banner names the step and offers Undo",
          'id="bench-saved"' in _after.text and "Saved: Step " in _after.text and ">Undo</button>" in _after.text)
    _fresh = bench_bridge.build_bench(VIN)
    check("after a one-tap save the lead step moves on",
          _fresh["next_step"] is None or _fresh["next_step"]["step_id"] != _one, str(_fresh["next_step"] and _fresh["next_step"]["step_id"]))
    client.post(f"/v/{VIN}/bench/done", data={"step_id": _one}, follow_redirects=False)
    check("Undo restores the step to not-done", not checklist_store.get(VIN).get(_one, {}).get("done"))
    _ff = client.post(f"/v/{VIN}/bench/done", data={"step_id": _one, "done": "1", "outcome": "fault_found",
                                                    "label": "one-tap label check"}, follow_redirects=False)
    check("one-tap Fault found files a mechanic note naming the step",
          any("one-tap label check" in (n.get("text") or "") for n in mes_bridge.notes(VIN).get("notes", [])))
    client.post(f"/v/{VIN}/bench/done", data={"step_id": _one}, follow_redirects=False)

# 6. title contains "UNVERIFIED"
title_match = re.search(r"<title>(.*?)</title>", page.text, re.DOTALL)
check("the page has a <title> tag", title_match is not None)
if title_match:
    check("the <title> contains UNVERIFIED", "UNVERIFIED" in title_match.group(1),
          title_match.group(1))


# --- 5. 400px CDP screenshot: first card's top < 800px, no overflow -------

print("=== 400px screenshot (cleanup via _edge_cleanup.kill_edge_profile) ===")
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_edge() -> str:
    for candidate in EDGE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return ""


def free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class CDP:
    def __init__(self, ws_url: str) -> None:
        from websockets.sync.client import connect
        self.ws = connect(ws_url, max_size=None, open_timeout=20)
        self._ids = itertools.count(1)

    def send(self, method: str, params: dict | None = None, timeout: float = 20):
        msg_id = next(self._ids)
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv(timeout=max(0.1, deadline - time.time()))
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} failed: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(f"CDP {method} timed out waiting for response")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for_devtools(port: int, timeout: float = 20) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
                json.loads(r.read().decode("utf-8"))
                return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.2)
    raise RuntimeError(f"headless Edge devtools endpoint never came up: {last_err}")


def open_target(port: int, url: str) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_for_port(port: int, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                s.connect(("127.0.0.1", port))
                return True
        except OSError:
            time.sleep(0.2)
    return False


def wait_for_navigation(cdp: "CDP", url: str, timeout: float = 15.0) -> bool:
    """Poll until the tab has actually navigated to ``url`` (not still
    ``about:blank``) and ``document.readyState`` is "complete". A fixed
    short sleep after ``/json/new?<url>`` is NOT enough in this environment
    -- a cold headless-Edge tab observably takes several seconds (not the
    ~1.5s this check used to assume) before ``location.href`` moves off
    ``about:blank``, independent of how fast the server itself answers
    (confirmed separately: the server's own response lands in well under a
    second). Polling, not a longer fixed guess, is what actually restores
    the strict downstream geometry checks reliably."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        val = cdp.send("Runtime.evaluate", {
            "expression": ("JSON.stringify({href: location.href, "
                           "ready: document.readyState})"),
            "returnByValue": True,
        })
        try:
            state = json.loads(val.get("result", {}).get("value") or "{}")
        except ValueError:
            state = {}
        if state.get("href", "about:blank") != "about:blank" and state.get("ready") == "complete":
            return True
        time.sleep(0.3)
    return False


edge = find_edge()
server_dir = tempfile.mkdtemp(prefix="cuore-check-bench-server-")
port = free_port()
env = dict(os.environ)
env["CUORE_STATE_DIR"] = server_dir

_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
import uvicorn

app = create_app()
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
"""

if not edge:
    check("headless Edge is available for the screenshot check", False, str(EDGE_CANDIDATES))
else:
    server_proc = subprocess.Popen(
        [sys.executable, "-c", _SERVER_SNIPPET],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        up = wait_for_port(port)
        check("uvicorn came up on the free port", up, f"port {port}")
        if up:
            # Warm the bench's own caches (mes_bridge.workup + dossier_bridge's
            # memoised core) in this freshly spawned, cold process BEFORE
            # Edge ever navigates -- building the Stelvio's 17-log workup and
            # resolving parts/tools for 3 next actions easily outruns the
            # 1.7s this check waits before reading document.readyState below,
            # which otherwise reads the pre-navigation about:blank document
            # (readyState "complete" trivially, body empty) rather than the
            # real page. check_screens.py hits the same thing and warms the
            # same way (its own seed POST, then a sleep) before measuring.
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/v/{VIN}", timeout=25)
            except Exception as exc:  # noqa: BLE001
                check("warming the bench page on the screenshot server", False, str(exc))
            time.sleep(0.5)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-bench-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,800",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    navigated = wait_for_navigation(cdp, url)
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 800, "deviceScaleFactor": 1, "mobile": True,
                    })
                    time.sleep(0.5)

                    nav = cdp.send("Runtime.evaluate", {
                        "expression": "document.readyState", "returnByValue": True})
                    check("bench page loaded in the headless browser",
                          navigated and nav.get("result", {}).get("value") in ("complete", "interactive"),
                          str(nav))

                    overflow = cdp.send("Runtime.evaluate", {
                        "expression": (
                            "JSON.stringify({sw: document.documentElement.scrollWidth, "
                            "cw: document.documentElement.clientWidth})"),
                        "returnByValue": True,
                    })
                    dims = json.loads(overflow.get("result", {}).get("value", "{}"))
                    sw, cw = dims.get("sw", 0), dims.get("cw", 0)
                    check("no page-level horizontal overflow at 400px",
                         sw <= cw + 1, f"scrollWidth={sw} clientWidth={cw}")

                    rect = cdp.send("Runtime.evaluate", {
                        "expression": (
                            "(() => { const el = document.querySelector('.bench-card'); "
                            "if (!el) return JSON.stringify(null); "
                            "const r = el.getBoundingClientRect(); "
                            "return JSON.stringify({top: r.top, left: r.left, right: r.right}); "
                            "})()"),
                        "returnByValue": True,
                    })
                    card_rect = json.loads(rect.get("result", {}).get("value", "null"))
                    check("the first next-action card is present on the page",
                          card_rect is not None, str(card_rect))
                    if card_rect is not None:
                        # Strict stopwatch check (matches check_stopwatch.py): the
                        # Bench's shared {% include "_vbar.html" %} hero now renders
                        # a COMPACT hero for tab == "bench" (image band capped at
                        # 18vh, no tagline, no key-figures row -- see _vbar.html and
                        # cuore.css's "Bench compact hero" section) specifically so
                        # the resume card and first next-action card land back
                        # on-screen at 400x800 with no scrolling. The full,
                        # taller hero (image/tagline/key-figures) is report-only.
                        check("the first next-action card's top is within the "
                             "first 800px viewport (no scrolling at 400x800)",
                             card_rect["top"] < 800, str(card_rect))
                        check("the first next-action card does not overflow horizontally",
                             card_rect["right"] <= 400 + 1, str(card_rect))

                    resume_rect = cdp.send("Runtime.evaluate", {
                        "expression": (
                            "(() => { const el = document.querySelector('.bench-resume'); "
                            "if (!el) return JSON.stringify(null); "
                            "const r = el.getBoundingClientRect(); "
                            "return JSON.stringify({top: r.top}); })()"),
                        "returnByValue": True,
                    })
                    resume_box = json.loads(resume_rect.get("result", {}).get("value", "null"))
                    check("the resume card is present on the page", resume_box is not None,
                         str(resume_box))
                    if resume_box is not None:
                        # The actual P1 fix (BENCH_UX_SPEC A1): the resume card
                        # itself -- not the task list -- is what should be reached
                        # with minimal scrolling, right under the hero + tab strip.
                        check("the resume card sits right under the hero/tab strip, "
                             "not buried under the task list",
                             resume_box["top"] < 1500, str(resume_box))  # 1300 -> 1500: Go-to chips now wrap (Chrome review) instead of scrolling sideways

                    shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                    data_b64 = shot.get("data", "")
                    check("a 400px screenshot of the bench was captured",
                         bool(data_b64), f"{len(data_b64)} bytes of base64")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge measured the bench page over CDP", False,
                     f"{type(exc).__name__}: {exc}")
            finally:
                edge_proc.terminate()
                try:
                    edge_proc.wait(timeout=5)
                except Exception:
                    edge_proc.kill()
                from _edge_cleanup import kill_edge_profile
                kill_edge_profile(profile_dir)
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()


# --- report ------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
