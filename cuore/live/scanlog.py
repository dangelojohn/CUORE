"""Scan log: from-car observations regrouped into browsable "scans".

Nothing here is a second copy of the truth. ``cuore.live.store`` already
appends every live read to ``observations.jsonl``, one JSON object per read
(``kind`` + ``data`` + ``vin`` + ``stream`` + ``at``) -- see that module's own
docstring and :func:`cuore.live.store.is_from_car`. This module only *groups*
that append-only log, on read, into the shape a mechanic actually wants: "the
scan I ran a minute ago", not fifty individual rows.

Grouping rule: consecutive from-car observations within :data:`WINDOW` of
each other are one scan. A key fob read 20 minutes after the last DTC read is
a new scan; two DTC reads 90 seconds apart are the same one. The VIN tagged
on a scan is the first non-empty ``vin`` any observation in the cluster
carries -- Mode 03/06 reads (``obd_dtcs``, ``mode06`` discovery) often carry
no VIN of their own (the car was never asked), so a cluster borrows the VIN
the readiness/identity read next to it supplied. A cluster with no VIN
anywhere in it cannot be shown under any vehicle and is dropped by
:func:`list_scans`/:func:`get_scan` (both take ``vin`` and only ever return
clusters that resolved to it).

Derived values are cached on the observations file's own mtime
(:func:`_fingerprint`) -- the same "cache key includes what makes it stale"
rule ``cuore.services.cache`` documents -- so a new live read invalidates the
cache on its own; there is no separate invalidation hook and nothing here
ever writes ``observations.jsonl``.

``freeze_frame`` and bare ``pid`` observation kinds are read defensively:
today's live link (``cuore.live.ops``) does not yet call ``_observe`` for
``obd_freeze_frame``/``obd_pid`` (both only ``_stamp``), so neither kind
exists in the real corpus yet. When wiring that up, the shapes already
produced by those two functions (``{"pid", "name", "by_ecu": {ecu:
{...}}}``) are exactly what is read here -- nothing to change on this side.

Owner's guidance (2026-10-13): "we do not need many scans, just 10" -- one
complete guided scan per visit, about ten over the whole diagnosis, not
fifty single reads. Two things follow from that, both derived here, never
invented elsewhere:

* ``coverage`` -- when a cluster carries a ``scan_coverage`` observation
  (written by ``cuore.live.fullscan.run``/``run_guided``, itself part of
  the same cluster because it is a from-car observation too), this is the
  whole-bus-sweep summary: which of CAN-C/IHS/CH were attempted, how many
  modules actually answered on each, and the raw counts. ``None`` when no
  such observation is in the cluster -- a manual single-purpose read
  (Codes/Live/Tests) never pretends to a coverage picture it does not have.
* ``partial`` -- ``True`` whenever :func:`_coverage_status` does not say
  ``"complete"`` (see below). Still a scan -- still listed -- just labelled
  "partial" (or "attempt") everywhere it is shown, and never one of
  :func:`scan_plan`'s own ``count``.

**Scan plan honesty** (owner's correction, 2026-10-14: the "Scan n of 10"
chip was counting partial/debug reads and failed attempts as if they were
real scans, so after an evening of mostly manual reads plus one guided
scan that never got past "opening COM3", the chip was overclaiming).
:func:`_coverage_status` sorts every scan into exactly one of three states,
from its ``scan_coverage`` observation's own raw ``coverage`` rows (one per
module probed, each tagged ``"answered"``/``"silent"``/``"not_reachable"``
by ``cuore.live.fullscan``):

* ``"complete"`` -- the CAN-C sweep answered at least one module (a
  fullscan or a guided scan, on any cable segment that reached CAN-C).
  Only these count toward :func:`scan_plan`'s ``count`` and only these get
  a "Scan n" number (``cuore.web.scanlog_routes``).
* ``"partial"`` -- no ``scan_coverage`` observation at all (a manual,
  single-purpose read -- Codes/Live/Tests -- was never a bus-sweep attempt
  in the first place), or one exists but CAN-C itself never answered
  (e.g. only IHS/CH responded). Still listed, labelled "partial",
  unnumbered.
* ``"attempt"`` -- a ``scan_coverage`` observation exists but NO module on
  any bus answered (every row ``"not_reachable"`` -- an adapter/cable
  error, most often COM3 failing to open). Listed, labelled "attempt --
  adapter not reachable", unnumbered -- never silently folded into
  "partial", which would read as "a read was taken" when nothing was.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import store
from .config import state_dir

#: Consecutive from-car observations closer together than this are one scan.
WINDOW = timedelta(minutes=15)

#: ``SCAN_<yymmddHHMM>`` -- the same stem ``mes.paths.SCAN_RE`` matches, so a
#: file this module exports under that name is picked up by existing MES
#: tooling (``list_logs``, ``read_log``) unchanged.
ID_FMT = "SCAN_%y%m%d%H%M"

_DTC_KINDS = ("stored", "pending", "permanent")

#: UDS status bits that make a module DTC a fault now -- same rule as
#: ``cuore.live.coverage.ACTIVE_MASK`` (testFailed | pendingDTC | confirmedDTC),
#: kept local so this read-only module does not import the live-sweep one.
ACTIVE_MASK = 0x01 | 0x04 | 0x08
_PENDING_BIT = 0x04
_CONFIRMED_BIT = 0x08

#: The owner's own number ("just 10") -- the plan chip's denominator, never
#: a hard cap: nothing here refuses an 11th scan, it only keeps counting.
PLAN_TOTAL = 10

#: Short label for the coverage line, and the bypass cable a bus not yet
#: attempted still needs -- same vocabulary ``cuore.live.fullscan``/
#: ``cuore.live.buses`` already use (grey A6 -> CAN-CH, blue A5 -> CAN-IHS).
_BUS_ORDER = ("can_c", "can_ihs", "can_ch")
_BUS_SHORT = {"can_c": "CAN-C", "can_ihs": "IHS", "can_ch": "CH"}
_BUS_CABLE_NOTE = {"can_ihs": "blue A5", "can_ch": "grey A6"}

#: PID parameter name -> sentence-case display name, same convention
#: ``dossier_bridge._KEY_FRAME_PARAMS`` already uses ("Fuel level", not
#: "fuel_level" or "Fuel Level").
def _sentence(name: str | None) -> str:
    if not name:
        return ""
    words = str(name).replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else ""


def _fingerprint() -> tuple[float, int]:
    try:
        st = store.observations_path().stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return (0.0, 0)


_cache: dict[tuple[float, int], list[dict[str, Any]]] = {}


def _parse_at(raw: Any) -> Optional[datetime]:
    s = str(raw or "")[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _clusters() -> list[list[dict[str, Any]]]:
    """Every from-car observation, windowed into clusters, oldest first."""
    timed: list[tuple[datetime, dict[str, Any]]] = []
    for o in store.recent_observations(10_000_000):
        if not store.is_from_car(o):
            continue
        at = _parse_at(o.get("at"))
        if at is None:
            continue
        timed.append((at, o))
    timed.sort(key=lambda t: t[0])

    out: list[list[dict[str, Any]]] = []
    stamps: list[datetime] = []
    for at, o in timed:
        if out and at - stamps[-1] <= WINDOW:
            out[-1].append(o)
        else:
            out.append([o])
        stamps.append(at)
    return out


# --- per-cluster assembly ----------------------------------------------------


def _collect_ecus(data: dict[str, Any], into: set[str]) -> None:
    by_ecu = data.get("by_ecu")
    if isinstance(by_ecu, dict):
        into.update(by_ecu.keys())
    ecu = data.get("ecu")
    if isinstance(ecu, str) and ecu:
        into.add(ecu)
    for rec in data.get("modules") or []:
        if isinstance(rec, dict) and rec.get("ecu"):
            into.add(str(rec["ecu"]))


def _add_dtc(by_ecu_codes: dict[str, set[str]], ecu: str, code: str) -> None:
    if not code:
        return
    by_ecu_codes.setdefault(ecu, set()).add(code.split("-", 1)[0].upper())


def _build_dtcs(cluster: list[dict[str, Any]], ecus: set[str]
                ) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    """``(dtcs, by_ecu_codes)`` -- ``dtcs`` is ``{"stored": [...], ...}``,
    latest ``obd_dtcs`` read of each kind wins (chronological order, so a
    later clear is reflected); ``by_ecu_codes`` is every DTC seen anywhere,
    keyed by ECU, for the MES export below."""
    dtcs: dict[str, list[str]] = {k: [] for k in _DTC_KINDS}
    by_ecu_codes: dict[str, set[str]] = {}
    for o in cluster:
        data = o.get("data") or {}
        kind = o.get("kind")
        if kind == "obd_dtcs":
            bucket = data.get("kind")
            codes = [c.split("-", 1)[0].upper() for c in (data.get("dtcs") or [])]
            if bucket in dtcs:
                dtcs[bucket] = codes
            by_ecu = data.get("by_ecu") or {}
            for ecu, lst in by_ecu.items():
                for c in lst or []:
                    _add_dtc(by_ecu_codes, ecu, c)
        elif kind == "module_dtcs":
            ecu = data.get("ecu") or (next(iter(ecus), "") if len(ecus) == 1 else "")
            for rec in data.get("dtcs") or []:
                code = rec.get("code") if isinstance(rec, dict) else None
                if not code:
                    continue
                # A UDS sweep reports every DTC the module knows, with a
                # status byte; 0x40 alone ("not completed this cycle", ~250
                # per module right after a clear) is no fault. Only the
                # coverage ACTIVE bits count; a record without a status
                # byte (older observations) is kept as before.
                status = rec.get("status")
                if isinstance(status, int):
                    if not status & ACTIVE_MASK:
                        continue
                    if status & _PENDING_BIT and not status & _CONFIRMED_BIT:
                        dtcs["pending"].append(code.split("-", 1)[0].upper())
                    else:
                        dtcs["stored"].append(code.split("-", 1)[0].upper())
                else:
                    dtcs["stored"].append(code.split("-", 1)[0].upper())
                _add_dtc(by_ecu_codes, ecu or "unknown", code)
    dtcs["stored"] = sorted(dict.fromkeys(dtcs["stored"]))
    dtcs["pending"] = sorted(dict.fromkeys(dtcs["pending"]))
    dtcs["permanent"] = sorted(dict.fromkeys(dtcs["permanent"]))
    return dtcs, by_ecu_codes


def _build_readiness(cluster: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    latest = None
    for o in cluster:
        if o.get("kind") == "readiness":
            latest = o.get("data") or {}
    return latest


def _mil_from(readiness: Optional[dict[str, Any]]) -> Optional[bool]:
    if not readiness:
        return None
    since = readiness.get("since_clear") or {}
    mil = since.get("mil_on")
    return bool(mil) if mil is not None else None


def _build_mode06(cluster: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flat ``[{mid, mid_name, tid, ecu, unit, value, min, max, passed}, ...]``
    from the latest ``mode06`` observation -- one row per MID/TID/ECU, the
    shape ``scan.html``'s Mode 06 table wants directly."""
    latest = None
    for o in cluster:
        if o.get("kind") == "mode06":
            latest = o.get("data") or {}
    if not latest:
        return []
    rows: list[dict[str, Any]] = []
    for mid, entry in (latest.get("results") or {}).items():
        by_ecu = (entry or {}).get("by_ecu") or {}
        for ecu, recs in by_ecu.items():
            for r in recs or []:
                rows.append({
                    "mid": r.get("mid", mid), "mid_name": r.get("mid_name"),
                    "tid": r.get("tid"), "ecu": ecu, "unit": r.get("unit"),
                    "value": r.get("value"), "min": r.get("min"), "max": r.get("max"),
                    "passed": r.get("passed"),
                })
    rows.sort(key=lambda r: (str(r["mid"]), str(r["tid"] or "")))
    return rows


