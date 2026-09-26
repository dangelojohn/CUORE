"""Regression checks for cuore.live.dtc_detail (ISO 14229-1 ReadDTCInformation
sub-functions 0x01/0x03/0x04/0x06).

Same posture as check_live.py: plain script, ``check()``, exit 1 on failure,
no pytest, no mocking framework.

Run:
    .venv/Scripts/python.exe cuore/tests/check_dtc_detail.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-dtc-detail-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import addressing  # noqa: E402
from cuore.live import dtc_detail  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.obd import decode_dtc_status, dtc_from_three_bytes  # noqa: E402
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
# 1. DTC string <-> 3-byte round trip (P, C, B, U codes)
# ===========================================================================

ROUNDTRIP_CASES = [
    ("01", "43", "P0143"), ("45", "61", "C0561"), ("81", "23", "B0123"),
    ("C1", "00", "U0100"), ("04", "56", "P0456"), ("D1", "10", "U1110"),
]
for a, b, base in ROUNDTRIP_CASES:
    code = f"{base}-2F"
    hi, mid, lo = dtc_detail.dtc_to_bytes(code)
    check_eq(f"dtc_to_bytes {code} -> high byte", hi, a)
    check_eq(f"dtc_to_bytes {code} -> middle byte", mid, b)
    check_eq(f"dtc_to_bytes {code} -> low byte", lo, "2F")
    check_eq(f"dtc_to_bytes/dtc_from_three_bytes round trip for {code}",
             dtc_from_three_bytes(hi, mid, lo), code)

check_eq("dtc_to_bytes defaults failure type to 00 when omitted",
         dtc_detail.dtc_to_bytes("P0456"), ("04", "56", "00"))
check_eq("dtc_to_bytes accepts lowercase", dtc_detail.dtc_to_bytes("p0456-2f"),
         ("04", "56", "2F"))

for bad in ("Q0456-00", "P045-00", "P0456-0", "P4456-00", "not a dtc"):
    try:
        dtc_detail.dtc_to_bytes(bad)
        rejected = False
    except Exception:
        rejected = True
    check(f"dtc_to_bytes rejects {bad!r}", rejected)


# ===========================================================================
# 2. 19 01 decode
# ===========================================================================

count = dtc_detail.decode_dtc_count(["59", "01", "FF", "01", "00", "05"])
check_eq("decode_dtc_count availability_mask", count["availability_mask"], 0xFF)
check_eq("decode_dtc_count format_id", count["format_id"], 0x01)
check_eq("decode_dtc_count count", count["count"], 5)
check("decode_dtc_count rejects a non-59-01 reply",
      "error" in dtc_detail.decode_dtc_count(["7F", "19", "12"]))


# ===========================================================================
# 3. 19 03 decode
# ===========================================================================

ids = dtc_detail.decode_snapshot_identification(
    ["59", "03", "04", "56", "2F", "01", "D1", "23", "10", "01"])
check_eq("decode_snapshot_identification finds both DTCs",
         [x["dtc"] for x in ids], ["P0456-2F", "U1123-10"])
check_eq("decode_snapshot_identification records the record numbers",
         [x["record_number"] for x in ids], [1, 1])


# ===========================================================================
# 4. 19 04 decode: known-length DIDs, and stop-at-unknown-length
# ===========================================================================

# ECM 0x1000 "Engine RPM" formula "((A*256)+B)/4" -> 2 bytes.
# ECM 0x192D "Current engaged gear" formula "A" -> 1 byte.
full_record = ["59", "04", "04", "56", "2F", "08",
              "01", "02", "10", "00", "0B", "4C", "19", "2D", "03"]
snap = dtc_detail.decode_snapshot_record(full_record, "ECM")
check_eq("decode_snapshot_record dtc", snap["dtc"], "P0456-2F")
check_eq("decode_snapshot_record status", snap["status"], 0x08)
check_eq("decode_snapshot_record confirmedDTC flag", snap["flags"]["confirmedDTC"], True)
check_eq("decode_snapshot_record one record parsed", len(snap["records"]), 1)
idents = snap["records"][0]["identifiers"]
check_eq("decode_snapshot_record decodes both known-length DIDs",
         [i["did"] for i in idents], ["1000", "192D"])
check_eq("decode_snapshot_record DID 1000 bytes", idents[0]["bytes"], ["0B", "4C"])
check_eq("decode_snapshot_record DID 192D bytes", idents[1]["bytes"], ["03"])
check_eq("decode_snapshot_record names DID 1000", idents[0]["name"], "Engine RPM")
check("decode_snapshot_record has no undecoded_from when everything is known",
      "undecoded_from" not in snap)

truncated_record = ["59", "04", "04", "56", "2F", "08",
                    "01", "02", "10", "00", "0B", "4C", "99", "99", "AA", "BB"]
snap2 = dtc_detail.decode_snapshot_record(truncated_record, "ECM")
check_eq("decode_snapshot_record stops at the unknown DID: one identifier decoded",
         len(snap2["records"][0]["identifiers"]), 1)
check("decode_snapshot_record reports undecoded_from for the unknown DID",
      "undecoded_from" in snap2 and "9999" in snap2["undecoded_from"], str(snap2))
check("decode_snapshot_record never guesses past the unknown DID: raw bytes are the ones left",
      "'AA', 'BB'" in snap2["undecoded_from"] and "4 raw byte(s)" in snap2["undecoded_from"],
      snap2["undecoded_from"])


# ===========================================================================
# 5. 19 06 raw records: labelled guess for known ones, raw for unknown
# ===========================================================================

ext_record = ["59", "06", "04", "56", "2F", "08", "01", "2A", "02", "05", "10", "AA", "BB"]
ext = dtc_detail.decode_extended_data(ext_record)
check_eq("decode_extended_data dtc", ext["dtc"], "P0456-2F")
check_eq("decode_extended_data decodes the two known counters", len(ext["records"]), 2)
check_eq("decode_extended_data record 1 bytes", ext["records"][0]["bytes"], ["2A"])
check("decode_extended_data record 1 is labelled a guess, unverified for FCA",
      ext["records"][0]["confidence"] == "unverified for FCA"
      and "occurrence" in ext["records"][0]["meaning_guess"])
check_eq("decode_extended_data record 2 bytes", ext["records"][1]["bytes"], ["05"])
check("decode_extended_data stops at the unrecognised record 0x10",
      "undecoded_from" in ext and "10" in ext["undecoded_from"], str(ext))

clean_ext = ["59", "06", "04", "56", "2F", "08", "01", "2A"]
check("decode_extended_data with no leftover records has no undecoded_from",
      "undecoded_from" not in dtc_detail.decode_extended_data(clean_ext))


# ===========================================================================
# 6. end-to-end fake-adapter read: dtc_detail on ECM for P0456-00, plus NRC 0x31
# ===========================================================================


def _frames(header: str, payload: str) -> str:
    """ISO-TP framing with headers on, as an STN prints it (same recipe as
    check_coverage.py's helper of the same name)."""
    n = len(payload) // 2
    if n <= 7:
        return f"{header}{n:02X}{payload}"
    out = [f"{header}1{n:03X}{payload[:12]}"]
    rest, seq = payload[12:], 1
    while rest:
        out.append(f"{header}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


class ScriptedStream(Stream):
    """Same fake ELM327/STN adapter as check_live.py's ScriptedStream."""

    def __init__(self, script: dict[str, str]):
        self.script = script
        self._buf = bytearray()
        self._opened = False

    def open(self) -> None:
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").rstrip("\r\n")
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
        return "scripted-dtc-detail"


ECM = addressing.by_code("ECM")
HDR = "18DAF110"

# 19 02 FF -> one code, P0456-00, status 0x08.
DTC_REPLY = HDR + "07" + "5902FF04560008"

# 19 04 04 56 00 FF -> snapshot: record 1, one DID (0x1000 Engine RPM, 2 bytes).
SNAPSHOT_PAYLOAD = "590404560008" + "0101" + "1000" + "0B4C"
SNAPSHOT_REPLY = _frames(HDR, SNAPSHOT_PAYLOAD)

# 19 06 04 56 00 FF -> extended: record 1 (occurrence, 0x2A), record 2 (aging, 0x05).
EXTENDED_PAYLOAD = "590604560008" + "012A" + "0205"
EXTENDED_REPLY = _frames(HDR, EXTENDED_PAYLOAD)

# 19 04 03 00 00 FF -> P0300-00 has no stored snapshot: NRC 0x31.
NRC31_REPLY = HDR + "03" + "7F1931"

SCRIPT: dict[str, str] = {
    "ATE0": "OK", "ATL0": "OK", "ATS0": "OK", "ATH1": "OK", "ATAT1": "OK",
    "ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2",
    "STP 34": "OK", "STCMM 1": "OK",
    "ATSH18DA10F1": "OK", "ATCRA18DAF110": "OK", "STCFCPA 18DA10F1,18DAF110": "OK",
    "1902FF": DTC_REPLY,
    "1904045600FF": SNAPSHOT_REPLY,
    "1906045600FF": EXTENDED_REPLY,
    "1904030000FF": NRC31_REPLY,
}

link = AdapterLink(stream_factory=lambda p, b: ScriptedStream(SCRIPT), process="check_dtc_detail")
set_link(link)

_saved_port_env = {k: os.environ.get(k) for k in ("CUORE_OBD_PORT", "OBD_PORT")}
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)

try:
    link.mark_verified(CAN_C, 10)
    with link.session("check_dtc_detail", bus=CAN_C) as sess:
        detail = dtc_detail.dtc_detail(sess, ECM, "P0456-00")
        check_eq("dtc_detail canonical dtc", detail["dtc"], "P0456-00")
        check_eq("dtc_detail status comes from 19 02", detail.get("status"), 0x08)
        check_eq("dtc_detail status_source is 19 02", detail.get("status_source"), "19 02")
        check("dtc_detail confirmedDTC flag set", detail["flags"]["confirmedDTC"] is True)

        snap = detail["snapshot"]
        check_eq("dtc_detail snapshot has no error", snap.get("error"), None)
        snap_ids = snap["records"][0]["identifiers"]
        check_eq("dtc_detail snapshot decodes DID 1000", snap_ids[0]["did"], "1000")
        check_eq("dtc_detail snapshot DID 1000 bytes", snap_ids[0]["bytes"], ["0B", "4C"])

        ext = detail["extended"]
        check_eq("dtc_detail extended has no error", ext.get("error"), None)
        check_eq("dtc_detail extended decodes two counters", len(ext["records"]), 2)
        check("dtc_detail extended record is labelled unverified for FCA",
              all(r["confidence"] == "unverified for FCA" for r in ext["records"]))

        # NRC 0x31 (requestOutOfRange) is handled as data, not an exception.
        snap31 = dtc_detail.dtc_snapshot(sess, ECM, "P0300-00")
        check_eq("NRC 0x31 snapshot has no adapter error", snap31.get("error"), None)
        check("NRC 0x31 snapshot is reported via 'note', not raised",
              bool(snap31.get("note")) and "requestOutOfRange" in snap31["note"], str(snap31))
finally:
    for k, v in _saved_port_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


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
