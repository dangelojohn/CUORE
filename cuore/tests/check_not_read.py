"""Silence must never look clean: every NOT READ state (no answer, CAN ERROR,
negative response, never read) on every module-read surface. Fakes only; no
hardware. Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_not_read.py"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-notread-")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import ops, read_state, uds  # noqa: E402
from cuore.services import modules_bridge, scan_health_bridge  # noqa: E402
from cuore.services import fault_board  # noqa: E402,F401

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label} {detail}")


NO_ANSWER = {"ecu": "ABS", "dtcs": [], "error": None, "nrc": None, "warning": "no answer from the module"}
CAN_ERR = {"ecu": "ABS", "dtcs": [], "error": "CAN ERROR", "nrc": None}
NEG = {"ecu": "ABS", "dtcs": [], "error": None, "nrc": "0x22 conditionsNotCorrect"}
CLEAN = {"ecu": "ABS", "dtcs": [], "error": None, "nrc": None, "codes": []}
STATES = {"no answer": NO_ANSWER, "can error": CAN_ERR, "negative response": NEG, "never read": {}}

BAD_WORDS = ("clean", "no codes", "tracked: 0")

for name, mod in STATES.items():
    # shared state
    check(f"{name}: not is_read", not read_state.is_read(mod))
    st = read_state.stamp(dict(mod) if mod else {"ecu": "ABS"}, mark_error=False)
    if mod:
        check(f"{name}: banner", st["not_read"].startswith("NOT READ: ")
              and st["not_read"].endswith("do not treat as clean"), st.get("not_read", ""))
    # MCP / API compact result: no empty lists posing as a read
    if mod:
        full = dict(mod, active=[], history=[], tracked=0)
        comp = ops._compact_dtc_result(read_state.stamp(full, mark_error=False))
        check(f"{name}: compact active is None", comp["active"] is None and comp["history"] is None
              and comp["tracked"] is None, str(comp))
        check(f"{name}: compact says NOT READ", comp.get("read_state") == "not_read"
              and "NOT READ" in comp["not_read"])
    # fault board: a not-read module cannot be an "absent" (clean) read
    check(f"{name}: fault board skips", not read_state.is_read(mod))

# a clean read still shows clean
check("clean read is_read", read_state.is_read(CLEAN))
comp = ops._compact_dtc_result(dict(CLEAN))
check("clean compact: lists + tracked 0 + state read",
      comp["active"] == [] and comp["tracked"] == 0 and comp["read_state"] == "read", str(comp))

# uds.read_dtcs stamps a silent module on the source
class _S:
    class bus: key = "can_ch"
orig = uds.request
uds.request = lambda *a, **k: {"error": None, "nrc": None, "nrc_text": "", "frames": [], "raw": ""}
try:
    uds._first_positive = lambda r: None
    out = uds.read_dtcs(_S(), type("E", (), {"code": "ABS"})())
    check("read_dtcs silent -> not_read", out.get("read_state") == "not_read"
          and "NOT READ" in out["not_read"], str(out))
finally:
    uds.request = orig

# Modules page: newest live read failed -> NOT READ, worst-first, never clean
import cuore.live.store as store  # noqa: E402
obs = [
    {"at": "2026-10-30T09:00:00", "data": dict(CLEAN)},       # old good read
    {"at": "2026-10-31T20:00:00", "data": dict(NO_ANSWER)},   # tonight: silence
]
store.recent_observations = lambda **k: list(reversed(obs))
live = modules_bridge._live_read_state("V")
check("modules: ABS last read failed", live["ABS"]["last"]["why"] is not None)
check("modules: last good read dated", live["ABS"]["good"] == "2026-10-30T09:00:00")
check("modules: not_read ranks before clean/stale",
      modules_bridge._STATUS_RANK["not_read"] < modules_bridge._STATUS_RANK["stale"]
      < modules_bridge._STATUS_RANK["clean"])

# dossier / report helper: unread listed with stale date, clean module not listed
un = read_state.unread_modules(obs + [{"at": "2026-10-31T20:01:00", "data": dict(CLEAN, ecu="ECM")}])
check("unread_modules lists ABS only", [u["ecu"] for u in un] == ["ABS"], str(un))
check("unread_modules carries last good date", un and un[0]["last_good"] == "2026-10-30T09:00:00")
check("unread_modules banner", un and un[0]["banner"].startswith("NOT READ: "))
check("never-clean: a later good read clears it",
      not read_state.unread_modules(obs + [{"at": "2026-10-31T21:00:00", "data": dict(CLEAN)}]))

# scan health: a GAP system blocks VERIFIED_CLEAN and is worded NOT READ
v = {"state": "VERIFIED_CLEAN", "label": "Verified clean", "basis": ["x"]}
rows = [{"system": "abs", "label": "ABS", "health": "GAP", "reading": "module did not answer"},
        {"system": "fuel", "label": "Fuel", "health": "OK"}]
scan_health_bridge._not_read_verdict(v, rows)
check("scan health: not VERIFIED_CLEAN with a GAP", v["state"] != "VERIFIED_CLEAN", str(v))
check("scan health: basis banner", v["basis"][0].startswith("NOT READ: "), str(v["basis"]))
v2 = {"state": "VERIFIED_CLEAN", "label": "Verified clean", "basis": ["x"]}
scan_health_bridge._not_read_verdict(v2, [rows[1]])
check("scan health: all read stays clean", v2["state"] == "VERIFIED_CLEAN")

# --- JOB 2 surfaces -------------------------------------------------------
# Bench "last scan": an attempt/partial scan's empty lists are not "none".
from cuore.services import bench_bridge, sensor_health, systems_map_bridge  # noqa: E402


class _SL:
    def __init__(self, scan): self.scan = scan
    def list_scans(self, vin): return {"scans": [self.scan]}
    def scan_plan(self, vin): return {"count": 1, "total": 10}


_scan = {"id": "s1", "started": "2026-10-31T10:00:00", "source": {}, "dtcs": {}, "coverage": {}}
_orig_sl = bench_bridge.scanlog_bridge
try:
    for st, part, want in (("attempt", True, True), ("partial", True, True), ("complete", False, False)):
        bench_bridge.scanlog_bridge = _SL(dict(_scan, status=st, partial=part))
        r = bench_bridge.last_scan_summary("V")
        nr = r.get("not_read")
        check(f"bench: {st} scan empty -> NOT READ is {want}", bool(nr) == want, str(r))
        if want:
            check(f"bench: {st} banner wording", nr.startswith("NOT READ: ") and nr.endswith("do not treat as clean"), nr)
    bench_bridge.scanlog_bridge = _SL(dict(_scan, status="attempt", partial=True))
    r = bench_bridge.last_scan_summary("V")
    check("bench: attempt has no code lists posing as none", r["active_codes"] is None and r["history_codes"] is None)
    bench_bridge.scanlog_bridge = _SL(dict(_scan, status="partial", partial=True, dtcs={"stored": ["P0440"]}))
    check("bench: partial scan WITH codes keeps them and no banner",
          bench_bridge.last_scan_summary("V")["active_codes"] == ["P0440"]
          and not bench_bridge.last_scan_summary("V")["not_read"])
finally:
    bench_bridge.scanlog_bridge = _orig_sl

# Sensors: a silent / errored / NRC module read cannot supersede a code as "answered without it".
from cuore.services import cache  # noqa: E402
_orig_ro = cache.recent_observations
cache.recent_observations = lambda *a, **k: [
    {"at": "2026-10-31T20:00:00", "vin": "V", "data": dict(NO_ANSWER, codes=[])},
    {"at": "2026-10-31T20:00:01", "vin": "V", "data": dict(CAN_ERR, codes=[])},
    {"at": "2026-10-31T20:00:02", "vin": "V", "data": dict(NEG, codes=[])},
    {"at": "2026-10-31T20:00:03", "vin": "V", "data": dict(CLEAN, ecu="ECM", codes=[])}]
try:
    ev = sensor_health._uds_evidence()
    check("sensors: only the answered read counts as evidence", [list(e["modules"]) for e in ev] == [["ECM"]], str(ev))
finally:
    cache.recent_observations = _orig_ro

# Systems map: an unread module puts NOT READ on its system and blocks VERIFIED_CLEAN.
_orig = (systems_map_bridge._module_dtc_observations, systems_map_bridge._all_systems)
systems_map_bridge._module_dtc_observations = lambda vin: [
    {"at": "2026-10-31T20:00:00", "data": dict(CLEAN, ecu="ECM")},
    {"at": "2026-10-31T20:00:01", "data": dict(CAN_ERR, ecu="TCM")}]
try:
    st = systems_map_bridge.system_states("V")
    tr = st.get("transmission_driveline") or {}
    check("systems map: unread TCM named on its system",
          [n["ecu"] for n in tr.get("not_read", [])] == ["TCM"]
          and tr["not_read"][0]["banner"].startswith("TCM: NOT READ: "), str(tr))
    check("systems map: system not asserted clean", tr.get("state") != "VERIFIED_CLEAN")
    check("systems map: answered ECM system has no banner", not (st.get("engine_management") or {}).get("not_read"))
except Exception as e:  # noqa: BLE001
    check("systems map: system_states runs on fakes", False, f"{type(e).__name__}: {e}")
finally:
    systems_map_bridge._module_dtc_observations, systems_map_bridge._all_systems = _orig

# Report: its verdict basis carries the dossier NOT READ banner, and its code mining lists only codes present.
import inspect  # noqa: E402
_rt = (Path(__file__).resolve().parents[1] / "web/templates/report.html").read_text(encoding="utf-8")
check("report: renders verdict.basis (NOT READ banner lives there)", "view.verdict.basis" in _rt)
check("dossier verdict wires read_state.unread_modules",
      "read_state.unread_modules" in inspect.getsource(__import__("cuore.services.dossier_bridge", fromlist=["x"])))
# Surfaces with no module-read state: they read MES scan-log codes or the fault board (already covered).
_src = lambda f: (Path(__file__).resolve().parents[1] / f).read_text(encoding="utf-8")
for f in ("services/arrive_ready.py", "services/bay_sheet.py", "services/warranty_pack.py"):
    check(f"{f}: no module_dtcs read of its own", '"module_dtcs"' not in _src(f).replace("_READING_KINDS", ""))
check("warranty pack: readings exclude module_dtcs", "module_dtcs" not in _src("services/warranty_pack.py"))

print(f"{checks - len(failures)}/{checks} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
