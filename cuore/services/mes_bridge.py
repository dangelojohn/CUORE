"""The only module in CUORE that imports :mod:`mes`.

Every route reaches the analysis library through here. That is deliberate:
``mes-log-mcp/server.py`` already exposes this library as MCP tools, and the
two surfaces must not drift. Each function below mirrors its MCP counterpart
call-for-call, so a change in the library shows up identically in both.

Nothing here re-implements analysis. Chronic classification, TSB matching,
fault-tree content and the evidence gate's criteria live in ``mes`` and are
unit-tested there against the real corpus; this file only calls them and
translates "no result" into an exception the HTTP layer can turn into a
status code.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from .errors import BadRequest, NotFound

from mes import (  # noqa: E402  -- must follow the bootstrap import
    analysis,
    catalog,
    compare,
    csvlog,
    dealer as dealer_mod,
    dtc as dtc_mod,
    encoding,
    faulttree,
    fes,
    knowledge,
    modules,
    notes as notes_mod,
    paths,
    scan,
    verdict,
)
from mes import workup as workup_mod  # noqa: E402
from mes.errors import MesError  # noqa: E402

CATALOG = catalog.CATALOG


# --- corpus ---------------------------------------------------------------


def corpus_status() -> dict[str, Any]:
    """Health and inventory: roots, real vs simulated counts, parse errors."""
    return CATALOG.stats()


def log_roots() -> dict[str, Any]:
    """The MES log directories being watched, and whether they exist."""
    return {
        "configured": [str(r) for r in paths.configured_roots()],
        "existing": [str(r) for r in paths.existing_roots()],
        "csv_configured": [str(r) for r in paths.csv_roots()],
        "csv_existing": [str(r) for r in paths.existing_csv_roots()],
        "env_overrides": ["MES_LOG_DIRS", "MES_LOG_DIR",
                          "MES_CSV_DIRS", "MES_CSV_DIR"],
    }


def vehicles(*, real_only: bool = False) -> list[dict[str, Any]]:
    """Every distinct vehicle in the corpus, keyed by VIN where recoverable.

    ``real_only`` keeps the two cars that actually exist -- a resolvable VIN
    and at least one non-simulated log -- and drops the simulation pseudo
    vehicles, whose "VIN" is MES's practice-data placeholder.
    """
    found = CATALOG.vehicles()
    if not real_only:
        return found
    return [v for v in found
            if v.get("real_logs", 0) > 0 and len(v.get("vin", "")) >= 11]


def newest_mtime(vin: str = "") -> float:
    """Newest file mtime across a vehicle's logs -- the cache key for workup."""
    entries = CATALOG.select(vin=vin) if vin else CATALOG.entries()
    return max((e.mtime for e in entries), default=0.0)


# --- logs -----------------------------------------------------------------


def list_logs(*, kind: str = "", vehicle: str = "", vin: str = "",
              since: str = "", until: str = "", limit: int = 30,
              include_simulation: bool = False) -> dict[str, Any]:
    """Filtered log index, newest first by session timestamp."""
    entries = CATALOG.select(kind=kind, vehicle=vehicle, vin=vin, since=since,
                             until=until, limit=limit,
                             include_simulation=include_simulation)
    return {
        "count": len(entries),
        "filters": {"kind": kind, "vehicle": vehicle, "vin": vin,
                    "since": since, "until": until,
                    "include_simulation": include_simulation},
        "logs": [e.to_dict() for e in entries],
    }


