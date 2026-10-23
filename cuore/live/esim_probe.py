"""ESIM switch probe: a serial-input channel source (kind ``"probe"``).

The probe is a small microcontroller board that taps the ESIM switch signal
and the 5 V reference through high-impedance inputs and prints one line per
sample over USB serial. See ``docs/hardware/ESIM_SWITCH_PROBE.md`` for the
hardware, wiring and safety rules. This module is the host side only.

Line protocol, 115200 baud, 20 Hz, ASCII, one line per sample::

    ESIM,<ms>,<sig_mV>,<ref_mV>,<state>

``ms`` is the probe's own millisecond counter, ``sig_mV``/``ref_mV`` are the
tapped voltages in millivolts (already scaled back up past the input divider),
``state`` is ``CLOSED`` / ``OPEN`` / ``FAULT``. Lines that do not start with
``ESIM,`` (boot banners, ``#`` comments) are ignored.

State rules (one place, :func:`classify_state`; the firmware implements the
same rules and the host re-derives the state from the millivolts, so a
firmware bug or a corrupted state word cannot silently pass through)::

    CLOSED  sig < 800 mV  and ref > 4500 mV
    OPEN    sig > 4000 mV
    FAULT   anything else (open or low reference, wiring, in-between voltage)

Channels exposed (kind ``"probe"``, bus ``"probe"``): ``esim_switch_state``
(numeric code, 1 CLOSED / 0 OPEN / -1 FAULT, so it plots), ``esim_signal_mV``
and ``esim_ref_mV``.

Safety, enforced here:

* the probe port comes only from ``CUORE_ESIM_PROBE_PORT``; ``COM3`` (the
  OBD adapter) and whatever port the OBD adapter resolves to are refused;
* this module only ever READS from the probe port -- it never writes a byte;
* ``CUORE_ESIM_PROBE_PORT=sim`` replays a scripted open/closed trace and
  opens no port at all.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

from .errors import BadCommand, Refused

ENV_PORT = "CUORE_ESIM_PROBE_PORT"
#: Set to ``1`` when the connector turns out to have no separate 5 V reference
#: pin (two-wire switch). The reference is then not tapped and the state rule
#: ignores it. The doc explains how the owner decides this at the connector.
ENV_NO_REF = "CUORE_ESIM_PROBE_NO_REF"
SIM_PORT = "sim"
BAUD = 115200
SAMPLE_HZ = 20.0

CLOSED_SIG_MAX_MV = 800
CLOSED_REF_MIN_MV = 4500
OPEN_SIG_MIN_MV = 4000
STATES = ("CLOSED", "OPEN", "FAULT")
STATE_CODE = {"OPEN": 0, "CLOSED": 1, "FAULT": -1}

CH_STATE = "esim_switch_state"
CH_SIG = "esim_signal_mV"
CH_REF = "esim_ref_mV"
CHANNEL_IDS = (CH_STATE, CH_SIG, CH_REF)

#: Never opened as a probe port. The OBD adapter lives here.
FORBIDDEN_PORTS = frozenset({"COM3"})


class ProbeParseError(ValueError):
    """A line that looked like an ESIM sample but is malformed."""


@dataclass(frozen=True)
class ProbeSample:
    ms: int
    sig_mV: int
    ref_mV: int
    state: str          # as reported by the probe firmware


def classify_state(sig_mV: float, ref_mV: float, require_ref: bool = True) -> str:
    """The state the three rules give for one sample (see module docstring)."""
    if sig_mV < CLOSED_SIG_MAX_MV and (not require_ref or ref_mV > CLOSED_REF_MIN_MV):
        return "CLOSED"
    if sig_mV > OPEN_SIG_MIN_MV:
        return "OPEN"
    return "FAULT"


def parse_line(line: str) -> Optional[ProbeSample]:
    """One protocol line -> :class:`ProbeSample`.

    ``None`` for anything that is not an ESIM line (blank, ``#`` comment, boot
    banner). :class:`ProbeParseError` for an ``ESIM,`` line that is malformed
    (wrong field count, non-integer, negative or absurd millivolts, unknown
    state word).
    """
    text = (line or "").strip()
    if not text.startswith("ESIM,"):
        return None
    parts = text.split(",")
    if len(parts) != 5:
        raise ProbeParseError(f"expected 5 fields, got {len(parts)}: {text[:60]!r}")
    try:
        ms, sig, ref = int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError as e:
        raise ProbeParseError(f"non-integer field in {text[:60]!r}") from e
    state = parts[4].strip().upper()
    if state not in STATES:
        raise ProbeParseError(f"unknown state {parts[4]!r}")
    if ms < 0:
        raise ProbeParseError(f"negative ms in {text[:60]!r}")
    if not (-500 <= sig <= 30000 and -500 <= ref <= 30000):
        raise ProbeParseError(f"millivolts out of range in {text[:60]!r}")
    return ProbeSample(ms=ms, sig_mV=sig, ref_mV=ref, state=state)


# ===========================================================================
# channels
# ===========================================================================

def channels() -> list[Any]:
    """The three probe channels for the registry (``kind="probe"``)."""
    from .channels import Channel
    note = ("ESIM switch probe (serial, read-only; docs/hardware/ESIM_SWITCH_PROBE.md). "
            "Not an ECM reading: it is a separate meter tapped on the ESIM connector. "
            f"Needs {ENV_PORT} (a COM port other than COM3, or 'sim').")
    return [
        Channel(id=CH_STATE, name="ESIM switch state (1=CLOSED 0=OPEN -1=FAULT)", unit="state",
                kind="probe", bus="probe", confidence="probe", default_rate_hz=SAMPLE_HZ,
                note=note),
        Channel(id=CH_SIG, name="ESIM switch signal", unit="mV", kind="probe", bus="probe",
                confidence="probe", default_rate_hz=SAMPLE_HZ, note=note),
        Channel(id=CH_REF, name="ESIM 5 V reference", unit="mV", kind="probe", bus="probe",
                confidence="probe", default_rate_hz=SAMPLE_HZ, note=note),
    ]


# ===========================================================================
# configuration and its refusals
# ===========================================================================

def configured_port() -> str:
    """The raw ``CUORE_ESIM_PROBE_PORT`` value, stripped ('' when unset)."""
    return os.environ.get(ENV_PORT, "").strip()


def no_ref() -> bool:
    return os.environ.get(ENV_NO_REF, "").strip() in ("1", "true", "yes")


def validate_port(port: str) -> str:
    """Normalised port, or :class:`Refused` for the OBD adapter's port.

    ``sim`` is returned as ``"sim"``. Everything else is upper-cased. COM3 is
    refused outright; so is whatever port the OBD side resolves to.
    """
    p = (port or "").strip()
    if not p:
        raise BadCommand(f"{ENV_PORT} is not set")
    if p.lower() == SIM_PORT:
        return SIM_PORT
    norm = p.upper()
    if norm in FORBIDDEN_PORTS:
        raise Refused(f"{ENV_PORT}={p}: COM3 is the OBD adapter and is never used for the "
                      "ESIM probe; plug the probe into a different USB port")
    try:
        from .config import resolve_port
        obd, _src = resolve_port()
    except Exception:  # noqa: BLE001 -- config trouble must not block a refusal check
        obd = None
    if obd and obd.upper() == norm:
        raise Refused(f"{ENV_PORT}={p} is the OBD adapter's port; the probe needs its own port")
    return p


# ===========================================================================
# sources: simulator and serial
# ===========================================================================

#: Scripted trace for ``sim``: (label, seconds, signal mV, reference mV).
#: Open at rest, a clean close, a close with contact bounce (the wiggle test),
#: and a short wiring-fault stretch (reference lost). Loops forever.
SIM_SCRIPT: tuple[tuple[str, float, int, int], ...] = (
    ("open", 6.0, 4960, 5010),
    ("closed", 3.0, 140, 5005),
    ("open", 4.0, 4955, 5008),
    ("closed", 1.0, 150, 5004),
    ("bounce", 1.0, 0, 0),          # alternates open/closed every sample pair
    ("closed", 2.0, 145, 5006),
    ("open", 5.0, 4958, 5009),
    ("fault", 1.5, 40, 120),        # reference lost: signal low, reference low
    ("open", 4.0, 4962, 5011),
)


def sim_lines(loops: Optional[int] = None, hz: float = SAMPLE_HZ) -> Iterator[str]:
    """The scripted trace as protocol lines. ``loops=None`` repeats forever.

    Deterministic: a fixed few-mV ripple, no randomness. Timestamps advance
    exactly ``1000/hz`` ms per line; real-time pacing is the caller's job.
    """
    step_ms = 1000.0 / hz
    ms = 0.0
    n = 0
    done = 0
    while loops is None or done < loops:
        for label, secs, sig, ref in SIM_SCRIPT:
            for k in range(int(round(secs * hz))):
                ripple = (n % 5) - 2          # -2..+2 mV
                if label == "bounce":
                    s, r = (4950, 5005) if (k // 2) % 2 == 0 else (150, 5005)
                else:
                    s, r = sig + ripple, ref + ripple
                state = classify_state(s, r)
                yield f"ESIM,{int(ms)},{s},{r},{state}"
                ms += step_ms
                n += 1
        done += 1


class _SimSource:
    """Replays :func:`sim_lines` at 20 Hz in real time (or flat out if ``realtime`` is False)."""

    def __init__(self, loops: Optional[int] = None, realtime: bool = True) -> None:
        self._lines = sim_lines(loops)
        self._realtime = realtime
        self.describe = "sim"

    def lines(self, stop: threading.Event) -> Iterator[str]:
        period = 1.0 / SAMPLE_HZ
        nxt = time.monotonic()
        for line in self._lines:
            if stop.is_set():
                return
            yield line
            if self._realtime:
                nxt += period
                delay = nxt - time.monotonic()
                if delay > 0:
                    stop.wait(delay)


class _SerialSource:
    """Read-only line reader on a real COM port; reconnects if the probe is unplugged."""

    def __init__(self, port: str) -> None:
        self.port = port
        self.describe = f"serial {port}@{BAUD}"

    def lines(self, stop: threading.Event) -> Iterator[str]:
        import serial  # pyserial; imported lazily so the simulator needs nothing
        while not stop.is_set():
            try:
                with serial.Serial(self.port, BAUD, timeout=0.5) as ser:
                    while not stop.is_set():
                        raw = ser.readline()
                        if raw:
                            yield raw.decode("ascii", errors="replace")
                        else:
                            yield ""      # timeout: lets the feed notice silence
            except (OSError, serial.SerialException):
                yield ""
                stop.wait(2.0)


def make_source(port: str, realtime: bool = True):
    p = validate_port(port)
    return _SimSource(realtime=realtime) if p == SIM_PORT else _SerialSource(p)


# ===========================================================================
# the feed: source -> poller channels
# ===========================================================================

SILENCE_S = 1.5     # no valid line this long = "no data from probe"


class ProbeFeed:
    """Reads a source on a thread and publishes the three channels into a poller.

    ``publish(channel_id, value, unit)`` and ``miss(channel_id, text)`` are the
    poller's :meth:`_publish` / :meth:`_note_miss`; ``on_transition(state)`` is
    called when the (host-derived) state changes; ``on_sample()`` after the
    three channels of a sample are published (the poller writes a CSV row
    there, so a recording carries the probe at its own rate).
    """

    def __init__(self, source, wanted: set[str],
                 publish: Callable[[str, Any, str], None],
                 miss: Callable[[str, str], None],
                 on_transition: Optional[Callable[[str], None]] = None,
                 on_sample: Optional[Callable[[], None]] = None) -> None:
        self.source = source
        self.wanted = wanted
        self._publish = publish
        self._miss = miss
        self._on_transition = on_transition
        self._on_sample = on_sample
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.samples = 0
        self.bad_lines = 0
        self.state_mismatches = 0
        self.transitions = 0
        self.last_state: Optional[str] = None
        self.last_error = ""

    def handle_line(self, line: str) -> bool:
        """Process one raw line. True if a sample was published."""
        try:
            s = parse_line(line)
        except ProbeParseError as e:
            self.bad_lines += 1
            self.last_error = str(e)
            return False
        if s is None:
            return False
        state = classify_state(s.sig_mV, s.ref_mV, require_ref=not no_ref())
        if state != s.state:
            self.state_mismatches += 1
        self.samples += 1
        if CH_STATE in self.wanted:
            self._publish(CH_STATE, STATE_CODE[state], "state")
        if CH_SIG in self.wanted:
            self._publish(CH_SIG, float(s.sig_mV), "mV")
        if CH_REF in self.wanted:
            self._publish(CH_REF, float(s.ref_mV), "mV")
        if state != self.last_state:
            if self.last_state is not None:
                self.transitions += 1
            prev, self.last_state = self.last_state, state
            if self._on_transition is not None and prev is not None:
                self._on_transition(state)
        if self._on_sample is not None:
            self._on_sample()
        return True

    def _run(self) -> None:
        last_ok = time.monotonic()
        try:
            for line in self.source.lines(self._stop):
                if self.handle_line(line):
                    last_ok = time.monotonic()
                elif time.monotonic() - last_ok > SILENCE_S:
                    for cid in self.wanted:
                        self._miss(cid, "no data from ESIM probe")
                    last_ok = time.monotonic()
        except Exception as e:  # noqa: BLE001 -- reported through status()
            self.last_error = f"{type(e).__name__}: {e}"
            for cid in self.wanted:
                self._miss(cid, self.last_error)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="cuore-esim-probe", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=3)

    def status(self) -> dict[str, Any]:
        return {"source": getattr(self.source, "describe", ""), "samples": self.samples,
                "bad_lines": self.bad_lines, "state_mismatches": self.state_mismatches,
                "transitions": self.transitions, "state": self.last_state,
                "last_error": self.last_error, "require_ref": not no_ref()}


__all__ = ["ENV_PORT", "ENV_NO_REF", "SIM_PORT", "BAUD", "SAMPLE_HZ", "CHANNEL_IDS",
           "CH_STATE", "CH_SIG", "CH_REF", "STATE_CODE", "ProbeSample", "ProbeParseError",
           "ProbeFeed", "SIM_SCRIPT", "channels", "classify_state", "parse_line",
           "validate_port", "make_source", "sim_lines", "configured_port", "no_ref"]
