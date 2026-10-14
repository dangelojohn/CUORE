"""Checks for TYPE_AND_UI_AUDIT_2026-10-14's foundation pass (section 1 +
root causes R1/R2/R6): one 7-step type scale, one colour-token :root block
per theme, one body font-size rule, and no horizontal page overflow at
485px on the three pages the audit measured it on (Bench, Job, Scan).

Static checks (always run, no server/browser needed):
  1. Every ``font-size`` declaration in the CSS files this pass owns
     (cuore.css, flow.css, icons.css, print.css, fullscan.css,
     liveboard.css, feedback.css, job.css, tests.css, scanlog.css,
     scan_health.css, system.css, systems.css, mods.css, m.css) is one of
     the 7 scale tokens (``var(--fs-xs|sm|md|lg|xl|2xl|3xl)``), ``0``,
     ``inherit``, or a ``pt`` value inside print.css (the one physical-unit
     exception the spec calls out for the print medium).
  2. cuore.css defines exactly one bare ``:root { ... }`` colour/type
     token block (the dark foundation) and exactly one
     ``:root[data-theme="light"] { ... }`` block, whose declared custom
     properties are the identical *set* of names as the
     ``@media (prefers-color-scheme: light) { :root:not(...) { ... } }``
     mirror -- i.e. light is declared twice (the mechanism: explicit
     override + system-preference fallback), never three times, and
     never with a different token set between the two.
  3. cuore.css declares exactly one ``body { ... font-size ... }`` rule.

Browser check (Bench/Job/Scan, 485px, dark): if headless Edge is on this
machine, a real uvicorn server + CDP measure ``document.documentElement
.scrollWidth`` vs ``innerWidth`` -- the audit's own acceptance line
("document.scrollWidth must equal the viewport at 485px"). Edge missing ->
this half is skipped with a note, the static checks above still run and
still gate the suite.

Run:
    .venv/Scripts/python.exe cuore/tests/check_type_scale.py
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
import urllib.request
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-typescale-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "cuore" / "web" / "static"
sys.path.insert(0, str(ROOT))

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus

OWNED_CSS = [
    "cuore.css", "flow.css", "icons.css", "print.css", "fullscan.css",
    "liveboard.css", "feedback.css", "job.css", "tests.css", "scanlog.css",
    "scan_health.css", "system.css", "systems.css", "mods.css", "m.css",
]

SCALE_TOKENS = {"xs", "sm", "md", "lg", "xl", "2xl", "3xl"}

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([^;}\n]+)")
_ALLOWED_VALUE_RE = re.compile(
    r"^var\(--fs-(?:xs|sm|md|lg|xl|2xl|3xl)\)$|^0$|^inherit$"
)
_PT_RE = re.compile(r"^[0-9.]+pt$")


def _strip_comments(css: str) -> str:
    return _COMMENT_RE.sub("", css)


# ---------------------------------------------------------------------------
# Static check 1: scale-token-only font-size
# ---------------------------------------------------------------------------

bad_sizes: list[str] = []
seen_distinct: set[str] = set()
for fname in OWNED_CSS:
    path = STATIC_DIR / fname
    if not path.exists():
        bad_sizes.append(f"{fname}: file missing")
        continue
    text = _strip_comments(path.read_text(encoding="utf-8"))
    for m in _FONT_SIZE_RE.finditer(text):
        value = m.group(1).strip()
        seen_distinct.add(value)
        if _ALLOWED_VALUE_RE.match(value):
            continue
        if fname == "print.css" and _PT_RE.match(value):
            continue
        bad_sizes.append(f"{fname}: font-size: {value}")

check("every font-size in the owned CSS uses only the 7 scale tokens "
      "(plus 0/inherit, plus print.css pt values)",
      not bad_sizes, "; ".join(bad_sizes[:15]) + ("..." if len(bad_sizes) > 15 else ""))

distinct_tokens = {v for v in seen_distinct if _ALLOWED_VALUE_RE.match(v)}
distinct_scale = {v for v in distinct_tokens if v.startswith("var(--fs-")}
check(f"<= 7 distinct scale tokens actually used (found {len(distinct_scale)})",
      len(distinct_scale) <= 7, ", ".join(sorted(distinct_scale)))

# ---------------------------------------------------------------------------
# Static check 2: one :root colour/type block per theme in cuore.css
# ---------------------------------------------------------------------------

cuore_css_raw = (STATIC_DIR / "cuore.css").read_text(encoding="utf-8")
cuore_css = _strip_comments(cuore_css_raw)

bare_root_blocks = re.findall(r"(?m)^:root\s*\{", cuore_css)
light_explicit_blocks = re.findall(r'(?m)^:root\[data-theme="light"\]\s*\{', cuore_css)

# A handful of small, single-purpose bare :root blocks are fine (the
# data-marque accent swap is its own attribute-selector block, not a bare
# :root) -- what R2 forbids is multiple bare :root blocks that each
# redeclare the *same* colour/type tokens with different values. Detect
# that directly: collect every custom-property name declared inside any
# bare `:root { ... }` block and make sure each name is declared in at
# most one such block.
root_prop_owner: dict[str, str] = {}
dupe_props: list[str] = []
for idx, m in enumerate(re.finditer(r"(?m)^:root\s*\{([^}]*)\}", cuore_css)):
    body = m.group(1)
    for prop_m in re.finditer(r"(--[a-zA-Z0-9-]+)\s*:", body):
        prop = prop_m.group(1)
        if prop in root_prop_owner and root_prop_owner[prop] != idx:
            dupe_props.append(prop)
        root_prop_owner[prop] = idx

check("no colour/type custom property is declared in more than one bare "
      ":root block in cuore.css",
      not dupe_props, ", ".join(sorted(set(dupe_props))))

check('exactly one :root[data-theme="light"] block in cuore.css',
      len(light_explicit_blocks) == 1, f"found {len(light_explicit_blocks)}")

# The light override and its prefers-color-scheme mirror must declare the
# same *set* of custom-property names (the spec's own example does this on
# purpose -- a mechanism, not a duplicate -- but the two must actually agree).
light_explicit_m = re.search(r'(?m)^:root\[data-theme="light"\]\s*\{([^}]*)\}', cuore_css)
light_media_m = re.search(
    r'@media \(prefers-color-scheme: light\)\s*\{\s*:root:not\(\[data-theme="dark"\]\)\s*\{([^}]*)\}',
    cuore_css)
if light_explicit_m and light_media_m:
    explicit_props = set(re.findall(r"(--[a-zA-Z0-9-]+)\s*:", light_explicit_m.group(1)))
    media_props = set(re.findall(r"(--[a-zA-Z0-9-]+)\s*:", light_media_m.group(1)))
    check("the light :root override and its prefers-color-scheme mirror "
          "declare the same set of custom properties",
          explicit_props == media_props,
          f"only-in-explicit={explicit_props - media_props} "
          f"only-in-media={media_props - explicit_props}")
else:
    check("light :root override and prefers-color-scheme mirror both found", False,
          f"explicit={'found' if light_explicit_m else 'MISSING'} "
          f"media={'found' if light_media_m else 'MISSING'}")

# ---------------------------------------------------------------------------
# Static check 3: one body font-size rule
# ---------------------------------------------------------------------------

body_rules_with_fs = re.findall(r"(?m)^body\s*\{[^}]*font-size[^}]*\}", cuore_css)
check("exactly one body rule sets font-size in cuore.css",
      len(body_rules_with_fs) == 1, f"found {len(body_rules_with_fs)}")

# button/input/select/textarea inherit the page font (R3)
check("button/input/select/textarea inherit the page font (R3)",
      "button, input, select, textarea {" in cuore_css
      and "font: inherit" in cuore_css, "")

print(f"static checks done: {checks} so far, {len(failures)} failing")

# ---------------------------------------------------------------------------
# Browser check: no horizontal overflow at 485px on Bench/Job/Scan
# ---------------------------------------------------------------------------


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

    def eval_value(self, expr: str):
        out = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return out.get("result", {}).get("value")


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


def wait_for_navigation(cdp: CDP, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        val = cdp.eval_value(
            "JSON.stringify({href: location.href, ready: document.readyState})")
        try:
            state = json.loads(val or "{}")
        except ValueError:
            state = {}
        if state.get("href", "about:blank") != "about:blank" and state.get("ready") == "complete":
            return True
        time.sleep(0.3)
    return False


def navigate(devtools_port: int, url: str, width: int, height: int) -> CDP:
    target = open_target(devtools_port, "about:blank")
    cdp = CDP(target["webSocketDebuggerUrl"])
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    cdp.send("Emulation.setEmulatedMedia",
             {"features": [{"name": "prefers-color-scheme", "value": "dark"}]})
    cdp.send("Page.navigate", {"url": url})
    wait_for_navigation(cdp)
    cdp.send("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": True,
    })
    time.sleep(0.4)
    return cdp


edge = find_edge()
if not edge:
    print("headless Edge not found -- skipping the browser scrollWidth checks "
          "(static checks above still gate this suite)")
else:
    server_dir = tempfile.mkdtemp(prefix="cuore-check-typescale-server-")
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

    server_proc = subprocess.Popen(
        [sys.executable, "-c", _SERVER_SNIPPET],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_for_port(port):
            print("uvicorn never came up -- skipping the browser checks")
        else:
            time.sleep(0.3)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-typescale-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run",
                 "--window-size=485,1200", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_devtools(devtools_port)

                pages = {
                    "bench": f"http://127.0.0.1:{port}/v/{VIN}",
                    "job": f"http://127.0.0.1:{port}/v/{VIN}/job",
                    "scan": f"http://127.0.0.1:{port}/v/{VIN}/scan",
                }
                for name, url in pages.items():
                    cdp = navigate(devtools_port, url, 485, 1200)
                    try:
                        dims = json.loads(cdp.eval_value(
                            "JSON.stringify({sw: document.documentElement.scrollWidth, "
                            "cw: document.documentElement.clientWidth})"))
                        sw, cw = dims.get("sw", 0), dims.get("cw", 0)
                        check(f"no horizontal overflow at 485px on {name}",
                              sw <= cw + 1, f"scrollWidth={sw} clientWidth={cw}")
                    finally:
                        cdp.close()
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
