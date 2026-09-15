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
``/live``                    the live link: adapter, cable, buses, OBD
``/live/module/{code}``      one module's UDS DTCs and identity, live
===========================  ==================================================
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..services import cache, mes_bridge
from ..services.errors import BridgeError
from ..api.deps import require_token, settings_of
from ..live import ops as live_ops
from ..live.buses import BUSES, PIN_1_9_WARNING
from ..live.errors import LiveError

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(include_in_schema=False,
                   dependencies=[Depends(require_token)])


# --- helpers --------------------------------------------------------------


def _status_strip() -> dict[str, Any]:
    """The live link's headline state, cheap enough for every page load.

    No adapter I/O happens here -- ``live_ops.status()`` only reads the
    registry, the lock file and the MES process/window state. This is what
    makes it safe to compute unconditionally rather than opt-in per page,
    which is the point: MES holding the port, or a bus sitting unverified,
    used to be invisible outside ``/live``.
    """
    try:
        s = live_ops.status()
        return {
            "port": s.get("port"), "baud": s.get("baud"),
            "mes_state": (s.get("mes") or {}).get("state"),
            "cable": (s.get("cable") or {}).get("cable"),
            "buses_verified": sum(1 for b in (s.get("cable") or {}).get("buses", [])
                                  if b.get("verified")),
            "buses_total": len((s.get("cable") or {}).get("buses", [])),
            "lock_holder": (s.get("lock") or {}).get("process"),
            "error": None,
        }
    except LiveError as exc:
        return {"error": str(exc)}


def _page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    """Render a template with the context every page needs."""
    settings = settings_of(request)
    ctx.setdefault("version", __version__)
    ctx.setdefault("profile", settings.profile.value)
    ctx.setdefault("live_strip", _status_strip())
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


def _live_observations_for(vin: str) -> tuple[list[dict[str, Any]], str | None]:
    """What the live link has recorded for this VIN, newest first.

    Read-only against the observation store cuore.live already writes to on
    every live read -- nothing here opens the adapter. A gate form with
    nothing to show just means no live session has run for this car yet.
    """
    try:
        obs = live_ops.observations(n=20, vin=vin)["entries"]
        return list(reversed(obs)), None
    except LiveError as exc:
        return [], str(exc)


