"""MES graph-subsystem CSV recordings: parsing and post-hoc trigger analysis.

MES's graph engine (UI string IDs 5001-5041) records up to 4 graphs of 10
parameters each into a timestamped CSV -- the only output MES produces that
has real per-sample timing. The ``.txt`` session log has no per-sample
timestamps at all, which is why :class:`mes.params.ParamSeries` carries a
"sample rate unrecoverable" warning. Here the rate is measured, not guessed.

Documented format (from vendor-doc inspection -- see
``docs/format/CSV_LOG_FORMAT.md`` for per-item confidence)::

    "Time"  "Engine speed"  "Fuel pressure"  "TAG"
    "sec"   "rpm"           "bar"            " "
    0.00    1215.0000       366.3000         ""

* UTF-16LE with BOM, text fields quoted.
* Separator per MES Settings (Tab on this install), so it is sniffed, not
  assumed.
* Row 1 = parameter names, row 2 = units, first column always ``Time`` in
  seconds, last column ``TAG``.
* Enabling "Monitor DTCs" writes DTCs into the recording. The exact rendering
  is UNCONFIRMED until the first real export -- every non-empty TAG cell is
  therefore surfaced as an event, and anything DTC-shaped inside one is
  extracted explicitly.

No CSV has ever been recorded on this install, so this parser is validated
against synthetic fixtures built from the documented sample. The first real
export should be diffed against ``docs/format/CSV_LOG_FORMAT.md`` and any
surprise recorded there.
"""

from __future__ import annotations

import csv as _csv
import io
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import params, paths
from .encoding import read_log_text
from .errors import MesParseError

#: Candidate separators, tried against the header row. Tab is the current
#: Settings value on this install; the other two are the plausible alternates.
_SEPARATORS = ("\t", ";", ",")

#: DTC-shaped token inside a TAG cell.
_DTC_RE = re.compile(r"\b([PBCU][0-9A-F]{4})\b", re.IGNORECASE)

#: ``<column> <op> <threshold>`` for trigger queries.
_COND_RE = re.compile(
    r"^\s*(.+?)\s*(>=|<=|==|!=|>|<)\s*([+-]?\d+(?:[.,]\d+)?)\s*$")

_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

#: A time gap larger than this multiple of the median interval is reported as
#: a dropout -- the adapter stalling or MES losing the ECU mid-recording.
GAP_FACTOR = 3.0


def _cell_number(text: str) -> float | None:
    """Parse a numeric cell, tolerating a comma-decimal locale build."""
    t = text.strip().strip('"')
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        try:
            return float(t.replace(",", "."))
        except ValueError:
            return None


@dataclass(frozen=True)
class Column:
    """One recorded parameter column."""

    index: int
    name: str
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "name": self.name, "unit": self.unit}


@dataclass
class TagEvent:
    """A non-empty TAG cell: an operator marker or a monitored DTC."""

    time: float
    text: str
    dtcs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"time_s": self.time, "text": self.text}
        if self.dtcs:
            d["dtcs"] = self.dtcs
        return d


