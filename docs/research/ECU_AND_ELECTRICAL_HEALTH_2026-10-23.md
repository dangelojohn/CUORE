# ECU and electrical-system health dossier, 2026-10-23

2018 Alfa Romeo Stelvio 2.0T Q4, VIN ZASFAKPN5J7B88115. Built from tonight's CUORE captures only (no new contact with the car, no clear, no job or MES change).

**Conditions at the time of the reads.** Engine running at idle: PID 0C 750 rpm, speed 0, coolant 73 C (`raw/28`, `raw/29`, `raw/30`), and the runner itself logged "the port reads 14.4 V, so the engine is running" (`raw/manifest.json` issues, steps A9_pid4D, A9_pid4E, A9_pid0F). A 10 A charger was connected [OWNER, per the capture brief]. CAN-C only, cable declared none (`raw/03`). The older line in `SCAN_2026-10-23_POST_ESIM.md` that says "engine off" is contradicted by these readings. Nothing in this file was cleared.

**Labels.** [CUORE] a reading, with its file. [OWNER] stated by the owner. [INFERENCE] the reviewer's reasoning. [EXTERNAL] a procedure or rule of thumb from outside this repo, never a reading and never a Stelvio specification.

**File keys.** `raw/NN` = `data/captures/stelvio-2018/scans/2026-10-23_SCAN_2610230010/raw/NN_*.json` (the 57-step scan, 00:09:48 to 00:12:01). `live/NN` = `data/captures/stelvio-2018/live_inputs/2026-10-23/NN_*` (the later read-only capture, 00:15:55 to 00:27; copied into the repo with this dossier so the citations resolve; its own `INDEX.md` describes it). `base` = `.../tooling/baseline_2026-10-19.json` (pre-clear 10-19 values). `SW levels` = `docs/vehicles/ZASFAKPN5J7B88115/MODULE_SOFTWARE_LEVELS.md`.

---

## 1. Computers on the car

Addresses from `raw/04` (request / response, 29-bit). Identity numbers from `raw/34` to `raw/38` (read 00:10:55 to 00:11:16). DTC counts are the records the module returned to UDS 19 02 mask FF (`raw/33`, 00:10:50); most records are "tracked, not run" entries at 0x40, so the second number is the count with any failure, pending or confirmed bit. "Highest status" is the most active byte seen.

| Module | Bus, address | HW part F187 | SW part F188 | Supplier SW F194 / ver F195 | HW F191 / F192 | Serial F18C | Answered tonight | DTC records (with bits) | Highest status |
|---|---|---|---|---|---|---|---|---|---|
| ECM (Marelli IAW 10JA, 2.0) | CAN-C 18DA10F1 / 18DAF110 | 50544870 | 52170619 | P235QB39 / 00 00 | 52055320 / MM10JAHW232 | TD4192427B17540 | yes (identity, DTCs, PIDs, DIDs) | 117 (3) | 0x4D (P0440, P0455, P0456) |
| TCM (ZF 8HP) | CAN-C 18DA18F1 / 18DAF118 | 46337308 | 52119227 | GK0902OE2HN / 00 03 | 52097735 / 10344202761 | TF0662057729150 | yes (identity, DTCs, 12 Mode 01 PIDs) | 45 records, 44 distinct (P1DCE-00 listed twice) (0) | 0x40 |
| BCM (Marelli 949, gateway) | CAN-C 18DA40F1 / 18DAF140 | 50554114 | 52154912 | not returned (identity read ended in CAN ERROR after F192); 10-19 base: 04441660441 | 52058054 / BCM949M_C02 | TD3692377101420 | yes (DTCs, DIDs); identity partial | 153 (4) | 0x4D (B101D-15) |
| IPC (Continental cluster) | CAN-C 18DA60F1 / 18DAF160 | 50551318 | not returned (CAN ERROR after F187); 10-19 base: 52128619 | 10-19 base: AR952 HL | 10-19 base: 52075458 / A2C11140400 | 10-19 base: TC4861807R07900 | yes (DTCs); identity partial | 2 (2) | 0x0E (U1736-86, U1736-87) |
| RFHUB (Continental RF hub) | CAN-C 18DAC7F1 / 18DAF1C7 | 50544008 | 52091977 | 10307064AB / 09 40 | 52057995 / 10161500AA | T04Z22117E01040 | yes | 0 | none |
| DTCM (Magna Q4 transfer case) | CAN-C 18DA29F1 (address unverified) | not read | not read | not read | not read | not read | **no**: discovery probe `22 F190` at 0x29 returned no hit (`raw/52`); DTC sweep skipped, no confirmed address | not read | not read |
| ESM (ZF gear shift) | CAN-C, no address known | not read | not read | not read | not read | not read | **no**: no address | not read | not read |
| DASM (Bosch radar) | CAN-C, no address known | not read | not read | not read | not read | not read | **no**: no address | not read | not read |
| ABS (Continental MK C1) | CAN-CH, 18DA2AF1 / 18DAF12A (discovered 10-15) | not read | not read | not read | not read | not read | **no**: needs the grey A6 cable; silent to CUORE since 2026-10-15 00:12 (`base` module_identity ABS) | not read | last ABS DTC read ever: MES 2026-09-04 (U1700-87, C104B-92, cleared) |
| Radio/nav (ETM 0x6F), HVAC, amplifier and the other CAN-IHS nodes | CAN-IHS | not read | not read | not read | not read | not read | **no**: no route with cable none; the blue A5 cable work is pending (`raw/manifest.json` no_read_only_path.radio_ETM; `base` modules_not_reached_by_cuore) | not read | not read |

