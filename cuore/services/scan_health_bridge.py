"""The scan health report: the document CUORE produces after every from-car
scan.

The Scans area (``cuore/live/scanlog.py`` -> ``cuore/services/scanlog_bridge.py``)
is other work's -- when it is importable, :func:`build` reads a scan through
``scanlog_bridge.list_scans``/``scan`` and never re-derives what that module
already derives (DTCs, readiness, Mode 06 rows, which modules answered, the
15-minute scan-session grouping -- see that module's own docstring for why
15 minutes: it is the gap this VIN's own log shows between "the scan" and
"the module scan run twenty minutes later"). ``_normalize_from_raw`` is this
file's own fallback -- the same grouping, done here, for the (expected to be
rare, soon never) case ``scanlog_bridge`` cannot be imported at all. Either
path ends at the same normalized shape (:func:`_normalize_from_scanlog` /
:func:`_normalize_from_raw`) so everything downstream -- the verdict, the
system table, the issues list -- is written once, against that shape, not
twice against two different ones.

Everything a report needs beyond the scan itself (known-good bands, the
system graph, the fault tree, the hypothesis ledger, maintenance intervals,
the verdict) is read through the existing bridge for that knowledge, never
through a second import of the same ``mes`` module another bridge already
owns:

* :mod:`mes.known_good` via :mod:`cuore.services.known_good_bridge`
* :mod:`mes.systems` -- read directly; no system-graph bridge exists yet
  (``systems_bridge.py`` serves a different, dossier-correlation surface)
* :mod:`mes.faulttree` / :mod:`mes.mechanic_tests` / :mod:`mes.jobs` /
  :mod:`mes.live_obs` -- read directly, same posture as ``verdict.py``/
  ``tests_bridge.py`` already take with these modules
* maintenance intervals via :mod:`cuore.services.service_bridge` (best
  effort -- it needs an odometer reading this scan format does not carry,
  so a maintenance section that cannot be computed is simply omitted, never
  guessed)

Three public functions, in order of what a caller actually wants:

* :func:`build` -- the report as a plain dict (the JSON API's body).
* :func:`markdown` -- the same report as the document text, same shape as
  ``docs/vehicles/<VIN>/reports/<date>-scan-health-report.md``.
* :func:`save` -- writes that text to disk, never over a hand-written file
  of the same name.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache
from ..live import read_state
from .errors import NotFound

# NOTE: this project's live link (``mes.live_obs``) logs DTCs, readiness and
# Mode 06 results, but no freeze-frame/live PID snapshot -- see the module
# docstring. ``mes.known_good``/``cuore.services.known_good_bridge`` are the
# right place to grade a PID reading once the Scans area starts logging one
# (``mes.scan_health.classify_system``'s ``pid_reading``/``known_good_row``
# path already supports it); nothing here invents that data meanwhile.

from mes import live_obs  # noqa: E402
from mes import mechanic_tests  # noqa: E402
from mes import scan_health  # noqa: E402
from mes import systems as systems_mod  # noqa: E402

try:
    from mes import jobs as jobs_mod  # noqa: E402
except Exception:  # noqa: BLE001 -- the report must still render with no job on file
    jobs_mod = None

try:
    from . import service_bridge  # noqa: E402
except Exception:  # noqa: BLE001 -- maintenance is a nice-to-have section
    service_bridge = None

try:
    from . import scanlog_bridge  # noqa: E402
    from ..live import addressing as _addressing  # noqa: E402
except Exception:  # noqa: BLE001 -- fall back to this file's own grouping
    scanlog_bridge = None
    _addressing = None

#: A from-car read more than this far from the previous one starts a new
#: scan session. See the module docstring for why 15 minutes, not some other
#: number: it is the gap this VIN's own log shows between "the scan" and
#: "the module scan run afterward".
_SESSION_GAP = timedelta(minutes=15)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- grouping observations into "a scan": this file's own fallback ---------
#
# Only used when ``scanlog_bridge`` cannot be imported at all -- see
# :func:`_scan_for`. Kept deliberately parallel to
# ``cuore.live.scanlog``'s own ``_clusters``/``WINDOW``: the same 15-minute
# gap rule, derived independently so this file has no hard dependency on
# that module's internals, only (preferentially) on its public read surface.

def _parse_at(entry: dict[str, Any]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(entry.get("at", "")))
    except ValueError:
        return None


def _vin_matches(entry: dict[str, Any], vin: str) -> bool:
    """A real read's own ``vin`` field is often blank even on this project's
    own live link (see ``mes.live_obs`` -- only the ``identity``/``readiness``/
    ``mode06``/``scan`` kinds reliably carry it); an untagged read is kept
    rather than dropped, on the documented single-car-install assumption
    ``mes.known_good._csv_numbers`` already states for this install."""
    v = entry.get("vin") or ""
    return v in ("", vin)


# --- enrichment: module codes / coverage / mode09 / PID readings -----------
#
# ``module_dtcs``, ``scan_coverage``, ``mode09``, ``pids_snapshot``, ``pid``
# and ``freeze_frame`` observations are read straight off ``mes.live_obs``
# here, independent of which 15-minute scan session (``_scan_for``, above)
# this report is built around. Two reasons, not one:
#
# * A whole-car module sweep, a coverage sweep and the DTC/Mode 06 read a
#   mechanic actually cares about routinely land in *different* sessions in
#   this project's own corpus (a module sweep minutes after the main read,
#   a coverage probe run stand-alone later) -- gating this data to one
#   session's own window would silently drop most of it on a normal night's
#   work, not just an edge case.
# * ``cuore.live.scanlog``'s own per-cluster view (read through
#   ``scanlog_bridge``, the preferred path above) folds ``module_dtcs``
#   into a bare code list for its MES-export surface and collapses
#   ``scan_coverage`` into a one-line summary for its own scan-list view --
#   both lose exactly the detail this report needs (status flags, the
#   per-module ``why``), so re-deriving them from the same ``mes.live_obs``
#   rows this project's other direct readers (``_dtc_lists``/``_mode06_by_mid``
#   above) already use is the only way to get it without a second,
#   drifting copy of ``cuore.live.scanlog``'s own logic.
#
# "Latest wins" per key, same rule every ``_latest*`` helper in this
# project's live-observation readers already uses.

def _latest_kind_data(vin: str, kind: str) -> Optional[dict[str, Any]]:
    """The newest observation of ``kind`` for this VIN, or ``None``."""
    data: Optional[dict[str, Any]] = None
    for o in live_obs.load(from_car_only=True):
        if o.get("kind") == kind and _vin_matches(o, vin):
            data = o.get("data") or {}
    return data


def _module_dtc_entries(vin: str) -> dict[str, dict[str, Any]]:
    """``{ecu: data}`` -- the newest ``module_dtcs`` read of each ECU for
    this VIN, regardless of session. An ADAPTER/BUS-ERROR read (``data.error``
    set, ``mes.live_obs``'s own "this is not 'no codes'" case) is skipped:
    it answers nothing, so it must never look like a module that was swept
    clean."""
    out: dict[str, dict[str, Any]] = {}
    for o in live_obs.load(from_car_only=True):
        if o.get("kind") != "module_dtcs" or not _vin_matches(o, vin):
            continue
        data = o.get("data") or {}
        ecu = data.get("ecu")
        if ecu and read_state.is_read(data):
            out[ecu] = data
    return out


def _module_dtc_systems(vin: str) -> tuple[dict[str, list[dict[str, Any]]],
                                           dict[str, list[dict[str, Any]]], int]:
    """``(active_by_system, history_by_system, live_u_code_count)`` from
    every module DTC on file for this VIN (see :func:`_module_dtc_entries`).

    A code's system is its own ``mes.systems.systems_for_code`` primary --
    the same rule already used for stored/pending/permanent DTCs below --
    so a U-code always lands on ``"network"`` no matter which physical
    module answered it; only when that resolves to nothing does the
    reporting module's own :data:`mes.scan_health.ECU_SYSTEM` bucket stand
    in. ``live_u_code_count`` counts every ``"active"``/``"history"``
    U-code (never a bare status-64 placeholder), for
    :func:`mes.scan_health.network_bus_event_note`.
    """
    active: dict[str, list[dict[str, Any]]] = {}
    history: dict[str, list[dict[str, Any]]] = {}
    live_u = 0
    for ecu, data in _module_dtc_entries(vin).items():
        for rec in data.get("dtcs") or []:
            code = rec.get("code")
            if not code:
                continue
            category = scan_health.module_dtc_category(rec.get("flags"))
            if category is None:
                continue
            if code.upper().startswith("U"):
                live_u += 1
            sys_key = _primary_system_for_codes([code]) or scan_health.ECU_SYSTEM.get(ecu)
            if not sys_key:
                continue
            bucket = active if category == "active" else history
            bucket.setdefault(sys_key, []).append({"code": code, "module": ecu})
    return active, history, live_u


def _coverage_by_system(vin: str) -> dict[str, str]:
    """``{system: gap_text}`` from this VIN's newest ``scan_coverage``
    observation -- one GAP row's reading per UDS-module system this
    coverage sweep did not get an answer from. A module that *did*
    answer (category ``"answered"``) contributes nothing here; everything
    else (``"not_reachable"``, ``"silent"``) is real, sourced GAP wording,
    via :func:`mes.scan_health.coverage_gap_text` -- never invented."""
    coverage = _latest_kind_data(vin, "scan_coverage")
    out: dict[str, str] = {}
    if not coverage:
        return out
    for row in coverage.get("coverage") or []:
        sys_key = scan_health.ECU_SYSTEM.get(row.get("module"))
        if not sys_key or sys_key in out or row.get("category") == "answered":
            continue
        out[sys_key] = scan_health.coverage_gap_text(row.get("category"), row.get("why"))
    return out


def _pid_readings(vin: str) -> dict[str, dict[str, Any]]:
    """``{pid_key: {"value", "unit"}}`` merged from this VIN's newest
    ``pids_snapshot`` (a full-scan PID battery), per-PID ``pid`` reads (the
    freeze panel), and ``freeze_frame`` rows -- whichever of the three
    this install's live link has actually logged (``pid``/``freeze_frame``
    are still speculative kinds on this install; see ``mes.scan_health``'s
    own module docstring). Latest observation wins per key, read in file
    (chronological) order."""
    out: dict[str, dict[str, Any]] = {}
    for o in live_obs.load(from_car_only=True):
        if not _vin_matches(o, vin):
            continue
        kind = o.get("kind")
        data = o.get("data") or {}
        if kind == "pids_snapshot":
            for name, reading in (data.get("readings") or {}).items():
                if isinstance(reading, dict) and reading.get("value") is not None:
                    out[name] = {"value": reading.get("value"), "unit": reading.get("unit", "")}
        elif kind == "pid":
            name = data.get("pid") or data.get("name")
            if name and data.get("value") is not None:
                out[name] = {"value": data.get("value"), "unit": data.get("unit", "")}
        elif kind == "freeze_frame":
            for row in data.get("pids") or []:
                name = row.get("pid") or row.get("name")
                if name and row.get("value") is not None:
                    out[name] = {"value": row.get("value"), "unit": row.get("unit", "")}
    return out


def sessions_for(vin: str) -> list[list[dict[str, Any]]]:
    """Every from-car observation for this VIN (or untagged), grouped into
    scan sessions by the 15-minute-gap rule, oldest session first."""
    obs = [o for o in live_obs.load(from_car_only=True) if _vin_matches(o, vin)]
    obs = [o for o in obs if _parse_at(o) is not None]
    obs.sort(key=_parse_at)
    sessions: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    prev: Optional[datetime] = None
    for o in obs:
        t = _parse_at(o)
        if prev is not None and t - prev > _SESSION_GAP:
            sessions.append(current)
            current = []
        current.append(o)
        prev = t
    if current:
        sessions.append(current)
    return sessions


def _session_id(session: list[dict[str, Any]]) -> str:
    """The scan id a caller addresses this session by: its first read's
    timestamp, exactly as logged -- stable, sortable, and never re-derived
    from content that could itself change."""
    return str(session[0].get("at", ""))


def _latest(session: list[dict[str, Any]], kind: str) -> Optional[dict[str, Any]]:
    for o in reversed(session):
        if o.get("kind") == kind:
            return o
    return None


def _dtc_lists(session: list[dict[str, Any]]) -> dict[str, list[str]]:
    """The newest stored/pending/permanent DTC read of each kind in this
    session, keyed by that kind."""
    out: dict[str, list[str]] = {}
    for o in session:
        if o.get("kind") != "obd_dtcs":
            continue
        data = o.get("data") or {}
        k = data.get("kind")
        if k in ("stored", "pending", "permanent"):
            out[k] = list(data.get("dtcs") or [])
    return out


def _mode06_by_mid(session: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """``{mid: [row, ...]}`` for the newest Mode 06 read in this session,
    pooled across every ECU that answered."""
    obs = _latest(session, "mode06")
    if obs is None:
        return {}
    results = ((obs.get("data") or {}).get("results")) or {}
    out: dict[str, list[dict[str, Any]]] = {}
    for mid, res in results.items():
        rows: list[dict[str, Any]] = []
        for ecu_rows in (res.get("by_ecu") or {}).values():
            rows.extend(ecu_rows)
        if rows:
            out[mid] = rows
    return out


def _readiness_since_clear(session: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    obs = _latest(session, "readiness")
    if obs is None:
        return None
    return (obs.get("data") or {}).get("since_clear")


def _module_answers(session: list[dict[str, Any]]) -> set[str]:
    """Raw/short module ids that answered a DTC query this scan (even with
    an empty result) -- from the generic ``obd_dtcs.by_ecu`` map and any
    ``module_dtcs``/``scan`` reads this session happens to carry. Translated
    to this project's short codes (``ECM``, ``TCM``, ...) by :func:`_ecu_code`
    one level up, same as the ``scanlog_bridge`` path."""
    answered: set[str] = set()
    for o in session:
        kind = o.get("kind")
        data = o.get("data") or {}
        if kind == "obd_dtcs":
            answered.update((data.get("by_ecu") or {}).keys())
        elif kind == "module_dtcs" and read_state.is_read(data):
            ecu = data.get("ecu")
            if ecu:
                answered.add(ecu)
        elif kind == "scan":
            for mod in data.get("modules") or []:
                if not mod.get("error") and mod.get("ecu"):
                    answered.add(mod["ecu"])
    return answered


def _normalize_from_raw(vin: str, session: list[dict[str, Any]]) -> dict[str, Any]:
    newest_at = session[-1].get("at")
    stream = next((o.get("stream") for o in reversed(session) if o.get("stream")), None)
    return {
        "dtcs": _dtc_lists(session),
        "mode06_by_mid": _mode06_by_mid(session),
        "readiness": _readiness_since_clear(session),
        "answered": {_ecu_code(e) or e for e in _module_answers(session)},
        "header": {"vin": vin, "as_of": newest_at, "adapter": stream or "unknown link"},
    }


# --- the scanlog_bridge path (preferred) ------------------------------------

_ECU_BY_HEX: Optional[dict[str, str]] = None


def _ecu_code(raw: str) -> Optional[str]:
    """A raw CAN response id (``"18DAF110"``) or an already-short code
    (``"ECM"``) to this project's own short module code, via
    ``cuore.live.addressing`` -- or ``None`` for an id this project's own
    module registry does not recognise (never guessed)."""
    global _ECU_BY_HEX
    if _addressing is None or not raw:
        return raw or None
    if _addressing.by_code(raw) is not None:
        return raw
    if _ECU_BY_HEX is None:
        _ECU_BY_HEX = {f"{m.response_id:08X}": m.code for m in _addressing.MODULES
                      if m.response_id is not None}
    return _ECU_BY_HEX.get(str(raw).upper())


def _normalize_from_scanlog(found: dict[str, Any]) -> dict[str, Any]:
    mode06_by_mid: dict[str, list[dict[str, Any]]] = {}
    for row in found.get("mode06") or []:
        mode06_by_mid.setdefault(str(row.get("mid")), []).append(row)
    answered = {_ecu_code(e) for e in (found.get("ecus") or [])}
    answered.discard(None)
    readiness = (found.get("readiness") or {}).get("since_clear")
    source = found.get("source") or {}
    return {
        "dtcs": found.get("dtcs") or {},
        "mode06_by_mid": mode06_by_mid,
        "readiness": readiness,
        "answered": answered,
        "header": {"vin": found.get("vin"), "as_of": found.get("ended") or found.get("started"),
                   "adapter": source.get("stream") or "unknown link"},
    }


def _scan_has_mode06_or_readiness(found: dict[str, Any]) -> bool:
    return bool(found.get("mode06") or found.get("readiness"))


def _scan_has_any_dtc(found: dict[str, Any]) -> bool:
    dtcs = found.get("dtcs") or {}
    return any(dtcs.get(k) for k in ("stored", "pending", "permanent"))


def _pick_latest_scan(scans: list[dict[str, Any]]) -> dict[str, Any]:
    """``scans`` is newest-first (``scanlog_bridge.list_scans``'s own
    order). "Latest" means the newest scan that actually read Mode 06 or
    readiness -- the two signals this report's own verdict/system-table
    logic is built around -- not simply the newest timestamp: a module
    sweep (``module_dtcs`` folds into ``dtcs["stored"]`` too, in
    ``cuore.live.scanlog``'s own per-cluster view -- a plain DTC check is
    not enough to tell the two apart) or a stand-alone coverage/mode09
    probe routinely lands in its own, later session on this project's own
    corpus, and must not silently blank out the DTC/Mode 06 read a
    mechanic actually came here to see. Falls back to the newest with any
    DTC signal, then to the newest overall -- so the common case (one
    scan on file) behaves exactly as before."""
    for pred in (_scan_has_mode06_or_readiness, _scan_has_any_dtc):
        found = next((s for s in scans if pred(s)), None)
        if found is not None:
            return found
    return scans[0]


def _session_has_mode06_or_readiness(session: list[dict[str, Any]]) -> bool:
    return bool(_mode06_by_mid(session) or _readiness_since_clear(session))


def _session_has_any_dtc(session: list[dict[str, Any]]) -> bool:
    dtcs = _dtc_lists(session)
    return any(dtcs.get(k) for k in ("stored", "pending", "permanent"))


def _pick_latest_session(sessions: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Same "latest with real signal" preference as :func:`_pick_latest_scan`,
    for this file's own 15-minute-grouping fallback. ``sessions`` is
    oldest-first (:func:`sessions_for`'s own order)."""
    for pred in (_session_has_mode06_or_readiness, _session_has_any_dtc):
        found = next((s for s in reversed(sessions) if pred(s)), None)
        if found is not None:
            return found
    return sessions[-1]


