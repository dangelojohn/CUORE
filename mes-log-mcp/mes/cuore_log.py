"""Read-only access to CUORE's own live-scan state, for the same tool
surface MES logs already get: list / latest / read / search / export, plus
a merged timeline and basic log hygiene (archive, integrity).

**Nothing here writes to ``CUORE_STATE_DIR``** except :func:`log_archive`,
which only ever *copies* the existing append-only files into a dated,
read-only snapshot folder -- never truncates or deletes the originals.

Grouping observations into "scans" is real logic (see
``cuore.live.scanlog``'s own docstring for the window/coverage/status
rules) and is deliberately **not** reimplemented here: this module imports
``cuore.live.scanlog`` defensively (``mes`` otherwise never imports
``cuore`` -- see ``mes.live_obs`` / ``mes.jobs.state_dir`` for the usual
"mirror the path, never the package" convention) and degrades to a clear
error if the ``cuore`` package is not on the path at all. Everything that
is *not* the grouping rule -- raw observations, owner events, attested
mechanic inputs, job/hypothesis audit lines, recording headers -- is read
directly off disk here, the same way every other ``mes.*`` store already
reads its own JSONL file.

File map under ``CUORE_STATE_DIR`` (see :func:`state_dir`):

* ``observations.jsonl`` -- every from-car read, append-only (owned by
  ``cuore.live.store``; grouped into scans by ``cuore.live.scanlog``).
* ``owner_events.jsonl`` -- what a person reported (``cuore.live.owner_events``).
* ``attested.jsonl`` -- what a mechanic typed against an UNKNOWN marker
  (``cuore.live.attested``).
* ``jobs.jsonl`` -- the hypothesis/action audit trail for a visit (``mes.jobs``,
  already in this package).
* ``recordings/*.csv`` -- CSV traces in the MES graph-CSV shape (``cuore.live.poller.CsvRecorder``).
* ``scans/<vin>/SCAN_*.txt`` -- MES-format exports of a live scan
  (``cuore.live.scanlog.write_mes_export``); see ``mes.catalog`` for how
  these rejoin the MES log corpus.
* ``archive/<stamp>[-label]/`` -- dated snapshots written only by
  :func:`log_archive` here.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import jobs as jobs_mod
from . import live_obs

# --- defensive import of cuore.live.scanlog --------------------------------
#
# Grouping from-car observations into "scans" is one real, documented rule
# (window, coverage, complete/partial/attempt) and must never be duplicated
# here. If the ``cuore`` package is not importable as-is (this package is
# normally run standalone), the repo root -- two levels up from this file,
# ``mes-log-mcp/mes/cuore_log.py`` -> ``mcp-servers`` -- is tried once, the
# same fallback every ``mes-log-mcp/tests/check_*`` script already uses to
# reach ``cuore.*``. Either way this import never raises: every public
# function here reports a clear error instead of crashing the server.
_scanlog: Any = None
_scan_health_bridge: Any = None
CUORE_LIVE_AVAILABLE = False

try:
    from cuore.live import scanlog as _scanlog  # type: ignore
    CUORE_LIVE_AVAILABLE = True
except ImportError:
    _repo_root = Path(__file__).resolve().parents[2]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))
    try:
        from cuore.live import scanlog as _scanlog  # type: ignore
        CUORE_LIVE_AVAILABLE = True
    except ImportError:
        _scanlog = None
        CUORE_LIVE_AVAILABLE = False

if CUORE_LIVE_AVAILABLE:
    try:
        from cuore.services import scan_health_bridge as _scan_health_bridge  # type: ignore
    except ImportError:
        _scan_health_bridge = None


class CuoreLiveUnavailable(RuntimeError):
    """The ``cuore`` package (hence ``cuore.live.scanlog``) is not importable."""


def _require_scanlog() -> Any:
    if _scanlog is None:
        raise CuoreLiveUnavailable(
            "cuore.live.scanlog is not importable -- cannot group observations "
            "into scans. Raw search/archive/integrity still work; list/latest/"
            "read/export of scans needs the cuore package on the path.")
    return _scanlog


# --- where everything lives -------------------------------------------------

#: Same candidates, first *writable* one wins -- mirrors ``cuore.live.config.
#: state_dir()`` without importing it (``mes.jobs.state_dir`` already does
#: this for ``jobs.jsonl``; reused here for every other file in the same
#: directory).
state_dir = jobs_mod.state_dir

_STORE_FILES = ("observations.jsonl", "owner_events.jsonl", "attested.jsonl", "jobs.jsonl")


def _owner_events_path() -> Path:
    return state_dir() / "owner_events.jsonl"


def _attested_path() -> Path:
    return state_dir() / "attested.jsonl"


def _jobs_path() -> Path:
    return jobs_mod.store_path()


def _observations_path() -> Path:
    return live_obs.observations_path()


def recordings_dir() -> Path:
    return state_dir() / "recordings"


def scans_export_dir() -> Path:
    """Where ``cuore.live.scanlog.write_mes_export`` writes MES-format scan
    exports -- see ``mes.catalog`` for the second log root built on this."""
    return state_dir() / "scans"


def archive_dir() -> Path:
    return state_dir() / "archive"


_SOURCE_PATHS = {
    "observations": _observations_path,
    "owner_events": _owner_events_path,
    "attested": _attested_path,
    "jobs": _jobs_path,
}


# --- date bounds -------------------------------------------------------------

def _bound(value: str, *, end: bool) -> str:
    """A bare ``YYYY-MM-DD`` is padded to the start/end of that day so a
    string compare against an ``at``/``started`` ISO timestamp (always
    ``YYYY-MM-DDTHH:MM:SS``) behaves as an inclusive day, not a prefix
    that only matches midnight exactly."""
    v = (value or "").strip()
    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        return v + ("T23:59:59" if end else "T00:00:00")
    return v


def _in_bounds(stamp: str, since: str, until: str) -> bool:
    if not stamp:
        return not since and not until
    if since and stamp < _bound(since, end=False):
        return False
    if until and stamp > _bound(until, end=True):
        return False
    return True


# --- scan kind (full | guided | partial | attempt) --------------------------

def scan_kind(scan: dict[str, Any]) -> str:
    """``"full"``/``"guided"``/``"partial"``/``"attempt"`` from a scan's own
    ``status`` (``cuore.live.scanlog``'s complete/partial/attempt) plus its
    ``coverage.guided`` flag -- never a fourth, invented state."""
    status = scan.get("status")
    if status == "complete":
        cov = scan.get("coverage") or {}
        return "guided" if cov.get("guided") else "full"
    if status in ("partial", "attempt"):
        return status
    return status or "unknown"


def _health_verdict_line(vin: str, scan_id: str) -> Optional[str]:
    """One line from ``cuore.services.scan_health_bridge`` if importable,
    else ``None`` -- never a guess at what the verdict would have been."""
    if _scan_health_bridge is None:
        return None
    try:
        report = _scan_health_bridge.build_cached(vin, scan_id)
        v = report.get("verdict") or {}
        label = v.get("label") or v.get("state")
        basis = v.get("basis") or []
        if not label:
            return None
        return f"{label} -- {basis[0]}" if basis else str(label)
    except Exception:
        return None


# --- public: scans -----------------------------------------------------------

def list_scans(vin: str, since: str = "", until: str = "", kind: str = "") -> list[dict[str, Any]]:
    """Scan summaries for one VIN, newest first, each tagged with its
    ``kind`` (full/guided/partial/attempt). ``since``/``until`` filter on
    the scan's own ``started`` timestamp."""
    scanlog = _require_scanlog()
    out: list[dict[str, Any]] = []
    for s in scanlog.list_scans(vin):
        k = scan_kind(s)
        if kind and kind.strip().lower() != k:
            continue
        if not _in_bounds(s.get("started") or "", since, until):
            continue
        row = dict(s)
        row["kind"] = k
        out.append(row)
    return out


def latest_scan(vin: str) -> Optional[dict[str, Any]]:
    scans = list_scans(vin)
    return scans[0] if scans else None


def read_scan(vin: str, scan_id: str) -> Optional[dict[str, Any]]:
    """The full scan dict (codes by status, freeze frames, Mode 06, Mode 09
    header extras where read, readiness, coverage), plus ``kind`` and a
    ``health_verdict`` one-liner when ``cuore.services.scan_health_bridge``
    is importable."""
    scanlog = _require_scanlog()
    scan = scanlog.get_scan(vin, scan_id)
    if scan is None:
        return None
    out = dict(scan)
    out["kind"] = scan_kind(scan)
    out["health_verdict"] = _health_verdict_line(vin, scan_id)
    return out


def export_scan(vin: str, scan_id: str, fmt: str = "json") -> dict[str, Any]:
    """``{"filename", "media_type", "content"}`` -- ``fmt="mes"`` renders the
    same ``SCAN_YYMMDDHHMM.txt`` text ``write_mes_export`` writes to disk
    (round-trips through ``mes.scan.parse_scan_text``); ``fmt="json"``
    returns the scan dict itself. Raises :class:`LookupError` if the scan
    does not exist for this VIN."""
    scanlog = _require_scanlog()
    scan = scanlog.get_scan(vin, scan_id)
    if scan is None:
        raise LookupError(f"no scan {scan_id!r} for VIN {vin!r}")
    fmt = (fmt or "json").strip().lower()
    if fmt == "mes":
        return {"filename": f"{scan_id}.txt", "media_type": "text/plain",
                "content": scanlog.export_mes_text(scan)}
    out = dict(scan)
    out["kind"] = scan_kind(scan)
    return {"filename": f"{scan_id}.json", "media_type": "application/json", "content": out}


# --- public: search -----------------------------------------------------------

_ALL_SOURCES = ("observations", "owner_events", "attested", "jobs", "recordings")


def _line_at(line: str) -> Optional[str]:
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if isinstance(obj, dict):
        at = obj.get("at")
        return str(at) if at else None
    return None


def search(pattern: str, since: str = "", until: str = "",
           kinds: Optional[list[str]] = None, context_lines: int = 2,
           max_matches: int = 40) -> dict[str, Any]:
    """Regex search (case-insensitive) across every CUORE log, newest first:
    observations (all kinds, any VIN), owner events, attested mechanic
    inputs, the jobs/hypothesis audit trail, and recording file headers.

    Same result shape as ``server.search_logs``: ``{"source", "file",
    "line", "at", "match", "context"}`` per hit.
    """
    import re
    rx = re.compile(pattern, re.IGNORECASE)
    want = {k.strip().lower() for k in (kinds or []) if k.strip()} or set(_ALL_SOURCES)

    hits: list[dict[str, Any]] = []

    for name in ("observations", "owner_events", "attested", "jobs"):
        if name not in want:
            continue
        path = _SOURCE_PATHS[name]()
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
            if lines and lines[-1] == "":
                lines.pop()  # trailing newline, not a record (JSONL splits on LF only: U+2028 etc. live inside records)
        except OSError:
            continue
        for i, line in enumerate(lines):
            if not rx.search(line):
                continue
            at = _line_at(line)
            if not _in_bounds(at or "", since, until):
                continue
            lo, hi = max(0, i - context_lines), min(len(lines), i + context_lines + 1)
            hits.append({
                "source": name, "file": path.name, "line": i + 1, "at": at,
                "match": line.strip()[:500],
                "context": [f"{j + 1}: {lines[j][:500]}" for j in range(lo, hi)],
            })

    if "recordings" in want:
        rdir = recordings_dir()
        if rdir.is_dir():
            try:
                csvs = sorted(rdir.glob("*.csv"))
            except OSError:
                csvs = []
            for p in csvs:
                try:
                    with p.open("r", encoding="utf-8", errors="replace") as fh:
                        head = [fh.readline().rstrip("\r\n"), fh.readline().rstrip("\r\n")]
                    head = [h for h in head if h]
                except OSError:
                    continue
                for i, line in enumerate(head):
                    if rx.search(line):
                        hits.append({
                            "source": "recordings", "file": p.name, "line": i + 1,
                            "at": None, "match": line.strip()[:500],
                            "context": [f"{j + 1}: {head[j][:500]}" for j in range(len(head))],
                        })

    # Newest first by `at` where known; undated rows (recordings headers)
    # sort after every dated hit, in filename order (already sorted above).
    hits.sort(key=lambda h: h.get("at") or "", reverse=True)
    truncated = len(hits) > max_matches
    return {"count": min(len(hits), max_matches), "truncated": truncated,
           "matches": hits[:max_matches]}


# --- public: unified timeline -------------------------------------------------

def logs_timeline(vin: str, since: str = "", until: str = "") -> dict[str, Any]:
    """MES logs and CUORE scans merged into one newest-first list, each row
    tagged with ``source`` (``"MES scan"``, ``"MES FES"``, or ``"CUORE
    full"``/``"guided"``/``"partial"``/``"attempt"``) so one visit can be
    read end to end without juggling two tools."""
    from . import catalog as catalog_mod

    rows: list[dict[str, Any]] = []
    for e in catalog_mod.CATALOG.select(vin=vin, since=since, until=until):
        source = "MES FES" if e.kind == "fes" else "MES scan"
        row = {"source": source, "file": e.name, "timestamp": e.timestamp, "vin": e.vin}
        provenance = getattr(e, "provenance", "") or None
        if provenance:
            row["provenance"] = provenance
        rows.append(row)

    if CUORE_LIVE_AVAILABLE:
        for s in list_scans(vin, since=since, until=until):
            rows.append({
                "source": f"CUORE {s['kind']}", "file": s["id"],
                "timestamp": s.get("started"), "vin": s.get("vin"),
                "mil": s.get("mil"), "status": s.get("status"),
            })

    rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return {"vin": vin, "count": len(rows), "entries": rows}


# --- public: log hygiene ------------------------------------------------------

def log_dir() -> dict[str, Any]:
    """Where every CUORE log lives, and the size each append-only file has
    grown to -- ``observations.jsonl`` in particular only ever grows; see
    :func:`log_archive` for the safe way to snapshot it, never to shrink it."""
    d = state_dir()
    files: dict[str, Any] = {}
    for name in _STORE_FILES:
        p = d / name
        files[name] = {"exists": p.exists(),
                      "size_bytes": p.stat().st_size if p.exists() else 0}
    rdir = recordings_dir()
    sdir = scans_export_dir()
    return {
        "state_dir": str(d),
        "files": files,
        "recordings_dir": str(rdir),
        "recordings_count": len(list(rdir.glob("*.csv"))) if rdir.is_dir() else 0,
        "scans_export_dir": str(sdir),
        "archive_dir": str(archive_dir()),
        "cuore_live_available": CUORE_LIVE_AVAILABLE,
        "note": ("observations.jsonl (and every other file here) is append-only "
                "and is never rotated or truncated automatically. Use "
                "cuore_log_archive for a dated, hashed snapshot before a file "
                "gets unwieldy -- it only ever copies, never deletes."),
    }


def log_archive(label: str = "") -> dict[str, Any]:
    """Copy every known CUORE log file as it stands right now into
    ``CUORE_STATE_DIR/archive/<timestamp>[-label]/``, with a per-file
    sha256 in ``manifest.json``. Read-only toward the originals: this
    function never opens them for writing, let alone truncates or deletes
    them."""
    d = state_dir()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    # The label becomes a directory name: keep it to one safe path component
    # (a label such as "x/../../y" or "..\\.." must not place the copies, or
    # the manifest, outside the archive folder).
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", label.strip()).strip(" .")[:60]
    name = f"{stamp}-{safe}" if safe else stamp
    root = archive_dir()
    dest = root / name
    n = 1
    while dest.exists():  # same-second archives must not overwrite each other
        n += 1
        dest = root / f"{name}-{n}"
    dest.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "label": label.strip() or None, "files": [],
    }
    for fname in _STORE_FILES:
        src = d / fname
        if not src.exists():
            continue
        data = src.read_bytes()  # read-only: never reopened for write below
        digest = hashlib.sha256(data).hexdigest()
        (dest / fname).write_bytes(data)
        manifest["files"].append({"file": fname, "sha256": digest, "size_bytes": len(data)})

    manifest_path = dest / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"archive_dir": str(dest), "manifest": manifest}


