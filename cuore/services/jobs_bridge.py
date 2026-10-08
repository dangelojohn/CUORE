"""Assembles the Job page: one case per shop visit, aligning driver input,
mechanic input, test results and malfunctions into one logical flow.

This is the only module that imports :mod:`mes.jobs` directly, same posture
as every other ``*_bridge.py`` here. ``build_job_view`` is the single entry
point: it resolves which job is "current" for a VIN, then gathers real
evidence already sitting in the other bridges (the dossier's verdict and
open-work, the mechanic-vs-driver timeline's symptoms, technician notes,
media and feedback counts, dealer results, electrical inspections, systems
correlation chains) into one shape the template renders, plus a short list
of *suggested* hypotheses pre-filled with real evidence_for/against refs --
never an invented one. Writing (opening a job, adding a hypothesis/action,
attaching evidence, closing) is thin pass-through to :mod:`mes.jobs`, which
does the validation.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache, dossier_bridge, mes_bridge, timeline_bridge, tools_kb_bridge
from .errors import BadRequest, NotFound

from mes import jobs as jobs_mod  # noqa: E402
from mes import tools_kb  # noqa: E402

try:
    from . import electrical_bridge
except Exception:  # noqa: BLE001 -- the job page must render without it
    electrical_bridge = None

try:
    from . import systems_bridge
except Exception:  # noqa: BLE001
    systems_bridge = None

try:
    from . import media_bridge
except Exception:  # noqa: BLE001
    media_bridge = None

try:
    from . import feedback_bridge
except Exception:  # noqa: BLE001
    feedback_bridge = None


# --- small ref builders -------------------------------------------------


def _ref(kind: str, id_: Any, label: str) -> dict[str, Any]:
    return {"kind": kind, "id": id_, "label": label}


# --- suggested hypotheses, built only from real data ---------------------


def _evap_suggestions(vin: str, view: dict[str, Any]) -> list[dict[str, Any]]:
    """The two EVAP hypotheses this corpus's own fault tree/bulletins
    distinguish: a signal-path fault at the ESIM, vs. an ECM calibration
    issue the TSBs describe. Only offered when the dossier's open-work
    already names an EVAP family card -- no family, no suggestion."""
    evap_card = next((c for c in view.get("open_work", []) if c.get("family") == "EVAP"), None)
    if evap_card is None:
        return []

    freeze_frames = view.get("freeze_frames", [])
    attempted = view.get("attempted", [])
    bulletins = view.get("bulletins", [])

    fuel_flag_evidence = [
        _ref("freeze_frame", f["code"], f"{f['code']} freeze frame: {k['flag']}")
        for f in freeze_frames for k in f.get("key", []) if k.get("flag")
    ]
    esim_step = next((s for s in evap_card.get("steps", []) if s["id"] == "evap-4"), None)
    esim_evidence_for = list(fuel_flag_evidence)
    if esim_step is not None and esim_step.get("done"):
        esim_evidence_for.append(_ref("inspection", "evap-4",
                                      "ESIM/canister inspection logged done"))
    actuator_evidence = [
        _ref("actuator", a["operation"],
             f"{a['operation']}: {a['outcome']} x{a['count']}")
        for a in attempted if "evapor" in (a.get("operation") or "").lower()
    ]
    esim_evidence_for += actuator_evidence

    calibration_bulletins = [b for b in bulletins
                             if "calib" in (b.get("title") or "").lower()
                             or "calib" in (b.get("action") or "").lower()]
    calib_evidence_for = [
        _ref("bulletin", b["id"], f"{b['id']}: {b['title']}") for b in calibration_bulletins
    ]
    dealer_results = mes_bridge.dealer_results(vin).get("results", [])
    slvt = [r for r in dealer_results if r.get("kind") == "slvt"]
    calib_evidence_for += [
        _ref("dealer", r.get("at"), f"SLVT {r['data'].get('result')}: {r['data'].get('detail') or ''}".strip(": "))
        for r in slvt if (r.get("data") or {}).get("result") == "fail"
    ]
    calib_evidence_against = [
        _ref("dealer", r.get("at"), f"SLVT {r['data'].get('result')}: {r['data'].get('detail') or ''}".strip(": "))
        for r in slvt if (r.get("data") or {}).get("result") == "pass"
    ]

    history = view.get("codes", [])
    returned = [r for r in history if r.get("bucket") == "returned_after_clear"]
    returned_evidence = [
        _ref("code", r["code"], f"{r['code']} returned after clear ({r.get('last_seen_short')})")
        for r in returned
    ]

    out = [
        {"text": "EVAP: ESIM signal path", "system": "EVAP",
         "evidence_for": esim_evidence_for, "evidence_against": [],
         "next_test": "Smoke test the recirculation line and canister/ESIM "
                      "connector under light vacuum."},
        {"text": "EVAP: ECM calibration", "system": "EVAP",
         "evidence_for": calib_evidence_for + returned_evidence,
         "evidence_against": calib_evidence_against,
         "next_test": "Check PCM calibration level against the latest EVAP "
                      "TSB before condemning hardware (SLVT or Mode $06)."},
    ]
    return out


def _network_suggestions(view: dict[str, Any]) -> list[dict[str, Any]]:
    net_card = next((c for c in view.get("open_work", []) if c.get("family") == "network"
                     or c.get("family") == "NETWORK"), None)
    if net_card is None:
        return []
    refs = [_ref("bulletin", r["label"], r["label"]) for r in net_card.get("refs", []) if r.get("label")]
    return [{"text": "Network: power/ground or bus event", "system": "network",
            "evidence_for": refs, "evidence_against": [],
            "next_test": "Check F82 fuse/BCM supply and the connectors/grounds "
                         "this fault tree cites before chasing individual codes."}]


#: EVAP and network each got a hand-written hypothesis builder above,
#: because they're this app's first, richest examples. Every other family
#: dossier_bridge's generic open-work builder can produce (misfire,
#: fuel_trim, cooling, body, chassis, adas, etc.) still deserves a
#: hypothesis per code -- built the same way, from real evidence, just
#: without a bespoke pair of ESIM/calibration-style hypotheses hand-written
#: for it. Skipped here so the two curated builders above keep owning their
#: own families rather than being duplicated.
_CURATED_FAMILIES = {"EVAP", "network"}


def _hypothesis_for_code(family: str, code: str,
                         steps: list[dict[str, Any]]) -> tuple[str, str]:
    """``(hypothesis text, next_test)`` for one code, built only from the
    real steps its own generated fault tree already produced -- see
    ``dossier_bridge._generic_tree_steps`` (``mes.faulttree.tree_for``).
    Never invents a branch beyond re-labelling a real step's own text."""
    swap_step = next(
        (s for s in steps if "swap" in (s.get("text") or "").lower()), None)
    if family == "misfire":
        m = re.match(r"^P030([1-4])$", code)
        cyl = f" cylinder {m.group(1)}" if m else ""
        text = f"{code}: coil or plug{cyl} (swap test)"
        next_test = swap_step["text"] if swap_step else (
            steps[0]["text"] if steps else "")
        return text, next_test
    lead = swap_step or (steps[0] if steps else None)
    if lead is None:
        return f"{code}: {family} fault", ""
    short = (lead["text"].split(":", 1)[0] if ":" in lead["text"]
             else lead["text"])
    return f"{code}: {short}", lead["text"]