def _scan_for(vin: str, scan_id: Optional[str]) -> tuple[str, dict[str, Any]]:
    """``(scan_id, normalized)`` -- via ``scanlog_bridge`` when it imports,
    else this file's own 15-minute grouping over the raw observations."""
    if scanlog_bridge is not None:
        scans = scanlog_bridge.list_scans(vin).get("scans") or []  # newest first
        if not scans:
            raise NotFound(f"no from-car scan on file for {vin}")
        if scan_id is None or scan_id == "latest":
            found = _pick_latest_scan(scans)
        else:
            found = next((s for s in scans
                         if s["id"] == scan_id or s["id"].startswith(scan_id)), None)
            if found is None:
                raise NotFound(f"no scan {scan_id!r} on file for {vin}")
        return found["id"], _normalize_from_scanlog(found)

    sessions = sessions_for(vin)
    if not sessions:
        raise NotFound(f"no from-car scan on file for {vin}")
    if scan_id is None or scan_id == "latest":
        session = _pick_latest_session(sessions)
    else:
        session = next((s for s in sessions if _session_id(s) == scan_id
                       or _session_id(s).startswith(scan_id)), None)
        if session is None:
            raise NotFound(f"no scan {scan_id!r} on file for {vin}")
    return _session_id(session), _normalize_from_raw(vin, session)


