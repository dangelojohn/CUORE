# NHTSA-hosted bulletins for the Alfa Romeo Giulia (952) and Stelvio (949), 2017-2022

Date: 2026-10-29. Research only: no car contact, nothing applied to `cuore/data/tsb_catalogue.json`. Proposed rows are in `C:\Users\User\AppData\Local\Temp\claude\C--Users-User\2b78a81f-e133-4838-bb10-86d4515c13d7\scratchpad\tsb_rows_proposed.json` (44 rows, each with its NHTSA source URL). Bulletin text is saved under `C:\ProgramData\cuore\research\nhtsa_bulletins_2026-10-29\` (one `<NHTSA id>.txt` each, plus `SOURCES_AND_FINDINGS.md`).

## 1. What was searched and how much was read

- The NHTSA vehicle API has no manufacturer-communications path that works without a key. The NHTSA bulk flat files do: `static.nhtsa.gov/odi/ffdd/tsbs/TSBS_RECEIVED_2015-2019.zip`, `..._2020-2024.zip`, `..._2025-2025.zip`. Filtering make ALFA ROMEO, models GIULIA, GIULIA QUADRIFOGLIO and STELVIO, model years 2017-2022 (Stelvio 2018-2022) gave **408 NHTSA records = 288 distinct documents** (the same bulletin is often filed once per model year or engine).
- PDFs come from `static.nhtsa.gov/odi/tsbs/<year>/MC-<id>-9999.pdf` (ids starting 11 use `-0001`). The NHTSA host blocks bursts of requests, so some were fetched slowly and a few through WebFetch's cache.
- **Full text retrieved for 249 of 288 documents** (291 of 408 records; the rest of the records are duplicate listings of a text already held). **39 documents are summary only**: image-only or near-empty PDFs (for example D-17-10, D1704, 9100142), parts notices, and a handful of duplicates not fetched. The summary is the NHTSA flat-file line.
- **Detailed reading** (every procedure line) of about 95 documents: all powertrain, EVAP, ECM, TCM, ABS, BCM, battery, security and STAR cases for the 2.0T, plus the 2.9 flashes briefly. The rest (body, glass, radio, HVAC, telematics, collision, warranty) were skimmed for DTCs and tools only.
- **Recalls**: the recalls API returned 21 campaigns for these cars; only the API summary text was used (remedy documents not retrieved), except 21V309 and 25V586 where a document was already cached.
- **No 2.2 diesel documents exist** on NHTSA for these models (not sold in the US). 2.9 V6 documents are listed in the tables as "2.9".
- Existing catalogue rows already covered 18-026-20, W05, 18-089-19, 18-048-23, 18-030-17 and the EVAP set; this sweep confirms them and adds the rest.

Key to tables: G = Giulia, S = Stelvio. "Read" = full text read. Dates are the bulletin dates inside the document.

## 2. Tables by model year

Counts of distinct documents NHTSA files per model year (all kinds): Giulia 2017 115, 2018 92, 2019 97, 2020 105, 2021 96, 2022 85; Stelvio 2018 88, 2019 102, 2020 107, 2021 98, 2022 88. Most are warranty, parts, body and radio items. The tables list the ones that matter for diagnosis.

### 2017 (Giulia only)

| Number | NHTSA id | Scope | What it does | Read |
|---|---|---|---|---|
| 18-030-17 base, Rev B, C, D | 10140044, 10138905, 10223658, 10216318 | G 2.0L, built to 2017-02-27 (base) and 2017-06-29 (Rev D) | ECM flash; DTC list incl. P0440 P0441 P0455 P0456 P1CEA P24D6; Phonic Wheel Replacement | yes |
| 18-025-17 Rev A | 10140019, 10223657 | G 2.9, built to 2017-05-10 | Both ECMs flashed; no restart after stop/start | yes |
| 21-032-17 | 10223674 | G 2.0, 8HP50, built to 2017-05-02 | TCM flash: bump after Stop/Start | yes |
| 09-005-17 | 10223656 | G 2.0, built to 2017-01-13 | Turbo coolant hose O-ring 68338389AA | yes |
| 08-065-17 | 10223651 | G 2.0, built to 2017-03-03 | EGR temperature sensor crack inspect, 68142905AA | yes |
| 08-064-17 | 10223650 | G Harman Kardon, built to 2017-05-24 | Amplifier cover; B10AA-4A, U1746-87, U0186-31, U197C-83 | yes |
| 08-060-17 | 10223646 | G 2.0 and 2.9, built to 2017-06-05 | ACC flash; C1401-86, C141C-86 | yes |
| 08-069-17 | 10223655 | G, built to 2017-07-10 | RFHM flash for B1052-13; record TPMS IDs, Exit Logistic first | yes |
| 08-026-17 / Rev A, 08-027-17 / Rev B | 10140023, 10140031, 10140030, 10224927 | G (08-027 is 2.9) | BCM Restore Vehicle Configuration / Proxi for remote start; BCM flash | yes |
| 9003694, 9003413 | 10139989, 10138856 | G | P06DD oil pump (Pentastar); accelerator pedal P2122 P2127 P2299 | yes |
| 07-004-17, 9003357 | 10138940, 10138863 | G 2.9 / V6 | Coolant hose clip; oil filter adapter | yes |

### 2018

| Number | NHTSA id | Scope | What it does | Read |
|---|---|---|---|---|
| 18-103-19 (RRT 17-112) | 10170404 | S 2018 2.0L, all builds | ECM flash + Phonic Wheel Replacement; P013A P015A P1CEA P0096 P04DB P024A P2097 P2B2F P24D6 P01BA P026E P164E P0191 P2299 U1008 | yes |
| 18-026-20 | 10174245 (also 10175165, 10175578) | S 2018 2.0L | Supersedes 18-103-19; adds P0106 | yes |
| W05 (CSN) | 10175524 (also 10174191, 10175111) | G 2017-2019, S 2018-2019, 2.0L | PCM flash for turbo oil-feed cooling; PROXI Alignment + Phonic Wheel Replacement | yes |
| 18-097-19 / 18-027-20 | 10170388, 10174247 | G 2017-2018 2.0L | Same flash with P0440 P0441 P0455 P0456 listed; adds RPM sensor/timing chain routine | yes |
| 21-032-20 | 10175728 | G 2018 2.0L | TCM flash (P0002 P026E P1066 P26E4 P2B61 P2BC1 U1008) | yes |
| 08-044-19 | 10162530 | S 2018 built to 2018-03-13, no NH3 | ABS flash, up to three steps with Proxi and Restore Vehicle between | yes |
| 08-042-19 | 10162528 | G 2018 | ABS flash | yes |
| 08-029-20 | 10174204 | S 2018 built to 2018-01-11, RAN/RAP/RSD radios | Radio to MV-002.010.041, then module updates | yes |
| 01-001-20 | 10175722 | G/S 2018-2019 2.0L | Oil monitor early; accelerator-pedal reset | yes |
| 18-017-21 | 10188809 | S 2018 2.9 | Oil vapor tube + both ECMs | yes |
| 18-089-19 | 10169219 | all FCA gas 2015-2020 | wiTECH SLVT mandatory for P0456 | yes |
| 18-039-20 | 10175733 | all FCA gas | Winter-blend fuel driveability | yes |
| S2018000004, S2018000011 | 10175670, 10183038 | G/S 2017-2019 | After W05: U04B1 (BCM restore config); P0299/P0300-4 (re-flash) | yes |
| S1808000005 | 10175655 | S 2018-2020 | No start, many modules silent: BCM feeds, fuse F82 | yes |
| S1809000007, 9004335 | 10190667, 10184380 | G/S | Oil filter adapter seals; turbo oil feed O-ring | yes |
| Recalls 17V823, 18V147, 18V203, 18V205, 18V636 (UA4), 19V148, 19V551 | n/a | S 2018 (18V636 also G) | See section 3 | summary |

### 2019

| Number | NHTSA id | Scope | What it does | Read |
|---|---|---|---|---|
| 18-101-19 then 18-024-20 | 10170399, 10174243 | S 2019 2.0L, built to 2019-10-10 | ECM flash, BCM PROXI Alignment, Phonic Wheel, TCM | yes |
| 18-098-19 then 18-025-20 | 10170393, 10174246 | G 2019 2.0L | Same | yes |
| 21-044-19 / 21-045-19 | 10170397, 10170394 | S / G 2019 2.0L | TCM flash (shift quality) | yes |
| 18-088-19 | 10169218 | S 2019 2.9, built to 2019-05-06 | Both ECMs, "control unit reprogramming" routine, oil level sensor routine (above 80 C) | yes |
| 08-025-21 | 10188814 | S 2019 2.0L, 2019-05-08 to 09-19 | EPS flash, lock to lock | yes |
| 08-022-21 / 08-023-21 / 08-106-20 / 08-107-20 | 10188797, 10188799, 10187709, 10187708 | S / G 2019 | DSCM flashes (B1603-68, U0011, U0012, U1700, U1A18, U1A20) | yes |
| 18-051-20 | 10177534 | G 2017-2019 2.9 | Bypass valve connector P00C0-00 | yes |
| S2018000014, S2018000008 | 10187651, 10223551 | G/S 2019-2020 | Cold-start misfire counts (injectors); surge/P0299 after update | yes |
| 08-081-19, 9004130 | 10166576, 10166551 | S 2018-2019 built 2017-10-30 to 2019-03-06 | Radio software MV 085.000.046; battery tech tip | yes |

### 2020

| Number | NHTSA id | Scope | What it does | Read |
|---|---|---|---|---|
| S2008000163 | 10183044 | G 2020 | P0440/P0456 after repair or low mileage: check ESIM connector D2812A | yes |
| 08-045-20 Rev A, S2008000001 | 10180265, 10174139 | G/S 2020 | B1006-49 C141C-86 C1999-86: Restore Vehicle Configuration + Proxi alignment | yes |
| 08-103-20 / 08-104-20 / 08-020-21 / 08-021-21 | 10187696, 10187694, 10188796, 10188795 | S / G 2020 | DSCM flash | yes |
| 08-093-20 | 10183073 | S/G 2020 | ACC flash (U148A-86) | yes |
| 08-038-21 / 08-039-21 | 10190707, 10190706 | S / G 2020 | BCM flash | yes |
| 24-003-20 / 24-002-20 / 24-003-21 | 10187718, 10187719, 10198437 | S/G 2020 | HVAC flash, B10C8-36 | yes |
| S2008000013, S2008000021, S2008000017 | 10173328, 10174150, 10174135 | all | Key PIN; ESS inhibit list door false; ESS above 5,250 ft | yes |
| S2008000078, S2008000080, S2008000079 | 10176550, 10177468, 10223522 | G | Start-stop U0102; P0103 main relay; cluster hours | yes |

### 2021

| Number | NHTSA id | Scope | What it does | Read |
|---|---|---|---|---|
| S2125000002 | 10212447 | G/S 2020-2021 | EVAP codes incl. P0441 P0455 P0456 P1CEA: check recirculation line mid-point quick connect, run wiTECH EVAP leak test | yes |
| S2125000003 | 10221635 | G/S 2020-2021 | P1CEA alone: borescope ejector tee | yes |
| S2108000196 | 10218498 | G/S 2021 | NRC 0x22 reading battery SOC; use ECM Data "Battery Charge Status" | yes |
| S2108000163 | 10221597 | G/S 2018-2021 | Module replacement: use Module Replacement Guide; BCM ECU Reset | yes |
| S1821000001 | 10221150 | G/S 2017-2021 | Gear ratio DTCs, shudder: tyre circumference | yes |
| 24-005-21 / 24-006-21 | 10198433, 10198436 | G / S 2021 | HVAC flash | yes |
| S2109000004 | 10221594 | all | Replacement engine heat tabs | yes |
| S2108000271, S2108000280 | 10204334, 10204355 | G/S | U0422-64 FFCM; C1417/C1418-78 DASM alignment pins | yes |
| 18-080-23 (2.9) | 10241139 | S 2021 2.9 | Both ECMs + TCM; P043E | yes |

### 2022

| Number | NHTSA id | Scope | What it does | Read |
|---|---|---|---|---|
| 18-069-22 Rev B | 10214611 | S 2022 2.0L, built 2021-11-30 to 2022-04-13 | PCM flash, Proxi, Phonic Wheel, accelerator relearn; P2AC0 | yes |
| 18-041-23 (RSU 23-098) | 10236901 | S 2022 2.0L | Adds P1CEA | yes |
| 09-002-22 | 10223001 | G/S 2021-2022 2.0L, Sep 8-28 2021 | Replace four coils | yes |
| S2218000018 | 10225219 | G/S 2017-2020 | Misfire: borescope for coolant after hot cycle | yes |
| S2208000073 | 10212318 | G/S 2018-2022 | P0513: PCM/ECM/ESL replace routine, Proxy Configuration Alignment, Learn ETC | yes |
| S2223000047 | 10221417 | G/S | C1452-86: brake switch voltage at PCM pin 71B | yes |
| 05-004-23 | 10242807 | S 2021-2022 | Brake pads and rotors thump | yes |
| Z17 (emissions recall), 21-006-22 / 21-009-23 TCM, 18-043-23 | 10214590, 10212419, 10236927 | S 2022 2.9 | 2.9 only | yes |
| S1408000384 (IBS) | 10234420 | G/S 2017-2023+ | IBS rules, B2193 U113E P00FD | yes |

Not on NHTSA for this car: any 2018 Stelvio TCM flash, any Stelvio 2.0L bulletin listing P0440, P0455 or P0456 as a flash symptom, and any bulletin containing B1040, B1176, B101D, U1736 or C104B. The word "shudder" appears in one bulletin only (S1821000001).

## 3. Recalls (NHTSA API summaries only)

| Campaign | Stellantis | Scope | Remedy |
|---|---|---|---|
| 18V636 | UA4 | G 2017-2018, S 2018, 2.0L | Inspect codes, update ECM software (misfire overheats catalyst); began 2018-10-10 |
| 17V823 | T84 | G/S 2018 | Brake fluid contamination; inspect and replace |
| 18V147 | U24 | S 2018 | Wiper motor replaced |
| 18V203, 18V205 | n/a | S 2018 | Liftgate wiring and BCM water intrusion |
| 19V148 | V27 | G 2017-2019, S 2018-2019 | BSM software (ACC cannot be disabled) |
| 19V551 | V84 | G/S 2018-2019 | BCM software (fuel level reads high) |
| 18V635 | n/a | S Quadrifoglio 2018-2019 | Coolant hose |
| 18V828, 20V714, 21V221, 21V309, 21V848, 21V878, 24V306, 24V512, 24V510, 24V943, 25V586, 25V667, 23V382 | various | Mostly not 2018 Stelvio | 24V510 (frontal air bags), 25V586 (fuel pump, S 2018-2019) and 23V382 (carbon ceramic brakes, option only) are the later ones that reach 2018 cars |

## 4. Procedures and identifiers published

No bulletin publishes a DID, a routine identifier, a UDS service number, a seed/key algorithm or a Mode 06 table. They publish **procedure names, menu paths, order and preconditions**. That is useful for naming and sequencing CUORE's own definitions, not for the bytes.

**Preconditions common to every flash bulletin** (18-030-17, 18-026-20, W05, 08-044-19 and the rest): wiTECH 2 at latest release; battery charger holding 13.2 to 13.5 V (W05 adds: use an accurate stand-alone voltmeter, charger on continuous, apply a light load if voltage is above 13.5); do not let the flash be interrupted, restart if it is; clear all DTCs after the flash (wiTECH presents them); S2018000011 says low voltage or a poor link can leave P0299 and P0300-P0304 behind. Flash time quoted: about 7 to 9 minutes for the ECM. Informs `web-write-lock`.

**Named routines and their location**

| Routine | Where wiTECH puts it | Bulletins | Parity ids |
|---|---|---|---|
| Phonic Wheel Replacement (then RPM Sensor and/or Timing Chain Replacement if errors; P1300 stays active if wrong) | ECM, Misc. Functions | 18-030-17, 18-103-19, 18-026-20, 18-097-19, W05, 18-069-22 | `throttle-relearn` |
| PROXI Alignment / Proxy Configuration Alignment | BCM, Misc. Functions; also Guided Diagnostics > activities; also Vehicle View > Diagnostic Procedures | 18-101-19, W05, 08-044-19, S2208000073 | `proxi-alignment` |
| Restore Vehicle (Proxy) Configuration | BCM, Misc. Functions; ABS Misc. Functions > Control Unit Programming for ABS | 08-045-20, S2008000001, S2018000004, 08-044-19 | `proxi-alignment` |
| PCM/ECM/ESL replace | BCM, Misc. Functions; verify PCM "programmed" | S2208000073 | `security-access`, `key-remote-learning` |
| Learn Electronic Throttle Control | PCM, Misc. Functions | S2208000073 | `throttle-relearn` |
| Control unit reprogramming routine; oil level sensor replacement (engine above 80 C, key on, engine off) | ECM and ECM2, Misc. Functions (2.9) | 18-088-19, 18-017-21 | sibling engine |
| Exit Logistic | BCM, Misc. Function | 08-069-17 | `bcm-commands` |
| FPS actuate (Fire Protection Strategy) and fuel pump relay actuate | scan tool actuator | S2308000004 | `bcm-commands`, actuator tests |
| wiTECH Small Leak Verification Test (SLVT) | EVAP diagnostic in wiTECH | 18-089-19, 18-048-23 | `act-evap`, `proof-of-repair` |
| Oil monitor reset: Start/Stop to RUN, accelerator fully five times within 10 s, Start/Stop once | pedal sequence or scan tool | 01-001-20 | `oil-change-reset` |
| Steering angle: lock to lock after EPS flash | manual | 08-025-21 | `steering-angle` |
| Battery SOC: ECM Data "Battery Charge Status" above 70 percent; IBS learn needs 1 crank and 2-4 h quiescent (-500 to +50 mA) | ECM Data | S2108000196, S1408000384 | `ibs-battery-read`, `battery-type` |
| Key PIN: rolling PIN from DealerCONNECT KeyCode or Tech Authority, valid 12 h or until next VIN search | external | S2008000013 | `security-access`, `key-remote-learning` |

**Published values, parts and levels**
- Sequence after a PCM flash for 2019 cars: ECM flash, BCM PROXI Alignment, ECM Phonic Wheel Replacement, clear, then TCM (18-101-19). For 2018 Stelvio (18-103-19, 18-026-20): ECM flash, Phonic Wheel Replacement, clear, then confirm BCM is current. 2022 (18-069-22 Rev B) adds: press the accelerator fully and release to idle three times; MIL stops blinking.
- Labour operations: 18-19-06-BF (18-026-20 and 18-103-19, 0.4 h), 18-19-06-AY (Stelvio 2019), 18-19-06-A8 (Giulia 2017-18), 18-W0-51-81/82/83 (W05, 0.2 / 0.4 / 0.5 h).
- ECM identity check: W05 step 9 compares "Current ECU Part Number" with "New ECU Part Number" in the wiTECH Flash tab. No software level or part number value is printed.
- Radio levels: MV 085.000.046 (08-081-19), MV-002.010.041 (08-029-20); sales codes RAN, RAP, RAJ, RAG, RSD.
- Parts: ESIM connector D2812A (S2008000163); ignition coil 68211953AA (09-002-22); turbo O-ring 68338389AA, EGR temperature sensor 68142905AA (Giulia 2017); turbo part numbers 04893687A, 68377382A, 05281614A, 05281541A (9004335); EVAP canister filter 04627332A (9100468); oil leak dye 05010042AC; ECM bypass connector 68369901AA (2.9).
- Pins and circuits: PCM connector pin 71B brake switch, under 1 V released, above 11 V pressed (S2223000047); IBS connector pin 2 above 11.8 V (S1408000384); fuse F82 rear PDC, BCM circuit A901, Stelvio (S1808000005); inline connector XY201 and grounds G003A, G003B (S2008000032).
- Misfire cold-start test: 90 seconds, coolant within 5 F of ambient, counts per cylinder (S2018000014).
- Tyre test: circumferences within 1/8 inch, pressures to door placard (S1821000001).

**Data items named** (for `live-ecm` and the live list): per-cylinder misfire counts, Battery Charge Status (ECM), PCM Generic Fail Status and Current Fail Status, PCM ESS Inhibits List (S2008000021 warns the Driver Door inhibit is a false display on some wiTECH versions; check BCM door state), RFHM tyre sensor IDs.

## 5. What applies to the reference car ZASFAKPN5J7B88115 (2018 Stelvio 2.0T, built 09/2017)

**Applies by model, year and engine (no build limit): 18-103-19 and its successor 18-026-20; CSN W05.** The first is the ECM flash for this car; its DTC list does not contain P0440, P0455 or P0456 (it holds P1CEA and P24D6, the EVAP pressure sensor family). So the old assumption that 18-030-17 is the EVAP calibration fix should stay marked unconfirmed: that bulletin and its 18-097/027 successors are Giulia only. Ask the dealer for ECM calibration history, and whether UA4 (18V636, ECM software) and W05 were done on this VIN.

**Apply if the sales code or build matches (vin_check):**
- 08-044-19 (ABS flash, up to three steps) if the car was built on or before 2018-03-13 and has no ACC with Stop (NH3). Built 09/2017 is inside the window.
- 08-029-20 radio flash if the car has the RAN, RAP or RSD 8.8 radio (scope: built on or before 2018-01-11, so 09/2017 qualifies). 08-081-19 starts at 2017-10-30 builds, so it does not.
- 01-001-20 oil monitor (2018-2019 2.0L 280HP).
- 18-089-19 (SLVT mandatory for P0456, scope 2015-2020 all FCA gas) and 18-048-23 (its successor). S2125000002 (EVAP mid-point quick connect) and 18-039-20 (winter-blend fuel) apply by engine and period.
- Recalls 17V823 (T84), 18V147 (U24), 18V203, 18V205, 18V636 (UA4), 19V148 (V27), 19V551 (V84), 24V510, 25V586 by VIN.

**By code, this car's EVAP codes (P0440, P0455, P0456):**
- Every bulletin that lists all three is Giulia only (18-030-17 chain, 18-097-19, 18-027-20).
- Stelvio-relevant text: 18-089-19 (SLVT), S2125000002 (quick connect), and S2008000163 (ESIM connector D2812A; NHTSA lists Giulia 2020 only). Since the evap parts were already replaced twice with clean smoke tests, S2008000163 and S2125000002 are the cheap remaining checks: re-seat D2812A and the mid-point quick connect, then run the SLVT to prove it.
- S2125000003 (P1CEA ejector tee) is the neighbouring boost-side purge path; this car has no P1CEA on record.

**By code, other reference codes:**
- **B10AA**: only 08-064-17 (Giulia 2017 amplifier, B10AA-4A). Code description match only; not this car's build window.
- **U1736, B1040, B1176, B101D, C104B**: no bulletin on NHTSA names them. Useful neighbours for a communication cascade: S1808000005 (BCM feeds, fuse F82), S2008000032 (connector XY201, grounds G003A/B), S1708000262 (ECM LIN terminals, U1008), S1408000384 (IBS, U113E).
- **The shudder**: S1821000001 (tyre circumference on AWD; the only bulletin with the word), S2018000014 (90 s cold-start misfire counts, injectors; lists 2019-2020), S2018000011 and S2018000008 (post-flash misfire and surge notes), S2218000018 (coolant in cylinders). If W05 was done, S2018000011 says re-flash when P0299 or P0300-P0304 follow. None is a confirmed match for this car; they give tests with numbers.

## 6. What it means for the parity board

- `proxi-alignment`, `throttle-relearn`, `oil-change-reset`, `ibs-battery-read`, `battery-type`, `security-access`, `key-remote-learning`, `steering-angle`, `tpms-reset`, `act-evap`: the table in section 4 gives each a manufacturer-sourced name, menu path, order and precondition to cite. Per the 2026-10-27 rule none of this is a write definition; it is the citation a definition needs.
- `web-write-lock`: the shared preconditions (13.2 to 13.5 V, uninterrupted link, clear DTCs afterwards, S2018000011 re-flash note) are the lock's checklist.
- `live-ecm` and `dtc-counters-19-06`: per-cylinder misfire counts and Battery Charge Status are named data; they are what the Next-MES-session misfire work should read.
- `tsb-xref`: add the proposed rows; 44 of them, 14 flagged `update` on existing ids and 30 new.
- Still unpublished on NHTSA: UDS addresses, routine IDs, DIDs, Mode 06, security algorithms. Those stay on the Stellantis technical-access list in MES_PARITY_PLAN section 1.
