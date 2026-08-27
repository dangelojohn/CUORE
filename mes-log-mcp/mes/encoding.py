"""Encoding-tolerant text reading for MES logs.

MES writes plain text with CRLF line endings, but the encoding is not constant
across versions and locales. On this corpus SCAN logs are pure ASCII while FES
logs are UTF-8 (they carry degree signs in temperature parameters). A MES build
running under a Western European Windows locale will emit cp1252 instead, where
a degree sign is the single byte 0xB0 -- invalid UTF-8.

The v1 server read everything as ``utf-8, errors="replace"``. That never raises,
which sounds safe but is the failure mode: a cp1252 log silently decodes with
U+FFFD replacement characters where the units used to be, and the corruption is
invisible until a parameter value fails to parse for no apparent reason.

Here we sniff, then fall back through a candidate list, and always report which
encoding was actually used so callers can surface it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: BOM prefixes, longest first so utf-32 is tested before utf-16.
_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)

#: Tried in order when there is no BOM. utf-8 is strict so that a cp1252 file
#: falls through instead of being mangled; cp1252 then accepts essentially any
#: byte, so it is the effective terminator.
_FALLBACKS: tuple[str, ...] = ("utf-8", "cp1252", "latin-1")


#: Control characters that are legitimate in a text log. Everything else in
#: the C0 range is stray binary.
_ALLOWED_CONTROL = {"\t", "\n", "\r"}


@dataclass(frozen=True)
class DecodedText:
    """Decoded file content plus the provenance of the decoding."""

    text: str
    encoding: str
    size_bytes: int
    #: True if we had to decode lossily -- i.e. the content may be corrupted.
    lossy: bool = False
    #: True if the caller's byte budget cut the file short.
    truncated: bool = False
    #: Count of stray control characters found and removed. Roughly half the
    #: logs in this corpus carry bytes like 0x03/0x07/0x13 inside identifier
    #: fields, which is why ``file(1)`` calls them "data" and why grep skips
    #: them as binary. They are noise from MES dumping uninterpreted ECU
    #: memory, not content, but their presence is worth reporting.
    control_chars: int = 0

    @property
    def binary_suspect(self) -> bool:
        """True when the file carries enough stray bytes to distrust it."""
        return self.control_chars > 0

    def splitlines(self) -> list[str]:
        return self.text.splitlines()


def sniff_encoding(head: bytes) -> str | None:
    """Return the encoding implied by a BOM, or None if there is no BOM."""
    for bom, enc in _BOMS:
        if head.startswith(bom):
            return enc
    return None


def strip_control(text: str) -> tuple[str, int]:
    """Remove stray control characters, returning the text and how many went.

    Kept separate from decoding because the two failures are different: a
    wrong codec corrupts meaning, whereas these bytes are debris that would
    otherwise break line matching in the middle of an identifier field.
    """
    if not any(ord(c) < 32 and c not in _ALLOWED_CONTROL for c in text):
        return text, 0
    kept = []
    removed = 0
    for c in text:
        if ord(c) < 32 and c not in _ALLOWED_CONTROL:
            removed += 1
            continue
        kept.append(c)
    return "".join(kept), removed


def decode_bytes(data: bytes, *, truncated: bool = False) -> DecodedText:
    """Decode MES log bytes, trying BOM first then the fallback ladder."""
    size = len(data)

    def _finish(text: str, enc: str, lossy: bool = False) -> DecodedText:
        cleaned, removed = strip_control(text)
        return DecodedText(cleaned, enc, size, lossy=lossy,
                           truncated=truncated, control_chars=removed)

    bom_enc = sniff_encoding(data[:4])
    if bom_enc:
        try:
            return _finish(data.decode(bom_enc), bom_enc)
        except UnicodeDecodeError:
            # A truncated utf-16 read can split a surrogate pair; fall through
            # rather than failing the whole call.
            pass

    for enc in _FALLBACKS:
        try:
            return _finish(data.decode(enc), enc)
        except UnicodeDecodeError:
            continue

    # Unreachable in practice (latin-1 maps all 256 bytes), kept as a hard floor.
    return _finish(data.decode("utf-8", errors="replace"), "utf-8/replace",
                   lossy=True)


def read_log_text(path: Path, *, max_bytes: int | None = None) -> DecodedText:
    """Read and decode a log file, optionally capping the bytes read.

    When ``max_bytes`` cuts a multi-byte character in half the tail is trimmed
    back to the last clean boundary rather than emitting a replacement char.
    """
    raw = path.read_bytes()
    truncated = False
    if max_bytes is not None and len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True

    decoded = decode_bytes(raw, truncated=truncated)
    if truncated and decoded.text.endswith("�"):
        decoded = DecodedText(
            decoded.text.rstrip("�"), decoded.encoding,
            decoded.size_bytes, decoded.lossy, True, decoded.control_chars,
        )
    return decoded
