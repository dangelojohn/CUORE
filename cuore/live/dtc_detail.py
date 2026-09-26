"""ISO 14229-1 ReadDTCInformation (service 0x19), the sub-functions beyond
``19 02`` (status mask, decoded in :mod:`obd`/:mod:`uds`): the count report
(``19 01``), snapshot identification (``19 03``), snapshot records
(``19 04``), and extended data records (``19 06``).

Everything here is read-only by construction: service 0x19 is on the
read-only allowlist for *any* sub-function (see ``safety.READ_ONLY_UDS``), so
this module only adds parsing on top of :func:`uds.request` -- it never opens
a new code path to the adapter. Pure decoders (stdlib only) plus thin session
readers.

Snapshot records (``19 04``) name each Data Identifier but do not carry its
length; ISO 14229-1 leaves that to whatever database the tester already has
for the ECU. This module only knows a DID's length when it is standard
(VIN, fixed 17 ASCII chars; the active-session DID, fixed 1 byte) or when it
can be inferred from a Table C formula in ``addressing.DIDS`` (the highest
byte letter -- A, B, C, ... -- the formula references). Anywhere else the
length is genuinely unknown, and this module refuses to guess it: it stops
walking the record and returns what is left as raw bytes under
``undecoded_from``.

Extended data records (``19 06``) are explicitly manufacturer-specific in
ISO 14229-1 Annex D, which gives no universal meaning for a record number.
The one convention this module labels (record 1/2/3 as an occurrence /
aging / aged counter, each a single byte) is a long-standing AUTOSAR Dem
convention seen across many OEMs -- not a Stellantis/FCA-confirmed one, and
it is flagged ``"confidence": "unverified for FCA"`` everywhere it appears.
No FCA/Stellantis-specific public documentation of its extended-data record
numbers was found (searched 2026-09-26). Sources for the convention itself:
  - https://automotive.wiki/index.php/Diagnostic_Event_Manager
    ("Extended data ... cycle counters, aging counters, time of last
    occurrences" -- generic AUTOSAR Dem terms)
  - https://uds.readthedocs.io/en/latest/pages/knowledge_base/dtc.html
    (aging counter counts operation cycles since the last occurrence; the
    DTC is aged out once its aging counter reaches the aging threshold,
    commonly 40 cycles)
Any record number outside that guessed set is returned raw, unlabelled.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import uds
from .addressing import ANNEX_C, DIDS, ECUAddress
from .errors import BadCommand
from .obd import HEX_DIGITS, decode_dtc_status, dtc_from_three_bytes
from .transport import Session

# ---------------------------------------------------------------------------
# DTC string <-> UDS 3-byte form
# ---------------------------------------------------------------------------


def dtc_to_bytes(code: str) -> tuple[str, str, str]:
    """Inverse of ``obd.dtc_from_three_bytes``: ``"P0456-2F"`` or ``"P0456"``
    (failure type defaults to ``"00"``) -> ``(high, middle, low)`` hex byte
    strings, upper case, ready to embed in a ``19 04``/``19 06`` request.

    Derivation, matching ``dtc_from_two_bytes``/``dtc_from_three_bytes``
    exactly: the code's first two characters encode the high nibble of the
    high byte (2-bit prefix P/C/B/U, then a 2-bit digit 0-3); the third
    character is that byte's low nibble; the fourth and fifth characters are
    the middle byte verbatim; the suffix after the dash is the low byte.
    """
    up = code.strip().upper()
    if "-" in up:
        base, low = up.split("-", 1)
    else:
        base, low = up, "00"
    if (len(base) != 5 or base[0] not in "PCBU"
            or any(c not in HEX_DIGITS for c in base[1:])):
        raise BadCommand(f"{code!r} is not a DTC like P0456 or P0456-00")
    digit = int(base[1], 16)
    if digit > 3:
        raise BadCommand(f"{code!r}: second character must be 0-3, got {base[1]!r}")
    if len(low) != 2 or any(c not in HEX_DIGITS for c in low):
        raise BadCommand(f"{code!r}: failure type {low!r} must be two hex digits")
    prefix_idx = "PCBU".index(base[0])
    high_val = (prefix_idx << 2) | digit
    high = f"{high_val:X}{base[2]}"
    middle = base[3:5]
    return high, middle, low.upper()


def _dtc_bytes(dtc: str) -> tuple[int, int, int, str]:
    """``(high, middle, low)`` as ints, plus the canonical ``"P0456-00"`` form."""
    hi, mid, lo = dtc_to_bytes(dtc)
    canonical = dtc_from_three_bytes(hi, mid, lo)
    return int(hi, 16), int(mid, 16), int(lo, 16), canonical


# ---------------------------------------------------------------------------
# DID length table for walking a 19 04 snapshot record
# ---------------------------------------------------------------------------

#: DIDs whose length ISO 14229-1 itself fixes, independent of any ECU.
_STANDARD_FIXED_LENGTHS: dict[int, int] = {
    0xF190: 17,  # VIN: ISO 14229-1 Annex C fixes this at 17 ASCII characters
    0xF186: 1,   # ActiveDiagnosticSessionDataIdentifier: fixed 1-byte enum
}

#: A single isolated uppercase letter -- not part of a longer word such as
#: "SIGNED" -- the way Table C formulas reference snapshot/DID data bytes.
_LETTER_RE = re.compile(r"(?<![A-Za-z])[A-Z](?![A-Za-z])")


def _formula_length(formula: str) -> Optional[int]:
    """Highest byte letter (A=1 byte, B=2, ...) a Table C formula references.

    Only clean algebraic formulas are used -- never ``""`` (unknown/diesel-
    only rows) or ``"multi-field"`` (the BCM 0x1005 composite, whose prose
    name mixes unit letters like "V" with byte letters and cannot be parsed
    without guessing).
    """
    if not formula or formula == "multi-field":
        return None
    letters = _LETTER_RE.findall(formula)
    if not letters:
        return None
    return max(ord(c) - ord("A") for c in letters) + 1


def _did_length(ecu_code: str, did: int) -> Optional[int]:
    if did in _STANDARD_FIXED_LENGTHS:
        return _STANDARD_FIXED_LENGTHS[did]
    spec = next((d for d in DIDS if d.module == ecu_code and d.did == did), None)
    return _formula_length(spec.formula) if spec else None


def _did_name(ecu_code: str, did: int) -> Optional[str]:
    if did in ANNEX_C:
        return ANNEX_C[did]
    spec = next((d for d in DIDS if d.module == ecu_code and d.did == did), None)
    return spec.name if spec else None


# ---------------------------------------------------------------------------
# Pure decoders
# ---------------------------------------------------------------------------


def decode_dtc_count(data: list[str]) -> dict[str, Any]:
    """``59 01 <availabilityMask> <formatId> <countHi> <countLo>``."""
    if len(data) < 6 or data[0] != "59" or data[1] != "01":
        return {"error": "not a 59 01 reply", "raw": data}
    return {
        "availability_mask": int(data[2], 16),
        "format_id": int(data[3], 16),
        "count": (int(data[4], 16) << 8) | int(data[5], 16),
    }


def decode_snapshot_identification(data: list[str]) -> list[dict[str, Any]]:
    """``59 03 (DTC(3) recordNumber(1))*`` -> one entry per (DTC, record)."""
    if len(data) < 2 or data[0] != "59" or data[1] != "03":
        return []
    body = data[2:]
    out: list[dict[str, Any]] = []
    for i in range(0, len(body) - 3, 4):
        h, m, l, rec = body[i], body[i + 1], body[i + 2], body[i + 3]
        out.append({"dtc": dtc_from_three_bytes(h, m, l), "record_number": int(rec, 16)})
    return out


def decode_snapshot_record(data: list[str], ecu_code: str) -> dict[str, Any]:
    """``59 04 DTC(3) status(1) (recordNum(1) numIds(1) (DID(2) data(?))*)*``.

    A DID's data length is not in the frame. Where it is known (see
    ``_did_length``) it is decoded; the first DID with an unknown length
    stops the walk and the remaining bytes from there are returned raw
    under ``undecoded_from`` -- never guessed.
    """
    if len(data) < 6 or data[0] != "59" or data[1] != "04":
        return {"error": "not a 59 04 reply", "raw": data}
    h, m, l, status = data[2], data[3], data[4], data[5]
    status_val = int(status, 16)
    out: dict[str, Any] = {"dtc": dtc_from_three_bytes(h, m, l), "status": status_val,
                           "flags": decode_dtc_status(status_val), "records": []}
    body = data[6:]
    i = 0
    while i < len(body):
        if i + 2 > len(body):
            out["undecoded_from"] = f"trailing byte at offset {i}: {body[i:]}"
            break
        record_number = int(body[i], 16)
        num_ids = int(body[i + 1], 16)
        i += 2
        record: dict[str, Any] = {"record_number": record_number, "identifiers": []}
        out["records"].append(record)
        stopped = False
        for _ in range(num_ids):
            if i + 2 > len(body):
                out["undecoded_from"] = (f"snapshot record {record_number}: truncated DID "
                                         f"at offset {i}: {body[i:]}")
                stopped = True
                break
            did_hex = body[i] + body[i + 1]
            did = int(did_hex, 16)
            length = _did_length(ecu_code, did)
            if length is None:
                out["undecoded_from"] = (f"DID {did_hex} (length unknown); "
                                         f"{len(body) - i} raw byte(s) remain from here: "
                                         f"{body[i:]}")
                stopped = True
                break
            i += 2
            value = body[i:i + length]
            if len(value) < length:
                out["undecoded_from"] = (f"DID {did_hex} claims {length} byte(s) but only "
                                         f"{len(value)} remain: {value}")
                stopped = True
                break
            record["identifiers"].append({"did": did_hex, "name": _did_name(ecu_code, did),
                                          "bytes": value})
            i += length
        if stopped:
            break
    return out


#: ISO 14229-1 Annex D leaves extended-data record numbers manufacturer
#: specific. This is a widely-used AUTOSAR Dem convention (occurrence /
#: aging / aged counters, each one byte) seen across many OEMs -- not
#: confirmed for FCA/Stellantis. See the module docstring for sources.
_EXT_RECORD_GUESSES: dict[int, tuple[str, int]] = {
    0x01: ("occurrence counter: number of times this DTC's test has failed", 1),
    0x02: ("aging counter: operation cycles since the last failure, counting "
           "toward the aging threshold that would clear the DTC", 1),
    0x03: ("aged counter / threshold at which the DTC is considered aged out", 1),
}


def decode_extended_data(data: list[str]) -> dict[str, Any]:
    """``59 06 DTC(3) status(1) (recordNum(1) data(?))*``.

    Record content is manufacturer-specific and its length is not in the
    frame either. Only the well-known counter record numbers above are
    decoded (as a labelled guess); the first unrecognised record number
    stops the walk and the rest is returned raw under ``undecoded_from``.
    """
    if len(data) < 6 or data[0] != "59" or data[1] != "06":
        return {"error": "not a 59 06 reply", "raw": data}
    h, m, l, status = data[2], data[3], data[4], data[5]
    status_val = int(status, 16)
    out: dict[str, Any] = {"dtc": dtc_from_three_bytes(h, m, l), "status": status_val,
                           "flags": decode_dtc_status(status_val), "records": []}
    body = data[6:]
    i = 0
    while i < len(body):
        record_number = int(body[i], 16)
        guess = _EXT_RECORD_GUESSES.get(record_number)
        if guess is None:
            out["undecoded_from"] = (f"record 0x{record_number:02X} (length unknown); "
                                     f"{len(body) - i} raw byte(s) remain: {body[i:]}")
            break
        meaning, length = guess
        value = body[i + 1:i + 1 + length]
        if len(value) < length:
            out["undecoded_from"] = (f"record 0x{record_number:02X} claims {length} byte(s) "
                                     f"but only {len(value)} remain: {value}")
            break
        out["records"].append({"record_number": record_number, "bytes": value,
                               "meaning_guess": meaning, "confidence": "unverified for FCA"})
        i += 1 + length
    return out


# ---------------------------------------------------------------------------
# Session readers
# ---------------------------------------------------------------------------


def _first_positive(r: dict[str, Any]) -> Optional[list[str]]:
    return next(iter(r["positive"].values()), None)


def _out_of_range(r: dict[str, Any]) -> bool:
    return 0x31 in r["nrc"].values()


def dtc_count(sess: Session, ecu: ECUAddress, mask: int = 0xFF) -> dict[str, Any]:
    """``19 01 <mask>``: how many DTCs match ``mask``, without listing them."""
    r = uds.request(sess, ecu, 0x19, bytes([0x01, mask & 0xFF]))
    out: dict[str, Any] = {"ecu": ecu.code, "mask": f"{mask:02X}", "error": r["error"],
                           "nrc": r["nrc_text"] or None}
    data = _first_positive(r)
    if data:
        out.update(decode_dtc_count(data))
    elif not r["error"] and not r["nrc"]:
        out["warning"] = "no answer"
    return out


def dtc_snapshot(sess: Session, ecu: ECUAddress, dtc: str, record: int = 0xFF) -> dict[str, Any]:
    """``19 04``: freeze-frame-style snapshot data captured with this DTC."""
    hi, mid, lo, canonical = _dtc_bytes(dtc)
    r = uds.request(sess, ecu, 0x19, bytes([0x04, hi, mid, lo, record & 0xFF]))
    out: dict[str, Any] = {"ecu": ecu.code, "dtc": canonical, "record": f"{record:02X}",
                           "error": r["error"], "nrc": r["nrc_text"] or None}
    if _out_of_range(r):
        out["note"] = "requestOutOfRange (NRC 0x31): no snapshot record stored for this DTC"
        return out
    data = _first_positive(r)
    if data:
        out.update(decode_snapshot_record(data, ecu.code))
    elif not r["error"] and not r["nrc"]:
        out["warning"] = "no answer"
    return out


def dtc_extended(sess: Session, ecu: ECUAddress, dtc: str, record: int = 0xFF) -> dict[str, Any]:
    """``19 06``: manufacturer-specific extended data (counters etc.) for this DTC."""
    hi, mid, lo, canonical = _dtc_bytes(dtc)
    r = uds.request(sess, ecu, 0x19, bytes([0x06, hi, mid, lo, record & 0xFF]))
    out: dict[str, Any] = {"ecu": ecu.code, "dtc": canonical, "record": f"{record:02X}",
                           "error": r["error"], "nrc": r["nrc_text"] or None}
    if _out_of_range(r):
        out["note"] = "requestOutOfRange (NRC 0x31): no extended data stored for this DTC"
        return out
    data = _first_positive(r)
    if data:
        out.update(decode_extended_data(data))
    elif not r["error"] and not r["nrc"]:
        out["warning"] = "no answer"
    return out


def dtc_detail(sess: Session, ecu: ECUAddress, dtc: str) -> dict[str, Any]:
    """Status (from ``19 02``, falling back to the ``19 04``/``19 06`` status
    byte) plus snapshot plus extended data, for one DTC."""
    _, _, _, canonical = _dtc_bytes(dtc)
    out: dict[str, Any] = {"ecu": ecu.code, "dtc": canonical}

    listing = uds.read_dtcs(sess, ecu)
    if not listing.get("error"):
        rec = next((r for r in listing.get("dtcs", []) if r["code"] == canonical), None)
        if rec:
            out["status"] = rec["status"]
            out["flags"] = rec["flags"]
            out["status_source"] = "19 02"

    snapshot = dtc_snapshot(sess, ecu, canonical)
    extended = dtc_extended(sess, ecu, canonical)
    out["snapshot"] = snapshot
    out["extended"] = extended

    if "status" not in out:
        for src, sub in ((snapshot, "04"), (extended, "06")):
            if isinstance(src.get("status"), int):
                out["status"] = src["status"]
                out["flags"] = src.get("flags") or decode_dtc_status(src["status"])
                out["status_source"] = f"19 {sub} status byte"
                break
    return out


__all__ = [
    "dtc_to_bytes", "decode_dtc_count", "decode_snapshot_identification",
    "decode_snapshot_record", "decode_extended_data", "dtc_count", "dtc_snapshot",
    "dtc_extended", "dtc_detail",
]
