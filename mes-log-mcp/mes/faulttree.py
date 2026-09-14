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


TREES: tuple[Tree, ...] = (EVAP_LEAK, P1CEA_FLOW)


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
        if evidence:
            out["vehicle_evidence"] = evidence
    return out
