# Dealer visit draft: 2018 Alfa Romeo Stelvio 2.0T Q4, VIN ZASFAKPN5J7B88115

Appointment: Wed 2026-10-28, Alfa dealer. Draft prepared 2026-10-22 from read-only repo data and web research. Nothing was written to the car, adapter or any server.

Label key (every item carries one):
- **[CUORE]** from the repo data under C:\Users\User\mcp-servers (path given).
- **[OFFICIAL]** manufacturer, regulator or FCA/wiTECH document.
- **[FORUM/3RD]** forum, parts vendor or other third-party page. Not authoritative.
- **[INFERENCE]** my reasoning. May be wrong.

Car facts used [CUORE: docs/vehicles/ZASFAKPN5J7B88115/CASE.md; docs/research/CEL_2026-10-19_DIAGNOSIS.md]:
- ECM Magneti Marelli IAW 10JA, HW MM10JAHW232, SW 52170619 / supplier P235QB39 ver 0000, unchanged in every 2026 read. BCM Marelli 949, SW 04441660441 ver 1454.
- About 142,290 km (88,415 mi) at 2026-09-26 (Pending Items sheet). Later reads put the odometer higher; confirm at drop-off.
- EVAP codes P0440 / P0455 / P0456, ECM cleared 11 times in 53 days (08-27 to 10-19). Each clear was followed by the same codes in 0.4 to 11 days. Last clear 2026-10-19 00:39 (MES). Since then a new ESIM and gasket have been fitted 2026-10-22 (owner-attested, recorded in CUORE). Monitor proof run pending.
- BCM U1713-2F active (status 0x0F) on 10-13 and 10-19. U1711/U1712-2F always appeared together (6 of 6 scans), last 09-25. ABS U1700-87 "Body computer" logged 2026-09-04 with battery 10.6 V (startups 14280).

---

## A. Must-do

**A1. Safety Recall 93C (NHTSA 25V586): replace the fuel delivery module (FDM).**
- What: 2018-2019 Stelvio (production 2017-04-12 to 2019-06-26) may have an FDM with heat-susceptible internals, loss of flow, loss of motive power. No warning before failure; a MIL may show. Remedy: replace FDM with improved design and tolerances plus an updated pump electronic module (PEM). [OFFICIAL] https://static.nhtsa.gov/odi/rcl/2025/RCLRPT-25V586-6450.pdf
- Recalled FDM part numbers listed in the Part 573 report: 68348890AA, 68348995AA, 68408467AA, 68408468AA, 68356890AA, 68357058AA, 68411153AA, 68411154AA. [OFFICIAL] same URL. The report does not say which number is the remedy part.
- Ask the dealer to write down the part number of the module removed and the one installed. [INFERENCE] If the installed number is one of the eight above, it may be the old design; ask them to confirm it is the remedy part.
- Remedy availability: as of the sources found, the final remedy was "anticipated July 2026" and an interim notice existed; I found no source confirming launch. [CUORE: cuore/data/tsb_catalogue.json id recall-25v586] [FORUM/3RD] https://moparinsiders.com/recall-53849-alfa-romeo-models-for-potential-fuel-pump-failure/ . Confirm by phone before the 28th that the part is in stock; otherwise the visit may be only an interim measure.
- Open/closed status for this VIN is unverified (catalogue `applies: vin_check`). The dealer must run the VIN. [CUORE: wiki/Recalls-and-Campaigns.md]
- Transport Canada number appears in the CUORE recall request sheet as "TC 2025463". Unverified in the catalogue; a Canadian listing exists at https://mobile.guideautoweb.com/en/recalls/2025463 [FORUM/3RD].

**A2. Ask for a printed VIN recall/campaign status for every line on the existing request sheet** [CUORE: docs/vehicles/ZASFAKPN5J7B88115/pdf/Stelvio_Recall_Request.pdf, made 2026-10-20]. None has a recorded VIN answer yet. All catalogue rows below are `vin_check` and summary-level (`verified: false`) unless stated.

| Recall / campaign | Subject | Why it matters for this car | Source |
|---|---|---|---|
| 18V636 | 2.0L misfire may overheat catalytic converter; ECM software update | Would have reflashed the ECM; settles whether calibration is current | [CUORE: catalogue recall-18v636] https://www.nhtsa.gov/recalls?nhtsaId=18V636 |
| CSN W05 (2020-03) | Reprogram PCM for turbo oil-feed cooling time; PROXI alignment and Phonic Wheel Replacement; 2018 Stelvio PCM only | Same. PDF read in full | [CUORE: bulletins/CSN_W05_2020-03.pdf] https://static.nhtsa.gov/odi/tsbs/2020/MC-10175524-9999.pdf |
| 19V551 | BCM software: fuel gauge may read high | BCM sits somewhere in the fuel-level chain; EVAP monitor has fuel-level conditions. That the ECM takes fuel level from the BCM is NOT established | [CUORE: wiki/Recalls-and-Campaigns.md] https://static.nhtsa.gov/odi/rcl/2019/RCRIT-19V551-7839.pdf |
| 18V205 (TC 2018151) | BCM / A-pillar connector water intrusion; add sealing. NHTSA build range 2017-03-20 to 2018-02-14 | BCM is the centre of the network-code cluster | [CUORE: catalogue recall-18v205] https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018151 |
| 17V823 | Contaminated brake fluid, inspect/replace | Brake code review (C104B-92 on 09-04); also new pads | [CUORE: catalogue recall-17v823] |
| 19V148 | Adaptive cruise cannot be disabled after wheel slip; software update | Standing item | [CUORE] |
| 24V510 | Seat-belt buckle switch connector (front airbag deployment) | Safety item; airbag lamp lit once during a tool incident 2026-10-14 (separate matter) | [CUORE: wiki/Recalls-and-Campaigns.md] |
| 18V147, 18V203 | Wiper motor low-speed; liftgate wiring water intrusion | Standing items | [CUORE] |
| Any CSN / extended warranty / emissions recall | Not confirmed absent | Ask for a complete VIN print | [CUORE: catalogue campaign-lookup, emissions-lookup] |