def log_integrity() -> dict[str, Any]:
    """Every JSONL store, line by line: does it parse, and counts per
    ``kind``/``op`` and per calendar day. A line that fails to parse is
    reported, never silently skipped from the count."""
    d = state_dir()
    report: dict[str, Any] = {}
    for fname in _STORE_FILES:
        p = d / fname
        if not p.exists():
            report[fname] = {"exists": False}
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
            if lines and lines[-1] == "":
                lines.pop()
        except OSError as exc:
            report[fname] = {"exists": True, "error": str(exc)}
            continue
        by_kind: dict[str, int] = {}
        by_day: dict[str, int] = {}
        errors: list[dict[str, Any]] = []
        parsed = 0
        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError as exc:
                errors.append({"line": i + 1, "error": str(exc)})
                continue
            parsed += 1
            if isinstance(obj, dict):
                key = str(obj.get("kind") or obj.get("op") or "?")
                by_kind[key] = by_kind.get(key, 0) + 1
                day = str(obj.get("at") or "")[:10]
                if day:
                    by_day[day] = by_day.get(day, 0) + 1
        report[fname] = {"exists": True, "lines": len(lines), "parsed": parsed,
                         "parse_errors": errors, "by_kind": by_kind, "by_day": by_day}
    return report


__all__ = [
    "CUORE_LIVE_AVAILABLE", "CuoreLiveUnavailable", "state_dir", "recordings_dir",
    "scans_export_dir", "archive_dir", "scan_kind", "list_scans", "latest_scan",
    "read_scan", "export_scan", "search", "logs_timeline", "log_dir",
    "log_archive", "log_integrity",
]
