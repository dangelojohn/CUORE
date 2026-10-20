# Body, infotainment and status-0x40 codes, Stelvio the reference car (2026-10-20)

Scope: BCM B1176-97; ETM U1736-86/-87; U1765-86; RFHUB B1040-64; U1702-87; TCM P1DAD/P1DB7/P1DCE and the ECM status-0x40 entries; every other code in the logs outside EVAP, the BCM U1711/12/13 cluster and the DASM/HALF C14xx group (those are listed in section 8, not analysed).

**Two evidence classes, kept apart.**
- **READINGS** [E] come only from `data/captures/stelvio-2018/mes_logs/` (19 SCAN_*, 23 FESLog_*; none flagged simulation) and `data/captures/stelvio-2018/cuore_state/observations.jsonl` (222 rows, 39 `module_dtcs` rows), parsed by script and cross-checked against `docs/research/NETWORK_PATTERN_READINGS_2026-10-20.md`. Scan ids are the filename stamp YYMMDDHHMM (a save stamp, not exact scan time). Status bytes use the UDS bit layout: 0x01 testFailed, 0x02 failed this cycle, 0x04 pending, 0x08 confirmed, 0x40 test not completed this cycle, 0x80 lamp requested.
- **LITERATURE** [L] is public text with a URL, or a `cuore/data/tsb_catalogue.json` row id. NHTSA PDFs below were downloaded and read as text (exact). Web pages known only through search summaries are marked "summary". [I] marks my inference. No source below was read from the car.

## 0. Corrections to the brief (readings disagree)

| Brief says | Readings say |
|---|---|
| B1176-97 chronic since 2026-06-07 | Not in either 06-07 BCM scan (09:54, 10:03). First seen 2026-08-27 11:31. Present in 9 of 18 BCM-read scans (08-27 11:31, 09-02, 09-04, 09-15, 09-25 x2, 09-28, 09-29, 10-14) and in CUORE 10-13 20:24 (status 0x08). Absent since the 10-14 08:59 clear (CUORE 10-14 19:02 and 10-19 00:23/00:30; MES 10-19 00:39). |
| U1736 and U1765 in several modules incl. RFHUB | U1736-87 in BCM and IPC, U1736-86 in IPC only. U1765-86 is stored in the **BCM** (not the RFHUB). The RFHUB holds B1040-64 and U2054-87. |
| B1040-64 first 2026-09-25 | First seen 2026-06-07 10:03 (SCAN_2606071003, RFHUB). Six of 18 RFHUB scans: 06-07 10:03, 08-27 11:31, 09-25 20:27, 09-28, 10-08 09:20, 10-14; CUORE 10-13 20:24. What 09-25 shows is a 31-minute appearance (see 3). |
| U1702-87 possibly from the EPS | Stored in the **DASM**, text "EPS electric steering (NGE) - Missing message", once: SCAN_2610190039 (10-19 00:39). The EPS was read once ever (SCAN_2609042008, 09-04 20:08: U1960-83 only) and never by CUORE. |
| TCM codes | P1DAD/P1DB7/P1DCE exist only in CUORE UDS reads, all status 0x40. MES never listed one (no TCM error block in 19 scans). |

## 1. Summary

| Code | Module | Verdict (readings + literature) | Action |
|---|---|---|---|
| B1176-97 | BCM | Real, intermittent, event-type (confirmed 0x08, not failing at read). Absent 4 d 15 h since last clear. | Window initialisation and obstruction check; observe |
| U1736-86/-87 | IPC, BCM (ETM source) | One episode, first seen between 10-08 09:26 and 10-13 20:24, not back since 10-14 clear. Predates the 10-14 bitrate window, so not caused by it. | Radio software level, owner history; observe |
| U1765-86 | BCM | Two episodes (09-15, 10-13/14). Not back since 10-14 clear. | Owner symptom check; observe |
| B1040-64 | RFHUB | Recurring since 06-07, always confirmed-not-failing. Reciprocal of U1765-86/U2054-87. | Observe with U1765 |
| U1702-87 | DASM | One sighting; falls inside the interval containing the 10-14 wrong-bitrate window. Probable tool artefact, not proven. | Re-read, no clear first |
| P1DAD/P1DB7/P1DCE and ECM 0x40 list | TCM, ECM | Not faults. | None |

