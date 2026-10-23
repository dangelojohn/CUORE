"""``/api/export/*`` -- build and fetch a bundle for AlfaCore.

Thin HTTP face over :mod:`cuore.services.bundle_export`. Read-only toward the
car and the stores: it writes only a ``*.cuore.zip`` under
``<state_dir>/exports``. There is no network call to AlfaCore and no token for
it; a person carries the file (spec section 2).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from ..services import bundle_export
from .deps import require_token

router = APIRouter(prefix="/export", tags=["export"], dependencies=[Depends(require_token)])


def _result(path: Any) -> dict[str, Any]:
    m = bundle_export.read_manifest(path)
    return {"path": str(path), "bundle_uuid": m["bundle_uuid"], "bytes": path.stat().st_size,
            "files": [f["path"] for f in m["files"]], "warnings": m.get("warnings") or [],
            "finalized": m.get("finalized"), "filename": path.name}


@router.post("/scan/{scan_id}")
def export_scan(scan_id: str, vin: str = Query(..., description="The vehicle's VIN")) -> dict[str, Any]:
    """Export one scan (full or guided) as a bundle file."""
    return _result(bundle_export.export_scan(scan_id, vin))


@router.post("/job/{job_id}")
def export_job(job_id: str, vin: str = Query(..., description="The vehicle's VIN")) -> dict[str, Any]:
    """Export one job as a bundle file."""
    return _result(bundle_export.export_job(job_id, vin))


@router.get("/download")
def download(path: str = Query(..., description="A path returned by an export call")) -> FileResponse:
    """Stream a bundle. Only ``*.cuore.zip`` files under the exports folder."""
    p = bundle_export.resolve_export_path(path)
    return FileResponse(p, media_type="application/zip", filename=p.name)
