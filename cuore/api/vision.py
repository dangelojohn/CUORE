"""``/api/vision/*`` -- "read this photo" for the mobile "Tell CUORE" page.

Thin HTTP face over :mod:`cuore.services.vision_bridge`; see that module's
docstring for the provider contract (``none``/``claude``/``tesseract``) and
the hint -> field/taxonomy table. **Every value this returns is a
suggestion a human confirms before saving** -- this module never writes an
owner event and never touches the vehicle; it only reads a photo the
caller already has in hand (the media API stores the photo itself, not
this one) and proposes field values for the add-event form.

Registration note: ``cuore/app.py`` is owned by another agent. The two
lines needed there, beside the other ``/api`` routers::

    from .api import vision as vision_api
    app.include_router(vision_api.router, prefix="/api")
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ..services import vision_bridge
from .deps import require_token, settings_of

router = APIRouter(tags=["vision"], dependencies=[Depends(require_token)])


@router.get("/vision/status", summary="Which photo-reading provider is configured")
def get_status(request: Request) -> dict[str, Any]:
    return vision_bridge.status(settings_of(request))


@router.post("/vision/{vin}/read", summary="Read one photo (odometer, fuel pump, oil "
            "bottle, part label, or receipt)")
async def read_photo(
    request: Request,
    vin: str,
    file: UploadFile = File(...),
    hint: str = Form(...),
) -> dict[str, Any]:
    if hint not in vision_bridge.HINTS:
        raise HTTPException(
            status_code=400,
            detail=f"hint must be one of {', '.join(vision_bridge.HINTS)}, got {hint!r}",
        )
    image_bytes = await file.read()
    mime = file.content_type or "image/jpeg"
    return vision_bridge.read_photo(hint=hint, image_bytes=image_bytes, mime=mime,
                                    settings=settings_of(request))
