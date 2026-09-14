# Adapted from stelvio_scan (MIT): src/stelvio_scan/adapter/stream.py, recording/recorder.py, recording/player.py
"""Pluggable transport abstraction for live OBD2/ELM327 sessions.

This module has three intended uses:

  1. Real adapter I/O — ``SerialStream`` (pyserial COM / virtual COM, e.g. a
     Bluetooth-paired ELM327) and ``TcpStream`` (Wi-Fi ELM327 clones that
     bridge a UART over a raw TCP socket, commonly 192.168.0.10:35000).
     Callers talk to either through the same minimal ``Stream`` interface
     and don't need to know which physical layer is underneath.

  2. Wire capture of on-car sessions — wrap a real stream in
     ``RecordingStream`` (backed by a ``RecordingFile``) to tee every byte
     written and read into a JSONL log. These captures are meant to become
     test fixtures: a real session, recorded once on a real car, that can
     be replayed offline forever after.

  3. No-hardware playback — ``PlaybackStream`` replays a JSONL recording
     back through the exact same ``Stream`` interface, so the rest of the
     stack (parsers, MES logic, UI) can be exercised in tests or at a desk
     without any adapter or vehicle attached.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import serial

log = logging.getLogger(__name__)


# ---- Stream interface -------------------------------------------------

class Stream(ABC):
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def is_open(self) -> bool: ...

    @abstractmethod
    def read(self, n: int) -> bytes:
        """Read up to n bytes within the configured timeout. May return b""."""

    @abstractmethod
    def write(self, data: bytes) -> None: ...

    def flush(self) -> None:
        """Default no-op — most transports don't need it."""

    def reset_input_buffer(self) -> None:
        """Drain any buffered input. Default no-op."""

    def reset_output_buffer(self) -> None:
        """Drain any buffered output. Default no-op."""

    def in_waiting(self) -> int:
        """Bytes known to be immediately available. Default 0 (unknown)."""
        return 0

    @property
    def describe(self) -> str:
        """Short human-readable description, e.g. "serial COM3@115200"."""
        return self.__class__.__name__


# ---- Serial -------------------------------------------------------------

class SerialStream(Stream):
    """pyserial-backed COM port / virtual COM (e.g. Bluetooth pairing)."""

    def __init__(self, port: str, baudrate: int, *, timeout: float = 0.25, write_timeout: float = 2.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        # Let serial.SerialException propagate unchanged — the caller turns
        # e.g. "Access is denied" into a port-busy message.
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout,
            write_timeout=self.write_timeout,
        )

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def read(self, n: int) -> bytes:
        if self._ser is None:
            return b""
        return self._ser.read(n)

    def write(self, data: bytes) -> None:
        if self._ser is None:
            raise IOError("serial not open")
        self._ser.write(data)

    def flush(self) -> None:
        if self._ser is not None:
            self._ser.flush()

    def reset_input_buffer(self) -> None:
        if self._ser is not None:
            self._ser.reset_input_buffer()

    def reset_output_buffer(self) -> None:
        if self._ser is not None:
            self._ser.reset_output_buffer()

    def in_waiting(self) -> int:
        if self._ser is None:
            return 0
        return self._ser.in_waiting

    @property
    def describe(self) -> str:
        return f"serial {self.port}@{self.baudrate}"


# ---- TCP / Wi-Fi ----------------------------------------------------------

