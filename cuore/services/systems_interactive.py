"""The tappable Systems map (view model for ``_systems_interactive.html``).

One drawing of the vehicle systems this car's faults touch. Each system node is coloured (and worded) by the worst
*present* fault in it. Selecting a system lights up, on that same drawing, what it DEPENDS ON (upstream systems and
the feeds / fuses / grounds / modules / buses behind it) and the systems that SHARE A CAUSE with it, and shows one
card: its present faults, the shared-cause group with its evidence counts, the dependency chain as a readable line
("EVAP <- ECM/PCM <- ... <- Electrical supply"), and the links a mechanic needs next.

Evidence only. Nothing here invents an edge or a part:

* system -> system edges are ``mes.systems`` ``depends_on`` rows (via :mod:`systems_bridge`), with their own
  ``technical`` detail (what is carried, the element ids on the path, the bus) and their stated confidence;
* the feeds / fuses / grounds / modules on a system's chain are (a) the element ids named on those edges, (b) the
  electrical hops of the dependency path of each *present* fault in that system (:mod:`layout_bridge` ``code_path``),
  and (c) the modules ``mes.systems`` lists for the system;
* "shares a cause" is :func:`fault_similarity.groups` (a group needs a shared cause, or two independent link
  families), mapped to systems through each member code's *primary* systems (``systems_for_code``);
* fault order and status come from :mod:`fault_board` (the Faults list), so the worst fault here is the same one the
  Faults list puts first.

The base model (nodes, edges, parts, cards) is cached on the recorded data; the selection is applied on top for each
request without recomputing anything. Read-only: nothing here touches the adapter or writes state.

Public: :func:`map`.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache
from .bench_interactive import PRESENT, age_text

#: board statuses in "look at first" order, with the node class, glyph and word they get
_SEV: dict[str, tuple[int, str, str, str]] = {
    "active":    (0, "sev-act", "●", "Active now"),
    "permanent": (0, "sev-act", "●", "Permanent"),
    "pending":   (1, "sev-pend", "◐", "Pending"),
    "verifying": (2, "sev-ver", "◇", "Being verified"),
}
_HIST = (3, "sev-hist", "○", "History only")
_NONE = (4, "sev-none", "–", "No fault on record")
STATUS_WORD = {"active": "Active now", "permanent": "Permanent (Mode 0A)", "pending": "Pending",
               "verifying": "Being verified", "history": "History (not present now)",
               "proven-fixed": "Proven fixed", "resolved": "Resolved"}

#: element kinds that are dependencies (feeds, protection, grounds, modules, connectors); the system's own
#: mechanical parts (valves, tanks, hoses ...) are not what it depends on
_DEP_KINDS = {"fuse": "fuse", "battery": "battery", "ground": "ground", "module": "module", "connector": "connector",
              "harness_section": "harness"}
#: reading order of a chain: the controller, its connectors, protection, supply, then ground
_KIND_RANK = {"module": 0, "connector": 1, "harness_section": 1, "fuse": 2, "battery": 3, "ground": 4}

_CONF_WORD = {"CONFIRMED": "confirmed", "CORROBORATED": "corroborated", "SINGLE-SOURCE": "single source",
              "UNKNOWN": "unverified"}
_DASH = {"SINGLE-SOURCE": "8,5", "UNKNOWN": "2,4"}
COLS = 4
_UP_DEPTH = 3

LEGEND_SEV = [
    {"cls": "sev-act", "glyph": _SEV["active"][2], "word": "Active or permanent fault"},
    {"cls": "sev-pend", "glyph": _SEV["pending"][2], "word": "Pending fault"},
    {"cls": "sev-ver", "glyph": _SEV["verifying"][2], "word": "Fix being verified"},
    {"cls": "sev-hist", "glyph": _HIST[2], "word": "History only, nothing present now"},
    {"cls": "sev-none", "glyph": _NONE[2], "word": "No fault on record"},
]
LEGEND_REL = [
    {"cls": "rel-selected", "word": "Selected system (solid heavy outline)"},
    {"cls": "rel-dep", "word": "Depends on: upstream systems, feeds, fuses, grounds, modules, buses (dashed outline)"},
    {"cls": "rel-shared", "word": "Shares a cause with it, from the fault groups (dotted outline)"},
]
REL_WORD = {"selected": "Selected", "dep": "Depends on", "shared": "Shares a cause"}


# --- helpers -------------------------------------------------------------------------------------------

def _tok(url: str, token: str) -> str:
    if not token:
        return url
    return url + ("&" if "?" in url else "?") + "token=" + quote(token)


def _short(label: str) -> str:
    """"EVAP (evaporative emissions)" -> "EVAP"; "ECM/PCM -- Magneti Marelli IAW 10JA" -> "ECM/PCM"."""
    s = re.split(r"\s+--\s+|\s+\(", label or "", maxsplit=1)[0].strip()
    return s or (label or "")


def _graph() -> dict[str, dict[str, Any]]:
    try:
        from . import systems_bridge
        raw = systems_bridge.systems()
    except Exception:  # noqa: BLE001 -- the map must render without it
        return {}
    return raw if isinstance(raw, dict) else {s.get("key"): s for s in (raw or []) if s.get("key")}


def _elements() -> dict[str, dict[str, Any]]:
    try:
        from . import layout_bridge
        return layout_bridge.elements() or {}
    except Exception:  # noqa: BLE001
        return {}


def _cards(vin: str) -> list[dict[str, Any]]:
    try:
        from . import fault_board
        return fault_board.board(vin)
    except Exception:  # noqa: BLE001
        return []


def _groups(vin: str) -> tuple[list[dict[str, Any]], bool]:
    try:
        from . import fault_similarity
        g = fault_similarity.groups(vin)
        return g, bool(fault_similarity.is_updating(vin) or any(x.get("stale") for x in g))
    except Exception:  # noqa: BLE001
        return [], False


def _data_key(vin: str) -> Optional[tuple]:
    try:
        from . import fault_similarity
        return fault_similarity._key(vin)
    except Exception:  # noqa: BLE001
        return None


def _primary_systems(code: str, description: str, memo: dict[str, list[str]]) -> list[str]:
    if code in memo:
        return memo[code]
    try:
        from . import systems_bridge
        rows = systems_bridge.systems_for_code(code, description or "")
    except Exception:  # noqa: BLE001
        rows = []
    memo[code] = [r["system"] for r in rows if r.get("role") == "primary" and r.get("system")]
    return memo[code]


def _path_hops(code: str, memo: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if code in memo:
        return memo[code]
    try:
        from . import layout_bridge
        memo[code] = list(layout_bridge.code_path(code).get("path") or [])
    except Exception:  # noqa: BLE001
        memo[code] = []
    return memo[code]


def _canon(key: str) -> str:
    try:
        from . import layout_bridge
        return layout_bridge._SYSTEM_ALIASES.get(key, "")
    except Exception:  # noqa: BLE001
        return ""


def _upstream(key: str, graph: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every ``depends_on`` edge reachable upstream of ``key`` (breadth first, a few hops), each once."""
    out: list[dict[str, Any]] = []
    seen_sys = {key}
    frontier = [key]
    for _ in range(_UP_DEPTH):
        nxt: list[str] = []
        for k in frontier:
            for dep in (graph.get(k) or {}).get("depends_on") or []:
                to = dep.get("system")
                if not to or to not in graph:
                    continue
                tech = dep.get("technical") or {}
                out.append({"from": k, "to": to, "carries": tech.get("carries") or "", "propagates": tech.get("propagates") or "",
                            "confidence": (dep.get("confidence") or "UNKNOWN").upper(), "why": dep.get("why") or "",
                            "source": dep.get("source") or "", "path": list(tech.get("path") or []),
                            "bus": dict(tech.get("bus") or {}) or None, "tsb_refs": list(tech.get("tsb_refs") or [])})
                if to not in seen_sys:
                    seen_sys.add(to)
                    nxt.append(to)
        frontier = nxt
        if not frontier:
            break
    return out


