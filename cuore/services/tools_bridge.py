"""Data side of the mechanic-facing Tools catalogue (rendered at /tools by another agent).

Curates the 117 HTTP operations (``create_app().openapi()``) into plain-words
cards grouped for a mechanic, not a developer. Every operation in the spec is
either in :data:`CURATED` or falls back to an auto-built ``developer_only``
card -- so a new route can never be silently missing from the catalogue (see
``cuore/tests/check_tools.py``).

Nothing here writes to the car. The HTTP API has no write route at all (see
``cuore/api/live.py``); the three MCP-only write operations are listed as
inert cards in the ``writes`` group with ``run="not_from_here"``.
"""

from __future__ import annotations

from typing import Any, Optional

import serial.tools.list_ports

from ..live import ops as live_ops
from ..live import safety
from ..live.config import resolve_port
from ..services import mes_bridge

GROUP_ORDER: list[tuple[str, str]] = [
    ("read_car", "Read the car now"),
    ("verify", "Check a repair"),
    ("history", "History and logs"),
    ("live", "Live data and recording"),
    ("service", "Service and maintenance"),
    ("learn", "Learning and dealer results"),
    ("settings", "Adapter and settings"),
    ("developer", "For developers"),
]

#: group -> one-sentence blurb shown above its cards.
GROUP_BLURBS: dict[str, str] = {
    "read_car": "Plug in and ask the car what is wrong, right now.",
    "verify": "Has a repair actually taken? Check readiness and re-reads.",
    "history": "What the shop's own logs already know about this vehicle.",
    "live": "Watch parameters move in real time, and record what you see.",
    "service": "Maintenance records, checklists and torque specs.",
    "learn": "Capture a dealer-tool session, and record wiTECH results.",
    "settings": "Cable, port and bus configuration for the adapter.",
    "developer": "Internal and advanced operations. Collapsed by default.",
}

