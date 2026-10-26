"""``GET /v/{vin}/fuses``: a find-the-fuse page for a busy workshop.

Order: one-line call + status filters, "Which box?" picker, ONE car picture
(Side / Top) with one marker per box, then one section per box (real photos,
catalogue diagram, slot line-art, fuse rows), then collapsed technician panels.

Data: :mod:`cuore.services.fuse_health` (lazy import). Reading the page never
contacts the car. Checks, added rows, added boxes and photos are plain POSTs
that redirect back with ``?msg=``. Photos live under the state dir
(``fuse_photos/<VIN>/<box id>/``), never in git.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from ..api.deps import require_token
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

STATUSES = ("green", "orange", "red", "grey")
STATUS_LABEL = {"green": "OK", "orange": "Suspect", "red": "Blown", "grey": "Not checked yet"}
STATUS_MARK = {"green": "✓", "orange": "!", "red": "✕", "grey": "?"}
CONF_WORDS = {"SOURCED": "from a source", "INFERRED": "worked out, not checked", "GENERAL": "general knowledge",
              "UNKNOWN": "not known"}
PHOTO_KINDS = ("Box open", "Cover label", "Location in the car", "Other")


def _svc():
    from ..services import fuse_health  # lazy
    return fuse_health


def _safe_redirect(url: str) -> bool:
    """Same-site relative path only (no //host, no backslash tricks, no CR/LF)."""
    return url.startswith("/") and not url.startswith("//") and not any(c in url for c in (chr(92), chr(13), chr(10)))


def _back(vin: str, msg: str, to: str = "") -> RedirectResponse:
    base = to if to and _safe_redirect(to) else f"/v/{vin}/fuses"
    path, _, frag = base.partition("#")
    sep = "&" if "?" in path else "?"
    return RedirectResponse(url=f"{path}{sep}msg={quote(msg)}" + (f"#{frag}" if frag else ""), status_code=303)


def _anchor(item_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in str(item_id))


def plain(text: Any) -> str:
    """Workshop words for jargon in data strings (PDC / PDM)."""
    t = str(text or "")
    t = re.sub(r"\s*\((?:rear )?PDC(?: / PDM)?\)", "", t)
    t = re.sub(r"\bPDC\b", "power distribution box", t)
    return re.sub(r"\bPDM\b", "power distribution module", t)


def photo_key(kind: str, type_text: str) -> str:
    """The component_image_keys.json key for a fuse / relay type as printed on the row; "" when not mapped."""
    t = re.sub(r"[^a-z]+", " ", str(type_text or "").lower()).strip()
    if kind == "relay":
        return "micro relay" if "micro" in t else "maxi relay" if "maxi" in t else ""
    if "fmx" in t or "j case" in t or "jcase" in t:
        return "j-case"
    for k in ("midi", "maxi", "mini"):
        if k in t.split():
            return k
    return ""


def _catalogue_photo(key: str, cache: dict[str, Any]) -> Any:
    if key not in cache:
        try:
            from ..services import component_images
            hits = component_images.images_for_key(key, limit=1) if key else []
        except Exception:  # noqa: BLE001
            hits = []
        cache[key] = ({"url": hits[0]["photo_url"], "href": hits[0]["part_url"], "name": hits[0]["name"]} if hits else None)
    return cache[key]


def _item_name(i: dict[str, Any]) -> str:
    lab = str(i.get("label") or "")
    pos = str(i.get("position") or "")
    for pre in ("Fuse ", "Relay "):
        if lab.startswith(pre):
            lab = lab[len(pre):]
    if pos and lab.startswith(pos):
        lab = lab[len(pos):].strip()
    lab = lab.strip(" -:")
    if lab.startswith("(") and lab.endswith(")"):
        lab = lab[1:-1]
    return plain(lab or i.get("label") or "")


def _how_sure(b: dict[str, Any]) -> str:
    conf = b.get("location_confidence") or "UNKNOWN"
    src = str(b.get("source") or "").lower()
    if b.get("added_by_technician"):
        return "added by a technician, from a source (not checked by CUORE)"
    if "third-party" in src:
        return "from a third-party diagram, not checked on this car"
    if conf == "INFERRED":
        return "worked out from the sources, not checked on this car"
    return CONF_WORDS.get(conf, "not known")


def _worst(sts: list[str]) -> str:
    s = set(sts)
    return "red" if "red" in s else "orange" if "orange" in s else "green" if s == {"green"} else "grey"


def build_context(vin: str, data: dict[str, Any], status_f: str, box_f: str) -> dict[str, Any]:
    svc = _svc()
    boxes = list(data.get("boxes") or [])
    items = [dict(i) for i in data.get("items") or []]
    counts = {k: int((data.get("counts") or {}).get(k, 0)) for k in STATUSES}
    if not data.get("counts"):
        for i in items:
            counts[i.get("status") if i.get("status") in counts else "grey"] += 1
    cache: dict[str, Any] = {}
    for i in items:
        st = i.get("status") if i.get("status") in STATUS_LABEL else "grey"
        sp = i.get("spec") or {}
        i.update(status=st, status_word=STATUS_LABEL[st], anchor=_anchor(i["id"]), name=_item_name(i),
                 photo=_catalogue_photo(photo_key(i.get("kind") or "", sp.get("type") or sp.get("relay_type") or ""), cache))
    secs: list[dict[str, Any]] = []
    for b in boxes:
        rows = [i for i in items if i.get("box") == b["id"]]
        st = _worst([r["status"] for r in rows])
        secs.append(_section(vin, svc, b, rows, st, status_f))
    nobox = [i for i in items if not i.get("box")]
    if nobox:
        secs.append(_section(vin, svc, {"id": "none", "label": "Box not stated by the source", "short": "No box stated",
                                        "source": "These rows come from a source that names the fuse or relay but not "
                                                  "which box it is in.", "location_confidence": "UNKNOWN",
                                        "full_list_sourced": False}, nobox, _worst([r["status"] for r in nobox]),
                             status_f, mapped=False))
    if box_f:
        secs = [x for x in secs if x["id"] == box_f]
    return {"secs": secs, "counts": counts, "total": len(items)}


def _section(vin: str, svc: Any, b: dict[str, Any], rows: list[dict[str, Any]], st: str, status_f: str,
             mapped: bool = True) -> dict[str, Any]:
    from . import fuse_map_svg as fm
    photos, diagrams = [], []
    if b["id"] != "none":
        photos = svc.photos(vin, b["id"])
        try:
            diagrams = svc.box_diagrams(b)
        except Exception:  # noqa: BLE001
            diagrams = []
    slots, from_layout = fm.slot_svg(rows, plain(b.get("short") or b.get("label")))
    shown = [r for r in rows if not status_f or r["status"] == status_f]
    n = len(rows)
    return {**b, "short": plain(b.get("short") or b.get("label")), "label_plain": plain(b.get("label")),
            "where_plain": plain(b.get("where") or ""), "pick_where": b.get("pick_where") or "", "source_plain": plain(b.get("source")), "status": st,
            "status_word": STATUS_LABEL[st], "count": n, "rows": shown, "how_sure": _how_sure(b),
            "list_word": "the full list is sourced" if b.get("full_list_sourced") else "the full list is not sourced yet",
            "photos": photos, "diagrams": diagrams, "slots": slots, "slots_from_layout": from_layout,
            "slot_note": fm.NOTE, "mapped": mapped,
            "side_word": {"left": "left side of the car", "right": "right side of the car (far side from the driver)"}
            .get(b.get("side") or "", "side not stated")}


def _directing(vin: str, dossier: dict[str, Any], data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(the call + job matches, the grounds). Both degrade to empty rather than failing the page."""
    from ..services import fuse_direct as fd
    try:
        grounds = fd.grounds(vin, REPO_ROOT)
    except Exception:  # noqa: BLE001
        grounds = []
    try:
        from ..services import electrical_bridge, mes_bridge
        codes = mes_bridge.open_codes_for(dossier)
        syms, ctext = fd.job_inputs(vin, codes, dossier)
        d = fd.direct(data.get("items") or [], data.get("boxes") or [], syms, codes, ctext, electrical_bridge.path_for_code)
    except Exception:  # noqa: BLE001
        d = {"call": "", "more": [], "matches": [], "ground_ids": [], "codes": []}
    return d, grounds


def ctx_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for i in data.get("items") or []:
        i = dict(i)
        i["status"] = i.get("status") if i.get("status") in STATUS_LABEL else "grey"
        out.append(i)
    return out


def _page_ctx(vin: str, status: str, box: str, q: str) -> dict[str, Any]:
    from . import fuse_map_svg as fm
    from ..services import fuse_direct as fd
    dossier = _dossier(vin)
    error = None
    try:
        data = _svc().health(vin)
    except Exception as exc:  # noqa: BLE001 - render without the service
        data = {"vin": vin, "checked_at": None, "boxes": [], "items": [], "counts": {}, "unplaced": [], "gaps": []}
        error = f"Fuse health is not available yet: {exc}"
    status_f = status.strip().lower() if status.strip().lower() in STATUSES else ""
    box_ids = {b["id"] for b in data.get("boxes") or []}
    box_f = box.strip() if box.strip() in box_ids or box.strip() == "none" else ""
    ctx = build_context(vin, data, status_f, box_f)
    secs, counts, total = ctx["secs"], ctx["counts"], ctx["total"]
    direction, grounds = _directing(vin, dossier, data)
    by_id = {it["id"]: it for it in ctx_items(data)}
    matches = []
    for m in direction["matches"]:
        it = by_id.get(m["id"], m["item"])
        sp = it.get("spec") or {}
        matches.append({**m, "anchor": _anchor(it["id"]), "rating": it.get("rating_a"), "type": sp.get("type") or "",
                        "colour": sp.get("colour") or "", "colour_derived": sp.get("colour_derived"), "kind": it.get("kind"),
                        "circuit": _item_name(it), "status": it.get("status", "grey")})
    for g in grounds:
        g["photo"] = _catalogue_photo("battery_negative_strap", {}) if g["id"] == "battery_neg_strap" else None
    gmap = {g["id"]: g for g in grounds}
    job_grounds = [gmap[i] for i in direction["ground_ids"] if i in gmap]
    if direction["call"]:
        call = direction["call"]
    else:
        call = f"{total} fuses and relays, {len(data.get('boxes') or [])} boxes. Pick a box."
    q = q.strip()[:80]
    results = fd.search(q, ctx_items(data), data.get("boxes") or [], grounds, status_f, box_f) if q else []
    for r in results:
        r["ref"], r["text"], r["where"] = plain(r["ref"]), plain(r["text"]), plain(r["where"])

    def href(st: str = "") -> str:
        return f"/v/{vin}/fuses" + (f"?status={st}" if st else "") + "#fuse-chips"

    chip_href = {k: href("" if status_f == k else k) for k in STATUSES}
    mapped = [s for s in secs if s.get("mapped", True) and s["id"] != "none"]
    short = {"g003a": "G003A", "g003b": "G003B", "esim_ground": "ESIM gnd", "battery_neg_strap": "Batt. strap"}
    svg = fm.box_map([{"id": s["id"], "short": s["short"], "side": s.get("side"), "zone": s.get("zone"),
                       "area": s.get("area"), "status": s["status"], "status_word": s["status_word"],
                       "count": s["count"], "location_confidence": s.get("location_confidence")}
                      for s in mapped],
                     [{"id": g["id"], "name": g["name"], "short": short.get(g["id"], g["name"])} for g in grounds]
                     ) if mapped else ""
    try:
        parts = _svc().catalogue_parts()
    except Exception:  # noqa: BLE001
        parts = {}
    skip = ("full fuse list not sourced", "not on the drawing")
    gaps = [g for g in data.get("gaps") or [] if not any(k in g for k in skip)]
    gaps.insert(0, "No box has its full fuse list from a source yet; each box section says how many rows are listed.")
    return dict(vin=vin, bar=_vehicle_bar(vin, dossier), tab="fuses", svg=svg, call=call, call_more=direction["more"],
                job_matches=matches, job_grounds=job_grounds, grounds=grounds, q=q, results=results,
                secs=secs, counts=counts, total=total, status_f=status_f, box_f=box_f, chip_href=chip_href,
                base=f"/v/{vin}/fuses", gaps=[plain(g) for g in gaps], status_label=STATUS_LABEL,
                status_mark=STATUS_MARK, parts=parts, colour_class=fm.colour_class, anchor=_anchor, error=error, plain=plain,
                checked_at=data.get("checked_at"), tested_label=_tested_label)


def _tested_label(kind: str) -> tuple[str, str]:
    return ("Tested OK", "Blown - replaced") if kind == "fuse" else ("Tested OK", "Faulty")


@router.get("/v/{vin}/fuses", response_class=HTMLResponse)
def fuses_page(request: Request, vin: str, status: str = "", box: str = "", msg: str = "", q: str = "") -> HTMLResponse:
    response = _page(request, "fuses.html", msg=msg, **_page_ctx(vin, status, box, q))
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/fuses/data", response_class=HTMLResponse)
def fuses_data_page(request: Request, vin: str, msg: str = "") -> HTMLResponse:
    """Owner data maintenance: the add / record / upload forms. Reached only from a footer link on the mechanic page."""
    dossier = _dossier(vin)
    try:
        data = _svc().health(vin)
    except Exception:  # noqa: BLE001
        data = {"boxes": [], "items": []}
    boxes = [{"id": b["id"], "short": plain(b.get("short") or b.get("label"))} for b in data.get("boxes") or []]
    items = [{"id": i["id"], "kind": i.get("kind"), "label": plain(i.get("label")), "position": i.get("position") or ""}
             for i in data.get("items") or []]
    response = _page(request, "fuses_data.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="fuses", base=f"/v/{vin}/fuses",
                     msg=msg, boxes=boxes, items=items, photo_kinds=PHOTO_KINDS,
                     area_choices=[("engine", "Engine bay"), ("interior", "Interior"), ("rear", "Rear"),
                                   ("luggage", "Luggage compartment")])
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/fuses/photo/{box}/{name}")
def fuses_photo(vin: str, box: str, name: str) -> Response:
    p = _svc().photo_path(vin, box, name)
    if not p:
        return Response(status_code=404)
    return FileResponse(p, headers={"Cache-Control": "max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.post("/v/{vin}/fuses/photo", response_class=HTMLResponse)
async def fuses_photo_add(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    box = f("box")
    to = f("redirect_to") or f"/v/{vin}/fuses#fuse-box-{_anchor(box)}"
    up = form.get("photo")
    if up is None or not hasattr(up, "read"):
        return _back(vin, "Photo not saved: choose a picture first", to)
    svc = _svc()
    data = await up.read(svc.MAX_PHOTO_BYTES + 1)
    kind = f("caption") if f("caption") in PHOTO_KINDS else ""
    try:
        svc.save_photo(vin, box, getattr(up, "filename", "") or "", data, by=f("by"), caption=kind)
    except ValueError as exc:
        return _back(vin, f"Photo not saved: {exc}", to)
    return _back(vin, "Photo saved", to)


@router.post("/v/{vin}/fuses/box", response_class=HTMLResponse)
async def fuses_box_add(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    try:
        rec = _svc().add_box(short=f("short"), label=f("label"), area=f("area"), side=f("side"), where=f("where"),
                             source=f("source"), by=f("by") or "technician")
    except ValueError as exc:
        return _back(vin, f"Box not added: {exc}", f("redirect_to"))
    return _back(vin, "Fuse box added (marked as added by a technician)", f"/v/{vin}/fuses#fuse-box-{_anchor(rec['id'])}")


@router.post("/v/{vin}/fuses/check", response_class=HTMLResponse)
async def fuses_check(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    to = f("redirect_to")
    note = f("note") or (f("blown_note") if f("result") == "blown" else "Tested OK" if f("result") == "ok" else "")
    try:
        _svc().add_check(vin, f("item"), f("result"), f("method") or "visual", value=f("value"), unit=f("unit"),
                         note=note, by=f("by") or "technician", limit=f("limit"))
    except ValueError as exc:
        return _back(vin, f"Check not saved: {exc}", to)
    return _back(vin, "Check recorded", to)


@router.post("/v/{vin}/fuses/spec", response_class=HTMLResponse)
async def fuses_spec(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    to = f("redirect_to")
    try:
        _svc().add_spec(f("item"), source=f("source"), by=f("by") or "technician",
                        **{k: f(k) for k in ("fuse_type", "voltage_v", "colour", "relay_type", "relay_number",
                                             "pin_layout", "orientation")})
    except ValueError as exc:
        return _back(vin, f"Details not saved: {exc}", to)
    return _back(vin, "Details saved", to)


@router.post("/v/{vin}/fuses/item", response_class=HTMLResponse)
async def fuses_item(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    mods = [m for m in f("feeds_modules").replace(";", ",").split(",") if m.strip()]
    try:
        _svc().add_item(kind=f("kind"), label=f("label"), source=f("source"), box=f("box"), position=f("position"),
                        rating_a=f("rating_a"), feeds_modules=mods, notes=f("notes"), by=f("by") or "technician",
                        **{k: f(k) for k in ("fuse_type", "voltage_v", "colour", "relay_type", "relay_number",
                                             "pin_layout", "orientation")})
    except ValueError as exc:
        return _back(vin, f"Not added: {exc}", f("redirect_to"))
    return _back(vin, "Fuse/relay added (marked as added by technician)", f("redirect_to"))
