"""Web-form face of the Job (case) workflow.

Same posture as ``cuore.web.dossier_routes``: a second router on the same
app reusing ``cuore.web.routes``'s own page/dossier helpers, so rendering
stays identical to every other ``/v/{vin}`` page. Every form here degrades
with no JavaScript -- a stepper of plain GET/POST/redirect forms, same
convention as ``/v/{vin}/dealer`` and ``/v/{vin}/notes``.

Job UX pass (docs/research/JOB_UX_FIXES_2026-10-08.md), 2026-10-08: every
mutating route below now redirects to ``?step=<the step it lives on>#<row
anchor>`` with a ``msg``/``mk`` (message/kind) query pair a toast reads --
never to a different tab, never to a different step (fix #5).

``cuore.services.jobs_bridge`` now carries the real guided-diagnostics
engine: ``edit_hypothesis``/``delete_hypothesis``/``undelete_hypothesis``/
``add_evidence``/``remove_evidence``/``resolve_evidence``/
``add_test_evidence``/``check_similar``/``step_registry``, and
``set_hypothesis`` enforces the confirm gate (open -> supported ->
confirmed, refuted from any state; confirm needs >=1 passed/failed test
result and 0 unresolved evidence_against -- fix #1) by raising
``jobs_bridge.RuleViolation`` *unconverted* -- this module's only job is to
catch that (never let it 500) and redirect back to the same card with its
``reason``/``next_test`` shown inline, per the 409 {detail, next_test}
contract. Every route below goes through ``jobs_bridge`` only -- no direct
``mes.jobs`` import here.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..api.deps import require_token
from ..services import cases_bridge, dossier_bridge, jobs_bridge, tools_kb_bridge
from ..services.errors import BridgeError
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

try:  # fix #12: System picker is a taxonomy select, not free text
    from mes import systems as _mes_systems
except Exception:  # noqa: BLE001 -- the manual hypothesis form must still render
    _mes_systems = None


def _systems_taxonomy() -> list[str]:
    if _mes_systems is None:
        return []
    try:
        return sorted({v.get("label", k) for k, v in _mes_systems.systems().items()})
    except Exception:  # noqa: BLE001
        return []


SYSTEMS_TAXONOMY: list[str] = _systems_taxonomy()


def _system_label_for_key(key: str) -> str:
    """``?system=<key>`` (a ``systems_bridge``/``mes.systems`` key, e.g.
    ``"evap"``) resolved to the human label the System ``<select>`` this
    page renders actually lists (``SYSTEMS_TAXONOMY``, and every
    hypothesis's own ``.system`` field) -- a bare key would never match any
    ``<option>``'s value. An unknown key, or ``mes.systems`` unavailable,
    reads as "" (no prefill) rather than a guess."""
    key = (key or "").strip().lower()
    if not key or _mes_systems is None:
        return ""
    try:
        row = _mes_systems.systems().get(key)
    except Exception:  # noqa: BLE001 -- a prefill hint must never 500 the page
        return ""
    return (row or {}).get("label") or ""


def _rule_violation_msg(exc: "jobs_bridge.RuleViolation") -> str:
    """One line out of a caught ``jobs_bridge.RuleViolation`` -- its own
    ``reason`` plus ``next_test`` when there is one, exactly what the toast
    shows (fix #1's 409 {detail, next_test} contract, rendered inline
    instead of as a raw HTTP body since this route serves an HTML form)."""
    reason = getattr(exc, "reason", None) or str(exc) or "That wasn't allowed."
    next_test = getattr(exc, "next_test", "") or ""
    return f"{reason} Next: {next_test}" if next_test else reason


def _step_redirect(vin: str, step: str = "", anchor: str = "", msg: str = "",
                   mk: str = "ok", extra: str = "") -> RedirectResponse:
    """Every mutating route's one exit: back to the *same* step, never a
    different tab or step (fix #5) -- optionally with a one-line toast
    message/kind and any extra query the receiving page wants (e.g.
    ``confirm=<hyp_id>`` for the confirm-summary panel)."""
    parts = []
    if step:
        parts.append(f"step={quote(str(step))}")
    if msg:
        parts.append(f"msg={quote(msg)}")
        parts.append(f"mk={quote(mk)}")
    if extra:
        parts.append(extra)
    qs = ("?" + "&".join(parts)) if parts else ""
    frag = f"#{anchor}" if anchor else ""
    return RedirectResponse(url=f"/v/{vin}/job{qs}{frag}", status_code=303)


@router.post("/tools-kb/inventory-form", response_class=HTMLResponse)
async def tools_inventory_form(status: str = Form(...), tool: str = Form(...),
                               return_to: str = Form(default="/")) -> RedirectResponse:
    """The "I have this / I don't" button pair on the tools panel -- a
    garage-wide owned/not-owned list (``cuore.services.tools_kb_bridge``),
    not tied to any one vehicle, so it lives here rather than under
    ``/v/{vin}/...`` even though the tools panel itself renders on
    vehicle-scoped pages (job.html, maintenance.html)."""
    tools_kb_bridge.inventory_set(tool, status)
    return RedirectResponse(url=return_to or "/", status_code=303)


def _job_page(request: Request, vin: str, job_id: str = "", tools_step: str = "",
             step: str = "", system: str = "", codes: str = "", hypothesis: str = "",
             **extra: Any) -> HTMLResponse:
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    job_view = jobs_bridge.build_job_view(vin, job_id or None, tools_step=tools_step or None)
    # Run 2, #9: _vehicle_bar falls back to "(unnamed vehicle)" straight
    # off dossier.identity; job_view["vehicle"] already carries
    # jobs_bridge._vehicle_name's richer resolution (shop_bridge corpus
    # name, then a WMI decode) -- the same fix bench_routes.py applies to
    # its own bar, so the Job tab's banner stops disagreeing with Bench's.
    if job_view.get("vehicle"):
        bar["name"] = job_view["vehicle"]
    live_status = web_routes._status_strip()
    try:
        dossier_view = dossier_bridge.build_view(vin, dossier, live_status)
    except Exception:  # noqa: BLE001 -- the job page must still render
        dossier_view = {"verdict": None, "open_work": [], "codes": [],
                        "code_counts": {}, "attempted": []}
    active_codes = [c["code"] for c in dossier_view.get("codes", [])
                    if c.get("status") == "ACTIVE"]
    try:
        case_prefill = cases_bridge.prefill(vin, active_codes)
    except Exception:  # noqa: BLE001 -- case memory must never 500 the job page
        case_prefill = None

    # --- display-only reshaping of job_view for this render (fix #11/#13):
    # active (non-deleted) hypotheses ranked by net evidence with the
    # leading one pinned first; deleted ones split out for an Undo row.
    # ``jobs_bridge.suggested_hypotheses`` already dedupes+ranks its own
    # list, so the suggestions themselves need no further work here --
    # job.html just slices the first 3 off for "top" vs. "Show N more".
    # Never mutates the stored job; this dict is built fresh per request.
    hyps = list((job_view.get("job") or {}).get("hypotheses") or [])
    active_hyps = [h for h in hyps if not h.get("deleted")]
    deleted_hyps = [h for h in hyps if h.get("deleted")]
    active_hyps.sort(
        key=lambda h: (len(h.get("evidence_for") or []) - len(h.get("evidence_against") or [])),
        reverse=True,
    )
    if job_view.get("job"):
        job_view["job"]["hypotheses"] = active_hyps
    job_view["deleted_hypotheses"] = deleted_hyps

    # Toast/flash state from a mutating route's redirect (fix #5) -- read
    # straight off the query string so this works with zero JavaScript;
    # job.js upgrades the same params into a nicer dismissable toast.
    qp = request.query_params
    flash_msg = qp.get("msg") or ""
    flash_kind = qp.get("mk") or "ok"
    confirm_pending = qp.get("confirm") or ""
    undo_hyp = qp.get("undo_hyp") or ""

    # The step 7 "+ Add a hypothesis" prefill (?system=<key>&codes=P0440,
    # P0455), step 5's "highlight these codes" (?codes=), and the "jump to
    # this existing card" pointer (?hypothesis=<id>, also what the "Do it
    # now" link on a hypothesis's own next_test now carries) -- all three
    # degrade to "no prefill" on a bad/empty value, never a 500. job.html
    # does the actual pre-select/pre-tick/expand with these, no JS
    # required; job.js only adds the one thing a plain GET can't do itself
    # (scrolling the target into view).
    prefill_system = _system_label_for_key(system)
    prefill_codes = [c.strip().upper() for c in codes.split(",") if c.strip()]
    prefill_hypothesis = hypothesis.strip()

    # `view` carries the full dossier view -- the shape _verdict_card.html,
    # _codes_table.html and _open_work.html already expect everywhere else
    # they're included; `job_view` carries the Job-specific data only
    # job.html itself reads.
    response = web_routes._page(request, "job.html", vin=vin, bar=bar, view=dossier_view,
                                job_view=job_view, case_prefill=case_prefill,
                                active_codes=active_codes, tab="job", step=step,
                                flash_msg=flash_msg, flash_kind=flash_kind,
                                confirm_pending=confirm_pending, undo_hyp=undo_hyp,
                                systems_taxonomy=SYSTEMS_TAXONOMY,
                                prefill_system=prefill_system, prefill_codes=prefill_codes,
                                prefill_hypothesis=prefill_hypothesis, **extra)
    web_routes._set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/job", response_class=HTMLResponse)
def job_page(request: Request, vin: str, tools_step: str = "", step: str = "",
            system: str = "", codes: str = "", hypothesis: str = "") -> HTMLResponse:
    """The current (or most recent) job for this vehicle, one step per
    screen -- ``step`` is the only query param this page reads to pick
    which of the 12 steps is the full screen (default: the flow's own
    current step, resolved inside job.html itself). ``system``/``codes``/
    ``hypothesis`` are the step 5/7 prefill hints -- see ``_job_page``."""
    return _job_page(request, vin, tools_step=tools_step, step=step,
                     system=system, codes=codes, hypothesis=hypothesis)


@router.get("/v/{vin}/job/{job_id}", response_class=HTMLResponse)
def job_page_one(request: Request, vin: str, job_id: str, tools_step: str = "",
                 step: str = "", system: str = "", codes: str = "",
                 hypothesis: str = "") -> HTMLResponse:
    """One specific job by id -- e.g. a closed case from this car's history."""
    return _job_page(request, vin, job_id=job_id, tools_step=tools_step, step=step,
                     system=system, codes=codes, hypothesis=hypothesis)


@router.post("/v/{vin}/job/open", response_class=HTMLResponse)
async def job_open(request: Request, vin: str,
                   technician: str = Form(default=""),
                   complaint: str = Form(default="")) -> RedirectResponse:
    """Step 1: open a new case for this vehicle, in the driver's own words."""
    jobs_bridge.open_job(vin, technician=technician, complaint=complaint)
    return _step_redirect(vin, "1", msg="Case opened.", mk="ok")


@router.post("/v/{vin}/job/{job_id}/hypotheses", response_class=HTMLResponse)
async def hypothesis_add(request: Request, vin: str, job_id: str,
                         text: str = Form(...), system: str = Form(default=""),
                         next_test: str = Form(default=""),
                         likelihood: str = Form(default=""),
                         codes: str = Form(default=""),
                         by: str = Form(default=""),
                         step: str = Form(default="7")) -> RedirectResponse:
    """Step 7: add a hypothesis by hand (fix #12: System is a taxonomy pick,
    Linked codes a multi-select of open DTCs, Likelihood Low/Med/High)."""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    likelihood_val = likelihood.strip().lower() or None
    try:
        hyp = jobs_bridge.add_hypothesis(job_id, text, system=system, next_test=next_test,
                                         codes=code_list or None, likelihood=likelihood_val,
                                         by=by.strip() or None)
    except BridgeError as exc:
        return _step_redirect(vin, step, anchor="add-hypothesis", msg=str(exc), mk="err")
    return _step_redirect(vin, step, anchor=f"hyp-{hyp['id']}", msg="Hypothesis added.", mk="ok")


@router.get("/v/{vin}/job/{job_id}/hypotheses/similar")
def hypothesis_similar(vin: str, job_id: str, text: str = "", system: str = "") -> dict[str, Any]:
    """Fix #11's "Similar to ... -- merge?" prompt, read live as the tech
    types (job.js debounces this) -- thin pass-through to
    ``jobs_bridge.check_similar``, the real token-overlap check against the
    job on file, so the prompt is never a client-side guess. No JS -> no
    prompt, no behaviour change: the manual-add form still saves a new
    hypothesis either way."""
    try:
        match = jobs_bridge.check_similar(job_id, text, system)
    except Exception:  # noqa: BLE001 -- a hint must never 500
        match = None
    if not match:
        return {"similar": None}
    return {"similar": {"id": match["id"], "text": match["text"]}}


@router.post("/v/{vin}/job/{job_id}/hypotheses/suggested", response_class=HTMLResponse)
async def hypothesis_add_suggested(request: Request, vin: str, job_id: str,
                                   text: str = Form(...), system: str = Form(default=""),
                                   next_test: str = Form(default=""),
                                   evidence_for: str = Form(default="[]"),
                                   evidence_against: str = Form(default="[]"),
                                   step: str = Form(default="7")
                                   ) -> RedirectResponse:
    """Step 7: promote one of the auto-suggested hypotheses, with its real
    evidence attached in the same step -- the refs travel as a hidden JSON
    field rather than being retyped, so nothing here can invent evidence
    that was not already shown on the page."""
    suggestion = {
        "text": text, "system": system, "next_test": next_test,
        "evidence_for": json.loads(evidence_for) if evidence_for.strip() else [],
        "evidence_against": json.loads(evidence_against) if evidence_against.strip() else [],
    }
    hyp = jobs_bridge.add_suggested_hypothesis(job_id, suggestion)
    return _step_redirect(vin, step, anchor=f"hyp-{hyp['id']}",
                          msg="Hypothesis added from suggestion.", mk="ok")


@router.post("/v/{vin}/job/{job_id}/hypotheses/{hyp_id}/status", response_class=HTMLResponse)
async def hypothesis_set_status(request: Request, vin: str, job_id: str, hyp_id: str,
                                status: str = Form(...), step: str = Form(default="7"),
                                ack: str = Form(default=""),
                                by: str = Form(default="")) -> RedirectResponse:
    """Step 7: the status buttons -- open / supported / refuted / confirmed.

    Fix #1: ``jobs_bridge.set_hypothesis`` itself enforces the path (open ->
    supported -> confirmed, refuted from any state) and the confirm gate
    (>=1 passed/failed test evidence_for, 0 unresolved evidence_against),
    raising ``jobs_bridge.RuleViolation`` -- caught below and shown inline
    (the 409 {detail, next_test} contract, rendered as this HTML form's own
    toast), never a 500 and never silently accepted. ``confirmed``
    additionally needs a second tap (``ack=1``): the first tap just
    redirects back with ``confirm=<hyp_id>`` so job.html renders the
    evidence-summary panel job.js promotes into a modal -- its own "confirm
    again" button is what actually sends ``ack=1``; if the gate would have
    refused anyway, that second POST catches the same RuleViolation. ``by``
    (who) rides along so the engine can stamp confirmed_by/at."""
    if status == "confirmed" and ack != "1":
        return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", extra=f"confirm={hyp_id}")

    # Job UX run 2, R8: Undo on a status-change toast, same posture as
    # Delete's own undo below -- remember the status this hypothesis was
    # on *before* this call so a toast click can put it straight back.
    old_status = ""
    try:
        old_job = jobs_bridge.get_job(job_id)
        old_hyp = next((h for h in (old_job.get("hypotheses") or []) if h.get("id") == hyp_id), None)
        old_status = (old_hyp or {}).get("status") or ""
    except Exception:  # noqa: BLE001 -- the undo hint is never load-bearing
        old_status = ""

    try:
        jobs_bridge.set_hypothesis(job_id, hyp_id, status=status, by=by.strip() or None)
    except jobs_bridge.RuleViolation as exc:
        return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}",
                              msg=_rule_violation_msg(exc), mk="err")
    except BridgeError as exc:
        return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg=str(exc), mk="err")
    undo_extra = (f"undo_status={quote(hyp_id)}:{quote(old_status)}"
                 if old_status and old_status != status else "")
    return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg=f"Status set to {status}.",
                          mk="ok", extra=undo_extra)


