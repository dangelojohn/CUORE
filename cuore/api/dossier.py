"""GET /api/vehicles/{vin}/view -- the redesigned dossier's data, as JSON.

The HTTP face of ``dossier_bridge.build_view``, so a future PWA or Claude's
own tool layer can read exactly what the server-rendered dossier renders.
Read-only: nothing here writes to the car or the corpus.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..live import ops as live_ops
from ..services import cache, dossier_bridge, mes_bridge
from .deps import require_token

router = APIRouter(tags=["vehicles"], dependencies=[Depends(require_token)])


def _live_status() -> dict[str, Any] | None:
    """The same cheap, I/O-free read ``base.html``'s live strip uses --
    never opens the adapter, so it is safe to call on every view request.
    A broken live link must not break the dossier view."""
    try:
        s = live_ops.status()
        return {"port": s.get("port"),
                "mes_state": (s.get("mes") or {}).get("state"),
                "lock_holder": (s.get("lock") or {}).get("process"),
                "error": None}
    except Exception as exc:  # noqa: BLE001 -- see cuore.web.routes._status_strip
        return {"error": str(exc)}


@router.get("/vehicles/{vin}/view", summary="The redesigned dossier's computed view")
def view(vin: str) -> dict[str, Any]:
    dossier = cache.get_or_build(
        ("workup", vin, mes_bridge.newest_mtime(vin)),
        lambda: mes_bridge.workup(vin=vin))
    return dossier_bridge.build_view(vin, dossier, _live_status())


__all__ = ["router"]
