# CEL 2026-10-19: evidence picture for P0440 / P0455 / P0456 on a sealed system

2018 Alfa Romeo Stelvio 2.0T Q4, VIN ZASFAKPN5J7B88115. Job 76d3454bce75, hypothesis ce6bd236 (EVAP: ESIM signal path); hypothesis 8c659dfc (EVAP monitor inputs invalid) added later the same night.
ECM Magneti Marelli IAW 10JA, HW MM10JAHW232, SW 52170619 / supplier P235QB39 ver 0000 (unchanged in every 2026 read). BCM Marelli 949, SW 04441660441 ver 1454.
Written 2026-10-19 about 00:45 from repo data only (observation store, MES logs, job store, TSB catalogue and xref, repo docs). No web, no car access, no new reads.

Claim tags used throughout:
- **[E]** evidence: a stored read, a log line or a recorded job entry (source named).
- **[I]** inference: my reasoning from [E] items; may be wrong.
- **[N]** not in repo: the repo has nothing on it; do not treat as known.

---

## 0. Read this first (four things that change the picture)

1. **The codes were cleared again tonight at 00:39.** [E] `SCAN_2610190039.txt` (MES, C:\Program Files (x86)\MultiEcuScan) lists P0455, P0456, P0440 on the ECM and U1713-2F on the BCM, then runs "CLEARING STORED FAULT CODES" with SUCCESS on ECM, DTCM, BCM and DASM. That is 16 minutes after the CUORE reads at 00:23 and 5 minutes after the last CUORE observation (00:34). The ECM's own status bytes, freeze frames and Mode 06 for tonight are therefore gone from the car. The only copies are in the CUORE observation store (`module_dtcs` 00:23:42 and 00:30:25; `dtc_detail` 00:25:35 to 00:25:39). The job note of 2026-10-15 00:19 records that the owner was told not to clear again. This is the 11th ECM clear in 53 days (list in the timeline).
2. **Tonight is not the first time the ECM asked for the lamp.** [E] On 2026-10-13 20:03 the readiness read had `mil_on: true` and at 20:24 ECM P0440 was 0xCD (bit 0x80 set). The session record (`docs/vehicles/ZASFAKPN5J7B88115/sessions/2026-10-07-session-record.md` sections 13 and 14) calls the lamp on but says the owner had not observed it illuminated. The reads of 2026-09-25 and 2026-10-14 19:02 had bit 0x80 clear, as you said; 10-13 sits between them and was erased by the 10-14 08:59 clear. So the lamp request has now come back twice, each time 4.6 to 5.4 days after a clear. [E]
3. **Tonight's OBD-side reads returned nothing.** [E] Mode 01, 03, 06, 07, 09, 0A and readiness all returned NO DATA at 00:23 and again at 00:29 to 00:34 (port 14.4 to 14.5 V, engine running) while UDS reads to the same ECM worked. No Mode 06 EVAP result, no readiness, no PID 21 (distance with MIL), no permanent codes tonight. The line "EVAP monitor ... not supported by this ECU" in tonight's `mode06` observation is a NO DATA artefact, not a finding (the same ECM returned all those MIDs on 10-13 and 10-14). [E] Why the legislated route failed tonight is not in the repo. [N]
4. **The three smoke tests cannot show a blockage.** [I] A smoke test finds leaks; a blocked or kinked path also reads "no smoke, no flow, sealed". The job records only "no leak found / all sections sealed" for all three tests (actions d5013d32, 195f9b05, 8aab8340). No flow readings and no note that smoke was seen arriving at the tank, canister or ESIM ports were recorded. [E] for what was recorded, [N] for whether continuity was confirmed.

---

## Timeline of every occurrence, clear and repair

Times are local. "Cleared" means MES ran CLEARING STORED FAULT CODES with SUCCESS on the ECM unless stated. All rows [E] unless tagged.

