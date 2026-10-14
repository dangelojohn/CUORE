"""Hand-sourced DTC descriptions for specific codes on this platform.

This is a *small, hand-curated* table -- the opposite of :mod:`mes.dtc_text`
(MES's own shipped language files, which carry no DTC-code key at all; see
that module's docstring). Every entry here was either already established
elsewhere in this repo's own knowledge (:mod:`mes.electrical`,
:mod:`mes.systems`, :mod:`mes.faulttree`) -- in which case this module keeps
that existing source rather than re-deriving or restating it differently --
or was looked up once, specifically for this platform (Alfa Romeo Giulia /
Stelvio), graded ``SINGLE-SOURCE`` with the URL and the date it was checked.

**Never invented.** A code with nothing sourced either way is reported as
``UNKNOWN`` with the instruction to use the service manual / TechAuthority,
never filled in with a guess.

**U-codes get an honest generic note, not a fabricated specific one.** SAE
J2012 reserves the U1xxx range for manufacturer-defined network codes (see
:func:`mes.dtc.code_authority`, which already resolves U1xxx to "manufacturer
(FCA)"). Where this table has nothing more specific sourced for a U1xxx code,
:func:`code_description` still surfaces that generic-range fact honestly,
rather than leaving the caller to think nothing at all is known.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Shown whenever a code has no sourced description -- never replaced with a
#: guess, however plausible.
UNKNOWN_TEXT = "not sourced in this repo -- use the service manual, TechAuthority"


@dataclass(frozen=True)
class CodeDescription:
    """One code's sourced description (independent of the FTB suffix)."""

    code: str
    text: str
    source: str
    confidence: str  # "CONFIRMED" | "SINGLE-SOURCE" | "UNKNOWN"
    url: str | None = None
    checked: str | None = None  # date the URL was verified, "YYYY-MM-DD"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "code": self.code,
            "text": self.text,
            "source": self.source,
            "confidence": self.confidence,
        }
        if self.url:
            d["url"] = self.url
        if self.checked:
            d["checked"] = self.checked
        return d


