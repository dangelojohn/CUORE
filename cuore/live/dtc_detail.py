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

For the two ECUs whose live records have been read on this car (ECM = Magneti
Marelli 10JA, BCM = Marelli 949; 2026-10-13 and 2026-10-19), the *snapshot*
DID lengths are known empirically and live in ``_SNAPSHOT_LAYOUTS`` below.
They are NOT the Table C live-read lengths (e.g. snapshot 0x1003 coolant is
1 byte, Table C says 2). Derivation: the three ECM records (P0455, P0456,
P0440) have identical length and identical DID bytes at identical offsets,
only the values differ, so the layout is the unique tokenisation whose DID
positions are constant across all three and which also parses the BCM record
to its last byte. Names/scales are attached only where a value is anchored to
a MultiEcuScan freeze-frame decode (FESLog_2609252002, SCAN/FES 2026-10-04:
operating time, startups, odometer, fuel %, oil/coolant/air temperature,
spark advance in 1/16 deg, UniAir mode) or is physically consistent across
the three records (engine-off P0456: 0 rpm, 12.3 V, manifold at ambient).
Everything else is returned as raw bytes with ``name=None``. Each identifier
carries ``confidence`` ("high" = anchored to MES numbers, "medium" =
physically consistent plus a source, "low" = identity or scale plausible
only, "unknown") and ``basis``. For an ECU with a layout, a DID missing from
it stops the walk exactly like before (Table C lengths are not trusted there).

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
from dataclasses import dataclass
from typing import Any, Optional

from . import snapshot_bindings as _sb
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
# Empirical 19 04 snapshot layouts (ECM 10JA, BCM 949) -- see module docstring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SnapField:
    """One snapshot DID: byte length, and (only when earned) name + scaling.

    ``value = raw * mul / div + offset`` (``raw`` big-endian, optionally
    signed). ``div=None`` with a name means "identified, scale unverified":
    the value is withheld rather than guessed. ``enum`` maps raw -> label.
    """
    length: int
    name: Optional[str] = None
    unit: Optional[str] = None
    mul: int = 1
    div: Optional[int] = 1
    offset: float = 0
    signed: bool = False
    enum: Optional[dict[int, str]] = None
    confidence: str = "unknown"
    basis: str = ""
    #: A decoded value above this is physically impossible -> reported as invalid (value withheld),
    #: not as a reading. Used where the decoding is unsigned but the quantity can be negative.
    max_plausible: Optional[float] = None
    invalid_note: str = ""


def _U(length: int) -> _SnapField:
    """Unknown field: length proven by the layout, meaning not."""
    return _SnapField(length)


_BOOST_NOTE = ("unsigned mbar; 195A = ABSOLUTE boost pressure, 1956 = atmospheric; confirmed against MultiEcuScan "
               "(atmospheric 990 mbar / boost 988 mbar) and raw bytes in audit.jsonl, 2026-10-25")