def _generic_family_suggestions(vin: str, view: dict[str, Any]
                                ) -> list[dict[str, Any]]:
    """One hypothesis per code for every open-work family dossier_bridge
    generated generically (i.e. everything that isn't EVAP/network), each
    pre-filled with real evidence: freeze frames and returned-after-clear
    history for that exact code, logged-done steps from the same card, and
    any bulletin that names the code -- the same evidence_for/against
    discipline as the EVAP/network builders, just applied to whichever
    family this car's own history actually has open."""
    freeze_frames = view.get("freeze_frames", [])
    codes_hist = view.get("codes", [])
    bulletins = view.get("bulletins", [])
    out: list[dict[str, Any]] = []
    for card in view.get("open_work", []):
        family = card.get("family") or ""
        if family in _CURATED_FAMILIES or not card.get("generic"):
            continue
        steps = card.get("steps", [])
        done_steps = [s for s in steps if s.get("done")]
        for code in card.get("codes", []):
            evidence_for = [
                _ref("freeze_frame", f["code"], f"{f['code']} freeze frame")
                for f in freeze_frames if f.get("code", "").startswith(code)
            ]
            evidence_for += [
                _ref("inspection", s["id"], f"{s['text']} -- logged done")
                for s in done_steps
            ]
            evidence_for += [
                _ref("bulletin", b["id"], f"{b['id']}: {b.get('title', '')}")
                for b in bulletins if code in (b.get("codes") or [])
            ]
            evidence_for += [
                _ref("code", r["code"],
                     f"{r['code']} returned after clear ({r.get('last_seen_short')})")
                for r in codes_hist
                if r.get("code") == code and r.get("bucket") == "returned_after_clear"
            ]
            text, next_test = _hypothesis_for_code(family, code, steps)
            out.append({"text": text, "system": family,
                       "evidence_for": evidence_for, "evidence_against": [],
                       "next_test": next_test})
    return out


