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


# --- summary -----------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