def read_log(name: str, *, max_bytes: int = 200_000) -> dict[str, Any]:
    """Read one MES log verbatim.

    Resolution goes through :func:`mes.paths.resolve_log`, which requires a
    bare filename matching a MES log pattern and verifies the fully resolved
    real path is inside a configured root. That check is the whole security
    boundary of this endpoint: an earlier version of the MCP server built the
    path by concatenation, which on Windows let both ``..`` and an absolute
    path escape it. Do not replace this with ``Path(root) / name``.
    """
    try:
        path = paths.resolve_log(name)
    except MesError as exc:
        raise BadRequest(str(exc)) from exc

    decoded = encoding.read_log_text(path, max_bytes=max_bytes)
    kind, raw_stamp, vehicle = paths.classify_name(path.name)
    stamp = catalog.parse_stamp(raw_stamp)
    out: dict[str, Any] = {
        "file": path.name,
        "kind": kind,
        "timestamp": stamp.isoformat(sep=" ") if stamp else raw_stamp,
        "vehicle": vehicle,
        "encoding": decoded.encoding,
        "size_bytes": decoded.size_bytes,
        "truncated": decoded.truncated,
        "text": decoded.text,
    }
    if decoded.control_chars:
        out["stray_control_bytes_removed"] = decoded.control_chars
    if "SIMULATION MODE" in decoded.text:
        out["simulation"] = True
        out["warning"] = "SIMULATION MODE - this data is not from a vehicle"
    elif kind == "scan":
        out["provenance"] = ("unverifiable - SCAN logs carry no simulation "
                             "marker")
    return out


def search_logs(pattern: str, *, kind: str = "", vehicle: str = "",
                vin: str = "", context_lines: int = 2, max_matches: int = 40,
                include_simulation: bool = False) -> dict[str, Any]:
    """Case-insensitive regex search across logs, newest first."""
    if not pattern.strip():
        raise BadRequest("a search pattern is required")
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise BadRequest(f"invalid regular expression: {exc}") from exc

    entries = CATALOG.select(kind=kind, vehicle=vehicle, vin=vin,
                             include_simulation=include_simulation)
    hits: list[dict[str, Any]] = []
    for entry in entries:
        try:
            lines = encoding.read_log_text(entry.path).splitlines()
        except Exception as exc:  # one unreadable file must not sink a search
            hits.append({"file": entry.name, "error": str(exc)})
            continue
        for i, line in enumerate(lines):
            if not rx.search(line):
                continue
            lo = max(0, i - context_lines)
            hi = min(len(lines), i + context_lines + 1)
            hits.append({
                "file": entry.name,
                "timestamp": entry.timestamp,
                "simulation": entry.simulation,
                "line": i + 1,
                "match": line.strip(),
                "context": [f"{j + 1}: {lines[j]}" for j in range(lo, hi)],
            })
            if len(hits) >= max_matches:
                return {"count": len(hits), "truncated": True,
                        "matches": hits}
    return {"count": len(hits), "truncated": False, "matches": hits}


# --- per-vehicle analysis -------------------------------------------------


def workup(vin: str = "", vehicle: str = "") -> dict[str, Any]:
    """The pre-work dossier. Raises :class:`NotFound` when no logs match."""
    dossier = workup_mod.build(vin=vin, vehicle=vehicle)
    if "error" in dossier:
        raise NotFound(dossier["error"])
    return dossier


def vehicle_report(vin: str = "", vehicle: str = "") -> dict[str, Any]:
    """Identity, odometer span and chronic faults for one vehicle."""
    report = analysis.vehicle_summary(vin=vin, vehicle=vehicle)
    if "error" in report:
        raise NotFound(report["error"])
    return report


def live_vs_log(vin: str, module: str = "") -> dict[str, Any]:
    """Newest log read vs newest live read, one row per code, per module.

    Passthrough to :func:`mes.compare.live_vs_log`; see that module for the
    join and classification rules.
    """
    if not vin.strip():
        raise BadRequest("a VIN is required")
    result = compare.live_vs_log(vin, module=module)
    if "error" in result:
        raise BadRequest(result["error"])
    return result