def has_any_scan(vin: str) -> bool:
    if scanlog_bridge is not None:
        return bool(scanlog_bridge.list_scans(vin).get("scans"))
    return bool(sessions_for(vin))


# --- the model doc's shape --------------------------------------------------

def _primary_system_for_codes(codes: list[str]) -> Optional[str]:
    for code in codes:
        for entry in systems_mod.systems_for_code(code):
            if entry["role"] == "primary" and entry["system"] != "UNKNOWN":
                return entry["system"]
    return None


def build_verdict(norm: dict[str, Any]) -> dict[str, Any]:
    dtcs = norm["dtcs"]
    mode06 = norm["mode06_by_mid"]
    fail_rows = [r for rows in mode06.values() for r in rows if r.get("passed") is False]
    v = scan_health.verdict(stored=dtcs.get("stored"), pending=dtcs.get("pending"),
                            permanent=dtcs.get("permanent"), readiness=norm["readiness"],
                            mode06_fail_rows=fail_rows)
    codes = list(dict.fromkeys((dtcs.get("stored") or []) + (dtcs.get("permanent") or [])
                               + (dtcs.get("pending") or [])))
    primary = _primary_system_for_codes(codes) if codes else None
    label = systems_mod.SYSTEMS.get(primary, {}).get("label") if primary else None
    v["primary_system"] = label
    v["codes"] = codes
    return v


