"""Knowledge table: known **modifications/configuration changes** for the
Alfa Romeo Giulia/Stelvio 2.0T (Giorgio platform) -- things an owner or
mechanic can deliberately change about how the car is configured, as
opposed to :mod:`mes.mechanic_tests`/:mod:`mes.mes_functions` (diagnostic
reads/tests) or :mod:`mes.parts` (what a worn part costs/looks like).

**Decided 2026-10-14 (NO-GO on CUORE performing any of these writes itself
-- see ``docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md`` and
``docs/research/mes_paddle_shift_function.json``):** every row here is a
*handoff* -- CUORE diagnoses and records, it never codes or configures the
car. The write happens in MES/wiTECH (or, for the one named exception, the
car's own infotainment menu); CUORE's job is to tell the mechanic exactly
what to do there, and then to keep the permanent record of what was done
once it's done (that record lives in :mod:`cuore.live.modifications`, not
here -- this module is the read-only catalogue of *known* modifications,
the same split :mod:`mes.parts`/:mod:`mes.mechanic_tests` already use
between "what we know about this kind of thing" and "what happened to
*this* car").

Seeded (2026-10-14) from two sources:

1. Every :mod:`mes.mes_functions` row of ``kind in ("coding", "adjustment")``
   -- mechanically converted by :func:`_from_mes_function` below, which
   never re-sources anything; it reshapes that module's own fields (name,
   module, menu_path, prerequisites, notes, source, confidence) into this
   module's own record shape and marks anything it cannot derive honestly
   as ``"UNKNOWN"`` rather than inventing it.
2. The paddle-shift NA/Euro byte-156 research pass
   (``docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md`` +
   ``docs/research/mes_paddle_shift_function.json``), reproduced in full
   below as :data:`PADDLE_SHIFT_NA_EU` -- catalogue entry one, per the
   owner's own instruction, fully populated rather than mechanically
   derived.

Same confidence vocabulary as every other knowledge table in this repo
(:data:`mes.systems.CONFIDENCE_LEVELS`): CONFIRMED / CORROBORATED /
SINGLE-SOURCE / UNKNOWN. Nothing here is invented -- a field this pass
could not source says ``"UNKNOWN"`` in plain text rather than guessing.

Four read-only lookups, the whole public surface (mirrors
``mes.mes_functions``'s own shape on purpose, so a caller already familiar
with that module needs nothing new):

* :func:`all_mods`       -- every modification, as a list, catalogue order
                            (paddle shift first).
* :func:`mod`            -- one modification by id, or ``None``.
* :func:`mods_for_module` -- modifications touching one module (substring,
                             case-insensitive).
* :func:`search`         -- modifications whose name matches a free-text
                            string (same token-overlap rule
                            ``mes_functions.search`` uses).
"""

from __future__ import annotations

from typing import Any, Optional

from .systems import CONFIDENCE_LEVELS, CORROBORATED, SINGLE_SOURCE  # noqa: F401
from . import mes_functions

#: coding       -- a configuration byte/variant-coding value is written.
#: config       -- a simpler, non-byte-level setting is changed (a toggle,
#:                 a threshold) -- reserved for future entries; nothing
#:                 seeded below needed it over "coding"/"adjustment".
#: adjustment   -- a calibration/procedure is run (reset, relearn, align).
#: aftermarket_part -- a part was fitted that was never stock on this car.
#: software     -- a module's software/calibration was flashed/updated.
KINDS = ("coding", "config", "adjustment", "aftermarket_part", "software")

MODS: dict[str, dict[str, Any]] = {}
_ORDER: list[str] = []


def _add(row: dict[str, Any]) -> None:
    rid = row["id"]
    if rid in MODS:
        raise ValueError(f"duplicate modification id {rid!r}")
    if row["kind"] not in KINDS:
        raise ValueError(f"bad kind {row['kind']!r} for {rid!r}")
    if row["confidence"] not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {row['confidence']!r} for {rid!r}")
    for required in ("name", "what_it_changes", "module", "how",
                      "prerequisites", "risks", "reversible",
                      "legal_warranty_note", "sources"):
        if required not in row:
            raise ValueError(f"{rid!r} is missing required field {required!r}")
    MODS[rid] = row
    _ORDER.append(rid)


