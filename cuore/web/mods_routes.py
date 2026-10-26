"""``/v/{vin}/mods``: the Modifications layer page -- "Modifications --
not diagnostics." Three sections: this car's status/ledger, the sourced
catalogue (with a "Do it in MES" handoff card and a "Record that it was
done" form per entry), and a free-text "Record a modification done
elsewhere" form (aftermarket parts, software).

``/v/{vin}/mods/{mod_id}`` is the single-catalogue-entry detail page
(``mod.html``) a catalogue card on the list page links to -- the full card
(risks/prerequisites/sources/handoff) plus the same record form, useful
when a mechanic has already decided which modification they're doing and
wants it full-screen rather than scrolled past a dozen others.

Plain POST forms, no JavaScript required, same degrade-first shape
``cuore.web.electrical_routes``'s own inspection form uses: submit,
redirect 303 back to the page with ``?saved=1`` or ``?error=...``.

Same posture as ``cuore.web.parts_routes``/``dashboard_routes`` (built the
same way, concurrently with other agents): reuses ``_dossier``/``_page``/
``_set_active_vehicle``/``_vehicle_bar`` from :mod:`cuore.web.routes` by
import rather than duplicating that plumbing.

Not registered on the app here -- ``app.py`` is owned by another agent.
The two lines needed there, beside the other ``web`` router imports/
includes::

    ``from .web import mods_routes``
    ``app.include_router(mods_routes.router)``

**Integration note for whoever owns ``_vtabs.html``:** this feature has no
tab of its own yet in that strip -- see ``cuore/web/templates/_mods_tab.html``
(one line, a ``vtab()`` call) for the include this router's own docstring
asks be added to that file's "More" menu.

**Integration note for whoever owns ``scan_health.html``/``system.html``:**
this bridge exposes ``non_stock(vin)`` (:mod:`cuore.services.
modifications_bridge`) for those pages to show a non-stock chip -- see this
module's own :data:`NON_STOCK_INCLUDE_SNIPPET` for the one-line Jinja
snippet to drop in, reported upward for routing.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..services import modifications_bridge as bridge
from ..services.errors import BridgeError
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: The one-line Jinja snippet that shows this car's non-stock chips on
#: another page. Reads safely even when the bridge import fails for any
#: reason (``mods_non_stock`` degrades to an empty list, never a 500) --
#: see the ``_register`` block below for where the global is installed.
NON_STOCK_INCLUDE_SNIPPET = (
    '{% for chip in mods_non_stock(vin) if mods_non_stock is defined %}'
    '<span class="chip chronic" title="{{ chip.detail }}">{{ chip.label }}</span>'
    '{% endfor %}'
)


def _redirect(vin: str, error: str | None = None, saved: bool = False) -> RedirectResponse:
    url = f"/v/{vin}/mods"
    if error:
        url += f"?error={quote(error)}"
    elif saved:
        url += "?saved=1"
    return RedirectResponse(url=url, status_code=303)


@router.get("/v/{vin}/mods", response_class=HTMLResponse)
def mods_page(request: Request, vin: str, saved: str = "", error: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    status = bridge.status(vin)
    catalog = bridge.all_mods()
    response = _page(
        request, "mods.html", vin=vin,
        bar=_vehicle_bar(vin, dossier), tab="mods",
        status=status, catalog=catalog,
        saved=bool(saved), error=error or None,
        handoff_for=bridge.handoff_for,
    )
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/mods/{mod_id}", response_class=HTMLResponse)
def mod_detail_page(request: Request, vin: str, mod_id: str,
                    saved: str = "", error: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    row = bridge.mod(mod_id)  # raises NotFound -> error.html, via the app's own handler
    handoff = bridge.handoff_for(mod_id)
    response = _page(
        request, "mod.html", vin=vin,
        bar=_vehicle_bar(vin, dossier), tab="mods",
        m=row, handoff=handoff,
        saved=bool(saved), error=error or None,
    )
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/mods/record", response_class=HTMLResponse)
async def record_submit(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def _s(key: str, default: str = "") -> str:
        return str(form.get(key, default) or "").strip()

    proxi_raw = _s("proxi_realigned")
    proxi_realigned = {"yes": True, "no": False}.get(proxi_raw.lower())

    try:
        bridge.record(
            vin,
            mod_id=_s("mod_id"),
            free_text=_s("free_text"),
            done_at=_s("done_at") or None,
            by_role=_s("by_role", "mechanic"),
            by_name=_s("by_name"),
            tool=_s("tool", "MES"),
            from_value=_s("from_value"),
            to_value=_s("to_value"),
            backup=_s("backup", "none"),
            verification_how=_s("verification_how"),
            verification_when=_s("verification_when"),
            verification_result=_s("verification_result"),
            proxi_realigned=proxi_realigned,
            notes=_s("notes"),
        )
    except BridgeError as exc:
        return _redirect(vin, error=str(exc))
    return _redirect(vin, saved=True)


@router.post("/v/{vin}/mods/{entry_id}/delete", response_class=HTMLResponse)
def delete_submit(vin: str, entry_id: str) -> RedirectResponse:
    try:
        bridge.delete(entry_id)
    except BridgeError as exc:
        return _redirect(vin, error=str(exc))
    return _redirect(vin, saved=True)


@router.post("/v/{vin}/mods/{entry_id}/restore", response_class=HTMLResponse)
def restore_submit(vin: str, entry_id: str) -> RedirectResponse:
    try:
        bridge.restore(entry_id)
    except BridgeError as exc:
        return _redirect(vin, error=str(exc))
    return _redirect(vin, saved=True)


# --- mods_non_stock Jinja global, for the other pages' non-stock chip ------

def _mods_non_stock(vin: str) -> list[dict[str, Any]]:
    """``mods_non_stock(vin)`` -- never raises, so a template can call it
    unconditionally once guarded with ``is defined`` (see
    :data:`NON_STOCK_INCLUDE_SNIPPET`)."""
    try:
        return bridge.non_stock(vin)
    except Exception:  # noqa: BLE001 -- a template global must never 500 a page
        return []


def _register(templates: Any) -> None:
    templates.env.globals["mods_non_stock"] = _mods_non_stock


_register(_shared_templates)

# scan_health.html and system.html both render through this same shared
# cuore.web.routes Jinja2Templates instance (neither owns a separate
# environment the way parts.html's group does), so the one registration
# above already covers the non-stock-chip include the owning agent will
# add to those two templates -- no second registration needed.


__all__ = ["router", "NON_STOCK_INCLUDE_SNIPPET"]
