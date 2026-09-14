"""Pure parsers for ELM/STN text replies. No device state, no I/O.

Every function takes the raw reply text and, where it matters, an explicit
``headers_on`` flag. Nothing here reads the link, which is what makes these
directly testable and what keeps the ISO-TP logic in one place for the OBD
reads, the UDS client and the passive capture alike.
"""

from __future__ import annotations

import re
from typing import Any

#: Adapter/bus conditions that must never be silently discarded. A bus fault
#: reported as "no codes" is the worst failure a diagnostic tool can have.
ADAPTER_ERRORS: tuple[str, ...] = (
    "BUFFER FULL", "CAN ERROR", "BUS BUSY", "BUS ERROR", "STOPPED",
    "DATA ERROR", "FB ERROR", "UNABLE TO CONNECT", "BUS INIT: ERROR",
    "ERR", "RX ERROR", "LV RESET", "ACT ALERT", "OUT OF MEMORY", "TIMEOUT",
)

#: Benign and genuinely ignorable lines.
BENIGN_LINES: tuple[str, ...] = ("OK", "NO DATA", "SEARCHING...", "?", "STOPPED SEARCHING")

HEX_DIGITS = frozenset("0123456789ABCDEF")
_ELM_INDEX_RE = re.compile(r"^([0-9A-F]{1,2}):(.*)$")


def adapter_error(text: str) -> str:
    """The adapter/bus error present in a reply, or ""."""
    up = text.upper()
    for err in ADAPTER_ERRORS:
        if err in up:
            return err
    return ""


def no_data(text: str) -> bool:
    return "NO DATA" in text.upper()


def looks_like_wrong_baud(reply: str) -> bool:
    """Framing errors decode to U+FFFD or control bytes; real replies never do."""
    return "�" in reply or any(ord(c) < 32 and c != "\n" for c in reply)


def is_hex(blob: str) -> bool:
    return bool(blob) and all(c in HEX_DIGITS for c in blob)


def hex_pairs(text: str) -> list[str]:
    """Flatten a reply into hex bytes, ignoring headers and framing.

    For callers that only need the byte stream. Prefer :func:`reassemble`
    for anything per ECU.
    """
    tokens: list[str] = []
    for line in text.splitlines():
        up = line.strip().upper()
        if not up or up in BENIGN_LINES or adapter_error(up):
            continue
        m = _ELM_INDEX_RE.match(up)
        if m:
            up = m.group(2)
        parts = up.split()
        if len(parts) > 1 and len(parts[0]) in (3, 8) and is_hex(parts[0]):
            parts = parts[1:]
        blob = "".join(parts)
        if not is_hex(blob):
            continue
        if len(blob) % 2:
            blob = blob[:-1]
        tokens.extend(blob[i:i + 2] for i in range(0, len(blob), 2))
    return tokens


def parse_frames(text: str, *, headers_on: bool) -> list[tuple[str, list[str]]]:
    """Split a reply into raw (header, bytes) frames without ISO-TP handling.

    With ``ATH1`` and ``ATS0`` an 11-bit CAN line is ``7E8`` + payload (odd
    length) and a 29-bit line is ``18DAF110`` + payload (even length), so the
    header width follows from line parity. With headers off the header is "".
    Used by the passive capture, where every frame is a datum in itself.
    """
    frames: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        up = line.strip().upper()
        if not up or up in BENIGN_LINES or adapter_error(up):
            continue
        m = _ELM_INDEX_RE.match(up)
        if m:
            blob = m.group(2).replace(" ", "")
            if is_hex(blob):
                frames.append(("", [blob[i:i + 2] for i in range(0, len(blob) - 1, 2)]))
            continue
        blob = up.replace(" ", "")
        if not is_hex(blob):
            continue
        if not headers_on:
            if len(blob) == 3:
                continue
            frames.append(("", [blob[i:i + 2] for i in range(0, len(blob) - 1, 2)]))
            continue
        hdr_len = 3 if len(blob) % 2 else 8
        if len(blob) < hdr_len + 2:
            continue
        hdr, rest = blob[:hdr_len], blob[hdr_len:]
        frames.append((hdr, [rest[i:i + 2] for i in range(0, len(rest) - 1, 2)]))
    return frames


def reassemble(text: str, *, headers_on: bool) -> dict[str, list[str]]:
    """Group a reply by sending ECU and reassemble ISO-TP multi-frame data.

    PCI types: ``0N`` single frame of N bytes, ``1N NN`` first frame with a
    12-bit length, ``2N`` consecutive frame. With headers off the adapter has
    already stripped framing; ELM's own multi-frame rendering (``0:``, ``1:``
    lines after a bare length line) is concatenated under the "" key.
    """
    ecus: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def entry(hdr: str) -> dict[str, Any]:
        if hdr not in ecus:
            ecus[hdr] = {"data": [], "expected": None}
            order.append(hdr)
        return ecus[hdr]

    for hdr, bytes_ in parse_frames(text, headers_on=headers_on):
        if not bytes_:
            continue
        if not headers_on or hdr == "":
            entry("")["data"].extend(bytes_)
            continue
        pci = int(bytes_[0], 16)
        ftype = pci >> 4
        e = entry(hdr)
        if ftype == 0:
            n = pci & 0x0F
            e["data"] = bytes_[1:1 + n] if n else bytes_[1:]
            e["expected"] = n or None
        elif ftype == 1 and len(bytes_) >= 2:
            e["expected"] = ((pci & 0x0F) << 8) | int(bytes_[1], 16)
            e["data"] = bytes_[2:]
        elif ftype == 2:
            e["data"].extend(bytes_[1:])
        else:
            e["data"].extend(bytes_)   # not ISO-TP framed; keep raw
        if e["expected"] and len(e["data"]) > e["expected"]:
            e["data"] = e["data"][:e["expected"]]

    return {hdr: ecus[hdr]["data"] for hdr in order}


def payloads_for(ecus: dict[str, list[str]], response_byte: str) -> dict[str, list[str]]:
    """Only the ECU payloads whose first byte is the expected positive response."""
    return {hdr: data for hdr, data in ecus.items() if data and data[0] == response_byte}


def negative_responses(ecus: dict[str, list[str]], service: str) -> dict[str, str]:
    """UDS negative responses (``7F <service> <NRC>``) per ECU, as NRC hex."""
    out: dict[str, str] = {}
    for hdr, data in ecus.items():
        if len(data) >= 3 and data[0] == "7F" and data[1] == service.upper():
            out[hdr] = data[2]
    return out


__all__ = [
    "ADAPTER_ERRORS", "BENIGN_LINES", "HEX_DIGITS", "adapter_error", "no_data",
    "looks_like_wrong_baud", "is_hex", "hex_pairs", "parse_frames", "reassemble",
    "payloads_for", "negative_responses",
]