def suggested_hypotheses(vin: str, view: dict[str, Any]) -> list[dict[str, Any]]:
    """Hypotheses this car's own fault tree/bulletins already point at, each
    pre-filled with real evidence_for/against refs -- never invented. The
    mechanic adds whichever apply via the job page's form; nothing here
    writes anything."""
    return (_evap_suggestions(vin, view) + _network_suggestions(view)
           + _generic_family_suggestions(vin, view))


# --- gathering the rest of the stepper's "auto-gathered evidence" --------


def _cached_workup(vin: str) -> dict[str, Any]:
    """The same memoised workup ``cuore.web.routes._dossier`` builds for the
    dossier page, keyed identically (vin, newest MES-log mtime) so the two
    share one cache entry instead of each re-running ``mes_bridge.workup`` --
    which alone re-parses every FES log for the VIN, seconds of work on a
    real corpus (see ``cuore.services.cache``)."""
    return cache.get_or_build(
        ("workup", vin, mes_bridge.newest_mtime(vin)),
        lambda: mes_bridge.workup(vin=vin),
    )


def _symptoms(vin: str) -> list[dict[str, Any]]:
    try:
        return timeline_bridge.symptoms(vin)["symptoms"]
    except Exception:  # noqa: BLE001
        return []


def _notes(vin: str) -> list[dict[str, Any]]:
    try:
        return mes_bridge.notes(vin)["notes"]
    except Exception:  # noqa: BLE001
        return []


def _media_count(vin: str) -> int:
    if media_bridge is None:
        return 0
    try:
        return len(media_bridge.list_media(vin)["items"])
    except Exception:  # noqa: BLE001
        return 0


def _feedback_open_count(vin: str) -> int:
    if feedback_bridge is None:
        return 0
    try:
        return len(feedback_bridge.load(vin, status="open")["feedback"])
    except Exception:  # noqa: BLE001
        return 0


def _dealer_results(vin: str) -> list[dict[str, Any]]:
    try:
        return mes_bridge.dealer_results(vin)["results"]
    except Exception:  # noqa: BLE001
        return []


def _electrical_inspections(vin: str) -> list[dict[str, Any]]:
    if electrical_bridge is None:
        return []
    try:
        return electrical_bridge.list_inspections(vin)
    except Exception:  # noqa: BLE001
        return []


def _systems_chains(vin: str) -> list[dict[str, Any]]:
    if systems_bridge is None:
        return []
    try:
        # Pure corpus analysis (mes.systems.correlate reuses mes.analysis/
        # mes.workup data) -- no mutable state read, so the MES-log mtime
        # alone is the right cache key, same as the workup itself.
        data = cache.get_or_build(
            ("systems_correlate", vin, mes_bridge.newest_mtime(vin)),
            lambda: systems_bridge.correlate(vin),
        )
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, dict) or data.get("error"):
        return []
    return data.get("chains", [])