Notes.

- All five answering modules returned F190 = ZASFAKPN5J7B88115 (`raw/34` to `raw/38`). F189 is requestOutOfRange in every module asked (`raw/34` to `raw/38`); F132 is requestOutOfRange in ECM, BCM, TCM, IPC and RFHUB (`raw/39` to `raw/43`).
- Software numbers equal the 10-19 baseline for every field the baseline holds (ECM, TCM, BCM, RFHUB F187/F188/F18C/F191/F192; IPC F187) (`base` module_identity). The "CHANGED" flags in `raw/REPORT.md` for ECM, RFHUB and TCM are comparison artefacts: the baseline stored a note string where tonight's read returned the F195 bytes [INFERENCE from `base`]. ECM continuity over the year is in `SW levels`.
- The BCM and IPC identity reads ended in `CAN ERROR` while the same calls' DTC reads worked (`raw/35`, `raw/37`, `raw/33`). That is a read-path error on two identity sequences, not a recorded module fault [INFERENCE].
- CUORE's scan status is "partial" for the reasons in this table (`docs/research/SCAN_2026-10-23_POST_ESIM.md`, Tooling note).

---

## 2. ECM internal health

### 2.1 Self-diagnostic codes

**No internal-processor, memory or supply-voltage code is recorded in the ECM.** Evidence [CUORE `raw/33`]: the ECM returned 117 records; 114 are at 0x40 (test not completed this operation cycle, nothing else) and only P0440-00, P0455-00 and P0456-00 carry failure bits (0x4D each). The 117 records contain no P0600 to P0606 code, no P0560 to P0563 code and no P0A-range code. The only P05xx entries are P050C, P0531, P058A and P05BD, all 0x40.

How to read the absence [INFERENCE, taken from `docs/research/CEL_2026-10-19_DIAGNOSIS.md`, section "What the ECM has and has not verified", where the same logic was applied to the 10-13 to 10-19 lists]: P0562, P0563 (system voltage low/high) and P0606 (control module processor) were listed at 0x40 on 09-25 and are absent from every later ECM list, which that document reads as "the monitor completed with no failure and no pending or confirmed bit". Tonight's list continues that pattern. Limits stated there and repeated here: availability mask 0xCF means b4 and b5 (not completed since clear, failed since clear) are not implemented, so a one-off dropout that set no code leaves no trace, and a pass leaves no history.

Other entries in the ECM list that nobody has sourced in this repo (all 0x40, none interpreted here): U1008-00, U0684-00, U04A0-00, P1607-00, C0608-00, C0574-00, C051C-00 (`raw/33`; U1008 is flagged "not sourced in this repo" in the CEL document).

Other modules' own-health entries, for completeness [CUORE `raw/33`]: TCM lists P0606-00 and P061B-00 at 0x40 (tracked, not failed). BCM lists B1000-44, -45, -46 and -47 at 0x40; by the failure-type table in `mes-log-mcp/mes/dtc.py` those suffixes are data memory, program memory, calibration memory and watchdog/safety failure types, and the base code B1000 has no sourced description in the repo. None of them has a failure bit.

### 2.2 ECM DIDs and counters read tonight

