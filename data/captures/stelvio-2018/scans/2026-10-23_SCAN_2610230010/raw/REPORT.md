# CUORE scan report, 2026-10-22

Source: C:\Users\User\AppData\Local\Temp\claude\C--Users-User\b392762d-d462-4aec-a062-100f3568b08f\scratchpad\scan_2026-10-22  (57 readable files). baseline loaded: baseline_2026-10-19.json.
Unparseable files: none.
Runner manifest: 57 steps, 13 issues.

## 1. Legislated OBD

- MIL: off (stored DTC count in PID 01: 0)
- Warm-ups since clear: 14    Distance since clear: 342 km
- Distance with MIL on (PID 21): 0 km

Readiness monitors since clear (Mode 01 PID 01):
| Monitor | State |
|---|---|
| Misfire | complete |
| Fuel system | complete |
| Comprehensive components | complete |
| Catalyst | complete |
| **Evaporative system** | **INCOMPLETE** |
| Oxygen sensor | complete |
| Oxygen sensor heater | complete |
| EGR system | complete |
**EVAP monitor: INCOMPLETE**
This drive cycle (PID 41): Comprehensive components=complete; EGR system=incomplete
CUORE's own EVAP line: EVAP monitor has NOT run since the last clear. Absence of an EVAP code right now carries no information. Complete the drive cycle first.

Legislated DTCs (Modes 03 / 07 / 0A):
- stored: none reported
- pending: P0440, P0455, P0456
- permanent: P0440, P0456

Mode 06 test results:
| OBDMID/TID | Test | Value | Min | Max | Result | Unit |
|---|---|---|---|---|---|---|
| **0x3A/0x87** | **EVAP monitor 0.090" leak** | **496** | **3707** | **65535** | **FAIL** | **ms** |
| 0x3C/0x85 | EVAP monitor 0.020" leak | 4722 | 0 | 4200 | FAIL (scaling unknown) | - |
| 0x3C/0x86 | EVAP monitor 0.020" leak | 15379 | 0 | 6000 | FAIL (scaling unknown) | - |
| **0x3C/0x90** | **EVAP monitor 0.020" leak** | **6096** | **0** | **6000** | **FAIL** | **ms** |
| 0x3D/0xA0 | EVAP purge flow monitor | 65535 | 19660 | 65535 | PASS (scaling unknown) | - |
| 0x3D/0xA1 | EVAP purge flow monitor | 196 | 63 | 326 | PASS (scaling unknown) | - |
(bold = the two EVAP proof tests: 0x3A/0x87 and 0x3C/0x90)
- 0x3A/0x87 vs baseline: now 496 (min 3707, max 65535); baseline 0 (min 0, max 0)
- 0x3C/0x90 vs baseline: now 6096 (min 0, max 6000); baseline 6000 (min 0, max 6000)

Voltage:
- ATRV before: 14.5 V
- ATRV after: 14.5 V
- PID 42 control module voltage: 14.312 V
- Baseline voltages: ATRV_adapter=14.4 V, BCM_DID_1004=0 V

Freeze frame (Mode 02, frame 0):
- PID 02: 18DAF110: DTC P0455; 18DAF118: not read
- PID 05: 18DAF110: 56 C
- PID 0F: NO DATA (warning: no ECU returned a freeze frame (none stored, or ignition off))
- PID 46: 18DAF110: 10 C
- PID 2F: 18DAF110: 82.745 %

## 2. Modules

| Module | VIN (F190) | Part (F187) | SW (F188) | SW ver (F189/F195) | HW (F191/F192) | vs baseline |
|---|---|---|---|---|---|---|
| BCM (Body Computer Marelli (949), gateway) | ZASFAKPN5J7B88115 | 50554114 | 52154912 | NRC {"18DAF140": "requestOutOfRange"} | 52058054 / BCM949M_C02 | SAME |
| DASM (Driver assistance radar Bosch) | not read |  |  |  |  | NOT READ: no identity file for this module |
| DTCM (Magna Q4 Transfer Case) | not read |  |  |  |  | NOT READ: no identity file for this module |
| ECM (Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)) | ZASFAKPN5J7B88115 | 50544870 | 52170619 | NRC {"18DAF110": "requestOutOfRange"} / hex:0000 | 52055320 / MM10JAHW232 | CHANGED (now: HEX:0000; baseline had: 'VER 0000' FOR SUPPLIER SW P235QB39 IS FROM THE CEL DOC / ADDRESSING.PY (MES); STORE F195 RETURNED 00 00., 18DA10F1, 18DAF110, 2026-10-19T00:30:25) |
| ESM (ZF Electronic Gear Shift Module) | not read |  |  |  |  | NOT READ: no identity file for this module |
| IPC (Instrument Panel Continental) | ZASFAKPN5J7B88115 | 50551318 | not read | not read | not read | SAME |
| RFHUB (Radio frequency hub Continental) | ZASFAKPN5J7B88115 | 50544008 | 52091977 | NRC {"18DAF1C7": "requestOutOfRange"} / hex:0940 | 52057995 / 10161500AA | CHANGED (now: HEX:0940; baseline had: 18DAC7F1, 18DAF1C7, 2026-10-19T00:30:25, C:\PROGRAMDATA\CUORE\OBSERVATIONS.JSONL) |
| TCM (ZF 8HP50/75 Automatic Gearbox) | ZASFAKPN5J7B88115 | 46337308 | 52119227 | NRC {"18DAF118": "requestOutOfRange"} / hex:0003 | 52097735 / 10344202761 | CHANGED (now: HEX:0003; baseline had: 18DA18F1, 18DAF118, 2026-10-19T00:30:25, C:\PROGRAMDATA\CUORE\OBSERVATIONS.JSONL) |
- Address discovery (22 F190): no node answered at the candidate addresses tried.

