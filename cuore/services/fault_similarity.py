"""Similar faults: which other faults share a cause (or a system, a bulletin, a read, a clear, a condition)
with this one, so the top issue is worked on together with everything that shares its cause.

Evidence only. A link is a *kind* (below) plus the ids / counts behind it; there is no similarity score.
Faults are ordered by how many distinct link kinds they share with the subject, then by most recent.

Link kinds
----------
``shared_cause``      both depend on the same dependency-graph element(s) (``common_cause.gather_faults`` chains;
                      an element that every covered fault depends on is left out when four or more faults are
                      covered, because it separates nothing -- the count is reported in ``omitted_universal``)
``same_module``       reported by the same module (ECM, BCM ...)
``same_system``       share a primary system in the systems graph
``same_bulletin``     a TSB (``tsb_xref_bridge`` ``by_code``) names both codes
``co_occurrence``     present in the same read / log session: "same read N of M times either appeared" (N >= 2);
                      reads holding more than half of all faults (whole-car scans) are not counted
``cleared_together``  cleared by the same clear event (``returned_together`` when both also came back after it);
                      clears that took out more than half of all faults are not counted
``same_conditions``   an intermittent band (e.g. engine cold, battery low) that holds for both, each with >= 3
                      recorded set events (``intermittent.analyze``)

Outside facts: none are used. Every number is a count of CUORE records.

Public: :func:`similar`, :func:`groups`, :func:`error_note`. Both are cached on the input stores' mtimes (MES
logs, CUORE state files, weights / priority tables) and never raise.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache

KINDS = ("shared_cause", "same_system", "same_module", "same_bulletin", "co_occurrence",
         "cleared_together", "returned_together", "same_conditions")
#: kinds that can never be counted twice for one pair
#: Co-occurrence and cleared-together are one family for grouping: a clear-all followed by one scan produces both
#: for every pair of faults, so together they count once toward the two-kind rule. ``same_module`` counts for
#: nothing there (every fault of a module has it), though it is still shown by :func:`similar`.
_FAMILY = {"shared_cause": "cause", "same_system": "structure", "same_module": None,
           "same_bulletin": "structure", "co_occurrence": "history", "cleared_together": "history",
           "returned_together": "history", "same_conditions": "conditions"}
_MIN_COOCCUR = 2
_MIN_COND_EVENTS = 3
_MAX_IDS = 6
_NOTE = {"error": ""}
_KIND_ORDER = {"fuse": 0, "ground": 1, "connector": 2, "harness_section": 3, "harness": 3}
_MAX_SPLITS = 6
_PHRASE_KIND = {"fuse": 0, "connector": 1, "harness_section": 2, "harness": 2, "ground": 3}

# Stale-while-revalidate: the last finished table per VIN, and a single background rebuild at a time.
_LAST: dict[str, tuple[tuple, dict[str, Any]]] = {}
_building: set[str] = set()
_build_lock = threading.Lock()
# intermittent.analyze per (vin, code, data key): a rebuild (e.g. after a changed weights file) never re-runs it
# for unchanged data.
_COND: dict[tuple, dict[str, Any]] = {}


# --- small helpers -------------------------------------------------------------

def _short(label: str) -> str:
    return re.split(r"\s+\(", label or "")[0].replace(" -- ", " / ")


def _positive(e: dict[str, Any]) -> bool:
    return e["state"] in ("active", "pending", "stored", "history", "cleared")


def _cause_nodes(vin: str) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, dict[str, dict[str, Any]]], int]:
    """(element nodes by fault id, primary-system nodes by fault id, number of covered faults)."""
    from . import common_cause
    els: dict[str, dict[str, dict[str, Any]]] = {}
    sys_: dict[str, dict[str, dict[str, Any]]] = {}
    try:
        faults = common_cause.gather_faults(vin)
    except Exception:  # noqa: BLE001
        return {}, {}, 0
    covered = 0
    for f in faults:
        nodes = common_cause._nodes_of(f)
        if nodes:
            covered += 1
        els[f["id"]] = {k: v for k, v in nodes.items() if v["level"] == "element"}
        sys_[f["id"]] = {k: v for k, v in nodes.items() if v["level"] == "system" and v.get("role") == "primary"}
    return els, sys_, covered


def _clear_sets(events: list[dict[str, Any]], clears: list[dict[str, Any]], tol: float, plus) -> tuple[set[str], set[str]]:
    """Which clear events (by ts) cleared this fault / which it came back after. Same rule as
    ``fault_board._clear_counts`` but keeping the identities."""
    sight = [e for e in events if _positive(e) or e["state"] == "permanent"]
    back = [e for e in events if _positive(e)]
    prev = ""
    cleared: set[str] = set()
    returned: set[str] = set()
    for c in clears:
        lim = plus(c["ts"], tol)
        if any(prev < e["ts"] <= lim for e in sight):
            cleared.add(c["ts"])
            prev = c["ts"]
            if any(e["ts"] > lim for e in back):
                returned.add(c["ts"])
    return cleared, returned


# --- the build -----------------------------------------------------------------

def _build(vin: str) -> dict[str, Any]:
    from . import fault_board as fb, intermittent, tsb_xref_bridge
    cards = fb.board(vin)
    facts = fb._facts(vin)
    cfg = facts["cfg"]
    present = set(cfg["present_statuses"])
    tol = float(cfg.get("clear_tolerance_minutes", 5))
    by_key = {c["key"]: c for c in cards}

    # per-fault records used by the pair checks
    reads: dict[str, set[str]] = {}          # fault key -> read ids it was present in
    cleared: dict[str, set[str]] = {}
    returned: dict[str, set[str]] = {}
    for (module, code), f in facts["codes"].items():
        key = f"code:{module}:{code}"
        if key not in by_key:
            continue
        ev = f["events"]
        reads[key] = {e["id"] for e in ev if _positive(e)}
        cl, rt = _clear_sets(ev, fb._scoped_clears(facts, module), tol, fb._plus)
        cleared[key], returned[key] = cl, rt

    # A read or a clear that involved more than half of all faults (a whole-car scan, a clear-all) says nothing
    # about which faults belong together, so it is not counted; the number ignored is reported in the evidence.
    half = len(by_key) / 2
    width: dict[str, int] = {}
    for rs in reads.values():
        for r in rs:
            width[r] = width.get(r, 0) + 1
    cwidth: dict[str, int] = {}
    for cs in cleared.values():
        for c in cs:
            cwidth[c] = cwidth.get(c, 0) + 1
    wide_reads = {r for r, n in width.items() if n > half}
    wide_clears = {c for c, n in cwidth.items() if n > half}
    for k in reads:
        reads[k] = reads[k] - wide_reads
        cleared[k] = cleared[k] - wide_clears
        returned[k] = returned[k] - wide_clears

    els, syss, n_cov = _cause_nodes(vin)
    sharers: dict[str, int] = {}
    for nodes in els.values():
        for nid in nodes:
            sharers[nid] = sharers.get(nid, 0) + 1
    covered_els = {fid: n for fid, n in els.items() if n or syss.get(fid)}
    universal = {nid for nid, k in sharers.items() if n_cov >= 4 and k >= n_cov}

    def fid(key: str) -> str:
        c = by_key[key]
        return f"code:{c['code']}" if c["kind"] == "code" else key

    # bulletins per code
    bul: dict[str, dict[str, str]] = {}
    try:
        view = tsb_xref_bridge.xref(vin)
        for code, lst in (view.get("by_code") or {}).items():
            bul[code] = {e["bulletin"]: e.get("number") or e["bulletin"] for e in lst}
    except Exception:  # noqa: BLE001
        pass

    # intermittent bands per code (only codes with >= 3 recorded set events)
    cond: dict[str, dict[tuple, dict[str, Any]]] = {}
    dkey = _data_key(vin)
    for ck in [k for k in _COND if k[0] == vin and k[2] != dkey]:
        _COND.pop(ck, None)
    for key, c in by_key.items():
        if c["kind"] != "code":
            continue
        ck = (vin, c["code"], dkey)
        r = _COND.get(ck)
        if r is None:
            try:
                r = intermittent.analyze(vin, c["code"])
            except Exception:  # noqa: BLE001
                continue
            _COND[ck] = r
        if r.get("n_events", 0) < _MIN_COND_EVENTS:
            continue
        cond[key] = {(ln["condition"], ln["band"]): ln for ln in r.get("lines") or []}

    keys = list(by_key)
    pairs: dict[str, dict[str, list[dict[str, Any]]]] = {k: {} for k in keys}
    cause_of: dict[tuple, list[dict[str, Any]]] = {}      # (a, b) -> shared element nodes

    def add(a: str, b: str, link: dict[str, Any]) -> None:
        pairs[a].setdefault(b, []).append(link)
        pairs[b].setdefault(a, []).append(link)

    for i, a in enumerate(keys):
        ca = by_key[a]
        for b in keys[i + 1:]:
            cb = by_key[b]
            # shared cause (elements)
            ea, eb = els.get(fid(a)) or {}, els.get(fid(b)) or {}
            shared = [ea[n] for n in ea if n in eb and n not in universal]
            if shared:
                shared.sort(key=lambda n: (sharers[n["id"]], n["id"]))
                cause_of[(a, b)] = shared
                labels = [_short(n["label"]) for n in shared[:3]]
                add(a, b, {"kind": "shared_cause",
                           "label": "shares " + ", ".join(labels) + (f" (+{len(shared) - 3} more)" if len(shared) > 3 else ""),
                           "evidence": {"elements": [{"id": n["id"], "label": n["label"], "kind": n.get("kind", ""),
                                                      "shared_by": sharers[n["id"]]}
                                                     for n in shared[:8]],
                                        "of_covered_faults": n_cov,
                                        "omitted_universal": len(universal)}})
            # systems / module
            sa, sb = syss.get(fid(a)) or {}, syss.get(fid(b)) or {}
            ss = [sa[n] for n in sa if n in sb]
            if ss:
                add(a, b, {"kind": "same_system", "label": "same system: " + ", ".join(n["label"] for n in ss[:3]),
                           "evidence": {"systems": [{"id": n["id"], "label": n["label"]} for n in ss]}})
            if ca["kind"] == "code" and cb["kind"] == "code" and ca["module"] and ca["module"] == cb["module"]:
                add(a, b, {"kind": "same_module", "label": f"both reported by {ca['module']}",
                           "evidence": {"module": ca["module"]}})
            # bulletin
            if ca["kind"] == "code" and cb["kind"] == "code":
                sb_ = set(bul.get(ca["code"], {})) & set(bul.get(cb["code"], {}))
                if sb_:
                    nums = sorted(bul[ca["code"]][x] for x in sb_)
                    add(a, b, {"kind": "same_bulletin", "label": "TSB " + ", ".join(nums[:3]) + " covers both",
                               "evidence": {"bulletins": [{"id": x, "number": bul[ca["code"]][x]} for x in sorted(sb_)]}})
            # co-occurrence
            ra, rb = reads.get(a, set()), reads.get(b, set())
            both = ra & rb
            if len(both) >= _MIN_COOCCUR:
                either = len(ra | rb)
                add(a, b, {"kind": "co_occurrence",
                           "label": f"appeared in the same read {len(both)} of {either} times either appeared",
                           "evidence": {"together": len(both), "either": either, "only_first": len(ra - rb),
                                        "only_second": len(rb - ra), "reads": sorted(both)[-_MAX_IDS:],
                                        "wide_reads_ignored": len(wide_reads)}})
            # clears
            cc = cleared.get(a, set()) & cleared.get(b, set())
            if cc:
                rr = returned.get(a, set()) & returned.get(b, set())
                add(a, b, {"kind": "returned_together" if rr else "cleared_together",
                           "label": (f"cleared together {len(cc)}x, returned together {len(rr)}x" if rr
                                     else f"cleared together {len(cc)}x"),
                           "evidence": {"cleared_together": len(cc), "returned_together": len(rr),
                                        "cleared_first": len(cleared[a]), "cleared_second": len(cleared[b]),
                                        "clears": sorted(cc)[-_MAX_IDS:],
                                        "wide_clears_ignored": len(wide_clears)}})
            # conditions
            if a in cond and b in cond:
                common = [k for k in cond[a] if k in cond[b]]
                if common:
                    parts = []
                    for k in common:
                        la, lb = cond[a][k], cond[b][k]
                        parts.append({"condition": k[0], "band": k[1], "phrase": la["short"],
                                      "first": f"{la['n']} of {la['m']}", "second": f"{lb['n']} of {lb['m']}"})
                    add(a, b, {"kind": "same_conditions",
                               "label": "both set when " + "; ".join(p["phrase"] for p in parts[:3]),
                               "evidence": {"conditions": parts}})

    return {"cards": {k: {"fault_key": k, "code": c["code"], "module": c["module"], "label": c["label"],
                          "status": c["status"], "last_seen": c["last_seen"], "tier": c["importance"]["tier"],
                          "ls": c["_ls"], "present": c["status"] in present}
                      for k, c in by_key.items()},
            "pairs": pairs, "cause_of": cause_of, "els": els, "sharers": sharers, "universal": universal}


def _data_key(vin: str) -> tuple:
    """The recorded data alone (MES logs + CUORE state files): what ``intermittent.analyze`` reads."""
    from . import dossier_bridge, mes_bridge
    return (mes_bridge.newest_mtime(vin), dossier_bridge._state_fingerprint())


def _key(vin: str) -> tuple:
    from . import common_cause, fault_board
    pf = 0.0
    try:
        pf = fault_board.PRIORITY_FILE.stat().st_mtime
    except OSError:
        pass
    return ("fault_similarity", vin) + _data_key(vin) + (common_cause.weights_mtime(), pf)


def _table(vin: str) -> tuple[Optional[dict[str, Any]], bool]:
    """(the pair table or ``None`` with the reason in ``_NOTE``, stale?).

    Stale-while-revalidate: when the inputs changed but a previous table exists, that table is returned at once
    (stale=True) and ONE background thread rebuilds it; the next call gets the fresh one. Only the first-ever
    call for a VIN builds synchronously."""
    vin = (vin or "").strip()
    _NOTE["error"] = ""
    if not vin:
        _NOTE["error"] = "a VIN is required"
        return None, False
    try:
        key = _key(vin)
        hit = _LAST.get(vin)
        if hit and hit[0] != key:
            _start_rebuild(vin)
            return hit[1], True
        t = cache.get_or_build(key, lambda: _build(vin))
        _LAST[vin] = (key, t)
        return t, False
    except Exception as exc:  # noqa: BLE001 -- a page must render without this
        _NOTE["error"] = f"{type(exc).__name__}: {exc}"
        return None, False


def _start_rebuild(vin: str) -> None:
    with _build_lock:
        if vin in _building:
            return
        _building.add(vin)

    def run() -> None:
        try:
            key = _key(vin)
            _LAST[vin] = (key, cache.get_or_build(key, lambda: _build(vin)))
        except Exception:  # noqa: BLE001 -- the next call reports it
            pass
        finally:
            with _build_lock:
                _building.discard(vin)

    threading.Thread(target=run, name="fault-similarity-rebuild", daemon=True).start()


def is_updating(vin: str) -> bool:
    """True while a background rebuild for ``vin`` is running."""
    with _build_lock:
        return (vin or "").strip() in _building


def error_note() -> str:
    """The reason the last :func:`similar` / :func:`groups` call returned nothing ('' when it did not fail)."""
    return _NOTE["error"]


# --- public --------------------------------------------------------------------

def similar(vin: str, fault_key: str, limit: int = 10) -> list[dict[str, Any]]:
    """Faults that share something with ``fault_key`` (``code:<module>:<code>`` or ``symptom:<id>``), most
    link kinds first, then most recently seen. Each: ``{fault_key, code, module, label, status, last_seen,
    n_kinds, links: [{kind, label, evidence}]}``. ``[]`` for an unknown key or on failure (see
    :func:`error_note`)."""
    t, stale = _table(vin)
    if not t or fault_key not in t["pairs"]:
        return []
    out = []
    for other, links in t["pairs"][fault_key].items():
        c = t["cards"][other]
        out.append(({"fault_key": other, "code": c["code"], "module": c["module"], "label": c["label"],
                     "status": c["status"], "last_seen": c["last_seen"],
                     "n_kinds": len({lk["kind"] for lk in links}), "links": links,
                     **({"stale": True, "updating": True} if stale else {})}, c["ls"]))
    out.sort(key=lambda x: (-x[0]["n_kinds"], -x[1], x[0]["fault_key"]))
    return [o for o, _ in out[:max(0, int(limit))]]


def groups(vin: str) -> list[dict[str, Any]]:
    """Connected components over strong links (>= 2 link kinds from different families -- cause, structure, history
    [co-occurrence + cleared-together count once], conditions -- or 1 kind when it is ``shared_cause``).
    Each: ``{id, label, why, members, n_present, newest, tier}``; best member's priority tier first, then
    newest. Single faults are not groups. ``[]`` on failure (see :func:`error_note`)."""
    t, stale = _table(vin)
    if not t:
        return []
    parent = {k: k for k in t["cards"]}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges: list[tuple[str, str, list[dict[str, Any]]]] = []
    for a, others in t["pairs"].items():
        for b, links in others.items():
            if a >= b:
                continue
            kinds = {lk["kind"] for lk in links}
            if len({_FAMILY[k] for k in kinds} - {None}) >= 2 or "shared_cause" in kinds:
                edges.append((a, b, links))
                parent[find(a)] = find(b)
    comps: dict[str, list[str]] = {}
    for k in t["cards"]:
        comps.setdefault(find(k), []).append(k)
    members_of = {r: m for r, m in comps.items() if len(m) > 1}
    edge_of: dict[str, list] = {}
    for a, b, links in edges:
        edge_of.setdefault(find(a), []).append((a, b, links))

    out = []
    flag = {"stale": True, "updating": True} if stale else {}
    for root, mem in members_of.items():
        edges_c = edge_of.get(root, [])
        for sub, label, why, elems in _split(t, mem, edges_c):
            cards = [t["cards"][k] for k in sub]
            sub.sort(key=lambda k: (t["cards"][k]["tier"], -t["cards"][k]["ls"], k))
            newest = max(cards, key=lambda c: c["ls"])
            hist = _history_of(sub, edges_c)
            out.append({"id": "sim:" + min(sub), "label": label, "why": why, "why_elements": elems, "history": hist, "members": sub,
                        "n": len(sub), "n_present": sum(1 for c in cards if c["present"]), "newest": newest["last_seen"],
                        "tier": min(c["tier"] for c in cards), "_ls": max(c["ls"] for c in cards), **flag})
    out.sort(key=lambda g: (g["tier"], -g["_ls"], g["id"]))
    for g in out:
        g.pop("_ls")
    return out


def _history_of(sub: list[str], edges: list) -> dict[str, int]:
    """The strongest read / clear evidence among the pairs inside a group: ``{together, either, cleared}``
    (zeros when none). Counts of CUORE records."""
    inside = set(sub)
    best = {"together": 0, "either": 0, "cleared": 0}
    for a, b, links in edges:
        if a not in inside or b not in inside:
            continue
        for lk in links:
            ev = lk["evidence"]
            if lk["kind"] == "co_occurrence" and ev["together"] > best["together"]:
                best["together"], best["either"] = ev["together"], ev["either"]
            elif lk["kind"] in ("cleared_together", "returned_together"):
                best["cleared"] = max(best["cleared"], ev["cleared_together"])
    return best


_PHRASE_ORDER = ("shared_cause", "same_bulletin", "co_occurrence", "returned_together", "cleared_together",
                 "same_conditions", "same_system")


def _phrase(lk: dict[str, Any]) -> str:
    """A short phrase for one link, from its evidence ("shared ESIM connector / harness run", "TSB 18-030-17",
    "same read 16 of 28")."""
    ev, k = lk["evidence"], lk["kind"]
    if k == "shared_cause":
        els = ev["elements"]
        pool = [x for x in els if x.get("kind") != "module"] or els          # a fuse / connector beats "the ECM"
        e = min(pool, key=lambda x: _PHRASE_KIND.get(x.get("kind", ""), 9))   # fuse, connector, harness, ground first
        return "shared " + _short(e["label"])
    if k == "same_bulletin":
        b = ev["bulletins"]
        return "TSB " + b[0]["number"] + (f" (+{len(b) - 1})" if len(b) > 1 else "")
    if k == "co_occurrence":
        return f"same read {ev['together']} of {ev['either']}"
    if k in ("cleared_together", "returned_together"):
        return f"cleared together {ev['cleared_together']}x"
    if k == "same_conditions":
        return "both set when " + ev["conditions"][0]["phrase"]
    if k == "same_system":
        return "same system: " + ev["systems"][0]["label"]
    return lk["label"]


def _evidence(lk: dict[str, Any]) -> str:
    ev, k = lk["evidence"], lk["kind"]
    if k == "shared_cause":
        return "; ".join(f"{_short(e['label'])} [{e['id']}] on {e['shared_by']} of {ev['of_covered_faults']} faults"
                         for e in ev["elements"][:4])
    if k == "same_bulletin":
        return ", ".join(f"{b['number']} [{b['id']}]" for b in ev["bulletins"][:4])
    if k == "co_occurrence":
        return (f"together {ev['together']}, only this {ev['only_first']}, only the other {ev['only_second']} "
                f"(wide reads ignored: {ev['wide_reads_ignored']})")
    if k in ("cleared_together", "returned_together"):
        return f"this fault was cleared {ev['cleared_first']}x, the other {ev['cleared_second']}x (wide clears ignored: {ev['wide_clears_ignored']})"
    if k == "same_conditions":
        return "; ".join(f"{c['condition']} {c['band']}: this {c['first']}, other {c['second']}" for c in ev["conditions"][:3])
    if k == "same_system":
        return ", ".join(x["label"] for x in ev["systems"][:3])
    return ev.get("module", "") if isinstance(ev, dict) else ""


_MIN_STRONG = 3
_HIST_ONLY = ("co_occurrence", "cleared_together", "returned_together")


def _strong(row: dict[str, Any]) -> bool:
    """>= 3 link kinds, not counting ``same_module`` (every fault of a module has it, so it separates nothing)."""
    return len({lk["kind"] for lk in row["links"]} - {"same_module"}) >= _MIN_STRONG


def strip(vin: str, fault_key: str, limit: int = 5) -> dict[str, Any]:
    """What the code page's "Similar:" strip shows: ``{faults, phrases, also, stale}``.

    ``faults`` are the similar faults with >= 3 link kinds (``same_module`` not counted), each
    ``{code, href, status, why: [{kind, label, evidence}]}``; ``phrases`` are up to 3 phrases from the TOP such
    fault's links, strongest first ("shared ESIM connector / harness run", "TSB 18-030-17", "same read 16 of 28").
    ``also`` are the other similar faults (appeared / cleared together only, or too few kinds), same item shape.
    Both empty when nothing is similar."""
    rows = similar(vin, fault_key, limit + 8)

    def item(r: dict[str, Any]) -> dict[str, Any]:
        why = [{"kind": lk["kind"], "label": lk["label"], "evidence": _evidence(lk)}
               for lk in sorted(r["links"], key=lambda x: (_PHRASE_ORDER.index(x["kind"]) if x["kind"] in _PHRASE_ORDER else 9))]
        return {"code": r["code"], "module": r["module"], "label": r["label"], "status": r["status"],
                "href": f"/v/{vin}/code/{r['code']}" if re.match(r"^[A-Z][0-9A-Z]{4,}$", r["code"] or "") else "",
                "n_kinds": r["n_kinds"], "why": why}

    strong = [r for r in rows if _strong(r)][:limit]
    rest = [r for r in rows if r not in strong]
    phrases: list[str] = []
    if strong:
        top = sorted((lk for lk in strong[0]["links"] if lk["kind"] in _PHRASE_ORDER),
                     key=lambda x: _PHRASE_ORDER.index(x["kind"]))
        for lk in top:
            ph = _phrase(lk)
            if ph not in phrases:
                phrases.append(ph)
    return {"faults": [item(r) for r in strong], "phrases": phrases[:3], "also": [item(r) for r in rest],
            "stale": bool(rows and rows[0].get("stale"))}


def _fid(t: dict[str, Any], mk: str) -> str:
    c = t["cards"][mk]
    return f"code:{c['code']}" if c["code"] != "Symptom" else mk


def _element_counts(t: dict[str, Any], mem: list[str]) -> dict[str, list]:
    """element id -> [members holding it, node] over ``mem`` (universal elements left out)."""
    count: dict[str, list] = {}
    for mk in mem:
        for nid, n in (t["els"].get(_fid(t, mk)) or {}).items():
            if nid not in t["universal"]:
                count.setdefault(nid, [0, n])[0] += 1
    return count


def _split(t: dict[str, Any], mem: list[str], edges: list) -> list[tuple[list[str], str, str, list[dict[str, Any]]]]:
    """One component -> one or more groups ``(members, label, why, elements)``.

    A component whose broadest shared element is a module (or that has none) is split by the most specific shared
    element: when >= 2 members share a fuse / ground / connector / harness run (anything that is not a module or
    system) that the rest do not, they become their own group labelled by what they share (the elements held by
    exactly that subset); the remainder keeps the broader label. Components already labelled by a specific element
    (EVAP's ESIM connector) or by a system (ABS) are left whole."""
    rest = list(mem)
    out = []
    for _ in range(_MAX_SPLITS):
        label, why, node, elems = _label(t, rest, [e for e in edges if e[0] in rest and e[1] in rest])
        coarse = node is None or (node.get("kind") or "").lower() == "module"
        spec = {nid: v for nid, v in _element_counts(t, rest).items()
                if (v[1].get("kind") or "").lower() != "module" and v[0] >= 2}
        if not coarse or not spec:
            break
        from . import common_cause
        top = max(v[0] for v in spec.values())
        nid0 = sorted((nid for nid, v in spec.items() if v[0] == top),
                      key=lambda nid: (_KIND_ORDER.get(spec[nid][1].get("kind", ""), 9),
                                       -common_cause._role_weight(spec[nid][1]["role"], spec[nid][1]["kind"]),
                                       t["sharers"][nid], nid))[0]
        sub = [mk for mk in rest if nid0 in (t["els"].get(_fid(t, mk)) or {})]
        # everything held by exactly this subset (among the members still unassigned) names it
        names = [nid for nid, v in spec.items()
                 if all(nid in (t["els"].get(_fid(t, mk)) or {}) for mk in sub) and v[0] == len(sub)]
        names.sort(key=lambda nid: (_KIND_ORDER.get(spec[nid][1].get("kind", ""), 9), t["sharers"][nid],
                                    _short(spec[nid][1]["label"]), nid))
        # one label per kind first (a fuse, then a ground), then the rest
        seen, ordered = set(), []
        for nid in names:
            k = spec[nid][1].get("kind", "")
            if k not in seen:
                seen.add(k)
                ordered.append(nid)
        ordered += [n for n in names if n not in ordered]
        lab = " / ".join(_short(spec[n][1]["label"]) for n in ordered[:2])
        sub_elems = [{"id": n, "label": _short(spec[n][1]["label"]), "kind": spec[n][1].get("kind", ""),
                      "members": len(sub), "of": len(rest)} for n in ordered[:8]]
        out.append((sub, lab, f"{len(sub)} of {len(rest)} faults ({label}) share "
                    + ", ".join(f"{e['label']} [{e['id']}] ({e['members']})" for e in sub_elems[:4])
                    + (f" (+{len(ordered) - 4} more)" if len(ordered) > 4 else ""), sub_elems))
        rest = [mk for mk in rest if mk not in sub]
        if not rest:
            break
    if len(rest) >= 2:
        label, why, _node, elems = _label(t, rest, [e for e in edges if e[0] in rest and e[1] in rest])
        out.append((rest, label, why, elems))
    return out


def _label(t: dict[str, Any], mem: list[str], edges: list) -> tuple[str, str, Optional[dict[str, Any]], list[dict[str, Any]]]:
    """The strongest shared element / system of a component, and the count behind it:
    ``(label, why, element node or None, evidence elements)``."""
    count = _element_counts(t, mem)
    if count:
        from . import common_cause
        best = max(v[0] for v in count.values())
        if best >= 2:
            tied = sorted((nid for nid, v in count.items() if v[0] == best),
                          key=lambda nid: (-common_cause._role_weight(count[nid][1]["role"], count[nid][1]["kind"]),
                                           t["sharers"][nid], nid))
            node = count[tied[0]][1]
            lab = _short(node["label"])
            if (node.get("kind") or "").lower() == "module":
                lab = "behind the " + lab.split(" / ")[0]
            more = f"; also shared: {', '.join(_short(count[x][1]['label']) for x in tied[1:4])}" if len(tied) > 1 else ""
            elems = [{"id": nid, "label": _short(count[nid][1]["label"]), "kind": count[nid][1].get("kind", ""),
                      "members": count[nid][0], "of": len(mem)} for nid in tied[:8]]
            return (lab, f"{best} of {len(mem)} faults depend on it [{tied[0]}]{more}", node, elems)
    tally: dict[str, int] = {}
    for _a, _b, links in edges:
        for lk in links:
            if lk["kind"] == "same_system":
                for s in lk["evidence"]["systems"]:
                    tally[s["label"]] = tally.get(s["label"], 0) + 1
    if tally:
        lab = max(tally.items(), key=lambda kv: (kv[1], kv[0]))
        return lab[0], f"same system in {lab[1]} link(s)", None, []
    kinds: dict[str, int] = {}
    for _a, _b, links in edges:
        for lk in links:
            kinds[lk["kind"]] = kinds.get(lk["kind"], 0) + 1
    if kinds:
        k = max(kinds.items(), key=lambda kv: (kv[1], kv[0]))[0]
        return k.replace("_", " "), f"{kinds[k]} link(s)", None, []
    return "related", "", None, []


__all__ = ["similar", "groups", "strip", "is_updating", "error_note", "KINDS"]
