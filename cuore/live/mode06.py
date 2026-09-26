"""OBD-II Mode $06 (on-board monitoring test results), CAN format per
ISO 15031-5 / SAE J1979.

Pure decoders plus one session-level reader, mirroring the split in
:mod:`obd.py` (pure) and :mod:`ops.py` (wiring). Reuses
:func:`obd.decode_supported_pids` for the supported-MID bitmaps: the 32-bit
"is this ID supported / is the next block supported" convention Mode 01 uses
for PIDs is the same one Mode 06 uses for OBDMIDs.

Record layout (SAE J1979 / ISO 15031-5, CAN): ``46`` then repeating 9-byte
records OBDMID(1) TID(1) UASID(1) value(2) min(2) max(2); every record
carries its own OBDMID. Not yet checked against a live reply from this car.

Unit-and-Scaling ID (UASID) table: only entries this module's author is
actually confident about are filled in; scaling formulas for the rest of
ISO 15031-5 Table E.1 were not reliably recalled, so per the "return raw
rather than guess" instruction they resolve to ``{"scaling": "unknown"}``
with the raw integer preserved. See the module docstring section below the
table for exactly what is and is not covered.
"""

from __future__ import annotations

from typing import Any, Optional

from .framing import negative_responses, no_data
from .obd import decode_supported_pids

# --- OBDMID names (SAE J1979 Appendix D / ISO 15031-5) ----------------------
#
# Filled in for the ranges the request called out explicitly. Anything not in
# this table returns None from :func:`obdmid_name` -- never a guessed name.

OBDMID_NAMES: dict[str, str] = {
    # O2 sensor monitors: bank 1-4, sensor 1-4 (Appendix D groups these as
    # 16 consecutive MIDs; bank/sensor split below is the conventional one,
    # not independently verified against the standard's exact wording).
    "01": "O2 sensor monitor bank 1 sensor 1",
    "02": "O2 sensor monitor bank 1 sensor 2",
    "03": "O2 sensor monitor bank 1 sensor 3",
    "04": "O2 sensor monitor bank 1 sensor 4",
    "05": "O2 sensor monitor bank 2 sensor 1",
    "06": "O2 sensor monitor bank 2 sensor 2",
    "07": "O2 sensor monitor bank 2 sensor 3",
    "08": "O2 sensor monitor bank 2 sensor 4",
    "09": "O2 sensor monitor bank 3 sensor 1",
    "0A": "O2 sensor monitor bank 3 sensor 2",
    "0B": "O2 sensor monitor bank 3 sensor 3",
    "0C": "O2 sensor monitor bank 3 sensor 4",
    "0D": "O2 sensor monitor bank 4 sensor 1",
    "0E": "O2 sensor monitor bank 4 sensor 2",
    "0F": "O2 sensor monitor bank 4 sensor 3",
    "10": "O2 sensor monitor bank 4 sensor 4",
    # Catalyst monitor, bank 1-4.
    "21": "Catalyst monitor bank 1",
    "22": "Catalyst monitor bank 2",
    "23": "Catalyst monitor bank 3",
    "24": "Catalyst monitor bank 4",
    # EGR monitor, bank 1-4.
    "31": "EGR monitor bank 1",
    "32": "EGR monitor bank 2",
    "33": "EGR monitor bank 3",
    "34": "EGR monitor bank 4",
    # VVT monitor, bank 1-4.
    "35": "VVT monitor bank 1",
    "36": "VVT monitor bank 2",
    "37": "VVT monitor bank 3",
    "38": "VVT monitor bank 4",
    # EVAP monitors.
    "39": "EVAP monitor (cap off / gross leak)",
    "3A": 'EVAP monitor 0.090" leak',
    "3B": 'EVAP monitor 0.040" leak',
    "3C": 'EVAP monitor 0.020" leak',
    "3D": "EVAP purge flow monitor",
    # Misfire monitors: 0xA1 is the general/summary data, 0xA2-0xAD are
    # cylinders 1-12.
    "A1": "Misfire monitor general data",
    "A2": "Misfire monitor cylinder 1",
    "A3": "Misfire monitor cylinder 2",
    "A4": "Misfire monitor cylinder 3",
    "A5": "Misfire monitor cylinder 4",
    "A6": "Misfire monitor cylinder 5",
    "A7": "Misfire monitor cylinder 6",
    "A8": "Misfire monitor cylinder 7",
    "A9": "Misfire monitor cylinder 8",
    "AA": "Misfire monitor cylinder 9",
    "AB": "Misfire monitor cylinder 10",
    "AC": "Misfire monitor cylinder 11",
    "AD": "Misfire monitor cylinder 12",
}

