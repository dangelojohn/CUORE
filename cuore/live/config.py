"""Where the port, speed and cable come from.

Precedence, most specific first:

1. an explicit argument on the call;
2. ``CUORE_OBD_PORT`` / ``CUORE_OBD_BAUD`` / ``CUORE_OBD_CABLE`` (this service's
   own settings tier);
3. ``OBD_PORT`` / ``OBD_BAUD`` (the obd2-mcp registration, kept for
   compatibility);
4. MultiEcuScan's own ``HKLM\\SOFTWARE\\Multiecuscan`` Interface 0 settings,
   readable without elevation;
5. the ELM327 fallback speed, and no port.

MES's registry is also where its log and export folders and CSV separator
live, which is why :func:`mes_folders` sits here rather than in ``mes.paths``:
this module is the one place that knows the registry key.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

IS_WINDOWS = sys.platform == "win32"
FALLBACK_BAUD = 38400
MES_INSTALL = r"C:\Program Files (x86)\Multiecuscan"
MES_REG_PATH = r"SOFTWARE\Multiecuscan"
_REDACTED_PREFIXES = ("Lic Number", "Removal Key")


def mes_registry() -> dict[str, Any]:
    """Read MES's settings key (64-bit view). Empty if absent or not Windows.

    Licence fields are redacted before they leave this function.
    """
    if not IS_WINDOWS:
        return {}
    import winreg

    out: dict[str, Any] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, MES_REG_PATH, 0,
                             winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except OSError:
        return {}
    with key:
        i = 0
        while True:
            try:
                name, value, _kind = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if any(name.startswith(p) for p in _REDACTED_PREFIXES):
                value = "<redacted>"
            out[name] = value
    return out


def mes_folders(reg: dict[str, Any] | None = None) -> dict[str, str]:
    """MES's LOG and Export folders resolved to absolute paths, plus the CSV separator."""
    reg = mes_registry() if reg is None else reg
    out: dict[str, str] = {}
    for key, label in (("LOG Folder", "log_folder"), ("Export Folder", "csv_folder")):
        raw = str(reg.get(key, "") or "")
        if not raw or raw == ".":
            out[label] = MES_INSTALL
        else:
            out[label] = raw if os.path.isabs(raw) else str(Path(MES_INSTALL, raw))
    out["csv_separator"] = str(reg.get("CSV Separator", "") or "")
    return out


def mes_interfaces(reg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    reg = mes_registry() if reg is None else reg
    out = []
    for i in range(5):
        if f"Interface {i} Port" in reg:
            out.append({"index": i, "type_ex": reg.get(f"Interface {i} Type Ex"),
                        "port": reg.get(f"Interface {i} Port"),
                        "speed": reg.get(f"Interface {i} Port Speed")})
    return out


def _env(*names: str) -> tuple[Optional[str], str]:
    for n in names:
        v = os.environ.get(n)
        if v and v.strip():
            return v.strip(), f"env {n}"
    return None, ""


def resolve_port(arg: str = "") -> tuple[Optional[str], str]:
    """Port to use and where the decision came from."""
    if arg and arg.strip():
        return arg.strip().upper(), "argument"
    v, src = _env("CUORE_OBD_PORT", "OBD_PORT")
    if v:
        return v.upper(), src
    port = mes_registry().get("Interface 0 Port")
    if port:
        return str(port).strip().upper(), "MES registry (Interface 0 Port)"
    return None, "unset"


def resolve_baud(arg: int = 0) -> tuple[int, str]:
    """Baud to use and where the decision came from."""
    if arg:
        return int(arg), "argument"
    v, src = _env("CUORE_OBD_BAUD", "OBD_BAUD")
    if v:
        try:
            return int(v), src
        except ValueError:
            pass
    speed = mes_registry().get("Interface 0 Port Speed")
    if speed:
        try:
            return int(speed), "MES registry (Interface 0 Port Speed)"
        except (TypeError, ValueError):
            pass
    return FALLBACK_BAUD, "ELM327 fallback"


def default_cable() -> str:
    """The cable declared through the environment, if any; else ``none``."""
    v, _ = _env("CUORE_OBD_CABLE")
    return (v or "none").lower()


def state_dir() -> Path:
    """Where lock, audit, store and wire recordings live. First writable wins."""
    override = os.environ.get("CUORE_STATE_DIR")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    if os.environ.get("PROGRAMDATA"):
        candidates.append(Path(os.environ["PROGRAMDATA"], "cuore"))
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"], "cuore"))
    candidates.append(Path.home() / ".cuore")
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write-test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return d
        except OSError:
            continue
    return Path.cwd()


__all__ = ["IS_WINDOWS", "FALLBACK_BAUD", "MES_INSTALL", "mes_registry", "mes_folders",
           "mes_interfaces", "resolve_port", "resolve_baud", "default_cable", "state_dir"]
