"""Parser for MES ``FESLog_YYMMDDHHMM_<vehicle>.txt`` engineering sessions.

A FES log is a transcript of one MES session against one ECU: identity header,
then any sequence of error reads, clears, actuator tests, adjustments and live
parameter samples.

What this parser does that reading the file by eye does not
-----------------------------------------------------------
**It models clear events.** The single highest-signal fact in the whole corpus
is a code that was read, erased, and set again before the session ended -- that
is a hard fault reproducing on demand. A flat "these codes were in the file"
extraction reports it identically to a code that was cleared and stayed gone,
which is close to the opposite conclusion. :class:`FesLog` tracks the order of
``READING ERROR CODES:`` and ``CLEARING STORED FAULT CODES...`` sections and
assigns each code a :class:`~mes.dtc.DtcStatus` accordingly.

**It keeps freeze frames.** Every DTC carries ~25 labelled parameters. Parsing
them turns "what were the conditions when this set?" from a manual file read
into a field lookup.

Format hazards handled here, all observed in the corpus
-------------------------------------------------------
* The preamble is **not always at line 1** -- four files open with a CAN/PROXI
  prologue and one has a stray ``1``. We scan for ``(Multiecuscan `` instead.
* **One file can hold several sessions** (multiple version headers), so all
  header positions are found and the file splits on them.
* Header key *order and set* vary by ECU family (14 shapes observed), so the
  header is an ordered list, never fixed offsets.
* A DTC freeze frame ends with a line of **exactly two spaces**, not an empty
  line. Trailing whitespace is load-bearing elsewhere too: an empty unit slot
  shows up as a trailing space, so values are split before any strip.
* Live parameter blocks have a **growing schema and duplicate keys** (``Engine
  oil pressure`` appears as both an enum and a bar value in the same block), so
  samples are ordered lists, not dicts.
* An operation may have **no outcome line at all**, and one file has an orphan
  ``COMPLETED`` with no preceding banner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import encoding, paths
from .dtc import Dtc, DtcStatus
from .params import ParamValue, ParamSeries, parse_kv_line, parse_value

VERSION_RE = re.compile(r"^\((Multiecuscan[^)]*)\)\s*$", re.I)
DATE_RE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*[AP]M)\s*$",
                     re.I)
SEPARATOR_RE = re.compile(r"^-{10,}\s*$")
SIMULATION_MARK = "SIMULATION MODE"

READ_ERRORS = "READING ERROR CODES:"
READ_PARAMS = "READING PARAMETERS:"
CLEARING_RE = re.compile(r"^CLEARING STORED FAULT CODES\s*\.{0,3}\s*$", re.I)
EXEC_RE = re.compile(r"^EXECUTING (ACTUATOR|ADJUSTMENT)\s*\.{0,3}\s*$", re.I)
CAN_READ_RE = re.compile(r"^Reading CAN configuration data\s*\.{0,3}\s*$", re.I)
CAN_DATA = "CAN CONFIGURATION DATA:"
ERROR_DETAILS = "ERROR DETAILS:"
NO_FAULTS = "No fault codes"
COMPLETED = "COMPLETED"
FAILED_EXEC = "FAILED TO EXECUTE"

#: ``1. P0455-00 - Evaporation system leak`` -- description optional.
DTC_ENTRY_RE = re.compile(
    r"^(?P<index>\d+)\.\s+(?P<code>[PBCU][0-9A-F]{4})(?:-(?P<ftb>[0-9A-F]{2}))?"
    r"(?:\s+-\s+(?P<desc>.+?))?\s*$"
)
STATUS_RE = re.compile(r"^Status:\s*(.*?)\s*$", re.I)
OLD_VALUE_RE = re.compile(r"^Old value:\s*(.*?)\s*$", re.I)
NEW_VALUE_RE = re.compile(r"^New value:\s*(.*?)\s*$", re.I)
#: PROXI node roster lines: ``Body Computer Node (BCM/NBC): EOL Ok``
NODE_RE = re.compile(r"^(?P<node>.+?\([^)]*\)):\s*(?P<status>.+?)\s*$")

#: Header keys that carry an ECU identity rather than a measurement.
IDENTITY_KEYS = (
    "ECU ISO code", "VIN code", "VIN code (original)", "ECU serial number",
    "Spare part number", "Hardware number", "Hardware version",
    "Software number", "Software version", "Homologation number",
    "FIAT drawing number", "ECU programming date",
)

#: Simulation-mode fingerprints, used only to corroborate the banner.
SIM_FINGERPRINTS = {"7C 86 4F FF FF", "5188214", "55188214", "281011421"}


@dataclass
class ActuatorRun:
    """One ``EXECUTING ACTUATOR/ADJUSTMENT`` block."""

    kind: str                      # "actuator" | "adjustment"
    operation: str = ""
    outcome: str = ""              # "COMPLETED" | "FAILED TO EXECUTE" | ""
    reason: str = ""               # the interlock reason on a failure
    status: str = ""               # "00" | "UNKNOWN" | ""
    old_value: str = ""
    new_value: str = ""
    line_number: int = 0

    @property
    def succeeded(self) -> bool:
        return self.outcome == COMPLETED

    @property
    def failed(self) -> bool:
        return self.outcome == FAILED_EXEC

    @property
    def inconclusive(self) -> bool:
        """No outcome was ever written -- MES closed before the call returned."""
        return not self.outcome

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kind": self.kind,
            "operation": self.operation,
            "outcome": self.outcome or "(none recorded)",
        }
        if self.reason:
            d["reason"] = self.reason
        if self.status:
            d["status"] = self.status
        if self.old_value or self.new_value:
            d["old_value"] = self.old_value
            d["new_value"] = self.new_value
        if self.inconclusive:
            d["note"] = ("no outcome line was written - the session ended "
                         "before the operation returned")
        return d


@dataclass
class ParamSample:
    """One ``READING PARAMETERS:`` block.

    Values are an ordered list, not a dict: a single block can carry the same
    key twice with different units (``Engine oil pressure`` as both ``Low`` and
    ``2.20 bar``), and a dict would silently drop one.
    """

    values: list[ParamValue] = field(default_factory=list)
    line_number: int = 0

    def get(self, name: str, unit: str = "") -> ParamValue | None:
        low = name.lower()
        for v in self.values:
            if v.name.lower() == low and (not unit or v.unit == unit):
                return v
        return None

    @property
    def names(self) -> list[str]:
        return [v.name for v in self.values]


@dataclass
class FesLog:
    """A parsed MES engineering session."""

    path: Path
    name: str
    timestamp: str = ""            # from the filename (save time)
    encoding_used: str = ""
    size_bytes: int = 0
    control_chars: int = 0

    mes_version: str = ""
    session_time: str = ""         # from the file content (session start)
    vehicle: str = ""
    ecu_description: str = ""
    simulation: bool = False

    header: list[tuple[str, str]] = field(default_factory=list)
    nodes: list[tuple[str, str]] = field(default_factory=list)
    dtcs: list[Dtc] = field(default_factory=list)
    actuators: list[ActuatorRun] = field(default_factory=list)
    samples: list[ParamSample] = field(default_factory=list)
    read_sections: int = 0
    clear_events: int = 0
    reported_no_faults: bool = False
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    # -- identity ---------------------------------------------------------

    def head(self, key: str) -> str:
        low = key.lower()
        for k, v in self.header:
            if k.lower() == low:
                return v
        return ""

    @property
    def vin(self) -> str:
        return self.head("VIN code")

    @property
    def odometer_km(self) -> float | None:
        """Best odometer reading available, header first then freeze frames."""
        raw = self.head("Odometer")
        if raw:
            pv = parse_value("Odometer", raw)
            if pv.number is not None:
                return pv.number
        best: float | None = None
        for d in self.dtcs:
            pv = d.freeze("Odometer")
            if pv and pv.number is not None:
                best = pv.number if best is None else max(best, pv.number)
        return best

    @property
    def identity(self) -> dict[str, str]:
        return {k: v for k, v in self.header if k in IDENTITY_KEYS and v}

    @property
    def sim_fingerprints(self) -> list[str]:
        """Simulation tell-tales found in identity fields.

        Reported alongside the banner so a log that *looks* fake but is not
        marked -- or vice versa -- is visible rather than silently trusted.
        """
        hits = []
        for _k, v in self.header:
            if v.strip() in SIM_FINGERPRINTS:
                hits.append(v.strip())
        return hits

    # -- derived ----------------------------------------------------------

    @property
    def returned_after_clear(self) -> list[Dtc]:
        """Codes that came back after being erased in this same session."""
        return [d for d in self.dtcs if d.status is DtcStatus.RETURNED]

    @property
    def cleared(self) -> list[Dtc]:
        return [d for d in self.dtcs if d.status is DtcStatus.CLEARED]

    @property
    def stored(self) -> list[Dtc]:
        return [d for d in self.dtcs if d.status is DtcStatus.STORED]

    @property
    def failed_actuators(self) -> list[ActuatorRun]:
        return [a for a in self.actuators if a.failed]

    def series(self, name: str) -> ParamSeries:
        """Assemble one live parameter into a time-ordered series.

        There are no per-sample timestamps in the format, so ordering is file
        order and the sampling rate is unrecoverable. Stamps are sample
        indices, labelled as such.
        """
        out = ParamSeries(name=name)
        for i, sample in enumerate(self.samples):
            v = sample.get(name)
            if v is not None:
                out.add(v, stamp=f"sample {i + 1}")
        return out

    def param_names(self) -> list[str]:
        """Union of every parameter name across all samples, in first-seen order."""
        seen: dict[str, None] = {}
        for s in self.samples:
            for v in s.values:
                seen.setdefault(v.name, None)
        return list(seen)

    def to_dict(self, *, include_freeze: bool = True,
                include_samples: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "file": self.name,
            "kind": "fes",
            "timestamp": self.timestamp,
            "session_time": self.session_time,
            "mes_version": self.mes_version,
            "vehicle": self.vehicle,
            "ecu": self.ecu_description,
            "vin": self.vin,
            "encoding": self.encoding_used,
            "size_bytes": self.size_bytes,
            "simulation": self.simulation,
            "identity": self.identity,
            "dtc_count": len(self.dtcs),
            "read_sections": self.read_sections,
            "clear_events": self.clear_events,
            "reported_no_faults": self.reported_no_faults,
            "actuator_runs": len(self.actuators),
            "param_samples": len(self.samples),
        }
        if self.simulation:
            d["warning"] = "SIMULATION MODE - this data is not from a vehicle"
        if self.sim_fingerprints:
            d["simulation_fingerprints"] = self.sim_fingerprints
        odo = self.odometer_km
        if odo is not None:
            d["odometer_km"] = odo
        if self.dtcs:
            d["dtcs"] = [x.to_dict(include_freeze=include_freeze)
                         for x in self.dtcs]
        if self.actuators:
            d["actuators"] = [a.to_dict() for a in self.actuators]
        if self.nodes:
            d["proxi_nodes"] = [{"node": n, "status": s} for n, s in self.nodes]
        if self.samples:
            d["parameters_available"] = self.param_names()
            if include_samples:
                d["samples"] = [[v.to_dict() for v in s.values]
                                for s in self.samples]
        if self.control_chars:
            d["stray_control_bytes"] = self.control_chars
        if self.truncated:
            d["truncated"] = True
        if self.warnings:
            d["warnings"] = self.warnings
        return d


# --- parsing --------------------------------------------------------------


def _is_blank(line: str) -> bool:
    return not line.strip()


def _freeze_terminator(line: str) -> bool:
    """A freeze frame ends on a whitespace-only line (canonically two spaces)."""
    return line.strip() == ""


def parse_fes_text(text: str, *, name: str = "", path: Path | None = None,
                   timestamp: str = "") -> FesLog:
    """Parse FES session text into a :class:`FesLog`."""
    lines = text.splitlines()
    log = FesLog(path=path or Path(name), name=name, timestamp=timestamp)
    log.simulation = SIMULATION_MARK in text

    # Locate the preamble by content, never by line number: four files open
    # with a CAN/PROXI prologue and one has a stray leading line.
    header_positions = [i for i, l in enumerate(lines) if VERSION_RE.match(l)]
    if not header_positions:
        log.warnings.append(
            "no '(Multiecuscan ...)' preamble found - file may be truncated "
            "or not a FES log")
        start = 0
    else:
        if len(header_positions) > 1:
            log.warnings.append(
                f"{len(header_positions)} MES session headers in one file; "
                "identity taken from the first, events merged across all")
        first = header_positions[0]
        m = VERSION_RE.match(lines[first])
        log.mes_version = m.group(1).strip() if m else ""
        idx = first + 1
        # Date, vehicle and ECU follow, but a simulation banner may sit
        # between them, so consume tolerantly rather than by fixed offset.
        seen: list[str] = []
        while idx < len(lines) and len(seen) < 3:
            raw = lines[idx].strip()
            idx += 1
            if not raw or SEPARATOR_RE.match(raw):
                break
            if SIMULATION_MARK in raw:
                continue
            seen.append(raw)
        if seen and DATE_RE.match(seen[0]):
            log.session_time = _iso_session_time(seen[0])
            seen = seen[1:]
        if seen:
            log.vehicle = seen[0]
        if len(seen) > 1:
            log.ecu_description = seen[1]
        start = idx

    _parse_body(lines, start, log)
    _assign_statuses(log)
    for d in log.dtcs:
        d.source_file = name
        d.timestamp = timestamp
        if not d.module:
            d.module = log.ecu_description
    return log


def _iso_session_time(raw: str) -> str:
    """``6/7/2026 10:03:48 AM`` -> ISO. Falls back to the raw text.

    The US format holds for every file on this machine, but MES formats with
    the Windows locale, so a non-US install will differ. Returning the raw
    string beats raising or silently mis-parsing a day/month swap.
    """
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S",
                "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(raw.strip(), fmt).isoformat(sep=" ")
        except ValueError:
            continue
    return raw.strip()


def _parse_body(lines: list[str], start: int, log: FesLog) -> None:
    """Walk the session body, dispatching on section banners."""
    i = start
    n = len(lines)
    in_header = True
    #: read section index -> how many clears preceded it
    read_events: list[tuple[int, list[Dtc]]] = []

    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if _is_blank(line):
            if in_header and log.header:
                in_header = False
            i += 1
            continue

        # A second embedded session header: reset the header state but keep
        # accumulating events into the same log.
        if VERSION_RE.match(line):
            in_header = True
            i += 1
            continue
        if SEPARATOR_RE.match(line) or SIMULATION_MARK in stripped:
            i += 1
            continue

        if stripped == READ_ERRORS:
            i, found = _parse_dtc_section(lines, i + 1, log)
            log.read_sections += 1
            read_events.append((log.clear_events, found))
            in_header = False
            continue

        if CLEARING_RE.match(stripped):
            log.clear_events += 1
            in_header = False
            i += 1
            continue

        m = EXEC_RE.match(stripped)
        if m:
            i = _parse_actuator(lines, i, m.group(1).lower(), log)
            in_header = False
            continue

        if stripped == READ_PARAMS:
            i = _parse_param_block(lines, i + 1, log)
            in_header = False
            continue

        if CAN_READ_RE.match(stripped) or stripped == CAN_DATA:
            i += 1
            continue

        if stripped == COMPLETED:
            # Orphan outcome with no preceding banner (one file does this).
            if log.actuators and not log.actuators[-1].outcome:
                log.actuators[-1].outcome = COMPLETED
            else:
                log.warnings.append(
                    f"orphan COMPLETED at line {i + 1} with no preceding "
                    "EXECUTING banner")
            i += 1
            continue

        if in_header:
            i = _parse_header_line(lines, i, log)
            continue

        i += 1

    log._read_events = read_events  # type: ignore[attr-defined]


def _parse_header_line(lines: list[str], i: int, log: FesLog) -> int:
    """Header entries, including the PROXI node roster and the WARNING pseudo-key."""
    stripped = lines[i].strip()

    if stripped.upper().startswith("WARNING:"):
        log.warnings.append(stripped)
        return i + 1

    node = NODE_RE.match(stripped)
    if node and "Node" in node.group("node") or (node and "(" in node.group("node")
                                                 and "Radio" in node.group("node")):
        log.nodes.append((node.group("node").strip(),
                          node.group("status").strip()))
        return i + 1

    if ":" in stripped:
        key, _, value = stripped.partition(":")
        # Header values keep meaningful leading/trailing spaces in some ECU
        # serial fields; strip only the single separator space.
        log.header.append((key.strip(), value[1:] if value.startswith(" ")
                           else value))
        return i + 1

    return i + 1


def _parse_dtc_section(lines: list[str], i: int,
                       log: FesLog) -> tuple[int, list[Dtc]]:
    """Parse one ``READING ERROR CODES:`` section, returning (next_i, dtcs)."""
    found: list[Dtc] = []
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            # A blank line ends the section only once we have left the last
            # freeze frame; the terminator is itself whitespace-only, so peek
            # ahead for a following numbered entry before stopping.
            nxt = _next_nonblank(lines, i + 1)
            if nxt is not None and DTC_ENTRY_RE.match(lines[nxt].strip()):
                i = nxt
                continue
            return i + 1, found

        if stripped == NO_FAULTS:
            log.reported_no_faults = True
            return i + 1, found

        m = DTC_ENTRY_RE.match(stripped)
        if m:
            dtc = Dtc(
                code=m.group("code").upper(),
                ftb=(m.group("ftb") or "").upper() or None,
                description=(m.group("desc") or "").strip(),
                index=int(m.group("index")),
                module=log.ecu_description,
            )
            i = _parse_freeze_frame(lines, i + 1, dtc)
            found.append(dtc)
            log.dtcs.append(dtc)
            continue

        # Any other banner ends the section.
        if (stripped == READ_ERRORS or stripped == READ_PARAMS
                or CLEARING_RE.match(stripped) or EXEC_RE.match(stripped)):
            return i, found

        i += 1

    return i, found


def _parse_freeze_frame(lines: list[str], i: int, dtc: Dtc) -> int:
    """Consume the indented freeze frame beneath a DTC entry."""
    n = len(lines)
    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        if not stripped:
            return i + 1                      # the two-space terminator
        if DTC_ENTRY_RE.match(stripped):
            return i                          # next DTC, no terminator seen
        if stripped == ERROR_DETAILS:
            i += 1
            continue
        if not raw.startswith(" "):
            return i                          # unindented -> section ended

        pv = parse_kv_line(raw)
        if pv is not None:
            dtc.freeze_frame[pv.name] = pv
        i += 1
    return i


def _parse_actuator(lines: list[str], i: int, kind: str, log: FesLog) -> int:
    """Parse an ``EXECUTING ACTUATOR/ADJUSTMENT`` block.

    The operation name is identified *positionally* (the line after the
    banner) because case is not a reliable signal -- most names are sentence
    case but ``PROXI ALIGNMENT PROCEDURE`` and ``NEXT SERVICE KM RESET`` are
    all-caps and would otherwise look like banners.
    """
    run = ActuatorRun(kind=kind, line_number=i + 1)
    log.actuators.append(run)
    i += 1
    n = len(lines)

    if i < n and lines[i].strip():
        run.operation = lines[i].strip()
        i += 1

    while i < n:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            if run.outcome:
                break
            continue
        if EXEC_RE.match(stripped) or stripped in (READ_ERRORS, READ_PARAMS) \
                or CLEARING_RE.match(stripped) or VERSION_RE.match(stripped):
            break

        m = OLD_VALUE_RE.match(stripped)
        if m:
            run.old_value = m.group(1)
            i += 1
            continue
        m = NEW_VALUE_RE.match(stripped)
        if m:
            run.new_value = m.group(1)
            i += 1
            continue
        m = STATUS_RE.match(stripped)
        if m and run.outcome:
            run.status = m.group(1)
            i += 1
            continue

        if stripped == COMPLETED:
            run.outcome = COMPLETED
            i += 1
            continue
        if stripped == FAILED_EXEC:
            run.outcome = FAILED_EXEC
            i += 1
            if i < n and lines[i].strip():
                run.reason = lines[i].strip()
                i += 1
            continue

        break

    return i


def _parse_param_block(lines: list[str], i: int, log: FesLog) -> int:
    """Parse one ``READING PARAMETERS:`` sample block."""
    sample = ParamSample(line_number=i)
    n = len(lines)
    while i < n:
        raw = lines[i]
        if not raw.strip():
            break
        if raw.strip() in (READ_PARAMS, READ_ERRORS) or EXEC_RE.match(raw.strip()):
            break
        pv = parse_kv_line(raw)
        if pv is not None:
            sample.values.append(pv)
        i += 1
    if sample.values:
        log.samples.append(sample)
    return i


def _next_nonblank(lines: list[str], i: int) -> int | None:
    while i < len(lines):
        if lines[i].strip():
            return i
        i += 1
    return None


def _assign_statuses(log: FesLog) -> None:
    """Assign a :class:`DtcStatus` to every DTC from the session's event order.

    This is the point of the module. A code seen only before any clear, with a
    clear afterwards, was erased. A code seen in a read that follows a clear
    came *back* -- the fault is live and reproducing. Without the ordering,
    both look like "present in the log".
    """
    events: list[tuple[int, list[Dtc]]] = getattr(log, "_read_events", [])
    if not events:
        for d in log.dtcs:
            d.status = DtcStatus.STORED
        return

    post_clear_codes: set[str] = set()
    pre_clear_codes: set[str] = set()
    for clears_before, dtcs in events:
        for d in dtcs:
            (post_clear_codes if clears_before > 0 else pre_clear_codes).add(d.full)

    any_clear = log.clear_events > 0
    for clears_before, dtcs in events:
        for d in dtcs:
            if clears_before > 0:
                d.status = DtcStatus.RETURNED
            elif any_clear and d.full not in post_clear_codes:
                d.status = DtcStatus.CLEARED
            else:
                d.status = DtcStatus.STORED


def load_fes(path: Path, *, timestamp: str = "") -> FesLog:
    """Read and parse a FES log from disk."""
    decoded = encoding.read_log_text(path)
    log = parse_fes_text(decoded.text, name=path.name, path=path,
                         timestamp=timestamp)
    log.encoding_used = decoded.encoding
    log.size_bytes = decoded.size_bytes
    log.control_chars = decoded.control_chars
    return log


def load_fes_by_name(name: str, *, timestamp: str = "") -> FesLog:
    return load_fes(paths.resolve_log(name), timestamp=timestamp)
