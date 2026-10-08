"""Checks for the passenger-seat liveboard (``/v/{vin}/liveboard``).

Same posture as the other ``check_*_page.py`` scripts: ``CUORE_STATE_DIR``
is pointed at a throwaway directory BEFORE cuore is imported, so no real
dealer/live/job state is touched.

Two parts:

1. Backend contract sanity over ``TestClient`` -- no browser, just the real
   ``/v/{vin}/liveboard`` page and the three routes the page's own
   ``liveboard.js`` calls (``/api/liveboard/{vin}``, ``POST
   /api/liveboard/evaluate``, ``POST /api/live/snapshots``, ``POST
   /api/liveboard/{vin}/snapshot-to-job``), including opening a job first
   so the snapshot-to-job pass has something to attach evidence to.
2. One headless-Edge session over the Chrome DevTools Protocol (the same
   approach ``check_live_dashboard_page.py``/``check_live_widgets.py``
   use), opened ONCE at a 400px viewport and reused for every DOM-driving
   check plus the one screenshot this script takes -- deliberately not two
   viewports or two browser launches, to keep this script's memory
   footprint small. Demo mode renders the board, a coolant sample is
   injected straight through ``window.CuoreLiveboard.app.injectSample``
   (no real adapter needed) to drive the excessive/Problems-strip path,
   then the real Snapshot button is clicked so the full save -> evaluate
   -> snapshot-to-job chain runs for real against the running server.

Run:
    .venv/Scripts/python.exe cuore/tests/check_liveboard_page.py
"""

from __future__ import annotations

import base64
import itertools
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-liveboard-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

from websockets.sync.client import connect  # noqa: E402

VIN = "ZASFAKPN5J7B88115"           # the Stelvio
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
SCRATCHPAD = Path(r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User"
                  r"\7cb02eb5-e299-4baf-b34b-9eb82aebbf17\scratchpad")

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


# ===========================================================================
# 1. page + backend contract, over TestClient
# ===========================================================================

print("=== page + API contract (TestClient) ===")
client = TestClient(create_app())

page = client.get(f"/v/{VIN}/liveboard")
check("liveboard page responds 200", page.status_code == 200, str(page.status_code))
for needle in ('id="lb-notice"', 'id="lb-start"', 'id="lb-snapshot"', 'id="lb-demo"',
              'id="lb-stop"', 'id="lb-problems"', 'id="lb-groups"', '>Start<', '>Snapshot<',
              'src="/static/liveboard.js', 'liveboard.css'):
    check(f"liveboard page contains {needle!r}", needle in page.text)
check("no template error leaked onto the page",
      "Jinja2" not in page.text and "Traceback" not in page.text)
check("no hero on the liveboard page", 'class="vhero"' not in page.text)

board = client.get(f"/api/liveboard/{VIN}")
check("GET /api/liveboard/{vin} responds 200", board.status_code == 200, str(board.status_code))
board_data = board.json() if board.status_code == 200 else {}
groups = board_data.get("groups") or []
check("liveboard contract has at least 1 group with channels", len(groups) >= 1, str(len(groups)))
all_ids = board_data.get("all_channel_ids") or []
check("liveboard contract carries all_channel_ids", "engine_coolant_temp" in all_ids, str(len(all_ids)))

ev = client.post("/api/liveboard/evaluate", json={"values": {"engine_coolant_temp": 140.0}})
check("POST /api/liveboard/evaluate responds 200", ev.status_code == 200, str(ev.status_code))
recs = (ev.json() or {}).get("recommendations") or [] if ev.status_code == 200 else []
check("evaluate grades a hot coolant sample as excessive",
      bool(recs) and recs[0].get("level") == "excessive", json.dumps(recs))

snap_values = {"engine_coolant_temp": {"value": 140.0, "unit": "C"}}
saved = client.post("/api/live/snapshots", json={
    "layout": "liveboard", "page": "liveboard", "source": "demo",
    "values": snap_values, "note": "check_liveboard_page.py",
})
check("POST /api/live/snapshots responds 200", saved.status_code == 200, str(saved.status_code))
snap_id = (saved.json() or {}).get("id") if saved.status_code == 200 else None
check("snapshot carries an id", bool(snap_id), str(saved.text))

# snapshot-to-job needs an open job to attach evidence to -- open one
# directly in this process's state dir (same CUORE_STATE_DIR the app just
# used) before calling the route.
from mes import jobs as jobs_mod  # noqa: E402  -- after bootstrap via cuore.app import

