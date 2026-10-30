"""``/v/{vin}/inbox``: every piece of mechanic feedback for this car,
grouped by status, with Answer and Mark applied/dismissed forms -- plus the
plain-HTML POST handlers both feedback.js's inline panels and
``_feedback_panel.html``'s no-JS fallback submit to.

Same posture as :mod:`cuore.web.parts_routes`/:mod:`cuore.web.timeline_routes`
(all built the same way, concurrently with other agents): a separate
router, reusing ``_dossier``/``_page``/``_safe_redirect``/
``_set_active_vehicle``/``_vehicle_bar`` from :mod:`cuore.web.routes` by
import rather than duplicating that plumbing.

The data contract is :mod:`cuore.services.feedback_bridge` (``add``/
``load``/``answer``/``set_status``/``counts``), the HTTP face of
``mes.feedback`` that :mod:`cuore.api.feedback` already serves as JSON --
this module never writes to that store any other way, so a row created
here and one created through the API are the same row.

Also registers the ``feedback_open_count`` Jinja global ``_vbar.html``'s
Inbox tab badge reads, the same side-effect-of-import trick
:mod:`cuore.web.experience_globals` uses for ``experience_links`` --
applied to every distinct ``Jinja2Templates`` instance a page that includes
``_vbar.html`` renders through, so the badge resolves to a real count
however that page got there.

Not registered on the app here -- ``app.py`` is owned by another agent and
does not import or include this module. Two lines needed there (next to the
other ``web`` router imports/includes)::

    from .web import inbox_routes
    app.include_router(inbox_routes.router)
"""

from __future__ import annotations

import importlib
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import actor, require_token
from ..services import feedback_bridge, list_groups
from ..services.errors import BridgeError
from .routes import _dossier, _page, _safe_redirect, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

STATUSES = ("open", "answered", "applied", "dismissed")


@router.get("/v/{vin}/inbox", response_class=HTMLResponse)
def inbox_page(request: Request, vin: str, status: str = "", did: str = "",
               undo: str = "") -> HTMLResponse:
    """All feedback for this car, grouped by status. ``?status=`` narrows
    the listing to one status but the grouping still only shows that group
    -- the other three just render empty, so the page layout never shifts
    between filtered and unfiltered."""
    dossier = _dossier(vin)
    status = status if status in STATUSES else ""
    rows = feedback_bridge.load(vin, status=status)["feedback"]
    grouped: dict[str, list[dict[str, Any]]] = {s: [] for s in STATUSES}
    for r in rows:
        grouped.setdefault(r.get("status", "open"), []).append(r)
    open_rows = grouped["open"] if not status else feedback_bridge.load(vin, status="open")["feedback"]
    active = list_groups.active_codes(vin)
    folded = {s: list_groups.group_feedback(grouped[s], active) for s in STATUSES}
    known = {r["id"] for r in rows}
    undo_ids = [i for i in undo.split(",") if i in known][:200]
    response = _page(request, "inbox.html", vin=vin, grouped=grouped, folded=folded,
                     did=did[:60] if undo_ids else "", undo_ids=undo_ids,
                     status=status, statuses=STATUSES,
                     bar=_vehicle_bar(vin, dossier), tab="inbox",
                     open_count=len(open_rows))
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/feedback", response_class=HTMLResponse)
async def feedback_add(request: Request, vin: str) -> RedirectResponse:
    """The plain-form fallback for the FAB's whole-page panel and for
    ``feedback.js``'s per-fact panels when a client has JavaScript off --
    same parallel-fields-over-JSON convention ``/v/{vin}/gate`` and
    ``/v/{vin}/dealer`` use for the same reason. Redirects back to wherever
    the form was posted from (the page itself, by default), never to the
    inbox, so correcting something on the dossier lands you back on the
    dossier.
    """
    form = await request.form()
    redirect_to = _safe_redirect(str(form.get("redirect_to", "")), f"/v/{vin}/inbox")
    target = {"page": str(form.get("page", "")).strip() or redirect_to,
             "section": str(form.get("section", "")).strip(),
             "item": str(form.get("item", "")).strip(),
             "label": str(form.get("label", "")).strip() or "(whole page)"}
    try:
        feedback_bridge.add(vin, str(form.get("kind", "")).strip(), target,
                            text=str(form.get("text", "")).strip(),
                            author=actor(request, str(form.get("author", "")).strip() or "technician"))
    except BridgeError:
        pass  # a malformed no-JS submission should not 500 the page it came from
    return RedirectResponse(url=redirect_to, status_code=303)


