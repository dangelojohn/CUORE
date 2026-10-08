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
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-bench-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import checklists as checklist_store  # noqa: E402
from cuore.services import bench_bridge, mes_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

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
check("at most 3 next actions", len(bench["next_actions"]) <= 3,
      str(len(bench["next_actions"])))
check("at most 6 shortcuts", len(bench["shortcuts"]) <= 6, str(len(bench["shortcuts"])))


# --- 1. the real route: GET /v/{vin} is the bench, GET /v/{vin}/dossier is
#    still the full dossier -----------------------------------------------

page = client.get(f"/v/{VIN}")
check("bench page responds 200", page.status_code == 200, str(page.status_code))
check("bench status line names the Stelvio", "Stelvio" in page.text)
check("bench status line never shows the unnamed placeholder",
      "(unnamed vehicle)" not in page.text)
check("bench status line carries the VIN tail",
      VIN[-6:] in page.text, VIN[-6:])

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
check("every rendered next-action card posts to the bench's own outcome-capturing "
      "route (2 forms per card: the checkbox, and the outcome Save button)",
      page.text.count(f'action="/v/{VIN}/bench/done"') == 2 * len(bench["next_actions"]),
      str(page.text.count(f'action="/v/{VIN}/bench/done"')))

for a in bench["next_actions"]:
    check(f"step {a['step_id']} text is on the page", a["text"] in page.text)
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
check("the resume card shows 'last scan'", "last scan" in page.text)
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
mes_task = next((a for a in bench["next_actions"]
                 if any(p["label"] == "MES running" for p in a["preconditions"])), None)
check("at least one task declares a live MES precondition",
      mes_task is not None, str([a["preconditions"] for a in bench["next_actions"]]))
if mes_task:
    check("the MES running precondition is shown on the page", "MES running" in page.text)

# 5. every task row has a labelled checkbox and data-task-id
for a in bench["next_actions"]:
    check(f"task row {a['step_id']} carries data-task-id",
          f'data-task-id="{a["step_id"]}"' in page.text)
    check(f"task row {a['step_id']} has a real checkbox input",
          f'id="chk-{a["step_id"]}"' in page.text)
    check(f"task row {a['step_id']}'s checkbox is labelled with its task title",
          f'Mark done: {a["text"]}' in page.text)

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
                             resume_box["top"] < 1300, str(resume_box))

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
