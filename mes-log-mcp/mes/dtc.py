"""Diagnostic trouble code model, classification and failure-type decoding.

A MES DTC is a five-character code plus a two-hex-digit failure type byte
(FTB), e.g. ``P0456-00``, ``B11A1-11``, ``U1711-2F``. The v1 server captured
only the code text and discarded both the description MES had already supplied
and the FTB's meaning.

Two design points worth stating:

**The FTB table is grounded in the corpus, not invented.** SCAN logs print the
failure-type phrase alongside the code (``U0019-88 - B-CAN line - Bus OFF``),
so the mapping below was read off real data from this vehicle's own ECUs rather
than recalled from a standard. Entries carry a ``source`` so a technician can
tell corpus-derived meanings from reference ones, and unknown bytes are
reported as unknown rather than guessed at.

**Status is a first-class field.** A code that was read, cleared, and came back
in the same session is the single highest-signal state in the whole dataset,
and v1 could not express it at all -- it reported cleared codes identically to
stored ones. See :class:`DtcStatus`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from . import dtc_text
from .params import ParamValue

#: Structural DTC pattern. Used for *validation* of an already-isolated token,
#: not for blind scanning of prose -- see :func:`scan_text_for_dtcs`.
DTC_RE = re.compile(r"^([PBCU][0-9A-F]{4})(?:-([0-9A-F]{2}))?$")

#: Loose pattern for finding candidates in free text. This over-matches by
#: design and every hit must be screened by :func:`is_plausible_dtc`.
DTC_SCAN_RE = re.compile(r"\b([PBCU][0-9A-F]{4}(?:-[0-9A-F]{2})?)\b")

#: Header keys whose values structurally resemble DTCs but never are. MES
#: prints part, hardware, software, drawing and homologation numbers in the
#: same files, and a naive scan happily reports them as fault codes.
NON_DTC_KEYS = {
    "ecu iso code", "iso code", "ecu serial number", "spare part number",
    "hardware number", "hardware version", "software number",
    "software version", "homologation number", "fiat drawing number",
    "drawing number", "vin code", "vin", "part number", "serial number",
    "calibration number", "proxi configuration write counter",
    "supplier code", "manufacturing date", "assembly number",
}


class DtcStatus(str, Enum):
    """What a log actually tells us about a code's state.

    ``RETURNED`` is the one that matters most clinically: the code was present,
    the technician erased it, and the ECU set it again before the session
    ended. That is a hard fault reproducing on demand, and it reads completely
    differently from a code that was merely stored.
    """

    #: Read from the ECU and present at that moment.
    STORED = "stored"
    #: Present earlier in the session, then erased by a clear operation.
    CLEARED = "cleared"
    #: Present again on a re-read *after* a clear in the same session.
    RETURNED = "returned"
    #: A clear was attempted on this module and reported FAILED.
    UNCLEARED = "uncleared"
    #: The ECU explicitly reported no fault codes.
    ABSENT = "absent"
    UNKNOWN = "unknown"

    @property
    def severity_rank(self) -> int:
        """Sort key: the most clinically significant states come first."""
        return {
            DtcStatus.RETURNED: 0,
            DtcStatus.UNCLEARED: 1,
            DtcStatus.STORED: 2,
            DtcStatus.CLEARED: 3,
            DtcStatus.UNKNOWN: 4,
            DtcStatus.ABSENT: 5,
        }[self]

    @property
    def explanation(self) -> str:
        return {
            DtcStatus.STORED: "present in the ECU when read",
            DtcStatus.CLEARED: "was present, erased during this session",
            DtcStatus.RETURNED: "reappeared after being cleared in this "
                                "session - the fault is reproducing",
            DtcStatus.UNCLEARED: "clear attempted but the module reported "
                                 "FAILED - code could not be erased",
            DtcStatus.ABSENT: "ECU reported no fault codes",
            DtcStatus.UNKNOWN: "state not determinable from this log",
        }[self]


@dataclass(frozen=True)
class FailureType:
    """Decoded meaning of the two-hex-digit failure type byte."""

    byte: str
    text: str
    source: str = "corpus"
    confidence: str = "confirmed"

    def to_dict(self) -> dict[str, Any]:
        return {"byte": self.byte, "meaning": self.text,
                "source": self.source, "confidence": self.confidence}


#: ISO 14229-1 style failure-type groups, for display.
FTB_GROUPS: dict[str, str] = {
    "0": "general failure categories",
    "1": "general electrical failures",
    "2": "general signal failures",
    "3": "FM/PWM (frequency and timing) failures",
    "4": "system internal failures",
    "5": "system programming failures",
    "6": "algorithm based failures",
    "7": "mechanical failures",
    "8": "bus signal / message failures",
    "9": "component failures",
}

# (byte, meaning, source, confidence)
#
# Sources, strongest first:
#   corpus    - printed by a real ECU in this shop's own logs, WITH its byte.
#               Ground truth.
#   mes-table - MultiEcuScan's shipped string table (Lang/English.txt, ids
#               3101-3199). The table lists phrases in byte order but does not
#               print the hex, so byte assignments were derived by anchoring
#               the ordered list to the corpus-confirmed values. Four group
#               boundaries closed with zero arithmetic slack, which is why the
#               reconstruction is trusted at all.
#
# Confidence:
#   confirmed - corpus-printed, or pinned between two corpus anchors in a
#               contiguous run with no slack.
#   likely    - vendor phrase, position derived, single source.
#   offset    - as 'likely', but sits in a run with one unlocated gap, so the
#               byte could be off by one. Reported as such rather than
#               silently presented as fact.
#
# Bytes absent from this table are reported as unknown, never guessed at.
_FTB_TABLE: tuple[tuple[str, str, str, str], ...] = (
    ("00", "no sub-type information", "corpus", "confirmed"),
    # 0x0N general categories
    ("01", "general electrical failure", "mes-table", "likely"),
    ("02", "general signal failure", "mes-table", "likely"),
    ("07", "mechanical failure", "mes-table", "likely"),
    ("08", "bus signal/message failure", "mes-table", "likely"),
    ("09", "component failure", "mes-table", "likely"),
    # 0x1N electrical
    ("11", "short circuit to ground", "corpus", "confirmed"),
    ("12", "short circuit to +V", "mes-table", "confirmed"),
    ("13", "open circuit", "mes-table", "confirmed"),
    ("14", "short to ground or open circuit", "mes-table", "confirmed"),
    ("15", "short to +V or open circuit", "corpus", "confirmed"),
    ("16", "voltage too low", "mes-table", "confirmed"),
    ("17", "voltage too high", "mes-table", "confirmed"),
    ("18", "current too low / below threshold", "corpus", "confirmed"),
    ("19", "current too high / above threshold / overload", "mes-table", "likely"),
    ("1A", "circuit resistance too low", "mes-table", "likely"),
    ("1B", "circuit resistance too high", "mes-table", "likely"),
    ("1C", "voltage out of range", "mes-table", "likely"),
    ("1D", "current out of range", "mes-table", "likely"),
    ("1E", "resistance out of range", "mes-table", "likely"),
    ("1F", "circuit intermittent", "mes-table", "likely"),
    # 0x2N signal
    ("21", "signal below lower limit", "mes-table", "likely"),
    ("22", "signal above max threshold", "mes-table", "likely"),
    ("23", "signal stuck low", "mes-table", "likely"),
    ("24", "signal stuck high", "mes-table", "likely"),
    ("25", "signal shape / waveform failure", "mes-table", "likely"),
    ("26", "signal rate of change below threshold", "mes-table", "likely"),
    ("27", "signal rate of change above threshold", "mes-table", "likely"),
    ("28", "signal bias level out of range", "mes-table", "likely"),
    ("29", "signal invalid", "mes-table", "likely"),
    ("2A", "signal stuck", "mes-table", "offset"),
    ("2B", "wires shorted together", "mes-table", "offset"),
    ("2C", "circuit low", "mes-table", "offset"),
    ("2D", "circuit high", "mes-table", "offset"),
    ("2F", "signal/message erratic", "corpus", "confirmed"),
    # 0x3N frequency / timing
    ("31", "no signal", "mes-table", "likely"),
    ("32", "signal low time below threshold", "mes-table", "likely"),
    ("33", "signal low time above threshold / stuck", "mes-table", "likely"),
    ("34", "signal high time below threshold", "mes-table", "likely"),
    ("35", "signal high time above threshold / stuck", "mes-table", "likely"),
    ("36", "signal frequency too low", "mes-table", "likely"),
    ("37", "signal frequency too high", "mes-table", "likely"),
    ("38", "signal frequency incorrect", "mes-table", "likely"),
    ("39", "signal has too few pulses", "mes-table", "likely"),
    ("3A", "signal has too many pulses", "mes-table", "likely"),
    ("3B", "circuit low", "mes-table", "likely"),
    ("3C", "circuit high", "mes-table", "likely"),
    # 0x4N system internal
    ("41", "general checksum failure", "mes-table", "likely"),
    ("42", "general memory failure", "mes-table", "likely"),
    ("43", "special memory failure", "mes-table", "likely"),
    ("44", "data memory failure", "mes-table", "likely"),
    ("45", "program memory failure", "mes-table", "likely"),
    ("46", "calibration / parameter memory failure", "mes-table", "likely"),
    ("47", "watchdog / safety failure", "mes-table", "likely"),
    ("48", "supervision software failure", "mes-table", "likely"),
    ("49", "internal electronic failure", "mes-table", "likely"),
    ("4A", "incorrect component installed", "mes-table", "likely"),
    ("4B", "over temperature", "mes-table", "likely"),
    ("4C", "circuit low", "mes-table", "likely"),
    ("4D", "circuit high", "mes-table", "likely"),
    # 0x5N programming
    ("51", "not programmed", "mes-table", "likely"),
    ("52", "missing calibration", "mes-table", "likely"),
    ("53", "not configured", "mes-table", "likely"),
    ("54", "incompatible configuration", "mes-table", "likely"),
    # 0x6N algorithm
    ("61", "signal calculation failure", "mes-table", "confirmed"),
    ("62", "signal compare failure", "mes-table", "confirmed"),
    ("63", "circuit / component protection time out", "mes-table", "confirmed"),
    ("64", "signal/message plausibility failure", "corpus", "confirmed"),
    ("65", "signal has too few transitions / events", "mes-table", "likely"),
    ("66", "signal has too many transitions / events", "mes-table", "likely"),
    ("67", "signal incorrect after event", "mes-table", "likely"),
    ("68", "event information", "mes-table", "likely"),
    # 0x7N mechanical
    ("71", "actuator stuck", "mes-table", "likely"),
    ("72", "actuator stuck open", "mes-table", "likely"),
    ("73", "actuator stuck closed", "mes-table", "likely"),
    ("74", "actuator slipping", "mes-table", "likely"),
    ("75", "wrong mounting position", "mes-table", "likely"),
    ("76", "commanded position not reachable", "mes-table", "likely"),
    ("77", "alignment or adjustment incorrect", "mes-table", "likely"),
    ("78", "mechanical linkage failure", "mes-table", "likely"),
    ("79", "fluid leak or seal failure", "mes-table", "likely"),
    ("7A", "low fluid level", "mes-table", "likely"),
    # 0x8N bus / message
    ("81", "invalid serial data received", "mes-table", "likely"),
    ("82", "alive / sequence counter incorrect or not updated", "mes-table",
     "likely"),
    ("83", "value of signal protection calculation incorrect", "mes-table",
     "likely"),
    ("84", "signal below allowable range", "mes-table", "confirmed"),
    ("85", "signal above allowable range", "mes-table", "confirmed"),
    ("86", "signal/message invalid", "corpus", "confirmed"),
    ("87", "missing message", "corpus", "confirmed"),
    ("88", "bus off", "corpus", "confirmed"),
    ("89", "communication erratic", "mes-table", "confirmed"),
    # 0x9N component
    ("92", "performance or incorrect operation", "mes-table", "offset"),
    ("93", "no operation", "mes-table", "offset"),
    ("94", "unexpected operation", "mes-table", "offset"),
    ("95", "incorrect assembly", "mes-table", "offset"),
    ("96", "component internal failure", "mes-table", "offset"),
    ("97", "component or system operation obstructed or blocked", "corpus",
     "confirmed"),
    ("98", "component or system over temperature", "mes-table", "likely"),
    ("99", "component or system operating conditions", "mes-table", "likely"),
)

FAILURE_TYPES: dict[str, FailureType] = {
    b: FailureType(b, text, source, confidence)
    for b, text, source, confidence in _FTB_TABLE
}

#: Bytes at or above this value have no standardised meaning. MES's own table
#: terminates at 0x99, which is strong corroborating evidence.
MANUFACTURER_SPECIFIC_FROM = 0xA0


def failure_type(ftb: str | None) -> FailureType | None:
    """Look up a failure-type byte, returning an explicit unknown if absent.

    Returning a marked-unknown rather than None-with-no-explanation keeps the
    "we do not know" visible all the way to the technician instead of silently
    dropping the byte from a report.
    """
    if not ftb:
        return None
    key = ftb.upper().strip()
    known = FAILURE_TYPES.get(key)
    if known:
        return known

    try:
        value = int(key, 16)
    except ValueError:
        return FailureType(key, f"not a valid failure type byte: {key!r}",
                           source="none", confidence="unknown")

    if value >= MANUFACTURER_SPECIFIC_FROM:
        return FailureType(
            key,
            f"0x{key} is outside the standardised range - manufacturer or "
            "vehicle specific, meaning not published",
            source="none", confidence="unknown")

    group = FTB_GROUPS.get(key[0])
    hint = f" (falls in the {group} group)" if group else ""
    return FailureType(
        key, f"unrecognised failure type byte 0x{key}{hint}",
        source="none", confidence="unknown")


#: System letter -> human name.
SYSTEM_NAMES = {
    "P": "Powertrain",
    "B": "Body",
    "C": "Chassis",
    "U": "Network/Communication",
}


def code_authority(code: str) -> str:
    """Whether a code is SAE-generic or manufacturer-defined.

    Matters in practice: a generic code has a published definition that holds
    across every make, while a manufacturer code means nothing without FCA
    documentation, so the two warrant different confidence in any lookup.
    """
    if len(code) < 2:
        return "unknown"
    letter, digit = code[0].upper(), code[1]
    if letter == "P":
        if digit == "0" or digit == "2":
            return "generic (SAE J2012)"
        if digit == "1":
            return "manufacturer (FCA)"
        if digit == "3":
            return "jointly defined / manufacturer"
        return "unknown"
    if digit == "0":
        return "generic (SAE J2012)"
    if digit in ("1", "2"):
        return "manufacturer (FCA)"
    return "unknown"


def is_plausible_dtc(token: str, *, line: str = "") -> bool:
    """Screen a regex candidate against the header keys that produce look-alikes.

    ``Hardware number: MM10JAHW232`` and ``Software number: P235QB39`` sit in
    every FES header, and the naive pattern will happily pull DTC-shaped
    substrings out of identifiers like these. Checking the line's key is a far
    more reliable filter than trying to make the pattern itself smarter.
    """
    if not DTC_RE.match(token.upper()):
        return False
    if line:
        head = line.split(":", 1)[0].strip().lower() if ":" in line else ""
        if head in NON_DTC_KEYS:
            return False
    return True


@dataclass
class Dtc:
    """One diagnostic trouble code with everything the log said about it."""

    code: str
    ftb: str | None = None
    description: str = ""
    #: For SCAN logs MES splits the description into component then failure
    #: phrase; both are kept so neither has to be re-derived.
    component: str = ""
    failure_text: str = ""
    module: str = ""
    iso_code: str = ""
    status: DtcStatus = DtcStatus.UNKNOWN
    #: Position in the log's numbered list, when there was one.
    index: int = 0
    freeze_frame: dict[str, ParamValue] = field(default_factory=dict)
    source_file: str = ""
    timestamp: str = ""

    @property
    def full(self) -> str:
        return f"{self.code}-{self.ftb}" if self.ftb else self.code

    @property
    def system(self) -> str:
        return SYSTEM_NAMES.get(self.code[:1].upper(), "Unknown")

    @property
    def authority(self) -> str:
        return code_authority(self.code)

    @property
    def failure(self) -> FailureType | None:
        return failure_type(self.ftb)

    @property
    def has_freeze_frame(self) -> bool:
        return bool(self.freeze_frame)

    def freeze(self, name: str) -> ParamValue | None:
        """Case-insensitive freeze-frame lookup."""
        if name in self.freeze_frame:
            return self.freeze_frame[name]
        low = name.lower()
        for k, v in self.freeze_frame.items():
            if k.lower() == low:
                return v
        return None

    @classmethod
    def from_scan_line(cls, *, code: str, ftb: str, description: str,
                       module: str = "", iso_code: str = "",
                       status: DtcStatus = DtcStatus.STORED) -> "Dtc":
        """Build from a SCAN log fault line.

        MES joins component and failure phrase with ``" - "``, but both halves
        may themselves contain hyphens and slashes, so the split binds to the
        LAST separator and tolerates its absence -- codes with FTB ``00``
        carry only one segment, and bare codes inside a FAILED clear block
        carry none.
        """
        component, failure_text = description, ""
        if " - " in description:
            component, failure_text = description.rsplit(" - ", 1)
        return cls(code=code.upper(), ftb=ftb.upper(), description=description,
                   component=component.strip(), failure_text=failure_text.strip(),
                   module=module, iso_code=iso_code, status=status)

    def to_dict(self, *, include_freeze: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "dtc": self.full,
            "code": self.code,
            "system": self.system,
            "authority": self.authority,
            "description": self.description,
            "status": self.status.value,
            "status_meaning": self.status.explanation,
        }
        if not self.description:
            # The log itself said nothing about this code -- e.g. a bare code
            # inside a FAILED clear block. Fall back to whatever MES's own
            # shipped language files know, clearly labelled as that source
            # rather than silently passed off as log text. See
            # mes/dtc_text.py and docs/format/MES_LANGUAGE_FILES.md: against
            # the currently installed English.dat/English.txt this is a
            # documented no-op (no DTC-code key exists in those files), but
            # the fallback is real and forward-compatible.
            fallback = dtc_text.describe(self.code, self.module or None)
            if fallback:
                d["description"] = fallback["text"]
                d["description_source"] = fallback["source"]
        if self.component:
            d["component"] = self.component
        if self.failure_text:
            d["failure_text"] = self.failure_text
        ft = self.failure
        if ft:
            d["failure_type"] = ft.to_dict()
        if self.module:
            d["module"] = self.module
        if self.iso_code:
            d["iso_code"] = self.iso_code
        if self.source_file:
            d["source_file"] = self.source_file
        if self.timestamp:
            d["timestamp"] = self.timestamp
        if include_freeze and self.freeze_frame:
            d["freeze_frame"] = {k: v.to_dict()
                                 for k, v in self.freeze_frame.items()}
        return d

    def summary(self) -> str:
        parts = [self.full]
        if self.description:
            parts.append(self.description)
        ft = self.failure
        if ft and ft.confidence != "unknown" and ft.byte != "00":
            parts.append(f"[{ft.text}]")
        if self.status is not DtcStatus.UNKNOWN:
            parts.append(f"({self.status.value})")
        return " - ".join(parts[:2]) + (" " + " ".join(parts[2:])
                                        if len(parts) > 2 else "")


def scan_text_for_dtcs(text: str) -> list[tuple[str, str]]:
    """Find DTC-shaped tokens in free text, screened for false positives.

    Returns ``(token, source_line)`` pairs. Structural parsers are always
    preferable; this exists for the cases where a code appears somewhere the
    grammar does not cover.
    """
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        for m in DTC_SCAN_RE.finditer(line):
            token = m.group(1).upper()
            if is_plausible_dtc(token, line=line):
                out.append((token, line.strip()))
    return out