| Date / time | Type | What happened | Source |
|---|---|---|---|
| 2025-08-15 (day unknown) | repair, test | Fuel cap new, EVAP canister replaced (no part numbers). Smoke test 1: no leak. Codes persisted afterwards (owner-confirmed, never logged by a tool). | job 8866b377, d5013d32 |
| 2025-09-24 13:45 | occurrence | First MES log of this VIN, 114,009 km. P0456 stored; freeze frame cold-start idle (ECT 16 C, fuel 73.7 %). Purge valve actuator test COMPLETED x5. | FESLog_2509241345 |
| 2026-06-07 09:54 to 10:08 | clear | MES scans: ECM lists no codes (P0456 absent 8.5 months after first sighting: gap unexplained [N]). BCM U1713/U1712/U1711-2F, DASM C141C-86; BCM and DASM cleared. | SCAN_2606070954/1003 |
| 2026-08-27 11:19 | occurrence, clear | 140,573 km. P0455, P0440, P0456 all logged (freeze frames below), ECM cleared in the session. 11:31 scan: BCM U1713-2F present; IPC, DTCM, BCM, RFHUB, DASM cleared. | FESLog_2608271119, SCAN_2608271131 |
| 2026-08-31 18:23 | occurrence, clear | P0440 back after 4.3 days; ECM cleared. | FESLog_2608311823 |
| 2026-09-02 14:45 to 14:54 | occurrence, clear, **repair** | P0456 + P0440 back after 1.9 days (141,059 km); ECM cleared. Same day new: canister air filter, fuel cap and seal, valve at the canister, ESIM 04861961AD. | SCAN_2609021445, FESLog_2609021454, job da2ad8dc |
| 2026-09-04 19:53 | occurrence, clear | P0440 after 2.2 days; ECM, DTCM, BCM cleared (DASM clear FAILED). | SCAN_2609041953 |
| 2026-09-15 20:48 | occurrence, clear | P0440 only, after 11.0 days; ECM, BCM, DASM cleared. 12 purge-valve actuator runs COMPLETED that evening. | SCAN_2609152048 |
| 2026-09-16 | test | Smoke test 2: no leak; E1 quick-connect and E5 purge routing OK. | job 195f9b05 |
| 09-02 to 09-25 (date unknown) | **repair** | Engine-side purge valve 68337662AC replaced. | job 7fda7572 |
| 2026-09-25 19:56 to 20:27 | occurrence, clear | P0455 + P0440 + P0456 all back after 10.0 days. 20:12 CUORE UDS: all three 0x4D, MIL bit clear. 20:27: ECM, BCM, RFHUB, DASM cleared. | SCAN_2609251956, FESLog_2609252002, SCAN_2609252027 |
| 2026-09-26 | inspection, test | Filter clear (9100468); no fuel in canister (9100471; recirculation line not reported); quick-connect latched (S2125000002); owner never tops off, no hiss, smell, slow fill or early click-off. Smoke test 3: all sections sealed. | job ef76e9d4, 550496bf, 9a8683bc, c8f8c907, 8aab8340 |
| 2026-09-28 11:59 | occurrence, clear | P0440 after 2.6 days; ECM, DTCM, BCM, RFHUB, DASM cleared. | SCAN_2609281159 |
| 2026-09-29 10:46 | occurrence, clear | P0440 again after 0.95 day; ECM, BCM cleared. | SCAN_2609291046 |
| 2026-10-04 11:13 to 11:16 | no codes | Two scans and an FES session: no codes, 5.0 days after the clear. No evidence the monitors ran. | SCAN_2610041113/1115 |
| 2026-10-08 09:20 | occurrence, clear | P0456 + P0455 (no P0440) after 8.9 days; ECM, RFHUB, DASM cleared; 09:26 re-scan clean. | SCAN_2610080920/0926 |
| 2026-10-13 20:03 to 20:38 | occurrence | First CUORE live read, 5.4 days after the 10-08 clear. **MIL on** (readiness `mil_on` true), all monitors complete incl. EVAP. UDS: P0440 **0xCD**, P0455 0x4D, P0456 0x40. Mode 06: gross-leak (MID 39) PASS; **0.090 in (MID 3A) FAIL 404 ms vs min 3965 ms**; 0.020 in (MID 3C) TID 90 FAIL 6096 vs max 6000, others PASS; purge flow (MID 3D) PASS (168 within 57 to 328). BCM U1713-2F **0x0F**. | store `readiness`, `module_dtcs`, `mode06`; session record sec. 13 |
| 2026-10-14 08:59 | occurrence, clear | MES: ECM P0455 + P0440; ECM, IPC, DTCM, BCM, RFHUB, DASM cleared. | SCAN_2610140859, job 94448c44, 418eba6d |
| 2026-10-14 19:01 to 19:02 | occurrence | 10 h, 9 km, 4 warm-ups after the clear: P0440 **0x4D** (MIL bit clear, `mil_on` false), P0455/P0456 0x40; Mode 07 P0440; Mode 0A P0440 + P0456; fuel 93.7 %; EVAP, catalyst, O2, EGR monitors incomplete; Mode 06 all reset to 0; PID 54 EVAP vapour pressure 0.0 kPa. BCM: no codes. | store, job ff5715b4 |
| 2026-10-14 23:58 to 00:00 | tool artefact | Wrong-bitrate listen test on CAN-CH: chime and airbag lamp. Not EVAP, not evidence. | job 63f15aba |
| 2026-10-19 00:23 to 00:34 | occurrence | CUORE UDS (engine running, plain OBD port): P0440 **0xCD**, P0455 **0x4D**, P0456 **0x4D**; BCM U1713-2F **0x0F**; TCM, IPC, RFHUB nothing. OBD side NO DATA. 4.6 days after the clear. | store |
| 2026-10-19 00:39 | occurrence, **clear** | MES scan: ECM P0455/P0456/P0440; BCM U1713-2F; DTCM U0100-87 and U0422-86; DASM C1408-86, C141B-97, U1702-87, C141C-86. Then ECM, DTCM, BCM, DASM cleared. | SCAN_2610190039 |

ECM clears so far: 08-27, 08-31, 09-02, 09-04, 09-15, 09-25, 09-28, 09-29, 10-08, 10-14, 10-19 (11 in 53 days). [E]

Clear-to-return intervals for an EVAP code: 4.3, 1.9, 2.2, 11.0, 10.0, 2.6, 0.95, [5.0 clean, then 8.9 with P0455/P0456 only], 5.4 (lamp), 0.4 (10 h), 4.6 (lamp) days. [E] The fault has come back after every clear, within 0.4 to 11 days (the 5.0-day read on 10-04 was clean; the 8.9-day read was not). Clearing changes nothing. [I]

### Conditions when each EVAP code set (freeze frames on record)

| Set at | Code | Odometer km | Fuel % | ECT C | Speed km/h | Note |
|---|---|---|---|---|---|---|
| 2025-09-24 | P0456 | 114,009 | 73.7 | 16 | 0 | cold-start idle |
| 2026-08-27 | P0455 | 140,471 | 51.8 | 58 | 23.6 | |
| 2026-08-27 | P0440 | 140,566 | 46.7 | 63 | 35.6 | |
| 2026-08-27 | P0456 | 140,573 | 46.7 | 32 | 0 | cold-start idle |
| 2026-08-31 | P0440 | 140,883 | 63.9 | 64 | 0 | idle 794 rpm, warm |
| 2026-09-02 | P0456 | 141,006 | 48.6 | 24 | 0 | cold-start idle |
| 2026-09-02 | P0440 | 141,059 | 43.9 | 59 | 34.2 | |
| 2026-09-25 | P0455 | 141,930 | **93.7** | 63 | 50.6 | |
| 2026-09-25 | P0440 | 142,227 | **91.8** | 60 | 40.4 | |
| 2026-09-25 | P0456 | 142,290 | 80.0 | 15 | 0 | cold-start idle |
| 2026-10-13 (OBD Mode 02) | P0440 | n/a | 28.6 | 63 | 2 | 217 s after start, purge commanded 18 %, ambient 17 C |

