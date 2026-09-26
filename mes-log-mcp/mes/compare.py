"""Live vs log: one row per code, for one vehicle.

Two evidence sources describe the same car and routinely disagree, because
they are taken at different times relative to the last clear:

* **The log corpus** (``mes.scan`` / ``mes.fes``) -- what MultiEcuScan last
  read from each module, on its own schedule.
* **Live observations** (``mes.live_obs``) -- what the cuore live link last
  read over UDS, on a different schedule, filtered to real serial-link reads
  only (see :func:`mes.live_obs.from_car`).

A code can be active live and absent from the newest log (set since the last
scan), present in the log and gone live (erased by a clear, or intermittent;
never read as passed without the status byte),
or -- the trap -- present in BOTH readings while both predate the newest
clear, in which case neither one describes the car as it is now. This module
does that join once, per module, per code, so the answer to "what does the
car actually have right now" does not require mentally cross-referencing two
tools by hand.

Module identity is the hard part. A SCAN log prints the MES abbreviation
("Engine / ECM"); a FES log prints the ECU's hardware name ("Magneti Marelli
IAW 10JA CF6/EOBD Injection (2.0)"); live observations use the same short
codes cuore addresses over UDS (ECM, TCM, BCM, IPC, RFHUB, DASM, ABS, ...).
:func:`_canon_module` and :func:`_module_for_fes_ecu` normalise the first two
onto the third's vocabulary, using :mod:`mes.modules` for the abbreviation
case and a corpus-grounded keyword table (cross-checked against cuore's own
``cuore/live/addressing.py`` ECU registry) for the FES hardware-name case.
"""

from __future__ import annotations

from typing import Any

from . import fes as fes_mod
from . import live_obs
from . import modules as modules_mod
from . import scan as scan_mod
from .catalog import CATALOG
from .verdict import _last_clear

#: DTC statuses that mean "present at the end of that log's session". A code
#: whose last recorded status in a FES session is CLEARED was erased and never
#: came back -- it is not present, whatever earlier read sections said.
_PRESENT_STATUSES = {"stored", "returned", "uncleared"}

#: FES logs print the ECU's hardware/marketing name, not its MES abbreviation.
#: Transcribed from this shop's own corpus (``mes.vehicles()`` for this VIN)
#: and cross-checked against cuore's ``cuore/live/addressing.py`` ECU
#: registry. Matched by keyword, not exact string, so a different hardware
#: revision of the same module ("10JA" vs another calibration) still resolves.
_FES_ECU_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("magneti marelli iaw", "ECM"),
    ("body computer", "BCM"),
    ("transfer case", "DTCM"),
    ("gear shift module", "ESM"),
    ("automatic gearbox", "TCM"),
    ("continental abs", "ABS"),
    ("radio frequency hub", "RFHUB"),
    ("instrument panel", "IPC"),
    ("driver assistant system module (dasm)", "DASM"),
    ("driver assistance radar", "DASM"),
)


def _canon_module(name: str) -> str:
    """Resolve a SCAN abbreviation (or anything already code-shaped) to a code."""
    if not name or not name.strip():
        return ""
    code = modules_mod.normalize_abbrev(name)
    return code or name.strip().upper()


def _module_for_fes_ecu(ecu_description: str) -> str:
    """Resolve a FES ``ecu_description`` string to the same code space."""
    low = (ecu_description or "").lower()
    for key, code in _FES_ECU_KEYWORDS:
        if key in low:
            return code
    return (ecu_description or "").strip().upper() or "UNKNOWN"


def _log_picture(vin: str) -> dict[str, dict[str, Any]]:
    """Newest log read per module: ``{module_code: {file, at, codes}}``.

    ``codes`` maps a full DTC (``P0456-00``) to the status that session last
    recorded for it. Entries are visited newest-first and recorded once, so
    each module ends up with exactly the single newest session that read it
    -- the same file a technician would open today to check that module.
    """
    out: dict[str, dict[str, Any]] = {}
    for entry in CATALOG.select(vin=vin):
        if entry.parse_error:
            continue
        if entry.kind == "scan":
            try:
                slog = scan_mod.load_scan(entry.path, timestamp=entry.timestamp)
            except Exception:
                continue
            for m in slog.modules:
                code = _canon_module(m.abbrev)
                if not code or code in out:
                    continue
                out[code] = {
                    "file": entry.name,
                    "at": entry.timestamp,
                    "codes": {d.full: d.status.value for d in m.dtcs},
                }
        elif entry.kind == "fes":
            try:
                flog = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
            except Exception:
                continue
            code = _module_for_fes_ecu(flog.ecu_description)
            if not code or code in out:
                continue
            codes: dict[str, str] = {}
            for d in flog.dtcs:                  # file order == read order
                codes[d.full] = d.status.value    # last write per code wins
            out[code] = {"file": entry.name, "at": entry.timestamp, "codes": codes}
    return out


