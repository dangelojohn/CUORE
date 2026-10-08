"""Checks for the media gallery (``/v/{vin}/media``) and the "Photos &
video" attach strip (``_media_attach.html``) embedded on other pages.

Same posture as ``cuore/tests/check_timeline_page.py`` (CDP/screenshot
plumbing copied from there almost verbatim): ``CUORE_STATE_DIR`` is pointed
at a throwaway directory BEFORE cuore is imported, and
``cuore/web/media_routes.py`` is not yet wired into ``cuore/app.py``, so
``_app_with_router()``/the server snippet include it themselves if
``create_app()`` did not already pick it up.

``cuore/services/media_bridge.py`` (the real backend, built in parallel by
another agent) may not exist yet -- ``media_routes`` falls back to its own
in-memory fixture store in that case (see that module's docstring), so every
check below exercises the fixture path and passes either way.

Run:
    .venv/Scripts/python.exe cuore/tests/check_media_page.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-media-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import media_routes  # noqa: E402

from websockets.sync.client import connect  # noqa: E402

VIN = "ZASFAKPN5J7B88115"           # the Stelvio -- real corpus
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
SCRATCHPAD = Path(r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User"
                  r"\7cb02eb5-e299-4baf-b34b-9eb82aebbf17\scratchpad")

BRIDGE_PRESENT = media_routes._bridge() is not None

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
    already = any(getattr(r, "path", "").startswith("/v/{vin}/media") for r in app.routes)
    if not already:
        app.include_router(media_routes.router)
    return app


# ===========================================================================
# 1. gallery page, upload form, search -- over TestClient
# ===========================================================================

print("=== gallery page (TestClient) ===")
client = TestClient(_app_with_router())

page = client.get(f"/v/{VIN}/media")
check("media page responds 200", page.status_code == 200, str(page.status_code))
check("no template error leaked onto the page",
      "Jinja2" not in page.text and "Traceback" not in page.text)
check("vbar carries a Media tab", f'/v/{VIN}/media' in page.text and ">Media<" in page.text)
check("upload form present", 'id="media-upload-form"' in page.text and 'enctype="multipart/form-data"' in page.text)
check("file input accepts camera capture", 'capture="environment"' in page.text)
check("search box present", 'data-search' in page.text and 'name="q"' in page.text)
check("kind filter chips present", "Photo" in page.text and "Video" in page.text and "Document" in page.text)
check("export-zip link present", "Export everything" in page.text and "/export.zip" in page.text)
check("empty gallery says so", "No media yet" in page.text)

print("=== plain-form upload round-trip ===")
upload = client.post(
    f"/v/{VIN}/media",
    data={"caption": "evap smoke test leak", "tags": "evap, smoke",
         "target_kind": "code", "target_id": "P0456"},
    files=[("file", ("leak_test.jpg", b"not-a-real-jpeg", "image/jpeg"))],
    follow_redirects=False,
)
check("upload POST redirects (303)", upload.status_code == 303, str(upload.status_code))
location = upload.headers.get("location", "")
check("redirect carries a flash", "saved=1" in location or "error=" in location, location)

followed = client.get(location) if location.startswith("/") else client.get(f"/v/{VIN}/media")
check("uploaded item appears on the gallery", "leak_test.jpg" in followed.text or "evap smoke test leak" in followed.text,
      "item not found after upload")
check("flash appears after following the redirect", "Uploaded" in followed.text or "Not uploaded" in followed.text)

bad_upload = client.post(f"/v/{VIN}/media", data={"caption": "no file"}, follow_redirects=False)
check("an upload POST with no file still redirects with an error, not a 500",
      bad_upload.status_code == 303 and "error=" in bad_upload.headers.get("location", ""),
      str(bad_upload.status_code) + " " + bad_upload.headers.get("location", ""))

print("=== search / kind filter narrows results ===")
photo_hit = client.get(f"/v/{VIN}/media", params={"kind": "photo"})
check("kind=photo keeps the uploaded photo", "leak_test.jpg" in photo_hit.text)
doc_miss = client.get(f"/v/{VIN}/media", params={"kind": "document"})
check("kind=document excludes the uploaded photo", "leak_test.jpg" not in doc_miss.text)
q_hit = client.get(f"/v/{VIN}/media", params={"q": "smoke test"})
check("q='smoke test' matches the caption", "leak_test.jpg" in q_hit.text)
q_miss = client.get(f"/v/{VIN}/media", params={"q": "totally-unmatched-xyz"})
check("an unmatched query excludes it", "leak_test.jpg" not in q_miss.text)
target_hit = client.get(f"/v/{VIN}/media", params={"target_kind": "code", "target_id": "P0456"})
check("target_kind/target_id filter keeps the item", "leak_test.jpg" in target_hit.text)

# --- code page's attach strip -------------------------------------------

print("=== attach strip on code.html ===")
code_resp = client.get(f"/v/{VIN}/code/P0456")
check("code page responds 200", code_resp.status_code == 200, str(code_resp.status_code))
check("attach strip present on the code page", 'data-media-attach' in code_resp.text)
check("the uploaded item's thumbnail shows up on the code page's strip",
      'media-attach-thumb' in code_resp.text and '/api/media/' in code_resp.text)
check("strip offers a '+ add' affordance", 'media-attach-add' in code_resp.text)

# --- vehicle dossier: open-work step strips + notes-area strip ----------

print("=== attach strip on vehicle.html ===")
veh_resp = client.get(f"/v/{VIN}")
check("vehicle page responds 200", veh_resp.status_code == 200, str(veh_resp.status_code))
check("at least one attach strip present (open-work step or notes)",
      'data-media-attach' in veh_resp.text)

if not BRIDGE_PRESENT:
    print("  [note] cuore.services.media_bridge is not built yet -- every "
        "check above ran against this module's own fixture store, which is "
        "process-lifetime only. Nothing here needs to change once the real "
        "bridge lands; list_media()/save_media() just stop falling through "
        "to it.")


# ===========================================================================
# 2. a real server, screenshotted at 400px, with a horizontal-overflow check
# ===========================================================================

print("=== screenshot + overflow at 400px ===")


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


edge = find_edge()
server_dir = tempfile.mkdtemp(prefix="cuore-check-media-server-")
port = free_port()
env = dict(os.environ)
env["CUORE_STATE_DIR"] = server_dir

_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
from cuore.web import media_routes
import uvicorn

app = create_app()
if not any(getattr(r, "path", "").startswith("/v/{{vin}}/media") for r in app.routes):
    app.include_router(media_routes.router)
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
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-media-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,900",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}/media"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    time.sleep(1.5)  # cold-cache first request: real MES-corpus workup
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 900, "deviceScaleFactor": 1, "mobile": True,
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
                    check("no horizontal overflow at 400px", sw <= cw + 1,
                         f"scrollWidth={sw} clientWidth={cw}")

                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    out_path = SCRATCHPAD / "media_400.png"
                    shot = cdp.send("Page.captureScreenshot",
                                   {"format": "png", "captureBeyondViewport": False})
                    out_path.write_bytes(base64.b64decode(shot["data"]))
                    check("screenshot media_400.png captured",
                         out_path.exists() and out_path.stat().st_size > 0, str(out_path))
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