@router.post("/v/{vin}/feedback/{id}/answer", response_class=HTMLResponse)
async def feedback_answer_submit(request: Request, vin: str, id: str) -> RedirectResponse:
    """The inbox's Answer form for one row."""
    form = await request.form()
    redirect_to = _safe_redirect(str(form.get("redirect_to", "")), f"/v/{vin}/inbox")
    text = str(form.get("text", "")).strip()
    by = str(form.get("by", "")).strip() or "technician"
    if text:
        try:
            feedback_bridge.answer(id, text, by=by)
        except BridgeError:
            pass
    return RedirectResponse(url=redirect_to, status_code=303)


@router.post("/v/{vin}/feedback/{id}/status", response_class=HTMLResponse)
async def feedback_status_submit(request: Request, vin: str, id: str) -> RedirectResponse:
    """The inbox's Mark applied/dismissed (and reopen) forms for one row."""
    form = await request.form()
    redirect_to = _safe_redirect(str(form.get("redirect_to", "")), f"/v/{vin}/inbox")
    status = str(form.get("status", "")).strip()
    note = str(form.get("note", "")).strip()
    if status in STATUSES:
        try:
            feedback_bridge.set_status(id, status, note=note)
        except BridgeError:
            pass
    return RedirectResponse(url=redirect_to, status_code=303)


@router.post("/v/{vin}/feedback-bulk", response_class=HTMLResponse)
async def feedback_bulk_submit(request: Request, vin: str) -> RedirectResponse:
    """One tap for a whole group of the same question: answer every id, or move
    every id to a status (dismissed/applied/open), through the same per-row
    ``answer``/``set_status`` the single-row forms use. Only ids that belong to
    this car are touched. A status move redirects back with an Undo banner."""
    form = await request.form()
    redirect_to = _safe_redirect(str(form.get("redirect_to", "")), f"/v/{vin}/inbox")
    mine = {r["id"] for r in feedback_bridge.load(vin)["feedback"]}
    ids = [str(i) for i in form.getlist("id") if str(i) in mine]
    op = str(form.get("op", ""))
    done: list[str] = []
    if op == "answer":
        text = str(form.get("text", "")).strip()
        by = str(form.get("by", "")).strip() or "technician"
        for i in ids if text else []:
            try:
                feedback_bridge.answer(i, text, by=by)
                done.append(i)
            except BridgeError:
                pass
        verb = "Answered"
    else:
        status = str(form.get("status", "")).strip()
        note = str(form.get("note", "")).strip()
        for i in ids if status in STATUSES else []:
            try:
                feedback_bridge.set_status(i, status, note=note)
                done.append(i)
            except BridgeError:
                pass
        verb = {"dismissed": "Dismissed", "applied": "Marked applied", "open": "Reopened"}.get(status, "Updated")
    if done and op != "undo":
        sep = "&" if "?" in redirect_to else "?"
        from urllib.parse import quote
        redirect_to += f"{sep}did={quote(f'{verb} {len(done)}')}&undo={','.join(done)}"
    return RedirectResponse(url=redirect_to, status_code=303)


# --- the feedback_open_count Jinja global -----------------------------------

def _open_count(vin: str) -> int:
    """Never raises -- a template global must not 500 the vehicle bar."""
    try:
        return len(feedback_bridge.load(vin, status="open")["feedback"])
    except Exception:  # noqa: BLE001
        return 0


def _register(templates: Any) -> None:
    templates.env.globals["feedback_open_count"] = _open_count


for _module_name in ("routes", "service_routes", "drivetrain_routes", "labels_routes", "media_routes"):
    try:
        _mod = importlib.import_module(f".{_module_name}", __package__)
        _tmpl = getattr(_mod, "templates", None) or getattr(_mod, "_shared_templates", None)
        if _tmpl is not None:
            _register(_tmpl)
    except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
        pass


__all__ = ["router"]
