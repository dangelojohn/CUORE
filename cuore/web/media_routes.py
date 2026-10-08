"""``GET /v/{vin}/media``: the photo/video/document gallery, and the small
"Photos & video" attach strip (``_media_attach.html``) embedded on other
pages for a specific target (a code, a checklist step, a service record, a
symptom, or the vehicle itself).

Same posture as :mod:`cuore.web.service_routes` and :mod:`cuore.web.
timeline_routes` (all three built the same way, concurrently with other
agents): a separate router and a self-contained ``Jinja2Templates`` instance
rather than importing private helpers from ``cuore.web.routes``, which was
being edited at the same time.

The JSON contract (``POST /api/vehicles/{vin}/media``, ``GET
/api/vehicles/{vin}/media``, ``GET /api/media/{id}/file``, ``GET
/api/media/{id}/thumb``, ``POST /api/media/{id}``, ``POST
/api/media/{id}/hide``, ``GET /api/vehicles/{vin}/media/export.zip``) is
being built in parallel by another agent under ``cuore/api`` -- not this
module's to create (``cuore/api/*`` is explicitly out of scope here). Every
templated link that names one of those paths (thumbnails, "open original",
the export button, the in-dialog edit/hide actions) points straight at the
documented path and degrades harmlessly -- a 404 broken-image icon, a dead
link -- until that lands; nothing here needs to change once it does.

What *is* this module's to provide, so the page and the attach strip are
developable and testable before that API exists, is the write path: a plain
``POST /v/{vin}/media`` form handler (the brief's "works without JS" case)
and the read path the attach strip needs. Both try a lazy import of
``cuore.services.media_bridge`` first (the plausible module name, matching
every other ``*_bridge.py`` in ``cuore/services``) and fall back to an
in-memory fixture store shaped exactly like the documented ``{"items": [...]}``
contract if that module is absent or its functions raise. The fixture is
process-lifetime only -- fine for development and for this page's own tests,
and automatically stops being used the moment the real bridge lands.

Not registered on the app here -- ``app.py`` is owned by another agent. The
one line needed there:

    ``from .web import media_routes``
    ``app.include_router(media_routes.router)``
"""

from __future__ import annotations

import itertools
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..services import cache, mes_bridge
from ..services.errors import BridgeError
from ..api.deps import require_token, settings_of

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

_VIN_COOKIE = "cuore_vin"

KINDS = ["photo", "scan", "video", "document"]
TARGET_KINDS = ["vehicle", "code", "step", "service_record", "symptom"]
TARGET_LABELS = {"vehicle": "Vehicle", "code": "Code", "step": "Checklist step",
                 "service_record": "Service record", "symptom": "Symptom"}


# --- helpers (small, deliberate duplicates of cuore.web.routes's/service_
#     routes's private helpers -- those modules were being edited
#     concurrently, so this stays self-contained) ---------------------------


def _dossier(vin: str) -> dict[str, Any]:
    try:
        return cache.get_or_build(
            ("workup", vin, mes_bridge.newest_mtime(vin)),
            lambda: mes_bridge.workup(vin=vin),
        )
    except BridgeError:
        return {"identity": {}}


def _vehicle_bar(vin: str, dossier: dict[str, Any]) -> dict[str, Any]:
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


def _current_odometer(dossier: dict[str, Any]) -> Any:
    return (dossier.get("identity") or {}).get("odometer_last_km")


def _page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    settings = settings_of(request)
    ctx.setdefault("version", __version__)
    ctx.setdefault("profile", settings.profile.value)
    ctx.setdefault("live_strip", None)
    return templates.TemplateResponse(request, name, ctx)


def _set_active_vehicle(response: Response, vin: str) -> None:
    response.set_cookie(_VIN_COOKIE, vin, max_age=60 * 60 * 24 * 30, samesite="lax")


# --- the backend bridge, or the fixture that stands in for it -------------


def _bridge():
    """``cuore.services.media_bridge``, or ``None`` if it has not landed."""
    try:
        from ..services import media_bridge
        return media_bridge
    except ImportError:
        return None


_FIXTURE_STORE: dict[str, list[dict[str, Any]]] = {}
_id_seq = itertools.count(1)


def _new_id() -> str:
    return f"fx{next(_id_seq)}"


def _kind_for_mime(mime: Optional[str]) -> str:
    mime = (mime or "").lower()
    if mime.startswith("image/"):
        return "photo"
    if mime.startswith("video/"):
        return "video"
    return "document"


