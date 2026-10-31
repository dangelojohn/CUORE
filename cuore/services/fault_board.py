"""The fault board: one card per distinct fault (a DTC on a module, or an open symptom).

Data side of the Job page's fault board. Pure readers over what CUORE already holds -- MES log history
(``jobs_bridge._cached_workup``), from-car live reads (``observations.jsonl`` via ``cache``), the repair
log (``mes.jobs``), symptoms and "resolved" notes (``mes.symptoms`` / ``mes.notes``), and the cached
shared-cause / suspect ranking (``suspect_ranking.diagnose``). Nothing here talks to the car.

Every claim on a card carries the ids of the records behind it (``card["evidence"]``): ``obs:module_dtcs:ECM@<at>``,
``obs:obd_dtcs:permanent@<at>``, ``obs:readiness@<at>``, ``log:<file>``, ``job:<job>:action:<id>``,
``symptom:<id>``, ``note:<id>``, ``cc:<cause>``, ``hyp:<id>``.

"Fixed" is a claim, not a result. :func:`mark_fixed` appends a ``repair`` action (reversible with
:func:`undo_fixed`, which retracts it) and the card goes to ``verifying``. ``proven-fixed`` is only ever
computed (:func:`_verify`): the code must be absent in a from-car read taken after the repair (and after
any clear that followed it, once the car has done enough warm-ups); for an emissions code the relevant
readiness monitor must be complete first and no permanent (Mode 0A) code may remain. If the code fails
again after the repair the card goes back to its live status, flagged ``returned_after_fix`` and counted
-- a learning signal. A symptom has no measurement behind it, so marking it fixed adds the existing
"resolved" note (tag ``resolved``, naming the symptom id) and nothing more.

The ordering rules live in ``cuore/data/fault_priority.json`` (heuristic, adjustable).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache
from ..live import read_state
from .errors import BadRequest, NotFound

PRIORITY_FILE = Path(__file__).resolve().parent.parent / "data" / "fault_priority.json"

STATUS_LABELS = {
    "active": "Active now", "pending": "Pending", "permanent": "Permanent",
    "history": "Stored history", "verifying": "Verifying fix",
    "proven-fixed": "Proven fixed", "resolved": "Resolved",
}
#: A mark next to the word so a status is never colour-only.
STATUS_MARKS = {
    "active": "●", "pending": "◐", "permanent": "■", "history": "○",
    "verifying": "◔", "proven-fixed": "✓", "resolved": "✓",
}
STATUS_ORDER = ["permanent", "active", "pending", "verifying", "history", "proven-fixed", "resolved"]
SORTS = ("importance", "newest", "oldest", "longest-present", "system", "code")
GROUPS = ("none", "related", "system", "status", "tiers")
FIXED_MARKER = "Marked fixed by mechanic"
_HEADER_MODULE = {"18DAF110": "ECM", "18DAF118": "TCM"}
_SYSTEM_BY_LETTER = {"P": "Powertrain", "C": "Chassis", "B": "Body", "U": "Network"}
_POSITIVE = ("active", "pending", "stored", "history", "cleared")


# --- small helpers -------------------------------------------------------------

def table() -> dict[str, Any]:
    """The priority table, re-read when the file changes."""
    st = PRIORITY_FILE.stat()
    return cache.get_or_build(("fault_priority", st.st_mtime_ns, st.st_size),
                              lambda: json.loads(PRIORITY_FILE.read_text(encoding="utf-8")))


def _n(ts: Any) -> str:
    """Normalise any timestamp to ``YYYY-MM-DDTHH:MM:SS`` so strings compare in time order."""
    s = str(ts or "").strip().replace(" ", "T")
    if len(s) == 10:
        s += "T00:00:00"
    elif len(s) == 16:
        s += ":00"
    return s[:19]


def _dt(ts: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(_n(ts))
    except ValueError:
        return None


def _plus(ts: str, minutes: float) -> str:
    d = _dt(ts)
    return (d + timedelta(minutes=minutes)).isoformat(timespec="seconds") if d else ts


def _base(code: str) -> str:
    return (code or "").strip().upper().split("-")[0]


def _clip(text: str, n: int = 200) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(" ,;:-(") + "..."


def _short_module(mods: list[str]) -> str:
    for m in mods or []:
        if " / " in m:
            return re.split(r"[ (]", m.split(" / ", 1)[1].strip())[0]
    for m in mods or []:
        low = m.lower()
        if "abs" in low:
            return "ABS"
        if "injection" in low or "engine" in low:
            return "ECM"
    return (mods[0] if mods else "") or "?"


def _from_car(o: dict[str, Any]) -> bool:
    s = str(o.get("stream") or "")
    return s.startswith("serial") or s.startswith("recording(serial")


def _state_of(flags: dict[str, Any]) -> Optional[str]:
    if flags.get("testFailed"):
        return "active"
    if flags.get("pendingDTC"):
        return "pending"
    if flags.get("confirmedDTC"):
        return "stored"
    if flags.get("testFailedSinceLastClear"):
        return "history"
    return None


def _ago(days: int) -> str:
    if days <= 0:
        return "today"
    return "1 day ago" if days == 1 else f"{days} days ago"


# --- facts (cached): everything that does not depend on who pressed Fixed -------

def _live_reads(vin: str) -> dict[str, Any]:
    """From-car module / OBD / readiness reads for this VIN. An untagged read (vin "") counts only when it sits
    within 15 minutes of a VIN-tagged module sweep -- the same session -- never on its own."""
    mod = [o for o in cache.recent_observations(10**7, kind="module_dtcs") if _from_car(o)]
    anchors = sorted(_n(o.get("at")) for o in mod if o.get("vin") == vin)

    def mine(o: dict[str, Any]) -> bool:
        if o.get("vin") == vin:
            return True
        if o.get("vin"):
            return False
        at = _n(o.get("at"))
        lo, hi = _plus(at, -15), _plus(at, 15)
        return any(lo <= a <= hi for a in anchors)

    return {
        "module": [o for o in mod if mine(o)],
        "obd": [o for o in cache.recent_observations(10**7, kind="obd_dtcs") if _from_car(o) and mine(o)],
        "readiness": [o for o in cache.recent_observations(10**7, kind="readiness") if _from_car(o) and mine(o)],
    }


def _clear_events(vin: str, log_clears: list[tuple[str, str, str]], modules: set[str],
                  cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Merged clear events: ``clear`` actions from every job of this VIN plus log sessions that ended with the code
    cleared. ``scope`` is the set of modules the text names (None = unknown, applies to all)."""
    from mes import jobs as jobs_mod
    raw: list[dict[str, Any]] = []
    for j in jobs_mod.load(vin):
        for a in j.get("actions") or []:
            if a.get("kind") != "clear" or (a.get("text") or "").startswith("DESCRIPTIVE ENTRY"):
                continue
            ts = _n((a.get("effective_date") or {}).get("date") if isinstance(a.get("effective_date"), dict)
                    else a.get("event_date") or a.get("at"))
            text = a.get("text") or ""
            scope = {m for m in modules if re.search(rf"\b{re.escape(m)}\b", text)} or None
            raw.append({"ts": ts, "scope": scope, "ids": [f"job:{j['id']}:action:{a['id']}"]})
    for ts, module, fid in log_clears:
        raw.append({"ts": _n(ts), "scope": {module}, "ids": [f"log:{fid}"]})
    raw.sort(key=lambda e: e["ts"])
    merged: list[dict[str, Any]] = []
    gap = float(cfg.get("clear_merge_minutes", 90))
    for e in raw:
        if merged and e["ts"] <= _plus(merged[-1]["ts"], gap):
            m = merged[-1]
            m["scope"] = None if (m["scope"] is None or e["scope"] is None) else (m["scope"] | e["scope"])
            m["ids"] += e["ids"]
        else:
            merged.append({"ts": e["ts"], "scope": None if e["scope"] is None else set(e["scope"]),
                           "ids": list(e["ids"])})
    return merged


