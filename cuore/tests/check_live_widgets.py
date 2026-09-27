"""Headless-browser check for the CuoreWidgets library.

Loads cuore/web/static/live/widgets_test.html in headless Edge, which builds
every widget type, pushes synthetic data at it (nulls, out-of-band values, a
2,000-sample burst), and writes a {"passed": N, "failed": [...]} JSON blob
into <pre id="result">. This script reads that back and prints
"N/N checks passed", exiting 1 if anything failed.

It also captures a screenshot of the demo layout (all 11 widget types) for a
manual visual check -- pass --screenshot to control where it lands; it
defaults to the system temp dir, not the repo.

Implementation note: this drives Edge over the Chrome DevTools Protocol
(remote debugging websocket) rather than the `--dump-dom`/`--screenshot`
CLI flags. On this machine `--dump-dom`'s stdout never reaches the
launching process (Edge detaches into a background target), and
`--screenshot` only works when `--disable-gpu` is *not* also passed
(with it, Edge fails with "Multiple targets are not supported in headless
mode"). CDP sidesteps both: it reads the DOM and takes the screenshot
in-process over the debugger websocket, which is reliable regardless of
those quirks.

Usage:
    .venv\\Scripts\\python.exe cuore/tests/check_live_widgets.py
    .venv\\Scripts\\python.exe cuore/tests/check_live_widgets.py --screenshot C:\\path\\to\\shot.png
"""

import argparse
import base64
import itertools
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_HTML = REPO_ROOT / "cuore" / "web" / "static" / "live" / "widgets_test.html"


def find_edge():
    for candidate in EDGE_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            return str(p)
    print("ERROR: could not find msedge.exe in known locations", file=sys.stderr)
    sys.exit(2)


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class CDP:
    """Minimal Chrome DevTools Protocol client over one target's websocket."""

    def __init__(self, ws_url):
        self.ws = connect(ws_url, max_size=None, open_timeout=20)
        self._ids = itertools.count(1)

    def send(self, method, params=None, timeout=20):
        msg_id = next(self._ids)
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv(timeout=max(0.1, deadline - time.time()))
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError("CDP %s failed: %s" % (method, msg["error"]))
                return msg.get("result", {})
        raise TimeoutError("CDP %s timed out waiting for response" % method)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for_devtools(port, timeout=20):
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2) as r:
                json.loads(r.read().decode("utf-8"))
                return
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    raise RuntimeError("headless Edge devtools endpoint never came up: %s" % last_err)


def open_target(port, url):
    # Recent Chromium/Edge builds require PUT (not GET) on /json/new as a
    # CSRF hardening measure.
    req = urllib.request.Request(
        "http://127.0.0.1:%d/json/new?%s" % (port, url), method="PUT"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", default=None,
                     help="Path to save the demo-layout screenshot (default: a temp file).")
    ap.add_argument("--no-screenshot", action="store_true",
                     help="Skip taking the screenshot.")
    args = ap.parse_args()

    if not TEST_HTML.exists():
        print("ERROR: test file not found: %s" % TEST_HTML, file=sys.stderr)
        sys.exit(2)

    edge = find_edge()
    port = free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-"))
    url = TEST_HTML.resolve().as_uri()

    proc = subprocess.Popen(
        [edge, "--headless=new", "--remote-debugging-port=%d" % port,
         "--user-data-dir=%s" % profile_dir, "--no-first-run", "--window-size=1400,1800",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    exit_code = 1
    try:
        wait_for_devtools(port)
        target = open_target(port, url)
        cdp = CDP(target["webSocketDebuggerUrl"])
        try:
            cdp.send("Page.enable")
            cdp.send("Runtime.enable")

            # The test script runs synchronously on load and writes into
            # #result before returning, but poll a little in case a future
            # edit makes it async.
            result = None
            deadline = time.time() + 15
            while time.time() < deadline:
                out = cdp.send("Runtime.evaluate", {
                    "expression": "document.getElementById('result') ? document.getElementById('result').textContent : null",
                    "returnByValue": True,
                })
                text = out.get("result", {}).get("value")
                if text and text.strip() and text.strip() != "running...":
                    try:
                        result = json.loads(text)
                        break
                    except json.JSONDecodeError:
                        pass
                time.sleep(0.25)

            if result is None:
                print("ERROR: test script in widgets_test.html never produced a result", file=sys.stderr)
                sys.exit(1)

            passed = result.get("passed", 0)
            failed = result.get("failed", [])
            total = passed + len(failed)

            if failed:
                print("Failures:")
                for f in failed:
                    print("  - " + f)

            print("%d/%d checks passed" % (passed, total))
            exit_code = 0 if not failed else 1

            if not args.no_screenshot:
                shot_path = Path(args.screenshot) if args.screenshot else Path(tempfile.gettempdir()) / "cuore_widgets_demo.png"
                try:
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 1400, "height": 1800, "deviceScaleFactor": 1, "mobile": False,
                    })
                    shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                    shot_path.parent.mkdir(parents=True, exist_ok=True)
                    shot_path.write_bytes(base64.b64decode(shot["data"]))
                    print("Screenshot: %s" % shot_path)
                except Exception as e:
                    print("WARNING: screenshot failed: %s" % e, file=sys.stderr)
        finally:
            cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        from _edge_cleanup import kill_edge_profile
        kill_edge_profile(profile_dir)  # Edge detaches; terminate() alone leaks it
        shutil.rmtree(profile_dir, ignore_errors=True)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
