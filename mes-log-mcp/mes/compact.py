"""Compact ("summary") views over the two largest MES tool outputs.

``analyze_scan`` and ``workup`` are useful precisely because they assemble
everything the corpus knows about a scan or a vehicle in one call -- which is
also why they are enormous: a whole-vehicle workup on a car with real history
ran 52 KB, and a SCAN log's module list is printed three times over
(``modules``, ``post_clear_modules``, ``modules_by_priority``) for no reason
an LLM caller needs. None of that detail is wrong, it just should not be the
default.

Everything here is a pure function over the plain dict a tool already built
(:func:`mes.scan.ScanLog.to_dict` / :func:`mes.workup.build`'s return value),
so it can be unit tested without touching a log file, and detail=True keeps
working by simply skipping this module entirely -- the full dict is never
mutated, only read.
"""

from __future__ import annotations

from typing import Any

#: The freeze-frame parameters worth carrying in the compact view. A FES
#: freeze frame holds ~25 labelled parameters; only these five are what a
#: first pass at "what was the car doing" actually needs, and they are the
#: ones :mod:`mes.fes` and the platform docs already treat as load-bearing
#: (odometer for chronic/distance reasoning, the rest for a cold-start vs.
#: highway read). Matched case-sensitively against the name MES itself
#: printed, which is stable across this corpus (see mes.params).
FREEZE_FRAME_KEYS: tuple[str, ...] = (
    "Odometer", "Engine speed", "Vehicle speed", "Engine temperature",
    "Fuel level",
)

_SCAN_HEADER_KEYS = (
    "file", "timestamp", "vin", "module_count", "fault_module_count",
    "dtc_count", "provenance", "aborted", "connection_failures",
)


def _compact_dtc(d: dict[str, Any]) -> dict[str, Any]:
    return {"dtc": d.get("dtc"), "description": d.get("description"),
            "status": d.get("status")}


# --- analyze_scan -----------------------------------------------------------


def compact_scan(full: dict[str, Any]) -> dict[str, Any]:
    """The compact view of an ``analyze_scan`` result.

    Keeps the header fields, lists only modules that actually hold a code
    (plus the clean ones by name only), reduces ``post_clear_modules`` to
    what changed since the scan phase, summarises each clear result to its
    pass/fail outcome, and reduces ``modules_by_priority`` to an ordered name
    list -- the per-DTC detail in that block duplicates ``modules`` byte for
    byte otherwise.
    """
    if "error" in full:
        return dict(full)

    out: dict[str, Any] = {k: full[k] for k in _SCAN_HEADER_KEYS if k in full}

    modules_full = full.get("modules") or []
    with_codes: list[dict[str, Any]] = []
    clean: list[str] = []
    scan_codes_by_module: dict[str, list[str]] = {}
    for m in modules_full:
        name = m.get("module")
        dtcs = m.get("dtcs") or []
        codes = sorted(d.get("dtc") for d in dtcs)
        scan_codes_by_module[name] = codes
        if dtcs:
            with_codes.append({"module": name, "ecu": m.get("ecu"),
                               "dtcs": [_compact_dtc(d) for d in dtcs]})
        else:
            clean.append(name)
    out["modules"] = with_codes
    out["clean_modules"] = clean

    post_clear_full = full.get("post_clear_modules") or []
    if post_clear_full:
        diff: dict[str, list[str]] = {}
        for m in post_clear_full:
            name = m.get("module")
            codes = sorted(d.get("dtc") for d in (m.get("dtcs") or []))
            if codes != scan_codes_by_module.get(name, []):
                diff[name] = codes
        if diff:
            out["post_clear"] = diff

    clear_results_full = full.get("clear_results") or []
    if clear_results_full:
        out["clear_results"] = {cr.get("module"): cr.get("result")
                                for cr in clear_results_full}

    priority_full = full.get("modules_by_priority") or []
    if priority_full:
        out["priority"] = [p.get("module") for p in priority_full]

    for passthrough in ("network_event", "note", "vin_conflicts"):
        if passthrough in full:
            out[passthrough] = full[passthrough]

    return out


# --- workup -------------------------------------------------------------


