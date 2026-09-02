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


def stats() -> dict[str, Any]:
    """What the cache is currently holding, for the status endpoint."""
    return {"entries": len(_store), "capacity": MAX_ENTRIES}
