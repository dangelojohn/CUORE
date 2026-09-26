"""Regression checks for the cuore.live package.

Same posture as ``cuore/tests/check_api.py``: plain script, ``check(label,
cond, detail)``, exit 1 on failure, no pytest, no mocking framework -- just
real function calls and (for the transport/HTTP sections) a hand-written
fake ``Stream`` that answers exactly the bytes a real ELM327/STN adapter
would.

This file never imports anything from obd2-mcp, and it never modifies
anything under cuore/live/ -- it only calls the public functions there.

Run:
    .venv/Scripts/python.exe cuore/tests/check_live.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: the audit log, observations and address store
# must go to a throwaway directory, never the bench's real evidence.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-live-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import addressing, buses, interlock  # noqa: E402
from cuore.live import uds as uds_mod  # noqa: E402
from cuore.live.buses import CAN_C, CAN_CH, CAN_IHS  # noqa: E402
from cuore.live.config import default_cable, resolve_baud, resolve_port  # noqa: E402
from cuore.live.errors import BadCommand, LinkUnavailable, Refused  # noqa: E402
from cuore.live.framing import (adapter_error, hex_pairs, negative_responses,  # noqa: E402
                                parse_frames, reassemble)
from cuore.live.obd import (decode_obd_dtcs, decode_pid, decode_readiness,  # noqa: E402
                            decode_supported_pids, decode_uds_dtc_block,
                            dtc_from_three_bytes, dtc_from_two_bytes,
                            evap_verdict, resolve_pid)
from cuore.live.safety import (assert_read_only_uds, assert_transmit_allowed,  # noqa: E402
                               classify_command, validate_command)
from cuore.live.stream import PlaybackStream, Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402
from cuore.live import ops  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    """Boolean assertion -- ``cond`` must already be True/False."""
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want, extra: str = "") -> None:
    """Equality assertion: records ``got``/``want`` in the failure detail."""
    detail = f"got {got!r} want {want!r}"
    if extra:
        detail += f" ({extra})"
    check(label, got == want, detail)


# ===========================================================================
# 1. framing
# ===========================================================================

check_eq("hex_pairs mode 01 rpm", hex_pairs("410C0B4C"), ["41", "0C", "0B", "4C"])
check_eq("hex_pairs spaced", hex_pairs("41 0C 0B 4C"), ["41", "0C", "0B", "4C"])
check_eq("hex_pairs with CAN header", hex_pairs("7E8 410C0B4C"), ["41", "0C", "0B", "4C"])
check_eq("hex_pairs ISO-TP multiline",
         hex_pairs("0: 49020157\n1: 5A415346"),
         ["49", "02", "01", "57", "5A", "41", "53", "46"])
check_eq("hex_pairs odd nibble trimmed", hex_pairs("410C0B4"), ["41", "0C", "0B"])
check_eq("hex_pairs skips adapter errors", hex_pairs("CAN ERROR\n410C0B4C"),
         ["41", "0C", "0B", "4C"])
check_eq("hex_pairs skips benign lines", hex_pairs("OK\nNO DATA\n410C0B4C"),
         ["41", "0C", "0B", "4C"])

for e in ("BUFFER FULL", "CAN ERROR", "BUS BUSY", "STOPPED", "UNABLE TO CONNECT",
          "OUT OF MEMORY", "TIMEOUT"):
    check(f"adapter_error surfaces {e}", bool(adapter_error(e)), repr(adapter_error(e)))
check_eq("adapter_error clean text", adapter_error("410C0B4C"), "")

# parse_frames: 11-bit two ECUs, headers on.
frames = parse_frames("7E80641 00BE3EA813\n7E9064100801A8001".replace(" ", ""), headers_on=True)
check_eq("parse_frames two 11-bit ECUs", sorted(h for h, _ in frames), ["7E8", "7E9"])

# reassemble: 11-bit two ECUs.
two = reassemble("7E80641 00BE3EA813\n7E9064100801A8001".replace(" ", ""), headers_on=True)
check_eq("reassemble two ECUs keyed by header", sorted(two), ["7E8", "7E9"])
check_eq("reassemble single frame length honoured", two["7E8"],
         ["41", "00", "BE", "3E", "A8", "13"])

# reassemble: 29-bit multi-frame VIN, first frame + two consecutive frames.
hx = "".join(format(ord(c), "02X") for c in VIN)
ff = "18DAF110" + "1014" + "490201" + hx[:6]
cf1 = "18DAF110" + "21" + hx[6:20]
cf2 = "18DAF110" + "22" + hx[20:]
r = reassemble("\n".join([ff, cf1, cf2]), headers_on=True)
payload = r.get("18DAF110", [])
check_eq("reassemble 29-bit header recovered", list(r), ["18DAF110"])
check_eq("reassemble first-frame length applied", len(payload), 20)
check_eq("reassemble VIN bytes reassembled",
         "".join(chr(int(b, 16)) for b in payload[3:]), VIN)

# ELM "0:"/"1:" headers-off fallback.
r0 = reassemble("014\n0: 49 02 01 5A 41 53\n1: 46 41 4B 50 4E 35\n2: 4A 37 42 38 38 31",
                headers_on=False)
check_eq("headers-off ELM fallback concatenated", r0.get("", [])[:6],
         ["49", "02", "01", "5A", "41", "53"])

# Error text yields {}.
check_eq("reassemble on error text yields {}", reassemble("CAN ERROR", headers_on=True), {})
check_eq("reassemble on NO DATA yields {}", reassemble("NO DATA", headers_on=True), {})

# negative_responses.
neg_ecus = {"18DAF110": ["7F", "22", "78"], "18DAF118": ["62", "F1", "90"]}
check_eq("negative_responses finds the 7F entry", negative_responses(neg_ecus, "22"),
         {"18DAF110": "78"})
check("negative_responses ignores positive ECUs",
      "18DAF118" not in negative_responses(neg_ecus, "22"))


# ===========================================================================
# 2. obd
# ===========================================================================

check_eq("decode_obd_dtcs CAN with count byte, two codes",
         decode_obd_dtcs(["43", "02", "04", "55", "04", "40"]), ["P0455", "P0440"])
check_eq("decode_obd_dtcs K-line without count byte",
         decode_obd_dtcs(["43", "04", "55", "04", "40"]), ["P0455", "P0440"])
check_eq("decode_obd_dtcs zero codes", decode_obd_dtcs(["43", "00"]), [])
check_eq("decode_obd_dtcs empty payload", decode_obd_dtcs([]), [])

DTC2_CASES = [
    ("01", "43", "P0143"), ("45", "61", "C0561"), ("81", "23", "B0123"),
    ("C1", "00", "U0100"), ("04", "56", "P0456"), ("D1", "10", "U1110"),
]
for a, b, want in DTC2_CASES:
    check_eq(f"dtc_from_two_bytes {a}{b} -> {want}", dtc_from_two_bytes(a, b), want)
check_eq("dtc_from_two_bytes 00 00 filler is None", dtc_from_two_bytes("00", "00"), None)

check_eq("dtc_from_three_bytes P0456-2F",
         dtc_from_three_bytes("04", "56", "2F"), "P0456-2F")
check_eq("dtc_from_three_bytes with 00 00 base falls back to P0000",
         dtc_from_three_bytes("00", "00", "08"), "P0000-08")

# decode_uds_dtc_block on a hand-built 59 02 FF payload with padding: one
# real code (04 56 2F 08 -> P0456-2F), one all-zero padding record (skipped),
# one more real code (D1 23 10 08 -> U1123-10).
uds_block = decode_uds_dtc_block(
    ["59", "02", "FF",
     "04", "56", "2F", "08",
     "00", "00", "00", "00",
     "D1", "23", "10", "08"])
check_eq("decode_uds_dtc_block decodes two real codes, skips the 00 00 00 pad",
         [rec["code"] for rec in uds_block], ["P0456-2F", "U1123-10"])
check("decode_uds_dtc_block reports the status flags",
      uds_block[0]["flags"]["confirmedDTC"] is True)
check_eq("decode_uds_dtc_block rejects a non-0x59 header",
         decode_uds_dtc_block(["7F", "19", "31"]), [])

# decode_readiness: spark layout.
spark = decode_readiness(hex_pairs("41 01 00 07 25 04"), "41")
spark_names = {m["monitor"]: m["complete"] for m in spark["monitors"]}
check_eq("readiness spark: MIL off", spark["mil_on"], False)
check_eq("readiness spark: ignition", spark["ignition"], "spark")
check_eq("readiness spark: EVAP incomplete", spark_names.get("Evaporative system"), False)
check_eq("readiness spark: Catalyst complete", spark_names.get("Catalyst"), True)
check_eq("readiness spark: unsupported monitor absent", "EGR system" in spark_names, False)

# decode_readiness: compression layout (byte B bit 3 set).
comp = decode_readiness(hex_pairs("41 01 00 0F 0B 08"), "41")
comp_names = {m["monitor"]: m["complete"] for m in comp["monitors"]}
check_eq("readiness compression: ignition flag", comp["ignition"], "compression")
check("readiness compression: Boost pressure named",
      "Boost pressure" in comp_names, str(sorted(comp_names)))
check("readiness compression: NOx/SCR monitor named",
      "NOx/SCR monitor" in comp_names, str(sorted(comp_names)))
check("readiness compression: does not use spark monitor names",
      "Catalyst" not in comp_names and "Evaporative system" not in comp_names,
      str(sorted(comp_names)))
check_eq("readiness undecodable returns None", decode_readiness(hex_pairs("NO DATA"), "41"), None)

verdict_not_run = evap_verdict(spark)
check("evap_verdict: not run yet warns no information",
      bool(verdict_not_run) and "carries no information" in verdict_not_run,
      repr(verdict_not_run))
complete_spark = decode_readiness(hex_pairs("41 01 00 07 25 00"), "41")
verdict_complete = evap_verdict(complete_spark)
check("evap_verdict: complete says meaningful",
      bool(verdict_complete) and "meaningful" in verdict_complete, repr(verdict_complete))
check("evap_verdict: monitor absent yields a sentence, not silence",
      evap_verdict({"monitors": [{"monitor": "Misfire", "complete": True}]}) is not None)
check("evap_verdict: no monitors at all -> None",
      evap_verdict({"monitors": []}) is None)

# PID formulas.
hexpid, spec = resolve_pid("0C")
check_eq("PID rpm 0B4C -> 723.0", decode_pid(hexpid, spec, ["0B", "4C"])["value"], 723.0)
hexpid, spec = resolve_pid("42")
check_eq("PID voltage 36B0 -> 14.0", decode_pid(hexpid, spec, ["36", "B0"])["value"], 14.0)
hexpid, spec = resolve_pid("32")
check_eq("PID evap signed FFF0 -> -4.0", decode_pid(hexpid, spec, ["FF", "F0"])["value"], -4.0)

check_eq("resolve_pid by name", resolve_pid("engine_rpm")[0], "0C")
check_eq("resolve_pid by hex (lowercase)", resolve_pid("0c")[0], "0C")
check_eq("resolve_pid by hex resolves the same spec as by name",
         resolve_pid("0c")[1].name, "engine_rpm")
check_eq("resolve_pid unknown hex has no spec", resolve_pid("A9")[1], None)
try:
    resolve_pid("not a pid")
    check("resolve_pid rejects garbage", False)
except BadCommand:
    check("resolve_pid rejects garbage", True)

supported, more = decode_supported_pids("00", ["BE", "3E", "A8", "13"])
check("decode_supported_pids returns known PIDs",
      {"05", "0C", "0D"} <= set(supported), str(supported))
check_eq("decode_supported_pids next-block flag reads bit 0",
         more, bool(int("BE3EA813", 16) & 1))


# ===========================================================================
# 3. safety
# ===========================================================================

for bad in ("ATI\r04", "ATI\n04", "STI|04", "", "   ", "ATI\x0004"):
    try:
        validate_command(bad)
        rejected = False
    except BadCommand:
        rejected = True
    check(f"validate_command rejects {bad!r}", rejected)
check_eq("validate_command passes a plain command", validate_command(" 0100 "), "0100")

CLASSIFY_CASES = [
    ("04", "vehicle_write"), ("0400", "vehicle_write"), ("ATSH 7E0", "vehicle_write"),
    ("2F0102", "vehicle_write"), ("31010203", "vehicle_write"), ("14FFFFFF", "vehicle_write"),
    ("2E F190", "vehicle_write"), ("34", "vehicle_write"), ("1003", "vehicle_write"),
    ("1101", "vehicle_write"), ("STPX h:7E0,d:0100", "vehicle_write"),
    ("ATRV", "read"), ("ATDP", "read"), ("ATDPN", "read"), ("ATI", "read"),
    ("0100", "read"), ("0902", "read"), ("19020C", "read"), ("22F190", "read"),
    ("3E00", "read"), ("STI", "read"), ("STDI", "read"), ("STPRS", "read"),
    ("STMFR", "read"), ("STSLCS", "read"),
    ("ATSP6", "adapter_state"), ("ATH1", "adapter_state"), ("ATPP 0C SV 23", "adapter_state"),
    ("ATCRA 7E8", "adapter_state"), ("STP 54", "adapter_state"), ("STBR 921600", "adapter_state"),
    ("STCMM 0", "adapter_state"), ("STFPA 7E8,7FF", "adapter_state"),
    ("ATMA", "blocked"), ("STM", "blocked"), ("STMA", "blocked"), ("STM 50", "blocked"),
    ("hello", "blocked"),
]
for cmd, want in CLASSIFY_CASES:
    kind, _reason = classify_command(cmd)
    check_eq(f"classify_command {cmd!r} -> {want}", kind, want)

try:
    assert_read_only_uds(0x10, bytes([0x01]))
    ok = True
except Refused:
    ok = False
check("assert_read_only_uds allows 0x10 sub 01", ok)
for service, payload in ((0x19, b"\x02\xFF"), (0x22, b"\xF1\x90"), (0x3E, b"\x80")):
    try:
        assert_read_only_uds(service, payload)
        ok = True
    except Refused:
        ok = False
    check(f"assert_read_only_uds allows 0x{service:02X}", ok)
for service, payload in ((0x10, bytes([0x03])), (0x14, b""), (0x2E, b"\xF1\x90\x00"), (0x2F, b""),
                         (0x31, b"\x01")):
    try:
        assert_read_only_uds(service, payload)
        ok = True
    except Refused:
        ok = False
    check(f"assert_read_only_uds refuses 0x{service:02X}", not ok)

TRANSMIT_MATRIX = [
    # (bus_cable_ok, verified, needs_confirmation, confirmed) -> should raise?
    (False, False, False, False, True),
    (True, False, False, False, True),
    (True, True, True, False, True),
    (True, True, True, True, False),
    (True, True, False, False, False),
]
for cable_ok, verified, needs_conf, confirmed, should_raise in TRANSMIT_MATRIX:
    try:
        assert_transmit_allowed(bus_key="can_test", bus_cable_ok=cable_ok, verified=verified,
                                needs_confirmation=needs_conf, confirmed=confirmed)
        raised = False
    except Refused:
        raised = True
    check_eq(f"assert_transmit_allowed(cable_ok={cable_ok},verified={verified},"
             f"needs_conf={needs_conf},confirmed={confirmed})", raised, should_raise)


# ===========================================================================
# 4. config
# ===========================================================================

_ENV_KEYS = ("CUORE_OBD_PORT", "CUORE_OBD_BAUD", "OBD_PORT", "OBD_BAUD", "CUORE_OBD_CABLE")
_saved_env = {k: os.environ.get(k) for k in _ENV_KEYS}
try:
    for k in _ENV_KEYS:
        os.environ.pop(k, None)

    check_eq("resolve_port: argument wins with nothing else set",
             resolve_port("com5"), ("COM5", "argument"))

    os.environ["OBD_PORT"] = "COM9"
    os.environ["OBD_BAUD"] = "9600"
    check_eq("resolve_port: argument beats OBD_PORT", resolve_port("com3"), ("COM3", "argument"))
    check_eq("resolve_baud: argument beats OBD_BAUD", resolve_baud(115200), (115200, "argument"))
    check_eq("resolve_port: OBD_PORT used with no argument",
             resolve_port(""), ("COM9", "env OBD_PORT"))
    check_eq("resolve_baud: OBD_BAUD used with no argument",
             resolve_baud(0), (9600, "env OBD_BAUD"))

    os.environ["CUORE_OBD_PORT"] = "COM7"
    os.environ["CUORE_OBD_BAUD"] = "38400"
    check_eq("resolve_port: CUORE_OBD_PORT beats OBD_PORT",
             resolve_port(""), ("COM7", "env CUORE_OBD_PORT"))
    check_eq("resolve_baud: CUORE_OBD_BAUD beats OBD_BAUD",
             resolve_baud(0), (38400, "env CUORE_OBD_BAUD"))

    for k in ("CUORE_OBD_PORT", "CUORE_OBD_BAUD", "OBD_PORT", "OBD_BAUD"):
        os.environ.pop(k, None)
    port, psrc = resolve_port("")
    baud, bsrc = resolve_baud(0)
    from cuore.live.config import mes_registry
    if mes_registry():
        check("resolve_port: registry used when env unset",
              psrc.startswith("MES registry"), psrc)
        check("resolve_baud: registry used when env unset",
              bsrc.startswith("MES registry"), bsrc)
    else:
        check_eq("resolve_port: no port when nothing set", port, None)
        from cuore.live.config import FALLBACK_BAUD
        check_eq("resolve_baud: ELM327 fallback when nothing set", baud, FALLBACK_BAUD)

    os.environ["CUORE_OBD_CABLE"] = "blue_a5"
    check_eq("default_cable reads CUORE_OBD_CABLE", default_cable(), "blue_a5")
    os.environ.pop("CUORE_OBD_CABLE", None)
    check_eq("default_cable defaults to none", default_cable(), "none")
finally:
    for k, v in _saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ===========================================================================
# 5. buses / addressing
# ===========================================================================

check_eq("route_for(CAN_CH, none) is None", buses.route_for(CAN_CH, "none"), None)
r_ihs = buses.route_for(CAN_IHS, "none")
check_eq("route_for(CAN_IHS, none).stn_protocol == 54",
         r_ihs.stn_protocol if r_ihs else None, "54")
r_ihs_a5 = buses.route_for(CAN_IHS, "blue_a5")
check_eq("route_for(CAN_IHS, blue_a5).bitrate_override == 125000",
         r_ihs_a5.bitrate_override if r_ihs_a5 else None, 125000)
check_eq("header_bits_for_protocol 34 -> 29", buses.header_bits_for_protocol("34"), 29)
check_eq("header_bits_for_protocol 33 -> 11", buses.header_bits_for_protocol("33"), 11)
check_eq("header_bits_for_protocol 6 (ELM short form) -> 11",
         buses.header_bits_for_protocol("6"), 11)

ecm = addressing.by_code("ECM")
check_eq("by_code(ECM).request_hex", ecm.request_hex if ecm else None, "18DA10F1")
check_eq("by_code(ECM).response_hex", ecm.response_hex if ecm else None, "18DAF110")

confirmed_codes = sorted(m.code for m in addressing.confirmed())
check_eq("confirmed() codes", confirmed_codes, sorted(["ECM", "TCM", "BCM", "IPC", "RFHUB"]))

sweep = addressing.sweep_candidates("can_c")
check("sweep_candidates excludes tester 0xF1", 0xF1 not in sweep)
check("sweep_candidates excludes functional 0x33", 0x33 not in sweep)
check("sweep_candidates excludes BACCAble 0xBA", 0xBA not in sweep)
check_eq("sweep_candidates covers the full byte range otherwise",
         len(sweep), 256 - len(addressing.RESERVED_TARGETS))

ecm_dids = addressing.dids_for("ECM")
check("dids_for(ECM) excludes diesel rows by default",
      all(not d.diesel_only for d in ecm_dids))
check("dids_for(ECM) includes diesel rows when asked",
      any(d.diesel_only for d in addressing.dids_for("ECM", include_diesel=True)))


# ===========================================================================
# 6. transport, with an injected fake Stream
# ===========================================================================

class ScriptedStream(Stream):
    """Answers whatever ``AdapterLink``/``Session`` would send a real
    ELM327/STN adapter, from a fixed script.

    ``script[cmd]`` is either a single reply string (returned every time)
    or a list of reply strings, consumed one per call and then held on the
    last entry -- that is how the NRC 0x78 "pending, retry" case is faked:
    the first call gets the negative response, the second gets the real
    answer.
    """

    def __init__(self, script: dict[str, str | list[str]]):
        self.script = script
        self._counts: dict[str, int] = {}
        self._buf = bytearray()
        self._opened = False
        self.sent: list[str] = []

    def open(self) -> None:
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def _lookup(self, cmd: str) -> str:
        val = self.script.get(cmd)
        if val is None:
            return "?"
        if isinstance(val, list):
            i = self._counts.get(cmd, 0)
            reply = val[min(i, len(val) - 1)]
            self._counts[cmd] = i + 1
            return reply
        return val

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").rstrip("\r\n")
        self.sent.append(cmd)
        reply = self._lookup(cmd)
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


ECM = addressing.by_code("ECM")
HDR = "18DAF110"

# 62 F1 90 + 17 VIN bytes = 20 bytes; first frame carries 6 (62 F1 90 + 3
# VIN chars), then two 7-byte consecutive frames (3 + 7 + 7 = 17).
_vin_hex = "".join(format(ord(c), "02X") for c in VIN)
_vin_ff = HDR + "1014" + "62F190" + _vin_hex[:6]
_vin_cf1 = HDR + "21" + _vin_hex[6:20]
_vin_cf2 = HDR + "22" + _vin_hex[20:]
VIN_REPLY = "\r".join([_vin_ff, _vin_cf1, _vin_cf2])

# 59 02 FF 04 56 2F 08 -- one real code (h=04 m=56 l=2F s=08 -> P0456-2F),
# single ISO-TP frame (PCI 07 = 7 bytes follow).
DTC_REPLY = HDR + "07" + "5902FF04562F08"

# 0x22 F187 (spare part) answered with NRC 0x78 (responsePending) on the
# first try, a real 4-byte ASCII answer on the retry.
NRC_PENDING = HDR + "03" + "7F2278"
NRC_POSITIVE = HDR + "07" + "62F18741424344"  # "ABCD"

SCRIPT: dict[str, str | list[str]] = {
    "ATE0": "OK",
    "ATL0": "OK",
    "ATS0": "OK",
    "ATH1": "OK",
    "ATAT1": "OK",
    "ATI": "ELM327 v2.3",
    "STI": "STN1170 v4.3.2",
    "STP 34": "OK",
    "STCMM 0": "OK",
    "ATRV": "12.6V",
    "STPRS": "HS CAN (ISO 15765, 500K/29B)",
    "ATSH18DA10F1": "OK",
    "ATCRA18DAF110": "OK",
    "STCFCPA 18DA10F1,18DAF110": "OK",
    "22F190": VIN_REPLY,
    "1902FF": DTC_REPLY,
    "22F187": [NRC_PENDING, NRC_POSITIVE],
}

scripted = ScriptedStream(SCRIPT)
link1 = AdapterLink(stream_factory=lambda p, b: scripted, process="check_live")
set_link(link1)

_saved_port_env = {k: os.environ.get(k) for k in ("CUORE_OBD_PORT", "OBD_PORT")}
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)

try:
    # (a) probe() returns identity with stn_chip True and battery 12.6V.
    probe_result = ops.probe()
    check_eq("probe() stn_chip True", probe_result["stn_chip"], True)
    check_eq("probe() battery_voltage 12.6", probe_result["battery_voltage"], 12.6)
    check_eq("probe() identity carries STI", probe_result["identity"].get("STI"),
             "STN1170 v4.3.2")

    # (b) a transmit session on can_c is Refused before verification.
    try:
        with link1.session("write_probe", bus=CAN_C) as _sess:
            pass
        refused = False
    except Refused:
        refused = True
    check("transmit session on can_c refused before verification", refused)

    # (c) after mark_verified, uds.read_did on ECM for 0xF190 returns the VIN.
    link1.mark_verified(CAN_C, 10)
    with link1.session("test_reads", bus=CAN_C) as sess:
        r_did = uds_mod.read_did(sess, ECM, 0xF190)
        check_eq("read_did F190 no error", r_did.get("error"), None)
        check_eq("read_did F190 ascii is the VIN", r_did.get("ascii"), VIN)

        # (d) uds.read_dtcs decodes the hand-built 59 02 FF ... block.
        r_dtc = uds_mod.read_dtcs(sess, ECM)
        check_eq("read_dtcs decodes P0456-2F", r_dtc.get("codes"), ["P0456-2F"])

        # (e) NRC 7F 22 78 then a positive on retry is handled transparently.
        r_retry = uds_mod.request(sess, ECM, 0x22, bytes.fromhex("F187"), timeout=2)
        check_eq("NRC 0x78 causes exactly one retry", r_retry.get("attempts"), 2)
        check("retry eventually returns the positive payload",
              bool(r_retry.get("positive")), str(r_retry))

    # (f) the lock file is absent after the session.
    check("adapter lock file absent after a completed session",
          interlock.read_lock() is None, str(interlock.read_lock()))

    # (g) MES interlock: a "connected" MES status refuses the session.
    _orig_mes_status = interlock.mes_status
    interlock.mes_status = lambda: {"running": True, "pids": [999],
                                    "state": "connected", "label": "Connected: Test"}
    try:
        try:
            with link1.session("blocked_by_mes", bus=CAN_C, passive=True) as _sess:
                pass
            blocked = False
        except LinkUnavailable:
            blocked = True
        check("session refused while MES reports connected", blocked)
    finally:
        interlock.mes_status = _orig_mes_status

    # ------------------------------------------------------------------
    # FastAPI surface, same injected link.
    # ------------------------------------------------------------------
    from fastapi.testclient import TestClient  # noqa: E402
    from cuore.app import create_app  # noqa: E402

    client = TestClient(create_app())

    resp = client.get("/api/live/status")
    check_eq("GET /api/live/status is 200", resp.status_code, 200)

    resp = client.get("/api/live/modules", params={"bus": "can_c"})
    check_eq("GET /api/live/modules?bus=can_c is 200", resp.status_code, 200)
    mods = resp.json()["modules"]
    check_eq("GET /api/live/modules?bus=can_c lists 5 usable",
             sum(1 for m in mods if m["usable"]), 5,
             str([m["code"] for m in mods if m["usable"]]))

    resp = client.get("/api/live/module/ECM/did/F190")
    check_eq("GET /api/live/module/ECM/did/F190 is 200", resp.status_code, 200)
    check_eq("GET .../did/F190 returns the VIN as ascii", resp.json().get("ascii"), VIN)

    # POST /api/live/cable clears verification. can_c is only reachable
    # with cable "none", so proving the *verification* (rather than the
    # cable/route mismatch) is what now blocks the read means returning to
    # "none" afterwards: the route is fine again, but the passive-listen
    # proof is gone, which is exactly the 403 Refused case.
    resp = client.post("/api/live/cable", json={"cable": "grey_a6"})
    check_eq("POST /api/live/cable grey_a6 is 200", resp.status_code, 200)
    check_eq("declaring a new cable clears every verification", link1.verified, {})

    resp = client.post("/api/live/cable", json={"cable": "none"})
    check_eq("POST /api/live/cable none is 200", resp.status_code, 200)

    resp = client.get("/api/live/module/ECM/did/F190")
    check_eq("module read after cable churn is 403 (verification was cleared)",
             resp.status_code, 403, resp.text[:200])
finally:
    for k, v in _saved_port_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ===========================================================================
# 7. wire-recorded fixture replay (see cuore/tests/fixtures/usb_probe.jsonl)
# ===========================================================================

fixture_path = FIXTURES / "usb_probe.jsonl"
if fixture_path.exists():
    _saved_port_env2 = {k: os.environ.get(k) for k in ("CUORE_OBD_PORT",)}
    os.environ["CUORE_OBD_PORT"] = "COM3"
    try:
        link2 = AdapterLink(stream_factory=lambda p, b: PlaybackStream(fixture_path))
        set_link(link2)
        replayed = ops.probe(allow_while_mes_connected=True)
        check_eq("fixture replay: STI is STN1170 v4.3.2",
                 replayed["identity"].get("STI"), "STN1170 v4.3.2")
    finally:
        for k, v in _saved_port_env2.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
else:
    print(f"SKIP: {fixture_path} not present -- no wire recording to replay")


# ===========================================================================
# report
# ===========================================================================

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
