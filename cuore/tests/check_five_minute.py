"""Five-minute test (cuore/live/five_minute.py). Fakes only; never touches COM3.

Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_five_minute.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-5min-")
os.environ["CUORE_AUTOSTART"] = "0"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from cuore.live import five_minute as fm  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


VIN = "ZASFAKPN5J7B88115"
IDENT = {"fields": {"F190": {"ascii": VIN, "bytes": ["41"], "nrc": None}}}


class Fake:
    def __init__(self, cable="none", volts=13.8, mes=False, silent=(), can_error_once=(), block=None):
        self._cable, self.volts, self.mes = cable, volts, mes
        self.silent, self.can_error_once, self.block = set(silent), set(can_error_once), block
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self.seen_error: set[str] = set()
        self.bus_ok = True

    def _enter(self, name):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append(name)

    def _exit(self):
        self.active -= 1

    def cable(self): return self._cable
    def mes_running(self): return self.mes
    def bus_ready(self, bus, cable): return (self.bus_ok, "" if self.bus_ok else "bus not verified")
    def voltage(self): self.calls.append("voltage"); return self.volts

    def modules(self, bus):
        self.calls.append("modules")
        return [{"code": c, "name": c, "usable": True, "present": True, "target": 1} for c in ("ECM", "TCM")] \
            if bus == "can_c" else [{"code": "ABS", "name": "ABS", "usable": True, "present": True, "target": 2}]

    def roster(self, vin): return []

    def identity(self, code, vin, confirm):
        self._enter(f"identity:{code}")
        try:
            if self.block:
                self.block.wait(5)
            if code in self.silent:
                return {"fields": {}, "warning": "no answer"}
            if code in self.can_error_once and code not in self.seen_error:
                self.seen_error.add(code)
                return {"error": "CAN ERROR", "fields": {}}
            return dict(IDENT)
        finally:
            self._exit()

    def dtcs(self, code, vin, confirm):
        self._enter(f"dtcs:{code}")
        try:
            if code in self.silent:
                return {"dtcs": [], "warning": "no answer from the module"}
            return {"dtcs": [], "codes": ["P0455"]}
        finally:
            self._exit()

    def abs_connect(self, vin):
        self.calls.append("abs_connect")
        return {"answered_by": None, "conclusion": "silent", "requests_sent": 5}

    def channels(self, bus):
        return [{"id": "rpm", "name": "Engine RPM", "unit": "rpm", "kind": "pid", "pid": "0C"}] if bus == "can_c" else []

    def read_channel(self, ch, vin, confirm):
        self.calls.append(f"channel:{ch['id']}")
        return {"value": 850.0, "unit": "rpm", "error": None}

    def mes_csv(self, since): return None


def go(fake, **kw):
    return fm.run(VIN, probe=fake, **kw)


# all-pass fixture: steps 1-3 and 4 pass, step 5 never
f = Fake()
r = go(f)
flags = [s["passed"] for s in r["steps"]]
check("all-pass fixture: steps 1-4 pass", flags[:4] == [True] * 4, str(flags))
check("step 5 never passes", flags[4] is False and "NOT AVAILABLE: no documented procedure yet" in json.dumps(r["steps"][4]))
check("overall never all-passed", r["all_passed"] is False and r["steps_passed"] == 4)
check("not compared without a CSV", all("not compared" in i["mes"] for i in r["steps"][2]["items"]))
check("stopwatch recorded", isinstance(r["seconds"], float))
saved = list((Path(os.environ["CUORE_STATE_DIR"]) / "five_minute").glob("*.json"))
check("result appended to state_dir/five_minute", len(saved) == 1 and json.loads(saved[0].read_text())["vin"] == VIN)
check("reads strictly one at a time", f.max_active == 1)

# silent module: fails step 2 (and 1), listed in step 4
r = go(Fake(silent={"TCM"}))
check("silent module fails step 2", r["steps"][1]["passed"] is False)
check("silent module listed in step 4 with a reason",
      any("TCM" in n["item"] and n["reason"].startswith("NOT READ") for n in r["not_read"]))
check("step 4 itself still states it", r["steps"][3]["passed"] is True)

# voltage
f = Fake(volts=12.6)
r = go(f)
check("voltage under 13.2 refuses with the reason", r["refused"] and "13.2" in r["reason"])
check("... and nothing else was read", not any(c.startswith(("identity", "dtcs", "channel")) for c in f.calls))
check("MES open refuses", go(Fake(mes=True))["refused"])

# CAN ERROR retried once, recorded
f = Fake(can_error_once={"ECM"})
r = go(f)
check("CAN ERROR retried once", f.calls.count("identity:ECM") == 2)
check("retry recorded and recovered", len(r["retries"]) == 1 and r["retries"][0]["retry_recovered"] is True)

# concurrency
ev = threading.Event()
slow = Fake(block=ev)
out: list = []
t = threading.Thread(target=lambda: out.append(go(slow)))
t.start()
while "identity:ECM" not in slow.calls:
    pass
r2 = go(Fake())
check("concurrent run refused", r2["refused"] and "in progress" in r2["reason"])
ev.set()
t.join()
check("first run still completed", out and not out[0]["refused"])

# CAN-CH gates
check("CAN-CH refused without grey cable", go(Fake(cable="none"), bus="can_ch", confirm=True)["refused"])
check("CAN-CH refused without confirm", go(Fake(cable="grey_a6"), bus="can_ch")["refused"])
f = Fake(cable="grey_a6", silent={"ABS"})
r = go(f, confirm=True)
check("grey + confirm runs can_ch and calls the ABS connect test", not r["refused"] and r["bus"] == "can_ch" and "abs_connect" in f.calls)
check("silent ABS fails and is listed", r["steps"][0]["passed"] is False and any("ABS" in n["item"] for n in r["not_read"]))
check("blue cable never reaches can_c", go(Fake(cable="blue_a5"), bus="can_c")["refused"])

# nothing gated in the code
src = Path(fm.__file__).read_text(encoding="utf-8")
code_only = re.sub(r'""".*?"""|#.*', "", src, flags=re.S)
for bad in ("clear_module_dtcs", "run_actuator", "actuate", "clear_dtcs", "consent_gate", "send_raw", "0x2E", "0x31", "0x14"):
    check(f"no gated call: {bad}", bad not in code_only)

# history
h = fm.history(10)
check("history lists runs with pass counts", len(h) >= 5 and all("steps_passed" in x for x in h) and len(fm.history(3)) == 3)

print(f"{checks - len(failures)}/{checks} checks passed")
for f_ in failures:
    print("FAIL:", f_)
sys.exit(1 if failures else 0)