# ===========================================================================
# Entry one: paddle shift NA/Euro -- fully sourced, per the owner's own
# instruction that this be populated from the research pass, not mechanically
# derived like the rows below it. Reproduces
# docs/research/mes_paddle_shift_function.json verbatim in this module's own
# shape; see docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md for the full
# research writeup (sections 1-7) this entry is built from.
# ===========================================================================

PADDLE_SHIFT_NA_EU: dict[str, Any] = {
    "id": "paddle_shift_na_eu",
    "name": "Paddle shift NA/Euro characteristic (CAN Setup byte 156)",
    "what_it_changes": (
        "Changes how the steering-wheel paddle shifters behave. North "
        "America spec: pulling both paddles together does NOT reach "
        "Neutral. Europe spec: pulling both paddles together reaches "
        "Neutral, and the right paddle returns the transmission to Drive. "
        "Written as a configuration byte inside the BCM's CAN-Setup/PROXI "
        "dataset -- not a TCM shift-logic change and not an ESM "
        "gear-actuator change, despite those being the owner's own first "
        "two guesses before this research pass."
    ),
    "module": "Body/BCM (CAN Setup, byte 156)",
    "kind": "coding",
    "how": {
        "method": "MES",
        "menu_path": ["Connect", "Body", "Adjustments (F7)", "CAN Setup",
                      "byte 156, bits 4-5"],
        "detail": (
            "Connect to the vehicle, select Body as the control module, "
            "open Adjustments (F7), locate CAN Setup, change byte 156 bits "
            "4-5 from the NA pattern to the EU pattern (reported whole-byte "
            "values 0x50 -> 0x40), then run the PROXI ALIGNMENT PROCEDURE "
            "(F10), confirm Y, then turn the key to OFF per the official "
            "manual's generic closing step. MES does not expose this as a "
            "single named button -- there is no 'Euro paddle mode' menu "
            "item, only the generic PROXI byte-edit mechanism."
        ),
    },
    "values": {
        "north_america": {"bit_pattern": "xx01xxxx", "reported_byte": "0x50"},
        "europe": {"bit_pattern": "xx00xxxx", "reported_byte": "0x40"},
    },
    "write_target": {
        "type": "configuration_byte", "byte_index": 156, "bits": "4-5",
        "did": None,
        "did_note": "No ISO 14229 DID documented by any source; 'byte 156' "
                    "is MES's own internal PROXI-dataset index only. Not "
                    "present in cuore/live/did_catalog.py. Do not treat as "
                    "a confirmed DID.",
    },
    "prerequisites": [
        "Interface connected to the OBD port, correct make/model/version "
        "selected, Connect (F10) first",
        "Back up the current PROXI/config data to a text file before "
        "editing -- community best practice, not vendor-documented; there "
        "is no documented DID to re-read this single byte in isolation "
        "afterward",
        "Edit only bits 4-5 of byte 156; leave the remaining bits of that "
        "byte untouched",
        "Run PROXI ALIGNMENT PROCEDURE (F10) and confirm (Y) immediately "
        "after the byte edit -- this is mandatory, not optional, for the "
        "edit to take effect",
        "Turn the ignition key to OFF after a successful PROXI alignment, "
        "per the official manual's generic closing step",
    ],
    "risks": [
        "No documented UDS DID for this byte -- the write is to a "
        "vendor-internal PROXI index inferred from one forum post, not an "
        "independently confirmed register",
        "Sourced wording (giuliaforums.com, author FizzGiGG, 2024-04-05, "
        "reposted on giuliatech.com): \"pay close attention and only alter "
        "what you are attempting to alter as these settings can have dire "
        "consequences if changed unknowingly\" -- i.e. neighbouring bits "
        "in the same PROXI byte/area are reported to affect unrelated "
        "settings if the edit strays outside bits 4-5",
        "Single-source procedure for the exact byte/bit values -- not "
        "independently corroborated by a second author or by "
        "MultiEcuScan's own documentation for this specific byte (the "
        "vendor manual corroborates only the generic PROXI-alignment "
        "mechanism, via an unrelated Fiat Stilo example, not this byte)",
        "BCM also carries alarm/immobiliser-adjacent configuration on this "
        "platform -- 'it's just the body module' is not the same claim as "
        "'it's low-risk'",
    ],
    "reversible": True,
    "reversal_method": "Restore the backed-up byte value and re-run PROXI "
                       "ALIGNMENT PROCEDURE.",
    "verification": [
        "Confirm both-paddles-pull reaches Neutral and the right paddle "
        "returns to Drive (the EU behaviour being sought)",
        "Re-scan all modules for new DTCs after the change -- an "
        "adjacent-bit slip in the same byte can set an unrelated fault",
    ],
    "legal_warranty_note": "UNKNOWN -- no source found addressing the "
                          "warranty/legal status of this specific "
                          "configuration change.",
    "sources": [
        {"title": "Added Neutral to paddle shifters! (EU settings)",
         "url": "https://www.giuliaforums.com/threads/added-neutral-to-"
                "paddle-shifters-eu-settings.56872/",
         "author": "FizzGiGG", "date": "2024-04-05",
         "note": "Original claim; site now behind a paywall gateway "
                 "(tollbit), content not directly fetchable as of "
                 "2026-10-14."},
        {"title": "Multiecuscan (MES) - Popular Settings Compilation",
         "url": "https://giuliatech.com/t/multiecuscan-mes-popular-"
                "settings-compilation/80",
         "date": "accessed 2026-10-14",
         "note": "Reproduces the same byte 156 / bit-pattern / module "
                 "details as the giuliaforums.com original -- same "
                 "underlying claim, not an independent second source."},
        {"title": "MultiEcuScan User Guide (vendor manual)",
         "url": "local file: C:\\Program Files (x86)\\MultiEcuScan\\"
                "Multiecuscan User Guide.pdf",
         "note": "Corroborates the generic PROXI Alignment mechanism "
                 "(Adjustments -> edit value -> PROXI ALIGNMENT PROCEDURE "
                 "-> confirm -> key OFF) via an unrelated Fiat Stilo "
                 "cruise-control-light example. Does not mention paddle "
                 "shift or byte 156."},
        {"title": "Alfa Roimeo Stelvio 2.2 210 Paddle Shifter Enabling",
         "url": "https://www.multiecuscan.net/forum/viewtopic.php?t=8494",
         "note": "Thread exists on MultiEcuScan's own official forum per "
                 "search results; content not fetchable in this pass "
                 "(404 / TLS cert mismatch on alternate host). Open, "
                 "unconfirmed lead -- not used to corroborate the byte "
                 "value above."},
    ],
    "confidence": SINGLE_SOURCE,
    "research_doc": "docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md",
    "mes_function_id": "paddle_shifter_logic",
    "cuore_read_support": {
        "status": "needs_did_definition",
        "note": "Not readable by CUORE today -- no DID defined in "
                "cuore/live/did_catalog.py and none documented publicly.",
    },
    "cuore_write_support": {
        "status": "not_supported",
        "note": "NO-GO, decided 2026-10-14 -- CUORE never performs coding/"
                "configuration writes itself. MES-handoff only; see "
                "docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md "
                "section 7.",
    },
    "research_date": "2026-10-14",
}

