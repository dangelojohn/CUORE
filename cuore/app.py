"""FastAPI application factory.

Two surfaces over one service layer:

* ``/api/*`` -- JSON, mirroring the MCP tool surface call-for-call. This is
  what a future PWA, the in-car node, and Claude's tool layer all talk to.
* ``/`` -- server-rendered pages for bench use. They are a *client* of the same
  bridge, not a parallel implementation, so the two cannot disagree.

Server-rendered rather than a single-page app on purpose: no build step, no
bundle to keep in sync, and it has to run on a Raspberry Pi.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from . import __version__, bootstrap  # noqa: F401  -- bootstrap has a side effect

import anyio  # noqa: E402
from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.openapi.docs import get_swagger_ui_html  # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from mes.errors import MesError  # noqa: E402  -- needs bootstrap to have run

from .api import attested as attested_api  # noqa: E402
from .api import buscapture as buscapture_api  # noqa: E402
from .api import modifications as modifications_api  # noqa: E402
from .api import scan_health as scan_health_api  # noqa: E402
from .api import cables as cables_api  # noqa: E402
from .api import cases as cases_api, checklists as checklists_api, dossier as dossier_api, electrical as electrical_api, feedback as feedback_api, flow as flow_api, jobs as jobs_api, known_good, live, live_ui, liveboard, logs, media as media_api, parts as parts_api, recordings, reference, shop as shop_api, system, systems as systems_api, systems_map as systems_map_api, tests as tests_api, timeline as timeline_api, tools as tools_api, tools_kb as tools_kb_api, experience as experience_api, vehicles, wiring as wiring_api  # noqa: E402
from .api import mes_learn as mes_learn_api  # noqa: E402
from .api import export as export_api  # noqa: E402
from .api import car_identify as car_identify_api  # noqa: E402
from .api import ingest as ingest_api  # noqa: E402
from .config import Settings, load  # noqa: E402
from .models import ErrorBody  # noqa: E402
from .services.errors import BridgeError  # noqa: E402
from .web import bench_routes  # noqa: E402
from .web import brand_gate as brand_gate_mod  # noqa: E402
from .web.brand_gate import BrandEmpty, brand_gate  # noqa: E402
from .web import dashboard_routes  # noqa: E402
from .web import drivetrain_routes  # noqa: E402
from .web import dossier_routes  # noqa: E402
from .web import electrical_routes  # noqa: E402
from .web import sensor_routes  # noqa: E402
from .web import fuse_routes  # noqa: E402
from .web import procedure_proto_routes  # noqa: E402
from .web import harness_routes  # noqa: E402
from .web import mes_param_routes  # noqa: E402
from .web import parity_routes  # noqa: E402
from .web import handoff_routes  # noqa: E402
from .web import adjustments_routes  # noqa: E402
from .web import witech_routes  # noqa: E402
from .web import configuration_routes  # noqa: E402
from .web import hardware_routes  # noqa: E402
from .web import settings_routes  # noqa: E402
from .web import about_routes  # noqa: E402
from .web import accounts_routes  # noqa: E402
from .web import field_quality_routes  # noqa: E402
from .web import arrive_ready_routes  # noqa: E402
from .web import warranty_routes  # noqa: E402
from .web import library_routes  # noqa: E402
from .web import bay_sheet_routes  # noqa: E402
from .web import bay_board_routes  # noqa: E402
from .web import bay_service_sheet_routes  # noqa: E402
from .web import car_session_routes  # noqa: E402
from .web import connect_session_routes  # noqa: E402
from .web import helped_routes  # noqa: E402
from .web import five_minute_routes  # noqa: E402
from .web import find_routes  # noqa: E402
from .web import handbook_routes  # noqa: E402
from .web import path_diag_routes  # noqa: E402
from .web import path_tests_routes  # noqa: E402
from .web import diagnosis_routes  # noqa: E402
from .web import crosscheck_routes  # noqa: E402
from .web import intermittent_routes  # noqa: E402
from .web import power_budget_routes  # noqa: E402
from .web import trends_routes  # noqa: E402
from .web import load_step_routes  # noqa: E402
from .web import purge_trim_routes  # noqa: E402
from .web import fullscan_routes  # noqa: E402
from .web import labels_routes  # noqa: E402
from .web import live_dashboard_routes  # noqa: E402
from .web import liveboard_routes  # noqa: E402
from .web import recordings_routes  # noqa: E402
from .web import learn_routes  # noqa: E402
from .web import mes_learn_routes  # noqa: E402
from .web import owner_routes  # noqa: E402
from .web import oil_level_routes  # noqa: E402
from .web import facts_routes  # noqa: E402
from .api import owner_events as owner_events_api  # noqa: E402
from .api import scanlog as scanlog_api  # noqa: E402
from .api import vision as vision_api  # noqa: E402
from .web import media_routes  # noqa: E402
from .web import mods_routes  # noqa: E402
from .web import modules_routes  # noqa: E402
from .web import parts_routes  # noqa: E402
from .web import catalog_routes  # noqa: E402
from .web import report_routes  # noqa: E402
from .web import routes as web_routes  # noqa: E402
from .web import scan_health_routes  # noqa: E402
from .web import next_session_routes  # noqa: E402
from .web import bench_interactive_routes  # noqa: E402
from .web import tests_interactive_routes  # noqa: E402
from .web import sensors_interactive_routes  # noqa: E402
from .web import scan_plan_routes  # noqa: E402
from .web import scanlog_routes  # noqa: E402
from .web import service_routes  # noqa: E402
from .web import add_routes  # noqa: E402
from .web import shop_routes  # noqa: E402
from .web import systems_interactive_routes  # noqa: E402
from .web import system_routes  # noqa: E402
from .web import systems_routes  # noqa: E402
from .web import tests_routes  # noqa: E402
from .web import timeline_routes  # noqa: E402
from .web import tools_routes  # noqa: E402
from .web import tsb_routes  # noqa: E402
from .web import cables_routes  # noqa: E402
from .web import ask_claude_routes  # noqa: E402
from .web import slvt_routes  # noqa: E402
from .web import inbox_routes  # noqa: E402
from .web import jobs_routes  # noqa: E402
from .web import fault_board_routes  # noqa: E402
from .web import login_routes  # noqa: E402
from .web import approve_routes  # noqa: E402
from .api.deps import LoginRedirect, require_token, resolve_token  # noqa: E402
from .web import flow_globals, tools_kb_globals  # noqa: F401
from .web import icons, i18n  # noqa: F401
from .web import static_version  # noqa: F401

log = logging.getLogger("cuore")

DESCRIPTION = """
Companion service over the MultiEcuScan diagnostic toolchain.

