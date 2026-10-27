"""The only module in CUORE that imports :mod:`mes.systems`.

Mirrors the pattern ``known_good_bridge.py``/``parts_bridge.py`` already
use: every route reaches the vehicle-systems graph and its DTC-correlation
view only through this file.

Nothing here invents data -- each function is a thin pass-through to
``mes.systems``, which is where every source citation and confidence level
actually lives (see that module's docstring).
"""

from __future__ import annotations

from typing import Any

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path

from mes import systems as systems_mod  # noqa: E402


def systems() -> dict[str, dict[str, Any]]:
    """Every vehicle system in the graph, in reading order."""
    return systems_mod.systems()


def systems_for_code(code: str, description: str = "") -> list[dict[str, Any]]:
    """Every system a DTC implicates (primary + upstream), each sourced."""
    return systems_mod.systems_for_code(code, description)


def correlate(vin: str) -> dict[str, Any]:
    """One vehicle's DTC corpus projected onto the systems graph: per-system
    counts/status, pairwise co-occurrence, and dependency chains. See
    ``mes.systems.correlate`` for the full contract."""
    return systems_mod.correlate(vin)


def related_systems(system_key: str, depth: int = 1) -> list[dict[str, Any]]:
    """Systems within ``depth`` ``depends_on`` hops of ``system_key``, both
    directions. Each row: ``system``, ``direction`` ("upstream" = the key
    depends on it, "downstream" = it depends on the key), ``depth``,
    ``path`` (keys from ``system_key`` to the row's system) and ``why``
    (the ``depends_on`` edge's own sourced reason, for the last hop).
    Read straight off ``mes.systems.SYSTEMS``; nothing inferred."""
    graph = systems_mod.systems()
    if system_key not in graph or depth < 1:
        return []
    out: list[dict[str, Any]] = []
    seen = {system_key}
    frontier = [(system_key, [system_key])]
    for level in range(1, depth + 1):
        nxt: list[tuple[str, list[str]]] = []
        for cur, path in frontier:
            edges: list[tuple[str, str, str]] = []
            for dep in graph[cur].get("depends_on") or []:
                edges.append((dep["system"], "upstream", dep.get("why") or ""))
            for other, rec in graph.items():
                for dep in rec.get("depends_on") or []:
                    if dep.get("system") == cur:
                        edges.append((other, "downstream", dep.get("why") or ""))
            for other, direction, why in edges:
                if other in seen or other not in graph:
                    continue
                seen.add(other)
                row_path = path + [other]
                out.append({"system": other, "direction": direction, "depth": level,
                            "path": row_path, "why": why})
                nxt.append((other, row_path))
        frontier = nxt
    return out



# --- Systems page: faults grouped by system, priority first -----------------

_PRESENT = ("active", "pending", "permanent")


def _poll_state() -> dict[str, Any]:
    """Is CUORE itself connected and polling, and which channel ids? Reads
    only in-memory state (``ops.status()`` / the poller's own status): no
    adapter I/O, no new polling. ``{connected, mes_holds, channels}``."""
    out: dict[str, Any] = {"connected": False, "mes_holds": False, "channels": set()}
    try:
        from ..live import ops as live_ops
        st = live_ops.status()
        out["mes_holds"] = (st.get("mes") or {}).get("state") == "connected"
        out["connected"] = (st.get("lock") or {}).get("process") == "cuore"
        ls = live_ops.live_session_status()
        if ls.get("active"):
            out["connected"] = True
            out["channels"] = {c.get("id") for c in ls.get("channels") or [] if c.get("id")}
    except Exception:  # noqa: BLE001 -- the page renders without it
        pass
    return out


