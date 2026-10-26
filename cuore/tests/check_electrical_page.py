"""Checks for the electrical layout diagram (``/v/{vin}/electrical``) and
the path stepper it shares with ``code.html``/``report.html``.

Same posture as ``cuore/tests/check_timeline_page.py`` (CDP/screenshot
plumbing copied from there): ``CUORE_STATE_DIR`` points at a throwaway
directory before cuore is imported, and ``cuore/web/electrical_routes.py``
is not wired into ``cuore/app.py`` (another agent owns that file), so
``_app_with_router()`` includes it itself if ``create_app()`` did not
already pick it up.

``cuore.services.electrical_bridge`` is being built in parallel and may not
exist yet -- ``electrical_routes`` falls back to its own fixture in that
case, so every check below runs either way.

Run:
    .venv/Scripts/python.exe cuore/tests/check_electrical_page.py
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

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-electrical-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import electrical_routes  # noqa: E402

from websockets.sync.client import connect  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus
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
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def _app_with_router():
    app = create_app()
    already = any(getattr(r, "path", "").startswith("/v/{vin}/electrical") for r in app.routes)
    if not already:
        app.include_router(electrical_routes.router)
    return app


client = TestClient(_app_with_router())

# 1. electrical page 200, with the svg and the legend ------------------------
page = client.get(f"/v/{VIN}/electrical")
check("electrical page responds 200", page.status_code == 200, str(page.status_code))
check("page has an inline SVG with the legend's 'never inspected' entry",
      "<svg" in page.text and "never inspected" in page.text)
check("page shows element cards", 'class="elec-card"' in page.text or "elec-cards" in page.text)

# 2. ?code=P0455 highlights the path (path class present) -------------------
hl = client.get(f"/v/{VIN}/electrical?code=P0455")
check("?code=P0455 responds 200", hl.status_code == 200, str(hl.status_code))
check("highlighted page carries the path-hop class", 'class="path-hop"' in hl.text)

# 3. inspection POST round trip shows the condition --------------------------
post = client.post(f"/v/{VIN}/electrical/inspect", data={
    "element": "purge_valve", "by": "check_electrical_page.py", "condition": "corroded",
    "note": "smoke test", "redirect_to": f"/v/{VIN}/electrical",
}, follow_redirects=False)
check("inspection POST redirects (303)", post.status_code == 303, str(post.status_code))
follow = client.get(post.headers.get("location", f"/v/{VIN}/electrical"))
check("the recorded condition appears back on the page", "Corroded" in follow.text)

# 4. code page shows the path stepper ----------------------------------------
code_resp = client.get(f"/v/{VIN}/code/P0455")
check("code page shows the electrical path stepper",
      code_resp.status_code == 200 and 'class="elec-stepper"' in code_resp.text,
      str(code_resp.status_code))

# 5. system filter + cross-system code paths (layout_bridge) ----------------
from cuore.services import layout_bridge  # noqa: E402

try:
    from mes import layout_systems as _layout_systems_mod  # noqa: E402
except Exception:  # noqa: BLE001
    _layout_systems_mod = None

all_resp = client.get(f"/v/{VIN}/electrical")
evap_resp = client.get(f"/v/{VIN}/electrical?system=evap")
check("?system=evap shows only EVAP elements",
      evap_resp.status_code == 200 and "Wheel speed" not in evap_resp.text
      and "Fuse F23" not in evap_resp.text and "EVAP" in evap_resp.text)

p0455_resp = client.get(f"/v/{VIN}/electrical?code=P0455")
if _layout_systems_mod is not None:
    check("?code=P0455 highlights canister and ESIM (mes.layout_systems path)",
          "canister" in p0455_resp.text.lower() and "ESIM" in p0455_resp.text)
else:
    # mes.layout_systems hasn't landed -- electrical_bridge's own
    # mes.electrical path is the fallback and already names the ESIM
    # connector (co-located with the canister per TSB 9100469/9100471).
    check("?code=P0455 highlights the ESIM path (electrical-only fallback)",
          "ESIM" in p0455_resp.text or "purge" in p0455_resp.text.lower())

p0171_resp = client.get(f"/v/{VIN}/electrical?code=P0171")
check("?code=P0171 path spans air and fuel",
      p0171_resp.status_code == 200
      and ("Air &amp; boost" in p0171_resp.text or "air_boost" in p0171_resp.text
           or "Air intake" in p0171_resp.text or "MAP sensor" in p0171_resp.text)
      and "Fuel" in p0171_resp.text)

all_systems_present = {e.get("system") for e in layout_bridge.elements().values()}
check("All view renders every system's elements",
      all_resp.status_code == 200
      and len(all_systems_present & layout_bridge.SYSTEM_KEYS) >= 8,
      str(sorted(all_systems_present)))


# --- nine-feature additions: safety, guided walk-through, module status, ----
# --- history/repaired, parts, photos, tablet/zoom, find, junior/expert ------
import re as _re  # noqa: E402

from cuore.services import electrical_extras, electrical_safety  # noqa: E402
from cuore.web import electrical_svg  # noqa: E402

STATE = Path(os.environ["CUORE_STATE_DIR"])
base_page = client.get(f"/v/{VIN}/electrical")

# 7. safety flags (rule table + badge + box) --------------------------------
srs = electrical_safety.flags_for({"label": "ORC -- Occupant Restraint Controller", "kind": "module"}, "orc_module")
check("safety rule table flags an SRS element with the generic wording",
      srs and srs[0]["key"] == "srs" and "Never probe SRS connectors with a test light" in srs[0]["text"])
check("safety rules: battery -> high current, fuel pump -> fuel, plain sensor -> none",
      electrical_safety.flags_for({"label": "12V battery", "kind": "battery"}, "battery")[0]["key"] == "high_current"
      and electrical_safety.flags_for({"label": "Fuel pump", "kind": "pump", "system": "fuel"}, "fuel_pump")[0]["key"] == "fuel"
      and not electrical_safety.flags_for({"label": "MAP sensor", "kind": "sensor"}, "map_sensor"))
check("page draws the safety triangle on nodes and a warning box on cards",
      "glyph-safety" in base_page.text and 'class="elec-safety"' in base_page.text)

# 8. guided walk-through ------------------------------------------------------
st1 = client.get(f"/v/{VIN}/electrical?code=P0455&step=1")
check("?step=1 shows 'Step 1 of N' with Next but no Prev",
      st1.status_code == 200 and _re.search(r"Step 1 of \d+", st1.text) and "Next &rarr;" in st1.text
      and "&larr; Prev" not in st1.text)
check("step mode highlights the current node and carries the inline inspection form",
      "step-current" in st1.text and 'id="st_' in st1.text and 'id="elec-step"' in st1.text)
stN = client.get(f"/v/{VIN}/electrical?code=P0455&step=99")
m = _re.search(r"Step (\d+) of (\d+)", stN.text)
check("an out-of-range step clamps to the last step", bool(m) and m.group(1) == m.group(2) and "Finish" in stN.text)
check("no 'Expected:' line is invented when the element data has no expected value",
      "Expected:" not in st1.text and electrical_routes._first({}, keys=electrical_routes._EXPECTED_KEYS) is None
      and electrical_routes._first({"expected_value": "12.6 V"}, keys=electrical_routes._EXPECTED_KEYS) == "12.6 V")
step_el = _re.search(r'id="st_([A-Za-z0-9_]+?)_(?:ok|loose)"', st1.text)
step_post = client.post(f"/v/{VIN}/electrical/inspect", data={
    "element": step_el.group(1) if step_el else "purge_valve", "by": "check", "condition": "corroded",
    "note": "", "redirect_to": f"/v/{VIN}/electrical?code=P0455&step=1"}, follow_redirects=False)
after = client.get(step_post.headers.get("location", ""))
check("a reading saved in the step shows as a failed step (cross + 'fail')",
      "&#10007; fail" in after.text and "step-mark" in after.text)

# 9. module status from persisted data only -----------------------------------
check("modules with no persisted scan read as not checked (grey dashed ring)",
      "mod-unchecked" in base_page.text and "mod-answered" not in base_page.text)
(STATE / "fullscan_last.json").write_text(json.dumps({"scan_id": "SCAN_X", "coverage": [
    {"bus": "can_c", "module": "ECM", "category": "answered", "why": None},
    {"bus": "can_c", "module": "BCM", "category": "silent", "why": "no reply"},
    {"bus": "can_c", "module": "TCM", "category": "not_reachable", "why": "needs cable"}]}), encoding="utf-8")
mod_page = client.get(f"/v/{VIN}/electrical")
check("module nodes show answered (green) and silent (red) rings with a last-scan time in the tooltip",
      "mod-answered" in mod_page.text and "mod-silent" in mod_page.text and "last scan 20" in mod_page.text)

# 10. repaired-before + history -----------------------------------------------
import mes.jobs as _jobs  # noqa: E402
_orig_load = _jobs.load
_jobs.load = lambda vin="": [{"actions": [
    {"kind": "repair", "text": "Replaced Starter motor, new part fitted", "at": "2026-09-01T10:00:00"},
    {"kind": "repair", "text": "ECM reset after oil change", "at": "2026-09-02T10:00:00"},
    {"kind": "note", "text": "Alternator looked fine", "at": "2026-09-03T10:00:00"}]}]
try:
    rep_page = client.get(f"/v/{VIN}/electrical")
    rep = electrical_extras.repaired_index(VIN, {"starter_motor": {"label": "Starter motor"},
                                                  "ecm": {"label": "ECM -- Engine"},
                                                  "alternator": {"label": "Alternator"}})
finally:
    _jobs.load = _orig_load
check("repaired-before matches a repair action naming the part, not a short id or a mere note",
      set(rep) == {"starter_motor"} and "glyph-repaired" in rep_page.text and "repaired before" in rep_page.text)
check("each inspected card lists its inspection history",
      "Inspection history (" in after.text or "Inspection history (" in follow.text)

# 11. part numbers --------------------------------------------------------------
check("every element card links into the catalogue search", "/catalog?q=" in base_page.text)
from cuore.services import parts_catalog as _pc  # noqa: E402
_orig_pc_load = _pc.load
_fake = {"diagrams": {"d1": {"title": "Fuel", "section": "S", "group": "G", "image": "", "parts": [
    {"pn": "123ABC", "name": "Fuel Injector", "description": "", "notes": ""}]}}, "_by_pn": {"123ABC": [("d1", 0)]}}
_pc.load = lambda cid=None: _fake
try:
    hit = electrical_extras.part_hits("Fuel Injector")
    miss = electrical_extras.part_hits("Unobtainium widget")
finally:
    _pc.load = _orig_pc_load
check("catalogue hits give real part numbers; no match gives none (nothing fabricated)",
      [h["pn"] for h in hit] == ["123ABC"] and miss == [])

# 12. photo pins ------------------------------------------------------------------
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
ph = client.post(f"/v/{VIN}/electrical/photo", data={"element": "battery", "redirect_to": f"/v/{VIN}/electrical"},
                 files={"photo": ("../we ird?.png", PNG, "image/png")}, follow_redirects=False)
check("a PNG photo uploads (303 with photo=1)", ph.status_code == 303 and "photo=1" in ph.headers.get("location", ""),
      ph.headers.get("location", ""))
bad = client.post(f"/v/{VIN}/electrical/photo", data={"element": "battery"},
                  files={"photo": ("x.png", b"not an image at all", "image/png")}, follow_redirects=False)
big = client.post(f"/v/{VIN}/electrical/photo", data={"element": "battery"},
                  files={"photo": ("x.png", PNG + b"\0" * (15 * 1024 * 1024 + 1), "image/png")}, follow_redirects=False)
check("a non-image and an over-15 MB file are rejected",
      "error=" in bad.headers.get("location", "") and "too%20large" in big.headers.get("location", ""),
      bad.headers.get("location", "") + " | " + big.headers.get("location", ""))
photo_page = client.get(f"/v/{VIN}/electrical")
check("the photo shows as a thumbnail on the card and a camera glyph on the node",
      "glyph-photo" in photo_page.text and "/api/media/" in photo_page.text
      and 'accept="image/*"' in photo_page.text and 'capture="environment"' in photo_page.text)

# 13. tablet mode, zoom, clipping ------------------------------------------------
css = (ROOT / "cuore" / "web" / "static" / "electrical.css").read_text(encoding="utf-8")
js = (ROOT / "cuore" / "web" / "static" / "electrical.js").read_text(encoding="utf-8")
check("zoom tools, script and 44px touch targets are present",
      "elec-zoom-tools" in base_page.text and "electrical.js" in base_page.text
      and "min-height: 44px" in css and "pointerdown" in js and "http" not in js.replace("https://developer", ""))
els_right = {"w1": {"kind": "sensor", "label": "Wheel speed sensor FR", "system": "chassis",
                    "location": {"zone": "wheel_fr"}}}
svg_r = electrical_svg.render(els_right, conditions={})
xs = [float(v) for v in _re.findall(r'<circle cx="([\d.]+)"', svg_r)]
legend = [(float(x), t) for x, t in _re.findall(r'<text x="([\d.]+)" y="[\d.]+" font-size="10"[^>]*>([^<]+)</text>', svg_r)]
check("right-hand wheel-well nodes and legend text stay inside the 420 viewBox",
      max(xs) + electrical_svg.NODE_R <= 420 and all(x + 5.6 * len(t) <= 420 for x, t in legend),
      f"max cx {max(xs)}; legend {[(x, len(t)) for x, t in legend]}")

# 14. find on car, junior/expert, legend ------------------------------------------------
fd = client.get(f"/v/{VIN}/electrical?find=battery")
check("?find= pulses matching nodes and cards server-side without JavaScript",
      'class="el-node el-match"' in fd.text and "elec-card el-match" in fd.text and 'data-search="' in fd.text)
check("find box, junior/expert toggle (default junior) and reduced-motion rule exist",
      'id="elec-find-input"' in base_page.text and 'data-mode="junior"' in base_page.text
      and 'id="elec-mode"' in base_page.text and "prefers-reduced-motion" in css
      and "localStorage" in js and "try {" in js)
check("legend explains every glyph",
      all(w in base_page.text for w in ("warning triangle", "wrench", "camera", "dashed grey ring",
                                        "green ring", "red ring", "tick or cross")))


# companion: check_api.py must still pass -------------------------------------
proc = subprocess.run([sys.executable, str(Path(__file__).parent / "check_api.py")],
                      cwd=str(ROOT), capture_output=True, text=True,
                      encoding="utf-8", errors="replace")
check("check_api.py exits 0", proc.returncode == 0,
     ((proc.stdout or "")[-1200:] + (proc.stderr or "")[-800:]) if proc.returncode else "")


# 6. no horizontal overflow at 400px, one screenshot -------------------------

def find_edge() -> str:
    for c in EDGE_CANDIDATES:
        if Path(c).exists():
            return c
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
server_dir = tempfile.mkdtemp(prefix="cuore-check-electrical-server-")
port = free_port()
env = dict(os.environ)
env["CUORE_STATE_DIR"] = server_dir

_SERVER_SNIPPET = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from cuore.app import create_app
from cuore.web import electrical_routes
import uvicorn

app = create_app()
if not any(getattr(r, "path", "").startswith("/v/{{vin}}/electrical") for r in app.routes):
    app.include_router(electrical_routes.router)
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
"""

