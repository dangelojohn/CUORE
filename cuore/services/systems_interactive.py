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
                              "layer": _edge_layer(conf, (dep.get("technical") or {}).get("path") or [], els),
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

    issues = _issues(vin, groups, board, sys_of_card, by_key, deps, cards, els, token)
    for n in nodes:
        n["issues"] = [i["letter"] for i in issues if i["present"] and any(it["key"] == n["id"] for it in i["items"])]
    act = [i for i in issues if i["present"]]
    rank = rank_issues(act)
    guides = {i["letter"]: guide_path(issues.index(i), issues) for i in act}
    return {"vin": vin, "n_rows": n_rows, "cols": COLS, "nodes": nodes, "edges": edges, "parts": chips, "cards": cards,
            "legend_sev": LEGEND_SEV, "legend_rel": LEGEND_REL, "token": token,
            "issues_all": issues, "overlap": overlap(act), "overlap_all": overlap(issues),
            "guides": guides,
            "guide_views": {L: [guide_view(st, n, L, f"token={quote(token)}&" if token else "") for n in range(1, len(st) + 1)]
                            for L, st in guides.items()},
            "guide_first": act[rank[0]]["letter"] if act else "",
            "faulty": [k for k in keys if cards[k]["faults"] or cards[k]["n_history"]],
            "has_faults": bool(faults_of),
            "note": "" if faults_of else "No fault on this car maps to a system yet, so the full system list is shown."}


# --- layers, issue sets and overlap ---------------------------------------------------------------------
GUESS_CONF = ("SINGLE-SOURCE", "UNKNOWN")
#: relation layers (edges carry one of these ids)
REL_LAYERS = [("dep", "Depends on"), ("pg", "Power or ground path"), ("conn", "Connector or harness path"),
              ("guess", "Guessed link")]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
NONE_YET = "none captured yet"


def _edge_layer(conf: str, path: list, els: dict) -> str:
    """Which relation layer an edge belongs to: a guess (single source / unverified) is always the guess layer."""
    if conf in GUESS_CONF:
        return "guess"
    kinds = {(els.get(p) or {}).get("kind") for p in path}
    if kinds & {"connector", "harness_section"}:
        return "conn"
    if kinds & {"ground", "fuse", "battery"}:
        return "pg"
    return "dep"


def date_word(iso: Optional[str]) -> str:
    """'26 Oct' from a recorded ISO time, or '' when there is none (never a made-up date)."""
    from datetime import datetime
    try:
        d = datetime.fromisoformat(str(iso)[:19])
    except (TypeError, ValueError):
        return ""
    return f"{d.day} {d.strftime('%b')}"


def _issues(vin, groups, board, sys_of_card, by_key, deps, cards, els, token) -> list:
    """One set per shared-cause group (the issue boxes the page shows): the systems its faults sit in, the systems
    upstream of those (a guess when only guessed edges reach them), and the shared parts the group names."""
    by_card = {c["key"]: c for c in board}
    out: list = []
    for g in groups:
        mem = [by_card[m] for m in g.get("members") or [] if m in by_card]
        direct: list = []
        for m in g.get("members") or []:
            for k in sys_of_card.get(m, []):
                if k in by_key and k not in direct:
                    direct.append(k)
        if not direct:
            continue
        items: dict = {}

        def put(key, label, href, guess, kind, path=""):
            cur = items.get(key)
            if cur is None:
                items[key] = {"key": key, "label": label, "href": href, "guess": guess, "kind": kind, "path": path}
            elif cur["guess"] and not guess:
                cur["guess"] = False

        for k in direct:
            put("s:" + k, by_key[k]["label"], cards[k]["detail_href"], False, "system", cards[k]["path_href"])
        for k in direct:
            for e in deps[k]["edges"]:
                if e["to"] in by_key:
                    put("s:" + e["to"], by_key[e["to"]]["label"], cards[e["to"]]["detail_href"],
                        e["confidence"] in GUESS_CONF, "upstream", cards[e["to"]]["path_href"])
        for we in g.get("why_elements") or []:
            if we.get("label"):
                eid = we.get("id") or ""
                href = _tok(f"/v/{vin}/electrical#el-{quote(eid)}", token) if eid else ""
                put("p:" + (eid or we["label"]), we["label"], href, False, "part", href)
        seen = [c.get("last_seen") for c in mem if c.get("last_seen")]
        out.append({"id": g.get("id") or "", "label": g.get("label") or "Shared cause", "n_codes": len(mem),
                    "codes": [c["code"] for c in mem], "present": int(g.get("n_present") or 0) >= 1,
                    "n_present": int(g.get("n_present") or 0), "why": g.get("why") or "",
                    "last_seen": max(seen) if seen else "", "items": list(items.values()), "letter": "",
                    "direct": ["s:" + k for k in direct]})
    for i, iss in enumerate(out):
        iss["letter"] = LETTERS[i % 26]
    return out


