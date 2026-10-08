"""Printable and PDF reports: what the mechanic hands to the owner or files
with the job.

A third client of the same bridges every other ``/v/`` page uses --
``dossier_bridge.build_view``, ``timeline_bridge``, ``experience_bridge`` --
never a second source of truth. Nothing here invents a fix: a report's
"possible fixes" section is exactly the open-work checklist steps and
bulletin actions the dossier already carries, each with its own source and
confidence. Parts and media are read lazily because neither is guaranteed to
be wired on every install; a missing one means a skipped section, not a 500.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from ..api.deps import require_token
from ..services import dossier_bridge, experience_bridge, mes_bridge, timeline_bridge
from ..services.errors import BridgeError, NotFound
from . import report_pdf
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


# --- lazy, optional data sources -------------------------------------------


def _parts_for_code(code: str) -> list[dict[str, Any]]:
    """Parts for one code, or ``[]`` -- the parts bridge may not be wired."""
    try:
        from ..services import parts_bridge
    except Exception:  # noqa: BLE001 -- optional dependency
        return []
    try:
        return list(parts_bridge.parts_for_code(code) or [])
    except Exception:  # noqa: BLE001 -- a report must never 500 on this
        return []


def _cases_for(vin: str, codes: list[str]) -> list[dict[str, Any]]:
    """Prior cases for this vehicle's model matching these codes, or ``[]``
    -- the cases bridge may not be wired (``cases_api`` is not registered
    on ``app.py`` yet; see ``cuore/api/cases.py``)."""
    try:
        from ..services import cases_bridge
    except Exception:  # noqa: BLE001 -- optional dependency
        return []
    try:
        return list(cases_bridge.match(vin, codes).get("matches") or [])
    except Exception:  # noqa: BLE001 -- a report must never 500 on this
        return []


def _photos_for(vin: str, limit: int = 6) -> list[dict[str, Any]]:
    """Up to ``limit`` media rows for this vehicle, or ``[]`` -- the media
    library may not be wired."""
    try:
        from ..live import media as media_mod
    except Exception:  # noqa: BLE001 -- optional dependency
        return []
    try:
        rows = media_mod.search(vin=vin) or []
    except Exception:  # noqa: BLE001
        return []
    return list(rows[:limit])


# --- shared context ---------------------------------------------------------


def _stamp(bar: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "data_through": bar.get("last_log") or "no logs on file",
    }


def _feels_for_open_work(vin: str, open_work: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """"What the driver would feel" per open code family, next to this car's
    own symptom-correlation pattern for that code."""
    out = []
    for card in open_work:
        for code in card.get("codes", []):
            try:
                feel = timeline_bridge.code_feel(vin, code)
            except Exception:  # noqa: BLE001
                continue
            out.append({"family": card.get("family"), "family_title": card.get("title"),
                       **feel})
    return out


def _experience_for(open_work: list[dict[str, Any]], codes: list[dict[str, Any]]
                    ) -> list[dict[str, Any]]:
    out = []
    seen_families: set[str] = set()
    for card in open_work:
        fam = card.get("family")
        if not fam or fam in seen_families:
            continue
        seen_families.add(fam)
        res = experience_bridge.links_for(family=fam)
        if res.get("links"):
            out.append({"label": card.get("title") or fam, "links": res["links"]})
    for c in codes:
        res = experience_bridge.links_for(code=c["code"])
        if res.get("links"):
            out.append({"label": c["code"], "links": res["links"]})
    return out


def _parts_section(codes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in codes:
        rows = _parts_for_code(c["code"])
        if rows:
            out.append({"code": c["code"], "parts": rows})
    return out


def _report_context(vin: str) -> dict[str, Any]:
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    live_status = web_routes._status_strip()
    view = dossier_bridge.build_view(vin, dossier, live_status)

    try:
        notes = mes_bridge.notes(vin, target_kind="vehicle")["notes"]
    except BridgeError:
        notes = []

    try:
        timeline = timeline_bridge.build_timeline(vin)
        correlation_findings = timeline.get("findings") or []
    except Exception:  # noqa: BLE001 -- a report must still render
        correlation_findings = []

    return {
        "vin": vin,
        "bar": bar,
        "view": view,
        "stamp": _stamp(bar),
        "feels": _feels_for_open_work(vin, view["open_work"]),
        "correlation_findings": correlation_findings,
        "parts": _parts_section(view["codes"]),
        "experience": _experience_for(view["open_work"], view["codes"]),
        "notes": notes,
        "photos": _photos_for(vin, 6),
        "cases": _cases_for(vin, [c["code"] for c in view["codes"]]),
    }


def _code_report_context(vin: str, code: str) -> dict[str, Any]:
    code_upper = code.strip().upper()
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    live_status = web_routes._status_strip()
    view = dossier_bridge.build_view(vin, dossier, live_status)

    history = mes_bridge.dtc_history(code_upper, vin=vin)  # raises NotFound -> 404

    try:
        feel = timeline_bridge.code_feel(vin, code_upper)
    except Exception:  # noqa: BLE001
        feel = None

    row = next((c for c in view["codes"] if c["code"] == code_upper), None)
    family = row.get("family") if row else None
    card = next((c for c in view["open_work"] if c.get("family") == family), None) if family else None
    bulletins = [b for b in view["bulletins"] if code_upper in (b.get("codes") or [])]
    frames = [f for f in view["freeze_frames"] if f.get("code") == code_upper]

    try:
        notes = mes_bridge.notes(vin, target_kind="code", target_id=code_upper)["notes"]
    except BridgeError:
        notes = []

    exp = experience_bridge.links_for(code=code_upper)
    if family:
        fam_exp = experience_bridge.links_for(family=family)
        exp = {"links": (exp.get("links") or []) + (fam_exp.get("links") or [])}

    return {
        "vin": vin, "code": code_upper, "bar": bar, "view": view,
        "stamp": _stamp(bar), "row": row, "feel": feel, "card": card,
        "bulletins": bulletins, "frames": frames, "notes": notes,
        "parts": _parts_for_code(code_upper), "experience": exp.get("links") or [],
        "history": history,
    }


# --- routes ------------------------------------------------------------------


@router.get("/v/{vin}/report", response_class=HTMLResponse)
def report(request: Request, vin: str) -> HTMLResponse:
    """The printable report: same page, on screen or on paper. ``print.css``
    does the rest."""
    ctx = _report_context(vin)
    response = web_routes._page(request, "report.html", tab="report", **ctx)
    web_routes._set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/report.pdf")
def report_pdf_route(vin: str, size: str = "letter") -> Response:
    ctx = _report_context(vin)
    pdf_bytes = report_pdf.build_vehicle_pdf(ctx, size=size)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{vin}-report.pdf"'})


@router.get("/v/{vin}/code/{code}/report.pdf")
def code_report_pdf(vin: str, code: str, size: str = "letter") -> Response:
    """One code, "problem and possible fixes" -- a 404 for a code with no
    history on this VIN, same as every other code page."""
    ctx = _code_report_context(vin, code)
    pdf_bytes = report_pdf.build_code_pdf(ctx, size=size)
    code_upper = ctx["code"]
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="{vin}-{code_upper}-report.pdf"'})


__all__ = ["router"]
