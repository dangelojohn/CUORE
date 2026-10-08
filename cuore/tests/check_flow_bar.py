"""Jinja-render + visual check for the flow bar and the flow-aware vehicle
tab strip (cuore/web/templates/_flow_bar.html, _vtabs.html).

No app/server needed: both partials are rendered directly, in a bare
jinja2.Environment, against a fixture standing in for
cuore.services.flow_bridge.flow_state(vin) -- that service doesn't exist
yet (see cuore/web/flow_globals.py's docstring for the contract), so a
fixture of the same shape is what "develop against a fixture" means here.
``flow_state_for`` and ``feedback_open_count`` are registered on this
Environment the same way flow_globals.py/_vbar.html's own feedback global
are registered on the app's real template environments.

Checks, in order:
  1. _flow_bar.html's normal state: "Step N of 12: <title>" label, the
     next-step button's href/label, the blocker count chip, and the amber
     (.note.warn) blocker line inside the expanded stepper.
  2. _flow_bar.html's other two states: "job complete" (last step done,
     no next -> "Tools away. Start the next Stelvio" / /start) and "no
     flow" (service has nothing for this VIN -> "Take this car in" /
     /start).
  3. _vtabs.html: exactly 5 tabs visible outside the More menu, every link
     path the old flat _vbar.html strip had still present (plus the new
     Labels link), the viewed tab marked `.on`, the flow's current-step
     tab marked `.flow-current-tab`, and the More menu auto-opening (with
     its own `.flow-has-current` marker) when that tab is hidden inside it.

Then one CDP screenshot (same technique as check_live_widgets.py; Edge
detaches from its own launcher, so cleanup goes through
_edge_cleanup.kill_edge_profile) of a standalone page holding both
partials' rendered output at a 400px viewport, asserting no horizontal
overflow.

Usage:
    .venv\\Scripts\\python.exe cuore/tests/check_flow_bar.py
    .venv\\Scripts\\python.exe cuore/tests/check_flow_bar.py --screenshot C:\\path\\to\\shot.png
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

from jinja2 import Environment, FileSystemLoader, select_autoescape
from websockets.sync.client import connect

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "cuore" / "web" / "templates"
STATIC_DIR = REPO_ROOT / "cuore" / "web" / "static"

VIN = "ZASFAKPN5J7B88115"

FAILURES: list[str] = []
PASSED = 0


def check(label: str, cond: bool) -> None:
    global PASSED
    if cond:
        PASSED += 1
    else:
        FAILURES.append(label)


# --- fixture: stands in for cuore.services.flow_bridge.flow_state() -------

_STEP_DEFS = [
    (1, "intake", "Take the car in", "/start", None),
    (2, "job", "Complaint & history", "/v/{vin}/job#complaint", None),
    (3, "codes", "Scan & codes", "/v/{vin}/codes", None),
    (4, "systems", "Visual inspection", "/v/{vin}/systems", None),
    (5, "gauges", "Live data baseline", "/v/{vin}/gauges", None),
    (6, "tests", "Tests and inspections", "/v/{vin}/job#tests", None),
    (7, "job", "Hypotheses", "/v/{vin}/job#hypotheses", None),
    (8, "job", "Repair plan & parts", "/v/{vin}/job#actions", None),
    (9, "parts", "Order parts", "/v/{vin}/parts", "Waiting on the parts counter"),
    (10, "job", "Verify repair", "/v/{vin}/job#verify", None),
    (11, "report", "Report & notes", "/v/{vin}/report", None),
    (12, "release", "Release", "/v/{vin}/release", None),
]


def make_flow(vin: str, current: int | None) -> dict:
    """``current=None`` means every step is done and there is no next
    step -- the "job complete" state. Step 9 is always marked "blocked"
    with a blocker, independent of ``current``, so the blocker-rendering
    checks don't depend on exactly which step is "current"."""
    steps = []
    blockers = []
    for n, key, title, href, blocked_why in _STEP_DEFS:
        if blocked_why:
            status = "blocked"
            blockers.append({"why": blocked_why, "step": n})
        elif current is None:
            status = "done"
        elif n < current:
            status = "done"
        elif n == current:
            status = "current"
        else:
            status = "todo"
        steps.append({
            "n": n, "key": key, "title": title, "href": href.format(vin=vin),
            "status": status, "why": f"why for step {n}", "est_min": 5 + n,
        })

    nxt = None
    if current is not None:
        for n, key, title, href, _ in _STEP_DEFS:
            if n == current + 1:
                nxt = {"n": n, "title": title, "href": href.format(vin=vin),
                       "button_label": f"Suggested next: {title} \u2192"}
                break

    return {
        "steps": steps, "current": current, "next": nxt,
        "visit": {"vin": vin}, "job": {"vin": vin}, "blockers": blockers,
    }


