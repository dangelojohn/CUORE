"""Curated repair knowledge: DTC -> TSB cross-reference for the GA/GU platform.

Every entry here is transcribed from ``docs/reference/TSB_CATALOGUE.md``, which
was itself built from the full NHTSA manufacturer-communication set for
Giulia/Stelvio (295 records -> 201 bulletins, all PDFs read where readable).
Nothing in this module is inferred: each bulletin carries its source and its
scope caveats, because a TSB quoted without its applicability line is how the
wrong repair gets sold.

This module was declared in ``mes.__init__.__all__`` from the start and is the
first piece of the planned knowledge base (capability-gap item 5). The
matching is deliberately conservative: a bulletin is offered when one of its
listed DTCs is present, or when a *family* rule fires (several EVAP codes
together, a multi-module U-code cascade) -- and family matches say why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

#: Strip the failure-type byte: "P0456-00" -> "P0456".
_BASE_RE = re.compile(r"^([PBCU][0-9A-F]{4})", re.IGNORECASE)


def base_code(code: str) -> str:
    m = _BASE_RE.match(code.strip().upper())
    return m.group(1) if m else code.strip().upper()


@dataclass(frozen=True)
class Bulletin:
    """One service bulletin, with scope and the action it prescribes."""

    number: str
    date: str
    title: str
    action: str
    dtcs: tuple[str, ...] = ()
    applies: str = "Giulia (GA) / Stelvio (GU)"
    caution: str = ""
    superseded_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "bulletin": self.number,
            "date": self.date,
            "title": self.title,
            "action": self.action,
            "applies": self.applies,
        }
        if self.dtcs:
            d["dtcs"] = list(self.dtcs)
        if self.caution:
            d["caution"] = self.caution
        if self.superseded_by:
            d["superseded_by"] = self.superseded_by
        d["source"] = "docs/reference/TSB_CATALOGUE.md (NHTSA set, 2026-08-27)"
        return d


BULLETINS: tuple[Bulletin, ...] = (
    # --- EVAP ---------------------------------------------------------------
    Bulletin(
        "S2125000002", "2021-06-18",
        "EVAP leak codes -- check the recirculation-line quick-connect first",
        "For P0456/P0455/P0441/P1CEA: inspect the recirculation-line "
        "mid-point quick-connect before any parts replacement, then re-run "
        "the EVAP leak test.",
        dtcs=("P0456", "P0455", "P0441", "P1CEA"),
    ),
    Bulletin(
        "S2125000003", "2021-07-29",
        "P1CEA alone -- ejector tee debris",
        "Borescope the Ejector Tee in the clean-air duct for debris.",
        dtcs=("P1CEA",),
    ),
    Bulletin(
        "9100471", "2025-03-17",
        "Hard-to-fill / canister flooded with fuel",
        "Vapour line disconnected internally at the FDM port floods the "
        "canister with liquid fuel; replace BOTH canister and ESIM. "
        "Supersedes/extends 9100469.",
    ),
    Bulletin(
        "9100469", "2024-12-16",
        "ESIM is a separate part from the canister",
        "If only the ESIM is at fault, replace only the ESIM.",
        superseded_by="9100471 (for the flooded-canister case)",
    ),
    Bulletin(
        "9100468", "2024-12",
        "Canister filter restriction",
        "Check the canister filter for restriction; dusty-condition vehicles "
        "have a customer-paid Mopar Dual EVAP Filter kit (25-009-24).",
    ),
    Bulletin(
        "9100325 Rev 1", "2025-10-02",
        "Purge control valve / purge hose routing",
        "Inspect for kinked or mis-connected purge hoses at the ejector "
        "tees, purge solenoid and intake.",
    ),
    Bulletin(
        "18-048-23", "2023-04-15",
        "EVAP small-leak verification requires wiTECH SLVT",
        "A road test cannot confirm a small-leak repair; the wiTECH SLVT "
        "procedure is the verification. (Mode $06 is the only non-dealer "
        "route to the measured value.) Supersedes 18-089-19.",
        dtcs=("P0456",),
    ),
    Bulletin(
        "18-030-17 REV. B", "latest of the 18-0xx flash family",
        "PCM flash family fixed-DTC list includes the EVAP codes",
        "The recurring PCM software updates list P0440/P0441/P0455/P0456 "
        "among fixed DTCs -- check the PCM calibration level before "
        "condemning hardware.",
        dtcs=("P0440", "P0441", "P0455", "P0456"),
        caution="Flashing needs wiTECH + AutoAuth; recall/campaign work is "
                "free at the dealer.",
    ),
    # --- transmission / AWD -------------------------------------------------
    Bulletin(
        "S2621000003 REV. A", "2026-03-09",
        "ZF 8HP shift-quality and ratio DTCs",
        "Burnt fluid odour and fine metallic content are NORMAL. Valve body "
        "replacement is the first option before transmission replacement. "
        "P1B13/P1B14: check the MPR cable is not stuck. P0733: clutch-D "
        "repair per 21-029-25 REV. A first.",
        dtcs=("P07E4", "P1DB2", "P0716", "P1B14", "P0733", "P1D90",
              "P1DB7", "P1B13"),
        applies="2017-2026 Giulia (GA), 2018-2026 Stelvio (GU)",
    ),
    Bulletin(
        "S1821000001 REV. A", "2021-04-16",
        "AWD shudder / gear-ratio DTCs -- tyre circumference first",
        "Tyre circumference mismatch on AWD must be within 1/8 inch; "
        "mismatch causes shudder, bind and transfer-case damage. Rule this "
        "out before condemning any driveline hardware.",
    ),
    Bulletin(
        "S2008000078 REV. A", "2022-07-22",
        "U0102 on a RWD car is a configuration fault",
        "U0102 'Lost communication with transfer case' active after an ECM "
        "replacement or flash on a RWD vehicle means AWD software was loaded "
        "on a RWD configuration -- not a bus fault.",
        dtcs=("U0102",),
    ),
    # --- electrical / network cascade --------------------------------------
    Bulletin(
        "S2008000032", "2020-04-07",
        "Multi-module warning cascade -- connector XY201 + grounds G003A/B",
        "Multiple warnings and DTCs across modules resolved by securing "
        "inline connector XY201 and cleaning frame grounds G003A/G003B. "
        "No parts required.",
        caution="NHTSA associates it only with 2020 Stelvio; GU circuitry "
                "is shared but verify applicability.",
    ),
    Bulletin(
        "S1808000005", "2020-04-04",
        "No start / multiple modules not responding -- BCM supply side",
        "Inspect all BCM power feeds including the standalone 20A fuse; on "
        "GU/Stelvio inspect fuse F82 in the rear PDC (A901 circuit). A BCM "
        "losing its feed drops off the bus and everything gatewaying "
        "through it throws U-codes.",
        applies="2018-2020 Stelvio",
    ),
    Bulletin(
        "S1708000262 REV. A", "2020-11-17",
        "Intermittent CAN-private / LIN bus codes -- spread terminals",
        "Inspect the involved connector terminals for pushed-out or spread "
        "terminals.",
    ),
    Bulletin(
        "S1408000384 REV. J", "2026-03-04",
        "IBS / intelligent battery sensor diagnostics",
        "For U113E, wiggle the IBS 2-way harness takeout while watching the "
        "code -- if it responds, the harness is the fault. DO NOT blind "
        "charge through the sensor.",
        dtcs=("U113E",),
    ),
    Bulletin(
        "S2018000004", "2020-04-15",
        "U04B1 after the W05 PCM campaign",
        "PCM sets U04B1 'Invalid data from battery monitor' after a W05 "
        "flash; the fix is the BCM restore-configuration routine, not "
        "circuit diagnosis. Check whether W05 was ever performed.",
        dtcs=("U04B1",),
    ),
    Bulletin(
        "S2308000004", "2023-01-19",
        "Cranks, no start",
        "Verify all ECM/PCM B+ feeds and grounds.",
    ),
)

#: Codes that, appearing together, are one EVAP system fault -- not N faults.
EVAP_FAMILY = frozenset({"P0440", "P0441", "P0455", "P0456", "P1CEA"})


def tsb_for(code: str) -> list[Bulletin]:
    """Bulletins whose DTC list contains this code (failure byte ignored)."""
    b = base_code(code)
    return [t for t in BULLETINS if b in t.dtcs]


def match_codes(codes: Iterable[str]) -> dict[str, Any]:
    """Cross-reference a set of DTCs against the bulletin table.

    Returns per-code matches plus family findings: several EVAP codes at
    once, or a spread of U-codes suggesting one supply/bus event rather than
    many module faults.
    """
    bases = {base_code(c) for c in codes if c.strip()}
    per_code: dict[str, list[dict[str, Any]]] = {}
    for b in sorted(bases):
        hits = tsb_for(b)
        if hits:
            per_code[b] = [t.to_dict() for t in hits]

    findings: list[dict[str, Any]] = []
    evap = sorted(bases & EVAP_FAMILY)
    if len(evap) >= 2:
        findings.append({
            "family": "EVAP",
            "codes": evap,
            "reading": (
                "Several EVAP codes together are one system fault, not "
                f"{len(evap)} separate ones. Clinical ordering per "
                "S2125000002 and docs/research/EVAP_STELVIO.md: "
                "recirculation-line quick-connect, purge/vent actuator "
                "tests (KOEO), hose routing per 9100325, canister/ESIM per "
                "9100471, smoke test to localise. Small-leak verification "
                "ultimately needs SLVT (18-048-23) or Mode $06."),
        })
    ucodes = sorted(b for b in bases if b.startswith("U"))
    if len(ucodes) >= 3:
        findings.append({
            "family": "network",
            "codes": ucodes,
            "reading": (
                "Three or more lost-communication codes point at one power "
                "or bus event, not per-module faults. Supply side first "
                "(S1808000005: BCM feeds, F82), then connector/grounds "
                "(S2008000032: XY201, G003A/B), then terminals "
                "(S1708000262)."),
        })
    return {"per_code": per_code, "family_findings": findings,
            "bulletins_considered": len(BULLETINS)}