def _classified(record: Any) -> dict[str, Any]:
    """A DTC record as a dict, with its classification made explicit.

    ``DtcRecord.to_dict`` reports the classification only as a prose
    ``assessment`` string; ``chronic`` and ``returned_after_clear`` are
    properties that do not survive serialisation. Clients need the booleans to
    colour a row, and re-deriving "chronic" from the odometer span in a
    template would fork the rule -- so read the library's own properties here
    and publish them. One definition, in ``mes.analysis.DtcRecord``.

    ``severity`` collapses the same facts onto the four states the UI shows,
    ordered by what changes a decision: a code that came back after a clear is
    live and reproducing; a chronic one has persisted over distance; a cleared
    one proves nothing until a monitor re-runs.
    """
    out = record.to_dict()
    out["chronic"] = record.chronic
    out["returned_after_clear"] = record.returned_after_clear

    if record.returned_after_clear:
        severity = "returned"
    elif record.chronic:
        severity = "chronic"
    elif "cleared" in record.statuses and record.session_count <= 1:
        severity = "cleared"
    elif record.session_count <= 1:
        severity = "seen-once"
    else:
        severity = "recurring"
    out["severity"] = severity
    return out


def extract_dtcs(*, vin: str = "", vehicle: str = "", since: str = "",
                 include_simulation: bool = False) -> dict[str, Any]:
    """Every DTC with first-seen, last-seen, session count and odometer span.

    Ordered so the codes that decide a diagnosis come first: returned-after-
    clear, then chronic, then the rest.
    """
    entries = CATALOG.select(vin=vin, vehicle=vehicle, since=since,
                             include_simulation=include_simulation)
    history = analysis.dtc_history(entries)
    records = sorted(history.values(),
                     key=lambda r: (not r.returned_after_clear,
                                    not r.chronic, r.dtc))
    return {
        "count": len(records),
        "logs_considered": len(entries),
        "simulation_included": include_simulation,
        "dtcs": [_classified(r) for r in records],
    }


def dtc_history(code: str, *, vin: str = "") -> dict[str, Any]:
    """One code's complete life across sessions."""
    wanted = code.strip().upper()
    if not wanted:
        raise BadRequest("a DTC is required")
    history = analysis.dtc_history(vin=vin)
    matches = {k: v for k, v in history.items()
               if wanted in (k, k.split("-")[0])}
    if not matches:
        raise NotFound(
            f"{wanted} appears in no real log for this vehicle "
            "(simulation logs are excluded by default)")
    return {"code": wanted,
            "matches": [_classified(r) for r in matches.values()]}


def freeze_frames(*, code: str = "", name: str = "",
                  vin: str = "") -> dict[str, Any]:
    """The ~25 parameters captured when a code set.

    This is the evidence that separates a cold-start fault from a highway one,
    and it is destroyed by a clear -- which is why the UI reads it before
    offering one.
    """
    wanted = code.strip().upper()
    if name.strip():
        try:
            entries = [CATALOG.by_name(name)]
        except MesError as exc:
            raise NotFound(str(exc)) from exc
    else:
        entries = CATALOG.select(kind="fes", vin=vin)

    found: list[dict[str, Any]] = []
    for entry in entries:
        if entry.kind != "fes" or entry.parse_error:
            continue
        log = fes.load_fes(entry.path, timestamp=entry.timestamp)
        for d in log.dtcs:
            if wanted and wanted not in (d.full, d.code):
                continue
            if not d.freeze_frame:
                continue
            found.append({
                "dtc": d.full,
                "description": d.description,
                "status": d.status.value,
                "status_meaning": d.status.explanation,
                "file": entry.name,
                "timestamp": entry.timestamp,
                "ecu": log.ecu_description,
                "vin": log.vin,
                "freeze_frame": {k: v.display
                                 for k, v in d.freeze_frame.items()},
            })
    if not found:
        raise NotFound(f"no freeze frame for {code or '(any code)'}")
    return {"count": len(found), "frames": found}


