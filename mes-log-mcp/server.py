"""MultiEcuScan log-bridge MCP server.

A thin tool surface over the :mod:`mes` package. All parsing, indexing and
analysis lives in the library so it can be tested and reused without MCP.

Design notes
------------
* Tools return **JSON**, not hand-formatted text. v1 returned tab-delimited
  strings that had to be re-parsed by eye and silently lost structure.
* Every tool that can be misled reports *why*: simulated logs are flagged and
  excluded by default, SCAN provenance is reported as unverifiable rather than
  clean, and a code cleared mid-session is never reported as merely "present".
* Filenames coming in from a caller are resolved through
  :func:`mes.paths.resolve_log`, which enforces containment. v1 concatenated
  the name onto the log directory, which on Windows let an absolute path or a
  ``..`` escape read any file on the machine.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from mes import analysis, catalog, compact, csvlog, dtc as dtc_mod, fes, modules, paths, scan
from mes import dealer as dealer_mod
from mes import notes as notes_mod
from mes import faulttree, verdict
from mes import workup as workup_mod
from mes.errors import MesError

mcp = FastMCP("mes-log")


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _json_compact(payload: Any) -> str:
    """Whitespace-free JSON for compact (detail=False) tool results.

    Pretty-printing with ``indent=2`` roughly doubles the size of a deeply
    nested structure, which defeats the point of a compact view. Only the
    formatting differs from :func:`_json`; the content is unaffected either
    way.
    """
    return json.dumps(payload, ensure_ascii=False, default=str,
                      separators=(",", ":"))


def _error(exc: Exception) -> str:
    return _json({"error": type(exc).__name__, "message": str(exc)})


def _guard(fn, *args, serialize=_json, **kwargs) -> str:
    try:
        return serialize(fn(*args, **kwargs))
    except MesError as exc:
        return _error(exc)
    except Exception as exc:  # never take the server down over one bad log
        return _error(exc)


# --- discovery ------------------------------------------------------------


@mcp.tool()
def status() -> str:
    """Health and inventory of the MES log corpus.

    Reports configured roots, how many logs are real vs simulated, how many
    vehicles are present, and any files that failed to parse.
    """
    return _guard(catalog.CATALOG.stats)


@mcp.tool()
def list_logs(kind: str = "", vehicle: str = "", vin: str = "",
              since: str = "", until: str = "", limit: int = 30,
              include_simulation: bool = False) -> str:
    """List MES logs, newest first by session timestamp.

    Args:
        kind: "fes" (engineering session), "scan" (all-systems scan), or "".
        vehicle: substring matched against the vehicle name AND the ECU
            description, so it works on SCAN logs whose filenames carry no
            vehicle.
        vin: substring matched against the VIN read from file content.
        since / until: "YYYY-MM-DD", an ISO datetime, or a raw YYMMDDHHMM.
        limit: maximum entries.
        include_simulation: include MES practice logs. Off by default -- most
            of the FES corpus is simulated and mixing it into a fault history
            is actively misleading.
    """
    def run():
        entries = catalog.CATALOG.select(
            kind=kind, vehicle=vehicle, vin=vin, since=since, until=until,
            include_simulation=include_simulation, limit=limit)
        return {
            "count": len(entries),
            "filters": {"kind": kind, "vehicle": vehicle, "vin": vin,
                        "since": since, "until": until,
                        "include_simulation": include_simulation},
            "logs": [e.to_dict() for e in entries],
        }
    return _guard(run)


@mcp.tool()
def latest_log(kind: str = "", vehicle: str = "", vin: str = "") -> str:
    """The newest log matching the filters, with its metadata."""
    def run():
        entry = catalog.CATALOG.latest(kind=kind, vehicle=vehicle, vin=vin)
        if entry is None:
            return {"error": "no logs match the given filters"}
        return entry.to_dict()
    return _guard(run)


@mcp.tool()
def vehicles() -> str:
    """Every distinct vehicle in the corpus, keyed by VIN where recoverable.

    VIN is read from file content, so SCAN logs -- whose filenames contain no
    vehicle at all -- are attributed correctly rather than left unassigned.
    """
    def run():
        return {"vehicles": catalog.CATALOG.vehicles()}
    return _guard(run)


# --- raw access -----------------------------------------------------------


@mcp.tool()
def read_log(name: str, max_bytes: int = 200_000) -> str:
    """Read a MES log verbatim by filename.

    Only files inside a configured MES log root whose names match a MES log
    pattern can be read.
    """
    def run():
        from mes import encoding
        path = paths.resolve_log(name)
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
            out["warning"] = ("SIMULATION MODE - this data is not from a "
                              "vehicle")
        elif kind == "scan":
            out["provenance"] = ("unverifiable - SCAN logs carry no "
                                 "simulation marker")
        return out
    return _guard(run)


@mcp.tool()
def search_logs(pattern: str, kind: str = "", vehicle: str = "", vin: str = "",
                context_lines: int = 2, max_matches: int = 40,
                include_simulation: bool = False) -> str:
    """Regex search across MES logs, newest first.

    Args:
        pattern: Python regex syntax, case-insensitive.
    """
    def run():
        import re
        from mes import encoding
        rx = re.compile(pattern, re.IGNORECASE)
        entries = catalog.CATALOG.select(
            kind=kind, vehicle=vehicle, vin=vin,
            include_simulation=include_simulation)
        hits: list[dict[str, Any]] = []
        for entry in entries:
            try:
                lines = encoding.read_log_text(entry.path).splitlines()
            except Exception as exc:
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
    return _guard(run)


# --- structured parsing ---------------------------------------------------


@mcp.tool()
def analyze_scan(name: str = "", vin: str = "", detail: bool = False) -> str:
    """Parse an all-systems SCAN log into per-module status.

    Deduplicates the module list, which MES repeats once per phase -- a naive
    count over-reports modules by 2-3x. Also runs network-cascade detection.

    Args:
        name: SCAN filename. Empty selects the newest matching scan.
        detail: False (default) returns a compact summary: modules WITH
            codes (plus a bare name list of the clean ones), post-clear
            results only where they differ from the scan phase, clear
            results as {module: outcome}, and priority as an ordered name
            list -- the full form repeats every module three times over.
            True returns the complete, unreduced structure.
    """
    def run():
        entry = catalog.resolve_or_latest(name, kind="scan", vin=vin)
        log = scan.load_scan(entry.path, timestamp=entry.timestamp)
        out = log.to_dict()
        by_module = {m.name: m.dtcs for m in log.modules if m.dtcs}
        event = analysis.detect_network_event(by_module)
        if event:
            out["network_event"] = event.to_dict()
        out["modules_by_priority"] = analysis.module_report(log.all_dtcs)
        if log.aborted:
            out["note"] = ("Scan aborted before reaching any module - the "
                           "adapter or vehicle connection failed. This file "
                           "cannot be attributed to a vehicle.")
        return out if detail else compact.compact_scan(out)
    return _guard(run, serialize=_json if detail else _json_compact)


@mcp.tool()
def analyze_session(name: str = "", vin: str = "",
                    include_samples: bool = False) -> str:
    """Parse a FES engineering session: identity, DTCs, clears, actuators.

    The clear-event model is the point of this tool. A code that was read,
    erased, and set again in the same session is reported as ``returned`` --
    a live, reproducing fault. A code erased and not seen again is reported as
    ``cleared``, with an explicit note that this is not proof of repair.

    Args:
        name: FESLog filename. Empty selects the newest matching session.
        include_samples: include every live-parameter sample. Off by default;
            one session in this corpus holds 99 samples of 133 parameters.
    """
    def run():
        entry = catalog.resolve_or_latest(name, kind="fes", vin=vin)
        log = fes.load_fes(entry.path, timestamp=entry.timestamp)
        out = log.to_dict(include_samples=include_samples)
        assessment = analysis.post_clear_assessment(log)
        if assessment:
            out["clear_assessment"] = assessment.to_dict()
        if log.failed_actuators:
            out["failed_actuators"] = [a.to_dict()
                                       for a in log.failed_actuators]
        return out
    return _guard(run)


@mcp.tool()
def get_freeze_frame(code: str = "", name: str = "", vin: str = "") -> str:
    """Freeze-frame conditions captured when a DTC was set.

    Every DTC in a FES log carries roughly 25 labelled parameters -- engine
    speed, coolant temperature, odometer, fuel level and the rest. This is the
    evidence that separates a cold-start fault from a highway one.

    Args:
        code: DTC to look up, with or without the failure-type byte
            ("P0456" or "P0456-00"). Empty returns every frame in the session.
        name: FESLog filename. Empty searches all matching sessions, newest
            first.
    """
    def run():
        wanted = code.strip().upper()
        entries = ([catalog.CATALOG.by_name(name)] if name.strip()
                   else catalog.CATALOG.select(kind="fes", vin=vin))
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
            return {"error": "no freeze frame found",
                    "code": code or "(any)", "file": name or "(any)"}
        return {"count": len(found), "frames": found}
    return _guard(run)


@mcp.tool()
def extract_dtcs(vin: str = "", vehicle: str = "", since: str = "",
                 include_simulation: bool = False) -> str:
    """Every DTC across the corpus with its full history.

    Reports first-seen AND last-seen, the session count, and the odometer span
    -- a code seen once last week and one recurring across a year are
    different problems, and printing only "latest" hides which is which.
    Occurrences are counted per file, not per regex hit.
    """
    def run():
        entries = catalog.CATALOG.select(
            vin=vin, vehicle=vehicle, since=since,
            include_simulation=include_simulation)
        history = analysis.dtc_history(entries)
        records = sorted(history.values(),
                         key=lambda r: (not r.returned_after_clear,
                                        not r.chronic, r.dtc))
        return {
            "count": len(records),
            "logs_considered": len(entries),
            "simulation_included": include_simulation,
            "dtcs": [r.to_dict() for r in records],
        }
    return _guard(run)


@mcp.tool()
def dtc_history(code: str, vin: str = "") -> str:
    """The complete history of one DTC: every session, status and odometer."""
    def run():
        wanted = code.strip().upper()
        history = analysis.dtc_history(vin=vin)
        matches = {k: v for k, v in history.items()
                   if wanted in (k, k.split("-")[0])}
        if not matches:
            return {"error": "code not found in any real log", "code": code,
                    "hint": "simulation logs are excluded by default"}
        return {"matches": [r.to_dict() for r in matches.values()]}
    return _guard(run)


# --- live parameters ------------------------------------------------------


@mcp.tool()
def list_parameters(name: str = "", vin: str = "") -> str:
    """Live parameters available in a FES session that logged them.

    Only a few sessions contain ``READING PARAMETERS:`` blocks. The parameter
    set grows during a session as the operator adds items to the watch list,
    so this returns the union across all samples.
    """
    def run():
        entry = catalog.resolve_or_latest(name, kind="fes", vin=vin)
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
    return _guard(run)


@mcp.tool()
def parameter_series(parameter: str, name: str = "", vin: str = "") -> str:
    """One live parameter as an ordered series, with statistics.

    ``static`` in the returned stats is the useful part: a value pinned across
    every sample is the signature of a substituted default rather than a live
    measurement, and that is difficult to spot by eye in a text log.

    Note there are no per-sample timestamps in the format -- ordering is file
    order and the sampling rate is unrecoverable.
    """
    def run():
        entry = catalog.resolve_or_latest(name, kind="fes", vin=vin)
        log = fes.load_fes(entry.path, timestamp=entry.timestamp)
        series = log.series(parameter)
        if not series.samples:
            return {"error": "parameter not found in this session",
                    "parameter": parameter, "file": entry.name,
                    "available": log.param_names()[:40]}
        out = series.stats()
        out["file"] = entry.name
        out["values"] = [s.display for s in series.samples]
        out["timing_note"] = ("MES records no per-sample timestamp; order is "
                              "file order and the sample rate is unknown")
        if out.get("static"):
            out["interpretation"] = (
                "This value never changed across the whole session. That is "
                "consistent with a substituted default or a modelled value "
                "rather than a live measurement - confirm before treating it "
                "as a reading."
            )
        return out
    return _guard(run)


# --- reference ------------------------------------------------------------


@mcp.tool()
def module_info(abbrev: str = "", domain: str = "") -> str:
    """Look up an ECU module by any name MES prints for it.

    Resolves alias sets ("TCM/NCA/NCR" -> TCM), Italian node names
    ("NBC" -> BCM, "NFR" -> ABS), and the CTM collision. With no arguments,
    returns the whole registry grouped by domain.
    """
    def run():
        if abbrev.strip():
            return modules.describe(abbrev)
        grouped = modules.by_domain()
        if domain.strip():
            key = domain.strip().lower()
            if key not in grouped:
                return {"error": "unknown domain", "domain": domain,
                        "available": sorted(grouped)}
            return {"domain": key,
                    "modules": [m.to_dict() for m in grouped[key]]}
        return {
            "stats": modules.registry_stats(),
            "by_domain": {d: [m.to_dict() for m in v]
                          for d, v in sorted(grouped.items())},
        }
    return _guard(run)


@mcp.tool()
def failure_type(byte: str) -> str:
    """Decode a DTC failure-type byte (the two hex digits after the dash).

    Meanings marked ``corpus`` were read directly off MES output on these
    vehicles' own ECUs. An unrecognised byte is reported as unknown rather
    than guessed at.
    """
    def run():
        ft = dtc_mod.failure_type(byte.strip())
        if ft is None:
            return {"error": "no failure type byte given"}
        return ft.to_dict()
    return _guard(run)


@mcp.tool()
def actuator_history(vin: str = "", operation: str = "") -> str:
    """Every actuator test and adjustment run across the corpus.

    Useful for two questions a log dump answers badly: what has already been
    tried on this car, and which tests the ECU refused and why.
    """
    def run():
        entries = catalog.CATALOG.select(kind="fes", vin=vin)
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
        failures = [r for r in runs if r["outcome"] == "FAILED TO EXECUTE"]
        return {
            "count": len(runs),
            "failed": len(failures),
            "runs": runs,
            "note": ("MES actuator tests on the IAW 10JA require key-on "
                     "engine-off; 'Engine running' is an interlock, not a "
                     "fault."),
        }
    return _guard(run)


@mcp.tool()
def vehicle_report(vin: str = "", vehicle: str = "") -> str:
    """A whole-vehicle picture: identity, odometer span, chronic faults.

    Chronic codes -- those recurring across sessions or across meaningful
    distance -- are surfaced separately from one-off faults, because the
    distinction usually decides the diagnosis.
    """
    return _guard(analysis.vehicle_summary, vin, vehicle)


@mcp.tool()
def workup(vin: str = "", vehicle: str = "", name: str = "", detail: bool = False) -> str:
    """The pre-work dossier: everything the logs know about one vehicle.

    One call answers "what am I looking at?" before the hood opens:
    identity and odometer span, the current DTC picture (including the
    newest session that actually held findings, not just a clean post-clear
    re-read), chronic vs returned vs seen-once classification, freeze
    frames, TSB cross-references with family findings (several EVAP codes =
    one fault; a U-code spread = one power/bus event), everything already
    attempted, and -- explicitly -- the blind spots the logs cannot answer
    and which live tool closes each one.

    Args:
        name: FESLog filename. Empty anchors the current picture on the
            newest session; naming one pins it there instead, which is how
            you ask "what did this car look like at that capture?" without
            a later log moving the answer.
        detail: False (default) returns a compact dossier: DTCs reduced to
            dtc/description/status, freeze frames trimmed to odometer/engine
            speed/vehicle speed/engine temperature/fuel level, each history
            class collapsed to one line per code (no per-occurrence lists),
            TSB matches reduced to bulletin + title, and already_attempted
            grouped by (kind, operation, outcome). True returns the complete,
            unreduced dossier.
    """
    def run():
        full = workup_mod.build(vin, vehicle, name)
        return full if detail else compact.compact_workup(full)
    return _guard(run, serialize=_json if detail else _json_compact)


@mcp.tool()
def fault_tree(codes: str = "", vin: str = "") -> str:
    """Fault-isolation sequence for a DTC or code family, cheapest-first.

    Every step names the exact action (MES screen, obd2 tool, or hand
    test), the expected result, what to conclude when it is abnormal, and
    the bulletin it was transcribed from. The parts cannon has no node.

    Args:
        codes: comma/space-separated DTCs ("P0455, P0440-00"). Empty lists
            the available trees.
        vin: when given, steps are annotated with this car's own log
            evidence -- e.g. a purge valve that already actuated COMPLETED
            while the code was stored is flagged so it is not re-tested.
    """
    def run():
        import re as _re
        toks = [t for t in _re.split(r"[,\s;]+", codes) if t.strip()]
        if not toks:
            return {"available": [
                {"tree": t.key, "title": t.title,
                 "applies_to": sorted(t.codes)}
                for t in faulttree.TREES]}
        return faulttree.evaluate(toks, vin=vin)
    return _guard(run)


@mcp.tool()
def diagnosis_verdict(vin: str, codes: str, component: str = "",
                      mechanism: str = "", measurements: str = "",
                      disconfirming_test: str = "") -> str:
    """The evidence gate: refuses "CONFIRMED" until the proof exists.

    Four criteria, checked against this car's corpus where possible:
    (1) the fault is demonstrated (chronic / returned / standing -- a code
    seen once then cleared is not), (2) a causal mechanism is stated,
    (3) at least one cited MEASUREMENT implicates the component (a DTC is
    not a measurement; actuator outcomes, freeze frames, parameters and
    recording events are verified in the logs; manual tests are recorded
    as attested), (4) a disconfirming test was run and described. Anything
    short returns NOT CONFIRMED with the specific missing test. The
    condemned component is also checked against the platform do-not list.

    Args:
        codes: the DTC(s) being diagnosed ("P0455, P0456").
        component: the part being condemned.
        mechanism: the causal chain in a sentence, not a part name.
        measurements: JSON array of cites, e.g.
            [{"type":"actuator","operation":"Evaporation control valve"},
             {"type":"freeze_frame","code":"P0456"},
             {"type":"parameter","name":"Canister fill","file":"FESLog_..."},
             {"type":"recording_event","file":"rec.csv","condition":"X > 5"},
             {"type":"manual","description":"smoke test: smoke at ESIM"}]
        disconfirming_test: the test that would have exonerated the part,
            and its result.
    """
    return _guard(verdict.assess, vin, codes, component, mechanism,
                  measurements, disconfirming_test)


@mcp.tool()
def record_dealer_result(vin: str, kind: str, data_json: str, note: str = "") -> str:
    """Record a wiTECH (dealer-tool) result as evidence. Append-only.

    wiTECH has no API -- a technician reads the result off the dealer's own
    screens and it gets typed in here. Once recorded, ``diagnosis_verdict``
    can cite a ``dealer`` measurement against it, and ``fault_tree``/``workup``
    annotate the relevant step automatically.

    Args:
        kind: one of flash_check | slvt | dtc_report | recall_status | routine.
        data_json: JSON object, shape depends on kind:
            flash_check: {"module":"ECM","current_part":"...","new_part":"...",
                          "flashed":false,"part_after":"..." (optional)}
            slvt: {"result":"pass|fail","detail":"..."}
            dtc_report: {"module":"ECM","codes":["P0456"],"note":"..."}
            recall_status: {"campaign":"25V586000","status":"open|completed|"
                            "not_applicable","date":"..."}
            routine: {"module":"BCM","name":"PROXI Alignment","result":"..."}
        note: free-text context.
    """
    def run():
        data = json.loads(data_json) if data_json.strip() else {}
        return dealer_mod.record(vin, kind, data, note=note)
    return _guard(run)


@mcp.tool()
def dealer_results(vin: str) -> str:
    """Every dealer (wiTECH) result recorded for this VIN, oldest first."""
    return _guard(lambda: {"vin": vin, "results": dealer_mod.load(vin)})


# --- technician notes -------------------------------------------------------


@mcp.tool()
def add_note(vin: str, text: str, target_kind: str = "vehicle", target_id: str = "",
            tags: str = "") -> str:
    """Add a technician note -- context Claude and the gate must see, that lives
    nowhere else: "purge valve replaced by me 2026-09-10", "this scan was
    taken right after a battery disconnect", "smoke test done at 0.5 psi, no
    leak". Append-only: use ``edit_note``/``hide_note`` to amend or retract,
    never re-add.

    Args:
        target_kind: one of vehicle | code | log | observation | dealer |
            tree_step | component.
        target_id: what the note is about, shaped by target_kind --
            a DTC (P0456 or P0456-00, matched on the base code), a MES log
            filename, an observation or dealer result's timestamp, a fault
            tree step (evap-leak:E7), or a free-text component name (ESIM).
            Empty for target_kind="vehicle".
        tags: comma-separated, optional.
    """
    def run():
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        return notes_mod.add(vin, text, target_kind, target_id=target_id, tags=tag_list)
    return _guard(run)


@mcp.tool()
def notes(vin: str, target_kind: str = "", target_id: str = "") -> str:
    """Technician notes for this VIN, oldest first. Empty target_kind/target_id
    returns every note for the vehicle; either filters."""
    return _guard(lambda: {"vin": vin,
                           "notes": notes_mod.load(vin, target_kind=target_kind or None,
                                                   target_id=target_id)})


@mcp.tool()
def edit_note(id: str, text: str) -> str:
    """Amend a note's text. Appends an amendment record -- never rewrites history."""
    return _guard(lambda: notes_mod.edit(id, text))