HIDDEN_VIN = "HIDDENVIN00000001"  # current step's tab (Parts) lives in the More menu

FLOW_FIXTURES: dict[str, dict | None] = {
    VIN: make_flow(VIN, current=6),
    "COMPLETEVIN0000001": make_flow("COMPLETEVIN0000001", current=None),
    HIDDEN_VIN: make_flow(HIDDEN_VIN, current=9),
    # deliberately absent from the dict -> flow_state_for returns None
}


def _flow_state_for(vin: str):
    return FLOW_FIXTURES.get(vin)


_FEEDBACK_COUNTS = {VIN: 3}


def _feedback_open_count(vin: str) -> int:
    return _FEEDBACK_COUNTS.get(vin, 0)


def make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)),
                       autoescape=select_autoescape(["html"]))
    env.globals["flow_state_for"] = _flow_state_for
    env.globals["feedback_open_count"] = _feedback_open_count
    return env


# --- 1 & 2: _flow_bar.html -------------------------------------------------

def check_flow_bar(env: Environment) -> None:
    tmpl = env.get_template("_flow_bar.html")

    normal = tmpl.render(bar={"vin": VIN}, tab="codes")
    check("flow_bar: step label 'Step 6 of 12: Tests and inspections'",
          "Step 6 of 12:" in normal and "Tests and inspections" in normal)
    # Job UX run 2, R1: the header carries no next button; the bottom bar is
    # the only navigation, so the bar must not render a second primary action.
    check("flow_bar: no header next button (bottom bar is the only navigation)",
          "Suggested next:" not in normal and 'class="btn primary flow-next"' not in normal)
    check("flow_bar: wording never orders the mechanic", "You must" not in normal)
    check("flow_bar: blocker count chip shown", "flow-blocker-chip" in normal and "1" in normal)
    check("flow_bar: blocker text shown as 'Not yet: <why>' inside amber .note.warn",
          'class="note warn flow-blocker"' in normal
          and "Not yet: Waiting on the parts counter" in normal)
    check("flow_bar: blocked step's own why also reads 'Not yet: <why>'",
          "flow-step-why-blocked" in normal and "Not yet: Waiting on the parts counter" in normal)
    check("flow_bar: step 1 links to /start", f'href="/start"' in normal)
    check("flow_bar: step 12 links to /v/{vin}/release", f'href="/v/{VIN}/release"' in normal)
    check("flow_bar: done/current/blocked icons present",
          all(s in normal for s in ("&#10003;", "&#9675;", "&#9888;")))

    complete = tmpl.render(bar={"vin": "COMPLETEVIN0000001"}, tab="report")
    check("flow_bar: job-complete state shows the Stelvio message",
          "Tools away. Start the next Stelvio" in complete)
    check("flow_bar: job-complete button links to /start", 'href="/start"' in complete)
    check("flow_bar: job-complete state has no 'Step N of 12' label",
          "Step" not in complete.split("flow-step-label")[1][:40])

    empty = tmpl.render(bar={"vin": "UNKNOWNVIN0000000"}, tab="dossier")
    check("flow_bar: no-flow fallback shows 'Take this car in'",
          "Take this car in" in empty)
    check("flow_bar: no-flow fallback links to /start", 'href="/start"' in empty)
    check("flow_bar: no-flow fallback renders no stepper", "flow-stepper" not in empty)


