"""Checks for the job-page UX pass (docs/research/JOB_UX_FIXES_2026-10-08.md):
no-JS redirect-in-place (#5), the viewed-step header (#6), the Next-button
href (#7), the honest step-6 count (#4's own accept test, reused here since
it's load-bearing for #11/#13's layout), and the confirm-gate's inline
reason on a fresh hypothesis (#1).

Same posture as ``check_jobs_page.py``/``check_screens.py``: ``CUORE_STATE_DIR``
pointed at a throwaway directory before cuore is imported, the Stelvio (real
corpus) as the fixture vehicle. One CDP session only (memory is limited on
this machine) -- it does the 200px content-start measurement AND the one
screenshot of ?step=7 in the same pass, at 768x1024.

Run:
    .venv/Scripts/python.exe cuore/tests/check_job_ux.py
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
import urllib.request
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-jobux-")
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


# --- #6: the sticky header shows the VIEWED step, with a chip when it
#     differs from the job's own current step -------------------------------

step7 = client.get(f"/v/{VIN}/job", params={"step": "7"})
check("?step=7 responds 200", step7.status_code == 200, str(step7.status_code))
check('header reads "Step 7 of 12"', "Step 7 of 12:" in step7.text, step7.text[:200])


# --- #7: the primary button on step 7 points at step 8, never the current
#     page, and the Back button points at step 6 ----------------------------

check("primary Next button on step 7 links to ?step=8",
      f'href="/v/{VIN}/job?step=8"' in step7.text, "no ?step=8 Next href found")
check("Back button on step 7 links to ?step=6",
      f'href="/v/{VIN}/job?step=6"' in step7.text, "no ?step=6 Back href found")


# --- #5: a mutating POST redirects back to the *same* step, with the row's
#     own anchor, never to a different tab/step -----------------------------

_open_job_id = client.get(f"/api/vehicles/{VIN}/job").json()["job"]["id"]
add_resp = client.post(f"/v/{VIN}/job/{_open_job_id}/actions",
                       data={"kind": "note", "text": "ux check note", "step": "9"},
                       follow_redirects=False)
check("an action POST redirects to ?step=9#actions, not #open-work/another tab",
      add_resp.status_code in (303, 307)
      and add_resp.headers.get("location", "").startswith(f"/v/{VIN}/job?step=9"),
      f"status={add_resp.status_code} location={add_resp.headers.get('location')}")


# --- #4's own accept test, reused: 0 results on step 6 reads "Not started
#     0/N", never green/complete ---------------------------------------------

step6 = client.get(f"/v/{VIN}/job", params={"step": "6"})
check("?step=6 responds 200", step6.status_code == 200, str(step6.status_code))
check('step 6 shows "Not started 0/" when nothing is done yet',
      "Not started 0/" in step6.text or "step6-status-not-started" in step6.text,
      step6.text[step6.text.find("step6-status"):step6.text.find("step6-status") + 120]
      if "step6-status" in step6.text else "no step6-status element found")
check("step 6's status is not marked complete when nothing is done",
      "step6-status-complete" not in step6.text)


# --- #1: the Confirm button is disabled with an inline reason on a fresh
#     hypothesis (no evidence at all) ----------------------------------------

job_id = client.get(f"/api/vehicles/{VIN}/job").json()["job"]["id"]
hyp_resp = client.post(f"/v/{VIN}/job/{job_id}/hypotheses",
                       data={"text": "ux-check fresh hypothesis", "step": "7"},
                       follow_redirects=True)
check("adding a manual hypothesis responds 200", hyp_resp.status_code == 200,
      str(hyp_resp.status_code))
view = client.get(f"/api/vehicles/{VIN}/job").json()
fresh = next((h for h in view["job"]["hypotheses"] if h["text"] == "ux-check fresh hypothesis"), None)
check("the fresh hypothesis landed on the ledger", fresh is not None, str(view["job"]["hypotheses"]))

step7_again = client.get(f"/v/{VIN}/job", params={"step": "7"})
hyp_card_start = step7_again.text.find(f'id="hyp-{fresh["id"]}"') if fresh else -1
hyp_card_end = step7_again.text.find('id="hyp-', hyp_card_start + 1) if hyp_card_start >= 0 else -1
if hyp_card_start >= 0 and hyp_card_end < 0:
    hyp_card_end = len(step7_again.text)
card_html = step7_again.text[hyp_card_start:hyp_card_end] if hyp_card_start >= 0 else ""
check("the fresh hypothesis's card is on the rendered page", hyp_card_start >= 0,
      "card not found for id " + str(fresh["id"] if fresh else "?"))
check('its Confirm button is disabled',
      'value="confirmed"' in card_html and "disabled" in card_html.split('value="confirmed"', 1)[1][:200],
      card_html[card_html.find('value="confirmed"'):card_html.find('value="confirmed"') + 200]
      if 'value="confirmed"' in card_html else "no confirmed button found")
check("an inline reason is shown (needs a passed/failed test result)",
      "passed/failed test result" in card_html, card_html[:2000])

# attempting to confirm it server-side anyway must still be refused (409-
# equivalent: refused with a reason, never silently accepted)
confirm_attempt = client.post(f"/v/{VIN}/job/{job_id}/hypotheses/{fresh['id']}/status",
                              data={"status": "confirmed", "step": "7"}, follow_redirects=True)
view2 = client.get(f"/api/vehicles/{VIN}/job").json()
fresh2 = next(h for h in view2["job"]["hypotheses"] if h["id"] == fresh["id"])
check("confirming a hypothesis with no evidence is refused, not silently accepted",
      fresh2["status"] != "confirmed", str(fresh2))
check("the refusal reason reaches the re-rendered page",
      "passed/failed test result" in confirm_attempt.text, confirm_attempt.text[:200])


# --- run 2 regression: Fail result linked -> evidence appears -> open ->
#     confirmed still rejected (the path rule, not just evidence) ->
#     supported -> confirm via the modal's ack -> stays on step 7, 1/1,
#     next test changes, and the job chip moves forward (R2/R3/R4/R7) ------

client.post(f"/v/{VIN}/job/{job_id}/hypotheses/{fresh['id']}/edit",
           data={"system": "EVAP", "step": "7"}, follow_redirects=True)

evap_view = client.get(f"/api/vehicles/{VIN}/view").json()
evap_card = next((c for c in evap_view.get("open_work", [])
                  if (c.get("family") or "").upper() == "EVAP"), None)
evap_step_id = (evap_card.get("steps") or [{}])[0].get("id") if evap_card else None
check("the fixture has an EVAP checklist step to link evidence to",
      bool(evap_step_id), str(evap_card))

if evap_step_id:
    result_resp = client.post(
        f"/api/vehicles/{VIN}/checklist/{evap_step_id}/result",
        json={"result": "fail", "reason": "leak found", "value": 0.5, "unit": "psi",
             "hypothesis_id": fresh["id"], "supports": "for"})
    check("recording the Fail result responds 200", result_resp.status_code == 200,
          str(result_resp.status_code))

    view3 = client.get(f"/api/vehicles/{VIN}/job").json()
    hyp3 = next(h for h in view3["job"]["hypotheses"] if h["id"] == fresh["id"])
    check("the Fail result shows up as evidence_for on the hypothesis (1)",
          len(hyp3.get("evidence_for") or []) == 1, str(hyp3.get("evidence_for")))

    # open -> confirmed is still rejected even though evidence now exists --
    # the path rule (R7), not only the evidence gate (#1), is enforced.
    still_open_attempt = client.post(
        f"/v/{VIN}/job/{job_id}/hypotheses/{fresh['id']}/status",
        data={"status": "confirmed", "step": "7"}, follow_redirects=True)
    view4 = client.get(f"/api/vehicles/{VIN}/job").json()
    hyp4 = next(h for h in view4["job"]["hypotheses"] if h["id"] == fresh["id"])
    check("open -> confirmed is still rejected once evidence exists but status is still open",
          hyp4["status"] != "confirmed", str(hyp4))

    step7_reason = client.get(f"/v/{VIN}/job", params={"step": "7"}).text
    start = step7_reason.find(f'id="hyp-{fresh["id"]}"')
    end = step7_reason.find('id="hyp-', start + 1) if start >= 0 else -1
    card3 = step7_reason[start:end if end > 0 else len(step7_reason)] if start >= 0 else ""
    check('the open-status reason reads "Mark supported first"',
          "Mark supported first" in card3, card3[:400])

    client.post(f"/v/{VIN}/job/{job_id}/hypotheses/{fresh['id']}/status",
               data={"status": "supported", "step": "7"}, follow_redirects=True)
    confirm_tap1 = client.post(
        f"/v/{VIN}/job/{job_id}/hypotheses/{fresh['id']}/status",
        data={"status": "confirmed", "step": "7"}, follow_redirects=False)
    check("the first confirm tap (no ack) redirects back to step 7 with a confirm panel",
          confirm_tap1.status_code in (303, 307)
          and confirm_tap1.headers.get("location", "").startswith(f"/v/{VIN}/job?step=7"),
          f"status={confirm_tap1.status_code} location={confirm_tap1.headers.get('location')}")
    confirm_tap2 = client.post(
        f"/v/{VIN}/job/{job_id}/hypotheses/{fresh['id']}/status",
        data={"status": "confirmed", "ack": "1", "step": "7"}, follow_redirects=False)
    check("the second confirm tap (ack=1) redirects back to step 7, never another step/tab",
          confirm_tap2.status_code in (303, 307)
          and confirm_tap2.headers.get("location", "").startswith(f"/v/{VIN}/job?step=7"),
          f"status={confirm_tap2.status_code} location={confirm_tap2.headers.get('location')}")

    view5 = client.get(f"/api/vehicles/{VIN}/job").json()
    hyp5 = next(h for h in view5["job"]["hypotheses"] if h["id"] == fresh["id"])
    check("the hypothesis is confirmed after the second tap", hyp5["status"] == "confirmed",
          str(hyp5))
    check("the next_test changed off the original evidence-gate wording (R4)",
          "passed/failed test result" not in (hyp5.get("next_test") or ""),
          str(hyp5.get("next_test")))

    step7_final = client.get(f"/v/{VIN}/job", params={"step": "7"}).text
    check('step 7 summary reads "1/1" resolved beyond open',
          "1/1" in step7_final, step7_final[step7_final.find("1/1") - 80:step7_final.find("1/1") + 20])

    flow_after = client.get(f"/api/vehicles/{VIN}/flow").json()
    check("the job progress chip moves forward off step 7 once it's resolved (R2)",
          flow_after.get("current", 7) != 7, str(flow_after.get("current")))


# --- #8: content starts within 200px of the sticky header at 768 wide
#     (CDP) -- and the one screenshot of ?step=7 this session is allowed ----

print("=== 768x1024 CDP: header-to-content gap + one screenshot of ?step=7 ===")
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
server_dir = tempfile.mkdtemp(prefix="cuore-check-jobux-server-")
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
    check("headless Edge is available for the UX checks", False, str(EDGE_CANDIDATES))
else:
    import urllib.parse

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
                                           data=data, method="POST"), timeout=30)
            except Exception as exc:  # noqa: BLE001
                check("seeding a job on the UX-check server", False, str(exc))

            time.sleep(0.5)
            devtools_port = free_port()
            profile_dir = Path(tempfile.mkdtemp(prefix="cuore-edge-jobux-"))
            edge_proc = subprocess.Popen(
                [edge, "--headless=new", f"--remote-debugging-port={devtools_port}",
                 f"--user-data-dir={profile_dir}", "--no-first-run",
                 "--window-size=768,1024", "about:blank"],
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
                    time.sleep(1.0)
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 768, "height": 1024, "deviceScaleFactor": 1, "mobile": False,
                    })

                    # Poll up to ~8s for #step-7 to actually exist -- the
                    # page carries a ~2.2s intro-splash CSS animation (see
                    # _intro.html) plus this is a content-heavy screen
                    # (many hypothesis/suggestion cards), so a fixed sleep
                    # proved flaky; a short poll is cheap and robust.
                    gap_val = -1
                    ready_val = None
                    deadline = time.time() + 8
                    while time.time() < deadline:
                        probe = cdp.send("Runtime.evaluate", {
                            "expression": (
                                "JSON.stringify((function(){"
                                "var rs = document.readyState;"
                                "var h = document.querySelector('.flow-bar') || document.querySelector('header.top');"
                                "var c = document.getElementById('step-7');"
                                "if (!c) return {ready: rs, gap: -1};"
                                "var hb = h ? h.getBoundingClientRect().bottom : 0;"
                                "var cb = c.getBoundingClientRect().top;"
                                "return {ready: rs, gap: cb - hb};"
                                "})())"
                            ),
                            "returnByValue": True,
                        })
                        data = json.loads(probe.get("result", {}).get("value", "{}"))
                        ready_val = data.get("ready")
                        gap_val = data.get("gap", -1)
                        if gap_val != -1:
                            break
                        time.sleep(0.4)

                    check("job page (step=7) loaded in the headless browser",
                          ready_val in ("complete", "interactive"), str(ready_val))

                    # _intro.html's splash is a ~2.2s CSS fade that covers
                    # the whole viewport but does not affect layout -- wait
                    # for it to actually finish (computed opacity 0, or the
                    # element gone) before trusting the gap measurement or
                    # taking the screenshot.
                    intro_deadline = time.time() + 5
                    while time.time() < intro_deadline:
                        intro = cdp.send("Runtime.evaluate", {
                            "expression": (
                                "(function(){var o = document.querySelector('.intro-overlay');"
                                "if (!o) return '0'; return getComputedStyle(o).opacity;})()"
                            ),
                            "returnByValue": True,
                        })
                        if intro.get("result", {}).get("value") in ("0", 0):
                            break
                        time.sleep(0.3)

                    gap2 = cdp.send("Runtime.evaluate", {
                        "expression": (
                            "JSON.stringify((function(){"
                            "var h = document.querySelector('.flow-bar') || document.querySelector('header.top');"
                            "var c = document.getElementById('step-7');"
                            "if (!c) return {gap: -1};"
                            "var hb = h ? h.getBoundingClientRect().bottom : 0;"
                            "var cb = c.getBoundingClientRect().top;"
                            "return {gap: cb - hb};"
                            "})())"
                        ),
                        "returnByValue": True,
                    })
                    gap_val = json.loads(gap2.get("result", {}).get("value", "{}")).get("gap", gap_val)
                    check("step 7's content starts within 200px below the sticky header",
                          0 <= gap_val <= 200, f"gap={gap_val}px")

                    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
                    out_path = SCRATCHPAD / "job_step7.png"
                    shot = cdp.send("Page.captureScreenshot",
                                   {"format": "png", "captureBeyondViewport": False})
                    out_path.write_bytes(__import__("base64").b64decode(shot["data"]))
                    check("screenshot job_step7.png captured",
                         out_path.exists() and out_path.stat().st_size > 0, str(out_path))
                    if out_path.exists():
                        print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
                finally:
                    cdp.close()
            except Exception as exc:  # noqa: BLE001
                check("headless Edge measured/screenshotted the job page over CDP", False,
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