@mcp.tool()
def hide_note(id: str) -> str:
    """Hide a note (soft delete). Appends a hide record -- never rewrites history."""
    return _guard(lambda: notes_mod.hide(id))


# --- CSV recordings (graph subsystem export) ------------------------------


@mcp.tool()
def list_recordings() -> str:
    """CSV recordings exported by MES's graph subsystem, newest first.

    These are the only MES output with real per-sample timestamps. None has
    ever been recorded on this install: to produce one, open the Graph tab,
    add parameters, enable "Monitor DTCs" if DTC markers are wanted, and use
    CSV Start/Stop. The export lands in the Settings "Export Folder"
    (currently the install directory).
    """
    def run():
        recs = csvlog.list_recordings()
        out: dict[str, Any] = {"count": len(recs), "recordings": recs,
                               "roots": [str(r) for r in paths.csv_roots()]}
        if not recs:
            out["note"] = (
                "No CSV recordings found. In MES: Graph tab -> add up to 4 "
                "graphs x 10 parameters -> CSV Start / Stop. Set the export "
                "folder in Settings (needs the MES dialog; the registry key "
                "is not user-writable). Point MES_CSV_DIR here if it differs "
                "from the log folder.")
        return out
    return _guard(run)


@mcp.tool()
def read_recording(name: str, preview_rows: int = 10) -> str:
    """Parse one CSV recording: columns, measured timing, tag/DTC events.

    Reports the measured sample rate and any dropouts (gaps over 3x the
    median interval -- an adapter or ECU-link stall), which the .txt session
    log structurally cannot show.
    """
    return _guard(lambda: csvlog.load_named(name).to_dict(
        preview_rows=preview_rows))