# true-Venn geometry in a 600 x 420 box (2 and 3 sets): circle centres/radius and where each region's label sits
_VENN = {
    2: {"r": 140, "c": [(220, 210), (380, 210)],
        "a": {(0,): (150, 210), (1,): (450, 210), (0, 1): (300, 210)}},
    3: {"r": 130, "c": [(240, 160), (360, 160), (300, 262)],
        "a": {(0,): (190, 120), (1,): (410, 120), (2,): (300, 340), (0, 1): (300, 110),
              (0, 2): (240, 255), (1, 2): (360, 255), (0, 1, 2): (300, 195)}},
}


def overlap(issues: list) -> dict:
    """Sets and their intersections from ``issues`` (each ``{id, label, items: [{key, label, href, guess}]}``).

    mode: ``none`` (0 issues), ``single`` (1), ``venn`` (2-3: circles, every region present), ``boxes`` (4+: one box
    per combination that has members, biggest first). A region's item is a guess when any issue that puts it there
    reached it only by a guessed link. Pure: no I/O."""
    n = len(issues)
    iss = [{"idx": i, "letter": x.get("letter") or LETTERS[i % 26], "id": x.get("id", ""), "label": x["label"], "n_items": len(x["items"])}
           for i, x in enumerate(issues)]
    out: dict = {"mode": "none" if n == 0 else "single" if n == 1 else "venn" if n <= 3 else "boxes",
                 "n": n, "issues": iss, "regions": [], "circles": []}
    if n == 0:
        return out
    where: dict = {}
    for i, x in enumerate(issues):
        for it in x["items"]:
            w = where.setdefault(it["key"], {"item": dict(it), "in": [], "guess": False})
            w["in"].append(i)
            w["guess"] = w["guess"] or bool(it.get("guess"))
    combos: dict = {}
    for w in where.values():
        combos.setdefault(tuple(w["in"]), []).append({**w["item"], "guess": w["guess"]})
    if out["mode"] == "venn":
        geo = _VENN[n]
        out["circles"] = [{"cx": cx, "cy": cy, "r": geo["r"], **iss[i]} for i, (cx, cy) in enumerate(geo["c"])]
        keys = list(geo["a"])
    else:
        keys = sorted(combos, key=lambda c: (-len(combos[c]), -len(c), c))
    for c in keys:
        its = sorted(combos.get(c, []), key=lambda t: (t["guess"], t["label"]))
        out["regions"].append({"members": list(c), "letters": [iss[i]["letter"] for i in c],
                               "labels": [iss[i]["label"] for i in c], "size": len(its), "is_overlap": len(c) > 1,
                               "its": its, "n_guess": sum(1 for t in its if t["guess"]),
                               "ikeys": [t["key"] for t in its],
                               "anchor": (_VENN[n]["a"][c] if out["mode"] == "venn" else None)})
    return out


# --- guided path ----------------------------------------------------------------------------------------
def rank_issues(issues: list) -> list:
    """Issue indexes, most important first: present faults before history, then more present faults, then more
    codes (more corroboration), then the page order."""
    return sorted(range(len(issues)), key=lambda i: (not issues[i]["present"], -issues[i]["n_present"],
                                                    -issues[i]["n_codes"], i))