**A3. If the dealer reflashes anything, they must give before/after software numbers** (see B1). [CUORE: Stelvio_Recall_Request.pdf, "print the current ECM calibration part number before and after any reflash"]

**A4. After the FDM job, verify the internal vapour line at the FDM port.** TSB 9100471 says a vapour line disconnected inside the tank at the FDM port floods the EVAP canister with liquid fuel; the check is to inspect the internal vapour line at the FDM port. [CUORE: catalogue tsb-9100471, verified: true; docs/research/CEL_2026-10-19_DIAGNOSIS.md bulletins table] https://static.nhtsa.gov/odi/tsbs/ (catalogue row has no direct link; NHTSA id 11015810). Reason: the FDM job opens exactly that connection, and a mis-seated line would create a new EVAP fault on top of the one under proof. [INFERENCE]

---

## B. wiTECH-only requests (each with a "why for this car")

Background on what wiTECH 2.0 can do that MES/AlfaOBD cannot:
- Security Gateway: on 2018+ FCA vehicles, if the SGW does not unlock, the tool can only view DTCs and data. It cannot program an ECU, clear DTCs or run routines. wiTECH unlocks through DealerCONNECT authorisation; aftermarket tools need an FCA-certified authentication path or a bypass. [OFFICIAL] https://kb.fcawitech.com/article/security-gateway-module-aftermarket-specific-903.html
- Flash: dealer campaign instructions have the technician open Topology > module > Flash tab and compare "Current ECU Part Number" with "New ECU Part Number". [CUORE: pdf/Stelvio ECM Flash Procedure (wiTECH).pdf, transcribed from CSN W05 and TSB 18-026-20] [OFFICIAL] https://static.nhtsa.gov/odi/tsbs/2020/MC-10175111-9999.pdf
- MES on this car has done full ECM writes (DTC clears, actuators) with no bypass and no authentication in the logs, so MES is not blocked on this car for ECM work. Whether this car has an SGW at all is open (door-jamb build date before 02/2018 predicts none). [CUORE: docs/research/CONNECTIVITY_AND_SGW.md] This does not change the dealer list below. The things MES cannot do are the module flashes, proxy alignment, the SLVT and the dealer-only service routines.

**B1. Module software level report plus pending flashes (all modules).**
- Ask: print wiTECH's topology list with, for every module that has a Flash tab, Current vs New part number. Flash only the ones with a listed newer calibration and only with the checks in D.
- Priority modules (software numbers read 2026-10-23 by CUORE, F188; [last known] in brackets): ECM 52170619 / P235QB39 [52170619 / P235QB39]; BCM 52154912, HW 52058054 [04441660441 v1454]; TCM 52119227 / GK0902OE2HN, F195 0003; RFHUB 52091977 / 10307064AB, F195 0940; IPC part 50551318 only, software not returned (CAN ERROR); ABS, radio/head unit, DASM, DTCM not read. Full table: `docs/vehicles/ZASFAKPN5J7B88115/MODULE_SOFTWARE_LEVELS.md`.
- Why for this car: no public source names a newer MM10JA calibration; this car's number is higher than any indexed publicly, so it was probably reflashed already. Only wiTECH can confirm. [CUORE: CASE.md "Vehicle and ECU"] [INFERENCE for "probably reflashed"]
- Related bulletins to be settled by that report, none yet VIN-confirmed: TSB 18-026-20 (2018 Stelvio 2.0L ECM flash; says BCM must also be on latest software; lists P1CEA / P24D6, NOT P0440/P0455/P0456) [CUORE: catalogue tsb-18-026-20, verified: true] https://static.nhtsa.gov/odi/tsbs/2020/MC-10174245-9999.pdf ; TSB 21-035-20 (TCM flash for 2018 Stelvio 2.0L; improves 8HP shift quality; pair with 18-026-20) [CUORE: catalogue tsb-21-035-20, verified: true] https://static.nhtsa.gov/odi/tsbs/2020/MC-10176569-9999.pdf ; TSB 08-044-19 (ABS module flash; PDF not opened) [CUORE] https://static.nhtsa.gov/odi/tsbs/2019/MC-10162530-9999.pdf ; radio software bulletins 08-081-19, 08-029-20, 08-065-20 (indexed only) [CUORE].
- Radio software (ETM): ask the dealer to read the radio's current MV number (Settings > System > Software Update > Current Software) and compare it with MV 090.000.061, the latest level in TSB 08-065-20 for the 2018-2019 Stelvio radio (sales code RAN, RAP, RAG or RSD; build 2017-10-30 to 2019-07-12; confirm by VIN and build date). If it is lower, the update is a USB-stick update started from the radio menu with the engine running, not a wiTECH flash; on a car built on or before 2018-04-12 the bulletin also requires BCM, amplifier, ABS, IPC, park-assist and blind-spot software to be current. NO Clear All DTCs afterwards: the bulletin step "clear all DTCs set by reprogramming" would erase the EVAP evidence; any clearing must wait for the proof run and be limited to codes the flash itself set. Ask for the before and after MV numbers on the invoice. The text of 08-029-20 was not found (a forum thread title calls it a 2.0-radio update to MV 002.010.041); ask whether it applies to this VIN. [OFFICIAL, opened in full 2026-10-23] https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf ; [CUORE: docs/research/RADIO_SOFTWARE_AND_UI_OPTIONS.md]
- Note: a forum-quoted Italian bulletin lists "BCM for Stelvio 04441660441, version 1454" as a reference. This car's BCM reads exactly that. Whether a later BCM release exists must come from wiTECH. [FORUM/3RD] https://forum.clubalfa.it/attachments/8242-pdf.191345/ [CUORE: CEL_2026-10-19_DIAGNOSIS.md header]

