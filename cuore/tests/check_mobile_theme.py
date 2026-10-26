"""Mobile layer, both OS colour-scheme preferences (2026-10-14 follow-up to
c50f90d, the CSS comment-closing typo that silently dropped the whole
foundation :root block under the default/dark path).

m_base.html pins every ``/m/{vin}...`` page to ``data-theme="dark"`` on
<html> precisely so the phone's own system theme never matters -- that
attribute defeats cuore.css's ``@media (prefers-color-scheme: light)``
block (guarded ``:not([data-theme="dark"])``), so the mobile layer only
ever reads the bare, unguarded ``:root`` block. That is exactly the block
c50f90d's one-character fix restored. Before the fix, the bare ``:root``
was dropped by every real CSS parser regardless of the OS preference, so
the mobile layer was broken whether the phone/OS said light OR dark --
hence this check drives headless Edge under BOTH emulated
``prefers-color-scheme`` values and expects IDENTICAL results each time
(data-theme="dark" should make the OS preference invisible to this layer).

Own throwaway server + CUORE_STATE_DIR (seeded with a read-only copy of the
real 2026-10-13 observation lines, same posture as check_owner_page.py's
own fixture copy -- the real file is only ever read). No COM3. Headless
Edge at 390x844, <=6 screenshots total, cleaned up via _edge_cleanup.py.

Routes checked: /m/{vin}, /m/{vin}/add/fuel/fill_up, /m/{vin}/messages,
/m/{vin}/history, /m/{vin}/print, /m/{vin}/snap.

Run:
    .venv/Scripts/python.exe cuore/tests/check_mobile_theme.py
"""

from __future__ import annotations

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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-mobile-theme-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- 1. seed this server's own state dir with a read-only copy of the real
# 2026-10-13 observation lines (gives /messages real EVAP/network prompts,
# /history and /print something to show) --------------------------------

_REAL_OBSERVATIONS = Path(r"C:\ProgramData\cuore\observations.jsonl")
SERVER_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-mobile-theme-server-"))

_copied = 0
if _REAL_OBSERVATIONS.exists():
    lines_2026_10_13 = [
        ln for ln in _REAL_OBSERVATIONS.read_text(encoding="utf-8").splitlines()
        if ln.strip() and json.loads(ln).get("at", "").startswith("2026-10-13")
    ]
    (SERVER_DIR / "observations.jsonl").write_text(
        "\n".join(lines_2026_10_13) + ("\n" if lines_2026_10_13 else ""), encoding="utf-8")
    _copied = len(lines_2026_10_13)
check("seeded the server's observations.jsonl from the real 2026-10-13 lines "
      "(read-only copy; the real file was never opened for writing)",
      _copied > 0, f"copied {_copied} lines")


# --- 2. start the real app on a free port, own CUORE_STATE_DIR -------------

def free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_port(port: int, timeout: float = 60.0) -> bool:
    """Wait until the server answers /api/health (create_app can take many
    seconds under load; the port only opens after it returns)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001 -- not up yet
            time.sleep(0.3)
    return False


PORT = free_port()
_env = dict(os.environ)
_env["CUORE_STATE_DIR"] = str(SERVER_DIR)

_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
import uvicorn

app = create_app()
uvicorn.run(app, host="127.0.0.1", port={PORT}, log_level="warning")
"""

server_proc = subprocess.Popen(
    [sys.executable, "-c", _SERVER_SNIPPET],
    cwd=str(ROOT), env=_env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)


def _cleanup_server() -> None:
    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except Exception:
        server_proc.kill()


up = wait_for_port(PORT)
check("the throwaway app server came up", up, f"port {PORT}")
if not up:
    _cleanup_server()
    print(f"{checks} checks, {len(failures)} failures")
    for f in failures:
        print(" -", f)
    sys.exit(1)


def post(path: str, data: dict) -> None:
    body = urllib.parse.urlencode(data).encode()
    urllib.request.urlopen(
        urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=body, method="POST"),
        timeout=15)


try:
    # a fill-up (gives /history, /print, the fill-up form's prefill something
    # real) and an oil change (gives /print a printable-label record too)
    post(f"/m/{VIN}/add/fuel/fill_up",
         {"station": "Petro-Canada", "octane": "91", "litres": "42", "price": "60"})
    post(f"/m/{VIN}/add/fluids/engine_oil_change",
         {"brand": "Selenia", "viscosity": "5W-30", "qty": "4.5"})
    check("seeded a fill-up and an oil-change owner event", True)
