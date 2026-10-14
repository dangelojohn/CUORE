"""Regression checks for cuore.live.dtc_records.

Same posture as cuore/tests/check_live.py: plain script, check()/check_eq(),
exit 1 on failure, no pytest. Never opens COM3, never calls ops/obd2 -- pure
function calls against raw bytes copied out of a real session log.

Run:
    .venv/Scripts/python.exe cuore/tests/check_dtc_records.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import dtc_records  # noqa: E402

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
# the real 38-byte remainder: Stelvio BCM U1713-2F, 19 04, 2026-10-13
# (docs/vehicles/ZASFAKPN5J7B88115/sessions/2026-10-13-live-read-3.json,
#  bcm_u1713.snapshot.undecoded_from)
# ===========================================================================

RAW_38 = ["10", "08", "00", "03", "BE", "84", "10", "09", "00", "0E", "20", "0A", "38", "F7",
          "60", "82", "00", "19", "21", "40", "00", "03", "00", "00", "00", "00", "04", "00",
          "10", "02", "00", "10", "04", "89", "01", "37", "00", "0A"]
check_eq("38-byte record length", len(RAW_38), 38)

walk = dtc_records.walk_structural_snapshot(RAW_38)
entries = walk["entries"]
check_eq("walk finds exactly 2 DIDs (1008, 1009)", len(entries), 2)
check_eq("entry 0 is DID 1008", entries[0]["did"] if entries else None, "1008")
check_eq("DID 1008 payload inferred as 4 bytes (next tag 1009 found 4 bytes later)",
         entries[0]["length"] if entries else None, 4)
check_eq("DID 1008 payload bytes", entries[0]["bytes"] if entries else None,
         ["00", "03", "BE", "84"])
check_eq("DID 1008 length_source says inferred, SINGLE-SOURCE",
         entries[0]["length_source"] if entries else None,
         "inferred from record layout, SINGLE-SOURCE")
check_eq("DID 1008 meaning is UNKNOWN, not invented", entries[0]["meaning"] if entries else None,
         "UNKNOWN (use the service manual, TechAuthority)")

check_eq("entry 1 is DID 1009", entries[1]["did"] if len(entries) > 1 else None, "1009")
check_eq("DID 1009 has no further ascending tag (100A never appears) -> honest remainder, "
         "30 bytes", entries[1]["length"] if len(entries) > 1 else None, 30)
check("DID 1009 length_source is the honest-remainder label, not a guessed length",
      len(entries) > 1 and entries[1]["length_source"].startswith("honest remainder"),
      entries[1]["length_source"] if len(entries) > 1 else "<missing>")
check_eq("DID 1009 meaning is UNKNOWN, not invented",
         entries[1]["meaning"] if len(entries) > 1 else None,
         "UNKNOWN (use the service manual, TechAuthority)")

# No leftover bytes: 2 (tag) + 4 (payload) + 2 (tag) + 30 (payload) == 38.
check_eq("no leftover bytes once the walk consumes DID 1008 + DID 1009",
         walk["leftover_bytes"], [])
total = sum(2 + e["length"] for e in entries)
check_eq("tags + payload lengths sum to the full 38 bytes", total, 38)


# ===========================================================================
# enrich_snapshot(): wraps a dtc_detail-shaped snapshot dict, byte-for-byte
# pass-through of every existing key, plus structural_decode
# ===========================================================================

undecoded_msg = ("DID 1008 (length unknown); 38 raw byte(s) remain from here: " + repr(RAW_38))
snapshot_in = {
    "ecu": "BCM", "dtc": "U1713-2F", "record": "FF", "error": None, "nrc": None,
    "status": 15, "flags": {"testFailed": True}, "records": [{"record_number": 1,
                                                                "identifiers": []}],
    "undecoded_from": undecoded_msg,
}
enriched = dtc_records.enrich_snapshot(snapshot_in)
check_eq("enrich_snapshot passes ecu through unchanged", enriched["ecu"], "BCM")
check_eq("enrich_snapshot passes status through unchanged", enriched["status"], 15)
check_eq("enrich_snapshot passes undecoded_from through unchanged",
         enriched["undecoded_from"], undecoded_msg)
check("enrich_snapshot adds structural_decode", "structural_decode" in enriched)
check_eq("enrich_snapshot's structural_decode finds the same 2 DIDs",
         len(enriched["structural_decode"]["entries"]), 2)
check_eq("enrich_snapshot's structural_decode raw_bytes matches the 38-byte record",
         enriched["structural_decode"]["raw_bytes"], RAW_38)

# A snapshot with no undecoded_from (dtc_detail fully decoded it) must come
# back completely unchanged -- no structural_decode key invented.
clean_snapshot = {"ecu": "BCM", "dtc": "P0456-00", "status": 0, "records": []}
check_eq("enrich_snapshot is a no-op when there is no undecoded_from",
         dtc_records.enrich_snapshot(clean_snapshot), clean_snapshot)


# ===========================================================================
# decode_standard_did(): F190 VIN -> ASCII (ISO 14229-1 Annex C)
# ===========================================================================

vin = "ZASFAKPN5J7B88115"
vin_bytes = [f"{b:02X}" for b in vin.encode("ascii")]
check_eq("VIN is 17 characters (ISO 14229-1 Annex C fixed length for F190)", len(vin_bytes), 17)
f190 = dtc_records.decode_standard_did(0xF190, vin_bytes)
check_eq("F190 decodes to the VIN string", f190["meaning"]["value"], vin)
check_eq("F190 length_source is ISO 14229-1 standard, not inferred",
         f190["length_source"], "ISO 14229-1 standard")
check_eq("F190 meaning cites ISO 14229-1 Annex C",
         f190["meaning"]["source"], "ISO 14229-1 Annex C (identification option F190)")


# ===========================================================================
# An unknown layout (no standard DID, no ascending tag at all) reports the
# raw bytes and invents nothing.
# ===========================================================================

unknown_run = ["20", "01", "AA", "BB", "CC"]  # 0x2001 is not F1xx and not 0x10xx
unknown_walk = dtc_records.walk_structural_snapshot(unknown_run)
check_eq("unknown DID walk produces exactly one entry", len(unknown_walk["entries"]), 1)
check_eq("unknown DID tag is 2001", unknown_walk["entries"][0]["did"], "2001")
check_eq("unknown DID payload is the raw remaining bytes, untouched",
         unknown_walk["entries"][0]["bytes"], ["AA", "BB", "CC"])
check("unknown DID gets the honest-remainder source label (no fixed length known)",
      unknown_walk["entries"][0]["length_source"].startswith("honest remainder"))
check_eq("unknown DID meaning is UNKNOWN, never invented",
         unknown_walk["entries"][0]["meaning"],
         "UNKNOWN (use the service manual, TechAuthority)")


# ===========================================================================
# enrich_extended(): 19 06 remainder is reported raw, never relabelled as
# ISO 14229 Annex D (Annex D itself assigns no record-number meanings)
# ===========================================================================

extended_undecoded = ("record 0x7F (length unknown); 2 raw byte(s) remain: ['7F', '01']")
extended_in = {"ecu": "BCM", "dtc": "U1713-2F", "status": 15, "records": [],
              "undecoded_from": extended_undecoded}
extended_out = dtc_records.enrich_extended(extended_in)
check_eq("enrich_extended passes dtc through unchanged", extended_out["dtc"], "U1713-2F")
check_eq("enrich_extended raw_bytes matches the undecoded remainder",
         extended_out["structural_decode"]["raw_bytes"], ["7F", "01"])
check("enrich_extended's note does not claim an ISO 14229 Annex D meaning",
      "Annex D leaves" in extended_out["structural_decode"]["note"],
      extended_out["structural_decode"]["note"])

clean_extended = {"ecu": "BCM", "dtc": "P0456-00", "status": 0, "records": []}
check_eq("enrich_extended is a no-op when there is no undecoded_from",
         dtc_records.enrich_extended(clean_extended), clean_extended)


# ===========================================================================
# enrich_dtc_detail(): the whole-record wrapper used by the live.py route
# ===========================================================================

full_detail = {"ecu": "BCM", "dtc": "U1713-2F", "status": 15,
               "snapshot": snapshot_in, "extended": extended_in}
full_out = dtc_records.enrich_dtc_detail(full_detail)
check_eq("enrich_dtc_detail passes top-level dtc through unchanged", full_out["dtc"], "U1713-2F")
check("enrich_dtc_detail enriches snapshot", "structural_decode" in full_out["snapshot"])
check("enrich_dtc_detail enriches extended", "structural_decode" in full_out["extended"])

no_snapshot_detail = {"ecu": "BCM", "dtc": "P0456-00", "status": 0}
check_eq("enrich_dtc_detail tolerates a detail dict with no snapshot/extended keys",
         dtc_records.enrich_dtc_detail(no_snapshot_detail), no_snapshot_detail)


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