| Item | Reading | Formula and confidence | Source |
|---|---|---|---|
| IBS state of charge, DID 19BD | 0x43 = **67 %** at 00:11:49; the live poll showed 67 % at 00:19:03 and 00:20:40 | `A`, unit %. Catalogue confidence "unverified" (`cuore/live/addressing.py`, source danardi78, "UNVERIFIED on 2.0T"); the freeze-frame decoder rates it "medium" (`cuore/live/dtc_detail.py`: Table C, 100 % at the cold-start P0456 as in MES). No independent calibration exists in the repo. | `raw/47`, `live/21`, `live/23` |
| Battery voltage, DID 1955 | requestOutOfRange (not supported on this ECM) | `((A*256)+B)*0.5/1000` in the catalogue; moot | `raw/48` |
| Fuel level, DID 1001 | 0x77 = 119 -> **46.7 %** | `A*100/255`, medium | `raw/49`; PID 2F in the same scan reads 45.882 % (`raw/27`) |
| Ambient/atmospheric pressure, DID 1956 | bytes 03 E9 = 1001 as a direct mbar value, i.e. about **1001 mbar** | The catalogue formula `(A*256+B)-32768` gives -31767 and cannot be right for this car; the freeze-frame decoder reads the two bytes directly as mbar (low confidence). PID 33 in the same scan reads 100 kPa (`raw/31`), which agrees with the direct reading [INFERENCE]. | `raw/50`; `live/23` shows the catalogue formula's wrong output (-31767) |
| Time since start (engine-on timer), DID 1009 | **17.25 min** at 00:19:03 and **18.25 min** at 00:20:40 | `((A*256)+B)/4`, unverified. PID 1F in the same snapshots reads 1007 s and 1135 s (16.8 and 18.9 min), so the DID tracks run time to within about a minute [INFERENCE]. Not read in the 57-step scan. | `live/21`, `live/23` |
| Number of ECU programming events, DID 2003 | **4** | `A`, unverified (catalogue note "anti-tamper / service-history value"). No earlier reading exists in the repo copy of `observations.jsonl` (copied 2026-10-20). Read only in the live poll. | `live/23` |
| Maximum RPM recorded (over-rev log), DID 2005 | **0** | `A`, unverified; a value of 0 is unexplained and is not evidence that no over-rev ever happened | `live/23` |
| Odometer, DID 2001 | **147,144.7 km** | `(A*65536+B*256+C)/10`, medium. Continues the freeze-frame series (146,879.1 / 147,103.7 / 147,134.9 km). The owner-stated dashboard figure is 148,207 km, 1,062 km higher; unexplained, listed as an open check in `SCAN_2026-10-23_POST_ESIM.md`. | `live/23`; section 2.4 |

Run and reset counters that exist on this car [CUORE]:

- Warm-ups since clear 14, distance since clear 342 km (PID 30, PID 31) (`raw/11`); distance with MIL on 0 km on both ECM and TCM (PID 21, `raw/21`); MIL off, stored DTC count 0 (`raw/11`).
- Startups counter (UDS snapshot DID 200A) and operating time (DID 1008, minutes, high confidence): 14,627 and 298,835 min at P0455; 14,634 and 299,157 min at P0440; 14,636 and 299,246 min at P0456 (`raw/46`, `raw/44`, `raw/45`). That is 9 starts and 411 min between the first and last snapshot.
- No engine-hours value: PID 4D, 4E and 7F are not advertised and the 4D/4E reads returned nothing (`raw/10`, `raw/22`, `raw/23`; `cuore/live/capabilities.py` engine_hours_available = False).
- No watchdog, brown-out or reset counter exists in CUORE's registry of 44 DIDs (`live/02_channels.json`). The question "has the ECM been resetting?" therefore cannot be answered from counters; the only indirect evidence is the absence of P0562/P0563/P06xx in section 2.1.

### 2.3 Freeze-frame voltage fields

- Mode 02 freeze frame (frame 0) was read for PIDs 02, 05, 0F, 46 and 2F only (`raw/16` to `raw/20`); no voltage PID was part of it, so there is **no Mode 02 voltage field**.
- The UDS 19 04 snapshots hold DID 1004 (battery voltage, `/10`, medium) for each EVAP code [CUORE]:

