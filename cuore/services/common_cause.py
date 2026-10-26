"""Common-cause finder: which one thing (or small set of things) could explain
ALL of the car's current faults at once.

Consistency-based diagnosis. Every current fault (an active or recent code, an
open symptom, a failed test) has a *dependency set*: the modules, fuses,
grounds, connectors and sensors on its electrical/physical path
(``layout_bridge.code_path`` -> ``mes.electrical`` / ``mes.layout_systems``) and
the systems it sits on or depends on (``mes.systems``). A candidate cause is a
set of those dependencies that hits every covered fault's dependency set (a
minimal hitting set), capped at 3 members. Single shared causes rank first.

Nothing is invented: a fault with no dependency data is listed as *not
covered*, never dropped, and never counted as explained. Dependency data
comes only from the existing graphs; nodes whose coverage is identical (for
example grounds G003A and G003B on the same path) are reported together as
"cannot be told apart by these faults alone".

Pure core: :func:`solve` (data in, answer out). Impure edge:
:func:`gather_faults`. Entry point: :func:`common_cause` (cached on the
inputs' mtimes). Weights live in ``cuore/data/diagnosis_weights.json``.
"""

from __future__ import annotations

import itertools
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache

WEIGHTS_FILE = Path(__file__).resolve().parent.parent / "data" / "diagnosis_weights.json"

_SUPPLY_ROLES = {"supply", "protection", "ground", "connector", "fuse"}
_ACTIVE_STATES = ("ACTIVE", "CLEARED_UNVERIFIED")


# --- weights ----------------------------------------------------------------

def load_weights() -> dict[str, Any]:
    """The scoring table, re-read when the file changes."""
    try:
        st = WEIGHTS_FILE.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    return cache.get_or_build(("diagnosis_weights", stamp), lambda: json.loads(
        WEIGHTS_FILE.read_text(encoding="utf-8")))


def weight(section: str, name: str, default: Any = 0) -> Any:
    ent = (load_weights().get(section) or {}).get(name)
    return ent.get("value", default) if isinstance(ent, dict) else default


def weights_mtime() -> float:
    try:
        return WEIGHTS_FILE.stat().st_mtime
    except OSError:
        return 0.0


def weights_table() -> list[dict[str, Any]]:
    """Flat rows (section, name, value, why) for the page's 'how this is scored' fold."""
    rows: list[dict[str, Any]] = []
    for sec, ents in load_weights().items():
        if sec.startswith("_") or not isinstance(ents, dict):
            continue
        for name, ent in ents.items():
            if isinstance(ent, dict) and "value" in ent:
                v = ent["value"]
                rows.append({"section": sec, "name": name,
                             "value": ", ".join(map(str, v)) if isinstance(v, list) else v,
                             "why": ent.get("why", "")})
    return rows


# --- pure core -------------------------------------------------------------------

def _role_weight(role: str, kind: str) -> float:
    r = (role or "").lower()
    if r in _SUPPLY_ROLES or (kind or "").lower() in _SUPPLY_ROLES:
        return float(weight("common_cause", "role_supply", 1.0))
    if r == "controller" or (kind or "").lower() == "module":
        return float(weight("common_cause", "role_controller", 0.7))
    return float(weight("common_cause", "role_other", 0.85))


