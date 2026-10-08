"""The Tools page: every cuore operation, reachable from a phone.

``/api/tools/catalogue``, ``/api/tools/suggest`` and ``/api/tools/shape`` are
a separate backend effort landing in parallel (see the contract in the task
that created this file). Until that lands, this page renders a *fixture*
catalogue of the same shape -- built from the real routes already live in
``cuore/api/*`` and ``cuore/web/routes.py`` -- merged with *real* live-link
state (adapter, cable, buses, active vehicle), so the page is honest about
what is actually connected even though the tool list itself is static.
``cuore/web/static/tools.js`` tries the real ``/api/tools/*`` endpoints first
and falls back to the embedded fixture on a 404.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import __version__
from ..api.deps import require_token, settings_of
from ..live import ops as live_ops
from ..services import mes_bridge
from .routes import templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

# Must match cuore.web.routes._VIN_COOKIE -- not imported directly since that
# name is private to that module.
_VIN_COOKIE = "cuore_vin"


# --- live state, for the status strip and for enabling/disabling tools -----

def _active_vin(request: Request) -> str:
    return (request.query_params.get("vin") or
            request.cookies.get(_VIN_COOKIE, "")).strip()


def _vehicle_name(vin: str) -> str | None:
    if not vin:
        return None
    try:
        rows = mes_bridge.vehicles()
    except Exception:  # noqa: BLE001 - a bad corpus must never break this page
        rows = []
    for v in rows:
        if v.get("vin") == vin:
            names = v.get("names") or []
            return names[0] if names else None
    return None


def _state(request: Request) -> dict[str, Any]:
    vin = _active_vin(request)
    out: dict[str, Any] = {
        "active_vin": vin or None,
        "vehicle_name": _vehicle_name(vin),
        "port": None, "mes_state": None, "cable": None,
        "buses_verified": 0, "buses_total": 0, "lock_holder": None,
        "poller_active": False, "error": None,
    }
    try:
        s = live_ops.status()
        out["port"] = s.get("port")
        out["mes_state"] = (s.get("mes") or {}).get("state")
        out["cable"] = (s.get("cable") or {}).get("cable")
        buses = (s.get("cable") or {}).get("buses", [])
        out["buses_verified"] = sum(1 for b in buses if b.get("verified"))
        out["buses_total"] = len(buses)
        out["lock_holder"] = (s.get("lock") or {}).get("process")
    except Exception as exc:  # noqa: BLE001 - the strip must never 500 the page
        out["error"] = str(exc)
    try:
        out["poller_active"] = bool(live_ops.live_session_status().get("active"))
    except Exception:  # noqa: BLE001
        pass
    return out


# --- the fixture catalogue --------------------------------------------------

def _input(name: str, in_: str, label: str, type_: str = "string",
           required: bool = False, default: Any = None, source: str | None = None,
           choices: list[dict[str, str]] | None = None, help: str | None = None
           ) -> dict[str, Any]:
    return {"name": name, "in": in_, "label": label, "type": type_,
            "required": required, "default": default, "source": source,
            "choices": choices, "help": help}


def _tool(method: str, path: str, name: str, what: str, when: str, *,
          needs: tuple[str, ...] = (), risk: str = "reads car",
          inputs: list[dict[str, Any]] | None = None, run: str = "one_tap",
          result_hint: str = "", developer_only: bool = False,
          synonyms: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "id": f"{method} {path}", "method": method, "path": path,
        "name": name, "what": what, "when": when, "needs": list(needs),
        "risk": risk, "inputs": inputs or [], "run": run, "enabled": True,
        "disabled_reason": None, "result_hint": result_hint,
        "developer_only": developer_only, "synonyms": list(synonyms),
    }


MODULE_CHOICES = [{"value": c, "label": c} for c in
                   ("ECM", "TCM", "ABS", "SRS", "BCM", "EPS", "HVAC", "IC")]
BUS_CHOICES = [{"value": "can_c", "label": "CAN-C"},
               {"value": "can_ch", "label": "CAN-CH"},
               {"value": "can_ihs", "label": "CAN-IHS"}]
CABLE_CHOICES = [{"value": "none", "label": "None"},
                  {"value": "blue_a5", "label": "Blue A5"},
                  {"value": "grey_a6", "label": "Grey A6"}]

VIN_INPUT = _input("vin", "path", "Vehicle", required=True, source="active_vin",
                    help="The active vehicle (set by visiting its dossier).")


def _groups() -> list[dict[str, Any]]:
    return [
        {"id": "read", "title": "Read the car",
         "blurb": "Legislated OBD and module reads, straight off the wire.",
         "tools": [
            _tool("GET", "/api/live/status", "Adapter status",
                  "Port, MES state, declared cable and which buses are verified.",
                  "Before doing anything else on the car.",
                  synonyms=("adapter", "connection", "port")),
            _tool("GET", "/api/live/obd/dtcs", "Read stored codes",
                  "Mode 03/07/0A: stored, pending and permanent DTCs.",
                  "First thing on any car with a light on.", needs=("adapter",),
                  synonyms=("dtc", "codes", "check engine light", "mil")),
            _tool("GET", "/api/live/obd/readiness", "Readiness monitors",
                  "Which emissions monitors have completed, EVAP called out.",
                  "Before telling a customer a repair is verified.",
                  needs=("adapter",), synonyms=("monitors", "evap", "smog")),
            _tool("GET", "/api/live/obd/vin", "Read VIN from the car",
                  "Mode 09: the VIN as the car itself reports it.",
                  "To confirm you are plugged into the car you think you are.",
                  needs=("adapter",)),
            _tool("GET", "/api/live/module/{code}/dtcs", "Read one module's codes",
                  "UDS 0x19 02 on a specific module (not legislated OBD).",
                  "Chasing a code a scan tool attributed to a specific ECU.",
                  needs=("adapter", "bus"), run="form",
                  inputs=[_input("code", "path", "Module", required=True,
                                 choices=MODULE_CHOICES, help="Module abbreviation")],
                  synonyms=("module", "ecu", "uds")),
         ]},
        {"id": "check", "title": "Check a repair",
         "blurb": "Confirm a fix actually held before the car leaves.",
         "tools": [
            _tool("GET", "/api/vehicles/{vin}/live-vs-log", "Live vs. last log",
                  "Compares the car's live UDS reads against its newest MES log.",
                  "Something was just fixed and you want today's reality vs history.",
                  needs=("vin", "adapter"), run="form", inputs=[VIN_INPUT]),
            _tool("GET", "/api/live/coverage/report", "Whole-car coverage report",
                  "Merged report from a completed three-pass, three-bus scan.",
                  "After running a full coverage session, to see what it found.",
                  needs=("adapter",)),
         ]},
        {"id": "history", "title": "History and logs",
         "blurb": "What this car's MES log corpus already says. No adapter needed.",
         "tools": [
            _tool("GET", "/api/vehicle/{vin}/dtcs", "Every code, with history",
                  "Full DTC history for this VIN: chronic, returned, seen-once.",
                  "Before touching the car, read what it has already told MES.",
                  risk="reads logs", needs=("vin",), run="form", inputs=[VIN_INPUT],
                  synonyms=("dtc history", "chronic")),
            _tool("GET", "/api/vehicle/{vin}/tree", "Fault-tree isolation",
                  "Cheapest-first diagnostic steps, annotated with this car's evidence.",
                  "You have open codes and want the next cheapest test, not a guess.",
                  risk="reads logs", needs=("vin",), run="form", inputs=[VIN_INPUT]),
            _tool("GET", "/api/logs", "Log index",
                  "Every MES log on file, newest first, with provenance.",
                  "Looking for a specific session instead of one VIN's summary.",
                  risk="reads logs"),
         ]},
        {"id": "live", "title": "Live data",
         "blurb": "Streamed channels while the car is running.",
         "tools": [
            _tool("GET", "/api/live/channels", "Channel registry",
                  "Every PID/DID/computed channel and preset cuore knows.",
                  "Deciding what to put on a gauge dashboard.", needs=("adapter",)),
            _tool("GET", "/api/live/snapshot", "Latest channel values",
                  "The most recent sample of every channel in the running session.",
                  "A live session is already running and you want a quick read.",
                  needs=("adapter",)),
            _tool("POST", "/api/live/session/stop", "Stop the live session",
                  "Stops the poller and releases the adapter.",
                  "Done with gauges/recording and want the port free again.",
                  risk="holds adapter", needs=("adapter",)),
         ]},
        {"id": "service", "title": "Service",
         "blurb": "Checklist, notes and open work for this vehicle.",
         "tools": [
            _tool("GET", "/api/vehicles/{vin}/view", "Open work (dossier view)",
                  "The verdict, open-work families and checklists for this car.",
                  "Picking up a car that has been worked on before.",
                  risk="reads logs", needs=("vin",), run="form", inputs=[VIN_INPUT]),
            _tool("GET", "/api/vehicles/{vin}/checklist", "Checklist state",
                  "Which repair-checklist steps are ticked for this car.",
                  "Checking what has already been done on this job.",
                  risk="reads logs", needs=("vin",), run="form", inputs=[VIN_INPUT]),
            _tool("GET", "/api/vehicles/{vin}/notes", "Technician notes",
                  "Every note left on this vehicle.",
                  "Catching up before touching a car someone else started.",
                  risk="reads logs", needs=("vin",), run="form", inputs=[VIN_INPUT]),
         ]},
        {"id": "dealer", "title": "Learning and dealer",
         "blurb": "Learn identifiers cuore doesn't know yet by watching a dealer tool.",
         "tools": [
            _tool("GET", "/api/live/learned", "Learned identifiers",
                  "DID mappings learned from a dealer-tool capture, per VIN.",
                  "Checking what cuore has already learned about this car.",
                  needs=("adapter",)),
            _tool("POST", "/api/live/learn/capture", "Capture bus traffic",
                  "Passive capture on a bus while a dealer tool reads the car.",
                  "Running wiTECH alongside cuore to learn its identifiers.",
                  risk="holds adapter", needs=("adapter", "bus"), run="form",
                  inputs=[_input("bus", "query", "Bus", required=True,
                                 choices=BUS_CHOICES),
                          _input("seconds", "query", "Seconds", type_="number",
                                 default=20)]),
         ]},
        {"id": "adapter", "title": "Adapter and settings",
         "blurb": "Cable, port and MultiEcuScan state.",
         "tools": [
            _tool("GET", "/api/live/ports", "Serial ports",
                  "Every serial port seen, with MES's configured one marked.",
                  "The adapter isn't responding and you need to check the port."),
            _tool("GET", "/api/live/mes", "MultiEcuScan settings",
                  "MES's own port/baud settings, read from the registry.",
                  "Cross-checking that cuore and MES agree on the port."),
            _tool("POST", "/api/live/cable", "Declare the fitted cable",
                  "Tells cuore which OBD cable is physically connected.",
                  "Before any bus verification or module read.",
                  risk="changes cuore settings", run="form",
                  inputs=[_input("cable", "body", "Cable", required=True,
                                 choices=CABLE_CHOICES)]),
            _tool("POST", "/api/live/verify", "Verify a bus",
                  "Passive listen on one bus; marks it verified if traffic is seen.",
                  "After declaring a cable, before any module-specific read.",
                  risk="holds adapter", needs=("adapter",), run="form",
                  inputs=[_input("bus", "body", "Bus", required=True, choices=BUS_CHOICES),
                          _input("seconds", "body", "Seconds", type_="number", default=2.0)]),
         ]},
        {"id": "developer", "title": "For developers",
         "blurb": "Raw endpoints a mechanic shouldn't need day to day.",
         "tools": [
            _tool("GET", "/api/capabilities", "Capabilities",
                  "What this cuore instance can do: profile, features, adapter.",
                  "Debugging why a feature seems to be missing.",
                  developer_only=True),
            _tool("GET", "/api/health", "Health", "Liveness check.",
                  "Scripting a monitor against this instance.", developer_only=True),
            _tool("GET", "/api/modules", "Module registry",
                  "The full 126-entry reference registry, grouped by domain.",
                  "Looking up a module's aliases or tier.", developer_only=True),
         ]},
        {"id": "writes", "title": "Writes to the car",
         "blurb": "Clearing codes and running actuators change the car. Do these "
                   "from the MCP tools (Claude), with explicit consent, not from "
                   "this page -- there is no undo.",
         "tools": [
            {"id": "mcp:clear_dtcs", "method": "MCP", "path": "obd2.clear_dtcs",
             "name": "Clear DTCs", "what": "Erases stored/pending codes from the car.",
             "when": "Only after the fault is actually fixed, never to make a light "
                     "go away temporarily.", "needs": ["adapter"],
             "risk": "holds adapter", "inputs": [], "run": "not_from_here",
             "enabled": False,
             "disabled_reason": "Writes to the car are MCP-only -- ask Claude, "
                                 "with the consent phrase below.",
             "result_hint": "", "developer_only": False, "synonyms": ["clear codes"],
             "consent_phrase": "I understand this clears diagnostic trouble codes "
                                "from the vehicle and this cannot be undone."},
            {"id": "mcp:run_actuator", "method": "MCP", "path": "obd2.run_actuator",
             "name": "Run an actuator test", "what": "Commands a component to move or "
                     "energize for a short, bounded time.",
             "when": "Confirming a part responds, key-on engine-off unless the test "
                     "says otherwise.", "needs": ["adapter"], "risk": "holds adapter",
             "inputs": [], "run": "not_from_here", "enabled": False,
             "disabled_reason": "Writes to the car are MCP-only -- ask Claude, "
                                 "with the consent phrase below.",
             "result_hint": "", "developer_only": False, "synonyms": ["actuator test"],
             "consent_phrase": "I understand this actuates a physical component on "
                                "the vehicle for a bounded time."},
         ]},
    ]


def _workflows() -> list[dict[str, Any]]:
    def step(tool_id: str, label: str, stop_on_fail: bool = False,
             uses_previous: bool = False) -> dict[str, Any]:
        return {"tool_id": tool_id, "label": label, "stop_on_fail": stop_on_fail,
                "uses_previous": uses_previous}

    return [
        {"id": "intake", "title": "New car in the bay",
         "blurb": "First contact: who is this car, and what does it already know.",
         "steps": [
            step("GET /api/live/status", "Check the adapter"),
            step("GET /api/live/obd/vin", "Read VIN from the car", stop_on_fail=True),
            step("GET /api/live/obd/dtcs", "Read stored/pending codes"),
            step("GET /api/live/obd/readiness", "Check readiness monitors"),
         ]},
        {"id": "diagnose", "title": "Diagnose an active code",
         "blurb": "Cross the live car against its own log history before touching anything.",
         "steps": [
            step("GET /api/live/obd/dtcs", "Read the code(s)", stop_on_fail=True),
            step("GET /api/vehicle/{vin}/dtcs", "Check this car's code history"),
            step("GET /api/vehicle/{vin}/tree", "Walk the fault tree"),
         ]},
    ]


def _apply_state(groups: list[dict[str, Any]], state: dict[str, Any]) -> None:
    """Fill in defaults from live state and compute enabled/disabled_reason.

    A placeholder for what the real ``/api/tools/catalogue`` will do server-side
    for real -- this fixture does the same job with the three conditions this
    page can already check cheaply.
    """
    has_vin = bool(state.get("active_vin"))
    has_adapter = bool(state.get("port")) and state.get("lock_holder") in (None, "", "cuore")
    has_bus = (state.get("buses_verified") or 0) > 0

    for group in groups:
        for tool in group["tools"]:
            for inp in tool.get("inputs", []):
                if inp.get("source") == "active_vin" and inp.get("default") is None:
                    inp["default"] = state.get("active_vin") or ""
            if tool.get("run") == "not_from_here":
                continue
            needs = tool.get("needs", [])
            reason = None
            if "vin" in needs and not has_vin:
                reason = "pick a vehicle first"
            elif "adapter" in needs and not has_adapter:
                reason = "car not connected -- check the adapter on Adapter & settings"
            elif "bus" in needs and not has_bus:
                reason = "no bus verified yet -- verify one on Adapter & settings"
            tool["enabled"] = reason is None
            tool["disabled_reason"] = reason


def _catalogue(state: dict[str, Any]) -> dict[str, Any]:
    groups = _groups()
    _apply_state(groups, state)
    total = sum(len(g["tools"]) for g in groups)
    developer_only = sum(1 for g in groups for t in g["tools"] if t.get("developer_only"))
    curated = total - developer_only
    return {
        "groups": groups,
        "workflows": _workflows(),
        "state": state,
        "coverage": {"total_operations": total, "curated": curated,
                     "developer_only": developer_only},
        "fixture": True,
    }


# --- pages ------------------------------------------------------------------

@router.get("/tools", response_class=HTMLResponse)
def tools_page(request: Request, vin: str = "") -> HTMLResponse:
    settings = settings_of(request)
    state = _state(request)
    catalogue = _catalogue(state)
    return templates.TemplateResponse(request, "tools.html", {
        "version": __version__, "profile": settings.profile.value,
        "live_strip": None, "catalogue": catalogue, "vin": state.get("active_vin") or "",
    })


@router.get("/api", include_in_schema=False)
def api_redirect() -> RedirectResponse:
    return RedirectResponse(url="/tools", status_code=307)


@router.get("/api/", include_in_schema=False)
def api_redirect_slash() -> RedirectResponse:
    return RedirectResponse(url="/tools", status_code=307)
