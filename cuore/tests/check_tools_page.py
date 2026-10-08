"""Smoke checks for the mechanic-facing Tools page (/tools).

Trimmed to 5 focused checks per the task's scope cut: routes/redirects,
header/footer wiring, and one 400px screenshot pass over CDP (phone-first
layout, 44px Run buttons, a disabled tool shows its reason). Companion
suites (check_api.py, check_dossier_page.py) are run as a single pass/fail.

Run:
    .venv/Scripts/python.exe cuore/tests/check_tools_page.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-tools-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import tools_routes  # noqa: E402

from websockets.sync.client import connect  # noqa: E402

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


def _app():
    app = create_app()
    if not any(getattr(r, "path", "") == "/tools" for r in app.routes):
        app.include_router(tools_routes.router)
    return app


client = TestClient(_app())

# --- 1. /tools renders, with groups and the search box ---------------------

page = client.get("/tools")
check("1. /tools responds 200 with groups and a search box",
      page.status_code == 200 and 'id="t-search"' in page.text
      and 'class="t-groups"' in page.text,
      str(page.status_code))

# --- 2. /api and /api/ redirect to /tools; /api/docs still works ----------

r1 = client.get("/api", follow_redirects=False)
r2 = client.get("/api/", follow_redirects=False)
docs = client.get("/api/docs")
check("2. /api and /api/ redirect to /tools, /api/docs still 200",
      r1.headers.get("location") == "/tools" and r2.headers.get("location") == "/tools"
      and docs.status_code == 200,
      f"{r1.status_code}->{r1.headers.get('location')} "
      f"{r2.status_code}->{r2.headers.get('location')} docs={docs.status_code}")

# --- 3. header/footer wiring -----------------------------------------------

home = client.get("/")
check("3. header shows 'Tools' (not the old 'API' label); footer has Developer API",
      'href="/tools">Tools<' in home.text and '>API<' not in home.text
      and 'href="/api/docs"' in home.text and "Developer API" in home.text)

print(f"checks so far: {checks - len(failures)}/{checks} passed")


# --- 4/5. one screenshot pass at 400px: overflow, button size, disabled ----

def find_edge() -> str:
    for c in EDGE_CANDIDATES:
        if Path(c).exists():
            return c
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
        raise TimeoutError(f"CDP {method} timed out")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for_devtools(port: int, timeout: float = 20) -> None:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
                json.loads(r.read().decode("utf-8"))
                return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.2)
    raise RuntimeError(f"headless Edge devtools never came up: {last_err}")


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
server_dir = tempfile.mkdtemp(prefix="cuore-check-tools-server-")
port = free_port()
env = dict(os.environ)
env["CUORE_STATE_DIR"] = server_dir

_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
from cuore.web import tools_routes
import uvicorn

app = create_app()
if not any(getattr(r, "path", "") == "/tools" for r in app.routes):
    app.include_router(tools_routes.router)
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
"""

if not edge:
    check("4/5. headless Edge available for the 400px screenshot pass", False, str(EDGE_CANDIDATES))
else:
    server_proc = subprocess.Popen(
        [sys.executable, "-c", _SERVER_SNIPPET], cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        up = wait_for_port(port)
        check("4. server came up for the screenshot pass", up, f"port {port}")
        if up:
            time.sleep(0.5)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-tools-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1200",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                target = open_target(devtools_port, "about:blank")
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    cdp.send("Emulation.setDeviceMetricsOverride",
                             {"width": 400, "height": 1200, "deviceScaleFactor": 1, "mobile": True})
                    cdp.send("Page.navigate", {"url": f"http://127.0.0.1:{port}/tools"})
                    time.sleep(1.8)  # tools.js render pass
                    metrics = cdp.send("Runtime.evaluate", {
                        "expression": (
                            "JSON.stringify({"
                            "sw: document.documentElement.scrollWidth,"
                            "cw: document.documentElement.clientWidth,"
                            "runH: (document.querySelector('.t-run')||{}).offsetHeight || 0,"
                            "disabledReason: (document.querySelector('.t-disabled-reason')||{}).textContent || ''"
                            "})"),
                        "returnByValue": True,
                    })
                    dims = json.loads(metrics.get("result", {}).get("value", "{}"))
                    check("5. 400px: no horizontal overflow, Run button >=44px, a disabled tool shows its reason",
                         dims.get("sw", 999) <= dims.get("cw", 0) + 1
                         and dims.get("runH", 0) >= 44
                         and bool(dims.get("disabledReason", "").strip()),
                         str(dims))
                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    shot_path = SCRATCHPAD / "tools_400.png"
                    shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                    shot_path.write_bytes(base64.b64decode(shot["data"]))
                    print(f"  screenshot: {shot_path}")
                finally:
                    cdp.close()
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


# --- companion suites, run as one pass/fail --------------------------------

comp_ok = True
comp_tail = ""
for script in ("check_api.py", "check_dossier_page.py"):
    proc = subprocess.run([sys.executable, str(Path(__file__).parent / script)],
                          cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        comp_ok = False
        comp_tail += f"\n{script}: {(proc.stdout + proc.stderr)[-800:]}"
check("companion suites (check_api.py, check_dossier_page.py) still pass", comp_ok, comp_tail)


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
