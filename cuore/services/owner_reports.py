"""Owner "Report a problem" (phone) -> technician Start step.

One ATTESTED owner complaint per submit, stored as an owner event
(category ``incidents``, kind ``problem_report``): never a reading, never
opens a job. Stored only with explicit consent. ``used_in_visit`` is set
(via the store's own ``edit`` amendment) once a job was opened from it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from ..live import owner_events

CATEGORY, KIND = "incidents", "problem_report"
SOURCE = "owner phone"

SPEEDS = ("Stopped / idle", "Low speed", "City", "Highway", "Any speed")
TEMPS = ("Cold engine", "Warm engine", "Both")
FREQUENCIES = ("Once", "Sometimes", "Often", "Every time")
LIGHTS = ("Yes", "No", "Not sure")


def compose_text(f: dict[str, Any]) -> str:
    """One readable complaint line for the technician's Start field."""
    parts = [str(f.get("description") or "").strip()]
    for key, label in (("speed", "Speed"), ("temperature", "Engine"), ("frequency", "How often"),
                       ("since", "Since"), ("warning_lights", "Warning lights")):
        if f.get(key):
            parts.append(f"{label}: {f[key]}")
    return ". ".join(p for p in parts if p)


def add_report(vin: str, *, description: str, consent: bool, speed: str = "",
               temperature: str = "", frequency: str = "", since: str = "",
               warning_lights: str = "", media_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Raises ValueError (nothing stored) without consent or description."""
    if not consent:
        raise ValueError("Not sent: tick the box to share this report with the technicians.")
    if not (description or "").strip():
        raise ValueError("Not sent: please say what happens.")
    now = datetime.now().isoformat(timespec="seconds")
    return owner_events.add(vin, CATEGORY, KIND, by_role="owner", media_ids=media_ids, fields={
        "description": description, "speed": speed, "temperature": temperature,
        "frequency": frequency, "since": since, "warning_lights": warning_lights,
        "consent": True, "consent_at": now, "source": SOURCE})


def new_reports(vin: str = "") -> list[dict[str, Any]]:
    """Unused, consented reports (all cars when ``vin`` is empty), newest first."""
    out = []
    for e in owner_events.load(vin):
        f = e.get("fields") or {}
        if (e.get("kind") == KIND and not e.get("deleted") and f.get("consent") is True
                and not f.get("used_in_visit")):
            out.append({"id": e["id"], "vin": e.get("vin", ""), "at": e.get("recorded_at", ""),
                        "text": compose_text(f), "has_photo": bool(e.get("media_ids"))})
    return sorted(out, key=lambda r: r["at"], reverse=True)


def mark_used(report_id: str, visit_id: str) -> None:
    try:
        owner_events.edit(report_id, fields={"used_in_visit": visit_id or "opened"},
                          by_role="mechanic")
    except ValueError:
        pass  # never block opening the job
