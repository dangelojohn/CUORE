"""Read-only 11-bit physical-ID discovery (TesterPresent sweep).

Some modules on CAN-CH answer UDS on 11-bit pairs rather than the 29-bit
18DAxxF1 scheme. For each request ID the pair is request -> request + 8
(FCA / ISO 15765-4 convention). ``3E 00`` proves a live node (positive 7E or
negative 7F 3E xx); identity DIDs then name it. Nothing is persisted: a human
decides what a hit means.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from . import audit, identify
from .addressing import on_bus
from .buses import Bus
from .safety import assert_read_only_uds
from .transport import Session
from .uds import IDENTITY_DIDS, _ascii, _did_reply, nrc_text

DEFAULT_CANDIDATES = [i for i in range(0x700, 0x800)
                      if i != 0x7DF and not 0x7E0 <= i <= 0x7EF]


def _tp_reply(q: dict[str, Any]) -> tuple[bool, Optional[int]]:
    """(positive 7E seen, NRC byte of a 7F 3E xx)."""
    for data in q["ecus"].values():
        if data and data[0].upper() == "7E":
            return True, None
    for data in (q.get("all_ecus") or {}).values():
        if len(data) >= 3 and data[0].upper() == "7F" and data[1].upper() == "3E":
            return False, int(data[2], 16)
    return False, None


def discover_11bit(sess: Session, bus: Bus, *, candidates: Optional[list[int]] = None,
                   per_target_timeout: float = 0.25,
                   stop_after: Optional[int] = None,
                   rx_mode: str = "plus8") -> dict[str, Any]:
    """``rx_mode``: response id = request + 8 ("plus8"), request - 0x280
    ("minus280", seen on FCA; skipped when below 0x100), or "both" (plus8
    first, then minus280)."""
    if rx_mode not in ("plus8", "minus280", "both"):
        raise ValueError("rx_mode must be plus8, minus280 or both")
    per_target_timeout = max(per_target_timeout, sess.adapter_wait + 0.2)
    targets = candidates if candidates is not None else DEFAULT_CANDIDATES
    bus_modules = on_bus(bus.key)
    hits: list[dict[str, Any]] = []
    started = time.monotonic()
    tried = 0
    for rid in targets:
        if rid == 0x7DF or 0x7E0 <= rid <= 0x7EF:
            continue
        offsets = {"plus8": [8], "minus280": [-0x280], "both": [8, -0x280]}[rx_mode]
        req_hex = f"{rid:03X}"
        resp_hex, positive, nrc, stop, tried_any = "", False, None, False, False
        for off in offsets:
            if rid + off < 0x100:
                continue
            if not tried_any:
                tried += 1
                tried_any = True
            resp_hex = f"{rid + off:03X}"
            sess.target_raw(req_hex, resp_hex)
            assert_read_only_uds(0x3E, b"\x00")
            q = sess.query("3E00", "7E", per_target_timeout)
            if q["error"] and q["error"] != "TIMEOUT":
                hits.append({"target": req_hex, "error": q["error"]})
                stop = q["error"] in ("BUS ERROR", "CAN ERROR", "OUT OF MEMORY")
                resp_hex = ""
                break
            positive, nrc = _tp_reply(q)
            if positive or nrc is not None:
                break
        if stop:
            break
        if not resp_hex or (not positive and nrc is None):
            continue
        hit: dict[str, Any] = {"target": req_hex, "request": req_hex, "response": resp_hex, "rx_mode": rx_mode,
                               "tester_present": "positive" if positive else nrc_text(nrc)}
        fields: dict[str, Optional[str]] = {}
        for did in IDENTITY_DIDS:
            dq = sess.query(f"22{did:04X}", "62", per_target_timeout)
            dp, _ = _did_reply(dq, f"{did:04X}")
            if dp:
                fields[f"{did:04X}"] = _ascii(dp)
        hit["identity"] = fields
        hit["identity_match"] = identify.match(fields, bus_modules)
        hits.append(hit)
        if stop_after and len(hits) >= stop_after:
            break
    sess.untarget()
    audit.record("discover_11bit", bus=bus.key, tried=tried, hits=len(hits))
    return {"bus": bus.key, "cable": sess.link.cable, "tried": tried,
            "seconds": round(time.monotonic() - started, 1), "hits": hits}


__all__ = ["DEFAULT_CANDIDATES", "discover_11bit"]
