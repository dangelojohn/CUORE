"""
Multiecuscan Integration

Parses Multiecuscan log files and CSV/XML exports to give Claude access
to deeper Fiat/Alfa Romeo/Lancia diagnostics that go beyond standard OBD2.

Multiecuscan supports proprietary FCA protocols and can access:
- ABS, Airbag, Body Computer, Climate, Instrument Cluster ECUs
- Manufacturer-specific DTCs with full descriptions
- Adaptation values and coding
- Service intervals and key programming data
"""

from __future__ import annotations

import csv
import glob
import io
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class MultiecuscanDTC:
    """A diagnostic trouble code from Multiecuscan."""
    code: str
    description: str
    ecu: str
    status: str  # "active", "stored", "pending"
    raw_data: str = ""


@dataclass
class MultiecuscanSession:
    """Parsed data from a single Multiecuscan diagnostic session."""
    timestamp: datetime
    vehicle: str
    ecu: str
    filename: str
    dtcs: list[MultiecuscanDTC] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_log: str = ""


class MultiecuscanParser:
    """
    Parses Multiecuscan log files and exports.

    Supported formats:
    - .log text files (raw session logs)
    - .csv exports (parameter data)
    - .xml exports (structured diagnostic data)
    """

    def __init__(self):
        self._config = get_config().multiecuscan

    @property
    def log_dir(self) -> Path:
        return Path(self._config.log_directory)

    @property
    def export_dir(self) -> Path:
        return Path(self._config.export_directory)

    def is_installed(self) -> bool:
        """Check if Multiecuscan is installed at the configured path."""
        return Path(self._config.install_path).exists()

    def get_status(self) -> dict[str, Any]:
        """Get Multiecuscan integration status."""
        return {
            "installed": self.is_installed(),
            "install_path": self._config.install_path,
            "log_directory": str(self.log_dir),
            "log_directory_exists": self.log_dir.exists(),
            "export_directory": str(self.export_dir),
            "export_directory_exists": self.export_dir.exists(),
            "log_file_count": len(self.list_log_files()),
            "export_file_count": len(self.list_export_files()),
        }

    def list_log_files(self, limit: int = 20) -> list[dict[str, Any]]:
        """List available Multiecuscan log files, newest first."""
        if not self.log_dir.exists():
            return []

        files = []
        for ext in ["*.log", "*.txt"]:
            for f in self.log_dir.glob(ext):
                files.append({
                    "filename": f.name,
                    "path": str(f),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })

        files.sort(key=lambda x: x["modified"], reverse=True)
        return files[:limit]

    def list_export_files(self, limit: int = 20) -> list[dict[str, Any]]:
        """List available Multiecuscan export files."""
        if not self.export_dir.exists():
            return []

        files = []
        for ext in ["*.csv", "*.xml", "*.json"]:
            for f in self.export_dir.glob(ext):
                files.append({
                    "filename": f.name,
                    "path": str(f),
                    "format": f.suffix.lstrip("."),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })

        files.sort(key=lambda x: x["modified"], reverse=True)
        return files[:limit]

    def parse_log_file(self, filepath: str) -> MultiecuscanSession:
        """
        Parse a Multiecuscan .log file.

        Extracts DTCs, parameter readings, ECU info, and vehicle identification.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")

        content = path.read_text(encoding="utf-8", errors="replace")

        session = MultiecuscanSession(
            timestamp=datetime.fromtimestamp(path.stat().st_mtime),
            vehicle="",
            ecu="",
            filename=path.name,
            raw_log=content[:5000],  # Keep first 5KB for reference
        )

        # Parse vehicle identification
        vin_match = re.search(r"VIN[:\s]+([A-HJ-NPR-Z0-9]{17})", content, re.IGNORECASE)
        if vin_match:
            session.vehicle = f"VIN: {vin_match.group(1)}"

        # Parse ECU identification
        ecu_match = re.search(r"ECU[:\s]+([\w\s\-]+?)(?:\n|$)", content, re.IGNORECASE)
        if ecu_match:
            session.ecu = ecu_match.group(1).strip()

        # Parse DTCs - various Multiecuscan formats
        # Pattern: DTC code followed by description
        dtc_patterns = [
            r"(P[0-9A-F]{4}|C[0-9A-F]{4}|B[0-9A-F]{4}|U[0-9A-F]{4})\s*[-:]\s*(.+?)(?:\n|$)",
            r"Error\s+code[:\s]+([\w]+)\s*[-:]\s*(.+?)(?:\n|$)",
            r"DTC[:\s]+([\w]+)\s*[-:]\s*(.+?)(?:\n|$)",
        ]

        seen_dtcs = set()
        for pattern in dtc_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                code = match.group(1).upper()
                if code not in seen_dtcs:
                    seen_dtcs.add(code)
                    # Determine status from context
                    context = content[max(0, match.start() - 50): match.start()].lower()
                    if "active" in context or "current" in context:
                        status = "active"
                    elif "pending" in context:
                        status = "pending"
                    else:
                        status = "stored"

                    session.dtcs.append(MultiecuscanDTC(
                        code=code,
                        description=match.group(2).strip(),
                        ecu=session.ecu,
                        status=status,
                    ))

        # Parse parameter readings (key: value pairs)
        param_pattern = r"^([\w\s/\(\)]+?)\s*[:=]\s*([\d.,]+)\s*([\w°%/]*)\s*$"
        for match in re.finditer(param_pattern, content, re.MULTILINE):
            name = match.group(1).strip()
            try:
                value = float(match.group(2).replace(",", "."))
                unit = match.group(3).strip()
                session.parameters[name] = {"value": value, "unit": unit}
            except ValueError:
                session.parameters[name] = {"value": match.group(2), "unit": match.group(3).strip()}

        return session

    def parse_csv_export(self, filepath: str) -> dict[str, Any]:
        """
        Parse a Multiecuscan CSV export file.

        These typically contain time-series parameter data logged during a session.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        content = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))

        rows = list(reader)
        if not rows:
            return {"error": "Empty CSV file", "headers": list(reader.fieldnames or [])}

        # Summarize the data
        headers = list(rows[0].keys())
        summary = {
            "filename": path.name,
            "row_count": len(rows),
            "columns": headers,
            "first_row": rows[0],
            "last_row": rows[-1],
        }

        # Try to identify time column and compute duration
        time_cols = [h for h in headers if "time" in h.lower() or "timestamp" in h.lower()]
        if time_cols:
            summary["time_column"] = time_cols[0]
            summary["start_time"] = rows[0].get(time_cols[0], "")
            summary["end_time"] = rows[-1].get(time_cols[0], "")

        # Compute basic stats for numeric columns
        stats = {}
        for header in headers:
            values = []
            for row in rows:
                try:
                    values.append(float(row[header].replace(",", ".")))
                except (ValueError, KeyError):
                    continue
            if values:
                stats[header] = {
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "avg": round(sum(values) / len(values), 2),
                    "samples": len(values),
                }
        summary["numeric_stats"] = stats

        return summary

    def parse_xml_export(self, filepath: str) -> dict[str, Any]:
        """Parse a Multiecuscan XML export file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"XML file not found: {filepath}")

        try:
            tree = ET.parse(path)
            root = tree.getroot()

            result = {
                "filename": path.name,
                "root_tag": root.tag,
                "attributes": dict(root.attrib),
            }

            # Extract DTCs if present
            dtcs = []
            for dtc_elem in root.iter():
                tag = dtc_elem.tag.lower()
                if "dtc" in tag or "error" in tag or "fault" in tag:
                    dtc_data = dict(dtc_elem.attrib)
                    dtc_data["text"] = (dtc_elem.text or "").strip()
                    for child in dtc_elem:
                        dtc_data[child.tag] = (child.text or "").strip()
                    if dtc_data:
                        dtcs.append(dtc_data)
            result["dtcs"] = dtcs

            # Extract parameters
            params = {}
            for elem in root.iter():
                tag = elem.tag.lower()
                if "param" in tag or "value" in tag or "data" in tag:
                    name = elem.attrib.get("name", elem.tag)
                    value = elem.text or elem.attrib.get("value", "")
                    unit = elem.attrib.get("unit", "")
                    if value:
                        params[name] = {"value": value, "unit": unit}
            result["parameters"] = params

            # General structure summary
            tags = set()
            for elem in root.iter():
                tags.add(elem.tag)
            result["element_types"] = sorted(tags)

            return result
        except ET.ParseError as e:
            return {"error": f"XML parse error: {str(e)}", "filename": path.name}

    def get_latest_session(self) -> Optional[dict[str, Any]]:
        """Parse the most recent Multiecuscan log file."""
        logs = self.list_log_files(limit=1)
        if not logs:
            return {"error": "No Multiecuscan log files found", "log_directory": str(self.log_dir)}

        latest = logs[0]
        try:
            session = self.parse_log_file(latest["path"])
            return {
                "filename": session.filename,
                "timestamp": session.timestamp.isoformat(),
                "vehicle": session.vehicle,
                "ecu": session.ecu,
                "dtc_count": len(session.dtcs),
                "dtcs": [
                    {"code": d.code, "description": d.description, "status": d.status, "ecu": d.ecu}
                    for d in session.dtcs
                ],
                "parameter_count": len(session.parameters),
                "parameters": session.parameters,
            }
        except Exception as e:
            return {"error": f"Failed to parse log: {str(e)}", "file": latest["path"]}

    def search_dtcs_across_sessions(self, dtc_code: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Search for a specific DTC across all Multiecuscan sessions.

        Args:
            dtc_code: Specific DTC to search for (e.g., 'P0300'), or None for all.
        """
        logs = self.list_log_files(limit=50)
        results = []

        for log_info in logs:
            try:
                session = self.parse_log_file(log_info["path"])
                for dtc in session.dtcs:
                    if dtc_code is None or dtc.code.upper() == dtc_code.upper():
                        results.append({
                            "code": dtc.code,
                            "description": dtc.description,
                            "ecu": dtc.ecu,
                            "status": dtc.status,
                            "session_date": session.timestamp.isoformat(),
                            "session_file": session.filename,
                            "vehicle": session.vehicle,
                        })
            except Exception as e:
                logger.warning(f"Error parsing {log_info['path']}: {e}")
                continue

        return results


# Module-level singleton
_parser: Optional[MultiecuscanParser] = None


def get_multiecuscan_parser() -> MultiecuscanParser:
    """Get the global Multiecuscan parser instance."""
    global _parser
    if _parser is None:
        _parser = MultiecuscanParser()
    return _parser
