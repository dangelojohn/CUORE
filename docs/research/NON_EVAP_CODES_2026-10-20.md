# Non-EVAP codes on the reference car, 2026-10-20

Review of every DTC that is not an EVAP code, from the MES logs and CUORE's store, with an all-systems inventory. The car is the 2018 Alfa Romeo Stelvio 2.0T Q4 in the CUORE store (VIN not repeated here). Companion job in the job ledger: "Network and chassis codes (non-EVAP)" (id bb4ebb961aee), one hypothesis per group, priority order brakes, network, ADAS camera, RFHUB, window.

How to read this document:

- **[E]** a reading from a log or the store (file, date, value).
- **[I]** inference from readings; the reasoning is shown and it can be wrong.
- **[O]** OUTSIDE LITERATURE: a bulletin, forum thread or web page about other cars or model years. It never counts as a reading of this car.
- Times are the clock stamped in each file (local). MES file names are `YYMMDDHHMM`.
- Nothing here recommends clearing a code as a fix. A clear erases the status bytes and freeze frames and proves nothing; CUORE's 2026-10-14 19:02 read was clean 10 hours after a clear and the codes were back by 10-19.

## 1. Sources and exclusions

- MES `SCAN_*.txt` read with the `mes.scan` parser (`mes-log-mcp/mes/scan.py`), VIN match, all dates: 18 genuine scans of the car from 2026-06-07 to 2026-10-19, plus one aborted attempt (SCAN_2608271112, adapter not connected, no module reached). SCAN logs carry no simulation marker, so their provenance is "unverifiable" by design [E: `ScanLog.provenance`].
- MES `FESLog_*.txt` read with `mes.fes`, real (not SIMULATION MODE) and VIN-matched only. Excluded: every log marked simulation (2026-06-06 12:01, 2026-09-02 14:42, 2026-09-25 19:56, 2026-10-20 06:20 to 06:24, and the October 2025 to November 2025 practice logs), and SCAN_2511151053/1116/1208 plus the November 2025 FES logs, which carry a Fiat 500L VIN, not this car.
- CUORE store (`C:\ProgramData\cuore\observations.jsonl`, kinds `module_dtcs`, `dtc_detail`): UDS sweeps of ECM, TCM, BCM, IPC, RFHUB on 2026-10-13 20:24, 10-14 19:02, 10-19 00:23 and 00:30 (the 10-14 and 10-19 00:23 sweeps are stored twice), one ABS attempt on 10-15 00:12, one ECM read on 09-25 20:12. Adapter contact days from the audit log: 09-14, 09-15, 09-25/26, 10-13 (16:35 to 20:53), 10-14 (19:01 to 23:55), 10-15 (00:07 to 00:42), 10-19 (00:23 to 00:34).
- ECM entries with status 0x40 in CUORE's lists are "supported, test not completed", not recorded codes; only non-0x40 statuses count as codes.

## 2. Every non-EVAP code since 2026-06-01 (readings)

"Scans" counts MES SCAN files whose first (scan) phase listed the code. "Cleared" counts the same files in which MES then reported a clear on that module (SUCCESS / FAILED / no clear that session).