Sources: MES FES logs; the 10-13 row from the session record. [E] Patterns:
- P0456 set at cold-start idle in 4 of 4 frames across 12 months (ECT 15 to 32 C). [E] P0440 and P0455 set warm (ECT 58 to 64 C), engine running, and on 10-13 with purge active. [E]
- [I] That split fits two different tests failing for the same reason: an engine-running purge-vacuum test (P0455, P0440) and a key-off natural-vacuum test whose result is reported at the next cold start (P0456). The repo's working model is that the ECM declares each failure when the ESIM switch does not report sealed/vacuum (docs/handbook/04-stelvio-case.md; CASE.md). That model is the repo's, not an FCA document; no FCA "Description and Operation" for the GME-T4 EVAP system was obtained (EVAP_STELVIO.md, "Could not verify"). [N]
- Fuel was inside the 15 to 85 % window in 9 of 11 frames; only the two 09-25 frames exceed it. [E] The "above 85 %: EVAP monitor could not run" items attached to ce6bd236 describe only those two frames; they are test-condition notes, not pass/fail results (also flagged in EXTERNAL_REVIEW_6). [E]/[I]

---

## What the status bytes say tonight

UDS 19 02 status bytes, ECM and BCM, reads at 00:23:42 and 00:30:25 (identical), detail reads 00:25:35 to 00:25:39. Bit order per ISO 14229: b0 testFailed, b1 failedThisCycle, b2 pending, b3 confirmed, b4 notCompletedSinceClear, b5 failedSinceClear, b6 notCompletedThisCycle, b7 warningIndicatorRequested.

| DTC | Tonight | Bits set | 10-13 (pre-clear) | 10-14 19:02 |
|---|---|---|---|---|
| ECM P0440-00 | 0xCD | b7 b6 b3 b2 b0 | 0xCD | 0x4D |
| ECM P0455-00 | 0x4D | b6 b3 b2 b0 | 0x4D | 0x40 |
| ECM P0456-00 | 0x4D | b6 b3 b2 b0 | 0x40 | 0x40 |
| BCM U1713-2F | 0x0F | b3 b2 b1 b0 | 0x0F | not present |

Reading:
- [E] These four are the only non-0x40 entries on ECM, TCM, BCM, IPC and RFHUB tonight. P2422 (vent), P0457, P0451, P0441, P0461 and P1CEA are tracked on the ECM and read 0x40 (no failure recorded). The 10-13 and 10-14 reads show the same. No ESIM-circuit code is tracked as failing; P24D6 is not in the tracked list tonight. [E]
- P0440 0xCD: last completed test result is failed (b0), pending and confirmed (b2, b3), lamp requested (b7), and the test has not completed this operation cycle (b6) with no failure this cycle (b1 clear). [E] So the failed state is carried over from an earlier completed cycle, which fits an engine-running read: the key-off test has not had a chance to run. [I]
- P0455 and P0456 carry the same bits without b7: the lamp request is attached to P0440 only. [E] Why the ECM ties the lamp to P0440 and not the others is not in the repo (the project notes of 2026-09-26 say the same: "reason (calibration MIL rules vs pending trip count) not determinable from the logs"). [N]
- P0456 went 0x40 (10-13) to 0x4D (tonight): the small-leak test failed again in the last five days. [E]
- The triplet 0xCD / 0x4D / 0x0F is identical on 10-13 and tonight, both 4.6 to 5.4 days after a clear. [E] Reproducible, not random. [I]
- Bits b4 and b5 are never set on this ECM in any stored read (1,140 ECM status values: only 0x40, 0x4D, 0xCD). [E] They cannot be used to say "the test completed since the clear". [I]
- U1713-2F 0x0F: the BCM's own test ran this cycle (b6 clear) and failed this cycle (b1). Active now with the engine running. Not lamp-requesting. [E]
- Extended-data record 1 reads byte 0x60 on all four codes tonight and on U1713-2F on 10-13, and the U1713 extended bytes are identical to 10-13 although the code was cleared in between. The "occurrence counter" label is an unverified guess in the decoder; this looks like a constant. [E]/[I]
- Lamp, permanent codes, readiness and distance with MIL cannot be cross-checked tonight (OBD NO DATA, section 0). The lamp-on is the owner's observation plus bit b7. [E]
- After the 00:39 clear the lamp request should drop and the bytes reset to 0x40; I have not seen a post-clear read. [I]

## Tonight's freeze frames (decoded from UDS 19 04, 2026-10-19; scaling medium confidence)

Raw material: store `dtc_detail` records at 2026-10-19 00:25:35 (P0440-00), 00:25:36 (P0455-00), 00:25:38 (P0456-00), 00:25:39 (BCM U1713-2F). Each has a `snapshot` with the raw bytes under `undecoded_from` (DID 1008 onward; ECM records 132 bytes, BCM 38). **These are now the only copy**: the ECM's own freeze frames were cleared at 00:39. Do not rotate or rewrite `C:\ProgramData\cuore\observations.jsonl`.

Decoded values. [E] for the bytes read from the car; [I] for the scaling, which is medium confidence.

| Field | P0455 | P0456 | P0440 |
|---|---|---|---|
| Startups counter | 14603 | 14608 | 14612 |
| Operating minutes | 298114 | 298329 | 298445 |
| Odometer km | 146522.2 | 146726.6 | 146755.7 |
| Fuel level % | 91.8 | 62.7 | 55.7 |
| Engine speed rpm | 764 | 0 | 921 |
| Vehicle speed km/h | 0 | 0 | 12.1 |
| Gear | 0 | 0 | 3 |
| Coolant temperature C | 69 | 17 | 51 |
| Battery voltage V | 14.2 | 12.3 | 14.3 |
| MAP mbar | 316 | 969 | 371 |
| Spark advance deg | 3.75 | 0 | -12.75 |

