"""Passive capture: listen on a bus without acknowledging a single frame.

Uses the adapter's monitor mode, which never returns to the prompt on its own,
so this module has its own read loop with a deadline and sends the interrupt
byte itself. Sessions are opened ``passive=True``, which sets ``STCMM 0``
(receive only, no CAN ACK) on STN adapters: the vehicle never sees the tool.
It is also how a bus gets verified under a declared cable.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any, Optional

from . import audit
from .framing import adapter_error, parse_frames
from .transport import Session

_FILTER_SPELLINGS = ("STFPA", "STFAP")   # rev F, then the 2010 legacy spelling


def _add_filters(sess: Session, filters: list[str]) -> Optional[str]:
    """Add pass filters, learning which spelling this firmware accepts."""
    if not sess.link.is_stn:
        return None
    # Always clear: pass filters (including the one ATCRA installs for a
    # targeted UDS session) persist across port closes, and an unfiltered
    # listen on a filtered adapter reports a dead bus.
    sess.cmd("STFAC", 2)
    if not filters:
        return None
    spelling = None
    for f in filters:
        pattern, _, mask = f.partition(",")
        mask = mask or ("7FF" if len(pattern) <= 3 else "1FFFFFFF")
        for sp in ([spelling] if spelling else _FILTER_SPELLINGS):
            r = sess.cmd(f"{sp} {pattern},{mask}", 2)
            if "OUT OF MEMORY" in r.upper():
                return "OUT OF MEMORY while adding filters"
            if r.strip() != "?":
                spelling = sp
                break
    return None


def listen(sess: Session, *, seconds: float = 2.0, max_frames: int = 500,
           filters: Optional[list[str]] = None) -> dict[str, Any]:
    """Collect raw frames for ``seconds`` or until ``max_frames``.

    Returns frames, per-ID counts, the measured rate, and any adapter error.
    The protocol is closed by the adapter when monitoring ends; the session
    is single-purpose so nothing depends on it afterwards.
    """
    err = _add_filters(sess, filters or [])
    if err:
        return {"bus": sess.bus.key, "error": err, "frames": [], "count": 0}
    if sess.link.is_stn:
        sess.cmd("STPO", 3)
        monitor = "STM"
    else:
        monitor = "ATMA"
    s = sess.stream
    s.reset_input_buffer()
    s.write((monitor + "\r").encode("ascii"))
    s.flush()
    started = time.monotonic()
    deadline = started + max(0.2, float(seconds))
    buf = bytearray()
    frames: list[dict[str, Any]] = []
    error = None
    partial = b""
    while time.monotonic() < deadline and len(frames) < max_frames:
        chunk = s.read(s.in_waiting() or 1)
        if not chunk:
            continue
        buf.extend(chunk)
        data = partial + chunk
        lines = data.replace(b"\r", b"\n").split(b"\n")
        partial = lines.pop()
        for line in lines:
            text = line.decode("ascii", errors="replace").strip()
            if not text or text.upper().startswith(monitor):
                continue
            e = adapter_error(text)
            if e and e != "STOPPED":
                error = e
                continue
            for hdr, bytes_ in parse_frames(text, headers_on=True):
                frames.append({"t": round(time.monotonic() - started, 4), "id": hdr,
                               "data": "".join(bytes_)})
    # interrupt the monitor and drain to the prompt
    s.write(b" ")
    s.flush()
    drain_deadline = time.monotonic() + 1.5
    while time.monotonic() < drain_deadline:
        chunk = s.read(s.in_waiting() or 1)
        if not chunk:
            continue
        if b">" in chunk:
            break
    elapsed = max(1e-3, time.monotonic() - started)
    ids = Counter(f["id"] for f in frames)
    out = {
        "bus": sess.bus.key, "cable": sess.link.cable, "passive": sess.passive,
        "monitor": monitor, "seconds": round(elapsed, 2), "count": len(frames),
        "rate_hz": round(len(frames) / elapsed, 1),
        "ids": dict(sorted(ids.items(), key=lambda kv: -kv[1])),
        "frames": frames, "error": error,
    }
    audit.record("capture", bus=sess.bus.key, count=len(frames), seconds=out["seconds"],
                 error=error)
    return out


__all__ = ["listen"]
