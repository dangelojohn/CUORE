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
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from ..api.deps import require_token, settings_of
from ..labels import render as label_render
from ..live import media as media_store
from ..live import owner_events as store
from ..services import (dossier_bridge, labels_bridge, mes_bridge,
                        owner_events_bridge as bridge, shop_bridge)
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


# --- Print label (owner's request, 2026-10-14): a "Print label" button on
# the oil-change/service confirmation card, History, and the edit screen,
# reusing cuore.services.labels_bridge / cuore.labels.render -- the exact
# same generator the desktop /v/{vin}/labels page uses -- rather than a
# second PDF path. Only a (category, kind) in this table is printable; see
# print_label() below for the 404 an owner event outside it gets. Each
# value is (label_kind, section_label) -- label_kind is one of
# cuore.labels.render.KINDS, section_label is only meaningful for
# label_kind == "service" (draw_service's own header line).
_PRINTABLE_KINDS: dict[tuple[str, str], tuple[str, str]] = {
    ("fluids", "engine_oil_change"): ("oil_change", ""),
    ("fluids", "coolant_change"): ("service", "Coolant change"),
    ("fluids", "brake_fluid"): ("service", "Brake fluid"),
    # Transmission/transfer-case/differential oil gets its own ATF/pan-
    # filter label kind (cuore.services.labels_bridge.transmission_service_
    # label_data) rather than the generic "service" kind -- see
    # cuore.services.labels_bridge.OWNER_EVENT_LABEL_KIND, the same mapping
    # under its own name for any other caller that needs it; section_label
    # is unused for this label_kind (only "service" reads it), same as
    # "oil_change" above.
    ("fluids", "driveline_fluid"): ("transmission_service", ""),
}

#: Remembers the last Avery size tapped on the ``/m/{vin}/print`` size-chip
#: row (or on a size chip elsewhere) so a plain "Print label" button -- no
#: size in its own URL -- reprints at the garage's usual size without
#: asking every time. Same cookie convention as ``_VIN_COOKIE`` above.
_LABEL_SIZE_COOKIE = "cuore_label_size"
_DEFAULT_LABEL_TEMPLATE = "avery_5520"  # same default cuore.web.labels_routes.labels_page uses


def _is_iphone(request: Request) -> bool:
    """True on an iPhone's own Safari/WebKit -- gates the one-line "Share ->
    Print" hint under a Print label button: that's the AirPrint path on iOS
    (there is no print dialog on the PDF tab itself), and the hint would
    only confuse a desktop or Android reader. A plain User-Agent sniff, not
    a feature the rest of this page needs -- never used to change what
    renders, only whether this one hint line does."""
    return "iPhone" in request.headers.get("user-agent", "")


def _label_work_done(kind: str, fields: dict[str, Any]) -> str:
    """A one-line "work done" summary for a ``service``-kind label from the
    owner event's own fields -- draw_service's free-text body line. Returns
    "" (the label then prints "(no summary recorded)") when the event
    carries none of the fields a given kind would normally have."""
    if kind == "coolant_change":
        bits = [fields.get("type"), (f"{fields.get('qty')} L" if fields.get("qty") else None)]
    elif kind == "brake_fluid":
        bits = [fields.get("action"), (f"{fields.get('qty')} L" if fields.get("qty") else None)]
    elif kind == "driveline_fluid":
        # No longer reached via _PRINTABLE_KINDS (that kind now prints as
        # "transmission_service", not "service" -- see _event_label_data),
        # kept correct anyway in case anything else ever calls this with
        # kind="driveline_fluid" directly. "action" was replaced by
        # "method" when the taxonomy grew fluid_spec/brand/pan_filter_
        # part_no/fill_temp_c (cuore.live.owner_events.TAXONOMY).
        bits = [fields.get("which"), fields.get("method"),
               (f"{fields.get('qty')} L" if fields.get("qty") else None)]
    else:
        bits = []
    return " / ".join(str(x) for x in bits if x)