Cross-cutting reading [E]: on 2026-10-13 20:24, with U1713-2F failing (0x0F), every code in this document that was present was stored-not-failing: BCM B1176/U1765/U1736-87/B10AA 0x08, RFHUB B1040 0x08, IPC U1736 0x0C (pending plus confirmed, test passing now). None was failing at the time of any CUORE read. B1176-97, U1765-86, U1736-86/-87 and B10AA-4A were all present on 10-13/10-14 and all absent on every read after the 10-14 08:59 clear. [I] This looks like one cluster of events in the 5 d 11 h window 10-08 09:26 to 10-13 20:24 (B1176 itself had been absent on 10-04 and 10-08). A supply interruption would fit all four but is not shown by any reading; the CUORE owner questions about battery work (feedback.jsonl, 10-13 21:45 and 10-14 02:26) are still unanswered.

## 2. B1176-97 Rear left window riser, obstructed or blocked (BCM)

**Readings [E]**
- Present in BCM at: 08-27 11:31, 09-02 14:45, 09-04 19:53, 09-15 20:48, 09-25 19:56, 09-25 20:27, 09-28 11:59, 09-29 10:46, 10-14 08:59; CUORE 10-13 20:24 status 0x08.
- Absent: 06-07 x2, 08-27 11:36 and 11:41 (after clear), 10-04 11:13/11:15, 10-08 09:20/09:26, CUORE 10-14 19:02, 10-19 00:23 and 00:30, SCAN 10-19 00:39.
- BCM clears at 08-27 11:31, 09-04, 09-15, 09-25 20:27, 09-28, 09-29, 10-14 (all SUCCESS in file). Return after each clear (scan stamps): 6 d 3 h (to 09-02), 11 d 1 h, 9 d 23 h, 2 d 15 h (to 09-28), 22 h 47 min (to 09-29), then absent at least 8 d 22 h (10-08 09:26) and back by 10-13 20:24 (at most 14 d 9 h), then absent 4 d 15 h 40 min so far (10-14 08:59 to 10-19 00:39).
- No freeze frame, voltage or counter exists for it. BCM supply was 13.7 V (DID 1004 0x89) at 10-13 20:28 and 14.5 V on 10-19, so no low-supply reading near it.
- Not in the 10-14 23:58 to 00:00 window: the code was recorded at 10-13 20:24 and 10-14 08:59, before it, and was absent at the first read after it.

