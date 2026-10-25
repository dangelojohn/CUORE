"""``GET /v/{vin}/sensors``: sensor health -- every sensor of the car as a
coloured dot on a side-profile drawing, plus a numbered list.

Data comes from :mod:`cuore.services.sensor_health` (imported lazily so this
page and its tests work before/without it). Reading the page never contacts
the car; only the explicit "Check all sensors" POST does, and that is a
read-only sweep.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from . import sensor_profile_svg
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

MODEL = "stelvio-2018-2.0"
STATUSES = ("green", "orange", "red", "grey")
STATUS_LABEL = {"green": "OK", "orange": "Fault / out of range", "red": "Dead / not responding",
                "grey": "Not read yet"}
STATUS_MARK = {"green": "✓", "orange": "!", "red": "✕", "grey": "?"}


def _sensor_health():
    from ..services import sensor_health  # lazy: built in parallel
    return sensor_health


def _safe_redirect(url: str) -> bool:
    """Same-site relative path only (no //host, no backslash tricks, no CR/LF)."""
    return url.startswith("/") and not url.startswith("//") and not any(c in url for c in (chr(92), chr(13), chr(10)))


def _back(vin: str, msg: str) -> RedirectResponse:
    return RedirectResponse(url=f"/v/{vin}/sensors?msg={quote(msg)}", status_code=303)


def _short(text: str) -> str:
    text = str(text or "").strip()
    return text if len(text) <= 160 else text[:157] + "..."


@router.get("/v/{vin}/sensors", response_class=HTMLResponse)
def sensors_page(request: Request, vin: str, status: str = "", system: str = "",
                 msg: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    error: Optional[str] = None
    try:
        data = _sensor_health().health(vin)
    except Exception as exc:  # noqa: BLE001 -- the page must render without the service
        data = {"vin": vin, "checked_at": None, "sensors": [], "counts": {}, "unplaced": []}
        error = f"Sensor health is not available yet: {exc}"
    sensors: list[dict[str, Any]] = list(data.get("sensors") or [])
    sensors.sort(key=lambda s: (str(s.get("system") or "zz"), str(s.get("label") or s.get("id"))))
    numbers = {s["id"]: i for i, s in enumerate(sensors, 1)}

    counts = {k: int((data.get("counts") or {}).get(k, 0)) for k in STATUSES}
    if not data.get("counts"):
        for s in sensors:
            counts[s.get("status") if s.get("status") in counts else "grey"] += 1
    status_f = status.strip().lower() if status.strip().lower() in STATUSES else ""
    system_f = system.strip()
    systems = sorted({str(s.get("system") or "other") for s in sensors})

    def match(s: dict[str, Any]) -> bool:
        if status_f and s.get("status") != status_f:
            return False
        return not system_f or str(s.get("system") or "other") == system_f

    shown = [s for s in sensors if match(s)]
    dim = {s["id"] for s in sensors if not match(s)}
    groups: dict[str, list[dict[str, Any]]] = {}
    for s in shown:
        groups.setdefault(str(s.get("system") or "other"), []).append(s)

    _, unplaced_ids = sensor_profile_svg.layout(sensors)
    unplaced = [s for s in sensors if s["id"] in set(unplaced_ids) and match(s)]
    svg = sensor_profile_svg.render(sensors, numbers, dim)

    def href(st: str = "", sy: str = "") -> str:
        q = [f"{k}={quote(v)}" for k, v in (("status", st), ("system", sy)) if v]
        return f"/v/{vin}/sensors" + ("?" + "&".join(q) if q else "")

    chip_href = {k: href("" if status_f == k else k, system_f) for k in STATUSES}
    sys_href = {sy: href(status_f, sy) for sy in systems}

    response = _page(request, "sensors.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="sensors",
                     svg=svg, groups=groups, numbers=numbers, unplaced=unplaced, counts=counts,
                     total=len(sensors), shown=len(shown), checked_at=data.get("checked_at"),
                     status_f=status_f, chip_href=chip_href, sys_href=sys_href, system_f=system_f, systems=systems,
                     status_label=STATUS_LABEL, status_mark=STATUS_MARK, msg=msg, error=error)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/sensors/check", response_class=HTMLResponse)
def sensors_check(vin: str) -> RedirectResponse:
    """Read-only live sweep. Never clears codes."""
    try:
        result = _sensor_health().check_all(vin)
    except Exception as exc:  # noqa: BLE001 -- explain plainly instead of a 500
        text = str(exc).strip() or exc.__class__.__name__
        low = text.lower()
        if "multiecuscan" in low or "mes" in low.split() or "busy" in low:
            text = f"Could not check: {text}. Close MultiEcuScan (or wait for the adapter), then try again."
        else:
            text = f"Could not check sensors: {text}"
        return _back(vin, _short(text))
    n = 0
    if isinstance(result, dict):
        n = result.get("checked", result.get("count", len(result.get("sensors") or [])))
    return _back(vin, f"Checked {n} sensors")


@router.post("/v/{vin}/sensors/range", response_class=HTMLResponse)
async def sensors_range(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    if not f("source"):
        return _back(vin, "A normal range needs a source (manual page, TechAuthority, measured on this car). Nothing saved.")
    try:
        lo, hi = float(f("min")), float(f("max"))
    except ValueError:
        return _back(vin, "Min and max must be numbers. Nothing saved.")
    try:
        _sensor_health().add_range(MODEL, f("sensor_id"), f("channel"), lo, hi, f("unit"),
                                   f("source"), "technician")
    except ValueError as exc:
        return _back(vin, _short(f"Range not saved: {exc}"))
    except Exception as exc:  # noqa: BLE001
        return _back(vin, _short(f"Range not saved: {exc}"))
    return _back(vin, "Normal range saved")
