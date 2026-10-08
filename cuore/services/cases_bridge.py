"""The only module in CUORE that imports :mod:`mes.cases`.

Thin pass-through, same posture as ``systems_bridge.py``/``feedback_bridge.py``:
every route reaches case memory only through this file. Nothing here invents
a result -- ``match``/``prefill`` return exactly what ``mes.cases`` built from
real job/shop/tool-usage/service/symptom records, worded so a prior car's fix
is never presented as this car's answer.
"""

from __future__ import annotations

from typing import Any

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from .errors import BadRequest

from mes import cases as cases_mod  # noqa: E402


def _require_vin(vin: str) -> str:
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    return vin


def match(vin: str, codes: list[str]) -> dict[str, Any]:
    """Prior cases for this VIN's model, ranked by code/family overlap and
    outcome -- see ``mes.cases.match`` for the ranking and wording rules."""
    vin = _require_vin(vin)
    rows = cases_mod.match(vin, codes or [])
    return {"vin": vin, "codes": [c.strip().upper() for c in (codes or []) if c.strip()],
           "matches": rows, "count": len(rows)}


def prefill(vin: str, codes: list[str]) -> dict[str, Any]:
    """A suggested starting point for a new job on this VIN, built from the
    best-matching prior case -- see ``mes.cases.prefill``."""
    vin = _require_vin(vin)
    return cases_mod.prefill(vin, codes or [])


def record_case(vin: str, job_id: str) -> dict[str, Any]:
    """Build and persist a Case from one job. Exposed here so a caller that
    *can* edit ``mes/jobs.py``/``cuore/services/jobs_bridge.py`` (this task's
    scope excludes both) can wire this in on close; until then, nothing
    calls it automatically."""
    vin = _require_vin(vin)
    job_id = (job_id or "").strip()
    if not job_id:
        raise BadRequest("a job_id is required")
    try:
        return cases_mod.record_case(vin, job_id)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


__all__ = ["match", "prefill", "record_case"]
