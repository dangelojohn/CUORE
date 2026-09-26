"""Checks for the customizable live-data dashboard (``/v/{vin}/gauges``).

Three parts, same posture as the other ``check_*_page.py`` scripts:
``CUORE_STATE_DIR`` is pointed at a throwaway directory BEFORE cuore is
imported, so no real dealer/live/layout state is touched.

1. The page and its HUD variant respond 200 and carry the script tags the
   client-side app needs -- against the real FastAPI app, via TestClient.
   ``cuore/web/live_dashboard_routes.py`` is not yet wired into
   ``cuore/app.py`` (see that module's docstring), so this script includes
   its router itself if ``create_app()`` did not already pick it up --
   whichever lands first, the checks below are exercised against the same
   route either way.
2. ``dashboard_test.html`` -- dashboard.js's own self-test page -- run
   headless in Edge, with its ``<pre id="result">`` parsed as
   ``{"passed": N, "failed": [...]}``.
3. A real server (uvicorn, background process, free port, temp state dir) is
   screenshotted in demo mode at two viewport sizes so layout problems are
   visible, not just "the HTML parsed".

Both (2) and (3) drive Edge over the Chrome DevTools Protocol (remote
debugging websocket), the same approach ``check_live_widgets.py`` uses --
on this machine ``--dump-dom``'s stdout never reaches the launching process
(Edge detaches into a background target) and ``--screenshot`` fails when
combined with ``--disable-gpu`` ("Multiple targets are not supported in
headless mode"). CDP sidesteps both.

Run:
    .venv/Scripts/python.exe cuore/tests/check_live_dashboard_page.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-gauges-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import live_dashboard_routes  # noqa: E402

from websockets.sync.client import connect  # noqa: E402

VIN = "ZASFAKPN5J7B88115"           # the Stelvio
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
STATIC_LIVE = ROOT / "cuore" / "web" / "static" / "live"
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


def _app_with_router():
    app = create_app()
    already = any(getattr(r, "path", "").startswith("/v/{vin}/gauges") for r in app.routes)
    if not already:
        app.include_router(live_dashboard_routes.router)
    return app


# ===========================================================================
# 1. the page, over TestClient
# ===========================================================================

print("=== page ===")
client = TestClient(_app_with_router())

page = client.get(f"/v/{VIN}/gauges")
check("gauges page responds 200", page.status_code == 200, str(page.status_code))
for needle in ('src="/static/live/widgets.js"', 'src="/static/live/dashboard.js"',
              'id="dd-app"', 'id="dd-grid"', 'CuoreDashboard.init()'):
    check(f"gauges page contains {needle!r}", needle in page.text)
check("gauges page links widgets.css and dashboard.css",
      "live/widgets.css" in page.text and "live/dashboard.css" in page.text)
check("no template error leaked onto the page",
      "Jinja2" not in page.text and "Traceback" not in page.text)
check("vbar links to the gauges tab", f"/v/{VIN}/gauges" in page.text)

hud = client.get(f"/v/{VIN}/gauges/hud")
check("hud page responds 200", hud.status_code == 200, str(hud.status_code))
for needle in ('src="/static/live/widgets.js"', 'src="/static/live/dashboard.js"',
              'initHud(', 'dd-hud-grid'):
    check(f"hud page contains {needle!r}", needle in hud.text)
check("hud page has no top nav (full-screen, no chrome)",
      'class="top"' not in hud.text and "CU<span>O</span>RE" not in hud.text)


# ===========================================================================
# CDP plumbing (same approach as check_live_widgets.py)
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
    # Recent Chromium/Edge builds require PUT (not GET) on /json/new.
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def read_result_pre(cdp: "CDP", timeout: float = 15) -> dict | None:
    """Poll ``#result`` until the test page's self-test has written its
    ``{"passed": ..., "failed": [...]}`` JSON into it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = cdp.send("Runtime.evaluate", {
            "expression": "document.getElementById('result') ? document.getElementById('result').textContent : null",
            "returnByValue": True,
        })
        text = out.get("result", {}).get("value")
        if text and text.strip() and text.strip() != "running...":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        time.sleep(0.25)
    return None