#: Curated overlay, keyed by (METHOD, path exactly as FastAPI prints it).
#: Every value omits id/method/path (filled in by catalogue()) and
#: developer_only (defaults False here -- CURATED is the mechanic-facing set).
CURATED: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/api/live/probe"): dict(
        group="read_car", name="Connect to the car",
        what="Resets the adapter and confirms it can see the car (battery voltage).",
        when="First thing, every visit, before any other read.",
        needs=["car"], risk="reads_car", inputs=[], run="one_tap",
        result_hint="kv", synonyms=["connect", "plug in", "probe"]),
    ("POST", "/api/live/verify"): dict(
        group="read_car", name="Verify a bus has traffic",
        what="Listens passively and confirms the chosen bus is alive under the fitted cable.",
        when="Before any module read, and after changing the cable.",
        needs=["car", "cable"],
        inputs=[{"name": "bus", "in": "body", "label": "Bus", "type": "string",
                 "required": True, "default": "can_c", "source": None,
                 "choices": ["can_c", "can_ch", "can_ihs"], "help": "Which bus to listen on."}],
        risk="reads_car", run="form", result_hint="kv",
        synonyms=["verify bus", "check bus", "listen"]),
    ("GET", "/api/live/obd/dtcs"): dict(
        group="read_car", name="Read codes (stored / pending / permanent)",
        what="Mode 03/07/0A: emissions-related codes the ECM currently reports.",
        when="The first read on any complaint.",
        needs=["car"],
        inputs=[{"name": "kind", "in": "query", "label": "Kind", "type": "string",
                 "required": False, "default": "stored", "source": None,
                 "choices": ["stored", "pending", "permanent", "all"], "help": None}],
        risk="reads_car", run="one_tap", result_hint="codes",
        synonyms=["read codes", "scan for codes", "check engine light"]),
    ("GET", "/api/live/obd/readiness"): dict(
        group="read_car", name="Readiness monitors",
        what="Which emissions monitors have run since the last clear, plus the EVAP verdict.",
        when="After a repair, or before an emissions test.",
        needs=["car"], risk="reads_car", inputs=[], run="one_tap",
        result_hint="readiness", synonyms=["readiness", "monitors", "inspection ready"]),
    ("GET", "/api/live/obd/freeze"): dict(
        group="read_car", name="Freeze frame",
        what="Conditions captured the moment a code set (RPM, speed, load, temps).",
        when="Before clearing anything -- a clear destroys this.",
        needs=["car"], risk="reads_car", inputs=[], run="one_tap", result_hint="kv",
        synonyms=["freeze frame", "snapshot at fault"]),
    ("GET", "/api/live/obd/vin"): dict(
        group="read_car", name="Read VIN from the car",
        what="Mode 09: the VIN the ECM itself reports.",
        when="To confirm you are on the right vehicle before anything else.",
        needs=["car"], risk="reads_car", inputs=[], run="one_tap", result_hint="kv",
        synonyms=["read vin", "confirm vehicle"]),
    ("GET", "/api/live/obd/voltage"): dict(
        group="read_car", name="Battery voltage at the port",
        what="Voltage the adapter sees right now.",
        when="To confirm the car has power before anything else reads blank.",
        needs=["car"], risk="reads_car", inputs=[], run="one_tap", result_hint="kv",
        synonyms=["battery voltage", "check battery"]),
    ("GET", "/api/live/obd/mode06"): dict(
        group="read_car", name="On-board test results (Mode $06)",
        what="Raw pass/fail test limits, with the EVAP tests summarised.",
        when="Diagnosing EVAP or catalyst issues the status PID does not explain.",
        needs=["car"], risk="reads_car", inputs=[], run="one_tap", result_hint="raw",
        synonyms=["mode 6", "test results"]),
    ("GET", "/api/live/module/{code}/dtcs"): dict(
        group="read_car", name="Read one module's codes (UDS)",
        what="Full UDS fault memory for one module, with status words per code.",
        when="When Mode 03 is silent, or the fault is a body/chassis/network code.",
        needs=["car"],
        inputs=[{"name": "code", "in": "path", "label": "Module", "type": "string",
                 "required": True, "default": None, "source": "vehicle_modules", "help": None},
                {"name": "vin", "in": "query", "label": "VIN", "type": "string",
                 "required": False, "default": None, "source": "active_vin", "help": None}],
        risk="reads_car", run="form", result_hint="codes",
        synonyms=["module codes", "uds codes", "body codes"]),
    ("GET", "/api/live/module/{code}/identity"): dict(
        group="read_car", name="Module identity",
        what="Part number, software and calibration identifiers for one module.",
        when="To confirm which module/software you are actually talking to.",
        needs=["car"],
        inputs=[{"name": "code", "in": "path", "label": "Module", "type": "string",
                 "required": True, "default": None, "source": "vehicle_modules", "help": None}],
        risk="reads_car", run="form", result_hint="kv", synonyms=["module id", "part number"]),
    ("GET", "/api/live/scan"): dict(
        group="read_car", name="Scan all modules on a bus",
        what="UDS DTC sweep over every confirmed module on one bus.",
        when="A general health check, or after an unfamiliar complaint.",
        needs=["car", "cable"],
        inputs=[{"name": "bus", "in": "query", "label": "Bus", "type": "string",
                 "required": False, "default": "can_c", "source": None,
                 "choices": ["can_c", "can_ch", "can_ihs"], "help": None}],
        risk="reads_car", run="form", result_hint="table", synonyms=["scan modules", "full scan"]),
    ("POST", "/api/live/discover"): dict(
        group="read_car", name="Discover module addresses",
        what="Probes candidate UDS addresses on a bus and confirms which modules answer.",
        when="Before a scan, if the module table looks incomplete for this car.",
        needs=["car", "cable"], risk="reads_car", inputs=[], run="form", result_hint="table",
        synonyms=["discover modules", "find ecus"]),
    ("GET", "/api/live/module/{code}/repair"): dict(
        group="verify", name="Check a repair (re-run since clear?)",
        what="Has each named test re-run since the last clear, and did it pass.",
        when="After a repair, to see if the fault is actually gone.",
        needs=["car", "vin"],
        inputs=[{"name": "code", "in": "path", "label": "Module", "type": "string",
                 "required": True, "default": "ECM", "source": "vehicle_modules", "help": None},
                {"name": "codes", "in": "query", "label": "Codes", "type": "string",
                 "required": True, "default": None, "source": "recent_codes",
                 "help": "Comma-separated, e.g. P0455,P0456"}],
        risk="reads_car", run="form", result_hint="table",
        synonyms=["verify repair", "check fix", "repair verification"]),
    ("POST", "/api/vehicle/{vin}/verdict"): dict(
        group="verify", name="Evidence gate (diagnosis verdict)",
        what="Grades a proposed diagnosis against the shop's own evidence standard.",
        when="Before telling a customer a diagnosis is confirmed.",
        needs=["vin"], risk="reads_logs", run="form", result_hint="kv",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["verdict", "confirm diagnosis", "evidence gate"]),
    ("GET", "/api/vehicles/{vin}/live-vs-log"): dict(
        group="verify", name="Live reads vs. the last log",
        what="Compares a fresh live read against the newest MES log, code by code.",
        when="To see whether a code the log shows has actually cleared on the car.",
        needs=["car", "vin"], risk="reads_car", run="form", result_hint="table",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["live vs log", "compare to log"]),
    ("GET", "/api/vehicle/{vin}"): dict(
        group="history", name="Vehicle dossier",
        what="Everything the shop's own logs know about this car, in one view.",
        when="Starting point for any repeat customer.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="kv",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["dossier", "vehicle history", "workup"]),
    ("GET", "/api/vehicle/{vin}/dtcs"): dict(
        group="history", name="Every logged code, with history",
        what="Every code ever seen on this car in the logs, chronic/returned flagged.",
        when="To see if today's complaint is a repeat.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="codes",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["code history", "past codes"]),
    ("GET", "/api/vehicle/{vin}/dtc/{code}"): dict(
        group="history", name="One code's full history",
        what="Every time this exact code was seen, cleared, or returned.",
        when="A code keeps coming back and you want the full timeline.",
        needs=["vin"], risk="reads_logs", run="form", result_hint="table",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None},
                {"name": "code", "in": "path", "label": "Code", "type": "string",
                 "required": True, "default": None, "source": "recent_codes", "help": None}],
        synonyms=["code detail", "one code history"]),
    ("GET", "/api/vehicle/{vin}/tree"): dict(
        group="history", name="Fault-tree isolation steps",
        what="A step-by-step isolation sequence for this car's open codes.",
        when="You have codes and need the diagnostic order of operations.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="table",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["fault tree", "isolation steps", "diagnostic tree"]),
    ("GET", "/api/vehicles/{vin}/notes"): dict(
        group="history", name="Technician notes",
        what="Notes other technicians (or you) left on this car.",
        when="Catching up on what has already been tried.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="table",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["notes", "technician notes"]),
    ("POST", "/api/vehicles/{vin}/notes"): dict(
        group="history", name="Add a technician note",
        what="Records a free-text note against this vehicle.",
        when="Anything worth remembering that is not a form field elsewhere.",
        needs=["vin"], risk="writes_cuore_state", run="form", result_hint="text",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None},
                {"name": "text", "in": "body", "label": "Note", "type": "string",
                 "required": True, "default": None, "source": None, "help": None}],
        synonyms=["add note", "leave note"]),
    ("GET", "/api/vehicles/{vin}/dashboard"): dict(
        group="history", name="Vehicle dashboard",
        what="Charts: code timeline, odometer, which modules have faulted.",
        when="A visual overview before diving into one code.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="raw",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["dashboard", "charts"]),
    ("GET", "/api/vehicles/{vin}/checklist"): dict(
        group="service", name="Open-work checklist",
        what="This car's open-work checklist state (ticked/unticked steps).",
        when="Working through a repair card step by step.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="table",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["checklist", "open work"]),
    ("POST", "/api/vehicles/{vin}/checklist"): dict(
        group="service", name="Tick a checklist step",
        what="Marks one checklist step done or not done.",
        when="As you complete each step of a repair card.",
        needs=["vin"], risk="writes_cuore_state", run="form", result_hint="kv",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None},
                {"name": "step_id", "in": "body", "label": "Step", "type": "string",
                 "required": True, "default": None, "source": None, "help": None},
                {"name": "done", "in": "body", "label": "Done", "type": "boolean",
                 "required": True, "default": True, "source": None, "help": None}],
        synonyms=["check off step", "mark done"]),
    ("GET", "/api/vehicles/{vin}/service-records"): dict(
        group="service", name="Service records",
        what="Logged oil changes, services and brake/tire work for this car.",
        when="Checking what maintenance has already been done.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="table",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["service history", "maintenance records"]),
    ("GET", "/api/vehicles/{vin}/maintenance"): dict(
        group="service", name="Maintenance checklist",
        what="The manufacturer maintenance checklist against this car's odometer.",
        when="Deciding what service is due today.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="table",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["maintenance schedule", "what's due"]),
    ("GET", "/api/vehicles/{vin}/oil-change/next"): dict(
        group="service", name="Next oil change",
        what="When the next oil change is due by distance and date.",
        when="Quick answer for the service counter.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="kv",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["oil change due", "next service"]),
    ("GET", "/api/vehicles/{vin}/torque"): dict(
        group="service", name="Torque spec search",
        what="Searches the torque-value library by fastener or assembly.",
        when="Looking up a spec mid-job.",
        needs=[], risk="reads_logs", run="form", result_hint="table",
        inputs=[{"name": "q", "in": "query", "label": "Search", "type": "string",
                 "required": False, "default": None, "source": None, "help": None}],
        synonyms=["torque spec", "bolt torque"]),
    ("GET", "/api/vehicles/{vin}/dealer-results"): dict(
        group="learn", name="Dealer (wiTECH) results",
        what="Every wiTECH result a technician has recorded for this car.",
        when="Checking what the dealer tool has already found.",
        needs=["vin"], risk="reads_logs", run="one_tap", result_hint="table",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None}],
        synonyms=["witech results", "dealer results"]),
    ("POST", "/api/vehicles/{vin}/dealer-results"): dict(
        group="learn", name="Record a dealer (wiTECH) result",
        what="Saves one technician-entered wiTECH result against this car.",
        when="After running something on wiTECH that is worth keeping.",
        needs=["vin"], risk="writes_cuore_state", run="form", result_hint="text",
        inputs=[{"name": "vin", "in": "path", "label": "VIN", "type": "string",
                 "required": True, "default": None, "source": "active_vin", "help": None},
                {"name": "kind", "in": "body", "label": "Kind", "type": "string",
                 "required": True, "default": None, "source": None,
                 "choices": ["flash_check", "slvt", "dtc_report", "recall_status", "routine"],
                 "help": None}],
        synonyms=["record witech result"]),
    ("POST", "/api/live/learn/capture"): dict(
        group="learn", name="Capture a dealer-tool session",
        what="Passively records bus traffic while wiTECH/MES talks to the car.",
        when="Learning a parameter or procedure MES does but cuore does not yet know.",
        needs=["car", "cable"], risk="reads_car", run="form", result_hint="kv",
        inputs=[], synonyms=["learn capture", "record witech traffic"]),
    ("GET", "/api/live/learned"): dict(
        group="learn", name="Learned identifier mappings",
        what="Identifier mappings learned so far from captured dealer-tool sessions.",
        when="Checking what cuore already knows how to read on this car.",
        needs=[], risk="reads_logs", run="one_tap", result_hint="table",
        inputs=[], synonyms=["learned dids", "learned mappings"]),
    ("GET", "/api/live/status"): dict(
        group="settings", name="Adapter status",
        what="Port, cable, MES state and who (if anyone) holds the adapter.",
        when="Troubleshooting why a read is refused.",
        needs=[], risk="reads_car", run="one_tap", result_hint="kv",
        inputs=[], synonyms=["adapter status", "connection status"]),
    ("GET", "/api/live/ports"): dict(
        group="settings", name="Serial ports",
        what="Every serial port seen, with MES's configured port marked.",
        when="Picking the right port when more than one adapter is plugged in.",
        needs=[], risk="reads_car", run="one_tap", result_hint="table",
        inputs=[], synonyms=["serial ports", "list ports"]),
    ("GET", "/api/live/buses"): dict(
        group="settings", name="Bus reachability",
        what="The three buses and whether the fitted cable can reach each.",
        when="Checking the cable before trying to verify a bus.",
        needs=["cable"], risk="reads_car", run="one_tap", result_hint="table",
        inputs=[], synonyms=["buses", "bus reachability"]),
    ("POST", "/api/live/cable"): dict(
        group="settings", name="Declare the fitted cable",
        what="Tells cuore which adapter cable is physically fitted.",
        when="Every time you change cables.",
        needs=[], risk="writes_cuore_state", run="form", result_hint="kv",
        inputs=[{"name": "cable", "in": "body", "label": "Cable", "type": "string",
                 "required": True, "default": None, "source": "cable",
                 "choices": ["none", "blue_a5", "grey_a6"], "help": None}],
        synonyms=["set cable", "change cable", "declare cable"]),
    ("GET", "/api/live/known-good"): dict(
        group="live", name="Known-good reference bands",
        what="Reference min/max/warn/alarm bands for live channels, with this car's own history.",
        when="Deciding whether a live reading is actually abnormal.",
        needs=[], risk="reads_logs", run="form", result_hint="table",
        inputs=[{"name": "vin", "in": "query", "label": "VIN", "type": "string",
                 "required": False, "default": None, "source": "active_vin", "help": None}],
        synonyms=["known good", "normal range"]),
    ("GET", "/api/live/channels"): dict(
        group="live", name="Live channel registry",
        what="Every channel (PID/DID/computed/battery) available to watch live, and presets.",
        when="Choosing what to put on the live-data screen.",
        needs=[], risk="reads_car", run="one_tap", result_hint="table",
        inputs=[], synonyms=["live channels", "parameters list"]),
    ("POST", "/api/live/session/start"): dict(
        group="live", name="Start live data",
        what="Starts polling channels in real time; holds the adapter for the session.",
        when="Watching parameters move while driving or revving.",
        needs=["car", "mes_stopped"], risk="holds_adapter", run="form", result_hint="kv",
        inputs=[{"name": "preset", "in": "body", "label": "Preset", "type": "string",
                 "required": False, "default": None, "source": "live_channels", "help": None}],
        synonyms=["start live data", "live session"]),
    ("POST", "/api/live/session/stop"): dict(
        group="live", name="Stop live data",
        what="Stops the live-data session and releases the adapter.",
        when="Done watching live parameters.",
        needs=["live_session"], risk="holds_adapter", run="one_tap", result_hint="kv",
        inputs=[], synonyms=["stop live data"]),
    ("GET", "/api/live/snapshot"): dict(
        group="live", name="Live snapshot",
        what="The latest value of every channel in the running live session.",
        when="A quick read while a live session is already running.",
        needs=["live_session"], risk="holds_adapter", run="one_tap", result_hint="table",
        inputs=[], synonyms=["live snapshot", "current values"]),
    ("POST", "/api/live/record/start"): dict(
        group="live", name="Start recording live data",
        what="Mirrors the running live session to an MES-format CSV.",
        when="Capturing evidence of a live symptom.",
        needs=["live_session"], risk="holds_adapter", run="one_tap", result_hint="kv",
        inputs=[], synonyms=["record live data", "start recording"]),
    ("POST", "/api/live/record/stop"): dict(
        group="live", name="Stop recording live data",
        what="Stops the CSV recording of the live session.",
        when="Done capturing a drive or test.",
        needs=["live_session"], risk="holds_adapter", run="one_tap", result_hint="kv",
        inputs=[], synonyms=["stop recording"]),
}

