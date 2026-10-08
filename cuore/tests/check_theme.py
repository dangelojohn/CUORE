"""Checks for the Marque theme (cuore.css's appended "Marque theme" section,
base.html's data-marque attribute, _vbar.html's hero band, job.html's
.step-title headings).

Same posture as check_jobs_page.py: a real uvicorn server on a throwaway
CUORE_STATE_DIR, the Stelvio (VIN below, real corpus) as the fixture vehicle,
headless Edge driven over CDP for anything that needs actual layout (font
size, button height, overflow) rather than just HTML text.

Five checks:
  1. The dossier (/v/{VIN}) and job (/v/{VIN}/job) pages render 200 with
     data-marque="alfa" on <html> (the default marque, nothing set it).
  2. Over CDP: computed body font-size >= 16px, and the flow-bar's
     "Suggested next" button (.flow-next) is >= 44px tall.
  3. Over CDP at 400px: no page-level horizontal overflow on either page.
  4. The light toggle still works: setting data-theme="light" on <html>
     changes the computed --bg custom property to the light value.
  5. print.css is still linked with media="print" on both pages.

Also writes three screenshots to the scratchpad for a one-time visual
read: job_400.png, dossier_400.png, job_1400.png.

Run:
    .venv/Scripts/python.exe cuore/tests/check_theme.py
"""

from __future__ import annotations

import base64
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-theme-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

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


client = TestClient(create_app())


# --- 1 & 5: cheap HTML-text checks via TestClient ---------------------------

dossier_html = client.get(f"/v/{VIN}").text
job_html = client.get(f"/v/{VIN}/job").text

check("dossier page renders 200 with data-marque=\"alfa\"",
      '<html lang="en" data-marque="alfa">' in dossier_html, dossier_html[:200])
check("job page renders 200 with data-marque=\"alfa\"",
      '<html lang="en" data-marque="alfa">' in job_html, job_html[:200])

check("dossier page still links print.css for the print media",
      bool(re.search(r'<link[^>]+print\.css[^>]+media="print"', dossier_html)), "")
check("job page still links print.css for the print media",
      bool(re.search(r'<link[^>]+print\.css[^>]+media="print"', job_html)), "")


# --- 2, 3, 4: real layout, over CDP against a live server ------------------

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


edge = find_edge()
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

if not edge:
    check("headless Edge is available for the layout checks", False, str(EDGE_CANDIDATES))
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
            # Seed a job so the job page's flow bar shows the real "Suggested
            # next" button, not the empty-job fallback.
            data = urllib.parse.urlencode(
                {"technician": "tester", "complaint": "CEL, smells like gas"}).encode()
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"http://127.0.0.1:{port}/v/{VIN}/job/open",
                                           data=data, method="POST"), timeout=10)
            except Exception as exc:  # noqa: BLE001
                check("seeding a job on the screenshot server", False, str(exc))

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

                for page_name, path, shot_name in (
                    ("job", f"/v/{VIN}/job", "job_400.png"),
                    ("dossier", f"/v/{VIN}", "dossier_400.png"),
                ):
                    # /json/new?<url> only registers the target's intended
                    # url on this Edge build -- it does not actually drive
                    # the navigation (location.href stays "about:blank").
                    # An explicit Page.navigate after connecting is what
                    # reliably loads the real page.
                    target = open_target(devtools_port, "about:blank")
                    cdp = CDP(target["webSocketDebuggerUrl"])
                    try:
                        cdp.send("Page.enable")
                        cdp.send("Runtime.enable")
                        cdp.send("Page.navigate", {"url": f"http://127.0.0.1:{port}{path}"})
                        time.sleep(1.2)
                        cdp.send("Emulation.setDeviceMetricsOverride", {
                            "width": 400, "height": 1400, "deviceScaleFactor": 1, "mobile": True,
                        })
                        time.sleep(0.6)

                        ready = cdp.eval_value("document.readyState")
                        check(f"{page_name} page loaded in the headless browser",
                              ready in ("complete", "interactive"), str(ready))

                        if page_name == "job":
                            fs = cdp.eval_value(
                                "parseFloat(getComputedStyle(document.body).fontSize)")
                            check("body font-size is >= 16px", fs is not None and fs >= 16, str(fs))

                            btn_h = cdp.eval_value(
                                "(function(){var b=document.querySelector('.flow-next');"
                                "return b?b.getBoundingClientRect().height:null;})()")
                            check("flow-bar \"Suggested next\" button is >= 44px tall",
                                  btn_h is not None and btn_h >= 44, str(btn_h))

                        dims = json.loads(cdp.eval_value(
                            "JSON.stringify({sw: document.documentElement.scrollWidth, "
                            "cw: document.documentElement.clientWidth})"))
                        sw, cw = dims.get("sw", 0), dims.get("cw", 0)
                        check(f"no page-level horizontal overflow on {page_name} at 400px",
                              sw <= cw + 1, f"scrollWidth={sw} clientWidth={cw}")

                        if page_name == "job":
                            # 4. light toggle still honoured.
                            cdp.send("Runtime.evaluate", {"expression":
                                "document.documentElement.setAttribute('data-theme','light')"})
                            bg = cdp.eval_value(
                                "getComputedStyle(document.documentElement)"
                                ".getPropertyValue('--bg').trim()")
                            check("data-theme=\"light\" renders the light --bg variable",
                                  bg == "#eef0f2", str(bg))
                            cdp.send("Runtime.evaluate", {"expression":
                                "document.documentElement.removeAttribute('data-theme')"})

                        shot = cdp.send("Page.captureScreenshot",
                                       {"format": "png", "captureBeyondViewport": False})
                        out_path = SCRATCHPAD / shot_name
                        out_path.write_bytes(base64.b64decode(shot["data"]))
                        check(f"screenshot {shot_name} captured",
                              out_path.exists() and out_path.stat().st_size > 0, str(out_path))

                        if page_name == "job":
                            cdp.send("Emulation.setDeviceMetricsOverride", {
                                "width": 1400, "height": 1800, "deviceScaleFactor": 1,
                                "mobile": False,
                            })
                            time.sleep(0.4)
                            shot_wide = cdp.send("Page.captureScreenshot", {"format": "png"})
                            wide_path = SCRATCHPAD / "job_1400.png"
                            wide_path.write_bytes(base64.b64decode(shot_wide["data"]))
                            check("screenshot job_1400.png captured",
                                  wide_path.exists() and wide_path.stat().st_size > 0,
                                  str(wide_path))
                    finally:
                        cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge completed the layout checks", False,
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