Every analysis here comes from the `mes` library and is unit-tested against the
real log corpus. Two conventions run through the whole API and are worth knowing
before reading any payload:

* **Simulation logs are excluded by default.** Most of the FES corpus is MES
  practice data. Pass `include_simulation=true` deliberately, or not at all.
* **SCAN provenance is `unverifiable`, never clean.** That format carries no
  simulation marker, so claiming a SCAN is real would be a claim the file
  cannot support.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app. Safe to call repeatedly (tests do)."""
    settings = settings or load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("CUORE %s starting: profile=%s bind=%s:%s",
                 __version__, settings.profile.value, settings.host,
                 settings.port)
        if settings.lan_exposed and not resolve_token(settings.token):
            log.warning(
                "Bound to %s with no token set. The log corpus contains "
                "customer VINs and is now readable by every device on this "
                "network. Set CUORE_TOKEN or run scripts/web_token.py --set.",
                settings.host)
        try:
            from .services import warmup
            warmup.start()          # background daemon thread; never blocks startup
        except Exception:  # noqa: BLE001
            log.exception("warm-up could not start")
        yield
        # Shutdown: end a running live-data poll session so its recorder is
        # flushed and the adapter released rather than dropped mid-frame. A
        # no-op when nothing is running; never allowed to block shutdown.
        try:
            from .live import ops as live_ops
            await anyio.to_thread.run_sync(live_ops.live_session_stop)
        except Exception:  # noqa: BLE001
            log.exception("live session stop at shutdown failed")

    app = FastAPI(
        title="CUORE",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url=None,       # re-added below behind require_token
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(brand_gate)],   # empty skeleton for a brand with no data (web/brand_gate.py)
    )
    app.state.settings = settings

    # --- error handling ---------------------------------------------------
    # The bridge raises transport-neutral errors. API callers get one uniform
    # JSON body so failure parses exactly one way; browsers get a page, because
    # a tech who mistypes a VIN should not be handed raw JSON.

    def _render_failure(request: Request, exc: Exception, status: int):
        body = ErrorBody(error=type(exc).__name__, detail=str(exc),
                         status=status)
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=status, content=body.model_dump())
        return web_routes.error_page(request, body)

    @app.exception_handler(BridgeError)
    async def _bridge_error(request: Request, exc: BridgeError):
        return _render_failure(request, exc, exc.status)

    # Anything the library raises that the bridge did not classify is a bad
    # request, not a server fault: these are parse and lookup failures driven
    # by caller input, and a 500 would misreport whose problem it is.
    @app.exception_handler(MesError)
    async def _mes_error(request: Request, exc: MesError):
        return _render_failure(request, exc, 400)

    @app.exception_handler(BrandEmpty)
    async def _brand_empty(request: Request, exc: BrandEmpty):
        return brand_gate_mod.render(request, exc)

    @app.exception_handler(LoginRedirect)
    async def _login_redirect(request: Request, exc: LoginRedirect):
        return RedirectResponse(exc.location, status_code=302)

    # --- routes -----------------------------------------------------------
    app.include_router(login_routes.router)
    app.include_router(accounts_routes.router)
    app.include_router(approve_routes.router)

    @app.get("/api/openapi.json", include_in_schema=False,
             dependencies=[Depends(require_token)])
    async def _openapi():
        return JSONResponse(app.openapi())

    @app.get("/api/docs", include_in_schema=False,
             dependencies=[Depends(require_token)])
    async def _docs():
        return get_swagger_ui_html(openapi_url="/api/openapi.json",
                                   title="CUORE - API docs")

    app.include_router(system.router, prefix="/api")
    app.include_router(ingest_api.router, prefix="/api")
    app.include_router(attested_api.router, prefix="/api")
    app.include_router(scan_health_api.router, prefix="/api")
    app.include_router(vehicles.router, prefix="/api")
    app.include_router(reference.router, prefix="/api")
    app.include_router(recordings.router, prefix="/api")
    app.include_router(logs.router, prefix="/api")
    app.include_router(live.router, prefix="/api")
    app.include_router(live_ui.router, prefix="/api")
    app.include_router(liveboard.router, prefix="/api")
    app.include_router(buscapture_api.router, prefix="/api")
    app.include_router(modifications_api.router, prefix="/api")
    app.include_router(owner_events_api.router, prefix="/api")
    app.include_router(scanlog_api.router, prefix="/api")
    app.include_router(vision_api.router, prefix="/api")
    app.include_router(tests_api.router, prefix="/api")
    app.include_router(known_good.router, prefix="/api")
    app.include_router(checklists_api.router, prefix="/api")
    app.include_router(dossier_api.router, prefix="/api")
    app.include_router(timeline_api.router, prefix="/api")
    app.include_router(tools_api.router, prefix="/api")
    app.include_router(experience_api.router, prefix="/api")
    app.include_router(media_api.router, prefix="/api")
    app.include_router(parts_api.router, prefix="/api")
    app.include_router(feedback_api.router, prefix="/api")
    app.include_router(jobs_api.router, prefix="/api")
    app.include_router(systems_api.router, prefix="/api")
    app.include_router(systems_map_api.router, prefix="/api")
    app.include_router(electrical_api.router, prefix="/api")
    app.include_router(wiring_api.router, prefix="/api")
    app.include_router(flow_api.router, prefix="/api")
    app.include_router(tools_kb_api.router, prefix="/api")
    app.include_router(cables_api.router, prefix="/api")
    app.include_router(shop_api.router, prefix="/api")
    app.include_router(cases_api.router, prefix="/api")
    app.include_router(mes_learn_api.router, prefix="/api")
    app.include_router(export_api.router, prefix="/api")
    app.include_router(dashboard_routes.api_router, prefix="/api")
    app.include_router(oil_level_routes.api_router, prefix="/api")
    app.include_router(service_routes.api_router, prefix="/api")
    app.include_router(drivetrain_routes.api_router, prefix="/api")
    app.include_router(labels_routes.api_router, prefix="/api")
    app.include_router(car_identify_api.router, prefix="/api")
    app.include_router(web_routes.router)
    app.include_router(ask_claude_routes.router)
    app.include_router(scanlog_routes.router)
    app.include_router(scan_plan_routes.router)
    app.include_router(next_session_routes.router)
    app.include_router(bench_interactive_routes.router)
    app.include_router(tests_interactive_routes.router)
    app.include_router(sensors_interactive_routes.router)
    app.include_router(bench_routes.router)
    app.include_router(add_routes.router)
    app.include_router(shop_routes.router)
    app.include_router(dashboard_routes.router)
    app.include_router(oil_level_routes.router)
    app.include_router(facts_routes.router)
    app.include_router(service_routes.router)
    app.include_router(drivetrain_routes.router)
    app.include_router(labels_routes.router)
    app.include_router(dossier_routes.router)
    app.include_router(timeline_routes.router)
    app.include_router(tools_routes.router)
    app.include_router(tsb_routes.router)
    app.include_router(cables_routes.router)
    app.include_router(slvt_routes.router)
    app.include_router(inbox_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(fault_board_routes.router)
    app.include_router(live_dashboard_routes.router)
    app.include_router(liveboard_routes.router)
    app.include_router(recordings_routes.router)
    app.include_router(learn_routes.router)
    app.include_router(mes_learn_routes.router)
    app.include_router(owner_routes.router)
    app.include_router(tests_routes.router)
    app.include_router(media_routes.router)
    app.include_router(parts_routes.router)
    app.include_router(catalog_routes.router)
    app.include_router(mods_routes.router)
    app.include_router(report_routes.router)
    app.include_router(systems_routes.router)
    app.include_router(systems_interactive_routes.router)
    app.include_router(system_routes.router)
    app.include_router(electrical_routes.router)
    app.include_router(sensor_routes.router)
    app.include_router(fuse_routes.router)
    app.include_router(procedure_proto_routes.router)
    app.include_router(mes_param_routes.router)
    app.include_router(parity_routes.router)
    app.include_router(handoff_routes.router)
    app.include_router(adjustments_routes.router)
    app.include_router(witech_routes.router)
    app.include_router(configuration_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(hardware_routes.router)
    app.include_router(about_routes.router)
    app.include_router(field_quality_routes.router)
    app.include_router(arrive_ready_routes.router)
    app.include_router(warranty_routes.router)
    app.include_router(library_routes.router)
    app.include_router(bay_sheet_routes.router)
    app.include_router(bay_service_sheet_routes.router)
    app.include_router(bay_board_routes.router)
    app.include_router(car_session_routes.router)
    app.include_router(connect_session_routes.router)
    app.include_router(helped_routes.router)
    app.include_router(five_minute_routes.router)
    app.include_router(find_routes.router)
    app.include_router(handbook_routes.router)
    app.include_router(path_diag_routes.router)
    app.include_router(harness_routes.router)
    app.include_router(path_tests_routes.router)
    app.include_router(diagnosis_routes.router)
    app.include_router(crosscheck_routes.router)
    app.include_router(intermittent_routes.router)
    app.include_router(power_budget_routes.router)
    app.include_router(trends_routes.router)
    app.include_router(load_step_routes.router)
    app.include_router(purge_trim_routes.router)
    app.include_router(modules_routes.router)
    app.include_router(scan_health_routes.router)
    app.include_router(fullscan_routes.router)

    # Every /static URL is already cache-busted by static_version.static_url's
    # ``?v=<mtime hash>`` query string, so a long max-age would be safe -- but
    # a stray hand-typed /static/ link (or icons.svg's #fragment reference,
    # which browsers don't even send back to the server to revalidate) must
    # never stick a tech with yesterday's CSS/JS. no-cache forces a
    # revalidation request every time instead of serving straight from disk
    # cache, which costs nothing on a bench LAN.
    @app.middleware("http")
    async def _no_cache_static(request: Request, call_next):
        # One MES-log directory listing per request (see mes.catalog.request_scope).
        from mes import catalog as _mes_catalog
        # GET only: a POST (write, guard) always sees fresh state.
        _mes_catalog.request_scope.set({} if request.method == "GET" else None)
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    app.mount("/static",
              StaticFiles(directory=str(web_routes.STATIC_DIR)),
              name="static")

    return app