CURATED[("GET", "/api/logs")] = dict(
    group="history", name="Search the log index",
    what="Lists MES logs, filterable by vehicle, VIN or date.",
    when="Finding the right log file to open.",
    needs=[], risk="reads_logs", run="form", result_hint="table",
    inputs=[{"name": "vin", "in": "query", "label": "VIN", "type": "string",
             "required": False, "default": None, "source": "active_vin", "help": None}],
    synonyms=["log index", "list logs"])

CURATED[("GET", "/api/log/{name}")] = dict(
    group="history", name="Read one log",
    what="The full text of one MES log file.",
    when="Reading the detail behind a log index entry.",
    needs=[], risk="reads_logs", run="form", result_hint="text",
    inputs=[{"name": "name", "in": "path", "label": "File", "type": "string",
             "required": True, "default": None, "source": None, "help": None}],
    synonyms=["read log", "open log file"])

CURATED[("GET", "/api/search")] = dict(
    group="history", name="Search across logs",
    what="Regex search across every MES log.",
    when="Hunting for a specific string or code pattern across the corpus.",
    needs=[], risk="reads_logs", run="form", result_hint="table",
    inputs=[{"name": "pattern", "in": "query", "label": "Search text", "type": "string",
             "required": True, "default": None, "source": None, "help": None}],
    synonyms=["search logs", "find in logs"])

