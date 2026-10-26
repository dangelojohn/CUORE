"""Checks for cuore.live.procedure_capture (review report + safety gate).

ALL FIXTURES BELOW ARE SYNTHETIC. The DIDs (DE01), routine ids and values are
invented to mimic the SHAPE of an ESIM vent-test session; they are not real
car data and must never be used as a replay procedure.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_procedure_capture.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import procedure_capture as pc  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def sf(vals: list[int]) -> str:
    return f"0{len(vals):X}" + "".join(f"{v:02X}" for v in vals)


def build(steps: list[tuple[list[int], list[int]]], target: str = "10") -> list[dict]:
    """SYNTHETIC capture: tester 18DA<target>F1 requests, module 18DAF1<target> replies."""
    out, t = [], 0.0
    for req, resp in steps:
        out.append({"t": t, "id": f"18DA{target}F1", "data": sf(req)})
        t += 0.01
        if len(resp) <= 7:
            out.append({"t": t, "id": f"18DAF1{target}", "data": sf(resp)})
        else:  # multi-frame response: FF + flow control from tester + CFs
            n = len(resp)
            out.append({"t": t, "id": f"18DAF1{target}",
                        "data": f"{0x10 | (n >> 8):02X}{n & 0xFF:02X}"
                                + "".join(f"{v:02X}" for v in resp[:6])})
            out.append({"t": t + 0.001, "id": f"18DA{target}F1", "data": "300000"})
            rest, seq = resp[6:], 1
            while rest:
                out.append({"t": t + 0.002 + seq * 0.001, "id": f"18DAF1{target}",
                            "data": f"{0x20 | (seq & 15):02X}"
                                    + "".join(f"{v:02X}" for v in rest[:7])})
                rest, seq = rest[7:], seq + 1
        t += 0.2
    return out


# SYNTHETIC ESIM-like vent sequence on the ECM (target 10): session, tester present,
# a multi-frame read, shortTermAdjustment, returnControlToECU, back to default session.
ESIM = build([
    ([0x10, 0x03], [0x50, 0x03, 0x00, 0x32, 0x01, 0xF4]),
    ([0x3E, 0x00], [0x7E, 0x00]),
    ([0x22, 0xDE, 0x00], [0x62, 0xDE, 0x00, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]),  # 14 bytes, FF+CF
    ([0x2F, 0xDE, 0x01, 0x03, 0x01], [0x6F, 0xDE, 0x01, 0x03, 0x01]),
    ([0x2F, 0xDE, 0x01, 0x00], [0x6F, 0xDE, 0x01, 0x00]),
    ([0x10, 0x01], [0x50, 0x01, 0x00, 0x32, 0x01, 0xF4]),
])
# SYNTHETIC with SecurityAccess.
WITH27 = build([
    ([0x10, 0x03], [0x50, 0x03, 0x00, 0x32, 0x01, 0xF4]),
    ([0x27, 0x01], [0x67, 0x01, 0xAA, 0xBB]),
    ([0x27, 0x02, 0x11, 0x22], [0x67, 0x02]),
    ([0x2F, 0xDE, 0x01, 0x03, 0x01], [0x6F, 0xDE, 0x01, 0x03, 0x01]),
    ([0x2F, 0xDE, 0x01, 0x00], [0x6F, 0xDE, 0x01, 0x00]),
])
# SYNTHETIC: actuation started, never stopped.
NOSTOP = build([
    ([0x10, 0x03], [0x50, 0x03, 0x00, 0x32, 0x01, 0xF4]),
    ([0x2F, 0xDE, 0x01, 0x03, 0x01], [0x6F, 0xDE, 0x01, 0x03, 0x01]),
])
# SYNTHETIC: a write (2E) mixed in.
WITHWRITE = build([
    ([0x10, 0x03], [0x50, 0x03, 0x00, 0x32, 0x01, 0xF4]),
    ([0x2E, 0xDE, 0x02, 0x01], [0x6E, 0xDE, 0x02]),
    ([0x2F, 0xDE, 0x01, 0x03, 0x01], [0x6F, 0xDE, 0x01, 0x03, 0x01]),
    ([0x2F, 0xDE, 0x01, 0x00], [0x6F, 0xDE, 0x01, 0x00]),
])

GOOD = dict(listen_bitrate=500000,
            pre={"engine_state": "running, idle", "voltage_v": 13.8},
            post={"engine_state": "running, idle", "voltage_v": 13.8},
            name="ESIM vent test")
# Neutral conditions (engine off, a name MES has no function for): exercises the other gate
# checks without the ESIM interlock conflict.
NEUTRAL_KW = dict(pre={"engine_state": "off", "voltage_v": 12.6},
                post={"engine_state": "off", "voltage_v": 12.6}, name="bench widget test")
NEUTRAL = dict(listen_bitrate=500000, pre={"engine_state": "off", "voltage_v": 12.6},
               post={"engine_state": "off", "voltage_v": 12.6}, name="bench widget test")

# --- reassembly and extraction ---
r = pc.review(ESIM)
check("one module reviewed", len(r["modules"]) == 1)
m = r["modules"][0]
check("module is ECM", m["module"] == "ECM", str(m["module"]))
check("sequence in order", m["sequence"] == ["10", "3E", "22", "2F", "2F", "10"], str(m["sequence"]))
check("multi-frame read reassembled to 14 bytes",
      len(m["procedure"]["steps"][2]["response"]) == 14,
      str(m["procedure"]["steps"][2]["response"]))
check("six transactions all answered", r["transactions"] == 6 and m["unanswered"] == 0)
check("no 0x27 in ESIM", not m["has_security_access"])
check("no write services in ESIM", m["write_reset_services"] == [])
check("actuate allows ESIM replay", m["replay_allowed"], str(m["replay_reasons"]))
check("report text names ECM and services",
      "ECM" in r["text"] and "2F InputOutputControlByIdentifier" in r["text"]
      and "ALLOW replay" in r["text"], r["text"])

# --- 0x27 detection ---
r27 = pc.review(WITH27)
m27 = r27["modules"][0]
check("0x27 detected", m27["has_security_access"])
check("0x27 means replay refused", not m27["replay_allowed"])
check("report flags 0x27", "PRESENT" in r27["text"] and "REFUSE" in r27["text"])

# --- write detection ---
mw = pc.review(WITHWRITE)["modules"][0]
check("write service detected", mw["write_reset_services"] == ["2E"])
check("write means replay refused", not mw["replay_allowed"])

# --- gate ---
g = pc.gate(m, **NEUTRAL)
check("gate passes a synthetic procedure under engine-off conditions", g["passed"], str(g["reasons"]))
check("passed status", g["status"] == "passed" and g["interlock_conflicts"] == [])
check("consent phrase defined", g["consent"] == "ACTUATE ECM BENCH WIDGET TEST", str(g["consent"]))
# ESIM vent test: MES needs engine running + purge active; run_actuator needs engine off + stationary.
ge = pc.gate(m, **GOOD)
check("ESIM vent test never passes: interlock conflict", not ge["passed"]
      and ge["status"] == "needs an owner decision: interlock conflict", str(ge))
check("conflict names MES prerequisite and the run_actuator interlock",
      any("purge active" in c and "run_actuator" in c for c in ge["interlock_conflicts"]),
      str(ge["interlock_conflicts"]))
ge2 = pc.gate(m, **{**GOOD, "name": "bench widget test"})
check("recorded engine-running pre-condition alone is a conflict",
      ge2["status"] == pc.INTERLOCK_CONFLICT_STATUS and not ge2["passed"], str(ge2))
ge3 = pc.gate(m, **{**NEUTRAL, "name": "ESIM vent test"})
check("conflict from the MES function even with engine-off conditions recorded",
      ge3["status"] == pc.INTERLOCK_CONFLICT_STATUS and not ge3["passed"], str(ge3))
check("review text does not hide the interlock rule", "interlock" in pc.INTERLOCK_CONFLICT_STATUS)
gr = pc.gate_report(r, listen_bitrate=500000, **{k: v for k, v in GOOD.items() if k != "listen_bitrate"})
check("gate_report: one gate per module with status",
      len(gr) == 1 and gr[0]["module"] == "ECM" and gr[0]["status"] == pc.INTERLOCK_CONFLICT_STATUS, str(gr))
check("gate_report: bitrate taken from the recorded value",
      pc.gate_report(r, listen_bitrate=125000, **NEUTRAL_KW)[0]["passed"] is False)
g27 = pc.gate(m27, **GOOD)
check("gate fails on 0x27", not g27["passed"] and any("0x27" in x for x in g27["reasons"]))
mn = pc.review(NOSTOP)["modules"][0]
gn = pc.gate(mn, **GOOD)
check("gate fails on missing stop step", not gn["passed"]
      and any("no stop step" in x for x in gn["reasons"]), str(gn["reasons"]))
gn2 = pc.gate(mn, max_seconds=10, **NEUTRAL)
check("gate passes missing stop with synthesised terminator + timeout", gn2["passed"],
      str(gn2["reasons"]))
check("gate fails with write service", not pc.gate(mw, **GOOD)["passed"])
check("gate fails on wrong bitrate",
      not pc.gate(m, **{**GOOD, "listen_bitrate": 125000})["passed"])
check("gate fails with no recorded conditions",
      not pc.gate(m, listen_bitrate=500000, name="x")["passed"])
check("gate fails with no voltage",
      not pc.gate(m, **{**GOOD, "pre": {"engine_state": "off"}})["passed"])
check("gate fails with no name", not pc.gate(m, **{**GOOD, "name": ""})["passed"])
# blocked module (ABS target 0x28? use RFHUB C7 per audit log) on CAN-C
mb = pc.review(build([([0x10, 0x03], [0x50, 0x03, 0, 0x32, 1, 0xF4]),
                      ([0x2F, 0xDE, 0x01, 0x03, 0x01], [0x6F, 0xDE, 0x01, 0x03, 0x01]),
                      ([0x2F, 0xDE, 0x01, 0x00], [0x6F, 0xDE, 0x01, 0x00])], target="C7"))["modules"][0]
check("RFHUB gate fails (blocked module)", not pc.gate(mb, **GOOD)["passed"])
# read-only capture is not an actuator test
mr = pc.review(build([([0x22, 0xDE, 0x00], [0x62, 0xDE, 0x00, 1])]))["modules"][0]
check("read-only capture fails gate", not pc.gate(mr, **GOOD)["passed"])
check("empty capture report", "No UDS requests" in pc.review([])["text"])

print(f"{checks - len(failures)}/{checks} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
