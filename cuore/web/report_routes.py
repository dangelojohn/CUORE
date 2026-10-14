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


_UNKNOWN_TEXT = "UNKNOWN -- use the service manual (TechAuthority)"


def _code_description(code: str) -> dict[str, Any]:
    """This platform's sourced description for ``code`` (``mes.dtc_descriptions``),
    or an honest ``UNKNOWN`` -- never invented, never raises. Covers a code the
    report's own tables never got a description for because it was never seen
    in an FES log (a module code read only live, e.g. B10AA)."""
    try:
        from mes import dtc_descriptions
    except Exception:  # noqa: BLE001 -- optional dependency
        return {"code": code, "text": _UNKNOWN_TEXT, "source": "none", "confidence": "UNKNOWN"}
    try:
        return dtc_descriptions.code_description(code)
    except Exception:  # noqa: BLE001 -- a report must never 500 on this
        return {"code": code, "text": _UNKNOWN_TEXT, "source": "none", "confidence": "UNKNOWN"}


def _live_code_suffixes(vin: str) -> dict[str, str]:
    """Base code -> newest-seen failure-type-byte suffix ("4A", "86", ...),
    read straight off this car's own live module-DTC (UDS 0x19) observations
    -- the one place the full "CODE-FTB" token still survives;
    ``dossier_bridge``'s own ``live_module_dtcs`` already strips it down to
    the base code. ``{}`` on any failure -- never raises."""
    try:
        from ..live import store as live_store
    except Exception:  # noqa: BLE001 -- optional dependency
        return {}
    try:
        obs = live_store.recent_observations(500, vin=vin, kind="module_dtcs")
    except Exception:  # noqa: BLE001
        return {}
    best: dict[str, tuple[str, str]] = {}
    for o in obs:
        at = o.get("at") or ""
        data = o.get("data") or {}
        for d in data.get("dtcs") or []:
            full = str(d.get("code") or "")
            if "-" not in full:
                continue
            base, _, suffix = full.partition("-")
            base = base.strip().upper()
            if not base or not suffix:
                continue
            if base not in best or at > best[base][0]:
                best[base] = (at, suffix)
    return {k: v[1] for k, v in best.items()}


def _failure_type_text(suffix: str | None) -> dict[str, Any]:
    """The decoded meaning of one failure-type-byte suffix (``mes.dtc``), or
    an honest ``UNKNOWN`` -- never invented, never raises."""
    if not suffix:
        return {"text": _UNKNOWN_TEXT, "confidence": "UNKNOWN"}
    try:
        from mes import dtc as dtc_mod
    except Exception:  # noqa: BLE001 -- optional dependency
        return {"text": _UNKNOWN_TEXT, "confidence": "UNKNOWN"}
    try:
        ft = dtc_mod.failure_type(suffix)
    except Exception:  # noqa: BLE001
        ft = None
    if ft is None:
        return {"text": _UNKNOWN_TEXT, "confidence": "UNKNOWN"}
    d = ft.to_dict()
    return {"text": d.get("text") or d.get("meaning") or _UNKNOWN_TEXT,
            "confidence": d.get("confidence", "UNKNOWN"), "source": d.get("source")}


def _all_report_codes(view: dict[str, Any]) -> list[str]:
    """Every base code currently known for this car, for the "Possible
    fixes"/"Parts for the open codes" sections -- the Codes table (sourced
    from this car's MES-log history) unioned with this car's own live
    module (UDS 0x19) reads, ACTIVE or HISTORY alike, so a code seen live
    but never logged to an FES file (e.g. B10AA, read only live) is never
    silently dropped the way a loop over ``view["codes"]`` alone would drop
    it."""
    codes = {c["code"] for c in (view.get("codes") or [])}
    codes.update(m["code"] for m in (view.get("live_module_dtcs") or []))
    return sorted(codes)


def _codes_covered_by_open_work(view: dict[str, Any]) -> set[str]:
    return {c for card in (view.get("open_work") or []) for c in card.get("codes", [])}


def _fixes_fallback(vin: str, view: dict[str, Any],
                    all_codes: list[str]) -> list[dict[str, Any]]:
    """One entry per live code the open-work cards do not already cover --
    a sourced fault-tree step sequence (``mes_bridge.fault_tree``, the same
    source ``dossier_bridge``'s own generic open-work cards use) when one
    exists, else an explicit UNKNOWN line, never a silently-missing code.

    In practice this only ever fires for a code read live but never logged
    to an FES file *and* not covered by the hand-curated EVAP/network
    family steps either (e.g. B10AA, HISTORY-state only, read live on
    2026-10-13) -- every code this car's MES-log history or an ACTIVE live
    module read already earns an open-work card for.
    """
    covered = _codes_covered_by_open_work(view)
    suffixes = _live_code_suffixes(vin)
    out: list[dict[str, Any]] = []
    for code in all_codes:
        if code in covered:
            continue
        description = _code_description(code)
        failure_type = _failure_type_text(suffixes.get(code))
        try:
            result = mes_bridge.fault_tree(code, vin=vin)
        except Exception:  # noqa: BLE001 -- a report must never 500 on this
            result = {}
        trees = result.get("trees") or []
        steps = []
        for t in trees[:1]:
            for s in (t.get("steps") or [])[:6]:
                steps.append({"text": s.get("title") or s.get("test") or "Step",
                             "ref": s.get("source")})
        out.append({"code": code, "description": description,
                   "failure_type": failure_type, "steps": steps})
    return out


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


def _parts_section(codes: list[str]) -> list[dict[str, Any]]:
    """One group per code -- module codes (U/B) wired in the same way a
    P-code already is, never silently skipped: a code with nothing in
    ``mes.parts`` still gets a row here, marked ``unknown``, so the report
    says "UNKNOWN -- use the service manual (TechAuthority)" for it rather
    than making it look like the question was never asked."""
    out = []
    for code in codes:
        rows = _parts_for_code(code)
        out.append({"code": code, "parts": rows, "unknown": not rows})
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

    all_codes = _all_report_codes(view)

    return {
        "vin": vin,
        "bar": bar,
        "view": view,
        "stamp": _stamp(bar),
        "feels": _feels_for_open_work(vin, view["open_work"]),
        "correlation_findings": correlation_findings,
        "parts": _parts_section(all_codes),
        "fixes_fallback": _fixes_fallback(vin, view, all_codes),
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
