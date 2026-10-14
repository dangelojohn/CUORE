"""The one-command pre-work dossier: everything the logs know, assembled.

The aviation analogue is the squawk-plus-history review a mechanic does
before touching anything. Without this, answering "what am I looking at?"
takes five tool calls and the cross-checks between them -- chronic vs fresh,
cleared vs returned, TSB applicability -- are exactly the judgments that get
skipped under time pressure.

The dossier is honest about its blind spots. A log corpus cannot say whether
the EVAP monitor has run since the last clear, whether a permanent DTC is
standing, or what the ECM's measured leak value is -- those need the car live
(the ``obd2`` server, and Mode $06 once built). The ``blind_spots`` section
names each one and the tool that closes it, so "the file says no faults"
never gets mistaken for "there are no faults".
"""

from __future__ import annotations

from typing import Any

from . import analysis, fes as fes_mod, knowledge, notes as notes_mod, scan as scan_mod
from .catalog import CATALOG


def _scan_clear_between(entries: list[Any], informative: Any,
                        latest_fes: Any) -> dict[str, Any] | None:
    """A clear done in an all-systems SCAN between the findings and the clean read.

    ``post_clear_assessment`` only sees clears inside one FES session. On
    2026-09-25 the codes were read in a FES session at 20:02, erased by a SCAN
    at 20:27, and re-read clean in a FES session at 20:28: without this, the
    dossier showed that clean read with no warning at all.
    """
    lo = getattr(informative, "timestamp", None) or ""
    hi = getattr(latest_fes, "timestamp", None) or ""
    best = None
    for e in entries:
        if e.kind != "scan" or e.parse_error or not e.timestamp:
            continue
        ts = str(e.timestamp)
        if not (str(lo) <= ts <= str(hi)):
            continue
        try:
            slog = scan_mod.load_scan(e.path, timestamp=e.timestamp)
        except Exception:
            continue
        if slog.clear_results and (best is None or ts > best[0]):
            best = (ts, e.name, slog)
    if best is None:
        return None
    ts, name, slog = best
    ok = [m.name for m in slog.clear_results if (m.clear_result or "").upper() == "SUCCESS"]
    refused = {m.name: [x.full for x in m.dtcs] for m in slog.clear_results
               if (m.clear_result or "").upper() != "SUCCESS"}
    return {
        "source": name,
        "cleared_at": ts,
        "modules_cleared": ok,
        "modules_refused": refused,
        "codes_cleared": [d.full for d in informative.dtcs],
        "re_read_after_clear": True,
        "verdict": (f"Codes were erased by the all-systems scan {name} at {ts}. The clean "
                    f"read in {getattr(latest_fes, 'name', 'the latest session')} came "
                    f"after that clear, before any monitor could re-run: it is NOT proof "
                    f"of repair and carries no information about whether the fault is "
                    f"still there."),
        "next_step": ("Drive until the monitors re-run (EVAP: fuel 15-85 %, cold starts, "
                      "several drives), then read the status bytes (verify_repair) or "
                      "re-scan. A returning code is the answer; silence right after a "
                      "clear is not."),
    }


def _latest(entries, kind):
    for e in entries:
        if e.kind == kind and not e.parse_error:
            return e
    return None


def _newest_global_clear(entries: list[Any]) -> tuple[str, Any, Any] | None:
    """(timestamp, entry, loaded log) of the single most recent clear event
    anywhere in the corpus, FES or SCAN alike.

    The per-session detection above is anchored to the latest FES session
    (and, within it, to a SCAN found strictly *between* that session and an
    older informative one). A SCAN-only clear with no FES session after it
    at all falls entirely outside that window: on 2026-10-08 the owner
    cleared 4 DTCs with MES (SCAN_2610080920.txt, confirmed clean by
    SCAN_2610080926.txt six minutes later) while the newest FES engineering
    session on file stayed dated 2026-10-04 -- older than the clear itself.
    The anchored logic above never looks that far forward, so this scans
    every entry directly instead of trusting any one session as the anchor.
    """
    best: tuple[str, Any, Any] | None = None
    for e in entries:
        if e.parse_error or not e.timestamp:
            continue
        if e.kind == "scan":
            try:
                log = scan_mod.load_scan(e.path, timestamp=e.timestamp)
            except Exception:
                continue
            if not log.clear_results:
                continue
        elif e.kind == "fes":
            try:
                log = fes_mod.load_fes(e.path, timestamp=e.timestamp)
            except Exception:
                continue
            if not log.clear_events:
                continue
        else:
            continue
        ts = str(e.timestamp)
        if best is None or ts > best[0]:
            best = (ts, e, log)
    return best


