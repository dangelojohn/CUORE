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
# 4b. Live 19 04 snapshots from the 2018 Stelvio (read 2026-10-19): ECM 10JA
#     (P0440 / P0455 / P0456, identical layout) and BCM U1713-2F. The payloads
#     are the bytes from the first DID on; the 59 04 header is synthetic.
# ===========================================================================

LIVE_ECM = {
    "P0440": ("04 40 00",
              "10 08 00 04 8D CD 10 09 00 0E 20 0A 39 14 60 82 00 19 21 40 00 01 00 00 00 00 04 00 "
              "10 00 0E 64 19 24 00 18 02 00 2D 10 02 05 E0 19 2D 03 20 01 16 64 A5 18 12 FF 34 "
              "10 03 5B 10 04 00 8F 19 37 01 73 19 23 12 19 1E 00 01 18 2F 00 86 19 35 32 19 5A 03 EC "
              "18 21 03 18 18 00 19 56 03 EC 13 02 00 23 1B 0D 80 00 00 00 00 00 04 01 19 BD 4C "
              "1B 03 84 19 8C 20 19 BE 00 20 00 00 19 28 00 10 01 8E 37 01 00"),
    "P0455": ("04 55 00",
              "10 08 00 04 8C 82 10 09 00 18 20 0A 39 0B 60 82 00 19 21 40 00 01 00 00 00 00 04 00 "
              "10 00 0B F0 19 24 00 18 02 00 23 10 02 00 00 19 2D 00 20 01 16 5B 86 18 12 00 3C "
              "10 03 6D 10 04 00 8E 19 37 01 3C 19 23 12 19 1E 00 09 18 2F 00 5C 19 35 39 19 5A 03 E9 "
              "18 21 03 18 18 00 19 56 03 E8 13 02 00 38 1B 0D A0 00 00 00 00 00 04 01 19 BD 3E "
              "1B 03 84 19 8C 20 19 BE 00 20 00 00 19 28 00 10 01 EA 37 01 00"),
    "P0456": ("04 56 00",
              "10 08 00 04 8D 59 10 09 00 00 20 0A 39 10 60 82 00 19 21 04 00 00 00 00 00 00 04 00 "
              "10 00 00 00 19 24 00 18 02 00 A0 10 02 00 00 19 2D 00 20 01 16 63 82 18 12 00 00 "
              "10 03 39 10 04 00 7B 19 37 03 C9 19 23 22 19 1E 01 00 18 2F 00 00 19 35 38 19 5A 03 CC "
              "18 21 00 18 18 00 19 56 03 D1 13 02 00 11 1B 0D 00 04 00 00 00 00 00 00 19 BD 64 "
              "1B 03 80 19 8C 01 19 BE 00 20 00 00 19 28 00 10 01 A0 37 01 00"),
}
LIVE_BCM = ("D7 13 2F",
            "10 08 00 03 C0 E2 10 09 00 11 20 0A 39 18 60 82 00 19 21 40 00 03 00 00 00 00 04 00 "
            "10 02 05 10 04 91 01 37 00 0A")


def _live_snapshot(ecu: str, dtc_bytes: str, payload: str, num_ids: int) -> tuple[dict, list[str]]:
    body = payload.split()
    frame = ["59", "04", *dtc_bytes.split(), "08", "01", f"{num_ids:02X}", *body]
    return dtc_detail.decode_snapshot_record(frame, ecu), body


def _by_did(snap: dict) -> dict[str, dict]:
    return {i["did"]: i for i in snap["records"][0]["identifiers"]}


# 4b.1 every ECM record parses with no remainder: re-joining did+bytes gives
# back the payload exactly, in order.
ecm_snaps = {}
for dtc, (dtc_b, payload) in LIVE_ECM.items():
    snap, body = _live_snapshot("ECM", dtc_b, payload, 32)
    ecm_snaps[dtc] = snap
    idents = snap["records"][0]["identifiers"]
    rebuilt = [b for i in idents for b in (i["did"][:2], i["did"][2:], *i["bytes"])]
    check(f"live ECM {dtc}: no undecoded_from", "undecoded_from" not in snap, str(snap.get("undecoded_from")))
    check_eq(f"live ECM {dtc}: 32 identifiers", len(idents), 32)
    check_eq(f"live ECM {dtc}: did+bytes re-joins to the payload with no remainder", rebuilt, body)
    check(f"live ECM {dtc}: every identifier has the full key set",
          all({"did", "name", "bytes", "value", "unit", "confidence"} <= set(i) for i in idents))
