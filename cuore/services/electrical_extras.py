"""Read-only helpers behind the extra layers on ``/v/{vin}/electrical``:
module reachability, "repaired before" matches and catalogue part hits.

Nothing here talks to the car or COM3. Every function degrades to an empty
result rather than raising -- the diagram page must render without any of
this.

* :func:`module_status` reads the persisted last full scan
  (``fullscan_last.json`` in the CUORE state dir, written by
  ``cuore.live.fullscan``) and reports, per module abbreviation, whether it
  ``answered``, was ``silent``, or is ``unchecked`` (never reached: no cable,
  no known address, bus error).
* :func:`repaired_index` finds job actions of kind repair/part, and service
  records, whose text names an element -- matched on the element id as a
  whole word or the full element label, nothing fuzzier.
* :func:`part_hits` runs the parts catalogue search on an element label.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _scan_time(path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="minutes").replace("T", " ")
    except OSError:
        return None


def module_status() -> dict[str, dict[str, Any]]:
    """``{MODULE_CODE: {state, checked_at, bus, why}}`` from the last
    persisted full scan; ``state`` is ``answered`` / ``silent`` /
    ``unchecked``. Empty when no scan has been persisted."""
    try:
        from ..live import fullscan
        data = fullscan.last()
        when = _scan_time(fullscan._last_file())
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in data.get("coverage") or []:
        code = str(row.get("module") or "").upper()
        if not code:
            continue
        cat = row.get("category")
        state = cat if cat in ("answered", "silent") else "unchecked"
        prev = out.get(code)
        if prev and prev["state"] == "answered":
            continue
        out[code] = {"state": state, "checked_at": when, "bus": row.get("bus"),
                     "why": row.get("why")}
    return out


def module_code_for(eid: str, element: dict[str, Any], codes: set[str]) -> Optional[str]:
    """The module abbreviation an element of kind ``module`` stands for:
    a whole token of its id (``abs_module`` -> ABS) or the first word of
    its label (``BCM -- Body...`` -> BCM) that is a known module code."""
    if str(element.get("kind") or "").lower() != "module":
        return None
    toks = [t.upper() for t in _TOKEN_RE.findall(eid.replace("_", " "))]
    first = _TOKEN_RE.findall(str(element.get("label") or ""))[:1]
    for t in toks + [f.upper() for f in first]:
        if t in codes:
            return t
    return None


def module_nodes(elements: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """``{element id: {state, title}}`` for module elements that map onto a
    known module code. A module the persisted scan never listed is
    ``unchecked`` with no timestamp."""
    status = module_status()
    codes = set(status) | {"ECM", "TCM", "DTCM", "ESM", "DASM", "BCM", "IPC"}
    out: dict[str, dict[str, Any]] = {}
    for eid, e in elements.items():
        code = module_code_for(eid, e, codes)
        if not code:
            continue
        s = status.get(code)
        if s is None:
            out[eid] = {"state": "unchecked", "title": f"{code}: not checked (no persisted scan result)"}
            continue
        word = {"answered": "answered", "silent": "silent (no reply)",
                "unchecked": "not checked"}[s["state"]]
        title = f"{code}: {word}"
        if s.get("checked_at"):
            title += f", last scan {s['checked_at']}"
        if s["state"] == "unchecked" and s.get("why"):
            title += f" ({s['why']})"
        out[eid] = {"state": s["state"], "title": title}
    return out


def _mentions(text: str, eid: str, label: str) -> bool:
    low = text.lower()
    if len(label) >= 4 and label.lower() in low:
        return True
    if len(eid) < 4 and "_" not in eid:  # 'ecm', 'bcm': too common as plain words
        return False
    pat = r"(?<![a-z0-9_])" + re.escape(eid.lower()) + r"(?![a-z0-9_])"
    return bool(re.search(pat, low))


def repaired_index(vin: str, elements: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    """``{element id: [{at, source, text}]}`` -- job repair/part actions and
    service records that name the element (id as a whole word, or its full
    label). Conservative on purpose: a miss is better than a wrong wrench."""
    events: list[tuple[str, str, str, Optional[str]]] = []  # at, source, text, ref id
    try:
        from mes import jobs as jobs_mod
        for job in jobs_mod.load(vin):
            for a in job.get("actions") or []:
                if a.get("kind") in ("repair", "part"):
                    ref = a.get("ref")
                    ref_id = str(ref["id"]) if isinstance(ref, dict) and ref.get("id") else None
                    events.append((str(a.get("effective_date") or a.get("at") or "")[:10],
                                   f"job {a.get('kind')}", str(a.get("text") or ""), ref_id))
    except Exception:  # noqa: BLE001
        pass
    try:
        from mes import service as service_mod
        for rec in service_mod.load(vin, None):
            events.append((str(rec.get("at") or "")[:10], f"service record ({rec.get('kind')})",
                           json.dumps(rec.get("data") or {}, default=str), None))
    except Exception:  # noqa: BLE001
        pass
    out: dict[str, list[dict[str, str]]] = {}
    if not events:
        return out
    for eid, e in elements.items():
        label = str(e.get("label") or "")
        for at, source, text, ref_id in events:
            if ref_id == eid or _mentions(text, eid, label):
                out.setdefault(eid, []).append({"at": at, "source": source, "text": text[:160]})
    return out


_hit_cache: dict[tuple[int, str], list[dict[str, str]]] = {}


def search_query(label: str) -> str:
    """The catalogue query for an element: its label up to ' -- ' and with
    any parenthesised remark dropped."""
    q = re.sub(r"\([^)]*\)", " ", str(label or "").split(" -- ")[0])
    return " ".join(q.split())


def part_hits(label: str, limit: int = 3) -> list[dict[str, str]]:
    """Up to ``limit`` distinct catalogue part numbers matching the element
    label -- ``[{pn, name}]``; empty when the catalogue is absent or nothing
    matches. Never invents a number: every row is a catalogue row."""
    try:
        from . import parts_catalog as pc
        cat = pc.load()
        if not cat:
            return []
        q = search_query(label)
        key = (id(cat), q)
        if key in _hit_cache:
            return _hit_cache[key][:limit]
        rows, seen = [], set()
        for h in pc.search(cat, q, limit=40):
            pn = h.get("pn")
            if not pn or pn in seen or h.get("fitment") == "other-engine":
                continue
            seen.add(pn)
            rows.append({"pn": str(pn), "name": str(h.get("name") or "")})
            if len(rows) >= 3:
                break
        _hit_cache[key] = rows
        return rows[:limit]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["module_status", "module_nodes", "repaired_index", "part_hits", "search_query"]
