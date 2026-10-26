"""Page-only search helpers shared by the sensors and harnesses pages (server-side, no JavaScript needed).

A query is split into words. Every word must hit the item's search text, either as typed or as any
synonym of it (``tire`` finds ``tyre``). Nothing here reads outside the page's own items.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

MAX_Q = 80
HINT_SENSORS = "Try a part or system word (oxygen, tyre, coolant, brake) or a sensor id."
HINT_CODES = "Try a code (P0456), a system word (evap, window, network) or a module (ECM, BCM)."
HINT_HARNESSES = "Try an area or part word (door, dash, engine, seat, headlamp)."

SENSOR_SYNONYMS = (
    ("o2", "oxygen", "lambda"), ("temp", "temperature"), ("pressure", "psi", "kpa"),
    ("tyre", "tire", "tpms"), ("battery", "ibs"), ("throttle", "tps"), ("pedal", "accelerator"),
    ("boost", "turbo", "map"), ("wheel", "abs"), ("fuel",), ("oil",), ("coolant",),
)
HARNESS_SYNONYMS = (
    ("door",), ("dash", "instrument panel", "instrument", "cluster"), ("engine",), ("seat",), ("console",),
    ("headlamp", "headlight", "head lamp", "head light"), ("body",),
    ("a/c", "ac", "air conditioning", "hvac", "climate"),
)


def clean_q(q: Any) -> str:
    return re.sub(r"\s+", " ", str(q or "")).strip()[:MAX_Q]


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower().replace("_", " ")).strip()


def haystack(parts: Iterable[Any]) -> str:
    return " | ".join(_norm(p) for p in parts if p not in (None, ""))


def _alts(word: str, groups: tuple) -> set[str]:
    out = {word}
    for g in groups:
        if word in g:
            out.update(g)
    return out


def _hit(a: str, t: str, squashed: str, grouped: bool) -> bool:
    if grouped and len(a) <= 3:   # short words (ac, o2, abs, oil) must be whole words, not inside "back" or "cabin"
        return re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", t) is not None
    return a in t or a.replace(" ", "") in squashed


def words(q: str, groups: tuple = ()) -> list[str]:
    n = _norm(q)
    out: list[str] = []
    for phrase in sorted({m for g in groups for m in g if " " in m}, key=len, reverse=True):
        if phrase in n:   # a multi-word synonym ("air conditioning") counts as one word
            out.append(phrase)
            n = n.replace(phrase, " ")
    return out + [w for w in re.findall(r"[a-z0-9/]+", n) if w]


def matches(q: str, text: str, groups: tuple) -> bool:
    """True when every query word (or one of its synonyms) occurs in ``text``."""
    ws = words(q, groups)
    if not ws:
        return True
    t = _norm(text)
    squashed = t.replace(" ", "")
    for w in ws:
        if not any(_hit(a, t, squashed, any(w in g for g in groups)) for a in _alts(w, groups)):
            return False
    return True
