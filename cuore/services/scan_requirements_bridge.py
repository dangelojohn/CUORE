"""What CUORE must capture at every scan -- an explicit, checked requirement.

``cuore/data/scan_requirements.json`` lists, for this platform (the 2018
Stelvio 2.0T, default VIN ``ZASFAKPN5J7B88115``), every read the open EVAP
diagnosis needs from a scan, why, where it comes from (``legislated`` OBD,
``uds``, ``did``, ``bundle``, ``mes_sync``, ``mechanic_input``) and which
store observation proves it was captured. Marque and car specifics live in
that file, not here; this module only knows how to look for evidence.

:func:`check` answers, for one scan, "did we actually get it?":

``met``
    requirements whose evidence is in the store for that scan.
``gaps``
    requirements that are not met, each with a plain reason. A legislated
    read (Modes 01/03/06/07/09/0A, readiness, PIDs) that was attempted but
    returned nothing decodable -- NO DATA -- gets the file's
    ``silent_reason`` ("legislated route silent (tool fault, ...)"): that is
    the adapter route failing, not the car having nothing to say. A read that
    answered but left out some of what was required says exactly which part.
``needs_mechanic``
    ``mechanic_input`` rows. CUORE cannot read these (no DID, needs a meter,
    visual, wiTECH), so they are always listed with their
    ``not_capturable_reason`` and are NEVER counted as failures.
``not_applicable``
    requirements that do not apply this scan (the EVAP bundle when the ECM
    holds no active EVAP code).

Which observations belong to which scan: observations carry no scan id, only
an ``at`` timestamp, so the scan's window is rebuilt the way the Scans area
does it. The start is the scan id itself (``SCAN_YYMMDDHHMM`` from
``cuore.live.fullscan``, or the ISO time of the first read for a scan-health
session id). The end is the newest ``scan_coverage`` observation carrying
that scan id (fullscan rewrites it after every segment), or, when there is
none, the 15-minute-gap rule ``scan_health_bridge`` uses. Requirements marked
``"window": "after_start"`` (the MES clear sync) accept anything recorded
since the scan began.

Read-only: nothing here touches the car or writes to the store.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from ..live import coverage as coverage_mod
from ..live import store as live_store
from ..live.config import state_dir
from . import cache

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "scan_requirements.json"

#: Fallbacks for a damaged data file; the file's own values win.
DEFAULT_VIN = "ZASFAKPN5J7B88115"
SILENT_REASON = ("legislated route silent (tool fault, see "
                 "docs/research/CEL_2026-10-19_DIAGNOSIS.md)")

SOURCES = ("legislated", "uds", "did", "bundle", "mes_sync", "mechanic_input")

#: Same gap rule as ``scan_health_bridge``/``cuore.live.scanlog``.
_SESSION_GAP = timedelta(minutes=15)

_SCAN_ID_RE = re.compile(r"^SCAN_(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$")

MET, SILENT, MISSING, NA = "met", "silent", "missing", "na"


# --- the requirement list ------------------------------------------------------

def load() -> dict[str, Any]:
    """The data file, tolerantly: rows without an ``id`` are dropped, a
    duplicate id keeps the first, every optional field gets a default, and an
    unreadable file yields an empty requirement list rather than an error."""
    try:
        raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    platform = raw.get("platform") if isinstance(raw.get("platform"), dict) else {}
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for r in raw.get("requirements") or []:
        if not isinstance(r, dict) or not r.get("id") or r["id"] in seen:
            continue
        seen.add(r["id"])
        ev = r.get("evidence_kind")
        rows.append({
            **r,
            "label": r.get("label") or r["id"],
            "why": r.get("why") or "",
            "source": r.get("source") or "uds",
            "evidence_kind": ev if isinstance(ev, dict) else {},
            "not_capturable_reason": r.get("not_capturable_reason") or "",
        })
    return {"platform": platform,
            "default_vin": platform.get("default_vin") or DEFAULT_VIN,
            "silent_reason": raw.get("silent_reason") or SILENT_REASON,
            "requirements": rows}


def requirements() -> list[dict[str, Any]]:
    """Every requirement row, in file order."""
    return load()["requirements"]


# --- which observations belong to a scan ---------------------------------------

def _parse_at(s: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def _scan_start(scan_id: str) -> Optional[datetime]:
    sid = (scan_id or "").strip()
    m = _SCAN_ID_RE.match(sid)
    if m:
        yy, mo, dd, hh, mi = (int(g) for g in m.groups())
        try:
            return datetime(2000 + yy, mo, dd, hh, mi)
        except ValueError:
            return None
    return _parse_at(sid) if sid else None


class _Ctx:
    """Everything one :func:`check` needs, so each checker stays a few lines."""

    def __init__(self, scan_id: str, vin: str, start: datetime, end: datetime,
                 in_window: list[dict[str, Any]], since_start: list[dict[str, Any]],
                 steps: list[dict[str, Any]], silent_reason: str) -> None:
        self.scan_id, self.vin, self.start, self.end = scan_id, vin, start, end
        self.in_window, self.since_start = in_window, since_start
        self.steps, self.silent_reason = steps, silent_reason

    def data(self, ev: dict[str, Any], kind: Optional[str] = None) -> list[dict[str, Any]]:
        """``data`` of every observation of ``kind`` in this requirement's window."""
        pool = self.since_start if ev.get("window") == "after_start" else self.in_window
        k = kind or ev.get("kind")
        return [o.get("data") or {} for o in pool if o.get("kind") == k]


