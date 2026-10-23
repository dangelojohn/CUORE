# Scan 2026-10-23 after ESIM replacement: readings and interpretation

> **Superseding event, 2026-10-23 01:12.** After this scan the owner cleared ECM, IPC, BCM and DASM in MES (SCAN_2610230112, SUCCESS; MES log, not a CUORE reading). The pending bits, EVAP readiness and the 342 km of monitor history below are reset. The permanent codes P0440/P0456 survive a clear by design and still clear only on a passed monitor. **Consequence (inference):** every EVAP result from now on is unambiguously post-ESIM, which removes the before/after ambiguity noted in this document. **New proof baseline: 2026-10-23 01:12, odometer 148,207 km.** Proof criteria are unchanged: Mode 06 0x3A/0x87 at or above its minimum, no test-failed bits, EVAP readiness complete, permanent codes gone. Conditions: fuel 15-85 % (46 % now, do not fill), cold soak, then cold start and a 20+ min drive, repeated. No further clears by anyone; re-read before 2026-10-28. The readings below remain the pre-clear record. Also on the owner side: IPC service-interval reset (FESLog 0114) and a BCM 'Indicators command' adjustment attempt that stopped at SECURITY CODE (FESLog 0127, no outcome recorded). See `docs/vehicles/ZASFAKPN5J7B88115/radio/MES_MODULE_READS_2026-10-23.md`. EVAP job 76d3454bce75.

2018 Alfa Romeo Stelvio 2.0T Q4, VIN ZASFAKPN5J7B88115. CUORE scan SCAN_2610230010, 2026-10-23 00:10 local. Jobs: 76d3454bce75 (EVAP), bb4ebb961aee (network), d04440124055 (dealer visit 2026-10-28).

Labels used: **[CUORE]** a reading taken by CUORE tonight (file named); **[OWNER]** a fact stated by the owner, not a reading. Outside facts are leads, not proof.

Nothing was cleared by this scan. (Superseded: the owner cleared at 01:12, see the box at the top.) No further clear is needed or allowed (see Verdict).

## Conditions

- [OWNER] Odometer at the scan: 148,207 km (owner-stated, dashboard; not a CUORE reading).
- [OWNER] ESIM and gasket replaced 2026-10-22 (white cylinder up). Car on a 10 A charger, ignition on, engine off. No adapter cable (CAN-C only).
- [CUORE] Discrepancy to check: PID 0C read 750 rpm, speed 0, coolant 73 C (files 28-30), which looks like the engine idling at the time of those reads, not "engine off". Intake PID 0F then returned NO DATA. The verdict below does not depend on this, but the conditions are recorded as read.
- [CUORE] Adapter voltage (ATRV) 14.5 V before and after (files 07, 53). Runner: 57 steps, 13 issues (manifest.json). An earlier attempt the same night aborted on a wrong port (see Tooling note).

## Readings [CUORE]

Raw files are under `data/captures/stelvio-2018/scans/2026-10-23_SCAN_2610230010/raw/`; the parsed report is `raw/REPORT.md`.

| Item | Reading | File |
|---|---|---|
| MIL | off (stored DTC count in PID 01: 0) | 11 |
| Mode 03 (stored) | none | 14 |
| Mode 07 (pending) | P0440, P0455, P0456 | 14 |
| Mode 0A (permanent) | P0440, P0456 | 14 |
| Warm-ups since clear | 14 | 11 |
| Distance since clear | 342 km (clear was 2026-10-19 00:39, MES) | 11 |
| Readiness | all complete except EVAP INCOMPLETE; EGR incomplete this drive cycle (PID 41) | 11-13 |

Mode 06 (file 15):

| OBDMID/TID | Value | Limit | Result | 2026-10-13 |
|---|---|---|---|---|
| 0x3A/0x87 | 496 ms | min 3707 | FAIL | 404 ms, min 3965 |
| 0x3C/0x90 | 6096 | max 6000 | FAIL | 6096, identical |
| 0x3C/0x85 | 4722 | max 4200 | FAIL | |
| 0x3C/0x86 | 15379 | max 6000 | FAIL | |
| 0x3D/0xA0 | 65535 | min 19660 | PASS | |
| 0x3D/0xA1 | 196 | 63 to 326 | PASS | |

Scaling of the 0x3C/0x85, 0x3C/0x86 and 0x3D records is unknown; their pass/fail is the ECM's own flag.

UDS 19 02 (file 33), status bytes:

- ECM: P0440-00, P0455-00, P0456-00 all 0x4D (testFailed, pendingDTC, confirmedDTC, testNotCompletedThisOperationCycle; warning indicator not requested). ECM availability mask 0xCF, so b4/b5 are not implemented there.
- BCM: B101D-15 0x4D; B10AA-4A 0x08; B1176-97 0x08; U1736-87 0x08.
- IPC: U1736-86 0x0E; U1736-87 0x0E.
- TCM, RFHUB: none.
- U1711, U1712, U1713: ABSENT in every module.
- DASM, DTCM, ESM: skipped (no confirmed address).
- No camera / ParkView / PAM module answered on CAN-C. Silence on CAN-C is not proof of absence if the module sits on another bus.

Freeze frame (Mode 02, files 16-20): P0455; coolant 56 C; 10 C from freeze-frame PID 46 (the brief calls this intake air; the standard definition of PID 46 is ambient air temperature, so the label is unconfirmed; freeze-frame PID 0F returned NO DATA); fuel level 82.7 % (82.745).

