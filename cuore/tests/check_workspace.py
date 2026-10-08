"""Checks for the job page as the single workspace: the home page routing
to the car in the bay (or to ``/start`` when none is), the 12 flow-step
anchors rendering inline on ``/v/{vin}/job``, the flow bar on the dossier
page, and the flow/tools-kb APIs wired through the real app.

Same posture as ``cuore/tests/check_jobs_page.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported, and the real MES
corpus on this machine (the Stelvio, VIN below -- chronic EVAP codes,
P0455/P0440/P0456) is the fixture.

Per the mechanic-UX review's Bench/tab reshuffle, the old dossier moved
from ``/v/{vin}`` to ``/v/{vin}/dossier`` -- check 3 below points there
now. The flow bar itself (_flow_bar.html) is job-specific chrome under
that same review (tab == "job" only), so the dossier page no longer
carries it; check 3 instead confirms the always-on compact vehicle strip
(.vline) that replaced it on every non-bench/report /v/ page.

Five checks:
  1. GET / redirects to /start when no car is in the bay.
  2. After an intake (via the real /start form), GET / redirects to that
     car's job page, and the job page renders step-1..step-12 anchors with
     the verdict card and codes table inline.
  3. The compact vehicle status strip (.vline) renders on the dossier page
     (/v/{vin}/dossier); the job-only flow bar does not.
  4. /api/vehicles/{vin}/flow and /api/tools-kb/recommend/oil_change both
     respond 200 through the real app.
  5. The job page renders at 400px with no page-level horizontal overflow
     (CDP technique from check_live_widgets.py; cleanup via _edge_cleanup).

Run:
    .venv/Scripts/python.exe cuore/tests/check_workspace.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-workspace-")
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


# --- 1. no car in the bay -> /start -----------------------------------------

resp1 = client.get("/", follow_redirects=False)
check("/ redirects when no car is in the bay", resp1.status_code in (302, 303, 307),
      str(resp1.status_code))
check("/ redirects to /start with no car in the bay",
      resp1.headers.get("location") == "/start", str(resp1.headers.get("location")))


# --- 2. after an intake, / redirects to the job; step anchors render -------

intake_resp = client.post("/start", data={"vin": VIN, "complaint": "CEL, smells like gas",
                                          "technician": "tester"}, follow_redirects=True)
check("intake via the real /start form responds 200", intake_resp.status_code == 200,
      str(intake_resp.status_code))

resp2 = client.get("/", follow_redirects=False)
check("/ redirects to that car's job page once it is in the bay",
      resp2.headers.get("location") == f"/v/{VIN}/job", str(resp2.headers.get("location")))

job_page = client.get(f"/v/{VIN}/job")
check("the job page responds 200", job_page.status_code == 200, str(job_page.status_code))
# The job page is one step per screen now, not all 12 anchors on one page:
# the current step renders its own section (id="step-N"), and the other
# 11 steps each render a headline row linking to ?step=N.
current_step_sections = re.findall(r'id="step-(\d+)"', job_page.text)
check("the job page renders exactly one current-step section",
      len(current_step_sections) == 1, str(current_step_sections))
headline_steps = re.findall(
    rf'class="step-headline[^"]*" href="/v/{VIN}/job\?step=(\d+)"', job_page.text)
check("the job page renders 11 headline rows linking to the other steps",
      len(headline_steps) == 11, str(headline_steps))
check("the current-step section plus the headline rows cover all 12 steps",
      sorted(int(n) for n in current_step_sections + headline_steps) == list(range(1, 13)),
      str(sorted(int(n) for n in current_step_sections + headline_steps)))
#  The job page is one step per screen (default step 2), so the verdict
# card (step 3) and codes table (step 4) only render on their own steps.
job_step3 = client.get(f"/v/{VIN}/job", params={"step": "3"})
check("the verdict card renders inline on the job page's step 3",
      "verdict-card" in job_step3.text, job_step3.text[:300])
job_step4 = client.get(f"/v/{VIN}/job", params={"step": "4"})
check("the codes table renders inline on the job page's step 4",
      "sec-history" in job_step4.text, job_step4.text[:300])


# --- 3. the compact vehicle strip renders on the dossier page --------------

dossier_page = client.get(f"/v/{VIN}/dossier")
check("the dossier page responds 200", dossier_page.status_code == 200,
      str(dossier_page.status_code))
check("the compact vehicle strip renders on the dossier page",
      'class="vline"' in dossier_page.text)
check("the job-only flow bar does not render on the dossier page",
      "flow-bar" not in dossier_page.text)


# --- 4. the flow + tools-kb APIs respond through the real app --------------

flow_resp = client.get(f"/api/vehicles/{VIN}/flow")
check("/api/vehicles/{vin}/flow responds 200 through the real app",
      flow_resp.status_code == 200, str(flow_resp.status_code))

tools_kb_resp = client.get("/api/tools-kb/recommend/oil_change")
check("/api/tools-kb/recommend/oil_change responds 200 through the real app",
      tools_kb_resp.status_code == 200, str(tools_kb_resp.status_code))


# --- 5. the job page renders at 400px with no horizontal overflow ----------

print("=== screenshot + overflow at 400px ===")
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
SCRATCHPAD = Path(r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User"
                  r"\7cb02eb5-e299-4baf-b34b-9eb82aebbf17\scratchpad")


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
server_dir = tempfile.mkdtemp(prefix="cuore-check-workspace-server-")
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
            # Seed a real intake on the screenshot server's own state dir, so
            # the page under screenshot renders the full 12-step workspace,
            # not the empty "no visit open" step 1.
            data = urllib.parse.urlencode(
                {"vin": VIN, "complaint": "CEL, smells like gas",
                 "technician": "tester"}).encode()
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"http://127.0.0.1:{port}/start",
                                           data=data, method="POST"), timeout=10)
            except Exception as exc:  # noqa: BLE001
                check("seeding an intake on the screenshot server", False, str(exc))

            time.sleep(0.3)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-workspace-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1400",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}/job"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    time.sleep(1.5)
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 1400, "deviceScaleFactor": 1, "mobile": True,
                    })
                    time.sleep(0.6)

                    nav = cdp.send("Runtime.evaluate", {
                        "expression": "document.readyState", "returnByValue": True})
                    check("job page loaded in the headless browser",
                          nav.get("result", {}).get("value") in ("complete", "interactive"),
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

                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    out_path = SCRATCHPAD / "workspace_job_phone.png"
                    shot = cdp.send("Page.captureScreenshot",
                                   {"format": "png", "captureBeyondViewport": False})
                    out_path.write_bytes(base64.b64decode(shot["data"]))
                    check("screenshot workspace_job_phone.png captured",
                         out_path.exists() and out_path.stat().st_size > 0, str(out_path))
                    if out_path.exists():
                        print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge captured the job page screenshot over CDP", False,
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
