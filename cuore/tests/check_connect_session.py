"""Guided connection session (cuore/live/connect_session.py). Fake link only; no port is opened.

Run: PYTHONPATH=mes-log-mcp .venv/Scripts/python.exe -X utf8 cuore/tests/check_connect_session.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-connect-")
os.environ["CUORE_AUTOSTART"] = "0"
os.environ.pop("CUORE_AUDIT_PATH", None)
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import connect_session as cs  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.services import car_identify as ci  # noqa: E402
from cuore.web import nav_items  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


VIN = "ZASFAKPN5J7B88115"
IDENT = {"fields": {"F190": {"ascii": VIN, "bytes": ["41"], "nrc": None}}}


class Fake:
    """Same methods as ConnectProbe; counts every call so 'no contact' can be asserted."""

    def __init__(self, volts=13.8, mes=False, silent=(), can_error=(), bus_silent=(), abs_answers=False):
        self.volts, self.mes = volts, mes
        self.silent, self.can_error = set(silent), set(can_error)
        self.bus_silent, self.abs_answers = set(bus_silent), abs_answers
        self.calls: list[str] = []
        self.csv = None

    def read_vin(self): self.calls.append("read_vin"); return {"vin": getattr(self, "car_vin", VIN)}
    def other_owner(self): return "MultiEcuScan is open" if self.mes else ""
    def mes_running(self): return self.mes
    def voltage(self): self.calls.append("voltage"); return self.volts

    def modules(self, bus, vin=None):
        return [{"code": c, "name": c, "usable": c != "ESM", "present": True, "target": 1,
                 "why": "" if c != "ESM" else "no confirmed address on this car"}
                for c in cs.ROUND_MODULES]

    def verify(self, bus):
        self.calls.append(f"verify:{bus}")
        if bus in self.bus_silent:
            return {"verified": False, "reason": "no traffic", "error": None}
        return {"verified": True, "frames": 40, "verified_by": "passive_listen"}

    def set_cable(self, cable): self.calls.append(f"cable:{cable}"); return {"cable": cable}

    def dtcs(self, code, vin, confirm):
        self.calls.append(f"dtcs:{code}")
        if code in self.can_error:
            return {"error": "CAN ERROR", "dtcs": []}
        if code in self.silent:
            return {"dtcs": [], "warning": "no answer from the module"}
        return {"dtcs": [], "codes": ["P0456"] if code == "ECM" else []}

    def identity(self, code, vin, confirm):
        self.calls.append(f"identity:{code}")
        if code in self.can_error:
            return {"error": "CAN ERROR", "fields": {}}
        if code in self.silent:
            return {"fields": {}, "warning": "no answer"}
        return dict(IDENT)

    def channels(self, bus):
        return [{"id": "rpm", "name": "Engine RPM", "unit": "rpm", "kind": "pid", "pid": "0C"},
                {"id": "batt", "name": "Battery", "unit": "V", "kind": "battery"}]

    def read_channel(self, ch, vin, confirm):
        self.calls.append(f"channel:{ch['id']}")
        return {"value": 850.0, "unit": "rpm", "error": None}

    def mes_csv(self, since): return self.csv

    def code_round(self, bus, modules, vin, confirm):
        self.calls.append(f"round:{bus}:{','.join(modules)}")
        return {"modules": [{"module": "ECM", "read": True, "codes": ["P0456"], "snapshots_decoded": 1, "snapshots_raw": 0}]}

    def abs_connect(self, vin):
        self.calls.append("abs_connect")
        return {"answered_by": "1_production_22F190" if self.abs_answers else None,
                "conclusion": "answered" if self.abs_answers else "silent", "requests_sent": 5}

    def discover(self, bus, vin, confirm):
        self.calls.append(f"discover:{bus}:{confirm}")
        return {"found": [1, 2]}


def fresh():
    return cs.start_new(VIN)


def run(fake, step, **kw):
    return cs.run_step(VIN, step, probe=fake, **kw)


def status(step):
    return cs.current(VIN)["steps"][step]["status"]


# --- 1. step order is the STATUS section 5 order ------------------------------------------------
check("eight steps in section 5 order", [s["id"] for s in cs.STEPS] == [
    "voltage_bus", "code_round", "ecm_live", "snapshot", "identity", "abs", "discover_ch", "blue_a5"])
check("round modules as listed", cs.ROUND_MODULES == ("ECM", "TCM", "BCM", "IPC", "RFHUB", "DTCM", "DASM", "ESM"))
check("every step names the hands, and MES steps exist", all(s["hands"] and s["does"] for s in cs.STEPS)
      and any(s["mes"] for s in cs.STEPS))

st = fresh()
f = Fake()
r = run(f, "code_round")
check("step 2 refused before step 1", r["refused"] and "step 1" in r["reason"] and f.calls == [], str(r["reason"]))
r = run(f, "voltage_bus")
check("step 1 runs", not r["refused"] and status("voltage_bus") == "done")
check("step 1 recorded voltage and bus", cs.current(VIN)["items"]["voltage_bus:voltage"]["volts"] == 13.8
      and cs.current(VIN)["items"]["voltage_bus:bus"]["status"] == "ANSWERED")

# --- 2. code round: ANSWERED / NOT READ with reasons, one at a time ---------------------------
f = Fake(silent={"DASM"})
r = run(f, "code_round")
it = cs.current(VIN)["items"]
check("ECM answered with codes", it["code_round:ECM"]["status"] == "ANSWERED" and it["code_round:ECM"]["codes"] == ["P0456"])
check("silent DASM is NOT READ with reason", it["code_round:DASM"]["status"] == "NOT READ" and it["code_round:DASM"]["reason"])
check("ESM without address is NOT READ and never sent", it["code_round:ESM"]["status"] == "NOT READ"
      and "dtcs:ESM" not in f.calls and "no confirmed address" in it["code_round:ESM"]["reason"])
check("reads in the stated order", [c for c in f.calls if c.startswith("dtcs:")] ==
      ["dtcs:ECM", "dtcs:TCM", "dtcs:BCM", "dtcs:IPC", "dtcs:RFHUB", "dtcs:DTCM", "dtcs:DASM"])
check("step done despite NOT READ items", status("code_round") == "done" and cs.current(VIN)["stop"] is None)

# --- 3. ABS cannot run before the cable is confirmed -----------------------------------------
for sid in ("ecm_live", "snapshot", "identity"):
    run(Fake(), sid)
check("steps 3-5 done", all(status(s) == "done" for s in ("ecm_live", "snapshot", "identity")))
f = Fake(abs_answers=True)
r = run(f, "abs")
check("ABS refused before cable confirmed, no contact", r["refused"] and "cable" in r["reason"].lower() and f.calls == [], r["reason"])
cs.confirm_cable(VIN, "grey_a6")
r = run(f, "abs")
check("ABS runs once cable confirmed: cable, listen, then connect test",
      not r["refused"] and f.calls[:3] == ["voltage", "cable:grey_a6", "verify:can_ch"] and "abs_connect" in f.calls, str(f.calls))
check("ABS answered, identity and codes read", all(cs.current(VIN)["items"][k]["status"] == "ANSWERED"
      for k in ("abs:ABS", "abs:ABS-identity", "abs:ABS-codes")))

# --- 4. optional discover needs ABS answer and a person's confirm -----------------------------
f = Fake()
r = run(f, "discover_ch")
check("discover refused without confirm", r["refused"] and "confirm" in r["reason"] and f.calls == [])
r = run(f, "discover_ch", confirm=True)
check("discover runs after ABS answered with confirm, bounded call", not r["refused"] and "discover:can_ch:True" in f.calls)
check("discover names nothing", "nothing was named" in cs.current(VIN)["items"]["discover_ch:discover"]["note"])

st = fresh()
for sid in ("voltage_bus", "code_round", "ecm_live", "snapshot", "identity"):
    run(Fake(), sid)
cs.confirm_cable(VIN, "grey_a6")
run(Fake(abs_answers=False), "abs")
f = Fake()
r = run(f, "discover_ch", confirm=True)
check("discover refused when ABS stayed silent", r["refused"] and "ABS" in r["reason"] and f.calls == [], r["reason"])
check("silent ABS is NOT READ with the conclusion", cs.current(VIN)["items"]["abs:ABS"]["status"] == "NOT READ")

# --- 5. stop rules --------------------------------------------------------------------------------
fresh()
f = Fake(volts=12.1)
r = run(f, "voltage_bus")
s_ = cs.current(VIN)["stop"]
check("low voltage stops with what to check", s_ and s_["kind"] == "voltage" and "engine" in s_["check"].lower()
      and not any(c.startswith(("verify", "dtcs")) for c in f.calls), str(s_))
r = run(Fake(), "voltage_bus")
check("stopped session refuses further runs until Resume", r["refused"] and "Resume" in r["reason"])
cs.resume(VIN)
check("resume clears the stop and logs it", cs.current(VIN)["stop"] is None
      and any("Resume" in e["what"] for e in cs.current(VIN)["events"]))
check("ok at 13.8 V after resume", not run(Fake(), "voltage_bus")["refused"] and status("voltage_bus") == "done")

fresh()
r = run(Fake(bus_silent={"can_c"}), "voltage_bus")
s_ = cs.current(VIN)["stop"]
check("silent bus stops the session", s_ and s_["kind"] == "bus_silent" and s_["check"] and status("voltage_bus") == "stopped")

fresh()
run(Fake(), "voltage_bus")
f = Fake(can_error={"BCM"})
run(f, "code_round")
s_ = cs.current(VIN)["stop"]
check("CAN ERROR twice on a bus stops (first plus retry)", s_ and s_["kind"] == "can_error" and "BCM" in s_["reason"], str(s_))
check("no module after the stop is read", "dtcs:IPC" not in f.calls and "dtcs:RFHUB" not in f.calls)
check("the earlier answers are kept", cs.current(VIN)["items"]["code_round:ECM"]["status"] == "ANSWERED")

fresh()
f = Fake(mes=True)
r = run(f, "voltage_bus")
s_ = cs.current(VIN)["stop"]
check("another owner stops before any read", s_ and s_["kind"] == "other_owner" and "MES" in s_["check"]
      and f.calls == [], str(f.calls))

# --- 6. summary: counts, moved, no MES claim without a comparison ------------------------------
fresh()
run(Fake(), "voltage_bus")
run(Fake(silent={"TCM"}), "code_round")
sm = cs.summary(cs.current(VIN))
check("summary counts", sm["not_read"] >= 2 and sm["answered"] >= 7 and sm["total"] == sm["answered"] + sm["not_read"])
check("no MES match claimed without comparison", "No comparison with MES" in sm["mes_statement"]
      and "matches MES" not in sm["mes_statement"].lower())
st = cs.current(VIN)
st["steps"]["code_round"]["status"] = "pending"      # run the step again after fixing the cause
cs.save(st)
run(Fake(), "code_round")
sm = cs.summary(cs.current(VIN))
moved = {m["key"]: m for m in sm["moved"]}
check("TCM moved from NOT READ to read with a time stamp", "code_round:TCM" in moved and moved["code_round:TCM"]["moved_at"])
saved = list((Path(os.environ["CUORE_STATE_DIR"]) / "connect_session").glob(f"*_{VIN}.json"))
check("result saved under state", saved and json.loads(saved[0].read_text(encoding="utf-8"))["vin"] == VIN)
check("read-only flag in the saved file", all(json.loads(p.read_text(encoding="utf-8"))["read_only"] for p in saved))

fresh()
run(Fake(), "voltage_bus")
g = Fake()
g.csv = {"name": "x.csv", "ranges": {"engine rpm": {"min": 800, "max": 900, "unit": "rpm"}}}
run(g, "code_round")
run(g, "ecm_live")
sm = cs.summary(cs.current(VIN))
check("a real CSV comparison is reported as such, codes still not compared",
      "1 of 1" in sm["mes_statement"] and "not compared with MES" in sm["mes_statement"], sm["mes_statement"])

# the baseline is the previous session
prev_moved = cs.start_new(VIN)
check("new session carries the previous one as baseline", bool(prev_moved["baseline"]))

# --- 7. hard limits in the source ---------------------------------------------------------------
src = (REPO / "cuore/live/connect_session.py").read_text(encoding="utf-8")
for banned in ("clear_module_dtcs", "run_actuator", "send_raw", "consent_gate", "import serial", "write_did", "ATBR", "ATPB"):
    check(f"source has no {banned}", banned not in src)

# --- 8. web: Alfa page, Maserati gated, Menu entry ---------------------------------------------------
Path(os.environ["CUORE_STATE_DIR"], "web_token.txt").write_text("cx-token", encoding="utf-8")
c = TestClient(create_app(), follow_redirects=False, raise_server_exceptions=False)
c.get("/login?token=cx-token")
r = c.get(f"/v/{VIN}/connect-session")
check("Alfa page renders one column of steps", r.status_code == 200 and r.text.count('class="step') == 8
      and "Voltage and bus" in r.text, str(r.status_code))
check("page tells the mechanic to take turns with MES", "close CUORE's session first" in r.text)
# --- a different car in the port files nothing ---
fresh()
other = Fake(); other.car_vin = "ZASFAKPN5J7B00000"
w = run(other, "voltage_bus")
check("wrong car stops at step 1", cs.current(VIN)["stop"] and cs.current(VIN)["stop"]["kind"] == "wrong_car")
check("wrong car: no module was read", not any(x.startswith(("dtc", "identity", "code_round")) for x in other.calls), str(other.calls))
fresh()
r2 = c.get(f"/v/{VIN}/connect-session/summary")
check("summary page renders", r2.status_code == 200 and "ANSWERED" in r2.text)
mas = ci._check_digit("ZN661XUA0JX000001")[1]
MAS = "ZN661XUA0" + mas + "JX000001"
r3 = c.get(f"/v/{MAS}/connect-session")
check("Maserati is gated to the empty skeleton", r3.status_code == 200 and "Voltage and bus" not in r3.text
      and 'name="step"' not in r3.text, str(r3.status_code))
check("Maserati cannot post a run either", c.post(f"/v/{MAS}/connect-session/run", data={"step": "voltage_bus"}).status_code != 303)
ferr = ci._check_digit("ZFF79ALA0K0000001")[1]
FER = "ZFF79ALA0" + ferr + "K0000001"
check("Ferrari gated", "Voltage and bus" not in c.get(f"/v/{FER}/connect-session").text)
item = next((i for i in nav_items.ITEMS if i["key"] == "connect-session"), None)
check("Menu entry in More, per car", item and item["more"] is True and item["href"] == "/v/{vin}/connect-session")
check("run route passes only the person's tick as confirm", "run_step(vin, step, confirm=bool(confirm))" in (REPO / "cuore/web/connect_session_routes.py").read_text(encoding="utf-8"))

print(f"{checks} checks, {len(failures)} failures")
for fl in failures:
    print("FAIL:", fl)
sys.exit(1 if failures else 0)