# --- 3: _vtabs.html ---------------------------------------------------------

# 2026-10-08 UX pass: Live board was promoted out of the More menu and into
# the visible row (after Codes, labelled "Live") -- see _vtabs.html.
VISIBLE_LABELS = ["Bench", "Job", "Codes", "Live", "Systems", "Report"]
OLD_LINK_PATHS = [
    f"/v/{VIN}", f"/v/{VIN}/job", f"/v/{VIN}/modules", f"/v/{VIN}/timeline",
    f"/v/{VIN}/systems", f"/v/{VIN}/electrical", f"/v/{VIN}/media", f"/v/{VIN}/parts",
    f"/v/{VIN}/dashboard", f"/v/{VIN}/gauges", f"/v/{VIN}/codes", f"/v/{VIN}/tree",
    f"/v/{VIN}/gate", f"/v/{VIN}/service-hub", f"/v/{VIN}/report", f"/v/{VIN}/inbox",
    f"/logs?vin={VIN}", f"/v/{VIN}/liveboard",
]
NEW_LINK_PATHS = [f"/v/{VIN}/labels"]


def check_vtabs(env: Environment) -> None:
    tmpl = env.get_template("_vtabs.html")

    # VIN's own current step ("tests") matches no tab -- a neutral case for
    # the general structural checks (nothing forced open, nothing wrongly
    # highlighted).
    rendered = tmpl.render(bar={"vin": VIN}, tab="job")
    before_more = rendered.split("<details")[0]
    check("vtabs: exactly 6 tabs visible outside the More menu",
          sum(f">{lbl}<" in before_more for lbl in VISIBLE_LABELS) == 6)
    check("vtabs: viewed tab (Job) marked .on",
          f'href="/v/{VIN}/job" class="on' in rendered)
    for path in OLD_LINK_PATHS + NEW_LINK_PATHS:
        check(f"vtabs: old link path kept -- {path}", f'href="{path}"' in rendered)
    check("vtabs: Dashboard present inside More (not in the flow spec's own list, "
          "kept so no existing link breaks)", ">Dashboard<" in rendered)
    check("vtabs: Labels present inside More (new -- had no tab link before)",
          ">Labels<" in rendered)
    check("vtabs: Inbox badge chip rendered from feedback_open_count",
          '<span class="chip chronic">3</span>' in rendered)
    check("vtabs: no forced-open when the flow highlight matches no tab",
          '<details class="vmore-tab" open>' not in rendered)

    # HIDDEN_VIN's current step ("parts") is hidden inside More -> auto-open
    # + highlight, independent of which tab the browser is actually on.
    rendered_hidden = tmpl.render(bar={"vin": HIDDEN_VIN}, tab="job")
    check("vtabs: flow-current-tab marks Parts (hidden in More)",
          f'href="/v/{HIDDEN_VIN}/parts" class=" flow-current-tab"' in rendered_hidden)
    check("vtabs: More auto-opens when the flow-current tab is hidden inside it",
          '<details class="vmore-tab" open>' in rendered_hidden)
    check("vtabs: More summary flags flow-has-current when auto-opened",
          "flow-has-current" in rendered_hidden)

    # COMPLETEVIN's current step is None (job finished) -> no highlight,
    # no forced-open either.
    rendered_complete = tmpl.render(bar={"vin": "COMPLETEVIN0000001"}, tab="systems")
    check("vtabs: no forced-open when flow has no current step (job-complete fixture)",
          '<details class="vmore-tab" open>' not in rendered_complete)


