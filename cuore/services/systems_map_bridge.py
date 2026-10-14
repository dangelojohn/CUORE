"""``GET /api/systems/{vin}/state`` -- live per-system state, hot edges and
the session timeline for the Systems map overlay (Phase 2 of the dive-in
plan, ``docs/research/SYSTEMS_DIVE_IN_PLAN_2026-10-08.md``).

Three view-model pieces, each a thin derivation of data another bridge (or
``mes`` itself) already sources -- nothing here invents a system key, a
confidence level or a status word that isn't already one of the existing
vocabularies:

* :func:`system_states` -- per system key: ``state`` (one of
  ``ALLOWED_STATES``), ``open_code_count`` and ``codes``. Built the same way
  ``cuore.services.system_detail_bridge._dossier_codes_map`` already does
  (``mes_bridge.workup`` + ``dossier_bridge.build_view`` for the per-code
  ACTIVE/CLEARED_UNVERIFIED/STALE vocabulary -- the only place in
  ``cuore.services`` that computes it, per
  ``grep -l "CLEARED_UNVERIFIED" cuore/services``), aggregated up to
  whichever system ``systems_bridge.correlate``'s own ``by_system`` row
  already groups that code under. ``VERIFIED_CLEAN`` is never borrowed from
  the whole-car verdict: a system earns it only when its own codes are all
  CLEARED_UNVERIFIED (none ACTIVE) *and* ``mes.systems.monitors_for_system``
  names a real OBD-II monitor for that system that
  ``dossier_bridge.readiness_panel`` reports complete -- and
  ``readiness_panel`` only ever reports a reading taken from the car itself
  (a serial-stream observation, after the last clear; see
  ``dossier_bridge._latest_readiness``/``cuore.live.store.is_from_car``), so
  a demo/replay/scripted readiness source can never produce VERIFIED_CLEAN
  here. A system with no monitor at all stays CLEARED_UNVERIFIED (no
  monitor evidence is possible for it, ever) until a car scan after the
  clear shows no code back for it; ``NO_DATA`` is a system with no codes in
  this car's corpus at all.
* :func:`edges` -- co-occurrence pairs from ``systems_bridge.correlate``
  merged with the dependency table from ``systems_bridge.systems()``, so
  every edge the map can draw carries ``lift``/``sessions_together`` (0/None
  when the corpus has no evidence yet) alongside ``confidence``/``source``.
  Never worded "depends on": a pure co-occurrence pair with no dependency
  edge gets ``kind="co-occurrence"`` and a plain "corpus co-occurrence"
  source, no prose ``why`` at all.
* :func:`sessions` -- one row per session (MES log file) ordered by time,
  each the systems that session's codes implicated, built the same way
  ``mes.systems.correlate`` builds its own internal (never-returned)
  ``session_systems``: ``mes.analysis.dtc_history`` occurrences grouped by
  file, primary systems via the public ``mes.systems.systems_for_code``.

Read-only: nothing here writes state.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401 -- side effect: puts `mes` on sys.path

from datetime import datetime

from . import dossier_bridge, mes_bridge, systems_bridge

from mes import analysis as analysis_mod  # noqa: E402
from mes import dtc as dtc_mod  # noqa: E402
from mes import systems as systems_mod  # noqa: E402

try:
    from mes import live_obs as live_obs_mod  # noqa: E402
except Exception:  # noqa: BLE001 -- the map must still render without it
    live_obs_mod = None

from ..live import poller as poller_mod  # noqa: E402

try:
    from . import liveboard_bridge
except Exception:  # noqa: BLE001 -- the map's state must still render without it
    liveboard_bridge = None

try:
    from . import bench_bridge
except Exception:  # noqa: BLE001
    bench_bridge = None

try:
    from . import jobs_bridge
except Exception:  # noqa: BLE001
    jobs_bridge = None

#: The map's five-state vocabulary -- a superset of the per-code
#: ACTIVE/CLEARED_UNVERIFIED/STALE words dossier_bridge already uses, plus
#: NO_DATA (never any code) and VERIFIED_CLEAN (borrowed from the car-level
#: verdict, see system_states' docstring).
ALLOWED_STATES = ("ACTIVE", "CLEARED_UNVERIFIED", "STALE", "NO_DATA", "VERIFIED_CLEAN")

#: Same wording ``systems_mod._dep``'s own UNKNOWN-confidence note uses --
#: restated here (not imported, that note is a private module constant) so
#: an edge with no sourced confidence still names the real reason plainly.
_UNKNOWN_SOURCE = "not established in any source checked -- use the service manual (TechAuthority)"


# --- small helpers -----------------------------------------------------------

def _all_systems() -> dict[str, dict[str, Any]]:
    try:
        raw = systems_bridge.systems()
    except Exception:  # noqa: BLE001 -- a knowledge-table miss must never 500
        raw = {}
    if isinstance(raw, dict):
        return raw
    return {s.get("key"): s for s in (raw or []) if s.get("key")}


def _correlate(vin: str) -> dict[str, Any]:
    try:
        corr = systems_bridge.correlate(vin)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(corr, dict) or corr.get("error"):
        return {}
    return corr


def _dossier_view(vin: str) -> dict[str, Any]:
    try:
        dossier = mes_bridge.workup(vin=vin)
        return dossier_bridge.build_view(vin, dossier, None) or {}
    except Exception:  # noqa: BLE001
        return {}


def _workup(vin: str) -> dict[str, Any]:
    """The raw dossier dict (not the built view) -- :func:`system_states`
    alone needs this, to hand to ``dossier_bridge.readiness_panel`` for its
    own ``_clear_info`` (the last-clear timestamp readiness has to be
    newer than)."""
    try:
        return mes_bridge.workup(vin=vin) or {}
    except Exception:  # noqa: BLE001
        return {}


def _readiness_panel(vin: str, dossier: dict[str, Any]) -> dict[str, Any]:
    """``dossier_bridge.readiness_panel``, guarded -- :func:`system_states`
    alone needs this. Only ever carries a from-car (serial-stream)
    observation; see that function's own docstring."""
    try:
        return dossier_bridge.readiness_panel(vin, dossier) or {}
    except Exception:  # noqa: BLE001
        return {}