@mcp.tool()
def recording_series(name: str, parameter: str) -> str:
    """One recorded parameter as a timed series with statistics.

    Unlike ``parameter_series`` over a .txt session, samples here carry real
    timestamps, so the stats are physically meaningful rates and durations.

    Args:
        parameter: column name (exact or unique substring) or column index.
    """
    def run():
        rec = csvlog.load_named(name)
        series = rec.series(parameter)
        out = series.stats()
        out["file"] = rec.name
        out["values"] = [
            {"t": stamp, "value": s.display}
            for stamp, s in zip(series.stamps, series.samples)
        ]
        if out.get("static"):
            out["interpretation"] = (
                "This value never changed across the recording - consistent "
                "with a substituted default or modelled value rather than a "
                "live measurement.")
        return out
    return _guard(run)


@mcp.tool()
def recording_events(name: str, condition: str = "") -> str:
    """Post-hoc trigger analysis over a CSV recording.

    With no condition, returns the recording's TAG events (operator markers
    and, with "Monitor DTCs" enabled, DTCs) plus timing dropouts. With a
    condition like "Engine speed > 3000" or "Fuel pressure < 250", returns
    the intervals where it held: enter/exit time, duration and the extreme
    value -- one event per excursion, not one per sample.
    """
    def run():
        rec = csvlog.load_named(name)
        out: dict[str, Any] = {
            "file": rec.name,
            "timing": rec.timing(),
            "tag_events": [t.to_dict() for t in rec.tags],
            "dtcs_in_tags": sorted({d for t in rec.tags for d in t.dtcs}),
        }
        if condition.strip():
            out["threshold"] = rec.crossings(condition)
        return out
    return _guard(run)


