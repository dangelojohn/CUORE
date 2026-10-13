"""``/m/{vin}`` -- "Tell CUORE": the phone-first page where an owner, driver
or mechanic records what the car cannot discover on its own, and reads
messages/questions from CUORE and the mechanic.

Deliberately its own minimal layout (``templates/m_*.html``, own
``Jinja2Templates`` instance), same "built concurrently with other agents"
posture as ``cuore.web.media_routes``/``timeline_routes``: no desktop
tabs/hero, no dependency on ``cuore.web.routes``'s shared chrome, just a
phone-width page with a bottom nav (Add / Messages / History).

**Every record this page writes is ATTESTED, never a car measurement** --
see ``cuore/live/owner_events.py``'s docstring. The one-line footer on every
page here says the same thing; do not remove it if these templates are
edited later.

Works without JavaScript: every form is a plain ``<form method="post">``
that redirects back to ``/m/{vin}#saved`` on success, same no-JS convention
``cuore.web.media_routes.media_upload`` and ``inbox_routes`` use.

Registration note: ``cuore/app.py`` is owned by another agent. The one line
needed there, beside the other ``web`` routers::

    app.include_router(owner_routes.router)
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..api.deps import require_token, settings_of
from ..live import owner_events as store
from ..services import owner_events_bridge as bridge
from ..services.errors import BridgeError

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: One pictogram-free label per category -- ``static/icons.svg`` has no
#: symbol for any of these nine categories (its ``i-sys_*``/``i-symptom_*``
#: set covers the systems graph and the driver symptom vocabulary, not
#: owner-reported maintenance categories), so tiles render as plain labelled
#: cards rather than inventing icons that would not match that file's house
#: style. Flagged here rather than silently -- see the task note this
#: satisfies.
CATEGORY_ORDER = ("fluids", "fuel", "battery_electrical", "tyres_wheels_brakes",
                  "parts_repairs_elsewhere", "environment_exposure", "incidents",
                  "driving_pattern", "cleaning_maintenance")


def _page(request: Request, name: str, vin: str, active: str, **ctx: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {
        "vin": vin, "active": active, **ctx,
    })


def _field(form: Any, name: str, default: str = "") -> str:
    return str(form.get(name, default) or "").strip()


# --- Add: category -> kind -> one-screen form --------------------------------


@router.get("/m/{vin}", response_class=HTMLResponse)
def home(request: Request, vin: str) -> HTMLResponse:
    """Category tiles -- the landing/Add screen."""
    tax = store.TAXONOMY
    cats = [{"key": k, "label": tax[k]["label"], "kind_count": len(tax[k]["kinds"])}
           for k in CATEGORY_ORDER if k in tax]
    saved = "saved" in request.query_params
    return _page(request, "m_categories.html", vin, "add", categories=cats, saved=saved)


@router.get("/m/{vin}/add/{category}", response_class=HTMLResponse)
def kinds_for_category(request: Request, vin: str, category: str) -> HTMLResponse:
    tax = store.TAXONOMY
    cat = tax.get(category)
    if cat is None:
        return _page(request, "m_categories.html", vin, "add",
                     categories=[], error=f"unknown category {category!r}")
    kinds = [{"key": k, "label": kd["label"], "why_it_matters": kd["why_it_matters"]}
            for k, kd in cat["kinds"].items()]
    return _page(request, "m_kinds.html", vin, "add", category=category,
                category_label=cat["label"], kinds=kinds)


@router.get("/m/{vin}/add/{category}/{kind}", response_class=HTMLResponse)
def add_form(request: Request, vin: str, category: str, kind: str) -> HTMLResponse:
    try:
        kd = store.kind_def(category, kind)
    except ValueError as exc:
        return _page(request, "m_categories.html", vin, "add", categories=[], error=str(exc))
    return _page(request, "m_form.html", vin, "add", category=category, kind=kind, kd=kd)


@router.post("/m/{vin}/add/{category}/{kind}", response_class=HTMLResponse)
async def add_submit(request: Request, vin: str, category: str, kind: str) -> RedirectResponse:
    form = await request.form()
    try:
        kd = store.kind_def(category, kind)
    except ValueError as exc:
        return RedirectResponse(url=f"/m/{vin}?error={quote(str(exc))}", status_code=303)

    fields: dict[str, Any] = {}
    for key in kd["fields"]:
        spec = kd["fields"][key]
        if spec["type"] == "bool":
            fields[key] = _field(form, key) in ("on", "true", "1", "yes")
        else:
            v = _field(form, key)
            if v:
                fields[key] = v

    at = _field(form, "at") or None
    by_role = _field(form, "by_role") or "owner"
    by_name = _field(form, "by_name")
    note = _field(form, "note")
    odo_raw = _field(form, "odometer_km")
    odometer_km: Optional[float] = None
    if odo_raw:
        try:
            odometer_km = float(odo_raw)
        except ValueError:
            return RedirectResponse(
                url=f"/m/{vin}/add/{category}/{kind}?error=odometer+must+be+a+number",
                status_code=303)

    try:
        bridge.add(vin, category, kind, at=at, by_role=by_role, by_name=by_name,
                  fields=fields, note=note, odometer_km=odometer_km)
    except BridgeError as exc:
        return RedirectResponse(
            url=f"/m/{vin}/add/{category}/{kind}?error={quote(str(exc))}", status_code=303)

    return RedirectResponse(url=f"/m/{vin}#saved", status_code=303)


# --- Messages ------------------------------------------------------------------


@router.get("/m/{vin}/messages", response_class=HTMLResponse)
def messages(request: Request, vin: str) -> HTMLResponse:
    data = bridge.messages(vin)
    saved = "saved" in request.query_params
    return _page(request, "m_messages.html", vin, "messages",
                messages=data["messages"], saved=saved)


@router.post("/m/{vin}/messages/{id}/reply", response_class=HTMLResponse)
async def reply(request: Request, vin: str, id: str) -> RedirectResponse:
    form = await request.form()
    text = _field(form, "text")
    by = _field(form, "by") or "owner"
    if not text:
        return RedirectResponse(url=f"/m/{vin}/messages?error=a+reply+is+required",
                                status_code=303)
    try:
        bridge.reply_message(id, text, by=by)
    except BridgeError as exc:
        return RedirectResponse(url=f"/m/{vin}/messages?error={quote(str(exc))}",
                                status_code=303)
    return RedirectResponse(url=f"/m/{vin}/messages#saved", status_code=303)


# --- History --------------------------------------------------------------------


@router.get("/m/{vin}/history", response_class=HTMLResponse)
def history(request: Request, vin: str) -> HTMLResponse:
    events = bridge.list_events(vin)["events"]
    events = sorted(events, key=lambda e: e.get("at") or "", reverse=True)
    rows = []
    tax = store.TAXONOMY
    for e in events:
        cat = tax.get(e.get("category", ""), {})
        kd = cat.get("kinds", {}).get(e.get("kind", ""), {})
        rows.append({**e, "category_label": cat.get("label", e.get("category")),
                    "kind_label": kd.get("label", e.get("kind"))})
    return _page(request, "m_history.html", vin, "history", events=rows)


# --- QR / LAN link ---------------------------------------------------------------


def _lan_ip() -> str:
    """Best-guess LAN-reachable address for this machine. Never sends
    traffic -- the UDP ``connect`` just picks the outbound route/interface
    without a packet leaving for a reserved address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


@router.get("/m/{vin}/qr", response_class=HTMLResponse)
def qr(request: Request, vin: str) -> HTMLResponse:
    """A QR of the LAN URL for this page -- only rendered when the server is
    actually bound to something other than loopback (``CUORE_HOST``, aka
    the bind setting; see ``cuore/config.py`` and the handbook note this
    satisfies). The ``qrcode`` package is not in this project's venv, and
    writing a from-scratch QR matrix generator is out of scope for this
    pass, so the LAN URL is rendered as selectable text instead -- the
    fallback the brief explicitly allows.
    """
    settings = settings_of(request)
    if not settings.lan_exposed:
        return _page(request, "m_qr.html", vin, "add", lan_url=None,
                    reason="This server is only reachable from this machine "
                          "(loopback). Set CUORE_HOST=0.0.0.0 in the keep-alive "
                          "to serve the LAN -- see docs/handbook/"
                          "05-methods-and-gotchas.md.")
    url = f"http://{_lan_ip()}:{settings.port}/m/{vin}"
    return _page(request, "m_qr.html", vin, "add", lan_url=url, reason=None)
