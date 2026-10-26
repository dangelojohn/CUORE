"""Persist RAW passive-listen frames so decoding can be checked offline.

Layout: ``<state dir>/bus_captures/<vin>/<timestamp>.jsonl``. Line 1 is a header
``{"kind": "header", bus, bitrate, cable, state_note, ...}``; every other line is
one frame ``{t, bus, bitrate, id, dlc, data}`` (``data`` = hex). Lines are
appended and fsynced, so a crash can only cut the LAST line; :func:`read_capture`
skips a torn line. Pure file I/O: nothing here touches the adapter and nothing is
ever transmitted. Callers only persist frames heard at the bus's confirmed
bitrate (see :func:`cuore.live.capture.listen`).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import state_dir


def capture_dir(vin: str = "") -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", vin or "") or "unknown_vin"
    return state_dir() / "bus_captures" / safe


def write_capture(frames: Iterable[dict[str, Any]], *, bus: str, bitrate: int,
                  cable: str, vin: str = "", state_note: str = "",
                  extra: Optional[dict[str, Any]] = None) -> Path:
    d = capture_dir(vin)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
    path = d / f"{stamp}.jsonl"
    header = {"kind": "header", "at": datetime.now().isoformat(timespec="seconds"),
              "vin": vin or None, "bus": bus, "bitrate": int(bitrate), "cable": cable,
              "state_note": state_note or "", "passive": True, **(extra or {})}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(header) + "\n")
        fh.flush()
        for f in frames:
            data = str(f.get("data", ""))
            fh.write(json.dumps({"t": f.get("t"), "bus": bus, "bitrate": int(bitrate),
                                 "id": f.get("id"), "dlc": len(data) // 2,
                                 "data": data}) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return path


def read_capture(path: Path | str) -> dict[str, Any]:
    """``{header, frames, torn_lines}``; a torn/garbled line is skipped, counted."""
    header: dict[str, Any] = {}
    frames: list[dict[str, Any]] = []
    torn = 0
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            torn += 1
            continue
        if not isinstance(rec, dict):
            torn += 1
        elif rec.get("kind") == "header":
            header = rec
        else:
            frames.append(rec)
    return {"header": header, "frames": frames, "torn_lines": torn}


__all__ = ["capture_dir", "write_capture", "read_capture"]
