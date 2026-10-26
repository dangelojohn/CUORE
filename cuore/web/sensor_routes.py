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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..api.deps import require_token
from . import page_search, sensor_profile_svg
from .routes import _dossier, _page, _set_active_vehicle, _status_strip, _vehicle_bar

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


def _back(vin: str, msg: str, to: str = "") -> RedirectResponse:
    page = "sensors/data" if to == "data" else "sensors"
    return RedirectResponse(url=f"/v/{vin}/{page}?msg={quote(msg)}", status_code=303)


STATUS_WORDS = {"green": "ok good healthy", "orange": "fault out of range", "red": "dead not responding fault",
                "grey": "not read unread"}


def _search_text(s: dict[str, Any]) -> str:
    """Everything a sensor card shows that is worth finding by: names, place, channels, units, status, codes."""
    zones = {z["id"]: z.get("label") or "" for z in sensor_profile_svg.ZONES}
    st = s.get("status") if s.get("status") in STATUS_WORDS else "grey"
    parts: list[Any] = [s.get("label"), s.get("id"), s.get("system"), s.get("module"), s.get("bus"), s.get("zone"),
                        zones.get(str(s.get("zone") or ""), ""), s.get("side"), STATUS_LABEL[st], STATUS_WORDS[st]]
    parts += list(s.get("channels") or [])
    for v in s.get("values") or []:
        parts += [v.get("label"), v.get("channel"), v.get("unit")]
    for c in s.get("codes") or []:
        parts += [c.get("code"), c.get("description"), c.get("state")]
    return page_search.haystack(parts)


def search_sensors(q: str, sensors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in sensors if page_search.matches(q, _search_text(s), page_search.SENSOR_SYNONYMS)]


def _short(text: str) -> str:
    text = str(text or "").strip()
    return text if len(text) <= 160 else text[:157] + "..."


def _photos(key: str, limit: int = 2) -> list[dict[str, Any]]:
    """Real catalogue photos for a CUORE item id; [] when none/no catalogue."""
    try:
        from ..services import component_images
        return component_images.images_for_key(key, limit=limit)
    except Exception:  # noqa: BLE001 -- photos are optional decoration
        return []


@router.get("/v/{vin}/component-images")
def component_images_json(vin: str, key: str = "", limit: int = 3) -> JSONResponse:
    """Catalogue photos for a CUORE item id (sensor id, fuse type, ...)."""
    return JSONResponse({"key": key, "images": _photos(key, max(1, min(int(limit or 3), 12)))})


def _job_inputs(vin: str, dossier: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], dict[str, str]]:
    """(the job's current codes, open symptoms newest first, {code: description}). Never raises, never touches the car."""
    try:
        from ..services import fuse_direct, mes_bridge
        codes = list(mes_bridge.open_codes_for(dossier))
        syms, ctext = fuse_direct.job_inputs(vin, codes, dossier)
        return codes, syms, ctext
    except Exception:  # noqa: BLE001 -- the page works without a job
        return [], [], {}