| Code | Startups | Battery voltage DID 1004 | Condition stored with it | Source |
|---|---|---|---|---|
| P0455-00 | 14,627 | bytes 00 8E = **14.2 V** | 819 rpm, 1.6 km/h, coolant 56 C, IBS SoC 73 % | `raw/46` |
| P0440-00 | 14,634 | bytes 00 8F = **14.3 V** | 1103 rpm, 42.1 km/h, coolant 61 C, IBS SoC 75 % | `raw/44` |
| P0456-00 | 14,636 | bytes 00 78 = **12.0 V** | 0 rpm, 0 km/h, coolant 12 C (key-on, engine off, cold), IBS SoC 100 % | `raw/45` |

  [INFERENCE] The P0456 pair (12.0 V beside an IBS SoC of 100 %) does not obviously agree. Either the 12.0 V is a key-on loaded figure and the SoC value is a clamp or stale value, or the SoC scaling is wrong. Because the SoC formula is unverified, an SoC number should not be used as battery-health evidence on its own.

### 2.4 DTC extended data (occurrence and aging counters) for the EVAP codes

[CUORE `raw/44`, `raw/45`, `raw/46`, UDS 19 06] Each of P0440, P0455 and P0456 returned one decoded record: record 1, one byte, **0x60**, which CUORE labels "occurrence counter ... unverified for FCA". The remaining bytes (`80 28 60 81 00 60 83 00`, from record 0x80 onward) are identical on all three codes and are not decoded; CUORE refuses to guess their meaning, and so does this dossier.

[INFERENCE] 0x60 is the same value on three different codes (and, per `docs/research/NETWORK_PATTERN_READINGS_2026-10-20.md`, on BCM and ECM codes read on 10-13 and 10-19), so it behaves as a constant, not a count. **No usable occurrence counter or aging counter was obtained.** The age of each code is better taken from the startups and operating-time fields in section 2.2.

---

## 3. Electrical system

### 3.1 Every voltage reading tonight

| # | Reading | Time | Source and condition | File |
|---|---|---|---|---|
| 1 | Adapter ATRV **14.5 V** (vehicle power detected) | 00:09:50 | OBD port pin 16 via the adapter; engine idling, charger connected | `raw/07` |
| 2 | PID 42 control module voltage: ECM **14.312 V**, TCM **14.062 V** (bytes 37 E8 and 36 EE) | 00:10:30 | Each module's own supply measurement, same request | `raw/24` |
| 3 | BCM DID 1004 = 0x91 = 145 -> **14.5 V** | 00:11:57 | BCM supply, formula `A/10` unverified | `raw/51` |
| 4 | ECM DID 1955 | 00:11:51 | not supported (requestOutOfRange) | `raw/48` |
| 5 | ATRV after the UDS sweep **14.5 V** | 00:12:01 | as row 1; the note on the step says "compare with A1 for charger/battery sag": no sag between 00:09:50 and 00:12:01 | `raw/53` |
| 6 | Adapter voltage at the start of the later capture **14.5 V** | 00:15:55 | as row 1 | `live/00_voltage_start.json` |
| 7 | Live poll: PID 42 **14.312 V**, BCM DID 1004 **14.5 V**, battery_voltage channel **14.5 V** then **14.4 V**; run time 1007 s then 1135 s | 00:19:03 and 00:20:40 | all-channel poll session already running (not started by the capture) | `live/21`, `live/23` |
| 8 | Recording, four rows: battery_voltage **14.4 V** in every row; PID 42 **14.312 V** in the two rows that have it (69 s and 71 s) | 00:19 to 00:23 | CUORE recording of the poll session | `live/26_live_recording.csv` |
| 9 | Stored with EVAP freeze frames: 14.2 V, 14.3 V, 12.0 V | earlier events | see section 2.3 | `raw/46`, `raw/44`, `raw/45` |
| 10 | IBS state of charge **67 %** (ECM DID 19BD) | 00:11:49 | unverified formula | `raw/47` |

Observations on the table [INFERENCE]:

- All live values sit between 14.06 and 14.5 V, inside the generic 13.8 to 14.8 V charging window quoted in `wiki/Network-and-Brake-Findings.md` ([EXTERNAL] rule of thumb, not a Stelvio specification). With a charger connected the number cannot be credited to the alternator or the battery.
- PID 42 on the ECM did not move from 14.312 V over roughly ten minutes (rows 2, 7, 8). A value flat to the millivolt is what a regulated source (the charger) would give; it says nothing about ripple.
- The port, BCM, ECM and TCM read 14.5, 14.5, 14.31 and 14.06 V: a spread of 0.44 V. The ECM-to-TCM offset was 0.25 V tonight and 0.285 V on 2026-10-14 (ECM 14.25 V, TCM 13.965 V, `base` voltages). The offset is repeatable, but the reads are not simultaneous and module ADC tolerance is unknown, so it is a lead for the ground-drop and feed checks in 3.4, not a finding.
- BCM DID 1005 (the IBS composite: state of charge, temperature, voltage, current) returned nothing in the poll (`live/23`, bcm_1005 = None). It was read once on 10-19 00:33:38 (formulas unverified): SoC 71 %, temperature 15 C, voltage 14.76 V, current 1.4 A (`base` voltages).

### 3.2 History line

| Date and time | Reading | Source |
|---|---|---|
| 2026-09-04 20:01:10 (read date; counter 14280) | ABS freeze frame of **U1700-87** ("Body computer", FTB 87 = missing message): battery **10.6 V**, speed 0, brake pedal off. The only low-voltage reading in the repo corpus. The stored startups counter 14280 is one count before the ECM's first EVAP freeze frame (14281) and about 19 starts before the 2026-08-27 10:57 scan (14299), so [INFERENCE] the event itself was in late August (at 5 to 7 starts a day, roughly three days before 08-27), not on 09-04. The ABS was cleared that evening and has not been read since. | `docs/research/NON_EVAP_CODES_2026-10-20.md` section 3.1 and `NETWORK_PATTERN_READINGS_2026-10-20.md` (MES FESLog_2609042001) |
| 2026-10-13 20:09 and 20:38 | IBS SoC 62 % and 63 % | `base` ECM_DID_19BD_IBS_SoC |
| 2026-10-13 20:28 and 2026-10-19 00:25 | BCM DID 1004 inside the U1713 snapshots: 0x89 (13.7 V) then 0x91 (14.5 V) | `NETWORK_PATTERN_READINGS_2026-10-20.md` |
| 2026-10-14 19:01 | PID 42: ECM 14.25 V, TCM 13.965 V | `base` voltages |
| 2026-10-19 00:23 to 00:34 | Adapter 14.4 to 14.5 V; BCM DID 1004 0x90/0x91; IBS SoC 71 % | `base` voltages |
| 2026-10-23 | Tonight, section 3.1 | |

[INFERENCE] SoC 62, 63, 71, 67 over ten days moves in the same direction as charge state, but the conditions differ (charger on tonight) and the formula is unverified, so no trend is claimed.

### 3.3 The open electrical leads (BCM and IPC codes)

All statuses are UDS 19 02 bytes read at 00:10:50 [CUORE `raw/33`]. "Baseline" is the BCM/IPC read of 10-19 00:30:25, which was before the 00:39 clear of ECM, DTCM, BCM and DASM (`base` timeline).

| Code | Module | Status tonight | Decode | Baseline and history |
|---|---|---|---|---|
| **B101D-15** | BCM | **0x4D** | b0 testFailed, b2 pending, b3 confirmed, b6 testNotCompletedThisOperationCycle. b1 (failed this cycle) is clear and b6 is set. [INFERENCE] the failed result is carried from an earlier cycle and the test has not yet re-run in tonight's cycle. | Listed at 0x40 (not run, no failure) on 2026-10-13 (`docs/vehicles/ZASFAKPN5J7B88115/sessions/2026-10-13-live-read-2.json`) and on 10-19 (`base`), and absent from all earlier failure tables (`NON_EVAP_CODES_2026-10-20.md`). **New since 10-19.** |
| B1176-97 | BCM | 0x08 | confirmed only. Per the repo, a rear-left window-riser motor circuit code; FTB 97 = obstructed or blocked (`mes-log-mcp/mes/dtc_descriptions.py`, `NON_EVAP_CODES_2026-10-20.md` section 3.4). | Absent on 10-19. Previously returned 1 to 14 days after each clear. A local mechanical item, not a supply code. |
| U1736-87 | BCM | 0x08 | confirmed only. U1736 = Entertainment/Telematic Module (ETM) missing message, "ETM node on B-CAN, no signal/message": a communication error between the ETM and other modules, not an ETM-internal fault (`dtc_descriptions.py`, single source dtcdecode.com, checked 2026-10-13). | Absent on 10-19. |
| **U1736-86 and U1736-87** | IPC | **0x0E** each | b1 testFailedThisOperationCycle, b2 pending, b3 confirmed. Both failed during tonight's operation cycle. | 0x0C on 10-13 20:24 (no this-cycle bit) (`NON_EVAP_CODES_2026-10-20.md`); the IPC listed no codes on 10-19 (`base`). **Returned and failing this cycle.** |
| B10AA-4A | BCM | 0x08 | confirmed only. PROXI "check configuration failed", FTB 4A = incorrect component installed (`dtc_descriptions.py`, single source dtcdecode.com). | Absent on 10-19; first seen 10-14 and cleared. |

