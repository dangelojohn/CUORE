"""
OBD2 Connection Manager

Handles connecting to the OBD2 adapter via USB serial or Bluetooth.
Supports the OBDLink MX++ and other ELM327-compatible adapters.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import obd
import serial.tools.list_ports

from .config import get_config

logger = logging.getLogger(__name__)


class ConnectionType(str, Enum):
    USB = "usb"
    BLUETOOTH = "bluetooth"
    UNKNOWN = "unknown"


@dataclass
class ConnectionStatus:
    """Current state of the OBD2 connection."""

    connected: bool = False
    connection_type: ConnectionType = ConnectionType.UNKNOWN
    port: str = ""
    protocol: str = ""
    vehicle_voltage: str = ""
    elm_version: str = ""
    supported_commands: list[str] = field(default_factory=list)
    error: str = ""


class OBD2ConnectionManager:
    """
    Manages the lifecycle of the OBD2 adapter connection.

    Supports:
    - Auto-detection of COM ports (USB and Bluetooth serial)
    - Manual port specification
    - Connection health monitoring
    - Reconnection logic
    """

    def __init__(self):
        self._connection: Optional[obd.OBD] = None
        self._status = ConnectionStatus()
        self._config = get_config()

    @property
    def connection(self) -> Optional[obd.OBD]:
        return self._connection

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.is_connected()

    def discover_ports(self) -> list[dict]:
        """
        List all available serial ports with metadata.
        Useful for finding the OBD2 adapter.
        """
        ports = []
        for port_info in serial.tools.list_ports.comports():
            port_data = {
                "device": port_info.device,
                "description": port_info.description,
                "manufacturer": port_info.manufacturer or "Unknown",
                "vid": port_info.vid,
                "pid": port_info.pid,
                "serial_number": port_info.serial_number or "",
                "is_bluetooth": "bluetooth" in (port_info.description or "").lower()
                or "bthenum" in (port_info.hwid or "").lower(),
            }
            ports.append(port_data)
        return ports

    def _detect_connection_type(self, port: str) -> ConnectionType:
        """Determine if a port is USB or Bluetooth."""
        ports = self.discover_ports()
        for p in ports:
            if p["device"] == port:
                return ConnectionType.BLUETOOTH if p["is_bluetooth"] else ConnectionType.USB
        return ConnectionType.UNKNOWN

    def _find_obd_port(self) -> Optional[str]:
        """
        Auto-detect the OBD2 adapter port.
        Tries to identify OBDLink or ELM327 devices by their USB VID/PID
        or Bluetooth device names.
        """
        ports = self.discover_ports()

        # Known OBDLink VID/PID pairs
        known_adapters = [
            (0x0403, 0x6015),  # OBDLink SX / MX (FTDI)
            (0x0403, 0x6001),  # Generic FTDI (many ELM327 clones)
            (0x1A86, 0xE015),  # OBDLink MX+ (direct USB)
        ]

        # Priority 1: Known adapter VID/PID
        for port_info in ports:
            if port_info["vid"] and port_info["pid"]:
                for vid, pid in known_adapters:
                    if port_info["vid"] == vid and port_info["pid"] == pid:
                        logger.info(f"Found known OBD adapter: {port_info['device']} ({port_info['description']})")
                        return port_info["device"]

        # Priority 2: Bluetooth port matching configured device name
        bt_config = self._config.bluetooth
        if bt_config.enabled:
            for port_info in ports:
                if port_info["is_bluetooth"]:
                    desc = (port_info["description"] or "").lower()
                    if bt_config.device_name.lower() in desc:
                        logger.info(f"Found Bluetooth OBD adapter: {port_info['device']}")
                        return port_info["device"]

        # Priority 3: Any Bluetooth serial port
        if bt_config.enabled:
            for port_info in ports:
                if port_info["is_bluetooth"]:
                    logger.info(f"Trying Bluetooth port: {port_info['device']}")
                    return port_info["device"]

        # Priority 4: Any port with "OBD" in description
        for port_info in ports:
            if "obd" in (port_info["description"] or "").lower():
                logger.info(f"Found port with OBD in description: {port_info['device']}")
                return port_info["device"]

        logger.warning("No OBD2 adapter detected on any serial port")
        return None

    def connect(self, port: Optional[str] = None) -> ConnectionStatus:
        """
        Establish connection to the OBD2 adapter.

        Args:
            port: Specific COM port (e.g., 'COM3'). If None, auto-detects.

        Returns:
            ConnectionStatus with current state.
        """
        cfg = self._config.obd2

        # Resolve port
        target_port = port or (cfg.port if cfg.port != "auto" else None) or self._find_obd_port()

        if not target_port:
            self._status = ConnectionStatus(
                connected=False,
                error="No OBD2 adapter found. Ensure adapter is plugged in and paired (if Bluetooth).",
            )
            return self._status

        logger.info(f"Connecting to OBD2 adapter on {target_port}...")

        try:
            # Disconnect existing connection if any
            self.disconnect()

            # Determine protocol
            protocol = None if cfg.protocol == "auto" else cfg.protocol

            self._connection = obd.OBD(
                portstr=target_port,
                baudrate=cfg.baudrate,
                protocol=protocol,
                fast=cfg.fast,
                timeout=cfg.timeout,
            )

            if self._connection.is_connected():
                conn_type = self._detect_connection_type(target_port)

                # Gather connection details
                supported = [cmd.name for cmd in self._connection.supported_commands]

                self._status = ConnectionStatus(
                    connected=True,
                    connection_type=conn_type,
                    port=target_port,
                    protocol=str(self._connection.protocol_name()),
                    elm_version=str(self._connection.query(obd.commands.ELM_VERSION).value or ""),
                    vehicle_voltage=str(self._connection.query(obd.commands.ELM_VOLTAGE).value or ""),
                    supported_commands=supported,
                )
                logger.info(
                    f"Connected via {conn_type.value} on {target_port}, "
                    f"protocol: {self._status.protocol}, "
                    f"{len(supported)} commands supported"
                )
            else:
                self._status = ConnectionStatus(
                    connected=False,
                    port=target_port,
                    error="Connection established but vehicle not responding. Is ignition on?",
                )
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._status = ConnectionStatus(
                connected=False,
                port=target_port,
                error=f"Connection error: {str(e)}",
            )

        return self._status

    def disconnect(self):
        """Close the OBD2 connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._connection = None
                self._status = ConnectionStatus()
                logger.info("Disconnected from OBD2 adapter")

    def reconnect(self) -> ConnectionStatus:
        """Attempt to reconnect using the last known port."""
        last_port = self._status.port
        self.disconnect()
        time.sleep(1)
        return self.connect(port=last_port if last_port else None)

    def query(self, command: obd.OBDCommand) -> obd.OBDResponse:
        """
        Execute an OBD2 query with connection validation.

        Raises:
            ConnectionError: If not connected to a vehicle.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OBD2 adapter. Call connect() first.")
        return self._connection.query(command)

    def query_by_name(self, command_name: str) -> obd.OBDResponse:
        """Query by command name string (e.g., 'RPM', 'SPEED')."""
        if not self.is_connected:
            raise ConnectionError("Not connected to OBD2 adapter.")

        # Look up the command by name
        if hasattr(obd.commands, command_name.upper()):
            cmd = getattr(obd.commands, command_name.upper())
            return self._connection.query(cmd)
        else:
            raise ValueError(f"Unknown OBD2 command: {command_name}")


# Module-level singleton
_manager: Optional[OBD2ConnectionManager] = None


def get_connection_manager() -> OBD2ConnectionManager:
    """Get the global connection manager instance."""
    global _manager
    if _manager is None:
        _manager = OBD2ConnectionManager()
    return _manager
