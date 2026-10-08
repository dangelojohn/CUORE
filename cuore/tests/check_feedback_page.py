"""Smoke checks for the feedback UI: data-fact on the dossier, the no-JS
plain-form POST, the inbox listing, the answer form, and the counts
endpoint reflecting it.

``CUORE_STATE_DIR`` is pointed at a fresh tempdir BEFORE anything cuore/mes
is imported (same posture as ``check_parts_page.py``). Neither
``cuore.web.inbox_routes`` nor ``cuore.api.feedback`` is wired into
``cuore.app`` yet -- ``app.py`` is owned by another agent -- so this
includes them itself if ``create_app()`` did not already pick them up (same
posture as ``check_parts_page.py``/``check_timeline_page.py``).

Run:
    .venv/Scripts/python.exe cuore/tests/check_feedback_page.py
"""

from __future__ import annotations

import base64
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
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-feedback-page-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import inbox_routes  # noqa: E402
from cuore.api import feedback as feedback_api  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def _app_with_router():
    app = create_app()
    if not any(getattr(r, "path", "") == "/v/{vin}/inbox" for r in app.routes):
        app.include_router(inbox_routes.router)
    if not any(getattr(r, "path", "") == "/api/vehicles/{vin}/feedback" for r in app.routes):
        app.include_router(feedback_api.router, prefix="/api")
    return app


client = TestClient(_app_with_router())


# === 1. the dossier carries data-fact and the feedback script ==============

r = client.get(f"/v/{VIN}")
check("dossier responds 200", r.status_code == 200, str(r.status_code))
check("dossier carries at least one data-fact attribute", 'data-fact="verdict|"' in r.text)
check("dossier loads feedback.js", "feedback.js" in r.text)
check("dossier carries the whole-page feedback FAB", 'id="feedback-fab"' in r.text)
check("dossier carries the no-JS feedback panel", 'id="feedback-page-panel"' in r.text)

_panel_tag = re.search(r'<details[^>]*id="feedback-page-panel"[^>]*>', r.text)
check("feedback page-panel <details> tag found", bool(_panel_tag))
if _panel_tag:
    tag = _panel_tag.group(0)
    check("feedback page-panel closed by default (no open attribute)",
          not re.search(r'\bopen\b', tag), tag)
    check("feedback page-panel carries the collapsed class",
          "feedback-page-panel-collapsed" in tag, tag)

# === 2. plain-form POST creates feedback and redirects back ================

r = client.post(f"/v/{VIN}/feedback", data={
    "redirect_to": f"/v/{VIN}",
    "page": f"/v/{VIN}", "section": "verdict", "item": "",
    "label": "(whole page)", "kind": "question",
    "text": "is this verdict still current after the smoke test?",
    "author": "tech1",
}, follow_redirects=False)
check("no-JS feedback POST redirects", r.status_code == 303, str(r.status_code))
check("redirects back to the page it came from", r.headers.get("location") == f"/v/{VIN}")

# === 3. inbox lists it, linking back to the page =============================

r = client.get(f"/v/{VIN}/inbox")
check("inbox page responds 200", r.status_code == 200, str(r.status_code))
check("inbox lists the question", "is this verdict still current" in r.text)
check("inbox links back to the dossier", f'href="/v/{VIN}' in r.text)

fb_rows = client.get(f"/api/vehicles/{VIN}/feedback").json()["feedback"]
check("exactly one feedback row recorded", len(fb_rows) == 1, str(len(fb_rows)))
fb_id = fb_rows[0]["id"]
check("row starts open", fb_rows[0]["status"] == "open", fb_rows[0]["status"])

# === 4. the answer form sets status answered ================================

r = client.post(f"/v/{VIN}/feedback/{fb_id}/answer", data={
    "redirect_to": f"/v/{VIN}/inbox",
    "text": "yes -- re-run after the latest clean scan, still VERIFIED_CLEAN.",
    "by": "claude",
}, follow_redirects=False)
check("answer POST redirects", r.status_code == 303, str(r.status_code))

answered = client.get(f"/api/vehicles/{VIN}/feedback").json()["feedback"][0]
check("row is now answered", answered["status"] == "answered", answered["status"])
check("answer text stored", "VERIFIED_CLEAN" in answered["answer"]["text"])

r = client.get(f"/v/{VIN}/inbox")
check("inbox shows the answer text", "VERIFIED_CLEAN" in r.text)

# === 5. the counts endpoint reflects it ======================================

key = f"/v/{VIN}|verdict|"
r = client.get(f"/api/vehicles/{VIN}/feedback/counts?targets={key}")
check("counts endpoint responds 200", r.status_code == 200, str(r.status_code))
tallies = r.json()["counts"].get(key)
check("counts show one answered, zero open", tallies == {"open": 0, "answered": 1,
                                                          "confirms": 0, "corrections": 0},
      str(tallies))


# === 6. screenshot: closed panel never covers the job page's step headings =

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
SCRATCHPAD = Path(r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User"
                  r"\7cb02eb5-e299-4baf-b34b-9eb82aebbf17\scratchpad")