**B2. TSB 18-030-17 status for the EVAP codes.**
- Ask: does 18-030-17 (any revision) list this VIN or a Stelvio 2.0L in the dealer's Service Library, and does wiTECH offer the ECM calibration it describes?
- Why for this car: it is the only catalogue flash bulletin that lists P0440, P0455 and P0456. But the NHTSA copy opened (Rev D, id 10216318) covers the 2017 Giulia 2.0L built on or before 2017-06-29 only; Stelvio is not listed, and no Stelvio copy was found. So it may not apply; do not let the dealer assume it does. [CUORE: catalogue tsb-18-030-17-rev-b, verified: true; applies: vin_check] https://static.nhtsa.gov/odi/tsbs/2017/MC-10216318-9999.pdf
- The project's earlier ECM-calibration verdict cited this bulletin as its basis; the catalogue records the correction. [CUORE]
- If the dealer finds a Stelvio-applicable EVAP calibration, flash is allowed only after B3 and D1 are done.

**B3. Run the SLVT (Small Leak Verification Test) after the ESIM repair, and before anyone clears codes.**
- Why: TSB 18-048-23 says a road test cannot confirm an EVAP small-leak repair; the wiTECH SLVT must run to confirm a leak and again after any repair, component replacement or software update. It supersedes 18-095-21 and 18-089-19. The bulletin gives no fuel range or pass limit. [CUORE: catalogue tsb-18-048-23, verified: true] https://static.nhtsa.gov/odi/tsbs/2023/MC-10236933-9999.pdf
- Why for this car: CUORE has no way to run the SLVT (read-only replica only). The new ESIM and gasket cannot be proven fixed by the owner's drive cycle alone. [CUORE: wiki/TSB-Layer-and-Cross-Reference.md "SLVT replica"]
- Also related dealer case record: STAR S2025000004 says keep the original gas cap fitted during the test (the adapter o-ring can mask a leak). Only partially opened. [CUORE: catalogue star-s2025000004] https://static.nhtsa.gov/odi/tsbs/2020/MC-10175692-9999.pdf
- Order matters: FDM replacement (A1) will itself disturb the fuel system. [INFERENCE] Ask the dealer to do the SLVT after the FDM work, not before.

**B4. wiTECH Test A (ESIM switch) and the ESIM commanded-vent test, if the ESIM repair did not hold.**
- Ask: with vacuum applied to the ESIM port, watch the ECU's switch state in wiTECH. Record whether it closes, holds, reopens. [CUORE: pdf/Stelvio wiTECH Test A - ESIM Switch.pdf; CEL_2026-10-19_DIAGNOSIS.md "A"]
- Why: the ESIM switch has no readable DID in CUORE or MES; only wiTECH shows it. The parameter name is not known. [CUORE: CEL_2026-10-19_DIAGNOSIS.md]
- Hypothesis H-A (ESIM solenoid / commanded vent circuit never closes the vent) also needs a commanded-vent test with the circuit back-probed. [CUORE: same file, "Also considered"]. Open hypothesis, no result yet.
- The new ESIM replaced one that had been new since 2026-09-02; P0440 returned 2.2 days after that swap. Ask the dealer to confirm ESIM part number, mounting orientation and port seating. [CUORE: CEL file; Stelvio_Recall_Request.pdf technician note] Part number 04861961AD is listed as the production Stelvio/Giulia part; TSB 9100469 does not name an ESIM part number. [CUORE: CASE.md; catalogue tsb-9100469] https://static.nhtsa.gov/odi/tsbs/2024/MC-11011985-0001.pdf

