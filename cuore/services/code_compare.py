"""Stored codes, CUORE read against MES log, per module (section of ``/v/{vin}/parity``).

Pure comparison over two lists of reads, plus two thin loaders. Reads only files on disk (CUORE's
``module_dtcs`` observations from a real serial link, and MES's own log files); nothing contacts the car.

Rule: a module is MATCHED only when a CUORE read and a MES read are at most :data:`WINDOW_S` seconds
apart AND list the same codes. Same window, different codes: DIFFERENT. Anything else, NOT COMPARED, with
the reason (and the codes of the nearest pair, labelled as no match). A MES read that a MES clear
erased cannot be compared with a CUORE read taken after MES opened that session.

CUORE "stored" = the UDS status byte has testFailed, pending, confirmed or testFailedSinceLastClear
(``coverage.ACTIVE_MASK | HISTORY_BIT``); a 19 02 FF reply also lists every code the module only
tracks (status 0x40, not tested), which is not a fault and which MES does not print.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- puts `mes` on sys.path
from ..live import coverage, read_state, store
from . import modules_bridge

from mes import catalog, dtc as mes_dtc, fes, scan  # noqa: E402

WINDOW_S = 300
STORED_MASK = coverage.ACTIVE_MASK | coverage.HISTORY_BIT


def _dt(v: Any) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def cuore_reads(vin: str) -> list[dict[str, Any]]:
    """Every answered ``module_dtcs`` read from the car for ``vin``: ``{module, at, codes, tracked}``."""
    out = []
    for o in store.recent_observations(n=2000, vin=vin, kind="module_dtcs"):
        d = o.get("data") or {}
        at = _dt(o.get("at"))
        if not at or not store.is_from_car(o) or not read_state.is_read(d) or d.get("dtcs") is None:
            continue
        recs = d["dtcs"]
        out.append({"module": str(d.get("ecu") or "").upper(), "at": at, "tracked": len(recs),
                    "codes": {r["code"] for r in recs if int(r.get("status") or 0) & STORED_MASK}})
    return out


def mes_reads(vin: str) -> list[dict[str, Any]]:
    """Stored-code reads in MES's own logs for ``vin`` (not simulation, not CUORE's own exports):
    ``{module, start, end, codes, source, cleared}``. ``start``..``end`` is when the read happened:
    SCAN logs only carry the file stamp (a point); an engineering log has its session start and its
    save stamp. ``cleared``: the log erased codes after reading them."""
    entries = [e for e in catalog.CATALOG.select(vin=vin) if not e.provenance and e.stamp]
    loaded = []
    iso_to_mod: dict[str, str] = {}
    for e in entries:
        try:
            if e.kind == "scan":
                log = scan.load_scan(e.path, timestamp=e.timestamp)
                for m in log.modules:
                    mod = modules_bridge._resolve_module(m.abbrev)
                    if mod and m.iso_code:
                        iso_to_mod[m.iso_code] = mod
            elif e.kind == "fes":
                log = fes.load_fes(e.path, timestamp=e.timestamp)
            else:
                continue
        except Exception:  # noqa: BLE001 -- one unreadable log must not hide the rest
            continue
        loaded.append((e, log))
    out = []
    for e, log in loaded:
        if e.kind == "scan":
            cleared = bool(log.clear_results)
            for m in log.modules:
                mod = modules_bridge._resolve_module(m.abbrev)
                if mod:
                    out.append({"module": mod, "start": e.stamp, "end": e.stamp, "source": e.name,
                                "codes": {d.full for d in m.dtcs}, "cleared": cleared})
        else:
            if not log.read_sections:
                continue
            iso = log.head("ECU ISO code")
            mod = iso_to_mod.get(iso) or modules_bridge._resolve_module(log.ecu_description)
            if not mod:
                continue
            start = _dt(log.session_time) or e.stamp
            out.append({"module": mod, "start": min(start, e.stamp), "end": max(start, e.stamp),
                        "source": e.name, "cleared": log.clear_events > 0,
                        "codes": {d.full for d in log.dtcs
                                  if d.status in (mes_dtc.DtcStatus.STORED, mes_dtc.DtcStatus.CLEARED)}})
    return out


def _gap_s(at: datetime, start: datetime, end: datetime) -> float:
    if at < start:
        return (start - at).total_seconds()
    return max(0.0, (at - end).total_seconds())


def _t(d: datetime) -> str:
    return d.isoformat(sep=" ", timespec="seconds")


def compare_reads(cuore: list[dict[str, Any]], mes: list[dict[str, Any]],
                  window_s: int = WINDOW_S) -> dict[str, Any]:
    """Pure: per module, the closest CUORE/MES pair and its verdict."""
    rows = []
    for mod in sorted({r["module"] for r in cuore} | {r["module"] for r in mes}):
        cs = [r for r in cuore if r["module"] == mod]
        ms = [r for r in mes if r["module"] == mod]
        row: dict[str, Any] = {"module": mod, "status": "NOT COMPARED", "why": "",
                               "both": [], "cuore_only": [], "mes_only": [],
                               "cuore_at": None, "mes_at": None, "mes_source": "", "gap_s": None}
        if not cs:
            row["why"] = "CUORE has no answered code read of this module"
        elif not ms:
            row["why"] = "no MES log of this module for this car"
            row["cuore_at"] = _t(max(r["at"] for r in cs))
        else:
            pairs = [(_gap_s(c["at"], m["start"], m["end"]), c, m) for c in cs for m in ms
                     if not (m["cleared"] and c["at"] > m["start"])]
            if not pairs:
                row["why"] = "every MES log of this module erased its codes (clear) after it opened, so a later CUORE read cannot match it"
            else:
                gap, c, m = min(pairs, key=lambda p: p[0])
                row.update(cuore_at=_t(c["at"]), mes_at=_t(m["start"]) if m["start"] == m["end"]
                           else f"{_t(m['start'])} to {_t(m['end'])}", mes_source=m["source"], gap_s=int(gap),
                           both=sorted(c["codes"] & m["codes"]), cuore_only=sorted(c["codes"] - m["codes"]),
                           mes_only=sorted(m["codes"] - c["codes"]))
                if gap > window_s:
                    row["why"] = (f"nearest pair is {gap / 60:.1f} min apart (limit {window_s // 60} min); "
                                  "the lists shown are not a match")
                elif row["cuore_only"] or row["mes_only"]:
                    row["status"] = "DIFFERENT"
                else:
                    row["status"] = "MATCHED"
        rows.append(row)
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("MATCHED", "DIFFERENT", "NOT COMPARED")}
    return {"window_s": window_s, "modules": rows, "counts": counts,
            "basis": "CUORE stored = status testFailed, pending, confirmed or failed since clear; "
                     "MES = codes it printed. MATCHED needs both reads within "
                     f"{window_s // 60} minutes and the same codes."}


def compare(vin: str, window_s: int = WINDOW_S) -> dict[str, Any]:
    return compare_reads(cuore_reads(vin), mes_reads(vin), window_s)
