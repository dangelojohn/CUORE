"""Checks for the Job (case) workflow: ``mes.jobs``, ``cuore.services.jobs_bridge``,
``cuore/api/jobs.py`` and the ``/v/{vin}/job`` page.

Same posture as ``cuore/tests/check_dossier_page.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported, and the real MES
corpus on this machine (the Stelvio, VIN below -- chronic EVAP codes,
P0455/P0440/P0456) is the fixture for the suggested-hypothesis evidence.

Five checks:
  1. Opening a case via the HTML form lands a job on the page.
  2. The suggested hypotheses include an EVAP one with >=1 real evidence_for ref.
  3. Add action + set hypothesis status round trip (both via the HTML forms).
  4. Closing with an outcome is required and sticks; closing is blocked
     without a tools-used review or a stated skip reason (see
     ``mes.tools_kb``/``mes.tool_usage`` and
     ``cuore.services.jobs_bridge.close_job``), and allowed once one is given.
  5. The job page renders 200 at 400px with no page-level horizontal overflow.

Run:
    .venv/Scripts/python.exe cuore/tests/check_jobs_page.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-jobs-")
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


# --- 1. open a case via the HTML form ---------------------------------------

open_resp = client.post(f"/v/{VIN}/job/open",
                        data={"technician": "tester", "complaint": "CEL, smells like gas"},
                        follow_redirects=True)
check("opening a case via the HTML form responds 200", open_resp.status_code == 200,
      str(open_resp.status_code))
check("the job page shows the complaint back", "smells like gas" in open_resp.text)

view = client.get(f"/api/vehicles/{VIN}/job").json()
job = view.get("job")
check("a job landed for this VIN", job is not None, str(view))
job_id = job["id"] if job else None
check("the new job starts open with no outcome",
      bool(job) and job["status"] == "open" and job["outcome"] is None, str(job))


# --- 2. suggested hypotheses include a real-evidenced EVAP one -------------

suggestions = view.get("suggested_hypotheses", [])
check("at least one suggested hypothesis was offered", len(suggestions) > 0, str(suggestions))

evap_suggestion = next((s for s in suggestions if s.get("system") == "EVAP"
                        and s["evidence_for"]), None)
check("an EVAP suggested hypothesis carries >=1 real evidence_for ref",
      evap_suggestion is not None, str(suggestions))
if evap_suggestion is not None:
    ref = evap_suggestion["evidence_for"][0]
    check("that evidence ref has kind/id/label (a real record, not invented)",
          {"kind", "id", "label"} <= set(ref), str(ref))


# --- 3. add action + set hypothesis status round trip ----------------------

if job_id and evap_suggestion is not None:
    add_resp = client.post(f"/v/{VIN}/job/{job_id}/hypotheses/suggested", data={
        "text": evap_suggestion["text"], "system": evap_suggestion["system"],
        "next_test": evap_suggestion["next_test"],
        "evidence_for": json.dumps(evap_suggestion["evidence_for"]),
        "evidence_against": json.dumps(evap_suggestion["evidence_against"]),
    }, follow_redirects=True)
    check("promoting a suggested hypothesis via its form responds 200",
          add_resp.status_code == 200, str(add_resp.status_code))

    view2 = client.get(f"/api/vehicles/{VIN}/job").json()
    hyps = view2["job"]["hypotheses"]
    check("the promoted hypothesis is now on the job's ledger",
          any(h["text"] == evap_suggestion["text"] for h in hyps), str(hyps))
    hyp = next(h for h in hyps if h["text"] == evap_suggestion["text"])
    check("its real evidence_for ref(s) carried over, not re-invented",
          len(hyp["evidence_for"]) == len(evap_suggestion["evidence_for"]), str(hyp))

    status_resp = client.post(
        f"/v/{VIN}/job/{job_id}/hypotheses/{hyp['id']}/status",
        data={"status": "supported"}, follow_redirects=True)
    check("setting a hypothesis's status via its form responds 200",
          status_resp.status_code == 200, str(status_resp.status_code))

    action_resp = client.post(f"/v/{VIN}/job/{job_id}/actions",
                              data={"kind": "test", "text": "smoke tested recirc line, clean"},
                              follow_redirects=True)
    check("recording an action via its form responds 200",
          action_resp.status_code == 200, str(action_resp.status_code))

    view3 = client.get(f"/api/vehicles/{VIN}/job").json()
    hyp3 = next(h for h in view3["job"]["hypotheses"] if h["id"] == hyp["id"])
    check("the hypothesis status round-tripped to 'supported'",
          hyp3["status"] == "supported", str(hyp3))
    check("the action round-tripped onto the job's action list",
          any(a["text"] == "smoke tested recirc line, clean" for a in view3["job"]["actions"]),
          str(view3["job"]["actions"]))
else:
    check("step 3 skipped: no job/suggestion to work with", False, "see checks above")


# --- 4. close requires an outcome, and it sticks ----------------------------

if job_id:
    bad_close = client.post(f"/v/{VIN}/job/{job_id}/close", data={"outcome": ""})
    check("closing with no outcome is refused, not silently accepted",
          bad_close.status_code == 422, str(bad_close.status_code))

    # The tools-used review is mandatory before a close is accepted (see
    # cuore.services.jobs_bridge.close_job) -- closing with no review and no
    # stated skip reason must be refused, not silently accepted.
    unreviewed_close = client.post(f"/v/{VIN}/job/{job_id}/close",
                                   data={"outcome": "fixed"}, follow_redirects=True)
    view_unreviewed = client.get(f"/api/vehicles/{VIN}/job/{job_id}").json()
    check("closing with no tools review and no skip reason is refused",
          view_unreviewed["job"]["status"] != "closed", str(view_unreviewed["job"]))
    check("the refusal is explained on the re-rendered page",
          "tools used review" in unreviewed_close.text.lower(), unreviewed_close.text[:2000])

    close_resp = client.post(f"/v/{VIN}/job/{job_id}/close",
                             data={"outcome": "fixed", "verdict": "ECM recalibrated per TSB",
                                   "tools_review_skip_reason": "no usage review captured on this run"},
                             follow_redirects=True)
    check("closing with a real outcome and a stated skip reason responds 200",
          close_resp.status_code == 200, str(close_resp.status_code))

    view4 = client.get(f"/api/vehicles/{VIN}/job/{job_id}").json()
    check("the job is now closed with outcome 'fixed'",
          view4["job"]["status"] == "closed" and view4["job"]["outcome"] == "fixed",
          str(view4["job"]))
    check("the skip reason was recorded as a job action, not silently dropped",
          any("Tools-used review skipped" in a["text"] for a in view4["job"]["actions"]),
          str(view4["job"]["actions"]))
else:
    check("step 4 skipped: no job to close", False, "see checks above")


# --- 5. the page renders at 400px with no horizontal overflow --------------

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
server_dir = tempfile.mkdtemp(prefix="cuore-check-jobs-server-")
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
            # Seed a real open job on the server's own state dir, so the
            # page under screenshot renders the full stepper, not the empty
            # "open a case" form.
            data = urllib.parse.urlencode(
                {"technician": "tester", "complaint": "CEL, smells like gas"}).encode()
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"http://127.0.0.1:{port}/v/{VIN}/job/open",
                                           data=data, method="POST"), timeout=30)
            except Exception as exc:  # noqa: BLE001
                check("seeding a job on the screenshot server", False, str(exc))

            time.sleep(0.3)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-jobs-"))
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
                    out_path = SCRATCHPAD / "job_phone.png"
                    shot = cdp.send("Page.captureScreenshot",
                                   {"format": "png", "captureBeyondViewport": False})
                    out_path.write_bytes(base64.b64decode(shot["data"]))
                    check("screenshot job_phone.png captured",
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