CURATED[("GET", "/api/recordings")] = dict(
    group="history", name="CSV recordings",
    what="Every CSV recording captured from MES's graph subsystem, newest first.",
    when="Reviewing a recorded drive or test.",
    needs=[], risk="reads_logs", run="one_tap", result_hint="table",
    inputs=[], synonyms=["recordings", "csv logs"])


# --- write operations: MCP-only, never over HTTP ----------------------------
#
# These three are deliberately absent from the OpenAPI spec (see
# cuore/api/live.py's own docstring: "There is no write route"). They are
# listed here so a mechanic knows they exist and exactly what consent phrase
# each one demands -- the phrase format and the blocked-module list are read
# from cuore.live.safety / cuore.live.clear / cuore.live.actuate, never
# duplicated.

def _write_cards() -> list[dict[str, Any]]:
    blocked = sorted(safety.ACTUATION_BLOCKED_MODULES)
    return [
        {
            "id": "mcp obd2.clear_module_dtcs", "method": None, "path": None,
            "name": "Clear a module's codes", "what": "Erases one module's fault memory.",
            "when": "Only after the fault is confirmed repaired and evidence is captured.",
            "needs": ["car", "module"], "risk": "writes_cuore_state",
            "inputs": [{"name": "consent", "in": "body", "label": "Consent phrase",
                        "type": "string", "required": True, "default": None, "source": None,
                        "choices": None,
                        "help": "Type exactly: CLEAR <MODULE>, e.g. CLEAR ECM"}],
            "run": "not_from_here", "enabled": False,
            "disabled_reason": "Clearing writes to the car; use the MCP obd2 tool directly, "
                               "never from this page.",
            "result_hint": "text", "developer_only": False,
            "synonyms": ["clear codes", "erase codes", "clear dtcs"],
        },
        {
            "id": "mcp obd2.run_actuator (actuator test)", "method": None, "path": None,
            "name": "Run an actuator test", "what": "Replays a learned actuator-test procedure.",
            "when": "Confirming a component responds, with the car stationary and off.",
            "needs": ["car", "module"], "risk": "writes_cuore_state",
            "inputs": [{"name": "consent", "in": "body", "label": "Consent phrase",
                        "type": "string", "required": True, "default": None, "source": None,
                        "choices": None,
                        "help": "Type exactly: ACTUATE <MODULE> <NAME>"}],
            "run": "not_from_here", "enabled": False,
            "disabled_reason": "Actuation writes to the car; use the MCP obd2 tool directly, "
                               "never from this page.",
            "result_hint": "text", "developer_only": False,
            "synonyms": ["actuate", "run actuator test"],
        },
        {
            "id": "mcp obd2.run_actuator (routine)", "method": None, "path": None,
            "name": "Run a routine", "what": "Replays a learned UDS RoutineControl procedure.",
            "when": "Running a learned adaptation/routine, with the car stationary and off.",
            "needs": ["car", "module"], "risk": "writes_cuore_state",
            "inputs": [{"name": "consent", "in": "body", "label": "Consent phrase",
                        "type": "string", "required": True, "default": None, "source": None,
                        "choices": None,
                        "help": "Type exactly: RUN ROUTINE <MODULE> <NAME>"}],
            "run": "not_from_here", "enabled": False,
            "disabled_reason": "Routines write to the car; use the MCP obd2 tool directly, "
                               "never from this page.",
            "result_hint": "text", "developer_only": False,
            "synonyms": ["run routine", "adaptation"],
            "blocked_modules": blocked,
        },
    ]