def _compact_freeze_frames(frames: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for dtc, params in frames.items():
        short = {k: params[k] for k in FREEZE_FRAME_KEYS if k in params}
        if short:
            out[dtc] = short
    return out


def _compact_session(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry)
    if "dtcs" in out:
        out["dtcs"] = [_compact_dtc(d) for d in out["dtcs"]]
    return out


def _compact_current_picture(cp: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("latest_session", "last_session_with_findings"):
        if key in cp:
            out[key] = _compact_session(cp[key])
    if "clear_assessment" in cp:
        # The verdict and next step carry the meaning; the code lists are
        # already in the findings session above.
        out["clear_assessment"] = {k: v for k, v in cp["clear_assessment"].items()
                                   if k in ("verdict", "next_step", "source", "cleared_at",
                                            "re_read_after_clear", "modules_refused",
                                            "codes_returned_in_session")}
    if "freeze_frames" in cp:
        ff = _compact_freeze_frames(cp["freeze_frames"])
        if ff:
            out["freeze_frames"] = ff
    if "latest_scan" in cp:
        out["latest_scan"] = cp["latest_scan"]
    if "network_event" in cp:
        out["network_event"] = cp["network_event"]
    return out


def _compact_history_record(r: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"dtc": r.get("dtc")}
    descriptions = r.get("descriptions") or []
    if descriptions:
        out["description"] = descriptions[0]
    out["sessions"] = r.get("sessions")
    out["first_seen"] = r.get("first_seen")
    out["last_seen"] = r.get("last_seen")
    if "distance_span_km" in r:
        out["distance_span_km"] = r["distance_span_km"]
    if "assessment" in r:
        out["assessment"] = r["assessment"]
    return out


def _group_attempted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse every actuator/adjustment run into one line per (kind,
    operation, outcome) triple -- the workup's own history classification
    already established chronic-vs-once; the same rollup is worth applying
    to "what has already been tried", which otherwise lists every run of a
    routine actuator test as its own entry.
    """
    groups: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for r in rows:
        key = (r.get("kind"), r.get("operation"), r.get("outcome"))
        g = groups.setdefault(key, {"kind": key[0], "operation": key[1],
                                    "outcome": key[2], "count": 0,
                                    "first": None, "last": None})
        g["count"] += 1
        ts = r.get("timestamp") or ""
        if ts and (g["first"] is None or ts < g["first"]):
            g["first"] = ts
        if ts and (g["last"] is None or ts > g["last"]):
            g["last"] = ts
    return sorted(groups.values(), key=lambda g: g["last"] or "", reverse=True)


def compact_workup(full: dict[str, Any]) -> dict[str, Any]:
    """The compact view of a ``workup`` result.

    Keeps identity, blind spots and the provenance note verbatim; trims the
    current-picture DTC lists and freeze frames to their essentials;
    collapses each history class to one line per code instead of a full
    occurrence list; reduces TSB matches to bulletin + title; and groups
    ``already_attempted`` by (kind, operation, outcome) instead of one row
    per run.
    """
    if "error" in full:
        return dict(full)

    out: dict[str, Any] = {"identity": full.get("identity", {})}
    out["current_picture"] = _compact_current_picture(full.get("current_picture") or {})

    history = full.get("history") or {}
    out["history"] = {cls: [_compact_history_record(r) for r in recs]
                      for cls, recs in history.items()}

    tsb = full.get("tsb_matches") or {}
    per_code = tsb.get("per_code") or {}
    compact_tsb: dict[str, Any] = {
        "per_code": {code: [{"bulletin": b.get("bulletin"), "title": b.get("title")}
                            for b in bulletins]
                    for code, bulletins in per_code.items()},
        "family_findings": tsb.get("family_findings", []),
    }
    if "bulletins_considered" in tsb:
        compact_tsb["bulletins_considered"] = tsb["bulletins_considered"]
    out["tsb_matches"] = compact_tsb

    out["already_attempted"] = _group_attempted(full.get("already_attempted") or [])
    # Question and remedy only; the "why_unknown" explanation stays in detail=True.
    out["blind_spots"] = [{k: b[k] for k in ("question", "closes_it") if k in b}
                          for b in full.get("blind_spots", [])]
    out["provenance_note"] = full.get("provenance_note", "")
    return out


__all__ = ["FREEZE_FRAME_KEYS", "compact_scan", "compact_workup"]