def _not_read_verdict(verdict: dict[str, Any], systems_table: list[dict[str, Any]]) -> None:
    """Silence is never clean: systems nothing answered for are listed on the
    verdict, and a would-be VERIFIED_CLEAN becomes NO_DATA."""
    gaps = [r["label"] if "label" in r else r["system"] for r in systems_table
            if r["health"] == scan_health.GAP]
    verdict["not_read"] = gaps
    if not gaps:
        return
    if verdict["state"] == scan_health.VERIFIED_CLEAN:
        verdict["state"] = scan_health.NO_DATA
        verdict["label"] = scan_health._VERDICT_LABELS[scan_health.NO_DATA]
    verdict["basis"] = [read_state.banner("no answer for " + ", ".join(gaps))] + list(verdict["basis"])


def build_systems_table(vin: str, norm: dict[str, Any]) -> list[dict[str, Any]]:
    mode06 = norm["mode06_by_mid"]
    dtcs = norm["dtcs"]
    codes = list(dict.fromkeys((dtcs.get("stored") or []) + (dtcs.get("permanent") or [])
                               + (dtcs.get("pending") or [])))
    fault_systems: set[str] = set()
    for code in codes:
        for entry in systems_mod.systems_for_code(code):
            if entry["role"] == "primary" and entry["system"] != "UNKNOWN":
                fault_systems.add(entry["system"])

    #: mid -> system, by this module's own interpretation table
    mid_system: dict[str, list[dict[str, Any]]] = {}
    for mid, rows in mode06.items():
        meta = scan_health.MODE06_MIDS.get(mid)
        sys_key = meta["system"] if meta else None
        if sys_key:
            mid_system.setdefault(sys_key, []).extend(rows)

    readiness = norm["readiness"] or {}
    monitors = readiness.get("monitors") or []
    monitor_by_system: dict[str, dict[str, Any]] = {}
    for mon in monitors:
        sys_key = scan_health.READINESS_MONITOR_SYSTEM.get(mon.get("monitor"))
        if sys_key and sys_key not in monitor_by_system:
            monitor_by_system[sys_key] = mon

    answered = norm["answered"]
    module_active, module_history, _live_u = _module_dtc_systems(vin)
    coverage_by_system = _coverage_by_system(vin)

    pid_readings = _pid_readings(vin)
    pid_by_system: dict[str, dict[str, Any]] = {}
    pid_key_by_system: dict[str, str] = {}
    for pid_key, reading in pid_readings.items():
        sys_key = scan_health.PID_SYSTEM.get(pid_key)
        if sys_key and sys_key not in pid_by_system:
            pid_by_system[sys_key] = reading
            pid_key_by_system[sys_key] = pid_key
    known_good_by_system: dict[str, Optional[dict[str, Any]]] = {}
    if pid_key_by_system:
        try:
            from . import known_good_bridge
        except Exception:  # noqa: BLE001 -- a PID reading with no band is still a reading
            known_good_bridge = None
        if known_good_bridge is not None:
            for sys_key, pid_key in pid_key_by_system.items():
                # vin-gated (2026-10-14 marque-port fix): a band tagged
                # for a platform this VIN cannot be confirmed to share
                # (mes.known_good.applies_to_vin) comes back None here,
                # same as a channel with no row at all.
                known_good_by_system[sys_key] = known_good_bridge.known_good_for(
                    pid_key, vin=vin)

    rows_out: list[dict[str, Any]] = []
    for sys_key, sys_def in systems_mod.SYSTEMS.items():
        ecu_answered = any(scan_health.ECU_SYSTEM.get(ecu) == sys_key for ecu in answered)
        row = scan_health.classify_system(
            sys_key,
            mode06_rows=mid_system.get(sys_key),
            dtc_fault=sys_key in fault_systems,
            module_active=module_active.get(sys_key),
            module_history=module_history.get(sys_key),
            pid_reading=pid_by_system.get(sys_key),
            known_good_row=known_good_by_system.get(sys_key),
            ecu_answered=ecu_answered,
            readiness_reading=monitor_by_system.get(sys_key),
            coverage_text=coverage_by_system.get(sys_key),
        )
        row["label"] = sys_def["label"]
        rows_out.append(row)
    return rows_out