Supplementary readings from the P0455 UDS 19 04 snapshot (file 46, scaling medium confidence): intake air temperature (DID 1935) 15 C, coolant 56 C, fuel level (DID 1001) 82.75 %, odometer (DID 2001) 146,879.1 km, startups counter 14,627. The 2026-10-19 freeze frames carried odometer 146,755.7 km on the last (P0440, driving) frame, so this snapshot is about 123 km after that point. The current odometer was not read in this scan; the owner-stated dashboard figure is 148,207 km. CHECK: that is 1,328 km above the snapshot's 146,879.1 km, while PID 31 reports only 342 km since the 10-19 clear (the clear was at roughly 146,756 km or later). The two cannot both hold: either DID 2001's scaling or source is off (medium confidence), or the figures refer to different things. The "about 123 km after" and "early in the window" reasoning that uses DID 2001 is therefore unverified.

Live now:

- Ambient 8 C (PID 46). Intake air (PID 0F): NO DATA.
- Fuel level 45.9 % (PID 2F) and 46.7 % (DID 1001).
- Voltage 14.5 V (adapter, charger on); PID 42 14.31 V.

Identity reads:

- BCM (file 35) and IPC (file 37) identity reads errored: the response carried `error: "CAN ERROR"` with HTTP 200, and the runner logged `/error: CAN ERROR` as a problem on attempt 1. The VIN and part-number fields still came back in the same response.
- ECM, TCM and RFHUB identity reads returned VIN and part numbers (files 34, 36, 38). Software-version DID reads (F132) are files 39-43.

## Verdict

EVAP proof: INCOMPLETE, not failed and not passed. The monitor has produced at least one failing result since the 2026-10-19 clear (pending + permanent codes, 0x3A/0x87 = 496 ms < 3707). Whether that result was produced before or after the new ESIM (fitted 2026-10-22) cannot be read from the ECM. Inference, medium confidence: the P0455 freeze frame was stored at 82.7 % fuel while the tank now reads 46 %; roughly a third of a tank was used between the two, which places the stored failure early in the 342 km window, i.e. most likely before the ESIM was changed. The permanent codes P0440/P0456 are the ECM's own proof mechanism: they clear only when the monitor runs and passes. No clearing is needed or allowed. Hypothesis 02c3c411 (ESIM) stays 'supported'; hypothesis 8c659dfc (EVAP inputs invalid) is weakened: ambient 8 C and fuel 46 % are plausible and inside the monitor's enable window. Watch item, inference: 0x3C/0x90 read exactly 6096 on both 10-13 and 10-23, which looks like a sentinel/saturation value rather than a measurement. Network: the BCM cluster U1711/U1712/U1713 has not returned in 14 warm-ups / 342 km since the clear; only U1736-87 (BCM, confirmed) and U1736-86/-87 (IPC) remain, plus BCM B101D-15 (battery-voltage circuit code, status 0x4D) which is the next reading to chase for the voltage line of enquiry. Battery health could not be judged (charger on, 14.5 V).

## Next conditions for the proof run

Source: the EVAP enable data collected in `docs/research/CEL_2026-10-19_DIAGNOSIS.md` (section "External cross-check", item 4 "Gating inputs"; "Next tests in order", step 4; and the 10-19 rule at its line 75 that fuel inside 15 to 85 % is the working window). These are outside-source enable conditions (leads), not CUORE readings.

1. Fuel level between 15 and 85 %. Do not fill the tank above 85 %. (CEL doc: V2 large and small leak tests 15 to 85 %; V1 12 to 88 %.)
2. Ambient inside the enable range: 4 to 37 C for the intrusive test, up to 43 C for the small-leak test (CEL doc, V1/V2). Tonight's 8 C is inside it; cold nights below 4 C would block the tests (CEL doc, lamp-cycle item).
3. Cold soak, then a cold start and a drive: the CEL doc's own wording is "cold start ... 20+ min steady cruise, long engine-off soak" and the natural-vacuum test "can take several hours". The figure of at least 8 h cold soak is the reviewer's, not a number in the CEL doc.
4. Repeat over the coming days. A "trip" only counts when the enable conditions are met.
5. Read again without clearing (Mode 01 readiness, Mode 06 0x3A/0x87 and 0x3C/0x90, Mode 07/0A, UDS 19 02 on the ECM) before the 2026-10-28 dealer visit.
6. PASS rule used by the parser: 0x3A/0x87 at or above 3965 ms, no test-failed bits on P0440/P0455/P0456, EVAP readiness complete.

## Why CUORE could not read the odometer

- Mode 01 PID A6 (odometer) is a later SAE J1979 addition (2019 onward); this 2018 ECM does not advertise it: its supported-PID list (`raw/10_A4_mode01_supported_pids.json`, 46 PIDs, ECM 18DAF110) stops at 0x72 and does not include 0x80, the bitmap that would announce the 0x81 to 0xA0 range, nor A6.
- On this car the odometer lives in the IPC/BCM behind manufacturer-specific UDS DIDs that are not in CUORE's DID registry (MES reads it there). The only odometer CUORE holds is the ECM freeze-frame DID 2001 (medium confidence).
- Tonight's IPC identity read errored with `CAN ERROR` after returning only the VIN and part number (`raw/37_B2_identity_IPC.json`), so no IPC read was available either.

## Tooling note

- The first attempt (`raw/attempt1_COM1_abort/`) aborted because CUORE had no `CUORE_OBD_PORT` set and fell back to the MES registry port, which resolved to COM1; every live call returned 503 LinkUnavailable and the runner sent nothing else. The fix is the user-level environment variable `CUORE_OBD_PORT=COM3`. The second attempt is the scan above.
- The scan status is 'partial' (DASM, DTCM, ESM unread; identity errors), so the exported bundle carries a warning and is not finalized.
- The runner and parser used are in `tooling/`. The baseline is the 2026-10-19 read (`tooling/baseline_2026-10-19.json`).
