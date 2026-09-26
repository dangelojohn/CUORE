"""Per-vehicle dashboard: the whole car on one screen.

``workup.build`` already assembles the pre-work dossier; this module reshapes
that same evidence -- plus a chronological merge of everything ever done to
the car -- into the handful of flat, chart-ready structures a dashboard page
needs. Nothing here re-derives a judgement ``workup`` or ``analysis`` already
make (chronic, returned, TSB matches); it only regroups their output by code,
by module and by time.

Pure stdlib, no ``cuore`` import -- same rule as every other module in this
package. Live data comes in through :mod:`mes.live_obs`, which already knows
how to find cuore's observation store without importing cuore itself.

Sections returned by :func:`build`:

* ``summary`` -- the handful of numbers a verdict-first header needs.
* ``code_timeline`` -- one row per code ever seen, every occurrence dated and
  odometer-tagged, for the timeline chart and the codes table.
* ``repairs_and_tests`` -- actuators, dealer results, clears (from the logs
  and from the live link) and notes (if that module exists yet), merged into
  one chronological ledger.
* ``live_status`` -- the newest real live read per module, plus the newest
  Mode $06 EVAP result if the car has ever been asked for one.
* ``modules`` -- per-module DTC counts and last-read provenance (log vs live).
* ``odometer_series`` -- (date, km) pairs for the mileage chart.
"""

from __future__ import annotations

from typing import Any

from . import analysis, dtc_text, live_obs, workup as workup_mod
from . import fes as fes_mod
from .catalog import CATALOG

#: Same four-way collapse ``cuore.services.mes_bridge._classified`` uses for
#: the codes table, reproduced here rather than imported -- this package
#: never imports ``cuore``, and it is three lines of pure boolean logic over
#: properties :mod:`mes.analysis` already publishes.
_SEV_RANK = {"returned": 0, "chronic": 1, "recurring": 2, "cleared": 3, "seen-once": 4}


def _severity(rec: Any) -> str:
    if rec.returned_after_clear:
        return "returned"
    if rec.chronic:
        return "chronic"
    if "cleared" in rec.statuses and rec.session_count <= 1:
        return "cleared"
    if rec.session_count <= 1:
        return "seen-once"
    return "recurring"


def _ts_key(ts: Any) -> str:
    """Sortable key for a timestamp string regardless of ``T``-or-space sep.

    Log timestamps read ``2026-09-25 20:02:00``; dealer/live timestamps come
    from ``datetime.isoformat()`` and read ``2026-09-25T20:02:00``. Comparing
    the raw strings puts every space-separated stamp before every ``T``-
    separated one on the same day (``' ' < 'T'`` in ASCII), which is wrong.
    Normalising the separator is enough -- no format here needs microseconds.
    """
    return str(ts or "").replace(" ", "T")


def _build_summary(vin: str, w: dict[str, Any]) -> dict[str, Any]:
    ident = w.get("identity", {})
    cp = w.get("current_picture", {})
    open_dtcs = (cp.get("latest_session") or {}).get("dtcs") or []
    ca = cp.get("clear_assessment") or {}
    # A clean newest session straight after a clear is silence, not health:
    # say so, or the tile reads "0 standing codes" as a clean bill.
    after_clear = None
    if not open_dtcs and ca:
        after_clear = {"cleared_at": ca.get("cleared_at"), "source": ca.get("source"),
                       "session": (cp.get("latest_session") or {}).get("timestamp"),
                       "findings_before": [d.get("dtc") for d in
                                           ((cp.get("last_session_with_findings") or {})
                                            .get("dtcs") or [])]}
    last_scan_date = (
        (cp.get("latest_scan") or {}).get("timestamp")
        or (cp.get("latest_session") or {}).get("timestamp")
        or ident.get("last_log")
    )
    return {
        "vin": vin,
        "vehicle": ident.get("vehicle"),
        "odometer_first_km": ident.get("odometer_first_km"),
        "odometer_last_km": ident.get("odometer_last_km"),
        "log_count": ident.get("log_count"),
        "open_codes_count": len(open_dtcs),
        "newest_session_after_clear": after_clear,
        "chronic_count": len(w.get("history", {}).get("chronic") or []),
        "last_scan_date": last_scan_date,
        "ecu_seen": ident.get("ecu_seen") or [],
    }