def _what_it_tells_us(vin: str, norm: dict[str, Any]) -> list[str]:
    """Rule-based, hedged prose for every failing Mode 06 MID this scan
    logged -- never "cause"/"proven", only what the ECM's own test measured
    (:data:`mes.scan_health.MODE06_MIDS`'s ``fail_meaning`` for that MID) --
    plus one network "bus event" note when three or more live U-codes are
    on file for this VIN (:func:`mes.scan_health.network_bus_event_note`)."""
    mode06 = norm["mode06_by_mid"]
    out: list[str] = []
    seen_systems: set[str] = set()
    for mid, rows in mode06.items():
        fail_rows = [r for r in rows if r.get("passed") is False]
        if not fail_rows:
            continue
        meta = scan_health.MODE06_MIDS.get(mid)
        if not meta or meta["system"] in seen_systems:
            continue
        seen_systems.add(meta["system"])
        row = sorted(fail_rows, key=lambda r: scan_health.MODE06_MIDS.get(
            str(r.get("mid") or ""), {}).get("priority", 50))[0]
        limit = scan_health.mode06_threshold(row)
        measured = (f"the ECM measured {row.get('value')} against its own limit of {limit}."
                   if limit is not None else f"the ECM measured {row.get('value')}.")
        sentence = (f"Mode 06 {meta['name']} (MID {mid}): {meta['fail_meaning']} "
                   f"-- {measured}")
        out.append(sentence)

    _active, _history, live_u = _module_dtc_systems(vin)
    bus_event = scan_health.network_bus_event_note(live_u)
    if bus_event:
        out.append(bus_event)
    return out