def systems_board(vin: str, system_list: list[dict[str, Any]], by_system: dict[str, dict[str, Any]],
                  labels: dict[str, str]) -> dict[str, Any]:
    """Faults grouped under their system, ranked like the fault board: a
    system's rank is its best fault's tier, then its newest last_seen. Built
    from ``fault_board.board`` and ``fault_similarity.groups`` (both CUORE
    records); the call line and the "why" use those and nothing else."""
    from . import fault_board
    poll = _poll_state()
    out: dict[str, Any] = {"rows": [], "quiet": [], "call": None, "connected": poll["connected"],
                           "mes_holds": poll["mes_holds"], "n_live": len(poll["channels"]),
                           "ok": True}
    try:
        cards = [c for c in fault_board.board(vin) if c["kind"] == "code"]
    except Exception:  # noqa: BLE001
        out["ok"] = False
        cards = []
    try:
        from . import fault_similarity
        sim = fault_similarity.groups(vin)
    except Exception:  # noqa: BLE001
        sim = []
    sim_of: dict[str, dict[str, Any]] = {}
    for g in sim:                                   # already best tier, then newest
        for k in g["members"]:
            sim_of.setdefault(k, g)

    code_sys: dict[str, str] = {}
    for key, row in by_system.items():
        for code in row.get("codes") or []:
            code_sys.setdefault(str(code).split("-")[0], key)

    def system_of(c: dict[str, Any]) -> str:
        k = code_sys.get(c["code"].split("-")[0])
        if k:
            return k
        try:
            for r in systems_for_code(c["code"], c.get("description") or ""):
                if r.get("role") == "primary":
                    return r["system"]
        except Exception:  # noqa: BLE001
            pass
        return "other"

    buckets: dict[str, list[dict[str, Any]]] = {}
    for c in cards:
        buckets.setdefault(system_of(c), []).append(c)
    live_by_sys = {s.get("key"): set(s.get("live_channels") or []) for s in system_list}

    def fault_row(c: dict[str, Any]) -> dict[str, Any]:
        return {"key": c["key"], "code": c["code"], "module": c["module"], "status": c["status"],
                "status_label": c["status_label"], "status_mark": c["status_mark"],
                "present": c["status"] in _PRESENT, "last_seen_ago": c["last_seen_ago"],
                "last_seen": c["last_seen"][:16].replace("T", " "), "can_fix": c["can_fix"],
                "href": c["href"], "path_href": f"/v/{vin}/electrical?code={c['code']}",
                "returned_after_fix": c["returned_after_fix"], "tier": c["importance"]["tier"],
                "ls": c["_ls"]}

    rows = []
    for key, cs in buckets.items():
        fr = [fault_row(c) for c in cs]
        fr.sort(key=lambda f: (f["tier"], -f["ls"]))
        n_present = sum(1 for f in fr if f["present"])
        groups = [sim_of[c["key"]] for c in cs if c["key"] in sim_of]
        g = groups[0] if groups else None
        newest = max(cs, key=lambda c: c["_ls"])
        rows.append({
            "key": key, "label": labels.get(key) or key.replace("_", " ").title(), "faults": fr,
            "n_present": n_present, "n_history": len(fr) - n_present, "tier": fr[0]["tier"],
            "ls": newest["_ls"], "last_seen_ago": newest["last_seen_ago"],
            "shared": (g["label"] if g else None),
            "shared_why": (fault_board._why_line(g) if g else None),
            "live": bool(poll["channels"] & live_by_sys.get(key, set())),
            "open": n_present > 0, "_cards": cs,
        })
    rows.sort(key=lambda r: (r["tier"], -r["ls"]))
    out["rows"] = rows
    have = {r["key"] for r in rows}
    out["quiet"] = [{"key": s.get("key"), "label": s.get("label") or s.get("key"),
                     "live": bool(poll["channels"] & live_by_sys.get(s.get("key"), set()))}
                    for s in system_list if s.get("key") not in have]

    top = next((r for r in rows if r["n_present"]), None)
    if top:
        pres = [c for c in top["_cards"] if c["status"] in _PRESENT]
        pres.sort(key=lambda c: (c["importance"]["tier"], -c["_ls"]))
        lead = pres[0]
        same = {c["status"] for c in pres}
        word = lead["status_label"].lower() if len(same) == 1 else "present"
        n = len(pres)
        text = f"{top['label']}: {n} {word} fault{'s' if n != 1 else ''}"
        if top["shared"] and n > 1:
            text += f" share {top['shared']}"
        elif top["shared"]:
            text += f" ({top['shared']})"
        nt = lead.get("next_test")
        nxt = (nt or {}).get("text") or ""
        if len(nxt) > 90:                       # one line: the full text goes in "Why this?"
            nxt = nxt[:90].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"
        out["call"] = {
            "text": text, "next": nxt or None, "code": lead["code"], "system": top["key"],
            "why": [x for x in (lead["importance"]["reason"], lead.get("status_detail"), top["shared_why"],
                                ("Next test (" + nt["source"] + "): " + nt["text"]) if nt else None) if x],
            "code_href": lead["href"], "path_href": f"/v/{vin}/electrical?code={lead['code']}",
        }
    for r in rows:
        r.pop("_cards", None)
    return out


__all__ = ["systems", "systems_for_code", "correlate", "related_systems", "systems_board"]