| Module | Code (text MES printed) | Scans | First | Last | Cleared | CUORE status byte | Freeze frame |
|---|---|---|---|---|---|---|---|
| BCM | U1713-2F Engine control (NCM) signal/message erratic | 10 | 06-07 | 10-19 | 8 / 0 / 2 | 0x0F on 10-13 20:24, 10-19 00:23 and 00:30 (failing this cycle; no lamp request) | undecoded raw on 10-13 and 10-19 (see 4.2) |
| BCM | U1712-2F Brake system (NFR) erratic | 6 | 06-07 | 09-25 | 5 / 0 / 1 | not read while present | none |
| BCM | U1711-2F Brake system (NFR) erratic | 6 | 06-07 | 09-25 | 5 / 0 / 1 | as above | none |
| BCM | U1716-2F Electric Steering (NGE) erratic | 1 | 08-27 | 08-27 | 1 / 0 / 0 | none | none |
| BCM | U1765-86 Lost communication with RF Hub, signal invalid | 2 | 09-15 | 10-14 | 2 / 0 / 0 | 0x08 on 10-13 20:24 | none |
| BCM | U1736-87 ETM missing message | 1 | 10-14 | 10-14 | 1 / 0 / 0 | 0x08 on 10-13 20:24 | none |
| BCM | B1176-97 Rear left window riser obstructed/blocked | 9 | 08-27 | 10-14 | 7 / 0 / 2 | 0x08 on 10-13 20:24 | none |
| BCM | B10AA-4A PROXI configuration control, incorrect component installed | 1 | 10-14 | 10-14 | 1 / 0 / 0 | 0x08 on 10-13 20:24 | none |
| IPC | U1736-86 and U1736-87 ETM signal invalid / missing | 1 | 10-14 | 10-14 | 1 / 0 / 0 | 0x0C (pending+confirmed) both, 10-13 20:24 | none |
| IPC | B1029-64 Lost communication with Steering module (SCM) plausibility | 1 | 08-27 | 08-27 | 1 / 0 / 0 | none | none |
| IPC | B102E-64 Communication with BCM plausibility | 1 | 08-27 | 08-27 | 1 / 0 / 0 | none | none |
| RFHUB | B1040-64 Communication with BCM plausibility | 6 | 06-07 | 10-14 | 6 / 0 / 0 | 0x08 on 10-13 20:24 | none |
| RFHUB | U2054-87 BCM missing message | 2 | 08-27 | 10-14 | 2 / 0 / 0 | not in the 10-13 20:24 list | none |
| DTCM | U0100-87 No communication with ECU, missing message | 7 | 08-27 | 10-19 | 6 / 0 / 1 | module not read by CUORE | none |
| DTCM | U0422-86 Communication with BCM, signal invalid | 1 | 10-19 | 10-19 | 1 / 0 / 0 | not read by CUORE | none |
| DASM | C141C-86 Private CAN between HALF and DASM, signal invalid | 7 | 06-07 | 10-19 | 5 / 1 / 1 | not read by CUORE | none |
| DASM | C141B-97 Camera blinded/obstructed/blocked | 8 | 09-02 | 10-19 | 5 / 1 / 2 | not read by CUORE | none |
| DASM | C1408-86 ESP control, signal invalid | 3 | 08-27 | 10-19 | 2 / 1 / 0 | not read by CUORE | none |
| DASM | C1403-86 EPS signal invalid; C1431-86 Lateral accel/YAW signal invalid | 1 | 08-27 | 08-27 | 1 / 0 / 0 | not read by CUORE | none |
| DASM | U1701-86 Communication with ECU, signal invalid | 1 | 06-07 | 06-07 | 1 / 0 / 0 | not read by CUORE | none |
| DASM | U1702-87 EPS missing message | 1 | 10-19 | 10-19 | 1 / 0 / 0 | not read by CUORE | none |
| EPS | U1960-83 Communication with ECU, protection value incorrect | 1 | 09-04 | 09-04 | 0 / 0 / 1 | not reachable | none |
| AFLS | U0428-86 Steering angle sensor signal invalid | 1 | 09-04 | 09-04 | 0 / 0 / 1 | not reachable | none |
| HALF | U0418-86 Communication with ABS, signal invalid | 1 | 09-04 | 09-04 | 0 / 0 / 1 | not reachable | none |
| ABS | C104B-92 Leaks in hydraulic group (FES) | 1 FES | 09-04 20:01 | 09-04 20:01 | cleared by FES 20:01 | ABS silent to CUORE 10-15 00:12 | yes, see 3.1 |
| ABS | U1700-87 Body computer (FES) | 1 FES | 09-04 20:01 | 09-04 20:01 | cleared by FES 20:01 | as above | yes, see 3.1 |

Dates are 2026. First and Last are MES scan dates (SCAN files, or FES for the ABS); CUORE reads are in the status column. Every code above was listed on the dates in section 6 (per module) and in the job's evidence. The five-code ECM list of 2025-09-24 (P1189, P00F5, P0098, P105E; non-EVAP) is in section 3.7 because it predates June.

One structural oddity [E]: in SCAN_2606070954 and SCAN_2610080920 the report scan that follows the first "CLEARING STORED FAULT CODES" block lists the same codes again, then a second clear runs; the 10-08 re-scan at 09:26 was clean. Either MES prints the pre-clear list in the report or the codes returned within seconds; the files do not say which.

## 3. Interpretation by group

### 3.1 BRAKES: C104B-92, U1700-87 (ABS), and the ABS/ESP-named codes elsewhere

**Readings [E].** FESLog_2609042001 (2026-09-04 20:01:10, Continental ABS MK C1):