def _hypothesis_lines(vin: str) -> list[str]:
    if jobs_mod is None:
        return []
    try:
        job = jobs_mod.current(vin)
    except Exception:  # noqa: BLE001 -- the job store is a nice-to-have here
        job = None
    if not job:
        return []
    lines: list[str] = []
    for h in job.get("hypotheses") or []:
        if h.get("status") in ("open", "supported"):
            lines.append(f"Unverified: {h.get('text')} (status {h.get('status')})"
                         + (f" -- next test: {h['next_test']}" if h.get("next_test") else ""))
    return lines


def _issues(vin: str, verdict: dict[str, Any], systems_table: list[dict[str, Any]],
           norm: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    # 1. active faults first, with the next test from mes.mechanic_tests.
    mode06 = norm["mode06_by_mid"]
    seen_tests: set[str] = set()
    if verdict["state"] == scan_health.ACTIVE_FAULTS:
        for mid, rows in mode06.items():
            if not any(r.get("passed") is False for r in rows):
                continue
            meta = scan_health.MODE06_MIDS.get(mid)
            if not meta or not meta.get("next_test") or meta["next_test"] in seen_tests:
                continue
            seen_tests.add(meta["next_test"])
            test = mechanic_tests.test(meta["next_test"])
            if not test:
                continue
            issues.append(f"{test['name']} now -- {test.get('purpose', '')} "
                          f"Do not clear codes before it.")

    # 1b. an ACTIVE network-system module DTC this scan (e.g. U1713-2F on
    #     the BCM) -- right after EVAP/Mode06 in the active-faults tier,
    #     pointing at the documented upstream cause before the bus itself.
    module_active, _history, _live_u = _module_dtc_systems(vin)
    network_issue = scan_health.network_active_issue(module_active.get("network"))
    if network_issue:
        issues.append(network_issue)

    # 3. gaps -- systems this scan did not read at all, grouped by the
    #    scan_coverage reason when one is on file (naturally "per cable",
    #    since every module behind the same missing cable shares the same
    #    reason) -- falls back to one flat list of system labels when no
    #    coverage observation narrows it down.
    gap_rows = [r for r in systems_table if r["health"] == scan_health.GAP]
    if gap_rows:
        by_reason: dict[Optional[str], list[str]] = {}
        for r in gap_rows:
            by_reason.setdefault(r.get("reading"), []).append(r["label"])
        for reason, labels in by_reason.items():
            if reason:
                issues.append(read_state.banner(reason.rstrip(".")) + ": " + ", ".join(labels) + ".")
            else:
                issues.append(read_state.banner("no answer this scan") + ": " + ", ".join(labels) + ".")

    # 2. unverified repairs (open/supported hypotheses on the job ledger).
    issues.extend(_hypothesis_lines(vin))

    # 4. maintenance overdue -- best effort; omitted when it cannot be computed.
    if service_bridge is not None:
        try:
            due = service_bridge.maintenance_due(vin)
            overdue = due.get("overdue") if isinstance(due, dict) else None
            if overdue:
                issues.append("Maintenance overdue: " + ", ".join(str(x) for x in overdue) + ".")
        except Exception:  # noqa: BLE001 -- no odometer on file is routine, not an error
            pass

    # 5. evidence to attach.
    if verdict["state"] == scan_health.ACTIVE_FAULTS:
        issues.append("Record this scan's Mode 06 results and DTC read as evidence on "
                      "the open hypotheses (attach from the job page).")

    return issues


def _clean_bill(systems_table: list[dict[str, Any]]) -> list[str]:
    return [r["label"] + (f" ({r['margin']} margin)" if r.get("margin") else "")
           for r in systems_table if r["health"] == scan_health.OK]


def _observations_mtime() -> float:
    try:
        return live_obs.observations_path().stat().st_mtime
    except OSError:
        return 0.0


def build_cached(vin: str, scan_id: Optional[str] = None) -> dict[str, Any]:
    """:func:`build`, memoised on ``(vin, scan_id, observations mtime)``.

    This is the "derived, cached by observations mtime, not pre-written"
    report the API/web routes call: a new from-car read moves the mtime and
    the cached report falls out on its own, same posture as
    ``cuore.services.cache``'s own corpus-mtime dossiers.
    """
    key = ("scan_health", vin, scan_id, _observations_mtime())
    return cache.get_or_build(key, lambda: build(vin, scan_id))


def build(vin: str, scan_id: Optional[str] = None) -> dict[str, Any]:
    """The scan health report as a plain dict."""
    vin = (vin or "").strip()
    if not vin:
        raise NotFound("a VIN is required")
    sid, norm = _scan_for(vin, scan_id)
    verdict = build_verdict(norm)
    systems_table = build_systems_table(vin, norm)
    _not_read_verdict(verdict, systems_table)

    # Mode 09: calibration IDs/CVNs in the header, EVAP's own IUPR
    # completion numerator/denominator folded into its row -- both only
    # when the ECM actually answered that PID this install (neither is
    # on file yet; see mes.scan_health.mode09_header_extras/evap_iupr).
    mode09_obs = _latest_kind_data(vin, "mode09")
    header = dict(norm["header"])
    header.update(scan_health.mode09_header_extras(mode09_obs))
    iupr = scan_health.evap_iupr(mode09_obs)
    if iupr:
        for row in systems_table:
            if row["system"] == "evap" and row.get("reading"):
                row["reading"] += (f" [EVAP IUPR {iupr.get('numerator')}/"
                                   f"{iupr.get('denominator')}]")
                break

    # Transmission: the newest ATF temperature any MES CSV recording on
    # this install has (never the live serial stream -- see
    # mes_recordings_bridge's own docstring), folded into the
    # transmission_driveline row the same way EVAP's IUPR note is folded in
    # above. No recording with that column yet (the common case today) ->
    # the row is left exactly as classify_system built it.
    try:
        from . import mes_recordings_bridge
        atf = mes_recordings_bridge.latest_atf_temp()
    except Exception:  # noqa: BLE001 -- the report must render with or without this
        atf = None
    if atf:
        for row in systems_table:
            if row["system"] == "transmission_driveline":
                note = f"ATF {atf['value_c']:g} C from MES recording {atf['recorded_at']}"
                row["reading"] = f"{row['reading']} [{note}]" if row.get("reading") else note
                break

    return {
        "vin": vin,
        "scan_id": sid,
        "header": header,
        "verdict": verdict,
        "systems": systems_table,
        "measurement_notes": _what_it_tells_us(vin, norm),
        "issues": _issues(vin, verdict, systems_table, norm),
        "clean_bill": _clean_bill(systems_table),
    }


# --- rendering ---------------------------------------------------------------

def markdown(vin: str, scan_id: Optional[str] = None) -> str:
    """The report as document text, same shape as the hand-written model
    (``docs/vehicles/<VIN>/reports/<date>-scan-health-report.md``)."""
    r = build_cached(vin, scan_id)
    header = r["header"]
    verdict = r["verdict"]
    lines: list[str] = []
    lines.append(f"# Scan health report -- {vin}")
    lines.append("")
    lines.append(f"As of {header['as_of']}, read live from the car ({header['adapter']}).")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{verdict['label'].upper()}.**" +
                 (f" Primary system: {verdict['primary_system']}." if verdict.get("primary_system") else ""))
    for b in verdict["basis"]:
        lines.append(f"- {b}")
    lines.append("")
    lines.append("## System by system")
    lines.append("")
    lines.append("| System | Reading | Band / spec | Health |")
    lines.append("|---|---|---|---|")
    for row in r["systems"]:
        conf = row.get("spec_confidence")
        if conf == "UNKNOWN":
            spec = scan_health.UNKNOWN_SPEC
        elif conf:
            spec = f"{conf} -- {row.get('spec_source') or ''}".rstrip(" -")
        else:
            spec = "--"
        reading = row.get("reading") or "--"
        if row["health"] == scan_health.GAP:
            reading = read_state.banner((row.get("reading") or "no answer this scan").rstrip("."))
        margin_txt = f" ({row['margin']} margin)" if row.get("margin") else ""
        lines.append(f"| {row['label']} | {reading}{margin_txt} | {spec} | {row['health']} |")
    lines.append("")
    if r["measurement_notes"]:
        lines.append("## What the measurement tells us")
        lines.append("")
        for n in r["measurement_notes"]:
            lines.append(n)
            lines.append("")
    lines.append("## Issues to address, in order")
    lines.append("")
    if r["issues"]:
        for i, issue in enumerate(r["issues"], 1):
            lines.append(f"{i}. {issue}")
    else:
        lines.append("None outstanding from this scan.")
    lines.append("")
    lines.append("## Clean bill")
    lines.append("")
    if r["clean_bill"]:
        lines.append(", ".join(r["clean_bill"]) + ".")
    else:
        lines.append("Nothing passed with a spec to grade it against this scan.")
    lines.append("")
    return "\n".join(lines)


