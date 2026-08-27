# Corpus Baseline — Vehicles, DTCs and Provenance

**Source:** `C:\Program Files (x86)\MultiEcuScan\` — 88 files (79 `FESLog_*`, 9 `SCAN_*`), MES 5.4.
**Captured:** 2026-08-27. **The corpus is live** — MES wrote three new files during analysis.

---

## 1. Provenance split — read this first

| | Count |
|---|---|
| FESLog files | 79 |
| ...of which **SIMULATION MODE** (fake) | **54** |
| ...real | 25 |
| SCAN files | 9 (none carry a simulation marker — provenance *unverifiable*, not confirmed real) |
| **Real files total** | **34** |
| Files containing DTCs | 14 real, 8 simulated |
| Raw DTC occurrences | 107 |
| **Distinct codes** | **36** = 34 real + 2 simulation-only (zero overlap) |

**68% of the FES corpus is practice data.** Any fault history that does not filter simulation logs is actively misleading.

### Simulation tell-tales
`ECU ISO code: 7C 86 4F FF FF` · `VIN code: 5188214` (7-digit fake) or `55188214` · `ECU serial number: 281011421` · `Functioning time (EEPROM): 2089177087` · `Vehicle speed: 3240 km/h` · DTCs `B0110-15` / `P068A-68` (these two appear **only** in simulation data — never build them into a real lookup table).

---

## 2. Vehicles

### Real vehicles (2)

| VIN | Vehicle | Evidence |
|---|---|---|
| `ZASFAKPN5J7B88115` | **Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir** (MY2018, Giorgio 949) | 11 FESLog + 5 SCAN |
| `ZFBCFABH1EZ020882` | **Fiat 500L 1.4 16V T-Jet/MultiAir** (MY2014, Small Wide 330) | 1 FESLog + 3 SCAN |

### Simulation-only vehicle profiles (5)
`Alfa Romeo Tonale 1.3 Plug-in Hybrid` (2) · `Alfa Romeo Tonale 1.5 Hybrid` · `Alfa Romeo Stelvio 2.9 V6 24V TwinTurbo` · `Alfa Romeo 4C 1750 TBi` · `Alfa Romeo 166 3.0 V6 24V`

### Filename vs content mismatch
Filename says `Fiat 500L 1.4 16V T-JetMultiAir`; content line 3 says `Fiat 500L 1.4 16V T-Jet/MultiAir`. MES strips `/` when building the filename. **Never join the two strings.**

12 real Fiat 500L FESLogs have an **empty** `VIN code:` — the ECU returned nothing. VIN presence is not guaranteed even in real logs.

---

## 3. Real DTC catalog

Descriptions are verbatim MES output. **No code has more than one description variant in this corpus.**

### P-codes (Powertrain) — all FESLog, all FTB `-00`

| Code | MES description | ECU | Vehicle | Files | First seen | Last seen |
|---|---|---|---|---|---|---|
| `P0098-00` | Air temperature sensor | IAW 10JA (2.0) | Stelvio | 1 | 2025-09-24 13:45 | 2025-09-24 13:45 |
| `P00F5-00` | Humidity sensor | IAW 10JA | Stelvio | 1 | 2025-09-24 13:45 | 2025-09-24 13:45 |
| `P0440-00` | Evaporation control valve | IAW 10JA | Stelvio | 1 | 2026-08-27 11:19 | 2026-08-27 11:19 |
| `P0455-00` | Evaporation system leak | IAW 10JA | Stelvio | 1 | 2026-08-27 11:19 | 2026-08-27 11:19 |
| **`P0456-00`** | **Evaporation system leak** | IAW 10JA | Stelvio | **2** | **2025-09-24 13:45** | **2026-08-27 11:19** |
| `P105E-00` | Humidity sensor | IAW 10JA | Stelvio | 1 | 2025-09-24 13:45 | 2025-09-24 13:45 |
| `P1189-00` | Intake pressure sensor | IAW 10JA | Stelvio | 1 | 2025-09-24 13:45 | 2025-09-24 13:45 |
| `P1D33-00` | Clutch self-calibration enable | Marelli SELESPEED/DDCT | Fiat 500L | 3 | 2025-11-15 11:14 | 2025-11-15 12:08 |
| `P1D34-00` | End of line / service self-calibration | Marelli SELESPEED/DDCT | Fiat 500L | 7 | 2025-11-15 11:14 | 2025-11-15 12:12 |

> **`P0456-00` spans 2025-09-24 (114,008 km) to 2026-08-27 (140,572 km) — a chronic small EVAP leak of ~26,500 km.** `P0440` and `P0455` are new as of 2026-08-27. This is the load-bearing finding of the whole corpus and it is invisible if a tool reports only "latest seen".

`P1D33`/`P1D34` also appear **bare, with no description**, in the post-clear re-read block where clearing returned `FAILED`. Same codes, description simply omitted.

### B-codes (Body) — all SCAN

| Code | MES description | Module | Vehicle | Files | First | Last |
|---|---|---|---|---|---|---|
| `B1011-18` | Number plate lights - Current too low/below threshold | BCM (330) | 500L | 1 | 2025-11-15 10:53 | 2025-11-15 10:53 |
| `B1014-15` | Left stop light - Short to +V or open circuit | BCM (330) | 500L | 3 | 2025-11-15 10:53 | 2025-11-15 12:08 |
| `B1015-15` | Right stop light - Short to +V or open circuit | BCM (330) | 500L | 3 | 2025-11-15 10:53 | 2025-11-15 12:08 |
| `B1029-64` | Lost communication with Steering module (SCM) - Signal/message plausibility | IPC | Stelvio | 1 | 2026-08-27 11:31 | 2026-08-27 11:31 |
| `B102E-64` | Communication with Body Computer (BCM/NBC) - Signal/message plausibility | IPC | Stelvio | 1 | 2026-08-27 11:31 | 2026-08-27 11:31 |
| `B1040-64` | Communication with Body Computer (BCM/NBC) - Signal/message plausibility | RFHUB | Stelvio | 2 | 2026-06-07 10:03 | 2026-08-27 11:31 |
| `B1176-97` | Rear left window riser - Component or system operation obstructed or blocked | BCM (949) | Stelvio | 1 | 2026-08-27 11:31 | 2026-08-27 11:31 |
| `B11A1-11` | Left daylight - Short circuit to ground | BCM (330) | 500L | 3 | 2025-11-15 10:53 | 2025-11-15 12:08 |
| `B11A2-11` | Right daylight - Short circuit to ground | BCM (330) | 500L | 3 | 2025-11-15 10:53 | 2025-11-15 12:08 |
| `B11AF-18` | Parking lights (right) - Current too low/below threshold | BCM (330) | 500L | 1 | 2025-11-15 10:53 | 2025-11-15 10:53 |
| `B11B0-18` | Parking lights (left) - Current too low/below threshold | BCM (330) | 500L | 1 | 2025-11-15 10:53 | 2025-11-15 10:53 |

### C-codes (Chassis) — all SCAN, all DASM, all FTB `-86`

| Code | MES description | Vehicle | Files | First | Last |
|---|---|---|---|---|---|
| `C1403-86` | EPS electric steering (NGE) - Signal/message invalid | Stelvio | 1 | 2026-08-27 11:31 | 2026-08-27 11:31 |
| `C1408-86` | ESP control - Signal/message invalid | Stelvio | 1 | 2026-08-27 11:31 | 2026-08-27 11:31 |
| `C141C-86` | Private CAN between HALF and DASM - Signal/message invalid | Stelvio | 2 | 2026-06-07 09:54 | 2026-08-27 11:31 |
| `C1431-86` | Lateral acceleration/YAW sensors - Signal/message invalid | Stelvio | 1 | 2026-08-27 11:31 | 2026-08-27 11:31 |

### U-codes (Network) — all SCAN

| Code | MES description | Module | Vehicle | Files | First | Last |
|---|---|---|---|---|---|---|
| `U0019-87` | B-CAN line - Missing message | ETM; also TPMS | 500L | 1 | 2025-11-15 10:53 | 2025-11-15 10:53 |
| `U0019-88` | B-CAN line - Bus OFF | BCM (330) | 500L | 2 | 2025-11-15 10:53 | 2025-11-15 11:16 |
| `U0100-87` | No communication with engine control unit (ECU) - Missing message | DTCM (Magna Q4) | Stelvio | 2 | 2026-08-27 11:31 | 2026-08-27 11:36 |
| `U1701-86` | Error in communication with engine control unit (ECU) - Signal/message invalid | DASM | Stelvio | 1 | 2026-06-07 10:03 | 2026-06-07 10:03 |
| `U1711-2F` | Brake system (NFR) - Signal/message erratic | BCM (949) | Stelvio | 2 | 2026-06-07 09:54 | 2026-08-27 11:31 |
| `U1712-2F` | Brake system (NFR) - Signal/message erratic | BCM (949) | Stelvio | 2 | 2026-06-07 09:54 | 2026-08-27 11:31 |
| `U1713-2F` | Engine control (NCM) - Signal/message erratic | BCM (949) | Stelvio | 2 | 2026-06-07 09:54 | 2026-08-27 11:31 |
| `U1716-2F` | Electric Steering (NGE) - Signal/message erratic | BCM (949) | Stelvio | 1 | 2026-08-27 11:31 | 2026-08-27 11:31 |
| `U1736-87` | Convergence Telematic Node (NCV) - Missing message | BCM (330) | 500L | 1 | 2025-11-15 11:16 | 2025-11-15 11:16 |
| `U2054-87` | Error in communication with Body Computer Module (BCM) - Missing message | RFHUB | Stelvio | 1 | 2026-08-27 11:31 | 2026-08-27 11:31 |

### Ambiguities

**MES descriptions are not a unique key** — four strings are shared by two codes each:
- `Evaporation system leak` -> `P0455-00` **and** `P0456-00`
- `Humidity sensor` -> `P00F5-00` **and** `P105E-00`
- `Communication with Body Computer (BCM/NBC) - Signal/message plausibility` -> `B102E-64` **and** `B1040-64`
- `Brake system (NFR) - Signal/message erratic` -> `U1711-2F` **and** `U1712-2F` (looks like an MES catalog defect)

**`U0019` is the only code observed with two different FTBs** (`-87` and `-88`), confirming the suffix is an independent failure-type byte. **Key on code+suffix, never code alone.**

---

## 4. Failure type byte (FTB) inventory — corpus-grounded

MES prints the failure phrase itself after the last ` - `, and it is perfectly consistent per suffix across the corpus. **These meanings are read off real FCA ECU output, not recalled from a standard.**

| FTB | Occurrences | Distinct codes | Letters | MES's own phrase |
|---|---|---|---|---|
| `00` | 21 | 9 | P | *(none — no sub-type)* |
| `11` | 8 | 2 | B | Short circuit to ground |
| `15` | 8 | 2 | B | Short to +V or open circuit |
| `18` | 6 | 3 | B | Current too low/below threshold |
| `2F` | 14 | 4 | U | Signal/message erratic |
| `64` | 7 | 3 | B | Signal/message plausibility |
| `86` | 11 | 5 | C **and** U | Signal/message invalid |
| `87` | 11 | 4 | U | Missing message |
| `88` | 3 | 1 | U | Bus OFF |
| `97` | 2 | 1 | B | Component or system operation obstructed or blocked |
| `68` | 8 | 1 | P | *(SIMULATION ONLY — do not trust)* |

FTBs cluster by code letter: `00` is P-exclusive; `11/15/18/64/97` B-exclusive; `87/88/2F` U-exclusive; `86` is the only one crossing letter classes (C and U).

---

## 5. Regex false-positive analysis

Pattern under test: `\b([PCBU][0-9A-F]{4}(?:-[0-9A-F]{2})?)\b`

### With `\b` on **both** sides: ZERO false positives across all 88 files.
An exhaustive overlapping character-by-character scan confirmed every word-bounded match is a genuine DTC. A case-insensitive variant finds no additional matches.

### But the `\b` is doing all the work. Weaken either boundary and 7 false positives appear:

| Bad match | Source line | Field | Files |
|---|---|---|---|
| `B8811` | `VIN code: ZASFAKPN5J7B88115` | VIN | 16 |
| `BCFAB` | `VIN code: ZFBCFABH1EZ020882` | VIN | 4 |
| `B1754` | `ECU serial number: TD4192427B17540` | serial | 9 |
| **`BC330`** | `Hardware number: BC330I.0100 - Ver: 04` | **hardware** | 3 |
| `C1114` | `Hardware number: A2C11140400 - Ver: 01` | hardware | 5 |
| `C3292` | `Hardware number: A2C32923302 - Ver: 01` | hardware | 1 |
| `C8264` | `Hardware number: A2C82649000 - Ver: 02` | hardware | 1 |

**`BC330` is the one to watch** — preceded by a space (clean leading boundary), only the trailing `I` blocks the match. A hardware number one character different would produce a real false positive.

### If the class is widened to `[0-9A-Z]`, two word-bounded false positives appear immediately:
`CODES` from `READING ERROR CODES:` and `PROXI` from `PROXI configuration write counter:`.

### Fields to exclude by NAME rather than relying on `\b`
`ECU ISO code` · `ISO Code` · `VIN code` · `ECU serial number` · `Spare part number` · `Hardware number` · `Software number` · `Homologation number` · `FIAT drawing number` · `- Ver:` values

### Recommendation
Keep `\b` on both sides and the strict `[0-9A-F]` class, **and anchor extraction to the two contexts MES actually uses**:
- SCAN: lines after `Errors found:` until a blank line
- FESLog: lines after `READING ERROR CODES:` matching `^\d+\. `

That reduces false-positive surface to essentially nil regardless of corpus growth.

---

## 6. Module fault status across the corpus

| Module | Clean reads | Reads with faults | Notable |
|---|---|---|---|
| `ECM` | 11 | **0** | never faulted in a SCAN; EVAP codes come from FES sessions |
| `BCM` | 5 | **8** | the busiest fault reporter |
| `DASM` | 4 | **5** | all `-86` signal-invalid |
| `TCM` | 9 | 4 | 500L DDCT self-calibration codes |
| `DTCM` | 5 | 4 | `U0100-87` transfer case |
| `IPC` | 9 | 2 | |
| `RFHUB` | 6 | 3 | |
| `ESM` | 11 | 0 | |
| `ETM` / `TPMS` | 0 | 2 each | `U0019-87` B-CAN |
| `ABS` / `ORC` / `HVAC` / `EPS` | 2 each | 0 | |

**Only one no-response event in the entire corpus:** the aborted scan with 5x `Connection failed!` and zero modules enumerated. Every other module MES attempted did answer.

### Actuator/procedure failures
`FAILED TO EXECUTE` appears 13x. Stelvio ECM -> `Electronic thermostat`; 500L TCM -> `Clutch self-calibration enable`. The interlock reason prints on the following line (`Engine running`, `Incorrect conditions to run this test!`, `Request out of range error`, `Transmission not in Park`).

---

## 7. Two findings worth acting on

### 7.1 SGW is not blocking this vehicle
multiecuscan.net lists Giulia/Stelvio among 2018+ models with confirmed Security Gateway presence, and SGW blocks actuators, procedures and DTC clearing. **Yet this car's logs show `CLEARING STORED FAULT CODES` returning `SUCCESS` on BCM, IPC, DTCM, RFHUB and DASM across four separate sessions.** Write access is evidently not gated here. Do not warn about SGW for this VIN. *(Mechanism unresolved — under investigation.)*

### 7.2 The Stelvio's recurring pattern is a comms cascade, not five faults
BCM reporting NFR/NCM/NGE erratic · RFHUB reporting BCM missing · IPC reporting SCM and BCM implausible · DASM reporting EPS/ESP/YAW/HALF invalid · DTCM reporting `U0100-87` — **every one is a `U`/`C` communication code**, all pointing at a single network or power event.

> **Proposed reporting rule:** when >=3 modules each hold only `U0xxx`/`U1xxx`/`Cxxxx` codes with FTB `-87` (missing message) or `-2F` (erratic), and no module holds a component-level `B`/`P` code, collapse them into a **single network-event finding** rather than five module faults.

The two genuine component faults in the same scans are `B1176-97` (rear-left window riser obstructed, BCM) and the `P0455`/`P0456` EVAP pair on the ECM.

**Timeline 2026-08-27:** 11:12 connection failed -> 11:19 FES: 3 EVAP codes, cleared -> 11:31 SCAN: 14 DTCs across 5 modules -> 11:36 SCAN: 1 DTC (`U0100-87`), cleared -> 11:41 SCAN: **clean, 0 faults across all 8 modules**.

---

## 8. Unidentified strings

1. **`UNKNOWN/UNSUPPORTED`** — MES's own placeholder when an ECU answers but its ISO code is absent from MES's database (`English.txt` string 2004: `WARNING: Unknown ISO code. Module cannot be identified!`). Seen on Fiat 500L `Gearbox / ESM/GSM/NSC`, `ISO Code: 2A 80 02 0B 8C`. **Treat as a sentinel, keep ISO/HW/SW as identity, surface as "responded but unidentified by MES".**

2. **`Instrument Panel MTA`** — Alfa 4C, simulation log. Module class is unambiguously IPC. `MTA` is almost certainly the supplier (MTA S.p.A.) rather than a functional acronym — UNCERTAIN. Carry as an opaque supplier token; do not expand.