@dataclass
class Recording:
    """One parsed CSV recording."""

    path: Path
    encoding: str
    separator: str
    columns: list[Column]
    times: list[float]
    #: Raw cell text per row, aligned by column index. Cells stay strings and
    #: are typed on access -- enum parameters ("Released") are legal in any
    #: column, and a recording can run to thousands of rows.
    rows: list[list[str]]
    tags: list[TagEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ragged_rows: int = 0
    unparseable_times: int = 0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def duration(self) -> float:
        return (self.times[-1] - self.times[0]) if len(self.times) > 1 else 0.0

    def timing(self) -> dict[str, Any]:
        """Measured sample timing: rate, median interval, dropouts."""
        out: dict[str, Any] = {"samples": len(self.times),
                               "duration_s": round(self.duration, 3)}
        if len(self.times) < 2:
            return out
        deltas = [b - a for a, b in zip(self.times, self.times[1:])]
        med = statistics.median(deltas)
        out["median_interval_s"] = round(med, 4)
        if self.duration > 0:
            out["rate_hz"] = round((len(self.times) - 1) / self.duration, 3)
        if med > 0:
            gaps = [{"after_s": round(self.times[i], 3),
                     "gap_s": round(d, 3)}
                    for i, d in enumerate(deltas) if d > GAP_FACTOR * med]
            if gaps:
                out["dropouts"] = gaps
                out["dropout_note"] = (
                    f"intervals over {GAP_FACTOR}x the median -- the adapter "
                    "or ECU link stalled; values bracketing a gap are not "
                    "adjacent in time")
        non_monotonic = sum(1 for d in deltas if d < 0)
        if non_monotonic:
            out["non_monotonic_steps"] = non_monotonic
        return out

    # -- column access -----------------------------------------------------

    def find_column(self, ref: str) -> Column:
        """Resolve a column by exact name, unique substring, or index.

        Duplicate names are legal (the .txt format demonstrably repeats
        ``Engine oil pressure`` as an enum and a bar value in one block), so
        exact matches prefer the first and the ambiguity is reported through
        ``duplicate_names`` in :meth:`to_dict`.
        """
        r = ref.strip()
        if r.isdigit():
            i = int(r)
            for c in self.columns:
                if c.index == i:
                    return c
            raise MesParseError(f"no column with index {i}")
        low = r.lower()
        exact = [c for c in self.columns if c.name.lower() == low]
        if exact:
            return exact[0]
        subs = [c for c in self.columns if low in c.name.lower()]
        if len(subs) == 1:
            return subs[0]
        if len(subs) > 1:
            raise MesParseError(
                f"{ref!r} is ambiguous: matches "
                + ", ".join(c.name for c in subs))
        raise MesParseError(
            f"no column matching {ref!r}; available: "
            + ", ".join(c.name for c in self.columns))

    def series(self, ref: str) -> params.ParamSeries:
        """One column as a typed :class:`ParamSeries`, stamped with times."""
        col = self.find_column(ref)
        s = params.ParamSeries(name=col.name, unit=col.unit)
        for t, row in zip(self.times, self.rows):
            raw = row[col.index] if col.index < len(row) else ""
            s.add(params.parse_value(col.name, raw.strip().strip('"')),
                  stamp=f"{t:g}s")
        return s

    def numbers(self, ref: str) -> list[tuple[float, float]]:
        """(time, value) pairs for a column, numeric samples only."""
        col = self.find_column(ref)
        out: list[tuple[float, float]] = []
        for t, row in zip(self.times, self.rows):
            raw = row[col.index] if col.index < len(row) else ""
            n = _cell_number(raw)
            if n is not None:
                out.append((t, n))
        return out

    def snapshot(self, at: float) -> dict[str, Any]:
        """Every column's value at the sample nearest ``at`` seconds.

        This is the post-hoc freeze frame: what everything read at the moment
        a tag fired or a threshold tripped.
        """
        if not self.times:
            raise MesParseError("recording has no samples")
        i = min(range(len(self.times)), key=lambda j: abs(self.times[j] - at))
        row = self.rows[i]
        vals: dict[str, str] = {}
        for c in self.columns:
            raw = row[c.index] if c.index < len(row) else ""
            v = params.parse_value(c.name, raw.strip().strip('"'))
            text = v.display
            if v.is_numeric and not v.unit and c.unit:
                text = f"{text} {c.unit}"
            vals[c.name] = text
        return {"requested_s": at, "sample_s": self.times[i],
                "sample_index": i, "values": vals}

    # -- trigger analysis ----------------------------------------------------

    def crossings(self, condition: str) -> dict[str, Any]:
        """Intervals where ``<column> <op> <value>`` held true.

        Returns entry/exit times per interval with the extreme value inside
        it, rather than one hit per sample -- 400 rows above a threshold is
        one event, not 400.
        """
        m = _COND_RE.match(condition)
        if not m:
            raise MesParseError(
                f"cannot parse condition {condition!r}; expected "
                "'<column> <op> <value>' with op one of > < >= <= == !=")
        ref, op, thr_text = m.group(1), m.group(2), m.group(3)
        threshold = float(thr_text.replace(",", "."))
        col = self.find_column(ref)
        test = _OPS[op]

        pairs = self.numbers(str(col.index))
        intervals: list[dict[str, Any]] = []
        cur: dict[str, Any] | None = None
        for t, v in pairs:
            if test(v, threshold):
                if cur is None:
                    cur = {"enter_s": t, "exit_s": t, "samples": 0,
                           "extreme": v}
                cur["exit_s"] = t
                cur["samples"] += 1
                if op in ("<", "<="):
                    cur["extreme"] = min(cur["extreme"], v)
                else:
                    cur["extreme"] = max(cur["extreme"], v)
            elif cur is not None:
                intervals.append(cur)
                cur = None
        if cur is not None:
            intervals.append(cur)
        for iv in intervals:
            iv["duration_s"] = round(iv["exit_s"] - iv["enter_s"], 3)
        return {
            "condition": f"{col.name} {op} {threshold:g}",
            "column": col.to_dict(),
            "numeric_samples": len(pairs),
            "intervals": intervals,
            "count": len(intervals),
        }

    # -- serialisation ---------------------------------------------------

    def to_dict(self, preview_rows: int = 0) -> dict[str, Any]:
        names = [c.name for c in self.columns]
        dupes = sorted({n for n in names if names.count(n) > 1})
        d: dict[str, Any] = {
            "file": self.name,
            "encoding": self.encoding,
            "separator": {"\t": "tab"}.get(self.separator, self.separator),
            "columns": [c.to_dict() for c in self.columns],
            "timing": self.timing(),
            "tag_events": [t.to_dict() for t in self.tags],
            "dtcs_in_tags": sorted({dtc for t in self.tags for dtc in t.dtcs}),
        }
        if dupes:
            d["duplicate_names"] = dupes
        if self.ragged_rows:
            d["ragged_rows"] = self.ragged_rows
        if self.unparseable_times:
            d["unparseable_times"] = self.unparseable_times
        if self.warnings:
            d["warnings"] = self.warnings
        if preview_rows > 0:
            d["preview"] = [
                {"time_s": t,
                 **{c.name: (row[c.index] if c.index < len(row) else "")
                    for c in self.columns}}
                for t, row in list(zip(self.times, self.rows))[:preview_rows]
            ]
        return d


def _sniff_separator(header: str) -> str:
    """Pick the separator that yields the most columns on the header row."""
    best, best_n = "\t", 1
    for sep in _SEPARATORS:
        n = len(next(_csv.reader(io.StringIO(header), delimiter=sep)))
        if n > best_n:
            best, best_n = sep, n
    if best_n < 2:
        raise MesParseError(
            "could not detect a separator on the header row -- not an MES "
            "CSV recording?")
    return best


def load_csv(path: Path) -> Recording:
    """Parse one MES CSV recording."""
    decoded = read_log_text(path)
    lines = [ln for ln in decoded.text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise MesParseError(
            f"{path.name}: too short to be a recording "
            f"({len(lines)} non-empty lines)")

    warnings: list[str] = []
    sep = _sniff_separator(lines[0])
    reader = _csv.reader(io.StringIO("\n".join(lines)), delimiter=sep)
    table = [[c.strip() for c in row] for row in reader]

    names = [c.strip().strip('"') for c in table[0]]
    units = [c.strip().strip('"') for c in table[1]] if len(table) > 1 else []
    while len(units) < len(names):
        units.append("")

    if not names or names[0].lower() != "time":
        warnings.append(
            f"first column is {names[0]!r}, not 'Time' -- the documented "
            "format always leads with Time in seconds; timing fields may be "
            "wrong")
    tag_index = len(names) - 1 if names and names[-1].upper() == "TAG" else -1
    if tag_index < 0:
        warnings.append("no trailing TAG column -- DTC/marker events "
                        "unavailable for this recording")

    columns = [
        Column(index=i, name=names[i],
               unit=params.canonical_unit(units[i]) if units[i].strip() else "")
        for i in range(len(names))
        if i != 0 and i != tag_index
    ]

    times: list[float] = []
    rows: list[list[str]] = []
    tags: list[TagEvent] = []
    ragged = 0
    bad_times = 0
    for raw_row in table[2:]:
        if len(raw_row) != len(names):
            ragged += 1
            if len(raw_row) < len(names):
                raw_row = raw_row + [""] * (len(names) - len(raw_row))
        t = _cell_number(raw_row[0])
        if t is None:
            bad_times += 1
            continue
        times.append(t)
        rows.append(raw_row)
        if 0 <= tag_index < len(raw_row):
            tag = raw_row[tag_index].strip().strip('"').strip()
            if tag:
                tags.append(TagEvent(
                    time=t, text=tag,
                    dtcs=[m.upper() for m in _DTC_RE.findall(tag)]))

    if decoded.control_chars:
        warnings.append(f"{decoded.control_chars} stray control bytes removed")

    return Recording(
        path=path, encoding=decoded.encoding, separator=sep,
        columns=columns, times=times, rows=rows, tags=tags,
        warnings=warnings, ragged_rows=ragged, unparseable_times=bad_times)


def list_recordings() -> list[dict[str, Any]]:
    """Cheap inventory of every CSV in the CSV roots, newest mtime first.

    The MES CSV filename convention is unknown (none has ever been written
    here), so unlike the .txt catalog there is no filename timestamp --
    mtime is all there is, and it is labelled as such.
    """
    out: list[dict[str, Any]] = []
    for p in paths.iter_csv_files():
        try:
            st = p.stat()
        except OSError:
            continue
        entry: dict[str, Any] = {
            "file": p.name,
            "size_bytes": st.st_size,
            "_mtime": st.st_mtime,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(
                sep=" ", timespec="seconds"),
            "timestamp_note": ("file mtime -- MES CSV filenames carry no "
                               "known session stamp"),
        }
        try:
            rec = load_csv(p)
            entry.update({
                "parameters": [c.name for c in rec.columns],
                "samples": len(rec.times),
                "duration_s": round(rec.duration, 3),
                "tag_events": len(rec.tags),
            })
        except Exception as exc:
            entry["parse_error"] = str(exc)
        out.append(entry)
    out.sort(key=lambda e: e["_mtime"], reverse=True)
    for e in out:
        del e["_mtime"]
    return out


def load_named(name: str) -> Recording:
    """Resolve a bare CSV filename through containment and parse it."""
    return load_csv(paths.resolve_csv(name))
