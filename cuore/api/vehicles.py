"""Per-vehicle diagnostics: the dossier and everything it points at.

These endpoints are the HTTP face of the tools in ``mes-log-mcp/server.py``.
Payload shapes come from the library unchanged, so an answer here and an answer
there are the same answer.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..models import VerdictRequest
from ..services import cache, mes_bridge
from .deps import require_token

router = APIRouter(tags=["vehicles"], dependencies=[Depends(require_token)])


@router.get("/vehicles", summary="Every vehicle in the corpus")
def vehicles(real_only: bool = Query(
        default=False,
        description="Keep only vehicles with a resolvable VIN and at least "
                    "one non-simulated log.")) -> dict[str, Any]:
    found = mes_bridge.vehicles(real_only=real_only)
    return {"count": len(found), "real_only": real_only, "vehicles": found}


@router.get("/vehicle/{vin}", summary="The pre-work dossier")
def workup(vin: str) -> dict[str, Any]:
    """Everything the logs know about one vehicle, in one call.

    Cached on the newest mtime across this vehicle's logs: ``workup.build``
    re-parses every FES log for the VIN to assemble "already attempted", which
    is the one analysis that escapes the catalog's own per-file cache.
    """
    return cache.get_or_build(
        ("workup", vin, mes_bridge.newest_mtime(vin)),
        lambda: mes_bridge.workup(vin=vin),
    )


@router.get("/vehicle/{vin}/report", summary="Identity and chronic faults")
def report(vin: str) -> dict[str, Any]:
    return mes_bridge.vehicle_report(vin=vin)


@router.get("/vehicle/{vin}/dtcs", summary="Every DTC with its full history")
def dtcs(vin: str, since: str = "",
         include_simulation: bool = Query(
             default=False,
             description="Include MES practice logs. Off by default -- most "
                         "of the FES corpus is simulated and mixing it into a "
                         "fault history is actively misleading.")
         ) -> dict[str, Any]:
    return mes_bridge.extract_dtcs(vin=vin, since=since,
                                   include_simulation=include_simulation)


@router.get("/vehicle/{vin}/dtc/{code}", summary="One code's complete life")
def dtc_detail(vin: str, code: str) -> dict[str, Any]:
    return mes_bridge.dtc_history(code, vin=vin)


@router.get("/vehicle/{vin}/freeze", summary="Freeze frames")
def freeze(vin: str, code: str = "", file: str = "") -> dict[str, Any]:
    """The ~25 parameters captured when a code set.

    Read this *before* clearing anything -- a clear destroys it, and it is the
    only evidence separating a cold-start fault from a highway one.
    """
    return mes_bridge.freeze_frames(code=code, name=file, vin=vin)


@router.get("/vehicle/{vin}/actuators", summary="What has already been tried")
def actuators(vin: str, operation: str = "") -> dict[str, Any]:
    return mes_bridge.actuator_history(vin=vin, operation=operation)


@router.get("/vehicle/{vin}/tree", summary="Fault-tree isolation sequences")
def tree(vin: str, codes: str = Query(
        default="",
        description="Codes to route on. Empty routes on the dossier's own "
                    "open and chronic codes.")) -> dict[str, Any]:
    if not codes.strip():
        dossier = cache.get_or_build(
            ("workup", vin, mes_bridge.newest_mtime(vin)),
            lambda: mes_bridge.workup(vin=vin))
        codes = " ".join(mes_bridge.open_codes_for(dossier))
    return mes_bridge.fault_tree(codes, vin=vin)


@router.get("/vehicle/{vin}/session", summary="One FES engineering session")
def session(vin: str, file: str = "") -> dict[str, Any]:
    return mes_bridge.analyze_session(name=file, vin=vin)


@router.get("/vehicle/{vin}/scan", summary="One all-systems SCAN")
def scan(vin: str, file: str = "") -> dict[str, Any]:
    return mes_bridge.analyze_scan(name=file, vin=vin)


@router.get("/vehicle/{vin}/parameters", summary="Live parameters in a session")
def parameters(vin: str, file: str = "") -> dict[str, Any]:
    return mes_bridge.list_parameters(name=file, vin=vin)


@router.get("/vehicle/{vin}/parameter/{parameter}", summary="One parameter series")
def parameter(vin: str, parameter: str, file: str = "") -> dict[str, Any]:
    return mes_bridge.parameter_series(parameter, name=file, vin=vin)


@router.get("/vehicles/{vin}/live-vs-log", summary="Live UDS reads vs the newest MES log")
def live_vs_log(vin: str, module: str = Query(
        default="", description="Restrict to one module (MES abbreviation, "
                                "ECU name, or cuore's short code). Empty "
                                "reports every module either side has seen.")
        ) -> dict[str, Any]:
    """One row per code: what the newest log says vs what the car just said.

    Read-only, writes nothing -- see ``mes.compare.live_vs_log`` for the join
    and the six-way classification (live_and_logged, logged_not_live,
    live_not_logged, stale_both, no_live_read, no_log).
    """
    return mes_bridge.live_vs_log(vin, module=module)


@router.post("/vehicle/{vin}/verdict", summary="The evidence gate")
def verdict(vin: str, body: VerdictRequest) -> dict[str, Any]:
    """Gate a proposed diagnosis against four criteria.

    Writes nothing, anywhere -- not to the car, not to the corpus. It reads
    the vehicle's history and refuses CONFIRMED unless the fault is
    demonstrated, a mechanism is stated, a corpus-verified measurement
    implicates the part, and disconfirmation was attempted.
    """
    measurements = [m.model_dump(exclude_none=True) for m in body.measurements]
    return mes_bridge.assess_verdict(
        vin=vin,
        codes=body.codes,
        component=body.component,
        mechanism=body.mechanism,
        measurements=json.dumps(measurements) if measurements else "",
        disconfirming_test=body.disconfirming_test,
    )