_ECM_SNAPSHOT: dict[int, _SnapField] = {
    0x1008: _SnapField(4, "Operating time", "min", confidence="high",
                       basis="MES 'Operating time': monotonic with startups at ~29 min/startup "
                             "(MES 296066 min @ startup 14532 on 2026-10-04; 31 min/startup in Sept)"),
    0x1009: _U(2),
    0x200A: _SnapField(2, "Startups counter", None, confidence="high",
                       basis="MES 'Startups counter' (14532 on 2026-10-04); record order matches"),
    0x6082: _U(1),   # constant 60 82 00 in every record; could instead be part of 200A's value
    0x1921: _U(9),   # flag bytes: 40 00 01 .. / 04 00 00 .. (P0456)
    0x1000: _SnapField(2, "Engine RPM", "rpm", div=4, confidence="medium",
                       basis="Table C /4; 764 rpm at warm idle, 0 in the engine-off P0456"),
    0x1924: _U(1),
    0x1802: _U(2),
    0x1002: _SnapField(2, "Vehicle speed", "km/h", div=124, confidence="medium",
                       basis="Table C /124 (/128 would read 3% lower); 0 at idle, 12 km/h in gear 3 "
                             "at 921 rpm"),
    0x192D: _SnapField(1, "Current engaged gear", None, confidence="medium",
                       basis="Table C; 3 at 12 km/h, 0 at idle in P/N and engine-off (MES shows N)"),
    0x2001: _SnapField(3, "Odometer", "km", div=10, confidence="medium",
                       basis="0.1 km units; monotonic with startups; MES odometer was 142289.9 km "
                             "@ startup 14457, +4.4k km by 14603 (204 km / 215 min between P0455 and P0456)"),
    0x1812: _SnapField(2, "Spark advance", "deg", div=16, signed=True, confidence="low",
                       basis="MES spark advance is an exact multiple of 1/16 deg; 0 engine-off, "
                             "3.75 at idle; identity from three points only"),
    0x1003: _SnapField(1, "Coolant temperature", "degC", offset=-40, confidence="medium",
                       basis="A-40; cold record 17 = air 16 = oil 17; warm records above oil (MES pattern)"),
    0x1004: _SnapField(2, "Battery voltage", "V", div=10, confidence="medium",
                       basis="/10; 14.3/14.2 V running, 12.3 V engine-off (MES shows 14.3 V running)"),
    0x1937: _SnapField(2, "Intake manifold pressure", "mbar", confidence="medium",
                       basis="969 engine-off = ambient; 316-371 at idle/decel; airflow tracks rpm x this"),
    0x1923: _U(1),
    0x191E: _U(2),
    0x182F: _SnapField(2, "Air flow rate", None, div=None, confidence="low",
                       basis="tracks rpm x manifold pressure within 3% and is 0 engine-off; "
                             "kg/h scale not verified (raw/10 would give 13.4 and 9.2)"),
    0x1935: _SnapField(1, "Intake air temperature", "degC", offset=-40, confidence="medium",
                       basis="A-40; cold-soak record 16 degC ~ coolant 17 (MES air temp pattern)"),
    0x195A: _SnapField(2, "Boost pressure (absolute)", "mbar", confidence="high", basis=_BOOST_NOTE),
    0x1821: _U(1),
    0x1818: _U(1),
    0x1956: _SnapField(2, "Atmospheric pressure", "mbar", confidence="high", basis=_BOOST_NOTE),
    0x1302: _SnapField(2, "Engine oil temperature", "degC", confidence="medium",
                       basis="direct degC; oil < coolant warming up, = coolant cold (MES 63/51, 60/46, 15/15)",
                       max_plausible=200,
                       invalid_note="decoded unsigned: a sub-zero oil temperature would wrap to ~65000 degC, "
                                    "so the sign handling is UNCONFIRMED"),
    0x1B0D: _U(8),   # flag bytes (pedals/switches/status) -- bit meaning not derived
    0x19BD: _SnapField(1, "IBS state of charge", "%", confidence="medium",
                       basis="Table C; 100 % on the cold-start P0456 as in MES (63/81/100)"),
    0x1B03: _U(1),
    0x198C: _SnapField(1, "UniAir actuation mode", None, confidence="low",
                       enum={0x20: "Hybrid", 0x01: "Late opening"},
                       basis="0x20,0x20,0x01 mirrors MES Hybrid,Hybrid,Late opening (cold start)"),
    0x19BE: _U(4),
    0x1928: _U(1),
    0x1001: _SnapField(1, "Fuel level", "%", mul=100, div=255, confidence="medium",
                       basis="MES fuel % is n*100/255; falls 91.8 -> 62.7 -> 55.7 % over the three "
                             "records in time order = 8 L/100 km over the 204 km between P0455 and P0456"),
    0x3701: _U(1),
}

_BCM_SNAPSHOT: dict[int, _SnapField] = {
    0x1008: _SnapField(4, "Operating time", "min", confidence="medium",
                       basis="BCM's own counter, minutes; 245380 on 2026-10-13, 245986 on 2026-10-19"),
    0x1009: _U(2),
    0x200A: _SnapField(2, "Startups counter", None, confidence="high",
                       basis="14583 on 2026-10-13, 14616 now, in step with the ECM's 14603-14612"),
    0x6082: _U(1),
    0x1921: _U(9),   # the same 9-byte flag block as the ECM; reading it as 12 B also parses
    0x1002: _U(1),
    0x1004: _U(2),
    0x3700: _U(1),
}

#: Per ECU code: the proven snapshot DID lengths. Absent ECU -> Table C fallback.
_SNAPSHOT_LAYOUTS: dict[str, dict[int, _SnapField]] = {
    "ECM": _ECM_SNAPSHOT,
    "BCM": _BCM_SNAPSHOT,
}


def _snapshot_value(field: _SnapField, value: list[str]) -> Any:
    raw = int("".join(value), 16)
    if field.enum is not None:
        return field.enum.get(raw)
    if field.div is None:
        return None
    if field.signed and raw >= 1 << (8 * len(value) - 1):
        raw -= 1 << (8 * len(value))
    out = raw * field.mul / field.div + field.offset
    return int(out) if out == int(out) else round(out, 2)