# --- CDP screenshot ---------------------------------------------------------

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
    req = urllib.request.Request(
        "http://127.0.0.1:%d/json/new?%s" % (port, url), method="PUT"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def build_standalone_html(env: Environment) -> str:
    """Both partials, rendered with the "current step is a visible tab"
    fixture so the More menu stays closed (its default, JS-free state) --
    this screenshot is of what a mechanic actually sees on load, not of a
    manually-expanded state."""
    flow_bar_html = env.get_template("_flow_bar.html").render(bar={"vin": VIN}, tab="codes")
    vtabs_html = env.get_template("_vtabs.html").render(bar={"vin": VIN}, tab="codes")
    cuore_css = (STATIC_DIR / "cuore.css").read_text(encoding="utf-8")
    flow_css = (STATIC_DIR / "flow.css").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{cuore_css}</style>
<style>{flow_css}</style>
<style>body {{ margin: 0; background: var(--bg); }}</style>
</head><body>
<div class="vbar">
{vtabs_html}
</div>
{flow_bar_html}
<main style="padding:14px"><p>page content</p></main>
</body></html>"""


def run_screenshot_check(html: str, screenshot_path, no_screenshot: bool) -> bool:
    edge = find_edge()
    port = free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="cuore-flowbar-edge-"))
    html_file = Path(tempfile.mkdtemp(prefix="cuore-flowbar-html-")) / "flow_bar_check.html"
    html_file.write_text(html, encoding="utf-8")
    url = html_file.resolve().as_uri()

    proc = subprocess.Popen(
        [edge, "--headless=new", "--remote-debugging-port=%d" % port,
         "--user-data-dir=%s" % profile_dir, "--no-first-run", "--window-size=400,900",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    ok = False
    try:
        wait_for_devtools(port)
        target = open_target(port, url)
        cdp = CDP(target["webSocketDebuggerUrl"])
        try:
            cdp.send("Page.enable")
            cdp.send("Runtime.enable")
            cdp.send("Emulation.setDeviceMetricsOverride", {
                "width": 400, "height": 900, "deviceScaleFactor": 1, "mobile": True,
            })
            time.sleep(0.3)

            out = cdp.send("Runtime.evaluate", {
                "expression": "JSON.stringify({sw: document.documentElement.scrollWidth, "
                               "cw: document.documentElement.clientWidth})",
                "returnByValue": True,
            })
            dims = json.loads(out.get("result", {}).get("value") or "{}")
            scroll_w = dims.get("sw")
            client_w = dims.get("cw")
            check("screenshot: no horizontal overflow at 400px",
                  scroll_w is not None and scroll_w <= 400)
            print("  scrollWidth=%s clientWidth=%s" % (scroll_w, client_w))
            ok = True

            if not no_screenshot:
                shot_path = Path(screenshot_path) if screenshot_path else Path(tempfile.gettempdir()) / "cuore_flow_bar_check.png"
                shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                shot_path.parent.mkdir(parents=True, exist_ok=True)
                shot_path.write_bytes(base64.b64decode(shot["data"]))
                print("Screenshot: %s" % shot_path)
        finally:
            cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        from _edge_cleanup import kill_edge_profile
        kill_edge_profile(profile_dir)
        shutil.rmtree(profile_dir, ignore_errors=True)
        shutil.rmtree(html_file.parent, ignore_errors=True)

    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", default=None)
    ap.add_argument("--no-screenshot", action="store_true")
    args = ap.parse_args()

    env = make_env()
    check_flow_bar(env)
    check_vtabs(env)

    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print("  - " + f)

    screenshot_ok = run_screenshot_check(build_standalone_html(env), args.screenshot, args.no_screenshot)

    total = PASSED + len(FAILURES)
    print("%d/%d checks passed" % (PASSED, total))
    sys.exit(0 if (not FAILURES and screenshot_ok) else 1)


if __name__ == "__main__":
    main()