@mcp.tool()
def recording_snapshot(name: str, at_seconds: float) -> str:
    """Every recorded value at the sample nearest a given time.

    The post-hoc freeze frame: after ``recording_events`` finds when a DTC
    tag fired or a threshold tripped, this shows what everything else read
    at that moment.
    """
    return _guard(lambda: {
        "file": name,
        **csvlog.load_named(name).snapshot(at_seconds),
    })


@mcp.tool()
def log_dir() -> str:
    """The MES log directories being watched, and whether they exist."""
    def run():
        return {
            "configured": [str(r) for r in paths.configured_roots()],
            "existing": [str(r) for r in paths.existing_roots()],
            "env_overrides": ["MES_LOG_DIRS (os.pathsep separated)",
                              "MES_LOG_DIR"],
        }
    return _guard(run)


# --- resources -------------------------------------------------------------


@mcp.resource("vehicle://index")
def vehicle_index() -> str:
    """Every distinct vehicle in the corpus, keyed by VIN where recoverable.

    The resource form of the ``vehicles`` tool, for a client that wants the
    fleet list without an explicit tool call.
    """
    return _guard(lambda: {"vehicles": catalog.CATALOG.vehicles()})


@mcp.resource("vehicle://{vin}/dossier")
def vehicle_dossier(vin: str) -> str:
    """The compact pre-work dossier for one vehicle, by VIN.

    Same content as ``workup(vin=...)`` with ``detail=False`` -- everything
    the logs know about the car, reduced to what fits a context window.
    """
    return _guard(lambda: compact.compact_workup(workup_mod.build(vin, "", "")),
                 serialize=_json_compact)


if __name__ == "__main__":
    mcp.run()