#: EVAP OBDMIDs in the order the request lists them.
EVAP_MIDS: tuple[str, ...] = ("39", "3A", "3B", "3C", "3D")


def obdmid_name(mid: str) -> Optional[str]:
    return OBDMID_NAMES.get(mid.upper())


# --- Unit-and-Scaling ID table -----------------------------------------------
#
# (unit, per-count multiplier) for the base (unsigned, 0x00-0x7F) IDs this
# module is confident about. A UASID with bit 0x80 set is the signed mirror
# of (uasid & 0x7F): same unit and multiplier, but the raw 16-bit field is
# two's-complement rather than unsigned -- that halving of the ID space is a
# structural fact of the table, independent of which individual entries are
# known here.
_UASID_TABLE: dict[int, tuple[str, float]] = {
    0x01: ("raw", 1.0),      # raw count / no scaling
    0x0A: ("mV", 0.122),     # voltage, 0.122 mV per count
    0x10: ("ms", 1.0),       # time, 1 ms per count
    0x24: ("count", 1.0),    # counter, 1 per count
}
#: UASIDs the request flagged but this module could not pin down confidently
#: enough to scale (kept out of _UASID_TABLE deliberately -- see decode_uasid).
UNCERTAIN_UASIDS: tuple[str, ...] = ("0B", "14", "FD", "FE")


def _twos_complement16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def decode_uasid(uasid_hex: str, raw: int) -> dict[str, Any]:
    """Scale one raw 16-bit Mode 06 field per its Unit-and-Scaling ID.

    Returns ``{"unit": ..., "value": ..., "scaling": "known"|"unknown"}``.
    Falls back to the untouched raw integer with ``"scaling": "unknown"``
    whenever the UASID (or its unsigned base, for a signed one) is not in
    ``_UASID_TABLE`` -- deliberately, rather than guessing a formula.
    """
    try:
        uid = int(uasid_hex, 16)
    except (TypeError, ValueError):
        return {"unit": None, "value": raw, "scaling": "unknown"}
    signed = bool(uid & 0x80)
    base = uid & 0x7F
    entry = _UASID_TABLE.get(base)
    if entry is None:
        return {"unit": None, "value": raw, "scaling": "unknown"}
    unit, scale = entry
    value = _twos_complement16(raw) if signed else raw
    scaled = value * scale
    return {"unit": unit, "value": round(scaled, 6) if scale != 1.0 else int(scaled),
            "scaling": "known"}


def decode_supported_mid_bitmap(base: str, data: list[str]) -> tuple[list[str], bool]:
    """Supported OBDMIDs from a ``46 <base> A B C D`` bitmap, and whether the
    next block is supported. Delegates to :func:`obd.decode_supported_pids`:
    the bit convention (MSB = base+1, LSB of the last byte = "next block
    supported") is identical to Mode 01's supported-PID bitmaps.
    """
    return decode_supported_pids(base, data)


# --- test-result records -----------------------------------------------------

#: SAE J1979 / ISO 15031-5 CAN format: the Mode $06 response is ``46`` followed
#: by repeating 9-byte records, each carrying its own OBDMID:
#: OBDMID(1) TID(1) UASID(1) value(2) min(2) max(2). An 8-byte stride (no
#: MID per record) misreads every record after the first.
_RECORD_LEN = 9


def _u16(hi: str, lo: str) -> int:
    return (int(hi, 16) << 8) | int(lo, 16)


def decode_mode06_records(mid: str, payload: list[str]) -> list[dict[str, Any]]:
    """Decode the repeating test-result records of one Mode $06 reply.

    ``payload`` is the byte list following ``46 <mid>`` (``data[2:]``), so
    the first record's OBDMID has already been consumed as the echo; it is
    put back and every record (9 bytes, own OBDMID) is read the same way.
    Records whose OBDMID differs from the requested one are still decoded
    under their own MID. Trailing bytes that do not fill a record are
    ignored rather than raising.
    """
    full = [mid.upper()] + [b.upper() for b in payload]
    out: list[dict[str, Any]] = []
    for i in range(0, len(full) - _RECORD_LEN + 1, _RECORD_LEN):
        rmid, tid, uasid = full[i], full[i + 1], full[i + 2]
        raw_value = _u16(full[i + 3], full[i + 4])
        raw_min = _u16(full[i + 5], full[i + 6])
        raw_max = _u16(full[i + 7], full[i + 8])
        dv = decode_uasid(uasid, raw_value)
        dmin = decode_uasid(uasid, raw_min)
        dmax = decode_uasid(uasid, raw_max)
        value, vmin, vmax = dv["value"], dmin["value"], dmax["value"]
        passed = vmin <= value <= vmax
        out.append({
            "mid": rmid, "mid_name": obdmid_name(rmid), "tid": tid, "uasid": uasid,
            "unit": dv["unit"], "value": value, "min": vmin, "max": vmax,
            "passed": passed,
            "raw": {"value": raw_value, "min": raw_min, "max": raw_max,
                    "scaling": dv["scaling"]},
        })
    return out