def _all_observations(vin: str) -> list[dict[str, Any]]:
    """Every observation for this VIN (an untagged read is kept, the same
    single-car assumption ``scan_health_bridge`` documents), oldest first."""
    out: list[tuple[datetime, dict[str, Any]]] = []
    for o in live_store.recent_observations(n=10 ** 9):
        if (o.get("vin") or "").upper() not in ("", vin):
            continue
        at = _parse_at(o.get("at"))
        if at is not None:
            out.append((at, o))
    out.sort(key=lambda t: t[0])
    return [o for _, o in out]


def _build_ctx(scan_id: str, vin: str, silent_reason: str) -> Optional[_Ctx]:
    start = _scan_start(scan_id)
    if start is None:
        return None
    obs = _all_observations(vin)
    cov = [o for o in obs if o.get("kind") == "scan_coverage"
           and (o.get("data") or {}).get("scan_id") == scan_id]
    after = [o for o in obs if _parse_at(o.get("at")) >= start]
    if cov:
        end = max(_parse_at(o["at"]) for o in cov)
    else:
        end = start
        for o in after:
            at = _parse_at(o["at"])
            if at - end > _SESSION_GAP:
                break
            end = at
    in_window = [o for o in after if _parse_at(o["at"]) <= end]
    steps: list[dict[str, Any]] = []
    if cov:
        latest = max(cov, key=lambda o: _parse_at(o["at"]))
        steps = [s for s in (latest.get("data") or {}).get("steps") or [] if isinstance(s, dict)]
    return _Ctx(scan_id, vin, start, end, in_window, after, steps, silent_reason)


# --- checkers ------------------------------------------------------------------
#
# Each takes (ctx, evidence_kind) and returns (status, reason). ``reason`` is
# only used for a non-met status. Statuses: MET, SILENT (legislated route
# answered nothing decodable), MISSING, NA.

Result = tuple[str, str]


def _absent(ctx: _Ctx, ev: dict[str, Any], what: str) -> Result:
    """No observation of the kind at all: say so, and why when fullscan's own
    step log knows."""
    base = f"no {what} observation recorded in this scan"
    step = ev.get("step")
    if step:
        for s in ctx.steps:
            if str(s.get("step", "")).startswith(step) and s.get("ok") is False:
                return MISSING, f"{base} (step failed: {s.get('error') or 'unknown error'})"
    return MISSING, base


def _norm_hex(v: Any) -> str:
    s = str(v).strip().upper()
    return s[2:] if s.startswith("0X") else s


def _list(items: list[str], prefix: str = "") -> str:
    return ", ".join(f"{prefix}{i}" for i in items)


