"""Fault-isolation trees: written test sequences, cheapest-first, sourced.

The aviation analogue is the FIM -- a mechanic never improvises a
troubleshooting order; the manual gives a decision sequence where every step
is a specific test with a specific expected result, and the parts cannon has
no node. Each step here names the exact action (MES screen, obd2 tool, or
hand test), what a pass looks like, and what to conclude when it fails, with
the bulletin or research source it was transcribed from.

Content is transcribed from ``docs/research/EVAP_STELVIO.md`` (which carries
per-item confidence and the retrieved PDFs' citations) and
``mes/knowledge.py``'s bulletin table. Nothing here is invented; where the
evidence is forum-grade the step says so.

``evaluate`` additionally annotates a tree against one vehicle's own log
corpus -- e.g. a purge valve that has already demonstrably actuated while
the code was stored is marked as such, because re-testing what is already
proven is exactly the time a solo mechanic does not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import fes as fes_mod, knowledge
from .catalog import CATALOG


@dataclass(frozen=True)
class Step:
    """One test in the sequence."""

    id: str
    title: str
    test: str
    tools: str
    expect: str
    if_abnormal: str
    cost: str
    source: str
    caution: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "step": self.id, "title": self.title, "test": self.test,
            "tools": self.tools, "expect": self.expect,
            "if_abnormal": self.if_abnormal, "cost": self.cost,
            "source": self.source,
        }
        if self.caution:
            d["caution"] = self.caution
        return d


@dataclass(frozen=True)
class Tree:
    """One fault-isolation sequence for a code family."""

    key: str
    title: str
    codes: frozenset[str]
    framing: tuple[str, ...]
    steps: tuple[Step, ...]
    verification: tuple[Step, ...]
    do_not: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tree": self.key,
            "title": self.title,
            "applies_to": sorted(self.codes),
            "framing": list(self.framing),
            "steps": [s.to_dict() for s in self.steps],
            "verification": [s.to_dict() for s in self.verification],
            "do_not": list(self.do_not),
        }


EVAP_LEAK = Tree(
    key="evap-leak",
    title="EVAP leak codes (P0440 / P0455 / P0456 / P0441) -- GA/GU 2.0T",
    codes=frozenset({"P0440", "P0441", "P0455", "P0456"}),
    framing=(
        "Several EVAP codes together are ONE system fault, not several.",
        "Large + small leak + valve code together points at the purge valve "
        "stuck open or a vent-side/canister fault, not three repairs.",
        "Field base rate on this platform (forum-grade but convergent): the "
        "canister module is the dominant failure; purge solenoid alone is "
        "low-yield; a standalone vent valve almost never (one tech: one vent "
        "valve in six years).",
        "'Pump clicks off during refuelling' or P2422 alongside is close to "
        "pathognomonic for a blocked/saturated canister on this platform.",
    ),
    steps=(
        Step("E1", "Recirculation-line mid-point quick-connect",
             "Check the recirculation-line mid-point quick-connect for a "
             "loose connection.",
             "Hands. Two minutes.",
             "Connector fully seated and latched.",
             "Reseat it; this is FCA's documented first check for exactly "
             "these codes. Re-verify (below) before doing anything else.",
             "free / 2 min",
             "STAR S2125000002 (2021-06-18) -- explicitly precedes deep "
             "diagnosis for P0456/P0455/P0441/P1CEA"),
        Step("E2", "Canister filter restriction",
             "Inspect the EVAP canister filter for restriction or blockage "
             "(it is on the owner's-manual maintenance schedule).",
             "Hands / visual; canister is behind the driver's-side rear "
             "wheel liner.",
             "Filter passes air freely.",
             "Replace the filter (dusty-duty vehicles: Mopar Dual EVAP "
             "Filter kit, TSB 25-009-24). Cheap cause cleared before any "
             "canister decision.",
             "cheap / scheduled maintenance item",
             "TSB 9100468 (2024-12)"),
        Step("E3", "KOEO actuator tests: purge valve, then vent side",
             "Key on, ENGINE OFF. In MES (IAW 10JA, Actuators tab) run "
             "'Evaporation control valve'; listen/feel for the click and "
             "watch the commanded parameter respond.",
             "MES actuator test; afterwards actuator_history logs the run.",
             "Audible/tactile click, COMPLETED result, parameter follows "
             "command.",
             "No click or FAILED with the engine off = valve or wiring "
             "fault on that branch; diagnose that circuit before any "
             "leak-hunting.",
             "free / 10 min",
             "MES capability confirmed in this corpus (6 COMPLETED purge "
             "actuations on record); interlock note: 'Engine running' "
             "refusal is a precondition, not a fault",
             caution="Engine must be OFF -- the 2026-08-27 attempt failed "
                     "on the running-engine interlock."),
        Step("E4", "Refuelling behaviour interview",
             "Ask/recall: does the pump nozzle click off early during "
             "fills? Any habit of topping off past the first click? Remote "
             "start ever disabled after fuelling?",
             "Conversation. Zero cost.",
             "Normal fills, no top-off habit.",
             "Early click-off points hard at a blocked/saturated canister "
             "(ORVR vapour path blocked). Top-off habit is the documented "
             "saturation mechanism. Weight the canister accordingly.",
             "free / 1 min",
             "EVAP_STELVIO.md section 5 -- mechanism confirmed, forum-grade "
             "corroboration on two sites"),
        Step("E5", "Purge hose routing at the tees, solenoid and intake",
             "Inspect for kinked or mis-connected purge hoses at the "
             "ejector tees, purge solenoid and intake connections.",
             "Hands / visual.",
             "Hoses routed, seated and unkinked.",
             "Correct the routing; re-verify before parts.",
             "free / 10 min",
             "TSB 9100325 Rev 1 (2025-10-02)"),
        Step("E6", "Canister flooded with fuel?",
             "Check whether the vapor canister or recirculation line "
             "contains liquid fuel (hard-to-fill symptom strengthens this).",
             "Visual at the canister; if fuel is found the tank comes down "
             "to inspect the internal vapour line at the FDM port.",
             "No liquid fuel in canister or recirculation line.",
             "Fuel found: internal vapour line disconnected at the FDM "
             "port; reconnect, and replace BOTH the canister and the ESIM "
             "per the bulletin. Note this VIN is in fuel-pump recall "
             "25V586000/93C -- if that FDM work is ever done, verify this "
             "connection on reassembly.",
             "inspection free; remedy is parts",
             "TSB 9100471 (2025-03-17), supersedes 9100469 for this mode"),
        Step("E7", "Smoke test to localise",
             "Low-pressure smoke into the EVAP system; look for the leak "
             "point (filler neck, canister housing, hose unions, ESIM "
             "area).",
             "Smoke machine.",
             "No visible smoke escape at correct (LOW) pressure.",
             "Leak localised: repair that joint/part. Distinguish ESIM "
             "from canister before ordering -- they are separate parts and "
             "replacing the canister for an ESIM fault is a "
             "bulletin-warned error.",
             "shop equipment / 30 min",
             "EVAP_STELVIO.md section 10; ESIM/canister split per TSB "
             "9100469",
             caution="EVAP is a low-pressure system -- over-pressurising "
                     "damages components."),
    ),
    verification=(
        Step("V1", "Do not road-test as proof",
             "Accept that a clean scan after a drive proves nothing: P0456 "
             "sets only across multiple engine-off soak/drive cycles.",
             "--",
             "--",
             "--",
             "free",
             "TSB 18-048-23 (current SLVT bulletin; supersedes 18-089-19): "
             "'A road test will not confirm the repair.'"),
        Step("V2", "Measured verification",
             "Run the wiTECH SLVT (subcontract if needed), or once the "
             "Mode $06 tool is built read the ECM's measured leak result "
             "against its own threshold. Meanwhile: obd2.read_readiness "
             "until the EVAP monitor reports RUN, and "
             "obd2.read_permanent_dtcs -- disappearance of the permanent "
             "code is the cheapest proof the monitor ran and passed.",
             "wiTECH SLVT / obd2 server (car connected)",
             "Monitor complete + no permanent DTC + (ideally) measured "
             "pass.",
             "Code returns: the repair was wrong or incomplete -- back to "
             "the tree with the new freeze frame.",
             "readiness/permanent free; SLVT is dealer-tool",
             "TSB 18-048-23; MES_CAPABILITY_GAPS.md items 1-3",
             caution="EVAP monitor needs fuel level roughly 15-85% and "
                     "cold-start windows to run at all."),
    ),
    do_not=(
        "Do not replace the purge solenoid alone -- low yield platform-wide.",
        "Do not condemn the gas cap by default -- low hit rate here (one "
        "owner: ~$144 dealer cap, no change).",
        "Do not sell a standalone vent valve on P2422 without proof -- the "
        "vent function is integrated in the canister module on NA cars.",
        "Do not read a clean post-clear scan as proof of repair.",
        "Do not replace the canister for an ESIM fault or vice versa "
        "(TSB 9100469 -- separate parts).",
    ),
)


P1CEA_FLOW = Tree(
    key="p1cea-boost-purge",
    title="P1CEA -- insufficient vapour flow under boost (NOT a leak code)",
    codes=frozenset({"P1CEA"}),
    framing=(
        "P1CEA is a flow/performance rationality monitor on the boost purge "
        "path, not a leak monitor. It runs only after the small-leak test "
        "has passed -- fix leak codes first if both are present.",
        "GME-T4 purges via two paths off one solenoid: manifold vacuum "
        "off-boost; on-boost via a CAC-duct tap through a directional "
        "ejector tee into the air cleaner.",
    ),
    steps=(
        Step("F1", "PCM software level",
             "Check the PCM calibration level against the current bulletin "
             "before any hardware diagnosis.",
             "MES Info tab (SW P-number) vs bulletin.",
             "Calibration current.",
             "P1CEA is attributed to PCM software on this platform -- "
             "update path is wiTECH (dealer; campaign work is free).",
             "free to check",
             "TSB 18-023-23 REV. B (on-platform, authoritative)"),
        Step("F2", "EVAP quick-connects at the air cleaner cover",
             "Push-pull-push both EVAP quick connects at the air cleaner "
             "cover to confirm full engagement.",
             "Hands. LOP on the donor bulletin is 0.2 hr.",
             "Both connectors locked.",
             "Reseat; re-evaluate.",
             "free / 10 min",
             "Technique from TSB 25-002-23 (same engine family -- 'EVAP "
             "vacuum lines not fully secured')"),
        Step("F3", "Ejector tee orientation + directional blow test",
             "Confirm the ejector tee's orientation, then blow through "
             "each side of the T: one side must be MUCH harder to blow "
             "through than the other.",
             "Hands / mouth or low-pressure air.",
             "Strong asymmetry; tee oriented per routing.",
             "Symmetrical flow = failed/missing check valve; reversed "
             "install sets exactly this code (FCA precedent on the 1.4L). "
             "Any aftermarket intake must correctly reinstate this tee.",
             "free / 10 min",
             "EVAP_STELVIO.md section 6 -- FCA precedent + documented "
             "Giulia case"),
        Step("F4", "CAC-duct and air-cleaner port flash/blockage",
             "Inspect the purge ports on the CAC duct and air cleaner for "
             "moulding flash or blockage.",
             "Visual / pick.",
             "Ports clear.",
             "Clear the flash -- an explicitly listed factory defect mode.",
             "free / 10 min",
             "FCA published possible-cause list for P1CEA"),
        Step("F5", "FTP sensor circuits, then purge solenoid",
             "Check fuel-tank-pressure sensor 5V supply/signal/return "
             "resistance; then purge solenoid vacuum supply and the "
             "solenoid itself.",
             "Meter; MES live parameters for FTP plausibility.",
             "Circuits in spec; FTP reads plausibly.",
             "Repair the implicated circuit/part.",
             "meter work / 30 min",
             "FCA published possible-cause list (ordered last for a "
             "reason -- the cheap physical causes above dominate)"),
    ),
    verification=(
        Step("V1", "Confirm under the running condition",
             "P1CEA sets under boost -- verify with a recorded road test: "
             "MES CSV recording (purge duty, boost, FTP) with Monitor DTCs "
             "on, then recording_events for any recurrence.",
             "MES Graph/CSV + mes-log recording tools",
             "No recurrence across boost events; flow parameters plausible.",
             "Recurs: back to F3/F4 with the recording's snapshot at the "
             "event time.",
             "free",
             "CSV_LOG_FORMAT.md workflow"),
    ),
    do_not=(
        "Do not chase P1CEA as a leak -- the leak monitor already passed.",
        "Do not replace the purge solenoid first; it is last on FCA's own "
        "cause list.",
    ),
)


NETWORK_CASCADE = Tree(
    key="network-cascade",
    title="BCM/RFHUB/DTCM comms cascade (U1711/U1712/U1713/U1716/U2054/"
          "U0100/B1040) -- one network event, not seven faults",
    # U1765 (BCM: lost communication with RF Hub) is named in no document here,
    # but this car logged U1765-86 in SCAN_2609152048 alongside U1711/12/13 --
    # the same lost-communication family, so it takes the same sequence.
    codes=frozenset({"U1711", "U1712", "U1713", "U1716", "U1765", "U2054", "U0100",
                      "B1040"}),
    framing=(
        "Every code in this family is a message-integrity failure type -- "
        "U-codes by definition, B1040's FTB `64` is 'plausibility' -- not a "
        "component-internal fault (GIORGIO_PLATFORM.md section 1's FTB "
        "table; mes/analysis.py COMMUNICATION_FTBS).",
        "CONNECTIVITY_AND_SGW.md section 1, verbatim: the pervasive U/C "
        "lost-communication DTCs -- BCM U1711/U1712/U1713/U1716, DTCM "
        "U0100, DASM C1403/C1408/C1431/C141C -- 'name exactly the modules "
        "on the unreachable buses'; recommendation there is a key-on-"
        "engine-RUNNING rescan before chasing any of them as faults.",
        "GIORGIO_MODULE_MAP.md Table B: whole-vehicle serial UDS sweeps "
        "and cable re-plugs manufacture -87/-2F bystander codes -- this "
        "car's own SCAN_2609041953 shows exactly that (DTCM U0100-87, BCM "
        "U171x-2F, EPS U1960-83). Pull DTC EX before clearing.",
        "This repo's own network family rule (mes/knowledge.py match_codes, "
        "CORPUS_BASELINE.md section 7.2's proposed reporting rule, mes/"
        "analysis.py detect_network_event): three or more modules holding "
        "only U/C communication codes with no component-level code of "
        "their own collapse into one network-event finding, not N module "
        "faults.",
        "Ranked, sourced causes on this platform, in the order mes/"
        "knowledge.py already uses: BCM supply/fuse F82 (TSB S1808000005), "
        "inline connector XY201 + frame grounds G003A/B (TSB S2008000032), "
        "then spread/backed-out terminals (TSB S1708000262 REV. A).",
    ),
    steps=(
        Step("N1", "Engine-running rescan before chasing any of this as real",
             "Rescan with the engine RUNNING (not just key-on-engine-off) "
             "and re-read the DTCs fresh.",
             "MES full scan, engine running.",
             "Codes do not reappear as freshly active with the engine "
             "running.",
             "Codes persist with the engine running: treat as a real, "
             "recurring event and continue down this tree.",
             "free / 5 min",
             "CONNECTIVITY_AND_SGW.md section 1 -- 'Recommendation: do not "
             "chase these as faults without a key-on-engine-RUNNING "
             "rescan.'"),
        Step("N2", "Pull DTC EX on every code BEFORE clearing anything",
             "In MES, read extended DTC data (DTC EX) on every code in "
             "this family: odometer, occurrence count, aging counter.",
             "MES DTC EX screen.",
             "Codes do not all share one identical odometer value and a "
             "single occurrence count.",
             "Every code shares one odometer value and one occurrence: "
             "your own scan (or a cable re-plug) produced them. Clear and "
             "move on -- there is nothing to repair. Do this BEFORE "
             "clearing; clearing destroys this evidence.",
             "free / 5 min",
             "GIORGIO_PLATFORM.md section 1 item #3, 'the decisive test, "
             "and it is cheap'; GIORGIO_MODULE_MAP.md Table B ('Pull DTC "
             "EX before clearing')."),
        Step("N3", "Read ABS directly on CAN-CH (grey A6) -- does the "
                   "brake side agree?",
             "Fit the grey A6 adapter cable and scan the Continental ABS "
             "MK C1 module directly on CAN-CH for its own stored codes.",
             "MES + grey A6 cable, CAN-CH bus.",
             "ABS reports no fault of its own.",
             "ABS itself holds a stored code: the brake side has a "
             "genuine finding, and BCM's U1711/U1712 'brake system (NFR) "
             "erratic' was reporting on a module that does have a real "
             "problem. Diagnose the ABS-reported code itself, outside "
             "this tree.",
             "needs grey A6 cable / 10 min",
             "GIORGIO_MODULE_MAP.md Table A (ABS Continental MK C1, "
             "CAN-CH, grey A6, CONFIRMED) and Table B (CAN-CH bus "
             "profile).",
             caution="Listen/scan only -- GIORGIO_MODULE_MAP.md Table B: "
                     "never transmit on CAN-CH without explicit human "
                     "confirmation; brakes, airbag squibs and steering "
                     "assist live here."),
        Step("N4", "Clear once, then rescan without re-plugging anything",
             "After N2's DTC EX read, clear the codes, then rescan "
             "without disconnecting or reseating the OBD connector, the "
             "grey/blue adapter, or any bus connector in between.",
             "MES clear + rescan.",
             "Codes stay cleared.",
             "Codes return with nothing re-plugged and no repair "
             "performed: this is a real, recurring network/power event, "
             "not a scan or cable artifact. Proceed to the ranked causes "
             "below.",
             "free / 10 min",
             "CORPUS_BASELINE.md section 7, 2026-08-27 timeline: this "
             "exact sequence on this car went 11:36 SCAN (1 DTC, "
             "U0100-87) -> cleared -> 11:41 SCAN clean across all 8 "
             "modules, with no re-plug in between."),
        Step("N5", "BCM power feed -- fuse F82 in the rear PDC, BCM A901 "
                   "circuit",
             "Inspect all BCM power feed circuits, including the "
             "standalone 20A fuse and, on this GU/Stelvio, fuse F82 in "
             "the rear PDC feeding the BCM A901 circuit.",
             "Fuse box, meter.",
             "F82 intact; A901 circuit and B+ A0 feed both in spec.",
             "Repair the feed/fuse. A BCM that loses its supply drops off "
             "the bus and every module gatewaying through it throws "
             "U-codes -- matching this car's exact module list.",
             "cheap / 20 min",
             "TSB S1808000005 (2020-04-04), 'No Start, Multiple Modules "
             "Are Not Responding', 2018-2020 Stelvio -- mes/knowledge.py "
             "BULLETINS."),
        Step("N6", "Inline connector XY201 + frame grounds G003A/G003B",
             "Inspect inline connector XY201 for security; clean and "
             "secure frame grounds G003A and G003B.",
             "Hands / visual, ground cleaning.",
             "Connector fully seated; grounds clean and tight.",
             "Reseat/clean and re-verify (N4) before anything further -- "
             "this is FCA's own published fix for exactly this cascade "
             "shape, no parts required.",
             "free / 20 min",
             "TSB S2008000032 (2020-04-07), 'EVIC Displays Multiple "
             "Warning Messages' -- mes/knowledge.py BULLETINS.",
             caution="NHTSA associates this bulletin only with 2020 "
                     "Stelvio; GU circuitry is shared but verify "
                     "applicability."),
        Step("N7", "Spread or backed-out connector terminals",
             "Inspect the involved connector terminals for pushed-out or "
             "spread terminals.",
             "Hands / visual / terminal pick.",
             "Terminals fully seated, no spread pins.",
             "Reseat/repair the terminal and re-verify (N4).",
             "free / 20 min",
             "TSB S1708000262 REV. A (2020-11-17), 'Check Engine Lamp Is "
             "On, Intermittent Module CAN Private Or LIN BUS Codes' -- "
             "mes/knowledge.py BULLETINS."),
        Step("N8", "BCM water-intrusion recall check (18V205000/U36, "
                   "18V203000/U34)",
             "Pull the passenger kick panel; check the BCM connectors "
             "for staining, a silt line, or green/white corrosion. Check "
             "the cowl drains. Verify whether recalls 18V205000 (U36, "
             "BCM water intrusion) and 18V203000 (U34, liftgate connector "
             "water intrusion) were performed on this VIN.",
             "Hands / visual, VIN recall lookup.",
             "No water staining/corrosion; recall(s) already performed, "
             "sealing kit intact.",
             "Water intrusion found, or the recall was never performed: "
             "corroded BCM connector pins produce faults in both "
             "directions because the BCM gateways CAN-C to CAN-IHS. "
             "Perform/redo the sealing kit -- recurrence after the kit is "
             "documented, so re-verify its integrity even if 'already "
             "done'.",
             "free to check; recall repair is free at the dealer",
             "GIORGIO_PLATFORM.md section 1 item #2 -- NHTSA 18V205000/"
             "U36 and 18V203000/U34, 12,595 vehicles, essentially the "
             "entire MY2018 US Stelvio population."),
        Step("N9", "Ground strap voltage-drop test (owner-reported "
                   "pattern, NO FCA bulletin)",
             "Voltage-drop test the engine/transmission-to-body ground "
             "strap and both front knuckle straps under load (cranking, "
             "cooling-fan step, ABS pump, EPS assist).",
             "DVOM / voltage-drop test under load.",
             "Under 0.1 V across each path; braid intact, no corrosion at "
             "the 90-degree bend.",
             "High-resistance strap: replace it. A shifted powertrain "
             "ground reference during a high-current event can push CAN "
             "transceivers outside their common-mode range for "
             "milliseconds, producing exactly this simultaneous erratic/"
             "invalid/missing-message pattern, then recovering cleanly.",
             "cheap part (~$200) / 30 min test",
             "GIORGIO_PLATFORM.md section 1 item #1 -- 13 NHTSA owner "
             "complaints, 2018-2019 Stelvio, dealer-diagnosed at "
             "54k-102k miles.",
             caution="Owner-reported pattern only. A full-text sweep of "
                     "all 287 readable FCA bulletins found NOTHING "
                     "describing a ground strap as a failing part -- no "
                     "FCA publication corroborates this. Rank below "
                     "N5-N8, not above them."),
        Step("N10", "Battery / IBS check",
             "Battery load test; check the IBS harness connection by "
             "wiggling the 2-way takeout while watching for a code "
             "response; check for parasitic draw.",
             "Battery tester, meter, MES DTC EX.",
             "Battery and IBS test good; no parasitic draw; IBS harness "
             "unaffected by the wiggle.",
             "IBS wiggle test reproduces a code: the harness takeout is "
             "the fault, per the documented U113E procedure. Weak "
             "battery/parasitic draw: repair accordingly.",
             "shop equipment / 20 min",
             "TSB S1408000384 REV. J (2026-03-04), wiggle test for "
             "U113E 'lost communication with intelligent battery'; "
             "GIORGIO_PLATFORM.md section 1 item #4 (only 1/371 NHTSA "
             "complaints names the IBS -- weakly evidenced generally, "
             "ranked last).",
             caution="DO NOT BLIND CHARGE through the sensor (TSB "
                     "S1408000384)."),
    ),
    verification=(
        Step("V1", "Confirm across more than one session, not one clean "
                   "scan",
             "Rescan on at least one additional, separate ignition "
             "cycle/session after whatever was found and fixed above, "
             "rather than trusting one immediate clean re-read.",
             "MES rescan, separate session.",
             "Stays clear across sessions.",
             "Recurs: the identified cause did not address the root "
             "event -- go back down the ranked list (N5-N10) with the "
             "new DTC EX data.",
             "free",
             "CORPUS_BASELINE.md section 7 -- this car's own history "
             "shows U1711/U1712/U1713 recurring across two widely "
             "separated sessions (2026-06-07 and 2026-08-27) while "
             "U0100-87 cleared once (11:36 -> 11:41 on 2026-08-27) and "
             "has not returned since; one clean scan does not "
             "distinguish these."),
    ),
    do_not=(
        "Do not replace any module on the strength of a communication "
        "cascade alone (GIORGIO_PLATFORM.md section 6 'professional "
        "discipline' #1; mes/analysis.py NetworkEvent caution).",
        "Do not clear codes before pulling DTC EX -- clearing destroys "
        "the only evidence that this was a scan artifact (GIORGIO_"
        "PLATFORM.md section 1 item #3).",
        "Do not read a missing-message code as naming the faulty module "
        "-- it names the module that went quiet, not the one that "
        "failed; U0100 on the DTCM does not implicate the transfer case "
        "(GIORGIO_PLATFORM.md section 3).",
        "Do not sell the ground-strap repair as a documented FCA fix -- "
        "no bulletin describes it; it is owner-reported only "
        "(GIORGIO_PLATFORM.md section 1 item #1).",
    ),
)


DASM_HALF_LINK = Tree(
    key="dasm-half-private-can",
    title="C141C / C141B -- DASM<->HALF private CAN (front radar/camera "
          "link)",
    codes=frozenset({"C141C", "C141B"}),
    framing=(
        "DASM (Bosch radar, front bumper) and HALF (Bosch MFK2 forward "
        "camera, windshield) share a direct point-to-point private CAN "
        "that does not transit the vehicle network (GIORGIO_PLATFORM.md "
        "section 2).",
        "C141C-86 (FTB `86`, signal/message invalid) means the link "
        "delivered malformed data; a broken/dead link would instead give "
        "FTB `87` (missing message) and would not self-clear. This car's "
        "C141C-86 has appeared and self-cleared twice (GIORGIO_PLATFORM."
        "md section 2; CORPUS_BASELINE.md C-codes table).",
        "Because it is a private point-to-point link, C141C names the "
        "link, not an end -- HALF-side or DASM-side component codes (if "
        "any) decide which end is actually at fault, not the link code "
        "itself (GIORGIO_PLATFORM.md section 2).",
        "C141B does not appear in this repo's corpus, TSB catalogue or "
        "research docs. Only the generic FTB `97` meaning ('component or "
        "system operation obstructed or blocked', mes/dtc.py) and the "
        "DASM<->HALF private-bus architecture above are confirmed; treat "
        "any specific camera-obstruction causation for C141B as "
        "inference, not a sourced finding.",
    ),
    steps=(
        Step("D1", "Read HALF directly on CAN-CH (grey A6)",
             "Fit the grey A6 adapter cable and scan the HALF forward "
             "camera module directly on CAN-CH for its own stored "
             "codes.",
             "MES + grey A6 cable, CAN-CH bus.",
             "HALF reports no fault of its own.",
             "HALF holds its own stored code: the camera side has a "
             "genuine finding, and that decides the private-link fault "
             "-- C141C alone does not say which end is at fault.",
             "needs grey A6 cable / 10 min",
             "GIORGIO_MODULE_MAP.md Table A (HALF, Bosch MFK2, CAN-CH, "
             "grey A6, CONFIRMED -- MES lists 'ELMA6') and GIORGIO_"
             "PLATFORM.md section 2.",
             caution="Listen/scan only on CAN-CH -- GIORGIO_MODULE_MAP.md "
                     "Table B: never transmit without explicit human "
                     "confirmation."),
        Step("D2", "Windscreen / camera field-of-view obstruction check",
             "Check the windscreen area ahead of the HALF camera for "
             "dirt, film, a chip/crack in the camera's field of view, or "
             "a disturbed/incorrectly seated camera cover.",
             "Visual.",
             "Clear field of view; camera cover properly seated.",
             "Clean/clear and retest. If the cover, windscreen or front "
             "bumper was disturbed (removed/replaced), the camera needs "
             "recalibration -- MES has no ADJ routine for HALF, so this "
             "needs wiTECH plus FCA static targets or a dedicated ADAS "
             "platform (Autel IA900/MA600, Hunter, Bosch, Texa); there "
             "is no cheap path through this toolchain.",
             "free / 5 min inspection; recalibration is a shop job",
             "General forward-camera diagnostic practice -- NOT sourced "
             "to any Stelvio/Giulia-specific bulletin in this repo. The "
             "recalibration-path claim IS sourced: MES_CAPABILITY_GAPS."
             "md section 9 ('ADAS calibration -- the cleanest negative "
             "here').",
             caution="The obstruction check itself is general practice, "
                     "not a documented bulletin for this platform -- "
                     "flagged per house rule rather than omitted, since "
                     "it is a legitimate free check."),
    ),
    verification=(
        Step("V1", "Recheck across a session, not one immediate clean "
                   "read",
             "Rescan on a subsequent session/key cycle rather than "
             "trusting one immediate clean re-read; this car's C141C-86 "
             "has already self-cleared twice without intervention.",
             "MES rescan.",
             "Stays clear across at least one additional real session.",
             "Recurs: treat as active and escalate to whichever end "
             "(D1's finding) actually holds a component code.",
             "free",
             "CORPUS_BASELINE.md C-codes table (C141C-86, 2 occurrences, "
             "2026-06-07 and 2026-08-27) and GIORGIO_PLATFORM.md "
             "section 2."),
    ),
    do_not=(
        "Do not condemn DASM or HALF from the link code alone -- C141C "
        "only says the link carried malformed data, not which end is "
        "faulty (GIORGIO_PLATFORM.md section 2).",
        "Do not attempt an ADAS calibration/adjustment through MES -- "
        "HALF has no ADJ routine in MES; recalibration after any "
        "disturbance needs wiTECH + static targets or a dedicated ADAS "
        "platform (MES_CAPABILITY_GAPS.md section 9).",
        "Do not treat C141B's causation as documented -- no local "
        "source names this code; only the generic FTB-97 meaning is "
        "confirmed (mes/dtc.py).",
    ),
)


TREES: tuple[Tree, ...] = (EVAP_LEAK, P1CEA_FLOW, NETWORK_CASCADE,
                            DASM_HALF_LINK)


def trees_for(codes) -> list[Tree]:
    """Every tree that any of the given codes routes to."""
    bases = {knowledge.base_code(c) for c in codes if str(c).strip()}
    return [t for t in TREES if bases & t.codes]


def evaluate(codes, vin: str = "") -> dict[str, Any]:
    """Select applicable trees and annotate them with this car's evidence.

    The annotation exists because a written sequence is generic but the
    corpus is not: a step this car's logs have already answered is marked,
    with the evidence, so it can be skipped or re-weighted instead of
    re-run.
    """
    matched = trees_for(codes)
    if not matched:
        return {
            "error": "no fault tree covers these codes",
            "codes": sorted({knowledge.base_code(c) for c in codes}),
            "available": [{"tree": t.key, "title": t.title,
                           "applies_to": sorted(t.codes)} for t in TREES],
        }

    out: dict[str, Any] = {
        "codes": sorted({knowledge.base_code(c) for c in codes}),
        "trees": [t.to_dict() for t in matched],
    }
    if len(matched) > 1:
        out["ordering_note"] = (
            "Leak codes are fixed and verified before P1CEA -- the flow "
            "monitor only runs after the small-leak test passes.")

    if vin.strip():
        evidence: list[dict[str, Any]] = []
        entries = CATALOG.select(kind="fes", vin=vin)
        purge_runs = 0
        for entry in entries:
            if entry.parse_error:
                continue
            try:
                log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
            except Exception:
                continue
            for a in log.actuators:
                if "evaporation" in a.operation.lower():
                    if a.to_dict().get("outcome") == "COMPLETED":
                        purge_runs += 1
        if purge_runs:
            evidence.append({
                "step": "E3",
                "finding": (
                    f"The purge valve has already COMPLETED {purge_runs} "
                    "actuator test(s) in this car's own logs -- including "
                    "while P0456 was stored. The valve actuates; weight "
                    "diagnosis toward the vent/canister side."),
                "source": "actuator_history for this VIN",
            })
        history = {}
        try:
            from . import analysis
            history = analysis.dtc_history(CATALOG.select(vin=vin))
        except Exception:
            pass
        for code, rec in history.items():
            if knowledge.base_code(code) in {"P2422"}:
                evidence.append({
                    "step": "E4",
                    "finding": "P2422 present in history -- with early "
                               "nozzle click-off this is close to "
                               "pathognomonic for a blocked canister.",
                    "source": f"dtc_history {code}",
                })

        matched_keys = {t.key for t in matched}
        if "network-cascade" in matched_keys:
            for full in ("U1711-2F", "U1712-2F", "U1713-2F", "U1716-2F",
                         "B1040-64", "U2054-87", "U0100-87"):
                rec = history.get(full)
                if not rec:
                    continue
                if rec.returned_after_clear:
                    finding = (
                        f"{full} has returned after being cleared within "
                        f"a single session in this car's own logs (first "
                        f"seen {rec.first_seen}, last seen {rec.last_seen}, "
                        f"{rec.session_count} session(s)) -- treat as "
                        "reproducing, not a one-off artifact.")
                elif rec.session_count >= 2:
                    finding = (
                        f"{full} recurs across {rec.session_count} "
                        f"separate sessions in this car's own logs "
                        f"({rec.first_seen} to {rec.last_seen}) -- weighs "
                        "against a single-scan artifact for this code "
                        "specifically.")
                else:
                    finding = (
                        f"{full} appears once in this car's own logs "
                        f"({rec.first_seen}) and has not recurred since -- "
                        "consistent with a scan/session artifact for this "
                        "code.")
                evidence.append({
                    "step": "N1",
                    "finding": finding,
                    "source": f"dtc_history for this VIN ({full})",
                })
        if "dasm-half-private-can" in matched_keys:
            rec = history.get("C141C-86")
            if rec:
                evidence.append({
                    "step": "D1",
                    "finding": (
                        f"C141C-86 has appeared and self-cleared "
                        f"{rec.session_count} time(s) in this car's own "
                        f"logs ({rec.first_seen} to {rec.last_seen})."),
                    "source": "dtc_history for this VIN (C141C-86)",
                })

        if evidence:
            out["vehicle_evidence"] = evidence
    return out