**B5. SGW status and the BCM network codes (U1711 / U1712 / U1713-2F).**
- Ask: (a) does wiTECH show the SGW unlocked, and is an SGW fitted; (b) read the BCM DTCs with extended data / DTC EX and snapshot BEFORE anything is cleared; (c) read ABS DTCs too, which CUORE could never read (ABS silent to CUORE 10-15).
- Why for this car: BCM U1713-2F "Engine control (NCM) signal erratic" is active now; U1711/U1712 appear and disappear together; ABS logged "BCM missing message" at 10.6 V. The BCM is the only module on both sides of the complaints; sender vs receiver cannot be separated from current data. [CUORE: NETWORK_PATTERN_READINGS_2026-10-20.md sections 3a, 3c, 4]
- Also ask for the BCM-side, ABS-side and ECM-side views in one session ("reciprocity snapshot"). [CUORE: same file section 5, item 1]
- Candidate bulletins for the dealer to check by VIN: recall 18V205 and 19V551 (A2), plus STAR S1708000262 "Intermittent module CAN private or LIN bus codes" (indexed only, PDFs not opened) and S2108000163 "No start, cannot complete module replace, PROXI configuration" (no PDF). [CUORE: catalogue] https://static.nhtsa.gov/odi/tsbs/2020/MC-10184414-9999.pdf
- A caution on scan artefacts: earlier CUORE notes said these cascade codes may be produced by the unreachable second and third CAN buses on a plain ELM327 and by ignition cycling during a scan. But U1713-2F was failing with the engine running and the plain-port read, so that does not fully explain it. [CUORE: CONNECTIVITY_AND_SGW.md section 1; CEL file "BCM U1713-2F"] [INFERENCE]
- B10AA-4A "PROXI configuration control, incorrect component installed" was stored in the BCM on 2026-10-14 and cleared. [CUORE: NON_EVAP_CODES_2026-10-20.md table] Ask the dealer to check the PROXI configuration report against the build.

**B6. Battery and IBS (intelligent battery sensor) test, plus charging-system check.**
- Ask: load/conductance test of the 12 V battery, IBS state of charge, and alternator output; record results.
- Why for this car: the only low-voltage reading in the data is the ABS freeze frame, 10.6 V at startups 14280, one start before the first EVAP code of 08-27. A low-voltage event can plausibly set BCM/ABS comm codes; no BCM freeze frame exists to test it. [CUORE: NETWORK_PATTERN_READINGS file 3c, NON_EVAP_CODES 3.1] [INFERENCE for the cause]
- CUORE read IBS state of charge 71 % on 2026-10-19 (ECM DID 19BD = 0x47, formula unverified) and port voltages of 14.0 to 14.5 V. [CUORE: NETWORK_PATTERN_READINGS file section 2]
- 2026-10-23 00:10 to 00:21, engine idling, 10 A charger connected, so battery health could not be judged: port 14.5 V; PID 42 ECM 14.312 V and TCM 14.062 V; BCM DID 1004 14.5 V; ECM DID 19BD IBS state of charge 67 % (formula unverified); ECM DID 1955 not supported. Freeze frames stored 14.2 V (P0455), 14.3 V (P0440) and 12.0 V (P0456, key-on engine-off cold start, IBS 100 %). [CUORE: docs/research/ECU_AND_ELECTRICAL_HEALTH_2026-10-23.md sections 2.2, 2.3, 3.1]
- BCM B101D-15 (FTB 15 = short to +V or open circuit) is new since 10-19: status 0x4D, listed at 0x40 on 10-13 and 10-19. No snapshot was read, and the circuit name is not sourced in the CUORE repo. Ask the dealer to read the B101D-15 freeze frame and extended data in wiTECH and to name the circuit. [CUORE: same file section 3.3]
- Owner tests not yet done (charger off): resting voltage after at least 1 h, cranking voltage record, key-off current after a 30 to 40 min sleep, ground-drop checks. Ask what the dealer's IBS/battery test reports beyond these. [CUORE: same file section 3.4; procedures are external, not readings]
- Low-voltage codes on Alfa: P0562 is the usual flag. Low supply can set U-codes in general. Not an Alfa specification. [FORUM/3RD] https://au7o.io/known-issues/dtc/p0562/alfa-romeo
- CUORE catalogue has TSB S1408000384 (start-stop charging lamp, IBS state of charge; revisions F to J through 2026-03; PDF present, NOT opened). Ask the dealer to check it by VIN. [CUORE: catalogue tsb-s1408000384] https://static.nhtsa.gov/odi/tsbs/2023/MC-10234420-9999.pdf
- I found no Alfa-specific source saying a Giulia/Stelvio needs a wiTECH IBS registration after a battery swap; ask the dealer whether wiTECH has such a function and whether the battery was ever replaced. [FORUM/3RD] https://www.alfabb.com/threads/battery-replacement-procedure.703066/

**B7. PROXI alignment (BCM) and configuration check.**
- Ask: run PROXI Alignment only if a flash or module replacement requires it (W05 and 18-026-20 pair an ECM reprogram with PROXI alignment and the Phonic Wheel Replacement routine). Do not run a "restore vehicle configuration".
- Why for this car: BCM B10AA-4A seen 10-14; any ECM/BCM flash needs the alignment. The "no restore configuration" advice is one forum user's. [CUORE: CSN W05; ECM Flash Procedure PDF] [FORUM/3RD] https://5thgenrams.com/community/posts/943612/ [OFFICIAL, for the pairing] https://static.nhtsa.gov/odi/tsbs/2020/MC-10175111-9999.pdf

**B8. Transmission: TCM software and adaptation state; 8HP fluid level check.**
- Ask: TCM Flash tab result (B1); TCM DTCs; after the earlier pan/filter service, confirm fluid level at the correct temperature using the dealer procedure.
- Why for this car: the transmission was flushed with a new pan/filter. CUORE's own sheet gives a 30-50 degC level-check window [CUORE: Stelvio Transmission and Drivetrain (1 page).pdf, "CONFIRM."] and says no relearn is needed after a routine fluid and filter change, nor after a TCM flash alone. Treat as the sheet's reading of other sources, not FCA text. [CUORE: same sheet; ZF8HP_SERVICE_DATA.md]
- If the dealer wants to run Fast Filling Adaptation / Standard Clutch Filling Adaptation, ask why first. [CUORE: same sheet]