**B101D-15, decoded as far as the data allows.**

- The suffix **-15** is the failure-type byte "short to +V or open circuit" (`mes-log-mcp/mes/dtc.py` failure-type table, source "corpus", confidence "confirmed"). In plain terms: the BCM saw the monitored circuit either shorted to battery positive or not connected at all; the code cannot say which.
- The BCM tracks a sibling **B101D-11** ("short circuit to ground", 0x40, not failed) (`raw/33`). So the circuit has both a ground-side and a positive/open-side monitor, and only the positive/open side has failed.
- **Which circuit B101D names is not sourced anywhere in the repo.** `mes-log-mcp/mes/dtc_descriptions.py` has no B101D entry, and a grep of the repo (code, docs, wiki, archive) finds no description. The phrase "battery-voltage circuit code" in `SCAN_2026-10-23_POST_ESIM.md`, the dealer sheet E6 and the job note was an unsourced label and should be treated as a guess. [INFERENCE, pattern only] it is a BCM circuit in the B10xx block that is monitored for both short-to-ground and short-to-+V/open (neighbours B100A/B100B/B100C, B1011 to B1018 and B102C also appear as -11/-15 pairs in `raw/33`); that says nothing about which load or sensor it is. [EXTERNAL] the dealer's wiTECH service information would name the circuit.
- **No snapshot was read.** The scan's detail reads covered only the ECM EVAP codes (`raw/44` to `raw/46`; `raw/manifest.json` ecm_evap_codes_detailed). No B101D-15 freeze frame, extended data or BCM voltage-at-event exists, so it cannot be said what the supply voltage was when it failed. This is the open reading the earlier job note calls "read B101D-15 detail with the charger off, no clear".
- It is a stand-alone BCM circuit code. Whether it relates to the 10.6 V ABS event, to the network cluster or to nothing is **not established**.

U1736 pair [INFERENCE]: both modules complain about the ETM, none complains about itself, and the ETM has never been read (it sits on CAN-IHS, no route tonight). That points at the ETM node or the bus branch it sits on, not at the cluster or the BCM. The ESIM replaced on 10-22 is the EVAP leak-detection part [OWNER, per the job] and has no stated link to the ETM; whether anything else on the head unit, antenna or a dashcam was touched since 10-08 is the open owner question from `NON_EVAP_CODES_2026-10-20.md` section 3.2.

**The old network cluster.** U1711, U1712 and U1713 are absent in every module that answered (`raw/33`, `raw/REPORT.md` section 6), after 14 warm-ups and 342 km since the 10-19 clear (`raw/11`). The longest clear-to-return seen was 14 days, so the proof criterion (three reads over at least 21 days) is not met [`NON_EVAP_CODES_2026-10-20.md`, group resolution criteria].

### 3.4 What cannot be judged tonight, and the test for each

Why: the car was on a 10 A charger with the engine idling, so every voltage above is charger-plus-alternator, not the battery or the charging system alone. The tests below are **procedures from outside this repo [EXTERNAL]**; the numbers are generic rules of thumb, not a Stelvio specification, and no reading in this file depends on them.