def _edge_kind(dep: dict[str, Any]) -> str:
    """"electrical supply" vs "functional" vs "UNKNOWN" -- same reading as
    ``system_detail_bridge._edge_kind``, from the edge's own
    ``technical.carries`` note, never a guess beyond that note's words."""
    if dep.get("system") == "electrical_supply":
        return "electrical supply"
    carries = ((dep.get("technical") or {}).get("carries") or "").lower()
    if any(w in carries for w in ("volt", "supply", "ground", "current", "12 v", "amp")):
        return "electrical supply"
    if carries or dep.get("why"):
        return "functional"
    return "UNKNOWN"


# --- 0. tonight's live module sweep -----------------------------------------
#
# ``module_dtcs`` observations (one per ECU per scan, see ``mes.live_obs``)
# are a second, independent evidence source from the MES log corpus
# ``system_states``/``edges`` otherwise read -- a direct from-car UDS read,
# not a workshop log file. Every reporting module reports hundreds of codes
# it merely *tracks*; only the UDS status byte says which are a fault now.

#: Reporting ECU -> the real vehicle system its own codes belong to. Needed
#: because a U-code's own ``systems_for_code`` resolution is the generic
#: "network" catch-all (any lost-communication code, regardless of which
#: module threw it) and a body/chassis B-code's SAE fallback is the equally
#: generic "body_comfort" -- neither says *which* system actually has the
#: problem. The reporting module does. P-codes are excluded from this table's
#: use (see :func:`_module_system_for`) because ``systems_for_code``'s
#: exact-code table already resolves them specifically (P0440 -> evap, not
#: ECM's own "engine_management").
_MODULE_SYSTEM: dict[str, str] = {
    "ECM": "engine_management",
    "TCM": "transmission_driveline",
    "DTCM": "transmission_driveline",
    "BCM": "body_comfort",
    "IPC": "infotainment_cluster",
    "RFHUB": "security_immobiliser",
    "ABS": "brakes_abs",
    "EPS": "steering",
    "ORC": "restraints",
    "AFLS": "lighting",
    "PAM": "adas_sensors",
    "HALF": "adas_sensors",
    "LBSS": "adas_sensors",
    "RBSS": "adas_sensors",
    "CSWM": "body_comfort",
    "CRSM": "body_comfort",
    "PLGM": "body_comfort",
    "TVM": "transmission_driveline",
    "ESL": "security_immobiliser",
}


