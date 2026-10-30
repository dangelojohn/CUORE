"""Checks for the liveboard: ``cuore.services.liveboard_bridge`` and
``cuore/api/liveboard.py``.

Same posture as ``cuore/tests/check_live_ui_api.py``/``check_jobs_page.py``:
plain script, no mocking framework, ``CUORE_STATE_DIR`` pointed at a
throwaway directory BEFORE anything is imported so this never touches the
bench's real job ledger.

Seven checks, plus a Freeze frame panel group (9):
  1. ``board`` groups ``engine_coolant_temp`` under "temperatures" and
     ``battery_voltage`` under "voltage".
  2. A coolant value above its sourced alarm grades "excessive" with text
     mentioning coolant.
  3. A channel with no sourced band grades "unknown".
  4. ``rates`` has engine RPM polled faster than coolant temperature.
  5. ``GET /api/liveboard/{vin}`` returns 200.
  6. A snapshot with coolant above its alarm creates a "cooling" hypothesis
     on the current job with a "live" evidence ref, and a second snapshot
     attaches to that same hypothesis rather than duplicating it.
  7. A fuel level inside the 15-85% window adds evidence_for on an open
     EVAP hypothesis.
  9. Freeze frame panel (``cuore.live.ops`` monkeypatched with tonight's real
     shapes -- stored P0440, 46 PIDs, including fuel_level 28.6 and
     commanded_evap_purge 18.0): a capture reaches "done" and its frame
     table carries both; Save writes "obd_dtcs"/"freeze_frame"/"pid"/
     "readiness" observations all with ``is_from_car`` true and returns a
     ``SCAN_`` id; Stop mid-capture ends with ``partial=True``; the
     liveboard page renders Start/Stop/Save/Discard.

Run:
    .venv/Scripts/python.exe cuore/tests/check_liveboard.py
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile
import time
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-liveboard-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401  -- side effect: mes on sys.path
from cuore.app import create_app  # noqa: E402
from cuore.live import ops as live_ops_mod  # noqa: E402
from cuore.live import store as live_store_mod  # noqa: E402
from cuore.services import cache, liveboard_bridge  # noqa: E402

from mes import jobs as jobs_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want, extra: str = "") -> None:
    detail = f"got {got!r} want {want!r}"
    if extra:
        detail += f" ({extra})"
    check(label, got == want, detail)


# --- 1. board grouping ------------------------------------------------------

board = liveboard_bridge.board(VIN)

group_of = {}
for g in board["groups"]:
    for ch in g["channels"]:
        group_of[ch["id"]] = g["id"]

check_eq("coolant grouped under temperatures", group_of.get("engine_coolant_temp"), "temperatures")
check_eq("battery grouped under voltage", group_of.get("battery_voltage"), "voltage")
check("board lists all_channel_ids", len(board["all_channel_ids"]) > 0)
# 2026-10-14 car: Start on the board was refused (HTTP 400) because
# all_channel_ids carried esim_status, a placeholder with no readable DID.
from cuore.live import channels as _ch
try:
    _ch.resolve_channels(board["all_channel_ids"], "")
    _ok, _err = True, ""
except Exception as _e:  # noqa: BLE001
    _ok, _err = False, str(_e)
check("every id the board asks the poller for is pollable", _ok, _err)
check("esim_status placeholder is not polled", "esim_status" not in board["all_channel_ids"])
check("board carries the read-only notice", "passenger" in board["notice"].lower())

# A learned, unscaled TCM DID (cuore.live.fullscan's discovery sweep,
# cuore.live.learned.record_did_answer) shows up under its own board key,
# never mixed into the polled channel list, and never claims a meaning.
from cuore.live import learned as learned_mod  # noqa: E402

learned_mod.record_did_answer(VIN, "TCM", "1018", ["01", "02"], source="check_liveboard")
board_with_did = liveboard_bridge.board(VIN)
did_channels = board_with_did.get("learned_did_channels", [])
check("liveboard lists the learned TCM DID", any(c.get("id") == "tcm_did_1018"
                                                 for c in did_channels), did_channels)
if did_channels:
    ch = next(c for c in did_channels if c.get("id") == "tcm_did_1018")
    check_eq("learned DID channel's system is transmission_driveline", ch.get("system"),
             "transmission_driveline")
    check("learned DID channel is labelled 'learned, unscaled'",
         "learned, unscaled" in ch.get("label", ""), ch)
    check("learned DID channel never claims a decoded meaning",
         ch.get("scale") == "unknown" and "bytes" in ch, ch)
    check("learned TCM DID is never in the polled channel list",
         "tcm_did_1018" not in board_with_did.get("all_channel_ids", []))


# --- 2. coolant above alarm -> excessive, text mentions coolant ------------

hot = liveboard_bridge.evaluate("engine_coolant_temp", 140.0)
check_eq("coolant 140C grades excessive", hot["level"], "excessive")
check("coolant excessive text mentions coolant", "coolant" in hot["text"].lower(), hot["text"])


# --- 3. no band -> unknown --------------------------------------------------

unknown = liveboard_bridge.evaluate("intake_air_temp", 25.0)
check_eq("IAT (no sourced band) grades unknown", unknown["level"], "unknown")


# --- 4. rates: rpm faster than coolant --------------------------------------

rpm_hz = board["rates"].get("engine_rpm")
coolant_hz = board["rates"].get("engine_coolant_temp")
check("rpm and coolant both rated", rpm_hz is not None and coolant_hz is not None,
     f"rpm={rpm_hz!r} coolant={coolant_hz!r}")
if rpm_hz is not None and coolant_hz is not None:
    check("rpm polled faster than coolant", rpm_hz > coolant_hz,
         f"rpm={rpm_hz} coolant={coolant_hz}")


# --- 5. API 200 --------------------------------------------------------------

app = create_app()
client = TestClient(app)
resp = client.get(f"/api/liveboard/{VIN}")
check_eq("GET /api/liveboard/{vin} status", resp.status_code, 200, resp.text[:200])
if resp.status_code == 200:
    body = resp.json()
    check("API board response has groups", "groups" in body and len(body["groups"]) > 0)


# --- 6. snapshot -> job: cooling hypothesis seeded then reused -------------

job = jobs_mod.open(VIN, technician="check_liveboard", complaint="overheating test")
job_id = job["id"]

result1 = liveboard_bridge.attach_snapshot_to_job(VIN, "snap_cooling_1",
                                                  {"engine_coolant_temp": 140.0})
check_eq("first hot snapshot: 1 value out of range", result1["out_of_range"], 1)
check("first hot snapshot created a new hypothesis", len(result1["new_hypotheses"]) == 1,
     repr(result1))

job_after1 = jobs_mod.get(job_id)
cooling_hyps = [h for h in job_after1["hypotheses"]
               if (h.get("system") or "").strip().lower() == "cooling"]
check_eq("exactly one cooling hypothesis after first snapshot", len(cooling_hyps), 1)
if cooling_hyps:
    hyp = cooling_hyps[0]
    check_eq("cooling hypothesis starts open", hyp["status"], "open")
    live_refs = [r for r in hyp["evidence_for"] if r.get("kind") == "live"]
    check("cooling hypothesis has a live evidence ref", len(live_refs) == 1, repr(hyp))
    check("live ref points at the snapshot id",
         any(r.get("id") == "snap_cooling_1" for r in live_refs))

result2 = liveboard_bridge.attach_snapshot_to_job(VIN, "snap_cooling_2",
                                                  {"engine_coolant_temp": 150.0})
check("second hot snapshot creates no new hypothesis", len(result2["new_hypotheses"]) == 0,
     repr(result2))

job_after2 = jobs_mod.get(job_id)
cooling_hyps2 = [h for h in job_after2["hypotheses"]
                if (h.get("system") or "").strip().lower() == "cooling"]
check_eq("still exactly one cooling hypothesis after second snapshot", len(cooling_hyps2), 1)
if cooling_hyps2:
    live_refs2 = [r for r in cooling_hyps2[0]["evidence_for"] if r.get("kind") == "live"]
    check_eq("cooling hypothesis now has two live refs", len(live_refs2), 2)


# --- 7. in-window fuel level -> evidence_for on an open EVAP hypothesis ----

evap_hyp = jobs_mod.add_hypothesis(job_id, "EVAP: test hypothesis", system="EVAP")
result3 = liveboard_bridge.attach_snapshot_to_job(VIN, "snap_fuel_1", {"fuel_level": 50.0})

job_after3 = jobs_mod.get(job_id)
evap_now = next(h for h in job_after3["hypotheses"] if h["id"] == evap_hyp["id"])
verify_refs = [r for r in evap_now["evidence_for"]
              if "verification possible" in (r.get("label") or "").lower()]
check("in-window fuel level adds a verification-possible ref to the EVAP hypothesis",
     len(verify_refs) == 1, repr(evap_now))
check("fuel snapshot-to-job ran without error", isinstance(result3, dict))


# --- 8. MECHANIC_REVIEW_3_TESTS_SYSTEMS_LIVE_2026-10-13.md regressions -----

print("--- F2: vehicle name is never (unnamed vehicle), cold server ---")
cache.clear()
cold_client = TestClient(create_app())
cold_page = cold_client.get(f"/v/{VIN}/liveboard")
check("cold /liveboard responds 200", cold_page.status_code == 200)
check("cold /liveboard never shows (unnamed vehicle)",
     "(unnamed vehicle)" not in cold_page.text)
check("cold /liveboard names the Stelvio", "Stelvio" in cold_page.text)

print("--- F2: visiting /tests first cannot poison /liveboard's vehicle name ---")
poison_client = TestClient(create_app())
poison_client.get(f"/v/{VIN}/tests")
lb_after = poison_client.get(f"/v/{VIN}/liveboard")
check("liveboard still names the Stelvio after /tests was visited first",
     "Stelvio" in lb_after.text and "(unnamed vehicle)" not in lb_after.text)

print("--- F3: Snapshot refuses honestly on zero live channels (same as the map) ---")
lb_js = (ROOT / "cuore" / "web" / "static" / "liveboard.js").read_text(encoding="utf-8")
map_js = (ROOT / "cuore" / "web" / "static" / "systems_map.js").read_text(encoding="utf-8")
check("liveboard.js's snapshot() guards against an empty this.values before POSTing",
     re.search(r"snapshot = function[^{]*\{\s*(?:.*\n)*?.*Object\.keys\(this\.values\)\.length",
              lb_js) is not None)
check("the empty-snapshot refusal text matches the Systems map's own wording",
     "No live readings to snapshot yet." in lb_js
     and "No live readings to snapshot yet." in map_js)

print("--- F4: readability floor -- liveboard.css never renders text under 12px ---")
lb_css = (ROOT / "cuore" / "web" / "static" / "liveboard.css").read_text(encoding="utf-8")
small_fonts = [m for m in re.findall(r"font-size:\s*([0-9.]+)px", lb_css) if float(m) < 12]
check("no font-size under 12px in liveboard.css", not small_fonts, str(small_fonts))


# --- 9. Freeze frame panel --------------------------------------------------

print("--- 9. Freeze frame: capture, Save, Stop (cuore.live.ops monkeypatched) ---")

FF_ECU = "7E8"
#: hex PID -> (name, value, unit); 46 total, including the two tonight's
#: real capture actually showed (fuel_level 28.6%, commanded_evap_purge 18.0%).
FF_PID_VALUES = {f"{i:02X}": (f"PID {i:02X}", float(i), "") for i in range(1, 45)}
FF_PID_VALUES["2F"] = ("Fuel level", 28.6, "%")
FF_PID_VALUES["2E"] = ("Commanded EVAP purge", 18.0, "%")
FF_PIDS = sorted(FF_PID_VALUES)
check_eq("fixture carries 46 supported PIDs", len(FF_PIDS), 46)


def _fake_obd_dtcs(kind: str = "stored", **kw):
    if kind != "stored":
        return {"kind": kind, "dtcs": [], "by_ecu": {}, "bus": "can_c", "cable": "ELM327", "raw": ""}
    return {"kind": "stored", "dtcs": ["P0440"], "by_ecu": {FF_ECU: ["P0440"]},
           "bus": "can_c", "cable": "ELM327", "raw": "43 01 04 40"}


def _fake_obd_supported_pids(**kw):
    return {"by_ecu": {FF_ECU: {"count": len(FF_PIDS), "pids": FF_PIDS, "known_names": []}},
           "raw": {}}


def _fake_obd_readiness(**kw):
    return {"since_clear": {"mil_on": True, "monitors": []}, "this_drive_cycle": {}}


def _make_fake_pid_reader(sleep_s: float = 0.0):
    def _reader(pid: str, **kw):
        if sleep_s:
            time.sleep(sleep_s)
        name, value, unit = FF_PID_VALUES.get(pid, (f"PID {pid}", 0.0, ""))
        return {"pid": pid, "name": name, "raw": "", "by_ecu": {FF_ECU: {"value": value, "unit": unit}},
               "value": value, "unit": unit, "bus": "can_c", "cable": "ELM327"}
    return _reader


def _patch_ops(pid_sleep: float = 0.0) -> None:
    live_ops_mod.obd_dtcs = _fake_obd_dtcs
    live_ops_mod.obd_supported_pids = _fake_obd_supported_pids
    live_ops_mod.obd_readiness = _fake_obd_readiness
    live_ops_mod.obd_pid = _make_fake_pid_reader(pid_sleep)
    live_ops_mod.obd_freeze_frame = _make_fake_pid_reader(pid_sleep)


def _wait_done(vin: str, capture_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    cap = liveboard_bridge.freeze_capture_status(vin, capture_id)
    while cap["status"] == "running" and time.time() < deadline:
        time.sleep(0.02)
        cap = liveboard_bridge.freeze_capture_status(vin, capture_id)
    return cap


# -- fast fakes: full capture, frame table, Save -----------------------------

_patch_ops(pid_sleep=0.0)

cap1 = liveboard_bridge.freeze_capture_start(VIN)
cap1 = _wait_done(VIN, cap1["id"])
check_eq("fast capture reaches done", cap1["status"], "done", repr(cap1.get("error")))
check("fast capture is not partial", cap1["partial"] is False)
check_eq("fast capture carries the stored code", cap1["codes"], ["P0440"])

fuel_rows = [r for t in cap1["frame_tables"] for r in t["rows"] if r["pid"] == "2F"]
purge_rows = [r for t in cap1["frame_tables"] for r in t["rows"] if r["pid"] == "2E"]
check("frame table carries fuel_level 28.6", any(r["value"] == 28.6 for r in fuel_rows), repr(fuel_rows))
check("frame table carries commanded_evap_purge 18.0",
     any(r["value"] == 18.0 for r in purge_rows), repr(purge_rows))
check("frame table is attributed to P0440", all(t["code"] == "P0440" for t in cap1["frame_tables"]))

save1 = liveboard_bridge.freeze_capture_save(VIN, cap1["id"], note="bench capture")
check("save returns a SCAN_ id", str(save1.get("scan_id", "")).startswith("SCAN_"), repr(save1))
check("save returns a Scans link", f"/v/{VIN}/scans/" in (save1.get("scans_url") or ""))

saved_kinds = {"obd_dtcs", "freeze_frame", "pid", "readiness"}
recent = live_store_mod.recent_observations(10_000, vin=VIN)
by_kind = {k: [o for o in recent if o["kind"] == k] for k in saved_kinds}
for k in saved_kinds:
    check(f"save wrote at least one {k!r} observation", len(by_kind[k]) > 0)
    check(f"every saved {k!r} observation is is_from_car",
         all(live_store_mod.is_from_car(o) for o in by_kind[k]), repr(by_kind[k][:1]))

save1_again = liveboard_bridge.freeze_capture_save(VIN, cap1["id"])
check_eq("saving twice is idempotent (same scan id)", save1_again["scan_id"], save1["scan_id"])
check("saving twice is reported as already_saved", save1_again["already_saved"] is True)

# -- slow fakes: Stop mid-capture ends partial -------------------------------

_patch_ops(pid_sleep=0.03)

cap2 = liveboard_bridge.freeze_capture_start(VIN)
check_eq("slow capture starts running", cap2["status"], "running")
stopped = liveboard_bridge.freeze_capture_stop(VIN, cap2["id"])
cap2 = _wait_done(VIN, cap2["id"])
check_eq("stopped capture settles to done", cap2["status"], "done", repr(cap2))
check("stopped capture is partial", cap2["partial"] is True, repr(cap2))

liveboard_bridge.freeze_capture_discard(VIN, cap2["id"])
try:
    liveboard_bridge.freeze_capture_status(VIN, cap2["id"])
    check("discarded capture is gone", False)
except Exception:  # noqa: BLE001 -- NotFound is the services.errors.NotFound subclass
    check("discarded capture is gone", True)

# -- page renders the panel ---------------------------------------------------

ff_client = TestClient(create_app())
ff_page = ff_client.get(f"/v/{VIN}/liveboard")
check_eq("liveboard page 200 with the freeze frame panel", ff_page.status_code, 200)
for needle in ('id="ff-start"', 'id="ff-stop"', 'id="ff-save"', 'id="ff-discard"'):
    check(f"liveboard page renders {needle}", needle in ff_page.text)


# --- 10. Mechanic-first layout (cuore/web/liveboard_view.py, liveboard.html) ---------------------------

print("--- 10. Mechanic layout: call, one Start, Advanced, For this job, dedupe, raw rows, search ---")
from cuore.web import liveboard_view as lbv  # noqa: E402

page = TestClient(create_app()).get(f"/v/{VIN}/liveboard")
html = page.text
check_eq("mechanic liveboard 200", page.status_code, 200)
check("call: not-connected text", 'id="lb-call-line">Connect the car, then Start.<' in html)
check("call: connected text carried for the page script", 'data-on="Watching live.' in html, "data-on missing")
check("call: names the cable for this job", "Cable for this job:" in html and "OBD-II" in html)
check("no raw MES state or VIN stub in the status line",
      "not_running" not in html and "lb-status-vin" not in html)
check("exactly one primary Start button", html.count("lb-btn-primary") == 1, str(html.count("lb-btn-primary")))
check("Snapshot is disabled until a session runs", re.search(r'id="lb-snapshot"[^>]*\bdisabled', html) is not None)
check("Record form is hidden until a session runs",
      re.search(r'<form[^>]*id="lb-record-form"[^>]*\bhidden', html) is not None)
check("Recordings link kept", f'href="/v/{VIN}/recordings' in html and 'id="lb-recordings"' in html)
# the Advanced fold has no nested <details>, so it ends at its first </details>; since 2026-10-28 the sort bar
# and (2026-10-29) the record-selection bar sit between the fold and the reading groups
adv = re.search(r'<details class="lb-adv".*?</details>', html, re.S)
adv_html = adv.group(0) if adv else ""
check("Advanced fold has no nested folds", adv_html.count("<details") == 1)
_after = html[adv.end():] if adv else ""
check("sort and selection bars sit between Advanced and the groups",
      _after.find('id="lb-sortbar"') != -1 and _after.find('id="lb-selbar"') != -1
      and max(_after.find('id="lb-sortbar"'), _after.find('id="lb-selbar"')) < _after.find('<div class="lb-groups"'))
for needle in ('id="lb-demo"', 'id="ff-start"', 'id="bc-start"', 'id="bc-panel"', 'id="ff-panel"'):
    check(f"Advanced fold holds {needle}", needle in adv_html)
check("Start/Snapshot are not inside Advanced", 'id="lb-start"' not in adv_html and 'id="lb-snapshot"' not in adv_html)
check("call comes before the search form (search is below the call)",
      0 < html.find('id="lb-call"') < html.find('class="lb-search"'))
check("compact header row with vehicle name and a Back to Bench link above the h1",
      0 < html.find('id="lb-head"') < html.find('class="lb-h1"') and 'id="lb-back"' in html
      and "Back to Bench" in html and 'id="lb-tabs"' in html)
_css = (Path(__file__).resolve().parents[1] / "web" / "static" / "liveboard.css").read_text(encoding="utf-8")
check("lb-back is a 44 px target and Others/Why folds are 44 px at --fs-md",
      ".lb-back, .lb-tabs-link { min-height: 44px; }" in _css
      and ".lb-others > summary, .lb-why > summary { min-height: 44px; font-size: var(--fs-md); }" in _css)
from cuore.web import liveboard_view as _lbv
check("unit formatter: C -> degC, kpa -> kPa, kph -> km/h, others kept",
      _lbv.fmt_unit("C") == "°C" and _lbv.fmt_unit("°C") == "°C" and _lbv.fmt_unit("kpa") == "kPa"
      and _lbv.fmt_unit("KPH") == "km/h" and _lbv.fmt_unit("bar") == "bar" and _lbv.fmt_unit("V") == "V"
      and _lbv.fmt_unit("%") == "%" and _lbv.fmt_unit("rpm") == "rpm" and _lbv.fmt_unit(None) == "")
check("band note shows °C", "°C normal" in _lbv.band_note({"unit": "C", "band": {"normal": [88, 105]}}))
check("one 'no reading' message, not a wall of dashes",
      html.count("No reading - start a session.") == 1 and html.count(">—<") == 0)

# For this job: the EVAP hypothesis in this throwaway ledger -> its key readings, built from the job
check("For this job group is open and first",
      re.search(r'<details class="lb-group lb-jobgroup"[^>]*\bopen', html) is not None)
jg = re.search(r'lb-jobgroup.*?Why these readings', html, re.S)
jg_html = jg.group(0) if jg else ""
for want in ("Fuel level", "Evap vapour pressure", "Commanded evap purge", "ESIM switch state"):
    check(f"For this job lists {want}", want in jg_html)
check("For this job comes before the other groups", 0 < html.find("lb-jobgroup") < html.find('data-group="temperatures"'))
check("job reason is in a Why fold", "Why these readings" in html and "EVAP job" in html)

# fixture jobs through the pure functions
fixture_board = liveboard_bridge.board(VIN)
v_evap = lbv.build(fixture_board, {"codes": ["P0456-00"], "symptoms": [], "jobs": []})
check_eq("EVAP code alone picks the EVAP readings",
         [r["label"] for r in v_evap["job_rows"]][:3], ["Fuel level", "Evap vapour pressure", "Commanded evap purge"])
v_none = lbv.build(fixture_board, {"codes": [], "symptoms": [], "jobs": []})
check("no job words -> no For this job group", v_none["job_rows"] == [] and not v_none["has_job"])
v_res = lbv.build(fixture_board, {"codes": [], "symptoms": [], "jobs": [
    {"complaint": "", "hypotheses": [{"text": "purge valve stuck", "system": "EVAP", "status": "refuted"}]}]})
check("a refuted hypothesis does not drive the group", v_res["job_rows"] == [])

# dedupe by quantity: one row per quantity, best (confirmed) source on top, the rest folded
labels = [r["label"] for g in v_none["groups"] for r in g["rows"]]
for lab in ("Coolant temperature", "Battery voltage", "Engine speed", "Vehicle speed", "Intake air temperature"):
    check_eq(f"{lab} appears once", labels.count(lab), 1)
by_label = {r["label"]: r for g in v_none["groups"] for r in g["rows"]}
check_eq("coolant: confirmed-source channel is the main row", by_label["Coolant temperature"]["id"], "engine_coolant_temp")
check("coolant: duplicates folded as other sources",
      "ecm_1003" in {o["id"] for o in by_label["Coolant temperature"]["others"]})
check_eq("battery: corroborated channel wins", by_label["Battery voltage"]["id"], "battery_voltage")
check("battery: other sources folded", len(by_label["Battery voltage"]["others"]) >= 2)
check("rendered page has an 'Other sources' fold", "Other sources (" in html)
ids_in_html = re.findall(r'id="lb-chan-([^"]+)"', html)
check("every channel row id is unique on the page", len(ids_in_html) == len(set(ids_in_html)))
check("no channel is dropped by the dedupe",
      set(ids_in_html) == {c["id"] for g in fixture_board["groups"] for c in g["channels"]})
check("plain groups render collapsed", re.search(r'<details class="lb-group" data-group="temperatures">', html) is not None)

# hidden formulas / bitmaps
raw_m = re.search(r'<details class="lb-group lb-raw".*?</details>', html, re.S)
raw_html = raw_m.group(0) if raw_m else ""
main_html = html.replace(raw_html, "") if raw_html else html
check("raw fold holds the IBS formula row", "((J*256)" in raw_html)
check("raw fold holds the pids supported rows", "pids supported 41 60" in raw_html.replace("Pids supported", "pids supported"))
check("formulas and bitmaps are not in the mechanic view",
      "((J*256)" not in main_html and "ids supported" not in main_html)
check("confidence jargon is not printed as a raw tag",
      "SINGLE-SOURCE" not in html and "CORROBORATED" not in html and "UNKNOWN DID" not in html)
check("confidence is a plain-words chip", "one source only" in html and "confirmed by 2+ sources" in html)
check("the chip is only shown with a live value (CSS)", ".lb-chan.has-value .lb-conf" in lb_css
      and re.search(r"\.lb-conf\s*\{[^}]*display:\s*none", lb_css) is not None)

# page-only search
s_html = TestClient(create_app()).get(f"/v/{VIN}/liveboard?q=rpm").text
check("search: Matches group comes first", 0 < s_html.find("lb-matches") < s_html.find("lb-jobgroup"))
check("search: engine speed is in the matches", "Engine speed" in s_html.split("lb-jobgroup")[0])
by_unit = lbv.build(fixture_board, None, "kPa")
check("search by unit finds pressure rows", any("pressure" in r["label"].lower() for r in by_unit["matches"]))
by_cid = lbv.build(fixture_board, None, "ecm_1003")
check("search by channel id finds the coolant row (via its other source)",
      any(r["label"] == "Coolant temperature" for r in by_cid["matches"]))
by_grp = lbv.build(fixture_board, None, "gearbox")
check("search by group finds its rows", len(by_grp["matches"]) >= 3)
nope = lbv.build(fixture_board, None, "zzzqq")
check("search with no match is empty and gives a hint", nope["matches"] == [] and "Try" in nope["hint"])
check("matched rows leave the plain groups (ids stay unique)",
      sum(r["id"] == "engine_rpm" for r in by_unit["matches"])
      + sum(r["id"] == "engine_rpm" for g in by_unit["groups"] for r in g["rows"]) <= 1)

# label fallback in the tab bar
from jinja2 import Environment, FileSystemLoader  # noqa: E402
vt_dir = ROOT / "cuore" / "web" / "templates"
vt = (vt_dir / "_vtabs.html").read_text(encoding="utf-8")
check("_vtabs falls back to its default text when a key is missing", "fallback if (_v == key)" in vt)
env = Environment(loader=FileSystemLoader(str(vt_dir)))
env.globals["t"] = lambda k: k   # a lookup that knows no key
from cuore.web import nav_items as _nav  # noqa: E402
env.globals["nav_menu"] = _nav.nav_menu   # tabs now come from the one nav data source
ctx = dict(bar={"vin": VIN}, tab="liveboard", _more=[], _visible=[], flow_tab_key="", _fb_open=0)
out = env.get_template("_vtabs.html").render(**ctx)
check("tab bar never shows the raw LIVE_BOARD key", "live_board" not in out.lower(), out[:300])
from cuore.web import i18n as _i18n  # noqa: E402
check_eq("'Live board' label exists", _i18n.t("live_board"), "Live board")
real = Environment(loader=FileSystemLoader(str(vt_dir)))
real.globals["t"] = _i18n.t
real.globals["nav_menu"] = _nav.nav_menu
check("tab bar shows 'Live board'", ">Live board<" in real.get_template("_vtabs.html").render(**ctx))
check("liveboard.css: 44 px controls and 16 px text", "min-height: 44px" in lb_css and "--fs-sm: var(--fs-md)" in lb_css)


# --- summary -----------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
