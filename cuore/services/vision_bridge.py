"""Pluggable "read this photo" service for the mobile "Tell CUORE" page.

A human points a phone camera at an odometer, a fuel pump, an oil bottle, a
parts-box label, or a receipt and asks CUORE to pre-fill the add-event form.
**Every value this returns is a suggestion, not a measurement.** The human
reviews and confirms it before anything is saved, and whoever saves the
event stamps ``fields_meta[key] = "photo"`` on that field (same convention
:mod:`cuore.live.owner_events` already uses for provenance) so the record
still says the value came from a picture, not an instrument. Nothing in
this module writes an owner event itself -- it only reads a photo and
proposes field values for one; nothing it returns is a car measurement.

Three providers, selected by ``CUORE_VISION_PROVIDER`` (default ``"none"``):

* ``none`` -- the honest default. CUORE runs offline by rule (see
  ``cuore/config.py``'s own loopback-by-default posture); a vision backend
  that silently failed, or one bolted on without the owner's say-so, would
  be the opposite of that. Returns ``available=False`` and asks the human
  to fill the form by hand.
* ``claude`` -- only when ``CUORE_VISION_PROVIDER=claude`` **and**
  ``ANTHROPIC_API_KEY`` is set. The photo is sent to Anthropic's Messages
  API over the open internet -- this is never the default; the owner turns
  it on knowingly. Called over plain HTTPS with ``urllib`` (the
  ``anthropic`` SDK is not installed in this venv and this module does not
  add it). The image bytes, the base64 payload, and the API key are never
  logged -- only the hint and byte count. 10-second timeout; any network
  or HTTP failure comes back as ``available=False`` with the error's class
  name in ``note``, never a raised exception.
* ``tesseract`` -- a documented hook, not an implementation. No
  ``tesseract.exe`` ships with this install; :func:`_find_tesseract` exists
  so a future local-OCR provider has somewhere to plug in, but reading
  always comes back unavailable today.

Field names mirror the owner-events taxonomy
(:mod:`cuore.live.owner_events` ``TAXONOMY``) wherever a hint corresponds to
one real category/kind, so the mobile page can drop a read field straight
into that kind's form:

====== ================================== ================================================
hint    fields returned                    suggested_kind
====== ================================== ================================================
odometer odometer_km                       null -- the event's own odometer_km, not a
                                            kind field
fuel_pump litres, price, octane, station   fuel/fill_up
oil_bottle brand, viscosity, qty           fluids/engine_oil_change
part_label part, part_no, brand            parts_repairs_elsewhere/part_fitted_elsewhere
receipt station, litres, price, at         fuel/fill_up
other   provider's best effort, unshaped   null
====== ================================== ================================================
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from ..config import Settings

log = logging.getLogger("cuore.vision")

#: The only hints the mobile page may send; the API returns a 400 for
#: anything else.
HINTS = ("odometer", "fuel_pump", "oil_bottle", "part_label", "receipt", "other")

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
CLAUDE_TIMEOUT_S = 10

#: Chocolatey/official-installer default; the other place to look besides
#: PATH. Nothing is installed at either location today.
TESSERACT_DEFAULT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

NOT_CONFIGURED_NOTE = "Automatic reading is not set up on this CUORE. Fill in by hand."

#: hint -> ordered (field_name, "number"|"string", unit-or-None). Names and
#: units match cuore.live.owner_events.TAXONOMY fields (see the module
#: docstring table) wherever one real kind covers the hint. The unit is
#: always ours, never the model's -- a provider is asked for a value and a
#: confidence, not for units, so "L"/"$"/"km" can't drift between photos.
_FIELD_SPECS: dict[str, tuple[tuple[str, str, Optional[str]], ...]] = {
    "odometer": (
        ("odometer_km", "number", "km"),
    ),
    "fuel_pump": (
        ("litres", "number", "L"),
        ("price", "number", "$"),
        ("octane", "string", None),
        ("station", "string", None),
    ),
    "oil_bottle": (
        ("brand", "string", None),
        ("viscosity", "string", None),
        ("qty", "number", "L"),
    ),
    "part_label": (
        ("part", "string", None),
        ("part_no", "string", None),
        ("brand", "string", None),
    ),
    "receipt": (
        ("station", "string", None),
        ("litres", "number", "L"),
        ("price", "number", "$"),
        ("at", "string", None),
    ),
    "other": (),
}

#: hint -> "category/kind" worth pre-selecting on the add-event form, or
#: None when the hint has no single matching taxonomy kind. Keys are real
#: TAXONOMY category/kind pairs (checked against cuore/live/owner_events.py
#: at the time this was written) -- never invented here.
_SUGGESTED_KIND: dict[str, Optional[str]] = {
    "odometer": None,
    "fuel_pump": "fuel/fill_up",
    "oil_bottle": "fluids/engine_oil_change",
    "part_label": "parts_repairs_elsewhere/part_fitted_elsewhere",
    "receipt": "fuel/fill_up",
    "other": None,
}


def _anthropic_key() -> str:
    """Deliberately read straight from the environment, not from
    ``Settings``: ``Settings`` is ``CUORE_``-prefixed and this is a
    third-party credential, not a CUORE setting -- it should not gain a
    ``CUORE_`` alias just because this one feature needs it."""
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def status(settings: Settings) -> dict[str, Any]:
    """GET /api/vision/status payload: which provider is configured and
    whether it can actually be used right now (never whether the *last*
    read succeeded)."""
    provider = (settings.vision_provider or "none").strip().lower()
    if provider == "claude":
        return {"provider": "claude", "available": bool(_anthropic_key()),
                "model": settings.vision_model}
    if provider == "tesseract":
        # Stub: the probe exists (see _find_tesseract) but nothing reads an
        # image with it yet, so this is never "available", regardless of
        # what the probe finds on this machine.
        return {"provider": "tesseract", "available": False, "model": None}
    return {"provider": "none", "available": False, "model": None}


def read_photo(*, hint: str, image_bytes: bytes, mime: str,
               settings: Settings) -> dict[str, Any]:
    """Read one photo under ``hint`` and return the vision API's exact
    response contract: ``{provider, available, fields, suggested_kind,
    note}``. Dispatches on ``settings.vision_provider``; an unrecognised
    value behaves like ``"none"`` so a typo'd env var fails safe, not loud.
    Never raises -- every provider path below catches its own failures."""
    provider = (settings.vision_provider or "none").strip().lower()

    if provider == "claude":
        return _read_claude(hint, image_bytes, mime, settings)
    if provider == "tesseract":
        return _read_tesseract()
    return _read_none()


def _read_none() -> dict[str, Any]:
    return {"provider": "none", "available": False, "fields": {},
            "suggested_kind": None, "note": NOT_CONFIGURED_NOTE}


def _find_tesseract() -> Optional[str]:
    """Documented hook for a future local-OCR provider: PATH first, then
    the official installer's default location. Exists so that provider has
    somewhere to start -- no OCR is wired up behind it yet."""
    exe = shutil.which("tesseract")
    if exe:
        return exe
    return TESSERACT_DEFAULT_PATH if Path(TESSERACT_DEFAULT_PATH).exists() else None


def _read_tesseract() -> dict[str, Any]:
    _find_tesseract()  # probe only, see module docstring -- no OCR wired up
    return {"provider": "tesseract", "available": False, "fields": {},
            "suggested_kind": None, "note": "Tesseract not installed"}


def _claude_prompt(hint: str) -> str:
    spec = _FIELD_SPECS.get(hint, ())
    if not spec:
        return (
            "Look at this photo from a car owner's garage logbook. Reply "
            "with ONLY a JSON object (no prose, no markdown fences). Pick "
            "whatever field names make sense for what is legible, each as "
            '{"value": <string or number, or null if unreadable>, '
            '"confidence": <number 0 to 1>}. If nothing legible is in the '
            "photo, reply with {}."
        )
    names = ", ".join(f'"{name}"' for name, _t, _u in spec)
    field_lines = "\n".join(
        f'- "{name}": {"a number" if type_ == "number" else "a short string"}'
        for name, type_, _unit in spec)
    return (
        f"Look at this photo (hint: {hint}) from a car owner's garage "
        "logbook. Reply with ONLY a JSON object (no prose, no markdown "
        f"fences), with exactly these top-level keys: {names}. Each value "
        'must be an object: {"value": <the reading, or null if unreadable '
        'or not present>, "confidence": <number 0 to 1>}. Fields expected:\n'
        f"{field_lines}\n"
        "Use null for value and 0 for confidence on anything you cannot "
        "read with confidence. Do not guess or invent a value."
    )


def _extract_text(response: dict[str, Any]) -> str:
    """Pull the first text block out of a Messages API response. Defensive:
    any shape surprise falls through to an empty string rather than a
    traceback -- the JSON parse right after this already expects to fail
    gracefully, so a wrong shape here just becomes "invalid JSON"."""
    try:
        for block in response.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "")
    except Exception:  # noqa: BLE001 -- defensive parse, never crash on shape
        pass
    return ""


def _parse_json_object(text: str) -> Optional[dict[str, Any]]:
    """Best-effort JSON object out of a model reply: strip a ```json fence
    if the model added one anyway, try the whole text, then fall back to
    the widest ``{...}`` span. Returns None (never raises) when nothing in
    the text parses as a JSON object."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(candidate[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _coerce_fields(hint: str, parsed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map a parsed reply onto this hint's fixed field/unit shape. A field
    the model omitted, or returned in a shape we don't trust (wrong type,
    an out-of-range confidence), degrades to null/0.0 instead of raising --
    a partial read is still useful, and the human confirms every value
    anyway before it is saved."""
    out: dict[str, dict[str, Any]] = {}
    for name, _type, unit in _FIELD_SPECS.get(hint, ()):
        raw = parsed.get(name)
        value: Any = None
        confidence = 0.0
        if isinstance(raw, dict):
            candidate_value = raw.get("value")
            if isinstance(candidate_value, bool):
                value = None
            elif isinstance(candidate_value, (int, float, str)):
                value = candidate_value
            conf = raw.get("confidence")
            if isinstance(conf, (int, float)) and not isinstance(conf, bool):
                confidence = max(0.0, min(1.0, float(conf)))
        out[name] = {"value": value, "confidence": confidence, "unit": unit}
    return out


def _read_claude(hint: str, image_bytes: bytes, mime: str,
                 settings: Settings) -> dict[str, Any]:
    api_key = _anthropic_key()
    if not api_key:
        return {"provider": "claude", "available": False, "fields": {},
                "suggested_kind": None,
                "note": "ANTHROPIC_API_KEY is not set; automatic reading is off."}

    model = settings.vision_model
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": mime or "image/jpeg",
                           "data": base64.b64encode(image_bytes).decode("ascii")}},
                {"type": "text", "text": _claude_prompt(hint)},
            ],
        }],
    }
    req = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
    )
    # Never logged: the image bytes, the base64 payload, or the API key.
    # Only the hint and the byte count are worth knowing if this ever needs
    # debugging.
    log.info("vision(claude): %d bytes, hint=%s, model=%s", len(image_bytes), hint, model)
    try:
        with urllib.request.urlopen(req, timeout=CLAUDE_TIMEOUT_S) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 -- any network/HTTP failure, same shape
        return {"provider": "claude", "available": False, "fields": {},
                "suggested_kind": None,
                "note": f"Could not reach Anthropic ({type(exc).__name__})."}

    text = _extract_text(raw)
    parsed = _parse_json_object(text)
    if parsed is None:
        return {"provider": "claude", "available": True, "fields": {},
                "suggested_kind": None,
                "note": "Claude's reply wasn't valid JSON, so nothing was "
                       "read automatically. Fill in by hand."}

    fields = _coerce_fields(hint, parsed) if _FIELD_SPECS.get(hint) else {}
    return {"provider": "claude", "available": True, "fields": fields,
            "suggested_kind": _SUGGESTED_KIND.get(hint),
            "note": "Suggested from the photo -- confirm or correct every "
                   "field before saving; this is not a car measurement."}


__all__ = ["HINTS", "status", "read_photo"]
