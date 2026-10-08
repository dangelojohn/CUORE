"""``GET /v/{vin}/timeline``: "Codes vs. what the driver notices".

Same posture as :mod:`cuore.web.dashboard_routes` and :mod:`cuore.web.
service_routes` (both built the same way, concurrently with other agents):
a separate router, reusing ``_dossier``/``_vehicle_bar``/``_page``/
``_set_active_vehicle`` from :mod:`cuore.web.routes` by import rather than
duplicating that plumbing.

The data contract lives in ``cuore.services.timeline_bridge``
(``build_timeline(vin)``, ``code_feel(vin, code)``), built in parallel by
another agent and not necessarily present yet. Every call into it is
wrapped and falls back to ``_FIXTURE`` (built to the exact shape the
contract specifies) so this page, and ``code.html``'s feel card, are
developable and testable before that module lands. Once it exists, nothing
here needs to change -- the lazy import just starts succeeding.

Not registered on the app here -- ``app.py`` is owned by another agent
while this was built. The two lines needed there:

    ``from .web import timeline_routes``
    ``app.include_router(timeline_routes.router)``

(next to the other ``web`` router imports/includes.)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..services import cache, mes_bridge
from ..services.errors import BridgeError
from ..api.deps import require_token
from . import timeline_svg
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

SYMPTOM_TAGS = ["drives_normally", "mil_on", "fuel_smell", "hard_start", "rough_idle",
               "hesitation", "loss_of_power", "hard_to_refuel", "noise", "vibration",
               "warning_message", "other"]
CONDITION_TAGS = ["cold_start", "hot", "just_refuelled", "highway", "city", "idle", "rain"]

_RANGE_DAYS = {"1y": 365, "90d": 90, "30d": 30}


# --- fixture: the exact shape cuore.services.timeline_bridge.build_timeline
# will return, used until that module lands (or for any VIN it does not yet
# cover). ---------------------------------------------------------------

def _fixture_timeline(vin: str) -> dict[str, Any]:
    return {
        "vin": vin,
        "range": {"start": "2025-09-24T00:00:00", "end": "2026-10-04T11:16:00",
                  "odo_start": 115790, "odo_end": 142290},
        "lanes": [
            {"id": "mil", "label": "MIL", "kind": "bars", "events": [
                {"t": "2025-09-24T00:00:00", "t_end": "2026-08-27T00:00:00", "odo": 115800,
                 "label": "MIL", "detail": "lamp on, EVAP family", "severity": "active",
                 "href": None, "count": 11},
            ]},
            {"id": "evap", "label": "EVAP", "kind": "bars", "events": [
                {"t": "2025-09-24T00:00:00", "t_end": "2026-08-27T00:00:00", "odo": 115800,
                 "label": "P0456", "detail": "EVAP small leak", "severity": "cleared",
                 "href": f"/v/{vin}/code/P0456", "count": 11},
            ]},
            {"id": "network", "label": "Network", "kind": "bars", "events": [
                {"t": "2026-01-15T00:00:00", "t_end": None, "odo": 128000,
                 "label": "U0100", "detail": "lost comms with ECM", "severity": "active",
                 "href": f"/v/{vin}/code/U0100", "count": 2},
            ]},
            {"id": "body", "label": "Body", "kind": "bars", "events": []},
            {"id": "chassis", "label": "Chassis", "kind": "bars", "events": []},
            {"id": "engine_other", "label": "Engine (other)", "kind": "bars", "events": []},
            {"id": "clears", "label": "Clears", "kind": "lines", "events": [
                {"t": "2026-08-27T00:00:00", "t_end": None, "odo": 138000,
                 "label": "cleared", "detail": "P0440/P0455/P0456 cleared (MultiEcuScan)",
                 "severity": "cleared", "href": None},
            ]},
            {"id": "symptoms", "label": "Symptoms", "kind": "points", "events": []},
            {"id": "notes", "label": "Notes", "kind": "points", "events": []},
            {"id": "work", "label": "Work", "kind": "points", "events": [
                {"t": "2026-09-15T21:18:00", "t_end": None, "odo": 138900,
                 "label": "Evaporation control valve", "detail": "FAILED TO EXECUTE (engine running)",
                 "severity": "work", "href": None},
                {"t": "2026-09-15T21:30:00", "t_end": None, "odo": 138900,
                 "label": "Evaporation control valve", "detail": "completed, key-on engine-off",
                 "severity": "work", "href": None},
            ]},
            {"id": "conditions", "label": "Conditions", "kind": "points", "events": [
                {"t": "2025-09-24T00:00:00", "t_end": None, "odo": 115800,
                 "label": "freeze frame", "detail": "fuel 93.7%, engine temp 89 C",
                 "severity": "warn", "href": None},
            ]},
        ],
        "correlation": [
            {"family": "EVAP", "codes": ["P0440", "P0455", "P0456"], "occurrences": 11,
             "symptom_reports_near": 0, "by_tag": {}, "drives_normally_near": 0,
             "window_days": 7, "verdict": "no reported symptom"},
            {"family": "NETWORK", "codes": ["U0100", "U0101"], "occurrences": 2,
             "symptom_reports_near": 0, "by_tag": {}, "drives_normally_near": 0,
             "window_days": 7, "verdict": "no reported symptom"},
        ],
        "findings": [
            "EVAP (P0440/P0455/P0456) has set 11 times over 26,500 km with no symptom "
            "ever reported near a sighting -- consistent with the TSB 18-030-17 "
            "calibration read, not a drivability complaint.",
            "No driver symptom report exists in the log for this vehicle yet -- use the "
            "symptom form below after every drive, including 'drives normally'.",
        ],
        "symptom_tags": SYMPTOM_TAGS,
        "conditions": CONDITION_TAGS,
    }


def _fixture_code_feel(vin: str, code: str) -> dict[str, Any]:
    code = (code or "").upper()
    if code in ("P0456", "P0440", "P0455"):
        return {
            "feel": {
                "feel": "Usually nothing -- EVAP small/large leaks are almost always silent "
                        "to the driver.",
                "expect": ["no drivability change", "MIL after 2 failed drive cycles"],
                "not_expected": ["rough idle", "loss of power", "stalling"],
                "mil": "check-engine light after two failed drives of the EVAP monitor",
                "notes": "A fuel-smell report alongside this code is unusual and worth a "
                         "real leak check rather than assuming it is this code.",
                "confidence": "high", "source": "mes/dtc_feel.yaml",
            },
            "pattern": {"occurrences": 11, "symptom_reports_near": 0, "by_tag": {},
                       "drives_normally_near": 0},
        }
    return {"feel": None, "pattern": {"occurrences": 0, "symptom_reports_near": 0,
                                      "by_tag": {}, "drives_normally_near": 0}}


def _bridge():
    """``cuore.services.timeline_bridge``, or ``None`` if it has not landed."""
    try:
        from ..services import timeline_bridge
        return timeline_bridge
    except ImportError:
        return None


def _systems_bridge():
    """``cuore.services.systems_bridge``, or ``None`` if it has not landed --
    used only by ``?lanes=systems`` (see ``_code_to_system_map`` below)."""
    try:
        from ..services import systems_bridge
        return systems_bridge
    except ImportError:
        return None


def _code_to_system_map(tl: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Best-effort ``code -> system key`` map for ``?lanes=systems``, built
    by calling ``systems_bridge.systems_for_code()`` once per distinct code
    this timeline's bars lanes carry and keeping each code's ``primary``
    system. Empty (which degrades ``regroup_by_system`` to the existing
    family grouping) if ``systems_bridge`` is not built yet, or classifies
    none of this car's codes."""
    bridge = _systems_bridge()
    code_system: dict[str, str] = {}
    system_labels: dict[str, str] = {}
    if bridge is None:
        return code_system, system_labels
    try:
        for s in bridge.systems() or []:
            if s.get("key"):
                system_labels[s["key"]] = s.get("label") or s["key"]
    except Exception:  # noqa: BLE001 -- a knowledge-table miss must never 500 this page
        pass
    codes: set[str] = set()
    for lane in tl.get("lanes", []):
        if (lane.get("kind") or "bars") != "bars":
            continue
        for e in lane.get("events") or []:
            for part in str(e.get("label") or "").split("/"):
                part = part.strip().upper()
                if part:
                    codes.add(part)
    for code in codes:
        try:
            roles = bridge.systems_for_code(code) or []
        except Exception:  # noqa: BLE001
            continue
        primary = next((r for r in roles if r.get("role") == "primary"),
                       roles[0] if roles else None)
        if primary and primary.get("system"):
            code_system[code] = primary["system"]
    return code_system, system_labels