**B9. Mode-06-class data on the dealer tool: record EVAP monitor state before and after.**
- Why: the ECM's own evidence (status bytes, freeze frames, Mode 06) is erased by every clear. On 2026-10-13 Mode 06 showed the 0.090 in test at 404 ms against a minimum of 3965 ms (FAIL) and one 0.020 in test at 6096 ms against a maximum of 6000 ms. What those numbers measure on an FCA ECM is unknown. [CUORE: CEL_2026-10-19_DIAGNOSIS.md, Mode 06 section]
- Ask for a printout (wiTECH freeze frame / DTC detail) of P0440, P0455, P0456 with status bits and snapshot data, before any procedure that clears.

---

## C. Normal-tool / mechanical inspection requests

**C1. Engine mounts, torque strut / "dogbone", transmission mount.**
- Ask: lift inspection plus watch engine movement with a helper shifting P to R/D under brake; look for cracked or separated rubber, fluid leaks (hydraulic mounts), play at the dogbone, and bracket fasteners.
- Why for this car: the owner wants it checked. No clunk or vibration complaint is recorded in the CUORE data I read. [CUORE: grep of docs/vehicles/.../CASE.md and sessions]. Mounts also affect Q4 driveline load. [INFERENCE]
- Bulletins: I found NO NHTSA TSB for Stelvio/Giulia engine or transmission mounts. CUORE's own catalogue notes "research gaps: engine mounts". [CUORE: docs/reference/TSB_CATALOGUE.md line 145] [FORUM/3RD for the search] https://recallcheck.net/tsb/1939 . Possibly relevant, unopened: S2123000016 "Creak noise from front of vehicle" (NHTSA flat-file title only, no PDF) [CUORE: catalogue].
- Forum/vendor material only: a transmission-mount clunk/vibration complaint is cited as common on 2017-2025 Giulia/Stelvio by a parts vendor (page unreadable, title only); general sources say replace mounts together because worn ones shift load to the next. [CUORE: docs/reference/STELVIO_20T_DRIVETRAIN_SPECS.md section 5.2] [FORUM/3RD] https://www.autoguru.com.au/repairs/transmission-mount-replacement-cost/alfa-romeo/stelvio
- If any mount is replaced: CUORE notes the dogbone mount and transmission-bracket fasteners are reported single-use (single-source, forum). Torque figures in CUORE are single-source; ask the dealer to use TechAuthority values, not mine. [CUORE: STELVIO_20T_DRIVETRAIN_SPECS.md section 5.3]

**C2. Front differential fluid ("re-flush") and level check.**
- Wording to use: ask for a drain-and-refill or level check/top-up, not a "flush". [INFERENCE: a machine flush is for automatic transmissions; the front diff holds about 0.5 L.]
- Spec per CUORE: SAE 75W-80, API GL-5, synthetic, FIAT approval 9.55550-DA10; capacity about 0.5 L (single source). [CUORE: Stelvio Transmission and Drivetrain (1 page).pdf] [FORUM/3RD, retailer] https://shop.alfisti.net/Tuning-Styling/Alfa-Giulia/Service-Maintainance/Petronas-Tutela-Transmission-Hypoide-Gear-Oil::9856.html
- Interval: I found no official interval for the front differential. One database and a seller treat the front axle, rear axle, transfer box and gearbox as "lifelong". [FORUM/3RD] https://cararac.com/gear_oil/alfa-romeo/stelvio.html . CUORE's sheet gives no front-diff interval. Ask the dealer what Alfa's own schedule says for this VIN.
- Plug torque: front fill plug 26 Nm is single-source only; drain unknown. Ask the dealer for the service-manual value. [CUORE: same sheet]
- Ask them to record the drained fluid's condition (metal, colour, smell) and amount drained vs refilled.

**C3. Transfer case (Magna Q4).**
- CUORE's sheet says oil is "DUE at 80,000 mi / 128,000 km / 8 years (owner's manual, marked CONFIRM)" and the car is past it. [CUORE: Stelvio Pending Items (1 page).pdf; Transmission and Drivetrain sheet] But third-party databases list it as "lifelong". The two conflict; the owner's manual or dealer schedule must settle it. [FORUM/3RD] https://cararac.com/gear_oil/alfa-romeo/stelvio.html
- Fluid per CUORE: Petronas Tutela Transmission Transfer Case (Q4), SAE 75W, API GL-5, FIAT approval 9.55550-DA11; do not substitute ATF or generic 75W GL-5. Capacity conflicts: about 1 L (repo doc) vs 0.7 L (giuliatech.com) vs 0.5 L (cararac). [CUORE: sheet; TRANSMISSION_ZF8HP_Q4.md section 5] [FORUM/3RD] https://cararac.com/gear_oil/alfa-romeo/stelvio.html
- Ask: confirm the correct spec and capacity from service information before refilling; check for leaks at output seals; DTCM DTCs (DTCM held U0100-87 "ECM missing" in 7 scans; likely a cascade code). [CUORE: NON_EVAP_CODES table]
- Do NOT run the DTCM ADJ (end-stop learn) unless a procedure calls for it; it can bind the driveline with wheels on the ground. [CUORE: TRANSMISSION_ZF8HP_Q4.md section 5, hypothesis]

