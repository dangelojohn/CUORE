"""Settings page: GET/POST /settings. Units (km/mi) is the only editable setting; folders and adapter are read-only."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..live import config as live_config
from . import units
from .routes import _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _folder(label: str, path: str) -> dict:
    return {"label": label, "path": path, "exists": Path(path).exists()}


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    state = live_config.state_dir()
    folders = live_config.mes_folders()
    port, port_src = live_config.resolve_port()
    baud, baud_src = live_config.resolve_baud()
    rows = [
        _folder("MES install folder", live_config.MES_INSTALL),
        _folder("MES log folder", folders.get("log_folder", "")),
        _folder("State directory", str(state)),
        _folder("Repo data directory", str(Path(__file__).resolve().parents[1] / "data")),
        _folder("Recordings directory", str(state / "recordings")),
    ]
    adapter = [
        ("Port", f"{port or 'not set'} ({port_src})"),
        ("Baud", f"{baud} ({baud_src})"),
        ("Cable", live_config.default_cable()),
    ]
    return _page(request, "settings.html", units=units.get_units(), folders=rows, adapter=adapter,
                 settings_file=str(units.settings_path()))


@router.post("/settings")
def settings_save(units_choice: str = Form("metric", alias="units")) -> RedirectResponse:
    units.set_units(units_choice)
    return RedirectResponse("/settings", status_code=303)
