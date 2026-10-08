"""Assembles the one-car-at-a-time shop pages: ``/start`` and the release
gate.

Same posture as ``cuore.services.jobs_bridge``: this is the only module
besides ``jobs_bridge`` that imports :mod:`mes.shop` directly. Writing
(intake, step timing, release) is thin pass-through to :mod:`mes.shop`,
which does the validation; reading enriches the raw visit with the
vehicle's name (from the corpus, via ``mes_bridge``) and the dossier's
verdict (via ``dossier_bridge``), so the release gate can show the evidence
behind "verified" instead of trusting a mechanic's checkbox.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import dossier_bridge, mes_bridge
from .errors import BadRequest, NotFound

from mes import shop as shop_mod  # noqa: E402

try:
    from . import jobs_bridge
except Exception:  # noqa: BLE001 -- the release page must still render
    jobs_bridge = None

try:
    from mes import tool_usage as tool_usage_mod
except Exception:  # noqa: BLE001 -- the tools-away section must still render
    tool_usage_mod = None


# --- vehicle name lookup, for intake prefill and board display -------------

#: WMI (VIN positions 1-4) -> make, for the handful of makes this shop
#: actually sees. Decoding stops at "make" -- the model is deliberately
#: reported as "UNKNOWN" rather than guessed from trim/engine codes nobody
#: has mapped yet.
_WMI_MAKES: dict[str, str] = {
    "ZASF": "Alfa Romeo",
    "ZN6": "Maserati",
    "ZN7": "Maserati",
}


def vehicle_choices() -> list[dict[str, Any]]:
    """VIN + display name for every real vehicle in the corpus, for the
    intake form's VIN prefill."""
    try:
        found = mes_bridge.vehicles(real_only=True)
    except Exception:  # noqa: BLE001
        return []
    return [{"vin": v.get("vin", ""),
            "name": (v.get("names") or [""])[0] or v.get("vin", "")}
           for v in found if v.get("vin")]


def _vehicle_name(vin: str) -> str:
    """The corpus's own name for this VIN, from the vehicle list -- empty
    when this VIN is not (yet) one of the corpus's known vehicles."""
    for v in vehicle_choices():
        if v["vin"] == vin:
            return v["name"]
    return ""


def _decode_wmi(vin: str) -> str:
    """Make only, from the VIN's WMI -- longest-prefix match so a 4-char
    WMI (``ZASF``) is tried before a 3-char one (``ZN6``/``ZN7``) that could
    otherwise shadow it. ``""`` when the WMI is not one this shop knows."""
    vin = (vin or "").strip().upper()
    for prefix in sorted(_WMI_MAKES, key=len, reverse=True):
        if vin.startswith(prefix):
            return _WMI_MAKES[prefix]
    return ""


def resolve_vehicle_name(vin: str) -> str:
    """Best name available for this VIN at the moment a visit/job is
    created, so a car with no name on file yet is never shown as
    "(unnamed vehicle)": the corpus's own vehicle list, then the dossier
    identity's own ``vehicle`` field (:func:`mes_bridge.workup`), then a WMI
    decode (make only, model "UNKNOWN"), then -- if nothing resolves at all
    -- the VIN itself, since a known VIN must never render as unnamed."""
    vin = (vin or "").strip()
    if not vin:
        return ""
    name = _vehicle_name(vin)
    if name:
        return name
    try:
        identity = mes_bridge.workup(vin=vin).get("identity") or {}
    except Exception:  # noqa: BLE001
        identity = {}
    if identity.get("vehicle"):
        return identity["vehicle"]
    make = _decode_wmi(vin)
    if make:
        return f"{make} UNKNOWN"
    return vin


# --- write surface, thin pass-through to mes.shop ---------------------------


def intake(vin: str, complaint: str = "", *, technician: str = "") -> dict[str, Any]:
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    try:
        return shop_mod.intake(vin, complaint, technician=technician,
                               vehicle=resolve_vehicle_name(vin))
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def start_step(visit_id: str, step: int) -> dict[str, Any]:
    try:
        return shop_mod.start_step(visit_id, step)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def end_step(visit_id: str, step: int) -> dict[str, Any]:
    try:
        return shop_mod.end_step(visit_id, step)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def release(visit_id: str, checks: dict[str, Any], *,
           reason: Optional[str] = None) -> dict[str, Any]:
    """Release the car. ``verified`` is never taken from ``checks`` -- it is
    looked up fresh from this visit's dossier verdict here, so a mechanic
    cannot tick a box into verification; only a ``VERIFIED_CLEAN`` dossier
    does that. Never blocks: this just records the decision."""
    visit = get_visit(visit_id)
    dossier_verified = _dossier_verdict(visit["vin"]).get("state") == "VERIFIED_CLEAN"
    try:
        return shop_mod.release(visit_id, checks, dossier_verified=dossier_verified,
                                reason=reason)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def get_visit(visit_id: str) -> dict[str, Any]:
    visit = shop_mod.get(visit_id)
    if visit is None:
        raise NotFound(f"no visit {visit_id!r}")
    return visit