def _live_picture(vin: str) -> dict[str, dict[str, Any]]:
    """Newest real ``module_dtcs`` read per ECU: ``{module_code: {at, ecu, codes}}``.

    ``codes`` holds only codes ACTIVE at that read (status & ACTIVE_MASK) -- a
    module lists every code it tracks, and a tracked-but-inactive code is not
    a fault. Only real serial-link reads count (``live_obs.load`` default).
    """
    out: dict[str, dict[str, Any]] = {}
    for obs in reversed(live_obs.load(vin, "module_dtcs")):   # newest first
        data = obs.get("data") or {}
        if data.get("error") or data.get("codes") is None:
            continue
        ecu_raw = str(data.get("ecu") or "").strip()
        ecu = ecu_raw.upper()
        if not ecu or ecu in out:
            continue
        active: dict[str, str] = {}
        for rec in data.get("dtcs") or []:
            code = str(rec.get("code", "")).strip().upper()
            status = int(rec.get("status") or 0)
            if code and (status & live_obs.ACTIVE_MASK):
                active[code] = f"0x{status:02X}"
        out[ecu] = {"at": obs.get("at"), "ecu": ecu_raw or ecu, "codes": active}
    return out


def _cmp_ts(ts: str | None) -> str | None:
    """Normalise a timestamp for lexical comparison: ISO 'T' -> a space."""
    return ts.replace("T", " ") if ts else ts


def _is_stale(ts: str | None, newest_clear: str | None) -> bool:
    """True if ``ts`` is older than the newest clear -- it predates it."""
    if not newest_clear or not ts:
        return False
    return _cmp_ts(ts) < newest_clear


def _newer(t_log: str | None, t_live: str | None) -> str:
    a, b = _cmp_ts(t_log), _cmp_ts(t_live)
    if a is None:
        return "live"
    if b is None:
        return "log"
    if a == b:
        return "equal"
    return "log" if a > b else "live"


def _classify(*, in_log: bool, in_live: bool, t_log: str | None,
             t_live: str | None, newest_clear: str | None) -> str:
    """One of six classes for a single code within one module.

    Both an active live read and a logged read for the SAME code are
    compared against the newest clear before anything else: if both predate
    it, neither one is evidence about the car today. Otherwise the more
    recent reading governs -- a fresher inactive/absent reading beats an
    older active one, on either side.
    """
    log_stale = _is_stale(t_log, newest_clear)
    live_stale = _is_stale(t_live, newest_clear)

    if in_log and in_live:
        return "stale_both" if (log_stale and live_stale) else "live_and_logged"
    if in_log and not in_live:
        return "no_live_read" if t_live is None else "logged_not_live"
    if in_live and not in_log:
        if t_log is None:
            return "no_log"
        # The log is newer than (or as new as) a live read that predates the
        # clear: the newer, silent log is the one that gets believed.
        if live_stale and not log_stale:
            return "logged_not_live"
        return "live_not_logged"
    return "no_log"  # unreachable -- code always comes from one side or both


