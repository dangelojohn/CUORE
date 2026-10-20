"""Per-code findings store: what the 2026-10-20 reviews established about each
non-EVAP code on the reference car, keyed by the full MES code (``CODE-FTB``).

Source documents (all under ``docs/research/``):
``NON_EVAP_CODES_2026-10-20.md``, ``CODES_ADAS_CAMERA_2026-10-20.md``,
``CODES_BODY_INFOTAINMENT_2026-10-20.md``,
``NETWORK_PATTERN_READINGS_2026-10-20.md``,
``NETWORK_PATTERN_LITERATURE_2026-10-20.md``.

Evidence classes are kept apart on purpose:

* ``readings``    -- READINGS from this car's logs (MES scans, FES, CUORE
  UDS reads). Dates are 2026 unless stated.
* ``literature``  -- OUTSIDE LITERATURE (bulletins, web pages, forums about
  other cars/years). Never a reading of this car.
* ``owner``       -- statements by the owner; attested, not read.

Nothing here is invented: a field with no sourced finding is left empty and
the renderer says so. ``lookup`` takes a full code (``C104B-92``) or a base
code (``C104B``, every FTB variant) and an optional module.
"""

from __future__ import annotations

import re
from typing import Any, Optional

AS_OF = "2026-10-20"

#: classification key -> (label shown, short explanation)
CLASSES: dict[str, str] = {
    "real": "Real",
    "service_induced": "Service-induced (owner-attested), not yet confirmed by a reading",
    "probable_artefact": "Probable tool artefact",
    "possible_bystander": "Possible bystander",
    "downstream_bcm": "Downstream of the BCM network cluster",
    "bcm_cluster": "Core of the BCM network cluster",
    "readiness_only": "Readiness flag only (not a fault)",
}

_RDOC = "docs/research/NETWORK_PATTERN_READINGS_2026-10-20.md"
_NDOC = "docs/research/NON_EVAP_CODES_2026-10-20.md"
_ADOC = "docs/research/CODES_ADAS_CAMERA_2026-10-20.md"
_BDOC = "docs/research/CODES_BODY_INFOTAINMENT_2026-10-20.md"

_FTB = ("https://oficinabrasil.com.br/noticia/tecnicas/quais-os-tipos-de-falha-sao-"
        "descritas-em-um-dtc-diagnostic-trouble-codes")
_TAT86 = "https://www.tat.net.au/scandata/codes/code-view.php?id=8470"
_S1808 = "https://static.nhtsa.gov/odi/tsbs/2020/MC-10175655-9999.pdf"
_S1708 = "https://static.nhtsa.gov/odi/tsbs/2020/MC-10184414-9999.pdf"
_TC18151 = "https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018151"
_08045 = "https://static.nhtsa.gov/odi/tsbs/2020/MC-10175724-9999.pdf"
_S2308 = "https://static.nhtsa.gov/odi/tsbs/2023/MC-10234434-9999.pdf"

_NETWORK_LIT = [
    {"text": "Ranked outside-literature causes for this cluster: (1) BCM supply/ground, fuse F82 "
             "and the stand-alone BCM fuse; (2) connector/terminal faults; (3) water in the BCM "
             "or A-pillar connector (recall 18V205 / Transport Canada 2018151, VIN scope not known). "
             "Ranking is inference; no source gives a probability.",
     "url": _S1808},
    {"text": "STAR S1708000262: intermittent CAN private/LIN codes, inspect connector terminals.",
     "url": _S1708},
    {"text": "Transport Canada recall 2018151 (BCM water corrosion, 2018 Stelvio).", "url": _TC18151},
]

_NETWORK_LADDER = [
    "Ask the owner: battery work, jump start, aftermarket electrical, engine bay washed (free).",
    "Multimeter: battery at rest after 12 h, during cranking and running; terminals.",
    "BCM supply/ground voltage drop under load, fuse F82 and the stand-alone BCM fuse; "
    "look at the BCM/A-pillar connector for moisture or corrosion.",
    "Read-only mirror-code snapshot in one key-on session while U1713 is active: BCM, ABS, ECM "
    "(plus DTCM/IPC/RFHUB) with full status bytes, before any clear.",
    "Frame census of ABS, ECM and BCM frames at the OBD port on the verified CAN-C bitrate.",
]

