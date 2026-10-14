"""MES handoff: the parts of a diagnosis CUORE deliberately never does over
HTTP (an actuator command, an adjustment, a coding write) because CUORE
never writes to the car outside the consent-gated MCP path. For those, this
module hands the technician a card -- "do this in MES: module, menu path,
prerequisites" -- built from the sourced knowledge table in
:mod:`mes.mes_functions`.

Two things live here, both additive and read-mostly:

1. **Handoff lookup** (:func:`candidates`, :func:`find_for_text`,
  :func:`card`) -- the Tests page and the job page's step 6 already have a
  pass/fail or done/outcome form for recording what happened; this module
  never duplicates that store (:mod:`cuore.live.checklists`). It only
  supplies the "what to do in MES first" text those existing forms sit
  below, matched against a test id or free-text step label.

2. **MES log import** (:func:`import_mes_log`, :func:`list_mes_scans`) --
  point 4 of the 2026-10-14 pass: an MES SCAN/FES log that was captured
  outside CUORE's own live link (``cuore.live.scanlog``, which only ever
  clusters ``observations.jsonl`` -- an append-only record of what CUORE's
  own serial link actually read, never edited here) should still get a
  health report. Rather than disguise an MES-captured file as a live serial
  read (which ``cuore.live.store.is_from_car`` -- rightly -- would reject,
  and which would be dishonest about provenance even if it didn't), this
  keeps its own small, clearly-labelled ledger of MES-sourced scans
  (``mes_imports.json`` beside the other small JSON stores in
  :mod:`cuore.live.config`'s state dir) and computes the same verdict
  :mod:`mes.scan_health` would compute for a live one, via that module's
  own public :func:`mes.scan_health.verdict` -- never a second copy of its
  logic, and never a write to ``cuore.live.scanlog``'s or
  ``cuore.services.scan_health_bridge``'s own files.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live.config import state_dir
from .errors import BadRequest, NotFound

from mes import mes_functions  # noqa: E402
from mes import paths as mes_paths  # noqa: E402
from mes import scan as scan_mod  # noqa: E402
from mes import scan_health  # noqa: E402

try:
    from mes import fes as fes_mod  # noqa: E402
except Exception:  # noqa: BLE001 -- FES import is a nice-to-have, not required
    fes_mod = None

_LOCK = threading.Lock()


# ===========================================================================
# 1. Handoff cards
# ===========================================================================

def candidates() -> list[dict[str, Any]]:
    """Every catalogued MES function, as full handoff cards plus the
    ``test_id`` cross-reference (when it has one). Small (well under 30
    rows) -- the Tests page and job page fetch this once and match
    client-side against the test id / step text already in the DOM
    (``_mes_handoff.html``'s own script), rather than round-tripping once
    per row/step."""
    return [{**_render_card(f), "test_id": f["test_id"]}
           for f in mes_functions.all_functions()]


def card(function_id: str) -> dict[str, Any]:
    """The full handoff card for one function id. Raises :class:`NotFound`
    for an unknown id."""
    f = mes_functions.function(function_id)
    if f is None:
        raise NotFound(f"unknown MES function id {function_id!r}")
    return _render_card(f)


def _render_card(f: dict[str, Any]) -> dict[str, Any]:
    native = f["mes_support"].startswith("no")
    return {
        "id": f["id"],
        "title": f"Do this in {'the car' if native else 'MES'}: "
                f"{f['module']} -> {f['menu_path'].split(' -- ')[0]}",
        "module": f["module"],
        "kind": f["kind"],
        "name": f["name"],
        "menu_path": f["menu_path"],
        "cable": f["cable"],
        "prerequisites": f["prerequisites"],
        "record_after": f["record_after"],
        "log_expected": f["log_expected"],
        "mes_support": f["mes_support"],
        "cuore_today": f["cuore_today"],
        "source": f["source"],
        "confidence": f["confidence"],
        "notes": f["notes"],
        #: Never true for a handoff card -- restated here (not just in the
        #: docstring) so a client can assert on it directly.
        "writes_to_car": False,
    }


def find_for_test(test_id: str) -> Optional[dict[str, Any]]:
    """The handoff card for a mechanic-test catalogue id (``tests.html``'s
    own ``t.id``), or ``None`` when that test has no MES-only counterpart."""
    hits = mes_functions.functions_for_test(test_id)
    return _render_card(hits[0]) if hits else None


def find_for_text(text: str) -> Optional[dict[str, Any]]:
    """The handoff card matching a free-text job step label (``job.html``'s
    checklist step text), or ``None``. First match wins -- the knowledge
    table has no two functions with overlapping names."""
    hits = mes_functions.search(text)
    return _render_card(hits[0]) if hits else None


# ===========================================================================
# 2. MES log import -> a "Scans" entry CUORE didn't capture live
# ===========================================================================

def _ledger_path() -> Path:
    return state_dir() / "mes_imports.json"


def _load_ledger() -> dict[str, Any]:
    try:
        return json.loads(_ledger_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_ledger(data: dict[str, Any]) -> None:
    try:
        _ledger_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _resolve_import(name: str) -> Path:
    try:
        return mes_paths.resolve_log(name)
    except Exception as exc:  # noqa: BLE001 -- MesNotFound/MesPathError -> BadRequest
        raise BadRequest(str(exc)) from exc


def _dtc_codes(dtcs: list[Any]) -> list[str]:
    return [d.full for d in dtcs]


def _scan_from_log(name: str, path: Path) -> dict[str, Any]:
    """A scan-shaped dict (same spirit as ``cuore.live.scanlog``'s own
    cluster shape -- id/vin/ecus/dtcs/source -- but built from a parsed MES
    file, never from ``observations.jsonl``) plus this scan's health
    verdict, computed via :func:`mes.scan_health.verdict` (that module's own
    public function, called -- never re-implemented)."""
    kind, raw_ts, _vehicle = mes_paths.classify_name(name)
    if kind == "scan":
        log = scan_mod.load_scan(path)
        vin = log.vin
        ecus = sorted({e.iso_code or e.name for e in log.modules})
        stored_codes = _dtc_codes(log.all_dtcs)
        simulation_note = log.provenance
    elif kind == "fes" and fes_mod is not None:
        log = fes_mod.load_fes(path)
        vin = log.vin
        ecus = sorted({n for _k, n in log.nodes}) or ([log.ecu_description]
                                                      if log.ecu_description else [])
        stored_codes = _dtc_codes(log.stored)
        simulation_note = ("simulation" if log.simulation else "not flagged "
                           "as a simulation")
    else:
        raise BadRequest(f"{name!r} is not a recognised MES SCAN/FES log name")

    verdict = scan_health.verdict(stored=stored_codes)
    scan_id = f"{'SCAN' if kind == 'scan' else 'FES'}_{raw_ts or 'import'}"
    return {
        "id": scan_id,
        "vin": vin,
        "ecus": ecus,
        "dtcs": {"stored": stored_codes, "pending": [], "permanent": []},
        "source": {"kind": "MES", "file": name, "provenance": simulation_note},
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "health": verdict,
    }


def import_mes_log(vin: str, name: str) -> dict[str, Any]:
    """Parse an MES SCAN/FES log already on one of ``mes.paths``'s
    configured roots (the catalogue "already rescans" -- this just reads
    the one file named, the same containment-safe way every other MES log
    read in this repo does, via :func:`mes.paths.resolve_log`) and record
    it as a "Scans timeline" entry tagged ``source: "MES"``, with the same
    health verdict a CUORE live scan would get.

    Raises :class:`BadRequest` for a VIN mismatch (never silently files an
    import under the wrong car) or an unrecognised log name/kind.
    """
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    path = _resolve_import(name)
    scan = _scan_from_log(name, path)
    if scan["vin"] and scan["vin"] != vin:
        raise BadRequest(f"{name!r} is for VIN {scan['vin']!r}, not {vin!r}")
    scan["vin"] = vin
    with _LOCK:
        data = _load_ledger()
        entries = data.setdefault(vin, [])
        entries = [e for e in entries if e["id"] != scan["id"]]  # re-import replaces
        entries.append(scan)
        entries.sort(key=lambda e: e.get("imported_at") or "", reverse=True)
        data[vin] = entries
        _save_ledger(data)
    return scan


def list_mes_scans(vin: str) -> list[dict[str, Any]]:
    """Every MES-imported scan on file for this VIN, newest first -- the
    "Scans timeline, source MES" surface this pass adds. Additive to (never
    merged into) ``cuore.live.scanlog.list_scans``, which stays exactly what
    it has always been: CUORE's own live-link history."""
    vin = (vin or "").strip()
    if not vin:
        return []
    with _LOCK:
        return list(_load_ledger().get(vin, []))


def health_line(scan: dict[str, Any]) -> str:
    """One printable line for a handoff card's "Import the MES log" result
    -- ``build_verdict``'s own label plus its first basis sentence."""
    v = scan.get("health") or {}
    basis = v.get("basis") or []
    label = v.get("label") or "no verdict"
    return f"{label}: {basis[0]}" if basis else label


__all__ = ["candidates", "card", "find_for_test", "find_for_text",
          "import_mes_log", "list_mes_scans", "health_line"]
