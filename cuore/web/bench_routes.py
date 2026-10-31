"""The bench: ``GET /v/{vin}``, the screen a mechanic sees the instant a car
lands on the lift.

Kept as its own router, same posture as ``cuore/web/dossier_routes.py``
(see that file's own docstring): the old dossier owned ``/v/{vin}`` until
this landed, and still owns everything else under ``/v/{vin}/*`` --
``cuore/web/routes.py``'s own ``/v/{vin}`` handler was moved to
``/v/{vin}/dossier`` to make room for this one, rather than this file
reaching into that module's handler.

``POST /v/{vin}/bench/done`` is this file's own form target -- separate
from the dossier's shared ``POST /v/{vin}/checklist`` (still used by the
full dossier's open-work cards) because the bench's "Mark done" captures an
outcome (BENCH_UX_SPEC_2026-10-08.md B5: OK / fault found / skipped, with a
one-line note) that the older route does not accept. Both routes write the
same ``cuore.live.checklists`` store, so a step ticked from either page
agrees with the other; a fault-found note is additionally filed as a
mechanic note (``mes.notes`` via ``mes_bridge.add_note``) so it shows up in
the dossier's own History.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import APIRouter

from ..api.deps import require_token
from ..live import checklists as checklist_store
from ..services import vehicle_facts_bridge
from ..services import bench_bridge, cache, dossier_bridge, mes_bridge
from ..services.errors import BadRequest
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: Mirrors ``cuore.api.checklists._OUTCOMES`` -- kept as a separate literal
#: (not imported) so this HTML form route has no dependency on the JSON API
#: module; the vocabulary is tiny and documented in both places.
_OUTCOMES = {"ok", "fault_found", "skipped"}
#: the words the buttons and the Undo banner show (same as the outcome vocabulary)
_OUTCOME_WORDS = {"ok": "OK", "fault_found": "Fault found", "skipped": "Skipped"}


@router.get("/v/{vin}/menu", response_class=HTMLResponse)
def car_menu_page(request: Request, vin: str) -> HTMLResponse:
    """The car's home after it is picked: its Menu as a page, not an overlay."""
    bar = web_routes._vehicle_bar(vin, web_routes._dossier(vin))
    return web_routes._page(request, "car_menu.html", vin=vin, bar=bar, menu_page=True, live_strip=None)


@router.get("/v/{vin}", response_class=HTMLResponse)
def bench_page(request: Request, vin: str, saved: str = "") -> HTMLResponse:
    """What to do right now: the resume card, the task roster (each with
    procedure, pass criteria, preconditions and parts/tools already
    resolved), the live fuel gate and readiness panel, and jump-off points
    to the codes, the job and the full dossier.

    ``bar``/``view`` are computed the same way every other ``/v/{vin}/*``
    page does (``web_routes._vehicle_bar`` over the same cached workup) so
    this page's ``{% include "_vbar.html" %}`` -- the persistent hero +
    tab strip every other vehicle page already uses -- renders identically
    here (BENCH_UX_SPEC_2026-10-08.md F16). ``_vbar.html``'s own docstring
    names the Bench as one of the two pages its hero was built for, so
    reusing it rather than keeping a bespoke status line is the integration
    that module was already waiting on.
    """
    dossier = cache.get_or_build(
        ("workup", vin, mes_bridge.newest_mtime(vin)),
        lambda: mes_bridge.workup(vin=vin))
    view = dossier_bridge.build_view(vin, dossier, None)
    bar = web_routes._vehicle_bar(vin, dossier)
    bench = bench_bridge.build_bench(vin)
    # _vehicle_bar falls back to "(unnamed vehicle)" straight off
    # dossier["identity"]; bench_bridge's own resolution additionally tries
    # shop_bridge (corpus name, then a WMI decode) before giving up, which is
    # exactly the one-display-name-per-vehicle fix BENCH_UX_SPEC_2026-10-08.md
    # A3 asks for -- reuse it here so the shared hero never regresses to the
    # placeholder this VIN's own dossier.identity has no "vehicle" field for.
    bar["name"] = bench["vehicle"]
    # The one-tap save redirects here with ?saved=<step id>; the page then
    # shows "Saved ... Undo" for that step (plain GET + POST, no JS). Only
    # while the step is still done, so a reload after Undo shows no banner.
    saved_step = next((a for a in bench["next_actions"]
                       if a["step_id"] == saved and a["done"]), None) if saved else None
    bench["saved"] = ({"step_id": saved_step["step_id"], "n": saved_step["n"], "of": saved_step["of"],
                       "text": saved_step["text"],
                       "outcome": _OUTCOME_WORDS.get(saved_step.get("outcome") or "", "Done")}
                      if saved_step else None)
    response = web_routes._page(request, "bench.html", vin=vin, bench=bench,
                                bar=bar, view=view, tab="bench",
                                facts_summary=vehicle_facts_bridge.summary(vin))
    web_routes._set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/bench/done")
def bench_mark_done(vin: str, step_id: str = Form(...),
                    done: Optional[str] = Form(None), outcome: str = Form(""),
                    note: str = Form(""), by: str = Form(""),
                    label: str = Form("")) -> RedirectResponse:
    """Mark (or un-mark) one bench task, with an outcome.

    ``done`` follows plain HTML checkbox semantics: present (``"1"``) only
    when the box was checked on submit, absent entirely when it was not --
    so posting without it (the Undo button) is the bench's own "undo": the
    step goes back to not-done and ``cuore.live.checklists.set_step``
    already clears its outcome/note when ``done`` is false.

    A step id is only meaningful in the context of the vehicle whose
    open-work cards named it -- same validation
    ``cuore.api.checklists.set_checklist_step`` already applies, reused here
    so a step id this VIN's dossier does not expose is a 400, not a silent
    no-op.
    """
    dossier = mes_bridge.workup(vin=vin)
    valid = dossier_bridge.checklist_step_ids(vin, dossier)
    if step_id not in valid:
        raise BadRequest(f"unknown checklist step id {step_id!r} for this vehicle")

    is_done = done == "1"
    clean_outcome = outcome.strip() or None
    if is_done and clean_outcome and clean_outcome not in _OUTCOMES:
        raise BadRequest(f"outcome must be one of {sorted(_OUTCOMES)}, got {clean_outcome!r}")

    checklist_store.set_step(vin, step_id, is_done, by=by, outcome=clean_outcome, note=note)

    # The one-tap "Fault found" button carries no typed note: file one naming
    # the step (``label``), so the finding still reaches History.
    finding = note.strip() or (f"Fault found at: {label.strip()}" if label.strip() else "")
    if is_done and clean_outcome == "fault_found" and finding:
        try:
            mes_bridge.add_note(vin, finding, target_kind="tree_step",
                                target_id=step_id, author=by or "technician",
                                tags=["bench", "finding"])
        except Exception:  # noqa: BLE001 -- the checklist write must still succeed
            pass

    if is_done:  # one-tap save: land on the next step with the Undo banner
        return RedirectResponse(f"/v/{vin}?saved={quote(step_id, safe='')}#bench-saved", status_code=303)
    return RedirectResponse(f"/v/{vin}#bench-next", status_code=303)


__all__ = ["router"]
