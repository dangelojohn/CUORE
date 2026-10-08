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
  already groups that code under. ``VERIFIED_CLEAN`` borrows the whole-car
  verdict (``dossier_bridge.build_view``'s own ``verdict.state``) only when
  a system's own open codes are all CLEARED_UNVERIFIED and the car-level
  verdict already reports a monitor-confirmed clean; ``NO_DATA`` is a
  system with no codes in this car's corpus at all.
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

from typing import Any

from .. import bootstrap  # noqa: F401 -- side effect: puts `mes` on sys.path

from . import dossier_bridge, mes_bridge, systems_bridge

from mes import analysis as analysis_mod  # noqa: E402
from mes import systems as systems_mod  # noqa: E402

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


# --- 1. per-system state -------------------------------------------------------

def system_states(vin: str) -> dict[str, dict[str, Any]]:
    """Every system key (even one with zero data for this VIN) ->
    ``{state, open_code_count, codes}``. ``codes`` is the list of base DTCs
    this VIN's corpus assigns to the system as a primary (see
    ``systems_bridge.correlate``'s own ``by_system`` rows)."""
    all_systems = _all_systems()
    corr = _correlate(vin)
    by_system = {r.get("system"): r for r in (corr.get("by_system") or [])}
    view = _dossier_view(vin)
    dossier_codes = {r.get("code"): r for r in (view.get("codes") or [])}
    verdict_state = (view.get("verdict") or {}).get("state")

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
            state = "VERIFIED_CLEAN" if verdict_state == "VERIFIED_CLEAN" else "CLEARED_UNVERIFIED"
        elif "STALE" in statuses:
            state = "STALE"
        else:
            state = "NO_DATA"

        out[key] = {
            "state": state,
            "open_code_count": sum(1 for s in statuses if s in ("ACTIVE", "CLEARED_UNVERIFIED")),
            "codes": codes_out,
        }
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
    return {"systems": system_states(vin), "edges": edges(vin), "sessions": sessions(vin)}


__all__ = ["ALLOWED_STATES", "system_states", "edges", "sessions", "build_state"]