def _snapshot_identifier(ecu_code: str, did: int, did_hex: str, value: list[str],
                         field: Optional[_SnapField]) -> dict[str, Any]:
    """``{did, name|None, bytes, value|None, unit|None, confidence[, basis]}``."""
    if field is None or field.name is None:
        name = None if field is not None else _did_name(ecu_code, did)
        return {"did": did_hex, "name": name, "bytes": value, "value": None, "unit": None,
                "confidence": "low" if name else "unknown"}
    out: dict[str, Any] = {"did": did_hex, "name": field.name, "bytes": value,
                           "value": _snapshot_value(field, value),
                           "unit": field.unit if field.div is not None else None,
                           "confidence": field.confidence}
    if field.basis:
        out["basis"] = field.basis
    if (field.max_plausible is not None and isinstance(out["value"], (int, float))
            and out["value"] > field.max_plausible):
        out["invalid_reason"] = (f"{out['value']:g} {field.unit or ''} is not a possible value (over "
                                 f"{field.max_plausible:g}); {field.invalid_note}. Raw bytes kept.").replace("  ", " ")
        out["value"] = None
        out["confidence"] = "unconfirmed"
    return out


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


def _bound_identifier(did_hex: str, value: list[str], b: dict[str, Any]) -> dict[str, Any]:
    """Identifier for a DID the owner bound (``snapshot_bindings``). The value is
    decoded only when the owner supplied a divisor; otherwise raw bytes only."""
    div = b.get("div")
    field = _SnapField(len(value), b["name"], b.get("unit"), mul=b.get("mul") or 1, div=div,
                       offset=b.get("offset") or 0)
    return {"did": did_hex, "name": b["name"], "bytes": value,
            "value": _snapshot_value(field, value) if div else None,
            "unit": b.get("unit") if div else None,
            "confidence": "owner-bound", "status": _sb.BOUND_STATUS}


def decode_snapshot_record(data: list[str], ecu_code: str, vin: Optional[str] = None) -> dict[str, Any]:
    """``59 04 DTC(3) status(1) (recordNum(1) numIds(1) (DID(2) data(?))*)*``.

    A DID's data length is not in the frame. Where it is known (the ECM/BCM
    ``_SNAPSHOT_LAYOUTS``, else ``_did_length``) it is decoded; the first DID
    with an unknown length stops the walk and the remaining bytes from there
    are returned raw under ``undecoded_from`` -- never guessed. Each
    identifier is ``{did, name|None, bytes, value|None, unit|None,
    confidence[, basis]}``; ``bytes`` is always the raw value.

    ``vin`` (optional) selects the owner bindings in snapshot_bindings.json. For
    a module with a scaffold (ABS) the result also carries ``candidate_fields``
    (names still unbound), ``unresolved_did`` (the DID that stopped the walk) and
    ``proposals`` (suggestions by length and range, status "proposed").
    """
    if len(data) < 6 or data[0] != "59" or data[1] != "04":
        return {"error": "not a 59 04 reply", "raw": data}
    bind_map = _sb.bindings_for(vin, ecu_code)
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
            layout = _SNAPSHOT_LAYOUTS.get(ecu_code)
            field = layout.get(did) if layout is not None else None
            bound = bind_map.get(did)
            if layout is None:
                length = (bound or {}).get("length") or _did_length(ecu_code, did)
            else:
                length = field.length if field else _STANDARD_FIXED_LENGTHS.get(did)
                if not (bound and field is not None and field.name is None):
                    bound = None
            if length is None:
                out["unresolved_did"] = did_hex
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
            record["identifiers"].append(_bound_identifier(did_hex, value, bound) if bound
                                         else _snapshot_identifier(ecu_code, did, did_hex, value, field))
            i += length
        if stopped:
            break
    if _sb.has_scaffold(ecu_code):
        out["candidate_fields"] = _sb.unbound_names(ecu_code, vin)
        out["scaffold_status"] = ("unbound: names from MES FESLog_2609042001 only; no DID, length or "
                                  "scale is known until the owner binds them")
        idents = [x for r in out["records"] for x in r["identifiers"]]
        out["proposals"] = _sb.propose(ecu_code, idents, vin)
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
        out.update(decode_snapshot_record(data, ecu.code, getattr(sess.link, "vin", None) or None))
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