# --- the base model -------------------------------------------------------------------------------------

def _build(vin: str, graph: dict[str, dict[str, Any]], board: list[dict[str, Any]], groups: list[dict[str, Any]],
           els: dict[str, dict[str, Any]], token: str, force_all: bool = False) -> dict[str, Any]:
    labels = {k: (s.get("label") or k) for k, s in graph.items()}
    memo_sys: dict[str, list[str]] = {}
    memo_path: dict[str, list[dict[str, Any]]] = {}
    order = {c["key"]: i for i, c in enumerate(board)}

    # faults per system (board order = the Faults list's importance order)
    faults_of: dict[str, list[dict[str, Any]]] = {}
    sys_of_card: dict[str, list[str]] = {}
    for c in board:
        if c.get("kind") != "code" or not c.get("code"):
            continue
        ks = [k for k in _primary_systems(c["code"], c.get("description") or "", memo_sys) if k in graph]
        sys_of_card[c["key"]] = ks
        for k in ks:
            faults_of.setdefault(k, []).append(c)

    def present_of(k: str) -> list[dict[str, Any]]:
        return [c for c in faults_of.get(k, []) if c.get("status") in PRESENT]

    # shared-cause groups -> per system: the groups touching it and the other systems in them
    sys_groups: dict[str, list[dict[str, Any]]] = {}
    shared_sys: dict[str, set[str]] = {}
    for g in groups:
        mem = [m for m in g.get("members") or []]
        member_sys = {m: sys_of_card.get(m, []) for m in mem}
        touched = {k for ks in member_sys.values() for k in ks}
        if not touched or int(g.get("n_present") or 0) < 1:
            continue
        for k in touched:
            sys_groups.setdefault(k, []).append(g)
            shared_sys.setdefault(k, set()).update(touched - {k})

    # systems on the drawing: those with a fault, what they depend on, what shares a cause with them
    shown: set[str] = {k for k in faults_of}
    for k in list(shown):
        shown.update(e["to"] for e in _upstream(k, graph))
        shown.update(shared_sys.get(k, set()))
    if not shown or force_all:
        shown = set(graph)
    keys = [k for k in graph if k in shown]

    deps: dict[str, dict[str, Any]] = {}
    parts: dict[str, dict[str, Any]] = {}

    def add_part(pid: str) -> None:
        if pid in parts:
            return
        el = els.get(pid) or {}
        kind = _DEP_KINDS.get(el.get("kind") or "")
        label = _short(el.get("label") or pid)
        canon = ""
        try:
            from . import layout_bridge
            canon = layout_bridge.canonical_system(el) if el else ""
        except Exception:  # noqa: BLE001
            pass
        parts[pid] = {"id": "p:" + pid, "eid": pid, "label": label, "kind": kind or el.get("kind") or "",
                      "text": label if (kind or "").lower() in label.lower() else f"{label} ({kind})",
                      "href": _tok(f"/v/{vin}/electrical?system={canon}#el-{quote(pid)}", token) if el else ""}

    for k in keys:
        up = _upstream(k, graph)
        toks: list[str] = []
        elem_ids: list[str] = []
        for e in up:
            t = "s:" + e["to"]
            if t not in toks:
                toks.append(t)
            for pid in e["path"]:
                if (els.get(pid) or {}).get("kind") in _DEP_KINDS and pid not in elem_ids:
                    elem_ids.append(pid)
            if e["bus"] and e["bus"].get("name") and "b:" + e["bus"]["name"] not in toks:
                toks.append("b:" + e["bus"]["name"])
        fault_hops: list[dict[str, Any]] = []
        for c in present_of(k):
            for h in _path_hops(c["code"], memo_path):
                hid = h.get("id")
                if hid and (h.get("kind") in _DEP_KINDS or (els.get(hid) or {}).get("kind") in _DEP_KINDS):
                    if hid not in elem_ids:
                        elem_ids.append(hid)
        mods = (graph[k].get("technical") or {}).get("modules") or []
        mod_toks: list[tuple[str, str]] = []
        for m in mods:
            code = (m.get("code") or "").strip()
            if not code:
                continue
            eid = next((i for i in (code.lower(), code.lower() + "_module") if (els.get(i) or {}).get("kind") == "module"), "")
            if eid:
                if eid not in elem_ids:
                    elem_ids.append(eid)
            else:
                toks.append("m:" + code)
                mod_toks.append((code, m.get("bus") or ""))
            if m.get("bus") and "b:" + m["bus"] not in toks:
                toks.append("b:" + m["bus"])
        elem_ids.sort(key=lambda i: _KIND_RANK.get((els.get(i) or {}).get("kind"), 9))
        for pid in elem_ids:
            add_part(pid)
            toks.append("p:" + pid)
        deps[k] = {"edges": up, "tokens": toks, "elem_ids": elem_ids, "mods_plain": mod_toks}

    # bus + plain module chips (no element behind them: shown as chips with their own sourced bus/speed)
    for k in keys:
        for e in deps[k]["edges"]:
            b = e["bus"]
            if b and b.get("name") and "b:" + b["name"] not in parts:
                parts["b:" + b["name"]] = {"id": "b:" + b["name"], "eid": "", "label": b["name"], "kind": "bus",
                                           "text": f"{b['name']} (bus, {b.get('speed') or 'speed not stated'})", "href": ""}
        for code, bus in deps[k]["mods_plain"]:
            parts.setdefault("m:" + code, {"id": "m:" + code, "eid": "", "label": code, "kind": "module",
                                            "text": f"{code} (module)", "href": ""})
        for t in deps[k]["tokens"]:
            if t.startswith("b:") and t not in parts:
                name = t[2:]
                parts[t] = {"id": t, "eid": "", "label": name, "kind": "bus", "text": f"{name} (bus)", "href": ""}
    # key the chips by their token id
    chips = []
    chips.extend(parts.values())
    chips.sort(key=lambda p: (_KIND_RANK.get(p["kind"], 9) if p["kind"] != "bus" else 8, p["label"]))

    # --- grid positions (the existing map's known cells first, compacted to the rows actually used)
    from ..web import systems_svg
    pos = systems_svg._positions(keys)
    cell: dict[str, tuple[int, int]] = {}
    for k in keys:
        x, y = pos[k]
        cell[k] = (int(round((x - systems_svg._MARGIN - systems_svg.NODE_W / 2) / systems_svg._COL_W)),
                   int(round((y - systems_svg._MARGIN - systems_svg.NODE_H / 2) / systems_svg._ROW_H)))
    rows = sorted({r for _, r in cell.values()})
    rmap = {r: i for i, r in enumerate(rows)}
    n_rows = max(1, len(rows))

    nodes: list[dict[str, Any]] = []
    for k in keys:
        pres = present_of(k)
        anyf = faults_of.get(k, [])
        worst = min(pres, key=lambda c: order.get(c["key"], 9999)) if pres else None
        if worst:
            rank, cls, glyph, word = _SEV.get(worst["status"], _SEV["pending"])
        elif anyf:
            rank, cls, glyph, word = _HIST
        else:
            rank, cls, glyph, word = _NONE
        col, row = cell[k]
        nodes.append({
            "key": k, "id": "s:" + k, "label": labels[k], "short": _short(labels[k]), "col": col + 1, "row": rmap[cell[k][1]] + 1,
            "cx": col + 0.5, "cy": rmap[cell[k][1]] + 0.5,
            "rank": rank, "cls": cls, "glyph": glyph, "word": word,
            "worst": ({"code": worst["code"], "status": worst["status"], "label": worst.get("label") or worst["code"]} if worst else None),
            "n_present": len(pres), "n_history": len(anyf) - len(pres), "deps": " ".join(deps[k]["tokens"]),
            "shared": " ".join("s:" + s for s in sorted(shared_sys.get(k, set()) & set(keys))),
            "href": _tok(f"?system={quote(k)}", token) + "#sx",
        })
    by_key = {n["key"]: n for n in nodes}
    edges = []
    for k in keys:
        for dep in graph[k].get("depends_on") or []:
            to = dep.get("system")
            if to in by_key:
                conf = (dep.get("confidence") or "UNKNOWN").upper()
                edges.append({"a": k, "b": to, "from": "s:" + k, "to": "s:" + to, "confidence": conf,
                              "conf_word": _CONF_WORD.get(conf, conf.lower()), "dash": _DASH.get(conf, ""),
                              "x1": by_key[k]["cx"], "y1": by_key[k]["cy"], "x2": by_key[to]["cx"], "y2": by_key[to]["cy"],
                              "title": f"{labels[k]} depends on {labels[to]} ({_CONF_WORD.get(conf, conf.lower())})"})

    # --- one card per shown system
    cards: dict[str, dict[str, Any]] = {}
    for k in keys:
        n = by_key[k]
        pres = present_of(k)
        pres.sort(key=lambda c: order.get(c["key"], 9999))
        faults = [{"code": c["code"], "key": c["key"], "label": c.get("label") or c["code"], "status": c["status"],
                   "status_word": STATUS_WORD.get(c["status"], c["status"]), "last_seen": c.get("last_seen") or "",
                   "age": age_text(c.get("last_seen")), "href": _tok(c.get("href") or f"/v/{vin}/code/{c['code']}", token)}
                  for c in pres]
        grp_out = []
        for g in sys_groups.get(k, []):
            members = []
            others: list[dict[str, str]] = []
            for m in g.get("members") or []:
                c = next((x for x in board if x["key"] == m), None)
                if not c:
                    continue
                msys = [s for s in sys_of_card.get(m, []) if s in by_key]
                members.append({"code": c["code"], "label": c.get("label") or c["code"], "status_word": STATUS_WORD.get(c["status"], c["status"]),
                                "systems": [labels[s] for s in msys],
                                "href": _tok(c.get("href") or "", token) if c.get("href") else ""})
                for s in msys:
                    if s != k and not any(o["key"] == s for o in others):
                        others.append({"key": s, "label": labels[s]})
            h = g.get("history") or {}
            ev = []
            els_w = [e.get("label") for e in (g.get("why_elements") or [])[:3] if e.get("label")]
            if els_w:
                ev.append("shared " + ", ".join(els_w))
            if h.get("together"):
                ev.append(f"appeared together in {h['together']} of {h['either']} reads")
            if h.get("cleared"):
                ev.append(f"cleared together {h['cleared']} time{'s' if h['cleared'] != 1 else ''}")
            grp_out.append({"id": g.get("id"), "label": g.get("label") or "Shared cause", "why": g.get("why") or "",
                            "evidence": ev or ["same system"], "n": len(members), "n_present": int(g.get("n_present") or 0),
                            "members": members, "others": others})
        d = deps[k]
        # the chain: system <- its modules/connectors/fuses/supply/grounds <- upstream systems
        chain = [{"text": n["short"], "kind": "system"}]
        for pid in d["elem_ids"]:
            p = parts[pid]
            chain.append({"text": p["label"], "kind": p["kind"], "href": p["href"]})
        for code, bus in d["mods_plain"]:
            chain.append({"text": code, "kind": "module"})
        direct = [e["to"] for e in d["edges"] if e["from"] == k]
        direct = [x for i, x in enumerate(direct) if x not in direct[:i]]
        if direct:
            chain.append({"text": ", ".join(_short(labels[x]) for x in direct), "kind": "system"})
        deeper: list[str] = []
        for e in d["edges"]:
            if e["to"] not in direct and e["to"] not in deeper:
                deeper.append(e["to"])
        for x in deeper:
            chain.append({"text": _short(labels[x]), "kind": "system"})
        dep_rows = []
        for e in d["edges"]:
            dep_rows.append({"key": e["to"], "label": labels[e["to"]], "from": labels[e["from"]], "carries": e["carries"],
                             "propagates": e["propagates"], "confidence": e["confidence"], "conf_word": _CONF_WORD.get(e["confidence"], e["confidence"].lower()),
                             "why": e["why"], "source": e["source"], "bus": (e["bus"] or {}).get("name") or "",
                             "tsb_refs": e["tsb_refs"],
                             "parts": [parts[p]["label"] for p in e["path"] if p in parts]})
        dependents = []
        for o, rec in graph.items():
            if o == k or o not in by_key:
                continue
            if any(dep.get("system") == k for dep in rec.get("depends_on") or []):
                pc = [c["code"] for c in present_of(o)]
                if pc:
                    dependents.append({"key": o, "label": labels[o], "codes": pc})
        first = pres[0]["code"] if pres else ""
        canon = _canon(k)
        path_href = _tok(f"/v/{vin}/electrical?code={quote(first)}" if first else (f"/v/{vin}/electrical?system={canon}" if canon else f"/v/{vin}/electrical"), token)
        layout_href = _tok(f"/v/{vin}/electrical?system={canon}" if canon else f"/v/{vin}/electrical", token)
        cards[k] = {"key": k, "id": "sx-card-" + k, "label": labels[k], "node": n, "faults": faults, "n_history": n["n_history"],
                    "groups": grp_out, "chain": chain, "chain_text": " ← ".join(c["text"] for c in chain),
                    "deps": dep_rows, "dependents": dependents, "path_href": path_href, "layout_href": layout_href,
                    "detail_href": _tok(f"/v/{vin}/systems/{quote(k)}", token),
                    "components": list((graph[k].get("components") or [])[:8])}

    return {"vin": vin, "n_rows": n_rows, "cols": COLS, "nodes": nodes, "edges": edges, "parts": chips, "cards": cards,
            "legend_sev": LEGEND_SEV, "legend_rel": LEGEND_REL, "token": token,
            "faulty": [k for k in keys if cards[k]["faults"] or cards[k]["n_history"]],
            "has_faults": bool(faults_of),
            "note": "" if faults_of else "No fault on this car maps to a system yet, so the full system list is shown."}


