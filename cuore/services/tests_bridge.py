"""The Tests surface: a catalogue of every mechanic test (:mod:`mes.mechanic_tests`)
grouped by category, each with this vehicle's latest recorded result and a
relevance ranking against its open codes and its job's open hypotheses.

Same posture as :mod:`cuore.services.liveboard_bridge`: one bridge module,
read-mostly, the single place ``cuore`` touches :mod:`mes.mechanic_tests` and
:mod:`mes.jobs` for this feature. Results are written through the existing
checklist result store (:mod:`cuore.live.checklists`), keyed
``step_id = "test:<test_id>"`` so they already flow into the job's
hypothesis evidence path the same way a job-page test row does (see
:mod:`cuore.api.checklists`'s own ``/result`` route, and
:func:`cuore.services.jobs_bridge.add_test_evidence`) -- :mod:`cuore.api.tests`
calls that same function, never a second copy of the auto-attach logic.

Nothing here writes to the car. ``bench_bridge.build_bench`` is read for its
``fuel_gate`` only, to flag the EVAP fuel-level verification window on the
tests it actually affects (the ESIM/EVAP monitor-verification family) --
same blocker the bench page itself already shows.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live import checklists as checklist_store
from . import cache, mes_bridge
from .errors import BadRequest

from mes import mechanic_tests  # noqa: E402

try:
    from mes import jobs as jobs_mod  # noqa: E402
except Exception:  # noqa: BLE001 -- the tests page must still render
    jobs_mod = None

try:
    from . import bench_bridge
except Exception:  # noqa: BLE001 -- blocker awareness is a nice-to-have
    bench_bridge = None

#: Step-id prefix for a test result in the checklist store -- see module
#: docstring. Every write/read against ``checklist_store`` for this feature
#: goes through :func:`_step_id`, never a hand-built string.
_STEP_PREFIX = "test:"

#: The family this catalogue's EVAP tests (``evap_smoke``, ``esim_vacuum_test_a``,
#: ``purge_vent_actuation``) share with the bench's own fuel-window blocker --
#: shown as a caution on these specific tests, not a generic banner on every
#: test.
_EVAP_MONITOR_TEST_IDS = ("evap_smoke", "esim_vacuum_test_a", "purge_vent_actuation")

RESULT_COUNT_KEYS = ("pass", "fail", "inconclusive", "not_possible", "not_done")


def step_id(test_id: str) -> str:
    return f"{_STEP_PREFIX}{test_id}"


def test_id_from_step(step: str) -> Optional[str]:
    """The test id a ``"test:<id>"`` step id names, or ``None`` if ``step``
    is not one of this feature's step ids."""
    if not step.startswith(_STEP_PREFIX):
        return None
    return step[len(_STEP_PREFIX):]


def _cached_dossier(vin: str) -> dict[str, Any]:
    mtime = mes_bridge.newest_mtime(vin)
    return cache.get_or_build(("workup", vin, mtime), lambda: mes_bridge.workup(vin=vin))


def _open_codes(vin: str, dossier: dict[str, Any]) -> list[str]:
    try:
        return mes_bridge.open_codes_for(dossier)
    except Exception:  # noqa: BLE001 -- relevance ranking is best-effort
        return []


def _open_hypotheses(vin: str) -> list[dict[str, Any]]:
    if jobs_mod is None:
        return []
    try:
        job = jobs_mod.current(vin)
    except Exception:  # noqa: BLE001
        return []
    if job is None:
        return []
    return [h for h in job.get("hypotheses", [])
           if h.get("status") == "open" and not h.get("deleted")]


def open_hypotheses_for_form(vin: str) -> list[dict[str, Any]]:
    """``{id, text, system}`` for every open hypothesis on this VIN's
    current job -- the select list the result form offers."""
    return [{"id": h["id"], "text": h.get("text") or "", "system": h.get("system") or ""}
           for h in _open_hypotheses(vin)]


def _fuel_gate(vin: str) -> dict[str, Any]:
    if bench_bridge is None:
        return {}
    try:
        return bench_bridge.build_bench(vin).get("fuel_gate") or {}
    except Exception:  # noqa: BLE001 -- blocker awareness must never 500 the page
        return {}


def _result_entry(vin: str, test_id: str) -> dict[str, Any]:
    entry = checklist_store.get(vin).get(step_id(test_id)) or {}
    result = entry.get("result")
    return {
        "result": result or "not_done",
        "value": entry.get("value"),
        "unit": entry.get("unit") or "",
        "reason": entry.get("reason") or "",
        "hypothesis_id": entry.get("hypothesis_id"),
        "when": entry.get("done_at"),
        "by": entry.get("done_by") or "",
        "media_ids": entry.get("media_ids") or [],
    }


def _base_code(code: str) -> str:
    code = (code or "").strip().upper()
    return code[:5] if len(code) >= 5 else code