def _find_edge() -> str:
    for candidate in EDGE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return ""


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _CDP:
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


def _wait_for_devtools(port: int, timeout: float = 20) -> None:
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
    raise RuntimeError(f"headless Edge devtools endpoint never came up: {last_err}")


def _open_target(port: int, url: str) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _wait_for_port(port: int, timeout: float = 15.0) -> bool:
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


_edge = _find_edge()
if not _edge:
    check("headless Edge is available for the job-page screenshot", False, str(EDGE_CANDIDATES))
else:
    from websockets.sync.client import connect  # noqa: E402

    _server_dir = tempfile.mkdtemp(prefix="cuore-check-feedback-server-")
    _port = _free_port()
    _env = dict(os.environ)
    _env["CUORE_STATE_DIR"] = _server_dir
    _env.pop("CUORE_AUDIT_PATH", None)

    # create_app() already wires inbox_routes/feedback_api/jobs_routes (see
    # cuore/app.py), so a plain run is enough -- no include-router dance
    # needed here, unlike check_live_dashboard_page.py's gauges route.
    _server_snippet = (
        "import sys; sys.path.insert(0, " + repr(str(ROOT)) + ")\n"
        "from cuore.app import create_app\n"
        "import uvicorn\n"
        "uvicorn.run(create_app(), host='127.0.0.1', port=" + str(_port) +
        ", log_level='warning')\n"
    )
    _server_proc = subprocess.Popen(
        [sys.executable, "-c", _server_snippet],
        cwd=str(ROOT), env=_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _up = _wait_for_port(_port)
        check("uvicorn came up for the screenshot check", _up, f"port {_port}")
        if _up:
            time.sleep(0.5)  # first-route import warmup
            # job.html only renders steps 2+ (including the "4. Scan &
            # codes" heading) once a job is open for this vin -- the fresh
            # CUORE_STATE_DIR this server points at starts with none.
            urllib.request.urlopen(urllib.request.Request(
                f"http://127.0.0.1:{_port}/v/{VIN}/job/open",
                data=b"technician=tech1&complaint=check+feedback+panel+overlap",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            ), timeout=10).read()
            _devtools_port = _free_port()
            _profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-feedback-"))
            _edge_proc = subprocess.Popen(
                [_edge, "--headless=new", f"--remote-debugging-port={_devtools_port}",
                 f"--user-data-dir={_profile_dir}", "--no-first-run",
                 "--window-size=1400,1000", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                _wait_for_devtools(_devtools_port)
                _url = f"http://127.0.0.1:{_port}/v/{VIN}/job"
                # /json/new?url creates the target but -- on this machine --
                # leaves it on about:blank rather than actually navigating
                # (confirmed by checking location.href after); Page.navigate
                # on an about:blank target navigates for real.
                _target = _open_target(_devtools_port, "about:blank")
                cdp = _CDP(_target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    cdp.send("Page.navigate", {"url": _url})
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 1400, "height": 1000, "deviceScaleFactor": 1, "mobile": False,
                    })
                    time.sleep(1.2)

                    out = cdp.send("Runtime.evaluate", {
                        "expression": (
                            "JSON.stringify((function(){"
                            "var h = document.getElementById('step-4');"
                            "var p = document.getElementById('feedback-page-panel');"
                            "if (!h || !p) return {ok:false};"
                            "var hr = h.getBoundingClientRect();"
                            "var pr = p.getBoundingClientRect();"
                            "var overlap = !(hr.right < pr.left || hr.left > pr.right ||"
                            "hr.bottom < pr.top || hr.top > pr.bottom);"
                            "return {ok:true, overlap: overlap, open: p.open,"
                            "heading: h.textContent};"
                            "})())"
                        ),
                        "returnByValue": True,
                    })
                    layout = json.loads(out.get("result", {}).get("value") or "{}")
                    check("job page and feedback panel both found for overlap check",
                          layout.get("ok", False), str(layout))
                    check("feedback page-panel starts closed on load",
                          layout.get("open") is False, str(layout))
                    check("closed feedback panel does not overlap the "
                          "'Scan & codes' step heading", layout.get("overlap") is False,
                          str(layout))

                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    shot_path = SCRATCHPAD / "feedback_job_page_1400.png"
                    shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                    shot_path.write_bytes(base64.b64decode(shot["data"]))
                    print(f"Screenshot: {shot_path}")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge captured the job-page screenshot over CDP", False,
                      f"{type(exc).__name__}: {exc}")
            finally:
                _edge_proc.terminate()
                try:
                    _edge_proc.wait(timeout=5)
                except Exception:
                    _edge_proc.kill()
                from _edge_cleanup import kill_edge_profile
                kill_edge_profile(_profile_dir)
                shutil.rmtree(_profile_dir, ignore_errors=True)
    finally:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
            _server_proc.wait(timeout=10)
        shutil.rmtree(_server_dir, ignore_errors=True)


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(" -", f)
if failures:
    sys.exit(1)