job = jobs_mod.open(VIN, complaint="check_liveboard_page.py: hot coolant sample")
job_resp = client.post(f"/api/liveboard/{VIN}/snapshot-to-job",
                       json={"snapshot_id": snap_id, "values": {"engine_coolant_temp": 140.0}})
check("POST /api/liveboard/{vin}/snapshot-to-job responds 200", job_resp.status_code == 200,
      str(job_resp.status_code))
job_data = job_resp.json() if job_resp.status_code == 200 else {}
check("snapshot-to-job attaches at least one evidence item",
      bool(job_data.get("attached")), json.dumps(job_data))


# ===========================================================================
# CDP plumbing (same approach as check_live_dashboard_page.py)
# ===========================================================================

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
    """Minimal Chrome DevTools Protocol client over one target's websocket."""

    def __init__(self, ws_url: str) -> None:
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

    def eval_json(self, expr: str, timeout: float = 20):
        out = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True}, timeout=timeout)
        val = out.get("result", {}).get("value")
        return val

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


def poll_until(cdp: "CDP", expr: str, predicate, timeout: float = 15.0, interval: float = 0.3):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = cdp.eval_json(expr)
        if predicate(last):
            return last
        time.sleep(interval)
    return last


# ===========================================================================
# 2. one headless-Edge/CDP session: demo render, coolant injection,
#    real Snapshot click, screenshot -- all in the same target.
# ===========================================================================

print("=== demo render + coolant injection + snapshot + screenshot (headless Edge, CDP) ===")

edge = find_edge()
if not edge:
    check("headless Edge is available", False, str(EDGE_CANDIDATES))
else:
    server_dir = tempfile.mkdtemp(prefix="cuore-check-liveboard-server-")
    # A job for the VIN, in the SAME state dir the server subprocess below
    # will use, so the real Snapshot click's snapshot-to-job pass has an
    # open job to attach evidence to.
    os.environ["CUORE_STATE_DIR"] = server_dir
    jobs_mod.open(VIN, complaint="check_liveboard_page.py (CDP pass): hot coolant sample")

    env = dict(os.environ)
    port = free_port()
    _SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
import uvicorn