def current_visit_for_vin(vin: str) -> Optional[dict[str, Any]]:
    """The visit a mechanic walking up to this car right now would be
    working on: the newest not-out visit, or (if every visit for this VIN
    has already gone out) the most recent one -- so ``/v/{vin}/release``
    still has something to show for a car that was already released today."""
    visit = shop_mod.current(vin)
    if visit is not None:
        return visit
    visits = shop_mod.load(vin)
    return visits[-1] if visits else None


# --- reads -------------------------------------------------------------------


def _tool_review(job_id: Optional[str]) -> Optional[dict[str, Any]]:
    """The Job's tool review, if ``jobs_bridge`` (or the job record itself)
    ever exposes one. Nothing in this corpus currently writes a tool review,
    so this returns ``None`` -- the release page shows "not reviewed" rather
    than inventing a result."""
    if not job_id or jobs_bridge is None:
        return None
    getter = getattr(jobs_bridge, "tool_review", None)
    if callable(getter):
        try:
            return getter(job_id)
        except Exception:  # noqa: BLE001
            return None
    try:
        job = jobs_bridge.get_job(job_id)
    except Exception:  # noqa: BLE001
        return None
    return job.get("tool_review") if isinstance(job, dict) else None


def tools_used_for_visit(vin: str, job_id: Optional[str]) -> list[str]:
    """Distinct tool names from this car's tools-used review
    (:mod:`mes.tool_usage`), for the release page's "Tools away" checklist.
    ``[]`` when that module is not installed yet or has nothing on file --
    the section still renders, just with nothing to tick."""
    if tool_usage_mod is None:
        return []
    try:
        rows = tool_usage_mod.load(vin=vin)
    except Exception:  # noqa: BLE001
        return []
    seen: set[str] = set()
    names: list[str] = []
    for r in rows:
        if job_id and r.get("job_id") and r.get("job_id") != job_id:
            continue
        for t in r.get("tools_used", []) or []:
            name = t.get("tool") if isinstance(t, dict) else None
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def confirm_tools_away(vin: str, job_id: Optional[str], put_away: list[dict[str, Any]],
                       restock: str, not_available: list[dict[str, Any]]) -> bool:
    """Record the mechanic's tools-away confirmation via
    ``mes.tool_usage.tools_away`` if that function exists yet -- advise,
    never block: any failure, or the function simply not existing on this
    install, must never stop the mechanic moving to the next car. Returns
    whether the confirmation was actually recorded."""
    if tool_usage_mod is None:
        return False
    fn = getattr(tool_usage_mod, "tools_away", None)
    if not callable(fn):
        return False
    try:
        fn(vin, job_id or "", put_away=put_away, restock=restock,
          not_available=not_available)
        return True
    except Exception:  # noqa: BLE001
        return False


def build_release_view(visit_id: str) -> dict[str, Any]:
    """Everything the release gate needs: the visit, its dossier verdict (so
    an UNVERIFIED car is flagged before release, not after), and whatever
    tool review the Job carries."""
    visit = get_visit(visit_id)
    return _release_view_for(visit)


def build_release_view_for_vin(vin: str) -> dict[str, Any]:
    """Same as :func:`build_release_view`, resolved from a VIN instead of a
    visit id -- what ``/v/{vin}/release`` renders."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    visit = current_visit_for_vin(vin)
    if visit is None:
        raise NotFound(f"no shop visit on record for {vin!r}")
    return _release_view_for(visit)


def _dossier_verdict(vin: str) -> dict[str, Any]:
    """This VIN's dossier verdict, or ``{}`` when it cannot be computed --
    never raises, since both the release decision and the release page must
    still work when the dossier is unavailable (then treated as not
    verified, the safer default)."""
    try:
        dossier = mes_bridge.workup(vin=vin)
    except Exception:  # noqa: BLE001
        return {}
    try:
        return dossier_bridge.build_view(vin, dossier, None).get("verdict") or {}
    except Exception:  # noqa: BLE001
        return {}


def _release_view_for(visit: dict[str, Any]) -> dict[str, Any]:
    vin = visit["vin"]
    verdict = _dossier_verdict(vin)
    return {
        "visit": visit,
        "vin": vin,
        "dossier_verdict": verdict or None,
        "verified": verdict.get("state") == "VERIFIED_CLEAN",
        "tool_review": _tool_review(visit.get("job_id")),
        "tools_used": tools_used_for_visit(vin, visit.get("job_id")),
        "checks": list(shop_mod.RELEASE_CHECKS),
    }


__all__ = ["vehicle_choices", "resolve_vehicle_name", "intake", "start_step", "end_step",
          "release", "get_visit", "build_release_view",
          "build_release_view_for_vin", "current_visit_for_vin",
          "tools_used_for_visit", "confirm_tools_away"]
