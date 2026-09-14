"""Regression checks for the parser, the frame reassembly and the command gate.

Plain script, no hardware. This test used to import ``server`` from
obd2-mcp and call its private helpers (``_hex_pairs``, ``_reassemble``,
``_decode_pid``, ``_validate_command``, ``classify_command``,
``resolve_port``/``resolve_baud`` ...). obd2-mcp/server.py no longer defines
any of those -- that logic moved wholesale to the ``cuore.live`` package
(``cuore/live/framing.py``, ``cuore/live/obd.py``, ``cuore/live/safety.py``,
``cuore/live/config.py``). This file re-runs the same essential cases against
the real functions there, so the old test path (and CI step, if any, that
runs "the obd2-mcp tests") keeps exercising the same behaviour.

The full, expanded version of these cases lives in
cuore/tests/check_live.py; this file is intentionally the smaller, original
subset, ported rather than replaced.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live.framing import adapter_error, hex_pairs, reassemble  # noqa: E402
from cuore.live.obd import decode_obd_dtcs, decode_pid, resolve_pid  # noqa: E402
from cuore.live.config import resolve_baud, resolve_port  # noqa: E402
from cuore.live.errors import BadCommand  # noqa: E402
from cuore.live.safety import classify_command, validate_command  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(f"  {'PASS' if good else 'FAIL'}  {label}")
    if not good:
        print(f"        got  {got!r}\n        want {want!r}")


print("1. hex_pairs with ATS0 (unspaced)")
check("mode 01 rpm",      hex_pairs("410C0B4C"),        ["41", "0C", "0B", "4C"])
check("spaced still ok",  hex_pairs("41 0C 0B 4C"),     ["41", "0C", "0B", "4C"])
check("with CAN header",  hex_pairs("7E8 410C0B4C"),    ["41", "0C", "0B", "4C"])
check("ISO-TP multiline", hex_pairs("0: 49020157\n1: 5A415346"),
      ["49", "02", "01", "57", "5A", "41", "53", "46"])
check("odd nibble trimmed", hex_pairs("410C0B4"),       ["41", "0C", "0B"])

print("\n2. adapter errors surfaced, not swallowed")
for e in ["BUFFER FULL", "CAN ERROR", "BUS BUSY", "STOPPED", "UNABLE TO CONNECT",
          "OUT OF MEMORY", "TIMEOUT"]:
    got = adapter_error(e)
    print(f"  {'PASS' if got else 'FAIL'}  {e:20} -> {got!r}")
    ok = ok and bool(got)
check("clean response has no error", adapter_error("410C0B4C"), "")

print("\n3. DTC category decode and count-byte parity")
cases = [("0143", "P0143"), ("4561", "C0561"), ("8123", "B0123"),
         ("C100", "U0100"), ("0456", "P0456"), ("D110", "U1110")]
for code, want in cases:
    # decode_obd_dtcs expects [response_byte, ...rest]; a lone code with no
    # count byte (even remaining length) is the K-line shape.
    check(f"{code} -> {want}", decode_obd_dtcs(["43", code[:2], code[2:]]), [want])
check("CAN with count byte, two codes",
      decode_obd_dtcs(["43", "02", "04", "55", "04", "40"]), ["P0455", "P0440"])
check("K-line without count byte",
      decode_obd_dtcs(["43", "04", "55", "04", "40"]), ["P0455", "P0440"])
check("zero codes", decode_obd_dtcs(["43", "00"]), [])

print("\n4. ISO-TP reassembly per ECU with headers on")
# ECM (7E8) and TCM (7E9) both answer 0100 on an 11-bit bus, ATS0 formatting.
two = reassemble("7E80641 00BE3EA813\n7E9064100801A8001".replace(" ", ""), headers_on=True)
check("two ECUs keyed by header", sorted(two), ["7E8", "7E9"])
check("single frame length honoured", two["7E8"], ["41", "00", "BE", "3E", "A8", "13"])
# 29-bit VIN: first frame (10 14) then two consecutive frames.
vin = "ZASFAKPN5J7B88115"
hx = "".join(format(ord(c), "02X") for c in vin)
ff = "18DAF110" + "1014" + "490201" + hx[:6]
cf1 = "18DAF110" + "21" + hx[6:20]
cf2 = "18DAF110" + "22" + hx[20:]
r = reassemble("\n".join([ff, cf1, cf2]), headers_on=True)
payload = r.get("18DAF110", [])
check("29-bit header recovered", list(r), ["18DAF110"])
check("first-frame length applied", len(payload), 20)
check("VIN bytes reassembled", "".join(chr(int(b, 16)) for b in payload[3:]), vin)
# ELM-side reassembly when headers are off.
r0 = reassemble("014\n0: 49 02 01 5A 41 53\n1: 46 41 4B 50 4E 35\n2: 4A 37 42 38 38 31",
                headers_on=False)
check("headers-off multi-frame concatenated", r0.get("", [])[:6],
      ["49", "02", "01", "5A", "41", "53"])
check("errors yield no payloads", reassemble("CAN ERROR", headers_on=True), {})

print("\n5. PID formulas")
hexpid, spec = resolve_pid("0C")
check("rpm", decode_pid(hexpid, spec, ["0B", "4C"])["value"], 723.0)
hexpid, spec = resolve_pid("05")
check("coolant", decode_pid(hexpid, spec, ["7B"])["value"], 83)
hexpid, spec = resolve_pid("42")
check("voltage", decode_pid(hexpid, spec, ["36", "B0"])["value"], 14.0)
hexpid, spec = resolve_pid("32")
check("evap pressure signed", decode_pid(hexpid, spec, ["FF", "F0"])["value"], -4.0)
hexpid, spec = resolve_pid("0C")
check("short bytes flagged", "error" in decode_pid(hexpid, spec, ["0B"]), True)
check("unknown pid raw", decode_pid("A9", None, ["01"])["unit"], "raw")
check("resolve friendly", resolve_pid("engine_rpm")[0], "0C")
check("resolve hex to name", resolve_pid("0c")[1].name, "engine_rpm")

print("\n6. command validation: one command per call")
for bad in ["ATI\r04", "ATI\n04", "STI|04", "", "   ", "ATI\x0004"]:
    try:
        validate_command(bad)
        rejected = False
    except BadCommand:
        rejected = True
    check(f"reject {bad!r}", rejected, True)
check("plain command passes", validate_command(" 0100 "), "0100")

print("\n7. command classification")
cases = [
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
for cmd, want in cases:
    kind, _reason = classify_command(cmd)
    check(f"{cmd:20} -> {want}", kind, want)

print("\n8. configuration resolution order")
saved = {k: os.environ.get(k) for k in ("CUORE_OBD_PORT", "CUORE_OBD_BAUD",
                                        "OBD_PORT", "OBD_BAUD")}
try:
    for k in ("CUORE_OBD_PORT", "CUORE_OBD_BAUD"):
        os.environ.pop(k, None)
    os.environ["OBD_PORT"], os.environ["OBD_BAUD"] = "COM9", "9600"
    check("argument beats env (port)", resolve_port("com3"), ("COM3", "argument"))
    check("argument beats env (baud)", resolve_baud(115200), (115200, "argument"))
    check("env used when no argument", resolve_port(""), ("COM9", "env OBD_PORT"))
    check("env baud used when no argument", resolve_baud(0), (9600, "env OBD_BAUD"))
    os.environ["CUORE_OBD_PORT"] = "COM7"
    check("CUORE_OBD_PORT beats OBD_PORT", resolve_port(""), ("COM7", "env CUORE_OBD_PORT"))
    for k in ("OBD_PORT", "OBD_BAUD", "CUORE_OBD_PORT"):
        os.environ.pop(k, None)
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print("\n" + ("ALL PASS" if ok else "FAILURES PRESENT"))
sys.exit(0 if ok else 1)
