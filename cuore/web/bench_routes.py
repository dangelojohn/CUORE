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

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import APIRouter

from ..api.deps import require_token
from ..live import checklists as checklist_store
from ..services import bench_bridge, cache, dossier_bridge, mes_bridge
from ..services.errors import BadRequest
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: Mirrors ``cuore.api.checklists._OUTCOMES`` -- kept as a separate literal
#: (not imported) so this HTML form route has no dependency on the JSON API
#: module; the vocabulary is tiny and documented in both places.
_OUTCOMES = {"ok", "fault_found", "skipped"}


@router.get("/v/{vin}", response_class=HTMLResponse)
def bench_page(request: Request, vin: str) -> HTMLResponse:
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
    response = web_routes._page(request, "bench.html", vin=vin, bench=bench,
                                bar=bar, view=view, tab="bench")
    web_routes._set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/bench/done")
def bench_mark_done(vin: str, step_id: str = Form(...),
                    done: Optional[str] = Form(None), outcome: str = Form(""),
                    note: str = Form(""), by: str = Form("")) -> RedirectResponse:
    """Mark (or un-mark) one bench task, with an outcome.

    ``done`` follows plain HTML checkbox semantics: present (``"1"``) only
    when the box was checked on submit, absent entirely when it was not --
    so un-checking the box and pressing Save is the bench's own "undo": the
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

    if is_done and clean_outcome == "fault_found" and note.strip():
        try:
            mes_bridge.add_note(vin, note.strip(), target_kind="tree_step",
                                target_id=step_id, author=by or "technician",
                                tags=["bench", "finding"])
        except Exception:  # noqa: BLE001 -- the checklist write must still succeed
            pass

    return RedirectResponse(f"/v/{vin}#task-{step_id}", status_code=303)


__all__ = ["router"]