# ===========================================================================
# 2. dashboard.js self-test, headless Edge over CDP
# ===========================================================================

print("=== dashboard.js self-test (headless Edge, CDP) ===")
test_html = STATIC_LIVE / "dashboard_test.html"
edge = find_edge()

if not test_html.exists():
    check("dashboard_test.html exists", False, str(test_html))
elif not edge:
    check("headless Edge is available", False, str(EDGE_CANDIDATES))
else:
    devtools_port = free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-dashboard-"))
    edge_proc = subprocess.Popen(
        [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
         f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=1400,1000",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_devtools(devtools_port)
        target = open_target(devtools_port, test_html.resolve().as_uri())
        cdp = CDP(target["webSocketDebuggerUrl"])
        try:
            cdp.send("Page.enable")
            cdp.send("Runtime.enable")
            result = read_result_pre(cdp)
            if result is None:
                check("dashboard_test.html produced a result", False,
                      "no #result content within timeout")
            else:
                passed = result.get("passed", 0)
                failed = result.get("failed", [])
                print(f"  dashboard.js self-test: {passed} passed, {len(failed)} failed")
                check("dashboard.js self-test: no failed checks", not failed,
                      f"{len(failed)} failed: {failed}")
        finally:
            cdp.close()
    except Exception as exc:  # noqa: BLE001
        check("headless Edge ran dashboard_test.html over CDP", False, f"{type(exc).__name__}: {exc}")
    finally:
        edge_proc.terminate()
        try:
            edge_proc.wait(timeout=5)
        except Exception:
            edge_proc.kill()


# ===========================================================================
# 3. screenshots in demo mode, two viewports, headless Edge over CDP
# ===========================================================================

print("=== screenshots ===")


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


server_dir = tempfile.mkdtemp(prefix="cuore-check-gauges-server-")
port = free_port()
env = dict(os.environ)
env["CUORE_STATE_DIR"] = server_dir

#: A one-off runner, not ``cuore.asgi:app`` -- that module builds its app
#: with plain ``create_app()``, which (per this feature's router docstring)
#: does not yet include ``live_dashboard_routes``. Editing ``cuore/asgi.py``
#: is outside this feature's file list, so the include-router-if-missing
#: dance from ``_app_with_router()`` above is repeated here for the live
#: server instead.
_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
from cuore.web import live_dashboard_routes
import uvicorn

app = create_app()
if not any(getattr(r, "path", "").startswith("/v/{{vin}}/gauges") for r in app.routes):
    app.include_router(live_dashboard_routes.router)
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
"""

if not edge:
    check("headless Edge is available for screenshots", False, str(EDGE_CANDIDATES))
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
            time.sleep(0.5)  # first-route import warmup
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-shot-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=1400,1000",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}/gauges?autostart=demo"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    # Cold-cache first request: /v/{vin}/gauges builds the vehicle
                    # bar off cuore's real MES-corpus workup, which is uncached on
                    # a freshly started server and alone takes ~1s; give the app
                    # room to also finish its four bootstrap fetches and a demo tick.
                    time.sleep(5.0)
                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    for w, h, name in ((1400, 1000, "gauges_desktop.png"), (400, 900, "gauges_phone.png")):
                        out_path = SCRATCHPAD / name
                        try:
                            cdp.send("Emulation.setDeviceMetricsOverride", {
                                "width": w, "height": h, "deviceScaleFactor": 1, "mobile": h > w,
                            })
                            time.sleep(0.8)
                            shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                            out_path.write_bytes(base64.b64decode(shot["data"]))
                        except Exception as exc:  # noqa: BLE001
                            check(f"screenshot {name} captured", False, f"{type(exc).__name__}: {exc}")
                            continue
                        check(f"screenshot {name} captured", out_path.exists() and out_path.stat().st_size > 0,
                              str(out_path))
                        if out_path.exists():
                            print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge captured screenshots over CDP", False, f"{type(exc).__name__}: {exc}")
            finally:
                edge_proc.terminate()
                try:
                    edge_proc.wait(timeout=5)
                except Exception:
                    edge_proc.kill()
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
