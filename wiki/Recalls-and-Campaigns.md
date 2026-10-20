# Recalls and Campaigns

This page lists the safety recalls, customer-satisfaction notices and campaigns in CUORE's catalogue that could apply to the reference car, a **2018 Alfa Romeo Stelvio 2.0T Q4**. The source is `cuore/data/tsb_catalogue.json` (last updated 2026-10-15; how it is scored is on [[TSB Layer and Cross-Reference|TSB-Layer-and-Cross-Reference]]).

## The one rule

**Whether any of these applies to this car, and whether it was already done, is settled only by a VIN lookup.** The dealer can answer it; so can the regulators' public VIN pages (the US NHTSA recall page and the Transport Canada recall site), and the catalogue marks nearly every row `vin_check`. The manufacturer's own lookups are VIN-gated, so a public search cannot show "none". CUORE cannot tell and does not guess; **no VIN check for these has been recorded yet**. Most rows are summary-level (`verified: false`: the record was indexed, not read in full), except where stated. A recall is an outside document, never a reading of the car ([[Evidence Model|Evidence-Model]]).

## Highlighted: the four to check first

| Number | What it is | Why it matters here |
|---|---|---|
| **19V551** (2019-07) | Body computer (BCM) software: the fuel gauge may show more fuel than there is, with a run-out risk. Remedy: BCM software update. | The EVAP monitor has fuel-level conditions, the EVAP freeze frames carry fuel level, and this recall puts the BCM somewhere in the fuel-level chain. That the engine computer takes its fuel value from the BCM is **not established**; a constant offset would not show in the readings taken so far. Check by VIN. |
| **18V205** (2018-03) | Water can corrode the BCM or its A-pillar connector; wipers, lights and horn may fail. NHTSA build range 2017-03-20 to 2018-02-14. Remedy: add sealing at the A-pillar and climate box. | The BCM is the centre of the network-code cluster ([[Network and Brake Findings|Network-and-Brake-Findings]]) and the third-ranked cause in the literature. The Transport Canada page (read 2026-10-20) lists the 2018 Stelvio and names warning lights and loss of wipers, exterior lights, horn and turn signals; windows are not named and the build range is not on that page. Whether this car is in scope is not known. Dealer notices U24, U34 and U36 are the customer handling for the 2018 wiper, liftgate and BCM recalls, not separate campaigns. |
| **25V586** (2025-09) | Fuel pump failure on the 2018 to 2019 Stelvio: loss of fuel flow and drive power. Remedy: replace the fuel delivery module; interim letters went out in 2025-10, with the final remedy expected mid 2026. Summary level only, PDFs not opened; a related older bulletin on inspecting the pump module was not located. | A **safety** item in its own right (loss of drive power), unrelated to the EVAP or network codes. Check by VIN whether the car is covered and whether the remedy is available. A twin notice on fuel delivery module heat damage (93C) is kept as a labelled analogue, not as a bulletin for this car. |
| **18V636 and CSN W05** | **Engine computer reflashes.** 18V636 (2018-09): on 2017-2018 Giulia and 2018 Stelvio with the 2.0 litre, a misfire can overheat the catalytic converter; the dealer checks for codes and updates the software. CSN W05 (2020-03): reprogram the engine computer so the turbo oil feed gets enough cooling time; 2017-2019 Giulia and 2018-2019 Stelvio; per VIN at the dealer, no parts; the bulletin PDF was read in full. | Either would have reflashed the engine computer. The computer's software number did not change in any stored read from 2026-09-25 to 10-19, so a reflash in that span is excluded, but **whether one was done earlier is unknown**. The answer settles "is the calibration current", which the EVAP case holds as an unproven suspect ([[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]). The engine flash bulletin that does apply to the 2018 Stelvio lists other codes, not the three EVAP codes; the one that lists them is for the 2017 Giulia only. |

## The rest of the applicable list

| Number | Subject | Applies | Notes |
|---|---|---|---|
| 17V823 (2017-12) | Contaminated brake fluid, 2018 Giulia and Stelvio; inspect and replace parts as needed | VIN check | Does not name any code. Relevant to the brake-code review ([[Code Reviews|Code-Reviews]]) only as a standing item |
| 19V148 (2019-03) | Adaptive cruise cannot be disabled after a wheel-slip event; remedy is a software update of the module the catalogue calls BSM; 2018 to 2019 Stelvio | VIN check | Not tied to a code on this car |
| 18V147 (2018-03) | Wiper motor limited to low speed (software misreads motor overheating) | VIN check | |
| 18V203 (2018-03) | Liftgate wiring or switch water intrusion; corrosion may open the liftgate unexpectedly | VIN check | |
| 24V510 (2024-07) | Seat-belt buckle switch connector; improper connection may prevent front airbag deployment | VIN check | Safety item; the airbag lamp lit once during a tool incident on 2026-10-14 ([[Safety Rules|Safety-Rules]]), which is a separate matter |
| Campaign and emissions lookups | Standalone campaigns, extended warranty, EVAP or head-unit special coverage; emissions recalls | VIN check | None found in public search; **not confirmed absent** |

Not applicable by scope: 18V635 (Quadrifoglio coolant hose), 23V382 (carbon-ceramic brake rotors, unlikely on the 2.0T), a tyre-label notice for 2017 to 2024 Giulia and 2021 to 2024 Stelvio, a brake-booster rod recall for 2019 vehicles only, and a 2026 emissions dealer notification indexed from a flat file (PDF not opened). Analogue rows from other models on the same engine family are labelled as such and are not bulletins for this car.

## How CUORE uses them

- Each row is a checklist line per car (met, not met, or `vin_check`); the cross-reference relates a recall to the car's codes, repairs and hypotheses with a stated reason and a score, and says "VIN check needed" rather than "applies".
- A recall appears in a hypothesis's mechanic steps as a **VIN check first, no tools**: for the EVAP case, 18V636, CSN W05 and 19V551; for the network cluster, 18V205 and 19V551 ([[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]).
- Outside the catalogue, a 2021 recall on a 2019 to 2021 brake part came up while researching the brake code; it is not this model year and is not in the catalogue.
- The answer to each check is recorded on the job with its date, who looked it up, and the source.

Related: [[TSB Layer and Cross-Reference|TSB-Layer-and-Cross-Reference]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].