def _nodes_of(fault: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """node id -> node info, from a fault's element chain and system chain."""
    out: dict[str, dict[str, Any]] = {}
    for h in fault.get("chain") or []:
        hid = h.get("id")
        if hid:
            out.setdefault(hid, {"id": hid, "label": h.get("label") or hid, "kind": h.get("kind") or "",
                                 "role": h.get("role") or "", "level": "element"})
    for s in fault.get("sys_chain") or []:
        sid = s.get("id")
        if sid:
            out.setdefault(sid, {"id": sid, "label": s.get("label") or sid, "kind": "system",
                                 "role": s.get("role") or "", "level": "system"})
    return out


def _fault_ref(f: dict[str, Any]) -> dict[str, Any]:
    return {"id": f["id"], "label": f["label"], "kind": f.get("kind", ""), "href": f.get("href")}


def _groups(faults: list[dict[str, Any]], class_ids: set[str], level: str) -> list[dict[str, Any]]:
    """Group the faults a cause explains by identical dependency chain, so 16
    U-codes on one path show that path once. The chain marks the cause's hops."""
    by_sig: dict[tuple, dict[str, Any]] = {}
    for f in faults:
        base = f.get("chain") if level == "element" else f.get("sys_chain")
        base = base or []
        sig = tuple(h.get("id") for h in base)
        g = by_sig.setdefault(sig, {"faults": [], "chain": [
            {"id": h.get("id"), "label": h.get("label") or h.get("id"), "kind": h.get("kind") or "",
             "role": h.get("role") or "", "why": h.get("why") or "", "hit": h.get("id") in class_ids}
            for h in base]})
        g["faults"].append(_fault_ref(f))
    return list(by_sig.values())


def solve(faults: list[dict[str, Any]]) -> dict[str, Any]:
    """Minimal hitting sets (size <= max_set_size) over the faults' dependency
    nodes, plus the best single causes that explain only some faults.

    ``faults``: ``{id, label, kind, chain: [{id,label,kind,role}], sys_chain: [...]}``.
    """
    max_size = int(weight("common_cause", "max_set_size", 3))
    max_sets = int(weight("common_cause", "max_sets", 10))
    max_partial = int(weight("common_cause", "max_partial", 8))
    spec_el = float(weight("common_cause", "specificity_element", 1.0))
    spec_sys = float(weight("common_cause", "specificity_system", 0.35))

    per_fault = [(f, _nodes_of(f)) for f in faults]
    covered = [(f, n) for f, n in per_fault if n]
    uncovered = [f for f, n in per_fault if not n]
    nbit = {f["id"]: i for i, (f, _n) in enumerate(covered)}
    full = (1 << len(covered)) - 1

    info: dict[str, dict[str, Any]] = {}
    mask: dict[str, int] = {}
    for f, nodes in covered:
        for nid, ni in nodes.items():
            info.setdefault(nid, ni)
            mask[nid] = mask.get(nid, 0) | (1 << nbit[f["id"]])

    # classes: nodes with identical coverage and level are indistinguishable by these faults
    classes: dict[tuple, dict[str, Any]] = {}
    for nid, m in mask.items():
        ni = info[nid]
        c = classes.setdefault((m, ni["level"]), {"mask": m, "level": ni["level"], "members": []})
        c["members"].append(ni)
    cls = list(classes.values())
    for i, c in enumerate(cls):
        c["members"].sort(key=lambda x: (-_role_weight(x["role"], x["kind"]), x["id"]))
        c["key"] = f"c{i}"
        c["ids"] = {x["id"] for x in c["members"]}
        c["spec"] = spec_el if c["level"] == "element" else spec_sys
        c["role_w"] = max(_role_weight(x["role"], x["kind"]) for x in c["members"])
        c["count"] = bin(c["mask"]).count("1")
        shown = [x["label"] for x in c["members"]]
        c["label"] = " / ".join(shown[:3]) + (f" (+{len(shown) - 3} more)" if len(shown) > 3 else "")
        if c["level"] == "system":
            c["label"] += " (system-level)"
    cls.sort(key=lambda c: (-c["count"], -c["spec"], -c["role_w"], c["label"]))

    def explain(sel: list[dict[str, Any]]) -> dict[str, Any]:
        m = 0
        for c in sel:
            m |= c["mask"]
        expl = [f for f, _n in covered if m >> nbit[f["id"]] & 1]
        not_expl = [f for f, _n in covered if not (m >> nbit[f["id"]] & 1)]
        paths = []
        for c in sel:
            cf = [f for f, _n in covered if c["mask"] >> nbit[f["id"]] & 1]
            paths.append({"cause": c["label"], "level": c["level"],
                          "equivalent": [{"id": x["id"], "label": x["label"], "kind": x["kind"]}
                                         for x in c["members"]],
                          "explains_n": len(cf), "groups": _groups(cf, c["ids"], c["level"])})
        return {
            "key": "+".join(c["key"] for c in sel),
            "size": len(sel),
            "level": "element" if any(c["level"] == "element" for c in sel) else "system",
            "members": [{"label": c["label"], "level": c["level"],
                         "role": c["members"][0]["role"], "kind": c["members"][0]["kind"],
                         "ids": [x["id"] for x in c["members"]]} for c in sel],
            "explains": [_fault_ref(f) for f in expl],
            "explains_n": len(expl), "of_n": len(covered),
            "does_not_explain": [_fault_ref(f) for f in not_expl],
            "paths": paths,
            "specificity": round(sum(c["spec"] for c in sel) / len(sel), 3),
            "_mask": m,
        }

    found: list[tuple[int, ...]] = []
    total_found = 0
    sets: list[dict[str, Any]] = []
    if covered:
        for size in range(1, max_size + 1):
            for combo in itertools.combinations(range(len(cls)), size):
                if any(set(prev) <= set(combo) for prev in found):
                    continue
                m = 0
                for i in combo:
                    m |= cls[i]["mask"]
                if m != full:
                    continue
                found.append(combo)
                total_found += 1
                sets.append(explain([cls[i] for i in combo]))
        sets.sort(key=lambda s: (s["level"] == "system", s["size"], -s["specificity"], s["key"]))
    partial: list[dict[str, Any]] = []
    for c in cls:
        if c["level"] != "element" or c["count"] < 2 or c["mask"] == full:
            continue
        partial.append(explain([c]))
        if len(partial) >= max_partial:
            break
    return {"sets": sets[:max_sets], "sets_found": total_found, "partial": partial,
            "uncovered": [_fault_ref(f) for f in uncovered],
            "n_faults": len(faults), "n_covered": len(covered)}


def make_call(res: dict[str, Any]) -> str:
    """One line a mechanic can act on."""
    if not res["n_faults"]:
        return "No current faults to explain."
    if not res["n_covered"]:
        return (f"{res['n_faults']} current fault(s), none with dependency data on file: "
                "no shared cause can be computed.")
    best = next((s for s in res["sets"] if s["level"] == "element" and
                 all(m["level"] == "element" for m in s["members"])), None)
    mixed = next((s for s in res["sets"] if s["level"] == "element"), None)
    if best is not None:
        names = " + ".join(m["label"] for m in best["members"])
        kind = "Most likely shared cause" if best["size"] == 1 else f"Smallest set of {best['size']} causes"
        line = f"{kind}: {names} -- explains all {best['of_n']} faults with dependency data."
    elif res["partial"]:
        p = res["partial"][0]
        line = (f"Largest specific shared cause: {p['members'][0]['label']} -- explains "
                f"{p['explains_n']} of {p['of_n']} faults.")
        if mixed is not None:
            line += (f" All {mixed['of_n']} are covered only by adding a system-level cause: "
                     + " + ".join(m["label"] for m in mixed["members"]) + ".")
    elif res["sets"]:
        s = res["sets"][0]
        line = (f"Only a system-level cause covers every fault: {s['members'][0]['label']} "
                f"(too broad to test directly).")
    else:
        line = "No shared cause of up to 3 parts explains the faults."
    if res["uncovered"]:
        line += f" {len(res['uncovered'])} fault(s) not covered (no dependency data)."
    return line


# --- gathering -----------------------------------------------------------------

def _parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    t = str(s).replace("T", " ").strip()
    for n in (19, 16, 10):
        try:
            return datetime.fromisoformat(t[:n])
        except ValueError:
            continue
    return None


def _system_labels() -> dict[str, dict[str, Any]]:
    try:
        from . import systems_bridge
        return systems_bridge.systems()
    except Exception:  # noqa: BLE001
        return {}


def _sys_chain(code: str, description: str, graph: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Primary + upstream systems for a code, each upstream with the edge's own reason."""
    try:
        from . import systems_bridge
        rows = systems_bridge.systems_for_code(code, description)
    except Exception:  # noqa: BLE001
        return []
    primaries = [r["system"] for r in rows if r.get("role") == "primary" and r.get("system") != "UNKNOWN"]
    out: list[dict[str, Any]] = []
    for r in rows:
        key = r.get("system")
        if not key or key == "UNKNOWN":
            continue
        why = ""
        if r.get("role") == "upstream":
            for p in primaries:
                for dep in (graph.get(p) or {}).get("depends_on") or []:
                    if dep.get("system") == key:
                        why = dep.get("why") or ""
                        break
                if why:
                    break
        out.append({"id": f"sys:{key}", "label": (graph.get(key) or {}).get("label") or key,
                    "kind": "system", "role": r.get("role") or "", "why": why})
    return out


def _systems_chain_for_keys(keys: list[str], graph: dict[str, dict[str, Any]], role: str = "primary"
                            ) -> list[dict[str, Any]]:
    out, seen = [], set()
    for k in keys:
        if k in graph and k not in seen:
            seen.add(k)
            out.append({"id": f"sys:{k}", "label": graph[k].get("label") or k, "kind": "system",
                        "role": role, "why": ""})
            for dep in graph[k].get("depends_on") or []:
                d = dep.get("system")
                if d in graph and d not in seen:
                    seen.add(d)
                    out.append({"id": f"sys:{d}", "label": graph[d].get("label") or d, "kind": "system",
                                "role": "upstream", "why": dep.get("why") or ""})
    return out


def gather_faults(vin: str, view: Optional[dict[str, Any]] = None, now: Optional[datetime] = None
                  ) -> list[dict[str, Any]]:
    """The car's currently relevant faults, each with its dependency chains.

    Codes: ACTIVE or CLEARED_UNVERIFIED, named in the dossier's open work, or
    seen within ``stale_code_days``. Symptoms: not hidden, within
    ``symptom_days``. Failed tests: a recorded ``fail`` result.
    """
    from . import dossier_bridge, layout_bridge
    from ..web import routes as web_routes   # lazy: the dossier cache lives there
    now = now or datetime.now()
    if view is None:
        view = dossier_bridge.build_view(vin, web_routes._dossier(vin), None)
    graph = _system_labels()
    stale = timedelta(days=int(weight("common_cause", "stale_code_days", 14)))
    open_codes = {c for g in view.get("open_work") or [] for c in g.get("codes") or []}
    faults: list[dict[str, Any]] = []
    path_cache: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    for row in view.get("codes") or []:
        code = (row.get("code") or "").upper()
        if not code or code in seen:
            continue
        last = _parse_ts(row.get("last_seen"))
        recent = bool(last and now - last <= stale)
        if not (row.get("status") in _ACTIVE_STATES or code in open_codes or recent):
            continue
        seen.add(code)
        if code not in path_cache:
            try:
                p = layout_bridge.code_path(code).get("path") or []
            except Exception:  # noqa: BLE001
                p = []
            path_cache[code] = [{"id": h.get("id"), "label": h.get("label") or h.get("id"),
                                 "kind": h.get("kind") or "", "role": h.get("role") or ""}
                                for h in p if h.get("id")]
        desc = row.get("description") or ""
        why = row.get("status_label") or row.get("status") or ""
        faults.append({
            "id": f"code:{code}", "kind": "code", "label": f"{code} {desc}".strip(),
            "detail": f"{why}; last seen {row.get('last_seen_short') or row.get('last_seen') or '?'}; "
                      f"{row.get('sessions') or '?'} session(s)",
            "href": row.get("href"), "family": row.get("family"),
            "chain": path_cache[code], "sys_chain": _sys_chain(code, desc, graph),
        })

    # open symptoms
    tag_sys = {k: v["value"] for k, v in (load_weights().get("symptom_tag_systems") or {}).items()}
    sym_days = timedelta(days=int(weight("common_cause", "symptom_days", 30)))
    try:
        from mes import symptoms as symptoms_mod
        syms = symptoms_mod.load(vin)
    except Exception:  # noqa: BLE001
        syms = []
    for s in syms:
        when = _parse_ts(s.get("at") or s.get("created_at"))
        if when and now - when > sym_days:
            continue
        keys: list[str] = []
        for t in s.get("tags") or []:
            keys += [k for k in tag_sys.get(t, []) if k not in keys]
        text = (s.get("text") or "").strip()
        faults.append({
            "id": f"symptom:{s.get('id')}", "kind": "symptom",
            "label": "Symptom: " + (text[:90] + ("..." if len(text) > 90 else "")),
            "detail": f"reported {str(s.get('at') or '')[:10]} by {s.get('reporter') or '?'}; tags "
                      f"{', '.join(s.get('tags') or []) or 'none'}",
            "href": None, "family": None, "chain": [],
            "sys_chain": _systems_chain_for_keys(keys, graph),
        })

    # failed tests
    try:
        from mes import mechanic_tests
        from ..live import checklists as checklist_store
        for sid, ent in (checklist_store.get(vin) or {}).items():
            if not (ent.get("result") == "fail" or ent.get("outcome") == "fault_found"):
                continue
            tid = sid[5:] if sid.startswith("test:") else sid
            t = mechanic_tests.test(tid)
            keys = list(t["systems"]) if t else ([sid.split("-")[0]] if sid.split("-")[0] in graph else [])
            faults.append({
                "id": f"test:{sid}", "kind": "test",
                "label": "Failed test: " + (t["name"] if t else sid),
                "detail": f"result recorded {str(ent.get('done_at') or '')[:10]}",
                "href": None, "family": None, "chain": [],
                "sys_chain": _systems_chain_for_keys(keys, graph),
            })
    except Exception:  # noqa: BLE001
        pass
    return faults


def _public(res: dict[str, Any]) -> dict[str, Any]:
    for s in res["sets"] + res["partial"]:
        s.pop("_mask", None)
    return res


def compute(vin: str, view: Optional[dict[str, Any]] = None, now: Optional[datetime] = None
            ) -> dict[str, Any]:
    faults = gather_faults(vin, view, now)
    res = _public(solve(faults))
    res["faults"] = [{"id": f["id"], "kind": f["kind"], "label": f["label"], "detail": f.get("detail", ""),
                      "href": f.get("href"), "covered": bool(f.get("chain") or f.get("sys_chain")),
                      "level": ("element" if f.get("chain") else "system" if f.get("sys_chain") else "none")}
                     for f in faults]
    res["call"] = make_call(res)
    res["vin"] = vin
    return res


def cache_key(vin: str) -> tuple:
    from . import dossier_bridge, mes_bridge
    return (mes_bridge.newest_mtime(vin), dossier_bridge._state_fingerprint(), weights_mtime())


def common_cause(vin: str) -> dict[str, Any]:
    """Cached on the inputs' mtimes (MES logs, CUORE state files, weights file)."""
    return cache.get_or_build(("common_cause", vin) + cache_key(vin), lambda: compute(vin))


__all__ = ["common_cause", "compute", "solve", "gather_faults", "make_call", "load_weights",
           "weight", "weights_table", "cache_key"]