def guide_path(idx: int, issues: list) -> list:
    """The ordered steps for issue ``idx`` among ``issues``. Pure.

    1 the issue; 2 its shared suspect (what the most issues share, a finding before a guess; for a single issue the
    parts its group names); 3.. the next systems upstream, findings before guesses; then the test (the electrical
    path / system page of the last suspect). If there is no shared suspect and nothing upstream, the last step says
    what to capture instead of naming a suspect. Each step: n, kind, title, why, basis (finding / guess / none),
    highlight (item keys), links [(text, href)]."""
    me = issues[idx]
    steps: list = []

    def add(kind, title, why, basis, highlight, links):
        steps.append({"kind": kind, "title": title, "why": why, "basis": basis, "highlight": list(highlight), "links": links})

    codes = ", ".join(me["codes"][:6]) or "no code listed"
    add("issue", me["label"],
        f"Start here: {me['n_present']} of its {me['n_codes']} fault{'s' if me['n_codes'] != 1 else ''} present now ({codes})."
        + (f" {me['why']}." if me["why"] else ""), "finding", me.get("direct") or [], [])
    count = {}
    for j, o in enumerate(issues):
        for it in o["items"]:
            count.setdefault(it["key"], set()).add(j)
    others = [i for i in range(len(issues)) if i != idx]
    shared = [it for it in me["items"] if len(count[it["key"]]) > 1]
    shared.sort(key=lambda t: (t["guess"], -len(count[t["key"]]), t["label"]))
    if not [t for t in shared if not t["guess"]]:                          # no shared finding: the parts its own group names come first
        parts = sorted((it for it in me["items"] if it["kind"] == "part"), key=lambda t: t["label"])
        shared = parts + [t for t in shared if t not in parts]
    last = None
    if shared:
        s = shared[0]
        n_iss = len(count[s["key"]])
        what = (f"also in {n_iss - 1} other issue{'s' if n_iss != 2 else ''}" if n_iss > 1 else "named by this issue's own group")
        add("shared", s["label"] + (" (guess)" if s["guess"] else ""),
            f"Check first: {s['label']} is {what}"
            + (", reached only by a guessed link, so treat it as a guess." if s["guess"] else "."),
            "guess" if s["guess"] else "finding", [s["key"]], [(f"Open {s['label']}", s["href"])] if s["href"] else [])
        last = s
    taken = {s["key"] for s in shared[:1]}
    up = [it for it in me["items"] if it["kind"] == "upstream" and it["key"] not in taken]
    up.sort(key=lambda t: (t["guess"], t["label"]))
    for u in up[:2]:
        add("upstream", u["label"] + (" (guess)" if u["guess"] else ""),
            f"Next upstream: {me['label']} depends on {u['label']}"
            + (", from a single or unverified source only: a guess." if u["guess"] else ", a recorded dependency."),
            "guess" if u["guess"] else "finding", [u["key"]], [(f"Open {u['label']}", u["href"])] if u["href"] else [])
        last = u
    if last is not None:
        links = []
        if last.get("path"):
            links.append((f"Electrical path for {last['label']}", last["path"]))
        if last.get("href"):
            links.append((f"System page: {last['label']}", last["href"]))
        add("test", "Prove it or rule it out",
            f"Test {last['label']} on the car and record the reading; the system page and electrical path list the checks.",
            "guess" if last["guess"] else "finding", [last["key"]], links)
    else:
        sysk = (me.get("direct") or [""])[0]
        add("capture", "Capture next",
            "No shared part and no upstream system is recorded for this issue, so no suspect is named. Capture next: "
            "re-read these codes with their freeze frames and record a live reading from the system's channels, then "
            "look again.", "none", me.get("direct") or [], [])
    for i, s in enumerate(steps):
        s["n"] = i + 1
        s["total"] = len(steps)
    return steps