# --- state --------------------------------------------------------------------

def current_state(vin: str = "") -> dict[str, Any]:
    """Everything enablement rules need: adapter, cable, MES, lock, and this car's logged ECUs."""
    try:
        status = live_ops.status()
    except Exception as exc:  # noqa: BLE001 -- state must never 500 the catalogue
        status = {"error": str(exc)}
    try:
        from ..live import poller as poller_mod
        live_status = poller_mod.poller().status()
        poller_active = bool(live_status.get("active"))
    except Exception:
        live_status = {}
        poller_active = False
    port = status.get("port")
    port_exists = False
    if port:
        try:
            port_exists = any(p.device.upper() == str(port).upper()
                              for p in serial.tools.list_ports.comports())
        except Exception:
            port_exists = False
    mes = status.get("mes") or {}
    lock = status.get("lock") or {}
    cable = (status.get("cable") or {}).get("cable")
    buses = (status.get("cable") or {}).get("buses") or []
    ecus: list[str] = []
    if vin:
        try:
            dossier = mes_bridge.workup(vin=vin)
            identity = dossier.get("identity") or {}
            ecus = identity.get("ecus") or identity.get("modules") or []
        except Exception:
            ecus = []
    return {
        "active_vin": vin or None,
        "port": port, "port_exists": port_exists,
        "mes_state": mes.get("state"), "mes_running": bool(mes.get("running")),
        "lock_holder": lock.get("process") or lock.get("pid"),
        "cable": cable, "buses_verified": [b["bus"] for b in buses if b.get("verified")],
        "live_session_active": poller_active,
        "logged_ecus": ecus,
        "status_error": status.get("error"),
    }