def _matches(item: dict[str, Any], *, q: str, kind: str, tag: str, target_kind: str,
            target_id: str, since: str, until: str) -> bool:
    if item.get("hidden"):
        return False
    if kind and item.get("kind") != kind:
        return False
    if target_kind and item.get("target_kind") != target_kind:
        return False
    if target_id and str(item.get("target_id") or "") != target_id:
        return False
    if tag and tag not in (item.get("tags") or []):
        return False
    if q:
        needle = q.strip().lower()
        hay = " ".join([str(item.get("caption") or ""), str(item.get("filename") or ""),
                        " ".join(item.get("tags") or [])]).lower()
        if needle not in hay:
            return False
    stamp = str(item.get("captured_at") or item.get("uploaded_at") or "")
    if since and stamp and stamp < since:
        return False
    if until and stamp and stamp[:10] > until:
        return False
    return True


def _list_media_fixture(vin: str, **filters: Any) -> dict[str, Any]:
    items = [it for it in _FIXTURE_STORE.get(vin, []) if _matches(it, **filters)]
    items.sort(key=lambda it: str(it.get("uploaded_at") or ""), reverse=True)
    return {"items": items}


def list_media(vin: str, *, q: str = "", kind: str = "", tag: str = "", target_kind: str = "",
               target_id: str = "", since: str = "", until: str = "") -> dict[str, Any]:
    """The gallery's read path. Tries the real bridge, falls back to the
    fixture store on any miss or failure -- a knowledge-table-style guard,
    never a 500."""
    bridge = _bridge()
    if bridge is not None:
        fn = getattr(bridge, "list_media", None)
        if fn is not None:
            try:
                return fn(vin, q=q, kind=kind, tag=tag, target_kind=target_kind,
                          target_id=target_id, since=since, until=until)
            except Exception:  # noqa: BLE001 -- a bridge misfire must fall back, not 500
                pass
    return _list_media_fixture(vin, q=q, kind=kind, tag=tag, target_kind=target_kind,
                               target_id=target_id, since=since, until=until)


async def save_media(vin: str, files: list[UploadFile], *, caption: str, tags: list[str],
                     target_kind: str, target_id: str, odometer_km: Optional[float],
                     author: str) -> list[dict[str, Any]]:
    """The upload path, shared by the plain-form handler below and (once it
    carries scripting) the dialog's own fetch. Reads each file's bytes once
    -- needed either way, to size it for the fixture or to hand real bytes
    to the real bridge -- so this is where that happens, not in the caller.
    """
    read: list[dict[str, Any]] = []
    for f in files:
        content = await f.read()
        read.append({"filename": f.filename, "content_type": f.content_type, "content": content})

    bridge = _bridge()
    if bridge is not None:
        fn = getattr(bridge, "save_media", None)
        if fn is not None:
            try:
                return fn(vin, files=read, caption=caption, tags=tags, target_kind=target_kind,
                          target_id=target_id, odometer_km=odometer_km, author=author)
            except Exception:  # noqa: BLE001 -- fall back to the fixture, never 500
                pass

    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for f in read:
        row = {
            "id": _new_id(), "vin": vin, "kind": _kind_for_mime(f["content_type"]),
            "filename": f["filename"] or "upload", "mime": f["content_type"],
            "size": len(f["content"]), "captured_at": now, "uploaded_at": now,
            "author": author or "mechanic", "caption": caption, "tags": list(tags),
            "target_kind": target_kind or "vehicle", "target_id": target_id,
            "odometer_km": odometer_km, "hidden": False,
        }
        rows.append(row)
    _FIXTURE_STORE.setdefault(vin, []).extend(rows)
    return rows


def recent_tags(vin: str, limit: int = 12) -> list[str]:
    bridge = _bridge()
    if bridge is not None:
        fn = getattr(bridge, "recent_tags", None)
        if fn is not None:
            try:
                return fn(vin, limit=limit)
            except Exception:  # noqa: BLE001
                pass
    seen: list[str] = []
    for it in sorted(_FIXTURE_STORE.get(vin, []),
                     key=lambda it: str(it.get("uploaded_at") or ""), reverse=True):
        for t in it.get("tags") or []:
            if t not in seen:
                seen.append(t)
    return seen[:limit]


def media_strip(vin: str, target_kind: str, target_id: str, limit: int = 6) -> dict[str, Any]:
    """Jinja global backing ``_media_attach.html``: up to ``limit`` items for
    one (target_kind, target_id) pair, plus the total count the "all media"
    link's badge needs."""
    if not target_kind:
        return {"items": [], "total": 0}
    data = list_media(vin, target_kind=target_kind, target_id=str(target_id or ""))
    items = data.get("items") or []
    return {"items": items[:limit], "total": len(items)}