**Meaning.** MES text: "Rear left window riser - Component or system operation obstructed or blocked". Suffix -97 = operation obstructed or blocked [L, summary: https://oficinabrasil.com.br/noticia/tecnicas/quais-os-tipos-de-falha-sao-descritas-em-um-dtc-diagnostic-trouble-codes]. [I] The BCM's obstruction detection saw the rear-left glass stall or exceed its current/travel limit.

**Implications for the car [I, not shown by any reading].** The rear-left window may stop or reverse during a one-touch close, and one-touch up may be disabled until the window learns its end stops again. The owner has not been asked what the window does; the logs hold no symptom entry for windows (symptoms.jsonl holds only the 10-08 fuel smell).

**Real or artefact.** [I] Real, intermittent. It recurs across 7 weeks in sessions with and without ignition cycling, is a single-component code, and is not tied to the 10-14 window. It is not downstream of U1713: it was present with U1713 absent (09-29, BCM held only B1176; U1711/12/13 clean) and absent with U1713 present (10-19).

**Literature [L].**
- No FCA/Alfa bulletin, recall or forum case found for B1176 or for a 2018 Stelvio rear window (3 web searches). Catalogue has no window row.
- Third-party reinitialisation, Stelvio and Giulia pages (summary; the site returned HTTP 403 to direct fetch): https://www.wheelsjoint.com/alfa-romeo-stelvio-auto-windows-not-working-how-to-reset/ and https://www.wheelsjoint.com/alfa-romeo-giulia-auto-windows-not-working-how-to-reset/. Steps as summarised: start the car, close all doors and windows; hold the switch down until fully open, keep holding a few seconds; pull and hold up until fully closed, keep holding a few seconds; if one-touch still fails repeat, then repeat with ignition ON engine off. The page says the usual trigger is a disconnected or replaced 12 V battery. Not official Alfa text; check the owner's handbook.
- Analogue only (Infiniti, different make): ITB16-042, https://static.nhtsa.gov/odi/tsbs/2018/MC-10120583-9999.pdf: after power interruption AUTO-UP can be lost; initialise before any repair; anti-pinch is not active during initialisation, so keep hands clear and check afterwards with a soft object.
- Other FCA window bulletins read are different codes and models (B18BA-12/-13, 2020-21 Challenger/Charger/300/Ram door modules): 08-031-21 https://static.nhtsa.gov/odi/tsbs/2021/MC-10190688-9999.pdf, GPOP 9004334 https://static.nhtsa.gov/odi/tsbs/2020/MC-10187603-9999.pdf. Not applicable; cited only so nobody re-searches them.
- BCM water ingress recall: catalogue `recall-18v205` (unverified row; NHTSA build range 2017-03-20 to 2018-02-14). Transport Canada page, read 2026-10-20: https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018151 lists 2018 Stelvio, water corrodes the BCM and/or its A-pillar connector; stated effects are warning lights and loss of wipers, exterior lights, horn, turn signals; windows not named; build range not on the page. Whether this VIN is in scope is not known (VIN lookup is gated, catalogue `campaign-lookup`).

**Resolution, cheapest first**
1. Owner questions (no tools): does rear-left one-touch up/down work, bounce back, move slowly, or make noise; do the other three windows behave the same; any battery disconnect or jump 10-08 to 10-13.
2. Visual and manual: with the door closed, operate the rear-left window by holding the switch (no one-touch), listen for binding or grinding, look at the glass run and seals for grit, ice or a stuck liner.
3. Window initialisation per the procedure above (hands clear; anti-pinch is off during it). Then test one-touch both ways. This is a normal user function, not a diagnostic write.
4. Re-read the BCM (UDS, no clear first) at intervals; do not clear as a test.
5. Only if it returns after step 3: regulator or motor inspection (no source says replacement cures B1176; unknown).
**Proof of fix [E needed].** B1176-97 absent from BCM reads for longer than its longest observed gap (14 d 9 h upper bound), counted from the later of 10-14 08:59 and the initialisation date, with the window used daily, and one-touch confirmed by the owner. Four days of absence proves nothing: it was absent 8 d 22 h or more once and came back.

## 3. RFHUB B1040-64 and BCM U1765-86 (and U2054-87)

**Readings [E]**
- B1040-64 "Communication with Body Computer (BCM/NBC) - Signal/message plausibility", RFHUB. Present: 06-07 10:03, 08-27 11:31, 09-25 20:27, 09-28 11:59, 10-08 09:20, 10-14 08:59; CUORE 10-13 20:24 (0x08). Absent at the other RFHUB reads incl. CUORE 10-14 19:02, 10-19 00:23/00:30 and SCAN 10-19 00:39.
- Return after clear: 06-07 10:03 to 08-27 11:31 (81 d, no RFHUB read between); 08-27 to 09-25 20:27 (clean at 09-02, 09-04, 09-15, 09-25 19:56); 09-25 20:27 to 09-28 11:59 = 2 d 15 h 32 min; 09-28 to 10-08 09:20 = 9 d 21 h (clean 09-29, 10-04 x2); 10-08 to 10-13 20:24 = 5 d 11 h (re-read 10-08 09:26 clean); 10-14 08:59 clean to 10-19 00:39 = 4 d 15 h 40 min.
- 09-25: RFHUB clean at 19:56, B1040-64 present at 20:27. ECM startups counter 14473 in both FES files (19:56 and 20:27), so no engine start in between; ignition-on cycling without start is not countable. The 09-25 sighting is not the first; the brief's "first during ignition cycling" does not hold.
- U1765-86 "Lost communication with RF Hub module - Signal/message invalid", BCM. Present: 09-15 20:48 (cleared; ECM counter 14415 at 20:48, 14416 at 20:49, 14417 at 21:11, so present before that session's cycling), then CUORE 10-13 20:24 (0x08) and 10-14 08:59 (cleared). Absent 09-25 19:56 and every read after 10-14 08:59.
- U2054-87 (RFHUB, "Error in communication with BCM - Missing message"): 08-27 11:31 and 10-14 08:59. CUORE 10-13 20:24 RFHUB list showed only B1040-64.
- Co-occurrence: B1040 and U1765-86 together only on 10-13/10-14. U1765-86 without B1040 on 09-15; B1040 without U1765 on 06-07, 09-25, 09-28, 10-08. [I] They are two ends of one RFHUB-to-BCM link but do not always set together.
- BCM's own list on 10-19 carries B1040-24/-86/-96 at 0x40 (supported, not failed): a different module's family, do not conflate with RFHUB B1040-64.

**Meaning.** -86 signal invalid (message arrives, content or check fails); -64 plausibility (value inconsistent). Sources: https://www.tat.net.au/scandata/codes/code-view.php?id=8470 (U1711-86, Fiat page), https://oficinabrasil.com.br/noticia/tecnicas/quais-os-tipos-de-falha-sao-descritas-em-um-dtc-diagnostic-trouble-codes (summary; not checked against SAE J2012-DA). The BCM and RFHUB exchange keyless-entry and ignition-status messages [I; an Alfa BB post quoted by a search summary says the BCM and RF hub must agree on ignition status, https://www.alfabb.com/posts/8779250, not opened].

**Implications [I, unobserved].** Keyless entry, passive start and ignition-state messages are the functions at risk. Nothing in the logs shows a start or entry failure; the car started for every logged session. Ask the owner.

**Real or artefact.** [I] Real events, short-lived (always stored-not-failing when read), clustered around 10-13/14 with B1176, U1736 and B10AA-4A. Not downstream of U1713 alone: U1765/B1040 occurred in scans with and without U1713 (09-15 with, 06-07/10-08 without). Not caused by the 10-14 23:58 window (recorded before it, absent after it).

**Literature [L]**
- Chrysler GPOP tech tip (MY15-16 RF hub, not Alfa, code -87 not -86): "U1765-87 ... may appear in a stored state on an ignition power cycle. No troubleshooting or parts replacement is necessary if this code is stored as the system is functioning to design." https://static.nhtsa.gov/odi/tsbs/2016/MC-10130086-9999.pdf. Analogue for a stored-only code; says nothing for the Giorgio RFHUB.
- STAR S2008000113 (catalogue `tsb-s2008000113`, PDF read: https://static.nhtsa.gov/odi/tsbs/2020/MC-10180203-9999.pdf): intermittent keyless start failures; check aftermarket LED bulbs and wireless devices for LF key interference; model list not stated in the text.
- BCM supply and connector bulletins: catalogue `tsb-s1808000005` (F82 in the rear PDC for GU, BCM stand-alone fuse) and `tsb-s1708000262` (terminal inspection for intermittent CAN private/LIN codes); read in the earlier literature note, not re-opened here. Model scope not in the text.
- No Alfa or FCA bulletin found for U1765-86 or B1040-64 (searches: RFHUB/U1765/B1040 with Giulia/Stelvio).

**Resolution, cheapest first**
1. Owner: any no-recognise-key, multiple presses to start, doors not unlocking, between 09-15 and now; spare key and fob battery test; aftermarket LED bulbs, chargers, trackers (S2008000113).
2. Read-only: re-read BCM and RFHUB at several key-on sessions and one engine-running session, no clear first; record status bytes (0x08 vs 0x0F).
3. Supply side: BCM supply and ground check, F82 and the stand-alone BCM fuse, as in S1808000005; log BCM DID 1004 across a start.
4. Inspect the BCM and RFHUB connectors (S1708000262), and the A-pillar BCM connector for corrosion (`recall-18v205`; look up the VIN on the Transport Canada recall page first).
**Proof of fix.** Both U1765-86 and B1040-64 absent over a span exceeding their longest observed gap (9 d 21 h for B1040, 10 d for U1765-86 from 09-15 to 09-25 though it returned later), with no keyless symptom. **No action** if the owner reports no keyless symptom and the codes stay absent after 10-14.

## 4. ETM U1736-86 / U1736-87 (Entertainment Telematic Module)

**Readings [E]**
- IPC: U1736-86 "Signal/message invalid" and U1736-87 "Missing message", both status 0x0C (pending plus confirmed, not failing) at CUORE 10-13 20:24; both in SCAN_2610140859, cleared.
- BCM: U1736-87, status 0x08, same two reads, cleared.
- Absent in IPC and BCM at every scan from 06-07 to 10-08 09:26 (16 scans each) and at all reads after 10-14 08:59 (CUORE 10-14 19:02, 10-19 00:23/00:30, SCAN 10-19 00:39). So one episode, first seen within the 5 d 11 h window 10-08 09:26 to 10-13 20:24, not back for 4 d 15 h 40 min.
- B10AA-4A "PROXI configuration control - Incorrect component installed" (BCM) was present in the same two reads and nowhere else. [I] Co-timed; the logs do not say whether the ETM was changed or disconnected. No ETM identity read exists (MES lists no radio module; CUORE reads ECM/TCM/BCM/IPC/RFHUB only). No freeze frame.

**Meaning.** -87: the IPC and BCM stopped receiving the ETM's cyclic messages. -86: the IPC saw messages with invalid content. The ETM is the Uconnect radio head unit (FCA bulletins use "Entertainment Telematics Module (ETM)" for the radio, e.g. 08-065-20 below).

**Implications [I].** Loss of ETM data to the cluster and BCM: media/phone/navigation text on the cluster, audio-related chimes and mute lines. Not shown by any reading; ask the owner.

**Real or artefact.** [I] Not the 10-14 wrong-bitrate window: recorded 10-13/14 before it, absent after it. Two receivers (IPC and BCM) both lost the ETM, which points at the ETM or the bus segment it sits on, not at one receiver. A radio reboot would produce this pattern. Not downstream of the BCM U1713 cluster as such: the IPC's own list carries it.

**Literature [L], PDFs read**
- 08-065-20 (catalogue `tsb-08-065-20`, https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf; supersedes 08-081-19 `tsb-08-081-19`): 2018-2019 Stelvio (GU) built 2017-10-30 (MDH 1030XX) to 2019-07-12 (MDH 0712XX) with radio sales codes RAN, RAP, RAG, RSD. Symptoms: radio may reboot while driving; stays on after exit during a call; remote start at old volume. Procedure: Menu, Settings, System, Software Update, Current Software. Levels: MV-002.009.059 or lower is an early 2.0 radio (not this bulletin); MV-072.001.002 to 085.000.046 update; MV 090.000.061 latest. Caution: for GU built to 2018-04-12 (MDH 0412XX), after the ETM goes to MV 090.000.06x, BCM, AMP, ABS, IPC, PAM and blind-spot sensors must also be updated, "failure ... may result in vehicle malfunctions". Phones must be re-paired afterwards. No DTC list.
- 08-029-20 (`tsb-08-029-20`, https://static.nhtsa.gov/odi/tsbs/2020/MC-10174204-9999.pdf): 2018 Stelvio built to 2018-01-11 (MDH 0111XX), radios RAN/RAP/RAJ/RAG/RSD, 2.0 radio software to MV-002.010.041: reboot while driving, freezes, voice and navigation faults.
- Not applicable to a 2018 car: 08-064-20 (2020 only, https://static.nhtsa.gov/odi/tsbs/2020/MC-10223593-9999.pdf); telematics-box 08-130-24 and 08-133-24 REV A (2022-2023 Stelvio, https://static.nhtsa.gov/odi/tsbs/2024/MC-11001300-0001.pdf, https://static.nhtsa.gov/odi/tsbs/2024/MC-11001323-0001.pdf).
- No bulletin found that names U1736. A forum thread on this exact code was not found (web search; the results returned P1736). The build date (MDH) of this car is not in any log (DID F18B reads blank), so which bulletin applies is unknown.

**Resolution, cheapest first**
1. Owner: any radio reboot, black screen, lost CarPlay/Bluetooth, nav fault between 10-08 and 10-13; any aftermarket head unit, amplifier, USB device; any battery work in that window.
2. Read the radio software level from the menu (path above), and the radio sales code and MDH from the door-jamb label. Compare with 08-065-20 / 08-029-20.
3. Re-read IPC and BCM (no clear first) after a normal week of use.
4. If the level is below the bulletin level and symptoms match: dealer ETM update, then the dependent-module updates the bulletin requires. Post-update PROXI/configuration steps are dealer-tool writes; not part of this research.
**Proof of fix.** Fix is only provable after a cause is found. The ETM codes were absent for four months of logs (06-07 to 10-08) before the episode, so a few weeks of absence is weak evidence. A convincing outcome: software below the bulletin level, update done, no reboot symptoms and no U1736 for 60 days. **No action** if the radio is already at the latest level, the owner reports no radio faults, and the codes stay absent.

## 5. U1702-87 EPS electric steering (NGE) missing message, logged in the DASM

**Readings [E]**
- One sighting: SCAN_2610190039 DASM, with C1408-86, C141B-97, C141C-86 (covered elsewhere). Cleared (SUCCESS) in that file. Absent in all 17 earlier DASM reads, incl. SCAN_2610140859 (10-14 08:59, DASM held C141B-97 only, cleared).
- So it first appeared between 10-14 08:59 and 10-19 00:39. That interval contains the 10-14 23:58 to 10-15 00:00 raw listen with three wrong-bitrate windows (250k, 125k) on CAN-CH, during which the owner heard a chime and saw the airbag lamp (notes.jsonl 10-15 00:01 and 00:06; jobs.jsonl 10-15 00:19). No DTC read of any module falls inside the window; the first DASM read after it is the 10-19 scan.
- EPS never held U1702. EPS read once: SCAN_2609042008 (09-04 20:08), U1960-83 "Error in communication with ECU - value of signal protection calculation incorrect" only. No EPS read since, by MES or CUORE. CUORE's only ABS read on that bus (10-15 00:12) returned empty identity fields (treat as no answer).
- Other steering-referencing codes, all on 08-27 11:31 (cleared, not seen since): BCM U1716-2F "Electric Steering (NGE) erratic", DASM C1403-86 "EPS signal invalid", IPC B1029-64 "Lost communication with Steering module (SCM) plausibility".

**Meaning.** The DASM did not receive the EPS's cyclic message for the code's timeout. -87 = missing, not corrupted.

**Implications [I].** The DASM (radar and camera ADAS) uses steering angle/torque. While it logs this code the lane-keep, adaptive-cruise or hands-on-wheel logic can degrade or show a message. No reading shows an ADAS message. The owner has not reported one.

**Real or artefact.** [I] Probable tool artefact: single sighting, EPS not implicated by its own codes, and it sits in the interval holding the wrong-rate listen on the chassis bus where the owner note says ABS/EPS/ORC messages were lost. Not proven: DASM C1408-86 and C141C-86 appear at times with no known tool event (08-27, 09-04), and the DASM was not read between 10-14 08:59 and 10-19. Not a downstream of the BCM cluster (it is a DASM-side code).

**Literature [L].** No Giorgio source for U1702 found. Analogues: Jeep Renegade 2019 EPS flash 08-041-20 (U1702-64 with C1013-49; https://static.nhtsa.gov/odi/tsbs/2020/MC-10175150-9999.pdf, read) , a Fiat forum thread reading U1702 as an EPS-to-engine-ECU CAN fault (summary, owner opinion, https://www.fiatforum.com/threads/1-6-dynamic-power-steering-failure.345801/latest), a Wagoneer case citing EPS supply 12-14 V, low-resistance ground, supply not below 10 V under load (summary, bulletin id not read). STAR S2019000002 (`tsb-s2019000002`, https://static.nhtsa.gov/odi/tsbs/2020/MC-10175674-9999.pdf, read): "Place hands on steering wheel" message with hands on the wheel on LDW cars is normal torque-sensing behaviour and not a fault; relevant only if the owner reports that message.

**Resolution, cheapest first**
1. Owner: any steering, lane-assist or cruise warning since 10-14; any steering lamp.
2. Re-read the DASM (no clear first) after at least five normal drives with no tool attached and no wrong-rate listening.
3. Read-only EPS DTC read (never done by CUORE; last MES read 09-04), to see whether the EPS itself holds U1702 or U1960 again.
4. Only if U1702-87 returns without tool activity: EPS supply and ground and connector check (supply not below 10 V under load per the Wagoneer case); then software levels.
**Proof it was an artefact.** DASM re-read shows no U1702-87 after multiple key cycles and drives without tool interference, and the EPS holds no U1702/U1960. **No action** until it recurs outside a tool session.

## 6. TCM P1DAD-00, P1DB7-00, P1DCE-00 and the ECM status-0x40 entries

**Readings [E]**
- CUORE UDS `module_dtcs` (39 rows; 2,368 listed entries): 2,337 entries have status exactly 0x40; the other 31 are the named codes (ECM P0440/P0455/P0456; BCM U1713-2F 0x0F, B1176-97, U1736-87, U1765-86, B10AA-4A 0x08; IPC U1736-86/-87 0x0C; RFHUB B1040-64 0x08). The 0x40 entries: ECM 1,121, BCM 933, TCM 283.
- For every 0x40 entry the parsed flags are: testNotCompletedThisOperationCycle true; testFailed, failed-this-cycle, pending, confirmed, test-failed-since-clear, test-not-completed-since-clear, lamp-requested all false. No failure bit is set on any of them in any read.
- TCM: 10-13 20:24 returned 1 entry (P0606-00); 10-14 19:02 48 entries (P1DAD, P1DB7, P1DCE listed twice, P061B, P1D8F ... P215C); 10-19 00:23 48; 10-19 00:30 45. All 0x40. MES's TCM block is empty in all 19 scans.
- Entry counts differ per read (ECM 278, 72, 142, 132, 121; TCM 1, 48, 48, 45). The cause is not in the data. Do not infer anything from the differences.

**Meaning.** Bit 6 (0x40), ISO 14229 "testNotCompletedThisOperationCycle": the monitor behind that DTC has not run in the current key cycle. It is a readiness flag, not a fault flag; 0x40 alone with bits 0 and 3 clear means nothing failed and nothing stored. Sources (secondary, ISO text itself not read): https://pyudskit.readthedocs.io/en/latest/reference/dtc-status-bits/ , https://uds.readthedocs.io/en/latest/pages/knowledge_base/dtc.html . [I] MES omits them because it prints only codes with failure bits; the UDS list with the 0xFF mask returns supported DTCs too.
- Names: P1DB7-00 = torque converter clutch performance (ZF 8HP, repo `docs/reference/ZF8HP_SERVICE_DATA.md`, FCA wording; only an item in TSB set `tsb-s2621000003` for 2026 8HP codes, not a Stelvio 2018 bulletin). P1DAD-00 "Input shaft - output shaft direction correlation" appears in a Chrysler bulletin for the 948TE nine-speed (search summary), so not confirmed for the 8HP. P1DCE: no description found.

**Implications.** None. **Real or artefact.** Neither; they are list entries. **Resolution: no action.** The only reading that would change this is any of these codes showing a status other than 0x40 (bits 0, 1, 2 or 3). Watch for that on the TCM list; ECM EVAP codes are handled in the EVAP documents.

## 7. Wrong-bitrate window and ignition-cycling check, per code

- **10-14 23:58 to 10-15 00:00 window:** no DTC read inside it. Codes recorded before it (B1176, U1736, U1765, B1040, B10AA) were absent at the first reads after it (10-19), so the window left nothing in the BCM, IPC or RFHUB. Only U1702-87 (DASM) and, outside this document, DTCM U0422-86 and DASM C1408/C141C first appeared after it, and the DASM/DTCM were unread for five days.
- **Ignition-cycling sessions** (ECM startups counter): 08-27 (14299 at 10:57 to 14303 at 11:19), 09-04 (14357 to 14359), 09-15 (14415 to 14417). B1176, B1040 and U2054-87 were first in the 08-27 11:31 scan after +4 starts; B1176 and B1040 also recur in sessions without engine starts (09-25 had none; B1176 09-02, 09-29, 10-13). [I] Cycling may raise odds but is not required.

## 8. Other codes in the logs, listed only [E]

| Code | Module | When |
|---|---|---|
| U1716-2F Electric steering erratic | BCM | 08-27 11:31 |
| B10AA-4A PROXI incorrect component | BCM | CUORE 10-13 20:24, SCAN 10-14 08:59 |
| U2054-87 BCM missing message | RFHUB | 08-27 11:31, 10-14 08:59 |
| B1029-64 SCM plausibility, B102E-64 BCM plausibility | IPC | 08-27 11:31 |
| U0100-87 ECU missing message | DTCM | 08-27 11:31, 11:36, 09-02, 09-04, 09-28, 10-14, 10-19 |
| U0422-86 BCM invalid | DTCM | 10-19 00:39 |
| U1701-86 ECU invalid | DASM | 06-07 10:03 |
| C1403-86, C1431-86 | DASM | 08-27 11:31 |
| U1960-83 ECU message protection | EPS | 09-04 20:08 |
| U0428-86 steering angle invalid | AFLS | 09-04 20:08 |
| U0418-86 ABS comm invalid | HALF | 09-04 20:08 |
| C104B-92 hydraulic leak, U1700-87 BCM missing (10.6 V, startups 14280) | ABS (FES) | 09-04 20:01 (cleared) |
| P1189, P00F5, P0098, P105E (ECM sensors) | ECM (FES) | 2025-09-24 13:45 only |

## 9. Reading and literature gaps

- No ETM, EPS or window-module identity or software level has ever been read from this car.
- Build date (MDH) unknown, so bulletin scope for 08-029-20 / 08-065-20 and recall 18V205 is unconfirmed.
- No freeze frame for any code here; the only BCM snapshot is U1713-2F.
- No official Alfa window-initialisation text found; the procedure is third-party and was seen only through search summaries.
- Searches used: 9 standard web searches (one over the cap of 8) plus 1 Transport Canada and 1 trade-article fetch; the earlier literature note is `NETWORK_PATTERN_LITERATURE_2026-10-20.md`. Stelvio-specific sources are 08-065-20, 08-029-20 and Transport Canada 2018151.