def _enabled(needs: list[str], state: dict[str, Any]) -> tuple[bool, Optional[str]]:
    for need in needs:
        if need == "car":
            if not state.get("port"):
                return False, "Connect the car: no adapter port configured"
            if not state.get("port_exists"):
                return False, f"Connect the car: no adapter on {state.get('port')}"
            if state.get("mes_state") == "connected":
                return False, "Close MultiEcuScan first: it holds the port"
            if state.get("lock_holder"):
                return False, f"Another process ({state['lock_holder']}) holds the adapter"
        elif need == "live_session":
            if not state.get("live_session_active"):
                return False, "Start a live-data session first"
        elif need == "mes_stopped":
            if state.get("mes_state") == "connected":
                return False, "Close MultiEcuScan first: it holds the port"
        elif need == "vin":
            if not state.get("active_vin"):
                return False, "Pick a vehicle first"
        elif need == "cable":
            if not state.get("cable") or state.get("cable") == "none":
                return False, "Declare the fitted cable first"
        elif need == "module":
            pass  # chosen per-call in the form; not a catalogue-wide gate
    return True, None


# --- catalogue ------------------------------------------------------------------

def _fallback_entry(method: str, path: str, tags: list[str] | None, summary: str | None
                    ) -> dict[str, Any]:
    risk = "reads_logs"
    if "/live/" in path:
        risk = "reads_car"
    if method in ("POST", "PUT", "DELETE"):
        risk = "writes_cuore_state"
    return dict(group="developer", name=summary or path, what=summary or "Internal operation.",
               when="Developer / internal use.", needs=[], risk=risk, inputs=[],
               run="not_from_here", result_hint="raw", synonyms=[])