_add(PADDLE_SHIFT_NA_EU)


# ===========================================================================
# The rest: mechanically seeded from mes_functions rows of kind
# coding/adjustment, minus paddle_shifter_logic (replaced by the fully
# sourced entry above). Nothing here is re-sourced beyond what
# mes_functions.py already carries; a field this converter cannot derive
# honestly from that row is marked "UNKNOWN" rather than guessed.
# ===========================================================================

def _how_method(f: dict[str, Any]) -> str:
    support = (f.get("mes_support") or "").strip().lower()
    if support.startswith("no"):
        return "the car's own menu" if "epb" in f["id"] else "dealer/wiTECH"
    return "MES"


def _risks_for(f: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    notes = (f.get("notes") or "").strip()
    if notes:
        risks.append(notes)
    menu = f.get("menu_path") or ""
    if "PROXI" in menu or "CAN Setup" in menu:
        risks.append(
            "Configuration write inside MES's PROXI/CAN-Setup dataset -- "
            "see paddle_shift_na_eu's own sourced caution about "
            "neighbouring bits in the same byte/area; this entry's own "
            "byte-level risk beyond that general caution is UNKNOWN unless "
            "noted above."
        )
    if not risks:
        risks.append(
            f"UNKNOWN -- no risk independently sourced for this exact "
            f"write beyond its general kind ({f['kind']})."
        )
    return risks


def _from_mes_function(f: dict[str, Any]) -> dict[str, Any]:
    """One modifications-catalogue row, mechanically reshaped from one
    :mod:`mes.mes_functions` row. See this module's own docstring, point 1."""
    return {
        "id": f["id"],
        "name": f["name"],
        "what_it_changes": f"{f['name']} on the {f['module']}.",
        "module": f["module"],
        "kind": f["kind"],  # "coding" or "adjustment" -- both valid KINDS
        "how": {"method": _how_method(f), "menu_path": f["menu_path"],
                "detail": f["menu_path"]},
        "prerequisites": list(f["prerequisites"]),
        "risks": _risks_for(f),
        "reversible": "UNKNOWN",
        "reversal_method": "",
        "verification": [],
        "legal_warranty_note": "UNKNOWN -- no source found addressing "
                              "the warranty/legal status of this write.",
        "sources": [{"title": f["id"], "url": f["source"],
                    "note": f.get("notes", "")}],
        "confidence": f["confidence"],
        "mes_function_id": f["id"],
        "cuore_write_support": {
            "status": "not_supported",
            "note": "CUORE never performs coding/configuration writes "
                    "itself -- MES-handoff only (decided 2026-10-14).",
        },
    }


for _f_row in mes_functions.all_functions():
    if _f_row["kind"] not in ("coding", "adjustment"):
        continue
    if _f_row["id"] == "paddle_shifter_logic":
        continue  # replaced by the fully-sourced PADDLE_SHIFT_NA_EU above
    _add(_from_mes_function(_f_row))


# ===========================================================================
# Public API
# ===========================================================================

def all_mods() -> list[dict[str, Any]]:
    """Every modification in catalogue order (paddle shift first)."""
    return [dict(MODS[i]) for i in _ORDER]


def mod(id_: str) -> Optional[dict[str, Any]]:
    """One modification by id, or ``None`` if unknown."""
    m = MODS.get(id_)
    return dict(m) if m is not None else None


def mods_for_module(module_substring: str) -> list[dict[str, Any]]:
    """Modifications whose ``module`` contains ``module_substring``
    (case-insensitive)."""
    want = (module_substring or "").strip().lower()
    if not want:
        return []
    return [dict(MODS[i]) for i in _ORDER if want in MODS[i]["module"].lower()]


_STOPWORDS = frozenset({
    "a", "an", "the", "this", "that", "is", "of", "for", "and", "or", "to",
    "s", "on", "in", "with", "per",
})


def _tokens(text: str) -> frozenset[str]:
    import re
    cleaned = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    return frozenset(t for t in cleaned.split() if t and t not in _STOPWORDS)


def search(text: str) -> list[dict[str, Any]]:
    """Modifications whose name matches ``text`` by token overlap, same
    rule as :func:`mes.mes_functions.search`."""
    hay_tokens = _tokens(text)
    if not hay_tokens:
        return []
    out = []
    for i in _ORDER:
        m = MODS[i]
        name_tokens = _tokens(m["name"])
        if not name_tokens:
            continue
        if name_tokens <= hay_tokens or (len(hay_tokens) >= 2 and hay_tokens <= name_tokens):
            out.append(dict(m))
    return out


__all__ = ["KINDS", "PADDLE_SHIFT_NA_EU", "all_mods", "mod", "mods_for_module", "search"]
