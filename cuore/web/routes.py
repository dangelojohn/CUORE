"""The bench UI.

Every page calls the same :mod:`cuore.services.mes_bridge` functions the JSON
API does, so the two surfaces cannot disagree about what a car's history says.
Templates render; they do not decide. Chronic classification, TSB matching,
fault-tree content and the gate's criteria all live in ``mes``.

Page set:

===========================  ==================================================
``/``                        vehicle picker and corpus health
``/v/{vin}``                 the dossier
``/v/{vin}/codes``           every code with severity and provenance
``/v/{vin}/code/{code}``     one code's life across sessions
``/v/{vin}/tree``            fault-tree walkthrough
``/v/{vin}/gate``            the evidence gate
``/modules``                 module registry and bus map
``/recordings``              CSV recordings
``/logs``                    the raw log index
===========================  ==================================================
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..services import cache, mes_bridge
from ..services.errors import BridgeError
from ..api.deps import require_token, settings_of

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(include_in_schema=False,
                   dependencies=[Depends(require_token)])


# --- helpers --------------------------------------------------------------


def _page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    """Render a template with the context every page needs."""
    settings = settings_of(request)
    ctx.setdefault("version", __version__)
    ctx.setdefault("profile", settings.profile.value)
    return templates.TemplateResponse(request, name, ctx)


def error_page(request: Request, body: Any) -> HTMLResponse:
    """Render a failure as a page. Used by the app's exception handlers.

    Lives here rather than in ``app.py`` so the template lookup stays with the
    other templates, and takes the same :class:`~cuore.models.ErrorBody` the
    API returns so the two never describe a failure differently.
    """
    settings = settings_of(request)
    return templates.TemplateResponse(
        request, "error.html",
        {"status": body.status, "error": body.error, "detail": body.detail,
         "version": __version__, "profile": settings.profile.value},
        status_code=body.status,
    )


def _dossier(vin: str) -> dict[str, Any]:
    """The cached workup for a VIN. See ``api/vehicles.py`` for why cached."""
    return cache.get_or_build(
        ("workup", vin, mes_bridge.newest_mtime(vin)),
        lambda: mes_bridge.workup(vin=vin),
    )


def _vehicle_bar(vin: str, dossier: dict[str, Any]) -> dict[str, Any]:
    """Data for the sticky context bar.

    It carries provenance and odometer span because those are the two facts
    most easily lost while scrolling, and both change how a page should be
    read: a simulated log is not evidence, and a code spanning 26,500 km is
    not a fresh fault.
    """
    ident = dossier.get("identity", {})
    first, last = ident.get("odometer_first_km"), ident.get("odometer_last_km")
    span = None
    if isinstance(first, (int, float)) and isinstance(last, (int, float)):
        span = int(last) - int(first)
    return {
        "vin": vin,
        "name": ident.get("vehicle") or "(unnamed vehicle)",
        "logs": ident.get("log_count"),
        "first_log": ident.get("first_log"),
        "last_log": ident.get("last_log"),
        "odo_first": first,
        "odo_last": last,
        "odo_span": span,
        "ecus": ident.get("ecu_seen") or [],
    }


# --- pages ----------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Vehicle picker, with the corpus's own health beside it."""
    status = mes_bridge.corpus_status()
    return _page(request, "index.html",
                 vehicles=mes_bridge.vehicles(real_only=True),
                 all_vehicles=mes_bridge.vehicles(),
                 stats=status)


@router.get("/v/{vin}", response_class=HTMLResponse)
def vehicle(request: Request, vin: str) -> HTMLResponse:
    """The dossier: what am I looking at, before the hood opens."""
    dossier = _dossier(vin)
    codes = mes_bridge.open_codes_for(dossier)
    return _page(request, "vehicle.html", vin=vin, d=dossier,
                 bar=_vehicle_bar(vin, dossier), open_codes=codes,
                 tab="dossier")


@router.get("/v/{vin}/codes", response_class=HTMLResponse)
def codes(request: Request, vin: str,
          include_simulation: bool = False) -> HTMLResponse:
    """Every code this car has ever set, ordered by what decides a diagnosis."""
    dossier = _dossier(vin)
    data = mes_bridge.extract_dtcs(vin=vin,
                                   include_simulation=include_simulation)
    return _page(request, "codes.html", vin=vin, rows=data["dtcs"], data=data,
                 bar=_vehicle_bar(vin, dossier),
                 include_simulation=include_simulation, tab="codes")


@router.get("/v/{vin}/code/{code}", response_class=HTMLResponse)
def code_detail(request: Request, vin: str, code: str) -> HTMLResponse:
    """One code's complete life, with its freeze frames beside it."""
    dossier = _dossier(vin)
    history = mes_bridge.dtc_history(code, vin=vin)
    try:
        frames = mes_bridge.freeze_frames(code=code, vin=vin)
    except BridgeError:
        frames = {"count": 0, "frames": []}
    return _page(request, "code.html", vin=vin, code=code.upper(),
                 records=history["matches"], frames=frames,
                 bar=_vehicle_bar(vin, dossier), tab="codes")