def catalogue(app_openapi: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """The full catalogue: curated groups, write-only cards, workflows, state, coverage."""
    ops: list[tuple[str, str, list[str] | None, str | None]] = []
    for path, methods in (app_openapi.get("paths") or {}).items():
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            ops.append((method.upper(), path, op.get("tags"), op.get("summary")))

    by_group: dict[str, list[dict[str, Any]]] = {gid: [] for gid, _ in GROUP_ORDER}
    curated_count = 0
    for method, path, tags, summary in ops:
        key = (method, path)
        if key in CURATED:
            curated_count += 1
            spec = CURATED[key]
            developer_only = False
        else:
            spec = _fallback_entry(method, path, tags, summary)
            developer_only = True
        needs = spec.get("needs", [])
        enabled, reason = (True, None) if developer_only and not needs else _enabled(needs, state)
        tool = {
            "id": f"{method} {path}", "method": method, "path": path,
            "name": spec["name"], "what": spec["what"], "when": spec["when"],
            "needs": needs, "risk": spec["risk"], "inputs": spec.get("inputs", []),
            "run": spec["run"], "enabled": enabled, "disabled_reason": reason,
            "result_hint": spec["result_hint"], "developer_only": developer_only,
            "synonyms": spec.get("synonyms", []),
        }
        by_group.setdefault(spec["group"], []).append(tool)

    groups = [{"id": gid, "title": title, "blurb": GROUP_BLURBS[gid], "tools": by_group.get(gid, [])}
              for gid, title in GROUP_ORDER]
    groups.append({"id": "writes", "title": "Clearing codes and running actuators",
                   "blurb": "Not available from this page -- use the MCP obd2 tool directly, "
                            "with the exact consent phrase.",
                   "tools": _write_cards()})

    total = len(ops)
    return {
        "groups": groups,
        "workflows": _workflows(),
        "state": state,
        "coverage": {"total_operations": total, "curated": curated_count,
                    "developer_only": total - curated_count},
    }


def _all_tool_ids(cat: dict[str, Any]) -> set[str]:
    return {t["id"] for g in cat["groups"] for t in g["tools"]}


# --- suggestions ----------------------------------------------------------------

def suggest(state: dict[str, Any], catalogue_: dict[str, Any]) -> list[str]:
    """Next sensible tool ids, most useful first. Never suggests a disabled tool."""
    ids = _all_tool_ids(catalogue_)
    out: list[str] = []

    def want(tool_id: str) -> None:
        if tool_id in ids and tool_id not in out:
            out.append(tool_id)

    if not state.get("cable") or state.get("cable") == "none":
        want("POST /api/live/cable")
        return out
    if state.get("port") and state.get("port_exists") and not state.get("buses_verified"):
        want("POST /api/live/verify")
        return out
    if state.get("buses_verified") and state.get("port_exists"):
        want("GET /api/live/obd/dtcs")
        want("GET /api/live/obd/readiness")
    if not state.get("active_vin"):
        want("GET /api/vehicles")
    return out


# --- workflows (read-only sequences) --------------------------------------------

def _workflows() -> list[dict[str, Any]]:
    return [
        {
            "id": "check_car", "title": "Check the car",
            "blurb": "Probe, verify the bus, read every code, readiness, freeze frame, "
                     "then scan confirmed modules. Read-only throughout.",
            "steps": [
                {"tool_id": "POST /api/live/probe", "label": "Connect", "stop_on_fail": True,
                 "uses_previous": None},
                {"tool_id": "POST /api/live/verify", "label": "Verify bus",
                 "stop_on_fail": True, "uses_previous": None},
                {"tool_id": "GET /api/live/obd/dtcs", "label": "Stored codes",
                 "stop_on_fail": False, "uses_previous": None},
                {"tool_id": "GET /api/live/obd/readiness", "label": "Readiness",
                 "stop_on_fail": False, "uses_previous": None},
                {"tool_id": "GET /api/live/obd/freeze", "label": "Freeze frame",
                 "stop_on_fail": False, "uses_previous": None},
                {"tool_id": "GET /api/live/scan", "label": "Scan confirmed modules",
                 "stop_on_fail": False, "uses_previous": "bus"},
            ],
        },
        {
            "id": "verify_repair", "title": "Verify a repair",
            "blurb": "Readiness, permanent codes, then the dossier's verdict gate. Read-only.",
            "steps": [
                {"tool_id": "GET /api/live/obd/readiness", "label": "Readiness",
                 "stop_on_fail": False, "uses_previous": None},
                {"tool_id": "GET /api/live/obd/dtcs", "label": "Permanent codes",
                 "stop_on_fail": False, "uses_previous": None},
                {"tool_id": "POST /api/vehicle/{vin}/verdict", "label": "Dossier verdict",
                 "stop_on_fail": False, "uses_previous": None},
            ],
        },
        {
            "id": "prep_live", "title": "Prepare for a live-data session",
            "blurb": "Probe, verify the bus, then list the channels available to watch.",
            "steps": [
                {"tool_id": "POST /api/live/probe", "label": "Connect", "stop_on_fail": True,
                 "uses_previous": None},
                {"tool_id": "POST /api/live/verify", "label": "Verify bus",
                 "stop_on_fail": True, "uses_previous": None},
                {"tool_id": "GET /api/live/channels", "label": "Channels",
                 "stop_on_fail": False, "uses_previous": None},
            ],
        },
    ]


# --- result shaping for the page -------------------------------------------------

_STATUS_BITS = [(0x01, "test failed"), (0x04, "confirmed/MIL"), (0x08, "test failed this cycle"),
               (0x80, "warning indicator")]


def _status_words(byte: Any) -> list[str]:
    try:
        b = int(byte, 16) if isinstance(byte, str) else int(byte)
    except (TypeError, ValueError):
        return []
    return [label for bit, label in _STATUS_BITS if b & bit]


def _shape_dtc_list(payload: dict[str, Any]) -> dict[str, Any]:
    codes = payload.get("dtcs") or payload.get("codes") or []
    rows = []
    for c in codes:
        if isinstance(c, str):
            rows.append({"code": c, "description": None, "status": []})
        elif isinstance(c, dict):
            rows.append({"code": c.get("code") or c.get("dtc"),
                        "description": c.get("description"),
                        "status": _status_words(c.get("status") or c.get("status_byte"))})
    summary = f"{len(rows)} code(s) found" if rows else "No codes"
    return {"kind": "codes", "title": "Diagnostic trouble codes", "columns": None,
           "rows": rows, "summary": summary}


def _shape_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for scope in ("since_clear", "this_drive_cycle"):
        section = payload.get(scope) or {}
        for monitor, val in (section.get("monitors") or {}).items():
            rows.append({"scope": scope, "monitor": monitor,
                        "complete": "complete" if val else "incomplete"})
    verdict = payload.get("evap_verdict")
    summary = verdict.get("verdict") if isinstance(verdict, dict) else (
        "Readiness read" if rows else "No readiness data")
    return {"kind": "readiness", "title": "Readiness monitors", "columns": None,
           "rows": rows, "summary": summary}


def shape_result(tool_id: str, payload: Any) -> dict[str, Any]:
    """Render one tool's raw JSON payload into a page-friendly shape."""
    if not isinstance(payload, dict):
        return {"kind": "text", "title": tool_id, "columns": None, "rows": None,
               "summary": str(payload)[:200]}
    if "dtcs" in payload or (tool_id and "dtc" in tool_id.lower() and "codes" in payload):
        return _shape_dtc_list(payload)
    if "since_clear" in payload or "this_drive_cycle" in payload:
        return _shape_readiness(payload)
    if "fields" in payload and "ecu" in payload:
        rows = [{"field": k, "value": v} for k, v in (payload.get("fields") or {}).items()]
        return {"kind": "table", "title": "Module identity", "columns": ["field", "value"],
               "rows": rows, "summary": f"Identity for {payload.get('ecu')}"}
    if "volts" in payload:
        return {"kind": "kv", "title": "Voltage", "columns": None, "rows": None,
               "summary": f"{payload.get('volts')} V"}
    if isinstance(payload.get("entries"), list):
        rows = payload["entries"]
        return {"kind": "table", "title": tool_id, "columns": None, "rows": rows,
               "summary": f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}"}
    rows = [{"field": k, "value": v} for k, v in payload.items()
           if not isinstance(v, (dict, list))]
    return {"kind": "kv", "title": tool_id, "columns": None, "rows": rows,
           "summary": "; ".join(f"{r['field']}={r['value']}" for r in rows[:3]) or "No data"}


__all__ = ["CURATED", "GROUP_ORDER", "GROUP_BLURBS", "catalogue", "current_state", "suggest",
          "shape_result"]
