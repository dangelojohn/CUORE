"""Parser for MES ``SCAN_YYMMDDHHMM.txt`` all-systems scan logs.

Format notes that drive the design
----------------------------------
A SCAN file is not a document. It is an append-only transcript of the "Scan
vehicle" panel, so the same module is commonly dumped two or three times in one
file (live scan, then the formatted VEHICLE SCAN REPORT, then once per clear
operation), and the phase order varies between files. Four distinct orderings
appear across this corpus and half the files have no report section at all, so
nothing here assumes a fixed sequence.

Three consequences, each of which is a trap worth naming:

* **Counting ``ISO Code:`` lines over-counts modules by 2-3x.** One file has 21
  of them for 8 physical modules. Dedup per phase.
* **The report phase is a fresh re-read, not a copy of the first scan.** When a
  clear runs between them the two phases legitimately disagree, and which one
  you want depends on the question: "what was wrong" is the scan phase, "what
  survived the clear" is the report phase.
* **Blank-line splitting is unsafe.** Runs of up to five blank lines occur, and
  clear-result blocks are shaped like module blocks for their first three
  lines. So we anchor on the ``ISO Code:`` line, which across 122 occurrences
  in this corpus always sits exactly two lines below its heading, and walk
  backwards.

A clean module has no status line at all -- the absence of ``Errors found:`` is
the only "no faults" signal MES gives. A module that does not answer is simply
omitted, so a SCAN log cannot distinguish "not fitted" from "not responding".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import encoding, paths
from .dtc import Dtc, DtcStatus

# --- line grammar ---------------------------------------------------------

ISO_CODE_RE = re.compile(r"^ISO Code:\s*((?:[0-9A-F]{2}\s+){4}[0-9A-F]{2})\s*$")
HEADING_RE = re.compile(r"^(?P<category>[^/]+?)\s+/\s+(?P<abbrev>.+?)"
                        r"(?:\s*\((?P<long>[^)]*)\))?\s*$")
VIN_RE = re.compile(r"^VIN code:\s*(.+?)\s*$")
HW_RE = re.compile(r"^Hardware number:\s*(.+?)\s*$")
SW_RE = re.compile(r"^Software number:\s*(.+?)\s*$")
#: Hardware/software values end with " - Ver: xxxx", but the value itself may
#: contain " - " and internal double spaces, so the split binds to the LAST
#: occurrence.
VER_SPLIT_RE = re.compile(r"^(.*)\s+-\s+Ver:\s*(\S+)\s*$")

#: ``CODE-FTB`` with the description tail optional: inside a FAILED clear block
#: MES prints codes bare.
DTC_LINE_RE = re.compile(
    r"^(?P<code>[PBCU][0-9A-F]{4})-(?P<ftb>[0-9A-F]{2})"
    r"(?:\s+-\s+(?P<desc>.+?))?\s*$"
)

ERRORS_FOUND = "Errors found:"
BANNER_RE = re.compile(r"^\*{10,}\s*$")
#: MES is inconsistent about the ellipsis: both "CLEARING STORED FAULT CODES..."
#: and the bare form appear, sometimes in the same file.
CLEARING_RE = re.compile(r"^CLEARING STORED FAULT CODES\s*\.{0,3}\s*$", re.I)
SCANNING_RE = re.compile(r"^Scanning\s*\.{0,3}\s*$", re.I)
SENDING_RE = re.compile(r"^SENDING DIAGNOSTIC REPORT\s*\.{0,3}\s*$", re.I)
REPORT_TITLE = "VEHICLE SCAN REPORT"
CONNECTION_FAILED = "Connection failed!"
META_RE = re.compile(r"^VEHICLE (MAKE|MODEL|YEAR):\s*(.*?)\s*$")

#: Not a status line. This occupies the ECU-description slot and means MES
#: talked to the ECU fine but has no name for it in its database.
UNKNOWN_ECU = "UNKNOWN/UNSUPPORTED"

PHASE_SCAN = "scan"
PHASE_REPORT = "report"
PHASE_CLEAR = "clear"


@dataclass
class ModuleEntry:
    """One ECU as printed in one phase of a SCAN transcript."""

    category: str = ""
    abbrev: str = ""
    long_name: str = ""
    ecu_description: str = ""
    iso_code: str = ""
    vin: str = ""
    hardware: str = ""
    hardware_version: str = ""
    software: str = ""
    software_version: str = ""
    phase: str = PHASE_SCAN
    #: "SUCCESS" / "FAILED" -- only meaningful in the clear phase.
    clear_result: str = ""
    dtcs: list[Dtc] = field(default_factory=list)
    line_number: int = 0

    @property
    def key(self) -> str:
        """Stable identity for a module.

        ISO code first: it is the only field repeated in every phase, and it
        survives the MES database renaming BCM from "Body Control Module" to
        "Body Computer Module" between versions. Keying on the printed heading
        would split one physical ECU into two.
        """
        return self.iso_code or f"{self.category}/{self.abbrev}"

    @property
    def name(self) -> str:
        base = f"{self.category} / {self.abbrev}" if self.category else self.abbrev
        return f"{base} ({self.long_name})" if self.long_name else base

    @property
    def ecu_named(self) -> bool:
        return bool(self.ecu_description) and self.ecu_description != UNKNOWN_ECU

    @property
    def clean(self) -> bool:
        return not self.dtcs

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.name,
            "category": self.category,
            "abbrev": self.abbrev,
            "long_name": self.long_name,
            "ecu": self.ecu_description,
            "ecu_named": self.ecu_named,
            "iso_code": self.iso_code,
            "vin": self.vin,
            "hardware": self.hardware,
            "hardware_version": self.hardware_version,
            "software": self.software,
            "software_version": self.software_version,
            "phase": self.phase,
            "clear_result": self.clear_result,
            "dtc_count": len(self.dtcs),
            "dtcs": [d.to_dict() for d in self.dtcs],
        }


@dataclass
class ScanLog:
    """A parsed all-systems scan transcript."""

    path: Path
    name: str
    timestamp: str = ""
    encoding_used: str = ""
    size_bytes: int = 0
    vin: str = ""
    vin_conflicts: list[str] = field(default_factory=list)
    make: str = ""
    model: str = ""
    year: str = ""
    entries: list[ModuleEntry] = field(default_factory=list)
    phases_seen: list[str] = field(default_factory=list)
    connection_failures: int = 0

    @property
    def provenance(self) -> str:
        """Why a SCAN log's authenticity can never be confirmed from content.

        FES logs announce simulation mode on line 5. SCAN logs have no header
        at all and no marker anywhere, so a simulated scan would be
        byte-indistinguishable from a real one, plausible VIN included.
        Callers must treat scan provenance as unknown, never as confirmed-real.
        """
        return "unverifiable - SCAN logs carry no simulation marker"

    @property
    def aborted(self) -> bool:
        """True for a scan that never reached a module (adapter not connected)."""
        return not self.entries and self.connection_failures > 0

    def phase_entries(self, phase: str) -> list[ModuleEntry]:
        """Deduplicated modules for one phase, first occurrence winning."""
        out: list[ModuleEntry] = []
        seen: set[str] = set()
        for e in self.entries:
            if e.phase != phase or e.key in seen:
                continue
            seen.add(e.key)
            out.append(e)
        return out

    @property
    def modules(self) -> list[ModuleEntry]:
        """Modules as first found -- the "what was wrong" view."""
        primary = self.phase_entries(PHASE_SCAN)
        return primary or self.phase_entries(PHASE_REPORT)

    @property
    def post_clear_modules(self) -> list[ModuleEntry]:
        """Modules as re-read after clearing, when the file has a report phase."""
        return self.phase_entries(PHASE_REPORT)

    @property
    def all_dtcs(self) -> list[Dtc]:
        out: list[Dtc] = []
        for e in self.modules:
            out.extend(e.dtcs)
        return out

    @property
    def clear_results(self) -> list[ModuleEntry]:
        return [e for e in self.entries if e.phase == PHASE_CLEAR]

    def to_dict(self, *, include_modules: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "file": self.name,
            "kind": "scan",
            "timestamp": self.timestamp,
            "vin": self.vin,
            "make": self.make,
            "model": self.model,
            "year": self.year,
            "encoding": self.encoding_used,
            "size_bytes": self.size_bytes,
            "phases": self.phases_seen,
            "aborted": self.aborted,
            "connection_failures": self.connection_failures,
            "module_count": len(self.modules),
            "fault_module_count": sum(1 for m in self.modules if m.dtcs),
            "dtc_count": len(self.all_dtcs),
            "provenance": self.provenance,
        }
        if self.vin_conflicts:
            d["vin_conflicts"] = self.vin_conflicts
        if include_modules:
            d["modules"] = [m.to_dict() for m in self.modules]
            if self.post_clear_modules:
                d["post_clear_modules"] = [m.to_dict()
                                           for m in self.post_clear_modules]
            if self.clear_results:
                d["clear_results"] = [
                    {"module": m.name, "iso_code": m.iso_code,
                     "result": m.clear_result,
                     "uncleared": [x.full for x in m.dtcs]}
                    for m in self.clear_results
                ]
        return d


def _split_ver(value: str) -> tuple[str, str]:
    m = VER_SPLIT_RE.match(value)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return value.strip(), ""


def _parse_heading(line: str) -> tuple[str, str, str]:
    """``Gearbox / TCM/NCA/NCR (Automatic Transmission)`` -> the three parts.

    The abbreviation may itself contain slashes, so the split binds to the
    first ``" / "`` only. The parenthetical is optional: ``Engine / ECM`` has
    none, and a DTC description can contain ``" / "`` too, which is why
    heading detection never keys on the slash alone.
    """
    m = HEADING_RE.match(line.strip())
    if not m:
        return "", line.strip(), ""
    return (m.group("category").strip(),
            m.group("abbrev").strip(),
            (m.group("long") or "").strip())


def _iter_blocks(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Yield ``(line_index, phase)`` for each ISO-Code-anchored module block."""
    phase = PHASE_SCAN
    saw_report = False
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if CLEARING_RE.match(line):
            phase = PHASE_CLEAR
            continue
        if line.strip() == REPORT_TITLE:
            saw_report = True
            phase = PHASE_REPORT
            continue
        if SCANNING_RE.match(line) and saw_report:
            phase = PHASE_REPORT
            continue
        if ISO_CODE_RE.match(line):
            yield i, phase


