"""The bench UI.

Every page calls the same :mod:`cuore.services.mes_bridge` functions the JSON
API does, so the two surfaces cannot disagree about what a car's history says.
Templates render; they do not decide. Chronic classification, TSB matching,
fault-tree content and the gate's criteria all live in ``mes``.

Page set:

===========================  ==================================================
``/``                        vehicle picker and corpus health
``/v/{vin}``                 the bench (cuore/web/bench_routes.py) -- what to
                              do right now
``/v/{vin}/dossier``         the full dossier
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
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..services import cache, dossier_bridge, mes_bridge
from ..services.errors import BridgeError
from ..api.deps import actor, require_token, settings_of
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
    except Exception as exc:  # noqa: BLE001 - a broken strip must never 500 a page
        return {"error": str(exc)}


#: data-marque values cuore.css actually themes -- an unrecognised/unknown
#: WMI (or no VIN at all, e.g. a vehicle-less page) falls back to "alfa",
#: this project's first-and-default marque, rather than leaking "unknown"
#: into data-marque where no theme would match it.
_THEMED_MARQUES = ("alfa", "maserati", "ferrari")


def _marque_for(ctx: dict[str, Any]) -> str:
    """The marque this page's vehicle (if any) should theme as.

    Every ``/v/{vin}/*`` route already passes ``vin=vin`` into ``_page()``'s
    ctx -- see ``bench_routes.py``/``jobs_routes.py``/``systems_routes.py``/
    ``tests_routes.py`` etc. Computing the marque once, here, means every
    one of those pages' ``data-marque`` (base.html) and marque-conditional
    copy agrees, instead of each route guessing (or not bothering, which is
    how ``data-marque`` ended up hardcoded to "alfa" before this existed).
    """
    vin = ctx.get("vin") or ""
    if not vin:
        return "alfa"
    try:
        marque = mes_bridge.marque_for_vin(vin)
    except Exception:  # noqa: BLE001 -- a broken decode must never sink a page
        marque = "unknown"
    return marque if marque in _THEMED_MARQUES else "alfa"


def _page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    """Render a template with the context every page needs."""
    settings = settings_of(request)
    ctx.setdefault("version", __version__)
    ctx.setdefault("profile", settings.profile.value)
    ctx.setdefault("marque", _marque_for(ctx))
    if "live_strip" not in ctx:  # not setdefault: the strip is not free to compute
        ctx["live_strip"] = _status_strip()
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


#: The 5 coarse system-filter buckets the codes table groups codes into
#: (review R8) -- matches the dossier's own cluster families 1:1 by reusing
#: dossier_bridge's EVAP special-case and generic SAE-prefix rules, so a
#: code row's "system" here is never a second, disagreeing guess at the
#: same classification the dossier already made for that code's cluster.
_SYSTEM_BUCKET_ORDER = ("EVAP", "Network", "Body", "Chassis", "Engine other")
_GENERIC_BUCKET = {"network": "Network", "body": "Body", "chassis": "Chassis",
                   "adas": "Chassis"}


def _code_family_and_bucket(base: str) -> tuple[str, str]:
    """``(family_key, bucket)`` for one base DTC (e.g. ``"P0456"``).

    ``family_key`` is the exact slug a dossier cluster is anchored at
    (``cluster-evap``, ``cluster-network``, ...); ``bucket`` is the coarser
    of the 5 filter chips the codes table shows. Never raises on an
    unrecognised prefix -- falls back to "Engine other" rather than
    dropping the row from every filter.
    """
    from ..services import dossier_bridge as _db
    try:
        if base in _db._EVAP_CODES:
            return "EVAP", "EVAP"
        fam = _db._generic_family_for(base)
    except Exception:  # noqa: BLE001 -- a classification miss must never 500 a page
        fam = None
    if fam is None:
        return "other", "Engine other"
    key, _label = fam
    return key, _GENERIC_BUCKET.get(key, "Engine other")


def _relative_ago(ts: str | None) -> str:
    """"11 d ago" / "3 mo ago" / "2 y ago" -- coarse enough for a table
    column; the cell's own title attribute keeps the exact timestamp (see
    codes.html), so nothing is actually lost by rounding here."""
    if not ts:
        return "—"
    s = str(ts).strip()
    dt = None
    for fmt_len, parser in ((19, lambda v: datetime.strptime(v[:19], "%Y-%m-%d %H:%M:%S")),
                            (10, lambda v: datetime.strptime(v[:10], "%Y-%m-%d"))):
        try:
            dt = parser(s)
            break
        except ValueError:
            continue
    if dt is None:
        return s
    days = (datetime.now() - dt).days
    if days < 0:
        days = 0
    if days == 0:
        return "today"
    if days < 31:
        return f"{days} d ago"
    months = days // 30
    if months < 12:
        return f"{months} mo ago"
    return f"{days // 365} y ago"


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


# --- the active vehicle -----------------------------------------------------
#
# The seam between the corpus side of this app and the live side used to be
# total: /v/{vin} knows a VIN, /live never did. A cookie is the whole fix --
# visiting a vehicle's dossier makes it the vehicle any live read tags itself
# against, until you visit a different one or clear it. Query-string ?vin=
# always wins over the cookie, so a link from the dossier is self-contained
# even if the cookie is stale or scripting is off.

_VIN_COOKIE = "cuore_vin"


def _set_active_vehicle(response: Response, vin: str) -> None:
    response.set_cookie(_VIN_COOKIE, vin, max_age=60 * 60 * 24 * 30, samesite="lax")


def _active_vehicle(request: Request, vin_param: str = "") -> str:
    """The VIN a live read should tag itself with: query param, then cookie."""
    return vin_param.strip() or request.cookies.get(_VIN_COOKIE, "").strip()


def _active_vehicle_bar(vin: str) -> dict[str, Any] | None:
    """The small "you are working on" fact, shown on the live pages. None if
    the active VIN does not resolve to anything in the corpus -- a stale
    cookie after a corpus root changes should not error, just stop showing."""
    if not vin:
        return None
    try:
        dossier = _dossier(vin)
    except BridgeError:
        return None
    ident = dossier.get("identity", {})
    return {"vin": vin, "name": ident.get("vehicle") or vin}


def _match_live_modules(ecu_seen: list[str]) -> list[dict[str, Any]]:
    """Which of this car's own logged ECUs the live link can also reach.

    ``ecu_seen`` carries MES's full hardware description ("Magneti Marelli
    IAW 10JA CF6/EOBD Injection (2.0)"); the live table's module names are
    drawn from the same source material and match by equality or containment
    -- checked both directions, since the live table sometimes carries a
    trailing qualifier the corpus string does not ("Body Computer Marelli
    (949)" vs "Body Computer Marelli (949), gateway").
    """
    try:
        live_rows = live_ops.modules()["modules"]
    except LiveError:
        return []
    seen_lower = [s.lower() for s in ecu_seen]
    out = []
    for m in live_rows:
        name_lower = (m.get("name") or "").lower()
        if any(name_lower == s or name_lower.startswith(s) or s in name_lower
               for s in seen_lower):
            out.append(m)
    return out


# --- pages ----------------------------------------------------------------


_BRAND_COOKIE = "cuore_brand"   # session cookie: the last brand picked, only ever highlights a tile


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """The landing page: pick a brand. Never redirects, whatever brand or car
    is remembered -- the CUORE logo always comes back here."""
    from ..services import landing_bridge
    last = request.cookies.get(_BRAND_COOKIE, "")
    n = landing_bridge.counts()
    brands = [dict(b, cars=n.get(b["key"], 0), last=(b["key"] == last))
              for b in landing_bridge.brands()]
    return _page(request, "landing.html", brands=brands, live_strip=None)


@router.get("/cars", response_class=HTMLResponse)
def cars_page(request: Request, brand: str = "", q: str = "") -> HTMLResponse:
    """Big cards for the cars of one brand (VIN/WMI rule), plus Add a car.
    No ``brand`` -> the remembered one, else every car."""
    from ..services import landing_bridge
    key = brand or request.cookies.get(_BRAND_COOKIE, "")
    chosen = landing_bridge.brand(key)
    cars = landing_bridge.cars(q, chosen["key"] if chosen else "")
    for c in cars:
        c["last_seen_ago"] = _relative_ago(c["last_seen"]) if c["last_seen"] else ""
    resp = _page(request, "cars.html", brand=chosen, cars=cars, q=q.strip(),
                 marque=chosen["key"] if chosen else "alfa", live_strip=None)
    if chosen:
        resp.set_cookie(_BRAND_COOKIE, chosen["key"], samesite="lax")
    return resp


@router.get("/vehicles", response_class=HTMLResponse)
def vehicles_page(request: Request) -> HTMLResponse:
    """Vehicle picker, with the corpus's own health beside it -- the old
    home page, kept reachable from the header's "Vehicles" link."""
    status = mes_bridge.corpus_status()
    return _page(request, "index.html",
                 vehicles=mes_bridge.vehicles(real_only=True),
                 all_vehicles=mes_bridge.vehicles(),
                 stats=status)


def _live_panel_for(vin: str, ecu_seen: list[str]) -> dict[str, Any]:
    """The dossier's embedded live section: bus state plus this car's own
    reachable modules, not the full 126-entry registry or the full 25-entry
    live table -- just the intersection with what this VIN has actually
    logged. Each matched module still carries ``usable``: being on this car
    is not the same as having a confirmed address, and a link that will
    only refuse is worse than no link.
    """
    out: dict[str, Any] = {"buses": [], "modules": [], "error": None}
    try:
        out["buses"] = live_ops.buses()["buses"]
    except LiveError as exc:
        out["error"] = str(exc)
        return out
    out["modules"] = _match_live_modules(ecu_seen)
    return out


@router.get("/v/{vin}/dossier", response_class=HTMLResponse)
def vehicle(request: Request, vin: str) -> HTMLResponse:
    """The full dossier: what am I looking at, before the hood opens.

    Used to live at ``/v/{vin}`` -- that path is now the bench
    (``cuore/web/bench_routes.py``), the smaller "what to do right now"
    screen. Every existing link to ``#open-work``/``#sec-*`` on this page
    still resolves the same way; only the path it hangs off changed.
    """
    dossier = _dossier(vin)
    codes = mes_bridge.open_codes_for(dossier)
    bar = _vehicle_bar(vin, dossier)
    vehicle_notes = mes_bridge.notes(vin, target_kind="vehicle")["notes"]
    live_status = _status_strip()
    view = dossier_bridge.build_view(vin, dossier, live_status)
    from ..services import tsb_xref_bridge  # local: keeps this module's import graph unchanged
    xr = tsb_xref_bridge.safe_xref(vin)
    tsb_xref = None
    if xr:
        tsb_xref = {"top": tsb_xref_bridge.top(xr, 5), "by_hypothesis": xr["by_hypothesis"],
                    "hypotheses": xr["hypotheses"], "by_repair": xr["by_repair"][:10],
                    "job_id": xr["job_id"]}
    open_jobs: list[dict[str, Any]] = []
    try:
        from mes import jobs as _jobs  # local: every open job, in the order jobs.current() picks
        for j in _jobs.open_jobs(vin):
            open_jobs.append({"id": j["id"], "title": j.get("complaint") or j["id"],
                              "opened_at": j.get("opened_at"), "safety": _jobs.has_safety(j),
                              "hypotheses": sum(1 for h in j["hypotheses"] if not h.get("deleted"))})
    except Exception:  # noqa: BLE001 -- the dossier must render without the job list
        open_jobs = []
    response = _page(request, "vehicle.html", vin=vin, d=dossier, bar=bar, tsb_xref=tsb_xref,
                     open_jobs=open_jobs,
                     open_codes=codes, live_panel=_live_panel_for(vin, bar["ecus"]),
                     notes_list=vehicle_notes, note_target_kind="vehicle",
                     note_target_id="", note_redirect=f"/v/{vin}/dossier",
                     note_kind_locked=True,
                     tab="dossier", view=view, live_strip=live_status)
    _set_active_vehicle(response, vin)
    return response


#: state column order when sorting by State -- the same "what changes a
#: decision" order ``mes_bridge`` documents for ``severity``.
_STATE_RANK = {"returned": 0, "chronic": 1, "recurring": 2, "cleared": 3,
               "seen-once": 4}

#: sortable columns on the codes page -> (row key function, first-click
#: direction). Counts, distance and dates open newest/largest first; text
#: columns open A-Z. ``None`` from a key function means "no value": those
#: rows always go last, whichever way the column is sorted.
_CODE_SORTS: dict[str, tuple[Any, str]] = {
    "code": (lambda r: (r.get("dtc") or "").upper() or None, "asc"),
    "state": (lambda r: _STATE_RANK.get(r.get("severity") or ""), "asc"),
    "system": (lambda r: (_SYSTEM_BUCKET_ORDER.index(r["system_bucket"])
                          if r.get("system_bucket") in _SYSTEM_BUCKET_ORDER
                          else len(_SYSTEM_BUCKET_ORDER)), "asc"),
    "description": (lambda r: ", ".join(r.get("descriptions") or []).lower() or None, "asc"),
    "module": (lambda r: ", ".join(r.get("modules") or []).lower() or None, "asc"),
    "sessions": (lambda r: r.get("sessions") or 0, "desc"),
    "first": (lambda r: r.get("first_seen") or None, "desc"),
    "last": (lambda r: r.get("last_seen") or None, "desc"),
    "distance": (lambda r: r.get("distance_span_km"), "desc"),
}


def _sort_code_rows(rows: list[dict[str, Any]], sort: str,
                    direction: str) -> tuple[list[dict[str, Any]], str, str]:
    """Re-order the codes table by one column -> (rows, sort, direction).

    An unknown or empty ``sort`` keeps the diagnosis order from
    ``extract_dtcs``. The sort is stable, so rows that tie keep that
    diagnosis order too.
    """
    if sort not in _CODE_SORTS:
        return rows, "", ""
    key, first_dir = _CODE_SORTS[sort]
    direction = direction if direction in ("asc", "desc") else first_dir
    have = [r for r in rows if key(r) is not None]
    missing = [r for r in rows if key(r) is None]
    have.sort(key=key, reverse=(direction == "desc"))
    return have + missing, sort, direction


@router.get("/v/{vin}/codes", response_class=HTMLResponse)
def codes(request: Request, vin: str,
          include_simulation: bool = False, system: str = "",
          sort: str = "", dir: str = "", q: str = "") -> HTMLResponse:  # noqa: A002
    """Every code this car has ever set, ordered by what decides a diagnosis.

    Review R8: each row is shaped here (not re-sorted -- ``extract_dtcs``
    already orders returned/chronic/cleared/seen-once, and that order is
    preserved through the filter below, unless the mechanic picks a column
    with ``?sort=``) with a relative "ago" date, an
    "xN" session count, and the system bucket/cluster anchor used for the
    filter chips and the row's link back to its dossier cluster.
    """
    dossier = _dossier(vin)
    data = mes_bridge.extract_dtcs(vin=vin,
                                   include_simulation=include_simulation)
    for r in data["dtcs"]:
        base = (r.get("dtc") or "").split("-")[0]
        family_key, bucket = _code_family_and_bucket(base)
        r["family_key"] = family_key
        r["system_bucket"] = bucket
        r["cluster_href"] = f"/v/{vin}/dossier#cluster-{family_key.lower()}"
        r["first_seen_ago"] = _relative_ago(r.get("first_seen"))
        r["last_seen_ago"] = _relative_ago(r.get("last_seen"))
        r["sessions_x"] = f"x{r.get('sessions') or 0}"

    from ..services import codes_call
    from . import page_search
    job_codes, blocker, action = codes_call.job_state(vin, dossier)
    codes_call.shape(data["dtcs"], job_codes)
    codes_call.attach_board(data["dtcs"], vin)
    system_filter = (system or "").strip()
    rows = data["dtcs"]
    if system_filter:
        rows = [r for r in rows if r["system_bucket"].lower() == system_filter.lower()]
    q = page_search.clean_q(q)
    if q:
        rows = [r for r in rows if page_search.matches(
            q, page_search.haystack(r["search_parts"]), codes_call.CODE_SYNONYMS)]
    rows, sort, dir = _sort_code_rows(rows, (sort or "").strip().lower(),
                                      (dir or "").strip().lower())
    groups = [] if sort else codes_call.group_rows(rows)
    # With ?q= the call line and the Go-to chip counts describe the FILTERED rows (empty chips drop out);
    # the unfiltered totals stay available as small text.
    call = codes_call.build_call(rows if q else data["dtcs"], job_codes, blocker, vin, action, query=q)
    all_groups = codes_call.group_rows(rows if q else data["dtcs"])
    go_chips = [{"kind": "state", "text": f"{g['label']} ({g['n']})", "href": f"#grp-{g['key']}"}
                for g in all_groups] + call["targets"]

    response = _page(request, "codes.html", vin=vin, rows=rows, data=data,
                     flash_msg=(request.query_params.get("msg") or "")[:300], flash_kind=request.query_params.get("mk") or "ok",
                     sort=sort, sort_dir=dir, q=q, groups=groups, call=call, go_chips=go_chips,
                     total_rows=len(data["dtcs"]),
                     state_help=codes_call.STATE_HELP, state_label=codes_call.STATE_LABEL, no_match_hint=page_search.HINT_CODES,
                     sort_first_dir={k: v[1] for k, v in _CODE_SORTS.items()},
                     bar=_vehicle_bar(vin, dossier),
                     include_simulation=include_simulation, tab="codes",
                     system_filter=system_filter,
                     system_buckets=_SYSTEM_BUCKET_ORDER)
    _set_active_vehicle(response, vin)
    return response


#: same honest-never-invented text the report page uses (``report_routes.
#: _UNKNOWN_TEXT``) -- kept as a second literal rather than imported from
#: there because ``report_routes`` imports this module at load time
#: (``from . import routes as web_routes``), so the reverse import would
#: be circular.
_CODE_UNKNOWN_TEXT = "UNKNOWN -- use the service manual (TechAuthority)"


def _module_dtc_state(flags: dict[str, Any]) -> str | None:
    """ACTIVE, HISTORY, or ``None`` -- same rule as ``dossier_bridge.
    _module_dtc_state``, reimplemented here for the same reason ``_base``
    is reimplemented there: one fewer cross-module private import."""
    if flags.get("testFailed") or flags.get("pendingDTC"):
        return "ACTIVE"
    if flags.get("confirmedDTC") or flags.get("testFailedSinceLastClear"):
        return "HISTORY"
    return None


def _code_failure_type(suffix: str) -> dict[str, Any]:
    """The decoded meaning of one failure-type-byte suffix (``mes.dtc``),
    or an honest ``UNKNOWN`` -- never invented, never raises."""
    if not suffix:
        return {"text": _CODE_UNKNOWN_TEXT, "confidence": "UNKNOWN"}
    try:
        from mes import dtc as dtc_mod
    except Exception:  # noqa: BLE001 -- optional dependency
        return {"text": _CODE_UNKNOWN_TEXT, "confidence": "UNKNOWN"}
    try:
        ft = dtc_mod.failure_type(suffix)
    except Exception:  # noqa: BLE001
        ft = None
    if ft is None:
        return {"text": _CODE_UNKNOWN_TEXT, "confidence": "UNKNOWN"}
    d = ft.to_dict()
    return {"text": d.get("text") or d.get("meaning") or _CODE_UNKNOWN_TEXT,
            "confidence": d.get("confidence", "UNKNOWN"), "source": d.get("source")}


def _code_description_fallback(code: str) -> dict[str, Any]:
    """This platform's sourced description for ``code``, or an honest
    ``UNKNOWN`` -- never invented, never raises. Covers a code never seen
    in an FES log (a module code read only live, e.g. B10AA, U1736)."""
    try:
        from mes import dtc_descriptions
    except Exception:  # noqa: BLE001 -- optional dependency
        return {"code": code, "text": _CODE_UNKNOWN_TEXT, "source": "none", "confidence": "UNKNOWN"}
    try:
        return dtc_descriptions.code_description(code)
    except Exception:  # noqa: BLE001 -- this page must never 500 on this
        return {"code": code, "text": _CODE_UNKNOWN_TEXT, "source": "none", "confidence": "UNKNOWN"}


def _code_fault_tree_steps(vin: str, code: str) -> list[dict[str, Any]]:
    """Up to the first tree's first 6 steps for ``code`` (``mes_bridge.
    fault_tree``, the same source the report's own fallback entry uses),
    or ``[]`` when no tree covers it -- the template shows an explicit
    UNKNOWN line in that case, never a silently-missing section."""
    try:
        result = mes_bridge.fault_tree(code, vin=vin)
    except Exception:  # noqa: BLE001 -- this page must never 500 on this
        result = {}
    steps: list[dict[str, Any]] = []
    for t in (result.get("trees") or [])[:1]:
        for s in (t.get("steps") or [])[:6]:
            steps.append({"text": s.get("title") or s.get("test") or "Step",
                         "ref": s.get("source")})
    return steps


def _live_code_occurrences(vin: str, code_upper: str) -> list[dict[str, Any]]:
    """Every from-car module (UDS 0x19) or generic OBD (Mode 03/07/0A) read
    of ``code_upper`` this car has on file, newest first -- the live
    stand-in for FES-log history when no log on file has ever carried the
    code (e.g. B10AA, U1736: read live on 2026-10-13, never logged to a
    file). ``[]`` on any failure, or when the code was never read live --
    never raises, and an empty result is exactly what tells the caller to
    fall back to the ordinary 404.
    """
    try:
        from ..live import store as live_store
    except Exception:  # noqa: BLE001 -- optional dependency
        return []

    out: list[dict[str, Any]] = []

    try:
        module_obs = live_store.recent_observations(1000, vin=vin, kind="module_dtcs")
    except Exception:  # noqa: BLE001
        module_obs = []
    for o in module_obs:
        if not live_store.is_from_car(o):
            continue
        data = o.get("data") or {}
        ecu = data.get("ecu") or "?"
        at = o.get("at") or ""
        for d in data.get("dtcs") or []:
            full = str(d.get("code") or "").strip().upper()
            base, _, suffix = full.partition("-")
            if base != code_upper:
                continue
            flags = d.get("flags") or {}
            state = _module_dtc_state(flags)
            out.append({"at": at, "module": ecu, "code": full,
                       "status": d.get("status"), "flags": flags, "state": state,
                       "state_class": {"ACTIVE": "status-active",
                                       "HISTORY": "chronic"}.get(state, "plain"),
                       "failure_type": _code_failure_type(suffix)})

    try:
        obd_obs = live_store.recent_observations(300, vin=vin, kind="obd_dtcs")
    except Exception:  # noqa: BLE001
        obd_obs = []
    for o in obd_obs:
        if not live_store.is_from_car(o):
            continue
        data = o.get("data") or {}
        at = o.get("at") or ""
        inner = str(data.get("kind") or "")
        for c in data.get("dtcs") or []:
            full = str(c).strip().upper()
            base = full.split("-", 1)[0]
            if base != code_upper:
                continue
            out.append({"at": at, "module": f"OBD ({inner})" if inner else "OBD",
                       "code": full, "status": None, "flags": {},
                       "state": inner.upper() if inner else None,
                       "state_class": "plain", "failure_type": {}})

    out.sort(key=lambda r: r.get("at") or "", reverse=True)
    return out


def _ask_panel(vin: str, code: str) -> dict[str, Any]:
    from .ask_claude_routes import panel_context
    return panel_context(vin, code)


@router.get("/v/{vin}/code/{code}", response_class=HTMLResponse)
def code_detail(request: Request, vin: str, code: str) -> HTMLResponse:
    """One code's complete life, with its freeze frames beside it.

    A code with no FES-log history still renders here, rather than 404ing,
    when this car's own live module (UDS 0x19) or OBD read ever reported
    it -- e.g. U1736, B10AA, read live on 2026-10-13 but never logged to a
    file. The live occurrence(s) stand in for the log-history table, with
    the same description/fault-tree/parts(UNKNOWN) fallback blocks the
    report page (``report_routes._fixes_fallback``/``_parts_section``)
    already uses for exactly this situation. Only a code neither logged
    nor ever read live on this car is still a 404.
    """
    dossier = _dossier(vin)
    code_upper = code.strip().upper()
    live_only = False
    live_occurrences: list[dict[str, Any]] = []
    description: dict[str, Any] = {}
    fault_tree_steps: list[dict[str, Any]] = []
    try:
        history = mes_bridge.dtc_history(code, vin=vin)
    except BridgeError:
        live_occurrences = _live_code_occurrences(vin, code_upper)
        if not live_occurrences:
            raise
        live_only = True
        history = {"code": code_upper, "matches": []}
        description = _code_description_fallback(code_upper)
        fault_tree_steps = _code_fault_tree_steps(vin, code_upper)
    try:
        frames = mes_bridge.freeze_frames(code=code, vin=vin)
    except BridgeError:
        frames = {"count": 0, "frames": []}
    code_notes = mes_bridge.notes(vin, target_kind="code", target_id=code_upper)["notes"]
    from ..services import codes_call, fault_similarity
    fbc = codes_call.code_view(vin, code_upper)
    try:
        sim = fault_similarity.strip(vin, fbc["key"], limit=5) if fbc else {}
    except Exception:  # noqa: BLE001 -- the code page renders without the similar-faults strip
        sim = {}
    response = _page(request, "code.html", vin=vin, code=code_upper,
                     fbc=fbc, sim=sim,
                     records=history["matches"], frames=frames,
                     notes_list=code_notes, note_target_kind="code",
                     note_target_id=code_upper, note_redirect=f"/v/{vin}/code/{code_upper}",
                     note_kind_locked=True,
                     live_only=live_only, live_occurrences=live_occurrences,
                     description=description, fault_tree_steps=fault_tree_steps,
                     **_ask_panel(vin, code_upper),
                     bar=_vehicle_bar(vin, dossier), tab="codes")
    _set_active_vehicle(response, vin)
    return response


def _board_card_for(vin: str, code: str):
    """Jinja global for _code_brief.html when its caller (job.html) passes no ``fbc``: the fault-board view of
    ``code`` (``fault_board.board`` is cached), or None."""
    from ..services import codes_call
    try:
        return codes_call.code_view(vin, code)
    except Exception:  # noqa: BLE001
        return None


templates.env.globals["board_card_for"] = _board_card_for


@router.get("/v/{vin}/tree", response_class=HTMLResponse)
def tree(request: Request, vin: str, codes: str = "") -> HTMLResponse:
    """Cheapest-first isolation, annotated with this car's own evidence."""
    dossier = _dossier(vin)
    if not codes.strip():
        codes = " ".join(mes_bridge.open_codes_for(dossier))
    result = mes_bridge.fault_tree(codes, vin=vin)
    tree_step_notes = mes_bridge.notes(vin, target_kind="tree_step")["notes"]
    response = _page(request, "tree.html", vin=vin, codes=codes, result=result,
                     notes_list=tree_step_notes, note_target_kind="tree_step",
                     note_target_id="",
                     note_redirect=f"/v/{vin}/tree?codes={quote(codes)}",
                     note_kind_locked=False,
                     bar=_vehicle_bar(vin, dossier), tab="tree")
    _set_active_vehicle(response, vin)
    return response


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
    response = _page(request, "gate.html", vin=vin, result=None,
                     form={"codes": codes, "component": "", "mechanism": "",
                           "disconfirming_test": ""},
                     rows=[{"type": "actuator"}],
                     live_observations=live_obs, live_observations_error=live_obs_error,
                     bar=_vehicle_bar(vin, dossier), tab="gate")
    _set_active_vehicle(response, vin)
    return response


def form_sync(request: Request):
    """Read the form body from a plain ``def`` handler (which FastAPI runs in
    the threadpool), so the handler's blocking work -- dossier build, log
    parsing, serial reads -- never runs on the event loop."""
    from anyio import from_thread
    return from_thread.run(request.form)



@router.post("/v/{vin}/gate", response_class=HTMLResponse)
def gate_submit(request: Request, vin: str,
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
    form = form_sync(request)
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
    response = _page(request, "gate.html", vin=vin, result=result,
                     form={"codes": codes, "component": component,
                           "mechanism": mechanism,
                           "disconfirming_test": disconfirming_test},
                     rows=rows or [{"type": "actuator"}],
                     live_observations=live_obs, live_observations_error=live_obs_error,
                     bar=_vehicle_bar(vin, dossier), tab="gate")
    _set_active_vehicle(response, vin)
    return response


@router.get("/modules", response_class=HTMLResponse)
def modules(request: Request, domain: str = "", view: str = "") -> HTMLResponse:
    """The module registry, and which OBD bus each module lives on.

    One page, two facets over the same overlap rather than two separately
    designed tables that happened to describe the same parts. The default
    view is the full 126-entry reference registry; the 5 rows with a
    confirmed live address link straight to a read, the other 20 the live
    link knows about but cannot yet address stay plain text. ``?view=live``
    flips to the live link's own facet -- bus, 29-bit address, confidence,
    whether this car has actually shown up carrying it -- over its full
    25-entry table, each enriched with its registry domain and tier rather
    than the live table needing to duplicate them.
    """
    try:
        live_rows = live_ops.modules()["modules"]
    except LiveError:
        live_rows = []
    # "In the live table" (25) is not "can actually be read right now" (5) --
    # only the confirmed-address rows get a link that won't just refuse.
    live_usable = {m["code"].upper() for m in live_rows if m["usable"]}
    live_present = {m["code"].upper() for m in live_rows if m.get("present") == "confirmed"}

    if view == "live":
        enriched = []
        for m in live_rows:
            try:
                info = mes_bridge.module_registry(abbrev=m["code"])
            except BridgeError:
                info = {}
            enriched.append({**m, "domain": info.get("domain"), "tier": info.get("tier"),
                             "aliases": info.get("aliases")})
        data = {"view_rows": sorted(enriched, key=lambda r: r["code"])}
    else:
        data = mes_bridge.module_registry(domain=domain)

    return _page(request, "modules.html", data=data, domain=domain, view=view,
                 live_usable=live_usable, live_present=live_present)


@router.get("/recordings", response_class=HTMLResponse)
def recordings(request: Request) -> HTMLResponse:
    return _page(request, "mes_recordings.html",
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
    return _page(request, "mes_recording.html", name=name, data=data,
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

    N2 (MECHANIC_REVIEW_4_SCANS_HEALTH_2026-10-13.md): this used to catch
    only :class:`cuore.live.errors.LiveError`. ``cuore.live.ops`` wraps the
    refusals it anticipates (no port, no cable declared, bus unverified) as
    ``LiveError``, but the adapter itself can fail in ways that never pass
    through that wrapper -- a serial/OS-level error opening the port, or any
    other exception the ops layer did not foresee. Any of those used to
    propagate straight out of this function and 500 the whole ``/live``
    page (verified: a fake raising a bare ``OSError`` reproduces it) instead
    of leaving just the one panel unreadable, which is the one thing this
    function's own docstring already promised. Catching ``Exception`` here
    keeps that promise for real: every panel always renders, as data,
    "unknown", or this panel's own error line -- never a 500.
    """
    out: dict[str, Any] = {}
    try:
        out["status"] = live_ops.status()
        out["status_error"] = None
    except LiveError as exc:
        out["status"] = None
        out["status_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 -- see docstring: never 500 this page
        out["status"] = None
        out["status_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out["cable_data"] = live_ops.buses()
        out["cable_error"] = None
    except LiveError as exc:
        out["cable_data"] = None
        out["cable_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 -- see docstring: never 500 this page
        out["cable_data"] = None
        out["cable_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out["module_rows"] = live_ops.modules()["modules"]
        out["module_error"] = None
    except LiveError as exc:
        out["module_rows"] = []
        out["module_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 -- see docstring: never 500 this page
        out["module_rows"] = []
        out["module_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _live_page(request: Request, vin: str = "", **extra: Any) -> HTMLResponse:
    active = _active_vehicle(request, vin)
    ctx = _live_snapshot()
    ctx["pin_1_9_warning"] = PIN_1_9_WARNING
    ctx["can_ch_note"] = BUSES["can_ch"].notes
    ctx["can_ihs_note"] = BUSES["can_ihs"].notes
    ctx["active_vehicle"] = _active_vehicle_bar(active)
    # This page already shows the live state in full below the fold; the
    # header strip would only repeat it.
    ctx["live_strip"] = None
    try:
        ctx["port_suggestion"] = live_ops.suggest_port(live_ops.ports()["ports"])
    except Exception:  # noqa: BLE001 -- listing ports must never 500 the page
        ctx["port_suggestion"] = None
    ctx.update(extra)
    return _page(request, "live.html", **ctx)


@router.get("/live", response_class=HTMLResponse)
def live_page(request: Request, cable_error: str = "", vin: str = "") -> HTMLResponse:
    """Adapter status, cable declaration, bus map, module table and OBD."""
    # Only override the snapshot's cable_error when the redirect carried one;
    # passing None here would erase a real bus-state failure.
    extra = {"cable_error": cable_error} if cable_error else {}
    return _live_page(request, vin=vin, **extra)


@router.post("/live/vehicle/clear", response_class=HTMLResponse)
def live_clear_vehicle() -> RedirectResponse:
    """Stop tagging live reads against a vehicle. Just the one cookie."""
    resp = RedirectResponse(url="/live", status_code=303)
    resp.delete_cookie(_VIN_COOKIE)
    return resp


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


@router.post("/live/simulation/{action}", response_class=HTMLResponse)
def live_simulation(request: Request, action: str) -> HTMLResponse:
    """Start/stop a SIMULATED session (fixture values, no adapter, no store writes)."""
    err = None
    try:
        if action == "start":
            live_ops.live_session_start(["engine_rpm", "vehicle_speed", "engine_coolant_temp",
                                         "battery_voltage"], simulation=True)
        else:
            live_ops.live_session_stop()
    except LiveError as exc:
        err = str(exc)
    return _live_page(request, simulation_error=err)


@router.post("/live/probe", response_class=HTMLResponse)
def live_probe(request: Request, port: str = Form(default="")) -> HTMLResponse:
    """Reset the adapter and read its identity. Holds nothing afterwards."""
    try:
        result = live_ops.probe(port=port.strip())
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
def live_module(request: Request, code: str, confirm: bool = False,
                vin: str = "") -> HTMLResponse:
    """One module's UDS DTCs and Annex C identity.

    A refusal from the live layer (unverified bus, unknown module, MES
    holding the adapter) is guidance here, not an error page -- this is the
    single most likely outcome on a bench that has not yet declared a cable
    or run a passive listen.

    Tags both reads with the active vehicle (``?vin=``, else the dossier's
    cookie) so they land as observations the evidence gate can find and so
    address confirmations persist per VIN, instead of every live read being
    anonymous until a VIN happens to be read back from the wire.
    """
    code = code.strip()
    active_vin = _active_vehicle(request, vin)
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
            dtcs = live_ops.module_dtcs(code, vin=active_vin, confirm=confirm)
        except LiveError as exc:
            dtcs_error = str(exc)
        try:
            identity = live_ops.module_identity(code, vin=active_vin, confirm=confirm)
        except LiveError as exc:
            identity_error = str(exc)

    return _page(request, "live_module.html", code=code.upper(), confirm=confirm,
                 row=row, bus_key=bus_key, needs_confirm=needs_confirm,
                 dtcs=dtcs, dtcs_error=dtcs_error,
                 identity=identity, identity_error=identity_error,
                 pin_1_9_warning=PIN_1_9_WARNING, live_strip=None,
                 active_vehicle=_active_vehicle_bar(active_vin))


# --- whole-car coverage --------------------------------------------------------

def _coverage_page(request: Request, error: str = "", refused: bool = False,
                   vin: str = "") -> HTMLResponse:
    from ..live import coverage as cov
    from ..live.buses import CABLES
    try:
        st = live_ops.coverage_status()
        cable = live_ops.cable_state()["cable"]
    except LiveError as exc:
        st, cable, error = {"active": False, "passes": []}, "unknown", str(exc)
    return _page(request, "coverage.html", st=st, cable=cable, cables=CABLES,
                 pass_by_key=cov.PASS_BY_KEY, error=error, refused=refused,
                 vin=vin or _active_vehicle(request))


def _coverage_do(request: Request, fn: Any) -> HTMLResponse:
    from ..live.errors import Refused
    try:
        fn()
    except Refused as exc:
        return _coverage_page(request, error=str(exc), refused=True)
    except LiveError as exc:
        return _coverage_page(request, error=str(exc))
    return RedirectResponse(url="/coverage", status_code=303)


@router.get("/coverage", response_class=HTMLResponse)
def coverage_page(request: Request, vin: str = "") -> HTMLResponse:
    """Guided three-pass, three-bus scan with the bystander diff."""
    return _coverage_page(request, vin=vin)


@router.post("/coverage/start", response_class=HTMLResponse)
def coverage_start(request: Request, vin: str = Form(...),
                   engine_running: bool = Form(default=False)) -> HTMLResponse:
    return _coverage_do(request, lambda: live_ops.coverage_start(vin.strip(),
                                                                 engine_running=engine_running))


@router.post("/coverage/cable", response_class=HTMLResponse)
def coverage_cable(request: Request, cable: str = Form(...)) -> HTMLResponse:
    return _coverage_do(request, lambda: live_ops.set_cable(cable))


@router.post("/coverage/run", response_class=HTMLResponse)
def coverage_run(request: Request, key: str = Form(...),
                 confirm: bool = Form(default=False)) -> HTMLResponse:
    return _coverage_do(request, lambda: live_ops.coverage_run(key, confirm=confirm))


@router.post("/coverage/skip", response_class=HTMLResponse)
def coverage_skip(request: Request, key: str = Form(...),
                  reason: str = Form(default="")) -> HTMLResponse:
    return _coverage_do(request, lambda: live_ops.coverage_skip(key, reason))


@router.post("/coverage/reset", response_class=HTMLResponse)
def coverage_reset(request: Request) -> HTMLResponse:
    return _coverage_do(request, live_ops.coverage_reset)


@router.get("/v/{vin}/live-vs-log", response_class=HTMLResponse)
def live_vs_log(request: Request, vin: str, module: str = "") -> HTMLResponse:
    """Newest MES log vs newest live UDS read, one row per code, per module."""
    dossier = _dossier(vin)
    result = mes_bridge.live_vs_log(vin, module=module)
    response = _page(request, "live_vs_log.html", vin=vin, result=result,
                     module=module, bar=_vehicle_bar(vin, dossier),
                     tab="live_vs_log")
    _set_active_vehicle(response, vin)
    return response


# --- dealer (wiTECH) results -------------------------------------------------
#
# wiTECH has no API; the owner's dealer account is read by a technician on
# wiTECH's own screens, and the result is typed in here to become evidence
# the gate, the fault tree and the dossier can all cite. This page writes only
# to the dealer results store -- never to the car, never to the MES corpus.


@router.get("/v/{vin}/dealer", response_class=HTMLResponse)
def dealer_form(request: Request, vin: str) -> HTMLResponse:
    """The dealer results page, with whatever has been recorded so far."""
    dossier = _dossier(vin)
    results = mes_bridge.dealer_results(vin)["results"]
    response = _page(request, "dealer.html", vin=vin, results=results, error=None,
                     bar=_vehicle_bar(vin, dossier), tab="dealer")
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/dealer", response_class=HTMLResponse)
def dealer_submit(request: Request, vin: str) -> HTMLResponse:
    """Record one technician-entered wiTECH result.

    One shared endpoint for all five kinds, distinguished by a ``kind`` hidden
    field on each of the page's small per-kind forms -- this keeps the page
    working with no JavaScript, and matches how ``/gate`` handles measurement
    rows.
    """
    form = form_sync(request)
    kind = str(form.get("kind", "")).strip()
    note = str(form.get("note", "")).strip()

    def field(name: str) -> str:
        return str(form.get(name, "")).strip()

    data: dict[str, Any] = {}
    if kind == "flash_check":
        data = {"module": field("module") or "ECM",
                "current_part": field("current_part"),
                "new_part": field("new_part"),
                "flashed": form.get("flashed") == "on"}
        if field("part_after"):
            data["part_after"] = field("part_after")
    elif kind == "slvt":
        data = {"result": field("result"), "detail": field("detail")}
    elif kind == "dtc_report":
        data = {"module": field("module"),
                "codes": [c.strip() for c in field("codes").split(",") if c.strip()],
                "note": field("dtc_note")}
    elif kind == "recall_status":
        data = {"campaign": field("campaign"), "status": field("status"),
                "date": field("date")}
    elif kind == "routine":
        data = {"module": field("module"), "name": field("name"),
                "result": field("result")}

    error = None
    try:
        mes_bridge.dealer_record(vin, kind, data, note=note)
    except BridgeError as exc:
        error = str(exc)

    dossier = _dossier(vin)
    results = mes_bridge.dealer_results(vin)["results"]
    response = _page(request, "dealer.html", vin=vin, results=results, error=error,
                     bar=_vehicle_bar(vin, dossier), tab="dealer")
    _set_active_vehicle(response, vin)
    return response


# --- technician notes -------------------------------------------------------
#
# Context on anything cuore found that lives nowhere else -- "purge valve
# replaced by me 2026-09-10", "this scan was taken right after a battery
# disconnect", "smoke test done at 0.5 psi, no leak" -- and that a diagnosis
# (and the LLM reading it) must be able to see. Same posture as the dealer
# results store above: append-only, never touches the car or the MES corpus.


def _safe_redirect(url: str, fallback: str) -> str:
    """Only ever redirect somewhere inside this app -- ``redirect_to`` is a
    hidden form field a client controls, not a trusted URL."""
    if (url.startswith("/") and not url.startswith("//")
            and not any(c in url for c in (chr(92), chr(13), chr(10)))):
        return url
    return fallback


@router.get("/v/{vin}/notes", response_class=HTMLResponse)
def notes_page(request: Request, vin: str, target_kind: str = "",
              target_id: str = "", q: str = "") -> HTMLResponse:
    """Every technician note for this vehicle, grouped by target (active codes
    first, then newest), one line each with expand, edit/hide, and a search."""
    from ..services import list_groups
    from . import page_search
    dossier = _dossier(vin)
    rows = mes_bridge.notes(vin, target_kind=target_kind, target_id=target_id)["notes"]
    q = page_search.clean_q(q)
    total = len(rows)
    if q:
        rows = [n for n in rows if page_search.matches(
            q, page_search.haystack([n.get("text"), n.get("target_kind"), n.get("target_id"),
                                     " ".join(n.get("tags") or []), n.get("author")]), ())]
    groups = list_groups.group_notes(rows, list_groups.active_codes(vin))
    response = _page(request, "notes.html", vin=vin, notes_list=rows,
                     notes_groups=groups, notes_q=q, notes_total=total,
                     filter_target_kind=target_kind, filter_target_id=target_id,
                     note_target_kind=target_kind or "vehicle",
                     note_target_id=target_id, note_redirect=f"/v/{vin}/notes",
                     note_kind_locked=False,
                     bar=_vehicle_bar(vin, dossier), tab="notes")
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/notes", response_class=HTMLResponse)
async def notes_add(request: Request, vin: str) -> RedirectResponse:
    """Record one technician note, then redirect back to wherever the add
    form was posted from -- the dossier, a code page, the tree, or this
    vehicle's own notes listing."""
    form = await request.form()
    redirect_to = _safe_redirect(str(form.get("redirect_to", "")), f"/v/{vin}/notes")
    tags = [t.strip() for t in str(form.get("tags", "")).split(",") if t.strip()]
    mes_bridge.add_note(vin, str(form.get("text", "")),
                        target_kind=str(form.get("target_kind", "vehicle")),
                        target_id=str(form.get("target_id", "")),
                        author=actor(request, str(form.get("author", "")).strip() or "technician"),
                        tags=tags)
    return RedirectResponse(url=redirect_to, status_code=303)


@router.post("/v/{vin}/notes/{id}/edit", response_class=HTMLResponse)
async def notes_edit(request: Request, vin: str, id: str) -> RedirectResponse:
    """Amend a note's text. Writes an amendment record -- never rewrites history."""
    form = await request.form()
    redirect_to = _safe_redirect(str(form.get("redirect_to", "")), f"/v/{vin}/notes")
    mes_bridge.edit_note(id, str(form.get("text", "")))
    return RedirectResponse(url=redirect_to, status_code=303)


@router.post("/v/{vin}/notes/{id}/hide", response_class=HTMLResponse)
async def notes_hide(request: Request, vin: str, id: str) -> RedirectResponse:
    """Hide a note (soft delete). Writes a hide record -- never rewrites history."""
    form = await request.form()
    redirect_to = _safe_redirect(str(form.get("redirect_to", "")), f"/v/{vin}/notes")
    mes_bridge.hide_note(id)
    return RedirectResponse(url=redirect_to, status_code=303)