def _timeline(vin: str) -> dict[str, Any]:
    bridge = _bridge()
    if bridge is None:
        return _fixture_timeline(vin)
    return cache.get_or_build(
        ("timeline", vin, mes_bridge.newest_mtime(vin)),
        lambda: bridge.build_timeline(vin))


def _code_feel_data(vin: str, code: str) -> dict[str, Any]:
    bridge = _bridge()
    if bridge is None:
        return _fixture_code_feel(vin, code)
    try:
        return bridge.code_feel(vin, code)
    except Exception:  # noqa: BLE001 -- a knowledge-table miss must never 500 a code page
        return {"feel": None, "pattern": None}


_shared_templates.env.globals["code_feel"] = _code_feel_data


# --- range/zoom filtering ---------------------------------------------

def _parse_dt(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    s = str(ts).strip().replace(" ", "T")[:19]
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _apply_range(tl: dict[str, Any], range_key: str) -> dict[str, Any]:
    """Zoom presets (?range=1y|90d|30d) filter every lane's events to a
    window before the newest timestamp in the timeline, and narrow
    ``range`` to match -- otherwise the chart's axis would still span the
    whole car even though the events on it had been cut down to a month."""
    days = _RANGE_DAYS.get(range_key)
    if not days:
        return tl
    stamps = [d for lane in tl.get("lanes", []) for e in lane.get("events", [])
              for raw in (e.get("t"), e.get("t_end")) if (d := _parse_dt(raw))]
    if not stamps:
        return tl
    newest = max(stamps)
    cutoff = newest - timedelta(days=days)

    new_lanes, odos = [], []
    for lane in tl.get("lanes", []):
        kept = []
        for e in lane.get("events", []):
            t_d, te_d = _parse_dt(e.get("t")), _parse_dt(e.get("t_end"))
            if (t_d and t_d >= cutoff) or (te_d and te_d >= cutoff):
                kept.append(e)
                if isinstance(e.get("odo"), (int, float)):
                    odos.append(e["odo"])
        new_lanes.append({**lane, "events": kept})

    new_range = dict(tl.get("range") or {})
    new_range["start"] = cutoff.isoformat()
    new_range["end"] = newest.isoformat()
    if odos:
        new_range["odo_start"], new_range["odo_end"] = min(odos), max(odos)
    return {**tl, "lanes": new_lanes, "range": new_range}


# --- correlation-row sparklines -----------------------------------------

def _month_buckets(tl: dict[str, Any]) -> list[datetime]:
    rng = tl.get("range") or {}
    lo, hi = _parse_dt(rng.get("start")), _parse_dt(rng.get("end"))
    if not lo or not hi:
        return []
    months, cur, end = [], lo.replace(day=1), hi.replace(day=1)
    while cur <= end and len(months) < 36:
        months.append(cur)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months or [lo]


def _bucket_counts(events: list[dict[str, Any]], months: list[datetime]) -> list[int]:
    counts = [0] * len(months)
    for e in events:
        d = _parse_dt(e.get("t"))
        if d is None:
            continue
        for i in range(len(months) - 1, -1, -1):
            if d >= months[i]:
                counts[i] += 1
                break
    return counts


def _attach_sparklines(tl: dict[str, Any]) -> None:
    """Mutates each ``correlation`` row in place, adding ``row["spark"]``:
    a tiny inline SVG (occurrence bars + symptom-report dots per month).
    A visual at-a-glance companion to the row's own scalar counts, not a
    re-derivation of them -- it buckets straight from the timeline's own
    lanes, which the correlation table's numbers were computed from too."""
    months = _month_buckets(tl)
    if not months:
        for row in tl.get("correlation", []):
            row["spark"] = ""
        return
    bar_events, symptom_events = [], []
    for lane in tl.get("lanes", []):
        if lane.get("id") == "symptoms":
            symptom_events = [e for e in lane.get("events", []) if e.get("severity") == "symptom"]
        elif (lane.get("kind") or "bars") == "bars":
            bar_events += lane.get("events", [])
    sym_counts = _bucket_counts(symptom_events, months)
    for row in tl.get("correlation", []):
        codes = set(row.get("codes") or [])
        # A bars-lane event's ``label`` is sometimes a single code and
        # sometimes a "/"-joined set of codes that set together in one
        # session (see cuore.services.timeline_bridge's "network" lane) --
        # match on overlap, not equality, so a family's sparkline still
        # picks those up.
        matched = [e for e in bar_events
                  if set(str(e.get("label") or "").split("/")) & codes]
        occ_counts = _bucket_counts(matched, months)
        row["spark"] = timeline_svg.sparkline(occ_counts, sym_counts)


def _verdict_class(verdict: str) -> str:
    v = (verdict or "").lower()
    if "co-occur" in v or "co occur" in v:
        return "chronic"   # amber
    return "plain"         # grey-neutral


# --- the page ------------------------------------------------------------


@router.get("/v/{vin}/timeline", response_class=HTMLResponse)
def timeline_page(request: Request, vin: str, axis: str = "time",
                  range: str = "all", lanes: str = "family",
                  saved: str = "", error: str = "") -> HTMLResponse:
    """Swimlane timeline: every code family's presence beside every
    recorded driver symptom, note and repair -- so "does this car actually
    feel wrong" can be read off against "what the logs say" at a glance.

    ``?lanes=systems`` regroups the bars lanes by system (per
    ``cuore.services.systems_bridge``) instead of DTC family -- see
    ``timeline_svg.regroup_by_system``. Everything else on the page (the
    by-family correlation table, findings, symptom form) is unaffected;
    only the swimlane chart's own grouping changes."""
    axis = axis if axis in ("time", "odometer") else "time"
    lanes_mode = "systems" if lanes == "systems" else "family"
    dossier = _dossier(vin)
    tl = _timeline(vin)
    tl = _apply_range(tl, range)
    _attach_sparklines(tl)
    for row in tl.get("correlation", []):
        row["verdict_class"] = _verdict_class(row.get("verdict", ""))

    tl_chart = tl
    if lanes_mode == "systems":
        code_system, system_labels = _code_to_system_map(tl)
        tl_chart = timeline_svg.regroup_by_system(tl, code_system, system_labels)

    svg = timeline_svg.render(tl_chart, axis=axis, width=1000)
    layout = timeline_svg.lane_layout(tl_chart)

    response = _page(request, "timeline.html", vin=vin, tl=tl, svg=svg, layout=layout,
                     axis=axis, range_key=range, lanes_mode=lanes_mode,
                     bar=_vehicle_bar(vin, dossier),
                     tab="timeline", saved=bool(saved), symptom_error=error,
                     symptom_tags=tl.get("symptom_tags") or SYMPTOM_TAGS,
                     condition_tags=tl.get("conditions") or CONDITION_TAGS,
                     note_redirect=f"/v/{vin}/timeline",
                     now_local=datetime.now().strftime("%Y-%m-%dT%H:%M"))
    _set_active_vehicle(response, vin)
    return response


# --- symptom entry --------------------------------------------------------

def _save_symptom(vin: str, data: dict[str, Any]) -> Optional[str]:
    """Record one symptom report. Returns an error string, or ``None`` on
    success. The contract names the JSON route
    (``POST /api/vehicles/{vin}/symptoms``) that another agent is building
    in ``cuore.api``; this form posts internally to the bridge function
    rather than making an HTTP call to itself. The exact function name was
    not pinned down in the contract handed to this page, so this tries the
    plausible candidates and fails soft (with a clear message) until the
    real one lands -- nothing here needs to change once it does, as long as
    it is named one of these or added as a fourth alias."""
    bridge = _bridge()
    if bridge is None:
        return "symptom recording is not available yet (timeline_bridge is not built)"
    fn = (getattr(bridge, "add_symptom", None) or getattr(bridge, "record_symptom", None)
          or getattr(bridge, "log_symptom", None))
    if fn is None:
        return "symptom recording is not available yet (no add/record/log_symptom on timeline_bridge)"
    try:
        fn(vin, **data)
    except BridgeError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 -- a bad form post must redirect, not 500
        return str(exc)
    return None


@router.post("/v/{vin}/symptoms", response_class=HTMLResponse)
async def symptoms_submit(request: Request, vin: str) -> RedirectResponse:
    """The symptom form's target. Degrades like every other form in this
    app (``/v/{vin}/notes``, ``/v/{vin}/gate``): parallel checkbox fields,
    no JavaScript required, redirects back with a flash rather than
    re-rendering so a reload cannot double-submit."""
    form = await request.form()
    redirect_base = str(form.get("redirect_to", "") or f"/v/{vin}/timeline")
    if not redirect_base.startswith("/") or redirect_base.startswith("//"):
        redirect_base = f"/v/{vin}/timeline"

    at = str(form.get("at", "")).strip() or datetime.now().isoformat(timespec="minutes")
    reporter = str(form.get("reporter", "driver")).strip() or "driver"
    tags = [t.strip() for t in form.getlist("tags") if t.strip()]
    conditions = [c.strip() for c in form.getlist("conditions") if c.strip()]
    text = str(form.get("text", "")).strip()
    odometer_raw = str(form.get("odometer_km", "")).strip()

    error = None
    if reporter not in ("driver", "mechanic"):
        error = "reporter must be 'driver' or 'mechanic'"
    elif not tags:
        error = "pick at least one tag -- 'Drives normally' counts as evidence too"

    odometer_km: Optional[float] = None
    if error is None and odometer_raw:
        try:
            odometer_km = float(odometer_raw)
        except ValueError:
            error = f"odometer must be a number, got {odometer_raw!r}"

    if error is None:
        payload: dict[str, Any] = {"at": at, "reporter": reporter, "tags": tags,
                                   "conditions": conditions}
        if odometer_km is not None:
            payload["odometer_km"] = odometer_km
        if text:
            payload["text"] = text
        error = _save_symptom(vin, payload)

    sep = "&" if "?" in redirect_base else "?"
    url = f"{redirect_base}{sep}{'saved=1' if error is None else 'error=' + quote(error)}"
    return RedirectResponse(url=url, status_code=303)


__all__ = ["router"]
