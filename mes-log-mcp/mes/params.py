"""Typed parameter values parsed from MES ``Name: value unit`` lines.

MES prints every measured quantity the same way, whether it appears in a freeze
frame, a live-parameter sample, or an ECU header::

    Engine speed: 1102 rpm
    Spark advance: -8.188 deg.
    Engine temperature: 58 degC
    Gas pedal position: 0.00 %
    Clutch pedal: Released
    STOP&START temporary deactivation status: Speed<10km/h

The v1 server treated all of this as opaque text, so any question about a value
("is canister fill actually changing?") meant a human reading the file. Parsing
it into ``(name, number, unit)`` or ``(name, state)`` is what makes trends,
comparisons and range checks possible at all.

Splitting on the *first* colon is deliberate and correct even for clock-shaped
values: ``Time: 12:30:45`` yields name ``Time`` and value ``12:30:45``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DEGREE = "°"
OHM = "Ω"

#: ``<name>: <value>``. The value may be empty; MES pads many lines with a
#: trailing space, which is stripped by the caller.
_KV_RE = re.compile(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$")

#: A leading signed number, optionally followed by a unit. Anchored so that a
#: value like ``Speed<10km/h`` is *not* mistaken for the number 10.
_NUM_RE = re.compile(r"^([+-]?\d+(?:[.,]\d+)?)\s*(.*)$")

#: Textual states MES uses, normalised to booleans where the meaning is
#: unambiguous. Anything not listed stays a plain string -- guessing at the
#: polarity of an unknown state would be worse than leaving it alone.
_TRUE_STATES = {
    "pressed", "closed", "active", "on", "yes", "present", "allowed",
    "received", "enabled", "engaged", "locked", "detected", "ok", "valid",
}
_FALSE_STATES = {
    "released", "open", "inactive", "off", "no", "absent", "not allowed",
    "not received", "disabled", "disengaged", "unlocked", "not detected",
    "not valid", "invalid", "none",
}

#: Unit spellings MES varies on, mapped to one canonical form so that a series
#: assembled from several logs does not fragment across ``Kg/h`` and ``kg/h``.
_UNIT_CANON = {
    "kg/h": "kg/h",
    "deg.": "deg",
    "deg": "deg",
    DEGREE + "c": DEGREE + "C",
    "c": DEGREE + "C",
    DEGREE: "deg",
    "km/h": "km/h",
    "rpm": "rpm",
    "min": "min",
    "s": "s",
    "v": "V",
    "mv": "mV",
    "a": "A",
    "ma": "mA",
    "mbar": "mbar",
    "bar": "bar",
    "kpa": "kPa",
    "hpa": "hPa",
    "%": "%",
    "km": "km",
    "l": "L",
    "l/h": "L/h",
    "ms": "ms",
    "nm": "Nm",
    "g/s": "g/s",
    "ohm": OHM,
    "hz": "Hz",
}


def canonical_unit(unit: str) -> str:
    """Normalise a unit spelling; unknown units pass through untouched."""
    if not unit:
        return ""
    return _UNIT_CANON.get(unit.strip().lower(), unit.strip())


@dataclass(frozen=True)
class ParamValue:
    """One measured parameter.

    Exactly one of :attr:`number` / :attr:`state` carries the meaning;
    :attr:`raw` always preserves what MES actually printed so nothing is lost.
    """

    name: str
    raw: str
    number: float | None = None
    unit: str = ""
    state: str | None = None
    boolean: bool | None = None
    #: The numeric literal exactly as MES printed it. Kept because formatting
    #: the parsed float loses information: "%g" renders an odometer of
    #: 140572.6 as 140573, and a diagnostic reading must not silently change
    #: on its way to the technician.
    number_text: str = ""

    @property
    def is_numeric(self) -> bool:
        return self.number is not None

    @property
    def display(self) -> str:
        if self.number is not None:
            text = self.number_text or repr(self.number)
            return f"{text} {self.unit}".strip()
        return self.state or self.raw

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "raw": self.raw}
        if self.number is not None:
            d["value"] = self.number
            d["printed"] = self.number_text or repr(self.number)
            if self.unit:
                d["unit"] = self.unit
        if self.state is not None:
            d["state"] = self.state
        if self.boolean is not None:
            d["boolean"] = self.boolean
        return d


def parse_value(name: str, raw: str) -> ParamValue:
    """Build a :class:`ParamValue` from a name and its raw printed value."""
    raw = raw.strip()
    if not raw:
        return ParamValue(name=name, raw="")

    m = _NUM_RE.match(raw)
    if m:
        num_text, unit = m.group(1), m.group(2).strip()
        # MES emits '.' decimals on this corpus, but a comma-decimal locale
        # build is plausible; accept both rather than dropping the fraction.
        try:
            number: float | None = float(num_text.replace(",", "."))
        except ValueError:
            number = None
        if number is not None:
            # A trailing token that is clearly words rather than a unit means
            # this was a state that merely began with a digit.
            if unit and len(unit) > 12 and " " in unit:
                return ParamValue(name=name, raw=raw, state=raw)
            return ParamValue(name=name, raw=raw, number=number,
                              unit=canonical_unit(unit),
                              number_text=num_text)

    lowered = raw.lower()
    boolean: bool | None = None
    if lowered in _TRUE_STATES:
        boolean = True
    elif lowered in _FALSE_STATES:
        boolean = False
    return ParamValue(name=name, raw=raw, state=raw, boolean=boolean)


def parse_kv_line(line: str) -> ParamValue | None:
    """Parse one ``Name: value`` line, or return None if it is not one."""
    m = _KV_RE.match(line)
    if not m:
        return None
    name = m.group(1).strip()
    if not name:
        return None
    return parse_value(name, m.group(2))


@dataclass
class ParamSeries:
    """A named parameter sampled repeatedly across one or more sessions."""

    name: str
    unit: str = ""
    samples: list[ParamValue] = field(default_factory=list)
    #: Parallel to ``samples``: an ISO timestamp or session label per sample.
    stamps: list[str] = field(default_factory=list)

    def add(self, value: ParamValue, stamp: str = "") -> None:
        if value.unit and not self.unit:
            self.unit = value.unit
        self.samples.append(value)
        self.stamps.append(stamp)

    @property
    def numbers(self) -> list[float]:
        return [s.number for s in self.samples if s.number is not None]

    @property
    def states(self) -> list[str]:
        return [s.state for s in self.samples if s.state is not None]

    def stats(self) -> dict[str, Any]:
        """Summary statistics, including whether the value ever moved.

        ``static`` is the point of this method. A parameter pinned at one value
        across every sample is the signature of a substituted default rather
        than a live measurement, and telling those apart by eye is exactly the
        kind of thing that gets missed.
        """
        nums = self.numbers
        out: dict[str, Any] = {
            "name": self.name,
            "unit": self.unit,
            "samples": len(self.samples),
        }
        if nums:
            lo, hi = min(nums), max(nums)
            out.update({
                "min": lo,
                "max": hi,
                "mean": sum(nums) / len(nums),
                "first": nums[0],
                "last": nums[-1],
                "span": hi - lo,
                "static": lo == hi,
                "distinct": len(set(nums)),
            })
        else:
            distinct = sorted(set(self.states))
            out.update({
                "distinct_states": distinct,
                "static": len(distinct) <= 1,
            })
        return out