def check_state(strip: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Can "Check all sensors" work right now? Read from the connection state the vehicle bar already shows."""
    if not strip or strip.get("error"):
        why = (strip or {}).get("error") or "unknown"
        return {"ok": False, "reason": f"The scanner state is unknown ({str(why)[:80]}). Use Connect to car first."}
    if strip.get("mes_state") == "connected":
        return {"ok": False, "reason": "MultiEcuScan has the adapter. Close MultiEcuScan, then check."}
    if not strip.get("buses_verified"):
        return {"ok": False, "reason": f"The car is not connected: the top bar shows Live {strip.get('buses_verified') or 0}/"
                                       f"{strip.get('buses_total') or 0} buses verified. Use Connect to car first."}
    return {"ok": True, "reason": ""}


def _zone_label(zone: Optional[str]) -> str:
    z = sensor_profile_svg.resolve_zone(zone)
    top = sensor_profile_svg.TOP_ZONES.get(z or "") or {}
    return top.get("label") or sensor_profile_svg.ZONE_BY_ID.get(z or "", {}).get("label") or ""


KIND_ORDER = {"fault": 0, "code_live": 1, "code_history": 2, "never": 3, "ok_nojudge": 4, "ok_judged": 5}


def _photo_for(s: dict[str, Any]) -> Optional[dict[str, Any]]:
    """ONE catalogue photo per sensor: the first, de-duplicated by its picture file."""
    seen: set[str] = set()
    for ph in _photos(s["id"], 3):
        if ph.get("photo_url") and ph["photo_url"] not in seen:
            seen.add(ph["photo_url"])
            return {"url": ph["photo_url"], "href": ph.get("part_url") or "", "name": ph.get("name") or "",
                    "alt": f"Mopar catalogue photo of the part type for: {s.get('label') or s['id']}"}
    return None


@router.get("/v/{vin}/sensors", response_class=HTMLResponse)
def sensors_page(request: Request, vin: str, status: str = "", system: str = "",
                 msg: str = "", q: str = "", zone: str = "") -> HTMLResponse:
    from ..services import sensor_direct
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
    zone_f = sensor_profile_svg.resolve_zone(zone.strip()) or ""
    systems = sorted({str(s.get("system") or "other") for s in sensors})

    codes, syms, ctext = _job_inputs(vin, dossier)
    strip = _status_strip()
    call = sensor_direct.direct(sensors, numbers, codes, ctext, syms)
    rows = call["rows"]

    def match(s: dict[str, Any]) -> bool:
        if status_f and s.get("status") != status_f:
            return False
        if zone_f and sensor_profile_svg.resolve_zone(s.get("zone")) != zone_f:
            return False
        return not system_f or str(s.get("system") or "other") == system_f

    shown = [s for s in sensors if match(s)]
    q = page_search.clean_q(q)
    results = []
    for s in (search_sensors(q, shown) if q else []):
        st = s.get("status") if s.get("status") in STATUS_LABEL else "grey"
        results.append({"id": s["id"], "label": s.get("label") or s["id"], "n": numbers[s["id"]],
                        "line": " · ".join(x for x in (str(s.get("system") or "other"), s.get("module") or "",
                                                       STATUS_LABEL[st]) if x)})
    dim = {s["id"] for s in sensors if not match(s)}

    open_ids = set(call["call_ids"]) if len(call["call_ids"]) <= 3 else set()
    open_ids |= {r["id"] for r in results[:1]}
    grouped: dict[str, list[dict[str, Any]]] = {g: [] for g, _, _ in sensor_direct.GROUPS}
    for s in sorted(shown, key=lambda s: (KIND_ORDER[rows[s["id"]]["kind"]],
                                           {"red": 0, "orange": 1}.get(s.get("status"), 2), numbers[s["id"]])):
        r = rows[s["id"]]
        grouped[r["group"]].append({"s": s, "r": r, "n": numbers[s["id"]], "photo": _photo_for(s),
                                    "zone_label": _zone_label(s.get("zone")), "open": s["id"] in open_ids})
    sections = [{"id": g, "title": title, "sub": sub, "items": grouped[g]}
                for g, title, sub in sensor_direct.GROUPS if grouped[g]]

    placed_ids = {s["id"] for s in sensors if sensor_profile_svg.resolve_zone(s.get("zone"))}
    unplaced = [{"s": s, "n": numbers[s["id"]], "r": rows[s["id"]]} for s in shown if s["id"] not in placed_ids]

    def href(st: str = "", sy: str = "", zn: str = "", keep_q: bool = True) -> str:
        parts = [f"{k}={quote(v)}" for k, v in (("status", st), ("system", sy), ("zone", zn), ("q", q if keep_q else "")) if v]
        return f"/v/{vin}/sensors" + ("?" + "&".join(parts) if parts else "")

    items = [{**s, "number": numbers[s["id"]],
              "title": f'{s.get("label", s["id"])} — {rows[s["id"]]["chip"]}'} for s in sensors]
    svg = sensor_profile_svg.sensor_map(items, cluster_href=lambda z: href(status_f, system_f, z, False) + "#sens-list",
                                        dim=dim)
    areas: dict[str, dict[str, Any]] = {}
    for s in sensors:
        z = sensor_profile_svg.resolve_zone(s.get("zone"))
        if z:
            a = areas.setdefault(z, {"zone": z, "label": _zone_label(z), "n": 0,
                                     "href": href(status_f, system_f, z, False) + "#sens-list"})
            a["n"] += 1

    showing = [x for x in (_zone_label(zone_f) if zone_f else "", STATUS_LABEL[status_f] if status_f else "", system_f) if x]
    chip_href = {k: href("" if status_f == k else k, system_f, zone_f) for k in STATUSES}
    sys_href = {sy: href(status_f, sy, zone_f) for sy in systems}
    response = _page(request, "sensors.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="sensors", live_strip=strip,
                     svg=svg, sections=sections, numbers=numbers, unplaced=unplaced, counts=counts, call=call,
                     check=check_state(strip), areas=sorted(areas.values(), key=lambda a: -a["n"]),
                     total=len(sensors), shown=len(shown), checked_at=data.get("checked_at"),
                     status_f=status_f, zone_f=zone_f, zone_label=_zone_label(zone_f), q=q, results=results,
                     results_shown=results[:10], no_match_hint=page_search.HINT_SENSORS,
                     clear_href=href(status_f, system_f, zone_f, False), chip_href=chip_href, sys_href=sys_href,
                     system_f=system_f, systems=systems, all_href=f"/v/{vin}/sensors",
                     status_label=STATUS_LABEL, status_mark=STATUS_MARK, msg=msg, error=error,
                     fmt_time=sensor_direct.fmt_time, showing=showing)
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/sensors/data", response_class=HTMLResponse)
def sensors_data(request: Request, vin: str, msg: str = "") -> HTMLResponse:
    """Owner page: the normal-range forms and the location links, kept off the mechanic's page."""
    dossier = _dossier(vin)
    error: Optional[str] = None
    try:
        data = _sensor_health().health(vin)
    except Exception as exc:  # noqa: BLE001
        data, error = {"sensors": []}, f"Sensor health is not available yet: {exc}"
    sensors = sorted(data.get("sensors") or [], key=lambda s: (str(s.get("system") or "zz"), str(s.get("label") or s.get("id"))))
    numbers = {s["id"]: i for i, s in enumerate(sensors, 1)}
    response = _page(request, "sensor_data.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="sensors",
                     sensors=sensors, numbers=numbers, msg=msg, error=error,
                     zone_label=_zone_label, placed=lambda s: bool(sensor_profile_svg.resolve_zone(s.get("zone"))))
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
    if not isinstance(result, dict):
        return _back(vin, "Checked sensors")
    if result.get("refused"):
        text = str(result.get("error") or "the adapter is busy").strip()
        return _back(vin, _short(f"Could not check: {text}. Close MultiEcuScan (or wait for the adapter), "
                                 "then try again."))
    n, got = result.get("checked", 0), result.get("read", 0)
    return _back(vin, f"Checked {n} sensors: {got} gave a value, {n - got} did not")


@router.post("/v/{vin}/sensors/range", response_class=HTMLResponse)
async def sensors_range(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    to = str(form.get("back", "") or "").strip()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    if not f("source"):
        return _back(vin, "A normal range needs a source (manual page, TechAuthority, measured on this car). Nothing saved.", to)
    try:
        lo, hi = float(f("min")), float(f("max"))
    except ValueError:
        return _back(vin, "Min and max must be numbers. Nothing saved.", to)
    try:
        _sensor_health().add_range(MODEL, f("sensor_id"), f("channel"), lo, hi, f("unit"),
                                   f("source"), "technician")
    except ValueError as exc:
        return _back(vin, _short(f"Range not saved: {exc}"), to)
    except Exception as exc:  # noqa: BLE001
        return _back(vin, _short(f"Range not saved: {exc}"), to)
    return _back(vin, "Normal range saved", to)


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


@router.get("/v/{vin}/sensors/readings", response_class=HTMLResponse)
def sensors_readings(request: Request, vin: str, last: int = 8) -> HTMLResponse:
    """Every saved reading side by side, one column per check, newest first."""
    dossier = _dossier(vin)
    data = _sensor_health().readings(vin)
    last = max(1, min(int(last or 8), 50))
    cols = list(reversed(data["checks"]))[:last]
    table: dict[tuple[str, str], dict[str, Any]] = {}
    for r in data["rows"]:
        if r["at"] not in cols:
            continue
        key = (r["channel"], r["part"])
        row = table.setdefault(key, {"channel": r["channel"], "part": r["part"], "name": r["name"],
                                     "unit": r["unit"], "sensors": r["sensors"], "cells": {}})
        row["cells"][r["at"]] = ({"text": _fmt(r["value"]), "num": r["value"]} if r["error"] is None
                                 else {"text": r["error"], "err": True})
    rows = sorted(table.values(), key=lambda x: (", ".join(x["sensors"]) or "zz", x["name"], x["part"]))
    for row in rows:
        a = row["cells"].get(cols[0]) if cols else None
        b = row["cells"].get(cols[1]) if len(cols) > 1 else None
        nums = [c.get("num") for c in (a, b) if c and not c.get("err")]
        row["delta"] = (_fmt(nums[0] - nums[1]) if len(nums) == 2
                        and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in nums) else "")
    response = _page(request, "sensor_readings.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="sensors",
                     cols=cols, rows=rows, total_checks=len(data["checks"]), last=last)
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/sensors/readings.csv")
def sensors_readings_csv(vin: str):
    """Every saved reading, one line per channel part per check (long form, for a spreadsheet)."""
    import csv
    import io

    from fastapi.responses import Response

    data = _sensor_health().readings(vin)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["check_at", "sensor", "sensor_id", "channel", "part", "name", "value", "unit", "error"])
    for r in data["rows"]:
        w.writerow([r["at"], "; ".join(r["sensors"]), "; ".join(r["sensor_ids"]), r["channel"], r["part"],
                    r["name"], "" if r["value"] is None else r["value"], r["unit"], r["error"] or ""])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="sensor-readings-{vin}.csv"'})
