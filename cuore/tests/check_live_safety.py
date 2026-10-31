"""Checks for the live-reading safety fixes: bus-aware target lookup (0x2A is ABS on
CAN-CH and DASM on CAN-C), the bounded actuator terminator, and the unconfirmed-VIN rule.

Fake link and fake sessions only; no port is opened and no car or adapter is contacted.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_live_safety.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_live_safety_")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import actuate, addressing, mes_learn, ops, procedure_capture as pc  # noqa: E402
from cuore.live import store, transport, witech_recording as wr  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- 1. a target byte is never looked up without its bus ---------------------------------
check("0x2A on CAN-CH is ABS", getattr(pc._module_for("2A", "can_ch"), "code", None) == "ABS")
check("0x2A with no bus refuses", pc._module_for("2A") is None and pc._module_for("2A", "") is None)
check("0x2A on CAN-C is not ABS (no confirmed DASM address without a car)",
      pc._module_for("2A", "can_c") is None)
check("garbage target refuses", pc._module_for("zz", "can_c") is None)
check("mes_learn: no bus -> raw byte, never a name", mes_learn._module_for_target("2A") == "2A")
check("mes_learn: CAN-CH 0x2A -> ABS", mes_learn._module_for_target("2A", "can_ch") == "ABS")
check("mes_learn: CAN-C 0x10 -> ECM", mes_learn._module_for_target("10", "can_c") == "ECM")
check("witech: no bus is not attributed", wr._module_code("2A").startswith("unknown")
      and wr._module_code("10").startswith("unknown"))
check("witech: bus given resolves", wr._module_code("2A", "can_ch") == "ABS")


def sf(vals):
    return f"{len(vals):02X}" + "".join(f"{v:02X}" for v in vals)


def frames(target):
    return [{"t": 0.0, "id": f"18DA{target}F1", "data": sf([0x2F, 0x12, 0x34, 0x03, 0x01])},
            {"t": 0.01, "id": f"18DAF1{target}", "data": sf([0x6F, 0x12, 0x34, 0x03, 0x01])},
            {"t": 1.0, "id": f"18DA{target}F1", "data": sf([0x2F, 0x12, 0x34, 0x00])},
            {"t": 1.01, "id": f"18DAF1{target}", "data": sf([0x6F, 0x12, 0x34, 0x00])}]


COND = dict(pre={"engine_state": "off", "voltage_v": 12.6}, post={"engine_state": "off", "voltage_v": 12.6},
            name="bench widget test", listen_bitrate=500000)
nb = pc.review(frames("10"))["modules"][0]
check("review with no bus attributes nothing", nb["module"] is None and nb["bus"] is None)
g = pc.gate(nb, **COND)
check("gate refuses a target with no bus context", not g["passed"]
      and any("not a known module" in r for r in g["reasons"]), str(g["reasons"]))
wb = pc.review(frames("10"), bus="can_c")["modules"][0]
check("review with bus resolves the module", wb["module"] == "ECM" and wb["bus"] == "can_c")
check("a bus-less gate of a bare procedure refuses too",
      not pc.gate(wb["procedure"], **COND)["passed"])
chg = pc.review(frames("2A"), bus="can_ch")["modules"][0]
check("0x2A on CAN-CH is gated as ABS (blocked)", chg["module"] == "ABS"
      and not pc.gate(chg, **COND, bus="can_ch")["passed"])


# --- 2. actuator terminator: limit stops new work, terminator gets its own bound ---------
class Clock:
    def __init__(self):
        self.t = 100.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Sess:
    def __init__(self, clock, cost=0.0):
        self.clock, self.cost, self.sent = clock, cost, []
        self.bus = NS(key="can_c")
        self.link = NS(cable="none")
        self.stream = NS(describe="fake")

    def uds(self, ecu, service, payload=b"", timeout=3.0, retries_on_pending=3):
        req = f"{service:02X}{payload.hex().upper()}"
        self.sent.append((req, timeout, retries_on_pending))
        self.clock.t += self.cost
        return {"positive": {"x": [f"{service + 0x40:02X}"]}, "nrc": {}, "error": None, "raw": ""}


ecm = addressing.by_code("ECM")
proc = {"name": "T", "vin": "V", "replayable": True, "reasons": [], "session_sub": "03",
        "steps": [{"service": "10", "payload": ["03"], "request": ["10", "03"], "t_req": 0.0},
                  {"service": "2F", "payload": ["12", "34", "03", "01"], "request": [], "t_req": 0.5}],
        "synthesised_terminator": {"service": "2F", "payload": ["12", "34", "00"], "request": []}}
real_time = actuate.time
try:
    clk = Clock()
    actuate.time = clk
    s = Sess(clk, cost=0.0)
    r = actuate.run_actuator(s, ecm, dict(proc), consent="ACTUATE ECM T", max_seconds=0.0)
    reqs = [x[0] for x in s.sent]
    check("budget 0: no learned step is sent", not any(q.endswith("0301") for q in reqs), str(reqs))
    check("budget 0: terminator and session restore are still attempted",
          "2F123400" in reqs and "1001" in reqs, str(reqs))
    check("terminator sends are bounded (timeout <= 2 s, <= 1 pending retry)",
          all(to <= 2.0 and rt <= 1 for q, to, rt in s.sent), str(s.sent))
    check("result records the terminator time and no overrun",
          r["terminator_overran"] is False and r["terminator_bound_s"] == actuate.TERMINATOR_BOUND_S)

    clk2 = Clock()
    actuate.time = clk2
    s2 = Sess(clk2, cost=5.0)           # every send takes 5 fake seconds
    r2 = actuate.run_actuator(s2, ecm, dict(proc), consent="ACTUATE ECM T", max_seconds=1.0)
    check("slow terminator is still attempted and the overrun is recorded",
          r2["terminator_overran"] is True and r2["control_returned"] is True
          and any(x.get("label") == "terminator overran" for x in r2["steps"]), str(r2["steps"]))
finally:
    actuate.time = real_time

# --- 3. the VIN of a previous car is not trusted -----------------------------------------
lk = transport.AdapterLink()
check("fresh link: no confirmed VIN", lk.confirmed_vin() == "")
lk.vin = "ZASFAKPN5J7B88115"
check("VIN read this process is confirmed", lk.confirmed_vin() == "ZASFAKPN5J7B88115")
lk.vin_ttl = -1.0
check("an old remembered VIN is no longer confirmed", lk.confirmed_vin() == ""
      and lk.vin == "ZASFAKPN5J7B88115")
check("status shows it as unconfirmed, not as the car's VIN",
      lk.status()["vin"] is None and lk.status()["vin_unconfirmed"] == "ZASFAKPN5J7B88115")
lk.vin_ttl = 3600.0
lk.vin = "ZASFAKPN5J7B88115"
lk.forget_vin()
check("forget_vin clears it", lk.confirmed_vin() == "" and lk.vin == "")
check("audit field carries no unconfirmed VIN", transport._vin_field(lk) == {})
lk.vin = "ZASFAKPN5J7B88115"
check("audit field carries a confirmed VIN", transport._vin_field(lk) == {"vin": "ZASFAKPN5J7B88115"})

stale = transport.AdapterLink()
stale._vin, stale._vin_at = "ZFBCFABH1EZ020882", None       # remembered, never read in this process
sess = NS(link=stale, bus=NS(key="can_c"), stream=NS(describe="serial COM99 (fake)"))
out = ops._observe(sess, "module_dtcs", {"ecu": "ECM", "dtcs": []})
mine = [o for o in store.recent_observations(1000) if o["kind"] == "module_dtcs"]
check("a read with an unconfirmed car is not filed under the remembered VIN",
      bool(mine) and all(o["vin"] == "" for o in mine) and "car_unconfirmed" in out, str(mine[-1:]))
stale.vin = "ZASFAKPN5J7B88115"
ops._observe(sess, "module_dtcs", {"ecu": "TCM", "dtcs": []})
check("a VIN read this session files the read",
      any(o["vin"] == "ZASFAKPN5J7B88115" for o in store.recent_observations(1000)))
ops._observe(sess, "module_dtcs", {"ecu": "BCM", "dtcs": []}, "ZFBCFABH1EZ020882")
check("an explicit VIN from the caller is honoured",
      any(o["vin"] == "ZFBCFABH1EZ020882" for o in store.recent_observations(1000)))

print(f"{checks - len(failures)}/{checks} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
