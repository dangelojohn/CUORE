"""
OBD2 Diagnostic Tools

Provides high-level diagnostic functions: live sensor data, DTCs,
freeze frame data, vehicle info, and O2 sensor tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import obd
from obd import OBDStatus

from .connection import get_connection_manager

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Live Sensor Data
# ──────────────────────────────────────────────

# Common sensor groups for convenience
SENSOR_GROUPS = {
    "engine": [
        "RPM", "SPEED", "THROTTLE_POS", "ENGINE_LOAD",
        "COOLANT_TEMP", "INTAKE_TEMP", "INTAKE_PRESSURE",
        "TIMING_ADVANCE", "MAF", "RUN_TIME",
    ],
    "fuel": [
        "FUEL_STATUS", "FUEL_LEVEL", "FUEL_PRESSURE",
        "SHORT_FUEL_TRIM_1", "LONG_FUEL_TRIM_1",
        "SHORT_FUEL_TRIM_2", "LONG_FUEL_TRIM_2",
        "FUEL_RAIL_PRESSURE_DIRECT", "FUEL_RAIL_PRESSURE_VAC",
        "ETHANOL_PERCENT", "FUEL_TYPE",
    ],
    "emissions": [
        "O2_B1S1", "O2_B1S2", "O2_B2S1", "O2_B2S2",
        "CATALYST_TEMP_B1S1", "CATALYST_TEMP_B1S2",
        "CATALYST_TEMP_B2S1", "CATALYST_TEMP_B2S2",
        "EVAP_VAPOR_PRESSURE", "COMMANDED_EGR",
    ],
    "performance": [
        "RPM", "SPEED", "THROTTLE_POS", "ENGINE_LOAD",
        "THROTTLE_ACTUATOR", "ACCELERATOR_POS_D",
        "ACCELERATOR_POS_E", "BAROMETRIC_PRESSURE",
        "AMBIANT_AIR_TEMP", "CONTROL_MODULE_VOLTAGE",
    ],
    "status": [
        "STATUS", "FREEZE_DTC", "FUEL_STATUS",
        "OBD_COMPLIANCE", "RUN_TIME", "DISTANCE_W_MIL",
        "DISTANCE_SINCE_DTC_CLEAR", "WARMUPS_SINCE_DTC_CLEAR",
        "PIDS_A", "PIDS_B", "PIDS_C",
    ],
}


def read_sensor(sensor_name: str) -> dict[str, Any]:
    """
    Read a single OBD2 sensor value.

    Args:
        sensor_name: OBD2 PID name (e.g., 'RPM', 'SPEED', 'COOLANT_TEMP')

    Returns:
        Dict with sensor name, value, unit, and timestamp.
    """
    mgr = get_connection_manager()
    try:
        response = mgr.query_by_name(sensor_name)
        if response.is_null():
            return {
                "sensor": sensor_name,
                "value": None,
                "unit": "",
                "error": "No data (sensor may not be supported by this vehicle)",
            }

        value = response.value
        # Handle pint Quantity objects
        if hasattr(value, "magnitude"):
            return {
                "sensor": sensor_name,
                "value": round(float(value.magnitude), 2),
                "unit": str(value.units),
            }
        else:
            return {
                "sensor": sensor_name,
                "value": str(value),
                "unit": "",
            }
    except Exception as e:
        return {"sensor": sensor_name, "value": None, "error": str(e)}


def read_sensor_group(group: str) -> list[dict[str, Any]]:
    """
    Read a predefined group of sensors.

    Args:
        group: One of 'engine', 'fuel', 'emissions', 'performance', 'status'

    Returns:
        List of sensor readings.
    """
    if group not in SENSOR_GROUPS:
        return [{"error": f"Unknown group '{group}'. Available: {list(SENSOR_GROUPS.keys())}"}]

    results = []
    for sensor_name in SENSOR_GROUPS[group]:
        results.append(read_sensor(sensor_name))
    return results


def read_all_supported() -> list[dict[str, Any]]:
    """Read all supported sensors from the connected vehicle."""
    mgr = get_connection_manager()
    if not mgr.is_connected:
        return [{"error": "Not connected to vehicle"}]

    results = []
    for cmd in mgr.connection.supported_commands:
        if cmd.name.startswith("PIDS_"):
            continue  # Skip PID support queries
        reading = read_sensor(cmd.name)
        if reading.get("value") is not None:
            results.append(reading)
    return results


# ──────────────────────────────────────────────
#  Diagnostic Trouble Codes (DTCs)
# ──────────────────────────────────────────────

# DTC type prefixes
DTC_TYPES = {
    "P": "Powertrain",
    "C": "Chassis",
    "B": "Body",
    "U": "Network/Communication",
}


def read_dtcs() -> dict[str, Any]:
    """
    Read current diagnostic trouble codes from the vehicle.

    Returns:
        Dict with DTC list, count, and MIL (check engine light) status.
    """
    mgr = get_connection_manager()
    if not mgr.is_connected:
        return {"error": "Not connected to vehicle"}

    try:
        # Read status (includes MIL state and DTC count)
        status_resp = mgr.query(obd.commands.STATUS)
        mil_on = False
        dtc_count = 0
        if not status_resp.is_null():
            mil_on = status_resp.value.MIL
            dtc_count = status_resp.value.DTC_count

        # Read actual DTCs
        dtc_resp = mgr.query(obd.commands.GET_DTC)
        dtcs = []
        if not dtc_resp.is_null() and dtc_resp.value:
            for code, description in dtc_resp.value:
                dtc_type = DTC_TYPES.get(code[0], "Unknown")
                dtcs.append({
                    "code": code,
                    "description": description or "No description available",
                    "type": dtc_type,
                })

        return {
            "mil_on": mil_on,
            "dtc_count": dtc_count,
            "dtcs": dtcs,
            "note": "Use Multiecuscan for manufacturer-specific codes on Fiat/Alfa/Lancia vehicles",
        }
    except Exception as e:
        return {"error": f"Failed to read DTCs: {str(e)}"}


def read_pending_dtcs() -> dict[str, Any]:
    """Read pending (not yet confirmed) diagnostic trouble codes."""
    mgr = get_connection_manager()
    if not mgr.is_connected:
        return {"error": "Not connected to vehicle"}

    try:
        resp = mgr.query(obd.commands.GET_CURRENT_DTC)
        dtcs = []
        if not resp.is_null() and resp.value:
            for code, description in resp.value:
                dtc_type = DTC_TYPES.get(code[0], "Unknown")
                dtcs.append({
                    "code": code,
                    "description": description or "No description available",
                    "type": dtc_type,
                    "status": "pending",
                })
        return {"pending_dtcs": dtcs, "count": len(dtcs)}
    except Exception as e:
        return {"error": f"Failed to read pending DTCs: {str(e)}"}


def read_freeze_frame() -> dict[str, Any]:
    """
    Read freeze frame data captured when a DTC was set.

    Freeze frame preserves the vehicle state at the moment a fault occurred.
    """
    mgr = get_connection_manager()
    if not mgr.is_connected:
        return {"error": "Not connected to vehicle"}

    try:
        freeze_dtc = mgr.query(obd.commands.FREEZE_DTC)
        freeze_data = {}

        if not freeze_dtc.is_null():
            freeze_data["trigger_dtc"] = str(freeze_dtc.value)

        # Read key sensors from freeze frame (Mode 02)
        freeze_sensors = [
            "COOLANT_TEMP", "ENGINE_LOAD", "RPM", "SPEED",
            "TIMING_ADVANCE", "INTAKE_TEMP", "MAF",
            "THROTTLE_POS", "SHORT_FUEL_TRIM_1", "LONG_FUEL_TRIM_1",
        ]

        sensor_readings = {}
        for sensor in freeze_sensors:
            reading = read_sensor(sensor)
            if reading.get("value") is not None:
                sensor_readings[sensor] = reading

        freeze_data["sensor_snapshot"] = sensor_readings
        return freeze_data
    except Exception as e:
        return {"error": f"Failed to read freeze frame: {str(e)}"}


# ──────────────────────────────────────────────
#  Vehicle Information
# ──────────────────────────────────────────────

def get_vehicle_info() -> dict[str, Any]:
    """
    Read vehicle identification information.

    Returns VIN, ECU name, OBD compliance standard, etc.
    """
    mgr = get_connection_manager()
    if not mgr.is_connected:
        return {"error": "Not connected to vehicle"}

    info = {}

    # Try to read various vehicle info commands
    info_commands = {
        "obd_compliance": "OBD_COMPLIANCE",
        "fuel_type": "FUEL_TYPE",
    }

    for key, cmd_name in info_commands.items():
        try:
            if hasattr(obd.commands, cmd_name):
                resp = mgr.query(getattr(obd.commands, cmd_name))
                if not resp.is_null():
                    val = resp.value
                    info[key] = str(val.magnitude if hasattr(val, "magnitude") else val)
        except Exception:
            pass

    # Connection metadata
    status = mgr.status
    info["protocol"] = status.protocol
    info["elm_version"] = status.elm_version
    info["voltage"] = status.vehicle_voltage
    info["connection_type"] = status.connection_type.value
    info["port"] = status.port
    info["supported_command_count"] = len(status.supported_commands)

    return info


def get_supported_pids() -> dict[str, Any]:
    """List all OBD2 PIDs supported by the connected vehicle."""
    mgr = get_connection_manager()
    if not mgr.is_connected:
        return {"error": "Not connected to vehicle"}

    commands = []
    for cmd in mgr.connection.supported_commands:
        commands.append({
            "name": cmd.name,
            "description": cmd.desc,
            "mode": cmd.mode,
            "pid": cmd.pid,
        })

    return {
        "total_supported": len(commands),
        "commands": sorted(commands, key=lambda c: (c["mode"], c["name"])),
    }


# ──────────────────────────────────────────────
#  O2 Sensor Tests
# ──────────────────────────────────────────────

def read_o2_sensors() -> list[dict[str, Any]]:
    """Read all available O2 sensor data."""
    o2_commands = [
        "O2_B1S1", "O2_B1S2", "O2_B1S3", "O2_B1S4",
        "O2_B2S1", "O2_B2S2", "O2_B2S3", "O2_B2S4",
        "O2_S1_WR_VOLTAGE", "O2_S2_WR_VOLTAGE",
        "O2_S3_WR_VOLTAGE", "O2_S4_WR_VOLTAGE",
        "O2_S1_WR_CURRENT", "O2_S2_WR_CURRENT",
        "O2_S3_WR_CURRENT", "O2_S4_WR_CURRENT",
    ]

    results = []
    for sensor in o2_commands:
        reading = read_sensor(sensor)
        if reading.get("value") is not None:
            results.append(reading)

    if not results:
        return [{"note": "No O2 sensor data available from this vehicle"}]
    return results