check_eq("live ECM: the three records share one DID sequence",
         len({tuple(i["did"] for i in s["records"][0]["identifiers"]) for s in ecm_snaps.values()}), 1)

# 4b.2 startup counter (DID 200A, 2 B) and the values that tie it to MES.
check_eq("P0440 startup counter 14612", _by_did(ecm_snaps["P0440"])["200A"]["value"], 14612)
check_eq("P0455 startup counter 14603", _by_did(ecm_snaps["P0455"])["200A"]["value"], 14603)
check_eq("P0456 startup counter 14608", _by_did(ecm_snaps["P0456"])["200A"]["value"], 14608)
p0440, p0456 = _by_did(ecm_snaps["P0440"]), _by_did(ecm_snaps["P0456"])
check_eq("P0440 operating time min (DID 1008, 4 B)", p0440["1008"]["value"], 298445)
check_eq("P0440 odometer km (DID 2001, 0.1 km)", p0440["2001"]["value"], 146755.7)
check_eq("P0456 is engine-off: 0 rpm", p0456["1000"]["value"], 0)
check_eq("P0456 is engine-off: 12.3 V", p0456["1004"]["value"], 12.3)
check_eq("P0440 signed spark advance -12.75 deg", p0440["1812"]["value"], -12.75)

# 4b.3 an unknown DID keeps its bytes: known length, no meaning -> name/value
# None; a DID absent from the ECU layout stops the walk (no Table C guess).
flags = p0440["1921"]
check_eq("DID 1921 keeps all 9 raw bytes", flags["bytes"],
         ["40", "00", "01", "00", "00", "00", "00", "04", "00"])
check("DID 1921 is unnamed, valueless, confidence unknown",
      flags["name"] is None and flags["value"] is None and flags["unit"] is None
      and flags["confidence"] == "unknown", str(flags))
check("named fields still keep their raw bytes",
      p0440["1000"]["bytes"] == ["0E", "64"] and p0440["1000"]["confidence"] in ("medium", "high"))
check("scale-unverified field is named but valueless (182F air flow)",
      p0440["182F"]["name"] and p0440["182F"]["value"] is None and p0440["182F"]["bytes"] == ["00", "86"])
foreign = dtc_detail.decode_snapshot_record(
    ["59", "04", "04", "40", "00", "08", "01", "02", "10", "03", "5B", "99", "99", "AA", "BB"], "ECM")
check_eq("walk keeps what it decoded before a DID the ECM layout lacks",
         [i["did"] for i in foreign["records"][0]["identifiers"]], ["1003"])
check("a DID missing from the ECM layout stops the walk with the raw bytes",
      "9999" in foreign.get("undecoded_from", "") and "'AA', 'BB'" in foreign["undecoded_from"],
      str(foreign))

# 4b.4 BCM U1713-2F parses to the last byte, and so does the 2026-10-13 BCM
# read (docs/vehicles/.../2026-10-13-live-read-3.json) that first stalled at 1008.
bcm_snap, bcm_body = _live_snapshot("BCM", *LIVE_BCM, 8)
bcm_idents = bcm_snap["records"][0]["identifiers"]
check("BCM: no undecoded_from", "undecoded_from" not in bcm_snap, str(bcm_snap.get("undecoded_from")))
check_eq("BCM: DID order", [i["did"] for i in bcm_idents],
         ["1008", "1009", "200A", "6082", "1921", "1002", "1004", "3700"])
check_eq("BCM: did+bytes re-joins to the payload with no remainder",
         [b for i in bcm_idents for b in (i["did"][:2], i["did"][2:], *i["bytes"])], bcm_body)
check_eq("BCM startup counter 14616", _by_did(bcm_snap)["200A"]["value"], 14616)
check_eq("BCM 1004 stays raw", _by_did(bcm_snap)["1004"]["bytes"], ["91", "01"])
bcm_old, _ = _live_snapshot(
    "BCM", "D7 13 2F",
    "10 08 00 03 BE 84 10 09 00 0E 20 0A 38 F7 60 82 00 19 21 40 00 03 00 00 00 00 04 00 "
    "10 02 00 10 04 89 01 37 00 0A", 8)
check("BCM 2026-10-13 record: no undecoded_from", "undecoded_from" not in bcm_old)
check_eq("BCM 2026-10-13 startup counter 14583", _by_did(bcm_old)["200A"]["value"], 14583)


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