def actuator_history(*, vin: str = "", operation: str = "") -> dict[str, Any]:
    """Every actuator test and adjustment ever run, and why any failed."""
    entries = CATALOG.select(kind="fes", vin=vin)
    runs: list[dict[str, Any]] = []
    for entry in entries:
        if entry.parse_error:
            continue
        log = fes.load_fes(entry.path, timestamp=entry.timestamp)
        for a in log.actuators:
            if operation.strip() and operation.lower() not in a.operation.lower():
                continue
            row = a.to_dict()
            row.update({"file": entry.name, "timestamp": entry.timestamp,
                        "ecu": log.ecu_description})
            runs.append(row)
    runs.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    failed = [r for r in runs if r.get("outcome") == "FAILED TO EXECUTE"]
    return {
        "count": len(runs),
        "failed": len(failed),
        "runs": runs,
        "note": ("MES actuator tests on the IAW 10JA require key-on "
                 "engine-off; 'Engine running' is an interlock, not a fault."),
    }


# --- sessions and scans ---------------------------------------------------


def analyze_session(*, name: str = "", vin: str = "") -> dict[str, Any]:
    """One FES engineering session: identity, DTCs, clears, actuators."""
    try:
        entry = catalog.resolve_or_latest(name, kind="fes", vin=vin)
    except MesError as exc:
        raise NotFound(str(exc)) from exc
    log = fes.load_fes(entry.path, timestamp=entry.timestamp)
    out = log.to_dict()
    out["file"] = entry.name
    out["timestamp"] = entry.timestamp
    cleared = analysis.post_clear_assessment(log)
    if cleared:
        out["clear_assessment"] = cleared.to_dict()
    return out


def analyze_scan(*, name: str = "", vin: str = "") -> dict[str, Any]:
    """One all-systems SCAN: per-module status, with network-cascade detection."""
    try:
        entry = catalog.resolve_or_latest(name, kind="scan", vin=vin)
    except MesError as exc:
        raise NotFound(str(exc)) from exc
    log = scan.load_scan(entry.path, timestamp=entry.timestamp)
    out = log.to_dict()
    out["file"] = entry.name
    out["timestamp"] = entry.timestamp
    by_module = {m.name: m.dtcs for m in log.modules if m.dtcs}
    event = analysis.detect_network_event(by_module)
    if event:
        out["network_event"] = event.to_dict()
    out["provenance"] = ("unverifiable - SCAN logs carry no simulation marker")
    return out


def list_parameters(*, name: str = "", vin: str = "") -> dict[str, Any]:
    """Live parameters a FES session recorded, unioned across samples."""
    try:
        entry = catalog.resolve_or_latest(name, kind="fes", vin=vin)
    except MesError as exc:
        raise NotFound(str(exc)) from exc
    log = fes.load_fes(entry.path, timestamp=entry.timestamp)
    if not log.samples:
        return {"file": entry.name, "samples": 0,
                "note": "this session logged no live parameters"}
    return {
        "file": entry.name,
        "timestamp": entry.timestamp,
        "ecu": log.ecu_description,
        "samples": len(log.samples),
        "parameter_count": len(log.param_names()),
        "parameters": log.param_names(),
    }


def parameter_series(parameter: str, *, name: str = "",
                     vin: str = "") -> dict[str, Any]:
    """One session parameter as an ordered series with statistics."""
    try:
        entry = catalog.resolve_or_latest(name, kind="fes", vin=vin)
    except MesError as exc:
        raise NotFound(str(exc)) from exc
    log = fes.load_fes(entry.path, timestamp=entry.timestamp)
    series = log.series(parameter)
    if not series.samples:
        raise NotFound(f"'{parameter}' was not logged in {entry.name}")
    out = series.stats()
    out["file"] = entry.name
    out["values"] = [s.display for s in series.samples]
    out["timing_note"] = ("MES records no per-sample timestamp; order is file "
                          "order and the sample rate is unknown")
    if out.get("static"):
        out["interpretation"] = (
            "This value never changed across the whole session -- consistent "
            "with a substituted default or a modelled value rather than a "
            "live measurement. Confirm before treating it as a reading.")
    return out