def _module_dtc_observations(vin: str) -> list[dict[str, Any]]:
    if live_obs_mod is None:
        return []
    try:
        return live_obs_mod.load(vin, "module_dtcs")
    except Exception:  # noqa: BLE001 -- an unreadable observations file is an honest empty state
        return []


def _module_code_state(flags: dict[str, Any]) -> Optional[str]:
    """"ACTIVE" / "HISTORY" / ``None`` (never shown) from a UDS status byte's
    decoded flags.

    ``testFailed`` is the only bit that means "failing right now" --
    ``confirmedDTC``/``pendingDTC`` alone (with ``testFailed`` false) is a
    code the module once confirmed but is not currently failing: history.
    A record with none of those three set -- the overwhelming majority,
    carrying only ``testNotCompletedThisOperationCycle``/
    ``testNotCompletedSinceLastClear`` -- is a code the module merely
    tracks and has never actually found; it is never shown at all.
    """
    if flags.get("testFailed"):
        return "ACTIVE"
    if flags.get("confirmedDTC") or flags.get("pendingDTC") or flags.get("testFailedSinceLastClear"):
        return "HISTORY"
    return None


def _module_system_for(ecu: str, base: str) -> Optional[str]:
    """The system a module-reported code belongs on.

    P-codes (powertrain) use ``systems_for_code``'s own exact-code table,
    which is specific per code (P0440 -> evap) -- the reporting ECU would
    only make that worse. Every other family (U/B/C) uses the reporting
    module's own system (see ``_MODULE_SYSTEM``'s docstring) when the ECU is
    known, falling back to ``systems_for_code`` otherwise.
    """
    if not base.startswith("P"):
        mapped = _MODULE_SYSTEM.get((ecu or "").upper())
        if mapped:
            return mapped
    for entry in systems_mod.systems_for_code(base, ""):
        if entry.get("role") == "primary" and entry.get("system") not in (None, "UNKNOWN"):
            return entry["system"]
    return _MODULE_SYSTEM.get((ecu or "").upper())


def module_dtc_overlay(vin: str) -> dict[str, Any]:
    """Tonight's (or the newest) live module sweep, projected onto the
    systems graph.

    Returns ``{"by_system": {system_key: [chip, ...]}, "scan_pairs":
    {frozenset({a, b}): count}}``. Each chip: ``{"code", "full", "ecu",
    "state" ("ACTIVE"/"HISTORY"), "at", "failure_type", "chip_text"}``.
    ``scan_pairs`` counts, across every distinct scan timestamp
    (``module_dtcs`` observations sharing one ``at``), how many times two
    different systems both had a code (any state) reported in that same
    scan -- the module-sweep half of the hot-edge overlay (see
    :func:`edges`).
    """
    by_system: dict[str, list[dict[str, Any]]] = {}
    scan_systems: dict[str, set[str]] = {}
    for obs in _module_dtc_observations(vin):
        data = obs.get("data") or {}
        ecu = str(data.get("ecu") or "").upper()
        at = obs.get("at")
        for rec in data.get("dtcs") or []:
            flags = rec.get("flags") or {}
            state = _module_code_state(flags)
            if state is None:
                continue
            full = str(rec.get("code") or "")
            base = systems_mod.base_code(full)
            sys_key = _module_system_for(ecu, base)
            if not sys_key:
                continue
            ftb = full.split("-")[-1] if "-" in full else None
            try:
                ft = dtc_mod.failure_type(ftb) if ftb else None
            except Exception:  # noqa: BLE001
                ft = None
            chip_text = (f"{full} · {ecu} · failing now" if state == "ACTIVE"
                        else f"{full} · {ecu} · history since clear")
            by_system.setdefault(sys_key, []).append({
                "code": base, "full": full, "ecu": ecu, "state": state, "at": at,
                "failure_type": ft.to_dict() if ft else None, "chip_text": chip_text,
            })
            if at:
                scan_systems.setdefault(at, set()).add(sys_key)

    scan_pairs: dict[frozenset, int] = {}
    for sys_keys in scan_systems.values():
        keys = sorted(sys_keys)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                pair = frozenset((a, b))
                scan_pairs[pair] = scan_pairs.get(pair, 0) + 1
    return {"by_system": by_system, "scan_pairs": scan_pairs}


