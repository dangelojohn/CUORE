"""READ-ONLY listener skeleton for the serial-mirror capture path.  NOT RUN BY ANYTHING.

It would open the MIRROR ports (virtual COM ports a hub copies MES's traffic
onto -- see ``docs/design/SERIAL_MIRROR_CAPTURE.md``), feed what it reads to
:class:`cuore.live.serial_mirror.MirrorParser`, and save the result in the
``state/mes_learn`` capture format. It NEVER transmits:

* the only object that holds a serial handle is :class:`RxOnlyPort`, which
  exposes ``read`` and ``close`` and nothing else -- there is no write path to
  call, and the module never names one;
* the port is opened with every flow-control mode OFF (XON/XOFF would make the
  driver transmit bytes by itself), and each read asserts the TX queue is empty;
* it refuses unless ``CUORE_SERIAL_MIRROR_PORT`` (adapter -> MES stream) AND
  ``CUORE_SERIAL_MIRROR_PORT_TX`` (MES -> adapter stream) are set, are two
  different ports, and neither is COM3 (the real adapter) nor any port named in
  ``CUORE_SERIAL_REAL_PORTS`` (comma list) nor MES's own configured port.

Nothing here imports pyserial at module level, so importing is harmless.
"""

from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from .errors import Refused
from .serial_mirror import MirrorParser, to_capture, write_capture

ENV_PORT = "CUORE_SERIAL_MIRROR_PORT"          # adapter -> MES direction (replies)
ENV_PORT_TX = "CUORE_SERIAL_MIRROR_PORT_TX"    # MES -> adapter direction (requests)
ENV_REAL = "CUORE_SERIAL_REAL_PORTS"           # extra never-open ports (comma list)
REAL_ADAPTER_PORTS = frozenset({"COM3"})       # the real adapter: never opened here
DEFAULT_BAUD = 115200                          # STN1170 / MES link rate (see the design doc)


def _norm(port: str) -> str:
    """'\\\\.\\com3', ' com3 ' -> 'COM3'."""
    p = (port or "").strip().upper()
    return p[4:] if p.startswith("\\\\.\\") else p


def check_guard(env: Optional[dict[str, str]] = None,
                mes_port: Optional[str] = None) -> tuple[str, str]:
    """Return ``(rx_port, tx_port)`` or raise :class:`Refused`. Pure; opens nothing."""
    env = os.environ if env is None else env
    rx, tx = _norm(env.get(ENV_PORT, "")), _norm(env.get(ENV_PORT_TX, ""))
    if not rx:
        raise Refused(f"{ENV_PORT} is not set. The serial-mirror listener only runs when the owner "
                      "names the mirror port explicitly.")
    if not tx:
        raise Refused(f"{ENV_PORT_TX} is not set. A mirror needs both directions (requests and "
                      "replies); a one-direction capture cannot attribute requests to targets.")
    if rx == tx:
        raise Refused("the two mirror ports are the same port; they must be two different virtual ports")
    deny = set(REAL_ADAPTER_PORTS)
    deny |= {_norm(p) for p in env.get(ENV_REAL, "").split(",") if p.strip()}
    if mes_port:
        deny.add(_norm(mes_port))
    for name, port in ((ENV_PORT, rx), (ENV_PORT_TX, tx)):
        if port in deny:
            raise Refused(f"{name}={port} is the real adapter or MES's own port. The listener reads "
                          "only the mirror's virtual output ports and never touches either.")
        if not re.fullmatch(r"COM\d{1,3}", port):
            raise Refused(f"{name}={port!r} is not a COM port name")
    return rx, tx


class RxOnlyPort:
    """Wraps a serial handle; exposes ``read`` and ``close`` ONLY."""

    __slots__ = ("_ser", "name")

    def __init__(self, ser: Any, name: str) -> None:
        self._ser, self.name = ser, name

    def read(self, n: int = 4096) -> bytes:
        if getattr(self._ser, "out_waiting", 0):
            raise Refused(f"{self.name}: bytes are queued for TRANSMIT on a listen-only port; stopping")
        return bytes(self._ser.read(n))

    def close(self) -> None:
        self._ser.close()


def open_rx_only(port: str, baud: int = DEFAULT_BAUD,
                 serial_factory: Optional[Callable[..., Any]] = None) -> RxOnlyPort:
    """Open ``port`` for reading with no flow control (so the driver sends nothing).
    ``serial_factory`` defaults to ``serial.Serial``; tests pass a fake."""
    if serial_factory is None:
        import serial  # local import: importing this module never needs pyserial
        serial_factory = serial.Serial
    if _norm(port) in REAL_ADAPTER_PORTS:      # belt and braces: also checked in check_guard
        raise Refused(f"{port} is the real adapter; never opened by the mirror listener")
    ser = serial_factory(port, baud, timeout=0.1, write_timeout=0,
                         xonxoff=False, rtscts=False, dsrdtr=False)
    # No TX: no software/hardware flow control that could make the driver emit bytes.
    for attr in ("xonxoff", "rtscts", "dsrdtr"):
        if getattr(ser, attr, False):
            ser.close()
            raise Refused(f"{port}: {attr} is enabled; refusing a port that could transmit by itself")
    return RxOnlyPort(ser, _norm(port))


def run(stop: threading.Event, *, vin: str = "", baud: int = DEFAULT_BAUD, bitrate: int = 500000,
        out_dir: Optional[Path] = None, env: Optional[dict[str, str]] = None,
        serial_factory: Optional[Callable[..., Any]] = None,
        mes_port: Optional[str] = None) -> dict[str, Any]:
    """Read both mirror ports until ``stop`` is set, then save and return the capture.

    ``out_dir`` is required: the caller chooses where the capture goes (the
    owner's run passes ``state_dir()/mes_learn/<vin>``; tests pass a scratch dir).
    """
    rx_name, tx_name = check_guard(env, mes_port)
    if out_dir is None:
        raise Refused("out_dir is required (state_dir()/mes_learn/<vin> for the owner's run)")
    rx = open_rx_only(rx_name, baud, serial_factory)
    tx = None
    try:
        tx = open_rx_only(tx_name, baud, serial_factory)
        parser = MirrorParser()
        started = datetime.now().isoformat(timespec="seconds")
        t0 = time.monotonic()
        while not stop.is_set():
            for direction, port in (("TX", tx), ("RX", rx)):
                chunk = port.read(4096)
                if chunk:
                    parser.feed(direction, chunk, time.monotonic() - t0)
        parser.close()
    finally:
        rx.close()
        if tx is not None:
            tx.close()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cap = to_capture(parser, port=f"{rx_name}+{tx_name}", bitrate=bitrate, vin=vin,
                     started_at=started, stopped_at=datetime.now().isoformat(timespec="seconds"))
    path = Path(out_dir) / f"{stamp}-mirror.jsonl"
    n = 1
    while path.exists():
        path = Path(out_dir) / f"{stamp}-mirror-{n}.jsonl"
        n += 1
    write_capture(cap, path)   # also auto-reviews: cap["verdict"], cap["review_file"]
    cap["file"] = str(path)
    return cap