# --- decision support -----------------------------------------------------


def fault_tree(codes: str = "", *, vin: str = "") -> dict[str, Any]:
    """Applicable isolation sequences, annotated with this car's evidence.

    Returns successfully even when nothing matches: the payload then carries
    the trees that *do* exist, which is the useful answer to "is there a tree
    for this?".
    """
    code_list = [c for c in re.split(r"[,\s;]+", codes) if c.strip()]
    if not code_list:
        return {
            "error": "no codes given",
            "available": [{"tree": t.key, "title": t.title,
                           "applies_to": sorted(t.codes)}
                          for t in faulttree.TREES],
        }
    return faulttree.evaluate(code_list, vin=vin)


def assess_verdict(*, vin: str, codes: str, component: str, mechanism: str,
                   measurements: str,
                   disconfirming_test: str) -> dict[str, Any]:
    """The evidence gate.

    The only non-read operation in the P1 surface, and it writes nothing to
    the car -- it evaluates a proposed diagnosis against four criteria and
    refuses CONFIRMED unless all of them hold.
    """
    result = verdict.assess(vin=vin, codes=codes, component=component,
                            mechanism=mechanism, measurements=measurements,
                            disconfirming_test=disconfirming_test)
    if "error" in result and "verdict" not in result:
        raise BadRequest(result["error"])
    return result


def open_codes_for(dossier: dict[str, Any]) -> list[str]:
    """The codes a dossier should route to a fault tree.

    Two sources, unioned:

    * the newest session that held findings -- preferred over the newest
      session outright, because the latter is often the empty post-clear
      re-read and routing off it produces "no codes" on a car that plainly
      has some;
    * every chronic or returned-after-clear code in the car's history.

    The second source matters more than it looks. On this Stelvio the newest
    session shows a cleared ``P0440`` while the code that actually decides the
    diagnosis is a chronic ``P0456`` spanning 26,500 km. Routing on the latest
    session alone would send the tree after the wrong fault.
    """
    codes: set[str] = set()

    current = dossier.get("current_picture", {})
    for key in ("last_session_with_findings", "latest_session"):
        session = current.get(key) or {}
        found = [d.get("code") or d.get("dtc") or ""
                 for d in session.get("dtcs", [])]
        found = [knowledge.base_code(c) for c in found if c]
        if found:
            codes.update(found)
            break

    history = dossier.get("history", {})
    for bucket in ("chronic", "returned_after_clear"):
        for record in history.get(bucket, []):
            raw = record.get("dtc") or record.get("code") or ""
            if raw:
                codes.add(knowledge.base_code(raw))

    return sorted(codes)


# --- dealer (wiTECH) results -----------------------------------------------


def dealer_record(vin: str, kind: str, data: dict[str, Any],
                  note: str = "") -> dict[str, Any]:
    """Record one technician-entered wiTECH result. Raises BadRequest on
    anything the store's per-kind validation rejects."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return dealer_mod.record(vin, kind, data, note=note)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def dealer_results(vin: str) -> dict[str, Any]:
    """Every dealer result recorded for this VIN, oldest first."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return {"vin": vin, "results": dealer_mod.load(vin)}


# --- technician notes -------------------------------------------------------


def add_note(vin: str, text: str, target_kind: str = "vehicle", target_id: str = "",
            author: str = "technician", tags: Optional[list[str]] = None) -> dict[str, Any]:
    """Record one technician note. Raises BadRequest on invalid input."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return notes_mod.add(vin, text, target_kind, target_id=target_id,
                             author=author, tags=tags)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def notes(vin: str, target_kind: str = "", target_id: str = "") -> dict[str, Any]:
    """Notes for this VIN, oldest first, filtered by target when given."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return {"vin": vin,
            "notes": notes_mod.load(vin, target_kind=target_kind or None,
                                    target_id=target_id)}