**C4. Rear differential.**
- Spec per CUORE: SAE 75W-85, synthetic, FIAT approval 9.55550-DA9, capacity 0.9 to 1.1 L depending on unit (195 open / 230 LSD / 210 eLSD). Which unit this VIN has is unknown. [CUORE: sheet]
- Ask: identify the unit from the VIN/RPO code; level check for leaks at pinion and side seals; interval per Alfa schedule (not found officially).

**C5. ZF 8HP transmission.** Pan/filter already renewed. Ask only for: leak check at pan and cooler lines; DTC read; fluid level per procedure (B8). CUORE's sheet lists ZF 'LifeguardFluid 8 / Mopar 8 & 9 Speed ATF' (part 68218925AA, from the sheet) and says it is NOT compatible with ATF+4. Confirm the fluid used last time. [CUORE: sheet] Vendor/forum intervals range from "lifetime fill" to 100,000 km; ZF generic guidance is 150,000 km (quoted on a Jeep forum). [FORUM/3RD] https://www.jeepgladiatorforum.com/forum/threads/zf-8hp-transmission-service.101988/post-1635420

**C6. Brakes after the new pads.**
- Ask: inspect fronts and rears after the new pads: rear EPB caliper function and that service mode was used for the rear job; pad-wear sensor state; rotor thickness vs minimum (front new 28 mm, minimum 25.5 mm; rear minimum unknown, read the MIN TH marking); caliper slide pin condition; brake fluid level and fluid condition. [CUORE: Stelvio Brakes Wheels Tyres (1 page).pdf]
- Why for this car: ABS FES on 2026-09-04 logged C104B-92 "leaks in hydraulic group" and U1700-87. It has not been re-read since the clear (ABS silent to CUORE 10-15). The only free check is physical: reservoir level, wetness, firm pedal. [CUORE: NON_EVAP_CODES_2026-10-20.md section 3.1] Brake fluid due every 2 years (DOT 4, FCA MS.90039); CUORE assumes it is overdue unless changed since 2024-09. [CUORE: Pending Items sheet]
- Ask the dealer to check recall 17V823 (A2) and TSB S1705000002 (front brake pulsation and/or clunk, Rev A; flat-file entry, not opened). [CUORE: catalogue tsb-s1705000002] https://static.nhtsa.gov/odi/tsbs/2025/MC-11013151-0001.pdf
- If the battery is disconnected with the caliper off: pump the brake pedal before reconnecting to avoid codes. [CUORE: Brakes sheet; single-source]

**C7. FDM seal and fuel tank area (during the 93C job).**
- Ask: inspect the FDM lock ring and seal condition, the internal vapour line at the FDM port (A4), the fuel feed and vapour connections; tell the owner what failed or was damaged.
- Keep the old seal (D3).

**C8. Underbody EVAP lines and the ESIM area.**
- Ask: visual inspection of the tank-to-canister vapour hose (kink, pinch), recirculation line including the mid-point quick-connect, canister-to-ESIM hose, ESIM-to-filter clean-air hose, the connector behind the driver-side rear wheel liner (water, corrosion), the ESIM mounting. Low-pressure air flow through each leg if they are willing (smoke shows leaks, not blockage). [CUORE: CEL_2026-10-19_DIAGNOSIS.md candidate causes C1 to C6, test B] [INFERENCE: three smoke tests cannot show a blockage]
- TSB 9100471's own tree lists a kinked tank-to-canister hose and the ESIM-to-filter clean-air hose; only the filter has been recorded as checked. [CUORE: catalogue tsb-9100471; CEL file]
- Also from CUORE: purge hose checks at the ejector tees (TSB 9100325, SOL S2518000008 by VIN search) apply before replacing a purge valve for P1CEA. That valve (68337662AC) is already new. [CUORE: catalogue tsb-9100325]

---

## D. What the dealer must NOT do, or must record

**D1. No clearing of ECM (or any) DTCs unless a documented procedure step demands it. Record before clearing.**
- Why: 11 ECM clears in 53 days each restarted the evidence; the monitor proof run is pending and the EVAP monitor needs 15-85 % fuel, cold starts and several days to complete. [CUORE: CEL file; Pending Items sheet]
- Exception that must be handled: the dealer's own flash procedures (CSN W05, TSB 18-026-20) include "Clear All DTCs" after the flash and PROXI alignment. If a flash is done, that clear is part of the procedure and will reset the EVAP monitor. Make this a conscious decision: ask the dealer to print DTCs, status bytes and freeze frames first, and tell the owner. [OFFICIAL] https://static.nhtsa.gov/odi/tsbs/2020/MC-10175111-9999.pdf [CUORE: ECM Flash Procedure PDF steps 10 and 12]
- The FDM recall and the SLVT do not require clearing. Say so on the work order: "DO NOT CLEAR CODES unless required by a flash procedure."

**D2. Battery disconnect: record it.**
- If the battery is disconnected (FDM work often does this), ask the dealer to note time, duration and whether a memory saver was used, so later codes can be dated against it. Reason: stored data and learned values can be affected; BCM/EPS relearn may follow (a 2019 bulletin for 2017-2018 Giulia pairs a negative-cable disconnect with an EPS relearn and DTC clear via wiTECH). [FORUM/3RD: search-result summary only; the bulletin itself was not opened and its number is not confirmed here]
- CUORE says 8HP adaptations are non-volatile and not lost on battery disconnect (sheet, single-source). [CUORE]
- Record battery voltage at arrival and before/after the visit.

