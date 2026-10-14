"""The HTTP/MCP face of ``cuore.live.scanlog``: list, read, diff, export.

Thin on purpose -- every actual grouping/derivation decision lives in
``cuore.live.scanlog`` (see its own docstring). This module only turns "not
found" into :class:`~cuore.services.errors.NotFound` the way every other
``*_bridge.py`` does, and resolves the two export formats.
"""

from __future__ import annotations

from typing import Any

from ..live import scanlog
from .errors import BadRequest, NotFound

EXPORT_FORMATS = ("json", "mes")


def list_scans(vin: str) -> dict[str, Any]:
    return {"vin": vin, "scans": scanlog.list_scans(vin)}


def scan(vin: str, scan_id: str) -> dict[str, Any]:
    found = scanlog.get_scan(vin, scan_id)
    if found is None:
        raise NotFound(f"no scan {scan_id!r} on file for {vin}")
    return found


def diff(vin: str, id_a: str, id_b: str) -> dict[str, Any]:
    result = scanlog.diff(vin, id_a, id_b)
    if result is None:
        raise NotFound(f"one of {id_a!r}/{id_b!r} is not a scan on file for {vin}")
    return result


def export(vin: str, scan_id: str, fmt: str = "json") -> dict[str, Any]:
    """``{"filename", "media_type", "content"}`` -- ``content`` is a dict
    for ``fmt="json"`` and the MES-format text for ``fmt="mes"``. The MES
    text is also written under ``CUORE_STATE_DIR/scans/<vin>/<id>.txt`` (see
    ``scanlog.write_mes_export``) so existing MES tooling can read it back
    without the caller doing anything extra -- never into MultiEcuScan's own
    LOG folder.
    """
    if fmt not in EXPORT_FORMATS:
        raise BadRequest(f"fmt must be one of {EXPORT_FORMATS}, got {fmt!r}")
    found = scan(vin, scan_id)  # raises NotFound
    if fmt == "json":
        return {"filename": f"{scan_id}.json", "media_type": "application/json",
                "content": found}
    path = scanlog.write_mes_export(vin, scan_id)
    text = path.read_text(encoding="utf-8") if path else scanlog.export_mes_text(found)
    return {"filename": f"{scan_id}.txt", "media_type": "text/plain", "content": text,
           "path": str(path) if path else None}


__all__ = ["list_scans", "scan", "diff", "export", "EXPORT_FORMATS"]