- C104B-92 "Leaks in hydraulic group": operating time 330849 min (the module's own clock read 330865 at the read, so about 16 key-on minutes earlier), startups 14356, dynamic selector Dynamic, brake pedal switch ON, brake contact 2 ON, parking brake released, speed 0, battery 12.1 V, hydraulic circuit pressure 11.1 bar, brake pedal pressure 3.6 bar, mode Normal.
- U1700-87 "Body computer (BCM/NBC)": operating time 329228 min, startups 14280, selector Normal, pedal OFF, battery 10.6 V, hydraulic circuit 2.6 bar, pedal pressure 0.0 bar, speed 0.
- The session then ran "CLEARING STORED FAULT CODES"; the re-reads in that file are clean. A second ABS FES at 20:08:34 and the chassis sweep SCAN_2609042008 (20:08) show the ABS with no codes. Those are the only ABS DTC reads that ever succeeded, all within 8 minutes.
- CUORE found the ABS on CAN-CH at 29-bit address 0x2A (identity DIDs matched this car, discovery 2026-10-15 00:08 to 00:10) but the DTC sweep at 00:12 got no reply; the stored empty list is silence, not "no codes" (docs/sessions/2026-10-15-chassis-bus-discoveries.md section 4).
- Codes elsewhere that name the brake/ESP side: BCM U1711-2F and U1712-2F ("Brake system (NFR) signal erratic", 06-07 to 09-25, absent in every later BCM read); DASM C1408-86 "ESP control signal invalid" (08-27, 09-04, 10-19); HALF U0418-86 "communication with ABS invalid" (09-04 20:08); AFLS U0428-86 "steering angle sensor invalid" and EPS U1960-83 (both 09-04 20:08).

**Inference [I].** The startup counter looks shared across modules (ABS 14359 at 20:01 against the ECM's 14357 at 19:53 that evening). Reading it that way:

- C104B-92 was set in the key cycle just before the evening's MES session, with the car stationary, engine off (12.1 V) and the pedal pressed. That fits an ignition cycle during the diagnostic session as well as a leak; the readings cannot choose.
- U1700-87 was set at startups 14280, one count before the ECM stored P0455 on 2026-08-27 (14281, FESLog_2608271119) with the battery at 10.6 V: a low-voltage moment around that day's engine start. This is a supply-side observation, not a brake one.

**Real or artefact?** Neither is established. Not an artefact by the incident rule (it predates 10-14). Possible bystander of the 09-04 ignition cycling. It cannot be called a real leak, because no fluid-level, wetness or pedal reading exists anywhere in the store, and no read of the ABS has succeeded since the clear. The 11.1 bar / 3.6 bar pair has no reference value in this repo. Because it is a brake-safety code with a "leak" name, the cheapest check is free and should be done before anything else (section 5, task 2). This is the only group where a physical check outranks a tool read.

**[O]** The catalogue (cuore/data/tsb_catalogue.json) lists recall 17V823 (contaminated brake fluid, 2018 Giulia/Stelvio, `vin_check`: run the VIN on NHTSA/Transport Canada) and TSB 08-044-19 (ABS module flash, "improved brake pedal feel"; title only, the PDF was not opened). Neither names C104B. A web search on 2026-10-20 for "C104B-92" found no document; the one ABS hydraulic result was recall 21V309 (2019 to 2021 ABS HCU rotor weld, not a fluid leak, not this model year). The repo already carries a C104B tree that leads with fluid level and a hydraulic leak look (mes/faulttree.py, mechanic_tests `brake_hydraulic_pressure_bleed`).

**Resolution criteria.** Fixed/cleared as a concern only if all hold: reservoir at MAX with no wetness found, a firm pedal that does not sink under 30 s of steady pressure with the engine running, and two ABS DTC reads at least 14 days apart, neither taken within hours of a clear, listing no C104B. One clean read proves nothing (the 09-04 20:08 read was clean seven minutes after the clear). If the fluid is low, wet, or the pedal sinks: stop and have it inspected; that would make it a real hydraulic fault.

**ESP-named receiver codes** (C1408-86, U0418-86, U0428-86, U1960-83, U1711/U1712): treated in 3.2 and 3.3; they are text about received signals, not hydraulic evidence.

### 3.2 Network and plausibility group: U1713, U1711, U1712, U1716, U1736, U1765, U2054, U0100, U0422, U1701, U1702, B1029, B102E

U1713-2F is also referenced by the EVAP job's input hypothesis 8c659dfc (ECM inputs reaching the monitor invalid); the network side is tracked in the new job and does not replace it.

**Meaning [E/O].** MES prints for U1713-2F "Engine control (NCM) signal/message erratic": the BCM says messages it receives from the ECM are erratic (direction ECM to BCM); FTB 2F is "signal erratic", not "lost" (a lost message is FTB 87). mes/dtc_descriptions.py previously called it a "lost-communication" code; the entry was corrected today. The cascade tree in mes/faulttree.py (NETWORK_CASCADE) groups it with U1711/U1712/U1716/U2054/U0100/B1040 as one network event reported by many receivers. [O] A Stelvio owner thread (stelvioforum.com thread 24275, link-verified 2026-10-07, listed in mes/experience.py) traced a C1408-86 / C141C-86 / U0102 cascade to a low 12 V battery.

**Readings and artefact reasoning.**

- **U1713-2F.** Listed on 10 MES scans. After the BCM clears of 06-07, 08-27, 09-04, 09-15 and 09-25 it was back at the next read (81, 6, 11, 10 and 3 days later); after the 09-28 and 09-29 clears it was absent on 09-29, 10-04 and 10-08 and present again by 10-13, at most 14 days after the 09-29 clear [E]. It was absent from CUORE's 10-14 19:02 read, 10 hours and 9 km after the 08:59 clear [E]. It is present with status 0x0F (failing this cycle) at 10-13 20:24 and 10-19 00:23 and 00:30, and its two freeze frames carry startup counts 14583 (10-13) and 14616 (10-19) [E]; [I] those counts sit within a few starts of the CUORE session of each day. It may be set during sessions as often as during driving; the readings cannot separate the two. Verdict: **recurring; cause unknown; possible bystander at least in part.**
- **U1711/U1712-2F.** Six scans 06-07 to 09-25, then absent in every later BCM read (08 MES scans and CUORE's four sweeps) [E]. Looks like it stopped, not like it was cleared away. Verdict: **no current evidence; no action.**
- **U1716-2F (08-27), B1029-64 and B102E-64 (IPC, 08-27), C1403-86 and C1431-86 (DASM, 08-27):** all seen only in SCAN_2608271131, the first read after 81 days, a burst of 14 codes in five modules, and never again, including after later IPC and BCM reads [E]. Verdict: **single burst; no action; watch only.**
- **U1765-86 (BCM, 09-15 and 10-14), U1736-87 (BCM) and U1736-86/-87 (IPC), B10AA-4A (BCM):** first read as history. CUORE 10-13 20:24 shows U1765, U1736-87 (BCM) and B10AA with status 0x08 (confirmed, not failing now) and IPC U1736 with 0x0C [E]. No adapter contact is on record from the 10-08 09:26 clean scan until the 10-13 16:35 CUORE session (audit log; one UI-only event on 10-07) [E]. [I] If "confirmed but not failing this cycle" means they failed in an earlier key cycle, they were stored in normal use between 10-08 and 10-13, not by a tool. That inference leans on bit semantics and on a CUORE session already being 4 hours old at 20:24, so it is a lean, not a proof. All four were absent on 10-19 after the 10-14 clear.
- **B10AA-4A with U1736 (ETM missing).** MES text: PROXI configuration "incorrect component installed" [O: dtcdecode.com, single source, in dtc_descriptions.py]. [I] Both together fit "the configured ETM/telematics unit was not found on the bus". The open owner question is whether anything was done to the head unit, antenna, telematics module or a dashcam between 10-08 and 10-13. The ETM itself has never been read.
- **U2054-87 (RFHUB).** 08-27, and 10-14 08:59, but not in CUORE's RFHUB list at 10-13 20:24 [E]; it appeared between 20:24 on 10-13 and 08:59 on 10-14, after the live session that evening. [I] Possible bystander of the 10-13 20:24 to 20:53 live probing, or overnight.
- **U0100-87 (DTCM, 7 scans 08-27 to 10-19).** The repo's own drivetrain table calls it a bystander of whole-vehicle serial UDS sweeps [E: mes/drivetrain_specs.py]. The Q4 DTCM was never read by CUORE. Verdict: **no action unless transfer-case symptoms exist.**
- **U1701-86 (DASM, 06-07 10:03).** Absent at 09:54 the same morning after a clear, present nine minutes later during MES sessions on other modules (FES of the body computer 09:55, transfer case 09:56) [E]. **Possible bystander; seen once; no action.**
- **U1702-87 (DASM) and U0422-86 (DTCM), both first seen 2026-10-19 00:39.** Their first-seen window runs from the 10-14 08:59 clear (DASM and DTCM were both cleared) to the 10-19 00:39 read, with no read of either module in between, and it contains the 2026-10-14 23:58 to 00:00 wrong-bitrate listen on CAN-CH (CAN ERROR on the adapter, chime and airbag lamp) and the CUORE guided scan 10-15 00:07 to 00:42 with 3E 00 and discovery probes on CAN-CH and CAN-IHS [E: notes 82b3090e1a85 and 5f28a6ea588f]. Both name the steering or body-computer link, the kind of lost-communication code the 10-15 note predicted. **PROBABLE TOOL ARTEFACT.** The bus the DTCM sits on is not established, so U0422's link to CAN-CH is an inference.

**Resolution criteria (group).** No U17xx, U0xxx or B1040 on three reads over at least 21 days (longer than the longest clear-to-return seen, 14 days for U1713 after the 09-29 clear), including at least one read taken under the conditions that previously showed them (engine running, tool on the port), with CUORE status bytes read before any clear and U1713 showing neither 0x08 nor 0x0F. A read within hours of a clear does not count.

### 3.3 Chassis ADAS group: C141B, C141C, C1408, C1403, C1431 (DASM) and EPS U1960, AFLS U0428, HALF U0418

**Readings [E].** DASM was read on 18 MES scans. C141C-86: 06-07 09:54, 08-27, 09-04, 09-15, 09-25 (twice), 10-19. C141B-97: 09-02, 09-04, 09-25 (twice), 09-28, 10-08, 10-14, 10-19; absent 09-15, 09-29, 10-04. C1408-86: 08-27, 09-04, 10-19. The 09-04 19:53 DASM clear FAILED, so C1408-86 and C141C-86 were not erased that evening. DASM was never read by CUORE (no status byte, no freeze frame). The 09-04 20:08 chassis sweep read EPS, ORC, AFLS, PAM, HALF and ABS once, immediately after the evening's ignition cycling and cable change, and stored U1960-83 (EPS), U0428-86 (AFLS), U0418-86 (HALF); ORC, PAM and the post-clear ABS were clean. None of these three modules has been read since.

**Interpretation.** [I] C1408, C1403, C1431, U1702, U0418, U0428 and U1960 are receivers saying a signal from the ESP, EPS or steering-angle sensor was invalid or missing; they say nothing about hydraulics or the steering rack. C141C ("private CAN between HALF and DASM") is a link between two driver-assist modules. C141B-97 is different: its text is about the camera's view and it is the most persistent single DASM code (8 reads), with no network explanation in its wording.

**[O]** FCA bulletin 08-045-20 (NHTSA document MC-10175724-9999, April 2020, opened and read 2026-10-20) lists C141C-86 "Video Camera Private Can Communication Failure, Signal Invalid" with B1006-49 and C1999-86 and an EVIC "Forward Collision Warning limited functionality, front camera service required" message for 2020 Giulia and Stelvio built on or before 2019-12-20 (GU: 1220XX); the repair is BCM Restore Vehicle Configuration then Proxi Configuration Alignment, check the codes after 10 to 15 minutes of sleep. Model year 2020, so it does not name this 2018 car, and no record of this car shows that EVIC message. Context only; do not apply it blindly. Searches on 2026-10-20 found no document naming C141B or C1408.

**Real or artefact?** C141B-97: possible real condition at the camera's view or a persistent bystander; undecided (it absent on a few reads, which a real obstruction usually would not be). C141C-86, C1408-86: recurring, unexplained, text points at signal receipt; the 10-19 occurrences fall in the incident window but both existed before it, so that occurrence cannot be blamed on it. U1702-87: probable tool artefact (3.2). U0418/U0428/U1960: single read at 09-04 20:08, first-ever read of those modules; possible bystanders of that evening's cable change.

**Resolution criteria.** C141B: the glass in front of the camera cleaned, then absent on at least two scans over at least 21 days that include one daylight drive; if it persists on clean glass, it is not a dirt problem. Network-type codes: as 3.2. DASM, HALF, EPS, AFLS re-read at least once by MES on a quiet day (none has been read since 09-04 for the chassis modules).

### 3.4 Body: B1176-97 rear left window riser

**Readings [E].** BCM scans 08-27, 09-02, 09-04, 09-15, 09-25 (twice), 09-28, 09-29, 10-14 (9 scans); CUORE 0x08 on 10-13 20:24. After each BCM clear from 08-27 to 09-29 it returned after 6, 11, 10, 3, 1 and 14 days. It was absent on 10-04 and 10-08 (5 and 9 days after the 09-29 clear), on CUORE 10-14 19:02, and on 10-19 (5 days after the 10-14 clear). No freeze frame, no window symptom on record.

**Interpretation.** [I] FTB 97 "obstructed or blocked" is typical of an anti-pinch or travel-resistance event at that window: glass-run friction, a tucked-in seal, debris, regulator drag. It is the one BCM code that reads as a local physical item rather than network text, and it has no network pattern (not tied to scan days). A web search on 2026-10-20 found no document for B1176 on this car [O: none found]. Verdict: **real local condition likely; low urgency; unconfirmed.**

**Resolution criteria.** Window runs full down and up both ways smoothly several times (one-touch and held), no slow travel, stop or reversal, and B1176 absent on two reads at least 14 days apart. A one-off absence after a clear (as 10-19) is not enough.

### 3.5 Keyless: RFHUB B1040-64 and U2054-87

**Readings [E].** B1040-64: 06-07 10:03 (absent at 09:54 the same morning), 08-27, 09-25 20:27, 09-28, 10-08, 10-14 08:59; CUORE 0x08 on 10-13 20:24. After the 08-27 clear it was absent on 09-02, 09-04, 09-15 and 09-25 19:56 (29 days) and appeared at 20:27 that evening, during ignition cycling and live-link sessions. U2054-87: 08-27, 10-14. Clean in CUORE 10-14 19:02, and in CUORE plus MES on 10-19.

**Interpretation.** [I] Receiver-side plausibility about the BCM link; two first appearances (06-07 10:03, 09-25 20:27) fall inside tool sessions; no key, start or keyless-entry symptom is on record (no record is not a negative test). No document naming B1040 or U2054 for this car was found (2026-10-20) [O]. Verdict: **possible bystander; watch; no action.**

**Resolution criteria.** Absent on three reads over at least 21 days; escalate only if it is active (0x0F) on a quiet read or a key or start symptom appears.

### 3.6 Infotainment and configuration: U1736 (ETM), B10AA-4A

See 3.2. ETM/AlfaConnect is not in any MES module list for this car; the only evidence is the BCM and IPC codes of 10-13/10-14. Resolution: both absent on three reads over at least 21 days; ask the owner about head-unit, antenna or telematics work before 10-13.

### 3.7 Powertrain non-EVAP: 2025-09-24 ECM sensor codes

**Readings [E].** FESLog_2509241345 (first log of the car, 2025-09-24, 114,117 km): P1189-00 "Intake pressure sensor", P00F5-00 "Humidity sensor", P0098-00 "Air temperature sensor", P105E-00 "Humidity sensor", all stored, all with a freeze frame at operating time 250617 min and startups 12712, which equals the session's own clock. Engine 0 rpm, battery 12.1 V (12.0 on P105E), intake pressure 985 mbar. No later ECM read lists them: FES 2025-10-14 (two sessions, none), every ECM scan and FES in 2026, and CUORE's four sweeps. No MES clear is recorded between.

**Interpretation.** [I] Four sensor-circuit codes frozen at the same key-on moment, engine off, 12.1 V, with the session's own clock as the set time: the pattern of codes stored at connection or key-on, not of a driven fault. Never seen again in 13 months. **Possible bystander; no action.** (P0456, the fifth code in that file, is EVAP.)

### 3.8 ECM, TCM, ESM, IPC, BCM: nothing else

TCM and ESM (gear-shift module) were clean on all 18 scans and on all four CUORE sweeps (no status other than 0x40). ECM carries only P0440, P0455, P0456 in 2026 (job 76d3454bce75). Nothing further in these modules.

## 4. Freeze frames and status bytes on record

### 4.1 Status bytes (CUORE UDS, ISO 14229 bits) [E]

0x0F = test failed, failed this operation cycle, pending, confirmed (active now, no lamp request). 0x08 = confirmed only (stored history, not failing now). 0x0C = pending + confirmed (failed last cycle). Only BCM U1713-2F carried 0x0F; the IPC U1736 pair 0x0C; everything else 0x08. DASM, DTCM, EPS, HALF, AFLS, ORC, ABS have no status byte on record (CUORE never read them).

### 4.2 BCM U1713-2F snapshots [E]

Stored as raw undecoded bytes on 2026-10-13 20:28:23 and 2026-10-19 00:25:39 (the store pre-dates the decoder's BCM layout). By hand with the current layout (cuore/live/dtc_detail.py): operating time 245380 min then 245986 min (606 min apart over 5.2 days, about 117 min a day, like the ECM's rate), startups 14583 then 14616, DID 0x1002 = 0x00 then 0x05, DID 0x1004 = 0x8901 then 0x9101 (meaning not established), DID 0x3700 = 0x0A both. Extended record 1 = 0x60 on both; the "occurrence counter" label is an unverified guess. No physical value (voltage, speed) is decoded; do not treat these as freeze-frame evidence.

### 4.3 ABS freeze frames: section 3.1.

## 5. Recommended tasks, cheapest first, read-only first

None of these clears a code. Each says what reading would settle it.

1. **Ask the owner (free).** Airbag or other warning lamps lit since the 10-14 23:58 incident? Any forward-collision or driver-assist message, ever? Pedal feel, ABS/ESP lamp, brake service? Rear-left window symptoms? Keyless or start problems? Battery work, jump start, aftermarket electrical (dashcam, tracker), head-unit or telematics work, engine bay washed, windshield replaced? (CUORE's open owner questions on the network codes are all unanswered.)
2. **Brake fluid and a look (free, 5 min, no tool).** Reservoir level and colour against MIN/MAX, photograph and mark it with the date; look at each wheel, caliper, hose and under the ABS block for wetness; with the engine running press the pedal steadily for 30 s. Anything wet, low or sinking: stop and have it inspected. (The existing how-to "brake fluid flush Stelvio", `brake_fluid` in mes/experience.py, link-verified 2026-10-07, is a service procedure, not a diagnosis; use it only if a bleed or fluid change is indicated.)
3. **Two free physical checks.** Rear-left window full travel both ways, one-touch and held, listening; glass run and seal. Clean the glass in front of the camera, check for film, stickers, chips, a dashcam mount.
4. **Multimeter (cheap).** Battery at rest after 12 h, during cranking and running; terminals. Typical rule of thumb (not a Stelvio spec): about 12.4 V or less at rest is a weak battery, a cranking dip below about 9.6 V is poor, charging outside roughly 13.8 to 14.8 V is suspect.
5. **Visual and online VIN checks (free).** BCM and A-pillar connector area for moisture (recall 18V205), fuse F82, grounds G003A/B and XY201 per the network-cascade tree; recall status by VIN for 18V205, 19V551 (BCM fuel level software), 17V823 (brake fluid) on NHTSA and Transport Canada (the catalogue marks them `vin_check`, not verified).
6. **Read-only tool read of the modules CUORE cannot reach.** MES chassis sweep (the 09-04 20:08 set: ABS, EPS, ORC, AFLS, PAM, HALF) plus an ABS FES read, saved with freeze frames before any clear. Rules: only on the confirmed bitrate of each bus, never a raw script on COM3 (RULES.md rule 4). The ORC has not been read since the airbag lamp lit on 10-14; this read answers that too.
7. **One quiet read.** After at least 3 tool-free days, engine running, one MES SCAN with CUORE's UDS status bytes and DTC extended data captured before any clear. This is the test that separates "stored by the car" from "stored by the session": codes present on a quiet read are the car's; codes that only appear on session days are bystanders.
8. **Option, outside this repo:** a dealer wiTECH look at the DASM/HALF/BCM configuration, only if C141B or C141C persist on a quiet read with a driver-assist message, or if a brake finding appears. Cost and availability not assessed here.

## 6. All systems inventory

Included: MES SCAN logs of this VIN from the first (2026-06-07), real FES logs of this VIN from the first (2025-09-24), CUORE store reads. Simulation logs and the Fiat 500L logs are excluded (section 1). "Clean" means no code listed, which proves nothing about history that was cleared earlier.

The eight modules MES finds on CAN-C (ECM, IPC, TCM, DTCM, ESM, BCM, RFHUB, DASM) were all read on the same 18 MES scans: 2026-06-07 09:54, 10:03; 08-27 11:31, 11:36, 11:41; 09-02 14:45; 09-04 19:53; 09-15 20:48; 09-25 19:56, 20:27; 09-28 11:59; 09-29 10:46; 10-04 11:13, 11:15; 10-08 09:20, 09:26; 10-14 08:59; 10-19 00:39 (08-27 11:12 aborted, no module reached). CUORE read ECM, TCM, BCM, IPC and RFHUB on 10-13 20:24, 10-14 19:02, 10-19 00:23 and 00:30.

### Brakes (highlighted)

| Module | Reads | Codes (first / last seen, sessions) | Last status | Notes |
|---|---|---|---|---|
| ABS/ESP Continental MK C1 (ISO 00 06 50 5B 14, CAN-CH 0x2A) | MES FES 2026-09-04 20:01, SCAN 20:08, FES 20:08:34. CUORE: identity 10-15 00:08 to 00:10, DTC sweep 10-15 00:12 silent | C104B-92 (09-04 / 09-04, 1 FES); U1700-87 (09-04 / 09-04, 1 FES) | cleared in FES 09-04 20:01; clean at 20:08 and 20:08:34; no status byte ever | **Freeze frames in 3.1.** CUORE has never read an ABS DTC. The ABS has not been read since 2026-09-04 |
| Brake codes in other modules | see sections 2, 3.1 | BCM U1711/U1712-2F (06-07 / 09-25, 6 scans each); DASM C1408-86 (08-27 / 10-19, 3 scans); HALF U0418-86 (09-04, 1) | last BCM read without them 10-19 | receiver-side text about ABS/ESP signals |
| Separate EPB, brake booster or ESC module | never listed by MES or CUORE | none | n/a | **Never read / not reachable.** The ABS/ESP functions are presumably in the MK C1 module [I]; the ECM shows "Brake booster vacuum switch" only as a live parameter (Open), no code |

### Steering, restraints, ADAS, lighting

| Module | Reads | Codes (first / last seen, sessions) | Last status | Notes |
|---|---|---|---|---|
| EPS ZF (ISO 00 02 40 5F 14) | MES SCAN 09-04 20:08 only | U1960-83 (09-04 / 09-04, 1) | stored, not cleared, never re-read | not reachable by CUORE (address unconfirmed; 11-bit discovery not run on the car) |
| ORC airbag (ISO 00 1A 70 84 15, MES name "UNKNOWN/UNSUPPORTED") | MES SCAN 09-04 20:08 only | none | clean on 09-04 | **not read since the 10-14 airbag lamp incident**; not reachable by CUORE |
| DASM radar/driver-assist Bosch | 18 MES scans | C141C-86 (06-07 / 10-19, 7); C141B-97 (09-02 / 10-19, 8); C1408-86 (08-27 / 10-19, 3); C1403-86, C1431-86 (08-27, 1 each); U1701-86 (06-07, 1); U1702-87 (10-19, 1) | 10-19 00:39: C1408, C141B, U1702, C141C stored, then cleared by MES (DASM clear SUCCESS) | CUORE never read it |
| HALF lane-feedback camera | SCAN 09-04 20:08 only | U0418-86 (09-04, 1) | stored, never re-read | not reachable by CUORE |
| AFLS adaptive headlamps | SCAN 09-04 20:08 only | U0428-86 (09-04, 1) | stored, never re-read | not reachable |
| PAM parking sensors | SCAN 09-04 20:08 only | none | clean | not reachable |

### Powertrain and transmission

| Module | Reads | Codes (first / last seen, sessions) | Last status | Notes |
|---|---|---|---|---|
| ECM IAW 10JA | 18 MES scans, FES from 2025-09-24, 4 CUORE sweeps | non-EVAP: P1189, P00F5, P0098, P105E (2025-09-24, 1 FES, section 3.7); EVAP codes are in job 76d3454bce75 | non-EVAP absent since 2025-10-14 | CUORE: only P0440/P0455/P0456 have a status other than 0x40 |
| TCM ZF 8HP | 18 MES, 4 CUORE | none | clean | |
| ESM gear-shift module | 18 MES | none | clean | CUORE did not read it |
| DTCM Magna Q4 | 18 MES | U0100-87 (08-27 / 10-19, 7); U0422-86 (10-19, 1) | stored 10-19 00:39 then cleared (SUCCESS) | CUORE did not read it |

### Body, network, keyless, instruments, infotainment, climate

| Module | Reads | Codes (first / last seen, sessions) | Last status | Notes |
|---|---|---|---|---|
| BCM Marelli 949 | 18 MES, 4 CUORE | U1713-2F (06-07 / 10-19, 10); U1712-2F, U1711-2F (06-07 / 09-25, 6); U1716-2F (08-27, 1); U1765-86 (09-15 / 10-14, 2); U1736-87 (10-14, 1); B1176-97 (08-27 / 10-14, 9); B10AA-4A (10-14, 1) | 10-19 00:30 CUORE: U1713-2F 0x0F active, nothing else; cleared at 00:39 | doors and windows are read through the BCM: no separate door or window module has ever been listed |
| IPC Continental | 18 MES, 4 CUORE | B1029-64, B102E-64 (08-27, 1); U1736-86, U1736-87 (10-14, 1) | clean on 10-19 | |
| RFHUB Continental (keyless) | 18 MES, 4 CUORE | B1040-64 (06-07 / 10-14, 6); U2054-87 (08-27 / 10-14, 2) | clean on 10-19 | |
| Gateway / SGW | never read | n/a | n/a | **Never read.** U-codes are reported by BCM, IPC, RFHUB, DTCM, DASM, EPS |
| ETM / AlfaConnect, AMP | never read | only seen as the named source of BCM/IPC U1736 | n/a | **Never read.** Not in any MES module list for this car |
| HVAC / climate | never read | none on record | n/a | **Never read.** Not in any module list |
| TPMS, blind-spot, ESL, TVM and other modules | never read | none on record | n/a | **Never read.** (TPMS appears only in the Fiat 500L scans, a different car) |

## 7. Outside literature and links

- Opened and read 2026-10-20 [O]: NHTSA 08-045-20 `https://static.nhtsa.gov/odi/tsbs/2020/MC-10175724-9999.pdf` (C141C-86, 2020 GA/GU); NHTSA 08-103-20 `https://static.nhtsa.gov/odi/tsbs/2020/MC-10187696-9999.pdf` (2020 Stelvio DSCM: U1700-87 BCM missing message set in the drive-mode selector, battery disconnect then flash); NHTSA 08-107-20 `https://static.nhtsa.gov/odi/tsbs/2020/MC-10187708-9999.pdf` (2019 Giulia, same). Recall 21V309 (ABS HCU rotor weld, 2019 to 2021) came up in search and is not this car's model year. None applies to the 2018 car by model year; the first and the last two are context for how FCA words these codes.
- Existing verified experience links used: stelvioforum.com thread 24275 (C1408-86, C141C-86, U0102 cascade traced to a low 12 V battery), link-verified 2026-10-07 by browser (the forum sits behind a bot wall, so it was not re-opened today); added today as lookup keys C1408 and C141C in mes/experience.py. Brake fluid how-to videos already in the table (`brake_fluid`, oEmbed-verified 2026-10-07).
- Searches run 2026-10-20 (7 of 8 allowed): C104B-92, C141C/C141B, U1711/U1712/U1713, B1176, RFHUB B1040/U2054/U1765, rear window regulator DIY, C141B camera. No YouTube or forum link was found that is specific to C104B, C141B, B1176, B1040 or the U17xx codes on a Stelvio, so none was added; nothing was invented.
- The repo's other bulletins reached through `tsb_xref_bridge.xref` (it ran without the serial port): recalls 18V205 (BCM water intrusion) and 19V551 (BCM fuel level), CSN U24/U34/U36, 17V823, 08-044-19, S2008000093 (blind spot/park assist warnings) and S2223000047 (ACC, C1452-86), all `vin_check` or title-only, none names a code on this car.

## 8. Needs no action now

B1029-64 and B102E-64, U1716-2F, C1403-86, C1431-86 (single burst on 08-27, never again); U1701-86 (once, in session); U1711-2F and U1712-2F (stopped after 09-25); P1189, P00F5, P0098, P105E (2025-09-24, never again); U0100-87 (repo-documented bystander, no transfer-case symptom on record); B1040-64 and U2054-87 (watch only). They still count in the resolution criteria of their groups: a read in three weeks should list none of them, and any that returns on a quiet read moves up.

## 9. Gaps this review could not close

- ABS DTC state since 2026-09-04, ORC state since 2026-10-14, EPS/HALF/AFLS since 2026-09-04: no read exists.
- No status byte or freeze frame for any DASM, DTCM, EPS, HALF or AFLS code.
- No battery voltage at rest, cranking or charging; no brake fluid level; no window or camera symptom record; the owner questions on the network codes are unanswered.
- The BCM freeze-frame bytes beyond operating time and startups are undecoded.
- Whether MES's post-clear report block lists returned codes or the pre-clear list (section 2) is not established by the files.