@router.post("/v/{vin}/job/{job_id}/hypotheses/{hyp_id}/next_test", response_class=HTMLResponse)
async def hypothesis_set_next_test(request: Request, vin: str, job_id: str, hyp_id: str,
                                   next_test: str = Form(default=""),
                                   step: str = Form(default="7")) -> RedirectResponse:
    jobs_bridge.set_hypothesis(job_id, hyp_id, next_test=next_test)
    return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg="Saved.", mk="ok")


@router.post("/v/{vin}/job/{job_id}/hypotheses/{hyp_id}/edit", response_class=HTMLResponse)
async def hypothesis_edit(request: Request, vin: str, job_id: str, hyp_id: str,
                          text: str = Form(default=""), system: str = Form(default=""),
                          next_test: str = Form(default=""),
                          likelihood: str = Form(default=""),
                          codes: str = Form(default=""),
                          by: str = Form(default=""),
                          step: str = Form(default="7")) -> RedirectResponse:
    """Fix #2: Edit -- any hypothesis field except status/evidence, which go
    through their own gated routes so editing can never route around the
    confirm gate."""
    kw: dict[str, Any] = {}
    if text.strip():
        kw["text"] = text
    if system:
        kw["system"] = system
    if next_test:
        kw["next_test"] = next_test
    if likelihood:
        kw["likelihood"] = likelihood.strip().lower()
    if codes.strip():
        kw["codes"] = [c.strip() for c in codes.split(",") if c.strip()]
    if not kw:
        return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg="Nothing to save.", mk="warn")
    try:
        jobs_bridge.edit_hypothesis(job_id, hyp_id, by=by.strip() or None, **kw)
    except BridgeError as exc:
        return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg=str(exc), mk="err")
    return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg="Hypothesis updated.", mk="ok")


