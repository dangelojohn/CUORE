"""Read-only UDS over a :class:`Session`: identity, DTCs, DIDs, discovery.

Everything here goes through :func:`request`, which refuses any service not on
the read-only allowlist before a byte leaves the adapter. DTCs come back in
the MES vocabulary (``P0456-00``) so live codes join the corpus.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from . import audit, store
from .addressing import ANNEX_C, DIDS, ECUAddress, Confidence, address_pair, by_code, on_bus, sweep_candidates
from .buses import Bus
from .obd import decode_uds_dtc_block
from .safety import assert_read_only_uds
from .transport import DEFAULT_TIMEOUT, Session

NRC_TEXT: dict[int, str] = {
    0x10: "generalReject", 0x11: "serviceNotSupported", 0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat", 0x14: "responseTooLong",
    0x21: "busyRepeatRequest", 0x22: "conditionsNotCorrect", 0x24: "requestSequenceError",
    0x31: "requestOutOfRange", 0x33: "securityAccessDenied", 0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts", 0x37: "requiredTimeDelayNotExpired",
    0x78: "requestCorrectlyReceived-ResponsePending", 0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}


def nrc_text(code: int) -> str:
    return NRC_TEXT.get(code, f"NRC 0x{code:02X}")


def request(sess: Session, ecu: ECUAddress, service: int, payload: bytes = b"",
            timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    assert_read_only_uds(service, payload)
    r = sess.uds(ecu, service, payload, timeout)
    r["nrc_text"] = {h: nrc_text(c) for h, c in r["nrc"].items()}
    return r


def _first_positive(r: dict[str, Any]) -> Optional[list[str]]:
    return next(iter(r["positive"].values()), None)


def read_did(sess: Session, ecu: ECUAddress, did: int, timeout: float = DEFAULT_TIMEOUT
             ) -> dict[str, Any]:
    r = request(sess, ecu, 0x22, did.to_bytes(2, "big"), timeout)
    out: dict[str, Any] = {"ecu": ecu.code, "bus": sess.bus.key, "did": f"{did:04X}",
                           "name": ANNEX_C.get(did), "error": r["error"], "nrc": r["nrc_text"] or None}
    spec = next((d for d in DIDS if d.module == ecu.code and d.did == did), None)
    if spec:
        out["name"] = spec.name
        out["formula"] = spec.formula
        out["unit"] = spec.unit
        out["confidence"] = spec.confidence
    data = _first_positive(r)
    if data and len(data) >= 3 and data[1] + data[2] == f"{did:04X}":
        payload = data[3:]
        out["bytes"] = payload
        if did == 0xF190 or all(32 <= int(b, 16) < 127 for b in payload) and len(payload) >= 4:
            out["ascii"] = "".join(chr(int(b, 16)) for b in payload if 32 <= int(b, 16) < 127)
    elif not r["error"] and not r["nrc"]:
        out["warning"] = "no answer"
    return out


def identity(sess: Session, ecu: ECUAddress) -> dict[str, Any]:
    """The Annex C identity set every module should answer."""
    out: dict[str, Any] = {"ecu": ecu.code, "bus": sess.bus.key, "fields": {}}
    for did in (0xF190, 0xF187, 0xF188, 0xF189, 0xF18C, 0xF191, 0xF192, 0xF194, 0xF195):
        r = read_did(sess, ecu, did, 2.5)
        if r.get("error"):
            out["error"] = r["error"]
            break
        out["fields"][f"{did:04X}"] = {"name": ANNEX_C.get(did), "ascii": r.get("ascii"),
                                       "bytes": r.get("bytes"), "nrc": r.get("nrc")}
    return out


def read_dtcs(sess: Session, ecu: ECUAddress, mask: int = 0xFF,
              timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    r = request(sess, ecu, 0x19, bytes([0x02, mask]), timeout)
    out: dict[str, Any] = {"ecu": ecu.code, "bus": sess.bus.key, "mask": f"{mask:02X}",
                           "error": r["error"], "nrc": r["nrc_text"] or None, "dtcs": []}
    data = _first_positive(r)
    if data:
        records = decode_uds_dtc_block(data)
        out["dtcs"] = records
        out["codes"] = [rec["code"] for rec in records]
        out["availability_mask"] = data[2] if len(data) > 2 else None
    elif r["error"]:
        out["note"] = "ADAPTER/BUS ERROR; this is not 'no codes'"
    elif not r["nrc"]:
        out["warning"] = "no answer from the module"
    return out


def tester_present(sess: Session, ecu: ECUAddress) -> dict[str, Any]:
    r = request(sess, ecu, 0x3E, b"\x80", 1.5)
    return {"ecu": ecu.code, "sent": True, "error": r["error"]}


def scan_bus(sess: Session, bus: Bus, vin: Optional[str] = None,
             mask: int = 0xFF) -> dict[str, Any]:
    """``0x19 02`` on every usable module of the bus, in registry order."""
    results = []
    for ecu in on_bus(bus.key):
        target = _effective_target(ecu, vin)
        if target is None:
            results.append({"ecu": ecu.code, "skipped": "no confirmed address"})
            continue
        eff = _with_target(ecu, target)
        results.append(read_dtcs(sess, eff, mask))
    audit.record("scan_bus", bus=bus.key, modules=len(results))
    return {"bus": bus.key, "cable": sess.link.cable, "modules": results}


def _effective_target(ecu: ECUAddress, vin: Optional[str]) -> Optional[int]:
    if vin:
        confirmed = store.confirmed_targets(vin).get(ecu.code)
        if confirmed is not None:
            return confirmed
    return ecu.target if ecu.usable else None


def _with_target(ecu: ECUAddress, target: int) -> ECUAddress:
    if ecu.target == target and ecu.confidence == Confidence.CONFIRMED:
        return ecu
    from dataclasses import replace
    return replace(ecu, target=target, confidence=Confidence.CONFIRMED,
                   source=f"{ecu.source}; confirmed on this car")


def resolve_module(code: str, vin: Optional[str] = None) -> ECUAddress:
    from .errors import BadCommand
    ecu = by_code(code.upper())
    if ecu is None:
        raise BadCommand(f"unknown module code {code!r}")
    target = _effective_target(ecu, vin)
    if target is None:
        raise BadCommand(f"module {ecu.code} has no confirmed address on this car; run discovery "
                         f"(confidence {ecu.confidence.value}, target "
                         f"{'unknown' if ecu.target is None else format(ecu.target, '02X')})")
    return _with_target(ecu, target)


def discover(sess: Session, bus: Bus, *, vin_expected: Optional[str] = None,
             candidates: Optional[list[int]] = None, per_target_timeout: float = 0.25,
             stop_after: Optional[int] = None) -> dict[str, Any]:
    """``22 F190`` at every candidate target; a VIN reply is proof of a live node.

    Hits are matched to registry modules by the VIN and, when available, the
    part numbers; confirmed matches are persisted per VIN so the sweep runs
    once. Read-only by construction.
    """
    targets = candidates if candidates is not None else sweep_candidates(bus.key)
    hits: list[dict[str, Any]] = []
    started = time.monotonic()
    tried = 0
    for ta in targets:
        tried += 1
        req_hex, resp_hex = address_pair(ta)
        sess.target_raw(req_hex, resp_hex)
        q = sess.query("22F190", "62", per_target_timeout)
        if q["error"] and q["error"] != "TIMEOUT":
            hits.append({"target": f"{ta:02X}", "error": q["error"]})
            if q["error"] in ("BUS ERROR", "CAN ERROR", "OUT OF MEMORY"):
                break
            continue
        data = next(iter(q["ecus"].values()), None)
        if not data or len(data) < 3 or data[1] + data[2] != "F190":
            continue
        vin = "".join(chr(int(b, 16)) for b in data[3:] if 32 <= int(b, 16) < 127)
        hit: dict[str, Any] = {"target": f"{ta:02X}", "request": req_hex, "response": resp_hex,
                               "vin": vin, "vin_matches": (vin == vin_expected) if vin_expected else None}
        known = [m for m in on_bus(bus.key) if m.target == ta]
        if known:
            hit["registry_match"] = known[0].code
        part = sess.query("22F187", "62", per_target_timeout)
        pdata = next(iter(part["ecus"].values()), None)
        if pdata and len(pdata) > 3:
            hit["spare_part"] = "".join(chr(int(b, 16)) for b in pdata[3:] if 32 <= int(b, 16) < 127)
        hits.append(hit)
        if vin_expected and vin == vin_expected and hit.get("registry_match"):
            store.confirm_target(vin, hit["registry_match"], ta, source="discover")
        if stop_after and len([h for h in hits if "vin" in h]) >= stop_after:
            break
    sess.untarget()
    audit.record("discover", bus=bus.key, tried=tried, hits=len(hits))
    return {"bus": bus.key, "cable": sess.link.cable, "tried": tried,
            "seconds": round(time.monotonic() - started, 1), "hits": hits}


__all__ = ["NRC_TEXT", "nrc_text", "request", "read_did", "identity", "read_dtcs",
           "tester_present", "scan_bus", "resolve_module", "discover"]