# --- tools for this job: recommend + what was learned last time ----------

#: Every job/step key ``mes.tools_kb`` knows, for the Job page's "job type
#: (for tool recommendations)" picker -- built from JOB_TOOLS itself so a
#: new step key added there shows up here with no second place to update.
TOOLS_STEP_CHOICES: tuple[str, ...] = tuple(tools_kb.JOB_TOOLS.keys())


def _infer_tools_step_key(view: dict[str, Any]) -> str:
    """A reasonable default job/step key for this case's own evidence --
    never a guess at a *size* or *tool*, just which already-tabulated
    step's tool list is most likely relevant, so the mechanic sees
    something useful before touching the picker. Falls back to
    "diagnostics", which is always a safe, honest default."""
    families = {c.get("family") for c in view.get("open_work", [])}
    if "EVAP" in families:
        return "evap_smoke_test"
    if "network" in families or "NETWORK" in families:
        return "network_voltage_drop"
    return "diagnostics"


def tools_panel(step: str, vin: str) -> dict[str, Any]:
    """The merged recommend+learned payload the Job/Maintenance pages
    render through ``_tools_panel.html``."""
    return tools_kb_bridge.recommend_with_learning(step, vin=vin)


def add_tool_usage(vin: str, step: str, job_id: str, **kw: Any) -> dict[str, Any]:
    return tools_kb_bridge.add_usage(vin, step, job_id=job_id, **kw)


# --- job CRUD, thin pass-through to mes.jobs ------------------------------