class TcpStream(Stream):
    """TCP transport for Wi-Fi ELM327 adapters.

    These adapters are typically ESP8266/ESP32 based. They expose a TCP
    server (commonly on 192.168.0.10:35000) that bridges directly to the
    ELM327 chip's UART. The wire format is identical to serial."""

    def __init__(self, host: str = "192.168.0.10", port: int = 35000, *, timeout: float = 0.25):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def open(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect((self.host, self.port))
        # Disable Nagle so single-byte ELM commands aren't delayed.
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = s

    def close(self) -> None:
        if self._sock is not None:
            try:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._sock.close()
            finally:
                self._sock = None

    def is_open(self) -> bool:
        return self._sock is not None

    def read(self, n: int) -> bytes:
        if self._sock is None:
            return b""
        try:
            data = self._sock.recv(n)
            return data or b""
        except socket.timeout:
            return b""

    def write(self, data: bytes) -> None:
        if self._sock is None:
            raise IOError("socket not open")
        self._sock.sendall(data)

    def reset_input_buffer(self) -> None:
        """Drain any buffered bytes by setting a 0 timeout and reading until empty."""
        if self._sock is None:
            return
        prior = self._sock.gettimeout()
        self._sock.settimeout(0.0)
        try:
            while True:
                try:
                    if not self._sock.recv(4096):
                        break
                except (BlockingIOError, socket.timeout):
                    break
        finally:
            self._sock.settimeout(prior)

    @property
    def describe(self) -> str:
        return f"tcp {self.host}:{self.port}"


# ---- Recording ------------------------------------------------------------

@dataclass
class RecordingFile:
    """JSONL sink for a recorded session.

    Wire format (one JSON object per line):
      {"t": <monotonic_seconds_since_record_start>, "kind": "write", "data": "<hex>"}
      {"t": ..., "kind": "read",  "data": "<hex>"}
      {"t": 0,   "kind": "header", "format": 1, "started_at": <unix_ts>,
                  "transport": "SerialStream"|"TcpStream", "note": "..."}
      {"t": ..., "kind": "footer", "bytes_written": ..., "bytes_read": ...}

    Non-intrusive: any exception during the file write is swallowed (so a
    misbehaving filesystem can't take down a live session).
    """

    path: Path
    fp: object | None = None
    started_monotonic: float = 0.0
    started_unix: float = 0.0
    bytes_written: int = 0
    bytes_read: int = 0
    # Reentrant — close() holds the lock and calls _write() which re-acquires.
    lock: threading.RLock = field(default_factory=threading.RLock)

    def open(self, transport: str = "", note: str = "") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fp = self.path.open("w", encoding="utf-8")
        self.started_monotonic = time.monotonic()
        self.started_unix = time.time()
        self._write({
            "t": 0.0,
            "kind": "header",
            "format": 1,
            "started_at": self.started_unix,
            "transport": transport,
            "note": note,
        })

    def close(self) -> None:
        with self.lock:
            if self.fp is not None:
                try:
                    self._write({
                        "t": time.monotonic() - self.started_monotonic,
                        "kind": "footer",
                        "bytes_written": self.bytes_written,
                        "bytes_read": self.bytes_read,
                    })
                    self.fp.flush()
                    self.fp.close()
                except Exception:
                    log.exception("recording close failed")
                finally:
                    self.fp = None

    def append(self, kind: str, data: bytes) -> None:
        if self.fp is None:
            return
        if kind == "write":
            self.bytes_written += len(data)
        elif kind == "read":
            self.bytes_read += len(data)
        try:
            self._write({
                "t": time.monotonic() - self.started_monotonic,
                "kind": kind,
                "data": data.hex().upper(),
            })
        except Exception:
            log.exception("recording append failed")

    def _write(self, obj: dict) -> None:
        with self.lock:
            self.fp.write(json.dumps(obj) + "\n")
            # Flush after every event so a crash doesn't lose the tail.
            self.fp.flush()


class RecordingStream(Stream):
    """Wraps an inner Stream and tees every read/write into a RecordingFile."""

    def __init__(self, inner: Stream, recording: RecordingFile):
        self._inner = inner
        self._rec = recording

    def open(self) -> None:
        self._inner.open()
        self._rec.open(transport=type(self._inner).__name__)

    def close(self) -> None:
        try:
            self._inner.close()
        finally:
            self._rec.close()

    def is_open(self) -> bool:
        return self._inner.is_open()

    def read(self, n: int) -> bytes:
        data = self._inner.read(n)
        if data:
            self._rec.append("read", data)
        return data

    def write(self, data: bytes) -> None:
        self._inner.write(data)
        self._rec.append("write", data)

    def flush(self) -> None:
        self._inner.flush()

    def reset_input_buffer(self) -> None:
        self._inner.reset_input_buffer()

    def reset_output_buffer(self) -> None:
        self._inner.reset_output_buffer()

    def in_waiting(self) -> int:
        return self._inner.in_waiting()

    @property
    def describe(self) -> str:
        return f"recording({self._inner.describe})"


# ---- Playback ---------------------------------------------------------

class PlaybackError(RuntimeError):
    pass


class PlaybackStream(Stream):
    """Replays a recorded session (see RecordingFile) with no hardware attached.

    Behaviour:
      - Open: read header line, position at first event.
      - Write: assert the bytes match the next 'write' event in the log
        (replays must follow the same request order as recording). On
        mismatch, raises PlaybackError so the caller knows the scenario
        diverged from the recording. Default (strict_writes=False) just
        consumes the write silently.
      - Read: return the data of the next 'read' event(s). If the log has
        no further read before the next write event, read() returns b""
        (rather than reaching past the write) so a caller polling with a
        deadline sees a timeout instead of a later, out-of-order response.
      - reset_input_buffer / reset_output_buffer: no-op.

    This is meant for offline analysis and no-hardware test fixtures. It is
    NOT a tool for replaying into a real adapter.
    """

    def __init__(self, path: Path | str, *, strict_writes: bool = False):
        """`strict_writes`: if True, raise PlaybackError when the caller's
        write bytes don't match the next 'write' event in the recording.
        Default False — we just consume writes silently and serve queued
        reads, which is friendlier when the caller's command sequence has
        drifted."""
        self.path = Path(path)
        self._strict = strict_writes
        self._fp = None
        self._read_queue: deque[bytes] = deque()
        # One-event lookahead: an event pulled from the log but not yet
        # consumed (e.g. a write event seen while looking for a read).
        self._pending: tuple[str, str] | None = None
        self._is_open = False
        self.header: dict = {}

    def open(self) -> None:
        if self._is_open:
            return
        self._fp = self.path.open("r", encoding="utf-8")
        first = self._fp.readline().strip()
        if first:
            try:
                obj = json.loads(first)
                if obj.get("kind") == "header":
                    self.header = obj
                else:
                    # No header — rewind.
                    self._fp.seek(0)
            except json.JSONDecodeError:
                raise PlaybackError(f"first line of {self.path} is not valid JSON")
        self._is_open = True

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None
        self._is_open = False
        self._read_queue.clear()
        self._pending = None

    def is_open(self) -> bool:
        return self._is_open

    def _next_event(self) -> tuple[str, str] | None:
        """Return the next (kind, hex_data) event of kind 'read'/'write',
        skipping header/footer/unknown lines. Consumes `_pending` first."""
        if self._pending is not None:
            ev = self._pending
            self._pending = None
            return ev
        while self._fp is not None:
            line = self._fp.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = obj.get("kind")
            if kind in ("read", "write"):
                return (kind, obj.get("data", ""))
            # header / footer / unknown — keep going
        return None

    def write(self, data: bytes) -> None:
        # Pull events forward until we either hit a write event (which we
        # match against `data`) or end of file. Any read events seen along
        # the way are queued up for subsequent read() calls.
        while True:
            ev = self._next_event()
            if ev is None:
                if self._strict:
                    raise PlaybackError("playback ran out of writes")
                return
            kind, hexdata = ev
            if kind == "read":
                self._read_queue.append(bytes.fromhex(hexdata))
                continue
            # kind == "write"
            expected = bytes.fromhex(hexdata)
            if self._strict and expected != data:
                raise PlaybackError(
                    f"write mismatch: expected {expected.hex().upper()} got {data.hex().upper()}"
                )
            return

    def read(self, n: int) -> bytes:
        # First serve from the queue.
        if self._read_queue:
            chunk = self._read_queue.popleft()
            if len(chunk) > n:
                self._read_queue.appendleft(chunk[n:])
                return chunk[:n]
            return chunk
        # Otherwise advance the log to find the next read — but stop (and
        # push back) at a write event, since that belongs to the *next*
        # write() call, not to this read().
        ev = self._next_event()
        if ev is None:
            return b""
        kind, hexdata = ev
        if kind == "write":
            self._pending = ev
            return b""
        data = bytes.fromhex(hexdata)
        if len(data) > n:
            self._read_queue.appendleft(data[n:])
            return data[:n]
        return data

    def in_waiting(self) -> int:
        if self._read_queue:
            return len(self._read_queue[0])
        return 0

    @property
    def describe(self) -> str:
        return f"playback {self.path}"
