"""
Configuration management for the OBD2 MCP Server.
Loads settings from config.json with sensible defaults.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent.parent / "config.json"


class OBD2Config(BaseModel):
    """OBD2 adapter connection settings."""

    port: str = Field(default="auto", description="COM port or 'auto' for auto-detect")
    baudrate: int = Field(default=115200, description="Serial baud rate")
    protocol: str = Field(default="auto", description="OBD protocol or 'auto'")
    timeout: int = Field(default=10, description="Connection timeout in seconds")
    fast: bool = Field(default=True, description="Use fast OBD2 mode")


class BluetoothConfig(BaseModel):
    """Bluetooth adapter settings (e.g., OBDLink MX++)."""

    enabled: bool = Field(default=True, description="Enable Bluetooth adapter support")
    device_name: str = Field(default="OBDLink MX+", description="Bluetooth device name")
    mac_address: str = Field(default="", description="MAC address (optional, for direct pairing)")


class MultiecuscanConfig(BaseModel):
    """Multiecuscan application integration settings."""

    install_path: str = Field(
        default=r"C:\Program Files (x86)\Multiecuscan",
        description="Multiecuscan installation directory",
    )
    log_directory: str = Field(
        default=r"C:\Users\Public\Documents\Multiecuscan\Logs",
        description="Directory where Multiecuscan writes log files",
    )
    export_directory: str = Field(
        default=r"C:\Users\Public\Documents\Multiecuscan\Exports",
        description="Directory for Multiecuscan CSV/XML exports",
    )
    watch_logs: bool = Field(default=True, description="Watch log directory for new files")


class SafetyConfig(BaseModel):
    """Safety guards for actuator commands and writes."""

    allow_actuator_commands: bool = Field(
        default=False,
        description="Allow sending actuator test commands to the vehicle",
    )
    allow_dtc_clear: bool = Field(
        default=False,
        description="Allow clearing diagnostic trouble codes",
    )
    require_confirmation_for_writes: bool = Field(
        default=True,
        description="Require explicit confirmation before any write command",
    )
    command_cooldown_seconds: int = Field(
        default=5,
        description="Minimum seconds between actuator commands",
    )


class LoggingConfig(BaseModel):
    """Logging settings."""

    level: str = Field(default="INFO", description="Log level")
    file: str = Field(default="obd2_mcp.log", description="Log file path")


class AppConfig(BaseSettings):
    """Root application configuration."""

    obd2: OBD2Config = Field(default_factory=OBD2Config)
    bluetooth: BluetoothConfig = Field(default_factory=BluetoothConfig)
    multiecuscan: MultiecuscanConfig = Field(default_factory=MultiecuscanConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """Load configuration from JSON file, falling back to defaults."""
    path = config_path or CONFIG_FILE
    if path.exists():
        logger.info(f"Loading configuration from {path}")
        with open(path, "r") as f:
            data = json.load(f)
        return AppConfig(**data)
    else:
        logger.warning(f"Config file not found at {path}, using defaults")
        return AppConfig()


# Singleton config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
