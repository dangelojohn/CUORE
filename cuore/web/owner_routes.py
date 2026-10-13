"""``/m/{vin}`` -- "Tell CUORE": the phone-first page where an owner, driver
or mechanic records what the car cannot discover on its own, and reads
messages/questions from CUORE and the mechanic.

Rebuilt 2026-10-13 to the Ferrari-page benchmark the main app follows (see
``cuore/web/static/cuore.css``'s "Emphasis pass" section) after the owner
rejected the first pass as "not up to the graphical and prestige standards
... CUORE was built upon". Still its own minimal layout (``templates/
m_*.html``, own ``Jinja2Templates`` instance, no desktop tabs/hero, no
dependency on ``cuore.web.routes``'s shared chrome) -- just a phone-width
page with a bottom nav (Add / Messages / History), now hero-first with four
one-tap quick actions and a camera on every form.

**Every record this page writes is ATTESTED, never a car measurement** --
see ``cuore/live/owner_events.py``'s docstring. The one-line footer on every
page here says the same thing; do not remove it if these templates are
edited later.

Works without JavaScript for everything except the "Snap & fill" photo
auto-read: every form is a plain ``<form method="post">`` (``enctype=
"multipart/form-data"`` wherever a photo tile is present) that redirects on
success -- the camera tile, the fill-up flow and the Snap screen's own
``Continue`` button all submit fine with scripting off; ``m.js`` only adds
the inline photo preview and the client-side call to
``POST /api/vision/{vin}/read`` that can skip straight to a prefilled form.
Same no-JS convention ``cuore.web.media_routes.media_upload`` and
``inbox_routes`` use.

Photo contract with ``cuore.services.vision_bridge`` (built by another
agent, now live as ``cuore.api.vision``): this module never calls it from
Python -- only ``m.js`` does, client-side, against
``POST /api/vision/{vin}/read`` (multipart ``file`` + ``hint``, one of
:data:`SNAP_FALLBACK_TARGET`'s keys). The response is
``{provider, available, fields: {key: {value, confidence, unit}},
suggested_kind: "category/kind"|None, note}``. When it comes back usable,
``m.js`` navigates straight to that kind's ``GET`` form with the read
values and ``source_<key>=photo`` on the query string; :func:`add_form`
turns those into the amber "read from photo" prefill, and
:func:`add_submit` turns a submitted ``source_<key>=photo`` into
``fields_meta[key] = "photo"`` on the stored event (the same provenance tag
the JSON API's ``POST /owner/{vin}/events`` body now also accepts, so a
native app can mark the same thing). When the endpoint is 404 (not wired
up yet), unreachable, or answers ``available: false``, the **same** POST
``/m/{vin}/snap`` this page already posts to without any JS at all is what
the person lands on -- there is no server-side dependency on vision ever
succeeding.

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
from ..live import media as media_store
from ..live import owner_events as store
from ..services import dossier_bridge, mes_bridge, owner_events_bridge as bridge, shop_bridge
from ..services.errors import BridgeError

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: One pictogram-free label per category -- ``static/icons.svg`` has no
#: symbol for any of these nine categories (its ``i-sys_*``/``i-symptom_*``
#: set covers the systems graph and the driver symptom vocabulary, not
#: owner-reported maintenance categories), so tiles render as plain labelled
#: rows rather than inventing icons that would not match that file's house
#: style. Flagged here rather than silently -- see the task note this
#: satisfies.
CATEGORY_ORDER = ("fluids", "fuel", "battery_electrical", "tyres_wheels_brakes",
                  "parts_repairs_elsewhere", "environment_exposure", "incidents",
                  "driving_pattern", "cleaning_maintenance")

#: The two categories promoted to their own hero quick-action tile (Oil &
#: fluids, Battery & electrical) -- everything else in CATEGORY_ORDER renders
#: as an "Everything else" row on the home screen. "fuel" is deliberately
#: NOT removed here even though Fill-up is a quick action too: fill_up is
#: only one of its three kinds (fuel_cap_issue/ran_low_or_out still need a
#: way in), so the category stays reachable both ways.
_QUICK_ACTION_CATEGORIES = ("fluids", "battery_electrical")

#: hint -> (category, kind)|(category, None)|(None, None), the Snap & fill
#: no-JS/no-vision fallback destination. Mirrors
#: ``cuore.services.vision_bridge``'s own (private) hint -> suggested_kind
#: table -- kept as a separate, small literal rather than reaching into that
#: module's private attribute, same posture ``bench_routes._OUTCOMES``
#: documents for why a small shared vocabulary sometimes isn't imported.
SNAP_FALLBACK_TARGET: dict[str, tuple[Optional[str], Optional[str]]] = {
    "odometer": (None, None),
    "fuel_pump": ("fuel", "fill_up"),
    "oil_bottle": ("fluids", "engine_oil_change"),
    "part_label": ("parts_repairs_elsewhere", "part_fitted_elsewhere"),
    "receipt": ("fuel", "fill_up"),
    "other": (None, None),
}

SNAP_HINT_LABELS: dict[str, str] = {
    "odometer": "Odometer", "fuel_pump": "Fuel pump", "oil_bottle": "Oil bottle",
    "part_label": "Part label", "receipt": "Receipt", "other": "Other",
}

#: Query-string keys a Snap & fill redirect carries forward through the
#: category -> kind picker chain, so a photo (and anything already read off
#: it) survives even when the person still has to tap through to a specific
#: kind by hand.
_CARRY_KEYS = ("media_id", "hint", "odometer_km", "source_odometer_km")


def _page(request: Request, name: str, vin: str, active: str, **ctx: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {
        "vin": vin, "active": active, **ctx,
    })


def _field(form: Any, name: str, default: str = "") -> str:
    return str(form.get(name, default) or "").strip()


def _carry_qs(request: Request) -> str:
    """The subset of this request's query params worth forwarding through
    the category -> kind picker chain (see :data:`_CARRY_KEYS`), already
    URL-encoded and ``&``-joined -- "" when there is nothing to carry."""
    parts = []
    for key in _CARRY_KEYS:
        v = request.query_params.get(key)
        if v:
            parts.append(f"{key}={quote(v)}")
    return "&".join(parts)


async def _upload_photo(vin: str, form: Any, *, caption: str) -> tuple[Optional[str], Optional[str]]:
    """Reads the ``photo`` file field off an already-parsed form, if a real
    file was chosen (same duck-typed guard ``media_routes.media_upload``
    uses: ``request.form()`` returns a plain Starlette ``UploadFile``, not
    FastAPI's subclass, so ``isinstance`` would miss every real upload).

    Returns ``(media_id, error)`` -- exactly one is not ``None``. ``(None,
    None)`` means no photo was offered at all, which is not an error on a
    form where the camera tile is optional.
    """
    photo = form.get("photo")
    if not (hasattr(photo, "filename") and hasattr(photo, "read") and photo.filename):
        return None, None
    body = await photo.read()
    if not body:
        return None, None
    try:
        row = media_store.add(vin, body, photo.filename, photo.content_type or "image/jpeg",
                              target_kind="vehicle", caption=caption, author="owner")
    except media_store.BadMedia as exc:
        return None, str(exc)
    return row.get("id"), None


# --- Home: the hero + quick actions ------------------------------------------


@router.get("/m/{vin}", response_class=HTMLResponse)
def home(request: Request, vin: str) -> HTMLResponse:
    """Hero (name, odometer, one-line verdict), four quick actions (Fill-up
    is the one red/primary tile -- the car's single most common report),
    the unread-messages row, then "Everything else" for the remaining
    categories. Plays the opening reveal on every visit (``show_intro``;
    see ``m_base.html``'s own comment on why this is the only route that
    passes it)."""
    vehicle_name = shop_bridge.resolve_vehicle_name(vin)
    dossier = mes_bridge.workup(vin=vin)
    identity = dossier.get("identity") or {}
    odo_last = identity.get("odometer_last_km")
    view = dossier_bridge.build_view(vin, dossier, None)
    verdict = view.get("verdict") or {}

    try:
        msgs = bridge.messages(vin)["messages"]
    except Exception:  # noqa: BLE001 -- a feedback-store hiccup must not sink the home screen
        msgs = []
    unread = sum(1 for m in msgs if m.get("status") == "open")

    tax = store.TAXONOMY
    everything_else = [
        {"key": k, "label": tax[k]["label"], "kind_count": len(tax[k]["kinds"])}
        for k in CATEGORY_ORDER if k in tax and k not in _QUICK_ACTION_CATEGORIES
    ]

    quick_actions = [
        {"key": "fillup", "label": "Fill-up", "icon": "sys_fuel",
         "href": f"/m/{vin}/add/fuel/fill_up", "primary": True},
        {"key": "fluids", "label": "Oil & fluids", "icon": "sys_lubrication",
         "href": f"/m/{vin}/add/fluids", "primary": False},
        {"key": "battery", "label": "Battery & electrical", "icon": "sys_electrical_supply",
         "href": f"/m/{vin}/add/battery_electrical", "primary": False},
        {"key": "snap", "label": "Snap & fill", "icon": "camera",
         "href": f"/m/{vin}/snap", "primary": False},
    ]

    saved = "saved" in request.query_params
    return _page(request, "m_home.html", vin, "add", vehicle_name=vehicle_name, odo_last=odo_last,
                verdict=verdict, quick_actions=quick_actions, unread=unread,
                everything_else=everything_else, saved=saved, show_intro=True)


@router.get("/m/{vin}/add", response_class=HTMLResponse)
def all_categories(request: Request, vin: str) -> HTMLResponse:
    """Every category, one tile each -- the fallback destination for a Snap
    & fill photo whose hint doesn't map to one category (odometer, other),
    and a plain "see everything" page for anyone who wants it. Carries a
    Snap-attached photo's query params forward onto each tile."""
    tax = store.TAXONOMY
    cats = [{"key": k, "label": tax[k]["label"], "kind_count": len(tax[k]["kinds"])}
           for k in CATEGORY_ORDER if k in tax]
    return _page(request, "m_categories.html", vin, "add", categories=cats,
                carry=_carry_qs(request))


@router.get("/m/{vin}/add/{category}", response_class=HTMLResponse)
def kinds_for_category(request: Request, vin: str, category: str) -> HTMLResponse:
    tax = store.TAXONOMY
    cat = tax.get(category)
    if cat is None:
        return _page(request, "m_categories.html", vin, "add",
                     categories=[], carry="", error=f"unknown category {category!r}")
    kinds = [{"key": k, "label": kd["label"], "why_it_matters": kd["why_it_matters"]}
            for k, kd in cat["kinds"].items()]
    return _page(request, "m_kinds.html", vin, "add", category=category,
                category_label=cat["label"], kinds=kinds, carry=_carry_qs(request))


def _last_fillup_fields(vin: str) -> dict[str, str]:
    """This car's most recently reported fill-up's field values, stringified
    -- what the flagship fill-up form preselects/prefills so a repeat
    fill-up with nothing changed needs no typing at all."""
    events = [e for e in store.load(vin)
             if e.get("category") == "fuel" and e.get("kind") == "fill_up"]
    if not events:
        return {}
    return {k: str(v) for k, v in (events[-1].get("fields") or {}).items()}


@router.get("/m/{vin}/add/{category}/{kind}", response_class=HTMLResponse)
def add_form(request: Request, vin: str, category: str, kind: str) -> HTMLResponse:
    try:
        kd = store.kind_def(category, kind)
    except ValueError as exc:
        return _page(request, "m_categories.html", vin, "add", categories=[], carry="",
                     error=str(exc))
    recents = {key: store.recent_values(vin, kind, key)
               for key, spec in kd["fields"].items() if spec.get("remember")}

    qp = request.query_params
    media_id = qp.get("media_id") or ""
    prefill: dict[str, dict[str, str]] = {}
    for key in kd["fields"]:
        v = qp.get(key)
        if v:
            prefill[key] = {"value": v, "source": qp.get(f"source_{key}") or ""}

    odometer_prefill = qp.get("odometer_km") or ""
    odometer_from_photo = qp.get("source_odometer_km") == "photo"

    if category == "fuel" and kind == "fill_up":
        for k, v in _last_fillup_fields(vin).items():
            prefill.setdefault(k, {"value": v, "source": ""})
        station_recents = store.recent_values(vin, kind, "station")
        return _page(request, "m_fillup.html", vin, "add", category=category, kind=kind,
                    kd=kd, prefill=prefill, media_id=media_id, station_recents=station_recents,
                    odometer_prefill=odometer_prefill, odometer_from_photo=odometer_from_photo)

    return _page(request, "m_form.html", vin, "add", category=category, kind=kind, kd=kd,
                recents=recents, prefill=prefill, media_id=media_id,
                odometer_prefill=odometer_prefill, odometer_from_photo=odometer_from_photo)


@router.post("/m/{vin}/add/{category}/{kind}", response_class=HTMLResponse)
async def add_submit(request: Request, vin: str, category: str, kind: str) -> RedirectResponse:
    form = await request.form()
    try:
        kd = store.kind_def(category, kind)
    except ValueError as exc:
        return RedirectResponse(url=f"/m/{vin}?error={quote(str(exc))}", status_code=303)

    fields: dict[str, Any] = {}
    fields_meta: dict[str, str] = {}
    for key in kd["fields"]:
        spec = kd["fields"][key]
        if spec["type"] == "bool":
            fields[key] = _field(form, key) in ("on", "true", "1", "yes")
        else:
            v = _field(form, key)
            if v:
                fields[key] = v
        if _field(form, f"source_{key}") == "photo":
            fields_meta[key] = "photo"

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

    media_ids: list[str] = []
    carried_media_id = _field(form, "media_id")
    if carried_media_id:
        media_ids.append(carried_media_id)

    new_media_id, photo_error = await _upload_photo(
        vin, form, caption=f"owner report: {category}/{kind}")
    if photo_error:
        return RedirectResponse(
            url=f"/m/{vin}/add/{category}/{kind}?error={quote('photo: ' + photo_error)}",
            status_code=303)
    if new_media_id and new_media_id not in media_ids:
        media_ids.append(new_media_id)

    try:
        rec = bridge.add(vin, category, kind, at=at, by_role=by_role, by_name=by_name,
                         fields=fields, note=note, odometer_km=odometer_km,
                         media_ids=media_ids, fields_meta=fields_meta)
    except BridgeError as exc:
        return RedirectResponse(
            url=f"/m/{vin}/add/{category}/{kind}?error={quote(str(exc))}", status_code=303)

    return RedirectResponse(
        url=f"/m/{vin}/add/{category}/{kind}/confirm/{rec['id']}", status_code=303)


@router.get("/m/{vin}/add/{category}/{kind}/confirm/{id}", response_class=HTMLResponse)
def add_confirm(request: Request, vin: str, category: str, kind: str, id: str) -> HTMLResponse:
    """The full-screen "record card" after Save -- a thin-ruled summary of
    exactly what was just stored, then "Add another" (same form, empty) or
    "Done" (home). Reads the just-written row back rather than trusting the
    POST body, so this always shows what is actually on disk."""
    try:
        kd = store.kind_def(category, kind)
    except ValueError as exc:
        return _page(request, "m_categories.html", vin, "add", categories=[], carry="",
                     error=str(exc))
    event = next((e for e in store.load(vin, include_deleted=True) if e.get("id") == id), None)
    if event is None:
        return RedirectResponse(url=f"/m/{vin}", status_code=303)

    fields_meta = event.get("fields_meta") or {}
    fields_disp = []
    for key, val in (event.get("fields") or {}).items():
        spec = kd["fields"].get(key, {})
        label = spec.get("label") or key.replace("_", " ").title()
        fields_disp.append({
            "label": label, "value": val, "unit": spec.get("unit", ""),
            "from_photo": fields_meta.get(key) == "photo",
        })

    return _page(request, "m_confirm.html", vin, "add", category=category, kind=kind,
                kd=kd, event=event, fields_disp=fields_disp)


# --- Snap & fill --------------------------------------------------------------


@router.get("/m/{vin}/snap", response_class=HTMLResponse)
def snap_page(request: Request, vin: str) -> HTMLResponse:
    hints = [{"key": k, "label": SNAP_HINT_LABELS.get(k, k.title())}
            for k in SNAP_FALLBACK_TARGET]
    return _page(request, "m_snap.html", vin, "add", hints=hints)


@router.post("/m/{vin}/snap", response_class=HTMLResponse)
async def snap_submit(request: Request, vin: str) -> RedirectResponse:
    """The no-JS (and no-vision-available) path: store the photo, then send
    the person to the category/kind it's most likely about -- no field is
    ever auto-filled here; only ``m.js``'s own client-side vision call does
    that, and only when it actually has usable fields to offer."""
    form = await request.form()
    hint = _field(form, "hint") or "other"
    if hint not in SNAP_FALLBACK_TARGET:
        hint = "other"

    media_id, error = await _upload_photo(vin, form, caption=f"snap: {hint}")
    if error:
        return RedirectResponse(url=f"/m/{vin}/snap?error={quote('photo: ' + error)}",
                                status_code=303)
    if not media_id:
        return RedirectResponse(url=f"/m/{vin}/snap?error=take+a+photo+first", status_code=303)

    category, kind = SNAP_FALLBACK_TARGET.get(hint, (None, None))
    qs = f"media_id={quote(media_id)}&hint={quote(hint)}"
    if category and kind:
        return RedirectResponse(url=f"/m/{vin}/add/{category}/{kind}?{qs}", status_code=303)
    if category:
        return RedirectResponse(url=f"/m/{vin}/add/{category}?{qs}", status_code=303)
    return RedirectResponse(url=f"/m/{vin}/add?{qs}", status_code=303)


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