def _build_code_timeline(history: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for rec in history.values():
        lo, hi = rec.odometer_span
        span = round(hi - lo, 1) if lo is not None and hi is not None and hi > lo else None
        description = ", ".join(rec.descriptions)
        if not description:
            fallback = dtc_text.describe(rec.dtc, rec.modules[0] if rec.modules else None)
            if fallback:
                description = fallback["text"]
        rows.append({
            "code": rec.dtc,
            "description": description,
            "module": ", ".join(rec.modules),
            "class": _severity(rec),
            "sessions": rec.session_count,
            "first_seen": rec.first_seen,
            "last_seen": rec.last_seen,
            "odometer_first_km": lo,
            "odometer_last_km": hi,
            "distance_span_km": span,
            "events": [
                {"at": o.get("timestamp"), "odometer_km": o.get("odometer_km"),
                 "status": o.get("status"), "source": o.get("file")}
                for o in rec.occurrences
            ],
        })
    rows.sort(key=lambda r: (_SEV_RANK.get(r["class"], 9), r["first_seen"] or ""))
    return rows


def _build_ledger(vin: str, entries: list[Any], w: dict[str, Any]) -> list[dict[str, Any]]:
    """Everything ever done to the car, oldest first.

    ``already_attempted`` already merges actuators/adjustments (from the FES
    logs) with dealer results (from :mod:`mes.dealer`) -- see
    ``workup.build``. This adds the two things it does not carry: clears
    (from the logs themselves, and from the live link's own evidence
    capture) and notes, if that concurrently-added module exists.
    """
    ledger: list[dict[str, Any]] = []

    for row in w.get("already_attempted", []):
        if row.get("kind") == "dealer":
            source = "wiTECH"
            if row.get("note"):
                source += f" -- {row['note']}"
            ledger.append({"at": row.get("timestamp"), "kind": "dealer",
                           "what": row.get("operation"), "result": row.get("outcome"),
                           "source": source})
        else:
            ledger.append({"at": row.get("timestamp"), "kind": row.get("kind") or "actuator",
                           "what": row.get("operation"), "result": row.get("outcome"),
                           "source": row.get("note") or "FES log"})

    for entry in entries:
        if entry.kind != "fes" or entry.parse_error:
            continue
        try:
            log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
        except Exception:
            continue
        if not log.clear_events:
            continue
        cleared = sorted({d.full for d in log.cleared} | {d.full for d in log.returned_after_clear})
        returned = [d.full for d in log.returned_after_clear]
        result = (f"returned immediately: {', '.join(returned)}" if returned
                  else "no code returned before the session ended")
        ledger.append({"at": entry.timestamp, "kind": "clear",
                       "what": f"cleared {', '.join(cleared)}" if cleared else "clear attempted",
                       "result": result, "source": entry.name})

    for obs in live_obs.load(vin, "clear_evidence"):
        data = obs.get("data") or {}
        active = data.get("active") or []
        ledger.append({
            "at": obs.get("at"), "kind": "clear (live)",
            "what": f"cleared {data.get('ecu', '?')}",
            "result": (f"{len(active)} active before clear: {', '.join(active)}"
                      if active else "no active codes before the clear"),
            "source": "live link",
        })

    try:
        from . import notes as notes_mod  # type: ignore
    except ImportError:
        notes_mod = None
    if notes_mod is not None:
        try:
            raw_notes = notes_mod.load(vin) or []
        except Exception:
            raw_notes = []
        for n in raw_notes:
            if not isinstance(n, dict):
                continue
            ledger.append({
                "at": n.get("at") or n.get("timestamp"),
                "kind": n.get("kind") or "note",
                "what": n.get("what") or n.get("text") or n.get("note") or n.get("body") or "",
                "result": n.get("result") or "",
                "source": n.get("source") or "notes",
            })

    ledger = [r for r in ledger if r.get("at")]
    ledger.sort(key=lambda r: _ts_key(r["at"]))
    return ledger


def _build_live_status(vin: str) -> dict[str, Any]:
    modules_map: dict[str, dict[str, Any]] = {}
    for obs in live_obs.load(vin, "module_dtcs"):
        data = obs.get("data") or {}
        ecu = data.get("ecu")
        if not ecu or data.get("error"):
            continue
        dtcs = data.get("dtcs") or []
        active = []
        for rec in dtcs:
            status = int(rec.get("status") or 0)
            if status & live_obs.ACTIVE_MASK:
                flags = rec.get("flags") or {}
                active.append({
                    "code": rec.get("code"),
                    "status_hex": f"0x{status:02X}",
                    "mil_requested": bool(flags.get("warningIndicatorRequested")),
                })
        # newest-last iteration order (see live_obs.load) -- later overwrites earlier
        modules_map[ecu] = {"ecu": ecu, "at": obs.get("at"), "tracked_count": len(dtcs),
                            "active": active, "active_count": len(active)}
    modules = sorted(modules_map.values(), key=lambda m: m["ecu"])

    mode06_obs = live_obs.load(vin, "mode06")
    mode06_evap = None
    if mode06_obs:
        newest = mode06_obs[-1]
        data = newest.get("data") or {}
        mode06_evap = {"at": newest.get("at"), "summary": data.get("evap_summary") or []}

    stamps = [m["at"] for m in modules if m.get("at")]
    if mode06_evap and mode06_evap.get("at"):
        stamps.append(mode06_evap["at"])
    as_of = max(stamps, key=_ts_key) if stamps else None

    return {"as_of": as_of, "modules": modules, "mode06_evap": mode06_evap}


def _module_key(name: str) -> str:
    """One code per module, whether the log printed 'Engine / ECM' (SCAN) or the
    ECU description 'Magneti Marelli IAW 10JA ...' (FES). Without this the ECM
    was counted as two modules."""
    from . import compare, modules as modules_mod
    if " / " in (name or ""):
        abbrev = analysis._abbrev_from_name(name)
        return modules_mod.normalize_abbrev(abbrev) or abbrev.upper()
    code = compare._module_for_fes_ecu(name)
    return code


def _build_modules(history: dict[str, Any], live_status: dict[str, Any]) -> list[dict[str, Any]]:
    codes_by_module: dict[str, set] = {}
    last_log_by_module: dict[str, str] = {}
    for rec in history.values():
        for raw_name in rec.modules:
            name = _module_key(raw_name)
            codes_by_module.setdefault(name, set()).add(rec.dtc)
            ls = rec.last_seen
            if ls and (name not in last_log_by_module or ls > last_log_by_module[name]):
                last_log_by_module[name] = ls

    live_by_abbrev = {m["ecu"].upper(): m for m in live_status.get("modules", [])}
    rows = []
    for name in sorted(codes_by_module):
        abbrev = name.upper()
        live = live_by_abbrev.get(abbrev)
        last_log = last_log_by_module.get(name)
        last_live = live.get("at") if live else None
        if last_live and (not last_log or _ts_key(last_live) > _ts_key(last_log)):
            last_read, source = last_live, "live"
        else:
            last_read, source = last_log, ("log" if last_log else None)
        rows.append({
            "module": name,
            "abbrev": abbrev,
            "dtc_count": len(codes_by_module[name]),
            "last_read": last_read,
            "last_read_source": source,
            "active_now": (live["active_count"] > 0) if live else None,
        })
    rows.sort(key=lambda r: (-r["dtc_count"], r["module"]))
    return rows


def _build_odometer_series(entries: list[Any]) -> list[dict[str, Any]]:
    out = []
    for entry in entries:
        if entry.kind != "fes" or entry.parse_error:
            continue
        try:
            log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
        except Exception:
            continue
        if log.odometer_km is not None:
            out.append({"at": entry.timestamp, "odometer_km": log.odometer_km})
    out.sort(key=lambda r: _ts_key(r["at"]))
    return out


def build(vin: str = "") -> dict[str, Any]:
    """Assemble the whole dashboard for one vehicle."""
    vin = (vin or "").strip()
    if not vin:
        return {"error": "a VIN is required"}
    entries = CATALOG.select(vin=vin)
    if not entries:
        return {"error": "no logs match", "vin": vin}
    w = workup_mod.build(vin=vin)
    if "error" in w:
        return w

    history = analysis.dtc_history(entries)
    live_status = _build_live_status(vin)

    return {
        "summary": _build_summary(vin, w),
        "code_timeline": _build_code_timeline(history),
        "repairs_and_tests": _build_ledger(vin, entries, w),
        "live_status": live_status,
        "modules": _build_modules(history, live_status),
        "odometer_series": _build_odometer_series(entries),
    }


__all__ = ["build"]
