"""Regression checks for the 2026-10-31 independent review of the car-contact code.

Fakes only; no port is opened and no car or adapter is contacted.

Run: PYTHONPATH=mes-log-mcp .venv/Scripts/python.exe -X utf8 cuore/tests/check_review_fixes.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-review-")
os.environ["CUORE_AUTOSTART"] = "0"
os.environ.pop("CUORE_AUDIT_PATH", None)
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import actuate, addressing, interlock, ops, store, transport  # noqa: E402
from cuore.live import connect_session as cs  # noqa: E402
from cuore.services import car_identify as ci  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- 1. actuator: session restore is attempted even when the terminator send raises ----------
class Sess:
    def __init__(self):
        self.sent = []
        self.bus = NS(key="can_c")
        self.link = NS(cable="none")
        self.stream = NS(describe="fake")

    def uds(self, ecu, service, payload=b"", timeout=3.0, retries_on_pending=3):
        req = f"{service:02X}{payload.hex().upper()}"
        self.sent.append(req)
        if req == "2F123400":
            raise RuntimeError("link dropped during terminator")
        return {"positive": {"x": [f"{service + 0x40:02X}"]}, "nrc": {}, "error": None, "raw": ""}


proc = {"name": "T", "vin": "V", "replayable": True, "reasons": [], "session_sub": "03",
        "steps": [{"service": "10", "payload": ["03"], "request": ["10", "03"], "t_req": 0.0},
                  {"service": "2F", "payload": ["12", "34", "03", "01"], "request": [], "t_req": None}],
        "synthesised_terminator": {"service": "2F", "payload": ["12", "34", "00"], "request": []}}
s = Sess()
r = actuate.run_actuator(s, addressing.by_code("ECM"), dict(proc), consent="ACTUATE ECM T", max_seconds=5.0)
check("terminator raised: session restore (10 01) is still attempted", s.sent.count("1001") == 1, str(s.sent))
check("terminator raised: result says control was NOT returned", r["control_returned"] is False)

# --- 2. a read is filed under the car that answered, not under the page's VIN -----------------
VIN_A, VIN_B = "ZASFAKPN5J7B88115", "ZFBCFABH1EZ020882"
lk = transport.AdapterLink()
lk.vin = VIN_B                                            # the car on the cable said it is B
sess = NS(link=lk, bus=NS(key="can_c"), stream=NS(describe="serial COM99 (fake)"))
out = ops._observe(sess, "module_dtcs", {"ecu": "ECM", "dtcs": []}, VIN_A)   # page of car A asked
rows = [o for o in store.recent_observations(1000) if o["kind"] == "module_dtcs"]
check("page VIN differs from the confirmed car: not filed under the page's VIN",
      not any(o["vin"] == VIN_A for o in rows), str(rows[-1:]))
check("filed under the car that answered", any(o["vin"] == VIN_B for o in rows))
check("result says the car differs", bool(out.get("car_mismatch")), str(out))

from cuore.services import codes_read  # noqa: E402

mods = lambda **kw: {"modules": [{"code": "ECM", "name": "Engine", "bus": "can_c", "usable": True}]}  # noqa: E731
res = codes_read.read_now(VIN_A, "ECM", lambda code, vin="", detail=True: dict(
    ops._observe(sess, "module_dtcs", {"ecu": "ECM", "active": [], "history": [], "read_state": "read"}, vin)), mods)
check("Codes page: a read of another car is not shown as this car's 'no stored codes'",
      not res["ok"] and "no stored codes" not in res["line"], str(res))

# --- 3. connect session -------------------------------------------------------------------------
IDENT = {"fields": {"F190": {"ascii": VIN_A, "bytes": ["41"], "nrc": None}}}


class Fake:
    def __init__(self, vin_raises=False, cable="none"):
        self.calls, self.vin_raises, self.declared = [], vin_raises, cable

    def read_vin(self):
        if self.vin_raises:
            raise RuntimeError("adapter vanished")
        return {"vin": VIN_A}

    def other_owner(self): return ""
    def mes_running(self): return False
    def voltage(self): return 13.8
    def cable(self): return self.declared
    def modules(self, bus, vin=None):
        return [{"code": c, "name": c, "usable": True, "present": True, "target": 1, "why": ""} for c in cs.ROUND_MODULES]
    def verify(self, bus): self.calls.append(f"verify:{bus}"); return {"verified": True, "frames": 9, "verified_by": "passive_listen"}
    def set_cable(self, cable): self.calls.append(f"cable:{cable}"); self.declared = cable; return {"cable": cable}
    def dtcs(self, code, vin, confirm): return {"dtcs": [], "codes": []}
    def identity(self, code, vin, confirm): return dict(IDENT)
    def channels(self, bus): return []
    def read_channel(self, ch, vin, confirm): return {"value": 1.0}
    def mes_csv(self, since): return None
    def code_round(self, bus, modules, vin, confirm): return {"modules": []}
    def abs_connect(self, vin): return {"answered_by": "x", "conclusion": "answered", "requests_sent": 1}
    def discover(self, bus, vin, confirm): self.calls.append(f"discover:{bus}:{self.declared}"); return {"found": []}


cs.start_new(VIN_A)
f = Fake(vin_raises=True)
r = cs.run_step(VIN_A, "voltage_bus", probe=f)
st = cs.current(VIN_A)
check("VIN read raised: step 1 does not pass", st["steps"]["voltage_bus"]["status"] != "done",
      st["steps"]["voltage_bus"]["status"])
check("VIN read raised: the session stops, step 2 is refused",
      bool(st["stop"]) and cs.run_step(VIN_A, "code_round", probe=Fake())["refused"])

cs.start_new(VIN_A)
f = Fake(cable="grey_a6")                                   # left over from an earlier CAN-CH run
cs.run_step(VIN_A, "voltage_bus", probe=f)
check("CAN-C step declares the plain cable first (no CAN-CH route left declared)",
      f.calls[:1] == ["cable:none"] and f.declared == "none", str(f.calls))

cs.start_new(VIN_A)
f = Fake()
for sid in ("voltage_bus", "code_round", "ecm_live", "snapshot", "identity"):
    cs.run_step(VIN_A, sid, probe=f)
cs.confirm_cable(VIN_A, "grey_a6")
cs.run_step(VIN_A, "abs", probe=f)
f.declared = "none"                                          # e.g. restored after an earlier stop
cs.run_step(VIN_A, "discover_ch", confirm=True, probe=f)
check("optional CAN-CH discover declares grey_a6 itself, never runs under another cable",
      any(c == "discover:can_ch:grey_a6" for c in f.calls), str(f.calls))
cs.finish(VIN_A, probe=f)
check("finishing the session puts the declared cable back to plain", f.declared == "none", f.declared)

cs.start_new(VIN_A)
f = Fake()
f.verify = lambda bus: {"verified": bus == "can_c", "frames": 9, "verified_by": "x", "reason": "no traffic"}
for sid in ("voltage_bus", "code_round", "ecm_live", "snapshot", "identity"):
    cs.run_step(VIN_A, sid, probe=f)
cs.confirm_cable(VIN_A, "grey_a6")
cs.run_step(VIN_A, "abs", probe=f)
check("a CAN-CH stop leaves the declared cable plain again", cs.current(VIN_A)["stop"] is not None
      and f.declared == "none", f.declared)

# --- 4. /api routes that reach the bus refuse a brand whose paths are not confirmed ---------------
def vin_with_check(v17):
    return v17[:8] + ci._check_digit(v17)[1] + v17[9:]


MASERATI = vin_with_check("ZN661XUA0JX000001")
Path(os.environ["CUORE_STATE_DIR"], "web_token.txt").write_text("cx-token", encoding="utf-8")
c = TestClient(create_app(), follow_redirects=False, raise_server_exceptions=False)
c.get("/login?token=cx-token")
touched: list[str] = []


def trap(name):
    def fn(*a, **k):
        touched.append(name)
        raise AssertionError("bus reached for a gated brand: " + name)
    return fn


for n in ("probe", "verify_bus", "obd_vin", "module_dtcs", "module_identity", "module_code_round", "scan_modules",
          "discover", "abs_connect_test", "module_did", "module_read_all"):
    setattr(ops, n, trap(n))
import cuore.live.fullscan as fullscan  # noqa: E402
import cuore.live.five_minute as fm  # noqa: E402
fullscan.run_guided = trap("run_guided")
fullscan.run = trap("fullscan.run")
fm.run = trap("five_minute.run")

for label, resp in (
        ("connect/start", c.post("/api/live/connect/start", json={"vin": MASERATI})),
        ("module dtcs", c.get(f"/api/live/module/ECM/dtcs?vin={MASERATI}")),
        ("module identity", c.get(f"/api/live/module/ECM/identity?vin={MASERATI}")),
        ("round", c.get(f"/api/live/round?vin={MASERATI}&confirm=true")),
        ("scan", c.get(f"/api/live/scan?vin={MASERATI}&confirm=true")),
        ("discover", c.post("/api/live/discover", json={"vin": MASERATI, "confirm": True})),
        ("fullscan", c.post("/api/live/fullscan", json={"vin": MASERATI, "confirm": True})),
        ("guided start", c.post("/api/live/fullscan/guided/start", json={"vin": MASERATI})),
        ("five-minute", c.post(f"/api/live/five-minute?vin={MASERATI}"))):
    check(f"/api {label} refuses a Maserati before the bus (409)", resp.status_code == 409, f"{resp.status_code} {resp.text[:120]}")
check("no bus function was reached for the Maserati", not touched, str(touched))

print(f"{checks - len(failures)}/{checks} checks passed")
for x in failures:
    print("FAIL:", x)
sys.exit(1 if failures else 0)