## 3. DTCs per module (UDS 19 02)

Status legend (cuore.live.obd.DTC_STATUS_BITS): b0=testFailed; b1=testFailedThisOperationCycle; b2=pendingDTC; b3=confirmedDTC; b4=testNotCompletedSinceLastClear; b5=testFailedSinceLastClear; b6=testNotCompletedThisOperationCycle; b7=warningIndicatorRequested. ECM availability mask 0xCF: b4 and b5 are not implemented there, so those two bits are never read as set/clear.
Shown per module: EVAP codes first (always, even if clear or absent), then every code with any of b0/b1/b2/b3/b5/b7 set. Not-run-since-clear (b4/b6 only) codes are counted, not listed.

### ECM (Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0))
Tracked 117 codes, availability mask 0xCF; 117 with a not-completed bit. Source B1_uds_19_02_all_modules.
| Code | Status | Decoded | vs baseline |
|---|---|---|---|
| **P0440-00** | 0x4D | b0 testFailed, b2 pendingDTC, b3 confirmedDTC, b6 testNotCompletedThisOperationCycle [b4/b5 n/i] | no baseline |
| **P0455-00** | 0x4D | b0 testFailed, b2 pendingDTC, b3 confirmedDTC, b6 testNotCompletedThisOperationCycle [b4/b5 n/i] | no baseline |
| **P0456-00** | 0x4D | b0 testFailed, b2 pendingDTC, b3 confirmedDTC, b6 testNotCompletedThisOperationCycle [b4/b5 n/i] | no baseline |

### BCM (Body Computer Marelli (949), gateway)
Tracked 153 codes, availability mask 0x4F; 150 with a not-completed bit. Source B1_uds_19_02_all_modules.
| Code | Status | Decoded | vs baseline |
|---|---|---|---|
| B101D-15 | 0x4D | b0 testFailed, b2 pendingDTC, b3 confirmedDTC, b6 testNotCompletedThisOperationCycle [b4/b5/b7 n/i] | no baseline |
| B10AA-4A | 0x08 | b3 confirmedDTC [b4/b5/b7 n/i] | no baseline |
| B1176-97 | 0x08 | b3 confirmedDTC [b4/b5/b7 n/i] | no baseline |
| U1736-87 | 0x08 | b3 confirmedDTC [b4/b5/b7 n/i] | no baseline |

### DASM (Driver assistance radar Bosch)
NO DATA: B1_uds_19_02_all_modules: skipped: no confirmed address

### DTCM (Magna Q4 Transfer Case)
NO DATA: B1_uds_19_02_all_modules: skipped: no confirmed address

### ESM (ZF Electronic Gear Shift Module)
NO DATA: B1_uds_19_02_all_modules: skipped: no confirmed address

### IPC (Instrument Panel Continental)
Tracked 2 codes, availability mask 0x4F; 0 with a not-completed bit. Source B1_uds_19_02_all_modules.
| Code | Status | Decoded | vs baseline |
|---|---|---|---|
| U1736-86 | 0x0E | b1 testFailedThisOperationCycle, b2 pendingDTC, b3 confirmedDTC [b4/b5/b7 n/i] | no baseline |
| U1736-87 | 0x0E | b1 testFailedThisOperationCycle, b2 pendingDTC, b3 confirmedDTC [b4/b5/b7 n/i] | no baseline |

### RFHUB (Radio frequency hub Continental)
Tracked 0 codes, availability mask 0xCF; 0 with a not-completed bit. Source B1_uds_19_02_all_modules.
No active/history codes.

### TCM (ZF 8HP50/75 Automatic Gearbox)
Tracked 44 codes, availability mask 0xCF; 44 with a not-completed bit. Source B1_uds_19_02_all_modules.
No active/history codes.

## 4. EVAP proof verdict