Reading [I]:
- P0455 was set at idle (764 rpm, 0 km/h, gear 0, charging at 14.2 V) just after a refuel (fuel 91.8 %).
- P0456 was set with the engine off (0 rpm, 12.3 V, MAP 969 mbar, close to ambient pressure) after a cold soak (coolant 17 C). This is the first P0456 frame with the engine not running; the four older MES frames show cold-start idle. It fits the earlier inference of a separate key-off natural-vacuum test, and suggests the code can be set during the engine-off test itself rather than only at the next start.
- P0440 was set while driving in 3rd gear (921 rpm, 12.1 km/h, coolant 51 C, 14.3 V, spark retarded to -12.75 deg).
- Three regimes (idle after refuel, engine off after cold soak, driving in 3rd), same outcome: the switch closure was never seen by the ECM.
- The startups counter and operating minutes rise from frame to frame (14603, 14608, 14612; 298114, 298329, 298445 min), so the three frames are three separate events, 5 and 4 starts apart. The odometer places the P0456 and P0440 frames 29 km apart and the P0455 frame 204 km before P0456.
- Check item: tonight's P0455 fuel value (91.8 %) is identical to the 2026-09-25 P0440 frame value (91.8 %, table above). It may be a coincidence; with medium-confidence scaling it is worth confirming against a second read of the fuel level before the value is relied on.
- Not in the table: purge duty, ambient/IAT, baro and time since start. Whether the raw bytes carry them is not established here. [N]

---

## Repairs done and what each ruled out

| Item | When | Ruled out | Strength and caveat |
|---|---|---|---|
| Fuel cap, new (twice) | 2025-08, 2026-09-02 | Cap as a leak source | Strong [E]. Two new caps and three smoke tests. |
| EVAP canister, new | 2025-08 (no part number) | Original saturated or failed canister (9100471) | Moderate [E]. P0456 was first logged 2025-09-24, after this swap, so this canister is 14 months old and part number unrecorded [N]. |
| Canister air filter, new; inspected clear 09-26 | 09-02; 09-26 | Dirty filter (9100468) | Strong [E]. |
| "Valve at the canister", new | 2026-09-02 | A valve at the canister | The job entry does not say which valve [N]. |
| ESIM 04861961AD, new | 2026-09-02 | An old or failed ESIM unit (9100469 remedy already applied) | Moderate [E]. Fitment never VIN-verified (alternative 04861959xx exists; mes/parts.py, project notes), mounting orientation and port seating not recorded [N]. Test A has never been run. |
| Engine-side purge valve 68337662AC, new | 09-02 to 09-25 | Purge valve leaking or stuck | Strong [E]. Also 18 actuator runs COMPLETED (5 on 2025-09-24, 1 on 2025-10-14, 12 on 2026-09-15) and Mode 06 purge-flow tests PASS on 10-13 (168 within 57 to 328). Actuating is not sealing, but the flow test covers supply [I]. |
| Smoke tests x3 | 2025-08, 09-16, 09-26 | A physical leak at smoke-test pressure | Strong for leaks [E]; **blind to blockage and to a sense-port fault** [I]; no flow numbers or arrival points recorded [N]. |
| Quick-connect latched; purge routing OK | 09-26; 09-16 | S2125000002 cause; 9100325 hose faults | Strong [E]. |
| No liquid fuel at canister | 09-26 | Flooded canister (9100471) | Strong at the canister [E]; recirculation line not reported [N]. |
| Owner refuelling interview | 09-26 | Overfill saturation; early click-off | [E]. No early click-off or slow fill also argues against a total blockage of the tank-canister-vent path at refuelling flow, if the vent path runs through the ESIM as TSB 9100471 describes it ("clean-air hose between the ESIM and the EVAP air filter") [I]. It does not cover a small sense port or a closed-state restriction [I]. |
| 11 clears | 08-27 to 10-19 | Clearing as a remedy | The fault returns every time [E]. |
| Mode 06, 2026-10-13 | | Supply of purge vacuum; gross leak | Gross-leak and purge-flow MIDs PASS; only the 0.090 in and one 0.020 in test fail [E]. What the 404 ms / 3965 ms number measures is not defined in the repo [N]; read as a hold or decay time it means vacuum was absent or lost within 0.4 s [I]. |
| ECM software | 2026 | A flash between 06-07 and 10-19 | SW 52170619 / P235QB39 unchanged in all MES scans and CUORE identity reads [E]. Whether it is current is unknown [N]. |

Not yet done (none recorded on the job): wiTECH Test A, wiTECH flash check, ESIM wiring test, ESIM bench test, VIN checks for recall 18V636 / CSN W05 / 19V551. [E]

---

## Bulletins (Stelvio and analogues) and how each relates

From `cuore.services.tsb_xref_bridge.xref(VIN)` (top rows by score) and `cuore/data/tsb_catalogue.json`. The xref marks several rows "supports" only because the bulletin's system tag is EVAP; that is a same-system match, not evidence. [E]/[I]

Stelvio / this model:

| Number | What it is | Relation to this fault |
|---|---|---|
| 18-048-23 (supersedes 18-089-19) | wiTECH SLVT; a road test cannot confirm a small-leak repair | Explains P0456 by code list. Proof-of-fix tool, not a cause. Not yet run. [E] |
| 9100471 (2025-03-17) | Hard to fill / flooded canister: check clean-air hose ESIM to filter, filter, kinked tank-canister vapour hose; if fuel, replace canister and ESIM | Code list matches all three. Canister and ESIM remedy already applied, did not resolve (xref `did_not_resolve`). Flooding ruled out 09-26. **Its kinked-hose checks have not been recorded as done** (only the filter was). [E] |
| 9100469 (2024-12-16) | Replace only the ESIM if only it is at fault | Applied 2026-09-02, did not resolve. [E] |
| 9100468 | Canister filter restriction | Ruled out by inspection and replaced. [E] |
| 9100325 Rev 1 | Purge hoses and ejector tees | Routing OK 09-16; purge flow PASS. Low. [E] |
| 18-026-20 | 2018 Stelvio 2.0L ECM flash; lists P1CEA, P24D6, not P0440/P0455/P0456 | Applies. Whether performed unknown; ECM SW unchanged through 2026. [E] |
| 18-030-17 REV B / D | ECM flash listing P0440/P0441/P0455/P0456; NHTSA copy is Giulia 2017 only | Weakens the calibration branch: no Stelvio copy found (xref relation "weakens"). [E] |
| STAR S2125000002 | Recirculation quick-connect | Latched 09-26. xref labels it an analogue (Jeep JL, same engine family); EVAP_STELVIO.md treats it as the first Stelvio check, scope labels disagree in the repo. [E] |
| STAR S2025000004 | Dealer case record for P0456/P0455: run SLVT, keep original cap fitted | Needs VIN/dealer check. [E] |
| Recall 18V636, CSN W05 | Either would have reflashed the ECM | VIN check pending; settles "is the ECM current". [E] |
| Recall 19V551 | BCM misreports fuel level, BCM software update | Not verified for this VIN; relevant to the fuel-level input path (section below). [E] |
| Recall 18V205 | BCM water intrusion, MY2018 Stelvio (NHTSA build range 2017-03-20 to 2018-02-14) | VIN check pending; relevant to BCM-side network codes. [E] |
| Recall 25V586 / 93C | Fuel pump / fuel delivery module | If the module is replaced, verify the internal vapour line at the FDM port (9100471). [E] |

Analogues (same engine family or sibling platform, not Stelvio bulletins; xref `analogues`):

| Number | What it is | Relation |
|---|---|---|
| 18-014-20, 18-018-20 | Wrangler JL 2.0T PCM flashes that list P0456 as a flash-fixed code | Keeps the calibration question open on the sibling engine. [E] |
| 18-052-20, 18-161-22 | Cherokee KL 2.0L PCM flashes listing P0456 | Same. [E] |
| MAS003111 (MTB 22-15) | Maserati V6, P043E reference-orifice low flow: ECM calibration false detection | Precedent for an EVAP monitor false detection fixed in software at a sister brand. [E] |
| FIELD REPORT 3 | Jeep: ESIM replaced after dealer found it failed, cured P0456 | Retailer claim, not opened. Supports an ESIM-side fault. [E] weak |
| FIELD REPORT 4 | Renegade/500X: ESIM O-ring flattens, ESIM must mount vertically | Retailer claim, not opened. Relevant to ESIM mounting after the 09-02 swap. [E] weak |
| 14-005-22 Rev B, 18-035-20, 25-002-15 | Updated filler cap (Wrangler); fuel vapour hose not connected (Grand Cherokee/Durango); purge valve hose splits | Hose and cap precedents; all already covered by the smoke tests and inspections. [E] |
| 18-039-20 | Winter-blend fuel in warm weather | No relation on a 14 to 17 C night. [I] |

---

## BCM U1713-2F and the inputs to the EVAP monitor

**What U1713-2F means (repo knowledge).**
- `mes/dtc_descriptions.py` gives U1713 a generic entry only: "Network/communication cascade code naming BCM -- a lost-communication DTC, not a component-internal fault", same family as U1711/U1712/U1716/U2054/U0100/B1040, confidence SINGLE-SOURCE, sourced to `faulttree.py NETWORK_CASCADE` and CONNECTIVITY_AND_SGW.md. It has no entry for P0440/P0455/P0456 ("not sourced"). [E]
- MES's own scan text on this car: "U1713-2F - Engine control (NCM) - Signal/message erratic", listed under the BCM. FTB 2F = "signal erratic" (SAE J2012-DA / ISO 14229-1 table in `mes/dtc.py`). [E] So the BCM is reporting that messages it receives from the engine control module are erratic. The direction is ECM to BCM. [I] The dtc_descriptions wording "lost-communication" fits U1765/U0100 better than an "erratic" FTB; the two repo texts are slightly inconsistent. [I]
- The network-cascade tree says serial UDS sweeps and cable re-plugs manufacture -87/-2F bystander codes (SCAN_2609041953 is the example) and says to rescan with the engine running (N1) and pull DTC EX before clearing (N2). [E] Tonight U1713-2F was active with the engine running, so N1 does not clear it. DTC EX was captured at 00:25 but not decoded, and the clear at 00:39 prevents a repeat. [E]

