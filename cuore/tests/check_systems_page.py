"""Checks for the system-dependency view (``/v/{vin}/systems``), the
``_system_badge.html`` chips on ``code.html``, and the timeline's
``?lanes=systems`` grouping mode.

Same posture as ``cuore/tests/check_timeline_page.py`` (CDP screenshot
plumbing copied from there almost verbatim): ``CUORE_STATE_DIR`` is pointed
at a throwaway directory before cuore is imported, and
``cuore/web/systems_routes.py``/``cuore/web/timeline_routes.py`` are not
necessarily wired into ``cuore/app.py`` yet, so this includes them itself
if ``create_app()`` did not already pick them up.

``cuore/services/systems_bridge.py`` is being built in parallel by another
agent and may not exist yet -- every route this touches falls back to its
own fixture in that case, so every check below runs either way.

Run:
    .venv/Scripts/python.exe cuore/tests/check_systems_page.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-systems-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import systems_routes, timeline_routes  # noqa: E402

from websockets.sync.client import connect  # noqa: E402

VIN = "ZASFAKPN5J7B88115"           # the Stelvio -- real corpus
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


def _app_with_routers():
    app = create_app()
    if not any(getattr(r, "path", "").startswith("/v/{vin}/systems") for r in app.routes):
        app.include_router(systems_routes.router)
    if not any(getattr(r, "path", "").startswith("/v/{vin}/timeline") for r in app.routes):
        app.include_router(timeline_routes.router)
    return app


# ===========================================================================
# TestClient checks
# ===========================================================================

print("=== systems page (TestClient) ===")
client = TestClient(_app_with_routers())

page = client.get(f"/v/{VIN}/systems")
check("systems page responds 200", page.status_code == 200, str(page.status_code))
check("no template error leaked onto the page",
      "Jinja2" not in page.text and "Traceback" not in page.text)
check("dependency graph svg present", "<svg" in page.text and "System dependency graph" in page.text)
check("legend present (status + edge-confidence keys)",
      "cleared, unverified" in page.text and "single source" in page.text)
check("dashed/dotted edge strokes are emitted (stroke-dasharray)",
      "stroke-dasharray" in page.text)
check("per-system card anchors present (id=\"sys-...\")", 'id="sys-evap"' in page.text)
check("vbar carries a Systems tab", ">Systems<" in page.text)

print("=== code page system badge ===")
code_resp = client.get(f"/v/{VIN}/code/P0455")
check("code page responds 200", code_resp.status_code == 200, str(code_resp.status_code))
check("EVAP system badge present on P0455", "sysb-row" in code_resp.text and "EVAP" in code_resp.text
      and "(primary)" in code_resp.text)
check("badge links to the systems page", f'/v/{VIN}/systems#sys-evap' in code_resp.text)

print("=== timeline ?lanes=systems ===")
tl_resp = client.get(f"/v/{VIN}/timeline?lanes=systems")
check("timeline lanes=systems responds 200", tl_resp.status_code == 200, str(tl_resp.status_code))
check("group toggle present", ">System<" in tl_resp.text and ">Family<" in tl_resp.text)
tl_family = client.get(f"/v/{VIN}/timeline")
check("timeline default (family) still responds 200", tl_family.status_code == 200)


# ===========================================================================
# CDP plumbing (copied from check_timeline_page.py)
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


# ===========================================================================
# one 400px screenshot + the horizontal-overflow check
# ===========================================================================

print("=== screenshot + overflow at 400px ===")
edge = find_edge()
server_dir = tempfile.mkdtemp(prefix="cuore-check-systems-server-")
port = free_port()
env = dict(os.environ)
env["CUORE_STATE_DIR"] = server_dir

_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
from cuore.web import systems_routes, timeline_routes
import uvicorn

app = create_app()
if not any(getattr(r, "path", "").startswith("/v/{{vin}}/systems") for r in app.routes):
    app.include_router(systems_routes.router)
if not any(getattr(r, "path", "").startswith("/v/{{vin}}/timeline") for r in app.routes):
    app.include_router(timeline_routes.router)
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
"""

if not edge:
    check("headless Edge is available for the screenshot", False, str(EDGE_CANDIDATES))
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
            time.sleep(0.5)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-systems-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1400",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}/systems"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    time.sleep(2.0)  # cold-cache first request: real MES-corpus workup
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 1400, "deviceScaleFactor": 1, "mobile": True,
                    })
                    time.sleep(0.6)
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

                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    out_path = SCRATCHPAD / "systems_phone.png"
                    shot = cdp.send("Page.captureScreenshot",
                                   {"format": "png", "captureBeyondViewport": False})
                    out_path.write_bytes(base64.b64decode(shot["data"]))
                    check("screenshot captured", out_path.exists() and out_path.stat().st_size > 0,
                         str(out_path))
                    if out_path.exists():
                        print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge captured the screenshot over CDP", False, f"{type(exc).__name__}: {exc}")
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