def open_job(vin: str, *, technician: str = "", complaint: str = "") -> dict[str, Any]:
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    try:
        return jobs_mod.open(vin, technician=technician, complaint=complaint)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def close_job(job_id: str, outcome: str, *, tools_review_skip_reason: str = "",
             **kw: Any) -> dict[str, Any]:
    """Close a job -- gated on the mandatory "tools used" review: a job
    cannot close until :func:`add_tool_usage` has recorded a review against
    it, or the mechanic explicitly skips the review with a stated reason
    (recorded as a job action, so the handover record shows it was a
    deliberate skip, not an omission)."""
    job = jobs_mod.get(job_id)
    if job is None:
        raise BadRequest(f"no job {job_id!r}")
    skip_reason = (tools_review_skip_reason or "").strip()
    reviewed = tools_kb_bridge.has_review(job["vin"], job_id)
    if not reviewed and not skip_reason:
        raise BadRequest(
            "Tools used review is required before closing this job -- fill "
            "it out at step 7, or explicitly skip it with a reason.")
    if skip_reason and not reviewed:
        jobs_mod.add_action(job_id, "note", f"Tools-used review skipped: {skip_reason}")
    try:
        return jobs_mod.close(job_id, outcome, **kw)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def add_hypothesis(job_id: str, text: str, *, system: str = "",
                   next_test: str = "") -> dict[str, Any]:
    try:
        return jobs_mod.add_hypothesis(job_id, text, system=system, next_test=next_test)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def set_hypothesis(job_id: str, hyp_id: str, *, status: Optional[str] = None,
                   next_test: Optional[str] = None) -> dict[str, Any]:
    try:
        return jobs_mod.set_hypothesis(job_id, hyp_id, status=status, next_test=next_test)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def add_action(job_id: str, kind: str, text: str, *,
              ref: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    try:
        return jobs_mod.add_action(job_id, kind, text, ref=ref)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def attach(job_id: str, ref: dict[str, Any], **kw: Any) -> dict[str, Any]:
    try:
        return jobs_mod.attach(job_id, ref, **kw)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def get_job(job_id: str) -> dict[str, Any]:
    job = jobs_mod.get(job_id)
    if job is None:
        raise NotFound(f"no job {job_id!r}")
    return job


def add_suggested_hypothesis(job_id: str, suggestion: dict[str, Any]) -> dict[str, Any]:
    """Promote one of :func:`suggested_hypotheses`' entries into a real
    hypothesis on the job, with its real evidence attached. The suggestion
    dict must be one this module itself produced (or shaped identically) --
    every evidence ref it carries already points at a real record, so
    attaching it here invents nothing new."""
    hyp = add_hypothesis(job_id, suggestion["text"], system=suggestion.get("system", ""),
                         next_test=suggestion.get("next_test", ""))
    for ref in suggestion.get("evidence_for", []):
        attach(job_id, ref, hyp_id=hyp["id"], supports=True)
    for ref in suggestion.get("evidence_against", []):
        attach(job_id, ref, hyp_id=hyp["id"], supports=False)
    job = get_job(job_id)
    return next(h for h in job["hypotheses"] if h["id"] == hyp["id"])


# --- the one read entry point ---------------------------------------------


def build_job_view(vin: str, job_id: Optional[str] = None, *,
                   tools_step: Optional[str] = None) -> dict[str, Any]:
    """Everything the Job page needs, computed once. ``job`` is ``None`` when
    this VIN has no matching job yet (job_id given but not found raises
    NotFound instead, since that is a bad link, not an empty state).

    ``tools_step`` picks which ``mes.tools_kb`` job/step key the "Tools for
    this step" panel (steps 3 and 5) and the mandatory review (step 7) use;
    left unset, it is inferred from this case's own open-work family."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")

    if job_id:
        job = get_job(job_id)
        if job.get("vin") != vin:
            raise NotFound(f"job {job_id!r} does not belong to {vin!r}")
    else:
        job = jobs_mod.current(vin)
        if job is None:
            jobs_for_vin = jobs_mod.load(vin)
            job = jobs_for_vin[-1] if jobs_for_vin else None

    try:
        dossier = _cached_workup(vin)
    except Exception:  # noqa: BLE001 -- the job page must still render
        dossier = {}
    try:
        dossier_view = dossier_bridge.build_view(vin, dossier, None)
    except Exception:  # noqa: BLE001
        dossier_view = {"verdict": None, "open_work": [], "codes": [],
                        "freeze_frames": [], "attempted": [], "bulletins": []}

    suggestions = suggested_hypotheses(vin, dossier_view)
    existing_texts = {h["text"] for h in (job or {}).get("hypotheses", [])}
    suggestions = [s for s in suggestions if s["text"] not in existing_texts]

    step_key = (tools_step or "").strip() or _infer_tools_step_key(dossier_view)
    try:
        panel = tools_panel(step_key, vin)
    except Exception:  # noqa: BLE001 -- the job page must still render
        panel = {"step": step_key, "tools": [], "learned": {}}

    reviewed = bool(job) and tools_kb_bridge.has_review(vin, job["id"])

    return {
        "vin": vin,
        "job": job,
        "all_jobs": jobs_mod.load(vin),
        "dossier_verdict": dossier_view.get("verdict"),
        "open_work": dossier_view.get("open_work", []),
        "suggested_hypotheses": suggestions,
        "symptoms": _symptoms(vin),
        "notes": _notes(vin),
        "media_count": _media_count(vin),
        "feedback_open_count": _feedback_open_count(vin),
        "dealer_results": _dealer_results(vin),
        "electrical_inspections": _electrical_inspections(vin),
        "systems_chains": _systems_chains(vin),
        "tools_step_key": step_key,
        "tools_step_choices": TOOLS_STEP_CHOICES,
        "tools_panel": panel,
        "tools_reviewed": reviewed,
    }


__all__ = ["build_job_view", "suggested_hypotheses", "open_job", "close_job",
          "add_hypothesis", "set_hypothesis", "add_action", "attach",
          "get_job", "add_suggested_hypothesis", "TOOLS_STEP_CHOICES",
          "tools_panel", "add_tool_usage"]
