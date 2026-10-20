"""
Actuator Commands & Write Operations

Provides controlled access to vehicle actuator tests and write commands.
All operations are gated by safety configuration and require explicit confirmation.

⚠️  WARNING: Actuator commands send real signals to the vehicle.
    Misuse can cause damage or unsafe conditions. These are disabled by default.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import obd

from .config import get_config
from .connection import get_connection_manager

logger = logging.getLogger(__name__)


class SafetyError(Exception):
    """Raised when a command is blocked by safety configuration."""
    pass


class CooldownError(Exception):
    """Raised when a command is sent too soon after the previous one."""
    pass


class ActuatorController:
    """
    Manages actuator commands with safety interlocks.

    Safety features:
    - Global enable/disable for actuator commands
    - Per-command confirmation requirement
    - Cooldown timer between commands
    - Logging of all command attempts
    """

    def __init__(self):
        self._config = get_config().safety
        self._last_command_time: float = 0.0
        self._command_history: list[dict[str, Any]] = []

    def _check_safety(self, command_name: str, confirmed: bool = False) -> None:
        """
        Validate that a command is allowed to execute.

        Raises:
            SafetyError: If actuator commands are disabled or confirmation missing.
            CooldownError: If cooldown period hasn't elapsed.
        """
        if not self._config.allow_actuator_commands:
            raise SafetyError(
                f"Actuator commands are DISABLED in configuration. "
                f"To enable, set safety.allow_actuator_commands=true in config.json. "
                f"Command '{command_name}' was blocked."
            )

        if self._config.require_confirmation_for_writes and not confirmed:
            raise SafetyError(
                f"Command '{command_name}' requires explicit confirmation. "
                f"Pass confirmed=True to execute. This sends a real command to the vehicle."
            )

        # Check cooldown
        elapsed = time.time() - self._last_command_time
        if elapsed < self._config.command_cooldown_seconds:
            remaining = self._config.command_cooldown_seconds - elapsed
            raise CooldownError(
                f"Cooldown active. Wait {remaining:.1f}s before sending another command."
            )

    def _log_command(self, command_name: str, success: bool, result: Any = None, error: str = "") -> None:
        """Record command execution in history."""
        entry = {
            "command": command_name,
            "timestamp": time.time(),
            "success": success,
            "result": str(result) if result else "",
            "error": error,
        }
        self._command_history.append(entry)
        logger.info(f"Actuator command: {entry}")

    def clear_dtcs(self, confirmed: bool = False) -> dict[str, Any]:
        """
        Clear all diagnostic trouble codes and reset the MIL.

        ⚠️  This clears ALL stored DTCs and resets emissions readiness monitors.
            The vehicle may need to complete drive cycles to re-set monitors.

        Args:
            confirmed: Must be True to execute.
        """
        config = get_config().safety
        if not config.allow_dtc_clear:
            return {
                "success": False,
                "error": "DTC clearing is DISABLED. Set safety.allow_dtc_clear=true in config.json.",
            }

        try:
            self._check_safety("CLEAR_DTC", confirmed)
        except (SafetyError, CooldownError) as e:
            return {"success": False, "error": str(e)}

        mgr = get_connection_manager()
        if not mgr.is_connected:
            return {"success": False, "error": "Not connected to vehicle"}

        try:
            resp = mgr.query(obd.commands.CLEAR_DTC)
            self._last_command_time = time.time()
            self._log_command("CLEAR_DTC", True, resp.value)
            return {
                "success": True,
                "message": "DTCs cleared. MIL should turn off. Emissions monitors have been reset.",
                "warning": "Vehicle will need drive cycles to re-set emissions readiness monitors.",
            }
        except Exception as e:
            self._log_command("CLEAR_DTC", False, error=str(e))
            return {"success": False, "error": f"Failed to clear DTCs: {str(e)}"}

    def send_raw_command(self, command_hex: str, confirmed: bool = False) -> dict[str, Any]:
        """
        Send a raw hex command to the ELM327 adapter.

        ⚠️  ADVANCED: This sends arbitrary commands to the adapter/ECU.
            Only use if you know exactly what you're doing.

        Args:
            command_hex: Raw hex string (e.g., "01 00" for Mode 01 PID 00)
            confirmed: Must be True to execute.
        """
        try:
            self._check_safety(f"RAW:{command_hex}", confirmed)
        except (SafetyError, CooldownError) as e:
            return {"success": False, "error": str(e)}

        mgr = get_connection_manager()
        if not mgr.is_connected:
            return {"success": False, "error": "Not connected to vehicle"}

        try:
            # Create a custom command
            custom_cmd = obd.OBDCommand(
                name="CUSTOM",
                desc=f"Custom command: {command_hex}",
                command=bytes.fromhex(command_hex.replace(" ", "")),
                bytes=0,
                decoder=obd.decoders.raw_string,
                eco=False,
                fast=False,
            )
            resp = mgr.connection.query(custom_cmd, force=True)
            self._last_command_time = time.time()

            result = str(resp.value) if not resp.is_null() else "No response"
            self._log_command(f"RAW:{command_hex}", True, result)
            return {
                "success": True,
                "command_sent": command_hex,
                "raw_response": result,
            }
        except Exception as e:
            self._log_command(f"RAW:{command_hex}", False, error=str(e))
            return {"success": False, "error": f"Raw command failed: {str(e)}"}

    def get_command_history(self) -> list[dict[str, Any]]:
        """Return the history of all actuator commands sent this session."""
        return list(self._command_history)

    def get_safety_status(self) -> dict[str, Any]:
        """Report current safety configuration."""
        config = get_config().safety
        return {
            "actuator_commands_enabled": config.allow_actuator_commands,
            "dtc_clear_enabled": config.allow_dtc_clear,
            "confirmation_required": config.require_confirmation_for_writes,
            "cooldown_seconds": config.command_cooldown_seconds,
            "commands_sent_this_session": len(self._command_history),
            "last_command_age_seconds": (
                round(time.time() - self._last_command_time, 1)
                if self._last_command_time > 0
                else None
            ),
        }


# Module-level singleton
_controller: Optional[ActuatorController] = None


def get_actuator_controller() -> ActuatorController:
    """Get the global actuator controller instance."""
    global _controller
    if _controller is None:
        _controller = ActuatorController()
    return _controller
