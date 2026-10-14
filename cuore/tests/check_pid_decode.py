"""Regression checks for the Mode 01 PID gap, Mode 09, and the Mode 06 retry.

Same posture as cuore/tests/check_live.py: plain script, check(label, cond,
detail), exit 1 on failure, no pytest, no mocking framework. Covers the 19
PIDs the 2018 Stelvio ECM (18DAF110) reported as supported but which came
back raw/undecoded on the 2026-10-13 bench read, plus Mode 09 (04/06/08/0A)
and the Mode 06 "CAN ERROR" retry path.

Run:
    .venv/Scripts/python.exe cuore/tests/check_pid_decode.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import mode06, mode09, obd  # noqa: E402
from cuore.live.framing import reassemble  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def decoded_value(pid: str, bytes_hex: list[str]) -> Any:
    hx, spec = obd.resolve_pid(pid)
    out = obd.decode_pid(hx, spec, bytes_hex)
    check(f"PID {pid} decodes without error", "error" not in out, str(out))
    return out.get("value")


# --- the 19 raw replies from the live 18DAF110 read, decoded + checked -----

v = decoded_value("13", ["03"])
check("13 o2 present", v == {"bank1_sensor1": True, "bank1_sensor2": True,
                              "bank1_sensor3": False, "bank1_sensor4": False,
                              "bank2_sensor1": False, "bank2_sensor2": False,
                              "bank2_sensor3": False, "bank2_sensor4": False}, str(v))

v = decoded_value("15", ["0A", "80"])
check("15 o2 voltage/trim", v == {"voltage_V": round(0x0A / 200, 3), "stft_pct": 0.0}, str(v))

v = decoded_value("1C", ["01"])
check("1C obd standard", v == {"code": 1, "standard": "OBD-II (California ARB)"}, str(v))

v = decoded_value("2C", ["00"])
check("2C commanded egr", v == 0.0, str(v))

v = decoded_value("2D", ["FF"])
check("2D egr error", v == round((0xFF - 128) * 100 / 128, 3), str(v))

v = decoded_value("34", ["7F", "80", "80", "00"])
ab, cd = 0x7F80, 0x8000
check("34 o2 wide range", v == {"lambda": round(ab / 32768, 5),
                                 "current_mA": round(cd / 256 - 128, 3)}, str(v))

v = decoded_value("3C", ["14", "DC"])
check("3C catalyst temp", v == round(0x14DC / 10 - 40, 3), str(v))

v = decoded_value("40", ["FE", "D0", "90", "81"])
expect_sup, expect_next = obd.decode_supported_pids("40", ["FE", "D0", "90", "81"])
check("40 pids supported 41-60", v == {"supported": expect_sup, "has_next": expect_next}, str(v))
check("40 includes 47/49/4A/54/59/60", all(p in v["supported"] for p in ("47", "49", "4A", "54", "59", "60")))

v = decoded_value("41", ["00", "04", "80", "A4"])
check("41 mil/dtc", v["mil_on"] is False and v["stored_dtc_count"] == 0, str(v))
check("41 ignition spark", v["ignition"] == "spark", str(v))
names = {m["monitor"]: m for m in v["monitors"]}
check("41 comprehensive components complete", names.get("Comprehensive components", {}).get("complete") is True, str(v))
check("41 EGR system incomplete", names.get("EGR system", {}).get("complete") is False, str(v))

v = decoded_value("47", ["2C"])
check("47 throttle B", v == round(0x2C * 100 / 255, 3), str(v))

v = decoded_value("49", ["53"])
check("49 pedal D", v == round(0x53 * 100 / 255, 3), str(v))

v = decoded_value("4A", ["50"])
check("4A pedal E", v == round(0x50 * 100 / 255, 3), str(v))

v = decoded_value("54", ["EE", "15"])
raw54 = 0xEE15
signed54 = raw54 - 65536 if raw54 & 0x8000 else raw54
check("54 evap vapor pressure signed", v == round(signed54 / 1000, 3), str(v))

v = decoded_value("59", ["01", "8B"])
check("59 fuel rail pressure abs", v == 0x018B * 10, str(v))

v = decoded_value("60", ["01", "21", "40", "00"])
expect_sup60, expect_next60 = obd.decode_supported_pids("60", ["01", "21", "40", "00"])
check("60 pids supported 61-80", v == {"supported": expect_sup60, "has_next": expect_next60}, str(v))
check("60 includes 68/6B/70/72", all(p in v["supported"] for p in ("68", "6B", "70", "72")), str(v))

v = decoded_value("68", ["03", "53", "62", "00"])
check("68 intake air temp sensors", v == {"bitmap": 3, "bank1_sensor1": 0x53 - 40,
                                           "bank1_sensor2": 0x62 - 40}, str(v))

v = decoded_value("6B", ["01", "7F", "00", "00", "00"])
check("6B egr temperature", v == {"bitmap": 1,
                                   "egr_temp_bank1_C": round(0x7F00 / 10 - 40, 3)}, str(v))

v = decoded_value("70", ["02", "01", "F4", "00", "C8"])
check("70 boost pressure control", v == {"status": 2, "commanded_boost_kPa": round(0x01F4 * 0.01, 3),
                                          "actual_boost_kPa": round(0x00C8 * 0.01, 3)}, str(v))

# No raw reply was captured for 72 tonight; synthetic data exercises the decoder.
v = decoded_value("72", ["02", "80", "7F"])
check("72 wastegate control", v == {"status": 2, "commanded_pct": round(0x80 * 100 / 255, 3),
                                     "actual_pct": round(0x7F * 100 / 255, 3)}, str(v))

# --- unknown PID still returns raw, never guessed -----------------------------

hx, spec = obd.resolve_pid("99")
out99 = obd.decode_pid(hx, spec, ["01", "02"])
check("unknown PID has no decoded value", "value" not in out99, str(out99))
check("unknown PID keeps raw bytes", out99["bytes"] == ["01", "02"], str(out99))
check("unknown PID unit is raw", out99["unit"] == "raw", str(out99))


# --- Mode 09: 04 / 06 / 08 / 0A from synthetic frames ------------------------

def isotp_lines(header: str, data: list[str]) -> str:
    """Build ELM-style text lines (header on) for an arbitrary-length payload,
    splitting into an ISO-TP first frame (6 data bytes) + consecutive frames
    (7 data bytes each) exactly as a real multi-frame reply would arrive.
    """
    n = len(data)
    if n <= 7:
        pci = f"{n:02X}"
        return header + pci + "".join(data)
    lines = []
    ff_data, rest = data[:6], data[6:]
    lines.append(header + f"1{(n >> 8) & 0xF:01X}{n & 0xFF:02X}" + "".join(ff_data))
    seq = 1
    while rest:
        chunk, rest = rest[:7], rest[7:]
        lines.append(header + f"2{seq & 0xF:01X}" + "".join(chunk))
        seq += 1
    return "\n".join(lines)


# PID 04: calibration ID "ABCD1234EFGH5678" (16 ASCII bytes), count=1.
calid_ascii = "ABCD1234EFGH5678"
calid_bytes = [f"{ord(c):02X}" for c in calid_ascii]
text04 = isotp_lines("7E8", ["49", "04", "01"] + calid_bytes)
ecus04 = reassemble(text04, headers_on=True)
check("mode09 04 multi-frame reassembled to 19 bytes", len(ecus04["7E8"]) == 19, str(ecus04))
r04 = mode09.decode_mode09("04", ecus04)
check("mode09 04 decodes one calibration id", r04["7E8"]["calibration_ids"] == [calid_ascii], str(r04))
check("mode09 04 count", r04["7E8"]["count"] == 1, str(r04))

# PID 06: one CVN, 4 raw bytes, count=1.
raw_ecus06 = {"7E8": ["49", "06", "01", "AB", "CD", "12", "34"]}
r06 = mode09.decode_mode09("06", raw_ecus06)
check("mode09 06 decodes one cvn", r06["7E8"]["cvns"] == ["ABCD1234"], str(r06))

# PID 0A: ECU name, NUL-padded ASCII.
name_bytes = [f"{ord(c):02X}" for c in "PCM-STELVIO"] + ["00"] * 9
raw_ecus0a = {"7E8": ["49", "0A", "01"] + name_bytes}
r0a = mode09.decode_mode09("0A", raw_ecus0a)
check("mode09 0A ecu name", r0a["7E8"]["ecu_name"] == "PCM-STELVIO", str(r0a))

# PID 08: IPT -- OBDCOND, IGNCNTR, then 8 monitor (num, den) pairs; EVAP is
# the 7th pair. Make EVAP's numerator/denominator distinctive so a wiring
# bug (off-by-one pair) fails loudly instead of landing on a plausible number.
words = [111, 222] + [0, 0] * 6 + [17, 34] + [0, 0]  # EVAP = (17, 34) -> rate 0.5
word_bytes = []
for w in words:
    word_bytes += [f"{(w >> 8) & 0xFF:02X}", f"{w & 0xFF:02X}"]
raw_ecus08 = {"7E8": ["49", "08"] + word_bytes}
r08 = mode09.decode_mode09("08", raw_ecus08)
m08 = r08["7E8"]["monitors"]
check("mode09 08 OBDCOND/IGNCNTR", r08["7E8"]["OBDCOND"] == 111 and r08["7E8"]["IGNCNTR"] == 222, str(r08))
check("mode09 08 EVAP numerator/denominator", m08["EVAP"]["numerator"] == 17
      and m08["EVAP"]["denominator"] == 34, str(m08))
check("mode09 08 EVAP completion rate", m08["EVAP"]["completion_rate"] == 0.5, str(m08))

# Mode 09 PID the module has no decoder for still returns raw, not a guess.
raw_ecus_unk = {"7E8": ["49", "11", "AA", "BB"]}
r_unk = mode09.decode_mode09("11", raw_ecus_unk)
check("mode09 unknown pid returns raw", r_unk["7E8"] == {"raw": ["49", "11", "AA", "BB"]}, str(r_unk))


# --- Mode 06: MID retry on "CAN ERROR", honest "retry failed" ---------------

def mode06_record(mid: str, tid: str, uasid: str, value: int, vmin: int, vmax: int) -> list[str]:
    def b2(n: int) -> list[str]:
        return [f"{(n >> 8) & 0xFF:02X}", f"{n & 0xFF:02X}"]
    return ["46", mid, tid, uasid] + b2(value) + b2(vmin) + b2(vmax)


class FakeMode06Session:
    """Minimal stand-in for transport.Session: scripted query() replies, one
    sequence per MID, replaying the last entry once a MID's script is used up.
    """

    def __init__(self, scripts: dict[str, list[dict[str, Any]]]) -> None:
        self.scripts = scripts
        self.calls: dict[str, int] = {}

    def untarget(self) -> None:
        pass

    def query(self, request_hex: str, response_byte: str, timeout: float = 4.0) -> dict[str, Any]:
        mid = request_hex[2:]
        seq = self.calls.get(mid, 0)
        self.calls[mid] = seq + 1
        script = self.scripts[mid]
        return script[min(seq, len(script) - 1)]


def ok_reply(mid: str) -> dict[str, Any]:
    data = mode06_record(mid, "01", "01", 5, 1, 16)
    return {"raw": "46 " + " ".join(data[1:]), "error": None,
            "ecus": {"7E8": data}, "all_ecus": {"7E8": data}}


def err_reply(err: str) -> dict[str, Any]:
    return {"raw": err, "error": err, "ecus": {}, "all_ecus": {}}


sess_retry_ok = FakeMode06Session({"01": [err_reply("CAN ERROR"), ok_reply("01")]})
r_retry_ok = mode06.read_mode06(sess_retry_ok, mids=["01"])
check("mode06 retry: two attempts made", sess_retry_ok.calls["01"] == 2)
check("mode06 retry succeeded: no error", "error" not in r_retry_ok["results"]["01"], str(r_retry_ok))
check("mode06 retry succeeded: flagged", r_retry_ok["results"]["01"].get("retried") ==
      "CAN ERROR on first attempt; retry succeeded", str(r_retry_ok))
check("mode06 retry succeeded: record decoded",
      r_retry_ok["results"]["01"]["by_ecu"]["7E8"][0]["value"] == 5, str(r_retry_ok))

sess_retry_fail = FakeMode06Session({"02": [err_reply("CAN ERROR"), err_reply("CAN ERROR")]})
r_retry_fail = mode06.read_mode06(sess_retry_fail, mids=["02"])
check("mode06 retry: two attempts made (both fail)", sess_retry_fail.calls["02"] == 2)
check("mode06 retry failed honestly reported",
      "retry failed" in r_retry_fail["results"]["02"]["error"], str(r_retry_fail))

# A non-CAN-ERROR failure must not be retried (only one attempt).
sess_other_err = FakeMode06Session({"03": [err_reply("BUS ERROR"), ok_reply("03")]})
r_other_err = mode06.read_mode06(sess_other_err, mids=["03"])
check("mode06 non-CAN-ERROR not retried", sess_other_err.calls["03"] == 1)
check("mode06 non-CAN-ERROR reported as adapter error",
      "ADAPTER/BUS ERROR" in r_other_err["results"]["03"]["error"], str(r_other_err))


# --- summary -----------------------------------------------------------------

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
if failures:
    sys.exit(1)