**D3. Keep the old FDM seal and the old FDM module (or photographs).** Reason: evidence for EVAP seal condition and for the FDM failure mode; the new ESIM/gasket work and this car's chronic EVAP history make any seal damage relevant. Ask for the removed seal in a bag labelled with the VIN. [INFERENCE]

**D4. Record these on the invoice / work order:**
- Odometer in and out; fuel level in and out (affects EVAP monitor conditions: 15-85 %).
- Every software part number before and after, per module.
- Every DTC found per module, with status.
- Recall/campaign VIN status printout (A2).
- Part numbers of installed FDM, ESIM, mounts, fluids (type, approval code, litres drained/filled).
- Whether a bypass or SGW workaround was used (should be none).

**D5. Do not top off or overfill the fuel tank, and ask them to return the car with fuel between about 15 and 85 percent, ideally not a fresh full tank.** Reason: EVAP monitor conditions; also over-fill saturates the canister (TSB 9100471 area). [CUORE: ECM Flash Procedure PDF; CEL file] [INFERENCE for the instruction to the dealer]

**D6. Do not substitute fluids.** Q4 transfer case and differentials have FIAT approval codes (DA10, DA11, DA9 above); ATF or generic 75W GL-5 is not acceptable for the transfer case per CUORE's sheet. [CUORE: sheet; single-source flagged]

**D7. Do not replace the EVAP canister or ESIM again without the SLVT result.** TSB 9100469: if only the ESIM is faulty, replace only the ESIM, not the canister; the canister and ESIM have both been replaced already. [CUORE: catalogue tsb-9100469, tsb-9100471] Parts-cannon risk: the case already has an ESIM, canister, purge valve, filter and fuel cap replaced and three clean smoke tests. [CUORE: CASE.md]

**D8. Do not run unneeded flashes or adaptations.** Flashes only per B1 (different Current vs New number), with charger at 13.2-13.5 V, tool on only, no interrupt, per the FCA instructions. [CUORE: ECM Flash Procedure PDF] [OFFICIAL] https://static.nhtsa.gov/odi/tsbs/2020/MC-10175111-9999.pdf

**D9. Ask the dealer NOT to attach any other scan tool at the same time, and for the owner not to leave MES or CUORE connected.** Only one tester on the OBD port. [CUORE: ECM Flash Procedure PDF "practice" items; WITECH_PASSIVE_LEARNING.md]

---

## E. Baseline OBD read, 2026-10-23 (filled from CUORE scan SCAN_2610230010)

Read only through CUORE sessions, one tester on the port, no clears. Full readings, verdict and raw files: `docs/research/SCAN_2026-10-23_POST_ESIM.md` and `data/captures/stelvio-2018/scans/2026-10-23_SCAN_2610230010/`. [CUORE] = reading; [OWNER] = owner-stated.

**E1. Read date/time, odometer, fuel level %, ambient temp, ignition state:**
2026-10-23 00:10 local. Odometer: 148,207 km (owner-stated, dashboard); MES reading 2026-10-23 01:16 of the IPC: 148207.0 km (identical). CUORE did not read it (see the research doc); the P0455 freeze snapshot carries 146,879.1 km (DID 2001, medium confidence), which does not agree with it and is unverified. Fuel 45.9 % (PID 2F) / 46.7 % (DID 1001). Ambient 8 C (PID 46). [OWNER] ignition on, engine off, car on a 10 A charger, no adapter cable (CAN-C only). [CUORE] note: PID 0C read 750 rpm at the time, so the engine may have been idling.

**E2. Module list and software versions** (last known in brackets):

| Module | Part / SW number (read 2026-10-23) | Version | Source |
|---|---|---|---|
| ECM | part 50544870 / SW 52170619 / supplier P235QB39 / serial TD4192427B17540 / HW 52055320 MM10JAHW232 [52170619 / P235QB39] | F195 00 00 [0000]; F189 not supported | CUORE F187/F188/F194/F195/F18C/F191/F192, file 34, read 2026-10-23 |
| BCM | part 50554114 / SW 52154912 / serial TD3692377101420 / HW 52058054 BCM949M_C02 [04441660441] | F194/F195 not returned; F189 not supported [1454]; identity read ended in CAN ERROR | CUORE file 35, read 2026-10-23 |
| TCM | part 46337308 / SW 52119227 / supplier GK0902OE2HN / serial TF0662057729150 / HW 52097735 10344202761 | F195 00 03; F189 not supported | CUORE file 36, read 2026-10-23 |
| IPC | part 50551318 (only F190 VIN and F187 returned); MES: HW A2C11140400 ver 01 / SW AR952 HL ver 203C | MES software version 203C; CUORE not read (CAN ERROR) | CUORE file 37, read 2026-10-23, CAN ERROR; MES FESLog_2610230116, 01:16 (see `radio/MES_MODULE_READS_2026-10-23.md`) |
| RFHUB | part 50544008 / SW 52091977 / supplier 10307064AB / serial T04Z22117E01040 / HW 52057995 10161500AA | F195 09 40; F189 not supported | CUORE file 38, read 2026-10-23 |
| ABS | not read | not read | needs grey adapter / CAN-CH; silent to CUORE 10-15 |
| DASM | MES: HW MRR1evo14F ver 00 / SW 52081920 ver 0500 | MES software version 0500 | MES SCAN_2610230112, read 2026-10-23 01:12 (CUORE: not read) |
| DTCM (transfer case) | MES: Magna Q4, HW M0045027.01 ver 21 / SW M0099947 ver 0501 | MES software version 0501 | MES SCAN_2610230112, read 2026-10-23 01:12 (CUORE: not read) |
| ESM (gear shift module) | MES: ZF, HW 1000597140 ver 08 / SW 1000678050 ver 0019 | MES software version 0019 | MES SCAN_2610230112, read 2026-10-23 01:12 (CUORE: not read) |
| Radio / nav (ETM) | not read | not read | no MES or CUORE log of the radio exists; IPC and BCM log the fault "Entertainment Telematic Module (ETM)" (U1736) |
| Others | not read | not read | No camera / ParkView / PAM module answered on CAN-C |

