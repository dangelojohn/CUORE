"""OBD-II Mode $09 (vehicle information), SAE J1979 / ISO 15031-5.

Pure decoders plus one session-level reader, same split as :mod:`mode06.py`
(pure decode / wiring) and the same posture as :mod:`obd.py`: never guess a
formula, return the undecoded bytes instead when unsure.

``ops.obd_vin`` already reads and decodes PID 0x02 (VIN) -- that function is
left alone (this module does not touch ``ops.py``). This module covers the
PIDs ops has no decoder for: 0x04 (calibration IDs), 0x06 (calibration
verification numbers), 0x08 (in-use performance tracking -- the EVAP monitor
completion-rate evidence), and 0x0A (ECU name).

Response format (SAE J1979, Mode 09): ``49 <pid> <count> <data...>`` for
0x02/0x04/0x06/0x0A, where ``count`` is the number of data items (messages);
0x08 (IPT) has no leading count byte -- it is a flat stream of 16-bit
counters, source SAE J1979 (CORROBORATED).
"""

from __future__ import annotations

from typing import Any, Optional

from .framing import negative_responses, no_data

RESPONSE_BYTE = "49"


def _ascii(byte_hex: list[str]) -> str:
    """Printable ASCII only; padding (space/NUL) and junk bytes are dropped."""
    return "".join(chr(int(b, 16)) for b in byte_hex if 32 <= int(b, 16) < 127)


def _u16(hi: str, lo: str) -> int:
    return (int(hi, 16) << 8) | int(lo, 16)


# --- PID 0x02 (VIN) -- included for a uniform dispatch table; ops.obd_vin is
# the one other code should actually call for a live VIN read. -------------

def _decode_vin(data: list[str]) -> dict[str, Any]:
    count = int(data[2], 16) if len(data) > 2 else 0
    vin = _ascii(data[3:])
    return {"count": count, "vin": vin, "length_ok": len(vin) == 17}


# --- PID 0x04: calibration ID(s), 16 ASCII bytes per ID ---------------------

def _decode_calibration_ids(data: list[str]) -> dict[str, Any]:
    count = int(data[2], 16) if len(data) > 2 else 0
    payload = data[3:]
    ids = [_ascii(payload[i:i + 16]).strip()
           for i in range(0, min(len(payload), count * 16), 16)]
    return {"count": count, "calibration_ids": ids}


# --- PID 0x06: calibration verification numbers, 4 raw bytes per CVN -------

def _decode_cvns(data: list[str]) -> dict[str, Any]:
    count = int(data[2], 16) if len(data) > 2 else 0
    payload = data[3:]
    cvns = ["".join(payload[i:i + 4]).upper()
            for i in range(0, min(len(payload), count * 4), 4)]
    return {"count": count, "cvns": cvns}


# --- PID 0x0A: ECU name, 20 ASCII bytes (NUL-padded) ------------------------

def _decode_ecu_name(data: list[str]) -> dict[str, Any]:
    count = int(data[2], 16) if len(data) > 2 else 0
    payload = data[3:]
    return {"count": count, "ecu_name": _ascii(payload).strip()}


# --- PID 0x08: in-use performance tracking ----------------------------------
#
# Spark-ignition counter order (SAE J1979 Table, CORROBORATED). This car's
# own readiness decode (obd.decode_readiness) picked the spark monitor table
# (bit 3 of byte B clear), so this is the right layout for it; a
# compression-ignition car has a different monitor list and is not covered
# here -- it would come back under the same raw words with these labels
# wrong, so callers should check decode_readiness's "ignition" field first.

_IPT_MONITORS: tuple[tuple[str, str, str], ...] = (
    ("CAT1", "CATCOMP1", "CATCOND1"), ("CAT2", "CATCOMP2", "CATCOND2"),
    ("O2S1", "O2SCOMP1", "O2SCOND1"), ("O2S2", "O2SCOMP2", "O2SCOND2"),
    ("EGR", "EGRCOMP", "EGRCOND"), ("AIR", "AIRCOMP", "AIRCOND"),
    ("EVAP", "EVAPCOMP", "EVAPCOND"), ("SO2S", "SO2SCOMP", "SO2SCOND"),
)