def guide_view(steps: list, step: int, letter: str, base_href: str = "") -> dict:
    """Navigation for one step: clamped step number, prev/next/restart/exit links, breadcrumb crumbs. ``base_href``
    is the query prefix to keep (e.g. '?token=x&'); links are '?guide=A&step=N#sx-guide'."""
    total = len(steps)
    n = min(max(int(step or 1), 1), total)

    def href(k):
        return f"?{base_href}guide={letter}&step={k}#sx-guide"
    return {"n": n, "total": total, "step": steps[n - 1], "progress": f"Step {n} of {total}",
            "prev": href(n - 1) if n > 1 else "", "next": href(n + 1) if n < total else "",
            "restart": href(1), "exit": f"?{base_href.rstrip('&')}#sx" if base_href.rstrip("&?") else "?#sx",
            "crumbs": [{"n": i + 1, "title": s["title"], "href": href(i + 1), "current": i + 1 == n} for i, s in enumerate(steps[:n])]}


def _live_state() -> dict:
    """In-process poller snapshot only (no adapter I/O): {connected, n, by_system: {key: [channel ids]}}."""
    out: dict = {"connected": False, "n": 0, "by_system": {}}
    try:
        from . import systems_bridge, liveboard_bridge
        st = systems_bridge._poll_state()
        ch = [c for c in st.get("channels") or [] if c]
        out["connected"] = bool(st.get("connected")) and bool(ch)
        out["n"] = len(ch)
        for c in ch:
            k = liveboard_bridge.channel_system(c)
            if k:
                out["by_system"].setdefault(k, []).append(c)
    except Exception:  # noqa: BLE001
        pass
    return out


def _layers(base: dict, live: dict) -> list:
    """The layer buttons with their own captured data. Every number is a count of what is on the map or in the
    fault records; nothing is estimated."""
    def mk(lid, kind, label, parts, on, group):
        return {"id": lid, "kind": kind, "label": label, "on": on, "group": group, "parts": parts,
                "text": " · ".join([label] + parts) if parts else f"{label} · {NONE_YET}"}

    out = []
    for lid, label in REL_LAYERS:
        es = [e for e in base["edges"] if e["layer"] == lid]
        parts = [f"{len(es)} link{'s' if len(es) != 1 else ''}"] if es else []
        if es and lid != "guess":
            parts.append(f"{sum(1 for e in es if e['confidence'] == 'CONFIRMED')} confirmed")
        if es and lid == "guess":
            parts.append("not findings")
        out.append(mk(lid, "rel", label, parts, lid != "guess", "Relations"))
    for l in base["legend_sev"]:
        ns = [n for n in base["nodes"] if n["cls"] == l["cls"]]
        parts = []
        if ns:
            parts.append(f"{len(ns)} system{'s' if len(ns) != 1 else ''}")
            seen = [f["last_seen"] for n in ns for f in base["cards"][n["key"]]["faults"] if f.get("last_seen")]
            if seen:
                parts.append("last read " + date_word(max(seen)))
        out.append({**mk(l["cls"], "sev", l["word"], parts, True, "Severity"), "glyph": l["glyph"]})
    act = [i for i in base["issues_all"] if i["present"]]
    parts = []
    if act:
        seen = [i["last_seen"] for i in act if i["last_seen"]]
        parts = [f"{len(act)} active", f"{sum(i['n_codes'] for i in act)} codes"] + (["last read " + date_word(max(seen))] if seen else [])
    out.append(mk("issues", "issues", "Issues", parts, True, "Show"))
    lp = [f"{live['n']} channel{'s' if live['n'] != 1 else ''}", "now"] if live["connected"] else ["not connected", NONE_YET]
    out.append({**mk("live", "live", "Live", lp, True, "Show"), "text": " · ".join(["Live"] + lp)})
    return out


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
    out = _apply(base, system)
    live = _live_state()
    out["live"] = live
    out["nodes"] = [{**n, "live_n": len(live["by_system"].get(n["key"], []))} for n in out["nodes"]]
    out["layers"] = _layers(out, live)
    return out


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
