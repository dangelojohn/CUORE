"""A memo cache keyed on corpus freshness.

:class:`mes.catalog.Catalog` already caches each log's parsed metadata on
``(mtime, size)`` and rescans the directory on every call, so new MES logs
appear without a restart and unchanged files are never re-parsed.

``workup.build`` is the one analysis that escapes that cache: to answer "what
has already been tried on this car" it calls ``fes.load_fes`` directly on every
FES log for the VIN, on every request. At seventeen logs that is imperceptible;
across a shop's corpus it is a full re-parse per page view.

So: memoise the dossier on ``(vin, newest mtime in that vehicle's logs)``. A new
log, an edited log, or a re-exported one all move the mtime and the entry falls
out on its own -- no invalidation hook, no staleness window, and no risk of
serving yesterday's picture of a car that is on the lift right now.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, Callable

#: Small on purpose. The working set is "vehicles someone is looking at",
#: which is one or two, and each dossier holds every DTC and freeze frame for
#: a car.
MAX_ENTRIES = 16

_store: "OrderedDict[tuple, Any]" = OrderedDict()


def get_or_build(key: tuple, build: Callable[[], Any]) -> Any:
    """Return the cached value for ``key``, or build and store it.

    ``key`` must include whatever makes the value stale -- for corpus-derived
    values that means the newest mtime, not just the VIN.
    """
    if key in _store:
        _store.move_to_end(key)
        return _store[key]
    value = build()
    _store[key] = value
    while len(_store) > MAX_ENTRIES:
        _store.popitem(last=False)
    return value


def clear() -> None:
    """Drop everything. Used by tests; not wired to a route."""
    _store.clear()
    _obs_index.clear()


def stats() -> dict[str, Any]:
    """What the cache is currently holding, for the status endpoint."""
    return {"entries": len(_store), "capacity": MAX_ENTRIES}


# --- observations.jsonl, parsed once per file state ------------------------
#
# ``live.store.recent_observations`` reads and json-parses the WHOLE
# observations file on every call (2.3 MB / ~9000 lines on the real car), and
# one Job page render makes about twenty such calls: ~0.6 s warm, ~1.9 s
# cold. This keeps (vin, kind, raw line) per file state -- (path, mtime, size)
# -- so the file is parsed once until something appends to it, and each call
# json-parses only the last ``n`` lines it actually returns. Same result as
# the store function (fresh dicts, same filters, same ``[-n:]`` slice).

_ANY = object()      # "no filter" marker in the (vin, kind) index
_obs_index: dict[str, tuple[tuple[int, int], list[tuple[Any, Any, str]], dict]] = {}


def recent_observations(n: int = 50, vin: str = "", kind: str = "") -> list[dict[str, Any]]:
    """Drop-in for ``live.store.recent_observations`` that parses the file once."""
    from ..live import store as live_store          # lazy: keeps this module import-free
    p = live_store.observations_path()
    from mes.catalog import request_scope           # one stat per GET request
    scope = request_scope.get()
    stamp = scope.get(("obs_stamp", str(p))) if scope is not None else None
    if stamp is None:
        try:
            st = p.stat()
        except OSError:
            return []
        stamp = (st.st_mtime_ns, st.st_size)
        if scope is not None:
            scope[("obs_stamp", str(p))] = stamp
    hit = _obs_index.get(str(p))
    if hit is None or hit[0] != stamp:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows: list[tuple[Any, Any, str]] = []
        for line in lines:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                rows.append((obj.get("vin"), obj.get("kind"), line))
        idx: dict[tuple, list[str]] = {}
        for v, k, line in rows:                     # one pass: every (vin, kind) filter pre-bucketed
            for key in ((_ANY, _ANY), (v, _ANY), (_ANY, k), (v, k)):
                idx.setdefault(key, []).append(line)
        hit = (stamp, rows, idx)
        _obs_index[str(p)] = hit
        while len(_obs_index) > 4:                  # tests point this at temp files
            _obs_index.pop(next(iter(_obs_index)))
    picked = hit[2].get((vin or _ANY, kind or _ANY), [])
    return [json.loads(line) for line in picked[-n:]]
