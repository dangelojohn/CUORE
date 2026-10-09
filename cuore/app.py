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

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from mes.errors import MesError  # noqa: E402  -- needs bootstrap to have run

from .api import attested as attested_api  # noqa: E402
from .api import cases as cases_api, checklists as checklists_api, dossier as dossier_api, electrical as electrical_api, feedback as feedback_api, flow as flow_api, jobs as jobs_api, known_good, live, live_ui, liveboard, logs, media as media_api, parts as parts_api, recordings, reference, shop as shop_api, system, systems as systems_api, systems_map as systems_map_api, tests as tests_api, timeline as timeline_api, tools as tools_api, tools_kb as tools_kb_api, experience as experience_api, vehicles  # noqa: E402
from .config import Settings, load  # noqa: E402
from .models import ErrorBody  # noqa: E402
from .services.errors import BridgeError  # noqa: E402
from .web import bench_routes  # noqa: E402
from .web import dashboard_routes  # noqa: E402
from .web import drivetrain_routes  # noqa: E402
from .web import dossier_routes  # noqa: E402
from .web import electrical_routes  # noqa: E402
from .web import labels_routes  # noqa: E402
from .web import live_dashboard_routes  # noqa: E402
from .web import liveboard_routes  # noqa: E402
from .web import media_routes  # noqa: E402
from .web import modules_routes  # noqa: E402
from .web import parts_routes  # noqa: E402
from .web import report_routes  # noqa: E402
from .web import routes as web_routes  # noqa: E402
from .web import service_routes  # noqa: E402
from .web import shop_routes  # noqa: E402
from .web import system_routes  # noqa: E402
from .web import systems_routes  # noqa: E402
from .web import tests_routes  # noqa: E402
from .web import timeline_routes  # noqa: E402
from .web import tools_routes  # noqa: E402
from .web import inbox_routes  # noqa: E402
from .web import jobs_routes  # noqa: E402
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
        if settings.unguarded_lan:
            log.warning(
                "Bound to %s with no token set. The log corpus contains "
                "customer VINs and is now readable by every device on this "
                "network. Set CUORE_TOKEN.", settings.host)
        yield

    app = FastAPI(
        title="CUORE",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
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

    # --- routes -----------------------------------------------------------
    app.include_router(system.router, prefix="/api")
    app.include_router(attested_api.router, prefix="/api")
    app.include_router(vehicles.router, prefix="/api")
    app.include_router(reference.router, prefix="/api")
    app.include_router(recordings.router, prefix="/api")
    app.include_router(logs.router, prefix="/api")
    app.include_router(live.router, prefix="/api")
    app.include_router(live_ui.router, prefix="/api")
    app.include_router(liveboard.router, prefix="/api")
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
    app.include_router(flow_api.router, prefix="/api")
    app.include_router(tools_kb_api.router, prefix="/api")
    app.include_router(shop_api.router, prefix="/api")
    app.include_router(cases_api.router, prefix="/api")
    app.include_router(dashboard_routes.api_router, prefix="/api")
    app.include_router(service_routes.api_router, prefix="/api")
    app.include_router(drivetrain_routes.api_router, prefix="/api")
    app.include_router(labels_routes.api_router, prefix="/api")
    app.include_router(web_routes.router)
    app.include_router(bench_routes.router)
    app.include_router(shop_routes.router)
    app.include_router(dashboard_routes.router)
    app.include_router(service_routes.router)
    app.include_router(drivetrain_routes.router)
    app.include_router(labels_routes.router)
    app.include_router(dossier_routes.router)
    app.include_router(timeline_routes.router)
    app.include_router(tools_routes.router)
    app.include_router(inbox_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(live_dashboard_routes.router)
    app.include_router(liveboard_routes.router)
    app.include_router(tests_routes.router)
    app.include_router(media_routes.router)
    app.include_router(parts_routes.router)
    app.include_router(report_routes.router)
    app.include_router(systems_routes.router)
    app.include_router(system_routes.router)
    app.include_router(electrical_routes.router)
    app.include_router(modules_routes.router)

    # Every /static URL is already cache-busted by static_version.static_url's
    # ``?v=<mtime hash>`` query string, so a long max-age would be safe -- but
    # a stray hand-typed /static/ link (or icons.svg's #fragment reference,
    # which browsers don't even send back to the server to revalidate) must
    # never stick a tech with yesterday's CSS/JS. no-cache forces a
    # revalidation request every time instead of serving straight from disk
    # cache, which costs nothing on a bench LAN.
    @app.middleware("http")
    async def _no_cache_static(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    app.mount("/static",
              StaticFiles(directory=str(web_routes.STATIC_DIR)),
              name="static")

    return app