def _build_freeze_frames(cluster: list[dict[str, Any]],
                         by_ecu_codes: dict[str, set[str]]) -> list[dict[str, Any]]:
    """``[{"code", "ecu", "pids": [{"pid","name","value","unit"}, ...]}]``.

    A ``pid="02"`` read identifies which DTC a freeze frame belongs to for
    that ECU (``by_ecu[ecu]["dtc"]``); every other PID read in the same
    cluster is a parameter of that frame. See the module docstring for why
    this kind may not exist in the corpus yet.
    """
    frame_dtc: dict[str, Optional[str]] = {}
    rows_by_ecu: dict[str, list[dict[str, Any]]] = {}
    saw_any = False
    for o in cluster:
        if o.get("kind") != "freeze_frame":
            continue
        saw_any = True
        data = o.get("data") or {}
        pid = str(data.get("pid") or "")
        by_ecu = data.get("by_ecu") or {}
        for ecu, val in by_ecu.items():
            if not isinstance(val, dict):
                continue
            if pid == "02":
                frame_dtc[ecu] = val.get("dtc")
                continue
            rows_by_ecu.setdefault(ecu, []).append({
                "pid": val.get("pid", pid), "name": _sentence(val.get("name")) or f"PID {pid}",
                "value": val.get("value"), "unit": val.get("unit"),
            })
    if not saw_any:
        return []
    out: list[dict[str, Any]] = []
    for ecu, rows in rows_by_ecu.items():
        code = frame_dtc.get(ecu)
        if not code:
            codes = by_ecu_codes.get(ecu) or set()
            code = next(iter(codes)) if len(codes) == 1 else None
        out.append({"code": code, "ecu": ecu, "pids": rows})
    out.sort(key=lambda f: (f["code"] or "", f["ecu"]))
    return out