@router.get("/v/{vin}/tree", response_class=HTMLResponse)
def tree(request: Request, vin: str, codes: str = "") -> HTMLResponse:
    """Cheapest-first isolation, annotated with this car's own evidence."""
    dossier = _dossier(vin)
    if not codes.strip():
        codes = " ".join(mes_bridge.open_codes_for(dossier))
    result = mes_bridge.fault_tree(codes, vin=vin)
    return _page(request, "tree.html", vin=vin, codes=codes, result=result,
                 bar=_vehicle_bar(vin, dossier), tab="tree")


@router.get("/v/{vin}/gate", response_class=HTMLResponse)
def gate_form(request: Request, vin: str, codes: str = "") -> HTMLResponse:
    """The evidence gate, empty."""
    dossier = _dossier(vin)
    if not codes.strip():
        codes = " ".join(mes_bridge.open_codes_for(dossier))
    return _page(request, "gate.html", vin=vin, result=None,
                 form={"codes": codes, "component": "", "mechanism": "",
                       "disconfirming_test": ""},
                 rows=[{"type": "actuator"}],
                 bar=_vehicle_bar(vin, dossier), tab="gate")


@router.post("/v/{vin}/gate", response_class=HTMLResponse)
async def gate_submit(request: Request, vin: str,
                      codes: str = Form(default=""),
                      component: str = Form(default=""),
                      mechanism: str = Form(default=""),
                      disconfirming_test: str = Form(default="")
                      ) -> HTMLResponse:
    """Gate a proposed diagnosis. Writes nothing, to the car or the corpus.

    Measurement rows arrive as parallel ``m_*`` fields rather than a JSON blob
    so the form degrades without JavaScript -- this gets used on a tablet with
    oily hands, and a page that needs a working script to submit is a page that
    fails at the worst moment.
    """
    form = await request.form()
    rows: list[dict[str, Any]] = []
    for i, mtype in enumerate(form.getlist("m_type")):
        def field(key: str) -> str:
            return str(form.get(f"m_{key}_{i}", "")).strip()

        row: dict[str, Any] = {"type": mtype}
        if mtype == "actuator" and field("operation"):
            row["operation"] = field("operation")
        elif mtype == "freeze_frame" and field("code"):
            row["code"] = field("code")
        elif mtype == "parameter" and field("name"):
            row["name"] = field("name")
            if field("file"):
                row["file"] = field("file")
        elif mtype == "recording_event" and field("file") and field("condition"):
            row["file"] = field("file")
            row["condition"] = field("condition")
        elif mtype == "manual" and field("description"):
            row["description"] = field("description")
        else:
            continue
        rows.append(row)

    result = mes_bridge.assess_verdict(
        vin=vin, codes=codes, component=component, mechanism=mechanism,
        measurements=json.dumps(rows) if rows else "",
        disconfirming_test=disconfirming_test)

    dossier = _dossier(vin)
    return _page(request, "gate.html", vin=vin, result=result,
                 form={"codes": codes, "component": component,
                       "mechanism": mechanism,
                       "disconfirming_test": disconfirming_test},
                 rows=rows or [{"type": "actuator"}],
                 bar=_vehicle_bar(vin, dossier), tab="gate")


@router.get("/modules", response_class=HTMLResponse)
def modules(request: Request, domain: str = "") -> HTMLResponse:
    """The module registry, and which OBD bus each module lives on."""
    data = mes_bridge.module_registry(domain=domain)
    return _page(request, "modules.html", data=data, domain=domain)


@router.get("/recordings", response_class=HTMLResponse)
def recordings(request: Request) -> HTMLResponse:
    return _page(request, "recordings.html",
                 data=mes_bridge.list_recordings())


@router.get("/recording/{name}", response_class=HTMLResponse)
def recording(request: Request, name: str, condition: str = "") -> HTMLResponse:
    """One recording, with optional threshold analysis over it."""
    data = mes_bridge.read_recording(name, preview_rows=15)
    events = None
    events_error = None
    try:
        events = mes_bridge.recording_events(name, condition=condition)
    except BridgeError as exc:
        events_error = str(exc)
    return _page(request, "recording.html", name=name, data=data,
                 events=events, events_error=events_error,
                 condition=condition)


@router.get("/logs", response_class=HTMLResponse)
def logs(request: Request, vin: str = "", kind: str = "",
         include_simulation: bool = False) -> HTMLResponse:
    """The raw index. Provenance is a column, not a footnote."""
    data = mes_bridge.list_logs(vin=vin, kind=kind, limit=200,
                                include_simulation=include_simulation)
    return _page(request, "logs.html", data=data, vin=vin, kind=kind,
                 include_simulation=include_simulation)
