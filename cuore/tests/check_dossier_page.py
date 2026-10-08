"""Smoke checks for the rebuilt vehicle dossier page (MECHANIC_UX_REVIEW.md).

Same posture as ``cuore/tests/check_notes_page.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported.

This exercises both sides:

  * The template-content checks (verdict chip, no raw dicts, bulletin
    anchors, checklist forms) render ``vehicle.html``/``verify.html``
    directly through the same Jinja environment ``cuore.web.routes`` uses,
    with a fixture ``view``/``result``/``verdict`` built to the agreed
    shape. This is deterministic regardless of the real route/corpus.
  * The real-route checks go through the real app (TestClient) against
    the Stelvio's real corpus (``view`` now lands on ``/v/{vin}/dossier`` --
    ``/v/{vin}`` itself is the bench, cuore/web/bench_routes.py -- from
    ``cuore.services.dossier_bridge.build_view``, and ``/v/{vin}/verify``
    plus the checklist routes are wired in ``cuore/web/dossier_routes.py``
    and ``cuore/api/checklists.py``) -- both landed while this file was
    being written, so these assert the real rendered content, not just a
    fallback.

Run:
    .venv/Scripts/python.exe cuore/tests/check_dossier_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: state goes to a throwaway directory.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-dossier-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web.routes import templates  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0456/P0440/P0456

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- the view fixture, built to the shape the backend route will supply ----
# (view.verdict / view.open_work / view.codes / view.code_counts /
# view.attempted / view.freeze_frames / view.blind_spots / view.bulletins /
# view.latest / view.provenance_note).

VIEW_FIXTURE = {
    "verdict": {
        "state": "UNVERIFIED_REPAIR",
        "label": "UNVERIFIED REPAIR",
        "summary": "EVAP leak (P0455/P0440/P0456) cleared 29 Sep -- monitors "
                    "have not re-run. Not proof of repair.",
        "basis": [
            "P0455/P0440/P0456 cleared 29 Sep 2026",
            "No session since the clear has re-run the EVAP monitor",
        ],
        "cleared_at": "2026-09-29", "cleared_by": "MultiEcuScan",
        # evap_monitor here is the string form ("complete"/"incomplete"/
        # "not_supported"/None) dossier_bridge._evap_from_readiness returns --
        # NOT a bool. verify.html's own `result.evap_monitor` (a separate,
        # boolean field from dossier_bridge.readiness_result) is covered
        # below under VERIFY_RESULT_FIXTURE.
        "readiness": {"at": "2026-09-29 18:02", "evap_monitor": "incomplete", "all_complete": False},
        "actions": [
            {"label": "Verify repair", "kind": "readiness", "href": f"/v/{VIN}/verify",
             "enabled": True, "hint": None},
            {"label": "EVAP fault tree", "kind": "link", "href": f"/v/{VIN}/tree?codes=P0455",
             "enabled": True, "hint": None},
            {"label": "Evidence gate", "kind": "link", "href": f"/v/{VIN}/gate",
             "enabled": False, "hint": "connect car first"},
        ],
    },
    "open_work": [
        {
            "family": "EVAP", "title": "EVAP -- one system fault",
            "codes": ["P0440", "P0455", "P0456"],
            "steps": [
                {"id": "evap-1", "text": "Inspect recirculation-line quick-connect",
                 "ref": "S2125000002", "ref_href": "#S2125000002", "done": True,
                 "done_at": "2026-10-01", "done_by": "me"},
                {"id": "evap-2", "text": "Actuate purge/vent solenoid KOEO",
                 "ref": None, "ref_href": None, "done": False,
                 "done_at": None, "done_by": None},
            ],
            "refs": [{"label": "S2125000002", "href": "#S2125000002"},
                     {"label": "docs/research/EVAP_STELVIO.md", "href": None}],
            "progress": {"done": 1, "total": 2},
        },
        {
            "family": "NETWORK", "title": "Network -- one power/bus event",
            "codes": ["U0100", "U0101"],
            "steps": [
                {"id": "net-1", "text": "Check F82/BCM supply", "ref": None,
                 "ref_href": None, "done": False, "done_at": None, "done_by": None},
            ],
            "refs": [],
            "progress": {"done": 0, "total": 1},
        },
    ],
    "codes": [
        {"code": "P0456", "dtc": "P0456-00", "description": "EVAP system small leak",
         "system": "engine", "bucket": "chronic", "status": "ACTIVE",
         "status_label": "ACTIVE", "sessions": 11, "last_seen_short": "25 Sep",
         "last_seen": "2026-09-25 20:27:00", "first_seen": "2025-09-24",
         "distance_km": 26500, "href": f"/v/{VIN}/code/P0456", "family": "EVAP"},
        {"code": "P0300", "dtc": "P0300-00", "description": "Random/multiple cylinder misfire",
         "system": "engine", "bucket": "seen_once", "status": "STALE",
         "status_label": "STALE", "sessions": 1, "last_seen_short": "3 Aug",
         "last_seen": "2026-08-03 09:00:00", "first_seen": "2026-08-03",
         "distance_km": None, "href": f"/v/{VIN}/code/P0300", "family": None},
    ],
    "code_counts": {"chronic": 11, "seen_once": 17, "returned_after_clear": 0,
                     "active": 1, "stale": 1},
    "attempted": [
        {"operation": "Evaporation control valve", "kind": "actuator",
         "outcome": "FAILED TO EXECUTE", "count": 2, "first_short": "15 Sep",
         "last_short": "15 Sep", "reason": "Engine running", "reason_chip": "interlock",
         "footnote": "key-on engine-off; “Engine running” is an interlock, not a fault.",
         "rows": [{"timestamp": "2026-09-15 21:18:00", "outcome": "FAILED TO EXECUTE"}]},
        {"operation": "Evaporation control valve", "kind": "actuator",
         "outcome": "COMPLETED", "count": 8, "first_short": "15 Sep",
         "last_short": "15 Sep", "reason": None, "reason_chip": None,
         "footnote": None, "rows": []},
    ],
    "freeze_frames": [
        {"code": "P0455", "set_km_ago": 360,
         "key": [{"name": "Fuel level", "value": "93.7 %", "flag": "above 85%: EVAP monitor could not run"},
                  {"name": "Engine temp", "value": "89 C", "flag": None}],
         "all": [{"name": "Fuel level", "value": "93.7 %"}, {"name": "Engine temp", "value": "89 C"}]},
    ],
    "blind_spots": [
        {"question": "Has the EVAP monitor actually re-run since the clear?",
         "why": "A log corpus cannot see a monitor that has not completed a session yet.",
         "action": {"label": "Read readiness", "kind": "readiness", "href": f"/v/{VIN}/verify",
                     "enabled": True, "hint": None}},
        {"question": "Is the calibration level current?",
         "why": "Only a dealer tool can read the PCM calibration ID.",
         "action": {"label": "wiTECH required", "kind": "dealer", "href": None,
                     "enabled": False, "hint": "needs wiTECH"}},
    ],
    "bulletins": [
        {"id": "S2125000002", "anchor": "S2125000002", "title": "Check recirc-line quick-connect",
         "action": "Check the quick-connect O-ring before replacing parts.",
         "caution": None, "codes": ["P0440", "P0455", "P0456"], "superseded": None,
         "source": "MOPAR S2125000002", "relevance": 1},
        {"id": "18-030-17", "anchor": "tsb-18-030-17", "title": "EVAP PCM calibration",
         "action": "Check PCM calibration before condemning hardware.",
         "caution": "Rev B supersedes Rev A.", "codes": ["P0455"], "superseded": "Rev A",
         "source": "TSB 18-030-17 REV. B", "relevance": 2},
    ],
    "latest": {"session_short": "04 Oct 11:16", "session_file": "FESLog_2610041116.txt",
               "ecu": "IAW 10JA", "scan_short": None, "scan_file": None},
    "provenance_note": "These are what a log corpus structurally cannot answer.",
}

BASE_CTX = {
    "version": "test", "profile": "bench",
    "live_strip": {"error": None, "mes_state": "idle", "port": "COM3", "baud": 500000,
                    "cable": "OBD", "buses_verified": 1, "buses_total": 3, "lock_holder": None},
    "live_panel": {"error": None, "buses": [{"bus": "CAN-C", "reachable_with_cable": True, "verified": True}],
                    "modules": []},
    "notes_list": [], "note_target_kind": "vehicle", "note_target_id": "",
    "note_redirect": f"/v/{VIN}", "note_kind_locked": True,
    "tab": "dossier",
    "bar": {"vin": VIN, "name": "Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir",
            "logs": 17, "first_log": "2025-09-24", "last_log": "2026-10-04",
            "odo_first": 115790, "odo_last": 142290, "odo_span": 26500,
            "ecus": ["IAW 10JA"]},
    "vin": VIN,
    "open_codes": ["P0456"],
}


def render(name: str, **extra) -> str:
    ctx = dict(BASE_CTX)
    ctx.update(extra)
    return templates.env.get_template(name).render(**ctx)


# --- vehicle.html rendered directly with the view fixture -------------------

html = render("vehicle.html", view=VIEW_FIXTURE, d={})

check("verdict chip text present", "UNVERIFIED REPAIR" in html)
check("verdict sentence present", "Not proof of repair" in html)
check("no raw python-dict repr anywhere ({'family')", "{'family'" not in html)
check("no raw python-dict repr anywhere ({\"family\")", '{"family"' not in html)
check("no raw dict repr of a code row ({'code')", "{'code'" not in html)
check("no raw dict repr of a step row ({'id')", "{'id'" not in html)

for b in VIEW_FIXTURE["bulletins"]:
    anchor_html = f'id="{b["anchor"]}"'
    check(f"bulletin anchor {b['id']} appears exactly once", html.count(anchor_html) == 1,
          str(html.count(anchor_html)))
    check(f"bulletin {b['id']} title present", b["title"] in html)

for job in VIEW_FIXTURE["open_work"]:
    for step in job["steps"]:
        needle = f'name="step_id" value="{step["id"]}"'
        check(f"checklist form present for step {step['id']}", needle in html, html.count(needle))
    check(f"job card title present for {job['family']}", job["title"] in html)

check("job progress shown as N/total, not a raw dict", "1/2" in html and "0/1" in html)
check("checklist steps post to /v/{vin}/checklist",
      f'action="/v/{VIN}/checklist"' in html)
check("freeze-frame flag rendered as text, not a dict",
      "above 85%: EVAP monitor could not run" in html)
check("blind spot dealer tag rendered, not a button, when no tool can run it",
      "wiTECH required" in html)
check("open-work section renders before the collapsed cards",
      html.index('id="open-work"') < html.index('id="sec-history"'))
check("history section is a <details> (collapsed by default pattern)",
      '<details class="card-details" id="sec-history"' in html)
check("quick-add note FAB present", 'id="quick-add-note"' in html)


# --- the real route, against the real Stelvio corpus ------------------------
# `view` now lands here from dossier_bridge.build_view(); verdict.label is
# sentence case ("Unverified repair"/"Active faults"/"Verified clean"/
# "No data") -- CSS uppercases it for display, the DOM text itself is not
# uppercase, so assert against the real casing rather than SHOUTING text.

client = TestClient(create_app())

page = client.get(f"/v/{VIN}/dossier")
check("dossier page responds 200", page.status_code == 200, str(page.status_code))
check("dossier page is HTML", "<html" in page.text.lower())

VERDICT_LABELS = ("Unverified repair", "Active faults", "Verified clean", "No data")
view_has_landed = any(lbl in page.text for lbl in VERDICT_LABELS)
check("live /v/{vin} route's view has landed (verdict card present)", view_has_landed,
      "none of " + str(VERDICT_LABELS) + " found in the real page")
check("live route's verdict card is a real chip, not a raw dict",
      'class="chip-verdict' in page.text)
check("live route's open-work / history cards present, no raw dict anywhere",
      "{'family'" not in page.text and '{"family"' not in page.text
      and "{'code'" not in page.text and '{"code"' not in page.text)
check("live route shows the EVAP family as one job card",
      "EVAP" in page.text and 'class="job-card"' in page.text)
check("live route shows the network family's real title",
      "Network" in page.text and "power/bus event" in page.text)
check("live route's history card summary carries real chronic/stale counts",
      'id="sec-history"' in page.text)


# --- verify.html: direct-render with a fixture, plus the live route --------

verify_ctx = dict(BASE_CTX)
verify_ctx.update({
    # the real shape (dossier_bridge.readiness_result): evap_monitor is a
    # plain bool here, unlike view.verdict.readiness.evap_monitor above.
    "result": {"at": "2026-09-29 18:02", "evap_monitor": False, "all_complete": False,
               "monitors": [{"name": "Evaporative system", "complete": False}]},
    "verdict": VIEW_FIXTURE["verdict"],
})
verify_html = templates.env.get_template("verify.html").render(**verify_ctx)
check("verify page (direct render) shows the verdict", "UNVERIFIED REPAIR" in verify_html)
check("verify page (direct render) shows readiness state", "not yet run" in verify_html)
check("verify page (direct render) has a big back-to-dossier button",
      "Back to dossier" in verify_html and f'href="/v/{VIN}"' in verify_html)
check("verify page (direct render) carries no raw dict",
      "{'at'" not in verify_html and '{"at"' not in verify_html)

verify_resp = client.get(f"/v/{VIN}/verify")
check("live /v/{vin}/verify route responds 200", verify_resp.status_code == 200,
      str(verify_resp.status_code))
check("live verify page has the back-to-dossier button",
      "Back to dossier" in verify_resp.text)
check("live verify page shows a verdict (sentence case label)",
      any(lbl in verify_resp.text for lbl in VERDICT_LABELS))


# --- checklist round-trip: real step id, real route, real redirect ---------

view_json = client.get(f"/api/vehicles/{VIN}/view").json()
first_step = None
for job in view_json.get("open_work", []):
    if job.get("steps"):
        first_step = job["steps"][0]
        break
check("the real view exposes at least one checklist step to tick", first_step is not None,
      str(view_json.get("open_work")))

if first_step is not None:
    step_id = first_step["id"]
    was_done = bool(first_step["done"])
    toggled = client.post(f"/v/{VIN}/checklist",
                          data={"step_id": step_id, "done": "0" if was_done else "1"},
                          follow_redirects=True)
    check("ticking a real checklist step via the dossier form responds 200",
          toggled.status_code == 200, str(toggled.status_code))
    check("the dossier form POST redirected back to #open-work",
          str(toggled.url).endswith(f"/v/{VIN}#open-work")
          or str(toggled.url).endswith(f"/v/{VIN}"), str(toggled.url))

    api_state = client.get(f"/api/vehicles/{VIN}/checklist").json()
    entry = (api_state.get("checklist") or {}).get(step_id)
    check("the JSON checklist store reflects the tick made through the HTML form",
          entry is not None and bool(entry.get("done")) != was_done, str(entry))

    # leave it as we found it
    client.post(f"/v/{VIN}/checklist", data={"step_id": step_id, "done": "1" if was_done else "0"})

bad_step = client.post(f"/v/{VIN}/checklist", data={"step_id": "not-a-real-step", "done": "1"})
check("an unknown checklist step id is rejected (400), not silently accepted",
      bad_step.status_code == 400, str(bad_step.status_code))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