def _event_label_data(vin: str, event: dict[str, Any], label_kind: str,
                      section_label: str) -> dict[str, Any]:
    """The label field dict for one owner event, via the exact same
    ``labels_bridge.oil_change_label_data``/``service_label_data`` the
    desktop Labels page's own ``oil_change``/``service`` kinds use --
    ``record=None`` (this event is never a ``mes.service`` ledger row) and
    every real value passed as an override, so the generator's own
    "no odometer on file" guard still applies.

    Oil brand (there is no "brand" field on the ``oil_change`` label --
    only viscosity/spec) is carried in ``oil_spec``; filter brand and part
    number both land in the one ``filter_part_no`` slot
    (``draw_oil_change`` prints a single "Filter <text>" line), e.g.
    ``"UFI 23.598.00"``.
    """
    fields = event.get("fields") or {}
    by = event.get("by") or {}
    technician = by.get("name") or by.get("role") or ""
    overrides: dict[str, Any] = {"date": _fmt_day(event.get("at")), "technician": technician}
    if event.get("odometer_km") is not None:
        overrides["odometer_km"] = event["odometer_km"]

    if label_kind == "oil_change":
        if fields.get("viscosity"):
            overrides["oil_viscosity"] = fields["viscosity"]
        if fields.get("brand"):
            overrides["oil_spec"] = fields["brand"]
        if fields.get("qty"):
            overrides["quantity_l"] = fields["qty"]
        filter_bits = " ".join(str(x) for x in
                               (fields.get("filter_brand"), fields.get("filter_part_no")) if x)
        if filter_bits:
            overrides["filter_part_no"] = filter_bits
        return labels_bridge.oil_change_label_data(vin, None, "CUORE", overrides)

    if label_kind == "transmission_service":
        # driveline_fluid's own fields (fluid_spec/brand/qty/pan_filter_
        # part_no/fill_temp_c -- cuore.live.owner_events.TAXONOMY) map
        # straight onto transmission_service_label_data's overrides; that
        # function also prefills from the last mes.service drivetrain
        # record when the event itself left a field blank.
        if fields.get("fluid_spec"):
            overrides["fluid_spec"] = fields["fluid_spec"]
        if fields.get("brand"):
            overrides["fluid_brand"] = fields["brand"]
        if fields.get("qty"):
            overrides["quantity_l"] = fields["qty"]
        if fields.get("pan_filter_part_no"):
            overrides["pan_filter_part_no"] = fields["pan_filter_part_no"]
        if fields.get("fill_temp_c"):
            overrides["fill_temp_c"] = fields["fill_temp_c"]
        return labels_bridge.transmission_service_label_data(vin, overrides)

    overrides["section"] = section_label
    overrides["work_done"] = _label_work_done(event.get("kind", ""), fields)
    return labels_bridge.service_label_data(vin, None, overrides)


def _print_href(vin: str, event: dict[str, Any]) -> Optional[str]:
    """``/m/{vin}/labels/{id}`` for a printable event, ``None`` otherwise --
    the one guard every "Print label" button below shares, so a non-
    printable kind never renders a button that would only 404."""
    key = (event.get("category", ""), event.get("kind", ""))
    if key not in _PRINTABLE_KINDS:
        return None
    return f"/m/{vin}/labels/{event['id']}"


def _page(request: Request, name: str, vin: str, active: str, **ctx: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {
        "vin": vin, "active": active, **ctx,
    })


def _field(form: Any, name: str, default: str = "") -> str:
    return str(form.get(name, default) or "").strip()


def _fmt_day(at: Optional[str]) -> str:
    """"Oct 10" from an ISO date/timestamp -- the edit screen's title and
    the record card's date line. Falls back to the raw string on anything
    that doesn't parse (never raises -- this is display only)."""
    s = (at or "").strip()
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return s
    return f"{dt.strftime('%b')} {dt.day}"