@router.post("/v/{vin}/job/{job_id}/hypotheses/{hyp_id}/evidence", response_class=HTMLResponse)
async def hypothesis_evidence(request: Request, vin: str, job_id: str, hyp_id: str,
                              side: str = Form(default="for"),
                              kind: str = Form(default="observation"),
                              ref_id: str = Form(default=""),
                              label: str = Form(...),
                              op: str = Form(default="add"),
                              by: str = Form(default=""),
                              step: str = Form(default="7")) -> RedirectResponse:
    """Fix #2: + Evidence for / + Evidence against, and the remove side of
    the same picker -- thin pass-through to ``jobs_bridge.add_evidence``/
    ``remove_evidence``, which is what the confirm gate itself reads, so an
    item linked here is real evidence for fix #1 the moment it's added."""
    side = side if side in ("for", "against") else "for"
    if op == "remove":
        try:
            jobs_bridge.remove_evidence(job_id, hyp_id, side, ref_id or label,
                                        ref_kind=kind or None, by=by.strip() or None)
        except BridgeError as exc:
            return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg=str(exc), mk="err")
        return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg="Evidence removed.",
                              mk="ok", extra=f"undo_ev={hyp_id}:{side}:{quote(label)}")

    ref = {"kind": kind or "observation", "id": ref_id or label, "label": label}
    try:
        jobs_bridge.add_evidence(job_id, hyp_id, side, ref, by=by.strip() or None)
    except BridgeError as exc:
        return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg=str(exc), mk="err")
    return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}",
                          msg=f"Evidence {'for' if side == 'for' else 'against'} added.", mk="ok")


