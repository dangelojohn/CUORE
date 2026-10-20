"""
OBD2 MCP Server

Main entry point. Registers all diagnostic tools with the MCP framework
so Claude can interact with the vehicle through natural language.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from .actuators import get_actuator_controller
from .config import get_config, load_config
from .connection import get_connection_manager
from .diagnostics import (
    get_supported_pids,
    get_vehicle_info,
    read_all_supported,
    read_dtcs,
    read_freeze_frame,
    read_o2_sensors,
    read_pending_dtcs,
    read_sensor,
    read_sensor_group,
    SENSOR_GROUPS,
)
from .multiecuscan import get_multiecuscan_parser

# ──────────────────────────────────────────────
#  Server Setup
# ──────────────────────────────────────────────

logger = logging.getLogger("obd2_mcp")

mcp = FastMCP(
    "OBD2 Vehicle Diagnostics",
    description=(
        "Connect to a vehicle's OBD2 port via USB or Bluetooth adapter (e.g., OBDLink MX++) "
        "to read live sensor data, diagnostic trouble codes, freeze frames, and vehicle info. "
        "Also integrates with Multiecuscan for deep Fiat/Alfa Romeo/Lancia diagnostics."
    ),
)


def _json(obj: Any) -> str:
    """Serialize result to JSON string for MCP response."""
    return json.dumps(obj, indent=2, default=str)


# ──────────────────────────────────────────────
#  Connection Tools
# ──────────────────────────────────────────────


@mcp.tool()
def connect_obd2(port: Optional[str] = None) -> str:
    """
    Connect to the OBD2 adapter.

    Args:
        port: COM port (e.g., 'COM3') or leave empty for auto-detect.
              Auto-detect will find USB and Bluetooth adapters including OBDLink MX++.

    Returns:
        Connection status including protocol, voltage, and supported commands.
    """
    mgr = get_connection_manager()
    status = mgr.connect(port=port)
    return _json({
        "connected": status.connected,
        "connection_type": status.connection_type.value,
        "port": status.port,
        "protocol": status.protocol,
        "elm_version": status.elm_version,
        "voltage": status.vehicle_voltage,
        "supported_commands": len(status.supported_commands),
        "error": status.error,
    })


@mcp.tool()
def disconnect_obd2() -> str:
    """Disconnect from the OBD2 adapter."""
    mgr = get_connection_manager()
    mgr.disconnect()
    return _json({"disconnected": True})


@mcp.tool()
def connection_status() -> str:
    """Check the current OBD2 connection status."""
    mgr = get_connection_manager()
    s = mgr.status
    return _json({
        "connected": s.connected,
        "connection_type": s.connection_type.value,
        "port": s.port,
        "protocol": s.protocol,
        "voltage": s.vehicle_voltage,
        "supported_commands": len(s.supported_commands),
        "error": s.error,
    })


@mcp.tool()
def discover_adapters() -> str:
    """
    Scan for available OBD2 adapters on all serial ports.
    Shows USB and Bluetooth devices with their details.
    """
    mgr = get_connection_manager()
    ports = mgr.discover_ports()
    return _json({"ports": ports, "count": len(ports)})


@mcp.tool()
def reconnect_obd2() -> str:
    """Reconnect to the OBD2 adapter (useful after connection drops)."""
    mgr = get_connection_manager()
    status = mgr.reconnect()
    return _json({
        "connected": status.connected,
        "port": status.port,
        "error": status.error,
    })


# ──────────────────────────────────────────────
#  Live Sensor Data Tools
# ──────────────────────────────────────────────


@mcp.tool()
def read_obd2_sensor(sensor_name: str) -> str:
    """
    Read a single OBD2 sensor value from the vehicle.

    Common sensors: RPM, SPEED, COOLANT_TEMP, THROTTLE_POS, ENGINE_LOAD,
    INTAKE_TEMP, MAF, FUEL_LEVEL, FUEL_PRESSURE, BAROMETRIC_PRESSURE,
    AMBIANT_AIR_TEMP, CONTROL_MODULE_VOLTAGE, TIMING_ADVANCE, INTAKE_PRESSURE

    Args:
        sensor_name: OBD2 PID name (e.g., 'RPM', 'SPEED', 'COOLANT_TEMP')
    """
    return _json(read_sensor(sensor_name))


@mcp.tool()
def read_obd2_sensor_group(group: str) -> str:
    """
    Read a predefined group of related sensors.

    Available groups:
    - engine: RPM, speed, throttle, load, temps, timing
    - fuel: fuel status, level, pressure, fuel trims
    - emissions: O2 sensors, catalyst temps, EGR, EVAP
    - performance: RPM, speed, throttle, accelerator position
    - status: readiness monitors, MIL status, distance

    Args:
        group: Group name (engine, fuel, emissions, performance, status)
    """
    return _json({"group": group, "readings": read_sensor_group(group)})


@mcp.tool()
def read_all_sensors() -> str:
    """Read ALL supported sensors from the connected vehicle. May take a few seconds."""
    return _json({"readings": read_all_supported()})


# ──────────────────────────────────────────────
#  Diagnostic Trouble Code Tools
# ──────────────────────────────────────────────


@mcp.tool()
def read_trouble_codes() -> str:
    """
    Read diagnostic trouble codes (DTCs) from the vehicle.

    Returns current DTCs, MIL (check engine light) status, and DTC count.
    For Fiat/Alfa/Lancia manufacturer-specific codes, use the Multiecuscan tools.
    """
    return _json(read_dtcs())


@mcp.tool()
def read_pending_trouble_codes() -> str:
    """Read pending (not yet confirmed) diagnostic trouble codes."""
    return _json(read_pending_dtcs())


@mcp.tool()
def read_freeze_frame_data() -> str:
    """
    Read freeze frame data - a snapshot of vehicle sensors captured
    at the moment a DTC was stored. Useful for diagnosing intermittent issues.
    """
    return _json(read_freeze_frame())


# ──────────────────────────────────────────────
#  Vehicle Information Tools
# ──────────────────────────────────────────────


@mcp.tool()
def vehicle_info() -> str:
    """
    Get vehicle identification and connection details.
    Includes OBD compliance, fuel type, protocol, adapter info.
    """
    return _json(get_vehicle_info())


@mcp.tool()
def list_supported_commands() -> str:
    """List all OBD2 commands/PIDs supported by the connected vehicle."""
    return _json(get_supported_pids())


@mcp.tool()
def read_o2_sensor_data() -> str:
    """Read all available oxygen sensor data for emissions diagnostics."""
    return _json({"o2_sensors": read_o2_sensors()})


# ──────────────────────────────────────────────
#  Actuator / Write Command Tools
# ──────────────────────────────────────────────


@mcp.tool()
def clear_trouble_codes(confirmed: bool = False) -> str:
    """
    Clear all diagnostic trouble codes and turn off the check engine light.

    ⚠️  WARNING: This clears ALL stored DTCs and resets emissions readiness monitors.
    The vehicle may need to complete drive cycles to re-set monitors for inspection.
    This is disabled by default - enable in config.json.

    Args:
        confirmed: Must be True to actually execute. Safety interlock.
    """
    ctrl = get_actuator_controller()
    return _json(ctrl.clear_dtcs(confirmed=confirmed))


@mcp.tool()
def send_raw_obd_command(command_hex: str, confirmed: bool = False) -> str:
    """
    Send a raw hex command to the ELM327/OBD adapter.

    ⚠️  ADVANCED: Only use this if you know the exact command to send.
    This bypasses normal safety checks. Disabled by default.

    Args:
        command_hex: Hex string (e.g., '01 00' for Mode 01 PID 00)
        confirmed: Must be True to execute.
    """
    ctrl = get_actuator_controller()
    return _json(ctrl.send_raw_command(command_hex, confirmed=confirmed))


@mcp.tool()
def actuator_safety_status() -> str:
    """Check current safety configuration for actuator/write commands."""
    ctrl = get_actuator_controller()
    return _json(ctrl.get_safety_status())


@mcp.tool()
def actuator_command_history() -> str:
    """View history of all actuator commands sent during this session."""
    ctrl = get_actuator_controller()
    return _json({"commands": ctrl.get_command_history()})


# ──────────────────────────────────────────────
#  Multiecuscan Integration Tools
# ──────────────────────────────────────────────


@mcp.tool()
def multiecuscan_status() -> str:
    """
    Check Multiecuscan installation and integration status.
    Shows if the application is installed and where log/export files are.
    """
    parser = get_multiecuscan_parser()
    return _json(parser.get_status())


@mcp.tool()
def multiecuscan_list_logs(limit: int = 20) -> str:
    """
    List available Multiecuscan diagnostic session logs.

    Args:
        limit: Maximum number of files to return (default 20, newest first)
    """
    parser = get_multiecuscan_parser()
    files = parser.list_log_files(limit=limit)
    return _json({"log_files": files, "count": len(files)})


@mcp.tool()
def multiecuscan_list_exports(limit: int = 20) -> str:
    """
    List available Multiecuscan CSV/XML export files.

    Args:
        limit: Maximum number of files to return (default 20, newest first)
    """
    parser = get_multiecuscan_parser()
    files = parser.list_export_files(limit=limit)
    return _json({"export_files": files, "count": len(files)})


@mcp.tool()
def multiecuscan_read_log(filepath: str) -> str:
    """
    Parse a Multiecuscan log file and extract DTCs, parameters, and vehicle info.

    Use multiecuscan_list_logs to find available files first.

    Args:
        filepath: Full path to the .log file
    """
    parser = get_multiecuscan_parser()
    try:
        session = parser.parse_log_file(filepath)
        return _json({
            "filename": session.filename,
            "timestamp": session.timestamp.isoformat(),
            "vehicle": session.vehicle,
            "ecu": session.ecu,
            "dtcs": [
                {"code": d.code, "description": d.description, "status": d.status, "ecu": d.ecu}
                for d in session.dtcs
            ],
            "parameters": session.parameters,
            "raw_log_preview": session.raw_log[:2000],
        })
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def multiecuscan_read_csv(filepath: str) -> str:
    """
    Parse a Multiecuscan CSV export and show summary statistics.

    Use multiecuscan_list_exports to find available files first.

    Args:
        filepath: Full path to the .csv file
    """
    parser = get_multiecuscan_parser()
    try:
        return _json(parser.parse_csv_export(filepath))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def multiecuscan_read_xml(filepath: str) -> str:
    """
    Parse a Multiecuscan XML export.

    Args:
        filepath: Full path to the .xml file
    """
    parser = get_multiecuscan_parser()
    try:
        return _json(parser.parse_xml_export(filepath))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def multiecuscan_latest_session() -> str:
    """
    Read the most recent Multiecuscan diagnostic session.
    Quickly see what was found in the last scan.
    """
    parser = get_multiecuscan_parser()
    return _json(parser.get_latest_session())


@mcp.tool()
def multiecuscan_search_dtc(dtc_code: Optional[str] = None) -> str:
    """
    Search for a specific DTC across all Multiecuscan session history.

    Args:
        dtc_code: DTC to search for (e.g., 'P0300'). Leave empty to list all DTCs found.
    """
    parser = get_multiecuscan_parser()
    results = parser.search_dtcs_across_sessions(dtc_code)
    return _json({
        "search_code": dtc_code or "ALL",
        "matches": results,
        "total_found": len(results),
    })


# ──────────────────────────────────────────────
#  Utility / Meta Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_sensor_groups() -> str:
    """List all available sensor groups and their contents."""
    return _json(SENSOR_GROUPS)


@mcp.tool()
def get_obd2_help(topic: Optional[str] = None) -> str:
    """
    Get help on using the OBD2 diagnostic tools.

    Args:
        topic: Optional topic - 'connection', 'sensors', 'dtcs', 'multiecuscan', 'safety', or 'all'
    """
    help_text = {
        "connection": {
            "description": "Connecting to your vehicle",
            "steps": [
                "1. Plug OBD2 adapter into vehicle's OBD2 port (under dashboard)",
                "2. Turn ignition to ON (engine can be off or running)",
                "3. If using Bluetooth (OBDLink MX++), ensure it's paired with this computer",
                "4. Use connect_obd2() to auto-detect, or specify a COM port",
                "5. Use discover_adapters() to see all available serial ports",
            ],
        },
        "sensors": {
            "description": "Reading live vehicle data",
            "steps": [
                "Use read_obd2_sensor('RPM') for a single sensor",
                "Use read_obd2_sensor_group('engine') for related sensors",
                "Use read_all_sensors() for everything the vehicle supports",
                "Use list_supported_commands() to see what your vehicle supports",
            ],
            "groups": list(SENSOR_GROUPS.keys()),
        },
        "dtcs": {
            "description": "Diagnostic Trouble Codes",
            "steps": [
                "Use read_trouble_codes() to see current DTCs and check engine light status",
                "Use read_pending_trouble_codes() for codes not yet confirmed",
                "Use read_freeze_frame_data() to see conditions when a DTC was set",
                "Use clear_trouble_codes(confirmed=True) to clear (if enabled in config)",
            ],
        },
        "multiecuscan": {
            "description": "Multiecuscan Integration for Fiat/Alfa/Lancia",
            "steps": [
                "Use multiecuscan_status() to check if Multiecuscan is detected",
                "Use multiecuscan_latest_session() to see the most recent scan",
                "Use multiecuscan_list_logs() and multiecuscan_read_log() for session history",
                "Use multiecuscan_search_dtc('P0300') to find a specific code across sessions",
                "Run a scan in Multiecuscan first, then use these tools to analyze results",
            ],
        },
        "safety": {
            "description": "Safety configuration for write commands",
            "steps": [
                "Actuator commands and DTC clearing are DISABLED by default",
                "Edit config.json to enable: safety.allow_actuator_commands = true",
                "All write commands require confirmed=True parameter",
                "Cooldown timer prevents rapid-fire commands",
                "Use actuator_safety_status() to see current settings",
            ],
        },
    }

    if topic and topic != "all" and topic in help_text:
        return _json(help_text[topic])
    return _json(help_text)


# ──────────────────────────────────────────────
#  Entry Point
# ──────────────────────────────────────────────


def main():
    """Start the OBD2 MCP Server."""
    # Setup logging
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(config.logging.file, mode="a"),
        ],
    )
    logger.info("Starting OBD2 MCP Server...")
    mcp.run()


if __name__ == "__main__":
    main()