if not edge:
    check("headless Edge is available for the screenshot", False, str(EDGE_CANDIDATES))
else:
    server_proc = subprocess.Popen(
        [sys.executable, "-c", _SERVER_SNIPPET], cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        up = wait_for_port(port)
        check("uvicorn came up on the free port", up, f"port {port}")
        if up:
            time.sleep(0.5)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-electrical-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run", "--window-size=400,1200",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)
                url = f"http://127.0.0.1:{port}/v/{VIN}/electrical"
                target = open_target(devtools_port, url)
                cdp = CDP(target["webSocketDebuggerUrl"])
                try:
                    cdp.send("Page.enable")
                    cdp.send("Runtime.enable")
                    time.sleep(1.5)
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 1200, "deviceScaleFactor": 1, "mobile": True,
                    })
                    time.sleep(0.6)
                    overflow = cdp.send("Runtime.evaluate", {
                        "expression": ("JSON.stringify({sw: document.documentElement.scrollWidth, "
                                      "cw: document.documentElement.clientWidth})"),
                        "returnByValue": True,
                    })
                    dims = json.loads(overflow.get("result", {}).get("value", "{}"))
                    sw, cw = dims.get("sw", 0), dims.get("cw", 0)
                    check("no page-level horizontal overflow at 400px", sw <= cw + 1,
                         f"scrollWidth={sw} clientWidth={cw}")

                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    out_path = SCRATCHPAD / "electrical_phone.png"
                    shot = cdp.send("Page.captureScreenshot",
                                   {"format": "png", "captureBeyondViewport": False})
                    out_path.write_bytes(base64.b64decode(shot["data"]))
                    check("screenshot captured", out_path.exists() and out_path.stat().st_size > 0,
                         str(out_path))
                    if out_path.exists():
                        print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge captured the screenshot over CDP", False,
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
            server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait(timeout=10)


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"{checks}/{checks} checks passed")