def _latest_scan_coverage(vin: str) -> Optional[dict[str, Any]]:
    if live_obs_mod is None:
        return None
    try:
        obs = live_obs_mod.load(vin, "scan_coverage")
    except Exception:  # noqa: BLE001
        return None
    return live_obs_mod.newest(obs)


def module_coverage(vin: str) -> dict[str, dict[str, Any]]:
    """system key -> ``{"reachable": False, "why": ..., "module": ...}`` for
    every system whose module was reported ``not_reachable`` in the newest
    ``scan_coverage`` observation. A system every one of whose modules was
    actually read (or that has no entry in ``_MODULE_SYSTEM`` at all) is
    simply absent from this dict -- never asserted "clean" here, the map
    just has nothing to grey out for it.

    A system that already carries a real module-sweep chip (see
    :func:`module_dtc_overlay`) is excluded even if a *later* coverage
    attempt could not reach it -- a cable swap or a dropped serial link
    between scans must never grey out a cell the car already answered for
    tonight.
    """
    obs = _latest_scan_coverage(vin)
    if not obs:
        return {}
    data = obs.get("data") or {}
    had_live_data = set(module_dtc_overlay(vin)["by_system"])
    out: dict[str, dict[str, Any]] = {}
    for row in data.get("coverage") or []:
        if row.get("category") != "not_reachable":
            continue
        module = str(row.get("module") or "").upper()
        sys_key = _MODULE_SYSTEM.get(module)
        if not sys_key or sys_key in out or sys_key in had_live_data:
            continue
        out[sys_key] = {"reachable": False, "why": row.get("why") or "not reachable",
                        "module": module, "bus": row.get("bus")}
    return out


# --- 1. per-system state -------------------------------------------------------

def system_states(vin: str) -> dict[str, dict[str, Any]]:
    """Every system key (even one with zero data for this VIN) ->
    ``{state, open_code_count, codes}``. ``codes`` is the list of base DTCs
    this VIN's corpus assigns to the system as a primary (see
    ``systems_bridge.correlate``'s own ``by_system`` rows).

    ``VERIFIED_CLEAN`` is never derived from the whole-car verdict (see
    this module's own docstring) -- only from this system's own monitor,
    read from the car, since the clear."""
    all_systems = _all_systems()
    corr = _correlate(vin)
    by_system = {r.get("system"): r for r in (corr.get("by_system") or [])}
    view = _dossier_view(vin)
    dossier_codes = {r.get("code"): r for r in (view.get("codes") or [])}

    dossier = _workup(vin)
    panel = _readiness_panel(vin, dossier)
    # readiness_panel() only ever returns a from-car (serial-stream)
    # observation -- "at" is set only when one exists, so this is also the
    # "was this reading actually taken from the car" check a demo/replay
    # source can never satisfy.
    readiness_from_car = bool(panel.get("at"))
    panel_monitors = {m.get("name"): bool(m.get("complete"))
                      for m in (panel.get("monitors") or []) if m.get("name")}

    out: dict[str, dict[str, Any]] = {}
    for key in all_systems:
        row = by_system.get(key) or {}
        statuses: list[str] = []
        codes_out: list[str] = []
        for full in row.get("codes") or []:
            base = systems_mod.base_code(full)
            codes_out.append(base)
            drow = dossier_codes.get(base) or {}
            statuses.append(drow.get("status") or "STALE")

        if "ACTIVE" in statuses:
            state = "ACTIVE"
        elif "CLEARED_UNVERIFIED" in statuses:
            state = "CLEARED_UNVERIFIED"
            if readiness_from_car:
                monitor_names = systems_mod.monitors_for_system(key)
                seen = [panel_monitors[n] for n in monitor_names if n in panel_monitors]
                if seen and all(seen):
                    state = "VERIFIED_CLEAN"
        elif "STALE" in statuses:
            state = "STALE"
        else:
            state = "NO_DATA"

        out[key] = {
            "state": state,
            "open_code_count": sum(1 for s in statuses if s in ("ACTIVE", "CLEARED_UNVERIFIED")),
            "codes": codes_out,
        }

    # tonight's (or newest) live module sweep: an independent from-car read,
    # never folded into "codes"/"open_code_count" above (those stay the
    # corpus-sourced counts other callers already rely on) -- carried
    # separately as "module_codes" chips. An ACTIVE module code always wins
    # the cell's colour; a HISTORY-only one never promotes NO_DATA past
    # CLEARED_UNVERIFIED (still honest that it is not currently failing).
    overlay = module_dtc_overlay(vin)
    for key, chips in overlay["by_system"].items():
        row = out.setdefault(key, {"state": "NO_DATA", "open_code_count": 0, "codes": []})
        row["module_codes"] = chips
        if any(c["state"] == "ACTIVE" for c in chips):
            row["state"] = "ACTIVE"
        elif row["state"] == "NO_DATA" and any(c["state"] == "HISTORY" for c in chips):
            row["state"] = "CLEARED_UNVERIFIED"
    for key, row in out.items():
        row.setdefault("module_codes", [])
    return out