@router.post("/v/{vin}/job/{job_id}/hypotheses/{hyp_id}/delete", response_class=HTMLResponse)
async def hypothesis_delete(request: Request, vin: str, job_id: str, hyp_id: str,
                            by: str = Form(default=""),
                            step: str = Form(default="7")) -> RedirectResponse:
    """Fix #2: Delete, soft (``jobs_bridge.delete_hypothesis``) -- the card
    itself stays on the audit trail; the undo offered in the toast is
    :func:`hypothesis_undelete` below."""
    try:
        jobs_bridge.delete_hypothesis(job_id, hyp_id, by=by.strip() or None)
    except BridgeError as exc:
        return _step_redirect(vin, step, anchor="hypotheses", msg=str(exc), mk="err")
    return _step_redirect(vin, step, anchor="hypotheses", msg="Hypothesis deleted.", mk="ok",
                          extra=f"undo_hyp={hyp_id}")


@router.post("/v/{vin}/job/{job_id}/hypotheses/{hyp_id}/undelete", response_class=HTMLResponse)
async def hypothesis_undelete(request: Request, vin: str, job_id: str, hyp_id: str,
                              by: str = Form(default=""),
                              step: str = Form(default="7")) -> RedirectResponse:
    try:
        jobs_bridge.undelete_hypothesis(job_id, hyp_id, by=by.strip() or None)
    except BridgeError as exc:
        return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg=str(exc), mk="err")
    return _step_redirect(vin, step, anchor=f"hyp-{hyp_id}", msg="Hypothesis restored.", mk="ok")