def _nearest_entry_after(entries: list[Any], ts: str, exclude_name: str) -> Any | None:
    """The chronologically-nearest log entry strictly after ``ts``, if any."""
    best = None
    for e in entries:
        if e.parse_error or not e.timestamp or e.name == exclude_name:
            continue
        et = str(e.timestamp)
        if et <= ts:
            continue
        if best is None or et < str(best.timestamp):
            best = e
    return best


def _clear_dict_from_global(entries: list[Any], entry: Any, log: Any,
                            ts: str) -> dict[str, Any]:
    """Build the ``clear_assessment`` dict for a clear found by
    :func:`_newest_global_clear`, in the same shape ``_scan_clear_between``
    and :class:`analysis.ClearAssessment` already produce, so every reader
    of ``current_picture.clear_assessment`` keeps working unchanged.
    """
    if entry.kind == "fes":
        ca = analysis.post_clear_assessment(log)
        if ca:
            return ca.to_dict()
        return {
            "source": entry.name, "cleared_at": ts, "codes_cleared": [],
            "verdict": f"Codes were cleared in {entry.name} at {ts}.",
            "next_step": "Drive until the monitors re-run, then re-check.",
        }

    # SCAN: a module's clear can be reported more than once in one file when
    # an earlier clear attempt is incomplete (announced but cut short by a
    # rescan) before a second attempt actually completes -- as on
    # 2026-10-08, where the Engine/ECM block appears once with no result at
    # all and again later. The last reported result per module is the one
    # that actually happened.
    last_by_key: dict[str, Any] = {}
    for m in log.clear_results:
        last_by_key[m.key] = m
    pre_by_key = {m.key: m for m in log.modules}
    codes_cleared = sorted({d.full for d in log.all_dtcs})

    nxt = _nearest_entry_after(entries, ts, entry.name)
    re_read_after_clear = False
    tail_note = ""
    still_present: set[str] = set()
    if nxt is not None:
        try:
            if nxt.kind == "scan":
                nlog = scan_mod.load_scan(nxt.path, timestamp=nxt.timestamp)
                still_present = {d.full for d in nlog.all_dtcs} & set(codes_cleared)
            else:
                nlog = fes_mod.load_fes(nxt.path, timestamp=nxt.timestamp)
                still_present = {d.full for d in nlog.dtcs} & set(codes_cleared)
            re_read_after_clear = True
            if still_present:
                tail_note = (f" {nxt.name} at {nxt.timestamp} still shows "
                             f"{', '.join(sorted(still_present))} -- not cleared.")
            else:
                tail_note = (f" {nxt.name} at {nxt.timestamp} read clean. This is NOT "
                             f"proof of repair: after a clear the ECU reports nothing "
                             f"until the monitor that governs the code actually re-runs.")
        except Exception:
            pass

    # A result of "SUCCESS"/"FAILED" is taken at face value. A blank result
    # -- the transcript's own SUCCESS/FAILED line sits one line further
    # down than the parser's per-module read stops, past an extra blank
    # line, as happens on the Engine/ECM block above -- is resolved from
    # evidence instead of guessed: cleared if this module's own pre-clear
    # codes are confirmed gone on the next read, refused if any persist.
    ok: list[str] = []
    refused: dict[str, list[str]] = {}
    for m in last_by_key.values():
        result = (m.clear_result or "").upper()
        if result == "FAILED":
            refused[m.name] = [x.full for x in m.dtcs]
        elif result == "SUCCESS":
            ok.append(m.name)
        elif nxt is not None:
            pre = pre_by_key.get(m.key)
            pre_codes = {d.full for d in pre.dtcs} if pre else set()
            persisted = sorted(pre_codes & still_present)
            if persisted:
                refused[m.name] = persisted
            else:
                ok.append(m.name)
        else:
            # No later read to confirm against -- can't be called cleared.
            pre = pre_by_key.get(m.key)
            refused[m.name] = [d.full for d in pre.dtcs] if pre else []

    return {
        "source": entry.name,
        "cleared_at": ts,
        "modules_cleared": ok,
        "modules_refused": refused,
        "codes_cleared": codes_cleared,
        "re_read_after_clear": re_read_after_clear,
        "verdict": (f"Codes were cleared by the all-systems scan {entry.name} at {ts} "
                    f"({', '.join(codes_cleared) if codes_cleared else 'no codes listed'})."
                    + tail_note),
        "next_step": ("Drive until the monitors re-run (EVAP: fuel 15-85 %, cold starts, "
                      "several drives), then read the status bytes (verify_repair) or "
                      "re-scan. A returning code is the answer; silence right after a "
                      "clear is not."),
    }


