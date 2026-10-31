"""Startup warm-up: build the caches the Job page needs before the first visit.

The keepalive restarts CUORE whenever it is unhealthy or files change, and the
first Job page load afterwards used to pay 9-11 s building the dossier, fault
board, suspect ranking and fault-similarity table. :func:`start` runs those
builds in ONE background daemon thread, so startup and /api/health are never
delayed. A request arriving mid-warm-up simply shares the same caches
(``cache.get_or_build`` / ``fault_similarity``'s single-flight rebuild).

Read-only and adapter-free: nothing here opens a serial port.
Disabled with ``CUORE_NO_WARMUP=1`` (tests) or when no vehicle exists.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

log = logging.getLogger("cuore.warmup")


def _vehicle() -> Optional[str]:
    from . import flow_bridge, mes_bridge
    try:
        vin = flow_bridge.current_vehicle()
    except Exception:  # noqa: BLE001
        vin = None
    if vin:
        return vin
    try:
        vins = {v.get("vin") for v in mes_bridge.vehicles(real_only=True) if v.get("vin")}
    except Exception:  # noqa: BLE001
        return None
    return next(iter(vins)) if len(vins) == 1 else None


def _steps(vin: str) -> list[tuple[str, Callable[[], object]]]:
    def workup():
        from . import jobs_bridge
        return jobs_bridge._cached_workup(vin)      # same cache key the pages use

    def job_view():
        from . import jobs_bridge
        return jobs_bridge.build_job_view(vin)

    def board():
        from . import fault_board
        return fault_board.board(vin)

    def diagnose():
        from . import suspect_ranking
        return suspect_ranking.diagnose(vin)

    def groups():
        from . import fault_similarity
        return fault_similarity.groups(vin)

    def dossier_view():
        from . import dossier_bridge, jobs_bridge
        from ..web import routes as web_routes      # lazy: avoids an import cycle
        return dossier_bridge.build_view(vin, jobs_bridge._cached_workup(vin),
                                         web_routes._status_strip())

    def plans():
        from . import jobs_bridge, mechanic_plan_bridge
        return mechanic_plan_bridge.plans_for_job(vin, jobs_bridge.build_job_view(vin).get("job"))

    def catalog():
        from . import mes_bridge
        return mes_bridge.CATALOG.entries()          # parses every log once (read-only)

    def report():
        from ..web import report_routes             # lazy: avoids an import cycle
        return report_routes._report_context(vin)

    def bay_sheet():
        from . import bay_sheet as bs, dossier_bridge, jobs_bridge
        from ..web import routes as web_routes
        dossier = jobs_bridge._cached_workup(vin)
        bar = web_routes._vehicle_bar(vin, dossier)
        return bs.build(vin, "", bar=bar, verdict=None, url="")

    return [("catalog", catalog), ("workup", workup), ("job_view", job_view), ("dossier_view", dossier_view), ("fault_board", board),
            ("suspect_ranking", diagnose), ("fault_similarity", groups), ("mechanic_plans", plans), ("report", report), ("bay_sheet", bay_sheet)]


def run(vin: Optional[str] = None, steps: Optional[list] = None) -> dict[str, float]:
    """Run every step, each in its own try/except. Returns {step: seconds}
    (negative seconds = failed). Synchronous; :func:`start` threads it."""
    t0 = time.perf_counter()
    vin = vin or _vehicle()
    if not vin:
        log.info("warm-up skipped: no vehicle")
        return {}
    out: dict[str, float] = {}
    for name, fn in (steps if steps is not None else _steps(vin)):
        t = time.perf_counter()
        try:
            fn()
            out[name] = time.perf_counter() - t
            log.info("warm-up %s: %.2fs", name, out[name])
        except Exception as exc:  # noqa: BLE001 -- one failed step must not stop the rest
            out[name] = -(time.perf_counter() - t)
            log.warning("warm-up %s failed after %.2fs: %s: %s", name, -out[name],
                        type(exc).__name__, exc)
    log.info("warm-up done in %.2fs", time.perf_counter() - t0)
    return out


def start(**kw) -> Optional[threading.Thread]:
    """Start the warm-up in a daemon thread and return at once (None if disabled)."""
    if os.environ.get("CUORE_NO_WARMUP") == "1":
        return None
    th = threading.Thread(target=lambda: _guarded(**kw), name="cuore-warmup", daemon=True)
    th.start()
    return th


def _guarded(**kw) -> None:
    try:
        run(**kw)
    except Exception:  # noqa: BLE001
        log.exception("warm-up crashed")