| Not judgeable tonight | Why | Owner test (procedure) |
|---|---|---|
| **Battery state of health** | Charger connected; surface charge; SoC DID unverified | Disconnect the charger and every load. Leave the car off with doors closed for at least 1 h (the wiki page `Network-and-Brake-Findings` asks for 12 h before the test). Measure at the battery posts with a DMM. The repo's wiki quotes about 12.4 V or less at rest as weak (generic). A resting voltage cannot show capacity; for that a load or conductance test is needed (dealer or parts store). |
| **Cranking behaviour** | No start was recorded; both scans began with the engine already running | In a CUORE session, start a recording of PID 42 and BCM DID 1004 with the key on before cranking, then crank and let it run. The channel registry's default rate is 1 Hz (`live/02_channels.json`), so a 1 to 2 s crank dip can be missed or leave a gap; expect to compare the last sample before and the first after. A DMM with min-hold at the battery posts catches the true minimum. Generic rule of thumb: a cranking dip below about 9.6 V is poor. |
| **Alternator ripple** | Charger masks the alternator; PID 42 is flat 14.312 V and has no ripple information; CUORE has no ripple channel | Charger off, engine at about 2,000 rpm, then with headlights, blower and rear defrost on. DMM on AC volts (or a scope) across the battery posts. A shop rule of thumb is that more than about half a volt of AC suggests a failing diode. Also record the DC value: 13.8 to 14.8 V is the generic window. |
| **Parasitic drain** | A running car on a charger cannot show key-off current | Charger off. Clamp meter (DC, mA resolution) around the battery negative lead, or the lead leaving the IBS, with the clamp zeroed first. Close all doors, lock, remove the key and keep the fob away. Watch for 30 to 40 min while the modules go to sleep; the reading should fall and settle. A value that stays high after that wait is the lead, then pull fuses one at a time. Do not disconnect the battery during the wait; it restarts the sleep timers. As a cross-check, BCM DID 1005 carries a current term (unverified formula, `live/02_channels.json`). |
| **Ground drops** | No measurement of the grounds or feeds exists | Engine running, then cranking, under load (headlights, blower, defrost). DMM on DC millivolts, probes on bare metal: battery negative post to engine block; battery negative post to the body near the BCM and rear power-distribution centre; engine block to body strap. Positive side: battery positive post to the alternator B+ stud, and across the BCM feed fuses (fuse F82 in the rear PDC and the stand-alone BCM fuse named in STAR S1808000005, `docs/research/NETWORK_PATTERN_LITERATURE_2026-10-20.md`). Generic rule: a drop above roughly 0.1 to 0.2 V on a ground path under load is worth chasing. This also tests the repeatable ECM-versus-TCM voltage offset of section 3.1. |

**What the dealer's IBS test adds [EXTERNAL, ask the dealer].** A calibrated battery test (conductance or load) giving capacity against rating, which neither a resting voltage nor the SoC DID gives; the IBS state of charge and health as wiTECH reports them, compared with a measured value; a loaded charging-system test; and a wiTECH read of the BCM, which can include the B101D-15 freeze frame and the circuit name that CUORE could not get. The repo found no Alfa-specific source saying a Stelvio needs an IBS registration after a battery swap (dealer sheet B6), so that is a question, not a requirement. TSB S1408000384 (start-stop charging lamp, IBS state of charge) is in the catalogue and its PDF has not been opened (dealer sheet B6).

---

## 4. Verdict (reviewer's inference)

**[INFERENCE]** The captures give no sign of a sick computer. The ECM records no internal, processor or supply-voltage fault, and its only failure bits are the three EVAP codes; software and hardware numbers are identical to the 10-19 read for every module that answered, and the ECM has been on the same calibration all year; the old network cluster U1711/U1712/U1713 has not returned in 14 warm-ups and 342 km. What stays open is electrical and on the BCM and IPC side: the U1736 pair (the IPC reports it failing in tonight's cycle, the BCM holds it confirmed) points at the entertainment/telematics node, and B101D-15 (BCM, short to +V or open, new since 10-19, status 0x4D, no snapshot read, circuit name unsourced) is the one fresh electrical code. The battery and charging system could not be judged at all, because the charger was connected; the only low-voltage reading on record remains the ABS 10.6 V from late August (read on 09-04). The readings neither show a supply problem nor rule one out.

**Ranked next three** (each is a test the owner can do; none clears a code):

1. **Rested, charger-off voltage, then running voltage with the charger off, then a CUORE read of the BCM (19 02 status byte of B101D-15, plus detail/snapshot if the BCM provides it) and DID 1004 before anything is cleared.** Cheapest, and it decides whether B101D-15 is failing now (b0) and what the battery looks like without the charger.
2. **Cranking voltage record (CUORE recording of PID 42 and DID 1004 plus a min-hold meter), with the ground-drop checks under load.** Targets the one low-voltage event on record and the ECM/TCM voltage offset.
3. **Key-off current after a 30 to 40 min sleep with a clamp meter, then the dealer's battery/IBS test on 2026-10-28 with a request to read the B101D-15 snapshot and to look at the ETM (U1736).**

Also open but outside the voltage line: the ETM on CAN-IHS has never been read (blue A5 cable work pending), and the ABS has been silent since 10-15.