def _decode_ipt(data: list[str]) -> dict[str, Any]:
    payload = data[2:]  # no count byte: PID 08 is a flat 16-bit-word stream
    words = [_u16(payload[i], payload[i + 1]) for i in range(0, len(payload) - 1, 2)]
    out: dict[str, Any] = {}
    idx = 0
    for name in ("OBDCOND", "IGNCNTR"):
        if idx < len(words):
            out[name] = words[idx]
        idx += 1
    monitors: dict[str, Any] = {}
    for base, num_name, den_name in _IPT_MONITORS:
        if idx + 1 < len(words):
            num, den = words[idx], words[idx + 1]
            monitors[base] = {
                "numerator_name": num_name, "denominator_name": den_name,
                "numerator": num, "denominator": den,
                "completion_rate": round(num / den, 4) if den else None,
            }
        idx += 2
    out["monitors"] = monitors
    return out


_DECODERS = {
    "02": _decode_vin, "04": _decode_calibration_ids, "06": _decode_cvns,
    "08": _decode_ipt, "0A": _decode_ecu_name,
}


def decode_mode09(pid: str, raw_by_ecu: dict[str, list[str]]) -> dict[str, Any]:
    """Decode one Mode 09 PID's positive-response payload, per ECU.

    ``raw_by_ecu`` maps ECU header -> full positive-response byte list
    (starting with ``49``), i.e. exactly what ``Session.query(...)["ecus"]``
    returns after :func:`framing.reassemble` has put a multi-frame reply back
    together. A PID this module has no decoder for comes back unchanged
    under ``"raw"`` rather than guessed. An ECU whose echoed PID does not
    match (wrong/empty frame) is skipped.
    """
    pid = pid.upper()
    decoder = _DECODERS.get(pid)
    out: dict[str, Any] = {}
    for hdr, data in raw_by_ecu.items():
        if len(data) < 2 or data[0] != RESPONSE_BYTE or data[1] != pid:
            continue
        out[hdr] = decoder(data) if decoder else {"raw": data}
    return out


# --- session reader ----------------------------------------------------------

def read_mode09(sess: Any, pids: Optional[list[str]] = None) -> dict[str, Any]:
    """Read and decode a set of Mode 09 PIDs. Never raises on NO DATA or a
    negative response -- both are recorded per PID instead. Defaults to the
    PIDs this module can decode (0x04, 0x06, 0x08, 0x0A); VIN (0x02) is left
    to ``ops.obd_vin``, which also records it onto the session/link.
    """
    sess.untarget()
    pids = [p.upper() for p in pids] if pids else ["04", "06", "08", "0A"]
    out: dict[str, Any] = {"raw": {}, "results": {}}
    for pid in pids:
        q = sess.query(f"09{pid}", RESPONSE_BYTE)
        out["raw"][pid] = q["raw"]
        if q["error"]:
            out["results"][pid] = {"error": f"ADAPTER/BUS ERROR: {q['error']}; "
                                             "the read did not complete"}
            continue
        decoded = decode_mode09(pid, q["ecus"])
        if decoded:
            out["results"][pid] = decoded
            continue
        from .uds import NRC_TEXT  # local: keep this module free of the UDS import
        neg = negative_responses(q["all_ecus"], "09")
        if neg:
            out["results"][pid] = {
                "negative": {hdr: f"NRC 0x{code} ({NRC_TEXT.get(int(code, 16), 'unknown')})"
                             for hdr, code in neg.items()}}
        else:
            out["results"][pid] = {"warning": "NO DATA" if no_data(q["raw"])
                                    else "no ECU answered this PID"}
    return out


__all__ = ["decode_mode09", "read_mode09", "RESPONSE_BYTE"]
