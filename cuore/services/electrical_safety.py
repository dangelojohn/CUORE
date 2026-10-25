"""Generic safety rules for the electrical page (``/v/{vin}/electrical``).

One data table, :data:`SAFETY_RULES`, so a new hazard is one more dict, not
new code. A rule fires on an element when any of its ``when`` conditions
matches; a condition may constrain ``system`` (the element's own ``system``
or any of its ``part_of_systems``), ``kind``, and ``words`` (whole-word,
case-insensitive match against the element's label and id). Every key a
condition names must match; the keys it leaves out are not checked.

The wording is deliberately generic: it names the hazard and the
general precaution, and defers every specific (time to wait, torque,
pressure, procedure) to the service manual. No value is invented here.
"""

from __future__ import annotations

import re
from typing import Any

SAFETY_RULES: list[dict[str, Any]] = [
    {
        "key": "srs",
        "title": "Airbag (SRS) circuit",
        "text": ("Airbag (SRS) circuit: switch ignition off, disconnect the battery and wait the "
                 "time the service manual gives before unplugging any SRS connector. Never probe "
                 "SRS connectors with a test light."),
        "when": [
            {"system": ["srs", "airbag", "restraint", "occupant_restraint"]},
            {"words": ["airbag", "air bag", "srs", "occupant restraint", "restraint", "orc",
                       "clockspring", "clock spring", "pyrotechnic", "pretensioner", "squib"]},
        ],
    },
    {
        "key": "high_current",
        "title": "High-current circuit",
        "text": ("High-current circuit: disconnect the battery negative terminal before working "
                 "on or near this part, remove rings and metal jewellery, and never bridge or "
                 "short terminals with tools. Follow the service manual for the order of "
                 "disconnection."),
        "when": [
            {"kind": ["battery"]},
            {"words": ["battery", "starter", "alternator", "megafuse", "mega fuse",
                       "main fuse", "jump start", "b+"]},
        ],
    },
    {
        "key": "fuel",
        "title": "Fuel system",
        "text": ("Fuel system: no sparks, flame or smoking nearby, work in a ventilated area, "
                 "and relieve fuel pressure the way the service manual directs before opening "
                 "any fuel line. Keep a suitable fire extinguisher within reach."),
        "when": [
            {"system": ["fuel"], "kind": ["pump", "line", "hose", "injector", "rail"]},
            {"words": ["fuel pump", "fuel line", "fuel lines", "injector", "injectors",
                       "fuel rail", "fuel pressure"]},
        ],
    },
]

#: Glyph legend text for the diagram/legend (one word per rule is not needed:
#: a single triangle covers every rule above).
BADGE_LEGEND = "safety warning: read the warning before working on this part"

_WORD_CACHE: dict[str, re.Pattern] = {}


def _word_re(word: str) -> re.Pattern:
    pat = _WORD_CACHE.get(word)
    if pat is None:
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])")
        _WORD_CACHE[word] = pat
    return pat


def _as_list(v: Any) -> list[str]:
    return [str(x).lower() for x in v] if isinstance(v, (list, tuple, set)) else (
        [str(v).lower()] if v else [])


def _cond_matches(cond: dict[str, Any], *, systems: set[str], kind: str, text: str) -> bool:
    if "system" in cond and not (systems & set(_as_list(cond["system"]))):
        return False
    if "kind" in cond and kind not in _as_list(cond["kind"]):
        return False
    if "words" in cond and not any(_word_re(w).search(text) for w in _as_list(cond["words"])):
        return False
    return bool(cond)


def flags_for(element: dict[str, Any], eid: str = "") -> list[dict[str, str]]:
    """Safety rules that apply to one element (``layout_bridge.elements()``
    shape) -- ``[{key, title, text}]``, empty when none."""
    systems = {str(element.get("system") or "").lower()}
    systems |= {str(s).lower() for s in (element.get("part_of_systems") or [])}
    systems.discard("")
    kind = str(element.get("kind") or "").lower()
    text = f"{element.get('label') or ''} {eid or element.get('id') or ''}".lower().replace("_", " ")
    out = []
    for rule in SAFETY_RULES:
        if any(_cond_matches(c, systems=systems, kind=kind, text=text) for c in rule["when"]):
            out.append({"key": rule["key"], "title": rule["title"], "text": rule["text"]})
    return out


__all__ = ["SAFETY_RULES", "BADGE_LEGEND", "flags_for"]