except Exception as exc:  # noqa: BLE001
    check("seeding owner events on the throwaway server", False, f"{type(exc).__name__}: {exc}")


# --- 3. headless Edge, 390x844, both prefers-color-scheme values -----------

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_edge() -> str:
    for c in EDGE_CANDIDATES:
        if Path(c).exists():
            return c
    return ""


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
        raise TimeoutError(f"CDP {method} timed out")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for_devtools(port: int, timeout: float = 20) -> None:
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
    raise RuntimeError(f"headless Edge devtools never came up: {last_err}")


def open_target(port: int, url: str) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def evaljs(cdp: CDP, expr: str):
    r = cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    if "exceptionDetails" in r:
        raise RuntimeError(r["exceptionDetails"])
    return r.get("result", {}).get("value")


ROUTES = {
    "home": f"/m/{VIN}",
    "fillup": f"/m/{VIN}/add/fuel/fill_up",
    "messages": f"/m/{VIN}/messages",
    "history": f"/m/{VIN}/history",
    "print": f"/m/{VIN}/print",
    "snap": f"/m/{VIN}/snap",
}

# Budget: <=6 screenshots total. One screenshot per route, alternating which
# theme pass takes it, so both themes are represented across the set.
SHOT_THEME = {"home": "dark", "fillup": "light", "messages": "dark",
              "history": "light", "print": "dark", "snap": "light"}

SCRATCH = Path(os.environ.get(
    "CUORE_MOBILE_THEME_SHOTS",
    r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User\7cb02eb5-e299-4baf-b34b-9eb82aebbf17"
    r"\scratchpad\mobile-theme-shots"))
SCRATCH.mkdir(parents=True, exist_ok=True)

edge = find_edge()
results: dict[str, dict] = {}
shots_taken: list[str] = []

if not edge:
    check("headless Edge is available", False, str(EDGE_CANDIDATES))