def _fmt_day_time(at: Optional[str]) -> str:
    """"Oct 10, 16:57" -- same as :func:`_fmt_day` but with the time, for
    the "Edited <time>" marker (the edit's own timestamp, not the event's
    occurrence time)."""
    s = (at or "").strip()
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return s
    return f"{_fmt_day(s)}, {dt.strftime('%H:%M')}"


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
        {"key": k, "label": tax[k]["label"], "kind_count": len(tax[k]["kinds"]),
         "href": f"/m/{vin}/add/{k}"}
        for k in CATEGORY_ORDER if k in tax and k not in _QUICK_ACTION_CATEGORIES
    ]
    #: "Print" (owner's request, 2026-10-14): not a report category -- a
    #: shortcut to the recent-printable-records list -- so it is appended
    #: here rather than folded into CATEGORY_ORDER/TAXONOMY, which only
    #: ever enumerate kinds of REPORT.
    everything_else.append({"key": "print", "label": "Print", "kind_count": None,
                            "href": f"/m/{vin}/print"})

    quick_actions = [
        {"key": "fillup", "label": "Fill-up", "icon": "sys_fuel",
         "href": f"/m/{vin}/add/fuel/fill_up", "primary": True},
        {"key": "fluids", "label": "Oil & fluids", "icon": "sys_lubrication",
         "href": f"/m/{vin}/add/fluids", "primary": False},
        {"key": "battery", "label": "Battery & electrical", "icon": "sys_electrical_supply",
         "href": f"/m/{vin}/add/battery_electrical", "primary": False},
        {"key": "snap", "label": "Snap & fill", "icon": "camera",
         "href": f"/m/{vin}/snap", "primary": False},
        {"key": "transmission", "label": "Transmission", "icon": "sys_transmission_driveline",
         "href": f"/m/{vin}/add/transmission", "primary": False},
    ]

    saved = "saved" in request.query_params
    return _page(request, "m_home.html", vin, "add", vehicle_name=vehicle_name, odo_last=odo_last,
                verdict=verdict, quick_actions=quick_actions, unread=unread,
                everything_else=everything_else, saved=saved, show_intro=True)


@router.get("/m/{vin}/add/transmission")
def add_transmission_alias(request: Request, vin: str) -> RedirectResponse:
    """One-tap alias for the home screen's "Transmission" quick action --
    owner's request, 2026-10-14 ("I don't see any transmission
    development"). Opens the real ``fluids/driveline_fluid`` form directly;
    carries any Snap & fill query params forward like every other tile."""
    carry = _carry_qs(request)
    url = f"/m/{vin}/add/fluids/driveline_fluid" + (f"?{carry}" if carry else "")
    return RedirectResponse(url=url, status_code=303)


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
                kd=kd, event=event, fields_disp=fields_disp,
                print_href=_print_href(vin, event), iphone=_is_iphone(request))


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


# --- Edit / Delete (soft, with Undo) -----------------------------------------
#
# "Tell CUORE"'s own edit, owner's request 2026-10-13: every history entry
# can be corrected (a typo'd octane, a wrong litres figure...) or soft-
# deleted, without ever rewriting the original append-only row -- see
# cuore.live.owner_events's "event_edit"/"restore" ops. The edit screen
# reuses the exact same m_fillup.html/m_form.html the Add flow uses, just
# pre-filled from the saved event instead of "last used"/photo values, via
# the same `prefill` context key both templates already read.
#
# One kind is deliberately NOT editable here: a symptoms-delegated
# ("incidents/noise_smell_vibration") row lives in mes.symptoms, not this
# module's own store -- out of scope for this agent's owned files (see
# owner_events_bridge.add's own docstring on the hand-off). _find_event
# below only ever looks in cuore.live.owner_events, so such a row 404s/
# redirects the same as an unknown id; m_history.html hides the Edit action
# for it via the `editable` flag computed in history() below.


def _find_event(vin: str, id: str, *, include_deleted: bool = True) -> Optional[dict[str, Any]]:
    return next((e for e in store.load(vin, include_deleted=include_deleted) if e.get("id") == id),
                None)


