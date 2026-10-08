"""Checks for the mechanic-UX "stopwatch" asks on the Bench landing page
(``/v/{vin}``, ``cuore/web/bench_routes.py`` + ``bench.html``) and the
tab/chrome reshuffle around it (``_vbar.html``, ``_vtabs.html``,
``_flow_bar.html``).

Same posture as ``cuore/tests/check_screens.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported, and the real MES
corpus on this machine (the Stelvio, VIN below) is the fixture vehicle.

Three checks over a plain ``TestClient`` (no browser needed for any of
these -- they're about markup/links, not rendered geometry):

  1. The Bench's own "next action" text is present in the page's initial
     HTML, not hidden inside a closed ``<details>`` -- i.e. reachable with
     zero taps, nothing to expand first.
  2. A code page is reachable from the Bench in <= 2 link hops: parse the
     ``href="..."`` attributes out of the Bench page itself (hop 1), and
     out of whatever hop-1 pages don't already have one (hop 2).
  3. The Job step bar (``_flow_bar.html``, ``class="flow-bar"``) does not
     render on ``/v/{vin}/codes`` -- it's job-specific chrome now (tab ==
     "job" only, per the mechanic-UX review).

Plus one CDP pass (real server + headless Edge, cleanup via
``_edge_cleanup.kill_edge_profile``, same technique as
``check_jobs_page.py``) at a 400px-wide viewport, measuring -- not
screenshotting, to keep this cheap -- the Bench's next-action element's own
bounding box: its bottom edge must sit within the first 800px of the page,
i.e. visible without scrolling on a 400x800 phone. Falls back to the Job
page's own first suggested-next-step button if the Bench route isn't
reachable for some reason (defensive; the Bench already exists as of this
check being written).

Run:
    .venv/Scripts/python.exe cuore/tests/check_stopwatch.py
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
import urllib.parse
import urllib.request
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-stopwatch-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())

# A job/visit on this VIN so the Bench has real next-actions to show,
# rather than the empty "nothing open" state.
open_resp = client.post(f"/v/{VIN}/job/open",
                        data={"technician": "tester", "complaint": "CEL, smells like gas"},
                        follow_redirects=True)
check("opening a case for the fixture responds 200", open_resp.status_code == 200,
      str(open_resp.status_code))


# --- 1. the Bench's next action is in the initial HTML, zero taps ----------

bench_resp = client.get(f"/v/{VIN}")
check("the Bench page (/v/{vin}) responds 200", bench_resp.status_code == 200,
      str(bench_resp.status_code))
bench_html = bench_resp.text

_next_action_m = re.search(
    r'<details\b[^>]*>(?:(?!</details>).)*?class="bench-next-action"',
    bench_html, re.DOTALL)
check("the Bench's next-action text is present in the initial HTML",
      'class="bench-next-action"' in bench_html, "no .bench-next-action on /v/{vin}")
check("the Bench's next-action text is not hidden inside a closed <details> "
      "(reachable with zero taps)", _next_action_m is None,
      "found .bench-next-action nested inside a <details> block")


# --- 2. a code page is reachable from the Bench in <= 2 link hops ---------

_HREF_RE = re.compile(r'href="([^"]+)"')


def _hrefs(html: str) -> list[str]:
    return [h for h in _HREF_RE.findall(html) if h.startswith("/")]


def _is_code_page(href: str) -> bool:
    return bool(re.match(rf"^/v/{re.escape(VIN)}/codes(\?|$)", href)
                or re.match(rf"^/v/{re.escape(VIN)}/code/", href))


hop1 = _hrefs(bench_html)
hop1_hit = next((h for h in hop1 if _is_code_page(h)), None)

hop2_hit = None
if hop1_hit is None:
    for h in hop1:
        try:
            r = client.get(h)
        except Exception:  # noqa: BLE001 -- a broken link must not crash this check
            continue
        if r.status_code != 200:
            continue
        hit = next((h2 for h2 in _hrefs(r.text) if _is_code_page(h2)), None)
        if hit:
            hop2_hit = (h, hit)
            break

check("a code page is reachable from the Bench in <= 2 link hops",
      hop1_hit is not None or hop2_hit is not None,
      f"hop1 links sampled: {hop1[:15]}")
if hop1_hit:
    print(f"  code page reached in 1 hop: {hop1_hit}")
elif hop2_hit:
    print(f"  code page reached in 2 hops: {hop2_hit[0]} -> {hop2_hit[1]}")


# --- 3. the job-only flow bar does not render on /v/{vin}/codes ------------

codes_resp = client.get(f"/v/{VIN}/codes")
check("the codes page (/v/{vin}/codes) responds 200", codes_resp.status_code == 200,
      str(codes_resp.status_code))
check('the Job step bar (class="flow-bar") is absent on /v/{vin}/codes',
      'class="flow-bar"' not in codes_resp.text)
check("the codes page still carries the compact vehicle strip (.vline)",
      'class="vline"' in codes_resp.text)


# --- CDP pass: next-action bounding box within the first 800px -------------

print("=== CDP: Bench next-action bounding box at 400px ===")
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


edge = find_edge()
server_dir = tempfile.mkdtemp(prefix="cuore-check-stopwatch-server-")
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
    check("headless Edge is available for the bounding-box check", False, str(EDGE_CANDIDATES))
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
            data = urllib.parse.urlencode(
                {"technician": "tester", "complaint": "CEL, smells like gas"}).encode()
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"http://127.0.0.1:{port}/v/{VIN}/job/open",
                                           data=data, method="POST"), timeout=25)
            except Exception as exc:  # noqa: BLE001
                check("seeding a job on the stopwatch-check server", False, str(exc))

            time.sleep(0.5)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-stopwatch-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1400",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)

                # Prefer the Bench (it exists); fall back to the Job page's
                # own suggested-next-step button if the Bench route can't be
                # reached for some reason.
                bench_url = f"http://127.0.0.1:{port}/v/{VIN}"
                target = open_target(devtools_port, bench_url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                selector = ".bench-next-action"
                page_label = "Bench"
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    time.sleep(1.2)
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 1400, "deviceScaleFactor": 1, "mobile": True,
                    })
                    time.sleep(0.5)

                    probe = cdp.send("Runtime.evaluate", {
                        "expression": f"document.querySelector({selector!r}) !== null",
                        "returnByValue": True,
                    })
                    has_el = bool(probe.get("result", {}).get("value"))
                    if not has_el:
                        # Fall back to the Job page.
                        page_label = "Job"
                        selector = ".flow-next"
                        cdp.close()
                        job_url = f"http://127.0.0.1:{port}/v/{VIN}/job"
                        target = open_target(devtools_port, job_url)
                        cdp = CDP(target["webSocketDebuggerUrl"])
                        cdp.send("Page.enable")
                        cdp.send("Runtime.enable")
                        time.sleep(1.2)
                        cdp.send("Emulation.setDeviceMetricsOverride", {
                            "width": 400, "height": 1400, "deviceScaleFactor": 1, "mobile": True,
                        })
                        time.sleep(0.5)

                    rect = cdp.send("Runtime.evaluate", {
                        "expression": (
                            f"(function(){{var e=document.querySelector({selector!r});"
                            "if(!e)return null;var r=e.getBoundingClientRect();"
                            "return JSON.stringify({top:r.top,bottom:r.bottom,height:r.height,"
                            "scrollY:window.scrollY});})()"),
                        "returnByValue": True,
                    })
                    raw = rect.get("result", {}).get("value")
                    check(f"the {page_label} page's next-action element was found for the "
                          "bounding-box check", raw is not None, str(rect))
                    if raw:
                        dims = json.loads(raw)
                        check("no scroll happened before measuring (viewport starts at top)",
                              dims.get("scrollY", 0) == 0, str(dims))
                        check(f"the {page_label} next-action element's bottom edge is within "
                              "the first 800px of the viewport (visible with no scrolling)",
                              dims.get("bottom", 99999) <= 800, str(dims))
                        check(f"the {page_label} next-action element is actually on-screen "
                              "(top >= 0)", dims.get("top", -1) >= 0, str(dims))
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge measured the next-action bounding box over CDP", False,
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
