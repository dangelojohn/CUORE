"""Smoke checks for the mechanic-vs-driver timeline.

Same posture as ``check_dossier_view.py``: ``CUORE_STATE_DIR`` is pointed at
a throwaway directory BEFORE cuore is imported, so symptom reports/notes
written here never land in the bench's real state. The MES log corpus is
NOT overridden -- VIN ZASFAKPN5J7B88115's real corpus (chronic EVAP trio) is
the fixture.

``cuore.app.create_app`` may not yet wire ``cuore.api.timeline`` (another
agent may own the next edit to ``app.py``) -- this file includes it itself,
defensively, so it is self-sufficient today and a harmless no-op once
``app.py`` is updated.

Run:
    .venv/Scripts/python.exe cuore/tests/check_timeline.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-timeline-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.api import timeline as timeline_api  # noqa: E402
from cuore.services import timeline_bridge  # noqa: E402
from mes import code_feel  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic EVAP trio

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


app = create_app()
existing_paths = {getattr(r, "path", None) for r in app.routes}
if "/api/vehicles/{vin}/timeline" not in existing_paths:
    app.include_router(timeline_api.router, prefix="/api")

client = TestClient(app)


# --- build_timeline() directly, against the real corpus --------------------

view = timeline_bridge.build_timeline(VIN)

check("vin echoed", view["vin"] == VIN)
check("range has a start/end", bool(view["range"]["start"]) and bool(view["range"]["end"]))

lane_ids = {lane["id"] for lane in view["lanes"]}
expected_lane_ids = {"mil", "evap", "network", "body", "chassis", "engine_other",
                     "clears", "symptoms", "notes", "work", "conditions"}
check("every expected lane is present", expected_lane_ids <= lane_ids, str(lane_ids))

evap_lane = next(lane for lane in view["lanes"] if lane["id"] == "evap")
check("EVAP lane has at least one bar", len(evap_lane["events"]) >= 1, str(evap_lane))

evap_corr = next((c for c in view["correlation"] if c["family"] == "EVAP"), None)
check("EVAP correlation entry present", evap_corr is not None, str(view["correlation"]))
check("EVAP occurrences >= 4", bool(evap_corr) and evap_corr["occurrences"] >= 4,
      str(evap_corr))
check("EVAP verdict starts with no-symptom with zero symptoms logged",
      bool(evap_corr) and evap_corr["verdict"] == "no symptom reports yet",
      str(evap_corr))
check("findings mention EVAP", any("EVAP" in f for f in view["findings"]), str(view["findings"]))

# Pick a timestamp inside the EVAP occurrence window to post symptoms near.
evap_occ_ts = None
for run in evap_lane["events"]:
    evap_occ_ts = run["t"]
    break
check("found an EVAP occurrence timestamp to test against", bool(evap_occ_ts))


# --- posting a drives_normally symptom near an EVAP session -----------------

posted = client.post(f"/api/vehicles/{VIN}/symptoms", json={
    "at": evap_occ_ts, "tags": ["drives_normally"], "text": "no complaints"})
check("posting a symptom responds 200", posted.status_code == 200, str(posted.text))

view2 = timeline_bridge.build_timeline(VIN)
evap_corr2 = next(c for c in view2["correlation"] if c["family"] == "EVAP")
check("verdict becomes 'no reported symptom' after a nearby drives_normally report",
      evap_corr2["verdict"] == "no reported symptom", str(evap_corr2))

rough = client.post(f"/api/vehicles/{VIN}/symptoms", json={
    "at": evap_occ_ts, "tags": ["rough_idle"], "text": "idle felt rough"})
check("posting a second symptom responds 200", rough.status_code == 200, str(rough.text))

view3 = timeline_bridge.build_timeline(VIN)
evap_corr3 = next(c for c in view3["correlation"] if c["family"] == "EVAP")
check("verdict becomes 'co-occurs with rough_idle' once a drivability tag is near",
      evap_corr3["verdict"] == "co-occurs with rough_idle", str(evap_corr3))


# --- validation ---------------------------------------------------------

bad_tag = client.post(f"/api/vehicles/{VIN}/symptoms", json={
    "at": "2026-09-25T12:00:00", "tags": ["not_a_tag"]})
check("invalid tag -> 400", bad_tag.status_code == 400, str(bad_tag.status_code))

bad_combo = client.post(f"/api/vehicles/{VIN}/symptoms", json={
    "at": "2026-09-25T12:00:00", "tags": ["drives_normally", "rough_idle"]})
check("drives_normally + rough_idle -> 400", bad_combo.status_code == 400,
      str(bad_combo.status_code))

listed = client.get(f"/api/vehicles/{VIN}/symptoms")
check("listing symptoms responds 200", listed.status_code == 200)
check("listing carries what was posted", len(listed.json()["symptoms"]) >= 2,
      str(listed.json()))
sid = listed.json()["symptoms"][0]["id"]
hidden = client.post(f"/api/vehicles/{VIN}/symptoms/{sid}/hide")
check("hiding a symptom responds 200", hidden.status_code == 200, str(hidden.text))


# --- code feel ------------------------------------------------------------

p0455_entry = code_feel.lookup("P0455")
check("P0455 feel lookup returns a sourced entry",
      p0455_entry is not None and p0455_entry["confidence"] != code_feel.UNKNOWN,
      str(p0455_entry))

feel_resp = client.get(f"/api/vehicles/{VIN}/code/P0455/feel")
check("code feel endpoint responds 200", feel_resp.status_code == 200)
feel_body = feel_resp.json()
check("code feel endpoint carries the feel entry", feel_body["feel"] is not None)
check("code feel endpoint carries this car's pattern",
      "pattern" in feel_body and "occurrences" in feel_body["pattern"], str(feel_body))

conditions_lane = next(lane for lane in view["lanes"] if lane["id"] == "conditions")
p0455_warn = next((e for e in conditions_lane["events"]
                   if "P0455" in e["label"] and e["severity"] == "warn"), None)
check("a P0455 conditions event flags fuel above 85%",
      p0455_warn is not None and "85" in p0455_warn["detail"], str(conditions_lane["events"]))


# --- symptoms never feed mes.verdict's evidence gate -----------------------

from mes import verdict as verdict_mod  # noqa: E402

check("mes.verdict module has no 'symptoms' attribute/import",
      not hasattr(verdict_mod, "symptoms") and "symptoms" not in verdict_mod.__dict__)


print(f"ran {checks} checks")
if failures:
    print(f"{len(failures)} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
