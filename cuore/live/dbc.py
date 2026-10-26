"""Small dependency-free DBC parser and frame decoder.

Handles ``BO_`` messages, ``SG_`` signals (start bit, length, byte order
``@1`` little / ``@0`` big Motorola, sign, factor, offset, [min|max], unit)
and optional ``VAL_`` value tables. Pure decode: nothing here touches the bus.

Motorola (``@0``) numbering follows the DBC convention: the start bit is the
signal's MSB; bits inside a byte count 7..0 and the signal continues into the
next byte's bit 7 after bit 0 of the current one. A bit position is
``byte * 8 + bit_in_byte``. Little-endian (``@1``) start bit is the LSB.

CONFIDENCE (read this before using any value from here): the vendored DBC
(opendbc fca_giorgio.dbc) was written for a Giulia and relayed through openpilot.
No raw broadcast frame from THIS car has ever been saved, so no scale, offset or
bit position has been checked here. Every decoded value therefore carries
:data:`UNVERIFIED_LABEL`, and none of it is diagnostic proof (core directive:
conclusions cite verified CUORE readings; use the UDS DIDs instead). Frame-id
presence ("this module is talking") is the only thing the data supports.
:data:`NOT_BATTERY_VOLTAGE` signals (MAYBE_VOLTAGE) must never be shown as volts
of the battery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

UNVERIFIED_LABEL = "unverified scale (opendbc Giulia DBC, not checked on this car)"
#: Signals whose meaning the DBC itself guesses at; never present as battery volts.
NOT_BATTERY_VOLTAGE = {"MAYBE_VOLTAGE"}
NOT_BATTERY_VOLTAGE_NOTE = ("unidentified 10-bit signal (upstream guess 'maybe voltage'); "
                            "NOT battery voltage")

DEFAULT_DBC = Path(__file__).resolve().parents[1] / "data" / "dbc" / "fca_giorgio.dbc"

_BO_RE = re.compile(r"^BO_\s+(\d+)\s+(\w+)\s*:\s*(\d+)\s+(\w+)")
_SG_RE = re.compile(
    r"^\s*SG_\s+(\w+)\s*(?:[Mm]\d*\s*)?:\s*(\d+)\|(\d+)@([01])([+-])\s*"
    r"\(\s*([^,\s]+)\s*,\s*([^)\s]+)\s*\)\s*\[\s*([^|\s]*)\s*\|\s*([^\]\s]*)\s*\]\s*"
    r'"([^"]*)"')
_VAL_RE = re.compile(r"^VAL_\s+(\d+)\s+(\w+)\s+(.*);\s*$")
_VAL_PAIR_RE = re.compile(r'(-?\d+)\s+"([^"]*)"')
_EXT_FLAG = 0x80000000


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return 0.0


def _tidy(x: float) -> Any:
    return int(x) if float(x).is_integer() else x


@dataclass
class Signal:
    name: str
    start: int
    length: int
    little_endian: bool
    signed: bool
    factor: float
    offset: float
    minimum: float
    maximum: float
    unit: str
    choices: dict[int, str] = field(default_factory=dict)

    def bit_positions(self) -> list[int]:
        """Absolute bit positions (byte*8 + bit), most significant first."""
        if self.little_endian:
            return [self.start + i for i in range(self.length - 1, -1, -1)]
        pos, out = self.start, []
        for _ in range(self.length):
            out.append(pos)
            pos = pos + 15 if pos % 8 == 0 else pos - 1
        return out

    def raw(self, data: bytes) -> Optional[int]:
        """Raw integer, or None when the frame is too short for the signal."""
        positions = self.bit_positions()
        if not positions or max(positions) // 8 >= len(data):
            return None
        value = 0
        for p in positions:
            value = (value << 1) | ((data[p // 8] >> (p % 8)) & 1)
        if self.signed and value & (1 << (self.length - 1)):
            value -= 1 << self.length
        return value

    def decode(self, data: bytes) -> Optional[tuple[Any, str]]:
        r = self.raw(data)
        if r is None:
            return None
        return _tidy(round(r * self.factor + self.offset, 9)), self.unit


@dataclass
class Message:
    frame_id: int
    name: str
    dlc: int
    sender: str
    extended: bool
    signals: dict[str, Signal] = field(default_factory=dict)


class Dbc:
    def __init__(self) -> None:
        self.messages: dict[tuple[int, bool], Message] = {}
        self.by_name: dict[str, Message] = {}

    def get(self, frame_id: int, extended: Optional[bool] = None) -> Optional[Message]:
        if extended is None:
            extended = frame_id > 0x7FF
        return self.messages.get((frame_id, extended))

    def decode(self, frame_id: int, data: bytes,
               extended: Optional[bool] = None) -> Optional[dict[str, Any]]:
        msg = self.get(frame_id, extended)
        if msg is None:
            return None
        signals: dict[str, tuple[Any, str]] = {}
        for sig in msg.signals.values():
            v = sig.decode(data)
            if v is not None:
                signals[sig.name] = v
        return {"message": msg.name, "signals": signals, "confidence": UNVERIFIED_LABEL}


def parse(text: str) -> Dbc:
    db = Dbc()
    current: Optional[Message] = None
    pending_vals: list[tuple[int, str, str]] = []
    for line in text.splitlines():
        m = _BO_RE.match(line)
        if m:
            raw_id = int(m.group(1))
            fid = raw_id & 0x1FFFFFFF
            ext = bool(raw_id & _EXT_FLAG) or fid > 0x7FF
            current = Message(fid, m.group(2), int(m.group(3)), m.group(4), ext)
            db.messages[(fid, ext)] = current
            db.by_name[current.name] = current
            continue
        m = _SG_RE.match(line)
        if m and current is not None:
            current.signals[m.group(1)] = Signal(
                name=m.group(1), start=int(m.group(2)), length=int(m.group(3)),
                little_endian=m.group(4) == "1", signed=m.group(5) == "-",
                factor=_num(m.group(6)), offset=_num(m.group(7)),
                minimum=_num(m.group(8)), maximum=_num(m.group(9)), unit=m.group(10))
            continue
        if line.strip() and not line.startswith((" ", "\t")):
            current = None
        m = _VAL_RE.match(line.strip())
        if m:
            pending_vals.append((int(m.group(1)), m.group(2), m.group(3)))
    for raw_id, sig_name, body in pending_vals:
        fid = raw_id & 0x1FFFFFFF
        msg = db.messages.get((fid, bool(raw_id & _EXT_FLAG) or fid > 0x7FF))
        sig = msg.signals.get(sig_name) if msg else None
        if sig is not None:
            sig.choices = {int(k): v for k, v in _VAL_PAIR_RE.findall(body)}
    return db


def load(path: Path | str = DEFAULT_DBC) -> Dbc:
    return parse(Path(path).read_text(encoding="utf-8", errors="replace"))


_default: Optional[Dbc] = None


def default() -> Dbc:
    global _default
    if _default is None:
        _default = load()
    return _default


def decode(frame_id: int, data: bytes, dbc: Optional[Dbc] = None,
           extended: Optional[bool] = None) -> Optional[dict[str, Any]]:
    """Decode one frame: ``{message, signals: {name: (value, unit)}}`` or None
    when the id is not in the DBC. 11-bit and 29-bit ids are told apart by
    value (> 0x7FF is 29-bit) unless ``extended`` is given."""
    return (dbc or default()).decode(frame_id, bytes(data), extended)


__all__ = ["Dbc", "Message", "Signal", "parse", "load", "default", "decode", "DEFAULT_DBC",
           "UNVERIFIED_LABEL", "NOT_BATTERY_VOLTAGE", "NOT_BATTERY_VOLTAGE_NOTE"]