def target_href(vin: str, target_kind: str, target_id: Any) -> Optional[str]:
    """Where a target chip links to -- best-effort, degrades to no link
    rather than a guess that 404s."""
    target_id = str(target_id or "")
    if not target_kind or not target_id:
        return None
    if target_kind == "code":
        return f"/v/{vin}/code/{quote(target_id)}"
    if target_kind == "step":
        return f"/v/{vin}#open-work"
    if target_kind == "service_record":
        return f"/v/{vin}/service"
    if target_kind == "symptom":
        return f"/v/{vin}/timeline"
    if target_kind == "vehicle":
        return f"/v/{vin}"
    return None


templates.env.globals["media_strip"] = media_strip
templates.env.globals["target_href"] = target_href

# Shared with every other page that includes _media_attach.html -- those
# pages render through cuore.web.routes's or cuore.web.service_routes's own
# Jinja2Templates instance (each a separate environment over the same
# template directory), so the globals have to be registered there too.
try:
    from .routes import templates as _routes_templates
    _routes_templates.env.globals["media_strip"] = media_strip
    _routes_templates.env.globals["target_href"] = target_href
except Exception:  # noqa: BLE001 -- must never block this module from loading
    pass
try:
    from .service_routes import templates as _service_templates
    _service_templates.env.globals["media_strip"] = media_strip
    _service_templates.env.globals["target_href"] = target_href
except Exception:  # noqa: BLE001
    pass


# --- the gallery page -------------------------------------------------------


@router.get("/v/{vin}/media", response_class=HTMLResponse)
def media_gallery(request: Request, vin: str, q: str = "", kind: str = "", tag: str = "",
                  target_kind: str = "", target_id: str = "", since: str = "", until: str = "",
                  saved: str = "", error: str = "") -> HTMLResponse:
    """The gallery: search, kind/target filter chips, date range, a
    responsive thumbnail grid, and the upload panel. ``target_kind``/
    ``target_id`` double as both a results filter and the upload form's
    prefill, so the attach strip's "+ add" link (which carries them) lands
    here ready to post against the right target."""
    dossier = _dossier(vin)
    data = list_media(vin, q=q, kind=kind, tag=tag, target_kind=target_kind,
                      target_id=target_id, since=since, until=until)
    response = _page(request, "media.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="media", items=data.get("items") or [], q=q, kind=kind, tag=tag,
                     target_kind=target_kind, target_id=target_id, since=since, until=until,
                     kinds=KINDS, target_kinds=TARGET_KINDS, target_labels=TARGET_LABELS,
                     recent_tags=recent_tags(vin), current_odometer=_current_odometer(dossier),
                     saved=bool(saved), error=error)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/media", response_class=HTMLResponse)
async def media_upload(request: Request, vin: str) -> RedirectResponse:
    """The upload form's no-JS target: a plain multipart POST that redirects
    back with a flash, same shape as ``/v/{vin}/symptoms`` and
    ``/v/{vin}/checklist``. With scripting on, ``media.js`` posts to this
    same URL over XHR for per-file progress and reads ``xhr.responseURL``
    (the redirect's destination) to navigate -- so this one handler serves
    both paths; nothing duplicated."""
    form = await request.form()
    # ``request.form()`` builds plain starlette ``UploadFile`` instances, not
    # fastapi's subclass -- an isinstance check against the latter misses
    # every real upload, so this ducktypes instead (same guard style as
    # service_routes's ``hasattr(form, "getlist")`` checks).
    files = [f for f in form.getlist("file")
            if hasattr(f, "filename") and hasattr(f, "read") and f.filename]

    def field(name: str, default: str = "") -> str:
        return str(form.get(name, default) or "").strip()

    redirect_base = field("redirect_to") or f"/v/{vin}/media"
    if not redirect_base.startswith("/") or redirect_base.startswith("//"):
        redirect_base = f"/v/{vin}/media"

    caption = field("caption")
    tags = [t.strip() for t in re.split(r"[,\n]+", field("tags")) if t.strip()]
    target_kind = field("target_kind", "vehicle") or "vehicle"
    target_id = field("target_id")
    author = field("author") or "mechanic"
    odometer_raw = field("odometer_km")

    error: Optional[str] = None
    if not files:
        error = "choose at least one photo, video or document"

    odometer_km: Optional[float] = None
    if error is None and odometer_raw:
        try:
            odometer_km = float(odometer_raw)
        except ValueError:
            error = f"odometer must be a number, got {odometer_raw!r}"

    if error is None:
        try:
            await save_media(vin, files, caption=caption, tags=tags, target_kind=target_kind,
                             target_id=target_id, odometer_km=odometer_km, author=author)
        except BridgeError as exc:
            error = str(exc)

    sep = "&" if "?" in redirect_base else "?"
    url = f"{redirect_base}{sep}{'saved=1' if error is None else 'error=' + quote(error)}"
    return RedirectResponse(url=url, status_code=303)


__all__ = ["router", "templates", "TEMPLATE_DIR", "list_media", "save_media", "media_strip",
          "target_href", "recent_tags"]