def parse_scan_text(text: str, *, name: str = "", path: Path | None = None,
                    timestamp: str = "") -> ScanLog:
    """Parse SCAN transcript text into a :class:`ScanLog`."""
    lines = text.splitlines()
    log = ScanLog(path=path or Path(name), name=name, timestamp=timestamp)
    log.connection_failures = sum(1 for l in lines
                                  if l.strip() == CONNECTION_FAILED)

    phases: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line == REPORT_TITLE and PHASE_REPORT not in phases:
            phases.append(PHASE_REPORT)
        elif CLEARING_RE.match(line) and PHASE_CLEAR not in phases:
            phases.append(PHASE_CLEAR)
        m = META_RE.match(line)
        if m:
            key, val = m.group(1).lower(), m.group(2).strip()
            if key == "make":
                log.make = val
            elif key == "model":
                log.model = val
            elif key == "year":
                log.year = val

    vins: list[str] = []
    for idx, phase in _iter_blocks(lines):
        if phase not in phases:
            phases.insert(0, phase)
        entry = ModuleEntry(phase=phase, line_number=idx + 1)
        m_iso = ISO_CODE_RE.match(lines[idx].rstrip())
        entry.iso_code = m_iso.group(1).strip() if m_iso else ""

        # The heading sits exactly two lines above the ISO Code line and the
        # ECU description one line above it. Verified against every block in
        # the corpus; guarded anyway so a malformed file degrades rather than
        # raising.
        if idx >= 2:
            entry.category, entry.abbrev, entry.long_name = _parse_heading(
                lines[idx - 2])
        if idx >= 1:
            entry.ecu_description = lines[idx - 1].strip()

        j = idx + 1
        in_errors = False
        while j < len(lines):
            line = lines[j].rstrip()
            stripped = line.strip()
            if not stripped or ISO_CODE_RE.match(line):
                break
            if BANNER_RE.match(line) or stripped == REPORT_TITLE:
                break

            if stripped in ("SUCCESS", "FAILED"):
                entry.clear_result = stripped
                j += 1
                continue
            if stripped == ERRORS_FOUND:
                in_errors = True
                j += 1
                continue

            m = VIN_RE.match(stripped)
            if m:
                entry.vin = m.group(1).strip()
                vins.append(entry.vin)
                j += 1
                continue
            m = HW_RE.match(stripped)
            if m:
                entry.hardware, entry.hardware_version = _split_ver(m.group(1))
                j += 1
                continue
            m = SW_RE.match(stripped)
            if m:
                entry.software, entry.software_version = _split_ver(m.group(1))
                j += 1
                continue

            m = DTC_LINE_RE.match(stripped)
            if m and in_errors:
                entry.dtcs.append(Dtc.from_scan_line(
                    code=m.group("code"), ftb=m.group("ftb"),
                    description=(m.group("desc") or "").strip(),
                    module=entry.name, iso_code=entry.iso_code,
                    status=(DtcStatus.UNCLEARED
                            if entry.clear_result == "FAILED"
                            else DtcStatus.STORED),
                ))
            j += 1

        for d in entry.dtcs:
            d.source_file = name
            d.timestamp = timestamp
        log.entries.append(entry)

    log.phases_seen = phases or [PHASE_SCAN]
    distinct = sorted(set(vins))
    if distinct:
        log.vin = vins[0]
        if len(distinct) > 1:
            log.vin_conflicts = distinct
    return log


def load_scan(path: Path, *, timestamp: str = "") -> ScanLog:
    """Read and parse a SCAN log from disk."""
    decoded = encoding.read_log_text(path)
    log = parse_scan_text(decoded.text, name=path.name, path=path,
                          timestamp=timestamp)
    log.encoding_used = decoded.encoding
    log.size_bytes = decoded.size_bytes
    return log


def load_scan_by_name(name: str, *, timestamp: str = "") -> ScanLog:
    return load_scan(paths.resolve_log(name), timestamp=timestamp)