def build(vin: str = "", vehicle: str = "",
          name: str = "") -> dict[str, Any]:
    """Assemble the full workup for one vehicle.

    ``name`` pins the current picture to one named FES session instead of
    whichever happens to be newest, which is what makes the post-clear
    look-behind addressable: point it at an empty re-read and the dossier
    must still surface the session behind it. History, TSB matching and
    attempted work continue to span the whole corpus.
    """
    anchor = None
    if name.strip():
        anchor = CATALOG.by_name(name.strip())
        if anchor.kind != "fes":
            return {"error": "not a FES engineering session",
                    "name": anchor.name, "kind": anchor.kind}
        if anchor.parse_error:
            return {"error": anchor.parse_error, "name": anchor.name}
        # Without this the dossier behind a named log would merge every
        # vehicle in the corpus into one history.
        if not vin and not vehicle:
            vin = anchor.vin or ""
            if not vin:
                vehicle = anchor.vehicle or ""

    entries = CATALOG.select(vin=vin, vehicle=vehicle)
    if not entries:
        return {"error": "no logs match", "vin": vin, "vehicle": vehicle}

    summary = analysis.vehicle_summary(vin=vin, vehicle=vehicle)
    history = analysis.dtc_history(entries)

    # --- current picture: the anchored session (newest unless a name was
    #     given) and the newest scan --------------------------------------
    current: dict[str, Any] = {}
    open_codes: list[str] = []
    latest_fes = anchor or _latest(entries, "fes")
    if latest_fes:
        log = fes_mod.load_fes(latest_fes.path, timestamp=latest_fes.timestamp)
        current["latest_session"] = {
            "file": latest_fes.name,
            "timestamp": latest_fes.timestamp,
            "ecu": log.ecu_description,
            "odometer_km": log.odometer_km,
            "dtcs": [d.to_dict() for d in log.dtcs],
        }
        open_codes = [d.full for d in log.dtcs]

        # The newest session is often the empty post-clear re-read; on its
        # own it looks like a healthy car. Surface the newest session that
        # actually held findings alongside it, so the workup shows what was
        # cleared, not just the silence after.
        informative = log
        if not log.dtcs:
            for e in entries:
                # Compared by name, not identity: a session reached through
                # ``name`` is a different LogEntry object than the indexed
                # one. Only sessions BEHIND the anchor count as "behind it".
                if (e.kind != "fes" or e.parse_error
                        or e.name == latest_fes.name
                        or (e.stamp and latest_fes.stamp
                            and e.stamp > latest_fes.stamp)):
                    continue
                cand = fes_mod.load_fes(e.path, timestamp=e.timestamp)
                if cand.dtcs:
                    informative = cand
                    current["last_session_with_findings"] = {
                        "file": e.name,
                        "timestamp": e.timestamp,
                        "odometer_km": cand.odometer_km,
                        "dtcs": [d.to_dict() for d in cand.dtcs],
                        "note": ("newest session that held DTCs; the latest "
                                 "session above read clean AFTER these were "
                                 "handled"),
                    }
                    open_codes = [d.full for d in cand.dtcs]
                    break
        cleared = analysis.post_clear_assessment(informative)
        if cleared:
            current["clear_assessment"] = cleared.to_dict()
        elif not log.dtcs and informative is not log:
            scan_clear = _scan_clear_between(entries, informative, latest_fes)
            if scan_clear:
                current["clear_assessment"] = scan_clear
        frames = {d.full: {k: v.display for k, v in d.freeze_frame.items()}
                  for d in informative.dtcs if d.freeze_frame}
        if frames:
            current["freeze_frames"] = frames

    # The FES-anchored detection above can miss a newer, SCAN-only clear
    # entirely (see _newest_global_clear). Let the newest clear found
    # anywhere in the corpus supersede a stale one.
    newest_clear = _newest_global_clear(entries)
    if newest_clear is not None:
        newest_ts, newest_entry, newest_log = newest_clear
        existing_ts = (current.get("clear_assessment") or {}).get("cleared_at") or ""
        if newest_ts > existing_ts:
            current["clear_assessment"] = _clear_dict_from_global(
                entries, newest_entry, newest_log, newest_ts)

    latest_scan = _latest(entries, "scan")
    if latest_scan:
        slog = scan_mod.load_scan(latest_scan.path,
                                  timestamp=latest_scan.timestamp)
        current["latest_scan"] = {
            "file": latest_scan.name,
            "timestamp": latest_scan.timestamp,
            "modules_with_faults": [
                {"module": m.name, "dtcs": [d.full for d in m.dtcs]}
                for m in slog.modules if m.dtcs],
            "provenance": "unverifiable (SCAN logs carry no simulation marker)",
        }
        by_module = {m.name: m.dtcs for m in slog.modules if m.dtcs}
        event = analysis.detect_network_event(by_module)
        if event:
            current["network_event"] = event.to_dict()

    # --- history classification -------------------------------------------
    chronic = [r for r in history.values() if r.chronic]
    returned = [r for r in history.values() if r.returned_after_clear]
    single = [r for r in history.values()
              if not r.chronic and not r.returned_after_clear
              and r.session_count == 1]
    classified = {
        "chronic": [r.to_dict() for r in
                    sorted(chronic, key=lambda r: r.first_seen)],
        "returned_after_clear": [r.to_dict() for r in returned],
        "seen_once": [r.to_dict() for r in
                      sorted(single, key=lambda r: r.first_seen)],
    }

    # --- TSB cross-reference over every code ever seen on this car ---------
    all_codes = set(history.keys()) | set(open_codes)
    tsb = knowledge.match_codes(all_codes)

    # --- what has already been tried ---------------------------------------
    attempted: list[dict[str, Any]] = []
    for entry in entries:
        if entry.kind != "fes" or entry.parse_error:
            continue
        try:
            log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
        except Exception:
            continue
        for a in log.actuators:
            row = a.to_dict()
            row["timestamp"] = entry.timestamp
            attempted.append(row)

    if vin.strip():
        from . import dealer as dealer_mod
        for rec in dealer_mod.load(vin):
            d = rec.get("data") or {}
            dkind = rec.get("kind", "")
            if dkind == "flash_check":
                operation = f"dealer flash_check ({d.get('module', '?')})"
                outcome = ("current" if d.get("current") else
                          "flashed" if d.get("flashed") else
                          "newer calibration available")
            elif dkind == "slvt":
                operation = "dealer SLVT (TSB 18-048-23)"
                outcome = d.get("result", "")
            elif dkind == "dtc_report":
                operation = f"dealer dtc_report ({d.get('module', '?')})"
                outcome = ", ".join(d.get("codes") or []) or "no codes reported"
            elif dkind == "recall_status":
                operation = f"dealer recall_status ({d.get('campaign', '?')})"
                outcome = d.get("status", "")
            elif dkind == "routine":
                operation = f"dealer routine ({d.get('module', '?')}: {d.get('name', '?')})"
                outcome = d.get("result", "")
            else:
                operation = f"dealer {dkind}"
                outcome = ""
            attempted.append({
                "kind": "dealer",
                "operation": operation,
                "outcome": outcome,
                "note": rec.get("note", ""),
                "timestamp": rec.get("at"),
            })
    attempted.sort(key=lambda r: r.get("timestamp") or "", reverse=True)

    # --- blind spots: what the logs structurally cannot answer -------------
    blind_spots = [
        {"question": "Has each emissions monitor RUN since the last clear?",
         "why_unknown": "MES has no OBD-II mode; a clean re-scan minutes "
                        "after a clear proves nothing",
         "closes_it": "obd2.read_readiness (car connected, ELM327 on COM3)"},
        {"question": "Is a permanent (Mode $0A) DTC standing?",
         "why_unknown": "invisible to MES entirely",
         "closes_it": "obd2.read_permanent_dtcs (car connected)"},
        {"question": "What did the on-board leak test actually MEASURE?",
         "why_unknown": "Mode $06 tool not yet built",
         "closes_it": "pending build; reachable today via obd2.send_raw"},
    ]
    if any(knowledge.base_code(c) in knowledge.EVAP_FAMILY
           for c in all_codes):
        from . import ecm
        ident = ecm.installed(vin) if vin else None
        from . import dealer as dealer_mod
        flash = dealer_mod.latest(vin, "flash_check", module="ECM") if vin else None
        if flash:
            fd = flash.get("data") or {}
            if fd.get("current"):
                answer = (f"Answered by dealer flash check {flash.get('at')}: current "
                          f"{fd.get('current_part')}, new {fd.get('new_part')} -- the ECM "
                          f"is on the latest calibration (software lead closed).")
            elif fd.get("flashed"):
                answer = (f"Answered by dealer flash check {flash.get('at')}: current "
                          f"{fd.get('current_part')}, new {fd.get('new_part')} -- flashed "
                          f"to {fd.get('part_after') or fd.get('new_part')}.")
            else:
                answer = (f"Answered by dealer flash check {flash.get('at')}: current "
                          f"{fd.get('current_part')}, newer calibration "
                          f"{fd.get('new_part')} is available -- not yet flashed.")
            blind_spots.append(
                {"question": "Is the ECM on the latest calibration?",
                 "why_unknown": answer,
                 "closes_it": "already closed (technician-entered from wiTECH)"})
        else:
            blind_spots.append(
                {"question": "Is the ECM on the latest calibration?",
                 "why_unknown": ("FCA publishes no calibration numbers; the logs show "
                                 "what is installed (" + ecm.summary_line(ident) + "), "
                                 "not what is available"),
                 "closes_it": ("dealer wiTECH ECU flash check on the VIN; the exact "
                               "request is in EVAP fault tree step E8")})
        blind_spots.append(
            {"question": "Will the EVAP monitor run on the next drive?",
             "why_unknown": "monitor needs fuel level roughly 15-85% and a "
                            "cold-start natural-vacuum window",
             "closes_it": "check fuel level before the verification drive"})

    # --- technician notes ---------------------------------------------------
    # Attached rather than merged: a note is context on a finding, not the
    # finding itself, so it rides alongside current_picture/history entries as
    # a "notes" list that only appears where a note actually exists.
    notes_out: dict[str, Any] = {"vehicle": []}
    if vin.strip():
        notes_out["vehicle"] = notes_mod.load(vin, target_kind="vehicle")
        code_notes = notes_mod.load(vin, target_kind="code")
        if code_notes:
            by_code: dict[str, list[dict[str, Any]]] = {}
            for n in code_notes:
                by_code.setdefault(knowledge.base_code(n.get("target_id", "")), []).append(n)
            for key in ("latest_session", "last_session_with_findings"):
                session = current.get(key)
                if not session:
                    continue
                for d in session.get("dtcs", []):
                    hits = by_code.get(knowledge.base_code(d.get("code") or d.get("dtc") or ""))
                    if hits:
                        d["notes"] = hits
            for bucket in classified.values():
                for r in bucket:
                    hits = by_code.get(knowledge.base_code(r.get("dtc", "")))
                    if hits:
                        r["notes"] = hits

    return {
        "identity": {k: summary.get(k) for k in
                     ("vin", "vehicle", "ecu_seen", "log_count", "first_log",
                      "last_log", "odometer_first_km", "odometer_last_km")},
        "current_picture": current,
        "history": classified,
        "tsb_matches": tsb,
        "already_attempted": attempted,
        "blind_spots": blind_spots,
        "notes": notes_out,
        "provenance_note": (
            "Simulation logs excluded. SCAN provenance is unverifiable "
            "(no simulation marker exists in that format)."),
    }
