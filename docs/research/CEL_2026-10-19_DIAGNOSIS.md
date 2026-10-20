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

---

## Also considered (2026-10-19)

Four more hypotheses were added to job 76d3454bce75 after the write-up above, each open with no test result. Tags as at the top: [E] evidence, [I] inference, [N] unknown. Reasoning order: H-A first, because its test is the cheapest (one MES actuator command with a back-probe at the ESIM connector, no parts) and it appears to explain all the data at once [I]; then H-C (a lookup that can promote H-A), H-B, H-D.

**H-A (02c3c411): ESIM solenoid (commanded vent) circuit or ECM driver never closes the vent.** The ESIM is taken to hold a switch that reports vacuum and a solenoid the ECM energises to seal the vent for its tests [I]; no FCA description confirms that split on this car [N]. If the solenoid or driver never works, no vacuum can build after a refuel (P0455, idle, 91.8 % fuel), in a cold soak (P0456, engine off, 17 C) or while driving (P0440, 3rd gear), the three frames of 2026-10-19 [E]. Three clean smoke tests and two ESIM units gave the same codes [E], which points at what the unit plugs into rather than the unit [I]. The repo's MES catalogue lists an "ESIM commanded vent test" (forum-corroborated) [E]; that this car's MES shows it on the ECM Actuators tab is not observed [N]. It was never run: the only EVAP actuator in the MES logs is "Evaporation control valve" x18, and the store's two actuator_test records are synthetic [E]. Against: none recorded; no circuit code (P2422 and others) has set, but whether the ECM monitors this driver is unknown [E]/[N]. Confirm: run the test with the solenoid back-probed; no click or no current means solenoid, wiring or driver, a click refutes. Next: then continuity from the ESIM connector to the ECM pin (no wiring diagram in the repo [N]).

**H-B (4408d755): ECM supply/ground or resets.** BCM U1713-2F is listed in 10 scans since June and ECM "External temperature" read -61 C in FESLog_2606071008 [E]; a marginal ground or supply, or resets mid-test, would abort the monitors [I]. Against: on 2026-10-13 all monitors completed and Mode 06 returned real values, and the freeze-frame voltages look normal [E]. Confirm or refute: ECM ground strap and connector voltage drop under load (workshop limit not in repo [N]); startup counter (frames 14603, 14608, 14612) against a counted number of real starts; U1713 freeze-frame timing. The raw BCM U1713-2F frame (store dtc_detail 00:25:39) is the only copy and is not yet decoded [E].

**H-C (f15ffa4f): P0440 definition.** MES names P0440 "Evaporation control valve" and P0455/P0456 "Evaporation system leak" [E]; P0440 alone carries the lamp bit (0xCD) [E]; the repo has no verified FCA definition [N]. If P0440 is the ESIM control-circuit code, H-A becomes the lead [I]. Confirm: obtain the FCA definition (dealer, wiring diagram, bulletin text) and record it; until then unknown.

**H-D (9d8bb433): modifications or environment.** No intake, PCV, catch-can, tune or aftermarket-part change is recorded, and the per-car modifications ledger does not exist yet [E]; whether any exists is unknown, not excluded [N]. ECM software unchanged through 2026 and a passing purge-flow Mode 06 argue against some forms [E]/[I]. Confirm: ask the owner, record the answers (or "none") in the modifications ledger, and inspect the purge and intake path.

Job action 7a84b151 (note) records the four and this order.

---

## Mode 06 EVAP records: unit, scaling and what 404 and 6096 can mean (added 2026-10-19, web research)

Built from the stored 2026-10-13 20:03:54 `mode06` observation (raw ISO-TP frames, ECM reply address 18DAF110) and five web searches plus page fetches. No car access, no new reads. Tags as at the top: [E] evidence, [I] inference, [N] not known.

### M1. The two failing records, byte by byte [E]

Record layout (J1979 CAN, as decoded in `cuore/live/mode06.py`): OBDMID, TID, UASID, value (2 bytes), min (2), max (2). Source: store kind `mode06`, `data.raw["3A"]` and `data.raw["3C"]`.

| Test | Raw frames (after the 18DAF110 header) | OBDMID | TID | UASID | value | min | max |
|---|---|---|---|---|---|---|---|
| 0.090 in | `10 0A 46 3A 87 10 01 94` then `21 0F 7D FF FF` | 0x3A | 0x87 | 0x10 | 0x0194 = 404 | 0x0F7D = 3965 | 0xFFFF = 65535 |
| 0.020 in | `10 1C 46 3C 85 34 00 00`, `21 00 00 00 00 3C 86 12`, `22 00 00 00 00 00 00 3C`, `23 90 10 17 D0 00 00 17`, `24 70 ...` | 0x3C | 0x90 | 0x10 | 0x17D0 = 6096 | 0x0000 = 0 | 0x1770 = 6000 |

- The 0x3C reply holds three 9-byte records: TID 0x85 (UASID 0x34) and TID 0x86 (UASID 0x12) are all zero (value 0, min 0, max 0); TID 0x90 is the failing one. The 0.020 limits are therefore min 0, max **6000**, and the value is 96 over the maximum. [E]
- The 0.090 limits are a minimum of 3965 and no upper bound (0xFFFF is the usual "no limit" fill). The value is 3561 under the minimum. [E]/[I]

### M2. UASID 0x10: unit and scaling

- UASID 0x10 = time in **milliseconds, 1 ms per count, unsigned 16-bit (0 to 65535 ms)**. Bit 0x80 is clear, so not the signed mirror. Raw-to-value: value_ms = raw x 1. Not counts, not kPa. [E]/[I]
- Support: the repo's `_UASID_TABLE` (0x10 = ms, 1.0), which the module author marks as a confident entry; and a GM Mode $06 reference as summarised by a search result: "UASID 0x10 means 1 ms per bit ... 0 to 65535 ms", with 0x24 = 1 count per bit (https://gsitlc.ext.gm.com/gmspo/mode6/pdf/GM%20CAN%20mode%20$06%20data%20final_dm.pdf; direct fetch returned HTTP 403 so the table itself was not read; the document describes itself as for information only). The authoritative table is SAE J1979-DA (https://saemobilus.sae.org/content/J1979DA_202203), paywalled, not read. Wikipedia's OBD-II PIDs page has no UASID table (checked). So the unit rests on two sources but is not checked against the SAE text.
- `mode06.py` already decodes both records correctly; no code change needed.
- The declared unit is the ECM's own claim in the UASID byte. A maker can reuse an ID for something else; nothing found says FCA does. [N]

### M3. Two record-level caveats found while decoding [E]

- **Gross-leak MID 0x39 is a zero-limit record, not a measured pass.** On 2026-10-13 it read TID 0x87, value 0, min 0, max 0 (and the same on 10-14). 0 sits inside 0..0, so the decoder prints PASS, but the ECM published no limit and no result. The "gross leak PASS" in the timeline and in the Mode 06 row of the repairs table rests on this and should be read as "no information". [I]
- **Reset state, 10-14 19:01 (after the 10-14 08:59 clear):** 0x3A read 0/0/0 (limits wiped as well). 0x3C TID 0x90 read value **6000**, min 0, max 6000, so after a reset the value equals the maximum. That "PASS" on 10-14 is a reset artefact. The 10-13 value (6096) differs from the reset value, so it was written by a test, not left over from a reset. Whether 6000 is a preload, a ceiling or a timeout is not stated anywhere found. [E]/[I]/[N]

### M4. What the two tests measure on an FCA ECM: unknown

No source found states what OBDMID 0x3A TID 0x87 or OBDMID 0x3C TID 0x90 measures on a Chrysler/FCA ECM. Searches ("Chrysler mode 6 EVAP NVLD TID", "ESIM mode $06 0.020", UASID table, "OBDMID $3A 0.090 TID $87") returned only general ESIM/NVLD material. TIDs 0x80 and up being manufacturer-defined is taken from the brief; no page found states it. **Quantity: unknown for both.** [N]

