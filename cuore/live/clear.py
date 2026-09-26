"""Per-module DTC clearing (UDS 0x14), with the evidence captured first.

Clearing is the one write the live link performs, and it destroys evidence:
status bytes, snapshots, occurrence counters and the ECU's record of which
tests have run. So a clear here is a procedure, not a command:

1. Refuse unless the operator typed the consent phrase ``CLEAR <MODULE>``,
   the car is stationary, and (on CAN-CH) the per-call confirmation is given.
2. Read everything first: 19 02 FF, plus snapshot and extended data for each
   active code, into ``<state>/clears/<timestamp>_<module>.json`` and the
   observation store (kind ``clear_evidence``).
3. Send ``14 <group>`` (FFFFFF = all groups).
4. Read back and report which codes came straight back: a code that returns
   within seconds of a clear is a live, reproducing fault.

A clear is not a repair. The ECU re-runs its tests over later drive cycles;
use verify_repair to see them run and pass.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from . import audit, store
from .addressing import ECUAddress
from .config import state_dir
from .errors import BadCommand, Refused
from .obd import decode_uds_dtc_block

ACTIVE_MASK = 0x01 | 0x04 | 0x08

CLEAR_NRC = {
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x22: "conditionsNotCorrect (e.g. engine running or vehicle moving)",
    0x31: "requestOutOfRange (group not supported)",
    0x33: "securityAccessDenied (Security Gateway or module lock: needs an authenticated tool)",
    0x72: "generalProgrammingFailure (memory write failed)",
    0x7F: "serviceNotSupportedInActiveSession",
    0x11: "serviceNotSupported",
}


def consent_phrase(module_code: str) -> str:
    return f"CLEAR {module_code.upper()}"


def assert_clear_allowed(module_code: str, consent: str, group: str) -> bytes:
    """The clear gate. Returns the 3-byte group on success."""
    if (consent or "").strip().upper() != consent_phrase(module_code):
        raise Refused(f"clearing {module_code} erases its fault memory; type the consent phrase "
                      f"exactly: {consent_phrase(module_code)!r}")
    g = (group or "FFFFFF").strip().upper()
    if len(g) != 6 or any(c not in "0123456789ABCDEF" for c in g):
        raise BadCommand("group must be 6 hex digits; FFFFFF clears all groups")
    return bytes.fromhex(g)


def _active(records: list[dict[str, Any]]) -> list[str]:
    return sorted(r["code"] for r in records if int(r.get("status") or 0) & ACTIVE_MASK)


def clear_module(sess: Any, ecu: ECUAddress, *, consent: str, vin: str = "",
                 group: str = "FFFFFF", evidence_extra: Optional[dict[str, Any]] = None
                 ) -> dict[str, Any]:
    """Capture evidence, clear one module, read back. ``sess`` must target ``ecu``'s bus."""
    from . import uds as uds_mod
    grp = assert_clear_allowed(ecu.code, consent, group)
    at = datetime.now()
    out: dict[str, Any] = {"module": ecu.code, "bus": sess.bus.key, "group": grp.hex().upper(),
                           "cleared": False}

    # 1. evidence
    before = uds_mod.read_dtcs(sess, ecu)
    if before.get("error"):
        raise Refused(f"could not read {ecu.code}'s codes before clearing ({before['error']}); "
                      f"nothing was cleared")
    records = before.get("dtcs") or []
    active = _active(records)
    details: dict[str, Any] = {}
    try:
        from . import dtc_detail
        for code in active:
            try:
                details[code] = dtc_detail.dtc_detail(sess, ecu, code)
            except Exception as exc:  # noqa: BLE001 -- evidence is best effort per code
                details[code] = {"error": str(exc)}
    except ImportError:
        details = {"note": "dtc_detail not available; status bytes only"}
    evidence = {"captured_at": at.isoformat(timespec="seconds"), "vin": vin, "module": ecu.code,
                "bus": sess.bus.key, "stream": sess.stream.describe, "active": active,
                "records": records, "details": details, **(evidence_extra or {})}
    d = state_dir() / "clears"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{at.strftime('%Y%m%d-%H%M%S')}_{ecu.code}.json"
    path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    store.record_observation("clear_evidence", {"ecu": ecu.code, "active": active,
                                                "tracked": len(records), "file": str(path)},
                             vin=vin, bus=sess.bus.key, cable=sess.link.cable,
                             stream=sess.stream.describe)
    out["evidence_file"] = str(path)
    out["active_before"] = active

    # 2. clear
    r = sess.uds(ecu, 0x14, grp, timeout=6.0)
    nrc = next(iter(r.get("nrc", {}).values()), None)
    acked = any(data and data[0].upper() == "54" for data in r.get("positive", {}).values())
    out["acknowledged"] = acked
    if r.get("error"):
        out["error"] = f"adapter/bus error during clear: {r['error']}"
    if nrc is not None:
        out["refused_by_module"] = f"NRC 0x{nrc:02X}: {CLEAR_NRC.get(nrc, 'unknown')}"
    audit.record("clear_module", module=ecu.code, vin=vin, acknowledged=acked,
                 nrc=None if nrc is None else f"{nrc:02X}", evidence=str(path))

    # 3. read back
    after = uds_mod.read_dtcs(sess, ecu)
    back = _active(after.get("dtcs") or []) if not after.get("error") else None
    out["active_after"] = back
    if acked and back is not None:
        out["cleared"] = True
        returned = sorted(set(back))
        out["returned_immediately"] = returned
        out["reading"] = ("codes back within seconds of the clear are live, reproducing faults: "
                          + ", ".join(returned)) if returned else (
            "no code active right after the clear. That is not a repair: the ECU re-runs its "
            "tests over later drives. Use verify_repair after a few drive cycles.")
    elif after.get("error"):
        out["readback_error"] = after["error"]
    evidence["result"] = {k: v for k, v in out.items() if k != "evidence_file"}
    path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    return out


__all__ = ["consent_phrase", "assert_clear_allowed", "clear_module", "CLEAR_NRC"]