Rule: PASS = 0x3A/0x87 >= 3965 ms AND no test-failed bits (b0, b1, and b5 where implemented) on P0440/P0455/P0456 AND EVAP readiness complete. INCOMPLETE = EVAP monitor not yet complete. FAIL otherwise. UNDETERMINED is added by this parser only when a needed reading is missing (an unread value is never counted as pass or fail).

**EVAP proof verdict: INCOMPLETE** - EVAP monitor has not completed since the last clear; nothing else is conclusive yet.

- EVAP readiness (PID 01): INCOMPLETE
- Mode 06 0x3A/0x87: value 496 ms (min 3707, max 65535) vs required >= 3965 ms -> BELOW
- P0440-00: status 0x4D; test-failed bits SET (checked mask 0x03); remaining: b2 pendingDTC, b3 confirmedDTC, b6 testNotCompletedThisOperationCycle [b4/b5 n/i]
- P0455-00: status 0x4D; test-failed bits SET (checked mask 0x03); remaining: b2 pendingDTC, b3 confirmedDTC, b6 testNotCompletedThisOperationCycle [b4/b5 n/i]
- P0456-00: status 0x4D; test-failed bits SET (checked mask 0x03); remaining: b2 pendingDTC, b3 confirmedDTC, b6 testNotCompletedThisOperationCycle [b4/b5 n/i]
- Legislated pending list contains P0440, P0455, P0456
- Legislated permanent list contains P0440, P0456

## 5. EVAP inputs

| Input | This scan | Baseline |
|---|---|---|
| Ambient air temp (PID 46) | 8 C | not read |
| Intake air temp (PID 0F) | NO DATA (warning: no ECU answered this PID; the port reads 14.4 V, so the engine is runni) | not read |
| Fuel level (PID 2F) | 45.882 % | not read |
| ECM DID 1001 fuel level (bytes 77) | 46.7 % (A*100/255, formula from CUORE snapshot layout, medium confidence) | - |
Flags: none

## 6. Network (U-codes)

- ECM: none with a status bit set   (U-codes tracked: 3)
- BCM: U1736-87 0x08   (U-codes tracked: 38)
- DASM: NO DATA (B1_uds_19_02_all_modules: skipped: no confirmed address)
- DTCM: NO DATA (B1_uds_19_02_all_modules: skipped: no confirmed address)
- ESM: NO DATA (B1_uds_19_02_all_modules: skipped: no confirmed address)
- IPC: U1736-86 0x0E, U1736-87 0x0E   (U-codes tracked: 2)
- RFHUB: none with a status bit set   (U-codes tracked: 0)
- TCM: none with a status bit set   (U-codes tracked: 0)

- U1711: not present (no status bit set / not tracked)
- U1712: not present (no status bit set / not tracked)
- U1713: not present (no status bit set / not tracked)
- U1711 and U1712 together: neither present; U1713: absent
- Voltage below 12.0 V: none among the readings above

## 7. Camera / ParkView / PAM

- No ParkView / PAM / camera module identity answered (codes checked: PAM). Silence on CAN-C is not proof the module is absent if it sits on another bus.

## Field sources used

Name-variant lookups that matched a key (label -> key found in the JSON):

- availability mask -> `availability_mask`
- baseline dtcs -> `dtc`
- baseline identity -> `module_identity`
- baseline m06 mid -> `mid`
- baseline m06 tid -> `tid`
- baseline mil -> `mil_on`
- baseline mode06 -> `mode06`
- baseline readiness -> `readiness_pids`
- baseline voltages -> `voltages`
- discover hits -> `hits`
- distance since clear -> `distance_since_clear`
- dtc status -> `status`
- freeze by_ecu -> `by_ecu`
- identity fields -> `fields`
- identity module -> `ecu`
- mil_on -> `mil_on`
- mode06 by_ecu -> `by_ecu`
- mode06 results -> `results`
- module dtc records -> `dtcs`
- module name -> `ecu`
- modules table -> `modules`
- monitor complete -> `complete`
- monitor name -> `monitor`
- obd pending codes -> `dtcs`
- obd permanent codes -> `dtcs`
- obd stored codes -> `dtcs`
- pid by_ecu -> `by_ecu`
- pid unit -> `unit`
- pid value -> `value`
- readiness counters -> `drive_cycle_counters`
- readiness monitors -> `monitors`
- readiness since_clear -> `since_clear`
- readiness this_drive_cycle -> `this_drive_cycle`
- scan modules -> `modules`
- voltage volts -> `volts`
- warm-ups since clear -> `warmups_since_clear`

Files by role: did=10, discover=1, dtc_detail=3, freeze=5, identity=5, mode06=1, modules=1, obd_dtcs=1, other=8, pid=14, readiness=1, scan=1, status=1, supported=1, verify=1, vin=1, voltage=2
