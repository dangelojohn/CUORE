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

import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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

#: Every C0 control character except tab, LF and CR (precompiled: the old
#: per-character generator cost seconds per cold report).
_CONTROL_RE = re.compile("[" + "".join(
    re.escape(chr(i)) for i in range(32) if chr(i) not in _ALLOWED_CONTROL) + "]")


def memoize_by_file(maxsize: int = 1024) -> Callable:
    """Decorator: memoise ``fn(path, *, timestamp="")`` on the file's identity.

    Key is (path as given, mtime_ns, size, timestamp), so an edited or replaced
    log is re-parsed. Bounded LRU, thread-safe (parse runs outside the lock; a
    race costs a duplicate parse, never a wrong result). A path that cannot be
    stat'ed bypasses the cache so the original error surfaces. The cached
    object is shared: callers must treat it as read-only (audited).
    """
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        cache: OrderedDict = OrderedDict()
        lock = threading.Lock()

        def wrapper(path, *, timestamp: str = ""):
            try:
                # stat once per GET request (the file set is fixed for one page render)
                from .catalog import request_scope
                scope = request_scope.get()
                sk = ("stat", str(path))
                if scope is not None and sk in scope:
                    st = scope[sk]
                else:
                    st = os.stat(path)
                    if scope is not None:
                        scope[sk] = st
                key = (str(path), st.st_mtime_ns, st.st_size, timestamp)
            except (OSError, TypeError, ValueError):
                return fn(path, timestamp=timestamp)
            with lock:
                hit = cache.get(key)
                if hit is not None:
                    cache.move_to_end(key)
                    return hit
            result = fn(path, timestamp=timestamp)
            with lock:
                cache[key] = result
                cache.move_to_end(key)
                while len(cache) > maxsize:
                    cache.popitem(last=False)
            return result

        def cache_clear() -> None:
            with lock:
                cache.clear()

        wrapper.__wrapped__ = fn
        wrapper.__doc__ = fn.__doc__
        wrapper.__name__ = fn.__name__
        wrapper.cache_clear = cache_clear
        wrapper.cache_len = lambda: len(cache)
        return wrapper
    return deco


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
    cleaned, removed = _CONTROL_RE.subn("", text)
    if not removed:
        return text, 0
    return cleaned, removed


def decode_bytes(data: bytes, *, truncated: bool = False) -> DecodedText:
    """Decode MES log bytes, trying BOM first then the fallback ladder."""
    size = len(data)

    def _finish(text: str, enc: str, lossy: bool = False) -> DecodedText:
        cleaned, removed = strip_control(text)
        return DecodedText(cleaned, enc, size, lossy=lossy,
                           truncated=truncated, control_chars=removed)

    bom_enc = sniff_encoding(data[:4])
    if bom_enc:
        # The endian-specific codecs ("utf-16-le") keep the BOM as a leading
        # U+FEFF, which then glues itself to the first header/line and defeats
        # every anchored match (the CSV "Time" column, the "(Multiecuscan"
        # preamble). The generic codecs consume it and pick the endianness.
        codec = {"utf-16-le": "utf-16", "utf-16-be": "utf-16",
                 "utf-32-le": "utf-32", "utf-32-be": "utf-32"}.get(bom_enc, bom_enc)
        try:
            return _finish(data.decode(codec), bom_enc)
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


def _cut_clean(raw: bytes, limit: int) -> bytes:
    """``raw[:limit]`` backed off to a character boundary. A plain byte cut
    through a multi-byte UTF-8 character makes the strict utf-8 decode fail,
    and the ladder then falls to cp1252 and mangles every non-ASCII character
    in the whole file (degree signs become 'Â°') with ``lossy`` still False."""
    cut = raw[:limit]
    bom = sniff_encoding(raw[:4])
    if bom in ("utf-16-le", "utf-16-be"):
        return cut[:len(cut) - (len(cut) % 2)]
    if bom in ("utf-32-le", "utf-32-be"):
        return cut[:len(cut) - (len(cut) % 4)]
    for back in range(4):
        trial = cut[:len(cut) - back] if back else cut
        try:
            trial.decode("utf-8")
            return trial
        except UnicodeDecodeError:
            continue
    return cut  # not UTF-8 at all (cp1252 etc.): any cut is a clean cut


def read_log_text(path: Path, *, max_bytes: int | None = None) -> DecodedText:
    """Read and decode a log file, optionally capping the bytes read.

    When ``max_bytes`` cuts a multi-byte character in half the tail is trimmed
    back to the last clean boundary rather than emitting a replacement char.
    """
    raw = path.read_bytes()
    truncated = False
    if max_bytes is not None and len(raw) > max(0, max_bytes):
        raw = _cut_clean(raw, max(0, max_bytes))
        truncated = True

    decoded = decode_bytes(raw, truncated=truncated)
    if truncated and decoded.text.endswith("�"):
        decoded = DecodedText(
            decoded.text.rstrip("�"), decoded.encoding,
            decoded.size_bytes, decoded.lossy, True, decoded.control_chars,
        )
    return decoded