def _apply(base: dict[str, Any], system: Optional[str]) -> dict[str, Any]:
    """The selection laid over the cached base: which nodes / chips / edges carry which relation."""
    out = dict(base)
    out["selected"] = None
    dep: set[str] = set()
    shared: set[str] = set()
    if system:
        sel = base["cards"][system]
        out["selected"] = sel
        dep = set(sel["node"]["deps"].split())
        shared = set(sel["node"]["shared"].split())
    sid = "s:" + system if system else ""

    def rels(i: str) -> list[str]:
        r = []
        if i == sid:
            r.append("selected")
        if i in dep:
            r.append("dep")
        if i in shared:
            r.append("shared")
        return r

    out["nodes"] = [{**n, "rels": rels(n["id"]), "rel_text": " · ".join(REL_WORD[r] for r in rels(n["id"]))} for n in base["nodes"]]
    out["parts"] = [{**p, "rels": [r for r in rels(p["id"]) if r != "selected"],
                     "rel_text": " · ".join(REL_WORD[r] for r in rels(p["id"]) if r != "selected")} for p in base["parts"]]
    chain_sys = ({sid} | {t for t in dep if t.startswith("s:")}) if system else set()
    out["edges"] = [{**e, "on": bool(system) and e["from"] in chain_sys and e["to"] in dep} for e in base["edges"]]
    return out


