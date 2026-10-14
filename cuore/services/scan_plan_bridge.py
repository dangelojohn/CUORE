"""``/v/{vin}/scan-plan`` -- the owner's ten scans, settled against one car.

:mod:`mes.scan_plan` states what each of the ten rows IS (purpose,
preconditions, what it proves, which cable) -- the same knowledge for every
car. This module is the only place that decides what each row looks like
for ONE car: done (with the scan that satisfied it and when), due (the next
one to run, with an honest note on what is and is not ready yet), or
blocked (a later row, waiting on the one above it). Nothing here is
hand-typed per VIN -- every row is derived from ``cuore.live.scanlog``'s own
grouping (:mod:`cuore.services.scanlog_bridge`), the modifications ledger
(:mod:`cuore.live.modifications`) and the shop checklist store
(:mod:`cuore.live.checklists`), the same three stores every other bridge in
this package already reads.

**Only a "complete" scan (``cuore.live.scanlog``'s own CAN-C-answered
bar) ever marks a row done.** A partial manual read or a failed COM3
attempt proves nothing about any of these ten rows, for the same reason it
does not count toward the "Scan n of 10" chip (``scanlog_bridge.scan_plan``,
read here unchanged for that chip's own count/total).

Exactly one row at a time is marked ``"due"`` (gets the Connect-to-car
button) -- the owner's own "one guided scan per visit", not a page of ten
buttons. Every not-yet-done row after it is ``"blocked"``, EXCEPT a row
whose plan entry sets ``gates: False`` (today, only "repair (if any)"):
such a row can sit at "due" without holding up the rows after it, since it
may never apply to this car at all.

Dates are the scan's own ``started`` timestamp, parsed the same tolerant
way :mod:`cuore.live.scanlog` parses it; never invented, never "proven" --
a row only ever says what is on file.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from .. import bootstrap  # noqa: F401 -- side effect: puts `mes` on sys.path
from ..live import checklists as checklist_store
from . import scanlog_bridge
from .errors import BadRequest

from mes import scan_plan as scan_plan_knowledge  # noqa: E402

try:
    from ..live import modifications as modifications_store
except Exception:  # noqa: BLE001 -- the plan page must still render
    modifications_store = None

try:
    from . import tests_bridge
except Exception:  # noqa: BLE001 -- test deep-links are a nice-to-have
    tests_bridge = None

#: EVAP monitor's own fuel window -- same figure ``dossier_bridge``/
#: ``mes.scan_plan``'s own "baseline" row text cites; not re-derived.
_FUEL_WINDOW = (15.0, 85.0)

#: ``mechanic_tests`` ids the "Test A + ESIM commanded test" row settles
#: against, and their short display names for the row's own "why" text.
_TEST_A_IDS = (("evap_test_a_esim_switch", "Test A"),
              ("esim_commanded_vent_test", "the ESIM commanded vent test"))

#: Open-work checklist step ids ``dossier_bridge.FAMILY_STEPS["network"]``
#: already defines -- "BCM supply/ground work" is exactly those two steps,
#: read here rather than re-defined.
_NETWORK_STEP_IDS = ("network-1", "network-2")

#: 1-2 weeks, read as 7 days -- the owner's own lower bound for "post-repair
#: confirmation, 1-2 weeks later".
_POST_REPAIR_MIN_DAYS = 7


def _parse_at(raw: Any) -> Optional[datetime]:
    s = str(raw or "")[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _fmt_date(dt: Optional[datetime]) -> str:
    """``"14 Oct"`` -- same day/month-abbreviation convention
    ``dossier_bridge._short_date`` uses, duplicated here (small helper, not
    worth a cross-import) rather than invented fresh."""
    return dt.strftime("%d %b") if dt else ""


def _fuel_pids(scan: dict[str, Any]) -> list[dict[str, Any]]:
    """Every "Fuel level" PID reading on file for one scan -- a freeze
    frame's own PID list is the only place :mod:`cuore.live.scanlog` puts
    one today (see that module's docstring on ``pids`` vs ``freeze_frames``)."""
    out = []
    for ff in scan.get("freeze_frames") or []:
        for p in ff.get("pids") or []:
            if p.get("name") == "Fuel level" and p.get("value") is not None:
                out.append(p)
    for p in scan.get("pids") or []:
        if p.get("name") == "Fuel level" and p.get("value") is not None:
            out.append(p)
    return out


def _latest_fuel(scans: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The newest fuel-level reading across every scan on file for this
    VIN (any status -- a clear does not drain the tank), or ``None`` if the
    car has never had one read. ``{"value", "at"}``."""
    best: Optional[dict[str, Any]] = None
    best_at: Optional[datetime] = None
    for s in scans:
        at = _parse_at(s.get("started"))
        for p in _fuel_pids(s):
            if best_at is None or (at and at > best_at):
                best, best_at = {"value": p["value"], "at": s.get("started")}, at
    return best


def _last_clear_at(vin: str) -> Optional[datetime]:
    """When this car was last cleared -- the newest ``clear_evidence``
    observation on file (``cuore.live.clear.clear_module`` writes one per
    clear; see that module's docstring). ``None`` if the car has never been
    cleared through the live link."""
    try:
        from ..live import store as live_store
    except Exception:  # noqa: BLE001
        return None
    newest: Optional[datetime] = None
    for o in live_store.recent_observations(10_000_000, vin=vin, kind="clear_evidence"):
        at = _parse_at(o.get("at"))
        if at and (newest is None or at > newest):
            newest = at
    return newest


def _mod_candidates(mods: list[dict[str, Any]], keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    out = []
    for m in mods:
        text = f"{m.get('mod_id') or ''} {m.get('free_text') or ''}".lower()
        if any(k in text for k in keywords):
            out.append(m)
    return out


def _latest_done_at(rows: list[dict[str, Any]]) -> Optional[datetime]:
    """Newest ``done_at``/``at`` across a handful of modification/checklist
    entries -- used wherever a row needs "after whatever happened last"."""
    best: Optional[datetime] = None
    for r in rows:
        at = _parse_at(r.get("done_at") or r.get("at"))
        if at and (best is None or at > best):
            best = at
    return best


def _first_scan_after(complete: list[dict[str, Any]], cutoff: Optional[datetime],
                      *, predicate=None) -> Optional[dict[str, Any]]:
    """Oldest complete scan strictly after ``cutoff`` (or any, when
    ``cutoff`` is ``None``) satisfying ``predicate`` (always, when omitted).
    ``complete`` must already be oldest-first."""
    for s in complete:
        st = _parse_at(s.get("started"))
        if cutoff is not None and (st is None or st <= cutoff):
            continue
        if predicate is not None and not predicate(s):
            continue
        return s
    return None


# --- per-row settlers ---------------------------------------------------------


def _settle_baseline(vin: str, complete: list[dict[str, Any]],
                     last_clear: Optional[datetime], fuel: Optional[dict[str, Any]]
                     ) -> dict[str, Any]:
    if last_clear is None:
        return {"status": "due", "why": "no clear on file yet -- this is the "
               "first baseline"}

    def _ok(s: dict[str, Any]) -> bool:
        since = ((s.get("readiness") or {}).get("since_clear") or {})
        if not since.get("all_complete"):
            return False
        for p in _fuel_pids(s):
            if not (_FUEL_WINDOW[0] <= p["value"] <= _FUEL_WINDOW[1]):
                return False
        return True

    s = _first_scan_after(complete, last_clear, predicate=_ok)
    if s is not None:
        return {"status": "done", "scan_id": s["id"], "date": s.get("started")}

    clear_label = f"{_fmt_date(last_clear)} clear"
    if fuel is None:
        why = f"monitors not run since the {clear_label}"
    elif _FUEL_WINDOW[0] <= fuel["value"] <= _FUEL_WINDOW[1]:
        why = f"fuel {fuel['value']:g} % ok / monitors not run since the {clear_label}"
    else:
        why = (f"fuel {fuel['value']:g} % out of the {_FUEL_WINDOW[0]:g}-"
              f"{_FUEL_WINDOW[1]:g} % window / {clear_label}")
    return {"status": "due", "why": why}


def _settle_test_a(vin: str, complete: list[dict[str, Any]],
                   checklist: dict[str, Any]) -> dict[str, Any]:
    links = [{"label": label, "href": f"/v/{vin}/tests#test-{tid}"}
            for tid, label in _TEST_A_IDS]
    entries = {}
    for tid, _label in _TEST_A_IDS:
        step = tests_bridge.step_id(tid) if tests_bridge else f"test:{tid}"
        entries[tid] = checklist.get(step) or {}
    missing = [label for tid, label in _TEST_A_IDS if not entries[tid].get("done")]
    if missing:
        return {"status": "due", "why": f"{' and '.join(missing)} not yet recorded",
               "test_links": links}
    cutoff = _latest_done_at(list(entries.values()))
    s = _first_scan_after(complete, cutoff)
    if s is not None:
        return {"status": "done", "scan_id": s["id"], "date": s.get("started"),
               "test_links": links}
    return {"status": "due", "why": "both tests recorded -- no scan taken since",
           "test_links": links}


def _settle_mod_gated(complete: list[dict[str, Any]], mods: list[dict[str, Any]],
                      keywords: tuple[str, ...], not_needed_why: str) -> dict[str, Any]:
    candidates = _mod_candidates(mods, keywords)
    if not candidates:
        return {"status": "due", "why": not_needed_why}
    cutoff = _latest_done_at(candidates)
    s = _first_scan_after(complete, cutoff)
    if s is not None:
        return {"status": "done", "scan_id": s["id"], "date": s.get("started")}
    label = f" ({_fmt_date(cutoff)})" if cutoff else ""
    return {"status": "due", "why": f"work recorded{label} -- no scan taken since"}


def _settle_verify_drive(complete: list[dict[str, Any]],
                         cutoff: Optional[datetime]) -> dict[str, Any]:
    if cutoff is None:
        return {"status": "due", "why": "needs the baseline and the repair "
               "steps above done first"}

    def _ok(s: dict[str, Any]) -> bool:
        since = ((s.get("readiness") or {}).get("since_clear") or {})
        if not since.get("all_complete"):
            return False
        if (s.get("counts") or {}).get("mode06_fail", 0):
            return False
        dtcs = s.get("dtcs") or {}
        return not (dtcs.get("stored") or dtcs.get("permanent"))

    s = _first_scan_after(complete, cutoff, predicate=_ok)
    if s is not None:
        return {"status": "done", "scan_id": s["id"], "date": s.get("started")}
    return {"status": "due", "why": "needs a drive cycle with the EVAP monitor "
           "complete, Mode $06 passing, and no code back"}


def _settle_network(complete: list[dict[str, Any]],
                    checklist: dict[str, Any]) -> dict[str, Any]:
    entries = {sid: checklist.get(sid) or {} for sid in _NETWORK_STEP_IDS}
    if not all(entries[sid].get("done") for sid in _NETWORK_STEP_IDS):
        return {"status": "due", "why": "BCM supply/ground work not yet ticked "
               "done on the open-work checklist"}
    cutoff = _latest_done_at(list(entries.values()))
    s = _first_scan_after(complete, cutoff)
    if s is not None:
        return {"status": "done", "scan_id": s["id"], "date": s.get("started")}
    return {"status": "due", "why": "BCM work done -- no scan taken since"}


def _settle_cable(complete: list[dict[str, Any]], bus_key: str,
                  cable_label: str) -> dict[str, Any]:
    def _ok(s: dict[str, Any]) -> bool:
        return bus_key in ((s.get("coverage") or {}).get("buses_attempted") or [])

    s = _first_scan_after(complete, None, predicate=_ok)
    if s is not None:
        return {"status": "done", "scan_id": s["id"], "date": s.get("started")}
    return {"status": "due", "why": f"needs the {cable_label} cable fitted and "
           "declared, then a guided scan"}


def _settle_post_repair(complete: list[dict[str, Any]],
                        cutoff: Optional[datetime]) -> dict[str, Any]:
    if cutoff is None:
        return {"status": "due", "why": "needs the verification drive-cycle "
               "read first"}
    due_after = cutoff + timedelta(days=_POST_REPAIR_MIN_DAYS)
    s = _first_scan_after(complete, due_after)
    if s is not None:
        return {"status": "done", "scan_id": s["id"], "date": s.get("started")}
    return {"status": "due", "why": "needs 1-2 weeks of normal driving since "
           "the verification read"}


def _settle_release(complete: list[dict[str, Any]],
                    cutoff: Optional[datetime]) -> dict[str, Any]:
    if cutoff is None:
        return {"status": "due", "why": "needs the post-repair confirmation "
               "first"}
    s = _first_scan_after(complete, cutoff)
    if s is not None:
        return {"status": "done", "scan_id": s["id"], "date": s.get("started")}
    return {"status": "due", "why": "post-repair confirmation done -- run the "
           "release scan to close the case record"}


def build_plan(vin: str) -> dict[str, Any]:
    """The ten rows for one VIN, in the owner's own order, plus the
    existing "Scan n of 10" chip (``scanlog_bridge.scan_plan``, unchanged --
    see that function's own docstring for what counts)."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")

    scans = scanlog_bridge.list_scans(vin)["scans"]  # newest first
    complete = sorted((s for s in scans if s.get("status") == "complete"),
                      key=lambda s: s.get("started") or "")
    last_clear = _last_clear_at(vin)
    fuel = _latest_fuel(scans)
    checklist = checklist_store.get(vin)
    try:
        mods = modifications_store.load(vin) if modifications_store else []
    except Exception:  # noqa: BLE001 -- the plan must still render
        mods = []

    rows: list[dict[str, Any]] = []
    cutoff: Optional[datetime] = None  # newest done-date among rows settled so far
    for step in scan_plan_knowledge.PLAN:
        sid = step["id"]
        if sid == "baseline":
            result = _settle_baseline(vin, complete, last_clear, fuel)
        elif sid == "test_a_esim":
            result = _settle_test_a(vin, complete, checklist)
        elif sid == "repair":
            result = _settle_mod_gated(complete, mods, ("esim", "wiring"),
                                       "no ESIM/wiring repair recorded yet -- "
                                       "skip this row if Test A found none needed")
        elif sid == "witech_flash":
            result = _settle_mod_gated(complete, mods, ("flash", "witech"),
                                       "no wiTECH flash check recorded yet")
        elif sid == "verify_drive":
            result = _settle_verify_drive(complete, cutoff)
        elif sid == "network":
            result = _settle_network(complete, checklist)
        elif sid == "body_a5":
            result = _settle_cable(complete, "can_ihs", "blue A5")
        elif sid == "chassis_a6":
            result = _settle_cable(complete, "can_ch", "grey A6")
        elif sid == "post_repair":
            result = _settle_post_repair(complete, cutoff)
        else:  # "release"
            result = _settle_release(complete, cutoff)

        if result["status"] == "done":
            dt = _parse_at(result.get("date"))
            if dt and (cutoff is None or dt > cutoff):
                cutoff = dt

        row = {**step, **result}
        rows.append(row)

    # Exactly one "due" row gets the Connect-to-car button -- the first
    # not-done row that gates the plan, or any not-done row ahead of it
    # that does not (today, only "repair (if any)"): see the module
    # docstring. Everything not-done AFTER the first gating hold-up is
    # "blocked", its own settler's "why" replaced with the sequential
    # reason so the page never shows a stale readiness note next to a
    # row the mechanic cannot act on yet anyway.
    gate_hit = False
    gate_title = None
    for row in rows:
        if row["status"] == "done":
            continue
        if gate_hit:
            row["status"] = "blocked"
            row["why"] = f'comes after "{gate_title}"'
            row.pop("test_links", None)
        else:
            row["status"] = "due"
            row["connect_href"] = f"/v/{vin}/scan"
            if row.get("gates", True):
                gate_hit = True
                gate_title = row["title"]

    return {
        "vin": vin, "rows": rows,
        "done_count": sum(1 for r in rows if r["status"] == "done"),
        "total": len(rows),
        "scan_plan": scanlog_bridge.scan_plan(vin),
    }


__all__ = ["build_plan"]