@router.get("/m/{vin}/edit/{id}", response_class=HTMLResponse)
def edit_form(request: Request, vin: str, id: str) -> HTMLResponse:
    event = _find_event(vin, id)
    if event is None or event.get("deleted"):
        return RedirectResponse(url=f"/m/{vin}/history?error=that+report+no+longer+exists",
                                status_code=303)
    category, kind = event.get("category", ""), event.get("kind", "")
    try:
        kd = store.kind_def(category, kind)
    except ValueError:
        return RedirectResponse(url=f"/m/{vin}/history?error=unknown+category+or+kind",
                                status_code=303)

    fields_meta = event.get("fields_meta") or {}
    prefill: dict[str, dict[str, str]] = {
        key: {"value": "" if v is None else str(v), "source": fields_meta.get(key, "")}
        for key, v in (event.get("fields") or {}).items()
    }
    recents = {key: store.recent_values(vin, kind, key)
              for key, spec in kd["fields"].items() if spec.get("remember")}
    odometer_prefill = "" if event.get("odometer_km") is None else str(event.get("odometer_km"))
    edit_date = _fmt_day(event.get("at"))
    ctx = dict(
        is_edit=True, edit_date=edit_date, event_note=event.get("note") or "",
        form_action=f"/m/{vin}/edit/{id}", cancel_href=f"/m/{vin}/history",
        delete_action=f"/m/{vin}/history/{id}/delete",
        prefill=prefill, media_id="", odometer_prefill=odometer_prefill,
        odometer_from_photo=False,
        print_href=_print_href(vin, event), iphone=_is_iphone(request),
    )

    if category == "fuel" and kind == "fill_up":
        station_recents = store.recent_values(vin, kind, "station")
        return _page(request, "m_fillup.html", vin, "history", category=category, kind=kind,
                    kd=kd, station_recents=station_recents, **ctx)

    return _page(request, "m_form.html", vin, "history", category=category, kind=kind, kd=kd,
                recents=recents, **ctx)


@router.post("/m/{vin}/edit/{id}", response_class=HTMLResponse)
async def edit_submit(request: Request, vin: str, id: str) -> RedirectResponse:
    form = await request.form()
    current = _find_event(vin, id)
    if current is None or current.get("deleted"):
        return RedirectResponse(url=f"/m/{vin}/history?error=that+report+no+longer+exists",
                                status_code=303)
    category, kind = current.get("category", ""), current.get("kind", "")
    try:
        kd = store.kind_def(category, kind)
    except ValueError as exc:
        return RedirectResponse(url=f"/m/{vin}/history?error={quote(str(exc))}", status_code=303)

    # Only a field that actually differs from the stored value is sent on
    # -- an untouched field (the form always re-submits every one of them)
    # must never show up as a spurious no-op audit entry.
    cur_fields = current.get("fields") or {}
    field_patch: dict[str, Any] = {}
    for key, spec in kd["fields"].items():
        if spec["type"] == "bool":
            new_v: Any = _field(form, key) in ("on", "true", "1", "yes")
            if bool(cur_fields.get(key)) != new_v:
                field_patch[key] = new_v
        else:
            raw = _field(form, key)
            new_v = raw if raw else None
            old_s = "" if cur_fields.get(key) is None else str(cur_fields.get(key))
            new_s = "" if new_v is None else str(new_v)
            if old_s != new_s:
                field_patch[key] = new_v

    note_raw = _field(form, "note")
    note_patch = note_raw if note_raw != (current.get("note") or "") else None

    odo_raw = _field(form, "odometer_km")
    odometer_patch: Optional[float] = None
    if odo_raw:
        try:
            odo_v = float(odo_raw)
        except ValueError:
            return RedirectResponse(
                url=f"/m/{vin}/edit/{id}?error=odometer+must+be+a+number", status_code=303)
        if current.get("odometer_km") != odo_v:
            odometer_patch = odo_v

    # "When" (m_form.html's own `at` input; m_fillup.html carries none) --
    # blank means "didn't touch it," same convention as Add; a value that
    # merely echoes the stored one (compared on its own length, since the
    # input may be date-only while the stored value carries a time) is
    # likewise not a change.
    at_raw = _field(form, "at")
    cur_at = current.get("at") or ""
    at_patch = at_raw if at_raw and at_raw != cur_at[:len(at_raw)] else None

    by_role = _field(form, "by_role") or "owner"
    by_name = _field(form, "by_name")

    if not (field_patch or note_patch is not None or odometer_patch is not None or at_patch):
        # Nothing actually changed -- a harmless re-save, not an error.
        return RedirectResponse(url=f"/m/{vin}/edit/{id}/confirm", status_code=303)

    patch = {"fields": field_patch or None, "note": note_patch, "odometer_km": odometer_patch,
             "at": at_patch}
    try:
        bridge.edit(vin, id, patch, by=by_role, by_name=by_name)
    except BridgeError as exc:
        return RedirectResponse(url=f"/m/{vin}/edit/{id}?error={quote(str(exc))}", status_code=303)

    return RedirectResponse(url=f"/m/{vin}/edit/{id}/confirm", status_code=303)