def edit_note(id: str, text: str) -> dict[str, Any]:
    """Amend a note's text. Never rewrites history."""
    try:
        return notes_mod.edit(id, text)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def hide_note(id: str) -> dict[str, Any]:
    """Hide a note (soft delete). Never rewrites history."""
    try:
        return notes_mod.hide(id)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


# --- reference ------------------------------------------------------------


def module_registry(*, abbrev: str = "", domain: str = "") -> dict[str, Any]:
    """The 126-module registry: one module, one domain, or the whole map."""
    if abbrev.strip():
        info = modules.describe(abbrev)
        if "error" in info:
            raise NotFound(info["error"])
        return info
    grouped = modules.by_domain()
    if domain.strip():
        key = domain.strip().lower()
        if key not in grouped:
            raise NotFound(f"unknown domain '{domain}'")
        return {"domain": key,
                "modules": [m.to_dict() for m in grouped[key]]}
    return {
        "stats": modules.registry_stats(),
        "by_domain": {d: [m.to_dict() for m in v]
                      for d, v in sorted(grouped.items())},
    }


def failure_type(byte: str) -> dict[str, Any]:
    """Decode the two hex digits after the dash in a UDS DTC."""
    ft = dtc_mod.failure_type(byte.strip())
    if ft is None:
        raise NotFound(f"no failure type for '{byte}'")
    return ft.to_dict()


# --- CSV recordings -------------------------------------------------------


def list_recordings() -> dict[str, Any]:
    """CSV recordings from MES's graph subsystem, newest first."""
    recs = csvlog.list_recordings()
    out: dict[str, Any] = {
        "count": len(recs),
        "recordings": recs,
        "roots": [str(r) for r in paths.csv_roots()],
    }
    if not recs:
        out["note"] = (
            "No CSV recordings found. In MES: Graph tab, add parameters, then "
            "CSV Start / Stop. The export lands in the Settings 'Export "
            "Folder'. Point MES_CSV_DIR at it if it differs from the log "
            "folder.")
    return out


def _recording(name: str):
    try:
        return csvlog.load_named(name)
    except MesError as exc:
        raise NotFound(str(exc)) from exc


def read_recording(name: str, *, preview_rows: int = 10) -> dict[str, Any]:
    """One recording: columns, measured timing, dropouts, TAG/DTC events."""
    return _recording(name).to_dict(preview_rows=preview_rows)


def recording_series(name: str, parameter: str) -> dict[str, Any]:
    """One recorded parameter as a *timed* series -- real timestamps, unlike
    a .txt session, so the statistics are physically meaningful."""
    rec = _recording(name)
    series = rec.series(parameter)
    if not series.samples:
        raise NotFound(f"'{parameter}' is not a column in {rec.name}")
    out = series.stats()
    out["file"] = rec.name
    out["values"] = [{"t": stamp, "value": s.display}
                     for stamp, s in zip(series.stamps, series.samples)]
    if out.get("static"):
        out["interpretation"] = (
            "This value never changed across the recording -- consistent with "
            "a substituted default rather than a live measurement.")
    return out


def recording_events(name: str, *, condition: str = "") -> dict[str, Any]:
    """TAG/DTC events and dropouts; with a condition, excursion intervals."""
    rec = _recording(name)
    out: dict[str, Any] = {
        "file": rec.name,
        "timing": rec.timing(),
        "tag_events": [t.to_dict() for t in rec.tags],
        "dtcs_in_tags": sorted({d for t in rec.tags for d in t.dtcs}),
    }
    if condition.strip():
        try:
            out["threshold"] = rec.crossings(condition)
        except MesError as exc:
            raise BadRequest(str(exc)) from exc
    return out


def recording_snapshot(name: str, at_seconds: float) -> dict[str, Any]:
    """The post-hoc freeze frame: every value at the sample nearest a time."""
    rec = _recording(name)
    return {"file": rec.name, **rec.snapshot(at_seconds)}