#: Codes from tonight's live UDS sweep (2018 Stelvio, 2026-10-13). Grouped by
#: how the description was sourced -- repo-internal first, then web-sourced.
_DESCRIPTIONS: tuple[CodeDescription, ...] = (
    # --- already sourced elsewhere in this repo; kept as-is -----------------
    CodeDescription(
        "U1713",
        "Network/communication cascade code naming BCM -- a lost-"
        "communication DTC, not a component-internal fault. Part of the "
        "same BCM/RFHUB/DTCM comms-cascade family as U1711/U1712/U1716/"
        "U2054/U0100/B1040 (one network event reported as many codes).",
        source=("mes/faulttree.py NETWORK_CASCADE + this repo's "
                "CONNECTIVITY_AND_SGW.md section 1 (platform doc: lost-"
                "communication DTCs 'name exactly the modules on the "
                "unreachable buses')"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U1765",
        "BCM: lost communication with the RF Hub. Not named in any TSB/"
        "platform doc in this repo, but this car logged U1765-86 alongside "
        "U1711/U1712/U1713 in the same session (SCAN_2609152048) -- the "
        "same lost-communication family, treated with the same sequence.",
        source=("mes/faulttree.py NETWORK_CASCADE comment, grounded in this "
                "car's own SCAN_2609152048 log (repo corpus, not a document)"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "B1176",
        "Window-riser motor circuit fault. This car's electrical-path "
        "knowledge (mes/electrical.py window_riser_circuit) traces it only "
        "at a plain-words level: door module -> window-motor circuit -> "
        "door harness connector -> ground, with the rear-left context from "
        "the RLDM (Rear Left Door Module, mes/modules.py). No TSB in this "
        "repo's knowledge base covers B1176.",
        source=("mes/electrical.py window_riser_circuit + mes/systems.py "
                "B1176 rule (\"generic body-module DTC definition; no "
                "model-specific TSB found\") + mes/modules.py RLDM"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "B1040",
        "BCM communications/network code, part of the BCM power/comms "
        "cascade family together with U1700.",
        source="mes/systems.py Bulletin S1808000005 (BCM power/comms cascade)",
        confidence="CONFIRMED",
    ),
    # --- looked up once for this platform, web-sourced ----------------------
    CodeDescription(
        "U1736",
        "Entertainment/Telematic Module (ETM/LTM) -- missing message. "
        "Reported on Stelvio as \"ETM node on B-CAN, no signal/message\": a "
        "communication/CAN-bus error between the ETM and other modules, not "
        "a component-internal ETM fault.",
        source="dtcdecode.com Alfa Romeo U1736-87",
        confidence="SINGLE-SOURCE",
        url="https://www.dtcdecode.com/Alfa-Romeo/U1736-87",
        checked="2026-10-13",
    ),
    CodeDescription(
        "B10AA",
        "BCM \"check configuration failed\": the Body Control Module "
        "detected a mismatch between the vehicle and its PROXI "
        "configuration -- consistent with this occurrence's own FTB `4A` "
        "(\"incorrect component installed\"). Can be triggered by a "
        "component/module added or replaced that isn't recognised by the "
        "original PROXI configuration.",
        source="dtcdecode.com Alfa Romeo B10AA-4A",
        confidence="SINGLE-SOURCE",
        url="https://www.dtcdecode.com/Alfa-Romeo/B10AA-4A",
        checked="2026-10-13",
    ),

    # --- from the 2026-10-14 MES scan ---------------------------------------
    CodeDescription(
        "U0100",
        "SAE J2012 standard code: Lost Communication With ECM/PCM 'A'. "
        "code_authority() already resolves U0xxx as the generic (SAE) "
        "range, not manufacturer-defined, so this is the published "
        "standard meaning, not a platform guess. On this car it was logged "
        "by the DTCM (Magna Q4 transfer case control module) with FTB `87` "
        "(missing message) -- the DTCM expected a periodic message from "
        "the ECM/PCM and didn't get one. Same reading this repo already "
        "gives it elsewhere: mes/drivetrain_specs.py TRANSFER_CASE_DTCS "
        "calls U0100-87 a bystander code from whole-vehicle serial UDS "
        "sweeps on this car's own scans, not a real transfer-case fault, "
        "and it is one of the named members of the BCM/RFHUB/DTCM "
        "lost-communication cascade (mes/faulttree.py NETWORK_CASCADE) "
        "together with U1711/U1712/U1713/U1716/U1765/U1736/U2054/B1040 -- "
        "one network event reported as many codes.",
        source=("SAE J2012-DA generic U0xxx definition (mes/dtc.py "
                "code_authority) + mes/drivetrain_specs.py "
                "TRANSFER_CASE_DTCS (this car's own SCAN_2609041953) + "
                "mes/faulttree.py NETWORK_CASCADE"),
        confidence="CONFIRMED",
    ),
    CodeDescription(
        "U2054",
        "RFHUB (Continental RF hub): dtcdecode.com's Alfa Romeo entry for "
        "U2054-87 gives the exact text \"Bcm_Command Message 2 - Missing "
        "Message\" (listed under BCM, FTB 87/missing message) -- the "
        "module expected a periodic BCM command message and didn't "
        "receive it in time. code_authority() resolves U2xxx as "
        "manufacturer-defined (FCA), so -- unlike U0100 -- there is no "
        "SAE-published generic meaning behind this one, only the "
        "dtcdecode.com entry itself. On this car it is one of the named "
        "members of the BCM/RFHUB/DTCM lost-communication cascade (mes/"
        "faulttree.py NETWORK_CASCADE) together with U1711/U1712/U1713/"
        "U1716/U1765/U1736/U0100/B1040 -- one network event reported as "
        "many codes, not a standalone RF-hub fault.",
        source="dtcdecode.com Alfa Romeo U2054-87",
        confidence="SINGLE-SOURCE",
        url="https://www.dtcdecode.com/Alfa-Romeo/U2054-87",
        checked="2026-10-14",
    ),
)

DESCRIPTIONS: dict[str, CodeDescription] = {d.code: d for d in _DESCRIPTIONS}


def _u_code_range_note(code: str) -> str | None:
    """Honest, generic SAE J2012 meaning for a U1xxx code with nothing more
    specific sourced -- never a stand-in for an actual description."""
    c = code.strip().upper()
    if len(c) >= 2 and c[0] == "U" and c[1] == "1":
        return ("U1xxx is the SAE J2012 manufacturer-defined network range "
                "-- generic network/communication fault, no published "
                "generic text for this exact code")
    return None


def code_description(code: str) -> dict[str, Any]:
    """This platform's sourced description for ``code``, or an honest unknown.

    Always returns a dict (never ``None``) so a caller never has to special-
    case "nothing found" separately from "found but empty" -- an UNKNOWN
    result still carries ``confidence`` and the instruction to use the
    service manual/TechAuthority, it just carries no invented text.
    """
    base = code.strip().upper()
    # Tolerate a full "CODE-FTB" token as well as a bare code.
    base = base.split("-", 1)[0]
    found = DESCRIPTIONS.get(base)
    if found:
        return found.to_dict()

    note = _u_code_range_note(base)
    text = UNKNOWN_TEXT if not note else f"{UNKNOWN_TEXT} ({note})"
    return {
        "code": base,
        "text": text,
        "source": "none",
        "confidence": "UNKNOWN",
    }