@router.get("/v/{vin}/gate", response_class=HTMLResponse)
def gate_form(request: Request, vin: str, codes: str = "") -> HTMLResponse:
    """The evidence gate, empty."""
    dossier = _dossier(vin)
    if not codes.strip():
        codes = " ".join(mes_bridge.open_codes_for(dossier))
    live_obs, live_obs_error = _live_observations_for(vin)
    return _page(request, "gate.html", vin=vin, result=None,
                 form={"codes": codes, "component": "", "mechanism": "",
                       "disconfirming_test": ""},
                 rows=[{"type": "actuator"}],
                 live_observations=live_obs, live_observations_error=live_obs_error,
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
        elif mtype == "live" and field("kind"):
            # Verified against cuore.live's own observation record, not typed
            # in -- the fields differ by kind, so only the ones that kind
            # actually uses get carried into the citation.
            row["kind"] = field("kind")
            if row["kind"] in ("dtc", "permanent", "module_dtc") and field("code"):
                row["code"] = field("code")
            if row["kind"] == "readiness" and field("monitor"):
                row["monitor"] = field("monitor")
            if row["kind"] in ("module_dtc", "did") and field("ecu"):
                row["ecu"] = field("ecu")
            if row["kind"] == "did" and field("did"):
                row["did"] = field("did")
            if len(row) <= 2:   # kind + type only -- nothing to verify against
                continue
        else:
            continue
        rows.append(row)

    result = mes_bridge.assess_verdict(
        vin=vin, codes=codes, component=component, mechanism=mechanism,
        measurements=json.dumps(rows) if rows else "",
        disconfirming_test=disconfirming_test)

    dossier = _dossier(vin)
    live_obs, live_obs_error = _live_observations_for(vin)
    return _page(request, "gate.html", vin=vin, result=result,
                 form={"codes": codes, "component": component,
                       "mechanism": mechanism,
                       "disconfirming_test": disconfirming_test},
                 rows=rows or [{"type": "actuator"}],
                 live_observations=live_obs, live_observations_error=live_obs_error,
                 bar=_vehicle_bar(vin, dossier), tab="gate")


@router.get("/modules", response_class=HTMLResponse)
def modules(request: Request, domain: str = "") -> HTMLResponse:
    """The module registry, and which OBD bus each module lives on.

    14 of these 126 codes are also in the live link's own module table --
    known 29-bit address, confirmed or otherwise, on a Giorgio bus. Those
    rows get a link straight to a live UDS read; the two tables no longer
    just happen to describe the same parts without ever pointing at each
    other.
    """
    data = mes_bridge.module_registry(domain=domain)
    try:
        live_codes = {m["code"].upper() for m in live_ops.modules()["modules"]}
    except LiveError:
        live_codes = set()
    return _page(request, "modules.html", data=data, domain=domain,
                 live_codes=live_codes)


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


# --- live link --------------------------------------------------------------
#
# Every value below comes from cuore.live.ops, the same functions the MCP
# tools call. This module never opens the adapter itself and never bypasses
# the ops-layer safety gates (cable declaration, bus verification, the
# transmit-confirmation flag) -- it only decides how to *render* what those
# gates say, including turning a refusal into guidance instead of a 500.
#
# The UI adds one gate of its own, stricter than the live layer's: reading a
# module on CAN-CH or CAN-IHS always shows a confirm checkbox here, even
# though only CAN-CH is flagged transmit_needs_confirmation in cuore.live.buses
# -- both carry chassis/body modules this bench UI treats as sensitive.


def _live_snapshot() -> dict[str, Any]:
    """The always-shown facts: adapter status, cable/bus state, module table.

    Each call is independently wrapped -- one failing (say, no port
    configured) must not blank the other two panels.
    """
    out: dict[str, Any] = {}
    try:
        out["status"] = live_ops.status()
        out["status_error"] = None
    except LiveError as exc:
        out["status"] = None
        out["status_error"] = str(exc)
    try:
        out["cable_data"] = live_ops.buses()
        out["cable_error"] = None
    except LiveError as exc:
        out["cable_data"] = None
        out["cable_error"] = str(exc)
    try:
        out["module_rows"] = live_ops.modules()["modules"]
        out["module_error"] = None
    except LiveError as exc:
        out["module_rows"] = []
        out["module_error"] = str(exc)
    return out


def _live_page(request: Request, **extra: Any) -> HTMLResponse:
    ctx = _live_snapshot()
    ctx["pin_1_9_warning"] = PIN_1_9_WARNING
    ctx["can_ch_note"] = BUSES["can_ch"].notes
    ctx["can_ihs_note"] = BUSES["can_ihs"].notes
    # This page already shows the live state in full below the fold; the
    # header strip would only repeat it.
    ctx["live_strip"] = None
    ctx.update(extra)
    return _page(request, "live.html", **ctx)


@router.get("/live", response_class=HTMLResponse)
def live_page(request: Request, cable_error: str = "") -> HTMLResponse:
    """Adapter status, cable declaration, bus map, module table and OBD."""
    return _live_page(request, cable_error=cable_error or None)


@router.post("/live/cable", response_class=HTMLResponse)
def live_set_cable(cable: str = Form(...)) -> RedirectResponse:
    """Declare the fitted cable, then redirect back (GET/POST/redirect, no JS needed)."""
    try:
        live_ops.set_cable(cable)
    except LiveError as exc:
        return RedirectResponse(url=f"/live?cable_error={quote(str(exc))}",
                                status_code=303)
    return RedirectResponse(url="/live", status_code=303)


@router.post("/live/verify", response_class=HTMLResponse)
def live_verify(request: Request, bus: str = Form(...),
                seconds: float = Form(default=2.0)) -> HTMLResponse:
    """Passive listen on one bus; rendered inline rather than a redirect so
    the frame count and IDs seen are not lost."""
    try:
        result = live_ops.verify_bus(bus, seconds=seconds)
        error = None
    except LiveError as exc:
        result = None
        error = str(exc)
    return _live_page(request, verify_bus_key=bus, verify_result=result,
                      verify_error=error)


@router.post("/live/probe", response_class=HTMLResponse)
def live_probe(request: Request) -> HTMLResponse:
    """Reset the adapter and read its identity. Holds nothing afterwards."""
    try:
        result = live_ops.probe()
        error = None
    except LiveError as exc:
        result = None
        error = str(exc)
    return _live_page(request, probe_result=result, probe_error=error)


_OBD_ACTIONS: dict[str, Any] = {
    "dtcs": live_ops.obd_all_dtcs,
    "readiness": live_ops.obd_readiness,
    "vin": live_ops.obd_vin,
    "voltage": live_ops.obd_voltage,
}


@router.post("/live/obd/{kind}", response_class=HTMLResponse)
def live_obd(request: Request, kind: str) -> HTMLResponse:
    """Legislated OBD on CAN-C: DTCs, readiness, VIN or battery voltage.

    These are Mode 01/02/03/07/09/0A reads, need no cable/verification gate
    and no confirm checkbox -- CAN-C carries no chassis-safety module and the
    live layer itself never lets a write reach the wire from here.
    """
    fn = _OBD_ACTIONS.get(kind)
    if fn is None:
        return _live_page(request, obd_kind=kind, obd_result=None,
                          obd_error=f"unknown legislated-OBD action {kind!r}")
    try:
        result = fn()
        error = None
    except LiveError as exc:
        result = None
        error = str(exc)
    return _live_page(request, obd_kind=kind, obd_result=result, obd_error=error)


@router.get("/live/module/{code}", response_class=HTMLResponse)
def live_module(request: Request, code: str, confirm: bool = False) -> HTMLResponse:
    """One module's UDS DTCs and Annex C identity.

    A refusal from the live layer (unverified bus, unknown module, MES
    holding the adapter) is guidance here, not an error page -- this is the
    single most likely outcome on a bench that has not yet declared a cable
    or run a passive listen.
    """
    code = code.strip()
    try:
        rows = live_ops.modules()["modules"]
    except LiveError:
        rows = []
    row = next((m for m in rows if m["code"].upper() == code.upper()), None)
    bus_key = row["bus"] if row else None
    needs_confirm = bus_key in ("can_ch", "can_ihs")

    dtcs = identity = None
    dtcs_error = identity_error = None
    if needs_confirm and not confirm:
        dtcs_error = identity_error = (
            f"module {code.upper()} lives on {bus_key}, which this bench UI treats as "
            f"sensitive (chassis/body). Tick 'confirm' and read again. This is in addition "
            f"to whatever cuore.live itself enforces for that bus.")
    else:
        try:
            dtcs = live_ops.module_dtcs(code, confirm=confirm)
        except LiveError as exc:
            dtcs_error = str(exc)
        try:
            identity = live_ops.module_identity(code, confirm=confirm)
        except LiveError as exc:
            identity_error = str(exc)

    return _page(request, "live_module.html", code=code.upper(), confirm=confirm,
                 row=row, bus_key=bus_key, needs_confirm=needs_confirm,
                 dtcs=dtcs, dtcs_error=dtcs_error,
                 identity=identity, identity_error=identity_error,
                 pin_1_9_warning=PIN_1_9_WARNING, live_strip=None)