def _build_facts(vin: str) -> dict[str, Any]:
    from . import jobs_bridge
    cfg = table()
    codes: dict[tuple[str, str], dict[str, Any]] = {}
    reads: dict[tuple[str, str], list[tuple[str, str, set[str]]]] = {}   # (module, src) -> [(ts, id, codes)]
    obd_seen: set[str] = set()
    log_clears: list[tuple[str, str, str]] = []

    def entry(module: str, code: str) -> dict[str, Any]:
        return codes.setdefault((module, code), {"module": module, "code": code, "desc": "", "events": []})

    # 1. MES log history
    try:
        history = (jobs_bridge._cached_workup(vin) or {}).get("history") or {}
    except Exception:  # noqa: BLE001
        history = {}
    for bucket in ("chronic", "returned_after_clear", "seen_once"):
        for rec in history.get(bucket, []):
            base = _base(rec.get("dtc", ""))
            if not base:
                continue
            module = _short_module(rec.get("modules") or [])
            e = entry(module, base)
            e["desc"] = e["desc"] or (rec.get("descriptions") or [""])[0]
            for occ in rec.get("occurrences") or []:
                st = "cleared" if occ.get("status") == "cleared" else "stored"
                ts = _n(occ.get("timestamp"))
                e["events"].append({"ts": ts, "src": "log", "state": st, "id": f"log:{occ.get('file')}", "mil": False})
                if st == "cleared":
                    log_clears.append((ts, module, occ.get("file") or ""))

    # 2. live reads
    live = _live_reads(vin)
    for o in live["module"]:
        d = o.get("data") or {}
        if not read_state.is_read(d):  # silence is not an absent code
            continue
        module, ts = d.get("ecu") or "?", _n(o.get("at"))
        rid = f"obs:module_dtcs:{module}@{o.get('at')}"
        present: set[str] = set()
        for t in d.get("dtcs") or []:
            base = _base(t.get("code") or "")
            flags = t.get("flags") or {}
            st = _state_of(flags)
            if not base:
                continue
            present.add(base)
            e = entry(module, base)
            if st:
                e["events"].append({"ts": ts, "src": "module", "state": st, "id": rid,
                                    "mil": bool(flags.get("warningIndicatorRequested"))})
            else:
                present.discard(base)
        reads.setdefault((module, "module"), []).append((ts, rid, present))
    for o in live["obd"]:
        d = o.get("data") or {}
        kind = d.get("kind")
        if d.get("error") or kind not in ("stored", "pending", "permanent"):
            continue
        ts = _n(o.get("at"))
        rid = f"obs:obd_dtcs:{kind}@{o.get('at')}"
        by_ecu = d.get("by_ecu") or {"18DAF110": d.get("dtcs") or []}
        for hdr, lst in by_ecu.items():
            module = _HEADER_MODULE.get(hdr, f"ECU {hdr}")
            present = {_base(c) for c in lst}
            for base in present:
                obd_seen.add(base)
                entry(module, base)["events"].append(
                    {"ts": ts, "src": f"obd_{kind}",
                     "state": {"stored": "stored", "pending": "pending", "permanent": "permanent"}[kind],
                     "id": rid, "mil": False})
            reads.setdefault((module, f"obd_{kind}"), []).append((ts, rid, present))

    # 3. absence: a read of the module (or the OBD list) that did not list the code
    prefixes = tuple(cfg.get("emissions_prefixes") or [])
    for (module, code), e in codes.items():
        for src in ("module", "obd_stored", "obd_pending", "obd_permanent"):
            if src != "module" and not (code.startswith(prefixes) or code in obd_seen):
                continue
            for ts, rid, present in reads.get((module, src), []):
                if code not in present:
                    e["events"].append({"ts": ts, "src": src, "state": "absent", "id": rid, "mil": False})
        e["events"].sort(key=lambda x: (x["ts"], x["state"] == "absent"))

    # 4. readiness
    ready: list[dict[str, Any]] = []
    for o in live["readiness"]:
        d = o.get("data") or {}
        since = d.get("since_clear") or {}
        ready.append({
            "ts": _n(o.get("at")), "id": f"obs:readiness@{o.get('at')}", "mil_on": bool(since.get("mil_on")),
            "monitors": {m.get("monitor"): bool(m.get("complete")) for m in since.get("monitors") or []
                         if m.get("supported", True)},
            "all_complete": bool(since.get("all_complete")),
            "warmups": (d.get("drive_cycle_counters") or {}).get("warmups_since_clear"),
        })
    ready.sort(key=lambda r: r["ts"])

    # 5. clears
    modules = {m for m, _c in codes} | {m for m, _s in reads}
    clears = _clear_events(vin, log_clears, modules, cfg)

    # 6. symptoms + resolved notes
    from mes import symptoms as symptoms_mod, notes as notes_mod
    syms = [dict(s) for s in symptoms_mod.load(vin)]
    resolved: dict[str, str] = {}
    for n in notes_mod.load(vin):
        if n.get("hidden") or "resolved" not in [str(t).lower() for t in n.get("tags") or []]:
            continue
        for sid in re.findall(r"\b[0-9a-f]{12}\b", n.get("text") or ""):
            resolved[sid] = f"note:{n['id']}"

    # 7. shared causes and suspects (cached upstream)
    groups: dict[str, dict[str, Any]] = {}
    suspects: list[dict[str, Any]] = []
    next_test: dict[str, Any] = {}
    try:
        from . import suspect_ranking
        d = suspect_ranking.diagnose(vin)
        suspects = d.get("suspects") or []
        next_test = d.get("next_test") or {}
        cc = d.get("common_cause") or {}
        found: list[tuple[int, str, str, list[str]]] = []
        for s in (cc.get("partial") or []) + [x for x in (cc.get("sets") or []) if x.get("size") == 1]:
            mem = (s.get("members") or [{}])[0]
            ids = mem.get("ids") or []
            if not ids:
                continue
            label = re.split(r"\s+\(", (mem.get("label") or ids[0]))[0].replace(" -- ", " / ")
            found.append((len(s.get("explains") or []), "cc:" + ids[0], label,
                          [f["id"] for f in s.get("explains") or []]))
        for n_, gid, label, fids in sorted(found, key=lambda x: -x[0]):
            for fid in fids:
                groups.setdefault(fid, {"id": gid, "label": label, "n": n_})
    except Exception:  # noqa: BLE001 -- the board must render without the ranking
        pass

    return {"cfg": cfg, "codes": codes, "ready": ready, "clears": clears, "symptoms": syms,
            "resolved": resolved, "groups": groups, "suspects": suspects, "next_test": next_test,
            "reads": {k: v for k, v in reads.items()}}