def evap_summary(read_result: dict[str, Any]) -> list[str]:
    """Plain-English sentences for the EVAP OBDMIDs (0x39-0x3D) in a
    :func:`read_mode06` result. The sentence compares the test value against
    the MAX limit -- these are upper-bound leak/flow thresholds -- even
    though ``passed`` itself uses the full min<=value<=max range.
    """
    results = read_result.get("results") or {}
    lines: list[str] = []
    for mid in EVAP_MIDS:
        name = obdmid_name(mid) or f"MID {mid}"
        entry = results.get(mid) or {}
        by_ecu = entry.get("by_ecu") or {}
        records = [r for recs in by_ecu.values() for r in recs]
        if not records:
            lines.append(f"{name}: not supported by this ECU")
            continue
        for r in records:
            verdict = "PASS" if r["passed"] else "FAIL"
            unit = r.get("unit")
            suffix = f" {unit}" if unit and unit not in ("raw",) else ""
            lines.append(f"{name}: value {r['value']}{suffix} vs limit {r['max']}{suffix} "
                        f"-> {verdict}")
    return lines


# --- session reader -----------------------------------------------------------

_SUPPORTED_BASES = ("00", "20", "40", "60", "80", "A0", "C0", "E0")


def _negative_lines(all_ecus: dict[str, list[str]]) -> dict[str, str]:
    from .uds import NRC_TEXT  # local: keep this module free of the UDS client import
    codes = negative_responses(all_ecus, "06")
    return {hdr: f"NRC 0x{code} ({NRC_TEXT.get(int(code, 16), 'unknown')})"
            for hdr, code in codes.items()}


def read_mode06(sess: Any, mids: Optional[list[str]] = None) -> dict[str, Any]:
    """Mode 06 discovery + test results. Never raises on NO DATA or a
    negative response (0x7F 06 xx = the MID is not supported) -- both are
    recorded in the result instead.

    With ``mids=None``, discovers supported OBDMIDs per ECU first (``06 00``,
    ``06 20``, ... while the previous bitmap's last bit says the next range
    is supported) and reads every MID any ECU reported as supported. Passing
    ``mids`` skips discovery and reads exactly those MIDs.
    """
    sess.untarget()
    out: dict[str, Any] = {"raw": {}, "supported": {}, "results": {}}
    if mids is None:
        discovered: dict[str, list[str]] = {}
        for base in _SUPPORTED_BASES:
            q = sess.query(f"06{base}", "46")
            out["raw"][f"supported_{base}"] = q["raw"]
            if q["error"]:
                out.setdefault("errors", {})[base] = q["error"]
                break
            any_next = False
            for hdr, data in q["ecus"].items():
                if len(data) < 6 or data[1] != base:
                    continue
                supported, more = decode_supported_mid_bitmap(base, data[2:6])
                discovered.setdefault(hdr, []).extend(supported)
                any_next = any_next or more
            if not any_next:
                break
        out["supported"] = discovered
        mids = sorted({m for lst in discovered.values() for m in lst})
    else:
        mids = [m.upper() for m in mids]
        out["supported"] = {"requested": list(mids)}
    for mid in mids:
        q = sess.query(f"06{mid}", "46")
        out["raw"][mid] = q["raw"]
        entry: dict[str, Any] = {}
        if q["error"]:
            entry["error"] = f"ADAPTER/BUS ERROR: {q['error']}; the read did not complete"
            out["results"][mid] = entry
            continue
        by_ecu: dict[str, list[dict[str, Any]]] = {}
        for hdr, data in q["ecus"].items():
            if len(data) < 2 or data[1] != mid:
                continue
            recs = decode_mode06_records(mid, data[2:])
            if recs:
                by_ecu[hdr] = recs
        neg = _negative_lines(q["all_ecus"])
        if neg:
            entry["negative"] = neg
        if by_ecu:
            entry["by_ecu"] = by_ecu
        elif not neg:
            entry["warning"] = "NO DATA" if no_data(q["raw"]) else "no ECU answered this MID"
        out["results"][mid] = entry
    return out


__all__ = [
    "OBDMID_NAMES", "EVAP_MIDS", "obdmid_name", "UNCERTAIN_UASIDS", "decode_uasid",
    "decode_supported_mid_bitmap", "decode_mode06_records", "evap_summary", "read_mode06",
]