# --- 2. edges ------------------------------------------------------------------

def edges(vin: str) -> list[dict[str, Any]]:
    """Every dependency edge from the systems graph, plus every corpus
    co-occurrence pair with no matching dependency edge -- each carrying
    ``lift``/``sessions_together`` (0/None with no corpus evidence) and
    ``confidence``/``source``/``kind``. No prose ``why`` field: nothing here
    is ever worded "depends on"."""
    all_systems = _all_systems()
    corr = _correlate(vin)
    co_by_pair: dict[frozenset, dict[str, Any]] = {}
    for row in corr.get("co_occurrence") or []:
        a, b = row.get("a"), row.get("b")
        if a and b:
            co_by_pair[frozenset((a, b))] = row

    out: list[dict[str, Any]] = []
    seen_pairs: set[frozenset] = set()

    for a_key, rec in all_systems.items():
        for dep in rec.get("depends_on") or []:
            b_key = dep.get("system")
            if not b_key:
                continue
            pair = frozenset((a_key, b_key))
            co = co_by_pair.get(pair)
            out.append({
                "a": a_key, "b": b_key,
                "lift": co.get("lift") if co else None,
                "sessions_together": co.get("sessions_together") if co else 0,
                "confidence": (dep.get("confidence") or "UNKNOWN").upper(),
                "source": dep.get("source") or _UNKNOWN_SOURCE,
                "kind": _edge_kind(dep),
            })
            seen_pairs.add(pair)

    for pair, row in co_by_pair.items():
        if pair in seen_pairs:
            continue
        out.append({
            "a": row.get("a"), "b": row.get("b"),
            "lift": row.get("lift"),
            "sessions_together": row.get("sessions_together") or 0,
            "confidence": "UNKNOWN",
            "source": "corpus co-occurrence, this VIN only -- not a dependency",
            "kind": "co-occurrence",
        })
        seen_pairs.add(pair)

    # tonight's (or newest) live module sweep: two systems whose modules
    # both reported a code (any state) in the same scan window count as a
    # hot edge too -- "seen together on this car", same wording and the
    # same sessions_together-counts-as-hot convention the corpus
    # co-occurrence edges above already use, just counting scans instead of
    # MES log files.
    scan_pairs = module_dtc_overlay(vin)["scan_pairs"]
    by_pair_in_out: dict[frozenset, dict[str, Any]] = {
        frozenset((e["a"], e["b"])): e for e in out if e.get("a") and e.get("b")
    }
    for pair, count in scan_pairs.items():
        a, b = tuple(pair) if len(pair) == 2 else (next(iter(pair)), next(iter(pair)))
        existing = by_pair_in_out.get(pair)
        if existing is not None:
            existing["sessions_together"] = (existing.get("sessions_together") or 0) + count
        else:
            out.append({
                "a": a, "b": b, "lift": None, "sessions_together": count,
                "confidence": "UNKNOWN",
                "source": "seen together on this car (module sweep), this VIN only -- not a dependency",
                "kind": "co-occurrence",
            })
            by_pair_in_out[pair] = out[-1]
    return out


# --- 3. session timeline --------------------------------------------------------