def _chk_readiness(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    field = ev.get("field") or "since_clear"
    obs = ctx.data(ev)
    if not obs:
        return _absent(ctx, ev, "readiness")
    for d in obs:
        part = d.get(field)
        if isinstance(part, dict) and part and not part.get("error"):
            return MET, ""
    return SILENT, ctx.silent_reason


def _chk_mode06(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    want = [_norm_hex(m) for m in ev.get("mids") or []]
    obs = ctx.data(ev)
    if not obs:
        return _absent(ctx, ev, "mode06")
    got: set[str] = set()
    for d in obs:
        for mid, res in (d.get("results") or {}).items():
            if isinstance(res, dict) and res.get("by_ecu"):
                got.add(_norm_hex(mid))
    missing = [m for m in want if m not in got]
    if not missing:
        return MET, ""
    if not got:
        return SILENT, ctx.silent_reason
    return MISSING, f"no result for Mode 06 MID {_list(missing, '0x')}"


def _chk_pids(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    want = [_norm_hex(p) for p in ev.get("pids") or []]
    snaps = ctx.data(ev)
    singles = ctx.data(ev, "pid")
    readiness = ctx.data(ev, "readiness")
    if not snaps and not singles:
        return _absent(ctx, ev, "pids_snapshot")
    got: set[str] = set()
    for d in snaps:
        for readings in (d.get("by_ecu") or {}).values():
            for pid, r in (readings or {}).items():
                if isinstance(r, dict) and r.get("value") is not None:
                    got.add(_norm_hex(pid))
    for d in singles:
        if d.get("pid") is not None and d.get("value") is not None:
            got.add(_norm_hex(d["pid"]))
    for d in readiness:  # PIDs 30/31 are also read, as counters, with readiness
        counters = d.get("drive_cycle_counters") or {}
        if counters.get("warmups_since_clear") is not None:
            got.add("30")
        if counters.get("distance_since_clear") is not None:
            got.add("31")
    missing = [p for p in want if p not in got]
    if not missing:
        return MET, ""
    if not got:
        return SILENT, ctx.silent_reason
    return MISSING, f"PID {_list(missing)} not read"


def _chk_dtc_modes(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    want = list(ev.get("dtc_kinds") or [])
    obs = ctx.data(ev)
    if not obs:
        return _absent(ctx, ev, "obd_dtcs")
    got = {d.get("dtc_kind") or d.get("kind") for d in obs
           if not d.get("warning") and not d.get("error")}
    missing = [k for k in want if k not in got]
    if not missing:
        return MET, ""
    if not got:
        return SILENT, ctx.silent_reason
    return MISSING, f"{_list(missing)} codes not read"


def _chk_mode09(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    want = [_norm_hex(p) for p in ev.get("pids") or []]
    obs = ctx.data(ev)
    if not obs:
        return _absent(ctx, ev, "mode09")
    got: set[str] = set()
    for d in obs:
        m09 = d.get("mode09") if isinstance(d.get("mode09"), dict) else {}
        for pid, res in (m09.get("results") or {}).items():
            if isinstance(res, dict) and res and not (
                    {"error", "warning", "negative"} & set(res)):
                got.add(_norm_hex(pid))
    missing = [p for p in want if p not in got]
    if not missing:
        return MET, ""
    if not got:
        return SILENT, ctx.silent_reason
    return MISSING, f"Mode 09 PID {_list(missing)} not answered"


def _why_not_answered(d: dict[str, Any]) -> str:
    return str(d.get("error") or d.get("nrc") or d.get("warning") or "no usable answer")


def _chk_module_dtcs(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    ecu = ev.get("ecu") or "ECM"
    obs = [d for d in ctx.data(ev) if d.get("ecu") == ecu]
    if not obs:
        return MISSING, f"no module_dtcs observation for {ecu} in this scan (module not swept)"
    last_reason = ""
    for d in obs:
        if d.get("error") or d.get("nrc") or d.get("warning"):
            last_reason = _why_not_answered(d)
            continue
        recs = d.get("dtcs")
        if isinstance(recs, list) and all(
                isinstance(r, dict) and r.get("status") is not None for r in recs):
            return MET, ""
        last_reason = "DTC records carry no status byte"
    return MISSING, f"{ecu} did not give DTCs with status bytes: {last_reason}"


def _active_codes(ctx: _Ctx, regex: str) -> Optional[list[str]]:
    """Active codes matching ``regex`` on the ECM, or ``None`` when the ECM's
    DTCs were not read at all."""
    ecm = [d for d in ctx.data({}, "module_dtcs")
           if d.get("ecu") == "ECM" and not d.get("error") and not d.get("nrc")
           and not d.get("warning") and isinstance(d.get("dtcs"), list)]
    if not ecm:
        return None
    rx = re.compile(regex, re.IGNORECASE)
    codes: list[str] = []
    for d in ecm:
        for r in d["dtcs"]:
            try:
                active = int(r.get("status") or 0) & coverage_mod.ACTIVE_MASK
            except (TypeError, ValueError):
                active = 0
            code = str(r.get("code") or "")
            if active and rx.match(code) and code not in codes:
                codes.append(code)
    return codes


def _chk_evap_bundle(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    active = _active_codes(ctx, ev.get("applies_regex") or r"^P04[456][0-9A-F]")
    if active is None:
        return MISSING, "ECM DTCs were not read, so the EVAP bundle could not be triggered"
    if not active:
        return NA, "no active EVAP code on the ECM this scan, so there was nothing to snapshot"
    rx = re.compile(ev.get("code_regex") or r"^P04[45][0-9A-F]", re.IGNORECASE)
    needed = [c for c in active if rx.match(c)]
    if not needed:
        return NA, f"active EVAP code(s) {_list(active)} are outside P044x/P045x"
    bundles = ctx.data(ev)
    if not bundles:
        return _absent(ctx, ev, "evap_bundle")
    have: set[str] = set()
    for b in bundles:
        for c in b.get("codes") or []:
            if (isinstance(c, dict) and c.get("snapshot_decoded") and not c.get("error")):
                have.add(str(c.get("code") or "").upper())
    missing = [c for c in needed if c.upper() not in have]
    if not missing:
        return MET, ""
    return MISSING, f"no decoded snapshot for {_list(missing)}"


def _chk_identity(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    ecu = ev.get("ecu") or "ECM"
    want = [_norm_hex(d) for d in ev.get("dids") or []]
    obs = [d for d in ctx.data(ev) if d.get("ecu") == ecu]
    if not obs:
        return MISSING, f"no module_identity observation for {ecu} in this scan"
    got: set[str] = set()
    for d in obs:
        for did, f in (d.get("fields") or {}).items():
            if isinstance(f, dict) and (f.get("ascii") or f.get("bytes")):
                got.add(_norm_hex(did))
    missing = [d for d in want if d not in got]
    if not missing:
        return MET, ""
    err = next((d["error"] for d in obs if d.get("error")), "")
    return MISSING, f"{ecu} identity DID {_list(missing)} not read" + (f" ({err})" if err else "")


def _chk_dids(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    want = [(str(w.get("ecu") or "").upper(), _norm_hex(w.get("did")))
            for w in ev.get("dids") or [] if isinstance(w, dict)]
    got: set[tuple[str, str]] = set()
    for d in ctx.data(ev):
        if d.get("ecu") and d.get("did") and d.get("bytes") and not d.get("error"):
            got.add((str(d["ecu"]).upper(), _norm_hex(d["did"])))
    for d in ctx.data(ev, "did_discovery"):
        ecu = str(d.get("ecu") or d.get("module") or "").upper()
        for h in d.get("hits") or []:
            if isinstance(h, dict) and h.get("did") and h.get("bytes"):
                got.add((ecu, _norm_hex(h["did"])))
    missing = [w for w in want if w not in got]
    if not missing:
        return MET, ""
    return MISSING, "DID not read: " + ", ".join(f"{e} {d}" for e, d in missing)


def _dig(obj: Any, path: list[str]) -> Any:
    for p in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(p)
    return obj


def _chk_state_stamp(ctx: _Ctx, ev: dict[str, Any]) -> Result:
    fname = ev.get("file") or ""
    path = [str(p).replace("{vin}", ctx.vin) for p in ev.get("path") or []]
    try:
        state = json.loads((state_dir() / fname).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    stamp = _dig(state, path)
    at = _parse_at(stamp)
    if at is not None and at >= ctx.start:
        return MET, ""
    seen = f"last synced {stamp}" if stamp else "never synced"
    return MISSING, f"no MES clear sync since this scan started ({seen})"


#: Checker name (``evidence_kind.check``) -> function.
CHECKERS: dict[str, Callable[[_Ctx, dict[str, Any]], Result]] = {
    "readiness_decoded": _chk_readiness,
    "mode06_mids": _chk_mode06,
    "pids": _chk_pids,
    "dtc_modes": _chk_dtc_modes,
    "mode09_pids": _chk_mode09,
    "module_dtcs": _chk_module_dtcs,
    "evap_bundle": _chk_evap_bundle,
    "identity": _chk_identity,
    "dids": _chk_dids,
    "state_stamp": _chk_state_stamp,
}


# --- the public check ------------------------------------------------------------

def check(scan_id: str, vin: str = "",
          rows: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Settle every requirement against the observations of one scan.

    Returns ``{"met": [...], "gaps": [{id, label, reason, source}], ...}``
    plus ``needs_mechanic`` (never failures), ``not_applicable``, ``captured``
    / ``required`` counts (mechanic and not-applicable rows excluded from
    both), the scan window, ``non_car_observations`` (how many of the scan's
    observations did not come from a real serial link) and a one-line
    ``summary``. ``vin`` defaults to the platform's default vehicle.
    """
    cfg = load()
    vin = (vin or cfg["default_vin"]).strip().upper()
    reqs = rows if rows is not None else cfg["requirements"]
    ctx = _build_ctx(scan_id, vin, cfg["silent_reason"])

    met: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    needs_mechanic: list[dict[str, Any]] = []
    not_applicable: list[dict[str, Any]] = []

    for r in reqs:
        base = {"id": r["id"], "label": r["label"], "source": r["source"]}
        if r["source"] == "mechanic_input":
            needs_mechanic.append({**base, "why": r.get("why", ""),
                                   "reason": r.get("not_capturable_reason", ""),
                                   "status": "needs mechanic"})
            continue
        if ctx is None:
            gaps.append({**base, "reason": f"scan id {scan_id!r} not recognised "
                         "(expected SCAN_YYMMDDHHMM or an ISO timestamp)"})
            continue
        ev = r.get("evidence_kind") or {}
        fn = CHECKERS.get(ev.get("check") or "")
        if fn is None:
            gaps.append({**base, "reason": f"no checker {ev.get('check')!r} for this requirement"})
            continue
        try:
            status, reason = fn(ctx, ev)
        except Exception as e:  # noqa: BLE001 -- one bad row must not hide the others
            status, reason = MISSING, f"check failed: {type(e).__name__}: {e}"
        if status == MET:
            met.append(base)
        elif status == NA:
            not_applicable.append({**base, "reason": reason})
        else:
            gaps.append({**base, "reason": reason})

    captured, required = len(met), len(met) + len(gaps)
    summary = f"Captured {captured} of {required} required"
    if gaps:
        summary += "; gaps: " + "; ".join(f"{g['label']} ({g['reason']})" for g in gaps)
    if needs_mechanic:
        summary += f"; needs mechanic: {len(needs_mechanic)}"
    return {
        "scan_id": scan_id, "vin": vin, "met": met, "gaps": gaps,
        "needs_mechanic": needs_mechanic, "not_applicable": not_applicable,
        "captured": captured, "required": required,
        "window": ({"start": ctx.start.isoformat(timespec="seconds"),
                    "end": ctx.end.isoformat(timespec="seconds")} if ctx else None),
        "non_car_observations": (sum(1 for o in ctx.in_window if not live_store.is_from_car(o))
                                 if ctx else 0),
        "summary": summary,
    }


# --- the scan page ----------------------------------------------------------------

def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def view(vin: str, scan_id: Optional[str] = None) -> dict[str, Any]:
    """What the guided-scan page renders. Never raises: a failed check comes
    back as ``{"error": ...}`` so the page still loads. With no scan, the
    list of what the next scan must capture (``has_scan`` false)."""
    try:
        cfg = load()
        if not scan_id:
            rows = cfg["requirements"]
            return {"has_scan": False,
                    "to_capture": [{"id": r["id"], "label": r["label"], "why": r["why"],
                                    "source": r["source"]}
                                   for r in rows if r["source"] != "mechanic_input"],
                    "needs_mechanic": [{"id": r["id"], "label": r["label"], "why": r["why"],
                                        "reason": r["not_capturable_reason"],
                                        "status": "needs mechanic"}
                                       for r in rows if r["source"] == "mechanic_input"]}
        key = ("scan_requirements", vin, scan_id,
               _mtime(live_store.observations_path()),
               _mtime(state_dir() / "mes_clear_watch.json"), _mtime(_DATA_FILE))
        return {"has_scan": True,
                **cache.get_or_build(key, lambda: check(scan_id, vin))}
    except Exception as e:  # noqa: BLE001 -- the scan page must still render
        return {"error": f"{type(e).__name__}: {e}"}


__all__ = ["load", "requirements", "check", "view", "CHECKERS", "SOURCES"]
