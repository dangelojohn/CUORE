"""One icon language for the Fuses & relays page: a hidden SVG sprite (``<symbol id="ci-<category>">``) and ``icon()``.
Every icon is 24 x 24, stroke only (currentColor), so it follows the light / dark theme. Always shown next to a text label."""
from __future__ import annotations

_P = {
    "fuse": '<rect x="5" y="3" width="14" height="10" rx="1.5"/><path d="M8.5 13v8M15.5 13v8M8.5 8h2l1.5-2 1.5 4 1-2h1"/>',
    "relay": '<rect x="2.5" y="4" width="19" height="16" rx="2"/><path d="M5 9h2l1-2.5 2 5 1-2.5h2M5 16.5h4M15 16.5h4M9 16.5l5.5-3.5"/>',
    "switch": '<circle cx="5" cy="17" r="2"/><circle cx="19" cy="17" r="2"/><path d="M6.5 15.5L17 7"/>',
    "motor": '<circle cx="12" cy="12" r="9"/><path d="M7.5 16V8l4.5 5 4.5-5v8"/>',
    "actuator": '<rect x="2" y="9" width="9" height="6" rx="1"/><path d="M11 12h10M18 8.5l3.5 3.5-3.5 3.5"/>',
    "solenoid_valve": '<rect x="3" y="6" width="12" height="12" rx="1"/><path d="M6.5 6v12M9 6v12M11.5 6v12M15 12h6M21 9v6"/>',
    "gauge_display": '<path d="M3 18a9 9 0 0 1 18 0z"/><path d="M12 18l4-6M6 14l1 1M12 9v1.5M18 14l-1 1"/>',
    "lamp": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9V16h7v-2.1A6 6 0 0 0 12 3z"/>',
    "module": '<rect x="6" y="6" width="12" height="12" rx="1"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>',
    "connector": '<rect x="2" y="8" width="8" height="8" rx="1"/><path d="M10 10h4M10 14h4M14 8v8M14 12h8"/>',
    "ground": '<path d="M12 3v9M4 12h16M7 16h10M10 20h4"/>',
    "pump": '<circle cx="12" cy="12" r="9"/><path d="M9 8l7 4-7 4z"/>',
    "heater": '<path d="M6 3c-2 3 2 5 0 8s2 5 0 8M12 3c-2 3 2 5 0 8s2 5 0 8M18 3c-2 3 2 5 0 8s2 5 0 8"/><path d="M3 21h18"/>',
    "horn_speaker": '<path d="M3 9h4l5-4v14l-5-4H3z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
    "antenna": '<path d="M12 22V10M8 22h8"/><circle cx="12" cy="8" r="2"/><path d="M7 5a7 7 0 0 0 0 6M17 5a7 7 0 0 1 0 6"/>',
    "sensor": '<circle cx="12" cy="12" r="2.5"/><path d="M7 7a7 7 0 0 0 0 10M17 7a7 7 0 0 1 0 10M4 4a11 11 0 0 0 0 16M20 4a11 11 0 0 1 0 16"/>',
    "other": '<circle cx="12" cy="12" r="9"/><path d="M7.5 12h.01M12 12h.01M16.5 12h.01"/>',
}
CATEGORIES = tuple(_P)


def sprite() -> str:
    syms = "".join(f'<symbol id="ci-{k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
                   f'stroke-linecap="round" stroke-linejoin="round">{v}</symbol>' for k, v in _P.items())
    return f'<svg class="ci-sprite" width="0" height="0" aria-hidden="true" focusable="false">{syms}</svg>'


def icon(cat: str, size: int = 24) -> str:
    c = cat if cat in _P else "other"
    return (f'<svg class="ci ci-{c}" width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            f'<use href="#ci-{c}"/></svg>')