@router.get("/m/{vin}/edit/{id}/confirm", response_class=HTMLResponse)
def edit_confirm(request: Request, vin: str, id: str) -> HTMLResponse:
    """The same record-card screen Add uses after Save, re-purposed to show
    what an edit changed: "Edited <time>" plus the full audit trail under a
    disclosure (owner's own request)."""
    event = _find_event(vin, id)
    if event is None:
        return RedirectResponse(url=f"/m/{vin}/history", status_code=303)
    try:
        kd = store.kind_def(event.get("category", ""), event.get("kind", ""))
    except ValueError:
        return RedirectResponse(url=f"/m/{vin}/history", status_code=303)

    fields_meta = event.get("fields_meta") or {}
    fields_disp = []
    for key, val in (event.get("fields") or {}).items():
        spec = kd["fields"].get(key, {})
        label = spec.get("label") or key.replace("_", " ").title()
        fields_disp.append({
            "label": label, "value": val, "unit": spec.get("unit", ""),
            "from_photo": fields_meta.get(key) == "photo",
        })

    audit = event.get("audit") or []
    edited_at_fmt = _fmt_day_time(audit[-1]["at"]) if audit else None

    return _page(request, "m_confirm.html", vin, "history", category=event.get("category"),
                kind=event.get("kind"), kd=kd, event=event, fields_disp=fields_disp,
                edited=True, audit=audit, edited_at_fmt=edited_at_fmt,
                print_href=_print_href(vin, event), iphone=_is_iphone(request))


@router.post("/m/{vin}/history/{id}/delete", response_class=HTMLResponse)
async def history_delete(request: Request, vin: str, id: str) -> RedirectResponse:
    try:
        bridge.delete(id)
    except BridgeError as exc:
        return RedirectResponse(url=f"/m/{vin}/history?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/m/{vin}/deleted/{id}", status_code=303)


@router.get("/m/{vin}/deleted/{id}", response_class=HTMLResponse)
def deleted_confirm(request: Request, vin: str, id: str) -> HTMLResponse:
    event = _find_event(vin, id)
    if event is None:
        return RedirectResponse(url=f"/m/{vin}/history", status_code=303)
    tax = store.TAXONOMY
    cat = tax.get(event.get("category", ""), {})
    kd = cat.get("kinds", {}).get(event.get("kind", ""), {})
    return _page(request, "m_deleted.html", vin, "history", event=event,
                kind_label=kd.get("label", event.get("kind")))


@router.post("/m/{vin}/history/{id}/restore", response_class=HTMLResponse)
async def history_restore(request: Request, vin: str, id: str) -> RedirectResponse:
    try:
        bridge.restore(id)
    except BridgeError as exc:
        return RedirectResponse(url=f"/m/{vin}/history?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/m/{vin}/history", status_code=303)


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
        edited_at = e.get("edited_at")
        rows.append({**e, "category_label": cat.get("label", e.get("category")),
                    "kind_label": kd.get("label", e.get("kind")),
                    "edited_at_fmt": _fmt_day_time(edited_at) if edited_at else None,
                    "editable": not e.get("delegated_to"),
                    "print_href": _print_href(vin, e)})
    return _page(request, "m_history.html", vin, "history", events=rows,
                iphone=_is_iphone(request))


# --- Print label -----------------------------------------------------------------
#
# "Print label" (owner's request, 2026-10-14): print the oil-change/fluid-
# service label for one owner event straight from the phone, reusing the
# desktop Labels page's own generator (cuore.services.labels_bridge,
# cuore.labels.render) -- never a second PDF path. Opens in the SAME tab on
# purpose (a plain <a href>, no target/download attribute) so iOS Safari's
# own Share -> Print (AirPrint) is reachable; see _is_iphone's docstring for
# why the on-page hint is gated the way it is.