def _why_for(t: dict[str, Any], open_codes: list[str],
            open_hyps: list[dict[str, Any]]) -> list[str]:
    why: list[str] = []
    bases = [_base_code(c) for c in open_codes if c]
    for rel in t["related_codes"]:
        rel_u = rel.strip().upper()
        matched = sorted({c for c, b in zip(open_codes, bases) if b.startswith(rel_u)})
        if matched:
            why.append(f"open code {', '.join(matched)}")
    for h in open_hyps:
        if (h.get("system") or "").strip().lower() in t["systems"]:
            why.append(f"open hypothesis: {h.get('text') or h['id']}")
    return why


def build_tests_view(vin: str) -> dict[str, Any]:
    """Everything ``tests.html`` needs: the full catalogue, each test's
    latest result, relevance ranking, and category/summary counts."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")

    dossier = _cached_dossier(vin)
    open_codes = _open_codes(vin, dossier)
    open_hyps = _open_hypotheses(vin)
    fuel_gate = _fuel_gate(vin)
    fuel_blocked = fuel_gate.get("in_window") is False

    code_test_ids = {t["id"] for t in mechanic_tests.tests_for_codes(open_codes)}
    hyp_systems = [h.get("system") or "" for h in open_hyps if h.get("system")]
    sys_test_ids = {t["id"] for t in mechanic_tests.tests_for_systems(hyp_systems)} if hyp_systems else set()
    recommended_ids = code_test_ids | sys_test_ids

    rows: list[dict[str, Any]] = []
    counts = {k: 0 for k in RESULT_COUNT_KEYS}
    for t in mechanic_tests.all_tests():
        rid = t["id"]
        latest = _result_entry(vin, rid)
        counts[latest["result"]] = counts.get(latest["result"], 0) + 1
        blocker = None
        if fuel_blocked and rid in _EVAP_MONITOR_TEST_IDS:
            blocker = {
                "reason": "fuel out of window",
                "window": fuel_gate.get("window"),
                "level": fuel_gate.get("level"),
                "direction": fuel_gate.get("direction"),
            }
        rows.append({
            **t,
            "step_id": step_id(rid),
            "latest_result": latest,
            "recommended": rid in recommended_ids,
            "why": _why_for(t, open_codes, open_hyps) if rid in recommended_ids else [],
            "blocker": blocker,
        })

    rows.sort(key=lambda r: (0 if r["recommended"] else 1, r["category"], r["name"]))
    categories = sorted({t["category"] for t in mechanic_tests.all_tests()})

    return {
        "vin": vin,
        "tests": rows,
        "categories": categories,
        "counts": counts,
        "total": len(rows),
        "open_codes": open_codes,
        "open_hypotheses": open_hypotheses_for_form(vin),
        "fuel_gate": fuel_gate,
    }


def record_result(vin: str, test_id: str, result: Optional[str], *, reason: str = "",
                  value: Optional[float] = None, unit: str = "",
                  hypothesis_id: Optional[str] = None, supports: str = "for",
                  by: str = "") -> dict[str, Any]:
    """Store one test's result and, when it names a hypothesis and the
    result is pass/fail, auto-attach it as evidence -- the same contract
    ``cuore.api.checklists``'s ``/result`` route already uses
    (:func:`cuore.services.jobs_bridge.add_test_evidence`), reused here
    rather than duplicated. ``supports`` is "for"/"against", exactly as
    that route's own field -- the caller (the result form) decides which
    side of the hypothesis this result counts toward; a plain pass/fail is
    not itself for/against any particular hypothesis without the tech
    saying so."""
    if mechanic_tests.test(test_id) is None:
        raise BadRequest(f"unknown test id {test_id!r}")
    if result is not None and result not in mechanic_tests.POSTABLE_RESULTS:
        raise BadRequest("result must be one of: "
                         + ", ".join(mechanic_tests.POSTABLE_RESULTS) + ", or null")
    if supports not in ("for", "against"):
        raise BadRequest("supports must be 'for' or 'against'")
    sid = step_id(test_id)
    entry = checklist_store.set_result(vin, sid, result, reason=reason, value=value,
                                       unit=unit, hypothesis_id=hypothesis_id, by=by)
    if hypothesis_id and result in ("pass", "fail"):
        t = mechanic_tests.test(test_id)
        label = f"{t['name']}: {result}"
        if value is not None:
            label += f" {value:g}{unit}"
        try:
            from . import jobs_bridge
            jobs_bridge.add_test_evidence(vin, hypothesis_id, sid, label, result,
                                          supports=supports, by=by)
        except Exception:  # noqa: BLE001 -- the result must still save
            pass
    return {"vin": vin, "test_id": test_id, "step_id": sid, **entry}


__all__ = ["build_tests_view", "record_result", "step_id", "test_id_from_step",
          "open_hypotheses_for_form", "RESULT_COUNT_KEYS"]