def _facts(vin: str) -> dict[str, Any]:
    from . import dossier_bridge, mes_bridge
    key = ("fault_board_facts", vin, mes_bridge.newest_mtime(vin), dossier_bridge._state_fingerprint())
    return cache.get_or_build(key, lambda: _build_facts(vin))


# --- per-fault derivations -----------------------------------------------------

def _current(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Status of one (module, code) from its newest evidence: ``{state, permanent, mil, event}``."""
    perm = [e for e in events if e["src"] == "obd_permanent"]
    rest = [e for e in events if e["src"] != "obd_permanent"]
    permanent = bool(perm) and perm[-1]["state"] == "permanent"
    last = rest[-1] if rest else None
    state = last["state"] if last else ("permanent" if permanent else "absent")
    mil = bool(last and last.get("mil") and state in _POSITIVE)
    return {"state": state, "permanent": permanent, "mil": mil, "event": last, "perm_event": perm[-1] if perm else None}


def _scoped_clears(facts: dict[str, Any], module: str) -> list[dict[str, Any]]:
    return [c for c in facts["clears"] if c["scope"] is None or module in c["scope"]]


def _clear_counts(events: list[dict[str, Any]], clears: list[dict[str, Any]], tol: float
                  ) -> tuple[int, int, list[str], list[str]]:
    return _clear_counts_ts(events, clears, tol)[:4]


def _clear_counts_ts(events: list[dict[str, Any]], clears: list[dict[str, Any]], tol: float
                     ) -> tuple[int, int, list[str], list[str], str]:
    """Like :func:`_clear_counts` plus the time of the newest return after a clear ("" when none)."""
    sight = [e for e in events if e["state"] in _POSITIVE or e["state"] == "permanent"]
    back = [e for e in events if e["state"] in _POSITIVE]
    prev, cleared, returned = "", 0, 0
    c_ids: list[str] = []
    r_ids: list[str] = []
    last_ret = ""
    for c in clears:
        lim = _plus(c["ts"], tol)
        if any(prev < e["ts"] <= lim for e in sight):
            cleared += 1
            prev = c["ts"]
            c_ids += c["ids"][:1]
            later = [e for e in back if e["ts"] > lim]
            if later:
                returned += 1
                r_ids.append(later[0]["id"])
                last_ret = later[0]["ts"]
    return cleared, returned, c_ids, r_ids, last_ret


def _monitor_for(code: str, cfg: dict[str, Any]) -> Optional[str]:
    best = ""
    for pre, name in (cfg.get("monitor_by_prefix") or {}).items():
        if code.startswith(pre) and len(pre) > len(best):
            best = pre
    return cfg["monitor_by_prefix"][best] if best else None


def _verify(card: dict[str, Any], events: list[dict[str, Any]], mark: dict[str, Any],
            facts: dict[str, Any], clears: list[dict[str, Any]]) -> dict[str, Any]:
    """Evidence after a fix mark. Returns ``{result: proven|verifying|returned, needs, met, evidence, ...}``."""
    cfg, tol = facts["cfg"], float(facts["cfg"].get("clear_tolerance_minutes", 5))
    t = _n(mark["at"])
    after = [e for e in events if e["ts"] > _plus(t, 2) and e["src"] != "obd_permanent"]
    clears_after = [c for c in clears if c["ts"] > t]
    cut = max([c["ts"] for c in clears_after], default=t)
    first_clear = min([c["ts"] for c in clears_after], default=None)
    code, module = card["code"], card["module"]

    failing = [e for e in after if e["state"] in ("active", "pending")]
    again = [e for e in after if first_clear and e["ts"] > _plus(first_clear, tol) and e["state"] in _POSITIVE]
    if failing or again:
        first = (failing + again)
        first.sort(key=lambda e: e["ts"])
        return {"result": "returned", "returned_at": first[0]["ts"], "evidence": [first[0]["id"]],
                "needs": [], "met": []}

    emissions = card["emissions"]
    monitor = _monitor_for(code, cfg) if emissions else None
    needs: list[str] = []
    met: list[str] = []
    ev: list[str] = []
    lo = _plus(cut, tol) if clears_after else t

    ready = [r for r in facts["ready"] if r["ts"] > cut]
    complete_at: Optional[str] = None
    if emissions:
        for r in ready:
            ok = r["monitors"].get(monitor) if monitor else r["all_complete"]
            if ok:
                complete_at = r["ts"]
                ev.append(r["id"])
                break
        if complete_at:
            met.append(f"{monitor or 'All monitors'} complete (readiness read {complete_at[:16].replace('T', ' ')})")
        else:
            needs.append(f"{monitor or 'Readiness monitors'} not complete since the "
                         f"{'clear' if clears_after else 'repair'} -- drive until it completes, then read readiness")
    if clears_after:
        need_w = int(cfg.get("min_warmups_for_proof", 3))
        w = max([r["warmups"] or 0 for r in ready], default=0)
        r_w = next((r for r in ready if (r["warmups"] or 0) >= need_w), None)
        if r_w:
            met.append(f"{w} warm-ups since the clear")
            ev.append(r_w["id"])
        else:
            needs.append(f"At least {need_w} warm-ups since the clear ({w} seen) -- read readiness after driving")
    clean_after = complete_at or lo
    clean = [e for e in events if e["state"] == "absent" and e["src"] in ("module", "obd_stored")
             and e["ts"] >= clean_after and e["ts"] > lo]
    if clean:
        met.append(f"{module} read without {code} ({clean[0]['ts'][:16].replace('T', ' ')})")
        ev.append(clean[0]["id"])
    elif not clears_after and card.get("_state") in _POSITIVE:
        needs.append(f"{code} is still stored -- nothing has cleared it since the repair; clear it, then re-read after driving")
    else:
        needs.append(f"A clean {module} read (code absent) after "
                     f"{'the monitor completes' if emissions else 'driving since the ' + ('clear' if clears_after else 'repair')}")
    if emissions:
        perm = [e for e in events if e["src"] == "obd_permanent" and e["ts"] > cut]
        if not perm:
            needs.append("A Mode 0A (permanent codes) read after the repair")
        elif perm[-1]["state"] == "permanent":
            needs.append(f"Permanent code {code} is still set -- it only clears when the car passes its own monitor")
        else:
            met.append("No permanent code")
            ev.append(perm[-1]["id"])
    return {"result": "proven" if not needs else "verifying", "needs": needs, "met": met, "evidence": ev,
            "since": t, "cleared_after": [c["ts"] for c in clears_after]}


def _proof_rule(card: dict[str, Any], cfg: dict[str, Any]) -> str:
    if card["emissions"]:
        mon = _monitor_for(card["code"], cfg)
        name = ({"Evaporative system": "EVAP", "EGR system": "EGR"}.get(mon) or mon or "readiness")
        return f"Proof: clean read after the {name} monitor completes; permanent code must clear"
    return (f"Proof: clean read after at least {cfg.get('min_warmups_for_proof', 3)} warm-ups since the clear; "
            "the code must not return")


def _rule_for(card: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    for r in sorted(cfg["rules"], key=lambda r: r["tier"]):
        m = r["match"]
        if "status" in m and card["status"] not in m["status"]:
            continue
        if m.get("safety") and not card["safety"]:
            continue
        if m.get("mil") and not card["mil"]:
            continue
        if m.get("returned_after_fix") and not card["returned_after_fix"]:
            continue
        return r
    return cfg["rules"][-1]


# --- marks (the repair log) ----------------------------------------------------

def _marks(vin: str) -> list[dict[str, Any]]:
    from mes import jobs as jobs_mod
    out = []
    for j in jobs_mod.load(vin):
        for a in j.get("actions") or []:
            ref = a.get("ref") or {}
            if a.get("kind") == "repair" and isinstance(ref, dict) and ref.get("fault_board") == "fixed":
                out.append({"action_id": a["id"], "job_id": j["id"], "at": a["at"], "key": ref.get("fault_key"),
                            "by": ref.get("by"), "before": ref.get("before"), "id": f"job:{j['id']}:action:{a['id']}"})
    out.sort(key=lambda m: m["at"])
    return out


def _job_for(vin: str, job_id: Optional[str]) -> Optional[dict[str, Any]]:
    from mes import jobs as jobs_mod
    if job_id:
        j = jobs_mod.get(job_id)
        return j if j and j.get("vin") == vin else None
    return jobs_mod.current(vin)


# --- the board -----------------------------------------------------------------

def _hyps_for(job: Optional[dict[str, Any]], code: str) -> list[dict[str, Any]]:
    out = []
    for h in (job or {}).get("hypotheses") or []:
        if h.get("deleted") or h.get("status") == "refuted":
            continue
        codes = {_base(c) for c in h.get("codes") or []}
        if code in codes or re.search(rf"\b{re.escape(code)}\b", h.get("text") or ""):
            try:
                from . import job_direct
                title = job_direct.hyp_title(h, None)
            except Exception:  # noqa: BLE001
                title = _clip(h.get("text") or "", 100)
            out.append({"id": h["id"], "title": title, "status": h.get("status"), "evidence_id": f"hyp:{h['id']}",
                        "next_test": h.get("next_test") or ""})
    return out[:3]


def _next_test(facts: dict[str, Any], code: str, hyps: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    for s in facts["suspects"]:
        if code in {_base(c) for c in s.get("codes") or []}:
            nt = (s.get("next_test") or "").strip()
            if nt:
                return {"text": _clip(nt, 220), "source": "suspect", "evidence_id": s.get("id")}
            g = facts["next_test"]
            if g and (s.get("rank") or 99) <= 6:
                return {"text": f"{g.get('name')} ({g.get('effort') or g.get('minutes')})",
                        "source": "suspect-ranking next test", "evidence_id": s.get("id")}
    for h in hyps:
        if h["next_test"]:
            return {"text": _clip(h["next_test"], 220), "source": "job hypothesis", "evidence_id": h["evidence_id"]}
    return None


def board(vin: str, job_id: Optional[str] = None, now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """One card per distinct fault, ordered by importance (rank 1 = look first)."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    now = now or datetime.now()
    facts = _facts(vin)
    cfg = facts["cfg"]
    job = _job_for(vin, job_id)
    marks = _marks(vin)
    tol = float(cfg.get("clear_tolerance_minutes", 5))
    present = set(cfg["present_statuses"])
    ready_last = facts["ready"][-1] if facts["ready"] else None
    cards: list[dict[str, Any]] = []

    for (module, code), f in facts["codes"].items():
        ev = f["events"]
        cur = _current(ev)
        sights = [e for e in ev if e["state"] in _POSITIVE or e["state"] == "permanent"]
        if not sights:
            continue
        first, last = sights[0], sights[-1]
        key = f"code:{module}:{code}"
        status = "permanent" if cur["permanent"] else {"active": "active", "pending": "pending"}.get(cur["state"], "history")
        emissions = code.startswith(tuple(cfg["emissions_prefixes"])) or any(e["src"].startswith("obd_") for e in ev)
        desc = f["desc"]
        desc_src = ""
        if not desc:
            try:
                from . import dtc_text as _printed
                _hit = _printed.lookup(code, module)
                if _hit:
                    desc, desc_src = _hit["description"], _hit["source_tag"]
            except Exception:  # noqa: BLE001 - naming is a bonus
                pass
        safety = (module.upper() in cfg["safety_modules"] or code[:1] in cfg["safety_code_prefixes"]
                  or any(k in desc.lower() for k in cfg["safety_keywords"]))
        mil = cur["mil"] or bool(emissions and ready_last and ready_last["mil_on"] and status in present)
        cleared, returned, c_ids, r_ids, last_ret = _clear_counts_ts(ev, _scoped_clears(facts, module), tol)
        fd, ld = _dt(first["ts"]), _dt(last["ts"])
        age_days = max(0, (now - fd).days) if fd else 0
        last_days = max(0, (now - ld).days) if ld else 0
        cur_ev = cur["event"]
        detail = ""
        if cur_ev:
            when = cur_ev["ts"][:16].replace("T", " ")
            word = {"active": "failing now", "pending": "pending", "stored": "stored (confirmed, not failing now)",
                    "history": "failed since last clear, not failing now", "cleared": "cleared in that session",
                    "absent": "not in the read"}[cur_ev["state"]]
            detail = f"Latest {'read' if cur_ev['src'] != 'log' else 'log'} {when}: {word}"
            if cur["permanent"]:
                detail += "; also in the permanent (Mode 0A) list"
        elif cur["permanent"]:
            detail = "In the permanent (Mode 0A) list"
        hyps = _hyps_for(job, code)
        grp = facts["groups"].get(f"code:{code}")
        card = {
            "key": key, "kind": "code", "code": code, "label": f"{code} {desc}".strip(), "module": module,
            "description_source": desc_src, "system": module, "system_kind": _SYSTEM_BY_LETTER.get(code[:1], code[:1]), "description": desc,
            "status": status, "status_detail": detail, "safety": safety, "mil": mil, "emissions": emissions,
            "permanent": cur["permanent"], "first_seen": first["ts"], "last_seen": last["ts"],
            "present_days": age_days,
            "times_cleared": cleared, "times_returned_after_clear": returned, "last_return": last_ret,
            "returned_after_fix": False, "returned_after_fix_count": 0,
            "group": ({"id": grp["id"], "label": grp["label"], "n": grp["n"]} if grp
                      else {"id": f"sys:{module}", "label": module, "n": None}),
            "next_test": _next_test(facts, code, hyps), "hypotheses": hyps,
            "verification": None, "fixed": None, "href": f"/v/{vin}/code/{code}", "_state": cur["state"],
            "evidence": {
                "status": [x for x in (cur_ev and cur_ev["id"], cur["perm_event"] and cur["perm_event"]["id"]) if x],
                "first_seen": [first["id"]], "last_seen": [last["id"]], "cleared": c_ids, "returned": r_ids,
                "group": [grp["id"]] if grp else [], "hypotheses": [h["evidence_id"] for h in hyps],
                "next_test": [(_next_test(facts, code, hyps) or {}).get("evidence_id")] if hyps or facts["suspects"] else [],
            },
        }
        card["evidence"]["next_test"] = [x for x in card["evidence"]["next_test"] if x]
        # fix marks for this fault, oldest first
        mine = [m for m in marks if m["key"] == key]
        for m in mine:
            v = _verify(card, ev, m, facts, _scoped_clears(facts, module))
            if v["result"] == "returned":
                card["returned_after_fix_count"] += 1
                card["evidence"].setdefault("returned_after_fix", []).extend(v["evidence"] + [m["id"]])
        if mine:
            m = mine[-1]
            v = _verify(card, ev, m, facts, _scoped_clears(facts, module))
            card["fixed"] = {"action_id": m["action_id"], "job_id": m["job_id"], "at": m["at"], "by": m["by"],
                             "before": m["before"], "evidence_id": m["id"]}
            if v["result"] == "returned":
                card["returned_after_fix"] = True
                card["status_detail"] = (f"Returned after the fix marked {m['at'][:16].replace('T', ' ')} "
                                         f"(seen again {v['returned_at'][:16].replace('T', ' ')}). " + card["status_detail"]).strip()
            else:
                card["status"] = "proven-fixed" if v["result"] == "proven" else "verifying"
                card["verification"] = {"rule": _proof_rule(card, cfg), "needs": v["needs"], "met": v["met"],
                                        "since": v["since"], "evidence": v["evidence"] + [m["id"]]}
                card["evidence"]["verification"] = v["evidence"] + [m["id"]]
        if card["status"] in ("active", "pending", "permanent", "history") and not card["fixed"]:
            card["proof_rule"] = _proof_rule(card, cfg)
        elif card["status"] == "verifying":
            card["proof_rule"] = card["verification"]["rule"]
        card["can_fix"] = card["status"] in ("active", "pending", "permanent", "history") or card["returned_after_fix"]
        card["can_undo"] = card["fixed"] is not None and card["status"] in ("verifying", "proven-fixed")
        cards.append(card)

    for s in facts["symptoms"]:
        sid = s["id"]
        text = (s.get("text") or "").strip()
        tags = s.get("tags") or []
        resolved_by = facts["resolved"].get(sid)
        grp = facts["groups"].get(f"symptom:{sid}")
        low = text.lower()
        safety = any(t in cfg["safety_symptom_tags"] for t in tags)   # tags only: free text mentions "brakes" while ruling them out
        mil = any(t in cfg["mil_symptom_tags"] for t in tags)
        fd = _dt(s.get("at"))
        age = max(0, (now - fd).days) if fd else 0
        status = "resolved" if resolved_by else "active"
        card = {
            "key": f"symptom:{sid}", "kind": "symptom", "code": "Symptom", "label": _clip(text, 90), "module": s.get("reporter") or "",
            "system": "Symptom", "system_kind": "Symptom", "description": text, "status": status,
            "status_detail": f"Reported by the driver; tags {', '.join(tags) or 'none'}",
            "safety": safety, "mil": mil, "emissions": False, "permanent": False,
            "first_seen": _n(s.get("at")), "last_seen": _n(s.get("at")), "present_days": age,
            "times_cleared": 0, "times_returned_after_clear": 0, "returned_after_fix": False, "returned_after_fix_count": 0,
            "group": ({"id": grp["id"], "label": grp["label"], "n": grp["n"]} if grp
                      else {"id": "sys:Symptom", "label": "Reported symptoms", "n": None}),
            "next_test": None, "hypotheses": [], "verification": None, "fixed": None, "href": None, "_state": status,
            "can_fix": status == "active", "can_undo": status == "resolved" and _own_resolved(vin, sid) is not None,
            "evidence": {"status": [resolved_by] if resolved_by else [f"symptom:{sid}"], "first_seen": [f"symptom:{sid}"],
                         "last_seen": [f"symptom:{sid}"], "cleared": [], "returned": [],
                         "group": [grp["id"]] if grp else [], "hypotheses": [], "next_test": []},
        }
        cards.append(card)

    _finish(cards, cfg, now)
    return cards


def _finish(cards: list[dict[str, Any]], cfg: dict[str, Any], now: datetime) -> None:
    for c in cards:
        rule = _rule_for(c, cfg)
        c["status_label"] = STATUS_LABELS[c["status"]]
        c["status_mark"] = STATUS_MARKS[c["status"]]
        c["importance"] = {"tier": rule["tier"], "rule": rule["id"], "name": rule["name"],
                           "reason": f"{rule['name']}: {rule['rationale']}", "label": cfg.get("label", "heuristic, adjustable")}
        d = c["present_days"]
        if c["kind"] == "symptom":
            c["present_text"] = f"reported {_ago(d)}"
            if c["status"] == "active":   # a driver report has no test behind it: never "Test failing"
                c["status_label"] = "Reported by the driver \u00b7 not resolved"
                c["importance"]["reason"] = "Driver report, no test behind it; ranks with the active faults."
        elif c["status"] in ("active", "pending", "permanent"):
            lr = _dt(c.get("last_return"))
            if c["times_cleared"] and lr:
                since = max(0, (now - lr).days)
                c["present_text"] = f"first seen {d} d ago \u00b7 present since {lr.date().isoformat()} ({since} d)"
            elif c["times_cleared"]:
                c["present_text"] = f"first seen {d} d ago"
            else:
                c["present_text"] = f"present {d} d"
        else:
            ld = _dt(c["last_seen"])
            c["present_text"] = f"last seen {_ago(max(0, (now - ld).days) if ld else 0)}"
        c["last_seen_ago"] = _ago(max(0, (now - (_dt(c["last_seen"]) or now)).days))
        c["cleared_text"] = (f"cleared {c['times_cleared']}×, returned {c['times_returned_after_clear']}×"
                             if c["times_cleared"] else "never cleared")
        ls = _dt(c["last_seen"])
        c["_ls"] = ls.timestamp() if ls else 0.0
    cards.sort(key=lambda c: (c["importance"]["tier"], -c["_ls"], -c["times_returned_after_clear"], c["code"], c["module"]))
    for i, c in enumerate(cards, 1):
        c["rank"] = i
    # Related: the other members of a shared-cause group (a module-only fallback group is not "related").
    members: dict[str, list[dict[str, Any]]] = {}
    for c in cards:
        if c["group"]["id"].startswith("cc:"):
            members.setdefault(c["group"]["id"], []).append(c)
    for c in cards:
        c["related"] = None
        names: list[str] = []
        for m in members.get(c["group"]["id"], []):
            nm = "symptom" if m["kind"] == "symptom" else m["code"]
            if m is not c and nm != c["code"] and nm not in names:
                names.append(nm)
        if names:
            c["related"] = {"codes": names[:3], "more": max(0, len(names) - 3), "label": c["group"]["label"]}


# --- sorting and grouping ------------------------------------------------------

def sort_by(cards: list[dict[str, Any]], how: str = "importance") -> list[dict[str, Any]]:
    how = how if how in SORTS else "importance"
    imp = lambda c: c["rank"]  # noqa: E731  (rank = priority tier, then most recent first)
    if how == "newest":
        return sorted(cards, key=lambda c: (-c["_ls"], imp(c)))
    if how == "oldest":
        return sorted(cards, key=lambda c: (c["first_seen"] or "~", imp(c)))
    if how == "longest-present":
        return sorted(cards, key=lambda c: (-c["present_days"], imp(c)))
    if how == "system":
        return sorted(cards, key=lambda c: (c["system"].lower(), imp(c)))
    if how == "code":
        return sorted(cards, key=lambda c: (c["code"], c["module"]))
    return sorted(cards, key=imp)


_TIER_ORDER = ["now", "history", "resolved"]
_TIER_LABELS = {"now": "Work on now", "history": "History", "resolved": "Resolved / proven fixed"}


def tier_of(c: dict[str, Any]) -> str:
    """The default board's three folds: what to work on now, stored history, closed."""
    if c["status"] in ("active", "pending", "permanent", "verifying") or c.get("returned_after_fix"):
        return "now"
    return "history" if c["status"] == "history" else "resolved"


def group_by(cards: list[dict[str, Any]], how: str = "none") -> list[dict[str, Any]]:
    """Groups of the (already sorted) cards. Each group: ``{id, label, cards, count, active, open}``. ``open`` is
    True when the group holds an active / pending / permanent / verifying fault or a safety fault."""
    how = how if how in GROUPS else "none"
    order: list[str] = []
    buckets: dict[str, dict[str, Any]] = {}
    for c in cards:
        if how == "related":
            gid, label = c["group"]["id"], c["group"]["label"]
        elif how == "system":
            gid, label = "system:" + c["system"], c["system"] + (f" ({c['system_kind']})" if c["kind"] == "code" else "")
        elif how == "status":
            gid, label = "status:" + c["status"], STATUS_LABELS[c["status"]]
        elif how == "tiers":
            gid = tier_of(c)
            label = _TIER_LABELS[gid]
        else:
            gid, label = "all", "All faults"
        if gid not in buckets:
            buckets[gid] = {"id": gid, "label": label, "cards": []}
            order.append(gid)
        buckets[gid]["cards"].append(c)
    out = []
    for gid in order:
        g = buckets[gid]
        cs = g["cards"]
        g["count"] = len(cs)
        g["active"] = sum(1 for c in cs if c["status"] in ("active", "pending", "permanent"))
        g["open"] = any(c["status"] in ("active", "pending", "permanent", "verifying") or (c["safety"] and c["status"] == "history")
                        for c in cs)
        if how == "tiers":
            g["open"] = g["id"] == "now"
            g["summary"] = f"{g['label']} \u2014 {g['count']}"
            out.append(g)
            continue
        g["summary"] = (f"{g['label']} — {g['count']} fault{'s' if g['count'] != 1 else ''}"
                        + (f" · {g['active']} active" if g["active"] else ""))
        out.append(g)
    if how == "tiers":
        out.sort(key=lambda g: _TIER_ORDER.index(g["id"]))
    elif how in ("related", "system"):
        # highest-priority member first, then the group whose most recent member is newest
        out.sort(key=lambda g: (min(c["importance"]["tier"] for c in g["cards"]), -max(c["_ls"] for c in g["cards"])))
    elif how == "status":
        out.sort(key=lambda g: STATUS_ORDER.index(g["id"][7:]))
    return out


def public(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """JSON-safe copies (drops private sort helpers)."""
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in cards]


# --- Fixed / Undo --------------------------------------------------------------

def _own_resolved(vin: str, sid: str) -> Optional[str]:
    from mes import notes as notes_mod
    for n in reversed(notes_mod.load(vin)):
        if (not n.get("hidden") and "resolved" in [str(t).lower() for t in n.get("tags") or []]
                and sid in (n.get("text") or "") and FIXED_MARKER in (n.get("text") or "")):
            return n["id"]
    return None


def _before_ids(card: dict[str, Any]) -> list[str]:
    ids = list(card["evidence"].get("status") or []) + list(card["evidence"].get("last_seen") or [])
    out: list[str] = []
    for i in ids:
        if i not in out:
            out.append(i)
    return out[:4]


def mark_fixed(vin: str, fault_key: str, job_id: Optional[str] = None, by: Optional[str] = None) -> dict[str, Any]:
    """Record "the mechanic says fixed". Code: a ``repair`` action on the job (card -> verifying). Symptom: the
    existing "resolved" note. Idempotent while an unretracted mark exists."""
    from . import jobs_bridge, mes_bridge
    card = next((c for c in board(vin, job_id) if c["key"] == fault_key), None)
    if card is None:
        raise NotFound(f"no fault {fault_key!r} on the board for {vin!r}")
    if card["kind"] == "symptom":
        sid = fault_key.split(":", 1)[1]
        existing = _own_resolved(vin, sid)
        if existing or card["status"] == "resolved":
            return {"fault_key": fault_key, "status": "resolved", "note_id": existing, "already": True}
        note = mes_bridge.add_note(vin, f"{FIXED_MARKER}: symptom {sid} -- {_clip(card['description'], 120)}",
                                   "vehicle", author=by or "mechanic", tags=["resolved"])
        return {"fault_key": fault_key, "status": "resolved", "note_id": note["id"], "already": False}
    if card["fixed"] and card["status"] in ("verifying", "proven-fixed"):
        return {"fault_key": fault_key, "status": card["status"], "action_id": card["fixed"]["action_id"], "already": True}
    job = _job_for(vin, job_id)
    if job is None:
        raise BadRequest("no open job to record the repair on -- open a job first")
    ref = {"kind": "code", "id": card["code"], "label": card["label"], "fault_board": "fixed", "fault_key": fault_key,
           "module": card["module"], "by": by, "status_before": card["status"],
           "before": {"read_ids": _before_ids(card), "last_seen": card["last_seen"],
                      "recorded_at": datetime.now().isoformat(timespec="seconds")}}
    act = jobs_bridge.add_action(job["id"], "repair", f"{FIXED_MARKER}: {card['label']}", ref=ref)
    return {"fault_key": fault_key, "status": "verifying", "action_id": act["id"], "job_id": job["id"],
            "rule": _proof_rule(card, table()), "already": False}


def undo_fixed(vin: str, fault_key: str, job_id: Optional[str] = None, by: Optional[str] = None) -> dict[str, Any]:
    """Take the mark back: retract the repair action (code) or hide the resolved note (symptom). Append-only."""
    from . import jobs_bridge, mes_bridge
    if fault_key.startswith("symptom:"):
        nid = _own_resolved(vin, fault_key.split(":", 1)[1])
        if not nid:
            raise NotFound("no fault-board 'resolved' note to undo for that symptom")
        mes_bridge.hide_note(nid)
        return {"fault_key": fault_key, "status": "active", "note_id": nid}
    mine = [m for m in _marks(vin) if m["key"] == fault_key]
    if not mine:
        raise NotFound(f"no fixed mark on {fault_key!r} to undo")
    m = mine[-1]
    jobs_bridge.retract_action(m["job_id"], m["action_id"], "undone by mechanic", by=by)
    return {"fault_key": fault_key, "retracted": m["action_id"], "job_id": m["job_id"]}


def _similar_groups(vin: str, cards: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Similarity groups (``fault_similarity.groups``) and whether they are stale / being rebuilt. Sets ``c["sim"]``
    on every card: up to 3 other member codes, ``more``, and the group label (``None`` for a fault in no group).
    Never raises; the page renders without it."""
    for c in cards:
        c["sim"] = None
        c["sim_group"] = None
    try:
        from . import fault_similarity
        groups = fault_similarity.groups(vin)
        updating = fault_similarity.is_updating(vin) or any(g.get("stale") for g in groups)
    except Exception:  # noqa: BLE001
        return [], False
    by_key = {c["key"]: c for c in cards}
    for g in groups:
        mem = [by_key[k] for k in g["members"] if k in by_key]
        for c in mem:
            names: list[str] = []
            for m in mem:
                nm = "symptom" if m["kind"] == "symptom" else m["code"]
                if m is not c and nm not in names and nm != c["code"]:
                    names.append(nm)
            c["sim_group"] = g["id"]
            c["sim"] = {"codes": names[:3], "more": max(0, len(names) - 3), "label": g["label"]}
    return groups, updating


def _why_line(g: dict[str, Any]) -> str:
    """"shared Fuse F82, Frame ground G003A · appeared together 4 of 15 reads · cleared together 4x" -- counts of
    CUORE records from the group's own links."""
    els = [e["label"] for e in (g.get("why_elements") or [])[:3]]
    parts = ["shared " + ", ".join(els) if els else "same system"]
    h = g.get("history") or {}
    if h.get("together"):
        parts.append(f"appeared together {h['together']} of {h['either']} reads")
    if h.get("cleared"):
        parts.append(f"cleared together {h['cleared']}×")
    return " · ".join(parts)


def _related_groups(cards: list[dict[str, Any]], sim_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ?group=related view: one group per similarity group (already ordered best tier, then newest), then the
    faults that are in none. Open when a member is present now."""
    by_key = {c["key"]: c for c in cards}
    out: list[dict[str, Any]] = []
    used: set[str] = set()

    def make(gid: str, label: str, cs: list[dict[str, Any]], why: str) -> dict[str, Any]:
        n_present = sum(1 for c in cs if c["status"] in ("active", "pending", "permanent"))
        n_open = any(c["status"] in ("active", "pending", "permanent", "verifying") for c in cs)
        return {"id": gid, "label": label, "cards": cs, "count": len(cs), "active": n_present, "n_present": n_present,
                "open": n_open, "why": why,
                "summary": f"{label} — {len(cs)} fault{'s' if len(cs) != 1 else ''} · {n_present} present"}

    for g in sim_groups:
        mem = {k for k in g["members"] if k in by_key}
        cs = [c for c in cards if c["key"] in mem]      # keeps the chosen sort
        if len(cs) < 2:
            continue
        used |= mem
        out.append(make(g["id"], g["label"], cs, _why_line(g)))
    rest = [c for c in cards if c["key"] not in used]
    if rest:
        out.append(make("sim:none", "Not linked to another fault", rest, ""))
    return out


# --- page context ---------------------------------------------------------------

def fault_board_context(vin: str, job_id: Optional[str] = None, sort: str = "importance",
                        group: str = "none", return_to: str = "") -> dict[str, Any]:
    """Everything ``_fault_board.html`` needs: ``fb`` (pass it to the include as ``fb``)."""
    sort = sort if sort in SORTS else "importance"
    group = group if group in GROUPS else "none"
    cards = sort_by(board(vin, job_id), sort)
    sim_groups, sim_updating = _similar_groups(vin, cards)
    groups = _related_groups(cards, sim_groups) if group == "related" else group_by(cards, group)
    for c in cards:
        c["group_lead"] = None
        c["group_first"] = False
    if group == "tiers":
        # Show a shared group's next test / hypotheses once: on its first card; the other members point to it.
        lead: dict[str, dict[str, Any]] = {}
        for g in groups:
            for c in g["cards"]:
                gid = c["group"]["id"]
                if gid.startswith("cc:") and c["related"]:
                    if gid in lead:
                        c["group_lead"] = {"key": lead[gid]["key"], "code": lead[gid]["code"]}
                    else:
                        lead[gid] = c
                        c["group_first"] = True
    present = [c for c in cards if c["status"] in ("active", "pending", "permanent")]
    codes_p = [c["code"] + " (" + c["status"] + ")" for c in present if c["kind"] == "code"]
    n_sym = sum(1 for c in present if c["kind"] == "symptom")
    parts = codes_p + ([f"{n_sym} symptom{'s' if n_sym != 1 else ''}"] if n_sym else [])
    present_line = (f"{len(present)} present now: " + ", ".join(parts)) if present else "Nothing present now"
    return {"vin": vin, "job_id": job_id or "", "sort": sort, "group": group, "sorts": SORTS,
            "groups_choices": ("tiers", "none", "related", "system", "status"), "present_line": present_line,
            "groups": groups, "total": len(cards), "sim_updating": sim_updating,
            "n_active": sum(1 for c in cards if c["status"] in ("active", "pending", "permanent")),
            "n_verifying": sum(1 for c in cards if c["status"] == "verifying"),
            "return_to": return_to or f"/v/{vin}/job",
            "priority_label": table().get("label", "heuristic, adjustable")}


__all__ = ["board", "sort_by", "group_by", "public", "mark_fixed", "undo_fixed", "fault_board_context",
           "table", "SORTS", "GROUPS", "STATUS_LABELS"]
