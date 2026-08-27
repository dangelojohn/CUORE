"""Log discovery, indexing and caching.

Two things this fixes from v1.

**Ordering.** v1 sorted by ``st_mtime``. The real session time is in the
filename, and mtime is not it: copy the folder to a backup drive and back, and
"newest" silently becomes "most recently touched", which quietly breaks
``latest_log`` and every "latest seen" field. Here the parsed filename
timestamp is authoritative and mtime is only a fallback for unparseable names.

**Vehicle identity.** v1 matched a substring against the filename, so SCAN logs
-- whose filenames contain no vehicle at all -- could never be filtered by car.
This index reads the VIN out of file *content* for both kinds, so a
mixed-vehicle directory can be separated properly. With two vehicles in this
corpus that is the difference between a correct history and a merged one.

The index is cached per file on ``(mtime, size)``. MES writes into the same
directory while it runs -- a new log appeared mid-session during development --
so entries are re-read when they change, and a file touched within
:data:`SETTLE_SECONDS` is flagged as possibly still being written.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from . import paths
from .errors import MesNotFound

#: A file modified this recently may still be open in MES. Reported, not
#: hidden -- the caller decides whether a half-written log is usable.
SETTLE_SECONDS = 3.0

_KIND_LABEL = {"fes": "engineering session", "scan": "all-systems scan"}


def parse_stamp(raw: str) -> datetime | None:
    """``YYMMDDHHMM`` -> datetime, or None if it is not a valid stamp."""
    try:
        return datetime.strptime(raw, "%y%m%d%H%M")
    except (ValueError, TypeError):
        return None


@dataclass
class LogEntry:
    """One indexed log file and the cheap metadata read from it."""

    path: Path
    name: str
    kind: str
    raw_stamp: str = ""
    stamp: datetime | None = None
    vehicle: str = ""
    size: int = 0
    mtime: float = 0.0
    # --- filled by a content read ---
    vin: str = ""
    ecu: str = ""
    simulation: bool = False
    simulation_determinable: bool = True
    module_count: int = 0
    dtc_count: int = 0
    encoding_used: str = ""
    parse_error: str = ""
    possibly_incomplete: bool = False

    @property
    def timestamp(self) -> str:
        return self.stamp.isoformat(sep=" ") if self.stamp else self.raw_stamp

    @property
    def sort_key(self) -> tuple[float, str]:
        """Filename timestamp first, mtime only when the name has no stamp."""
        if self.stamp:
            return (self.stamp.timestamp(), self.name)
        return (self.mtime, self.name)

    @property
    def label(self) -> str:
        return _KIND_LABEL.get(self.kind, self.kind)

    @property
    def trustworthy(self) -> bool:
        """False for known-simulated data.

        Note this is not the same as "verified real": a SCAN log has no
        simulation marker at all, so it reports True while
        :attr:`simulation_determinable` is False. Callers that care about
        provenance must check both.
        """
        return not self.simulation

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "file": self.name,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "vehicle": self.vehicle,
            "vin": self.vin,
            "size_bytes": self.size,
            "modules": self.module_count,
            "dtcs": self.dtc_count,
        }
        if self.ecu:
            d["ecu"] = self.ecu
        if self.simulation:
            d["simulation"] = True
            d["warning"] = "SIMULATION MODE - this data is not from a vehicle"
        if not self.simulation_determinable:
            d["provenance"] = "unverifiable (no simulation marker in this format)"
        if self.encoding_used:
            d["encoding"] = self.encoding_used
        if self.possibly_incomplete:
            d["possibly_incomplete"] = True
        if self.parse_error:
            d["parse_error"] = self.parse_error
        return d


class Catalog:
    """Cached index over every MES log in the configured roots."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, int, LogEntry]] = {}

    # -- building ---------------------------------------------------------

    def _read_metadata(self, entry: LogEntry) -> None:
        """Populate content-derived fields, degrading gracefully on error."""
        from . import fes, scan  # local import to avoid a cycle at module load

        try:
            if entry.kind == "scan":
                log = scan.load_scan(entry.path, timestamp=entry.timestamp)
                entry.vin = log.vin
                entry.module_count = len(log.modules)
                entry.dtc_count = len(log.all_dtcs)
                entry.encoding_used = log.encoding_used
                # SCAN logs carry no marker, so simulation is undecidable.
                entry.simulation = False
                entry.simulation_determinable = False
                if log.modules:
                    entry.ecu = log.modules[0].ecu_description
            else:
                log = fes.load_fes(entry.path, timestamp=entry.timestamp)
                entry.vin = log.vin
                entry.ecu = log.ecu_description
                entry.simulation = log.simulation
                entry.module_count = 1
                entry.dtc_count = len(log.dtcs)
                entry.encoding_used = log.encoding_used
                if not entry.vehicle:
                    entry.vehicle = log.vehicle
        except Exception as exc:  # a corrupt log must not sink the whole index
            entry.parse_error = f"{type(exc).__name__}: {exc}"

    def _entry_for(self, path: Path) -> LogEntry:
        try:
            st = path.stat()
        except OSError as exc:
            kind, raw, veh = paths.classify_name(path.name)
            e = LogEntry(path=path, name=path.name, kind=kind, raw_stamp=raw,
                         stamp=parse_stamp(raw), vehicle=veh)
            e.parse_error = f"stat failed: {exc}"
            return e

        cached = self._cache.get(str(path).lower())
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            return cached[2]

        kind, raw, veh = paths.classify_name(path.name)
        entry = LogEntry(path=path, name=path.name, kind=kind, raw_stamp=raw,
                         stamp=parse_stamp(raw), vehicle=veh,
                         size=st.st_size, mtime=st.st_mtime)
        entry.possibly_incomplete = (time.time() - st.st_mtime) < SETTLE_SECONDS
        self._read_metadata(entry)
        # A file still being written is deliberately not cached, so the next
        # call re-reads it once MES has finished.
        if not entry.possibly_incomplete:
            self._cache[str(path).lower()] = (st.st_mtime, st.st_size, entry)
        return entry

    def entries(self) -> list[LogEntry]:
        """All indexed logs, newest first by filename timestamp."""
        out = [self._entry_for(p) for p in paths.iter_log_files()]
        out.sort(key=lambda e: e.sort_key, reverse=True)
        return out

    # -- querying ---------------------------------------------------------

    def select(self, *, kind: str = "", vehicle: str = "", vin: str = "",
               since: str = "", until: str = "",
               include_simulation: bool = False,
               limit: int | None = None) -> list[LogEntry]:
        """Filter the index.

        ``vehicle`` matches the filename vehicle string *or* the ECU
        description, so it works on SCAN logs too. ``vin`` matches content.
        Simulated logs are excluded unless explicitly asked for -- 54 of the 78
        FES logs in this corpus are practice data, and silently mixing them
        into a fault history would be actively misleading.
        """
        lo = _parse_bound(since)
        hi = _parse_bound(until)
        want_kind = kind.strip().lower()
        veh_q = vehicle.strip().lower()
        vin_q = vin.strip().upper()

        out: list[LogEntry] = []
        for e in self.entries():
            if want_kind and e.kind != want_kind:
                continue
            if not include_simulation and e.simulation:
                continue
            if vin_q and vin_q not in e.vin.upper():
                continue
            if veh_q and veh_q not in f"{e.vehicle} {e.ecu}".lower():
                continue
            if lo and e.stamp and e.stamp < lo:
                continue
            if hi and e.stamp and e.stamp > hi:
                continue
            out.append(e)
            if limit is not None and len(out) >= limit:
                break
        return out

    def latest(self, **kw: Any) -> LogEntry | None:
        found = self.select(limit=1, **kw)
        return found[0] if found else None

    def by_name(self, name: str) -> LogEntry:
        path = paths.resolve_log(name)
        return self._entry_for(path)

    def vehicles(self) -> list[dict[str, Any]]:
        """Every distinct vehicle in the corpus, keyed by VIN where known.

        Logs with no recoverable VIN are grouped under their filename vehicle
        string so nothing is silently dropped from the roster.
        """
        groups: dict[str, dict[str, Any]] = {}
        for e in self.entries():
            key = e.vin or (e.vehicle or "(unknown)")
            g = groups.setdefault(key, {
                "vin": e.vin, "names": set(), "ecus": set(), "logs": 0,
                "real_logs": 0, "simulated_logs": 0,
                "first": None, "last": None, "kinds": set(),
            })
            g["logs"] += 1
            g["simulated_logs" if e.simulation else "real_logs"] += 1
            g["kinds"].add(e.kind)
            if e.vehicle:
                g["names"].add(e.vehicle)
            if e.ecu:
                g["ecus"].add(e.ecu)
            if e.stamp:
                if g["first"] is None or e.stamp < g["first"]:
                    g["first"] = e.stamp
                if g["last"] is None or e.stamp > g["last"]:
                    g["last"] = e.stamp

        out = []
        for key, g in groups.items():
            out.append({
                "key": key,
                "vin": g["vin"],
                "names": sorted(g["names"]),
                "ecus": sorted(g["ecus"]),
                "kinds": sorted(g["kinds"]),
                "logs": g["logs"],
                "real_logs": g["real_logs"],
                "simulated_logs": g["simulated_logs"],
                "first_seen": g["first"].isoformat(sep=" ") if g["first"] else "",
                "last_seen": g["last"].isoformat(sep=" ") if g["last"] else "",
            })
        out.sort(key=lambda v: v["last_seen"], reverse=True)
        return out

    def stats(self) -> dict[str, Any]:
        entries = self.entries()
        real = [e for e in entries if not e.simulation]
        return {
            "roots": [str(r) for r in paths.configured_roots()],
            "roots_present": [str(r) for r in paths.existing_roots()],
            "total_logs": len(entries),
            "fes_logs": sum(1 for e in entries if e.kind == "fes"),
            "scan_logs": sum(1 for e in entries if e.kind == "scan"),
            "simulated_logs": sum(1 for e in entries if e.simulation),
            "real_logs": len(real),
            "parse_errors": [
                {"file": e.name, "error": e.parse_error}
                for e in entries if e.parse_error
            ],
            "vehicles": len(self.vehicles()),
            "oldest": min((e.timestamp for e in entries if e.stamp), default=""),
            "newest": max((e.timestamp for e in entries if e.stamp), default=""),
        }


