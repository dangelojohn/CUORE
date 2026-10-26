"""``GET /v/{vin}/fuses``: every fuse/relay CUORE can source, placed on a side
profile of the Stelvio and coloured by evidence (green / orange / red / grey).

Data: :mod:`cuore.services.fuse_health` (lazy import). Reading the page never
contacts the car. Technician checks and technician-added rows are plain POSTs
that redirect back with ``?msg=``.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

STATUSES = ("green", "orange", "red", "grey")
STATUS_LABEL = {"green": "OK", "orange": "Suspect / fault", "red": "Blown / dead", "grey": "No evidence yet"}
STATUS_MARK = {"green": "✓", "orange": "!", "red": "✕", "grey": "?"}


def _svc():
    from ..services import fuse_health  # lazy
    return fuse_health


def _safe_redirect(url: str) -> bool:
    """Same-site relative path only (no //host, no backslash tricks, no CR/LF)."""
    return url.startswith("/") and not url.startswith("//") and not any(c in url for c in (chr(92), chr(13), chr(10)))


def _back(vin: str, msg: str, to: str = "") -> RedirectResponse:
    base = to if to and _safe_redirect(to) else f"/v/{vin}/fuses"
    sep = "&" if "?" in base else "?"
    return RedirectResponse(url=f"{base}{sep}msg={quote(msg)}", status_code=303)


def _anchor(item_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in str(item_id))


def _profile(boxes: list[dict[str, Any]], items: list[dict[str, Any]], dim: set[str]) -> tuple[str, bool]:
    """(svg html, drawn). ('', False) if the shared drawing is not available."""
    try:
        from . import sensor_profile_svg as psvg
        draw = getattr(psvg, "both_views", None) or getattr(psvg, "profile_svg")
    except Exception:  # noqa: BLE001 - module absent or lacks profile_svg: list-only page
        return "", False
    pts: list[dict[str, Any]] = []
    for b in boxes:
        its = [i for i in items if i.get("box") == b["id"]]
        # red/orange if any fuse inside is; green only when EVERY fuse inside
        # is green -- one known-good fuse must not paint a mostly unchecked box
        sts = {i["status"] for i in its}
        st = ("red" if "red" in sts else "orange" if "orange" in sts
              else "green" if sts == {"green"} else "grey")
        pts.append({"id": "box-" + b["id"], "label": b["label"], "status": st, "zone": b.get("zone"), "side": None,
                    "location_confidence": b.get("location_confidence"), "number": "B",
                    "title": f"{b['label']} - {len(its)} listed, full list "
                             f"{'sourced' if b.get('full_list_sourced') else 'not sourced'}"})
    for n, i in enumerate(items, 1):
        pts.append({"id": _anchor(i["id"]), "label": i["label"], "status": i["status"], "zone": i.get("zone"),
                    "side": i.get("side"), "location_confidence": i.get("location_confidence"), "number": n,
                    "title": f"{i['label']} - {STATUS_LABEL[i['status']]}"})
    try:
        svg = draw(pts, href_prefix="fuse-",
                   aria_label="Side view of the car with fuse boxes, fuses and relays placed by area")
    except TypeError:
        svg = draw(pts, href_prefix="fuse-")
    return svg, True


@router.get("/v/{vin}/fuses", response_class=HTMLResponse)
def fuses_page(request: Request, vin: str, status: str = "", box: str = "", msg: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    error = None
    try:
        data = _svc().health(vin)
    except Exception as exc:  # noqa: BLE001 - render without the service
        data = {"vin": vin, "checked_at": None, "boxes": [], "items": [], "counts": {}, "unplaced": [], "gaps": []}
        error = f"Fuse health is not available yet: {exc}"
    boxes = list(data.get("boxes") or [])
    items = list(data.get("items") or [])
    numbers = {i["id"]: n for n, i in enumerate(items, 1)}
    counts = {k: int((data.get("counts") or {}).get(k, 0)) for k in STATUSES}
    if not data.get("counts"):
        for i in items:
            counts[i.get("status") if i.get("status") in counts else "grey"] += 1
    status_f = status.strip().lower() if status.strip().lower() in STATUSES else ""
    box_ids = {b["id"] for b in boxes}
    box_f = box.strip() if box.strip() in box_ids or box.strip() == "none" else ""

    def match(i: dict[str, Any]) -> bool:
        if status_f and i.get("status") != status_f:
            return False
        if box_f == "none":
            return not i.get("box")
        return not box_f or i.get("box") == box_f

    shown = [i for i in items if match(i)]
    dim = {i["id"] for i in items if not match(i)}
    svg, drawn = _profile(boxes, items, dim)
    groups: list[dict[str, Any]] = []
    for b in boxes:
        rows = [i for i in shown if i.get("box") == b["id"]]
        if rows or not (status_f or box_f):
            groups.append({"box": b, "rows": rows})
    nobox = [i for i in shown if not i.get("box")]
    if nobox:
        groups.append({"box": {"id": "none", "label": "Box not stated by the source", "full_list_sourced": False,
                               "source": "These rows come from a source that names the fuse or relay but not which box it is in."},
                       "rows": nobox})
    unplaced = [i for i in items if not i.get("zone")]

    def href(st: str = "", bx: str = "") -> str:
        q = [f"{k}={quote(v)}" for k, v in (("status", st), ("box", bx)) if v]
        return f"/v/{vin}/fuses" + ("?" + "&".join(q) if q else "")

    chip_href = {k: href("" if status_f == k else k, box_f) for k in STATUSES}
    box_href = {b["id"]: href(status_f, "" if box_f == b["id"] else b["id"]) for b in boxes}
    try:
        parts = _svc().catalogue_parts()
    except Exception:  # noqa: BLE001
        parts = {}
    response = _page(request, "fuses.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="fuses", svg=svg, drawn=drawn,
                     groups=groups, numbers=numbers, counts=counts, total=len(items), shown=len(shown),
                     checked_at=data.get("checked_at"), status_f=status_f, box_f=box_f, chip_href=chip_href,
                     box_href=box_href, boxes=boxes, base=f"/v/{vin}/fuses", unplaced=unplaced,
                     gaps=data.get("gaps") or [], status_label=STATUS_LABEL, status_mark=STATUS_MARK,
                     anchor=_anchor, parts=parts, msg=msg, error=error)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/fuses/check", response_class=HTMLResponse)
async def fuses_check(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    to = f("redirect_to")
    try:
        _svc().add_check(vin, f("item"), f("result"), f("method"), value=f("value"), unit=f("unit"),
                         note=f("note"), by=f("by") or "technician", limit=f("limit"))
    except ValueError as exc:
        return _back(vin, f"Check not saved: {exc}", to)
    return _back(vin, "Check recorded", to)


@router.post("/v/{vin}/fuses/item", response_class=HTMLResponse)
async def fuses_item(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    mods = [m for m in f("feeds_modules").replace(";", ",").split(",") if m.strip()]
    try:
        _svc().add_item(kind=f("kind"), label=f("label"), source=f("source"), box=f("box"), position=f("position"),
                        rating_a=f("rating_a"), feeds_modules=mods, notes=f("notes"), by=f("by") or "technician")
    except ValueError as exc:
        return _back(vin, f"Not added: {exc}", f("redirect_to"))
    return _back(vin, "Fuse/relay added (marked as added by technician)", f("redirect_to"))