**How it behaves on this car.**
- Present in 10 MES scans since 2026-06-07 (the first MES scan of this VIN, tonight's included) and live-active on 10-13 and in the CUORE reads tonight. Absent right after clears (10-14 19:02) and from 09-29, 10-04 and 10-08. [E]
- Of the 10 MES scans that listed an EVAP code on the ECM, 8 also listed U1713-2F; the two without are 09-29 and 10-08. U1713-2F was also present on 06-07 and 08-27 11:31 when the ECM list was empty (before the EVAP codes appeared in MES, and right after an ECM clear). [E] Co-occurrence only. Every one of these reads had a scan tool on the port, so tool-induced and real cannot be separated from this data. [I]
- Tonight's MES scan adds the usual cascade codes in DTCM (U0100-87, U0422-86) and DASM (C1408-86, U1702-87, C141C-86). TCM, IPC, ESM and RFHUB are clean. [E]

**Does the BCM supply fuel level or ambient temperature to the ECM's EVAP monitor? Not in repo.** What the repo does contain:
- No document or table lists the EVAP monitor's inputs or their source modules. [N]
- Fuel level: the ECM reports it itself (OBD PID 2F, MES "Fuel level", freeze-frame "Fuel level"). The ECM tracks fuel-level-sensor and EVAP-pressure-sensor codes (P0461, P0451, both 0x40; the repo does not describe these codes [N], they are SAE generic numbers). Recall 19V551 says the BCM misreports fuel level and is fixed by BCM software, which puts the BCM somewhere in the fuel-level chain. [E] (catalogue summary, unverified, VIN check pending) Whether the ECM's EVAP monitor reads the BCM's value or a hardwired sender is not stated. [N]
- Ambient: the ECM has its own air-temperature sensor (MES "Air temperature" with an "Air temperature signal" voltage line) and answers OBD PID 46 (14 to 25 C on 10-13 and 10-14, plausible). [E] The ECM also has an MES parameter "**External temperature**", which read a constant **-61 C in all 61 samples on 2026-06-07** while "Air temperature" read 30 C. [E] "Canister fill" was pinned at 50.00 % (24 samples) and the purge valve opening at 0.0 %. [E] "External temperature" and "Fuel level" have no companion "signal" voltage line, unlike the sensor-fed parameters, which is consistent with, but does not prove, CAN-delivered values. [I] That is the only direct hint in the repo of an ECM input that was invalid. It was read once, on one day, and not since. [E]
- The BCM 949 is the CAN-IHS to CAN-C gateway on this car (GIORGIO_MODULE_MAP.md). Body-bus data bound for the ECM would pass through it. [E]/[I]

---

## Remaining candidate causes on a sealed system

Working model (the repo's, see above): the ECM sees "sealed/vacuum" only through the ESIM switch; on this car it never does, and nothing leaks. Each candidate below says what supports or weakens it, the test that separates it, and what the result means.

**C1. Blocked or kinked tank-to-canister vapour path (hose, ORVR/FDM internal vapour line, recirculation line).**
- For: smoke tests cannot see a blockage [I]; 9100471's own tree lists a kinked tank-to-canister hose and an FDM-port line; this VIN is in the fuel-pump recall that opens the FDM. Against: normal refuelling with no early click-off [E] argues against a total blockage; no P2422 [E].
- Test: low-pressure air (see next tests, B) through each disconnected leg, both directions; during a repeat smoke test, confirm smoke visibly reaches the far end of each leg and record flow.
- Result: a leg that flows poorly or not at all is the fault. All legs free removes C1, C2, C3 together.

**C2. Blocked or kinked canister-to-ESIM or clean-air path (hose ESIM to filter, filter housing, the "valve at the canister").**
- For: 9100471 names the clean-air hose between the ESIM and the filter; only the filter itself was inspected [E]. Against: the filter flows clear; refuelling normal [E].
- Test: same as C1 on the canister-ESIM and ESIM-filter hoses; look for pinch at the wheel-liner area.
- Result: as C1. A restriction that only matters in the closed test state would pass the refuelling check [I].

**C3. Canister internal blockage.**
- For: platform base rate puts the canister first (EVAP_STELVIO.md rank 1, forum-grade). Against: the canister is new (2025-08); no fuel in it; refuelling normal [E].
- Test: air flow through the canister between its tank port and its vent port with the ESIM and hoses off, then the same with the purge port; compare with a new unit if one is on hand.
- Result: restricted flow = canister, replace (not the ESIM, per 9100469). Free = canister out.

**C4. ESIM mounting or port (orientation, O-ring, hose seating, sense port kinked or unconnected, wrong or defective new part).**
- For: the ESIM was swapped on 09-02 and P0440 was back by 09-04 19:53, 2.2 days later [E]; one retailer report says the ESIM must mount vertically and its O-ring degrades [E] weak; fitment 04861961AD never VIN-verified [E]. Against: none recorded either way; mounting was not logged [N].
- Test: with the ESIM in place, check orientation against the old unit's position and the parts diagram, port seating and every hose it carries; bench test against a known-good unit (esim_bench_test); Test A (below).
- Result: a mis-seated or wrongly mounted unit is fixed by reseating; a unit that fails the bench test is replaced. A unit that behaves like a new one on the bench moves the case to C5/C6/C7.

**C5. ESIM switch (contacts never close, close too late, or do not hold).**
- For: nothing measured yet. The Mode 06 failure is consistent with it but not specific. [I] Against: new part [E].
- Test: Test A: hand vacuum at the ESIM port, watch the ECU's switch state; closes, holds about 30 s, reopens on release, repeat three times, wiggle test.
- Result: never closes with a good hand pump and a tight hose = ESIM switch or its mounting (C4), unless the circuit is open (C6; the wiring test B5 jumper separates them). Closes, holds, reopens cleanly = switch, connector, wiring and ECU input all work, which sends the case upstream (C1 to C3 blockage, vacuum never reaching the ESIM in service) or to C7/C8.

**C6. ESIM-to-ECM circuit (connector behind the driver-side rear wheel liner, pins, ground, high resistance, ECM input).**
- For: no ESIM circuit DTC has set, so an intermittent or high-resistance fault is likelier than a clean break (CASE.md). The connector sits in the wheel-well splash area; the repo records BCM-side water-intrusion recalls as a platform theme. Against: nothing measured. [N] for pin-out and wire colours: no wiring diagram in repo (Stelvio ESIM Wiring Diagram Lookup sheet is a to-fill form).
- Test: ESIM wiring test B1 to B5 (connector, reference voltage, ground, end-to-end, jumper), with wiggle; B5 stays open with good B2 to B4 = ECU input.
- Result: out-of-range B2 to B4 = repair that circuit; flicker on wiggle = intermittent connector/chafe; B5 closes in wiTECH while Test A failed = the ESIM contacts, not the wiring.

**C7. ECM input or calibration (monitor logic, thresholds, input stage).**
- For: calibration status unknown; sibling-engine flashes list P0456 (18-014-20, 18-018-20, 18-052-20, 18-161-22) and a Maserati bulletin fixes a false EVAP detection in software [E]. Against: no Stelvio bulletin lists the EVAP leak codes (18-026-20 does not; 18-030-17 is Giulia-only); the SW number is higher than any publicly indexed MM10JA calibration, so it was probably reflashed already (project notes, inference, only wiTECH confirms) [I].
- Test: wiTECH ECM Flash tab: Current vs New ECU part number; VIN checks for 18V636 and W05.
- Result: a newer calibration = flash per 18-026-20, then the SLVT (18-048-23) as proof. Already current, with Test A and the air checks clean, makes the calibration the leading suspect with no bulletin behind it.

**C8. CAN inputs to the EVAP monitor, including the BCM U1713-2F interplay.**
- For: U1713-2F is active in the same cycle; 8 of 10 EVAP-positive MES scans carried it; an implausible "External temperature" (-61 C pinned) was logged on 06-07; BCM is the gateway; recall 19V551 puts the BCM in the fuel-level path. Against: the direction of U1713-2F is ECM to BCM, opposite to the inputs the monitor needs [I]; U1713-2F was absent in 09-29 and 10-08 when EVAP codes were present [E]; PID 46 ambient and fuel level read plausibly in October [E]; no document links any BCM signal to the monitor [N].
- Test: with the engine running and ambient known, read MES "External temperature" and "Fuel level" live and compare with the dash outside temperature and fuel gauge; repeat while U1713-2F is active. For the network side follow the cascade tree: BCM supply and fuse F82, XY201 and grounds G003A/B, terminal tension, with DTC EX captured before any clear.
- Result: an invalid or frozen External temperature (-61 C) or a wrong fuel level on the ECM side = look at the BCM/gateway path and consider recall 19V551 and BCM software; plausible values with the codes still returning removes C8 as the common cause. A shared power/ground/CAN fault would show on more than EVAP and U1713 [I].

**C9 (low). Purge-side vacuum supply.** Valve replaced, 18 actuator runs, purge-flow Mode 06 PASS. [E] Retest only if A and B pass.

**C10 (added 2026-10-19, job hypothesis 8c659dfc). EVAP monitor inputs invalid: ECM external temperature pinned at -61 C, BCM U1713-2F "ECM signal/message erratic" since June.** A narrower form of C8 built around the one logged invalid value. The claim: ambient temperature and fuel level reach the ECM over CAN, the engine-off cold-soak vacuum test depends on them, and a sealed system with corrupted inputs would fail all three EVAP tests. No document in the repo names the EVAP monitor's inputs or their source modules, so the dependency itself is an assumption. [N]
- For: the ECM parameter "External temperature" read -61 C in all 61 samples of `FESLog_2606071008` (MES, 2026-06-07, 10:03 to 10:08; first sample line 271, last line 5045) while "Air temperature" read 30 C in the same log; it has no companion signal-voltage line, which fits a CAN-delivered value but does not prove it. [E]/[I] U1713-2F (BCM, "Engine control (NCM) - Signal/message erratic") is active tonight at 0x0F and is listed in 10 MES scans from 2026-06-07 to 2026-10-19. [E] Three clean smoke tests while all three EVAP tests fail. [E]
- Against: none attached to the job. Caveats on record: the -61 C value has been read once, on 2026-06-07, and not since [E]; U1713-2F was not listed in the 2026-09-29 and 2026-10-08 scans although EVAP codes were present, so it is not in every scan [E]; PID 0x46 (ambient) read 14 C at 2026-10-14 19:01 (store `pids_snapshot`) and the 2026-10-13 freeze frame carried ambient 17 C, both plausible [E]; U1713-2F is logged by the BCM about messages from the engine control module, the opposite direction to BCM-to-ECM inputs [I]; whether the "External temperature" parameter feeds the EVAP monitor is not established [N].
- Test: on the next connection read the ECM external temperature parameter (UDS DID via the MES parameter list, or PID 0x46) and the BCM's own ambient value, and compare both with the real outside temperature; add PID 0x54 if the ECM answers it. No MES log in the repo shows a BCM ambient parameter, so the BCM-side parameter name is not known. [N]
- Result: ECM value invalid while the BCM's is right = the BCM-to-ECM CAN data path or the ECM's reception is the cause (then the network side of C8 and recall 19V551 apply); both right = refuted.

---

## Next tests in order

Standing rule: **do not clear again.** Every clear restarts the evidence and has been followed by the same codes within 0.4 to 11 days. After the 00:39 clear expect the codes back in about 5 days (4.6 and 5.4 days were the last two); when P0440 reports 0xCD again, read **Mode 06 first**, before anything else, because tonight it was missed. Fix the NO DATA route (10-13 note: this car answers legislated OBD on the 29-bit 18DB33F1 route) before then. [I]

Added later on 2026-10-19, first in order because it is one live read:

**E. Read the EVAP monitor's ambient inputs on the next connection (hypothesis 8c659dfc, C10).**
- Read the ECM external temperature parameter (UDS DID via the MES parameter list, or PID 0x46) and the BCM's own ambient value; compare both with the real outside temperature. Add PID 0x54 (EVAP vapour pressure) if the ECM answers it; it answered on 2026-10-14 19:01 with 0.0 kPa. [E]
- Result: ECM invalid and BCM right = the BCM-to-ECM CAN data path or the ECM's reception; both right = hypothesis 8c659dfc refuted. It overlaps D (same External temperature read) and can be done in the same sitting.

The hypothesis's own 7-step next_test, unchanged:
1. VIN checks, no tools: dealer / Mopar lookup / Transport Canada for recall 18V636 and CSN W05; record answer and date.
2. wiTECH, ECM Flash tab: record the current ECM calibration part number and the latest available.
3. If outdated: flash per TSB 18-026-20; record before/after part numbers; run the wiTECH SLVT (18-048-23) as proof of fix. Stop if it passes and the codes stay away.
4. If current: drive until the EVAP monitor reports complete (cold start, fuel 1/4 to 3/4, 20+ min steady cruise, long engine-off soak); check readiness in CUORE after each drive. Never clear.
5. After the monitor has run, read in CUORE: P0440/P0456 status bytes, Mode 06 EVAP 0.090 in and 0.020 in tests (values vs limits), readiness.
6. Decide: P0440 sets with Mode 06 leak tests passing = signal path confirmed, then ESIM circuit (connector pins, ground and signal continuity per diagram, back-probe the switch signal while applying vacuum). A Mode 06 leak-test failure = a leak, then SLVT and a fourth sectioned smoke test.
7. Record every step on this job with date, values and meaning before the next.

Added on 2026-10-19:

**A. Hand vacuum at the ESIM port while watching the switch state (wiTECH Test A, with CUORE/MES watching what they can).**
- What CUORE and MES can and cannot show [E]: the ESIM switch has **no readable DID** (`esim_status` is a non-pollable placeholder; the ESIM function is a 0x31 RoutineControl that CUORE refuses). MES's ECM parameter list has no ESIM switch either, only "Evaporation control valve opening" and "Canister fill". So the switch state itself must come from wiTECH (parameter name not known [N]) or a meter across the switch circuit (wiring test B5).
- What CUORE can add [E]: the ECM supports **PID 0x54 (EVAP vapour pressure, signed kPa)** (read 0.0 kPa on 10-14 19:01), plus 2E purge duty and 2F fuel level. Log PID 54 at the highest rate the adapter allows during the pump test as a proxy for vacuum reaching the ECM's pressure sensing. Whether that sensor is the one the ESIM test uses is not in the repo [N], so treat a PID 54 response as supporting evidence only.
- Procedure: engine off and cool, only one tool on the OBD port (MES and CUORE share COM3; the repo says MES holds it while connected); driver-side rear wheel liner; leave the ESIM plugged in; baseline, then hand pump on the canister-side port, hold 30 s, release, three times, wiggle the connector while held. Hand vacuum only, never shop air, no sparks (fuel vapour).
- Result: see C5. Clean on every run moves the case upstream (B) and to C7/C8.

**B. Check the vent and recirculation path for blockage with low-pressure air, not smoke.**
- Purpose: smoke shows leaks, this shows continuity. [I]
- Procedure: engine off, ESIM and canister disconnected from the legs under test; at most hand-bulb or lung pressure, or a regulated source at the EVAP-machine level of about 0.5 psi (EVAP_SMOKE_TEST.md, `[practice]`, not an FCA figure); never through the ESIM body and never shop air. Legs: tank-to-canister vapour hose; recirculation line including the mid-point quick-connect; canister-to-ESIM; ESIM-to-filter clean-air hose and the filter housing; then through the canister, tank port to vent port. Each leg should pass air freely both ways with no kink or pinch. Record which leg, how it felt, photos.
- Also on the next smoke test: record the flow reading at every step, and note where smoke is seen to arrive (filler neck, canister ports, ESIM port).
- Result: any restricted leg is the fault (C1 to C3). All free leaves C4 to C8.

**C. If A fails or is ambiguous:** ESIM wiring test B1 to B5, then bench test (esim_bench_test) against a known-good unit.

**D. CAN-input check (C8):** MES live "External temperature" and "Fuel level" against dash readings; BCM DTC EX on U1713-2F before any clear; recall 19V551 and 18V205 VIN checks added to step 1.

**Suggested run order:** E first (one live read), then 1 and 2 (same sitting, no hardware beyond wiTECH) then A (same wiTECH session), then B, then 3 if outdated, then C and D as the results require, with 4 to 6 running in the background whenever the codes return. Record each result on the job with date and values (step 7).

---

## Gaps and inconsistencies found in the repo's own records

- The session record says "1,663 km and 8 warm-ups since the 29 Sep clear; 34 km with MIL on" for 2026-10-13. The stored 10-13 read has PID 21 and PID 31 empty or NO DATA, and a successful ECM clear on 2026-10-08 09:2x sits between 09-29 and 10-13. Those three figures cannot be traced to a stored read; treat them as unverified. [E]
- The project note says "two clean smoke tests"; the job holds three (2025-08, 09-16, 09-26). [E]
- Hypothesis ce6bd236 says the 0.020 in test "FAIL 6096 ms vs min 0 ms"; the stored limits are min 0, max 6000, value 6096 (over the maximum). [E]
- `cuore/live/mode06.py` `evap_summary` prints the MAX limit for every test (404 ms "vs limit 65535 ms") and reports NO DATA as "not supported by this ECU". Both are misleading wording; the job entries quote the correct minimum. [E]
- xref and EVAP_STELVIO.md disagree on whether STAR S2125000002 is a Stelvio or an analogue bulletin. [E]
- `dtc_descriptions.py` calls U1713 a "lost-communication" code; its FTB 2F is "signal erratic". [E]

## Sources

Observation store `C:\ProgramData\cuore\observations.jsonl` (kinds module_dtcs, obd_dtcs, readiness, mode06, dtc_detail, pids_snapshot, module_identity, scan_coverage); job store `C:\ProgramData\cuore\jobs.jsonl` (job 76d3454bce75: 25 actions as of 2026-10-19 00:55, hypotheses bc8987f8 (soft-deleted reviewer test data), ce6bd236 and 8c659dfc); MES logs in `C:\Program Files (x86)\MultiEcuScan` (SCAN_26*.txt, FESLog_26*.txt) read through `mes.analysis`, `mes.catalog`, `mes.fes`; `cuore.services.tsb_xref_bridge.xref`; `cuore/data/tsb_catalogue.json`; `docs/research/EVAP_STELVIO.md`, `EVAP_SMOKE_TEST.md`, `GIORGIO_PLATFORM.md`; `docs/vehicles/ZASFAKPN5J7B88115/CASE.md`, `sessions/2026-10-07-session-record.md`, `reports/2026-10-13-scan-health-report.md`; `docs/reference/GIORGIO_MODULE_MAP.md`; `mes-log-mcp/mes/dtc_descriptions.py`, `faulttree.py`, `mechanic_tests.py`, `parts.py`.