_NETWORK_PROOF = ("No U17xx/U0xxx/B1040 on three reads over at least 21 days (longer than the longest "
                  "clear-to-return seen, 14 days), including one read under the conditions that "
                  "showed them, status bytes read before any clear. A read within hours of a clear "
                  "does not count.")


def _e(code: str, module: str, **kw: Any) -> dict[str, Any]:
    kw.update({"code": code, "module": module})
    kw.setdefault("safety", False)
    kw.setdefault("safety_note", "")
    kw.setdefault("owner", [])
    kw.setdefault("literature", [])
    return kw


FINDINGS: list[dict[str, Any]] = [
    _e("C104B-92", "ABS", safety=True,
       safety_note="SAFETY: brake-hydraulic code name. Confirm with an ABS DTC read (grey cable).",
       meaning="Leaks in hydraulic group (ABS, Continental MK C1). FTB 92 per the MES text.",
       meaning_source="MES text; FTB list: " + _FTB,
       readings=[
           "One occurrence: FESLog 2026-09-04 20:01:10, cleared in the same session. Every ABS DTC read "
           "that ever succeeded falls within 8 minutes that evening (later reads clean).",
           "Freeze frame: standstill, engine off, 12.1 V, brake pedal ON, hydraulic circuit 11.1 bar, "
           "pedal pressure 3.6 bar, startups 14356.",
           "ABS not read for DTCs since; CUORE's 2026-10-15 00:12 sweep got no reply (silence, not 'no codes').",
       ],
       classification="service_induced",
       classification_note="Owner statement 2026-10-20: the code was caused by the owner's own brake-pad "
                           "inspection that evening (pedal pressed during pad/caliper work) and is fixed. "
                           "Consistent with the standstill, pedal-pressed freeze frame. Attested, not read.",
       owner=["Owner 2026-10-20: set 2026-09-04 by the owner's own brake-pad inspection; states it is fixed."],
       implications="If the owner's account is right there is no leak. Until an ABS read confirms no "
                    "C104B-92, the code's name keeps it on the safety list.",
       ladder=[
           "Read-only ABS DTC read with the grey cable; save the log and freeze frames before any clear.",
           "Optional: brake fluid level and colour against MIN/MAX, look for wetness at calipers, hoses "
           "and the ABS block.",
           "If C104B-92 is listed active, the fluid is low or wet, or the pedal sinks under steady "
           "pressure: stop driving and have it inspected.",
       ],
       proof="ABS DTC read with the grey cable shows no C104B-92.",
       literature=[
           {"text": "Catalogue recall 17V823 (contaminated brake fluid, 2018 Giulia/Stelvio, VIN check "
                    "needed) and TSB 08-044-19 (ABS flash, pedal feel). Neither names C104B. No document "
                    "found for 'C104B-92' (search 2026-10-20).",
            "url": ""}]),
    _e("U1700-87", "ABS",
       meaning="Body computer (BCM/NBC) missing message, seen from the ABS.",
       meaning_source="MES text; FCA wording 'U1700-87 BCM - Missing Message': " + _08045,
       readings=[
           "One occurrence: FESLog 2026-09-04 20:01:10 (cleared). Freeze frame: 10.6 V, startups 14280, "
           "speed 0, pedal off, hydraulic circuit 2.6 bar.",
           "The only low-voltage reading in the corpus; startups 14280 is one count before the ECM's "
           "2026-08-27 P0455 (14281). ABS not read for DTCs since.",
       ],
       classification="bcm_cluster",
       classification_note="Reciprocal of BCM U1711/U1712 (ABS says the BCM message is missing). "
                           "Supply-side observation, not a brake one.",
       implications="A low-voltage moment near an engine start can set body/ABS communication codes "
                    "(inference; no BCM freeze frame exists to test it).",
       ladder=_NETWORK_LADDER,
       proof="ABS read (grey cable) in the mirror-code snapshot shows no U1700-87 while the BCM shows no "
             "U1713/U1711/U1712. " + _NETWORK_PROOF,
       literature=_NETWORK_LIT),
    _e("U1711-2F", "BCM",
       meaning="Brake system (NFR) signal erratic: the BCM says messages it receives from the ABS are erratic "
               "(FTB 2F is 'erratic', a lost message is FTB 87).",
       meaning_source="MES text; " + _FTB,
       readings=[
           "Six scans, 2026-06-07 to 09-25 (last 2026-09-25 20:27); absent in every later BCM read.",
           "Always appears and disappears together with U1712 (6 of 6) and never without U1713.",
           "Mirror: ABS U1700-87 at 10.6 V (2026-09-04).",
       ],
       classification="bcm_cluster",
       classification_note="The BCM is the only module with complaints in both directions.",
       implications="No driver symptom recorded. Looks like it stopped, not like it was cleared away.",
       ladder=_NETWORK_LADDER, proof=_NETWORK_PROOF, literature=_NETWORK_LIT),
    _e("U1712-2F", "BCM",
       meaning="Brake system (NFR) signal erratic (second message of the same ABS node).",
       meaning_source="MES text; " + _FTB,
       readings=[
           "Six scans, 2026-06-07 to 09-25; always together with U1711, last 2026-09-25 20:27.",
           "Absent in every later BCM read (09-28, 09-29, 10-04, 10-08, 10-13, 10-14, 10-19).",
       ],
       classification="bcm_cluster",
       classification_note="Subset of the U1713 episodes: U1713 continued after the pair stopped, which a "
                           "uniform supply fault would not do.",
       implications="No current evidence; watch with the cluster.",
       ladder=_NETWORK_LADDER, proof=_NETWORK_PROOF, literature=_NETWORK_LIT),
    _e("U1713-2F", "BCM",
       meaning="Engine control (NCM) signal erratic: the BCM says messages it receives from the ECM are erratic.",
       meaning_source="MES text; " + _FTB,
       readings=[
           "10 of 18 eight-module scans, 2026-06-07 to 10-19; failing now (CUORE status 0x0F at 10-13 20:24, "
           "10-19 00:23 and 00:30; MES 10-19 00:39).",
           "Present at 14.0 to 14.5 V, so a low supply is not needed for the code to be present at read time.",
           "Returned after every BCM clear except 09-29 and 10-14 19:02 (clear 8 d 22 h or more once); "
           "return time 2.6 to over 8.9 days.",
       ],
       classification="bcm_cluster",
       classification_note="The most persistent cluster code; cause unknown.",
       implications="No driver symptom recorded. Reported by many receivers: network-level condition.",
       ladder=_NETWORK_LADDER, proof=_NETWORK_PROOF, literature=_NETWORK_LIT),
    _e("C141C-86", "DASM",
       meaning="Private CAN between HALF (camera) and DASM (radar), signal invalid.",
       meaning_source="MES text; FCA wording 'Video Camera Private Can Communication Failure - Signal Invalid': "
                      + _08045,
       readings=[
           "7 of 18 DASM reads: 06-07 09:54, 08-27, 09-04, 09-15, 09-25 (x2), 10-19. The 09-04 clear FAILED.",
           "Present in 6 of 6 scans where the BCM U1711/U1712 pair was present; 1 of 12 without it (10-19). "
           "Shared-clear confound: DASM and BCM were always cleared in the same session.",
       ],
       classification="downstream_bcm",
       classification_note="Tracks the BCM U1711/U1712 pair. Do not fix separately while the pair is worked.",
       implications="Camera-dependent features may degrade; no dashboard message is on record.",
       ladder=["Work the BCM network cluster first, then re-read the DASM.",
               "If it persists with the pair absent: HALF and DASM connectors and the windscreen-header to "
               "bumper harness; read the HALF as well (grey cable)."],
       proof="Absent on DASM re-reads on separate days after U1711/U1712 stayed absent; one clean read does not count.",
       literature=[{"text": "08-045-20 (2020 builds only, not this 2018 car): BCM Restore Vehicle "
                            "Configuration plus PROXI alignment. Candidate, not a documented fix for 2018.",
                    "url": _08045}]),
    _e("C141B-97", "DASM",
       meaning="Camera blinded/obstructed/blocked. Stored in the DASM (radar), which reports on the camera's view.",
       meaning_source="MES text; FTB 97 = operation obstructed or blocked: " + _FTB,
       readings=[
           "8 of 18 DASM reads: 09-02 (first), 09-04, 09-25 (x2), 09-28, 10-08, 10-14, 10-19; absent 09-15, "
           "09-29, 10-04 and 10-08 09:26 after a clear.",
           "Independent of the BCM cluster: present with the BCM clean on 10-08 09:20.",
           "DASM never read by CUORE: no status byte, no freeze frame. No windscreen, tint or dashcam record.",
       ],
       classification="real",
       classification_note="Possible real condition at the camera's view; the one DASM code with a cheap "
                           "physical test.",
       implications="Lane keep, forward collision warning and ACC may be limited; treat as unavailable while live. "
                    "No dashboard message is recorded.",
       ladder=["Owner: any windscreen replacement, tint, dashcam, sticker or device in the camera's view.",
               "STAR S2308000020: clean the windscreen (outside and inside) in the camera patch first; "
               "do not calibrate or replace before that.",
               "Re-read the DASM (and HALF, grey cable) after a daylight drive in dry weather.",
               "Only if it persists on clean glass or after windscreen work: dealer/ADAS calibration "
               "(not possible with MES)."],
       proof="Absent on at least two DASM reads on separate days over at least 21 days, including a daylight "
             "drive. A clean read the day after a clear is not proof.",
       literature=[{"text": "STAR S2308000020: 'ACC/FCW Limited Functionality Clean Windshield', camera "
                            "blinded by sun/rain/dirt; clean first, no repair. Code is C14A5, not C141B; "
                            "vehicle not named.", "url": _S2308},
                   {"text": "I-CAR: 2018 Giulia camera needs calibration after windscreen replacement or "
                            "when a DTC indicates.", "url": "https://rts.i-car.com/oem-calibration-requirements-search/calv-2719.html"}]),
    _e("C1408-86", "DASM",
       meaning="ESP control signal invalid (the DASM is the receiver).",
       meaning_source="MES text; " + _FTB,
       readings=[
           "3 scans: 08-27, 09-04 (stayed after the FAILED clear), 10-19. Gone by 09-15 without a successful "
           "clear in between.",
           "Not bound to the BCM pair (absent 06-07, 09-15, 09-25).",
       ],
       classification="downstream_bcm",
       classification_note="Receiver of an ABS/ESP signal; says nothing about hydraulics or sensors. "
                           "Order of cause not proven.",
       implications="None shown by the readings.",
       ladder=["Read ABS, EPS, DASM and HALF in one session (grey cable for HALF), BCM state in the same "
               "session; log voltage.", "Then the BCM network cluster ladder."],
       proof="Absent on DASM re-reads on separate days with ABS/EPS/DASM read in the same session and BCM "
             "U1713/U1711/U1712 not failing at the same time.",
       literature=_NETWORK_LIT[:1]),
    _e("C1431-86", "DASM",
       meaning="Lateral acceleration/YAW sensor signal invalid (the DASM is the receiver).",
       meaning_source="MES text; " + _FTB,
       readings=["One scan only: 2026-08-27 11:31, in a burst of 14 codes in five modules; cleared, clean at 11:36 and 11:41."],
       classification="downstream_bcm",
       classification_note="Single burst with the BCM trio; no action, watch only.",
       implications="None shown.", ladder=["Watch only; fold into the ABS/EPS/DASM same-session read."],
       proof="Not seen again over three reads across at least 21 days.", literature=[]),
    _e("C1403-86", "DASM",
       meaning="EPS (electric steering) signal invalid (the DASM is the receiver).",
       meaning_source="MES text; " + _FTB,
       readings=["One scan only: 2026-08-27 11:31 (same burst as C1431-86 and BCM U1716-2F)."],
       classification="downstream_bcm",
       classification_note="Single burst with the BCM trio; no action, watch only.",
       implications="None shown.", ladder=["Watch only; fold into the ABS/EPS/DASM same-session read."],
       proof="Not seen again over three reads across at least 21 days.", literature=[]),
    _e("U0418-86", "HALF",
       meaning="Error in communication with ABS, signal/message invalid (seen from the HALF camera).",
       meaning_source="MES text; " + _FTB,
       readings=["One sighting: SCAN 2026-09-04 20:08, the only HALF read ever, 15 minutes after DASM C141B/C1408/C141C. "
                 "Not cleared, not read again."],
       classification="downstream_bcm",
       classification_note="Receiver-side; one read, so not intermittent or chronic. (BCM U0418-96 at status 0x40 is a "
                           "different code.)",
       implications="None shown.",
       ladder=["Read the HALF again with the grey A6 cable; if absent, record as a single event; if present, "
               "it belongs to the ABS/EPS/BCM cluster work. Do not clear as a fix."],
       proof="Absent on at least two HALF reads on separate days, ABS read in the same session.", literature=[]),
    _e("U1702-87", "DASM",
       meaning="EPS electric steering (NGE) missing message, stored in the DASM (not in the EPS).",
       meaning_source="MES text; FTB 87 = missing message: " + _TAT86,
       readings=["One sighting: SCAN 2026-10-19 00:39. First seen between 10-14 08:59 and 10-19 00:39, an interval "
                 "containing the 10-14 23:58 to 10-15 00:00 wrong-bitrate listen on CAN-CH; no read of any module "
                 "inside it.",
                 "The EPS held U1960-83 only (read once, 09-04); never read by CUORE."],
       classification="probable_artefact",
       classification_note="Single sighting, EPS not implicated by its own codes. Not proven: neighbouring "
                           "DASM codes also appear with no known tool event.",
       implications="While logged the DASM's steering-dependent assist could degrade; no message on record.",
       ladder=["Owner: any steering, lane-assist or cruise warning since 10-14.",
               "Re-read the DASM (no clear first) after at least five normal drives, no tool attached.",
               "Read-only EPS DTC read (never done by CUORE).",
               "Only if it returns outside a tool session: EPS supply/ground (supply not below 10 V under load) "
               "and connector check."],
       proof="DASM re-read shows no U1702-87 after several key cycles and drives without tool interference, "
             "and the EPS holds no U1702/U1960. No action until it recurs outside a tool session.",
       literature=[{"text": "Analogue only: Jeep Renegade 2019 EPS flash 08-041-20 (U1702-64).",
                    "url": "https://static.nhtsa.gov/odi/tsbs/2020/MC-10175150-9999.pdf"}]),
    _e("U0422-86", "DTCM",
       meaning="Communication with BCM, signal invalid (seen from the DTCM, transfer case/Q4 module).",
       meaning_source="MES text; " + _FTB,
       readings=["One sighting: SCAN 2026-10-19 00:39. DTCM cleared 10-14 08:59 and not read between; the first-seen "
                 "window contains the wrong-bitrate listen. The bus the DTCM sits on is not established."],
       classification="probable_artefact",
       classification_note="Same window as U1702-87; the CAN-CH link is an inference.",
       implications="None shown.",
       ladder=["Re-read the DTCM after tool-free days; watch only.", "Fold into the BCM mirror-code snapshot."],
       proof="Not seen again over three reads across at least 21 days.", literature=[]),
    _e("U1736-86", "IPC",
       meaning="ETM (Entertainment Telematic Module, the Uconnect radio) signal invalid, seen by the instrument cluster.",
       meaning_source="MES text; ETM = radio head unit in FCA bulletin 08-065-20.",
       readings=["IPC: status 0x0C (pending plus confirmed, not failing) at CUORE 2026-10-13 20:24; in SCAN 10-14 08:59, cleared.",
                 "Absent in IPC and BCM at every scan 06-07 to 10-08 and at all reads after the 10-14 clear. "
                 "One episode between 10-08 09:26 and 10-13 20:24.",
                 "B10AA-4A (PROXI incorrect component) co-timed. No ETM identity ever read."],
       classification="possible_bystander",
       classification_note="Two receivers (IPC and BCM) lost the ETM: points at the ETM or its bus segment, not one "
                           "receiver. Predates the 10-14 bitrate window.",
       implications="Media/phone/navigation text on the cluster, audio chimes (inference; none reported).",
       ladder=["Owner: radio reboot, black screen, lost CarPlay/Bluetooth, any head-unit/amp/USB work or battery work "
               "10-08 to 10-13.",
               "Read the radio software level (Menu, Settings, System, Software Update) and the sales code/MDH label; "
               "compare with 08-065-20 / 08-029-20.",
               "Re-read IPC and BCM (no clear first) after a normal week."],
       proof="Provable only once a cause is found: software below the bulletin level, updated, no reboot symptoms and no "
             "U1736 for 60 days. No action if the radio is current and the codes stay absent.",
       literature=[{"text": "08-065-20 (2018-2019 Stelvio, radio reboots; update levels).", "url": "https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf"},
                   {"text": "08-029-20 (2018 Stelvio built to 2018-01-11, radio reboots/freezes).", "url": "https://static.nhtsa.gov/odi/tsbs/2020/MC-10174204-9999.pdf"}]),
    _e("U1736-87", "IPC",
       meaning="ETM missing message, seen by the instrument cluster.",
       meaning_source="MES text; FTB 87: " + _TAT86,
       readings=["IPC status 0x0C at CUORE 2026-10-13 20:24 (with U1736-86); cleared 10-14 08:59; not seen since "
                 "(4 d 15 h at 10-19). Same single episode as U1736-86."],
       classification="possible_bystander",
       classification_note="Single episode, first seen between 10-08 09:26 and 10-13 20:24.",
       implications="As U1736-86.",
       ladder=["As U1736-86: owner questions, radio software level, re-read without clearing."],
       proof="As U1736-86.", literature=[{"text": "08-065-20 (see U1736-86).", "url": "https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf"}]),
    _e("U1736-87", "BCM",
       meaning="ETM missing message, seen by the BCM.",
       meaning_source="MES text; FTB 87: " + _TAT86,
       readings=["BCM status 0x08 (confirmed, not failing) at CUORE 2026-10-13 20:24; in SCAN 10-14 08:59, cleared. "
                 "Absent at every other BCM read. Stored with IPC U1736-86/-87."],
       classification="possible_bystander",
       classification_note="One episode; the IPC and BCM both lost the ETM.",
       implications="As U1736-86.",
       ladder=["As U1736-86."], proof="As U1736-86.",
       literature=[{"text": "08-065-20 (see U1736-86).", "url": "https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf"}]),
    _e("U1765-86", "BCM",
       meaning="Lost communication with RF Hub, signal invalid (stored in the BCM).",
       meaning_source="MES text; " + _TAT86,
       readings=["Two episodes: 2026-09-15 20:48 and CUORE 10-13 20:24 (0x08) / SCAN 10-14 08:59 (cleared). "
                 "Not back since the 10-14 clear.",
                 "With RFHUB B1040-64 only on 10-13/14; B1040 occurs without it and it without B1040."],
       classification="possible_bystander",
       classification_note="Short-lived, always stored-not-failing when read; clustered around 10-13/14 with B1176, "
                           "U1736 and B10AA-4A. Not downstream of U1713 alone.",
       implications="Keyless entry, passive start, ignition-state messages are the functions at risk; no failure "
                    "logged (ask the owner).",
       ladder=["Owner: no-recognise-key, multiple presses to start, doors not unlocking; spare key and fob battery; "
               "aftermarket LED bulbs/chargers/trackers.",
               "Read-only: re-read BCM and RFHUB at several key-on sessions and one running session, no clear first.",
               "BCM supply and ground, F82 and the stand-alone BCM fuse; BCM/RFHUB connectors."],
       proof="U1765-86 and B1040-64 absent over a span longer than their longest gap (9 d 21 h for B1040), with no "
             "keyless symptom.",
       literature=[{"text": "STAR S2008000113: intermittent keyless start failures; LED bulbs/wireless devices.", "url": "https://static.nhtsa.gov/odi/tsbs/2020/MC-10180203-9999.pdf"},
                   {"text": "GPOP tech tip (MY15-16, U1765-87): stored-only code, no repair needed.", "url": "https://static.nhtsa.gov/odi/tsbs/2016/MC-10130086-9999.pdf"},
                   {"text": "STAR S1808000005 (BCM supply, F82).", "url": _S1808}]),
    _e("B1040-64", "RFHUB",
       meaning="Communication with Body Computer (BCM/NBC), signal/message plausibility.",
       meaning_source="MES text; " + _FTB,
       readings=["First seen 2026-06-07 10:03 (not 09-25). 6 of 18 RFHUB scans: 06-07, 08-27, 09-25 20:27, 09-28, "
                 "10-08, 10-14; CUORE 10-13 20:24 (0x08). Absent after the 10-14 clear through 10-19.",
                 "Always confirmed-not-failing when read."],
       classification="possible_bystander",
       classification_note="Receiver-side; reciprocal of BCM U1765-86 and RFHUB U2054-87 but they do not always "
                           "set together. Not caused by the 10-14 window.",
       implications="As U1765-86.", ladder=["As U1765-86."],
       proof="Absent over a span exceeding 9 d 21 h, no keyless symptom. No action if no symptom and absent after 10-14.",
       literature=[{"text": "STAR S1708000262: connector terminal inspection for intermittent CAN codes.", "url": _S1708}]),
    _e("B1176-97", "BCM",
       meaning="Rear left window riser, component or system operation obstructed or blocked.",
       meaning_source="MES text; FTB 97: " + _FTB,
       readings=["First seen 2026-08-27 11:31 (not 06-07: absent in both 06-07 BCM scans). 9 of 18 BCM scans: 08-27, "
                 "09-02, 09-04, 09-15, 09-25 (x2), 09-28, 09-29, 10-14; CUORE 10-13 20:24 (0x08).",
                 "Absent since the 10-14 clear (4 d 15 h at 10-19); longest observed return gap at most 14 d 9 h. "
                 "No freeze frame; BCM supply 13.7 V at 10-13."],
       classification="real",
       classification_note="Real, intermittent, local; not downstream of U1713 (present with it absent and "
                           "absent with it present).",
       implications="The rear-left window may stop or reverse on one-touch close and may lose one-touch until it "
                    "re-learns (inference; no symptom recorded).",
       ladder=["Owner: does rear-left one-touch work, bounce back, move slowly or make noise; other windows the same?",
               "Hold the switch (no one-touch), listen for binding; look at glass run and seals for grit or ice.",
               "Window initialisation procedure, hands clear (anti-pinch is off during it): start the car, close "
               "doors; hold down until fully open and a few seconds more, hold up until fully closed and a few "
               "seconds more; repeat if needed. Third-party text; check the owner's handbook.",
               "Re-read the BCM at intervals, no clear as a test.",
               "Only if it returns after initialisation: regulator/motor inspection."],
       proof="B1176-97 absent from BCM reads for longer than 14 d 9 h counted from the later of 10-14 and the "
             "initialisation date, window used daily, one-touch confirmed by the owner.",
       literature=[{"text": "Third-party Stelvio window reinitialisation (summary; page returned 403).", "url": "https://www.wheelsjoint.com/alfa-romeo-stelvio-auto-windows-not-working-how-to-reset/"},
                   {"text": "Analogue only (Infiniti ITB16-042): initialise after power interruption.", "url": "https://static.nhtsa.gov/odi/tsbs/2018/MC-10120583-9999.pdf"},
                   {"text": "Recall 18V205 / Transport Canada 2018151: BCM water; windows not named.", "url": _TC18151}]),
    _e("P1DAD-00", "TCM",
       meaning="TCM list entry. Name uncertain: 'Input shaft - output shaft direction correlation' appears in a "
               "bulletin for another transmission, not confirmed for the 8HP.",
       meaning_source="Not confirmed for the ZF 8HP.",
       readings=["CUORE UDS only, status exactly 0x40 (test not completed this cycle) on every read; MES never listed it."],
       classification="readiness_only",
       classification_note="Bit 0x40 only: the monitor has not run this cycle. No failure bit set on any read.",
       implications="None.", ladder=["No action. Watch for any status other than 0x40 (bits 0, 1, 2 or 3)."],
       proof="Nothing to prove; escalate only if a failure bit appears.",
       literature=[{"text": "ISO 14229 status bit 6 (secondary source).", "url": "https://pyudskit.readthedocs.io/en/latest/reference/dtc-status-bits/"}]),
    _e("P1DB7-00", "TCM",
       meaning="Torque converter clutch performance (ZF 8HP, FCA wording; from the repo's 8HP reference).",
       meaning_source="docs/reference/ZF8HP_SERVICE_DATA.md",
       readings=["CUORE UDS only, status 0x40 on every read; MES never listed it."],
       classification="readiness_only",
       classification_note="Bit 0x40 only: readiness flag, not a fault.",
       implications="None.", ladder=["No action. Watch for any status other than 0x40."],
       proof="Nothing to prove; escalate only if a failure bit appears.",
       literature=[{"text": "ISO 14229 status bit 6 (secondary source).", "url": "https://pyudskit.readthedocs.io/en/latest/reference/dtc-status-bits/"}]),
    _e("P1DCE-00", "TCM",
       meaning="No description found.", meaning_source="",
       readings=["CUORE UDS only, listed twice on 10-14 19:02, status 0x40 on every read."],
       classification="readiness_only",
       classification_note="Bit 0x40 only: readiness flag, not a fault.",
       implications="None.", ladder=["No action. Watch for any status other than 0x40."],
       proof="Nothing to prove; escalate only if a failure bit appears.",
       literature=[{"text": "ISO 14229 status bit 6 (secondary source).", "url": "https://pyudskit.readthedocs.io/en/latest/reference/dtc-status-bits/"}]),
]

_BASE_RE = re.compile(r"^([PBCU][0-9A-F]{4})", re.IGNORECASE)


def _base(code: str) -> str:
    m = _BASE_RE.match((code or "").strip())
    return m.group(1).upper() if m else (code or "").strip().upper()


def lookup(code: str, module: Optional[str] = None) -> list[dict[str, Any]]:
    """Findings for a code. A full code (``C104B-92``) matches exactly; a
    base code (``C104B``) matches every FTB variant. ``module`` (case
    insensitive) narrows to that module when given. ``[]`` when nothing is
    recorded -- never a guess."""
    c = (code or "").strip().upper()
    if not c:
        return []
    if "-" in c:
        out = [f for f in FINDINGS if f["code"] == c]
    else:
        out = [f for f in FINDINGS if _base(f["code"]) == _base(c)]
    if module:
        m = module.strip().upper()
        out = [f for f in out if f["module"].upper() == m]
    return [dict(f, classification_label=CLASSES.get(f["classification"], f["classification"]))
            for f in out]


__all__ = ["FINDINGS", "CLASSES", "AS_OF", "lookup"]
