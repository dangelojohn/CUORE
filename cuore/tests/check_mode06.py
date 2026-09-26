"""Regression checks for cuore.live.mode06.

Same posture as check_live.py / check_coverage.py: plain script, ``check()``,
exit 1 on failure, no pytest -- hand-built adapter replies and a fake
``Stream`` (same shape as the ``BusStream``/``MonitorStream`` fakes in
check_coverage.py) instead of a mocking framework.

Run:
    .venv/Scripts/python.exe cuore/tests/check_mode06.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: state must go to a throwaway directory.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-mode06-")
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import mode06  # noqa: E402
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


def check_eq(label: str, got, want) -> None:
    check(label, got == want, f"got {got!r} want {want!r}")


# ===========================================================================
# 1. supported-MID bitmap decode (pure)
# ===========================================================================

supported, more = mode06.decode_supported_mid_bitmap("00", ["80", "00", "00", "01"])
check_eq("bitmap: bit31 -> MID 01 supported", "01" in supported, True)
check_eq("bitmap: bit0 also flags MID 32 (0x20) supported", "20" in supported, True)
check_eq("bitmap: bit0 set means the next block is supported", more, True)

supported2, more2 = mode06.decode_supported_mid_bitmap("00", ["00", "00", "00", "00"])
check_eq("bitmap: all-zero bitmap supports nothing", supported2, [])
check_eq("bitmap: all-zero bitmap has no next block", more2, False)

# A bitmap for base "20" with only bit4 set names MID 0x3C (start=0x20=32,
# i=27, code = 32+1+27 = 60 = 0x3C).
supported3, more3 = mode06.decode_supported_mid_bitmap("20", ["00", "00", "00", "10"])
check_eq("bitmap: base 20 bit4 names MID 3C", supported3, ["3C"])
check_eq("bitmap: that bitmap does not flag a next block", more3, False)


# ===========================================================================
# 2. test-result record decode (pure): two records, one pass one fail
# ===========================================================================

# TID 01, UASID 0A (voltage, 0.122 mV/count): value 1000 -> 122.0 mV,
# min 0 -> 0.0 mV, max 2000 -> 244.0 mV. 122 is within [0, 244]: PASS.
# TID 02, UASID 24 (count, 1/count): value 500, min 0, max 100. 500 is
# above the max: FAIL.
payload = ["01", "0A", "03", "E8", "00", "00", "07", "D0",
           "3C", "02", "24", "01", "F4", "00", "00", "00", "64"]
records = mode06.decode_mode06_records("3C", payload)
check_eq("records: two 9-byte records decoded", len(records), 2)

r1, r2 = records
check_eq("record1: mid_name resolved for EVAP 0.020\" MID", r1["mid_name"],
         mode06.OBDMID_NAMES["3C"])
check_eq("record1: TID kept as given", r1["tid"], "01")
check_eq("record1: UASID kept as given", r1["uasid"], "0A")
check_eq("record1: voltage scaled 1000 * 0.122 = 122.0 mV", r1["value"], 122.0)
check_eq("record1: min scaled to 0.0 mV", r1["min"], 0.0)
check_eq("record1: max scaled to 244.0 mV", r1["max"], 244.0)
check_eq("record1: unit is mV", r1["unit"], "mV")
check_eq("record1: within [min, max] -> passed", r1["passed"], True)

check_eq("record2: count value kept raw (scale 1)", r2["value"], 500)
check_eq("record2: over the max limit -> failed", r2["passed"], False)
check_eq("record2: unit is count", r2["unit"], "count")


# ===========================================================================
# 3. unknown UASID is returned raw, not guessed
# ===========================================================================

unknown = mode06.decode_uasid("99", 42)
check_eq("unknown UASID: scaling flagged unknown", unknown["scaling"], "unknown")
check_eq("unknown UASID: value kept as the untouched raw int", unknown["value"], 42)
check_eq("unknown UASID: no unit invented", unknown["unit"], None)

# The UASIDs the spec named but this module would not guess a formula for.
for uid in mode06.UNCERTAIN_UASIDS:
    d = mode06.decode_uasid(uid, 7)
    check(f"uncertain UASID 0x{uid} stays unknown", d["scaling"] == "unknown", str(d))

# Signed mirror: 0x8A is the signed twin of 0x0A (voltage, same scale), and
# a raw value with the sign bit set must come back negative.
signed = mode06.decode_uasid("8A", 0xFFFF)  # -1 raw -> -0.122 mV
check_eq("signed UASID 8A mirrors 0A's scale", signed["unit"], "mV")
check_eq("signed UASID 8A decodes two's-complement -1", signed["value"], -0.122)


# ===========================================================================
# 4. evap_summary sentences
# ===========================================================================

fake_read_result = {
    "results": {
        "3C": {"by_ecu": {"18DAF110": records}},
        # 39, 3A, 3B, 3D deliberately absent -> "not supported"
    }
}
summary = mode06.evap_summary(fake_read_result)
check_eq("evap_summary: one line per EVAP MID gap + two 3C records", len(summary), 6)
check("evap_summary: cap-off MID reported unsupported",
      any("cap off" in line and "not supported by this ECU" in line for line in summary),
      str(summary))
check("evap_summary: 0.020\" pass sentence",
      any('0.020" leak' in line and "122.0 mV" in line and "244.0 mV" in line
          and "PASS" in line for line in summary),
      str(summary))
check("evap_summary: 0.020\" fail sentence",
      any('0.020" leak' in line and "value 500" in line and "FAIL" in line
          for line in summary),
      str(summary))


# ===========================================================================
# 5. fake-adapter end-to-end run of read_mode06
# ===========================================================================

def _iso_tp(header: str, payload_hex: str) -> str:
    """ISO-TP framing with headers on, as an STN prints it (see check_coverage.py)."""
    n = len(payload_hex) // 2
    if n <= 7:
        return f"{header}{n:02X}{payload_hex}"
    out = [f"{header}1{n:03X}{payload_hex[:12]}"]
    rest, seq = payload_hex[12:], 1
    while rest:
        out.append(f"{header}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


_HDR = "18DAF110"
_MID_3C_PAYLOAD = "463C" + "010A03E8000007D0" + "3C" + "022401F400000064"
_MID_39_PAYLOAD = "7F0612"  # negative response: MID not supported (NRC 0x12)

_TABLE = {
    "0620": "NO DATA",
    "063C": _iso_tp(_HDR, _MID_3C_PAYLOAD),
    "0639": _iso_tp(_HDR, _MID_39_PAYLOAD),
}


class Mode06Stream(Stream):
    """Answers by exact command match; everything AT/ST-ish is just OK'd."""

    def __init__(self, table: dict[str, str]) -> None:
        self.table = table
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
        if cmd in self.table:
            return self.table[cmd]
        if cmd == "ATI":
            return "ELM327 v2.3"
        if cmd == "STI":
            return "STN1170 v4.3.2"
        if cmd.startswith(("AT", "ST")):
            return "OK"
        return "NO DATA"

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
        return "mode06-fake"


