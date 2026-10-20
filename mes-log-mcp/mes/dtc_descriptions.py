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
        "BCM network code, MES text \"Engine control (NCM) - Signal/message "
        "erratic\" (FTB 2F = signal erratic): the BCM reports that messages "
        "it receives from the engine control module are erratic. Direction "
        "is ECM to BCM; it names a received signal, not a component-"
        "internal BCM fault. Listed in this repo's BCM/RFHUB/DTCM network "
        "cascade family with U1711/U1712/U1716/U2054/U0100/B1040 (one "
        "network event can be reported as many codes). Earlier wording "
        "here called it a \"lost-communication\" code; the FTB says erratic, "
        "not missing (a missing message is FTB 87).",
        source=("MES SCAN text on this car (SCAN_2606070954 .. "
                "SCAN_2610190039) + FTB 2F per mes/dtc.py (SAE J2012-DA) + "
                "mes/faulttree.py NETWORK_CASCADE + CONNECTIVITY_AND_SGW.md "
                "section 1"),
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

    # --- added 2026-10-20 (docs/research/NON_EVAP_CODES_2026-10-20.md) -----
    # Texts are the wording MES printed on this car's own logs; outside
    # documents are labelled OUTSIDE LITERATURE. None is a service-manual
    # definition: use TechAuthority / wiTECH for that.
    CodeDescription(
        "U1711",
        "BCM network code, MES text \"Brake system (NFR) - Signal/message "
        "erratic\" (FTB 2F): the BCM reports erratic messages from the brake "
        "system module (MES label NFR; ABS/ESP). Same family as U1712, "
        "which carries identical MES text. Seen only on the BCM, 2026-06-07 "
        "to 2026-09-25, not since the 2026-09-29 BCM clear.",
        source=("MES SCAN text on this car (SCAN_2606070954 .. "
                "SCAN_2609252027) + FTB 2F per mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U1712",
        "BCM network code, MES text \"Brake system (NFR) - Signal/message "
        "erratic\" (FTB 2F): identical MES wording to U1711; MES does not "
        "say which message differs. Seen on the BCM 2026-06-07 to "
        "2026-09-25.",
        source=("MES SCAN text on this car (SCAN_2606070954 .. "
                "SCAN_2609252027) + FTB 2F per mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U1716",
        "BCM network code, MES text \"Electric Steering (NGE) - "
        "Signal/message erratic\" (FTB 2F): erratic messages from the "
        "electric power steering module. Seen once, BCM, 2026-08-27.",
        source=("MES SCAN text on this car (SCAN_2608271131) + FTB 2F per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U1700",
        "Network code naming the body computer. This car: ABS freeze-frame "
        "record, MES FES text \"U1700-87 - Body computer (BCM/NBC)\" (FTB 87 "
        "= missing message), seen once (ABS, 2026-09-04). OUTSIDE "
        "LITERATURE: FCA bulletins 08-103-20 (2020 Stelvio) and 08-107-20 "
        "(2019 Giulia) print \"U1700-87 Body Control Module (BCM) - Missing "
        "Message\" as a code set in the DSCM (drive-mode selector) module; "
        "other model years and another module, so context only.",
        source=("MES FES text on this car (FESLog_2609042001) + FTB 87 per "
                "mes/dtc.py; outside: NHTSA "
                "static.nhtsa.gov/odi/tsbs/2020/MC-10187696-9999.pdf and "
                "MC-10187708-9999.pdf, opened 2026-10-20"),
        confidence="SINGLE-SOURCE",
        url="https://static.nhtsa.gov/odi/tsbs/2020/MC-10187696-9999.pdf",
        checked="2026-10-20",
    ),
    CodeDescription(
        "U1701",
        "DASM network code, MES text \"Error in communication with engine "
        "control unit (ECU) - Signal/message invalid\" (FTB 86). Seen once, "
        "2026-06-07 10:03, nine minutes after a DASM clear, during a MES "
        "session that was reading other modules.",
        source=("MES SCAN text on this car (SCAN_2606071003) + FTB 86 per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U1702",
        "DASM network code, MES text \"EPS electric steering (NGE) - Missing "
        "message\" (FTB 87): the radar/driver-assist module did not receive "
        "an expected message from the steering module. Seen once, DASM, "
        "2026-10-19 00:39.",
        source=("MES SCAN text on this car (SCAN_2610190039) + FTB 87 per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U1960",
        "EPS code, MES text \"Error in communication with engine control "
        "unit (ECU) - Value of signal protection calculation incorrect\" "
        "(FTB 83: the message protection value was wrong). Seen once, EPS, "
        "read 2026-09-04 20:08, never re-read.",
        source=("MES SCAN text on this car (SCAN_2609042008) + FTB 83 per "
                "mes/dtc.py (mes-table)"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U0422",
        "DTCM (Magna Q4 transfer-case module) code, MES text \"Error in "
        "communication with Body Computer Module (BCM) - Signal/message "
        "invalid\" (FTB 86). U0xxx is the SAE J2012 generic network range. "
        "Seen once, 2026-10-19 00:39, together with U0100-87.",
        source=("MES SCAN text on this car (SCAN_2610190039) + FTB 86 per "
                "mes/dtc.py + SAE generic U0xxx range (mes/dtc.py "
                "code_authority)"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U0418",
        "HALF (haptic lane feedback module) code, MES text \"Error in "
        "communication with ABS module - Signal/message invalid\" (FTB 86). "
        "Seen once, read 2026-09-04 20:08 on the chassis sweep, never "
        "re-read.",
        source=("MES SCAN text on this car (SCAN_2609042008) + FTB 86 per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "U0428",
        "AFLS (self-adaptive headlamp module) code, MES text \"Steering "
        "angle sensor - Signal/message invalid\" (FTB 86): the headlamp "
        "module judged the steering-angle message invalid. Seen once, read "
        "2026-09-04 20:08, never re-read.",
        source=("MES SCAN text on this car (SCAN_2609042008) + FTB 86 per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "B1029",
        "IPC code, MES text \"Lost communication with Steering module (SCM) "
        "- Signal/message plausibility\" (FTB 64). Seen once, IPC, "
        "2026-08-27, in the same scan as B102E.",
        source=("MES SCAN text on this car (SCAN_2608271131) + FTB 64 per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "B102E",
        "IPC code, MES text \"Communication with Body Computer (BCM/NBC) - "
        "Signal/message plausibility\" (FTB 64). Seen once, IPC, 2026-08-27, "
        "with B1029.",
        source=("MES SCAN text on this car (SCAN_2608271131) + FTB 64 per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "C141B",
        "DASM code, MES text \"Camera blinded/obstructed/blocked - Component "
        "or system operation obstructed or blocked\" (FTB 97). Read on 8 "
        "scans from 2026-09-02 to 2026-10-19 (not on 2026-09-15 or "
        "2026-09-29). MES text only; no outside document naming C141B was "
        "found on 2026-10-20.",
        source=("MES SCAN text on this car (SCAN_2609021445 .. "
                "SCAN_2610190039) + FTB 97 per mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "C141C",
        "DASM code, MES text \"Private CAN between HALF and DASM - "
        "Signal/message invalid\" (FTB 86). OUTSIDE LITERATURE: FCA bulletin "
        "08-045-20 (April 2020; 2020 Giulia/Stelvio, North America, GU "
        "built on or before 2019-12-20) prints \"C141C-86 - Video Camera "
        "Private Can Communication Failure - Signal Invalid\" with B1006-49 "
        "and C1999-86 and an EVIC forward-collision-warning "
        "limited-functionality message; its repair is a BCM Restore Vehicle "
        "Configuration plus Proxi Configuration Alignment. Model year 2020, "
        "not this 2018 car, and no record from this car shows that EVIC "
        "message: context only.",
        source=("MES SCAN text on this car (SCAN_2606070954 .. "
                "SCAN_2610190039) + outside: NHTSA "
                "static.nhtsa.gov/odi/tsbs/2020/MC-10175724-9999.pdf, opened "
                "2026-10-20"),
        confidence="SINGLE-SOURCE",
        url="https://static.nhtsa.gov/odi/tsbs/2020/MC-10175724-9999.pdf",
        checked="2026-10-20",
    ),
    CodeDescription(
        "C1408",
        "DASM code, MES text \"ESP control - Signal/message invalid\" (FTB "
        "86): the radar module judged a stability-control message invalid. "
        "Seen 2026-08-27, 2026-09-04 (DASM clear FAILED that evening) and "
        "2026-10-19. A Stelvio owner thread listing \"C-1408-86 (ESC)\" with "
        "C141C-86 traced to a low 12 V battery (stelvioforum.com thread "
        "24275, in mes/experience.py).",
        source=("MES SCAN text on this car (SCAN_2608271131, SCAN_2609041953, "
                "SCAN_2610190039) + FTB 86 per mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "C1403",
        "DASM code, MES text \"EPS electric steering (NGE) - Signal/message "
        "invalid\" (FTB 86). Seen once, 2026-08-27.",
        source=("MES SCAN text on this car (SCAN_2608271131) + FTB 86 per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "C1431",
        "DASM code, MES text \"Lateral acceleration/YAW sensors - "
        "Signal/message invalid\" (FTB 86). Seen once, 2026-08-27.",
        source=("MES SCAN text on this car (SCAN_2608271131) + FTB 86 per "
                "mes/dtc.py"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "C104B",
        "ABS (Continental MK C1) code, MES FES text \"Leaks in hydraulic "
        "group\" (FTB 92 = performance or incorrect operation). Brake-safety "
        "code. Seen once, FESLog_2609042001 (2026-09-04 20:01): freeze "
        "frame at standstill, brake pedal pressed, hydraulic circuit 11.1 "
        "bar; cleared in that session; the ABS has not been read for DTCs "
        "since (it was silent to CUORE sweep on 2026-10-15). MES text only; "
        "the text does not say fluid was lost.",
        source=("MES FES text on this car (FESLog_2609042001) + FTB 92 per "
                "mes/dtc.py (mes-table)"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "P1189",
        "ECM code, MES FES text \"Intake pressure sensor\". Seen once, "
        "FESLog_2509241345 (2025-09-24): freeze frame at key-on, engine "
        "off, 12.1 V, shared with P00F5, P0098 and P105E at the same "
        "operating time; absent from every later ECM read.",
        source=("MES FES text on this car (FESLog_2509241345)"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "P00F5",
        "ECM code, MES FES text \"Humidity sensor\". Seen once, "
        "FESLog_2509241345 (2025-09-24), key-on freeze frame shared with "
        "P1189/P0098/P105E.",
        source=("MES FES text on this car (FESLog_2509241345)"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "P105E",
        "ECM code, MES FES text \"Humidity sensor\". Seen once, "
        "FESLog_2509241345 (2025-09-24), key-on freeze frame shared with "
        "P1189/P00F5/P0098.",
        source=("MES FES text on this car (FESLog_2509241345)"),
        confidence="SINGLE-SOURCE",
    ),
    CodeDescription(
        "P0098",
        "ECM code, MES FES text \"Air temperature sensor\". Seen once, "
        "FESLog_2509241345 (2025-09-24), key-on freeze frame shared with "
        "P1189/P00F5/P105E.",
        source=("MES FES text on this car (FESLog_2509241345)"),
        confidence="SINGLE-SOURCE",
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
