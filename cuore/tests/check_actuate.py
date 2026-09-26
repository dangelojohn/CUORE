"""Checks for actuator tests learned from a dealer tool and replayed under guards.

Same posture as ``check_clear.py`` and ``check_learn.py``: plain script,
``check()``, exit 1 on failure, no pytest, no mocking framework. Part 1
exercises ``actuate.extract_procedure`` against synthetic capture frames
(same helpers as ``check_learn.py``); part 2 exercises the replay guards and
the replay itself against a hand-built fake UDS module.

Run:
    .venv/Scripts/python.exe cuore/tests/check_actuate.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-actuate-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import actuate, interlock, ops, store  # noqa: E402
from cuore.live.errors import Refused  # noqa: E402
from cuore.live.learn import uds_transactions  # noqa: E402
from cuore.live.safety import assert_read_only_uds  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0
interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label, got, want):
    check(label, got == want, f"got {got!r} want {want!r}")


def raises(exc, fn):
    try:
        fn()
    except exc as e:
        return str(e)
    return None


# ===========================================================================
# Part 1: extract_procedure, from synthetic capture frames
# ===========================================================================

def frame(t: float, can_id: str, byte_list: list[str]) -> dict:
    return {"t": t, "id": can_id, "data": "".join(byte_list)}


def sf(byte_values: list[int]) -> list[str]:
    n = len(byte_values)
    assert n <= 7
    return [f"0{n:X}"] + [f"{v:02X}" for v in byte_values]


# --- 1a. a 2F test: 10 03, 2F <did> 03 <state>, 2F <did> 00, 10 01 ---------

frames_2f_full = [
    frame(0.0, "18DA10F1", sf([0x10, 0x03])),
    frame(0.01, "18DAF110", sf([0x50, 0x03])),
    frame(1.0, "18DA10F1", sf([0x2F, 0x12, 0x34, 0x03, 0xAA])),
    frame(1.01, "18DAF110", sf([0x6F, 0x12, 0x34, 0x03, 0xAA])),
    frame(2.0, "18DA10F1", sf([0x2F, 0x12, 0x34, 0x00])),
    frame(2.01, "18DAF110", sf([0x6F, 0x12, 0x34, 0x00])),
    frame(3.0, "18DA10F1", sf([0x10, 0x01])),
    frame(3.01, "18DAF110", sf([0x50, 0x01])),
]
proc_2f = actuate.extract_procedure(uds_transactions(frames_2f_full), "10")
check("2F full procedure: replayable", proc_2f["replayable"] is True, str(proc_2f))
check_eq("2F full procedure: kind", proc_2f["kind"], "io_control")
check_eq("2F full procedure: step count", len(proc_2f["steps"]), 4)
check_eq("2F full procedure: ended_with_terminator", proc_2f["ended_with_terminator"], True)
check("2F full procedure: no synthesised terminator needed", proc_2f["synthesised_terminator"] is None)
check_eq("2F full procedure: session entered", proc_2f["session_sub"], "03")

# --- 1b. a 31 routine start/stop -------------------------------------------

frames_31 = [
    frame(0.0, "18DA10F1", sf([0x31, 0x01, 0x20, 0x01])),
    frame(0.01, "18DAF110", sf([0x71, 0x01, 0x20, 0x01])),
    frame(1.0, "18DA10F1", sf([0x31, 0x02, 0x20, 0x01])),
    frame(1.01, "18DAF110", sf([0x71, 0x02, 0x20, 0x01])),
]
proc_31 = actuate.extract_procedure(uds_transactions(frames_31), "10")
check("31 start/stop: replayable", proc_31["replayable"] is True, str(proc_31))
check_eq("31 start/stop: kind", proc_31["kind"], "routine_control")
check_eq("31 start/stop: ended_with_terminator", proc_31["ended_with_terminator"], True)
check("31 start/stop: no synthesised terminator needed", proc_31["synthesised_terminator"] is None)

# --- 1c. a procedure containing 0x27 -> not replayable ---------------------

frames_27 = [
    frame(0.0, "18DA10F1", sf([0x10, 0x03])),
    frame(0.01, "18DAF110", sf([0x50, 0x03])),
    frame(1.0, "18DA10F1", sf([0x27, 0x01])),
    frame(1.01, "18DAF110", sf([0x67, 0x01, 0xAA, 0xBB, 0xCC, 0xDD])),
    frame(2.0, "18DA10F1", sf([0x27, 0x02, 0x11, 0x22, 0x33, 0x44])),
    frame(2.01, "18DAF110", sf([0x67, 0x02])),
    frame(3.0, "18DA10F1", sf([0x2F, 0x12, 0x34, 0x03, 0xAA])),
    frame(3.01, "18DAF110", sf([0x6F, 0x12, 0x34, 0x03, 0xAA])),
    frame(4.0, "18DA10F1", sf([0x2F, 0x12, 0x34, 0x00])),
    frame(4.01, "18DAF110", sf([0x6F, 0x12, 0x34, 0x00])),
]
proc_27 = actuate.extract_procedure(uds_transactions(frames_27), "10")
check("0x27 present: requires_security_access", proc_27["requires_security_access"] is True)
check("0x27 present: not replayable", proc_27["replayable"] is False)
check("0x27 present: reason names SecurityAccess",
      any("SecurityAccess" in r for r in proc_27["reasons"]), str(proc_27["reasons"]))

# --- 1d. a procedure containing 0x2E -> not replayable ---------------------

frames_2e = [
    frame(0.0, "18DA10F1", sf([0x10, 0x03])),
    frame(0.01, "18DAF110", sf([0x50, 0x03])),
    frame(1.0, "18DA10F1", sf([0x2E, 0xF1, 0x90, 0x41, 0x42])),
    frame(1.01, "18DAF110", sf([0x6E, 0xF1, 0x90])),
]
proc_2e = actuate.extract_procedure(uds_transactions(frames_2e), "10")
check("0x2E present: not replayable", proc_2e["replayable"] is False)
check("0x2E present: reason names WriteDataByIdentifier",
      any("2E" in r for r in proc_2e["reasons"]), str(proc_2e["reasons"]))

# --- 1e. missing terminator -> synthesised ---------------------------------

frames_missing = [
    frame(0.0, "18DA10F1", sf([0x10, 0x03])),
    frame(0.01, "18DAF110", sf([0x50, 0x03])),
    frame(1.0, "18DA10F1", sf([0x2F, 0x12, 0x34, 0x03, 0xAA])),
    frame(1.01, "18DAF110", sf([0x6F, 0x12, 0x34, 0x03, 0xAA])),
]
proc_missing = actuate.extract_procedure(uds_transactions(frames_missing), "10")
check("missing terminator: not already ended", proc_missing["ended_with_terminator"] is False)
check("missing terminator: still replayable (only 10/2F used)", proc_missing["replayable"] is True,
      str(proc_missing))
term = proc_missing["synthesised_terminator"]
check("missing terminator: one was synthesised", term is not None, str(proc_missing))
if term:
    check_eq("missing terminator: synthesised payload", term["payload"], ["12", "34", "00"])
    check("missing terminator: flagged synthesised", term["synthesised"] is True)

# --- 1f. persistence round trip --------------------------------------------

saved = actuate.save_actuator(VIN, "ECM", "Evap valve", proc_2f, source="cap1.json", tool="MES")
check_eq("save_actuator: module stamped", saved["module"], "ECM")
got = actuate.get_actuator(VIN, "ECM", "Evap valve")
check("get_actuator: round trip", got is not None and got["replayable"] is True, str(got))
listing = actuate.list_actuators(VIN)
check("list_actuators: entry present",
      any(r["name"] == "Evap valve" for r in listing.get(VIN, [])), str(listing))
check("actuators.json: written to the state dir", actuate.path().exists() and
      str(actuate.path()).startswith(_TMP))


# ===========================================================================
# Part 2: replay guards and replay itself, over a fake UDS module
# ===========================================================================

def _frames(header: str, payload: str) -> str:
    n = len(payload) // 2
    if n <= 7:
        return f"{header}{n:02X}{payload}"
    out = [f"{header}1{n:03X}{payload[:12]}"]
    rest, seq = payload[12:], 1
    while rest:
        out.append(f"{header}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


class FakeECU(Stream):
    """A UDS module that acks whatever it is sent, with a per-command script
    for negative responses and simulated stream failures. Also answers the
    legislated Mode 01 PIDs 0C (RPM) and 0D (speed) that ops.run_actuator
    reads before actuating."""

    def __init__(self, script: dict[str, str] | None = None, rpm_raw: int = 0, speed: int = 0,
                header: str = "18DAF110") -> None:
        self.script = {k.upper(): v for k, v in (script or {}).items()}
        self.rpm_raw = rpm_raw
        self.speed = speed
        self.header = header
        self.sent: list[str] = []
        self.proto = ""
        self._buf = bytearray()
        self._open = False

    def open(self): self._open = True
    def close(self): self._open = False
    def is_open(self): return self._open
    @property
    def describe(self): return "serial COM99@115200 (fake)"

    def _uds_reply(self, cmd: str) -> str:
        rule = self.script.get(cmd.upper())
        svc = cmd[:2]
        if rule == "RAISE":
            raise OSError("simulated stream failure")
        if isinstance(rule, str) and rule.startswith("NRC:"):
            payload = f"7F{svc}{rule.split(':', 1)[1]}"
        else:
            resp_svc = f"{(int(svc, 16) + 0x40) & 0xFF:02X}"
            payload = resp_svc + cmd[2:]
        return _frames(self.header, payload)

    def _reply(self, cmd: str) -> str:
        if not cmd:
            return ""  # capture.listen's monitor-interrupt byte: no reply needed, just the prompt
        if cmd.startswith("STP "):
            self.proto = cmd[4:]
            return "OK"
        if cmd == "STM":
            return "1E36000100112233\r1E36000B00112233"
        if cmd == "010C":
            return f"7E804410C{self.rpm_raw:04X}" if self.proto == "33" else "NO DATA"
        if cmd == "010D":
            return f"7E803410D{self.speed:02X}" if self.proto == "33" else "NO DATA"
        if cmd.startswith(("AT", "ST")):
            return {"ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2", "ATRV": "12.4V"}.get(cmd, "OK")
        return self._uds_reply(cmd)

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").strip()
        self.sent.append(cmd)
        reply = self._reply(cmd)  # may raise -- propagates out of Session.cmd
        self._buf.extend(reply.encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    def reset_input_buffer(self): self._buf.clear()
    def in_waiting(self): return len(self._buf)


def use(car: FakeECU) -> AdapterLink:
    lk = AdapterLink(stream_factory=lambda p, b: car, process="check_actuate")
    lk.auto_verify_seconds = 0.2
    set_link(lk)
    return lk


def actuation_sent(car: FakeECU) -> list[str]:
    """``car.sent`` minus AT/ST adapter setup, the monitor interrupt, and PID reads."""
    return [c for c in car.sent
           if c and c[:2] not in ("AT", "ST") and c not in ("010C", "010D")]


def make_procedure(name: str, *, steps, replayable=True, reasons=None,
                   requires_security_access=False, ended_with_terminator=True,
                   synthesised_terminator=None, session_sub="03") -> dict:
    return {
        "target": "10", "kind": "io_control", "steps": steps, "replayable": replayable,
        "requires_security_access": requires_security_access, "reasons": reasons or [],
        "ended_with_terminator": ended_with_terminator,
        "synthesised_terminator": synthesised_terminator,
        "used_tester_present": False, "session_sub": session_sub, "name": name,
    }


def step(t: float, service: str, payload: list[str]) -> dict:
    return {"t_req": t, "t_resp": t + 0.005, "service": service, "payload": payload,
           "request": [service, *payload], "response": None, "nrc": None, "synthesised": False}


# --- 2a. refused without the exact consent phrase; nothing reaches the wire

car = FakeECU()
use(car)
proc_a = make_procedure("Test A", steps=[
    step(0.0, "10", ["03"]), step(0.01, "2F", ["12", "34", "03", "AA"]),
    step(0.02, "2F", ["12", "34", "00"]), step(0.03, "10", ["01"]),
])
actuate.save_actuator(VIN, "ECM", "Test A", proc_a, source="test", tool="MES")
msg = raises(Refused, lambda: ops.run_actuator(VIN, "ECM", "Test A", "please actuate this"))
check("wrong consent phrase is refused", msg is not None and "ACTUATE ECM TEST A" in msg, str(msg))
check("nothing was sent to the car without consent", car.sent == [], str(car.sent))

# --- 2b. refused outright for ABS (safety-critical / CAN-CH); nothing sent -

store.confirm_target(VIN, "ABS", 0x28, source="test")
car = FakeECU()
use(car)
proc_abs = make_procedure("Test B", steps=[
    step(0.0, "2F", ["55", "66", "03", "01"]), step(1.0, "2F", ["55", "66", "00"]),
])
actuate.save_actuator(VIN, "ABS", "Test B", proc_abs, source="test", tool="MES")
consent_abs = actuate.consent_phrase("ABS", "Test B")
msg = raises(Refused, lambda: ops.run_actuator(VIN, "ABS", "Test B", consent_abs))
check("ABS actuation is refused outright", msg is not None and "safety-critical" in msg, str(msg))
check("nothing was sent to the car for a blocked module", car.sent == [], str(car.sent))

# --- 2c. a non-replayable procedure (0x27) is refused; nothing sent -------

car = FakeECU()
use(car)
proc_g = make_procedure("Test G", steps=[step(0.0, "27", ["01"])], replayable=False,
                        requires_security_access=True,
                        reasons=["procedure includes UDS 0x27 SecurityAccess"])
actuate.save_actuator(VIN, "ECM", "Test G", proc_g, source="test", tool="MES")
consent_g = actuate.consent_phrase("ECM", "Test G")
msg = raises(Refused, lambda: ops.run_actuator(VIN, "ECM", "Test G", consent_g))
check("a non-replayable procedure is refused", msg is not None and "not replayable" in msg, str(msg))
check("nothing was sent for a non-replayable procedure", car.sent == [], str(car.sent))

# --- 2d. refused while the engine is running -------------------------------

car = FakeECU(rpm_raw=400)  # 400/4 = 100 rpm
use(car)
proc_c = make_procedure("Test C", steps=[
    step(0.0, "2F", ["12", "34", "03", "AA"]), step(1.0, "2F", ["12", "34", "00"]),
])
actuate.save_actuator(VIN, "ECM", "Test C", proc_c, source="test", tool="MES")
consent_c = actuate.consent_phrase("ECM", "Test C")
msg = raises(Refused, lambda: ops.run_actuator(VIN, "ECM", "Test C", consent_c))
check("a running engine is refused", msg is not None and "running" in msg, str(msg))
check("no actuation request sent while the engine is running", actuation_sent(car) == [],
      str(car.sent))

# --- 2e. refused while the vehicle is moving -------------------------------

car = FakeECU(speed=30)
use(car)
proc_c2 = make_procedure("Test C2", steps=[
    step(0.0, "2F", ["12", "34", "03", "AA"]), step(1.0, "2F", ["12", "34", "00"]),
])
actuate.save_actuator(VIN, "ECM", "Test C2", proc_c2, source="test", tool="MES")
consent_c2 = actuate.consent_phrase("ECM", "Test C2")
msg = raises(Refused, lambda: ops.run_actuator(VIN, "ECM", "Test C2", consent_c2))
check("a moving vehicle is refused", msg is not None and "km/h" in msg, str(msg))
check("no actuation request sent while moving", actuation_sent(car) == [], str(car.sent))

# --- 2f. replay success: in order, an NRC mid-procedure does not abort it -

car = FakeECU(script={"2F123403AA": "NRC:22"})
use(car)
proc_d = make_procedure("Test D", steps=[
    step(0.0, "10", ["03"]), step(0.01, "2F", ["12", "34", "03", "AA"]),
    step(0.02, "2F", ["12", "34", "00"]), step(0.03, "10", ["01"]),
])
actuate.save_actuator(VIN, "ECM", "Test D", proc_d, source="test", tool="MES")
consent_d = actuate.consent_phrase("ECM", "Test D")
out_d = ops.run_actuator(VIN, "ECM", "Test D", consent_d)
check("replay reports control returned", out_d.get("control_returned") is True, str(out_d))
check("replay reports session restored", out_d.get("session_restored") is True, str(out_d))
check_eq("requests are sent in order despite a mid-procedure NRC", actuation_sent(car),
        ["1003", "2F123403AA", "2F123400", "1001"])
check("the NRC step is reported, not hidden",
      any(s.get("label") == "learned" and s.get("nrc") for s in out_d["steps"]), str(out_d["steps"]))

# --- 2g. replay: the stream raising mid-procedure still gets a terminator -

car = FakeECU(script={"2F123403AA": "RAISE"})
use(car)
proc_e = make_procedure("Test E", steps=[
    step(0.0, "10", ["03"]), step(0.01, "2F", ["12", "34", "03", "AA"]),
    step(0.02, "2F", ["12", "34", "00"]), step(0.03, "10", ["01"]),
])
actuate.save_actuator(VIN, "ECM", "Test E", proc_e, source="test", tool="MES")
consent_e = actuate.consent_phrase("ECM", "Test E")
out_e = ops.run_actuator(VIN, "ECM", "Test E", consent_e)
check("a raising step is reported, not raised out of run_actuator",
      any(s.get("label") == "learned" and s.get("error") for s in out_e["steps"]), str(out_e["steps"]))
check("the terminator is still sent after a mid-procedure raise",
      "2F123400" in actuation_sent(car), str(car.sent))
check("control_returned True even though a step raised", out_e.get("control_returned") is True,
      str(out_e))

# --- 2h. max_seconds bounds the replay; the terminator is still sent ------

car = FakeECU()
use(car)
proc_f = make_procedure("Test F", steps=[
    step(0.0, "10", ["03"]),
    step(5.0, "2F", ["12", "34", "03", "AA"]),   # 5s gap forces an early stop under budget=1s
    step(10.0, "2F", ["12", "34", "00"]),
    step(15.0, "10", ["01"]),
])
actuate.save_actuator(VIN, "ECM", "Test F", proc_f, source="test", tool="MES")
consent_f = actuate.consent_phrase("ECM", "Test F")
t0 = time.monotonic()
out_f = ops.run_actuator(VIN, "ECM", "Test F", consent_f, max_seconds=1.0)
elapsed = time.monotonic() - t0
check("max_seconds bounds the whole replay", elapsed < 5.0, f"elapsed {elapsed:.2f}s")
check("a budget note is recorded when the replay is cut short",
      any(s.get("label") == "budget" for s in out_f["steps"]), str(out_f["steps"]))
check("the terminator is still sent when the budget cuts the replay short",
      "2F123400" in actuation_sent(car), str(car.sent))

# --- 2i. the read-only path (uds.request) still refuses 0x2F and 0x31 -----

msg = raises(Refused, lambda: assert_read_only_uds(0x2F, bytes([0x12, 0x34, 0x03, 0xAA])))
check("the read-only allowlist refuses 0x2F", msg is not None, str(msg))
msg = raises(Refused, lambda: assert_read_only_uds(0x31, bytes([0x01, 0x20, 0x01])))
check("the read-only allowlist refuses 0x31", msg is not None, str(msg))

# --- 2j. list-only over HTTP: no run route -----------------------------------

from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402
paths = list(create_app().openapi().get("paths", {}))
check("the actuators list route exists over HTTP", "/api/live/actuators" in paths, str(paths))
check("no HTTP route can run an actuator test",
      not any("actuat" in p.lower() and "run" in p.lower() for p in paths),
      str([p for p in paths if "actuat" in p.lower()]))


from cuore.live import safety as _safety  # noqa: E402
for _code in ("TCM", "ESM", "DTCM", "RFHUB"):
    try:
        _safety.assert_actuation_module_allowed(_code, "can_c")
        _refused = False
    except Exception:
        _refused = True
    check(f"actuation refused on {_code} (driveline / park lock / immobiliser)", _refused)


# --- review fixes: budget, terminator acceptance, routine consent ------------------
import time as _time  # noqa: E402
from types import SimpleNamespace as _NS  # noqa: E402
from cuore.live import actuate as _act, addressing as _addr  # noqa: E402
from cuore.live.errors import Refused as _Refused  # noqa: E402


class _FakeSess:
    def __init__(self, terminator_reply="ok", raise_on=None):
        self.sent = []
        self.bus = _NS(key="can_c")
        self.link = _NS(cable="none")
        self.stream = _NS(describe="serial COM99 (fake)")
        self.terminator_reply = terminator_reply
        self.raise_on = raise_on

    def uds(self, ecu, service, payload=b"", timeout=3.0, retries_on_pending=3):
        req = f"{service:02X}{payload.hex().upper()}"
        self.sent.append((req, timeout, retries_on_pending))
        if self.raise_on and req.startswith(self.raise_on):
            raise OSError("adapter unplugged")
        is_term = service == 0x2F and payload[2:3] == bytes([0])
        if is_term and self.terminator_reply == "nrc":
            return {"positive": {}, "nrc": {"18DAF110": 0x22}, "error": None, "raw": ""}
        return {"positive": {"18DAF110": [f"{service + 0x40:02X}"]}, "nrc": {}, "error": None,
                "raw": ""}


_ecm = _addr.by_code("ECM")
_proc = {"name": "Budget", "vin": "V", "replayable": True, "reasons": [], "session_sub": None,
         "steps": [{"service": "2F", "payload": ["12", "34", "03", "01"], "request": [], "t_req": 0.0},
                   {"service": "2F", "payload": ["12", "34", "03", "02"], "request": [], "t_req": 0.9},
                   {"service": "2F", "payload": ["12", "34", "03", "03"], "request": [], "t_req": 5.9}],
         "synthesised_terminator": {"service": "2F", "payload": ["12", "34", "00"], "request": []}}
_s = _FakeSess()
_t0 = _time.monotonic()
_r = _act.run_actuator(_s, _ecm, _proc, consent="ACTUATE ECM BUDGET", max_seconds=1.0)
_el = _time.monotonic() - _t0
check("a long learned gap cannot stretch the budget", _el < 1.5, f"{_el:.2f}s")
check("the third step (after the 5 s gap) was never sent",
      not any(req.endswith("0302") is False and req.endswith("0303") for req, *_ in _s.sent),
      str(_s.sent))
check("learned steps get no responsePending retries",
      all(r == 0 for req, to, r in _s.sent if req.endswith(("0301", "0302", "0303"))), str(_s.sent))
check("control returned when the module accepts the terminator", _r["control_returned"] is True)

_s2 = _FakeSess(terminator_reply="nrc")
_r2 = _act.run_actuator(_s2, _ecm, dict(_proc, name="Refused"), consent="ACTUATE ECM REFUSED",
                        max_seconds=0.5)
check("a refused terminator is NOT counted as control returned", _r2["control_returned"] is False)
check("and the outcome tells the mechanic to switch the ignition off",
      "ignition OFF" in _r2["outcome"], _r2["outcome"])

_s3 = _FakeSess(raise_on="2F")
_r3 = _act.run_actuator(_s3, _ecm, dict(_proc, name="Unplugged"), consent="ACTUATE ECM UNPLUGGED",
                        max_seconds=0.5)
check("adapter failure mid-test leaves control unconfirmed and says so",
      _r3["control_returned"] is False and "ignition OFF" in _r3["outcome"], str(_r3["outcome"]))

_routine = {"name": "Relearn", "vin": "V", "replayable": True, "reasons": [], "session_sub": None,
            "steps": [{"service": "31", "payload": ["01", "AB", "CD"], "request": [], "t_req": 0.0}],
            "synthesised_terminator": {"service": "31", "payload": ["02", "AB", "CD"], "request": []}}
check("a routine is recognised", _act.is_routine(_routine))
try:
    _act.run_actuator(_FakeSess(), _ecm, _routine, consent="ACTUATE ECM RELEARN")
    _msg = None
except _Refused as e:
    _msg = str(e)
check("a routine refuses the ordinary actuation phrase", _msg is not None and "RUN ROUTINE" in _msg,
      str(_msg))
_r4 = _act.run_actuator(_FakeSess(), _ecm, _routine, consent="RUN ROUTINE ECM RELEARN")
check("a routine runs with its own phrase and is flagged", _r4["routine"] is True)

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
