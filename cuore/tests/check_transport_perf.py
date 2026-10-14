"""Regression + behaviour checks for the connectivity wins in
docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md:

  (a) Session.query_pids -- Mode 01 multi-PID batching (up to
      transport.MAX_MULTI_PID per request) with automatic per-PID fallback.
  (b) uds.sweep_bus_full -- DTCs + identity + one DID per module, all in
      ONE held session (no per-module session open).
  (c) AdapterLink.raised_baud -- optional STSBR UART-speed raise, off by
      default, always self-reverting, and never sent to a transport that
      cannot follow (Stream.supports_set_baud).
  (d) AdapterLink._probe_pass_filter / Session.untarget's STFAP-vs-STP-reissue
      choice -- off by default (CUORE_PASS_FILTER_PROBE), proven fallback
      preserved exactly when the probe is disabled OR comes back anything
      other than a clean "OK".
  (e) Session.target_raw's explicit ISO-TP flow control (STmin/BS) for
      29-bit STN targets.

Same posture as cuore/tests/check_active_probe.py: plain script, ``check``,
exit 1 on failure, no pytest -- a hand-written fake Stream. This never opens
COM3 and never talks to the real adapter.

Run:
    .venv/Scripts/python.exe cuore/tests/check_transport_perf.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-transport-perf-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)
os.environ.pop("CUORE_ADAPTER_BAUD", None)
os.environ.pop("CUORE_PASS_FILTER_PROBE", None)
os.environ["CUORE_AUTOSTART"] = "0"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from cuore.live import uds as uds_mod  # noqa: E402
from cuore.live.addressing import by_code  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want, extra: str = "") -> None:
    detail = f"got {got!r} want {want!r}"
    if extra:
        detail += f" ({extra})"
    check(label, got == want, detail)


# ===========================================================================
# fakes
# ===========================================================================

#: Common adapter-init replies every session needs, STN1170-flavoured --
#: same base script as check_active_probe.py.
_BASE = {
    "ATE0": "OK", "ATL0": "OK", "ATS0": "OK", "ATH1": "OK", "ATAT1": "OK",
    "ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2",
    "STP 33": "OK", "STP 34": "OK",
    "STCMM 0": "OK", "STCMM 1": "OK",
    "ATCAF1": "OK", "ATSH7DF": "OK", "ATCRA": "OK",
    "ATCP18": "OK", "ATSHDB33F1": "OK", "ATSTFF": "OK",
}


class ScriptedStream(Stream):
    """Answers from a fixed script keyed by the exact command sent; an
    unlisted command gets "?" (the adapter's own "unrecognized" reply) --
    NOT a generic "OK", so a probe-based feature is only ever exercised by
    a script that explicitly opts in, never by accident."""

    supports_set_baud = False  # overridden per-instance where needed

    def __init__(self, script: dict[str, str]):
        self.script = script
        self._buf = bytearray()
        self._opened = False
        self.sent: list[str] = []

    def open(self) -> None:
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").rstrip("\r\n")
        self.sent.append(cmd)
        reply = self.script.get(cmd, "?")
        self._buf.extend(reply.encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        if not self._buf:
            return b""
        n = max(n, 1)
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk

    def reset_input_buffer(self) -> None:
        self._buf.clear()

    def in_waiting(self) -> int:
        return len(self._buf)

    @property
    def describe(self) -> str:
        return "scripted"


class BaudCapableStream(ScriptedStream):
    """Same as ScriptedStream, but can actually change baud -- a fake
    SerialStream, for testing AdapterLink.raised_baud's success path."""

    supports_set_baud = True

    def __init__(self, script: dict[str, str], fail_set_baud: bool = False):
        super().__init__(script)
        self.baud_calls: list[int] = []
        self._fail = fail_set_baud

    def set_baud(self, baud: int) -> bool:
        self.baud_calls.append(baud)
        return not self._fail


def _frames(header: str, payload: str) -> str:
    """Single/multi-frame ISO-TP framing, as an STN prints it with headers
    on. Same helper as check_live_data.py's -- copied rather than imported
    so this file stays a single, independently runnable script."""
    n = len(payload) // 2
    if n <= 7:
        return f"{header}{n:02X}{payload}"
    out = [f"{header}1{n:03X}{payload[:12]}"]
    rest, seq = payload[12:], 1
    while rest:
        out.append(f"{header}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


def _link(script: dict[str, str], stream_cls=ScriptedStream, **kw) -> tuple[AdapterLink, ScriptedStream]:
    stream = stream_cls(script, **kw) if kw else stream_cls(script)
    lk = AdapterLink(stream_factory=lambda p, b: stream, process="check_transport_perf")
    lk.auto_verify_seconds = 0.05
    set_link(lk)
    lk.mark_verified(CAN_C, 10)
    return lk, stream


ECM = by_code("ECM")
TCM = by_code("TCM")
BCM = by_code("BCM")


# ===========================================================================
# (a) Session.query_pids: multi-PID batching + per-PID fallback
# ===========================================================================

# PIDs 0C (RPM, 2 bytes), 0D (speed, 1 byte), 05 (coolant, 1 byte) --
# matches check_live_data.py's own multi-PID fixture shape.
script_multi = dict(_BASE)
script_multi["010C0D05"] = _frames("7E8", "410C1F40" + "410D3C" + "410528")
lk, stream = _link(script_multi)
with lk.session("query_pids-full", bus=CAN_C) as sess:
    sess.untarget()
    r = sess.query_pids(["0C", "0D", "05"])
check("full multi-PID reply: one request only",
      stream.sent.count("010C0D05") == 1 and r["requests_sent"] == 1, str(r))
check("full multi-PID reply: multi_pid_used True", r["multi_pid_used"] is True, str(r))
check_eq("full multi-PID reply: RPM bytes", r["by_ecu"]["7E8"]["0C"], ["1F", "40"])
check_eq("full multi-PID reply: speed bytes", r["by_ecu"]["7E8"]["0D"], ["3C"])
check_eq("full multi-PID reply: coolant bytes", r["by_ecu"]["7E8"]["05"], ["28"])

# Partial reply: the ECU only answers 0C and 0D, not 05 -- the same
# "fewer groups than asked" shape poller.py's own fallback test uses.
script_partial = dict(_BASE)
script_partial["010C0D05"] = _frames("7E8", "410C1F40" + "410D3C")
script_partial["0105"] = _frames("7E8", "410528")
lk2, stream2 = _link(script_partial)
with lk2.session("query_pids-partial", bus=CAN_C) as sess:
    sess.untarget()
    r2 = sess.query_pids(["0C", "0D", "05"])
check("partial reply: the batch is still tried once",
      "010C0D05" in stream2.sent, str(stream2.sent))
check("partial reply: the missing PID falls back to its own request",
      "0105" in stream2.sent, str(stream2.sent))
check_eq("partial reply: RPM still decodes from the batch", r2["by_ecu"]["7E8"]["0C"], ["1F", "40"])
check_eq("partial reply: coolant decodes from the single fallback", r2["by_ecu"]["7E8"]["05"], ["28"])
check("partial reply: multi_pid_used True (some PIDs did come from the batch)",
      r2["multi_pid_used"] is True, str(r2))

# More than MAX_MULTI_PID (6) PIDs: two batches, not one oversized request.
script_many = dict(_BASE)
many_pids = ["0C", "0D", "05", "04", "0F", "11", "33", "2F"]  # 8 PIDs
batch1_req = "01" + "".join(many_pids[:6])
batch2_req = "01" + "".join(many_pids[6:])
script_many[batch1_req] = _frames("7E8", "410C1F40" + "410D3C" + "410528" +
                                  "410480" + "410F32" + "411110")
script_many[batch2_req] = _frames("7E8", "413364" + "412F50")
lk3, stream3 = _link(script_many)
with lk3.session("query_pids-many", bus=CAN_C) as sess:
    sess.untarget()
    r3 = sess.query_pids(many_pids)
check("8 PIDs: first batch of 6 sent", batch1_req in stream3.sent, str(stream3.sent))
check("8 PIDs: second batch of the remaining 2 sent",
      batch2_req in stream3.sent, str(stream3.sent))
check_eq("8 PIDs: byte-for-byte decode from batch 1", r3["by_ecu"]["7E8"]["0C"], ["1F", "40"])
check_eq("8 PIDs: byte-for-byte decode from batch 2", r3["by_ecu"]["7E8"]["33"], ["64"])

# A single PID never goes through the multi-PID path at all.
script_single = dict(_BASE)
script_single["010C"] = "7E8 03 41 0C 1F 40"
lk4, stream4 = _link(script_single)
with lk4.session("query_pids-single", bus=CAN_C) as sess:
    sess.untarget()
    r4 = sess.query_pids(["0C"])
check_eq("single PID: multi_pid_used is False", r4["multi_pid_used"], False)
check_eq("single PID: exactly one request", r4["requests_sent"], 1)


# ===========================================================================
# (b) uds.sweep_bus_full: DTCs + identity + DID per module, one session
# ===========================================================================

script_sweep = dict(_BASE)
ECM_HDR = ECM.response_hex
script_sweep[f"ATSH{ECM.request_hex}"] = "OK"
script_sweep[f"ATCRA{ECM.response_hex}"] = "OK"
script_sweep[f"STCFCPA {ECM.request_hex},{ECM.response_hex}"] = "OK"
script_sweep[f"ATFCSH{ECM.request_hex}"] = "OK"
script_sweep["ATFCSD300000"] = "OK"
script_sweep["ATFCSM1"] = "OK"
script_sweep["1902FF"] = _frames(ECM_HDR, "590201" + "0456" + "00")  # no active DTCs reported
script_sweep["22F190"] = _frames(ECM_HDR, "62F190" + "31" * 17)
for did in ("F187", "F188", "F189", "F18C", "F191", "F192", "F194", "F195"):
    script_sweep[f"22{did}"] = _frames(ECM_HDR, f"62{did}" + "30")
script_sweep["2204FE"] = _frames(ECM_HDR, "6204FE7D")

lk5, stream5 = _link(script_sweep)
with lk5.session("sweep_bus_full", bus=CAN_C) as sess:
    result = uds_mod.sweep_bus_full(sess, CAN_C, vin="ZASFAKPN5J7B88115",
                                    known_did=lambda code: 0x04FE if code == "ECM" else None)
check("sweep_bus_full: one module in the result", len(result["modules"]) >= 1, str(result))
ecm_row = next((m for m in result["modules"] if m.get("ecu") == "ECM"), None)
check("sweep_bus_full: ECM row present", ecm_row is not None, str(result))
if ecm_row:
    check("sweep_bus_full: DTC read ran", "dtcs" in ecm_row, str(ecm_row))
    check("sweep_bus_full: identity read ran in the same session", "identity" in ecm_row,
          str(ecm_row))
    check("sweep_bus_full: the one known DID was read too", "did" in ecm_row, str(ecm_row))
# ATE0 is sent exactly once per AdapterLink._init -- i.e. once per session
# open. sweep_bus_full itself never opens a session (it only uses the one
# passed in), so seeing it exactly once here proves every module's DTCs +
# identity + DID were read inside that single held session, not one open
# per module the way cuore.live.fullscan._sweep_bus_modules currently does.
check_eq("sweep_bus_full: exactly one session open for every module read",
         stream5.sent.count("ATE0"), 1, str(stream5.sent))


# ===========================================================================
# (c) AdapterLink.raised_baud -- off by default, opt-in, self-reverting
# ===========================================================================

script_baud_ok = dict(_BASE)
script_baud_ok["STSBR 500000"] = "OK"
script_baud_ok["STSBR 115200"] = "OK"
lk6, stream6 = _link(script_baud_ok, stream_cls=BaudCapableStream)
with lk6.session("raised_baud-off", bus=CAN_C, passive=True) as sess:
    with lk6.raised_baud(sess, target=0) as raised_off:
        pass
check_eq("raised_baud: target 0 (feature off) never engages", raised_off, False)
check("raised_baud: target 0 never sends STSBR", "STSBR 500000" not in stream6.sent, str(stream6.sent))

with lk6.session("raised_baud-on", bus=CAN_C, passive=True) as sess:
    with lk6.raised_baud(sess, target=500000) as raised_on:
        engaged = raised_on
        baud_during = lk6.baud
check("raised_baud: a supported transport + confirmed STI raises",
      engaged is True, str(lk6.last_baud_raise))
check_eq("raised_baud: link.baud reflects the raised rate inside the block", baud_during, 500000)
check_eq("raised_baud: link.baud reverts after the block", lk6.baud, 115200)
check("raised_baud: STSBR sent for the raise and the revert",
      stream6.sent.count("STSBR 500000") >= 1 and stream6.sent.count("STSBR 115200") >= 1,
      str(stream6.sent))
check_eq("raised_baud: stream.set_baud called for raise and revert",
         stream6.baud_calls, [500000, 115200])

# A transport that cannot change baud live is never even asked (no STSBR
# sent at all) -- the ScriptedStream default, same as every other fake in
# this suite and the real adapter's own TcpStream for a Wi-Fi clone.
lk7, stream7 = _link(script_baud_ok)  # plain ScriptedStream: supports_set_baud False
with lk7.session("raised_baud-unsupported", bus=CAN_C, passive=True) as sess:
    with lk7.raised_baud(sess, target=500000) as raised_unsupported:
        pass
check_eq("raised_baud: unsupported transport never raises", raised_unsupported, False)
check("raised_baud: unsupported transport is never asked (no STSBR at all)",
      not any(c.startswith("STSBR") for c in stream7.sent), str(stream7.sent))

# The adapter not acknowledging the switch leaves everything untouched.
script_baud_refused = dict(_BASE)
script_baud_refused["STSBR 500000"] = "?"
lk8, stream8 = _link(script_baud_refused, stream_cls=BaudCapableStream)
with lk8.session("raised_baud-refused", bus=CAN_C, passive=True) as sess:
    with lk8.raised_baud(sess, target=500000) as raised_refused:
        pass
check_eq("raised_baud: adapter refusing STSBR never raises", raised_refused, False)
check_eq("raised_baud: link.baud unchanged when the adapter refuses", lk8.baud, 115200)
check("raised_baud: set_baud is never called when STSBR was not acknowledged",
      stream8.baud_calls == [], str(stream8.baud_calls))


# ===========================================================================
# (d) pass-filter probe: off by default, proven STP-reissue path preserved
# ===========================================================================

script_untarget = dict(_BASE)
lk9, stream9 = _link(script_untarget)
with lk9.session("untarget-default", bus=CAN_C) as sess:
    sess.untarget()
check("untarget (probe disabled, the default): STCFCPC + STP reissue still sent",
      "STCFCPC" in stream9.sent, str(stream9.sent))
check_eq("untarget (probe disabled): pass_filter_mode cached as 'stp_reissue' without probing",
         lk9.pass_filter_mode, "stp_reissue")
check("untarget (probe disabled): STFAP is never sent",
      not any(c.startswith("STFAP") for c in stream9.sent), str(stream9.sent))

# Opted in, and the adapter clearly supports it: the lighter path is used,
# and the heavy STCFCPC+STP path is skipped.
os.environ["CUORE_PASS_FILTER_PROBE"] = "1"
script_stfap_ok = dict(_BASE)
script_stfap_ok["STFAP 1,DB33F1,FFFFFFFF"] = "OK"
lk10, stream10 = _link(script_stfap_ok)
with lk10.session("untarget-stfap", bus=CAN_C) as sess:
    sess.untarget()
check_eq("untarget (probe on, confirmed): pass_filter_mode is 'pass_filter'",
         lk10.pass_filter_mode, "pass_filter")
check("untarget (probe on, confirmed): STFAP sent", "STFAP 1,DB33F1,FFFFFFFF" in stream10.sent,
      str(stream10.sent))
check("untarget (probe on, confirmed): STCFCPC NOT sent (lighter path replaces it)",
      "STCFCPC" not in stream10.sent, str(stream10.sent))

# Opted in, but the adapter does not understand STFAP ("?", the honest
# default of every fake in this suite unless scripted otherwise): the
# proven fallback is used, unchanged.
script_stfap_unsupported = dict(_BASE)  # no STFAP entry -> "?"
lk11, stream11 = _link(script_stfap_unsupported)
with lk11.session("untarget-stfap-unsupported", bus=CAN_C) as sess:
    sess.untarget()
check_eq("untarget (probe on, unsupported): pass_filter_mode is 'stp_reissue'",
         lk11.pass_filter_mode, "stp_reissue")
check("untarget (probe on, unsupported): STCFCPC + STP reissue still sent",
      "STCFCPC" in stream11.sent, str(stream11.sent))
os.environ.pop("CUORE_PASS_FILTER_PROBE", None)


# ===========================================================================
# (e) explicit ISO-TP flow control (STmin/BS) for 29-bit STN targets
# ===========================================================================

script_target = dict(_BASE)
script_target[f"ATSH{ECM.request_hex}"] = "OK"
script_target[f"ATCRA{ECM.response_hex}"] = "OK"
script_target[f"STCFCPA {ECM.request_hex},{ECM.response_hex}"] = "OK"
script_target[f"ATFCSH{ECM.request_hex}"] = "OK"
script_target["ATFCSD300000"] = "OK"
script_target["ATFCSM1"] = "OK"
lk12, stream12 = _link(script_target)
with lk12.session("target-fc", bus=CAN_C) as sess:
    sess.target(ECM)
check("target_raw (29-bit STN): explicit flow-control header set",
      f"ATFCSH{ECM.request_hex}" in stream12.sent, str(stream12.sent))
check("target_raw (29-bit STN): explicit STmin/BS data set",
      "ATFCSD300000" in stream12.sent, str(stream12.sent))
check("target_raw (29-bit STN): flow-control mode set to narrowband (1)",
      "ATFCSM1" in stream12.sent, str(stream12.sent))
check("target_raw (29-bit STN): STCFCPA still sent too (additive, not a replacement)",
      f"STCFCPA {ECM.request_hex},{ECM.response_hex}" in stream12.sent, str(stream12.sent))


print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