What the sources do say about the ESIM/NVLD tests, none of it Mode 06 and none of it naming a TID:
- The switch is vacuum operated and normally open; it "closes with as little as 1" H2O" of vacuum. During an intrusive test the PCM must pull enough vacuum to close it. After the switch closes the PCM "will start an internal decay timer to determine the actual size of the leak". (FenderBender, NVLD, https://www.fenderbender.com/running-a-shop/operations/article/33024148/diagnosing-and-repairing-nvld-systems-can-present-unique-challenges; the page does not say how the timer is read out.)
- ESIM: "when fuel tank vacuum reaches 1 in. of water, the switch closes". Large-leak test: manifold vacuum applied through the purge valve, and "the PCM measures the time required for the vacuum to decay enough for the NVLD or ESIM switch to open"; a switch that never closes "could mean there's a leak" or a purge problem. Small-leak test: starts after shutdown, watches for switch closure, "can take several hours". The article names time to switch closure/opening and vacuum decay time as the measured quantities but gives no numeric limits and no Mode 06 mapping. (Vehicle Service Pros, https://www.vehicleservicepros.com/industry-news/article/53090062/chrysler-evap-performance-codes-2016-10-13)
- NVLD on the older LH platform: about five minutes to build 1 in. H2O of vacuum; the switch monitor may run half an hour before aborting. (FenderBender, https://www.fenderbender.com/running-a-shop/operations/article/33025468/evap-testing-working-behind-the-scenes; NVLD, key-off, not ESIM, not Mode 06.)
- Other makers differ for the same OBDMID: a Saab Trionic 8 table lists MID $3A TID $81 and MID $3C TID $83 as "EVAP monitor leak factor", 0 to 65535 counts, 1 count/bit (https://saabwisonline.com/9-3-9440/2009/2-engine/4-cyl-petrol-e85/engine-management-system-trionic-t8/technical-data/trionic-8-mode-06). Not FCA evidence; it shows the same OBDMID can carry a different quantity per maker.
- A forum-posted "Enhanced Evaporative System Monitor #2 (0.020" Leak)" table (TID 0A, CID 06 = 0.020 leak, CID 05 = 0.040) is the pre-CAN TID/CID format, names no maker and gives no units; it does not apply to a CAN OBDMID/TID record (https://forum.ih8mud.com/threads/pendragon.914649/page-6).
- Older Chrysler LDP timing bands (under 0.9 s gross, 0.9 to 1.2 s medium, 1.2 to 6 s small) belong to the leak detection pump, not the ESIM; not used here (https://www.brakeandfrontend.com/pulling-codes-the-story-of-code-p0456/, as summarised by a search result; direct fetch 403).

### M5. What the stored limits and timescales add [I]

- The limits point in opposite directions: 0.090 TID 0x87 passes at **higher** values (at least 3965 ms); 0.020 TID 0x90 passes at **lower** values (at most 6000 ms). One quantity cannot be "higher is better" in one test and "lower is better" in the other, so the two TIDs probably measure different things.
- A key-off small-leak closure takes minutes to hours in the sources above. A 6.1 s or 0.4 s figure therefore is not the whole key-off closure time; it could be an engine-running purge-vacuum timing (the large-leak method in the Vehicle Service Pros article) or a sub-interval such as a decay timer. The TID mapping for this ECM remains unstated.

### M6. What each reading implies about the ESIM switch ever closing, by candidate meaning

Candidates are the ones the question named. None is confirmed for these TIDs [N].

| Candidate meaning of the ms value | 0.090 test, TID 0x87: 404 (needs >= 3965) | 0.020 test, TID 0x90: 6096 (needs <= 6000) |
|---|---|---|
| A. Time from vacuum applied to switch closure | Closure at 0.4 s. The switch closed. Limit shape contradicts it: a minimum on a closure time would fail the best case, so A is unlikely here. | Closure at 6.1 s, 96 ms late. The switch closed, late. Limit shape fits. Fits only an engine-running test (M5). |
| B. Time the switch stayed closed / vacuum decay time until it reopened | The switch closed, then reopened after 0.4 s against a 4.0 s requirement. Closed but did not hold (leak, restriction or loss after closure, or contact chatter). Limit shape fits. | Held for 6.1 s, yet the limit is a maximum: a longer hold would be the good direction. Shape contradicts it, so B is unlikely here. If it held, the switch closed. |
| C. Counts (leak-factor style, as the Saab table) | No closure information. Contradicts the declared UASID 0x10 (ms). | Same. |
| D. Anything else, including the elapsed wait stored when the switch never closes | Compatible with never closed only if FCA stores a value on a no-closure abort. No source says so. [N] | Same. The reset value is exactly 6000 (M3), so a 6096 is not that value. |

Reading across the table [I]:
- Under A and B every nonzero value requires at least one closure event. Under C nothing can be said. Only D, with an undocumented stored-on-abort behaviour, lets either number mean "never closed".
- The most self-consistent pair by limit direction is 0.090 = a hold/decay-type time that was too short, and 0.020 = a closure-type time that was slightly too long. Both would then say the switch input did change state in the 10-13 tests. That is a fit to limit shape only, not a source.
- **The stored Mode 06 data does not show that the ESIM switch never closed.** The statement in the freeze-frame section above ("the switch closure was never seen by the ECM") and the "never closes" wording in C5 are not supported by this record, though not refuted either; they rest on the codes (P0440/P0455/P0456), not on Mode 06. If A or B holds, a dead switch or an open circuit is less likely than a closed-then-lost or late-closing vacuum (C1 to C4, C7). This does not separate H-A (a vent that does not seal could let vacuum form briefly and decay [I]) from the blockage candidates.
- One refinement to the repairs table: "read as a hold or decay time it means vacuum was absent or lost within 0.4 s" should read "lost within 0.4 s of closure"; "absent" is not implied by B.

### M7. What would settle it (no clearing, no new hardware)

1. The FCA test-ID description for MID 0x3A TID 0x87 and MID 0x3C TID 0x90 on this ECM: wiTECH or dealer service information. Not found in public sources. [N]
2. On the next return of P0440 0xCD, read Mode 06 first (standing rule above) and store the raw frames. A measured quantity varies between reads (compare against 404 and 6096); a fixed sentinel repeats.
3. During Test A (hand vacuum at the ESIM port), read Mode 06 0x3A and 0x3C before and after one pump cycle; a changed 0x3A value after a deliberate closure tests candidate B directly.

Searches used: five (standard mode). Fetches that failed: GM Mode $06 PDF (403), Brake & Front End article (403), motor.com Advanced Mode $06 PDF (unreadable binary).

---

## Stage 1 from archived data, 2026-10-19

Compiled 2026-10-19 about 01:15 from files already on disk: no car access, no new reads, no web, no owner statements, no weather lookup. Stage 1 names two live reads that have not been made: (1) ECM external (ambient) temperature and fuel level against the body module's own values; (2) the ESIM switch state. This section says what the archive already answers for each. Tags as at the top ([E] evidence, [I] inference, [N] not known), plus a grade per conclusion: STRONG (several independent reads agree), WEAK (few reads or one source), NONE (no data in the archive). Mode 06 meaning is not repeated here: see M3 and M6 above.

### S0. What was searched, and what exists

- MES folder: 92 FESLog and 23 SCAN files, read with `mes.fes.load_fes` (`param_names`, `series`, freeze frames, actuator runs). No CSV export exists on disk (MES folder and home folder to depth 4); `mes/csvlog.py` says the same. [E]
- Live parameters exist for this VIN in exactly one FES log: FESLog_2606071008 (2026-06-07 10:03:48 to about 10:08, ECM, 99 samples, engine idling). The three other FES logs with samples (2510150207, 2510150219, 2510271230) are flagged simulation (VIN 5188214) and carry no external-temperature or fuel-level parameter. [E]
- No BCM or IPC live data exists: FESLog_2606070955 (BCM 949) is an identity header with no parameter block; SCAN files hold identity and DTC lines only. No MES header holds weather (headers carry version, time, vehicle, ECU, VIN, serials, counters), so no per-date weather is given. [E]
- Store (`cuore.live.store.recent_observations`, this VIN, all from-car): pids_snapshot 4 (only 2026-10-14 19:01:35 has values; the two of 10-19 are empty), did 21 (ECM 1302 and 19BD, TCM 04FE, BCM 1004 and 1005), `module_did` 0 (no record of that kind exists), dtc_detail 5, mode06 5. Outside the store: `C:\ProgramData\cuore\live_snapshots.jsonl` (live-board snapshots 2026-10-13 20:09:08 and 20:38:32) and `docs/vehicles/ZASFAKPN5J7B88115/sessions/2026-10-13-live-read.json` (Mode 02 frame and live PIDs). [E]
- No DID or PID for BCM ambient temperature or BCM fuel level has ever been read, and the repo's DID tables have none (ECM 1001 fuel tank level and 1956 atmospheric pressure only). [E]

### S1. Part 1: ambient temperature and fuel level, ECM versus body module

Ambient / external temperature, every value on record:

| Date, time | Channel | Value | Source | Engine state |
|---|---|---|---|---|
| 2025-09-24 | MES freeze-frame "Air temperature" (intake, not external) | 15 C; 20 C | FESLog_2509241345 | cold start (ECT 16 C); engine-off frame (ECT 25 C) |
| 2026-06-07 10:03 to 10:08 | MES live "External temperature" | **-61 C in 61 of 61 samples** | FESLog_2606071008 | idle 742 to 759 rpm, ECT 89 to 96 C, 0 km/h, 14.0 V |
| same log | MES live "Air temperature" | 30 to 33 C | same | same |
| 2026-08-27, 08-31, 09-02, 09-25 | MES freeze-frame "Air temperature" | 25/22/29; 26; 23/25; 15/22/13 C | FESLog_2608271119, 2608311823, 2609021454, 2609252002 | mixed (cold-start idle and driving) |
| 2026-10-13 about 20:00 | OBD PID 46 in the Mode 02 frame | 17 C | live-read.json | 217 s after start, ECT 63 C |
| 2026-10-13 20:03:23, 20:09:08, 20:38:32 | OBD PID 46, live | 25, 25, 24 C | live-read.json, live_snapshots | idling, ECT 101 to 103 C; 1834 s, 2134 s, 211 s since start |
| same two snapshots | RFHUB tyre temperatures (body module) | 27 to 30 C; 27 to 34 C | live_snapshots | after driving |
| 2026-10-14 19:01:35 | OBD PID 46 | 14 C | store pids_snapshot | 74 s after start, ECT 72 C, 795 rpm |
| 2026-10-19 00:25 | freeze-frame intake air temperature (DID 1935, medium scaling) | 17 C; 16 C; 10 C | store dtc_detail | P0455 idle; P0456 engine off, cold soak; P0440 driving |
| 2026-10-19 00:33:38 | BCM DID 1005 byte G minus 40 (formula unverified) | 15 C | store did | engine running; battery-sensor temperature, not an ambient channel |

Fuel level, every value on record (ECM only; no BCM, IPC or gauge value exists):

| Date | Fuel % (odometer km) | Source | Engine state |
|---|---|---|---|
| 2025-09-24 | 73.73 (114,008.9); 55.69 (114,116.9) | MES freeze frames | cold start 1307 rpm; engine off |
| 2026-06-07 | 84.7 in 19 of 19 samples (136,536.7) | MES live | idle 750 rpm |
| 2026-08-27 | 51.76 (140,471.2); 46.67 (140,565.5); 46.67 (140,572.6) | MES freeze frames | 24 km/h; 36 km/h; cold-start idle |
| 2026-08-31 | 63.92 (140,883.2) | MES freeze frame | warm idle |
| 2026-09-02 | 48.63 (141,005.6); 43.92 (141,059.1) | MES freeze frames | cold-start idle; 34 km/h |
| 2026-09-25 | 93.73 (141,929.9); 91.76 (142,227.2); 80.00 (142,289.9) | MES freeze frames | 51 km/h; 40 km/h; cold-start idle |
| 2026-10-13 | 28.6 (Mode 02 frame); 20.8 (about 20:00); 20.0 (20:09:08, 146,501.2); 17.647 (20:38:32, 146,509.9) | PID 2F; at 20:09 and 20:38 DID 1001 gave the same 20.0 and 17.647 | idling, ECT 101 to 103 C |
| 2026-10-14 19:01 | 93.725 | PID 2F | idle 795 rpm, 74 s after start |
| 2026-10-19 | 91.76 (146,522.2); 62.75 (146,726.6); 55.69 (146,755.7) | ECM freeze frames, DID 1001 raw EA, A0, 8E | idle; engine off, cold soak; driving 3rd gear |

How the fuel series behaves [E]: 20 readings on 9 dates. Between points where no refill is needed the level falls 5.4 to 27 points per 100 km (median about 15, about 8 L/100 km if the tank is 53 L, the repo's unverified figure). It rises where a refill must have happened: 08-27 to 08-31 (+17.3 points over 311 km), 09-02 to 09-25 (+49.8 over 871 km), 10-13 20:38 to the 10-19 P0455 frame (+74 over 12 km, with 93.7 % read at 10-14 19:01 between), and net over 06-07 to 08-27. The 06-07 value is constant because five minutes of idle burns about 0.14 points, below the 0.39-point resolution. Two segments do not fit a simple burn rate: 08-27 (5.4 points per 100 km, about 3 L/100 km) and 09-25 P0455 to P0440 (-1.97 points over 297 km, so a refill or top-up must have happened between the frames; none is recorded). DID 1001 equals PID 2F at both 10-13 snapshots, which supports the A*100/255 scale used for the 10-19 freeze frames. The ECM tracks fuel-level performance codes P0461 and P2066 and both read 0x40 (never failed) in every ECM read on record. [E]

**Conclusion 1a. Is the ECM's external temperature valid on any date other than 2026-06-07?**
- Facts: the MES parameter "External temperature" was read on one date only (06-07, -61 C, 61 of 61, while "Air temperature" read 30 to 33 C). The same log shows other values that contradict the car's state: "Ignition key position: Stop" in 19 of 19 samples with the engine at 742 to 759 rpm and 14.0 V; "Relative humidity (MAF)" and "Atmospheric pressure signal" print a unit and no number. The BCM was cleared at the 09:54 scan and the 10:03 scan listed no BCM codes, so the -61 C (from 10:03:48) was read with no U1713-2F listed. The ECM's own ambient over OBD (PID 46) read 17, 25, 25, 24 C on 10-13 and 14 C on 10-14: plausible and not constant.
- Inference: the archive can say neither "valid on another date" nor "invalid on another date" for the MES parameter. PID 46 is not a proven match for MES "External temperature" [N]. The 17 C (217 s after start) against 24 to 25 C (hot idle, same evening) fits heat soak of the sensor or its air rather than a stuck value [I]. Several MES values on 06-07 were wrong or blank at once, which fits MES showing placeholders for channels this ECM does not publish as well as it fits a bad CAN input [I].
- Unknown: whether MES "External temperature" and PID 46 are one signal; whether -61 C persists; what the BCM and the cluster show for outside temperature (nothing of theirs was ever read); the real outside temperature on any date (no log records it).
- Grade: validity of MES "External temperature" on any other date NONE (one date). PID 46 plausibility WEAK (five values, two days, one source, no outdoor reference); the tyre temperatures of 27 to 34 C after driving do not contradict PID 46 of 24 to 25 C, WEAK.

**Conclusion 1b. Does fuel level reach the ECM plausibly, against freeze-frame fuel 91.8 / 62.7 / 55.7?**
- Facts: as tabulated. The three 10-19 values fall 29.1 points over 204.4 km (14 per 100 km) and 7.0 points over 29.1 km (24 per 100 km, cold start and short trips), after a refill from 17.6 % on 10-13.
- Inference: the ECM's fuel value is live and tracks consumption and refills, so it is neither frozen nor a default [I]. That says nothing about its source (hardwired sender, a BCM or fuel-module message, or the cluster). Recall 19V551 (BCM misreports fuel level) cannot be tested here, because a fixed offset or non-linearity would not show in this series.
- A side finding: three EVAP codes set above the repo's working 15 to 85 % window (09-25 P0455 at 93.7 and P0440 at 91.8; 10-19 P0455 at 91.8). Either the window is wrong for this calibration (it is the repo's rough figure, not an FCA value) or the monitor sees a different fuel value than the one logged [I].
- Unknown: any BCM, IPC or gauge fuel reading; the ECM's source for fuel.
- Grade: the ECM's fuel value live and coherent STRONG (20 readings, 9 dates, two ECM paths equal); agreement with the body module or gauge NONE (no comparator).
- One cross-module equality exists, for IBS rather than ambient or fuel: ECM DID 19BD read 71 % and BCM DID 1005 byte B read 71 % at 2026-10-19 00:33:36 to 00:33:38 (BCM formula unverified). It shows the comparison can be made, not that ambient or fuel agree. [E]

**Exact live read that closes Part 1.** One sitting, engine idling, ideally the first start after an overnight soak, with the clock noted:
1. MES, ECM (IAW 10JA), Read parameters: "External temperature", "Air temperature", "Fuel level", "Atmospheric pressure", "IBS Battery charge status", at least 30 samples.
2. Same minute, MES, BCM (Marelli 949), Read parameters: copy the whole parameter list and note any outside-temperature or fuel entry (names unknown [N]). If it lists none, the cluster is the body-side reference: photograph its outside-temperature display and fuel gauge with the time.
3. Same minute, CUORE on the 18DB33F1 route: PID 46, PID 2F, PID 33; UDS ECM DID 1001 and 19BD; BCM DID 1005.
4. Reading it: ECM "External temperature" close to PID 46 and the cluster = the -61 C was transient or is gone, and C10 weakens. Still -61 C while PID 46 is plausible = MES "External temperature" is a different, dead channel, and the BCM-to-ECM path becomes the lead for C10. ECM fuel % against the gauge, within the gauge's graduation, closes the fuel input.

### S2. Part 2: has the ECM ever seen the ESIM switch close?

What the archive holds about the switch and the EVAP path [E]:
- MES: the only EVAP-related ECM parameters (06-07 live log) are "Evaporation control valve opening" (0.0 % in 24 of 24 samples) and "Canister fill" (50.00 % in 24 of 24). There is no ESIM, leak-detection, EVAP-switch or tank-pressure parameter in the 133 names of that log.
- MES actuators: "Evaporation control valve" COMPLETED 18 times, FAILED 0 (2025-09-24 x5, 2025-10-14 x1, 2026-09-15 x12), all on the ECM. The blocks carry only the word COMPLETED, no feedback value. This is the engine-side purge valve; the ESIM commanded vent test was never run (also stated under H-A).
- OBD: PID 2E purge commanded 18.0 % (10-13 frame), 12.2 to 13.7 % (10-13 live), 0 % (10-14, 74 s after start); PID 54 EVAP vapour pressure 0.0 kPa (one read, 10-14 19:01); PID 32 NO DATA on 10-13; MAP 31 to 33 kPa at hot idle on 10-13 and 10-14. The ECM tracks P0451, P0457 and P2422 and all read 0x40 (never failed) in every ECM read on record. CUORE has no DID for the ESIM switch (`esim_status` is a placeholder).
- Mode 06 (values only on 10-13; 10-14 reset; 10-19 NO DATA): see M1 to M6. Additions: zero is not a "did not run" marker (MID 39 and the 0x3C TIDs 85 and 86 read 0 with limits 0/0 on 10-13, when the EVAP monitor was complete, and again after the clear). The 0x3A limits were wiped by the clear while 0x3C TID 90 kept 0 to 6000. A 3965 minimum that is not a round number and that disappears on a clear fits a limit computed per run, possibly from fuel level or temperature [I, WEAK, one read]. If so, the Part 1 inputs reach the pass/fail threshold and not only the monitor's enable.

ECM status bytes for the three codes, every stored read (bit order as in the status-byte section):

| Read | P0440 | P0455 | P0456 |
|---|---|---|---|
| 2026-09-25 20:12 | 0x4D | 0x4D | 0x4D |
| 2026-10-13 20:24 | 0xCD | 0x4D | 0x40 |
| 2026-10-14 19:02 | 0x4D | 0x40 | 0x40 |
| 2026-10-19 00:23 and 00:30 | 0xCD | 0x4D | 0x4D |

- In all 15 values (5 reads x 3 codes) b6 testNotCompletedThisOperationCycle is set and b1 testFailedThisOperationCycle is never set; b4 and b5 never. The 10-13, 10-14 and 10-19 reads were made with the engine running (port 14.0 to 14.5 V). [E]
- So no read has ever caught a test failing in the current cycle. The failed state (b0, b2, b3) is carried from earlier cycles; the reads show that it exists, not in which cycle, at which test step, or why. [I]

**Conclusion 2.**
- Facts: no log, store record or session file records the ESIM switch state, the ESIM solenoid, or any tank-pressure value other than one PID 54 read of 0.0 kPa. The EVAP monitor reached completion with stored results on 10-13 (readiness complete, Mode 06 values), and on 10-19 the three codes' freeze frames show failures in three regimes (idle after a refill, engine off in a cold soak, driving). One stretch had the codes absent with no recorded clear: ECM "no faults" reads on 2025-10-14 21:39 (20 days and 43 starts after the 2025-09-24 P0456 read) and on 2026-06-07 (x3, startups 13,865). The codes were back by 2026-08-27.
- Inference: the archive proves nothing about whether the switch ever closed, in either direction. A nonzero Mode 06 time shows the ECM ran a test to a stored number; it does not show a switch edge (M6: meanings A and B imply a closure, D does not, and the TID definition decides). The 2025-10 to 2026-06 stretch is the only hint of a period when the tests did not fail, which would mean the vacuum path and switch worked then. An unlogged clear (another tool, a battery disconnect) fits equally, and the archive cannot separate them. [I, WEAK]
- Unknown: the switch state at any time; the definitions of TIDs 0x87 and 0x90; what ended the 2025-10 to 2026-06 stretch; the ECM's own status during a key-off test (the three UDS status reads were all taken with the engine running).
- Grade: "the ECM has never seen the switch close" NONE (neither supported nor refuted); "EVAP tests ran and stored values on 10-13" STRONG (one read, matches readiness).

**Exact live read that closes Part 2.** Two items:
1. The switch itself: wiTECH, ECM live data, the ESIM switch or EVAP vacuum-switch parameter (name not in the repo [N]), logged through Test A (hand vacuum at the ESIM port, three cycles). Neither MES nor CUORE can show it. It closes and reopens with the pump = the switch and its wiring work; it never closes = switch, mounting or circuit.
2. What the ECM concluded, read the moment the codes return and before anything else, on the 18DB33F1 route, with no clear: Mode 06 MIDs 39, 3A, 3C, 3D (all TIDs); UDS 19 02, 19 04 and 19 06 for P0440, P0455, P0456; PID 54, 2E, 2F, 46 in the same minute. Compare with 10-13 (404, 6096, minimum 3965): a changed value, or a changed 3A minimum at a different fuel level or temperature, separates a measured quantity from a sentinel and tests the computed-limit idea above. A second read of the same frames after the next complete cycle, with fuel and PID 46 noted, closes it.

### S3. Corrections and additions to earlier sections

- Conditions table: with the three 10-19 frames, 11 of 14 EVAP frames are inside the 15 to 85 % window and 3 are above it (09-25 P0455, 09-25 P0440, 10-19 P0455).
- C8 / C10 / H-B: the -61 C was read after the BCM codes had been cleared that morning and with none listed, so it did not track an active U1713-2F at that moment; whether the cause outlasts a clear is unknown. Other MES values on 06-07 were also wrong or blank, so -61 C alone is weak evidence of a CAN input fault.
- Section "BCM U1713-2F and the inputs": "PID 46 (14 to 25 C on 10-13 and 10-14)" is now itemised (17, 25, 25, 24, 14 C); the gap between 17 and 25 C on the same evening is unexplained in the repo.
- Freeze-frame section: the DID 1001 fuel scale is supported by two exact matches with PID 2F (10-13 20:09 and 20:38); the 91.8 % in the 10-19 P0455 frame and the 09-25 P0440 frame is the same raw count (EA = 234), not an error.

---

## ECM EVAP sub-tests by status bits (2026-10-19)

Source: the five full ECM UDS 19 02 reads in the observation store (`module_dtcs`, ECM, request mask FF, VIN ZASFAKPN5J7B88115): 2026-09-25 20:12 (278 codes), 2026-10-13 20:24 (72), 2026-10-14 19:02 (142), 2026-10-19 00:23 (132) and 00:30 (121). Only the last three fall after the 2026-10-14 08:59 clear. The ECM was cleared again at 2026-10-19 00:39 (job action 0a1823c1), after all five reads; no ECM read exists after that clear. [E] Tags as at the top: [E] evidence, [I] inference, [N] unknown. Code texts: `mes/dtc_descriptions.py` holds no text for any code below [E]; texts are from `mes/code_feel.py` and EVAP_STELVIO.md where marked "repo", otherwise the SAE J2012 generic title, which is not repo-sourced and whose FCA mapping on this car is unverified [N].

### How the status byte can and cannot be read on this ECM

- [E] The ECM's own status availability mask is **0xCF** in all five reads. Bits b4 (0x10, testNotCompletedSinceLastClear) and b5 (0x20, testFailedSinceLastClear) are outside it: the ECM does not implement them. Across 745 stored status values only 0x40, 0x4D and 0xCD occur; b1, b4 and b5 are never set.
- [E] Three further facts agree. (1) ISO 14229 sets b4 and b6 on every DTC at a clear; the 10-14 19:02 read (10 h after the clear) shows b6 only. (2) P0440 reads 0x4D (testFailed, confirmed) with b5 clear, which the standard forbids if b5 were implemented. (3) At 10-14 19:01 the OBD readiness read said the catalyst, O2 sensor, EGR and EVAP monitors had NOT run since the clear, while P0420, P0133, P0139 and P0401 read 0x40 with b4 clear in the UDS read of 19:02.
- [I] So the rule "0x10 clear and failure bits clear = ran since the last clear and passed" cannot be used here: applied literally it would call every 0x40 code (including the four above) "passed", which the readiness read contradicts. **b4 clear carries no information on this ECM.**
- [E] What does carry information: b0/b2/b3 (failed, pending, confirmed), b7 (lamp), and b6 together with presence in the returned list. A 19 02 FF request returns only DTCs whose status is non-zero, and the list changes between reads (206 codes dropped between 09-25 and 10-13; 11 dropped between 00:23 and 00:30 on 10-19, with the engine running at 14.4 V: P0111, P0116, P0196, P0199, P0521, P02EE to P02F1, P00D2, P1212).
- [I] A code that drops out of the list went 0x40 to 0x00: its test completed this operation cycle with no failure. A code present at 0x40 has not completed this operation cycle, which says nothing about earlier cycles. **A code absent from one read but present in another therefore reads "passed this cycle"; a code never returned by any read is "no such code tracked"** (or it sits at 0x00 in every read; the 09-25 list is near-full, 278 of the 282 codes ever seen, so absence from it makes non-existence the likelier case).
- [E] Failed-state bytes: 0x4D = b0 testFailed + b2 pending + b3 confirmed + b6 not completed this cycle (b1 clear: the failure is carried from an earlier completed cycle, the test has not re-run); 0xCD = the same plus b7 lamp requested. 0x40 = b6 only.

### EVAP-related codes the ECM returns (status byte per read)

Columns 10-14 19:02, 10-19 00:23 and 10-19 00:30 are after the 10-14 08:59 clear. "abs" = not in that read's list (status 0x00). The 00:23 and 00:30 values are identical for every EVAP code in this table.

| Code | Description | 09-25 20:12 | 10-13 20:24 | 10-14 19:02 | 10-19 00:23 | 10-19 00:30 |
|---|---|---|---|---|---|---|
| P0440 | general EVAP fault; MES names it "Evaporation control valve", no verified FCA definition (H-C f15ffa4f) | 0x4D | 0xCD | 0x4D | 0xCD | 0xCD |
| P0441 | incorrect EVAP purge flow (repo) | 0x40 | abs | 0x40 | 0x40 | 0x40 |
| P0451 | EVAP pressure sensor/switch, range/performance (SAE generic) | 0x40 | 0x40 | 0x40 | 0x40 | 0x40 |
| P0455 | large EVAP leak (repo) | 0x4D | 0x4D | 0x40 | 0x4D | 0x4D |
| P0456 | small EVAP leak (repo) | 0x4D | 0x40 | 0x40 | 0x4D | 0x4D |
| P0457 | leak consistent with loose/missing/faulty fuel cap (repo) | 0x40 | 0x40 | 0x40 | 0x40 | 0x40 |
| P0458 | EVAP purge control valve circuit low (SAE generic) | 0x40 | abs | 0x40 | 0x40 | 0x40 |
| P0459 | EVAP purge control valve circuit high (SAE generic) | 0x40 | abs | 0x40 | 0x40 | 0x40 |
| P0461 | fuel level sensor, range/performance (SAE generic) | 0x40 | 0x40 | 0x40 | 0x40 | 0x40 |
| P1CEA | insufficient vapour flow under boost, flow rationality, not a leak code (repo) | 0x40 | 0x40 | 0x40 | 0x40 | 0x40 |
| P2422 | EVAP vent valve stuck closed (repo, EVAP_STELVIO.md) | 0x40 | 0x40 | 0x40 | 0x40 | 0x40 |
| P018B | not sourced in this repo | 0x40 | abs | abs | abs | abs |
| U04A0 | not sourced in this repo | 0x40 | abs | 0x40 | 0x40 | 0x40 |
| U0684 | not sourced in this repo | 0x40 | 0x40 | 0x40 | 0x40 | 0x40 |
| U1008 | not sourced in this repo | 0x40 | abs | 0x40 | 0x40 | 0x40 |
| P0111 | intake air temperature range/performance (SAE generic); the ECM's own air-temperature sensor, not an ambient code | 0x40 | abs | 0x40 | 0x40 | abs |
| P0116 | engine coolant temperature range/performance (SAE generic); context only | 0x40 | abs | 0x40 | 0x40 | abs |

No other P1xxx code in the ECM list has EVAP, ESIM or purge text anywhere in the repo; P1CEA is the only one. [E] The three U-codes have no repo text and no stated link to the EVAP monitor; none is failed. [E] BCM U1713-2F is a BCM entry, not an ECM one.

Not tracked (never returned in any of the five reads): P0442 to P0449, P0450, P0452 to P0454, P0460, P0462 to P0464, P0498, P0499, P2401 to P2421, P2423, P0070 to P0074, P0180 to P0189 (also P044A to P044F and P045A to P045F). [E] "No such code tracked" below means this.

### Verdict per EVAP sub-system and read

| Sub-system | Code(s) | 09-25 | 10-13 | 10-14 19:02 | 10-19 00:23 / 00:30 |
|---|---|---|---|---|---|
| ESIM switch circuit | P0450, P0452, P0453 | no such code tracked | no such code tracked | no such code tracked | no such code tracked |
| ESIM switch / tank-pressure signal (range, performance) | P0451 | not run | not run | not run | not run |
| ESIM solenoid / vent control circuit | P0446 to P0449 | no such code tracked | no such code tracked | no such code tracked | no such code tracked |
| Vent valve stuck closed | P2422 | not run | not run | not run | not run |
| Purge valve circuit | P0443 | no such code tracked | no such code tracked | no such code tracked | no such code tracked |
| Purge valve circuit (SAE generic low/high) | P0458, P0459 | not run | passed this cycle | not run | not run |
| Purge flow | P0441 | not run | passed this cycle | not run | not run |
| Purge flow under boost | P1CEA | not run | not run | not run | not run |
| Leak 0.020 in (small) | P0456 | FAILED | not run | not run | FAILED |
| Leak 0.040 in | P0442 | no such code tracked | no such code tracked | no such code tracked | no such code tracked |
| Leak 0.090 in / large | P0455 | FAILED | FAILED | not run | FAILED |
| Fuel cap | P0457 | not run | not run | not run | not run |
| General EVAP fault | P0440 | FAILED | FAILED, lamp | FAILED | FAILED, lamp |
| Fuel level sensor / input | P0461 | not run | not run | not run | not run |
| Fuel level, other | P0460, P0462 to P0464 | no such code tracked | no such code tracked | no such code tracked | no such code tracked |
| Ambient temperature input | P0070 to P0074 | no such code tracked | no such code tracked | no such code tracked | no such code tracked |
| Tank pressure | P0451 (row 2); P0450, P0452, P0453 (row 1) | as rows 1 and 2 | as rows 1 and 2 | as rows 1 and 2 | as rows 1 and 2 |

The mapping of 0.020 to P0456 and 0.090 to P0455 is by SAE convention and the Mode 06 labels in `cuore/live/mode06.py` (MID 3C 0.020, 3B 0.040, 3A 0.090, 39 gross, 3D purge flow); the repo does not state which DTC each Mode 06 test feeds. [I] Mode 06 on 2026-10-13 (before the 10-14 clear) agrees with the bits: purge flow PASS, gross leak PASS, 0.090 and 0.020 FAIL. [E]

### What the ECM has and has not verified since the 2026-10-14 08:59 clear

- [E] Verified OK, EVAP side: **nothing.** In the three post-clear reads no EVAP circuit, flow, level or pressure code is absent from the list, so none completed clean; each sits at 0x40. The last clean completion of the purge circuit and purge flow tests (P0458, P0459, P0441) was 2026-10-13, before the clear, and the 10-13 Mode 06 purge-flow PASS (168, within 57 to 328) corroborates it for that day.
- [E] Failed, post-clear: P0440 (first post-clear read, 10 h, 9 km), then P0455 and P0456 by 10-19; P0440 carried the lamp on 10-19.
- [E] Verified OK, non-EVAP, in every cycle read (10-13, 10-14, 10-19 twice): the ECM's own system-voltage and processor monitors. P0562 and P0563 (system voltage low/high, SAE generic) and P0606 (ECM/PCM processor, SAE generic) read 0x40 on 09-25 and are absent from all four later lists, so they completed with no failure and no pending or confirmed bit.
- [N] Not verified by any bit: ESIM switch and its wiring (no circuit code tracked; P0451 never completed), ESIM solenoid and vent (no circuit code tracked; P2422 never completed), purge valve and flow after the clear, fuel level input (P0461 never completed), ambient input (no code exists that would flag it), fuel cap.

### Effect on the hypotheses on job 76d3454bce75

- **ce6bd236, ESIM signal path:** neither supported nor weakened. No ESIM-switch circuit code (P0450/P0452/P0453) exists in the list, and P0451 has never completed in any read, so the silence of the circuit codes is not a pass. The failed bits on P0440/P0455/P0456 on a smoke-sealed system restate the case; they do not locate the fault. [I]
- **8c659dfc, inputs invalid:** neither. P0461 never completed, and no ambient-temperature code is tracked, so the ECM has nothing that would flag a pinned -61 C external temperature; silence here is not evidence against. The three U-codes are 0x40 or absent, none failed, and none is described in the repo. [I]
- **02c3c411, ESIM solenoid never closes the vent:** neither, and one correction. The hypothesis text counts "P2422, P0457, P0451, P0441, P0461 and P1CEA all read 0x40, no failure recorded" as evidence against. 0x40 means "not completed this operation cycle", not "passed". No vent-control circuit code (P0446 to P0449) is tracked, so a dead solenoid or driver would raise no circuit code of its own on this ECM; that is consistent with the hypothesis, not against it. [I] The purge side (P0458/P0459/P0441 clean on 10-13) is the only EVAP part with a recorded pass, and it is pre-clear.
- **4408d755, ECM supply/resets:** weakened a little. The supply-voltage and processor monitors completed clean in all four cycles read since 10-13. It does not refute the hypothesis: a short dropout that set no code leaves no trace (b5, failed-since-clear, is not implemented; passes leave no history). The U1713-2F evidence on the BCM side is unchanged. [I]

### Consequence for the next reads

A post-clear status read shows "failed" and "carried over" reliably, "completed clean this cycle" only by a code dropping out of the list, and never "ran since the clear". To prove an EVAP circuit or flow test passed, read the list after a drive that includes a key-off test and look for P0451, P2422, P0458, P0459 and P0441 dropping out (0x40 to absent), together with the Mode 06 values. [I]

---

## External cross-check (2026-10-19)

Method: 8 web searches (standard mode) plus page fetches. Read directly: V1 and V2 below. Fetch failed (404, 403 or unreadable PDF): Standard Brand ESIM PDF and page, Rick's Free Auto Repair pages, UnderhoodService, NHTSA MC-10236933-9999.pdf. Claims that rest only on a search-result summary are marked (snippet). Nothing found describes the Stelvio or Giulia ESIM itself; every source is Chrysler, Jeep or Dodge. Verdicts: AGREE / DISAGREE / UNKNOWN (not found, not guessed).

- V1 = Vehicle Service Pros, "Chrysler ESIM": https://www.vehicleservicepros.com/industry-news/service-repair/article/53084355/chrysler-esim
- V2 = Vehicle Service Pros, "Chrysler EVAP Performance Codes": https://www.vehicleservicepros.com/industry-news/article/53090062/chrysler-evap-performance-codes-2016-10-13
- S1 = Standard Brand ESIM (snippet): https://www.standardbrand.com/media/12092/st11710-esim-r1.pdf and https://standardbrand.com/en/products/emission-controls/evap-emissions/esim

### 1. ESIM operation and the three codes

- Solenoid-closed vent during the test: **DISAGREE**. V1: the ESIM has no solenoid; it is a case, a vacuum-operated contact switch, a diaphragm and two weighted valves held shut by gravity; the PCM controls a separate purge valve. S1 (snippet) says the same ("does not contain a solenoid"). So the premise of H-A (02c3c411, ESIM solenoid or driver never closes the vent) is not supported for the Chrysler ESIM. A Stelvio ESIM with a different design: not found.
- Switch closes at about 1 inH2O vacuum: **AGREE** (V1, V2). V1 adds: the large valve vents at about 0.5 inH2O positive, the small valve admits air at about 2.2 inH2O negative.
- Natural-vacuum (cold soak) small-leak test: **AGREE** it exists (V1, V2: starts after shutdown, "can take several hours"). **DISAGREE** with how we use it: V1 says a key-off pass or inconclusive result alone does not set a leak DTC; an inconclusive result sends the monitor to the intrusive test on a later key cycle. S1 (snippet) says P0456 sets if the switch does not close within a calibrated time after key-off. The sources conflict. Tonight's engine-off P0456 frame fits S1, not V1.
- Purge-driven large-leak test: **AGREE** (V1, V2): the purge valve pulls manifold vacuum, the PCM times the decay until the switch opens; a fast opening is a large leak; a switch that never closes means a leak or a purge problem.
- P0440: V1 "will set if the ESIM switch does not close during the intrusive leak test"; a general fault, many causes. It is a failure-to-close code, not a circuit code. No ESIM circuit DTC is described. This answers H-C (f15ffa4f): P0440 is not documented as a control-circuit code, so it does not promote H-A.
- P0455 / P0456: large and small leak. V1: P0456 only after the large/medium test has run. V2: two consecutive small-leak failures set the hard code and MIL. S1 (snippet): 0.090 in and 0.020 in thresholds.

### 2. The signature (P0440 + P0455 + P0456, repeating, after parts and clean smoke)

- A source or bulletin with this exact signature on any FCA car: **not found**.
- Closest: TSB 18-090-23, 2022 Challenger 5.7 Hemi, lists P0455, P0456, P0440 and P0441 together; cause PCM software; repair is a PCM reprogram (search summary, exact PDF not isolated; NHTSA 2023 set at https://static.nhtsa.gov/odi/tsbs/2023/). Siblings 18-092-23 (Chrysler 300) and 18-019-23 (Compass, P0456): same summary.
- Giulia 2017 reflash bulletins list P0456, and P0440/P0441, with build-date cutoffs (on or before 2017-02-27; on or before 2017-06-29) (search summary of https://static.nhtsa.gov/odi/tsbs/2017/MC-10140044-9999.pdf and https://static.nhtsa.gov/odi/tsbs/2017/MC-10216318-9999.pdf, not opened). An MY2018 VIN may sit outside both. Check the VIN.
- TSB 18-048-23 (wiTECH SLVT): run it before and after any repair, keep the original cap fitted, a road test does not confirm a repair, P0456 sets only over multiple engine-off and drive cycles (search summary of https://static.nhtsa.gov/odi/tsbs/2023/MC-10236933-9999.pdf; direct read failed).
- Causes named in parts guides and forums (anecdotal): ESIM internal failure, O-ring or diaphragm, which a smoke test may miss; ESIM must mount upright (V1; S1); wiring in the ESIM circuit; vent filter restriction (V1); split purge hose (bulletin 25-002-15 REV B, https://ricksfreeautorepairadvice.com/p0455-code-on-jeep-and-dodge-service-bulletin-fix/, snippet); stuck-open purge valve; cracked canister (less common); dust or charcoal on a check valve (forum threads https://www.jk-forum.com/forums/stock-jk-tech-12/persistent-p0456-363125/ and https://forum.powerwagonregistry.org/viewtopic.php?p=113691, snippet); ESIM guide https://ricksfreeautorepairadvice.com/dodge-p0456-common-causes-and-solutions/ (snippet).
- Wrong ESIM part number as a cause: **not found**. Fuel level or ambient inputs as a cause of a failed result: **not found** (they appear only as enable conditions, item 4).

### 3. Mode 06 TID meaning: UNKNOWN

No source maps OBDMID 0x3A TID 0x87 or OBDMID 0x3C TID 0x90 on an FCA ECM. V1 and V2 say the PCM measures switch-closure and vacuum-decay times in the intrusive test, so a time in ms is plausible, but no mapping is stated. Sections M4 to M6 above stand unchanged.

### 4. Gating inputs and the -61 C value

- Fuel level and ambient gate the monitor: **AGREE**. V1 intrusive-test entry: coolant within 10 C of ambient, fuel 12 to 88 %, closed loop, adequate manifold vacuum, ambient 4 to 37 C, elevation under 2,591 m. V2: large leak fuel 15 to 85 %, ambient 4 to 37 C; small leak fuel 15 to 85 %, ambient 4 to 43 C. Gating means the test does not run; no source says bad inputs make it fail.
- Tension in our own data [I]: the P0455 frame at 91.8 % (tonight) and the 09-25 frames at 93.7 % and 91.8 % are above both fuel windows, and the P0440/P0455 frames sit at ECT 51 to 69 C against ambient 14 to 17 C, against the "coolant within 10 C of ambient" entry. Either this ECM's windows differ, the frame records DTC logging not test start, or the scaling is off. UNKNOWN.
- Ambient and fuel arrive over CAN from the BCM/IPC on this platform: **UNKNOWN** (not found). Sources describe other architectures; none is for Giulia/Stelvio.
- -61 C is a default or invalid value: **UNKNOWN** (not found for any FCA ECU).

### 5. Lamp cycle

**AGREE** in rule, **UNKNOWN** in number. V2: the large-leak code is a two-trip code ("the test must fail on two consecutive trips if the right test conditions are met"); a small-leak failure stores a pending code, the large-leak test runs next, then two consecutive small-leak failures set the hard code and MIL. A "trip" only counts when the enable conditions are met, so about 5 days from clear to lamp is plausible (cold nights below 4 C would block the tests), but no source gives a Stelvio figure. Why only P0440 carries bit 0x80: not found.

### Ranked causes the external evidence supports for this signature

1. **ESIM unit does not seal or close under vacuum (mounting, orientation, O-ring, diaphragm, wrong part, port seating).** Supported by V1, S1 and parts guides. The ESIM's small valve opens on negative pressure and its large valve on positive, so a positive-pressure smoke test does not load the vacuum seat [I from V1]. Confirm: part number against VIN, upright mount, seating; hand vacuum at the ESIM with the switch back-probed (V1: about 4.5 to 5 V open, near 0 V and 0.5 to 2 ohm closed); bench test against a known-good unit.
2. **ESIM switch circuit (connector, ground, wiring).** V1 gives the voltage and resistance check; guides list wiring. No circuit DTC is expected. Confirm: the same back-probe under vacuum, wiggle test, wiTECH switch state.
3. **ECM calibration.** Same code set fixed by PCM reprogram on 18-090-23; Giulia flashes have build-date cutoffs. Confirm: wiTECH flash check, VIN recall check, SLVT per 18-048-23 after any change.
4. **Vacuum supply or vapour-path blockage (purge valve, tank-canister line, vent filter).** V1/V2: a switch that never closes can be a purge problem; V1 says check the vent filter. Purge valve and filter already replaced; Mode 06 purge flow PASS. Confirm: command purge and watch the switch and fuel trim at once (V2), low-pressure flow through each leg.
5. **Canister crack or contamination.** Low: new part, anecdotal sources. Confirm: flow check, smoke at the canister ports.
6. **Invalid fuel, ambient or coolant inputs (CAN).** Weakest: external sources treat them as gates, not failure causes. Confirm: live read against dash and thermometer.

### Where external evidence contradicts our ranking

- "Solenoid first": the ESIM has no solenoid (V1, S1). H-A's solenoid premise is unsupported; the vent-seal idea survives only as the ESIM's passive valves and diaphragm (rank 1).
- "Signal path weakened": nothing external weakens it. V1 defines P0440 as the switch failing to close, and the voltage and resistance check is the documented test; the Mode 06 argument (M6) has no external mapping behind it. The switch and circuit stay open until the back-probe test is done.
- "Inputs second": no source ties bad inputs to failed results, and the CAN path is not found. Calibration and vacuum supply rank ahead of inputs.
- Smaller: V1 says a key-off result alone sets no leak DTC, which questions the "P0456 reported at next cold start" model in the freeze-frame section.

Searches used: 8 of 8.

---

## Ranking after cross-check (2026-10-19)

Written 2026-10-19 from the repo and the "External cross-check" section above. No car access, no new reads, no web, no clears. Tags as at the top: [E] evidence, [I] inference, [N] not in repo. V1 and V2 were read directly; S1 is a search snippet only. Every external source is Chrysler, Jeep or Dodge; none describes the Stelvio ESIM. [N]

### What changed

- [E] The Chrysler/FCA ESIM has no solenoid (V1; S1 snippet). It is a passive device: two weighted valves hold the vent shut at rest and a diaphragm switch closes at about 1 inH2O of vacuum. The "ESIM solenoid / commanded vent" premise of hypothesis 02c3c411 (H-A) is retracted; the old text stays on the job under "RETRACTED 2026-10-19: ESIM has no solenoid". The new claim is ESIM seal / mounting orientation / part fitment.
- [E] P0440 on these cars means the ESIM switch did not close during the purge-vacuum test (V1). It is a failure-to-close code, not a circuit code, so it does not promote H-A (answers H-C f15ffa4f for the Chrysler ESIM; the Stelvio definition itself is [N]).
- [E] This ECM tracks no code for the ESIM switch circuit (P0450, P0452, P0453 never returned in five reads) or the vent circuit (P0446 to P0449 not tracked); P0451 and P2422 never completed (0x40). The ECM cannot self-check that wiring, and silent circuit codes are not a pass.
- [E] Ambient PID 0x46 read plausibly: 17, 25, 25, 24 C on 2026-10-13 and 14 C on 2026-10-14 19:01:35. Fuel level is coherent (20 readings on 9 dates; DID 1001 equals PID 2F at both 10-13 snapshots). V1 and V2 use both as test enable conditions (gates); no source found says bad inputs make a test fail.
- [N] The Mode 06 times (404 ms vs min 3965; 6096 ms vs max 6000) are measurements whose test-ID meaning is unpublished (M4 to M6 stand). They neither show nor exclude that the switch closed.
- [E] ESIM 04861961AD was fitted 2026-09-02; fitment was never VIN-verified (alternative 04861959xx exists); mounting orientation and port seating were not recorded. [N]

### Ranked order

1. **ESIM seal / orientation / part** (job 76d3454bce75, hypothesis 02c3c411, revised).
   - For: V1 and S1 (snippet) say the ESIM must mount upright and the O-ring degrades [E, weak]; V1's valve openings (about 0.5 inH2O positive, about 2.2 inH2O negative) mean positive-pressure smoke does not load the vacuum seat [I]; three regimes with one outcome [E values, I that one cause fits]; fitment never verified [E]/[N].
   - Against: the same codes were present with the original unit (2025-09-24 to 2026-09-02), so this needs that unit to have been faulty or mis-seated too, or the cause to lie elsewhere [I]; no Stelvio ESIM source [N].
   - Confirm: check mounting orientation and part number against the FCA service procedure and the parts catalogue for this VIN; bench the ESIM with gentle vacuum at the tank-side port: the switch closes (continuity) near 1 inH2O and the valves hold vacuum. Refute: both correct and the bench passes.
2. **ESIM switch circuit** (ce6bd236; status open, not weakened).
   - For: the ECM cannot self-check this circuit (above) [E]; V1 documents a voltage check at the switch, about 4.5 to 5 V open and near 0 V closed [E]; the connector sits in the wheel-well splash area [I from CASE.md and the platform's water-intrusion recalls].
   - Against: nothing measured either way; the wiring diagram and ECM pin-out are not in the repo. [N]
   - Confirm: back-probe the ESIM switch wires at the ECM connector while applying vacuum at the ESIM. Refute: the voltage follows the switch on every run and a connector wiggle causes no flicker.
3. **ECM calibration currency.**
   - For: SW 52170619 / P235QB39 unchanged through 2026 [E]; TSB 18-090-23 (2022 Challenger) lists the same four codes with a PCM reprogram, and the Jeep JL/KL flashes list P0456 [E, search summary]; Giulia flashes carry build-date cutoffs, so a VIN check matters [E].
   - Against: no Stelvio bulletin lists P0440 / P0455 / P0456 (18-026-20 lists P1CEA and P24D6; 18-030-17 is Giulia only) [E].
   - Confirm: VIN checks for recall 18V636 and CSN W05; wiTECH Flash tab, current against latest, per TSB 18-026-20. Outdated: flash, then the SLVT. Current: the calibration stays an unproven suspect.
4. **Vacuum supply: purge valve and hoses.**
   - For: V1 and V2 say a switch that never closes can be a purge problem; smoke cannot show a blockage or a kink [E]/[I].
   - Against: purge valve 68337662AC replaced, 18 actuator runs COMPLETED, Mode 06 purge flow PASS (168, within 57 to 328) on 2026-10-13 (before the 10-14 clear), purge routing OK 2026-09-16 [E].
   - Confirm: command purge and watch the switch and fuel trim together (V2); low-pressure air through each hose leg. Refute: free legs, the switch closes on commanded purge.
5. **Canister internal.** For: platform base rate, forum-grade [E weak]. Against: new 2025-08, no liquid fuel found 2026-09-26, normal refuelling [E]. Confirm: air through the canister, tank port to vent port, with the ESIM and hoses off; restricted means replace the canister (not the ESIM, per TSB 9100469).
6. **CAN inputs** (8c659dfc; likelihood set to low, still open). For: External temperature -61 C in 61 of 61 samples on 2026-06-07 (one log, one date) and U1713-2F in 10 MES scans [E]. Against: PID 0x46 plausible on 10-13 and 10-14, fuel level coherent, U1713-2F points ECM to BCM (opposite to the inputs the monitor needs), absent from the 09-29 and 10-08 scans, and sources treat the inputs as gates [E]/[I]. Confirm: live read of MES External temperature, Air temperature and Fuel level against PID 0x46, the dash display and the fuel gauge; the BCM DTC EX before any clear.

### Standing rules

- [E] No clears: 11 ECM clears in 53 days, the codes returned after each. Every clear restarts the evidence.
- Proof of any fix is the wiTECH Small Leak Verification Test per TSB 18-048-23 (the CUORE /slvt replica stands in until wiTECH) plus a completed EVAP monitor with P0440, P0455 and P0456 not returning; a road test alone does not confirm a repair (TSB summary, search snippet).
- When P0440 reports 0xCD again, Mode 06 is read first (MIDs 39, 3A, 3C, 3D, all TIDs, 18DB33F1 route), with the raw frames stored.

### What this supersedes in the sections above

- "Also considered": the reasoning order that put H-A (solenoid) first, and the H-A paragraph's solenoid premise.
- "Suggested run order" (E first, then A, B): the hands-on order is now the ranking above. Step E (the ambient read) is now step 6; it is still one live read and can share a sitting with any connected step.
- "Next tests", test A: still the ESIM hand-vacuum test, now with the back-probe at the ECM connector in step 2 and the bench check in step 1.
- Section "Mode 06 EVAP records" M6: unchanged; "never closes" wording in C5 and in the freeze-frame section remains unsupported by Mode 06 (rests on the codes only).

### Job record (job 76d3454bce75, VIN ZASFAKPN5J7B88115)

- 02c3c411: text and next_test edited (new claim; old text kept under "RETRACTED 2026-10-19: ESIM has no solenoid"; the ref about the never-run vent test stays attached but is not counted for the new claim).
- ce6bd236: status open; text gets an UPDATE 2026-10-19 paragraph; next_test rewritten as a numbered mechanic plan in the order above, with tools and expected results.
- 8c659dfc: likelihood low, still open; evidence against attached (ref `pid46-ambient-2026-10-13-14`).
- Note action 23a35c18 records the new order and the standing rules.

---

## Verification pass (2026-10-19)

Written 2026-10-19 about 01:35, after the sections above (including "Ranking after cross-check"). Method: tried to disprove each finding below from files on disk only: observation store (`C:\ProgramData\cuore\observations.jsonl`, `live_snapshots.jsonl`, `jobs.jsonl`, `owner_events.jsonl`, `audit.jsonl`), the MES folder, the 2026-10-13 live-read JSONs, and the two saved bulletin PDFs (pdftotext). No car access, no COM3, no web, no git, no subagents, no new theories. Tags as at the top: [E] evidence, [I] inference, [N] not known. Verdicts: CONFIRMED, CONTRADICTED, UNVERIFIABLE.

### V1. Freeze-frame decoder scalings (`cuore/live/dtc_detail.py`): CONFIRMED, two limits

- [E] Re-decoded the raw stored bytes by hand with the `_ECM_SNAPSHOT` lengths. Odometer raw 1465222 / 1467266 / 1467557 = 146,522.2 / 146,726.6 / 146,755.7 km (P0455 / P0456 / P0440). Startups 0x390B / 0x3910 / 0x3914 = 14603 / 14608 / 14612. Operating time 298114 / 298329 / 298445 min. All equal the table in "Tonight's freeze frames".
- [E] Odometer scale outside the decoder: live DID 0x2001 (formula from the third-party catalogue, `did_catalog.py`) read 146,501.2 km at 10-13 20:09:08 and 146,509.9 km at 20:38:32 (`live_snapshots.jsonl`); the P0455 frame is 12.3 km after the second. ECM PID 31 read 9 km since clear at 10-14 19:01:35 while P0455 was still 0x40, so that frame cannot lie below 146,518.9 km (146,509.9 + 9); observed 146,522.2, a 3.3 km margin. A different scale would break both checks.
- [E] MES September frames (FESLog_2609252002): startups / odometer / operating time = 14439 / 141,929.9 / 293,135; 14448 / 142,227.2 / 293,469; 14457 / 142,289.9 / 293,703. The three counters rise together in all six frames (Sept and tonight).

| Interval | Starts | km | Minutes | km per start | min per start | km/h |
|---|---|---|---|---|---|---|
| Sep frame 1 to 2 | 9 | 297.3 | 334 | 33.0 | 37.1 | 53.4 |
| Sep frame 2 to 3 | 9 | 62.7 | 234 | 7.0 | 26.0 | 16.1 |
| Tonight P0455 to P0456 | 5 | 204.4 | 215 | 40.9 | 43.0 | 57.0 |
| Tonight P0456 to P0440 | 4 | 29.1 | 116 | 7.3 | 29.0 | 15.1 |
| 08-27 P0456 to 09-25 P0455 | 152 | 1,357.3 | 2,760 | 8.9 | 18.2 | 29.5 |
| 09-25 P0456 to tonight P0455 | 146 | 4,232.3 | 4,411 | 29.0 | 30.2 | 57.6 |

- [E] Each pair has the same shape in Sept and tonight: a long leg then a short leg (7.0 and 7.3 km per start). km per start is not constant (7 to 41), so it cannot validate the counter alone. The bridge 09-25 to tonight is 3.3 times the 08-27 to 09-25 km per start and 1.9 times its average speed; the car was used far harder in that stretch. [I] Not contradicted: ECM PID 31 read 1,663 km since clear on 10-13 20:03 (store readiness `drive_cycle_counters`), and 146,501.2 - 142,289.9 = 4,211.3 km between the Sept frame and the 10-13 live odometer.
- [E] Operating time against distance: 146,755.7 km / (298,445 min / 60) = 29.5 km/h lifetime average, 10.0 km and 20.4 min per start. Same quotient from MES: 27.3 km/h (2025-09-24, 114,008.9 km / 250,423 min), 29.0 (2026-06-07, 136,536.7 km / 282,311 min), 29.05 (2026-09-25, 141,929.9 km / 293,135 min). Minutes per start since the last MES counters (10-04 11:16: 14532 starts, 296,066 min): 2,379 min / 80 starts = 29.7, against 31.3 between 09-25 20:28 and 10-04. Plausible and stable.
- [E] The nearest MES "engine hours" values are the header lines "Operating time" and "Functioning time (EEPROM)" (296,066 and 296,041 min on 10-04). The one live parameter log (FESLog_2606071008) has Odometer 136,536.7 km, Odometer at last Oil change 131,823.0 km, Odometer at last programming 44,074.9 km and "Max. engine speed time", but no engine-hours parameter.
- Limit 1 [E]: SCAN_2610190039.txt prints module identity, DTC lines and the clear result only; no odometer, operating time or counter. No MES file after 2026-10-04 11:16 (FESLog_2610041116: counters, no odometer) carries one, and the last MES odometer is 142,289.9 km on 09-25. Tonight's three values have no MES copy; the 10-13 live read is the nearest anchor.
- Limit 2 [E]/[I]: BCM startups 14583 (10-13 20:28:23) to ECM 14603 (P0455 frame) is about 20 starts (the BCM and ECM counters differ by at most 4) for 12.3 km of odometer, far denser than any other interval. The counter evidently counts non-driving engine starts; it is not a distance proxy.

### V2. "11 ECM clears in 53 days" and the lamp interval

- 11 ECM clears: CONFIRMED. [E] Dates, from the MES folder: 2026-08-27 (FESLog_2608271119), 08-31 (FESLog_2608311823), 09-02 (FESLog_2609021454), 09-04 19:53 (SCAN_2609041953), 09-15 20:48 (SCAN_2609152048), 09-25 20:27 (SCAN_2609252027), 09-28 11:59 (SCAN_2609281159), 09-29 10:46 (SCAN_2609291046), 10-08 09:20 (SCAN_2610080920), 10-14 08:59 (SCAN_2610140859), 10-19 00:39 (SCAN_2610190039). 08-27 to 10-19 is 53 days. Eight have an ECM SUCCESS line. The first three come from ECM FES logs that show "CLEARING STORED FAULT CODES... READING ERROR CODES: No fault codes" with no SUCCESS line. SCAN_2610080920 has two clear blocks: the first (line 67) stops after the ECM ISO code with no SUCCESS and the re-scan still lists P0456 and P0455; the second (line 151) has ECM SUCCESS. The two 09-04 FES logs (2001, 2009) are the Continental ABS, not the ECM. `audit.jsonl` (1,899 events) holds no clear service, so CUORE added none.
- "Codes returned after each clear" (Ranking section, Standing rules): CONFIRMED for 10 of 11. [E] The 11th (10-19 00:39) has no later read. The 09-29 clear was followed by a clean 10-04 scan (5.0 days) and codes by 10-08.
- "Lamp request came back twice, 4.6 to 5.4 days after a clear": CONFIRMED. [E] 10-08 09:20 to 10-13 20:03:00 (readiness `since_clear.mil_on` true) is 5.45 days, and P0440 was 0xCD at 20:24:25. 10-14 08:59 to 10-19 00:23:42 (P0440 0xCD, repeated 00:30:25) is 4.64 days.
- "Lamp returns about 5 days after each clear": CONTRADICTED as a rule. [E] The only other clears followed by a read that carries a lamp bit: 09-15 20:48 to 09-25 20:12 (9.97 days), P0440/P0455/P0456 all 0x4D, b7 clear; and 10-14 08:59 to 19:02 (0.42 day), 0x4D, `mil_on` false. No MES log has a lamp parameter (searched all 2025-09 and 2026 Stelvio FES logs), so the other clears have no lamp data. Two lamp-on cases, two lamp-off cases; the lamp is not a fixed function of days since clear.
- "MIL-on first seen 2026-10-13": CONFIRMED as the first tool record. [E] Earlier decodable lamp data: 09-25 20:12 UDS b7 clear; the 09-25 readiness reads are undecodable (`7F 01 11`, NO DATA). Caveat: this is the ECM's request, not the dash. `owner_events` entry 1552e1755ecb (2026-10-14 06:54): "Owner attests the dash MIL has not lit since the 2026-10-08 09:20 MES clear"; session record line 132: "owner has not observed lamp illumination"; CASE.md line 38: "The check-engine light has not been on". Section 13 of the session record is headed "check-engine light on" (the OBD flag). So 10-13 is the first lamp REQUEST, not a first observed lamp.
- [E] Side finding: the store DOES hold the 10-13 counters the "Gaps" section calls untraceable: readiness 2026-10-13T20:03:00 `drive_cycle_counters` = warmups_since_clear 8, distance_since_clear 1663 (10-14 19:01:26: 4 and 9). The "29 Sep clear" in the session record is not what the MES logs show: the ECM was cleared 09-29 10:46 and again 10-08 09:20. PID 21 "34 km with MIL" is still not in the store (freeze PID 21 errored, live has none).

### V3. Ambient PID 46 and the -61 C parameter

- [E] Every PID 46 value on record: 17 C in the stored Mode 02 frame read 10-13 (captured when P0440 set, 217 s after start, ECT 63 C; the frame's own date is somewhere between the 10-08 clear and the 10-13 read, so it is not a 10-13 measurement); live 25 C at 10-13 20:03:23 (1834 s since start, ECT 101 to 103 C), 25 C at 20:09:08, 24 C at 20:38:32; 14 C at 10-14 19:01:35 (74 s after start, ECT 72 C, 795 rpm). Nothing after: 10-19 OBD returned NO DATA.
- Values quoted: CONFIRMED. "Plausible": UNVERIFIABLE as outdoor truth, because no outdoor temperature or weather record exists for any date in the repo. The values are not constant (14, 17, 24, 25) and sit near the ECM's own intake-air readings (MES freeze-frame Air temperature 13 to 22 C on 09-25; DID 1935 10 to 17 C in tonight's frames). [I]
- [E] The -61 C parameter: MES "External temperature", ECM (Magneti Marelli IAW 10JA, ISO 00 01 50 40 18), FESLog_2606071008 (2026-06-07 10:03:48), -61 C in 61 of 61 samples (lines 271 to 5045) while "Air temperature" read 30 to 33 C in 60 samples. It appears in no other MES file. The October PID 46 values do not test it: different date (4 months), different interface (OBD PID versus MES parameter), and the MES parameter has not been read since. Neither confirmed nor contradicted; UNVERIFIABLE.

### V4. "No ESIM switch-circuit, vent-circuit, ambient or 0.040-leak codes tracked": CONFIRMED, scope note

- [E] Tonight's ECM read (module_dtcs 2026-10-19 00:23:42, 132 codes). P04xx present: P0401, P0402, P0403, P040B, P0420, P0425, P0426, P042A, P042B, P0440 (0xCD), P0441, P0451, P0455 (0x4D), P0456 (0x4D), P0457, P0458, P0459, P0461, P0471, P0472, P0473, P0489, P0490, P04DB. P045x present: P0451, P0455, P0456, P0457, P0458, P0459. P007x present: P007B only. P2422 present. All are 0x40 except P0440, P0455, P0456. The union of the five stored ECM reads is 282 codes.
- [E] Absent from all five reads: P0442 (0.040 leak), P0443 to P0445, P0446 to P0449 (vent circuit), P0450, P0452, P0453, P0454, P0498, P0499, P2401 to P240B, P0070 to P0074 (ambient), P0460, P0462 to P0464, and P24D6.
- Scope: P0451 (EVAP pressure sensor/switch range/performance) and P2422 (vent valve stuck closed) ARE tracked, at 0x40 in every read. P24D6 ("EVAP System Pressure Sensor/Switch B Circuit Range/Performance") is named in both saved bulletins yet never returned by this ECM. "Absent" means status 0x00 or not implemented; `19 02 FF` omits 0x00 codes, and the 09-25 list (278 of 282) is the best discriminator, so the two cannot be separated. [I]

### V5. "Purge circuit and purge flow passed on 10-13 only": CONFIRMED (bytes), limited (meaning)

- [E] P0458, P0459 and P0441: 0x40 at 09-25 20:12, 10-14 19:02, 10-19 00:23 and 10-19 00:30; absent from the 10-13 20:24 list (72 codes) only. Under the section's own rule (absent = 0x00 = completed with no failure in that cycle) 10-13 is the only one of the five stored UDS reads where they completed. MES scans carry no status bytes, so "only" says nothing about other dates. [I]
- [E] Corroboration is thinner for the circuit than for flow. Mode 06 10-13 MID 3D: TID A1 = 168 (limits 57 to 328) PASS; TID A0 = 65535 (limits 19660 to 65535) PASS, a value equal to the maximum and to 0xFFFF, so the flow pass rests on one TID. [I] No Mode 06 value exists for P0458/P0459. The same 10-13 read left P0451, P2422 and P1CEA at 0x40 although readiness said the EVAP monitor had completed.

### V6. Bulletin claims: CONFIRMED

- [E] 18-030-17 is `MC-10216318-9999.pdf`: "NUMBER: 18-030-17 REV. D ... DATE: November 17, 2017". "MODELS: 2017 (GA) Alfa Romeo Giulia". "applies to vehicles built on or before **June 29, 2017 (MDH 0629XX)** equipped with a 2.0L I4 DI Turbo Engine (Sales Code EC2)". DTC list includes P0455-00 (Large Leak), P0440 ("Evaporative Emission System Incorrect Flow"), P0441, P0456 ("Very Small Leak"), and also P1CEA and P24D6. The Stelvio is not named. Only REV. D is saved; REV. B is not in the folder, so "REV B / D" in the bulletin table rests on REV. D alone.
- [E] 18-026-20 is `MC-10174245-9999.pdf`: "DATE: March 25, 2020", supersedes 18-103-19. "MODELS: 2018 (GU) Alfa Romeo Stelvio", North America, 2.0L I4 DI Turbo (EC2). DTCs: P0106-00 (asterisked as the added code), P013A, P015A, P1CEA, P0096, P04DB, P024A, P2097, P2B2F, P24D6, P01BA, P026E, P164E, P0191, P2299, U1008. No P0440, P0441, P0455 or P0456 (grep of the extracted text returns only P0106, P1CEA, P24D6).

### Corrections to earlier sections

- "Gaps and inconsistencies", first bullet: the 1,663 km and 8 warm-ups ARE stored (V2). The "29 Sep clear" label does not match the MES logs. Only PID 21 "34 km with MIL" remains untraceable.
- Conditions table row "2026-10-13 (OBD Mode 02)" and the fuel-level series: 10-13 is the read date; the frame's own date is unknown (V3).
- Section 0 item 2 and the job note 0a1823c1 say the lamp "came back" 5.4 and 4.6 days after clears: true as an ECM request on those two occasions; the dash lamp on 10-13 is not evidenced (V2).
- Bulletin table: "REV B / D" for 18-030-17 rests on REV. D only (V6).

---

## Readings-only ledger and verdict (2026-10-19)

Source: CUORE's observation store only, `C:\ProgramData\cuore\observations.jsonl`, all 222 lines parsed and every kind reviewed: 175 tagged VIN ZASFAKPN5J7B88115, 45 serial reads with an empty VIN tag (marked "untagged"; `recent_observations(vin=...)` would drop them), and 2 `stream=fake` actuator-test lines of 2026-09-26 that did not come from the car (excluded). No MES log, job note, owner statement, bulletin, web page or earlier section of this file is used as a fact below, and nothing was re-read from the car. Tags: **[E]** a store observation (timestamp and observation number given), **[I]** inference, **[N]** not in the store. Observation numbers are 0-based line numbers. WIR = warningIndicatorRequested (b7).

### L1. OBD lists, Mode 03 / 07 / 0A (`obd_dtcs`, bus can_c)

| Time (obs #) | Stored (03) | Pending (07) | Permanent (0A) |
|---|---|---|---|
| 2026-10-13T20:02:56 to :58 (#40-42, untagged) | 18DAF110: P0440; 18DAF118: none | 18DAF110: P0455, P0440; 18DAF118: none | 18DAF110: P0440, P0456; 18DAF118: none |
| 2026-10-14T19:01:23 to :25 (#61-66) | none, both ECUs | P0440 | P0440, P0456 |
| 2026-10-19T00:23:26 to :28 and 00:29:41 to :44 (#125-130, #175-180) | NO DATA | NO DATA | NO DATA |

Reads with no content, all NO DATA: 2026-09-25T20:07 to 20:16 (CUORE note: ignition off), 2026-10-13T19:52:49 to 20:01:09 (untagged, port 14.0-14.1 V), 2026-10-14T19:09:19 (#101, 14.5 V). [E]

### L2. Readiness (`readiness`)

| Time (obs #) | Since clear | This drive cycle | Counters |
|---|---|---|---|
| 2026-10-13T20:03:00 (#43) | MIL on; stored count 1; all 8 monitors supported and complete, **Evaporative system complete** | MIL off; count 0; listed: Comprehensive components complete, EGR not complete; **no Evaporative entry** | warmups 8; distance 1663; CUORE verdict "EVAP monitor has COMPLETED since the last clear" |
| 2026-10-14T19:01:26 (#67, #68 identical) | MIL off; count 0; **Evaporative NOT complete** (also Catalyst, Oxygen sensor, EGR not complete; Misfire, Fuel system, Comprehensive, O2 heater complete) | same two entries as above | warmups 4; distance 9; CUORE verdict "EVAP monitor has NOT run since the last clear" |
| 2026-10-19T00:23:29, 00:29:51, 00:33:30, 00:33:34, 00:34:05, 00:34:06 (#131-132, #181-182, #215-216, #220-221) | NO DATA | NO DATA | none |

### L3. Mode 06, ECM 18DAF110 (`mode06`; value [min..max]; the flag is CUORE's own value-vs-limit test; MID names are CUORE's labels)

| MID / TID (UASID, unit) | 2026-10-13T20:03:54 (#44) | 2026-10-14T19:01:28 (#69, #70 identical) |
|---|---|---|
| 39 "cap off / gross leak" / 87 (10, ms) | 0 [0..0] pass | 0 [0..0] pass |
| 3A "0.090 in" / 87 (10, ms) | **404 [3965..65535] FAIL** | 0 [0..0] pass |
| 3C "0.020 in" / 85 (34, none) | 0 [0..0] pass | 0 [0..0] pass |
| 3C / 86 (12, none) | 0 [0..0] pass | 0 [0..0] pass |
| 3C / 90 (10, ms) | **6096 [0..6000] FAIL** | 6000 [0..6000] pass |
| 3D "purge flow" / A0 (30, none) | 65535 [19660..65535] pass | 0 [0..0] pass |
| 3D / A1 (FC, none) | 168 [57..328] pass | 0 [0..0] pass |

- Supported MIDs on both dates: 01 02 20 21 31 35 39 3A 3C 3D 40 41 42 60 80 81 A0 A2 A3 A4 A5. MID 3B (0.040 in), 3E and 3F are not in the list. MID 01 returned CAN ERROR on 10-13. [E]
- 2026-10-19T00:23:30 and 00:29:52 (#133-134, #183-184): the supported-MID request returned NO DATA; CUORE's "not supported by this ECU" lines there are a NO DATA artefact. [E]
- The MID 39 and MID 3C TID 85/86 records are byte-identical on 10-13 (monitor complete) and 10-14 (monitor not run). [E] So a zero with 0/0 limits does not mean "ran and passed". [I]

### L4. PIDs (`pids_snapshot`)

One snapshot with data: 2026-10-14T19:01:35 (#71 and #72, identical copies; ECM 18DAF110; 46 PIDs, 52 requests). No PID snapshot exists for 10-13. 2026-10-19T00:23:30 and 00:29:52 (#135, #185): `by_ecu` empty, nothing returned. [E]

| PID (store label) | Value, 2026-10-14T19:01:35 |
|---|---|
| 2C commanded_egr | 0.0 % |
| 2D egr_error | 0.0 % |
| 2E commanded_evap_purge | 0.0 % |
| 54 evap_vapor_pressure_signed | 0.0 kPa (PID 54 is in the ECM's supported list; PID 32 has no entry in the snapshot) |
| 46 ambient_air_temp | 14 deg C |
| 2F fuel_level | 93.725 % |
| 42 control_module_voltage | 14.25 V |
| 06 / 07 fuel trim b1 short / long | +2.344 % / -0.781 % |
| 05 / 0C / 0D / 1F | coolant 72 deg C / 795 rpm / 0 km/h / 74 s since start |
| 30 / 31 / 33 | warmups since clear 4 / distance since clear 9 km / baro 99 kPa |
| 0B / 43 / 11 | MAP 31 kPa / absolute load 21.176 % / throttle 12.157 % |

PID 2C is the store's commanded-EGR; the purge command is PID 2E. [E] PID 41 (this drive cycle) lists no Evaporative entry (see L2). [E]

### L5. UDS 19 02, ECM, request mask FF (`module_dtcs`; status byte in hex, "--" = not in the returned list)

| Obs, time | Codes returned | P0440 | P0455 | P0456 | P0441 | P0458 | P0459 | P0451 | P0457 | P0461 | P1CEA | P2422 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #13, 2026-09-25T20:12:02 | 278 | 4D | 4D | 4D | 40 | 40 | 40 | 40 | 40 | 40 | 40 | 40 |
| #46, 2026-10-13T20:24:25 | 72 | CD | 4D | 40 | -- | -- | -- | 40 | 40 | 40 | 40 | 40 |
| #74 (copy #87), 2026-10-14T19:02:07 | 142 | 4D | 40 | 40 | 40 | 40 | 40 | 40 | 40 | 40 | 40 | 40 |
| #138 (copy #151), 2026-10-19T00:23:42 | 132 | CD | 4D | 4D | 40 | 40 | 40 | 40 | 40 | 40 | 40 | 40 |
| #188 (copy #201), 2026-10-19T00:30:25 | 121 | CD | 4D | 4D | 40 | 40 | 40 | 40 | 40 | 40 | 40 | 40 |

- Bits: 0x40 = b6 only (testNotCompletedThisOperationCycle). 0x4D = b0 testFailed + b2 pending + b3 confirmed + b6. 0xCD = 0x4D + b7 (WIR). b1 (testFailedThisOperationCycle), b4 and b5 are never set in any ECM status in the store; the only ECM values ever returned are 0x40, 0x4D, 0xCD (no 0x00). The `availability_mask` the ECM returned is 0xCF in all five reads, which excludes b4 and b5. [E]
- P0442 to P0450, P0452, P0453 appear in none of the five lists (282 distinct codes in their union, the 278-code list included). [E] "Not tracked by this ECM" is the likely reading, but list length swings from 72 to 278 between reads. [I]
- TCM, IPC and RFHUB reads on these dates contain no EVAP-family code; for the BCM see L7. [E]

### L6. UDS 19 04 / 19 06 detail (`dtc_detail`)

| Time (obs #) | Module, code | Status | Flags |
|---|---|---|---|
| 2026-10-19T00:25:35 (#165) | ECM P0440-00 | 0xCD (205) | testFailed 1, failedThisCycle 0, pending 1, confirmed 1, notCompletedThisCycle 1, WIR 1, since-clear bits 0 |
| 2026-10-19T00:25:36 (#166) | ECM P0455-00 | 0x4D (77) | same, WIR 0 |
| 2026-10-19T00:25:38 (#167) | ECM P0456-00 | 0x4D (77) | same, WIR 0 |
| 2026-10-19T00:25:39 (#168) | BCM U1713-2F | 0x0F (15) | testFailed 1, failedThisCycle 1, pending 1, confirmed 1, notCompletedThisCycle 0, WIR 0 |
| 2026-10-13T20:28:23 (#55) | BCM U1713-2F | 0x0F (15) | as #168 |

- **Decoded freeze-frame fields in the store: none.** All four snapshots carry `identifiers: []` and `undecoded_from: DID 1008 (length unknown)`; the bytes are stored raw (ECM 132 bytes each, BCM 38). Any decode needs a DID scaling table, which is not a reading. [E]
- ECM raw snapshot bytes, verbatim: P0440 `100800048DCD1009000E200A3914608200192140000100000000040010000E641924001802002D100205E0192D0320011664A51812FF3410035B1004008F19370173192312191E0001182F0086193532195A03EC182103181800195603EC130200231B0D800000000000040119BD4C1B0384198C2019BE0020000019280010018E370100`; P0455 `100800048C8210090018200A390B608200192140000100000000040010000BF01924001802002310020000192D002001165B861812003C10036D1004008E1937013C192312191E0009182F005C193539195A03E9182103181800195603E8130200381B0DA00000000000040119BD3E1B0384198C2019BE002000001928001001EA370100`; P0456 `100800048D5910090000200A3910608200192104000000000000040010000000192400180200A010020000192D002001166382181200001003391004007B193703C9192322191E0100182F0000193538195A03CC182100181800195603D1130200111B0D000400000000000019BD641B0380198C0119BE002000001928001001A0370100`. [E]
- Extended data: record 1 = `60` on all four (CUORE's own note: "occurrence counter ... unverified for FCA"); trailing raw `80 28 60 81 03 60 83 00` on P0440 and `80 28 60 81 00 60 83 00` on P0455 and P0456; BCM U1713-2F `60` with trailing `80 28 60 81 01` on both 10-13T20:28:23 and 10-19T00:25:39. Meanings not in the store. [E][N]

### L7. BCM U1713-2F (`module_dtcs`, BCM, availability mask 0x4F)

Present at 0x0F: 2026-10-13T20:24:25 (#48, 100 codes), 2026-10-19T00:23:42 (#144/#157, 148 codes), 2026-10-19T00:30:25 (#194/#207). Absent from the list: 2026-10-14T19:02:07 (#80/#93, 125 codes). [E] The store holds no text for U1713-2F and no link between it and the EVAP monitor. [N]

### L8. ECM identity and context

- `identity` / `module_identity`, ECM: F187 `50544870`, F188 `52170619`, F194 `P235QB39`, F191 `52055320`, F192 `MM10JAHW232`, F18C `TD4192427B17540`, F189 requestOutOfRange, F195 `00 00`. Identical at 2026-09-25T20:11:51 (#11), 2026-10-14T19:02:07 (#75), 2026-10-19T00:23:42 (#139), 2026-10-19T00:30:25 (#189); F187/F188 identical in the partial read 2026-10-13T20:25:15 (#51). [E]
- Mode 09 (#60, 2026-10-14T19:01:23): ECM calibration ID `52170619`, CVN `D3E2AD62`. 2026-10-19T00:23:26 and 00:29:39 (#124, #174): NO DATA. The IUPR (PID 08) decode in #60 is not usable: its first field (OBDCOND 7177) is bytes `1C 09`, and `1C` is the item-count byte in the frame. [E]
- Context: port or module voltage recorded at 14.0-14.5 V on 10-13, 10-14 and 10-19 (adapter probe, PID 42, CUORE warnings); CUORE's own warnings on 10-13 and 10-19 say the engine is running. ECM DID 1302 (catalogue label "Engine oil temperature", formula B, confidence unverified): 71 deg C at 2026-10-14T19:02:07, 47 deg C at 2026-10-19T00:23:42, 68 deg C at 2026-10-19T00:30:25. [E] So the 10-19 reads span a warm-up. [I]

### L9. What the store does not contain [E]

No ESIM, vent-valve, canister or tank-pressure DID or switch state ("ESIM" occurs 0 times in 222 lines); no actuator or routine test taken from the car (the only two are `stream=fake`); no PID snapshot on 10-13; no OBD-side data of any kind on 10-19; no decoded freeze-frame field; no record of a clear command (only counter resets); no Mode 06 MID 3B, 3E or 3F; no second Mode 06 read with the monitor complete.

### (a) What the readings PROVE, and what they do not

Proven [E]:
1. The ECM held P0440, P0455 and P0456 as failed, pending and confirmed (b0, b2, b3): all three at 2026-09-25T20:12:02, 2026-10-19T00:23:42 and 00:30:25; P0440 and P0455 at 2026-10-13T20:24:25; P0440 alone at 2026-10-14T19:02:07. Mode 03/07/0A on 10-13T20:02:56-58 and 10-14T19:01:23-25 agree on the code names.
2. Only P0440 ever asked for the lamp (b7): 2026-10-13T20:24:25 and the two 10-19 reads; readiness MIL on 2026-10-13T20:03:00, off 2026-10-14T19:01:26. P0455 and P0456 never carried b7.
3. A reset happened between 2026-10-13T20:03:00 and 2026-10-14T19:01:26 (warmups 8 to 4, distance 1663 to 9, MIL on to off, EVAP monitor complete to not complete). That it was a code clear is [I]; the store has no clear command.
4. P0440 was already 0x4D at 2026-10-14T19:02:07, 9 km after the reset, while readiness said the EVAP monitor had not completed. Whether it was re-detected or carried over cannot be told from these readings. [I]
5. P0455 and P0456 went from 0x40 (2026-10-14T19:02:07) to 0x4D (2026-10-19T00:23:42): a new failure was recorded in between. P0440 gained b7 in the same interval.
6. Purge side, 2026-10-13 only: Mode 06 MID 3D A1 168 inside 57..328 and A0 65535 inside 19660..65535 at 20:03:54; P0441, P0458, P0459 never failed in any read. PID 2E was 0.0 % in the only PID snapshot (2026-10-14T19:01:35), so no purge was commanded there.
7. Both non-trivial leak records failed at 2026-10-13T20:03:54: 404 under a minimum of 3965 (MID 3A) and 6096 over a maximum of 6000 (MID 3C TID 90). What those two TIDs measure is not in the store. [N]
8. ECM software identity did not change anywhere in the store, 2026-09-25T20:11:51 to 2026-10-19T00:30:25. That shows no reflash; it does not show the installed software is the right one.
9. No ECM status read ever caught a test failing in the current cycle (b1 never set, five reads).

NOT proven, with the reason:
- **"The ECM never recorded the ESIM switch closed in any regime": not proven by the bits, and not provable from the store.** (i) No reading carries the switch, the solenoid or the vent state: no DID, no actuator test, one PID 54 sample of 0.0 kPa with no stimulus. (ii) The sense/vent codes P0451, P2422 (and P0457, P0461, P1CEA) read 0x40 in all five reads, which means "not completed this cycle", never a completed pass; the ECM does not implement b4/b5 (mask 0xCF), so it keeps no "ran since clear" memory. (iii) No switch-circuit or vent-circuit code (P0446-P0450, P0452, P0453) appears in any list, so there is no silent code to cite. (iv) The b0/b2/b3 bits on P0440/P0455/P0456 give the ECM's verdict, not the input that produced it. Grade: neither supported nor refuted. [I]
- "0x40 means passed": false on this ECM. At 2026-10-14T19:02:07 P0441, P0458, P0459, P0451 and P2422 read 0x40 while readiness (19:01:26) said the EVAP monitor had not run since the reset. [E]
- "Absent from the list means passed this cycle" (P0441/P0458/P0459 at 2026-10-13T20:24:25): inference only. It fits the same session's MID 3D pass, but list length varies 72 to 278 and CUORE never saw a 0x00 status. [I]
- Status bytes are not a full history: P0456 sits in Mode 0A permanent (2026-10-13T20:02:58; 2026-10-14T19:01:25) while UDS shows 0x40 (2026-10-13T20:24:25; 2026-10-14T19:02:07); P0455 is pending-only at 2026-10-13T20:02:57 and 0x4D at 20:24:25. [E]
- "Purge circuit and flow are healthy now": no. The only pass is pre-reset; every later read is 0x40, zeros or NO DATA. [E]
- "Freeze frames show failures in three regimes": not in the store; no field is decoded (L6). [E]
- "Mode 06 gross-leak (MID 39) passed": MID 39 on 10-13 is byte-identical to the 10-14 not-run record (L3), so it shows nothing. [E]

### (b) Component the readings prove must be replaced

**None.** No reading fails a part: there is no circuit code on any EVAP component, no commanded test, no measured output, and no stimulus-response pair. ESIM: no reading at all. Vent: P2422 never completed. Pressure/vacuum sense: P0451 never completed, PID 54 read once at rest. Purge valve: passed 10-13, never failed. Cap, hoses, canister, tank: zero readings. ECM: identity constant, no reading of misbehaviour. BCM: U1713-2F has no stated EVAP link. [E]

### (c) Component the readings isolate as the test target

The readings isolate a **function**, not a part: the leak-detection chain (what makes P0440, P0455, P0456 and the two failing leak records) rather than the purge chain. The part to test first is the **ESIM sense/vent assembly and its signal path**. The brief names the ESIM; the store never does, so that identification is premise, and the following is what the readings add [I]:
1. The purge chain is the only part with a recorded pass (L3, L5 on 2026-10-13) and never a failure, so it is last in line.
2. The three leak-class codes set together (2026-09-25T20:12:02; 2026-10-19T00:23:42 and 00:30:25), were all back after the reset (P0440 by 2026-10-14T19:02:07, P0455 and P0456 by 2026-10-19T00:23:42), and both leak records failed on 10-13. One shared upstream element fits that better than three independent faults. [I]
3. The sense and vent codes (P0451, P2422) have never completed, so nothing exonerates that circuit, and no circuit code exists for it to have raised. [E]
4. It is the one candidate with a stimulus that produces a reading on a route CUORE already has: PID 54 is in the ECM's supported list (2026-10-14T19:01:35). [E]
5. A physical leak (cap, hoses, canister, tank) is not excluded by any reading; the readings cannot rank it against the sense/vent path. [E]

### (d) Additional readings that would prove a replacement

| Reading to take | Proves replacement if | Exonerates if |
|---|---|---|
| PID 54 (with 2E, 2F, 46 in the same minute) logged through a stimulus applied at the ESIM sense port and confirmed on an independent gauge (the gauge and stimulus are not store readings) | PID 54 stays 0.0 kPa through a verified stimulus, and the connector supply, ground and signal are in spec (also not store readings). The store does not say which sensor feeds PID 54 [N], so a flat PID 54 alone is not proof | PID 54 follows the stimulus and returns on release |
| ESIM switch state, if a tool exposes it (no such parameter exists in the store) | Never closes under a verified stimulus | Closes, holds, reopens |
| Commanded vent close, then a pressure hold reading (no actuator test of any EVAP part exists in the store) | Vent commanded closed, system does not hold, with the circuit verified | Holds |
| ECM 19 02 for P0440/P0455/P0456 with b1 = 1, plus 19 04 and 19 06 in the same cycle, before any clear (never seen) | Does not prove a part; separates "test aborts" from "test ran and saw loss" | n/a |
| Mode 06 MIDs 39, 3A, 3C, 3D, all TIDs, in two complete cycles with no reset between, readiness EVAP complete both times, PID 2F/46/54 beside each (the OBD route returned NO DATA on 10-19; it answered on 10-13 and 10-14) | Does not prove a part; identical values twice = a measured quantity, differing = condition-driven | n/a |
| ECM 19 02 after a cycle containing the tests: P0451, P2422 (and P0441, P0458, P0459) leaving the list | n/a | They drop out while P0455/P0456 still fail: sense, vent and purge are exonerated and the leak becomes the target |

Replacement of the ECM cannot be proven from OBD readings alone; it would need a correct PID 54 response to a verified stimulus while the leak records still fail in a cycle where the rest of the chain is shown sound. Cap, hose, canister and tank condition are not readable on any OBD route. [I]

### Conflicts this ledger forces on earlier sections of this file

- The "working model" under "Remaining candidate causes" (the ECM sees sealed/vacuum only through the ESIM switch and "on this car it never does"): unproven (grade NONE), see (a).
- The "three regimes" freeze-frame statement and the "gross leak PASS" line under the status-bit verdict table rest on a repo scaling table and on a MID 39 record that is identical to a not-run record; neither is a reading.
- The "passed this cycle" labels for P0441/P0458/P0459 on 10-13 are inference from list absence, corroborated only by the same session's MID 3D pass.

## MES recordings 2026-10-20 06:20-06:24

Four MultiEcuScan files were parsed with `mes.fes.load_fes` (readings only). **All four are simulations, not vehicle data.** Each carries the banner "SIMULATION MODE!!! THE DATA IS NOT REAL!!!" and the simulation fingerprints (ECU ISO code `7C 86 4F FF FF`; VIN field `5188214`, a number and not a VIN). [E: file lines 5 onward of each file; `log.simulation` = True in all four]

| File (FESLog_) | Module | Parameters | Samples | Duration |
|---|---|---|---|---|
| 2610200620 (session 06:18:57) | Service Interval Reset | 8 (odometer, service distance/dates/counts) | 77 | not recoverable (no per-sample timestamps) |
| 2610200622 (06:21:55) | Blind Spot Sensor Autoliv (Right) | none | 0 | n/a |
| 2610200623 (06:22:58) | Marelli AlfaConnect Radio/Nav | 4 (rear camera brightness, ECU temperature, battery voltage, vehicle speed) | 80 | not recoverable |
| 2610200624 (06:24:11) | ZF Electronic Gear Shift Module | none | 0 | n/a |

- Values are random across samples (for example Odometer 85, 8, 33, 61 km; vehicle speed 0 to 98 km/h; ECU temperature 1 to 99 C), and "Battery voltage" is pinned at 1.4 V in all 80 samples. These are generated numbers. [E: 2610200620, 2610200623]
- DTC lines: B0110-15 and P068A-68 appear in 2610200622 and 2610200623, both "stored", module-level, in simulated sessions. No clear events, no actuator tests, no freeze frames in any of the four. [E]
- EVAP, purge, ESIM, leak, fuel level, external/ambient temperature, IBS/battery (real), coolant, engine state: none recorded in any file (text search finds none). No ambient value exists to compare with the -61 C of FESLog_2606071008. [E]
- No SCAN_26102006* or later exists. The latest scan file is SCAN_2610190039.txt (saved 2026-10-19 00:39), already covered in this ledger. [E: directory listing]

**Ledger effect: nothing new.** Nothing proven, nothing changed. The recordings are not readings of the car and must not be cited as evidence for or against any EVAP candidate. [I: they show only that MES was run in simulation on 2026-10-20, with no vehicle connected]
