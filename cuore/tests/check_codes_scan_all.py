"""Codes page "Read all modules" (services/codes_scan_all.py). Fakes only; no port, no adapter, no car.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_codes_scan_all.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-csa-")
os.environ["CUORE_AUTOSTART"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.services import codes_scan_all as S  # noqa: E402

fails: list[str] = []


def check(cond: bool, label: str) -> None:
    if not cond:
        fails.append(label)


VIN = "ZASFAKPN5J7B88115"
MODS = {"modules": [
    {"code": "ECM", "name": "Engine", "bus": "can_c", "usable": True},
    {"code": "BCM", "name": "Body", "bus": "can_c", "usable": True},
    {"code": "TCM", "name": "Gear", "bus": "can_c", "usable": True},
    {"code": "IPC", "name": "Cluster", "bus": "can_c", "usable": True},
    {"code": "ESM", "name": "Shifter", "bus": "can_c", "usable": False},
    {"code": "ABS", "name": "Brakes", "bus": "can_ch", "usable": True}]}
mods = lambda **kw: MODS  # noqa: E731


class Fake:
    def __init__(self, volts=13.8, mes=False, vin=VIN, answers=None):
        self.volts, self.mes, self.vin, self.calls = volts, mes, vin, []
        self.answers = answers or {}

    def mes_running(self): return self.mes
    def voltage(self): return self.volts
    def read_vin(self): return {"vin": self.vin}

    def code_round(self, bus, modules, vin, confirm):
        self.calls.append((bus, tuple(modules)))
        a = self.answers.get(modules[0], {"read": True, "codes": []})
        a = a.pop(0) if isinstance(a, list) else a
        return {"modules": [{"module": modules[0], **a}]}


# normal run: codes, clean, silent, retried CAN ERROR that recovers
f = Fake(answers={"ECM": {"read": True, "codes": ["P0456", "P0455"]},
                  "BCM": {"read": True, "codes": []},
                  "TCM": {"read": False, "warning": "no 19 02 answer"},
                  "IPC": [{"read": False, "error": "CAN ERROR"}, {"read": True, "codes": ["U0100"]}]})
r = S.run(VIN, probe=f, modules_fn=mods)
t = {x["module"]: x for x in r["results"]}
check(not r["refused"] and not r["running"], "run finishes")
check(f.calls[:3] == [("can_c", ("ECM",)), ("can_c", ("BCM",)), ("can_c", ("TCM",))], "one module per call, can_c only")
check(t["ECM"]["text"] == "ECM: 2 stored codes: P0456, P0455", "codes with count")
check(t["BCM"]["text"] == "BCM: no stored codes", "answered, clean")
check(t["TCM"]["state"] == "not_read" and "no 19 02 answer" in t["TCM"]["text"] and "NOT READ" in t["TCM"]["text"], "silent is NOT READ")
check(t["IPC"]["state"] == "codes" and len(r["retries"]) == 1, "CAN ERROR retried once and recovered")
nt = {x["module"]: x["why"] for x in r["not_tried"]}
check(set(nt) == {"ESM", "ABS"} and "can_ch" in nt["ABS"] and "address" in nt["ESM"], "not tried lists other bus and unconfirmed")
check(all(c[0] == "can_c" for c in f.calls) and len(f.calls) == 5, "no other bus; retry made one extra call")

# refusals contact nothing
for label, p in (("low voltage", Fake(volts=12.1)), ("no voltage", Fake(volts=None)), ("wrong VIN", Fake(vin="ZASOTHER000000000")),
                 ("no VIN", Fake(vin=""))):
    r = S.run(VIN, probe=p, modules_fn=mods)
    check(r["refused"] and not r["results"] and not p.calls, f"{label}: refused, nothing read")
check("nothing was read or filed" in S.status(VIN)["reason"], "VIN mismatch says why")
check(S.start(VIN, probe=Fake(mes=True), modules_fn=mods)["started"] is False, "MES open refuses")
check(S.start("ZASFAKPN5J7B88000", probe=Fake(), modules_fn=lambda **kw: {"modules": []})["started"] is False, "no modules refuses")

# CAN ERROR twice stops
f = Fake(answers={"ECM": {"read": False, "error": "CAN ERROR"}, "BCM": {"read": False, "error": "CAN ERROR"}})
r = S.run(VIN, probe=f, modules_fn=mods)
check(len(r["results"]) == 2 and r.get("stopped") and len(f.calls) == 4, "stops after CAN ERROR twice (each retried once)")
check({"TCM", "IPC"} <= {x["module"] for x in r["not_tried"]} and "CAN ERROR twice" in r["not_tried"][0]["why"], "rest listed as not tried")

# exception from the link is NOT READ, never clean
class Boom(Fake):
    def code_round(self, *a): raise RuntimeError("adapter busy")
r = S.run(VIN, probe=Boom(), modules_fn=mods)
check(all(x["state"] == "not_read" and "adapter busy" in x["text"] for x in r["results"]), "exception is NOT READ")

# does not block: start returns while the read is held; second start refused; lock freed after
gate = threading.Event()
class Slow(Fake):
    def code_round(self, *a):
        gate.wait(5)
        return super().code_round(*a)
sp = Slow()
out = S.start(VIN, probe=sp, modules_fn=mods)
check(out["started"] and S.status(VIN)["running"], "start returns at once, running")
check(S.start(VIN, probe=Fake(), modules_fn=mods)["started"] is False, "second read refused while running")
gate.set()
for _ in range(100):
    if not S.status(VIN)["running"]:
        break
    threading.Event().wait(0.05)
check(not S.status(VIN)["running"] and len(S.status(VIN)["results"]) == 4 and not S._RUN_LOCK.locked(), "finishes, lock freed")

# wiring
root = Path(__file__).resolve().parents[1]
check("/codes/read-all" in json.loads((root / "data/brand_pages.json").read_text(encoding="utf-8"))["contact_posts"], "brand gate lists the path")
pi = json.loads((root / "data/parity_items.json").read_text(encoding="utf-8"))
row = next(i for i in pi["items"] if i["id"] == "mes-fn-scan-dtc-all-modules")
check(row["status"] == "BUILT NOT PROVEN", "parity row status")
check("Read all modules" in (root / "web/templates/codes.html").read_text(encoding="utf-8"), "button on the page")

print("FAIL: " + "; ".join(fails) if fails else "OK codes_scan_all")
sys.exit(1 if fails else 0)
