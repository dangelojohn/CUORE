"""Checks for the "one step per screen" job page redesign: the ``?step=N``
query param on ``/v/{vin}/job`` (cuore/web/jobs_routes.py, job.html), the
12-icon process map, and the header language chooser (POST /lang).

Same posture as check_jobs_page.py: ``CUORE_STATE_DIR`` pointed at a
throwaway directory before cuore is imported, the Stelvio (real corpus) as
the fixture vehicle. Lighter on purpose -- everything except the overflow
check runs against a plain ``TestClient`` (no server, no browser); only the
no-overflow check needs real layout, so only that one spins up a server +
headless Edge, and it takes no screenshot (just reads scrollWidth over
CDP) to keep this cheap to run.

Five checks:
  1. ``?step=7`` renders step 7's full content and the other 11 steps as
     headline rows only (11 ``.step-headline`` rows, step 7's own
     ``step-title`` heading present, no other step's heading present).
  2. The process map renders all 12 step icons, with exactly one marked
     current.
  3. ``?step=12`` shows the release link.
  4. POST /lang (it) sets the cookie; the job page then carries Italian
     labels (e.g. "Rilascio" for step 12's headline, with no ?step= so
     step 1 is current and step 12 is a headline row).
  5. No page-level horizontal overflow at 400px (CDP, no screenshot).

Run:
    .venv/Scripts/python.exe cuore/tests/check_screens.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-screens-")
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

open_resp = client.post(f"/v/{VIN}/job/open",
                        data={"technician": "tester", "complaint": "CEL, smells like gas"},
                        follow_redirects=True)
check("opening a case for the fixture responds 200", open_resp.status_code == 200,
      str(open_resp.status_code))


# --- 1. ?step=7 shows step 7's full content, the rest as headlines --------

step7 = client.get(f"/v/{VIN}/job", params={"step": "7"})
check("?step=7 responds 200", step7.status_code == 200, str(step7.status_code))
text7 = step7.text
check("?step=7 shows step 7's own heading", 'id="step-7"' in text7, "no id=\"step-7\"")
for n in [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12]:
    check(f"?step=7 does not show step {n}'s full heading", f'id="step-{n}"' not in text7,
          f"id=\"step-{n}\" found on the step=7 screen")
_headline_count = text7.count('<a class="step-headline ')
check("?step=7 shows exactly 11 headline rows",
      _headline_count == 11, f"found {_headline_count}")


# --- 2. process map: 12 icons, exactly one current -------------------------

_pm_count = text7.count('<a class="pm-step ')
check("process map renders all 12 step icons", _pm_count == 12, f"found {_pm_count}")
check("process map marks exactly one step current",
      len(re.findall(r'class="pm-step [^"]*\bpm-current\b', text7)) == 1,
      str(len(re.findall(r'pm-current', text7))))
check("process map's current icon links to step 7",
      re.search(r'<a class="pm-step[^"]*pm-current[^"]*"\s+href="/v/' + re.escape(VIN)
               + r'/job\?step=7"', text7) is not None,
      "no pm-current anchor pointing at ?step=7")


# --- 3. ?step=12 shows the release link -------------------------------------

step12 = client.get(f"/v/{VIN}/job", params={"step": "12"})
check("?step=12 responds 200", step12.status_code == 200, str(step12.status_code))
check("?step=12 shows the release link", f'/v/{VIN}/release' in step12.text and
      "Go to release" in step12.text, "release link/text not found")
check("?step=12 shows step 12's own heading", 'id="step-12"' in step12.text,
      "no id=\"step-12\"")


# --- 4. POST /lang then Italian labels on the job page ---------------------

lang_resp = client.post("/lang", data={"lang": "it", "next": f"/v/{VIN}/job"},
                        follow_redirects=False)
check("POST /lang responds with a redirect", lang_resp.status_code in (302, 303),
      str(lang_resp.status_code))
check("the lang cookie was set to it", client.cookies.get("lang") == "it",
      str(client.cookies.get("lang")))

job_it = client.get(f"/v/{VIN}/job")
check("job page responds 200 after switching language", job_it.status_code == 200,
      str(job_it.status_code))
check("job page shows an Italian step label (Rilascio) after POST /lang",
      "Rilascio" in job_it.text, "Rilascio (release, it) not found")
check("the IT button reads as active in the header chooser",
      re.search(r'value="it"\s+class="lang-btn lang-btn-active"', job_it.text) is not None,
      "lang-btn-active not found on the it button")


# --- 5. no horizontal overflow at 400px (CDP, no screenshot) ---------------

print("=== overflow check at 400px (no screenshot) ===")
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
server_dir = tempfile.mkdtemp(prefix="cuore-check-screens-server-")
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
    check("headless Edge is available for the overflow check", False, str(EDGE_CANDIDATES))
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
                check("seeding a job on the overflow-check server", False, str(exc))

            time.sleep(1.0)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-screens-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1400",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}/job?step=7"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    time.sleep(1.2)
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 1400, "deviceScaleFactor": 1, "mobile": True,
                    })
                    time.sleep(0.5)

                    nav = cdp.send("Runtime.evaluate", {
                        "expression": "document.readyState", "returnByValue": True})
                    check("job page (step=7) loaded in the headless browser",
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
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge measured the job page over CDP", False,
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