def _build_pids(cluster: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Latest value per live PID read in the window (kind ``"pid"``; see the
    module docstring -- speculative, not produced by today's link)."""
    latest: dict[str, dict[str, Any]] = {}
    for o in cluster:
        if o.get("kind") != "pid":
            continue
        data = o.get("data") or {}
        pid = str(data.get("pid") or "")
        if not pid:
            continue
        if "value" in data and data.get("value") is not None:
            name, value, unit = data.get("name"), data.get("value"), data.get("unit")
        else:
            first = next(iter((data.get("by_ecu") or {}).values()), {})
            name, value, unit = first.get("name"), first.get("value"), first.get("unit")
        latest[pid] = {"pid": pid, "name": _sentence(name) or f"PID {pid}",
                       "value": value, "unit": unit, "at": o.get("at")}
    return sorted(latest.values(), key=lambda p: p["pid"])


def _build_source(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    stream = next((o.get("stream") for o in cluster if o.get("stream")), "")
    identity = next((o.get("data") for o in cluster if o.get("kind") == "identity"), None)
    return {"stream": stream, "identity": identity}


def _latest_coverage_obs(cluster: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Raw ``data`` of this cluster's own ``scan_coverage`` observation
    (latest one wins, same "latest in cluster" rule every other
    ``_build_*`` helper here uses), or ``None`` when the cluster has
    none -- shared by :func:`_build_coverage` (the display line) and
    :func:`_coverage_status` (complete/partial/attempt) so they can never
    disagree about which observation is "the" coverage for this scan."""
    latest = None
    for o in cluster:
        if o.get("kind") == "scan_coverage":
            latest = o.get("data") or {}
    return latest


def _coverage_status(latest: Optional[dict[str, Any]]) -> str:
    """``"complete"``/``"partial"``/``"attempt"`` -- see the module
    docstring's "Scan plan honesty" section. ``None`` (no ``scan_coverage``
    observation at all) is always ``"partial"``: a manual read was never a
    bus-sweep attempt to begin with, so it cannot have "failed" one."""
    if latest is None:
        return "partial"
    rows = latest.get("coverage") or []
    if not any(r.get("category") == "answered" for r in rows):
        return "attempt"
    can_c_answered = sum(1 for r in rows
                        if r.get("bus") == "can_c" and r.get("category") == "answered")
    if "can_c" in (latest.get("buses_attempted") or []) and can_c_answered >= 1:
        return "complete"
    return "partial"


def _build_coverage(latest: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The whole-bus-sweep summary line from one ``scan_coverage``
    observation's raw data (see :func:`_latest_coverage_obs`), or ``None``
    when there is none -- see the module docstring for what that means
    (:data:`PLAN_TOTAL`, ``partial``)."""
    if latest is None:
        return None

    attempted = set(latest.get("buses_attempted") or [])
    modules_by_bus: dict[str, set[str]] = {}
    for row in latest.get("coverage") or []:
        if row.get("category") in ("answered", "silent"):
            modules_by_bus.setdefault(row.get("bus"), set()).add(row.get("module"))

    parts: list[str] = []
    for bus in _BUS_ORDER:
        label = _BUS_SHORT[bus]
        if bus in attempted:
            n = len(modules_by_bus.get(bus, set()))
            parts.append(f"{label} {n} module{'' if n == 1 else 's'}")
        else:
            note = _BUS_CABLE_NOTE.get(bus)
            parts.append(f"{label} not scanned" + (f" ({note})" if note else ""))

    return {
        "line": " · ".join(parts),
        "buses_attempted": sorted(attempted),
        "counts": latest.get("counts") or {},
        "guided": bool(latest.get("guided")),
    }


def _scan_from_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    vin = next((o.get("vin") for o in cluster if o.get("vin")), "")
    started_dt = _parse_at(cluster[0].get("at"))
    ended_dt = _parse_at(cluster[-1].get("at"))
    scan_id = started_dt.strftime(ID_FMT) if started_dt else "SCAN_0000000000"

    ecus: set[str] = set()
    for o in cluster:
        _collect_ecus(o.get("data") or {}, ecus)

    dtcs, by_ecu_codes = _build_dtcs(cluster, ecus)
    ecus.update(by_ecu_codes.keys())
    readiness = _build_readiness(cluster)
    mode06 = _build_mode06(cluster)
    freeze_frames = _build_freeze_frames(cluster, by_ecu_codes)
    pids = _build_pids(cluster)
    raw_coverage = _latest_coverage_obs(cluster)
    coverage = _build_coverage(raw_coverage)
    status = _coverage_status(raw_coverage)

    return {
        "id": scan_id,
        "vin": vin,
        "started": cluster[0].get("at"),
        "ended": cluster[-1].get("at"),
        "source": _build_source(cluster),
        "ecus": sorted(ecus),
        "dtcs": dtcs,
        "readiness": readiness,
        "mil": _mil_from(readiness),
        "freeze_frames": freeze_frames,
        "mode06": mode06,
        "pids": pids,
        "coverage": coverage,
        #: "complete"/"partial"/"attempt" -- see the module docstring's
        #: "Scan plan honesty" section. Only "complete" counts toward
        #: scan_plan() and gets a "Scan n" number.
        "status": status,
        #: Kept for every existing reader of this flag (templates, bench_
        #: bridge, scan_health_bridge...): True for BOTH "partial" and
        #: "attempt" -- "not a complete scan" -- read ``status`` for the
        #: three-way distinction.
        "partial": status != "complete",
        "counts": {
            "observations": len(cluster),
            "stored": len(dtcs["stored"]), "pending": len(dtcs["pending"]),
            "permanent": len(dtcs["permanent"]),
            "mode06_fail": sum(1 for r in mode06 if r.get("passed") is False),
        },
    }


def _all_scans() -> list[dict[str, Any]]:
    """Every scan across every VIN, newest first. Cached on the observations
    file's own ``(mtime, size)`` -- a new live read moves one of those and
    the cache entry falls out on its own."""
    key = _fingerprint()
    cached = _cache.get(key)
    if cached is not None:
        return cached
    scans = [_scan_from_cluster(c) for c in _clusters()]
    scans.sort(key=lambda s: s.get("started") or "", reverse=True)
    _cache.clear()  # one corpus fingerprint at a time; see cuore.services.cache's own note
    _cache[key] = scans
    return scans


# --- public read surface -----------------------------------------------------


def _assign_numbers(scans: list[dict[str, Any]]) -> None:
    """Mutates ``scans`` (one VIN's own list, any order) in place, setting
    ``"number"`` on each -- "Scan n" numbering runs oldest-to-newest (scan 1
    is the first one run this diagnosis), the opposite order the list itself
    is usually shown in. Only a ``"complete"`` scan is numbered -- a partial
    or failed-attempt scan is still listed (see the module docstring) but
    stays unnumbered (``None``), same honesty rule :func:`scan_plan` applies
    to the "Scan n of 10" chip. Centralised here (rather than left to each
    caller to recompute, as ``cuore.web.scanlog_routes`` once did only for
    the list page) so every reader of a scan dict -- the list, the detail
    page, and the diff page -- agrees on the same number for the same scan,
    never recomputed, never silently left off one reader at a time."""
    oldest_first = sorted((s for s in scans if s.get("status") == "complete"),
                         key=lambda s: s.get("started") or "")
    numbers = {s["id"]: i for i, s in enumerate(oldest_first, start=1)}
    for s in scans:
        s["number"] = numbers.get(s["id"])


def list_scans(vin: str) -> list[dict[str, Any]]:
    """Scan summaries for one VIN, newest first, each carrying its own
    "Scan n" ``number`` (``None`` when unnumbered -- see
    :func:`_assign_numbers`)."""
    scans = [s for s in _all_scans() if s["vin"] == vin]
    _assign_numbers(scans)
    return scans


def get_scan(vin: str, scan_id: str) -> Optional[dict[str, Any]]:
    return next((s for s in list_scans(vin) if s["id"] == scan_id), None)


def scan_plan(vin: str) -> dict[str, Any]:
    """``{"count", "total"}`` for the "Scan n of 10" chip (Bench and the
    scans list). Only a ``"complete"`` scan counts toward ``count`` -- a
    partial (manual-read-only, or CAN-C never answered) or a failed
    attempt (adapter not reachable) does not, so the chip never overclaims
    how many real scans have been run -- see the module docstring's "Scan
    plan honesty" section. ``total`` is :data:`PLAN_TOTAL`, a target, never
    a cap."""
    return {"count": sum(1 for s in list_scans(vin) if s.get("status") == "complete"),
           "total": PLAN_TOTAL}


# --- diff ---------------------------------------------------------------------


def _mode06_key(r: dict[str, Any]) -> tuple[str, str, str]:
    return (str(r.get("mid")), str(r.get("tid") or ""), str(r.get("ecu") or ""))


def diff(vin: str, id_a: str, id_b: str) -> Optional[dict[str, Any]]:
    """``a`` -> ``b`` delta: codes added/removed per bucket, freeze-frame PID
    value changes, Mode 06 pass/fail flips, and readiness/MIL changes.
    ``None`` if either scan does not exist for this VIN."""
    a, b = get_scan(vin, id_a), get_scan(vin, id_b)
    if a is None or b is None:
        return None

    codes: dict[str, dict[str, list[str]]] = {}
    for bucket in _DTC_KINDS:
        sa, sb = set(a["dtcs"][bucket]), set(b["dtcs"][bucket])
        codes[bucket] = {"added": sorted(sb - sa), "removed": sorted(sa - sb)}

    # Same code, different bucket (e.g. pending -> stored) -- a status
    # change, not an add/remove. A code is not expected to sit in two
    # buckets of the same scan at once; if it somehow does, the last
    # bucket in _DTC_KINDS order (permanent) wins.
    bucket_a = {c: bucket for bucket in _DTC_KINDS for c in a["dtcs"][bucket]}
    bucket_b = {c: bucket for bucket in _DTC_KINDS for c in b["dtcs"][bucket]}
    status_changes = [
        {"code": c, "before": bucket_a[c], "after": bucket_b[c]}
        for c in sorted(set(bucket_a) & set(bucket_b))
        if bucket_a[c] != bucket_b[c]
    ]

    cov_a, cov_b = a.get("coverage"), b.get("coverage")
    line_a = (cov_a or {}).get("line") or ("partial scan -- no bus-sweep coverage" if a.get("partial") else None)
    line_b = (cov_b or {}).get("line") or ("partial scan -- no bus-sweep coverage" if b.get("partial") else None)
    coverage_changes: list[dict[str, Any]] = []
    if line_a != line_b:
        coverage_changes.append({"before": line_a, "after": line_b})

    ff_a = {(f["code"], f["ecu"]): {p["pid"]: p for p in f["pids"]} for f in a["freeze_frames"]}
    ff_b = {(f["code"], f["ecu"]): {p["pid"]: p for p in f["pids"]} for f in b["freeze_frames"]}
    freeze_frame_deltas: list[dict[str, Any]] = []
    for key in sorted(set(ff_a) | set(ff_b)):
        pids_a, pids_b = ff_a.get(key, {}), ff_b.get(key, {})
        for pid in sorted(set(pids_a) | set(pids_b)):
            va = pids_a.get(pid, {}).get("value")
            vb = pids_b.get(pid, {}).get("value")
            if va != vb:
                freeze_frame_deltas.append({
                    "code": key[0], "ecu": key[1], "pid": pid,
                    "name": (pids_b.get(pid) or pids_a.get(pid) or {}).get("name"),
                    "before": va, "after": vb,
                })

    m_a = {_mode06_key(r): r.get("passed") for r in a["mode06"]}
    m_b = {_mode06_key(r): r.get("passed") for r in b["mode06"]}
    mode06_changes: list[dict[str, Any]] = []
    for key in sorted(set(m_a) | set(m_b)):
        if m_a.get(key) != m_b.get(key):
            mode06_changes.append({"mid": key[0], "tid": key[1], "ecu": key[2],
                                   "before": m_a.get(key), "after": m_b.get(key)})

    readiness_changes: list[dict[str, Any]] = []
    mon_a = {m["monitor"]: m["complete"] for m in
             ((a.get("readiness") or {}).get("since_clear") or {}).get("monitors", [])}
    mon_b = {m["monitor"]: m["complete"] for m in
             ((b.get("readiness") or {}).get("since_clear") or {}).get("monitors", [])}
    for name in sorted(set(mon_a) | set(mon_b)):
        if mon_a.get(name) != mon_b.get(name):
            readiness_changes.append({"monitor": name, "before": mon_a.get(name),
                                      "after": mon_b.get(name)})
    if a.get("mil") != b.get("mil"):
        readiness_changes.append({"monitor": "MIL", "before": a.get("mil"),
                                  "after": b.get("mil")})

    return {"a": a["id"], "b": b["id"], "codes": codes, "status_changes": status_changes,
           "freeze_frame_deltas": freeze_frame_deltas,
           "mode06_changes": mode06_changes, "readiness_changes": readiness_changes,
           "coverage_changes": coverage_changes}


# --- MES-format export ---------------------------------------------------------

_ISO_PLACEHOLDER = "00 00 00 00 00"


def _iso_bytes(ecu: str) -> str:
    """Best-effort ``XX XX XX XX XX`` from an 8-hex-char CAN header
    (``18DAF110`` -> ``18 DA F1 10 00``); the real byte meaning does not
    matter to :mod:`mes.scan` -- it only needs five hex-pair groups to
    anchor a module block (see ``ISO_CODE_RE``)."""
    hexdigits = "".join(c for c in ecu.upper() if c in "0123456789ABCDEF")
    hexdigits = (hexdigits + "0000000000")[:10]
    return " ".join(hexdigits[i:i + 2] for i in range(0, 10, 2))


def export_mes_text(scan: dict[str, Any]) -> str:
    """Render one scan as MES ``SCAN_YYMMDDHHMM.txt`` text.

    SCAN logs carry no stored/pending/permanent distinction -- that is a
    Mode 03/06/0A OBD concept, not something the "Scan vehicle" UDS report
    ever had -- so this writes the union of everything seen on each ECU
    as its one ``Errors found:`` list, the same limitation a real SCAN
    export already has. ``mes.scan.parse_scan_text`` only anchors on
    ``ISO Code:`` lines and skips anything else, so the leading provenance
    stamp and any other line here that is not part of that grammar is
    simply ignored by the parser, not an error.
    """
    lines: list[str] = [f"source: cuore live read, {scan['source'].get('stream') or 'serial COM3'}",
                        ""]

    by_ecu_codes: dict[str, set[str]] = {}
    for bucket in _DTC_KINDS:
        for code in scan["dtcs"][bucket]:
            ecus = scan["ecus"] or ["ECM"]
            target = ecus[0] if len(ecus) == 1 else None
            if target:
                by_ecu_codes.setdefault(target, set()).add(code)
            else:
                for ecu in ecus:
                    by_ecu_codes.setdefault(ecu, set()).add(code)

    ecus = scan["ecus"] or ["ECM"]
    for ecu in ecus:
        lines.append(f"Engine / {ecu}")
        lines.append(ecu)
        lines.append(f"ISO Code: {_iso_bytes(ecu) if ecu != 'ECM' else _ISO_PLACEHOLDER}")
        if scan.get("vin"):
            lines.append(f"VIN code: {scan['vin']}")
        codes = sorted(by_ecu_codes.get(ecu, set()))
        if codes:
            lines.append("Errors found:")
            for code in codes:
                lines.append(f"{code}-00")
        lines.append("")
    return "\n".join(lines)


def export_path(vin: str, scan_id: str) -> Path:
    """Where this scan's MES-format export would live, never MultiEcuScan's
    own LOG folder -- a live scan is CUORE's own evidence, not an MES log."""
    return state_dir() / "scans" / vin / f"{scan_id}.txt"


def write_mes_export(vin: str, scan_id: str) -> Optional[Path]:
    """Write the MES-format export for one scan, returning its path, or
    ``None`` if the scan does not exist for this VIN."""
    scan = get_scan(vin, scan_id)
    if scan is None:
        return None
    path = export_path(vin, scan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_mes_text(scan), encoding="utf-8")
    return path


__all__ = ["WINDOW", "PLAN_TOTAL", "list_scans", "get_scan", "scan_plan", "diff",
           "export_mes_text", "export_path", "write_mes_export"]
