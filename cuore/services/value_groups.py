"""Value groups: live values that belong together across modules (``cuore/data/value_groups.json``).

This module is data access and lookup only. It never touches the car and never stores a limit, scale or
unit: the Live board renders a group from the existing board/channel/decode-status code
(``cuore.web.liveboard_view.group_view``). Everything here degrades to "no groups" rather than failing a page.

Callers: the Live board (the picker and the group panel), the Systems map card, the Module workspace and Find.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

_DATA = Path(__file__).resolve().parent.parent / "data" / "value_groups.json"
_cache: dict[str, Any] = {}


def _load() -> dict[str, Any]:
    if "doc" not in _cache:
        try:
            _cache["doc"] = json.loads(_DATA.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache["doc"] = {"groups": [], "module_platforms": {}}
    return _cache["doc"]


def reload() -> None:
    _cache.clear()


def doc() -> dict[str, Any]:
    return _load()


def groups() -> list[dict[str, Any]]:
    return list(_load().get("groups") or [])


def get(group_id: str) -> Optional[dict[str, Any]]:
    return next((g for g in groups() if g.get("id") == group_id), None)


def group_channel_ids(g: dict[str, Any]) -> list[str]:
    """Every channel id a group lists, once, in section order."""
    seen: list[str] = []
    for s in g.get("sections") or []:
        for cid in s.get("channels") or []:
            if cid not in seen:
                seen.append(cid)
    return seen


def href(vin: str, group_id: str, token: str = "") -> str:
    """The Live board with this group open."""
    url = f"/v/{vin}/liveboard?group={quote(group_id)}"
    return url + (f"&token={quote(token)}" if token else "") + "#lb-values"


def groups_for_system(system_key: str) -> list[dict[str, Any]]:
    return [g for g in groups() if system_key in (g.get("systems") or [])]


def _module_of(channel_id: str) -> str:
    try:
        from ..live import channels as channels_mod
        return (channels_mod.registry().get(channel_id).module or "").upper()
    except Exception:  # noqa: BLE001
        return ""


def groups_for_module(code: str) -> list[dict[str, Any]]:
    """Groups holding at least one channel read from this module:
    [{id, label, mine: [channel ids from this module], others: [other module codes]}]."""
    code = (code or "").upper()
    out: list[dict[str, Any]] = []
    for g in groups():
        mine, others = [], []
        for cid in group_channel_ids(g):
            m = _module_of(cid)
            if m == code:
                mine.append(cid)
            elif m and m not in others:
                others.append(m)
        if mine:
            out.append({"id": g["id"], "label": g["label"], "mine": mine, "others": others})
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def match(q: str) -> list[dict[str, Any]]:
    """Groups a typed word points at, best first: [{group, score}]. An exact label or alias is 100;
    a label that contains the words 80; an alias word inside the query 60."""
    nq = _norm(q)
    if not nq:
        return []
    out: list[tuple[int, dict[str, Any]]] = []
    for g in groups():
        label = _norm(g.get("label", ""))
        aliases = [_norm(a) for a in g.get("aliases") or []]
        if nq == label:
            score = 100
        elif nq in aliases:
            score = 96
        elif nq in label:
            score = 80
        elif any(a and (a in nq.split() or (" " in a and a in nq)) for a in aliases):
            score = 60
        else:
            continue
        out.append((score, g))
    out.sort(key=lambda p: -p[0])
    return [{"group": g, "score": s} for s, g in out]


def picker(vin: str, token: str = "", current: str = "") -> list[dict[str, Any]]:
    """The big-button list for the Live board."""
    return [{"id": g["id"], "label": g["label"], "blurb": g.get("blurb", ""),
             "href": href(vin, g["id"], token), "current": g["id"] == current,
             "n": len(group_channel_ids(g))} for g in groups()]


__all__ = ["groups", "get", "group_channel_ids", "href", "groups_for_system", "groups_for_module", "match",
           "picker", "doc", "reload"]
