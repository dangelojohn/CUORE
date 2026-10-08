"""Checks for the one-car-at-a-time shop flow: ``mes.shop``,
``cuore.services.shop_bridge`` and the ``/start`` page.

Same posture as ``cuore/tests/check_jobs_page.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE anything is imported. ``/start`` and
``/v/{vin}/release`` are not registered on ``cuore.app.create_app`` yet --
that file is owned by another agent while this was built -- so the
screenshot check mounts a minimal standalone app over the same
``shop_routes.router`` instead of going through ``create_app``.

Five checks:
  1. Intake creates a visit and a linked Job (same vin, visit.job_id == job.id).
  2. The release view resolves that visit from the VIN, with its dossier verdict.
  3. Step timing (start_step/end_step) records minutes.
  4. Release advises and records rather than blocking: an unverified release
     succeeds and is recorded as ``released_unverified`` with the given
     reason; a dossier-verified one records ``fixed``.
  5. ``/start`` renders 200 at 400px with no page-level horizontal overflow.

Run:
    .venv/Scripts/python.exe cuore/tests/check_shop_page.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-shop-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cuore import bootstrap  # noqa: E402,F401 -- side effect: puts `mes` on sys.path

from mes import jobs as jobs_mod  # noqa: E402
from mes import shop as shop_mod  # noqa: E402

from cuore.services import shop_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- 1. intake creates a visit and a linked job -----------------------------

visit = shop_bridge.intake(VIN, "CEL, smells like gas", technician="tester")
check("intake returns a visit for this VIN", visit.get("vin") == VIN, str(visit))
check("intake starts the visit with status 'in'", visit.get("status") == "in", str(visit))
check("intake links a job id", bool(visit.get("job_id")), str(visit))

job = jobs_mod.get(visit["job_id"]) if visit.get("job_id") else None
check("the linked job exists and matches this VIN",
      job is not None and job["vin"] == VIN, str(job))


# --- 2. the release view resolves this visit from the VIN ------------------

view = shop_bridge.build_release_view_for_vin(VIN)
check("the release view resolves the visit just taken in",
      view["visit"]["id"] == visit["id"], str(view["visit"]))
check("the release view carries a dossier_verdict key (possibly None)",
      "dossier_verdict" in view, str(view))
check("'verified' is a plain bool, never mechanic-suppliable",
      isinstance(view["verified"], bool), str(view.get("verified")))


# --- 3. step timing records minutes -----------------------------------------

shop_bridge.start_step(visit["id"], 1)
time.sleep(1.1)
after_end = shop_bridge.end_step(visit["id"], 1)
step1 = next(s for s in after_end["step_times"] if s["step"] == 1)
check("the step timer closed with a real end timestamp",
      step1["ended_at"] is not None, str(step1))
# Timestamps are second-precision (same convention as mes.jobs), so a
# sub-minute step can legitimately round to 0.0 -- what matters is that a
# real, non-negative number was recorded, not invented or left null.
check("the step timer recorded a real, non-negative number of minutes",
      isinstance(step1["minutes"], (int, float)) and step1["minutes"] >= 0,
      str(step1))


# --- 4. release advises and records; it never blocks -----------------------
# The real Stelvio corpus is chronic/unverified (see check_api.py), so
# releasing through the bridge with no checks ticked and no prior readiness
# must still succeed -- it just records the decision as released unverified.

released = shop_bridge.release(visit["id"], {
    "report_printed": False, "labels_printed": False, "parts_logged": False,
    "tools_reviewed": False, "notes": "customer waiting",
}, reason="customer waiting, will verify next visit")
check("release with every check unmet still succeeds -- advisory, not a gate",
      released["status"] == "out" and released["out_at"] is not None, str(released))
check("an unverified release is recorded with that outcome, not 'fixed'",
      released["outcome"] == "released_unverified", str(released.get("outcome")))
check("the reason given is recorded under unverified_override",
      released["release"].get("unverified_override") == "customer waiting, will verify next visit",
      str(released["release"]))

job_after = jobs_mod.get(visit["job_id"])
check("release closes the still-open linked job (as 'deferred', since the "
      "Job vocabulary has no released_unverified outcome)",
      job_after is not None and job_after["status"] == "closed"
      and job_after["outcome"] == "deferred", str(job_after))

# A second visit, released with dossier_verified forced true at the library
# level, to prove the 'fixed' path -- the real corpus is never actually
# VERIFIED_CLEAN, so this exercises mes.shop.release directly rather than
# going through the bridge's own dossier lookup.
visit2 = shop_bridge.intake(VIN, "second visit", technician="tester")
released2 = shop_mod.release(visit2["id"], {"report_printed": True, "labels_printed": True,
                                           "parts_logged": True, "tools_reviewed": True},
                             dossier_verified=True)
check("release with dossier_verified=True records outcome 'fixed'",
      released2["outcome"] == "fixed" and released2["release"]["verified"] is True,
      str(released2))
check("a verified release carries no unverified_override",
      "unverified_override" not in released2["release"], str(released2["release"]))


# --- 5. /shop renders at 400px with no horizontal overflow -----------------

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
server_dir = tempfile.mkdtemp(prefix="cuore-check-shop-server-")
port = free_port()
env = dict(os.environ)
env["CUORE_STATE_DIR"] = server_dir

# A minimal standalone app over shop_routes -- app.py (which owns the real
# router registration) is being edited by another agent concurrently, so
# this does not depend on that landing first.
_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from cuore.config import load as load_settings
from cuore.web import routes as web_routes
from cuore.web import shop_routes
import uvicorn

app = FastAPI()
app.state.settings = load_settings()
app.include_router(shop_routes.router)
app.mount("/static", StaticFiles(directory=str(web_routes.STATIC_DIR)), name="static")
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
            time.sleep(0.3)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-shop-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1400",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/start"
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
                    check("shop page loaded in the headless browser",
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
                    out_path = SCRATCHPAD / "shop_phone.png"
                    shot = cdp.send("Page.captureScreenshot",
                                   {"format": "png", "captureBeyondViewport": False})
                    out_path.write_bytes(base64.b64decode(shot["data"]))
                    check("screenshot shop_phone.png captured",
                         out_path.exists() and out_path.stat().st_size > 0, str(out_path))
                    if out_path.exists():
                        print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge captured the shop page screenshot over CDP", False,
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
