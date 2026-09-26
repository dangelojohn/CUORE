"""Checks for whole-vehicle coverage, identity-matched discovery, and the
2026-09-25 live-link fixes.

Same posture as check_live.py: plain script, ``check()``, exit 1 on failure.
Runs against a temporary state directory so it never touches the bench's
real address confirmations or coverage session.

Run:
    .venv/Scripts/python.exe cuore/tests/check_coverage.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-coverage-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import addressing, coverage, identify, interlock, ops, store  # noqa: E402
from cuore.live import uds as uds_mod  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.errors import BadCommand, Refused  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want) -> None:
    check(label, got == want, f"got {got!r} want {want!r}")


def raises(exc, fn) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running",
                                "label": None}


# ===========================================================================
# 1. identity matching (pure)
# ===========================================================================

DASM = addressing.by_code("DASM")
ECM = addressing.by_code("ECM")
check_eq("normalise drops the MES version suffix", identify.normalise("MRR1evo14F (00)"),
         "MRR1EVO14F")
check_eq("normalise strips padding and punctuation", identify.normalise(" 52081920   "),
         "52081920")
check_eq("registry tokens for DASM", identify.registry_tokens(DASM),
         {"hw_number": "MRR1EVO14F", "sw_number": "52081920"})

m = identify.match({"F192": "MRR1evo14F", "F194": "52081920"},
                   addressing.on_bus("can_c"))
check_eq("DASM identity names DASM", m.get("matched"), "DASM")
check_eq("DASM matched on both numbers", m.get("score"), 2)

# The ECM identity exactly as the car returned it on 2026-09-25.
m = identify.match({"F187": "50544870", "F188": "52170619", "F191": "52055320",
                    "F192": "MM10JAHW232", "F194": "P235QB39", "F18C": "TD4192427B17540"},
                   addressing.on_bus("can_c"))
check_eq("live ECM identity names ECM", m.get("matched"), "ECM")

check_eq("an identity with no Table A number matches nothing",
         identify.match({"F192": "ZZZ999999"}, addressing.on_bus("can_c")).get("matched"),
         None)
check_eq("short tokens never match by containment",
         identify.match({"F192": "00"}, addressing.on_bus("can_c")).get("matched"), None)


# ===========================================================================
# 2. coverage helpers (pure)
# ===========================================================================

recs = [{"code": "P0455-00", "status": 0x4D}, {"code": "P0562-00", "status": 0x40},
        {"code": "P0456-00", "status": 0x08}, {"code": "P0300-00", "status": 0x20 | 0x40},
        {"code": "P0128-00", "status": 0x10}]
cr = coverage.classify_records(recs)
check_eq("classify: active = failed/pending/confirmed bits", cr["active"],
         ["P0455-00", "P0456-00"])
check_eq("classify: history = failed since clear only", cr["history"], ["P0300-00"])
check_eq("classify: tracked counts every record", cr["tracked"], 5)
check_eq("classify: not-run-since-clear counted", cr["not_run_since_clear"], 1)

d = coverage.bystander_diff({"BCM": ["U1711-2F"], "ECM": ["P0455-00"]},
                            {"BCM": ["U1711-2F", "U0100-87"], "ECM": []})
check_eq("diff reports two modules", [x["module"] for x in d], ["BCM", "ECM"])
check_eq("diff: code appearing mid-session is flagged", d[0]["appeared"], ["U0100-87"])
check_eq("diff: code gone on re-read is flagged", d[1]["gone"], ["P0455-00"])
check("diff: appeared codes are read as bystanders", "bystander" in d[0]["reading"])


# ===========================================================================
# 3. coverage session state machine, against a fake ops layer
# ===========================================================================

def rec(code: str, status: int) -> dict:
    return {"code": code, "status": status}


class FakeOps:
    def __init__(self) -> None:
        self.cable = "none"
        self.calls: list[tuple] = []
        self.silent: set[str] = set()
        self.scans: dict[str, list[dict]] = {}

    def cable_state(self) -> dict:
        return {"cable": self.cable}

    def verify_bus(self, bus: str, seconds: float = 2.0) -> dict:
        self.calls.append(("verify", bus))
        if bus in self.silent:
            return {"verified": False, "frames": 0}
        return {"verified": True, "frames": 40, "rate_hz": 20.0}

    def discover(self, bus: str, **kw) -> dict:
        self.calls.append(("discover", bus, kw.get("stop_after"), kw.get("confirm")))
        if bus == "can_c":
            store.confirm_target(VIN, "DASM", 0x7E, source="fake")
        return {"tried": 3, "seconds": 0.1, "hits": []}

    def scan_modules(self, bus: str, **kw) -> dict:
        self.calls.append(("scan", bus, kw.get("confirm")))
        return {"modules": self.scans.get(bus, [])}


fo = FakeOps()
check("run before start is refused", raises(Refused, lambda: coverage.run_pass("c_first", ops=fo)))
check("start needs a 17-character VIN", raises(BadCommand, lambda: coverage.start("ABC")))
coverage.start(VIN, engine_running=True)
check_eq("status names the baseline as next", coverage.status()["next"], "c_first")
check("grey pass refused before the baseline",
      raises(Refused, lambda: coverage.run_pass("ch", ops=fo)))
check("baseline cannot be skipped", raises(Refused, lambda: coverage.skip_pass("c_first", "")))
fo.cable = "grey_a6"
check("baseline refused with the grey cable declared",
      raises(Refused, lambda: coverage.run_pass("c_first", ops=fo)))

fo.cable = "none"
fo.scans["can_c"] = [
    {"ecu": "ECM", "codes": ["P0455-00", "P0562-00"],
     "dtcs": [rec("P0455-00", 0x4D), rec("P0562-00", 0x40)]},
    {"ecu": "BCM", "codes": ["U1711-2F"], "dtcs": [rec("U1711-2F", 0x09)]},
    {"ecu": "IPC", "codes": [], "dtcs": []},
    {"ecu": "TCM", "error": "CAN ERROR", "dtcs": [], "note": "ADAPTER/BUS ERROR"},
    {"ecu": "ESM", "skipped": "no confirmed address"},
]
st = coverage.run_pass("c_first", ops=fo)
disc = [c for c in fo.calls if c[0] == "discover"]
check_eq("baseline discovers the three unaddressed CAN-C modules", disc[0][2], 3)
rep = coverage.report()
rows = {r["code"]: r for r in rep["modules"]}
check_eq("ECM read with one active fault", rows["ECM"]["active"], ["P0455-00"])
check_eq("ECM tracked count kept", rows["ECM"]["tracked"], 2)
check_eq("IPC read clean", rows["IPC"]["status"], "read")
check_eq("TCM bus error is not reported as read", rows["TCM"]["status"], "no_answer")
check_eq("ESM without address reported as such", rows["ESM"]["status"], "no_address")
check_eq("DASM address found this session is shown", rows["DASM"]["address"], "7E")
check_eq("DASM address source is this car", rows["DASM"]["address_source"], "this car")
check_eq("ABS not reached before its pass", rows["ABS"]["status"], "not_reached")
check("bystander note present before the final pass", bool(rep["bystander_note"]))

fo.cable = "grey_a6"
fo.silent = {"can_ch"}
coverage.run_pass("ch", ops=fo, confirm=True)
rows = {r["code"]: r for r in coverage.report()["modules"]}
check_eq("silent grey bus marks its modules bus_silent", rows["ABS"]["status"], "bus_silent")
check("silent bus does not scan",
      not any(c for c in fo.calls if c[0] == "scan" and c[1] == "can_ch"))

check("final re-read refused while blue is pending",
      raises(Refused, lambda: coverage.run_pass("c_final", ops=fo)))
coverage.skip_pass("ihs", "blue cable not on hand")
fo.cable = "none"
fo.scans["can_c"][1] = {"ecu": "BCM", "codes": ["U1711-2F", "U0100-87"],
                        "dtcs": [rec("U1711-2F", 0x09), rec("U0100-87", 0x09)]}
calls_before = len([c for c in fo.calls if c[0] == "discover"])
coverage.run_pass("c_final", ops=fo)
check_eq("final re-read does not sweep addresses",
         len([c for c in fo.calls if c[0] == "discover"]), calls_before)
rep = coverage.report()
check("session finished after the last pass", rep["finished"])
bys = {b["module"]: b for b in rep["bystanders"]}
check_eq("re-plug bystander caught on BCM", bys.get("BCM", {}).get("appeared"), ["U0100-87"])
check("baseline codes stay the reported faults, not the re-read's",
      {"module": "BCM", "bus": "can_c", "active": ["U1711-2F"]} in rep["faults"])
rows = {r["code"]: r for r in rep["modules"]}
check_eq("skipped blue pass marks HVAC skipped", rows["HVAC"]["status"], "skipped")
check("coverage percent is computed", 0 < rep["coverage"]["percent"] < 100,
      str(rep["coverage"]))
coverage.reset()
check("reset clears the session", not coverage.status()["active"])


# ===========================================================================
# 4. discovery on a fake bus: negative replies count, identity names nodes
# ===========================================================================

def _frames(header: str, payload: str) -> str:
    """ISO-TP framing with headers on, as an STN prints it."""
    n = len(payload) // 2
    if n <= 7:
        return f"{header}{n:02X}{payload}"
    out = [f"{header}1{n:03X}{payload[:12]}"]
    rest, seq = payload[12:], 1
    while rest:
        out.append(f"{header}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


def _ascii_hex(s: str) -> str:
    return "".join(f"{ord(c):02X}" for c in s)


class BusStream(Stream):
    """Answers per target: the reply depends on the last ATSH."""

    def __init__(self, nodes: dict[int, dict[str, str]]) -> None:
        self.nodes = nodes
        self.target: int | None = None
        self.sent: list[str] = []
        self._buf = bytearray()
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def _reply(self, cmd: str) -> str:
        if cmd.startswith("ATSH18DA") and len(cmd) == 12:
            self.target = int(cmd[8:10], 16)
            return "OK"
        if cmd in ("ATI",):
            return "ELM327 v2.3"
        if cmd == "STI":
            return "STN1170 v4.3.2"
        if cmd.startswith(("AT", "ST")):
            return "OK"
        node = self.nodes.get(self.target or -1)
        if node is None:
            return "NO DATA"
        header = f"18DAF1{self.target:02X}"
        payload = node.get(cmd)
        if payload is None:
            return _frames(header, "7F" + cmd[:2] + "31")
        return _frames(header, payload)

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").strip()
        self.sent.append(cmd)
        self._buf.extend(self._reply(cmd).encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    def reset_input_buffer(self) -> None:
        self._buf.clear()

    def in_waiting(self) -> int:
        return len(self._buf)

    @property
    def describe(self) -> str:
        return "bus-fake"


nodes = {
    0x10: {"22F190": "62F190" + _ascii_hex(VIN),
           "22F192": "62F192" + _ascii_hex("MM10JAHW232")},
    0x7E: {"22F192": "62F192" + _ascii_hex("MRR1evo14F"),        # refuses F190
           "22F194": "62F194" + _ascii_hex("52081920")},
    0x44: {"22F190": "62F190" + _ascii_hex(VIN)},                  # anonymous, no numbers
}
store.path().unlink(missing_ok=True)   # section 3 confirmed DASM itself; start clean
check_eq("store starts empty for discovery", store.confirmed_targets(VIN), {})
bus = BusStream(nodes)
lk = AdapterLink(stream_factory=lambda p, b: bus, process="check_coverage")
set_link(lk)
lk.mark_verified(CAN_C, 10)
with lk.session("discover-test", bus=CAN_C) as sess:
    res = uds_mod.discover(sess, CAN_C, vin_expected=VIN,
                           candidates=[0x10, 0x55, 0x7E, 0x44], per_target_timeout=0.2)
hits = {h["target"]: h for h in res["hits"]}
check_eq("silent address is not a hit", "55" in hits, False)
check_eq("ECM named by address and identity", hits["10"].get("matched_by"),
         "address+identity")
check("a node refusing F190 still counts as alive", "7E" in hits, str(res["hits"]))
check_eq("the refusing node is named DASM by identity", hits["7E"].get("module"), "DASM")
check_eq("its NRC is reported", hits["7E"].get("vin_nrc"), uds_mod.nrc_text(0x31))
check("DASM persisted on two matching numbers", hits["7E"].get("persisted") is True)
check_eq("store now holds DASM at 7E", store.confirmed_targets(VIN).get("DASM"), 0x7E)
check_eq("an anonymous node with this VIN is reported but not named",
         hits["44"].get("module"), None)
check("anonymous node is not persisted", not hits["44"].get("persisted"))
try:
    _dasm_target = uds_mod.resolve_module("DASM", VIN).target
except BadCommand as exc:
    _dasm_target = str(exc)
check_eq("resolve_module now finds DASM", _dasm_target, 0x7E)


# ===========================================================================
# 5. regressions for the 2026-09-25 live-link fixes
# ===========================================================================

check_eq("legislated OBD uses the 11-bit route", ops._obd_route().stn_protocol, "33")
neg = ops._negative_responses({"all_ecus": {"18DAF110": ["7F", "01", "11"]}})
check("NRC 0x11 on Mode 01 is named, not read as silence",
      bool(neg) and "serviceNotSupported" in neg[0], str(neg))

bus.sent.clear()
with lk.session("untarget-test", bus=CAN_C) as sess:
    sess.untarget()
check("untarget always restates the functional header",
      any(c in ("ATSH18DB33F1", "ATSH7DF") for c in bus.sent), str(bus.sent))
check("untarget clears STN pass filters", "STFAC" in bus.sent, str(bus.sent))
check("a request session puts the adapter in normal CAN mode", "STCMM 1" in bus.sent,
      str(bus.sent))


class MonitorStream(BusStream):
    """STM on the 29-bit route hears nothing; on the 11-bit route it hears
    two frames and one DATA ERROR, as the car did on 2026-09-25."""

    def __init__(self) -> None:
        super().__init__({})
        self.proto = ""

    def _reply(self, cmd: str) -> str:
        if cmd.startswith("STP "):
            self.proto = cmd[4:]
            return "OK"
        if cmd == "STM":
            return ("" if self.proto == "34" else
                    "1E36000100112233\rDATA ERROR\r1E36000B00112233")
        return super()._reply(cmd)


mon = MonitorStream()
lk2 = AdapterLink(stream_factory=lambda p, b: mon, process="check_coverage")
set_link(lk2)
v = ops.verify_bus("can_c", seconds=0.3)
check("DATA ERROR beside parsed frames does not veto verification", v.get("verified") is True,
      str(v))
check_eq("the DATA ERROR is still reported", v.get("error"), "DATA ERROR")
check("a passive listen clears filters before monitoring", "STFAC" in mon.sent)


# ===========================================================================
# 6. the bench page renders every state
# ===========================================================================

from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402

client = TestClient(create_app())
coverage.reset()
r = client.get("/coverage")
check_eq("GET /coverage with no session is 200", r.status_code, 200)
check("no-session page offers a start form", "Start coverage session" in r.text)
r = client.post("/coverage/start", data={"vin": "SHORT"}, follow_redirects=False)
check("bad VIN is shown on the page, not a 500", r.status_code == 200 and "VIN" in r.text,
      str(r.status_code))
r = client.post("/coverage/start", data={"vin": VIN, "engine_running": "true"},
                follow_redirects=False)
check_eq("start redirects back to the page", r.status_code, 303)
r = client.post("/coverage/run", data={"key": "ch"}, follow_redirects=True)
check("running grey before baseline shows the refusal", "Refused" in r.text and
      "baseline" in r.text)
r = client.get("/coverage")
check("mid-session page shows the pass list and checklist",
      "Main bus, no cable" in r.text and "Continuity-check" in r.text)

# Drive the rest with the fake ops, then render the finished report.
fo2 = FakeOps()
fo2.scans["can_c"] = [{"ecu": "ECM", "codes": ["P0455-00"],
                       "dtcs": [rec("P0455-00", 0x4D)]}]
coverage.run_pass("c_first", ops=fo2)
coverage.skip_pass("ch", "grey cable not on hand")
coverage.skip_pass("ihs", "blue cable not on hand")
fo2.scans["can_c"].append({"ecu": "BCM", "codes": ["U0100-87"],
                           "dtcs": [rec("U0100-87", 0x09)]})
coverage.run_pass("c_final", ops=fo2)
r = client.get("/coverage")
check_eq("finished page is 200", r.status_code, 200)
check("finished page shows the bystander", "U0100-87" in r.text and "appeared" in r.text)
check("finished page lists the active EVAP fault", "P0455-00" in r.text)
check("nav links to coverage", 'href="/coverage"' in r.text)
r = client.post("/coverage/reset", follow_redirects=True)
check("reset returns to the start form", "Start coverage session" in r.text)
r = client.get("/api/live/coverage")
check_eq("GET /api/live/coverage is 200", r.status_code, 200)


# ===========================================================================
# 7. auto-verify: reads verify their own bus instead of refusing
# ===========================================================================

from cuore.live.buses import CAN_CH  # noqa: E402

mon2 = MonitorStream()
lk3 = AdapterLink(stream_factory=lambda p, b: mon2, process="check_coverage")
lk3.auto_verify_seconds = 0.3
set_link(lk3)
out = ops.obd_dtcs("stored")
check("an unverified live bus verifies itself and the read runs",
      out.get("auto_verified", {}).get("verified") is True, str(out)[:300])
check("the read reports the route the listen found",
      out.get("auto_verified", {}).get("stn_protocol") == "33", str(out.get("auto_verified")))
mon2.sent.clear()
ops.obd_dtcs("stored")
check("a fresh proof is reused, no second listen", "STM" not in mon2.sent)

lk3.verified["can_c"]["ts"] -= lk3.verify_ttl + 1
mon2.sent.clear()
ops.obd_dtcs("stored")
check("a stale proof is re-checked", "STM" in mon2.sent)


class SilentStream(MonitorStream):
    def _reply(self, cmd: str) -> str:
        if cmd == "STM":
            return ""
        return super()._reply(cmd)


sil = SilentStream()
lk4 = AdapterLink(stream_factory=lambda p, b: sil, process="check_coverage")
lk4.auto_verify_seconds = 0.2
set_link(lk4)
try:
    ops.obd_dtcs("stored")
    msg = ""
except Refused as exc:
    msg = str(exc)
check("a silent bus refuses with the reason", "silent" in msg and "HS/MS switch" in msg, msg)
check("nothing was transmitted on the silent bus", "03" not in sil.sent, str(sil.sent[-5:]))

lk4.auto_verify = False
sil.sent.clear()
check("with auto-verify off the old refusal stands",
      raises(Refused, lambda: ops.obd_dtcs("stored")) and "STM" not in sil.sent)

lk4.auto_verify = True
lk4.set_cable("grey_a6")
sil.sent.clear()
check("CAN-CH without confirm is refused",
      raises(Refused, lambda: lk4.session("x", bus=CAN_CH).__enter__()))
check("and refused before any listen", "STM" not in sil.sent, str(sil.sent))
lk3.verified["can_c"]["ts"] -= lk3.verify_ttl + 1
check_eq("cable_state shows a stale proof as unverified",
         [b["verified"] for b in lk3.cable_state()["buses"] if b["bus"] == "can_c"], [False])


# ===========================================================================
# 8. review fixes: no double passes, no persisting a weak identity
# ===========================================================================

import threading as _th  # noqa: E402

coverage.reset()
coverage.start(VIN)
fo3 = FakeOps()
fo3.scans["can_c"] = [{"ecu": "ECM", "codes": [], "dtcs": []}]
coverage.run_pass("c_first", ops=fo3)
check("a finished pass cannot be re-run",
      raises(Refused, lambda: coverage.run_pass("c_first", ops=fo3)))

gate_open, release = _th.Event(), _th.Event()


class SlowOps(FakeOps):
    def verify_bus(self, bus, seconds=2.0):
        gate_open.set()
        release.wait(5)
        return super().verify_bus(bus, seconds)


slow = SlowOps()
slow.cable = "grey_a6"
worker = _th.Thread(target=lambda: coverage.run_pass("ch", ops=slow, confirm=True))
worker.start()
gate_open.wait(5)
check("a second pass is refused while one is running",
      raises(Refused, lambda: coverage.run_pass("ch", ops=slow, confirm=True)))
release.set()
worker.join(5)
check_eq("the running pass still stored its result",
         coverage.current()["passes"]["ch"]["status"], "done")
check_eq("the bus was swept once", len([c for c in slow.calls if c[0] == "verify"]), 1)
coverage.reset()

m = identify.match({"F192": "XMRR1EVO14FX"}, addressing.on_bus("can_c"))
check_eq("a lone partial match still names a candidate", m.get("matched"), "DASM")
check_eq("but is not strong", m.get("strong"), False)
m = identify.match({"F192": "MRR1evo14F"}, addressing.on_bus("can_c"))
check_eq("one exact match is strong", m.get("strong"), True)

store.path().unlink(missing_ok=True)
weak = BusStream({0x7E: {"22F190": "62F190" + _ascii_hex(VIN),
                         "22F192": "62F192" + _ascii_hex("XMRR1EVO14FX")}})
lk5 = AdapterLink(stream_factory=lambda p, b: weak, process="check_coverage")
set_link(lk5)
lk5.mark_verified(CAN_C, 10)
with lk5.session("weak-id", bus=CAN_C) as sess:
    res = uds_mod.discover(sess, CAN_C, vin_expected=VIN, candidates=[0x7E],
                           per_target_timeout=0.2)
h = res["hits"][0]
check_eq("weak identity with this car's VIN is still reported", h.get("module"), "DASM")
check("but not persisted", not h.get("persisted") and bool(h.get("not_persisted")), str(h))
check_eq("and the store stays empty", store.confirmed_targets(VIN), {})


# ===========================================================================
# 9. test reads never pass as evidence about the car
# ===========================================================================

from cuore.live import audit as audit_mod  # noqa: E402

check("the audit log follows CUORE_STATE_DIR",
      str(audit_mod.log_path()).startswith(_TMP), str(audit_mod.log_path()))
check("observations follow CUORE_STATE_DIR",
      str(store.observations_path()).startswith(_TMP), str(store.observations_path()))
fake_obs = [o for o in store.recent_observations(200) if o.get("stream")]
check("scripted reads were recorded with their stream", bool(fake_obs))
check("no scripted read counts as from the car",
      not any(store.is_from_car(o) for o in fake_obs),
      str({o.get("stream") for o in fake_obs}))
check("a serial read counts as from the car",
      store.is_from_car({"stream": "serial COM3@115200"}))
check("a recorded serial session counts as from the car",
      store.is_from_car({"stream": "recording(serial COM3@115200)"}))
check("an untagged legacy read does not", not store.is_from_car({}))


# ===========================================================================
# 10. silence is explained from the port voltage, not assumed to be ignition
# ===========================================================================


class VoltStream(MonitorStream):
    def __init__(self, volts: str) -> None:
        super().__init__()
        self.volts = volts

    def _reply(self, cmd: str) -> str:
        if cmd == "ATRV":
            return self.volts
        return super()._reply(cmd)


for volts, want, label in (("14.1V", "engine is running", "charging voltage"),
                           ("12.3V", "ignition may be off", "resting voltage"),
                           ("10.2V", "battery is low", "low voltage"),
                           ("OK", "no vehicle voltage", "no voltage")):
    vs = VoltStream(volts)
    lkv = AdapterLink(stream_factory=lambda p, b, vs=vs: vs, process="check_coverage")
    lkv.auto_verify_seconds = 0.3
    set_link(lkv)
    w = ops.obd_dtcs("stored").get("warning", "")
    check(f"silence at {label} says '{want}'", want in w, w)
    check(f"silence at {label} never blames the ignition as 'expected'",
          "this is expected" not in w, w)
vs = VoltStream("14.1V")
lkv = AdapterLink(stream_factory=lambda p, b: vs, process="check_coverage")
lkv.auto_verify_seconds = 0.3
set_link(lkv)
rd = ops.obd_readiness()
check("readiness NO DATA carries the voltage explanation",
      "engine is running" in (rd.get("since_clear") or {}).get("why", ""), str(rd)[:300])


# ===========================================================================
# 11. repair verification from the status byte
# ===========================================================================

from cuore.live import repair  # noqa: E402

check_eq("0x4D (last night's EVAP) is failing", repair.classify_status(0x4D), "failing")
check_eq("0x02 failed this drive is failing", repair.classify_status(0x02), "failing")
check_eq("0x28 failed since clear, not now", repair.classify_status(0x28),
         "failed_since_clear")
check_eq("0x50 not run since clear", repair.classify_status(0x50), "not_run_since_clear")
check_eq("0x40 ran since clear, not this cycle, never failed",
         repair.classify_status(0x40), "passed_since_clear")

a = repair.assess(["P0455", "P0456"], [{"code": "P0455-00", "status": 0x50},
                                       {"code": "P0456-00", "status": 0x40}], answered=True)
check("one test not yet run gives NOT YET KNOWN", a["verdict"].startswith("NOT YET KNOWN"),
      a["verdict"])
a = repair.assess(["P0455", "P0456"], [{"code": "P0455-00", "status": 0x40},
                                       {"code": "P0456-00", "status": 0x40}], answered=True)
check("all run and passed gives TESTS PASSED", a["verdict"].startswith("TESTS PASSED"),
      a["verdict"])
check("TESTS PASSED still asks for the permanent-code check", "Mode 0A" in a["verdict"])
a = repair.assess(["P0455"], [], answered=True)
check_eq("absent from an answered reply is likely passed", a["codes"][0]["state"],
         "likely_passed")
check("which is not reported as a full pass", a["verdict"].startswith("PROBABLY PASSED"))
a = repair.assess(["P0455"], [], answered=False)
check("no answer concludes nothing", a["verdict"].startswith("no answer"))
check_eq("codes match with or without the failure byte",
         repair.assess(["P0455-00"], [{"code": "P0455-00", "status": 0x4D}],
                       answered=True)["codes"][0]["state"], "failing")
tl = repair.timeline(["P0455"], [
    {"at": "t1", "data": {"ecu": "ECM", "codes": ["P0455-00"],
                          "dtcs": [{"code": "P0455-00", "status": 0x4D}]}},
    {"at": "t2", "data": {"ecu": "ECM", "error": "CAN ERROR", "codes": None}},
    {"at": "t3", "data": {"ecu": "TCM", "codes": [], "dtcs": []}},
    {"at": "t4", "data": {"ecu": "ECM", "codes": ["P0455-00"],
                          "dtcs": [{"code": "P0455-00", "status": 0x50}]}},
], "ECM")
check_eq("timeline keeps only clean reads of that module", [t["at"] for t in tl],
         ["t1", "t4"])
check_eq("timeline shows the progression", [t["states"]["P0455"] for t in tl],
         ["failing", "not_run_since_clear"])


print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
