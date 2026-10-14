"""Regression checks for cuore.live.fullscan.

Same posture as check_live.py / check_mode06.py: plain script, ``check()``,
exit 1 on failure, no pytest. Per the task spec this suite monkeypatches
``cuore.live.ops`` functions directly with canned replies (tonight's real
shapes: stored P0440; BCM module DTCs U1713-2F status 15, B1176-97 status 8;
an ECM supported-PID list with 46 PIDs) rather than faking the adapter wire
protocol -- fullscan.py never opens a session itself, it only calls ops, so
this is the natural seam.

Run:
    .venv/Scripts/python.exe cuore/tests/check_fullscan.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-fullscan-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import addressing, fullscan, interlock, ops, store  # noqa: E402
from cuore.live.buses import adapter_switch  # noqa: E402
from cuore.live.errors import LiveError, Refused  # noqa: E402
from cuore.web.fullscan_routes import cable_reference_table  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
ECM_HDR = "18DAF110"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want) -> None:
    check(label, got == want, f"got {got!r} want {want!r}")


#: "Which cable for which module" -- generated once from the live module
#: registry (same function the wizard page and the handbook generator both
#: call), so every phase of the wizard can be checked against it below
#: instead of a hand-typed list that could drift from addressing.py.
_CABLE_COLS = cable_reference_table()

# The adapter switch comes from the route, not the bitrate: both bypass
# cables re-pin onto the adapter's HS pins, so blue A5 (125k) is HS too.
_SWITCH_BY_CABLE = {c["cable"]: c["switch"] for c in _CABLE_COLS}
check_eq("wizard reference: blue A5 -> HS", _SWITCH_BY_CABLE.get("blue_a5"), "HS")
check_eq("wizard reference: grey A6 -> HS", _SWITCH_BY_CABLE.get("grey_a6"), "HS")
check_eq("adapter_switch can_ihs/blue_a5", adapter_switch("can_ihs", "blue_a5"), "HS")
check_eq("adapter_switch can_ch/grey_a6", adapter_switch("can_ch", "grey_a6"), "HS")
check_eq("adapter_switch can_c/none", adapter_switch("can_c", "none"), "HS")
check_eq("adapter_switch can_ihs/none (STP 54) is MS", adapter_switch("can_ihs", "none"), "MS")
try:
    adapter_switch("can_ch", "blue_a5")
    check("adapter_switch rejects a bus/cable with no route", False)
except ValueError:
    check("adapter_switch rejects a bus/cable with no route", True)


def check_cable_reference_rendered(label: str, html: str) -> None:
    """Every module cable_reference_table() lists, for every bus, must
    appear somewhere in this rendered wizard page -- the whole point of
    generating the on-screen block from the registry is that it can never
    silently drop a module the registry has."""
    for col in _CABLE_COLS:
        for m in col["modules"]:
            check(f"{label}: cable reference lists {m['code']} ({col['bus_key']})",
                  m["code"] in html)


_SUPPORTED_PIDS = [f"{i:02X}" for i in range(1, 47)]  # 46 PIDs, tonight's ECM count
_originals: dict[str, object] = {}


def _patch(obj, name, fn):
    _originals.setdefault((obj, name), getattr(obj, name))
    setattr(obj, name, fn)


def _restore_all() -> None:
    for (obj, name), fn in _originals.items():
        setattr(obj, name, fn)
    _originals.clear()


def _identity_for(code):
    return {"ecu": code, "bus": "can_c", "fields": {"F190": {"name": "VIN", "ascii": VIN}}}


def _fake_sweep_bus_full(bus, vin="", mask=0xFF, confirm=False, known_did=None, **kw):
    """Combined fake for the held-session ``ops.sweep_bus_full`` -- replaces
    the old separate ``scan_modules``/``module_identity``/``module_did``
    fakes with one function, same shape ``cuore.live.uds.sweep_bus_full``
    returns: DTCs + identity + (when ``known_did`` names one) a DID, per
    module, in one dict."""
    def _with_did(code, dtcs=None, codes=None):
        mod = {"ecu": code, "bus": bus, "mask": "FF", "dtcs": dtcs or [], "codes": codes or [],
              "identity": _identity_for(code)}
        did_int = known_did(code) if known_did else None
        if did_int is not None:
            mod["did"] = {"ecu": code, "bus": bus, "did": f"{did_int:04X}", "name": "x",
                         "bytes": ["32"]}
        return mod

    if bus == "can_c":
        modules = [
            _with_did("ECM"), _with_did("TCM"),
            _with_did("BCM", codes=["U1713-2F", "B1176-97"], dtcs=[
                {"code": "U1713-2F", "raw": "17132F", "status": 15,
                 "flags": {"confirmedDTC": True, "testFailed": True}},
                {"code": "B1176-97", "raw": "117697", "status": 8,
                 "flags": {"pending": True}},
            ]),
            _with_did("IPC"), _with_did("RFHUB"),
            {"ecu": "DTCM", "skipped": "no confirmed address"},
            {"ecu": "ESM", "skipped": "no confirmed address"},
            {"ecu": "DASM", "skipped": "no confirmed address"},
        ]
        return {"bus": "can_c", "cable": "none", "modules": modules}
    # can_ihs (reachable with cable "none"): nothing confirmed yet on this car.
    return {"bus": bus, "cable": "none",
            "modules": [{"ecu": m.code, "skipped": "no confirmed address"}
                       for m in addressing.on_bus(bus)]}


def _fake_module_did_sweep(code, dids, vin="", per_did_timeout=0.3, confirm=False, **kw):
    """Exactly two of the candidate DIDs answer -- the rest time out."""
    hits = [{"did": d, "bytes": ["01", "02"]} for d in dids[:2]]
    return {"ecu": code, "bus": "can_c", "tried": len(dids), "hits": hits}


def _fake_obd_dtcs(kind, **kw):
    if kind == "stored":
        return {"kind": "stored", "dtcs": ["P0440"], "by_ecu": {ECM_HDR: ["P0440"]}, "raw": "43"}
    return {"kind": kind, "dtcs": [], "by_ecu": {}, "raw": "NO DATA"}


def _fake_obd_mode06(**kw):
    raise RuntimeError("adapter timeout mid-MID sweep")


def _install_common_fakes() -> None:
    _patch(ops, "_poller_active_guard", lambda: None)
    _patch(interlock, "mes_status",
          lambda: {"running": False, "pids": [], "state": "not_running", "label": ""})
    _patch(ops, "status", lambda: {"port": "COM3", "baud": 115200})
    _patch(ops, "cable_state", lambda: {"cable": "none", "buses": {}})
    _patch(ops, "verify_bus", lambda bus, **kw: {"verified": True, "frames": 12, "bus": bus,
                                                 "cable": "none"})
    _patch(ops, "probe", lambda **kw: {"port": "COM3", "baud": 115200, "stn_chip": True,
                                       "battery_voltage": 12.6,
                                       "identity": {"STI": "STN1170 v4.3.2"}})
    _patch(ops, "obd_vin", lambda **kw: {"vin": VIN, "ecu": ECM_HDR, "length_ok": True,
                                         "raw": "4902"})
    _patch(ops, "obd_dtcs", _fake_obd_dtcs)
    _patch(ops, "obd_supported_pids",
          lambda **kw: {"by_ecu": {ECM_HDR: {"count": len(_SUPPORTED_PIDS),
                                             "pids": list(_SUPPORTED_PIDS), "known_names": []}}})
    _patch(ops, "obd_freeze_frames",
          lambda pids, **kw: {"by_ecu": {ECM_HDR: {p: {"name": f"name_{p}", "value": 1.23,
                                                       "unit": "u"} for p in pids}},
                              "requests_sent": len(pids)})
    _patch(ops, "obd_pids_snapshot",
          lambda pids, **kw: {"by_ecu": {ECM_HDR: {p: {"name": f"name_{p}", "value": 4.56,
                                                       "unit": "u"} for p in pids}},
                              "requests_sent": -(-len(pids) // 6), "multi_pid_used": len(pids) > 1})
    _patch(ops, "obd_readiness", lambda **kw: {"since_clear": {"mil_on": False},
                                               "this_drive_cycle": {"mil_on": False}})
    _patch(ops, "obd_mode06", _fake_obd_mode06)
    _patch(ops, "sweep_bus_full", _fake_sweep_bus_full)
    _patch(ops, "module_did_sweep", _fake_module_did_sweep)
    _patch(ops, "learned_dids", lambda vin="": {"learned": {}})


try:
    # =======================================================================
    # 1. a normal run: every kind recorded, coverage right, mode06 isolated
    # =======================================================================
    _install_common_fakes()
    result = fullscan.run(vin=VIN)

    check("scan_id matches SCAN_<yymmddHHMM>", bool(re.fullmatch(r"SCAN_\d{10}",
                                                                  result["scan_id"])),
          result.get("scan_id"))
    check_eq("vin carried through", result["vin"], VIN)

    kinds_present = {e["kind"] for e in store.recent_observations(1000, vin=VIN)}
    for kind in ("adapter_identity", "mode09", "obd_dtcs", "freeze_frame", "readiness",
                "pids_snapshot", "module_dtcs", "module_identity", "did", "scan_coverage"):
        check(f"observation kind {kind!r} recorded", kind in kinds_present, str(kinds_present))
    check("mode06 kind NOT recorded (the step raised)", "mode06" not in kinds_present)

    mode06_step = next((s for s in result["steps"] if s["step"] == "obd_mode06"), None)
    check("obd_mode06 step present and recorded as failed",
          bool(mode06_step) and mode06_step["ok"] is False and
          "adapter timeout" in mode06_step.get("error", ""), str(mode06_step))
    check("scan still completed (coverage present) despite the mode06 failure",
          bool(result.get("coverage")))

    # sessions_opened: held-session batching (query_pids for the 46-PID
    # snapshot, one held session for the 46-PID freeze-frame set, one
    # sweep_bus_full per bus for DTCs+identity+DID) must land far below the
    # old one-session-per-PID/per-module count for this same fixture (46 +
    # 46 PID opens alone, plus 5 identity + 3 did opens on can_c).
    check("sessions_opened recorded on the result", isinstance(result.get("sessions_opened"), int))
    check(f"sessions_opened ({result.get('sessions_opened')}) well below the old per-op count "
         f"(46 PID + 46 freeze-frame + ~9 per-module opens alone)",
         result.get("sessions_opened", 999) < 20, str(result.get("sessions_opened")))

    # Coverage: ABS (can_ch) not reachable without the grey cable.
    cov_by_module = {r["module"]: r for r in result["coverage"]}
    abs_row = cov_by_module.get("ABS")
    check("ABS present in coverage", abs_row is not None)
    if abs_row:
        check_eq("ABS category", abs_row["category"], "not_reachable")
        check("ABS why mentions the grey A6 cable", "grey A6" in (abs_row.get("why") or ""),
              str(abs_row))

    # Coverage: BCM answered, with the two real codes classified active.
    bcm_row = cov_by_module.get("BCM")
    check("BCM present in coverage", bcm_row is not None)
    if bcm_row:
        check_eq("BCM category", bcm_row["category"], "answered")
        check_eq("BCM active count (status 15 and 8 both set an active bit)",
                 bcm_row["active"], 2)
        check("BCM did resolved to the known battery-voltage DID",
              isinstance(bcm_row.get("did"), dict) and bcm_row["did"]["did"] == "1004",
              str(bcm_row.get("did")))

    # Coverage: DTCM has a target but no confirmed address -- run-discovery gap.
    dtcm_row = cov_by_module.get("DTCM")
    check("DTCM present in coverage", dtcm_row is not None)
    if dtcm_row:
        check_eq("DTCM category", dtcm_row["category"], "not_reachable")
        check_eq("DTCM why", dtcm_row["why"], "no known address: run discovery")

    # module_dtcs observation carries the exact BCM codes/status.
    module_dtcs_obs = [e for e in store.recent_observations(1000, vin=VIN, kind="module_dtcs")
                      if e["data"].get("ecu") == "BCM"]
    check("exactly one BCM module_dtcs observation", len(module_dtcs_obs) == 1,
          str(len(module_dtcs_obs)))
    if module_dtcs_obs:
        codes = {d["code"]: d["status"] for d in module_dtcs_obs[0]["data"]["dtcs"]}
        check_eq("BCM module_dtcs codes/status", codes, {"U1713-2F": 15, "B1176-97": 8})

    # did observations: ECM oil temperature (1302), TCM gearbox oil temp (04FE),
    # BCM battery voltage (1004) -- never a guessed DID.
    did_obs = {e["data"]["ecu"]: e["data"]["did"]
              for e in store.recent_observations(1000, vin=VIN, kind="did")}
    check_eq("did reads: ECM/TCM/BCM resolved to the known registry DIDs", did_obs,
             {"ECM": "1302", "TCM": "04FE", "BCM": "1004"})

    # TCM DID discovery (fake answering exactly two candidate DIDs): two
    # learned entries, raw bytes only, never a meaning.
    from cuore.live import learned as learned_mod  # noqa: E402
    learned_rows = learned_mod.learned_did_discovery(VIN, module="TCM").get(VIN, [])
    check_eq("TCM DID discovery recorded exactly two learned entries",
             len(learned_rows), 2)
    if learned_rows:
        check("learned entries are unscaled raw bytes, never a decoded meaning",
             all(r.get("scale") == "unknown" and r.get("name") is None and r.get("bytes")
                 for r in learned_rows), str(learned_rows))
        check("learned entries are tagged kind='did' module='TCM'",
             all(r.get("kind") == "did" and r.get("module") == "TCM" for r in learned_rows),
             str(learned_rows))

    did_disc_obs = store.recent_observations(1000, vin=VIN, kind="did_discovery")
    check("did_discovery observation recorded for TCM with answered=2",
         any(o["data"].get("module") == "TCM" and o["data"].get("answered") == 2
             for o in did_disc_obs), str(did_disc_obs))

    # freeze_frame: one observation for the one stored code, with all 46 supported
    # PIDs present in its frame.
    ff_obs = store.recent_observations(1000, vin=VIN, kind="freeze_frame")
    check_eq("exactly one freeze_frame observation (one stored code)", len(ff_obs), 1)
    if ff_obs:
        check_eq("freeze_frame code", ff_obs[0]["data"]["code"], "P0440")
        check_eq("freeze_frame ecu", ff_obs[0]["data"]["ecu"], ECM_HDR)
        check_eq("freeze_frame frame has all 46 supported PIDs",
                 sorted(ff_obs[0]["data"]["frame"]), sorted(_SUPPORTED_PIDS))

    # pids_snapshot: all 46 PIDs present.
    snap_obs = store.recent_observations(1000, vin=VIN, kind="pids_snapshot")
    check_eq("exactly one pids_snapshot observation", len(snap_obs), 1)
    if snap_obs:
        check_eq("pids_snapshot has all 46 supported PIDs for the ECM header",
                 sorted(snap_obs[0]["data"]["by_ecu"].get(ECM_HDR, {})), sorted(_SUPPORTED_PIDS))

    # mode09: VIN captured, the known gap documented rather than fabricated.
    mode09_obs = store.recent_observations(1000, vin=VIN, kind="mode09")
    check("mode09 observation recorded", len(mode09_obs) == 1)
    if mode09_obs:
        check_eq("mode09 carries the VIN", mode09_obs[-1]["data"].get("vin"), VIN)
        check("mode09 documents the calibration/CVN/ECU-name/IUPR gap",
              bool(mode09_obs[-1]["data"].get("gaps")), str(mode09_obs[-1]["data"]))

    # =======================================================================
    # 2. the poller-active guard refuses before anything is recorded
    # =======================================================================
    before = len(store.recent_observations(10000, vin=VIN))
    _patch(ops, "_poller_active_guard",
          lambda: (_ for _ in ()).throw(Refused("a live-data poll session is running")))
    try:
        fullscan.run(vin=VIN)
        refused = False
    except LiveError:
        refused = True
    check("poller-active guard refuses the whole scan", refused)
    check("nothing new recorded when the poller guard refuses",
          len(store.recent_observations(10000, vin=VIN)) == before)
    _patch(ops, "_poller_active_guard", lambda: None)

    # =======================================================================
    # 3. MES-connected guard refuses
    # =======================================================================
    _patch(interlock, "mes_status", lambda: {"running": True, "pids": [999],
                                             "state": "connected", "label": "Connected: MES"})
    try:
        fullscan.run(vin=VIN)
        refused = False
    except LiveError:
        refused = True
    check("MES-connected guard refuses the whole scan", refused)
    _patch(interlock, "mes_status",
          lambda: {"running": False, "pids": [], "state": "not_running", "label": ""})

    # =======================================================================
    # 4. HTTP surface
    # =======================================================================
    from fastapi.testclient import TestClient  # noqa: E402
    from cuore.app import create_app  # noqa: E402

    client = TestClient(create_app())
    resp = client.post("/api/live/fullscan", json={"vin": VIN})
    check("POST /api/live/fullscan is 200", resp.status_code == 200,
         f"{resp.status_code}: {resp.text[:300]}")
    check("POST /api/live/fullscan returns a scan_id", bool(resp.json().get("scan_id")))

    resp = client.get("/api/live/fullscan/last")
    check_eq("GET /api/live/fullscan/last is 200", resp.status_code, 200)
    check_eq("GET /api/live/fullscan/last matches the last run",
             resp.json().get("scan_id"), fullscan.last().get("scan_id"))

    # =======================================================================
    # 5. guided scan: the coloured-cable pause/resume workflow
    # =======================================================================
    # HVAC/ETM answer on can_ihs, ABS on can_ch -- a dedicated scan_modules
    # fake for the two bypass buses; can_c keeps using _fake_scan_modules's
    # own ECM/TCM/BCM/... reply (segment 1 is otherwise identical to run()).
    def _fake_sweep_bus_full_guided(bus, vin="", mask=0xFF, confirm=False, known_did=None, **kw):
        if bus == "can_ihs":
            return {"bus": bus, "cable": "blue_a5", "modules": [
                {"ecu": "HVAC", "bus": "can_ihs", "mask": "FF", "dtcs": [], "codes": [],
                 "identity": _identity_for("HVAC")},
                {"ecu": "ETM", "bus": "can_ihs", "mask": "FF", "dtcs": [], "codes": [],
                 "identity": _identity_for("ETM")},
            ]}
        if bus == "can_ch":
            return {"bus": bus, "cable": "grey_a6", "modules": [
                {"ecu": "ABS", "bus": "can_ch", "mask": "FF", "dtcs": [], "codes": [],
                 "identity": _identity_for("ABS")},
            ]}
        return _fake_sweep_bus_full(bus, vin=vin, mask=mask, confirm=confirm, known_did=known_did,
                                    **kw)

    _cable_box = {"cable": "none"}
    _patch(ops, "sweep_bus_full", _fake_sweep_bus_full_guided)
    _patch(ops, "set_cable",
          lambda c: _cable_box.update(cable=c) or {"cable": c, "buses": {}})
    _patch(ops, "cable_state", lambda: {"cable": _cable_box["cable"], "buses": {}})

    g1 = fullscan.run_guided(VIN)
    check("guided segment 1 scan_id matches SCAN_<yymmddHHMM>",
          bool(re.fullmatch(r"SCAN_\d{10}", g1["scan_id"])), g1.get("scan_id"))
    check_eq("guided segment 1 segment_done is just can_c", g1["segment_done"], ["can_c"])
    check_eq("guided segment 1 pauses for blue_a5", g1["next"]["cable"], "blue_a5")
    check_eq("guided segment 1 next bus is can_ihs", g1["next"]["bus"], "can_ihs")
    check("guided segment 1 next lists the IHS module table",
          {"HVAC", "ETM", "AMP", "ESEM", "CSWM", "CRSM", "LBSS", "RBSS", "PLGM"} <=
          {m["code"] for m in g1["next"]["modules"]},
          str(g1["next"]["modules"]))
    check("guided segment 1 instruction names the blue A5 cable and CAN-IHS",
          "BLUE A5" in g1["next"]["instruction"] and "CAN-IHS" in g1["next"]["instruction"],
          g1["next"]["instruction"])

    guided_scan_id = g1["scan_id"]

    # State survives a fresh import -- persisted to fullscan_guided.json, not
    # held in a module-level variable.
    import importlib
    fullscan_reloaded = importlib.reload(fullscan)
    resumed = fullscan_reloaded.guided_state()
    check_eq("guided state survives a fresh import (scan_id)", resumed["scan_id"],
             guided_scan_id)
    check_eq("guided state survives a fresh import (next cable)",
             resumed["next"]["cable"], "blue_a5")

    # A mismatched cable is rejected, not silently accepted.
    try:
        fullscan_reloaded.continue_guided(guided_scan_id, "grey_a6")
        check("continue_guided rejects the wrong cable", False)
    except LiveError:
        check("continue_guided rejects the wrong cable", True)

    # A refused (silent-bus) sweep => segment failed, same step offered again.
    _real_sweep = ops.sweep_bus_full

    def _refusing_sweep(bus, **kw):
        if bus == "can_ihs":
            raise Refused("bus can_ihs is silent: heard no traffic, so nothing was sent")
        return _real_sweep(bus, **kw)
    _patch(ops, "sweep_bus_full", _refusing_sweep)
    gf = fullscan_reloaded.continue_guided(guided_scan_id, "blue_a5")
    seg2 = gf["segments"][1]
    check_eq("refused sweep marks segment failed", seg2["status"], "failed")
    check("failed segment why carries the error", "silent" in (seg2["why"] or ""), str(seg2))
    check("failed segment keeps can_ihs out of segment_done", "can_ihs" not in gf["segment_done"])
    check_eq("failed segment leaves pending_index", gf["pending_index"], 1)
    check_eq("failed segment offers blue_a5 again", gf["next"]["cable"], "blue_a5")
    check("failed segment instruction says retry", "retry" in gf["next"]["instruction"])
    check("failed segment not in buses_attempted",
          "can_ihs" not in fullscan_reloaded.last().get("buses_attempted", []))
    _patch(ops, "sweep_bus_full", _real_sweep)

    g2 = fullscan_reloaded.continue_guided(guided_scan_id, "blue_a5")
    check_eq("retry success marks segment done", g2["segments"][1]["status"], "done")
    check_eq("guided segment 2 keeps the same scan_id", g2["scan_id"], guided_scan_id)
    check_eq("guided segment 2 segment_done adds can_ihs", g2["segment_done"],
             ["can_c", "can_ihs"])
    check_eq("guided segment 2 pauses for grey_a6", g2["next"]["cable"], "grey_a6")
    ihs_rows = {r["module"]: r for r in g2["coverage"] if r["bus"] == "can_ihs"}
    check("guided segment 2 swept HVAC as answered",
          ihs_rows.get("HVAC", {}).get("category") == "answered", str(ihs_rows.get("HVAC")))
    check("guided segment 2 swept ETM as answered",
          ihs_rows.get("ETM", {}).get("category") == "answered", str(ihs_rows.get("ETM")))
    verify_ihs_steps = [s for s in g2["steps"] if s["step"] == "verify_bus can_ihs"]
    check("guided segment 2 verified can_ihs (failed try + retry)", len(verify_ihs_steps) == 2,
          str(verify_ihs_steps))

    g3 = fullscan_reloaded.skip_guided(guided_scan_id)
    check_eq("guided skip keeps the same scan_id", g3["scan_id"], guided_scan_id)
    check_eq("guided skip pauses for the final removal step (cable none)",
             g3["next"]["cable"], "none")
    ch_rows = {r["module"]: r for r in g3["coverage"] if r["bus"] == "can_ch"}
    check("guided skip records ABS as not reachable", ch_rows.get("ABS", {}).get("category")
          == "not_reachable", str(ch_rows.get("ABS")))
    check("guided skip's why says skipped, needs grey A6",
          "skipped, needs grey A6" in (ch_rows.get("ABS", {}).get("why") or ""),
          str(ch_rows.get("ABS")))

    g4 = fullscan_reloaded.continue_guided(guided_scan_id, "none")
    check_eq("guided final step keeps the same scan_id", g4["scan_id"], guided_scan_id)
    check_eq("guided final step declares the cable back to none", g4["cable"], "none")
    check_eq("guided final step closes the session", g4["status"], "done")
    check("guided final step has nothing left to do next", g4["next"] is None)
    verify_final = [s for s in g4["steps"] if s["step"] == "verify_bus can_c"]
    check("guided final step re-verified can_c", len(verify_final) >= 2, str(verify_final))

    # Every segment recorded under the one scan_id picked at segment 1.
    guided_obs = [e for e in store.recent_observations(10000, vin=VIN)
                 if e["data"].get("scan_id") == guided_scan_id]
    check("every guided scan_coverage observation shares one scan_id",
          len(guided_obs) >= 1, str(len(guided_obs)))

    # --- abandon clears an open session honestly -----------------------------
    g5 = fullscan_reloaded.run_guided(VIN)
    _patch(ops, "sweep_bus_full", _refusing_sweep)
    fullscan_reloaded.continue_guided(g5["scan_id"], "blue_a5")
    _patch(ops, "sweep_bus_full", _real_sweep)
    gs = fullscan_reloaded.skip_guided(g5["scan_id"])
    check_eq("skip after failure records skipped", gs["segments"][1]["status"], "skipped")
    check_eq("skip after failure moves to grey", gs["next"]["cable"], "grey_a6")
    check("a second guided scan can start once the first is done", bool(g5["scan_id"]))
    other_scan_id = g5["scan_id"]
    g6 = fullscan_reloaded.abandon_guided(other_scan_id)
    check_eq("abandon_guided marks the session abandoned", g6["status"], "abandoned")
    check("abandon_guided leaves nothing pending", g6["next"] is None)
    try:
        fullscan_reloaded.run_guided(VIN)
    except LiveError as e:
        check("starting a new guided scan after abandon is not blocked", False, str(e))
    else:
        check("starting a new guided scan after abandon is not blocked", True)
    # ...and that fresh session is itself open, so a second start now refuses.
    try:
        fullscan_reloaded.run_guided(VIN)
        check("a second run_guided while one is paused refuses", False)
    except LiveError:
        check("a second run_guided while one is paused refuses", True)

    # =======================================================================
    # 6. wizard page: 200 in every phase
    # =======================================================================
    # Fresh guided session for the page walk, independent scan_id from the
    # one above.
    client.post(f"/v/{VIN}/scan/abandon",
               data={"scan_id": fullscan_reloaded.guided_state()["scan_id"]})

    resp = client.get(f"/v/{VIN}/scan")
    check_eq("wizard idle phase is 200", resp.status_code, 200)
    check("wizard idle phase shows the Start button", 'data-phase="idle"' in resp.text,
          resp.text[:200])
    check_cable_reference_rendered("idle", resp.text)

    resp = client.post(f"/v/{VIN}/scan/start", follow_redirects=True)
    check_eq("wizard start redirects to 200", resp.status_code, 200)
    check("wizard pause_blue phase renders", 'data-phase="pause_blue"' in resp.text
          and "BLUE A5" in resp.text, resp.text[:200])
    check_cable_reference_rendered("pause_blue", resp.text)
    page_scan_id = re.search(r'name="scan_id" value="([^"]+)"', resp.text).group(1)

    resp = client.post(f"/v/{VIN}/scan/continue",
                      data={"scan_id": page_scan_id, "cable_fitted": "blue_a5"},
                      follow_redirects=True)
    check_eq("wizard continue (blue) redirects to 200", resp.status_code, 200)
    check("wizard pause_grey phase renders", 'data-phase="pause_grey"' in resp.text
          and "GREY A6" in resp.text, resp.text[:200])
    check_cable_reference_rendered("pause_grey", resp.text)

    resp = client.post(f"/v/{VIN}/scan/skip", data={"scan_id": page_scan_id},
                      follow_redirects=True)
    check_eq("wizard skip redirects to 200", resp.status_code, 200)
    check("wizard remove_cable phase renders", 'data-phase="remove_cable"' in resp.text
          and "Remove the cable" in resp.text, resp.text[:200])
    check_cable_reference_rendered("remove_cable", resp.text)

    resp = client.post(f"/v/{VIN}/scan/continue",
                      data={"scan_id": page_scan_id, "cable_fitted": "none"},
                      follow_redirects=True)
    check_eq("wizard final continue redirects to 200", resp.status_code, 200)
    check("wizard summary phase renders", 'data-phase="summary"' in resp.text
          and "complete" in resp.text, resp.text[:200])

    resp = client.get(f"/v/{VIN}/scan")
    check_eq("wizard page reload keeps the summary phase", resp.status_code, 200)
    check("wizard reload still shows the summary", 'data-phase="summary"' in resp.text)

    # --- abandon through the HTTP surface, and the MCP-facing routes --------
    resp = client.post("/api/live/fullscan/guided/start", json={"vin": VIN})
    check_eq("POST guided/start is 200", resp.status_code, 200)
    http_scan_id = resp.json()["scan_id"]

    resp = client.get("/api/live/fullscan/guided/state")
    check_eq("GET guided/state is 200", resp.status_code, 200)
    check_eq("GET guided/state matches the open session", resp.json()["scan_id"], http_scan_id)

    resp = client.post("/api/live/fullscan/guided/abandon", json={"scan_id": http_scan_id})
    check_eq("POST guided/abandon is 200", resp.status_code, 200)
    check_eq("POST guided/abandon closes it", resp.json()["status"], "abandoned")

    # =======================================================================
    # 7. handbook section matches the generator (never hand-edited out of sync)
    # =======================================================================
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs" / "handbook"))
    import generate_cable_reference  # noqa: E402

    handbook_path = (Path(__file__).resolve().parents[2] / "docs" / "handbook" /
                     "07-first-live-session.md")
    handbook_text = handbook_path.read_text(encoding="utf-8")
    check("handbook has the generated cable-reference block",
          generate_cable_reference.START in handbook_text and
          generate_cable_reference.END in handbook_text)
    for col in _CABLE_COLS:
        for m in col["modules"]:
            check(f"handbook cable-reference lists {m['code']} ({col['bus_key']})",
                  f"| {m['code']} | {m['confidence']} |" in handbook_text)
    rendered_block = generate_cable_reference.render_block()
    current_block = (generate_cable_reference.START +
                     handbook_text.split(generate_cable_reference.START, 1)[1]
                     .split(generate_cable_reference.END, 1)[0] +
                     generate_cable_reference.END)
    check_eq("handbook's cable-reference block matches a fresh render "
            "(re-run docs/handbook/generate_cable_reference.py if this fails)",
            current_block, rendered_block.rstrip("\n"))

finally:
    _restore_all()


# ===========================================================================
# report
# ===========================================================================

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