app = create_app()
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
"""
    server_proc = subprocess.Popen(
        [sys.executable, "-c", _SERVER_SNIPPET],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        up = wait_for_port(port)
        check("uvicorn came up on the free port", up, f"port {port}")
        if up:
            time.sleep(0.5)  # first-route import warmup
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-liveboard-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1200",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}/liveboard?demo=1"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 1200, "deviceScaleFactor": 1, "mobile": True,
                    })
                    # Cold-cache first request (vehicle bar off the real MES
                    # corpus workup) plus the /api/liveboard fetch and the
                    # first demo tick.
                    time.sleep(3.0)

                    # ---- check: demo mode renders >=5 groups with values ----
                    counts = cdp.eval_json(
                        "(function(){"
                        "var groups=document.querySelectorAll('.lb-group').length;"
                        "var withVal=Array.prototype.filter.call("
                        "document.querySelectorAll('.lb-chan-value'),"
                        "function(e){return e.textContent!=='\\u2014';}).length;"
                        "return JSON.stringify({groups:groups, withVal:withVal});"
                        "})()"
                    )
                    counts = json.loads(counts) if counts else {}
                    check("demo mode rendered a page (window.CuoreLiveboard present)",
                          cdp.eval_json("!!window.CuoreLiveboard") is True)
                    check("demo mode renders at least 5 groups",
                          counts.get("groups", 0) >= 5, json.dumps(counts))
                    check("demo mode renders at least 5 channels with a value",
                          counts.get("withVal", 0) >= 5, json.dumps(counts))

                    # ---- check: injected coolant sample -> excessive + Problems strip ----
                    # Stop the demo generator first -- otherwise its own
                    # engine_coolant_temp profile (a plausible warm-up curve
                    # that never reaches the alarm line) overwrites the
                    # injected sample on its next 400ms tick, before the
                    # Snapshot click below gets to see it.
                    cdp.send("Runtime.evaluate", {"expression": "window.CuoreLiveboard.app.stop()"})
                    cdp.send("Runtime.evaluate", {
                        "expression": "window.CuoreLiveboard.app.injectSample("
                                      "'engine_coolant_temp', 140, 'C')",
                    })
                    time.sleep(0.3)
                    coolant = cdp.eval_json(
                        "(function(){"
                        "var row=document.getElementById('lb-chan-engine_coolant_temp');"
                        "var wrap=document.getElementById('lb-problems');"
                        "var rows=document.querySelectorAll('#lb-problems-list .lb-problem-row');"
                        "var text=rows.length?rows[0].textContent:'';"
                        "return JSON.stringify({cls: row?row.className:null,"
                        "problemsHidden: wrap?wrap.hidden:null,"
                        "problemsCount: rows.length, problemsText: text});"
                        "})()"
                    )
                    coolant = json.loads(coolant) if coolant else {}
                    check("injected hot coolant sample shows class level-excessive",
                          "level-excessive" in (coolant.get("cls") or ""), json.dumps(coolant))
                    check("Problems strip is visible with the hot coolant sample",
                          coolant.get("problemsHidden") is False and coolant.get("problemsCount", 0) >= 1,
                          json.dumps(coolant))

                    # ---- check: Snapshot button -- real save+evaluate+job chain ----
                    cdp.send("Runtime.evaluate", {
                        "expression": "document.getElementById('lb-snapshot').click()",
                    })
                    # The id appears as soon as the save+evaluate hops resolve;
                    # the job line is a THIRD, later async hop
                    # (snapshot-to-job) -- wait for both, not just the id,
                    # or this reads the DOM mid-chain and misses the line.
                    snap_result = poll_until(
                        cdp,
                        "(function(){"
                        "var idEl=document.getElementById('lb-snapshot-id');"
                        "var recRows=document.querySelectorAll('#lb-snapshot-result .lb-rec-row');"
                        "var jobEl=document.getElementById('lb-job-line');"
                        "return JSON.stringify({id: idEl?idEl.textContent:'',"
                        "recCount: recRows.length, jobText: jobEl?jobEl.textContent:null});"
                        "})()",
                        lambda raw: bool(raw and json.loads(raw).get("id") and json.loads(raw).get("jobText")),
                        timeout=15.0,
                    )
                    snap_result = json.loads(snap_result) if snap_result else {}
                    check("Snapshot button saved a snapshot (id shown)",
                          bool(snap_result.get("id")), json.dumps(snap_result))
                    check("Snapshot shows the evaluate() recommendations",
                          snap_result.get("recCount", 0) >= 1, json.dumps(snap_result))
                    check('Snapshot renders the "Added to the Job" line',
                          bool(snap_result.get("jobText")) and
                          "Added to the Job" in (snap_result.get("jobText") or ""),
                          json.dumps(snap_result))

                    # ---- check: no horizontal overflow at 400px ----
                    # Dismiss the once-per-session opening splash (_intro.html,
                    # base.html) first -- its ~2.2s fade is still mid-animation
                    # this soon after a cold-start page load, and that's pure
                    # pre-existing base.html chrome, not something this page
                    # renders. Same mechanism the page's own inline script
                    # uses on a second load this session (cuore.css: "shown
                    # once per browser session").
                    cdp.send("Runtime.evaluate", {
                        "expression": "document.documentElement.classList.add('intro-skip')",
                    })
                    overflow = cdp.eval_json(
                        "document.documentElement.scrollWidth <= "
                        "document.documentElement.clientWidth + 1"
                    )
                    check("no horizontal overflow at 400px", overflow is True, str(overflow))

                    # ---- the one screenshot ----
                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    out_path = SCRATCHPAD / "liveboard_phone.png"
                    try:
                        shot = cdp.send("Page.captureScreenshot",
                                       {"format": "png", "captureBeyondViewport": False})
                        out_path.write_bytes(base64.b64decode(shot["data"]))
                    except Exception as exc:  # noqa: BLE001
                        check("screenshot liveboard_phone.png captured", False, f"{type(exc).__name__}: {exc}")
                    else:
                        check("screenshot liveboard_phone.png captured",
                              out_path.exists() and out_path.stat().st_size > 0, str(out_path))
                        print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge ran the liveboard checks over CDP", False, f"{type(exc).__name__}: {exc}")
            finally:
                edge_proc.terminate()
                try:
                    edge_proc.wait(timeout=5)
                except Exception:
                    edge_proc.kill()
                from _edge_cleanup import kill_edge_profile
                kill_edge_profile(profile_dir)  # Edge detaches; terminate() alone leaks it
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait(timeout=10)


# ===========================================================================
# report
# ===========================================================================

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    print(f"{checks - len(failures)}/{checks} checks passed")
    sys.exit(1)
print(f"{checks}/{checks} checks passed")
