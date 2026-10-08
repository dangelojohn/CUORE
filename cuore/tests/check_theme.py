"""Checks for the Emphasis pass (cuore.css's appended "Emphasis pass"
section, on top of the Marque theme below it; _vbar.html's hero band;
job.html's .step-title headings).

Same posture as check_jobs_page.py: a real uvicorn server on a throwaway
CUORE_STATE_DIR, the Stelvio (VIN below, real corpus) as the fixture vehicle,
headless Edge driven over CDP for anything that needs actual layout (font
size, overflow, element presence) rather than just HTML text.

Four checks, matching the owner's brief exactly:
  1. Body computed font-size is >= 17px (job page).
  2. The hero shows the verdict state text (.hero-verdict-state, non-empty)
     on both the job page and the dossier page.
  3. The hero's key-figures row renders at least two figures
     (.hero-figure) for VIN ZASFAKPN5J7B88115.
  4. No page-level horizontal overflow at 400px on the job page.

Also writes two screenshots to the scratchpad for a one-time visual read:
job_1400.png (wide, dark) and job_400.png (narrow) -- capped at two per the
low-memory environment; Edge is always killed via _edge_cleanup after.

Run:
    .venv/Scripts/python.exe cuore/tests/check_theme.py
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
import urllib.parse
import urllib.request
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-theme-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

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
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


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

    def eval_value(self, expr: str):
        out = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return out.get("result", {}).get("value")


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


def navigate(devtools_port: int, url: str, width: int, height: int,
            dark: bool = False) -> CDP:
    target = open_target(devtools_port, "about:blank")
    cdp = CDP(target["webSocketDebuggerUrl"])
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    # Headless Edge's default prefers-color-scheme is light, which would
    # otherwise silently flip the whole body (below the always-dark hero
    # band) to the light palette -- force dark so the dark palette (the
    # one this pass actually changes) is what gets measured/screenshotted.
    if dark:
        cdp.send("Emulation.setEmulatedMedia",
                {"features": [{"name": "prefers-color-scheme", "value": "dark"}]})
    cdp.send("Page.navigate", {"url": url})
    time.sleep(1.2)
    cdp.send("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 768,
    })
    time.sleep(0.5)
    return cdp


edge = find_edge()
if not edge:
    print("headless Edge not found -- cannot run the layout checks")
    sys.exit(1)

server_dir = tempfile.mkdtemp(prefix="cuore-check-theme-server-")
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

server_proc = subprocess.Popen(
    [sys.executable, "-c", _SERVER_SNIPPET],
    cwd=str(ROOT), env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    if not wait_for_port(port):
        print("uvicorn never came up -- aborting")
        sys.exit(1)

    # Seed a job so the job page's flow bar / verdict render for real.
    data = urllib.parse.urlencode(
        {"technician": "tester", "complaint": "CEL, smells like gas"}).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{port}/v/{VIN}/job/open",
                                   data=data, method="POST"), timeout=10)
    except Exception as exc:  # noqa: BLE001
        print(f"warning: seeding the job failed ({exc}); checks continue regardless")

    time.sleep(0.3)
    devtools_port = free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-theme-"))
    edge_proc = subprocess.Popen(
        [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
         f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1400",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_devtools(devtools_port)
        SCRATCHPAD.mkdir(parents=True, exist_ok=True)

        job_url = f"http://127.0.0.1:{port}/v/{VIN}/job"
        dossier_url = f"http://127.0.0.1:{port}/v/{VIN}"

        # --- job page at 1400px: checks 1-3, plus the wide screenshot ----
        cdp = navigate(devtools_port, job_url, 1400, 1800, dark=True)
        try:
            fs = cdp.eval_value("parseFloat(getComputedStyle(document.body).fontSize)")
            check("body computed font-size is >= 17px", fs is not None and fs >= 17, str(fs))

            job_state = cdp.eval_value(
                "(function(){var e=document.querySelector('.hero-verdict-state');"
                "return e?e.textContent.trim():null;})()")

            fig_count = cdp.eval_value(
                "document.querySelectorAll('.hero-figure').length")
            check(f"hero key-figures row renders >= 2 figures for {VIN}",
                  fig_count is not None and fig_count >= 2, str(fig_count))

            shot = cdp.send("Page.captureScreenshot", {"format": "png"})
            wide_path = SCRATCHPAD / "job_1400.png"
            wide_path.write_bytes(base64.b64decode(shot["data"]))
            check("screenshot job_1400.png captured",
                  wide_path.exists() and wide_path.stat().st_size > 0, str(wide_path))
        finally:
            cdp.close()

        # --- dossier page: other half of check 2 -------------------------
        cdp = navigate(devtools_port, dossier_url, 1400, 1800)
        try:
            dossier_state = cdp.eval_value(
                "(function(){var e=document.querySelector('.hero-verdict-state');"
                "return e?e.textContent.trim():null;})()")
        finally:
            cdp.close()

        check("hero shows the verdict state text on the job and dossier pages",
              bool(job_state) and bool(dossier_state),
              f"job={job_state!r} dossier={dossier_state!r}")

        # --- job page at 400px: check 4, plus the narrow screenshot ------
        cdp = navigate(devtools_port, job_url, 400, 1400)
        try:
            dims = json.loads(cdp.eval_value(
                "JSON.stringify({sw: document.documentElement.scrollWidth, "
                "cw: document.documentElement.clientWidth})"))
            sw, cw = dims.get("sw", 0), dims.get("cw", 0)
            check("no horizontal overflow at 400px on the job page",
                  sw <= cw + 1, f"scrollWidth={sw} clientWidth={cw}")

            shot = cdp.send("Page.captureScreenshot", {"format": "png"})
            narrow_path = SCRATCHPAD / "job_400.png"
            narrow_path.write_bytes(base64.b64decode(shot["data"]))
            check("screenshot job_400.png captured",
                  narrow_path.exists() and narrow_path.stat().st_size > 0, str(narrow_path))
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
