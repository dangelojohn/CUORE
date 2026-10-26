"""Checks for the job-page UX pass (docs/research/JOB_UX_FIXES_2026-10-08.md):
no-JS redirect-in-place (#5), the viewed-step header (#6), the Next-button
href (#7), the honest step-6 count (#4's own accept test, reused here since
it's load-bearing for #11/#13's layout), and the confirm-gate's inline
reason on a fresh hypothesis (#1).

Also covers the 2026-10-14 "Connect to car" pass: the button (and its
no-JS fallback href) renders on both the job page and the bench page
(_vbar.html renders on every /v/{vin} page), the new additive
POST /api/live/connect/start route (cuore/api/live.py) reaches a started
guided scan and surfaces its first pause, and refuses with the live
layer's own wording -- never invented copy -- when the adapter or the
poller guard refuses. Same posture as cuore/tests/check_fullscan.py: every
``cuore.live.ops``/``cuore.live.interlock`` call is monkeypatched with a
canned reply, never a real adapter, never COM3.

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
import shutil
import time
import urllib.request
from datetime import datetime
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-jobux-")
os.environ.pop("CUORE_AUDIT_PATH", None)

# MES_LOG_DIR: a read-only copy of the real MultiEcuScan corpus (never the
# real install dir itself -- this test must never write there), plus one
# synthetic scan this test owns. The corpus moves forward in real time as
# the mechanic keeps working this car -- P0456 was the one still-ACTIVE
# chronic EVAP code when fix item 1 below was written (2026-10-08), but by
# 2026-10-14 the real corpus's own later clears/rescans have carried every
# chronic code to STALE/CLEARED_UNVERIFIED (none left ACTIVE at all), which
# would make the ?codes= highlight check below untestable against the real
# corpus alone. One extra scan, that reports P0456 again -- the exact
# "returned after clear" shape the real corpus itself held on 2026-10-08/13
# -- keeps this check deterministic without weakening it and without
# touching the real install's own files. Its own timestamp is "right now"
# (never a hard-coded date) so it is always the newest scan on file,
# whatever day this runs -- a hard-coded date (even one a day ahead of the
# scenario it was first written against) is exactly what let a later real
# scan quietly become newer and flip P0456 back off ACTIVE from under this
# check, the same drift bug this file's own comment above describes.
_REAL_MES_DIR = Path(r"C:\Program Files (x86)\MultiEcuScan")
_MES_LOG_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-jobux-logs-"))
os.environ["MES_LOG_DIR"] = str(_MES_LOG_DIR)
if _REAL_MES_DIR.exists():
    for _f in _REAL_MES_DIR.iterdir():
        if _f.is_file():
            shutil.copyfile(_f, _MES_LOG_DIR / _f.name)
_jobux_scan_at = datetime.now()
(_MES_LOG_DIR / f"SCAN_{_jobux_scan_at.strftime('%y%m%d%H%M')}.txt").write_text(
    "Scan vehicle for available modules and check each module for errors...\n\n"
    "Engine / ECM\n"
    "Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)\n"
    "ISO Code: 00 01 50 40 18\n"
    f"VIN code: {'ZASFAKPN5J7B88115'}\n"
    "Hardware number: MM10JAHW232 - Ver: 00\n"
    "Software number: P235QB39 - Ver: 0000\n"
    "Errors found:\n"
    "P0456-00 - Evaporation system leak\n",
    encoding="utf-8",
)

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


# ===========================================================================
# "Connect to car": the button renders everywhere, the additive route
# reaches a started scan and its first pause, and refusals carry the live
# layer's own wording. Run first, before any job/hypothesis fixture state,
# since it is independent of it; every ops/interlock call is faked, never
# a real adapter.
# ===========================================================================

from cuore.live import fullscan as connect_fullscan  # noqa: E402
from cuore.live import interlock as connect_interlock  # noqa: E402
from cuore.live import ops as connect_ops  # noqa: E402
from cuore.live.errors import LiveError as ConnectLiveError  # noqa: E402
from cuore.live.errors import Refused as ConnectRefused  # noqa: E402

_connect_originals: dict[tuple, object] = {}


def _connect_patch(obj, name, fn) -> None:
    _connect_originals.setdefault((obj, name), getattr(obj, name))
    setattr(obj, name, fn)


def _connect_restore_all() -> None:
    for (obj, name), fn in _connect_originals.items():
        setattr(obj, name, fn)
    _connect_originals.clear()


def _fake_scan_modules_connect(bus, vin="", mask=0xFF, confirm=False, detail=True):
    if bus == "can_c":
        return {"bus": "can_c", "cable": "none",
                "modules": [{"ecu": "ECM", "bus": "can_c", "mask": "FF", "dtcs": [], "codes": []}]}
    from cuore.live.addressing import on_bus as _on_bus
    return {"bus": bus, "cable": "none",
            "modules": [{"ecu": m.code, "skipped": "no confirmed address"} for m in _on_bus(bus)]}


def _install_connect_fakes() -> None:
    _connect_patch(connect_ops, "_poller_active_guard", lambda: None)
    _connect_patch(connect_interlock, "mes_status",
                   lambda: {"running": False, "pids": [], "state": "not_running", "label": None})
    _connect_patch(connect_ops, "status", lambda: {"port": "COM3", "baud": 115200})
    _connect_patch(connect_ops, "cable_state", lambda: {"cable": "none", "buses": {}})
    _connect_patch(connect_ops, "set_cable", lambda c: {"cable": c, "buses": {}})
    _connect_patch(connect_ops, "probe",
                   lambda **kw: {"port": "COM3", "baud": 115200, "stn_chip": True,
                                 "battery_voltage": 12.6, "identity": {"STI": "STN1170 v4.3.2"}})
    _connect_patch(connect_ops, "verify_bus",
                   lambda bus, **kw: {"verified": True, "frames": 12, "bus": bus, "cable": "none"})
    _connect_patch(connect_ops, "obd_vin",
                   lambda **kw: {"vin": VIN, "ecu": "18DAF110", "length_ok": True})
    _connect_patch(connect_ops, "obd_dtcs",
                   lambda kind, **kw: {"kind": kind, "dtcs": [], "by_ecu": {}, "raw": "NO DATA"})
    _connect_patch(connect_ops, "obd_supported_pids", lambda **kw: {"by_ecu": {}})
    _connect_patch(connect_ops, "obd_freeze_frame", lambda pid, **kw: {"pid": pid, "by_ecu": {}})
    _connect_patch(connect_ops, "obd_pid", lambda pid, **kw: {"pid": pid, "by_ecu": {}})
    _connect_patch(connect_ops, "obd_readiness",
                   lambda **kw: {"since_clear": {"mil_on": False},
                                 "this_drive_cycle": {"mil_on": False}})
    _connect_patch(connect_ops, "obd_mode06", lambda **kw: {"mids": []})
    _connect_patch(connect_ops, "scan_modules", _fake_scan_modules_connect)
    _connect_patch(connect_ops, "module_identity",
                   lambda code, vin="", confirm=False, **kw:
                   {"ecu": code, "bus": "can_c", "fields": {}})
    _connect_patch(connect_ops, "module_did",
                   lambda code, did, vin="", confirm=False, **kw:
                   {"ecu": code, "did": did, "bytes": []})
    _connect_patch(connect_ops, "module_did_sweep",
                   lambda code, dids, vin="", per_did_timeout=0.3, confirm=False, **kw:
                   {"ecu": code, "tried": len(dids), "hits": []})
    _connect_patch(connect_ops, "learned_dids", lambda vin="": {"learned": {}})


# 1. the button (and its no-JS fallback href straight to the wizard) renders
#    on both the job page and the bench page -- it lives in _vbar.html,
#    included by every /v/{vin} page, not just job.html.
for _page_label, _page_url in (("job page", f"/v/{VIN}/job"), ("bench page", f"/v/{VIN}")):
    _btn_resp = client.get(_page_url)
    check(f"the Connect to car button renders on the {_page_label}",
          'id="connect-car-btn"' in _btn_resp.text, _page_label)
    check(f"the {_page_label}'s button carries the no-JS fallback href to the wizard",
          f'href="/v/{VIN}/scan"' in _btn_resp.text, _page_label)

try:
    # Never start over an already-open session left by an earlier run in
    # this same throwaway state dir.
    _leftover = connect_fullscan.guided_state()
    if _leftover.get("status") == "paused":
        connect_fullscan.abandon_guided(_leftover["scan_id"])

    _install_connect_fakes()

    # 2. the sequence reaches a started scan and surfaces its first pause.
    connect_resp = client.post("/api/live/connect/start", json={"vin": VIN})
    check("POST /api/live/connect/start is 200", connect_resp.status_code == 200,
          str(connect_resp.status_code))
    connect_data = connect_resp.json()
    check("the connect sequence reports ok", connect_data.get("ok") is True, str(connect_data))
    check("the connect sequence's own checks cover adapter/bus/VIN, in order",
          [c.get("stage") for c in connect_data.get("checks", [])] == ["adapter", "bus", "vin", "scan"],
          str(connect_data.get("checks")))
    connect_guided = connect_data.get("guided") or {}
    check("the connect sequence starts the guided scan (a real scan_id)",
          bool(connect_guided.get("scan_id")), str(connect_guided))
    check("the connect sequence surfaces a pause state (blue A5 cable next)",
          connect_guided.get("status") == "paused"
          and (connect_guided.get("next") or {}).get("cable") == "blue_a5",
          str(connect_guided))

    connect_fullscan.abandon_guided(connect_guided["scan_id"])

    # 3. refusal wording: adapter missing -- the live layer's own message
    #    (the real LinkUnavailable text transport.py raises), never invented.
    _connect_patch(
        connect_ops, "probe",
        lambda **kw: (_ for _ in ()).throw(
            ConnectLiveError("no reply from the adapter on COM3; is it plugged in?")))
    refuse_resp = client.post("/api/live/connect/start", json={"vin": VIN})
    check("a missing adapter still responds 200 (refused honestly, never a 500)",
          refuse_resp.status_code == 200, str(refuse_resp.status_code))
    refuse_data = refuse_resp.json()
    check("the refusal is reported explicitly (ok: false, stage: adapter)",
          refuse_data.get("ok") is False and refuse_data.get("stage") == "adapter",
          str(refuse_data))
    check("the refusal wording is the live layer's own adapter message, not invented copy",
          "no reply from the adapter on COM3" in (refuse_data.get("error") or ""),
          str(refuse_data.get("error")))

    # 4. refusal wording: the live-data poller holds the adapter.
    _connect_patch(connect_ops, "probe",
                   lambda **kw: {"port": "COM3", "baud": 115200, "stn_chip": True,
                                 "battery_voltage": 12.6, "identity": {}})
    _connect_patch(
        connect_ops, "_poller_active_guard",
        lambda: (_ for _ in ()).throw(
            ConnectRefused("a live-data poll session is running and holds the adapter; "
                           "stop it first")))
    poller_data = client.post("/api/live/connect/start", json={"vin": VIN}).json()
    check("the poller-running refusal reaches the caller with the live layer's own wording",
          poller_data.get("ok") is False
          and "a live-data poll session is running" in (poller_data.get("error") or ""),
          str(poller_data))
finally:
    _connect_restore_all()


open_resp = client.post(f"/v/{VIN}/job/open",
                        data={"technician": "tester", "complaint": "CEL, smells like gas"},
                        follow_redirects=True)
check("opening a case for the fixture responds 200", open_resp.status_code == 200,
      str(open_resp.status_code))


# --- item 1 (2026-10-08 follow-up): ?system=<key>&codes=P0440 on step 7
#     expands the add-hypothesis form and pre-selects/pre-ticks both -------

step7_prefill = client.get(f"/v/{VIN}/job", params={"step": "7", "system": "evap", "codes": "P0440"})
check("?step=7&system=evap&codes=P0440 responds 200",
      step7_prefill.status_code == 200, str(step7_prefill.status_code))
text_prefill = step7_prefill.text

_ah_tag_start = text_prefill.find('<details class="add-hypothesis-collapsed"')
_ah_tag_end = text_prefill.find(">", _ah_tag_start) if _ah_tag_start >= 0 else -1
_ah_tag = text_prefill[_ah_tag_start:_ah_tag_end + 1] if _ah_tag_start >= 0 else ""
check("the add-hypothesis form is expanded (open) when ?system=/?codes= is present",
      "open" in _ah_tag, _ah_tag)

_ah_end = text_prefill.find("</details>", _ah_tag_start) if _ah_tag_start >= 0 else -1
_ah_html = text_prefill[_ah_tag_start:_ah_end] if _ah_tag_start >= 0 else ""


def _option_selected(html: str, value: str) -> tuple[bool, str]:
    marker = f'value="{value}"'
    idx = html.find(marker)
    if idx < 0:
        return False, f"{marker} not found"
    end = html.find(">", idx)
    tag = html[idx:end + 1]
    return "selected" in tag, tag


_sel_ok, _sel_detail = _option_selected(_ah_html, "EVAP (evaporative emissions)")
check("?system=evap pre-selects the EVAP option in the System select",
      _sel_ok, _sel_detail)
_code_ok, _code_detail = _option_selected(_ah_html, "P0440")
check("?codes=P0440 pre-ticks the P0440 option in the linked-codes select",
      _code_ok, _code_detail)


# --- item 1 continued: ?codes= on step 5 highlights that code's own card --
# (P0456, not P0440 -- the fixture's P0440 is CLEARED_UNVERIFIED right now,
# so it has no step 5 card at all to highlight; step 5 only ever shows
# ACTIVE codes' own cards, same restriction as before this pass.)

step5_prefill = client.get(f"/v/{VIN}/job", params={"step": "5", "codes": "P0456"})
check("?step=5&codes=P0456 responds 200", step5_prefill.status_code == 200,
      str(step5_prefill.status_code))
check('P0456\'s step 5 card carries the highlight class',
      'id="code-brief-P0456"' in step5_prefill.text
      and "is-codes-highlighted" in step5_prefill.text[
          step5_prefill.text.find('id="code-brief-P0456"') - 80:
          step5_prefill.text.find('id="code-brief-P0456"') + 20],
      "no highlighted P0456 card found" if "P0456" in step5_prefill.text
      else "P0456 is not an active code on this fixture")


# --- item 2 (2026-10-08 follow-up): the step 6 result sheet's hypothesis
#     picker -- next_test match first, then ?hypothesis=, else a real
#     prompt label rather than "(none)" ---------------------------------

job_js_text = (ROOT / "cuore" / "web" / "static" / "job.js").read_text(encoding="utf-8")
check('the result sheet\'s hypothesis picker default reads "Choose a hypothesis...", '
      'not "(none)"',
      "Choose a hypothesis" in job_js_text
      and '<option value="">(none)</option>' not in job_js_text,
      "still has the old (none) wording" if '<option value="">(none)</option>' in job_js_text
      else "\"Choose a hypothesis\" text not found in job.js")
check("the picker matches by next_test before falling back to ?hypothesis=",
      "matchByNextTest" in job_js_text and 'get("hypothesis")' in job_js_text,
      "next_test match / ?hypothesis= read not found in job.js")


# --- item 3 (2026-10-08 follow-up): the Bench links row carries a Tests
#     link and a /systems/<key> link to the top code's primary system ----

bench_page = client.get(f"/v/{VIN}")
check("bench page responds 200", bench_page.status_code == 200, str(bench_page.status_code))
check("the bench links row carries a Tests link",
      f'href="/v/{VIN}/tests"' in bench_page.text, "no /tests link on the bench page")
check("the bench links row carries a /systems/<key> link",
      f"/v/{VIN}/systems/" in bench_page.text, "no /systems/<key> link on the bench page")


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


# --- N1: the step-6 result sheet's hypothesis list is embedded server-side
#     (a #job-hyp-data JSON script block), not only fetched async at page
#     parse time -- the race the mechanic review reproduced twice (the
#     dropdown opening with only the placeholder, no hypothesis options,
#     while job.js's one-shot fetch was still in flight) cannot happen if
#     the data is already sitting in the page's own HTML. The headless-Edge
#     CDP section below drives the real page and confirms the dialog's
#     <select> is populated the instant it opens, with no wait. -----------

step6_data = client.get(f"/v/{VIN}/job", params={"step": "6"})
check("?step=6 responds 200 (for the embedded hypothesis data check)",
      step6_data.status_code == 200, str(step6_data.status_code))
_hyp_json_start = step6_data.text.find('id="job-hyp-data"')
check('step 6 embeds a server-rendered "#job-hyp-data" JSON script block',
      _hyp_json_start >= 0, "no #job-hyp-data script tag found on ?step=6")
if _hyp_json_start >= 0 and fresh:
    _script_open = step6_data.text.find(">", _hyp_json_start) + 1
    _script_close = step6_data.text.find("</script>", _script_open)
    _embedded_raw = step6_data.text[_script_open:_script_close]
    try:
        _embedded_hyps = json.loads(_embedded_raw)
    except Exception as exc:  # noqa: BLE001
        _embedded_hyps = None
        check("the embedded hypothesis JSON parses", False, f"{exc}: {_embedded_raw[:200]}")
    if _embedded_hyps is not None:
        check("the embedded hypothesis JSON parses", True)
        check("the just-added hypothesis is present in the embedded JSON "
              "(available the instant the page renders, before any fetch)",
              any(h.get("id") == fresh["id"] for h in _embedded_hyps),
              str([h.get("id") for h in _embedded_hyps]))
        check("the embedded JSON excludes deleted hypotheses",
              all(not h.get("deleted") for h in _embedded_hyps), str(_embedded_hyps))


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

    # Mechanic review #3, N5: this used to assert only `current != 7`, which
    # a chip stuck at 1 (R2's real bug -- flow_bridge.py's step 1 required
    # an open *visit*, which this test's own /job/open seed never creates)
    # would also satisfy, so a chip frozen at 1 passed as "moved forward".
    # The real expected value, given exactly this test's own flow (intake
    # via /job/open with no separate visit, no step-2 symptom recorded,
    # real-corpus codes/verdict already on file, one hypothesis confirmed
    # with one linked Fail result) is 2 -- intake and hypotheses both now
    # read complete, tests sits at in_progress (1/22, which correctly does
    # not block), and step 2 (no symptom filed in this flow) is the first
    # real gap left. Asserting the specific number -- not just "!= 7" or
    # "!= 1" -- is what actually proves R2's fix: that progress is read off
    # the step criteria alone, with the visit optional.
    flow_after = client.get(f"/api/vehicles/{VIN}/flow").json()
    check("the job progress chip moves forward to the real next gap, step 2, "
          "once step 7 is resolved -- not stuck at step 1 for want of an open "
          "visit (R2)",
          flow_after.get("current") == 2, str(flow_after.get("current")))


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
            cdp_job_id = None
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"http://127.0.0.1:{port}/v/{VIN}/job/open",
                                           data=data, method="POST"), timeout=30)
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/vehicles/{VIN}/job", timeout=10) as r:
                    cdp_job_id = json.loads(r.read().decode("utf-8"))["job"]["id"]
                # N1/N2 (real-browser checks below): a hypothesis to populate
                # the result sheet's dropdown with, seeded the same real way
                # (a POST, server-side) rather than faked in the browser.
                hyp_data = urllib.parse.urlencode(
                    {"text": "cdp-check hypothesis", "step": "6"}).encode()
                urllib.request.urlopen(
                    urllib.request.Request(
                        f"http://127.0.0.1:{port}/v/{VIN}/job/{cdp_job_id}/hypotheses",
                        data=hyp_data, method="POST"), timeout=30)
            except Exception as exc:  # noqa: BLE001
                check("seeding a job (and a hypothesis) on the UX-check server", False, str(exc))

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
                                "var c = document.getElementById('job-call') || document.getElementById('step-7');"
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
                            "var c = document.getElementById('job-call') || document.getElementById('step-7');"
                            "if (!c) return {gap: -1};"
                            "var hb = h ? h.getBoundingClientRect().bottom : 0;"
                            "var cb = c.getBoundingClientRect().top;"
                            "return {gap: cb - hb};"
                            "})())"
                        ),
                        "returnByValue": True,
                    })
                    gap_val = json.loads(gap2.get("result", {}).get("value", "{}")).get("gap", gap_val)
                    # 2026-10-26: the page now opens on search + the one-line call, so the
                    # first useful content (the call) is what must start within 200px.
                    check("step 7's content (the call) starts within 200px below the sticky header",
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

                    # --- item 4 (400px clipping report): same tab, just
                    # re-emulated at 400px -- the one 400px screenshot this
                    # session is allowed, plus the bounding-rect check that
                    # the vbar's "..." (More) button is fully on-screen and
                    # nothing had to grow a page-level horizontal scrollbar
                    # to get it there. -----------------------------------
                    print("=== 400px CDP: vbar \"...\" button + one screenshot ===")
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 400, "height": 800, "deviceScaleFactor": 1, "mobile": True,
                    })
                    time.sleep(0.4)

                    vmore_rect = cdp.send("Runtime.evaluate", {
                        "expression": (
                            "(() => { const el = document.querySelector('.vbar .vmore'); "
                            "if (!el) return JSON.stringify(null); "
                            "const r = el.getBoundingClientRect(); "
                            "return JSON.stringify({top: r.top, left: r.left, right: r.right, "
                            "width: r.width, height: r.height}); })()"),
                        "returnByValue": True,
                    })
                    vmore_box = json.loads(vmore_rect.get("result", {}).get("value", "null"))
                    check("the vbar's \"...\" (More) button is present at 400px",
                          vmore_box is not None, str(vmore_box))
                    if vmore_box is not None:
                        check("the \"...\" button has a real, non-zero box (not clipped away)",
                              vmore_box["width"] > 0 and vmore_box["height"] > 0, str(vmore_box))
                        check("the \"...\" button sits fully inside the 400px viewport",
                              vmore_box["left"] >= 0 and vmore_box["right"] <= 400 + 1,
                              str(vmore_box))

                    overflow400 = cdp.send("Runtime.evaluate", {
                        "expression": (
                            "JSON.stringify({sw: document.documentElement.scrollWidth, "
                            "cw: document.documentElement.clientWidth})"),
                        "returnByValue": True,
                    })
                    dims400 = json.loads(overflow400.get("result", {}).get("value", "{}"))
                    sw400, cw400 = dims400.get("sw", 0), dims400.get("cw", 0)
                    check("no page-level horizontal overflow at 400px either",
                          sw400 <= cw400 + 1, f"scrollWidth={sw400} clientWidth={cw400}")

                    out_path_400 = SCRATCHPAD / "job_step7_400.png"
                    shot400 = cdp.send("Page.captureScreenshot",
                                      {"format": "png", "captureBeyondViewport": False})
                    out_path_400.write_bytes(__import__("base64").b64decode(shot400["data"]))
                    check("400px screenshot job_step7_400.png captured",
                         out_path_400.exists() and out_path_400.stat().st_size > 0,
                         str(out_path_400))
                    if out_path_400.exists():
                        print(f"  wrote {out_path_400} ({out_path_400.stat().st_size} bytes)")

                    # --- N1/N2: the real page, real clicks, same tab/session
                    #     this file is allowed (no second Edge instance) --
                    #     step 6's result sheet populates its hypothesis
                    #     dropdown the instant it opens (no async race to
                    #     lose), and the step6-status counter is never
                    #     stale by the time the dialog has actually closed
                    #     (R3/N2's save-complete signal). --------------------
                    print("=== same tab: step 6 result sheet, N1 (no-race dropdown) + N2 (counter) ===")
                    cdp.send("Emulation.setDeviceMetricsOverride", {
                        "width": 768, "height": 1024, "deviceScaleFactor": 1, "mobile": False,
                    })
                    cdp.send("Page.navigate", {"url": f"http://127.0.0.1:{port}/v/{VIN}/job?step=6"})

                    step6_ready = False
                    deadline6 = time.time() + 8
                    while time.time() < deadline6:
                        probe6 = cdp.send("Runtime.evaluate", {
                            "expression": "JSON.stringify(!!document.querySelector('.result-sheet-trigger'))",
                            "returnByValue": True,
                        })
                        if probe6.get("result", {}).get("value") == "true":
                            step6_ready = True
                            break
                        time.sleep(0.3)
                    check("step 6 loaded with at least one 'Record result' trigger (job.js ran)",
                          step6_ready, "no .result-sheet-trigger appeared within 8s")

                    if step6_ready:
                        # N1: click "Record result" and read the dropdown back
                        # with NO wait in between -- same tick, no setTimeout,
                        # no poll. If the dropdown depended on an in-flight
                        # fetch (the original bug), this would see only the
                        # placeholder.
                        n1_probe = cdp.send("Runtime.evaluate", {
                            "expression": (
                                "(function(){"
                                "var btn = document.querySelector('.result-sheet-trigger');"
                                "btn.click();"
                                "var sel = document.querySelector('dialog.result-sheet select[name=\"hypothesis_id\"]');"
                                "if (!sel) return JSON.stringify({ok:false});"
                                "var opts = Array.prototype.map.call(sel.options, function(o){return {v:o.value, t:o.textContent};});"
                                "return JSON.stringify({ok:true, opts:opts});"
                                "})()"
                            ),
                            "returnByValue": True,
                        })
                        n1_data = json.loads(n1_probe.get("result", {}).get("value", "{}"))
                        check("Record result opens a sheet with a hypothesis <select> (N1)",
                              n1_data.get("ok") is True, str(n1_data))
                        n1_opts = n1_data.get("opts") or []
                        check("the dropdown already lists the seeded hypothesis the instant it "
                              "opens -- not just the empty placeholder (N1, the load-bearing check)",
                              any("cdp-check hypothesis" in (o.get("t") or "") for o in n1_opts),
                              str(n1_opts))

                        # N2: fill the sheet (real hypothesis picked, so the
                        # N1 unlinked-save gate doesn't intercept this run)
                        # and save, then poll tightly for the dialog to
                        # actually close (which, after the fix, only happens
                        # once refreshCounters() has resolved) -- the instant
                        # it's gone, step6-status must already show the real
                        # count, not the stale "Not started 0/" it carried
                        # before any result existed.
                        cdp.send("Runtime.evaluate", {
                            "expression": (
                                "(function(){"
                                "var dlg = document.querySelector('dialog.result-sheet');"
                                "var fail = dlg.querySelector('input[name=\"result\"][value=\"fail\"]');"
                                "fail.checked = true; fail.dispatchEvent(new Event('change'));"
                                "dlg.querySelector('textarea[name=\"reason\"]').value = 'cdp check leak';"
                                "var sel = dlg.querySelector('select[name=\"hypothesis_id\"]');"
                                "for (var i = 0; i < sel.options.length; i++) {"
                                "  if (sel.options[i].textContent.indexOf('cdp-check hypothesis') !== -1) { sel.selectedIndex = i; break; }"
                                "}"
                                "dlg.querySelector('[data-save]').click();"
                                "return '1';"
                                "})()"
                            ),
                            "returnByValue": True,
                        })
                        dialog_gone = False
                        deadline_save = time.time() + 5
                        while time.time() < deadline_save:
                            still_open = cdp.send("Runtime.evaluate", {
                                "expression": "JSON.stringify(!!document.querySelector('dialog.result-sheet'))",
                                "returnByValue": True,
                            })
                            if still_open.get("result", {}).get("value") == "false":
                                dialog_gone = True
                                break
                            time.sleep(0.15)
                        check("the result-sheet dialog actually closes after Save (save completed)",
                              dialog_gone, "dialog.result-sheet still present after 5s")
                        if dialog_gone:
                            status_probe = cdp.send("Runtime.evaluate", {
                                "expression": (
                                    "(function(){var s = document.querySelector('.step6-status');"
                                    "return s ? s.textContent : null;})()"
                                ),
                                "returnByValue": True,
                            })
                            status_text = status_probe.get("result", {}).get("value") or ""
                            check("step6-status is NOT still the stale pre-save count the instant "
                                  "the dialog closes -- no reload, no extra wait (N2)",
                                  "Not started 0/" not in status_text, repr(status_text))
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