# --- saving ------------------------------------------------------------------

def _state_dir() -> Path:
    from ..live.config import state_dir
    return state_dir()


def _target_dir(vin: str) -> Path:
    override = os.environ.get("CUORE_SCAN_REPORT_DIR")
    if override:
        return Path(override) / vin / "reports"
    per_vehicle = REPO_ROOT / "docs" / "vehicles" / vin
    if per_vehicle.is_dir():
        return per_vehicle / "reports"
    return _state_dir() / "reports" / vin


def save(vin: str, scan_id: Optional[str] = None) -> dict[str, Any]:
    """Write the report to disk. Never overwrites a hand-written file of the
    same name -- writes ``<date>-scan-health-report-auto.md`` instead, and
    is free to overwrite *that* file on a later call, since it is this
    function's own derived output."""
    r = build(vin, scan_id)
    date_str = str(r["header"]["as_of"])[:10] or datetime.now().strftime("%Y-%m-%d")
    target_dir = _target_dir(vin)
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{date_str}-scan-health-report.md"
    path = target_dir / name
    if path.exists():
        path = target_dir / f"{date_str}-scan-health-report-auto.md"
    text = markdown(vin, scan_id)
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "scan_id": r["scan_id"]}


__all__ = ["build", "build_cached", "markdown", "save", "sessions_for", "has_any_scan",
          "build_verdict", "build_systems_table"]