**E3. Current DTCs per module with status byte** (NOTE: a MES scan at 01:12 on 2026-10-23, after the 00:10 read, ended with a fault-code clear on ECM, IPC, BCM and DASM; so the 00:10 codes below are the pre-clear state and the EVAP proof restarted. Also an IPC service-interval reset at 01:13. See `radio/MES_MODULE_READS_2026-10-23.md`.) (last known: ECM P0440 0xCD, P0455 0x4D, P0456 0x4D; BCM U1713-2F 0x0F; cleared 2026-10-19 00:39, so confirm what has returned):
ECM: P0440-00 0x4D, P0455-00 0x4D, P0456-00 0x4D (testFailed, pending, confirmed, testNotCompletedThisOperationCycle; MIL not requested). Mode 03 stored: none. Mode 07 pending: P0440 P0455 P0456. Mode 0A permanent: P0440 P0456. P0455 freeze frame: coolant 56 C, fuel 82.7 %. BCM: B101D-15 0x4D; B10AA-4A 0x08; B1176-97 0x08; U1736-87 0x08. IPC: U1736-86 0x0E; U1736-87 0x0E. TCM and RFHUB: none. U1711 / U1712 / U1713: ABSENT in every module (BCM U1713-2F is no longer present). DASM, DTCM, ESM, ABS: not read.

**E4. Readiness monitors** (EVAP, catalyst, O2, EGR; MIL status; distance with MIL; warm-ups and km since last clear):
MIL off. Distance with MIL on 0 km. Warm-ups since clear 14; distance since clear 342 km. Readiness since clear: all complete except EVAP INCOMPLETE; EGR incomplete this drive cycle (PID 41). EVAP proof: INCOMPLETE, not failed and not passed.

**E5. Mode 06 EVAP** (OBDMID 0x3A TID 0x87 value/min/max; OBDMID 0x3C TID 0x90 value/min/max; 0x3D purge flow). Last known 2026-10-13: 404 / 3965 / 65535 and 6096 / 0 / 6000. The OBD side returned NO DATA on 10-19; the legislated route is the 29-bit 18DB33F1 route per CUORE note. If it returns NO DATA again, say so; do not fill with a guess.
Answered this time. 0x3A/0x87: 496 ms, min 3707, max 65535, FAIL (10-13: 404, min 3965). 0x3C/0x90: 6096, min 0, max 6000, FAIL (identical to 10-13; looks like a sentinel value, inference). 0x3C/0x85: 4722 (max 4200) FAIL. 0x3C/0x86: 15379 (max 6000) FAIL. 0x3D/0xA0: 65535 (min 19660) PASS. 0x3D/0xA1: 196 (63 to 326) PASS. Units are ms where UASID 0x10; scaling of the 0x85/0x86/0x3D records is unknown.

**E6. Battery voltage and IBS:** key-on engine-off V, engine-running V, BCM DID 1004 V, IBS state of charge (last 14.0-14.5 V running; SoC 71 % unverified formula).
Adapter 14.5 V before and after; PID 42 14.31 V; BCM DID 1004 145 = 14.5 V (unverified formula); ECM DID 19BD IBS state of charge 67 % (unverified formula). The car was on a 10 A charger, so battery health could not be judged. BCM B101D-15 (FTB 15 short to +V or open circuit; the circuit name is not sourced in the repo; status 0x4D) is new and is the next reading to chase.

**E7. ECM external temperature vs real ambient** (last 06-07: pinned at -61 C while air temp read 30 C) and fuel level vs gauge. Hypothesis 8c659dfc (EVAP inputs invalid) depends on this. [CUORE: CEL file test E]
ECM ambient (PID 46) 8 C: plausible, no -61 C value. Real outside temperature at the car was not recorded; compare with the owner's figure. Fuel 45.9 % (PID 2F), 46.7 % (DID 1001); the dash gauge reading was not recorded. Hypothesis 8c659dfc is weakened, not refuted.

**E8. Anything the owner reports** (symptoms, MIL on or off, warning messages, mount noises, brake pedal feel):
`____________________`

---

## F. Open points to check before sending this to the dealer

1. 93C remedy availability and the parts ETA: ring the dealer and Alfa Romeo Premium Care. [FORUM/3RD] https://moparinsiders.com/recall-53849-alfa-romeo-models-for-potential-fuel-pump-failure/ (phone numbers quoted in the search summary: not verified here).
2. Official Alfa schedule for transfer case, front/rear differential and 8HP intervals: not found in any official document; owner's manual maintenance section needed. CUORE's "80,000 mi / 8 years" for the transfer case is marked "CONFIRM" in its own sheet.
3. The recall-request PDF layout in CUORE is garbled in the text extraction (columns misaligned). Check the printed sheet before handing it over.
4. ESIM + gasket replacement (2026-10-22, white cylinder up) is recorded in CUORE (commit 7eb8e8b); add the new ESIM part number when known.