def map(vin: str, system: Optional[str] = None, *, token: str = "", cards: Optional[list[dict[str, Any]]] = None,  # noqa: A001
        groups: Optional[list[dict[str, Any]]] = None, graph: Optional[dict[str, dict[str, Any]]] = None) -> Optional[dict[str, Any]]:
    """The interactive systems map for ``vin`` with ``system`` selected (None = nothing selected). Returns ``None``
    when ``system`` is not a system on this car's graph (the route turns that into a 404). ``cards`` / ``groups`` /
    ``graph`` are injection points for tests; when any is given the result is not cached."""
    g = graph if graph is not None else _graph()
    injected = cards is not None or groups is not None or graph is not None
    if system and system not in g:
        return None
    base = None
    key = None
    if not injected:
        dk = _data_key(vin)
        if dk is not None:
            key = ("systems_interactive", vin, token, dk)
    if key is not None:
        base = cache.get_or_build(key, lambda: _make(vin, g, None, None, token, cache_ok=True))
        if base.get("_updating"):
            cache._store.pop(key, None)       # similarity table still rebuilding: do not pin the interim answer
    else:
        base = _make(vin, g, cards, groups, token)
    if system and system not in base["cards"]:
        # a system on the graph but not drawn (no fault touches it): draw it anyway by rebuilding with it forced in
        base = _make(vin, g, cards, groups, token, force=system)
    return _apply(base, system)


def _make(vin: str, g: dict[str, dict[str, Any]], cards: Optional[list[dict[str, Any]]], groups: Optional[list[dict[str, Any]]],
          token: str, cache_ok: bool = False, force: Optional[str] = None) -> dict[str, Any]:
    board = cards if cards is not None else _cards(vin)
    updating = False
    if groups is None:
        groups, updating = _groups(vin)
    base = _build(vin, g, board, groups, _elements(), token, force_all=bool(force))
    base["_updating"] = updating
    return base


__all__ = ["map", "PRESENT", "REL_WORD", "STATUS_WORD"]
