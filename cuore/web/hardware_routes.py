"""Hardware page: GET /hardware. Read-only. GET never opens the adapter; it shows the identity the link
already holds. POST /hardware/probe runs the existing audited ops.probe path only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..live import ops
from ..live.adapter_check import check_adapter, load_hardware
from .routes import _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])
PARITY = Path(__file__).resolve().parents[1] / "data" / "parity_items.json"
_last_probe: dict[str, Any] = {}


def parity_rows() -> list[dict[str, Any]]:
    items = json.loads(PARITY.read_text(encoding="utf-8"))["items"]
    return [{"function": i["function"], "mes": i["mes"].get("note", ""), "cuore": i["cuore"].get("note", ""),
             "state": i["state"], "screen": i.get("screen") or i["cuore"].get("screen")}
            for i in items if i["cuore"].get("has") == "yes" and not i.get("mes_item")]


@router.get("/hardware", response_class=HTMLResponse)
def hardware_page(request: Request, msg: str = "") -> HTMLResponse:
    try:
        st = ops.status()
    except Exception:  # noqa: BLE001
        st = {}
    ident = _last_probe.get("identity") or st.get("adapter_identity") or {}
    try:
        mes = ops.mes_settings()
    except Exception as exc:  # noqa: BLE001
        mes = {"error": str(exc)}
    check = check_adapter(ident, _last_probe.get("battery_voltage"), None)
    return _page(request, "hardware.html", hw=load_hardware(), check=check, mes=mes,
                 port=st.get("port"), baud=st.get("baud"), rows=parity_rows(), flash_msg=msg[:300])


@router.post("/hardware/probe")
def hardware_probe() -> RedirectResponse:
    try:
        r = ops.probe()
        _last_probe.clear()
        _last_probe.update(r)
        text = "Probe finished."
    except Exception as exc:  # noqa: BLE001
        text = f"Not probed: {exc}"
    return RedirectResponse(f"/hardware?msg={quote(text[:300])}", status_code=303)