def _reading(*, code: str, cls: str, module: str, in_log: bool, in_live: bool,
            log_entry: dict | None, live_entry: dict | None,
            newest_clear: str | None) -> str:
    log_bit = (f"the log ({log_entry['file']} at {log_entry['at']})"
              if log_entry else "no log")
    live_bit = (f"live ({live_entry['ecu']} at {live_entry['at']})"
               if live_entry else "no live read")
    newer = (_newer(log_entry["at"], live_entry["at"])
            if (log_entry and live_entry) else None)

    if cls == "live_and_logged":
        return (f"{code} is active in {live_bit} and present in {log_bit} for "
                f"{module}; {newer} is newer -- the fault is standing now.")
    if cls == "stale_both":
        return (f"{code} appears in {log_bit} and {live_bit} for {module}, but "
                f"both predate the last clear at {newest_clear} -- neither "
                f"reading describes the car now.")
    if cls == "logged_not_live" and in_log:
        return (f"{code} is present in {log_bit} for {module}; {live_bit} "
                f"({newer or 'newer'}) does not show it active. Absent is not "
                f"passed: it may be intermittent, or erased by a clear. Check "
                f"the status byte with verify_repair after a few drives.")
    if cls == "logged_not_live":
        # The code was active live, but that read predates the newest clear,
        # and the newer log is clean. A clean read after a clear shows only
        # that the list was erased; the ECU has not necessarily re-run the
        # test. On 2026-09-25 the "clean" log came one minute after the clear.
        return (f"{code} was active in {live_bit} for {module} until the clear at "
                f"{newest_clear}; {log_bit} came after the clear and does not list "
                f"it. That shows the list was erased, NOT that the fault is fixed: "
                f"the test must re-run first (several drives, fuel 15-85 %, cold "
                f"starts for EVAP). Check with verify_repair.")
    if cls == "live_not_logged":
        return (f"{code} is active in {live_bit} for {module}, newer than "
                f"{log_bit}, which does not list it -- set after the last "
                f"MES scan.")
    if cls == "no_live_read":
        return (f"{code} is present in {log_bit} for {module}; {live_bit} -- "
                f"no live read exists to confirm or refute it now.")
    if cls == "no_log":
        return (f"{code} is active in {live_bit} for {module}; no MES log has "
                f"ever read this module for this VIN.")
    return f"{code}: unclassified"  # pragma: no cover


def live_vs_log(vin: str, module: str = "") -> dict[str, Any]:
    """Per-module, per-code comparison of the newest log read vs the newest live read.

    ``module`` restricts the report to one module (MES abbreviation, ECU
    hardware name, or the plain code cuore uses -- all resolve to the same
    space). Empty reports every module either side has seen.
    """
    vin = (vin or "").strip()
    if not vin:
        return {"error": "vin is required"}

    newest_clear = _last_clear(vin)
    log_map = _log_picture(vin)
    live_map = _live_picture(vin)

    if not log_map and not live_map:
        return {"vin": vin, "newest_clear": newest_clear, "modules": [],
                "summary": {},
                "note": "no logs and no live observations for this VIN"}

    want = _canon_module(module) if module.strip() else ""
    all_modules = sorted(set(log_map) | set(live_map))
    if want:
        all_modules = [m for m in all_modules if m == want]

    modules_out: list[dict[str, Any]] = []
    summary: dict[str, int] = {}

    for mod in all_modules:
        log_entry = log_map.get(mod)
        live_entry = live_map.get(mod)
        log_codes = log_entry["codes"] if log_entry else {}
        live_codes = live_entry["codes"] if live_entry else {}
        in_log_codes = {c for c, s in log_codes.items() if s in _PRESENT_STATUSES}
        in_live_codes = set(live_codes)
        t_log = log_entry["at"] if log_entry else None
        t_live = live_entry["at"] if live_entry else None

        rows = []
        for code in sorted(in_log_codes | in_live_codes):
            in_log = code in in_log_codes
            in_live = code in in_live_codes
            cls = _classify(in_log=in_log, in_live=in_live,
                            t_log=t_log, t_live=t_live, newest_clear=newest_clear)
            rows.append({
                "code": code,
                "class": cls,
                "log_status": log_codes.get(code),
                "live_status": live_codes.get(code),
                "reading": _reading(code=code, cls=cls, module=mod,
                                    in_log=in_log, in_live=in_live,
                                    log_entry=log_entry, live_entry=live_entry,
                                    newest_clear=newest_clear),
            })
            summary[cls] = summary.get(cls, 0) + 1

        modules_out.append({
            "module": mod,
            "log": {"file": log_entry["file"], "at": t_log} if log_entry else None,
            "live": {"at": t_live, "ecu": live_entry["ecu"]} if live_entry else None,
            "rows": rows,
        })

    return {"vin": vin, "newest_clear": newest_clear, "modules": modules_out,
            "summary": summary}


__all__ = ["live_vs_log"]