def sessions(vin: str) -> list[dict[str, Any]]:
    """One row per session (MES log file) this VIN's corpus has, ordered by
    time: ``{id, when, systems_fired}``. Rebuilt from the same inputs
    ``mes.systems.correlate`` uses for its own internal ``session_systems``
    (that function never returns the per-session shape, only aggregates)."""
    try:
        history = analysis_mod.dtc_history(vin=vin)
    except Exception:  # noqa: BLE001
        history = {}
    if not history:
        return []

    session_codes: dict[str, set[str]] = {}
    session_when: dict[str, str] = {}
    for code, rec in history.items():
        for occ in rec.occurrences:
            fname = occ.get("file")
            if not fname:
                continue
            session_codes.setdefault(fname, set()).add(code)
            ts = occ.get("timestamp")
            if ts and (fname not in session_when or ts < session_when[fname]):
                session_when[fname] = ts

    rows: list[dict[str, Any]] = []
    for fname, codes in session_codes.items():
        fired: set[str] = set()
        for code in codes:
            descr = (history[code].descriptions or [""])[0]
            for entry in systems_mod.systems_for_code(code, descr):
                if entry.get("role") == "primary" and entry.get("system") != "UNKNOWN":
                    fired.add(entry["system"])
        rows.append({"id": fname, "when": session_when.get(fname),
                     "systems_fired": sorted(fired)})
    rows.sort(key=lambda r: r.get("when") or "")
    return rows


# --- the whole view model -------------------------------------------------------

def build_state(vin: str) -> dict[str, Any]:
    """Everything ``GET /api/systems/{vin}/state`` returns."""
    return {"systems": system_states(vin), "edges": edges(vin), "sessions": sessions(vin),
           "coverage": module_coverage(vin)}


# ===========================================================================
# 4. live overlay -- Phase 4 (GET /api/systems/{vin}/live)
# ===========================================================================
#
# Everything below reuses the Live board's own wiring instead of growing a
# second one: ``liveboard_bridge.evaluate``'s ok/moderate/excessive/unknown
# vocabulary for the grade, ``liveboard_bridge.channel_system`` for which
# system a channel belongs to (``mes.systems.SYSTEMS[*]["live_channels"]``,
# first system to claim a channel wins -- never re-decided here), and the
# process-wide ``cuore.live.poller`` the Live board's own SSE route already
# reads. ``"none"`` is this overlay's own word, not the Live board's --
# the Live board itself only ever renders while a session is already
# active, so it never needed a "nothing to grade" grade.

#: Same ranking the Live board itself piles excessive-first with
#: (``liveboard_bridge._LEVEL_ORDER``), restated here (not imported, that
#: ordering is a private module constant) plus "none" ranked last of all --
#: no live session beats "unknown", it's simply not graded.
_LIVE_GRADE_RANK: dict[str, int] = {"excessive": 0, "moderate": 1, "unknown": 2,
                                    "ok": 3, "none": 4}


def _live_channels_by_system() -> dict[str, list[str]]:
    """system key -> the ``can_c`` live channel ids it owns, the same
    first-claim ownership :func:`liveboard_bridge.channel_system` already
    decides -- grouped the other way round, never re-decided here."""
    out: dict[str, list[str]] = {}
    if liveboard_bridge is None:
        return out
    try:
        from ..live import channels as channels_mod
        channels = [c.id for c in channels_mod.available_channels() if c.bus == "can_c"]
    except Exception:  # noqa: BLE001
        return out
    for cid in channels:
        sys_key = liveboard_bridge.channel_system(cid)
        if sys_key:
            out.setdefault(sys_key, []).append(cid)
    return out


def _scanner_label(active: bool) -> str:
    """"Scanner: Connected" / "Scanner: Not running" -- the same human
    vocabulary ``cuore.services.bench_bridge.LABELS["mes_state"]`` already
    speaks for the live strip elsewhere on this app, never a new word
    invented for this overlay. ``active`` is the live poller's own
    ``is_active()`` -- a live-data session genuinely polling the car, not
    the (distinct) MultiEcuScan-connected state ``bench_bridge`` itself
    tracks."""
    labels = bench_bridge.LABELS["mes_state"] if bench_bridge else {}
    key = "connected" if active else "not_running"
    return f"Scanner: {labels.get(key, 'Unknown')}"