@router.get("/m/{vin}/print", response_class=HTMLResponse)
def print_list(request: Request, vin: str) -> HTMLResponse:
    """Recent printable records -- the "Print" entry on the home screen's
    "Everything else" list -- plus the label-size chip row the desktop
    Labels page already offers (the same Avery catalogue,
    ``labels_bridge.list_templates()``); tapping a size chip remembers it
    (``_LABEL_SIZE_COOKIE``) for every "Print label" button elsewhere on
    this phone, not just the ones on this page."""
    size_param = request.query_params.get("size") or ""
    current_size = request.cookies.get(_LABEL_SIZE_COOKIE) or _DEFAULT_LABEL_TEMPLATE
    if size_param:
        try:
            labels_bridge.get_template(size_param)
            current_size = size_param
        except BridgeError:
            size_param = ""

    events = [e for e in store.load(vin)
             if (e.get("category", ""), e.get("kind", "")) in _PRINTABLE_KINDS]
    events = sorted(events, key=lambda e: e.get("at") or "", reverse=True)[:20]
    tax = store.TAXONOMY
    rows = []
    for e in events:
        cat = tax.get(e.get("category", ""), {})
        kd = cat.get("kinds", {}).get(e.get("kind", ""), {})
        rows.append({**e, "kind_label": kd.get("label", e.get("kind")),
                    "print_href": f"/m/{vin}/labels/{e['id']}?size={current_size}"})

    sizes = labels_bridge.list_templates()["templates"]
    response = _page(request, "m_print.html", vin, "add", events=rows, sizes=sizes,
                     current_size=current_size, iphone=_is_iphone(request))
    if size_param:
        response.set_cookie(_LABEL_SIZE_COOKIE, current_size, max_age=60 * 60 * 24 * 365,
                            samesite="lax")
    return response


@router.get("/m/{vin}/labels/{event_id}")
def print_label(request: Request, vin: str, event_id: str) -> Response:
    """The print-ready PDF for one owner event -- an oil change or a fluid
    service (see :data:`_PRINTABLE_KINDS`); 404s, with a message naming
    what IS printable, for any other kind (a fill-up, a top-up, an
    incident report...) rather than printing a label with nothing on it.
    ``?size=<template id>`` picks the Avery layout (same catalogue the
    desktop Labels page offers); left off, this uses whatever size was
    last picked on this phone (``_LABEL_SIZE_COOKIE``), or
    :data:`_DEFAULT_LABEL_TEMPLATE` the first time.
    """
    event = _find_event(vin, event_id)
    if event is None or event.get("deleted"):
        raise HTTPException(status_code=404, detail="that report no longer exists")

    category, kind = event.get("category", ""), event.get("kind", "")
    mapping = _PRINTABLE_KINDS.get((category, kind))
    if mapping is None:
        try:
            kind_label = store.kind_def(category, kind)["label"]
        except ValueError:
            kind_label = kind or "this report"
        raise HTTPException(
            status_code=404,
            detail=(f"{kind_label!r} reports aren't printable as a service label -- "
                    "only an engine oil change or a fluid service (coolant, brake "
                    "fluid, transmission/transfer-case/differential) can be printed."))
    label_kind, section_label = mapping

    template_id = (request.query_params.get("size") or request.cookies.get(_LABEL_SIZE_COOKIE)
                  or _DEFAULT_LABEL_TEMPLATE)
    try:
        template = labels_bridge.get_template(template_id)
    except BridgeError:
        template_id = _DEFAULT_LABEL_TEMPLATE
        template = labels_bridge.get_template(template_id)

    try:
        data = _event_label_data(vin, event, label_kind, section_label)
        pdf = label_render.generate_labels_pdf(template, label_kind, data, copies=1,
                                               start_index=0)
    except BridgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition":
                                f'inline; filename="label-{kind}-{vin}.pdf"'})
    response.set_cookie(_LABEL_SIZE_COOKIE, template_id, max_age=60 * 60 * 24 * 365,
                        samesite="lax")
    return response


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
