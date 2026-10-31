"""abs_connect_test: a bounded, read-only ladder of routes to ONE chassis module.

Why it exists (2026-10-31): CUORE got only ``NO DATA`` from the ABS on CAN-CH while
MultiEcuScan read it minutes later on the same cable. The only CUORE contact that ever
answered was one 253-target discover sweep (2026-10-15 00:08). The code could not say which
adapter setting separates the two, and the normal path throws away what the adapter says to
each addressing command. This tool tries a few different, ranked ways of asking the module
the same small question, one request each, writes down exactly what was sent and what came
back, and stops at the first answer. The bench then shows which route works, with no guessing.

Rules it keeps (all enforced here, none relaxed):

* CAN-CH only, grey A6 cable declared, 500 kbit/s, the bus verified by a passive listen, and
  ``confirm=True``. Otherwise it refuses before any byte leaves the adapter.
* The adapter protocol is never changed (no ``STP``, no ``STPBR``): the session's own
  ``STP 34`` at 500k stays in force, so a wrong-rate frame is impossible.
* Read-only services only: ``22 F190``, ``3E 00``, ``10 01`` (default session). Each one goes
  through ``assert_read_only_uds`` and the transport's consent belt.
* A handful of frames: at most :data:`MAX_REQUESTS` requests, no sweeps, stops at the first
  answer and at the first adapter/bus error.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import audit
from . import uds as uds_mod
from .buses import CAN_CH
from .errors import BadCommand, Refused
from .framing import negative_responses
from .safety import assert_read_only_uds, assert_transmit_allowed
from .transport import Session, declared_rate, link

REQUIRED_CABLE = "grey_a6"
REQUIRED_RATE = 500000
MAX_REQUESTS = 5
#: Adapter errors that end the test at once: the bus is complaining, do not keep sending.
STOP_ERRORS = ("BUS ERROR", "CAN ERROR", "BUFFER FULL", "FB ERROR", "OUT OF MEMORY",
               "UNABLE TO CONNECT", "LV RESET", "ACT ALERT")

#: Setup commands this test may send. Protocol, bit rate, monitor and filter-table commands
#: are not on it, so no route can change what the adapter runs at.
_ALLOWED_SETUP = re.compile(
    r"^(ATST[0-9A-F]{2}|ATAT[012]|ATCP[0-9A-F]{2}|ATSH[0-9A-F]{6,8}|ATCRA(?:[0-9A-F]{8})?|"
    r"ATFCSM[01]|ATFCSD[0-9A-F]+|ATFCSH[0-9A-F]{8}|STCFCPC|STCFCPA [0-9A-F]{8},[0-9A-F]{8})$")


class _Step:
    """One route: setup commands, one request, and what the adapter said to each."""

    def __init__(self, name: str, why: str) -> None:
        self.name, self.why = name, why
        self.commands: list[dict[str, str]] = []
        self.request: Optional[str] = None
        self.raw: Optional[str] = None
        self.error: Optional[str] = None
        self.headers_seen: list[str] = []
        self.outcome = "silent"
        self.nrc: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {"route": self.name, "why": self.why, "commands": self.commands,
                "request": self.request, "raw": self.raw, "error": self.error,
                "headers_seen": self.headers_seen, "outcome": self.outcome, "nrc": self.nrc}


def _setup(sess: Session, step: _Step, command: str) -> None:
    if not _ALLOWED_SETUP.match(command):
        raise Refused(f"abs_connect_test never sends {command!r}")
    step.commands.append({"sent": command, "got": sess.cmd(command, 2)})


def _ask(sess: Session, step: _Step, ecu: Any, request_hex: str, timeout: float = 1.5) -> bool:
    """Send one read-only request, record everything, return True if anything answered."""
    service = int(request_hex[:2], 16)
    assert_read_only_uds(service, bytes.fromhex(request_hex[2:]))
    step.request = request_hex
    q = sess.query(request_hex, f"{service + 0x40:02X}", timeout)
    step.raw, step.error = q["raw"], q["error"]
    step.headers_seen = sorted(h for h in q["all_ecus"] if h)
    if q["ecus"]:
        step.outcome = "positive"
    else:
        nrc = negative_responses(q["all_ecus"], f"{service:02X}")
        if nrc:
            step.outcome, step.nrc = "negative", next(iter(nrc.values()))
        elif q["all_ecus"]:
            step.outcome = "other_reply"
    other = [h for h in step.headers_seen if ecu.response_hex and h != ecu.response_hex.upper()]
    if other and step.outcome != "silent":
        step.outcome += "_from_other_id"
    audit.record("abs_connect_step", route=step.name, request=request_hex, outcome=step.outcome,
                 raw=(step.raw or "")[:200], error=step.error, commands=step.commands)
    return step.outcome != "silent"


def _routes(sess: Session, ecu: Any) -> list[tuple[_Step, Any]]:
    """The ranked routes as (step, runner). Order matters: cheapest and most likely first."""
    req, resp = ecu.request_hex, ecu.response_hex
    tt = req[4:6]                                   # target byte, e.g. 2A
    six = f"{req[2:]}"                              # DA2AF1: lower 24 bits for ATSH after ATCP18

    def r1(st: _Step) -> bool:                      # the path every CUORE tool uses today
        sess.target_raw(req, resp)
        st.commands = [dict(c) for c in sess.last_setup]
        return _ask(sess, st, ecu, "22F190")

    def r2(st: _Step) -> bool:                      # single frame, no flow control involved
        sess.target_raw(req, resp)
        return _ask(sess, st, ecu, "3E00")

    def r3(st: _Step) -> bool:                      # adapter-default ISO-TP flow control
        for c in ("STCFCPC", "ATFCSM0", f"ATSH{req}", f"ATCRA{resp}"):
            _setup(sess, st, c)
        return _ask(sess, st, ecu, "22F190")

    def r4(st: _Step) -> bool:                      # 6-digit header, receive filter removed
        for c in ("ATCP18", f"ATSH{six}", "ATCRA"):
            _setup(sess, st, c)
        return _ask(sess, st, ecu, "22F190")

    def r5(st: _Step) -> bool:                      # same wiring, default diagnostic session
        return _ask(sess, st, ecu, "1001")

    return [
        (_Step("1_production_22F190",
               f"exactly what read_module_identity sends: ATSH {req}, ATCRA {resp}, STCFCPA, "
               "ATFCSM1 custom flow control, then 22 F190"), r1),
        (_Step("2_tester_present_3E00",
               "same addressing, but a single-frame request: if this answers while 22 F190 "
               "did not, the module is reachable and the flow-control/multi-frame side is at fault"), r2),
        (_Step("3_default_flow_control_22F190",
               "clear the flow-control pair table, adapter default flow control (ATFCSM0), then "
               "22 F190: tests whether the custom flow control CUORE adds is what breaks it"), r3),
        (_Step("4_six_digit_header_open_filter_22F190",
               f"ATCP18 + ATSH {six} (the form MES-style probes use) with NO receive filter: any "
               "reply from any 29-bit responder is shown, so a module that answers from another "
               f"id than {resp} becomes visible"), r4),
        (_Step("5_default_session_1001",
               "10 01 (default diagnostic session, read-only) in the same open-filter set-up: "
               "tests whether the module wants a session started before it answers"), r5),
    ]


def abs_connect_test(code: str = "ABS", vin: str = "", confirm: bool = False,
                     **kw: Any) -> dict[str, Any]:
    """Try the ranked routes to one CAN-CH module until one answers. See the module docstring."""
    ecu = uds_mod.resolve_module(code, vin or None)
    if ecu.bus_key != CAN_CH.key:
        raise BadCommand(f"abs_connect_test is for CAN-CH modules only; {ecu.code} is on {ecu.bus_key}")
    if not ecu.request_hex or not ecu.response_hex:
        raise BadCommand(f"module {ecu.code} has no address")
    lk = link()
    if lk.cable != REQUIRED_CABLE:
        raise Refused(f"abs_connect_test needs the grey A6 cable declared (cable is {lk.cable!r}); "
                      "fit it, declare it (set_cable grey_a6), then verify the bus")
    if declared_rate(CAN_CH, lk.cable) != REQUIRED_RATE:
        raise Refused("CAN-CH is only ever used at 500 kbit/s; refusing")
    if not lk.is_verified(CAN_CH):
        raise Refused("CAN-CH has not been verified under the grey cable (or the proof is stale): "
                      "run verify_bus can_ch first so a passive listen proves 500 kbit/s traffic")
    assert_transmit_allowed(bus_key=CAN_CH.key, bus_cable_ok=True, verified=True,
                            needs_confirmation=True, confirmed=bool(confirm))
    steps: list[dict[str, Any]] = []
    answered_by: Optional[str] = None
    stopped = ""
    with lk.session(f"abs_connect_test {ecu.code}", bus=CAN_CH, confirm=True, **kw) as sess:
        if (sess.route.stn_protocol != "34" or sess.route.bitrate_override
                or sess.header_bits != 29 or sess.bus.bitrate != REQUIRED_RATE):
            raise Refused("session is not on the 29-bit 500 kbit/s CAN-CH route; refusing")
        proto = {"stn_protocol": sess.route.stn_protocol, "header_bits": sess.header_bits,
                 "bitrate": sess.bus.bitrate, "adapter_wait_s": None}
        try:
            first = _Step("0_adapter_timing", "full adapter reply window so a slow module is not cut off")
            for c in ("ATAT0", "ATSTFF"):
                _setup(sess, first, c)
            proto["adapter_wait_s"] = round(sess.adapter_wait, 2)
            sent = 0
            for step, run in _routes(sess, ecu):
                if sent >= MAX_REQUESTS:
                    break
                sent += 1
                got = run(step)
                steps.append(step.as_dict())
                if got:
                    answered_by = step.name
                    break
                if step.error and any(e in step.error.upper() for e in STOP_ERRORS):
                    stopped = f"stopped at {step.name}: adapter reported {step.error}"
                    break
        finally:
            try:
                sess.untarget()
            except Exception as exc:  # noqa: BLE001 -- restoring must never hide the result
                stopped = (stopped + "; " if stopped else "") + f"restore after test failed: {exc}"
    out: dict[str, Any] = {
        "module": ecu.code, "bus": CAN_CH.key, "cable": lk.cable, "rate": REQUIRED_RATE,
        "protocol": proto, "request_id": ecu.request_hex, "response_id": ecu.response_hex,
        "requests_sent": len(steps), "max_requests": MAX_REQUESTS, "steps": steps,
        "answered_by": answered_by, "stopped": stopped or None,
        "read_only": True,
    }
    out["conclusion"] = _conclusion(out)
    audit.record("abs_connect_test", module=ecu.code, answered_by=answered_by,
                 requests=len(steps), stopped=stopped or None)
    return out


def _conclusion(out: dict[str, Any]) -> str:
    by = out["answered_by"]
    if by:
        return (f"{out['module']} answered on route {by}. That route's commands (in 'steps') are the "
                "ones that reach it; compare them with route 1_production_22F190. If route 1 "
                "itself answered, the normal path works and the earlier silence was the car's "
                "state (ignition/wake), not CUORE's set-up.")
    if out["stopped"]:
        return out["stopped"]
    return (f"{out['module']} stayed silent on all {out['requests_sent']} routes with the bus "
            "verified. CUORE's addressing, flow control and session variants are then not what "
            "separates it from MES; see BENCH_TEST.md for the next step.")
