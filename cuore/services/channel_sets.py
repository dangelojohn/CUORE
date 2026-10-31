"""Saved live-value sets: a named list of channels a mechanic picks again with one press.

Two kinds, shown together as one list:

* the mechanic's own sets, stored per VIN at ``<state dir>/channel_sets/<vin>.json`` (names and channel ids only);
* the Live board's value groups (``cuore/data/value_groups.json``), offered as ready-made sets.

A set holds no scale, limit or unit and never changes what is read: it only ticks boxes on the Recordings page. Channels
that the running session does not have are reported as missing, never silently dropped. No adapter, no network.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from . import value_groups

MAX_SETS = 40
MAX_CHANNELS = 60
MAX_NAME = 40
_VIN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CH = re.compile(r"^[^\x00-\x1f]{1,80}$")
_lock = threading.Lock()


class SetError(Exception):
    """Refused or invalid; the message is shown to the mechanic as-is."""


def _path(vin: str) -> Path:
    if not _VIN.match(vin or ""):
        raise SetError("bad VIN")
    from ..live.config import state_dir
    return Path(state_dir()) / "channel_sets" / f"{vin}.json"


def _load(vin: str) -> list[dict[str, Any]]:
    try:
        doc = json.loads(_path(vin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [s for s in doc.get("sets", []) if isinstance(s, dict) and s.get("name") and isinstance(s.get("channels"), list)]


def _save(vin: str, sets: list[dict[str, Any]]) -> None:
    from ..live.ui_store import atomic_write_text
    atomic_write_text(_path(vin), json.dumps({"sets": sets}, indent=1))


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip().casefold()


def save(vin: str, name: str, channels: Iterable[str]) -> dict[str, Any]:
    """Create or replace the set called ``name`` (case-insensitive). Returns the stored set."""
    name = re.sub(r"\s+", " ", name or "").strip()
    if not name:
        raise SetError("Give the set a name.")
    if len(name) > MAX_NAME:
        raise SetError(f"Set names are at most {MAX_NAME} characters.")
    chans = list(dict.fromkeys(str(c) for c in channels if c))
    if not chans:
        raise SetError("Tick at least one value before saving a set.")
    if len(chans) > MAX_CHANNELS or any(not _CH.match(c) for c in chans):
        raise SetError("That selection is not valid.")
    with _lock:
        sets = [s for s in _load(vin) if _key(s["name"]) != _key(name)]
        if len(sets) >= MAX_SETS:
            raise SetError(f"At most {MAX_SETS} sets; delete one first.")
        item = {"name": name, "channels": chans}
        sets.append(item)
        _save(vin, sets)
    return item


def delete(vin: str, name: str) -> bool:
    with _lock:
        sets = _load(vin)
        kept = [s for s in sets if _key(s["name"]) != _key(name)]
        if len(kept) == len(sets):
            return False
        _save(vin, kept)
    return True


def listing(vin: str, available: Optional[Iterable[str]] = None) -> list[dict[str, Any]]:
    """Every set, the mechanic's first: ``{name, kind, channels, here, missing}``.

    ``here`` = channels the running session has (all of them when ``available`` is None); ``missing`` the rest.
    Ready-made sets with no channel in this session are left out; the mechanic's own are always kept.
    """
    have = None if available is None else set(available)
    out = []
    for s in _load(vin):
        out.append(("own", s["name"], list(s["channels"])))
    for g in value_groups.groups():
        ids = value_groups.group_channel_ids(g)
        if ids:
            out.append(("group", str(g.get("label") or g.get("id")), ids))
    rows = []
    for kind, name, ids in out:
        here = ids if have is None else [c for c in ids if c in have]
        if kind == "group" and not here:
            continue
        rows.append({"name": name, "kind": kind, "channels": ids, "here": here,
                     "missing": [c for c in ids if c not in here]})
    return rows