else:
    devtools_port = free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-mobile-theme-"))
    edge_proc = subprocess.Popen(
        [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
         f"--user-data-dir={profile_dir}", "--no-first-run",
         "--window-size=390,844", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_devtools(devtools_port)
        for scheme in ("dark", "light"):
            for key, route in ROUTES.items():
                url = f"http://127.0.0.1:{PORT}{route}"
                target = open_target(devtools_port, "about:blank")
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True,
                    })
                    cdp.send("Emulation.setEmulatedMedia", {
                        "features": [{"name": "prefers-color-scheme", "value": scheme}],
                    })
                    # Explicit navigate + poll, rather than relying on
                    # /json/new?url's own pre-connect navigation (which can
                    # race the CDP websocket connect and leave the tab on
                    # about:blank with the device-metrics override never
                    # having applied to the real document).
                    cdp.send("Page.navigate", {"url": url})
                    ready = None
                    for _ in range(40):
                        time.sleep(0.25)
                        try:
                            ready = evaljs(cdp, "document.readyState")
                        except Exception:  # noqa: BLE001
                            continue
                        if ready == "complete" and evaljs(cdp, "location.href") == url:
                            break
                    check(f"{key} ({scheme}) loaded", ready == "complete", str(ready))
                    check(f"{key} ({scheme}) landed on the right URL",
                          evaljs(cdp, "location.href") == url, evaljs(cdp, "location.href"))

                    data = json.loads(evaljs(cdp, """
JSON.stringify((function(){
  var b = document.body;
  var bodyBg = getComputedStyle(b).backgroundColor;
  var hero = document.querySelector('.m-hero-name');
  var chipSpan = document.querySelector('.m-chip span, .m-label, .m-section-h');
  var intro = document.querySelector('.intro-overlay');
  var introToggle = document.getElementById('intro-dismiss');
  var targets = Array.from(document.querySelectorAll(
    '.m-chip, .m-submit, .m-ghost-btn, .m-delete-btn, .m-undo-btn, .m-print-btn, .m-bottomnav a'
  )).map(function(e){ var r = e.getBoundingClientRect(); return r.height; });
  return {
    bodyBg: bodyBg,
    colorScheme: getComputedStyle(document.documentElement).colorScheme,
    heroWeight: hero ? getComputedStyle(hero).fontWeight : null,
    heroText: hero ? hero.textContent : null,
    chipFontSize: chipSpan ? getComputedStyle(chipSpan).fontSize : null,
    introPresent: !!intro,
    introToggleChecked: introToggle ? introToggle.checked : null,
    minTargetHeight: targets.length ? Math.min.apply(null, targets) : null,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  };
})())
""")) or {}
                    results[f"{key}:{scheme}"] = data

                    check(f"{key} ({scheme}): body background is true black (rgb(0, 0, 0))",
                          data.get("bodyBg") == "rgb(0, 0, 0)", str(data.get("bodyBg")))
                    check(f"{key} ({scheme}): no horizontal overflow at 390px",
                          (data.get("scrollWidth") or 0) <= (data.get("clientWidth") or 0) + 1,
                          f"sw={data.get('scrollWidth')} cw={data.get('clientWidth')}")
                    if data.get("chipFontSize") is not None:
                        px = float(str(data["chipFontSize"]).replace("px", ""))
                        check(f"{key} ({scheme}): chip/label text is >= 12px",
                              px >= 12, f"{px}px")
                    if data.get("minTargetHeight") is not None:
                        check(f"{key} ({scheme}): every measured tap target is >= 48px tall",
                              data["minTargetHeight"] >= 48, f"{data['minTargetHeight']}px")
                    if key == "home":
                        check(f"home ({scheme}): intro overlay is present on first load",
                              data.get("introPresent") is True, str(data))
                        check(f"home ({scheme}): intro's dismiss checkbox starts unchecked",
                              data.get("introToggleChecked") is False, str(data))

                        # Dismiss on first tap: click the centre of the overlay
                        # (a <label for="intro-dismiss">) and confirm it hides.
                        box = cdp.send("Runtime.evaluate", {
                            "expression": ("JSON.stringify((function(){var r=document.querySelector"
                                           "('.intro-overlay').getBoundingClientRect();"
                                           "return {x:r.x+r.width/2,y:r.y+r.height/2};})())"),
                            "returnByValue": True,
                        })
                        pt = json.loads(box.get("result", {}).get("value", "{}"))
                        cdp.send("Input.dispatchMouseEvent", {
                            "type": "mousePressed", "x": pt.get("x", 195), "y": pt.get("y", 100),
                            "button": "left", "clickCount": 1})
                        cdp.send("Input.dispatchMouseEvent", {
                            "type": "mouseReleased", "x": pt.get("x", 195), "y": pt.get("y", 100),
                            "button": "left", "clickCount": 1})
                        time.sleep(0.2)
                        dismissed = evaljs(cdp, "document.getElementById('intro-dismiss').checked")
                        check(f"home ({scheme}): intro overlay is dismissable on first tap",
                              dismissed is True, str(dismissed))

                    if SHOT_THEME.get(key) == scheme and len(shots_taken) < 6:
                        shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                        png_bytes = __import__("base64").b64decode(shot["data"])
                        out_path = SCRATCH / f"{key}_{scheme}.png"
                        out_path.write_bytes(png_bytes)
                        shots_taken.append(str(out_path))
                finally:
                    cdp.close()
    except Exception as exc:  # noqa: BLE001
        check("headless Edge measured the mobile pages over CDP", False,
              f"{type(exc).__name__}: {exc}")
    finally:
        edge_proc.terminate()
        try:
            edge_proc.wait(timeout=5)
        except Exception:
            edge_proc.kill()
        from _edge_cleanup import kill_edge_profile
        kill_edge_profile(profile_dir)


# --- 4. the two themes must agree (data-theme="dark" makes the OS setting
# invisible to this layer) ---------------------------------------------------

for key in ROUTES:
    d, l = results.get(f"{key}:dark"), results.get(f"{key}:light")
    if d and l:
        check(f"{key}: body background identical under both OS themes "
              "(data-theme=dark pins the mobile layer)",
              d.get("bodyBg") == l.get("bodyBg"),
              f"dark={d.get('bodyBg')} light={l.get('bodyBg')}")
        check(f"{key}: color-scheme resolves to 'dark' regardless of the OS preference",
              d.get("colorScheme") == "dark" and l.get("colorScheme") == "dark",
              f"dark-pass={d.get('colorScheme')} light-pass={l.get('colorScheme')}")

_cleanup_server()

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(" -", f)
print("screenshots:")
for s in shots_taken:
    print(" -", s)
print("measured hero font-weight (home, dark pass):",
      results.get("home:dark", {}).get("heroWeight"))
if failures:
    sys.exit(1)