def _on_new_live_codes(vin: str) -> None:
    """A brand-new live code never writes to the car -- it only wakes the
    two other surfaces so Bench, Job and Systems agree on it:

    * the Job page's own suggestion pipeline
      (:func:`cuore.services.jobs_bridge.suggested_hypotheses`) is called
      here, not re-implemented -- it is already what builds the hypothesis
      ledger's suggested cards from this car's current dossier view, so
      calling it is what "wakes" that ledger rather than a parallel
      DTC-to-hypothesis builder living in this module too.
    * :func:`cuore.services.bench_bridge.regenerate_for_live_codes` drops
      Bench's small memo cache so its next-action is rebuilt rather than
      served stale.

    Best-effort only: a hiccup in either must never break
    ``GET /api/systems/{vin}/live`` itself.
    """
    try:
        if jobs_bridge is not None:
            jobs_bridge.suggested_hypotheses(vin, _dossier_view(vin))
    except Exception:  # noqa: BLE001
        pass
    try:
        if bench_bridge is not None:
            bench_bridge.regenerate_for_live_codes(vin)
    except Exception:  # noqa: BLE001
        pass


def new_live_codes(vin: str) -> list[dict[str, Any]]:
    """DTCs the live poller's Monitor-DTCs read (Mode 03/07) currently
    carries that this VIN's own :func:`system_states` does not carry yet --
    i.e. a code the car just threw, before any MES log backs it.

    Each entry: ``{"code", "systems" (the mes.systems primary-role systems
    for that code), "since" (the poller's own ``dtc_snapshot()``
    first-seen timestamp for it, this session)}``. Never reports the same
    code twice across calls within one "new" window is not tracked here --
    a code already present in :func:`system_states` (true once the car's
    own corpus/dossier has picked it up) simply stops qualifying as new.

    Calling this (whenever it finds anything) also runs
    :func:`_on_new_live_codes` once per call with results -- see that
    function's own docstring.
    """
    poller = poller_mod.poller()
    live = poller.dtc_snapshot()
    codes = live.get("codes") or []
    if not codes:
        return []

    known: set[str] = set()
    for row in system_states(vin).values():
        known.update(row.get("codes") or [])

    first_seen = live.get("first_seen") or {}
    now_iso = datetime.now().isoformat(timespec="seconds")
    out: list[dict[str, Any]] = []
    seen_here: set[str] = set()
    for code in codes:
        base = systems_mod.base_code(code)
        if base in known or base in seen_here:
            continue
        seen_here.add(base)
        systems_hit = sorted({
            e["system"] for e in systems_mod.systems_for_code(base, "")
            if e.get("role") == "primary" and e.get("system") not in (None, "UNKNOWN")
        })
        out.append({"code": base, "systems": systems_hit,
                   "since": first_seen.get(code) or now_iso})

    if out:
        _on_new_live_codes(vin)
    return out


def live_state(vin: str) -> dict[str, Any]:
    """``GET /api/systems/{vin}/live``'s whole body: an honest scanner
    status, every system key's worst live colour grade (plus the value/
    unit/channel backing that grade), and any brand-new DTC the live
    poller has just seen (see :func:`new_live_codes`).

    No live session running: every system grades ``"none"`` and
    ``scanner`` names it plainly (:func:`_scanner_label`) -- never a
    fabricated "ok".
    """
    poller = poller_mod.poller()
    active = poller.is_active()
    scanner = _scanner_label(active)

    all_systems = _all_systems()
    by_system = _live_channels_by_system()
    systems_out: dict[str, dict[str, Any]] = {}

    snap_channels: dict[str, Any] = {}
    if active and liveboard_bridge is not None:
        snap_channels = poller.snapshot().get("channels", {})

    for key in all_systems:
        best: tuple[int, str, str, Any, str] | None = None
        if active and liveboard_bridge is not None:
            for cid in by_system.get(key, []):
                row = snap_channels.get(cid)
                if row is None or row.get("value") is None:
                    continue
                ev = liveboard_bridge.evaluate(cid, row["value"])
                rank = _LIVE_GRADE_RANK.get(ev["level"], 9)
                if best is None or rank < best[0]:
                    best = (rank, ev["level"], cid, row["value"], row.get("unit", ""))
        if best is None:
            systems_out[key] = {"grade": "none", "value": None, "unit": None, "channel": None}
        else:
            _, grade, cid, value, unit = best
            systems_out[key] = {"grade": grade, "value": value, "unit": unit, "channel": cid}

    new_codes = new_live_codes(vin) if active else []

    return {"active": active, "scanner": scanner, "systems": systems_out,
            "new_codes": new_codes}


__all__ = ["ALLOWED_STATES", "system_states", "edges", "sessions", "build_state",
          "new_live_codes", "live_state", "module_dtc_overlay", "module_coverage"]
