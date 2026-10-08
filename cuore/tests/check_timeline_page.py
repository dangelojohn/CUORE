"""Checks for the "Codes vs. what the driver notices" timeline page
(``/v/{vin}/timeline``) and the symptom form it shares with ``code.html``.

Same posture as ``cuore/tests/check_live_dashboard_page.py`` (this file's
screenshot/CDP plumbing is copied from there almost verbatim): ``
CUORE_STATE_DIR`` is pointed at a throwaway directory BEFORE cuore is
imported, and ``cuore/web/timeline_routes.py`` is not yet wired into
``cuore/app.py``, so ``_app_with_router()``/the server snippet include it
themselves if ``create_app()`` did not already pick it up.

``cuore/services/timeline_bridge.py`` is being built in parallel by another
agent and may not exist yet -- ``timeline_routes`` falls back to its own
built-in fixture in that case (see that module's docstring), so every check
below runs either way. The one check that is genuinely bridge-dependent
(the symptom actually appearing back on the page after a POST, since the
fixture path has nowhere durable to write it) is skipped with a clear note
when the bridge is absent, per the task brief.

Parts:
  1. The page, the symptom form and the code page's feel card, over
     TestClient.
  2. Visual grammar content checks on the rendered SVG: every legend line
     style (solid/dashed/dotted/thick) and marker shape, the fuel band, and
     that dashed/dotted strokes are actually emitted.
  3. A real server, screenshotted at 400px and 1400px over CDP, with a
     horizontal-overflow check (the page itself must never scroll sideways
     -- only the chart's own box may).

Run:
    .venv/Scripts/python.exe cuore/tests/check_timeline_page.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-timeline-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import timeline_routes  # noqa: E402

from websockets.sync.client import connect  # noqa: E402

VIN = "ZASFAKPN5J7B88115"           # the Stelvio -- real corpus
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
SCRATCHPAD = Path(r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User"
                  r"\7cb02eb5-e299-4baf-b34b-9eb82aebbf17\scratchpad")

BRIDGE_PRESENT = timeline_routes._bridge() is not None

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
    already = any(getattr(r, "path", "").startswith("/v/{vin}/timeline") for r in app.routes)
    if not already:
        app.include_router(timeline_routes.router)
    return app


# ===========================================================================
# 1. the page, the symptom form, the code page's feel card -- over TestClient
# ===========================================================================

print("=== page (TestClient) ===")
client = TestClient(_app_with_router())

page = client.get(f"/v/{VIN}/timeline")
check("timeline page responds 200", page.status_code == 200, str(page.status_code))
check("timeline page is HTML with an inline SVG", "<svg" in page.text and "<html" in page.text.lower())
check("no template error leaked onto the page",
      "Jinja2" not in page.text and "Traceback" not in page.text)
check("vbar carries a Timeline tab", f'/v/{VIN}/timeline' in page.text and ">Timeline<" in page.text)
check("sticky lane-label column present", 'class="tl-labels"' in page.text)
check("accessible list view present", "List view" in page.text and "<details" in page.text)
check("correlation table present", 'class="tl-corr"' in page.text or "No code family" in page.text)

axis_resp = client.get(f"/v/{VIN}/timeline?axis=odometer")
check("axis=odometer responds 200", axis_resp.status_code == 200, str(axis_resp.status_code))
check("odometer axis link marked current", 'axis=odometer' in axis_resp.text)

for rk in ("all", "1y", "90d", "30d"):
    rr = client.get(f"/v/{VIN}/timeline?range={rk}")
    check(f"range={rk} responds 200", rr.status_code == 200, str(rr.status_code))

# --- symptom form round-trip --------------------------------------------

print("=== symptom form ===")
form_resp = client.get(f"/v/{VIN}/timeline")
check("symptom form present on timeline page", 'id="symptom-form"' in form_resp.text)
check("'Drives normally' chip present and first", "Drives normally" in form_resp.text)
check("evidence hint present", "Nothing felt is useful evidence" in form_resp.text)

post = client.post(f"/v/{VIN}/symptoms", data={
    "redirect_to": f"/v/{VIN}/timeline",
    "at": "", "reporter": "driver", "tags": ["drives_normally"],
    "conditions": ["highway"], "text": "check_timeline_page.py smoke test",
}, follow_redirects=False)
check("symptom POST redirects (303)", post.status_code == 303, str(post.status_code))
location = post.headers.get("location", "")
check("redirect carries a flash", "saved=1" in location or "error=" in location, location)

if not BRIDGE_PRESENT:
    print("  [skip] symptom actually appearing on the page -- "
        "cuore.services.timeline_bridge is not built yet, so this form has "
        "nowhere durable to write to; the fixture path is exercised above "
        "(redirect + flash), which is as far as it can go until the bridge lands.")
else:
    followed = client.get(location)
    check("flash appears after following the redirect", "Recorded" in followed.text)

bad_post = client.post(f"/v/{VIN}/symptoms", data={
    "redirect_to": f"/v/{VIN}/timeline", "reporter": "driver", "text": "no tags",
}, follow_redirects=False)
check("a symptom POST with no tags still redirects with an error, not a 500",
      bad_post.status_code == 303 and "error=" in bad_post.headers.get("location", ""),
      str(bad_post.status_code) + " " + bad_post.headers.get("location", ""))

# --- code page's feel card ----------------------------------------------

print("=== code page feel card ===")
code_resp = client.get(f"/v/{VIN}/code/P0456")
check("code page responds 200", code_resp.status_code == 200, str(code_resp.status_code))
check("feel card present", "What would the driver feel?" in code_resp.text)
check("feel card shows a knowledge-table answer or the TechAuthority fallback",
      ("Not in the knowledge table" in code_resp.text) or ("occurrence(s)" in code_resp.text))
check("symptom form also offered on the code page", 'id="symptom-form"' in code_resp.text)

# Direct unit check of the fallback text, independent of which real codes
# the knowledge table happens to cover today: render code.html with the
# globals' code_feel swapped for one that always misses.
real_code_feel = timeline_routes._shared_templates.env.globals["code_feel"]
try:
    timeline_routes._shared_templates.env.globals["code_feel"] = (
        lambda vin, code: {"feel": None, "pattern": {"occurrences": 0,
                           "symptom_reports_near": 0, "by_tag": {}, "drives_normally_near": 0}})
    miss_resp = client.get(f"/v/{VIN}/code/U0100")
finally:
    timeline_routes._shared_templates.env.globals["code_feel"] = real_code_feel
check("a knowledge-table miss falls back to the TechAuthority line",
      miss_resp.status_code == 200 and "Not in the knowledge table" in miss_resp.text
      and "TechAuthority" in miss_resp.text, f"status={miss_resp.status_code}")


# ===========================================================================
# 2. visual-grammar content checks on the rendered SVG
# ===========================================================================

print("=== visual grammar (legend + strokes) ===")
svg_text = page.text
LEGEND_NEEDLES = [
    "active", "cleared (unverified)", "stale (not seen since)", "returned after clear",
    "code read (present)", "code read (clean)", "clear", "repair/test completed",
    "repair/test failed", "mechanic note", "symptom: drivability",
    "symptom: smell/refuel/warning", "drives normally",
]
for needle in LEGEND_NEEDLES:
    check(f"legend contains {needle!r}", needle in svg_text)
check("fuel/EVAP-window band present", "EVAP monitor window" in svg_text)
check("dashed/dotted strokes are actually emitted (stroke-dasharray)",
      "stroke-dasharray" in svg_text)
check("a double/thick stroke width is used for 'returned after clear' bars",
      "stroke-width=\"3." in svg_text or "stroke-width=\"4." in svg_text)


# ===========================================================================
# CDP plumbing (copied from check_live_dashboard_page.py)
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
# 3. screenshots at 400px and 1400px, plus the horizontal-overflow check
# ===========================================================================

print("=== screenshots + overflow ===")
edge = find_edge()
server_dir = tempfile.mkdtemp(prefix="cuore-check-timeline-server-")
port = free_port()
env = dict(os.environ)
env["CUORE_STATE_DIR"] = server_dir

_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
from cuore.web import timeline_routes
import uvicorn

app = create_app()
if not any(getattr(r, "path", "").startswith("/v/{{vin}}/timeline") for r in app.routes):
    app.include_router(timeline_routes.router)
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
            time.sleep(0.5)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-timeline-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=1400,1400",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}/timeline"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    time.sleep(2.0)  # cold-cache first request: real MES-corpus workup
                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    for w, h, name in ((400, 1400, "timeline_phone.png"), (1400, 1000, "timeline_desktop.png")):
                        try:
                            cdp.send("Emulation.setDeviceMetricsOverride", {
                                "width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 600,
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
                            check(f"no page-level horizontal overflow at {w}px",
                                 sw <= cw + 1, f"scrollWidth={sw} clientWidth={cw}")

                            out_path = SCRATCHPAD / name
                            shot = cdp.send("Page.captureScreenshot",
                                           {"format": "png", "captureBeyondViewport": False})
                            out_path.write_bytes(base64.b64decode(shot["data"]))
                            check(f"screenshot {name} captured",
                                 out_path.exists() and out_path.stat().st_size > 0, str(out_path))
                            if out_path.exists():
                                print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
                        except Exception as exc:  # noqa: BLE001
                            check(f"screenshot/overflow check at {w}px", False, f"{type(exc).__name__}: {exc}")
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
# 4. the two other pages this change touches, run as subprocesses
# ===========================================================================

print("=== companion checks (check_dossier_page.py, check_api.py) ===")
for script in ("check_dossier_page.py", "check_api.py"):
    proc = subprocess.run([sys.executable, str(Path(__file__).parent / script)],
                          cwd=str(ROOT), capture_output=True, text=True)
    ok = proc.returncode == 0
    check(f"{script} exits 0", ok,
         (proc.stdout[-1500:] + proc.stderr[-1500:]) if not ok else "")
    print(f"  {script}: " + proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else script)


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