@router.post("/v/{vin}/job/{job_id}/actions", response_class=HTMLResponse)
async def action_add(request: Request, vin: str, job_id: str,
                     kind: str = Form(...), text: str = Form(...),
                     step: str = Form(default="9")) -> RedirectResponse:
    """Step 9: record one repair action -- test, inspection, repair, part,
    clear, or a free-text note."""
    jobs_bridge.add_action(job_id, kind, text)
    return _step_redirect(vin, step, anchor="actions", msg="Action recorded.", mk="ok")


@router.post("/v/{vin}/job/{job_id}/tools-review", response_class=HTMLResponse)
async def tools_review_add(request: Request, vin: str, job_id: str) -> RedirectResponse:
    """Step 12: the mandatory "tools used" review -- what was actually used
    at release, right/wrong/unsure with a reason, anything missing, and
    what he'd buy next time. Field names are dynamic (one triplet per
    recommended tool, keyed by tool key) because the recommended-tool list
    itself is dynamic, so this reads the raw form rather than a fixed
    Pydantic/Form model -- same reasoning job_page's tools panel is built
    for a variable-length list.
    """
    form = await request.form()

    def _get(key: str) -> str:
        v = form.get(key)
        return str(v).strip() if v is not None else ""

    step = _get("step") or "diagnostics"
    tools_used: list[dict[str, Any]] = []
    for key in form.keys():
        if key.startswith("used__") and _get(key):
            tool_key = key[len("used__"):]
            tools_used.append({
                "tool": tool_key,
                "was_right": _get(f"right__{tool_key}") or "unsure",
                "note": _get(f"note__{tool_key}"),
            })
    for i in range(1, 4):
        name = _get(f"extra{i}_name")
        if name:
            tools_used.append({
                "tool": name,
                "was_right": _get(f"extra{i}_right") or "unsure",
                "note": _get(f"extra{i}_note"),
            })

    missing_tools = [m.strip() for m in _get("missing_tools").split(",") if m.strip()]

    would_buy: list[dict[str, Any]] = []
    for i in range(1, 4):
        name = _get(f"buy{i}_name")
        if name:
            would_buy.append({"name": name, "why": _get(f"buy{i}_why")})

    time_min_raw = _get("time_min")
    time_min = float(time_min_raw) if time_min_raw else None

    jobs_bridge.add_tool_usage(vin, step, job_id, by=_get("by"), tools_used=tools_used,
                               missing_tools=missing_tools, would_buy=would_buy,
                               time_min=time_min)
    return _step_redirect(vin, "12", anchor="outcome", msg="Tools review saved.", mk="ok")


@router.post("/v/{vin}/job/{job_id}/close", response_class=HTMLResponse)
async def job_close(request: Request, vin: str, job_id: str,
                    outcome: str = Form(...),
                    codes_returned: str = Form(default=""),
                    verdict: str = Form(default=""),
                    tools_review_skip_reason: str = Form(default="")) -> HTMLResponse:
    """Step 12: close the case. Outcome is required -- a job can never be
    closed with no stated result. Also gated on the tools-used review
    (see ``jobs_bridge.close_job``) -- ``tools_review_skip_reason`` lets a
    mechanic close without filling the review, but only by stating why."""
    codes = [c.strip() for c in codes_returned.split(",") if c.strip()]
    error = None
    try:
        jobs_bridge.close_job(job_id, outcome, codes_returned=codes or None,
                              verdict=verdict or None,
                              tools_review_skip_reason=tools_review_skip_reason)
    except BridgeError as exc:
        error = str(exc)
    # Rendered directly (no redirect) -- the close form lives on step 12's
    # screen, so that's the screen the re-render must show, regardless of
    # the flow's own current-step opinion, or a refusal would render onto
    # whatever step happens to be current and never be seen.
    return _job_page(request, vin, job_id=job_id, close_error=error, step="12")


__all__ = ["router"]