stream = Mode06Stream(_TABLE)
lk = AdapterLink(stream_factory=lambda p, b: stream, process="check_mode06")
set_link(lk)
lk.mark_verified(CAN_C, 10)
with lk.session("mode06-test", bus=CAN_C) as sess:
    result = mode06.read_mode06(sess, mids=["20", "3C", "39"])

check("read_mode06 requested exactly the three given MIDs", "20" in result["results"] and
      "3C" in result["results"] and "39" in result["results"], str(result["results"].keys()))

r20 = result["results"]["20"]
check_eq("MID 20: NO DATA recorded as a warning, not an error", r20.get("warning"), "NO DATA")
check("MID 20: no crash, no fabricated records", "by_ecu" not in r20)

r3c = result["results"]["3C"]
check("MID 3C: multi-frame reply reassembled into two records",
      len(r3c.get("by_ecu", {}).get(_HDR, [])) == 2, str(r3c))
check_eq("MID 3C via read_mode06: record1 passes", r3c["by_ecu"][_HDR][0]["passed"], True)
check_eq("MID 3C via read_mode06: record2 fails", r3c["by_ecu"][_HDR][1]["passed"], False)

r39 = result["results"]["39"]
check("MID 39: negative response reported, not silence", "negative" in r39, str(r39))
check("MID 39: NRC 0x12 named", "0x12" in r39["negative"].get(_HDR, ""), str(r39))
check("MID 39: subFunctionNotSupported text included",
      "subFunctionNotSupported" in r39["negative"].get(_HDR, ""), str(r39))
check("MID 39: no by_ecu fabricated for a negative response", "by_ecu" not in r39)

check("untarget() was called before the MID loop (functional header restated)",
      any(c.startswith("ATSH") for c in stream.sent), str(stream.sent))


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