def _parse_bound(value: str) -> datetime | None:
    """Accept ``YYYY-MM-DD``, a full ISO datetime, or a raw ``YYMMDDHHMM``."""
    if not value or not value.strip():
        return None
    v = value.strip()
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        pass
    stamped = parse_stamp(v)
    if stamped:
        return stamped
    raise ValueError(
        f"unrecognised date {value!r}; use YYYY-MM-DD, an ISO datetime, "
        "or a MES YYMMDDHHMM stamp"
    )


#: Process-wide index. Cheap to share -- it holds only metadata, and every
#: entry revalidates against (mtime, size) on access.
CATALOG = Catalog()


def resolve_or_latest(name: str, *, kind: str = "", vehicle: str = "",
                      vin: str = "") -> LogEntry:
    """Resolve an explicit filename, or fall back to the newest match."""
    if name and name.strip():
        return CATALOG.by_name(name.strip())
    entry = CATALOG.latest(kind=kind, vehicle=vehicle, vin=vin)
    if entry is None:
        raise MesNotFound("no logs match the given filters")
    return entry


def iter_dtc_history(entries: Iterable[LogEntry]) -> dict[str, dict[str, Any]]:
    """Aggregate DTC occurrences across logs, counting *files* not mentions.

    v1 counted regex hits, so a code read, cleared and re-read inside one
    session appeared as two sightings of a recurring fault. Occurrences are
    keyed by file here, and both ends of the history are kept -- a code seen
    once last week and one seen in nine sessions across a year are different
    problems, and printing only "latest" hides which is which.
    """
    from . import fes, scan

    history: dict[str, dict[str, Any]] = {}
    for e in entries:
        if e.parse_error:
            continue
        try:
            if e.kind == "scan":
                log = scan.load_scan(e.path, timestamp=e.timestamp)
                dtcs = log.all_dtcs
            else:
                log = fes.load_fes(e.path, timestamp=e.timestamp)
                dtcs = log.dtcs
        except Exception:
            continue

        for d in dtcs:
            rec = history.setdefault(d.full, {
                "dtc": d.full,
                "descriptions": set(),
                "modules": set(),
                "vehicles": set(),
                "vins": set(),
                "files": [],
                "statuses": set(),
                "first_seen": "",
                "last_seen": "",
            })
            if d.description:
                rec["descriptions"].add(d.description)
            if d.module:
                rec["modules"].add(d.module)
            if e.vehicle:
                rec["vehicles"].add(e.vehicle)
            if e.vin:
                rec["vins"].add(e.vin)
            rec["statuses"].add(d.status.value)
            if e.name not in [f["file"] for f in rec["files"]]:
                rec["files"].append({"file": e.name, "timestamp": e.timestamp})

    for rec in history.values():
        stamps = sorted(f["timestamp"] for f in rec["files"] if f["timestamp"])
        rec["first_seen"] = stamps[0] if stamps else ""
        rec["last_seen"] = stamps[-1] if stamps else ""
        rec["file_count"] = len(rec["files"])
        for k in ("descriptions", "modules", "vehicles", "vins", "statuses"):
            rec[k] = sorted(rec[k])
    return history
