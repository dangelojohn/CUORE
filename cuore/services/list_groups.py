"""Grouping helpers for the Inbox and Notes pages: fold repeats into one counted
line, priority (active codes) first, most recent next, with a plain age label.

Pure functions over the rows the existing stores already return -- nothing here
writes to a store or talks to the car.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional


def age_label(ts: Optional[str], now: Optional[datetime] = None) -> str:
    """"just now", "3 h ago", "2 d ago", "5 mo ago" for an ISO timestamp ("" if unparseable)."""
    try:
        t = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return ""
    secs = ((now or datetime.now()) - t).total_seconds()
    if secs < 90:
        return "just now"
    if secs < 3600 * 2:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    days = int(secs // 86400)
    if days < 60:
        return f"{days} d ago"
    return f"{days // 30} mo ago"


def base_code(code: str) -> str:
    return (code or "").split("-")[0].strip().upper()


def active_codes(vin: str) -> set[str]:
    """Base codes the car currently carries (not simply cleared). Never raises."""
    try:
        from .owner_events_bridge import _active_codes
        return {base_code(c) for c in _active_codes(vin)}
    except Exception:  # noqa: BLE001 -- the page works without it
        return set()


_CODE_RE = re.compile(r"^[PCBU][0-9A-F]{4}$", re.I)


def _question_title(row: dict[str, Any]) -> str:
    text = (row.get("text") or "").strip()
    if text:
        return text
    label = (row.get("target") or {}).get("label") or ""
    return re.sub(r"^[PCBU][0-9A-F]{4}:\s*", "", label)


def group_feedback(rows: list[dict[str, Any]], active: set[str]) -> list[dict[str, Any]]:
    """Fold feedback rows (already one status) into groups.

    Owner questions with the same ``target.item`` become ONE group listing the
    codes they cover; anything else stays a group of one. Groups touching an
    active code, and every non-owner item (a mechanic's own correction), come
    first; inside that, newest first.
    """
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = r.get("target") or {}
        owner = t.get("page") == "owner" and bool(t.get("item"))
        key = f"owner|{t.get('item')}|{r.get('kind')}" if owner else f"row|{r.get('id')}"
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "owner": owner, "kind": r.get("kind"),
                               "title": _question_title(r) if owner else "",
                               "rows": [], "codes": [], "latest": ""}
        g["rows"].append(r)
        sec = base_code(t.get("section", ""))
        if owner and _CODE_RE.match(sec) and sec not in g["codes"]:
            g["codes"].append(sec)
        g["latest"] = max(g["latest"], r.get("at") or "")
    out = []
    for g in groups.values():
        g["n"] = len(g["rows"])
        g["ids"] = [r["id"] for r in g["rows"]]
        g["active_codes"] = [c for c in g["codes"] if c in active]
        g["priority"] = 0 if (g["active_codes"] or not g["owner"]) else 1
        g["age"] = age_label(g["latest"])
        for r in g["rows"]:
            r["age"] = age_label(r.get("at"))
        g["codes"].sort(key=lambda c: (c not in active, c))
        g["answer_text"] = next(((r.get("answer") or {}).get("text") for r in g["rows"] if r.get("answer")), "")
        out.append(g)
    out.sort(key=lambda g: g["latest"], reverse=True)
    out.sort(key=lambda g: g["priority"])
    return out


def _norm(text: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", (text or "").lower())).strip()[:160]


def _summary(text: str, n: int = 110) -> str:
    first = (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""
    return first if len(first) <= n else first[:n].rsplit(" ", 1)[0] + "..."


def group_notes(notes: list[dict[str, Any]], active: set[str]) -> list[dict[str, Any]]:
    """Notes -> kind groups -> target subgroups -> one-line entries.

    A note tagged "resolved" sinks to the bottom and its group closes.
    Identical (digit-normalised) text on the same target folds into one counted entry.
    Groups on an active code first, then newest.
    """
    kinds: dict[str, dict[str, Any]] = {}
    for n in notes:
        kind = n.get("target_kind") or "vehicle"
        tid = n.get("target_id") or ""
        k = kinds.setdefault(kind, {"kind": kind, "targets": {}, "latest": ""})
        t = k["targets"].setdefault(tid, {"target_id": tid, "entries": {}, "latest": ""})
        resolved = "resolved" in [str(x).lower() for x in (n.get("tags") or [])]
        e = t["entries"].setdefault(_norm(n.get("text", "")), {
            "note": n, "count": 0, "resolved": resolved, "all_ids": []})
        e["count"] += 1
        e["all_ids"].append(n["id"])
        if (n.get("at") or "") > (e["note"].get("at") or ""):
            e["note"] = n
        stamp = n.get("edited_at") or n.get("at") or ""
        t["latest"] = max(t["latest"], stamp)
        k["latest"] = max(k["latest"], stamp)
    out = []
    for k in kinds.values():
        targets = []
        for t in k["targets"].values():
            entries = list(t["entries"].values())
            for e in entries:
                nn = e["note"]
                e["summary"] = _summary(nn.get("text", ""))
                e["long"] = len(nn.get("text", "")) > len(e["summary"])
                e["age"] = age_label(nn.get("at"))
            entries.sort(key=lambda e: e["note"].get("at") or "", reverse=True)
            entries.sort(key=lambda e: e["resolved"])
            is_active = k["kind"] == "code" and base_code(t["target_id"]) in active
            targets.append({"target_id": t["target_id"], "entries": entries, "n": sum(e["count"] for e in entries),
                            "active": is_active, "latest": t["latest"], "age": age_label(t["latest"]),
                            "open": is_active or any(not e["resolved"] for e in entries)})
        targets.sort(key=lambda t: t["latest"], reverse=True)
        targets.sort(key=lambda t: not t["active"])
        out.append({"kind": k["kind"], "targets": targets, "n": sum(t["n"] for t in targets),
                    "active": any(t["active"] for t in targets), "latest": k["latest"],
                    "age": age_label(k["latest"]),
                    "open": any(t["open"] for t in targets),
                    "n_targets": len(targets)})
    out.sort(key=lambda g: g["latest"], reverse=True)
    out.sort(key=lambda g: not g["active"])
    return out
