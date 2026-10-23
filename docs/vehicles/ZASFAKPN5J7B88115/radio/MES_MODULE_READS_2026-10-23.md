# MES module reads, 2026-10-23 (01:12 to 01:27), 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115

Source: six MultiEcuScan 5.4 logs from `C:\Program Files (x86)\MultiEcuScan`, copied unchanged to `data/captures/stelvio-2018/mes_logs/`. Everything below is quoted from those logs unless it is marked [inference] or [OWNER]. Label for every reading: **MES reading 2026-10-23**. The logs do not record which cable was on the car. [OWNER] statement, not in any log: adapter alone for radio and engine, blue for climate, grey for ABS/parking/airbag.

## What these logs do and do not contain

- **No radio/nav (ETM), no HVAC, no ABS, no parking and no airbag module was read.** None of the six logs names one of those modules as a read target. The only trace of the radio is the fault text "Entertainment Telematic Module (ETM)" held by other modules (below). There are therefore no radio software version, screen/variant or HVAC identity fields in these files.
- The modules that were read: ECM, IPC (Instrument Panel Continental), BCM (identity only), plus an 8-module scan that lists ECM, IPC, TCM, DTCM, ESM, BCM, RFHUB and DASM.
- **Two write actions are in the logs and are not reads:** (1) the scan ended with "CLEARING STORED FAULT CODES" on ECM, IPC, BCM and DASM, all "SUCCESS"; (2) an IPC "Service Interval Reset" ("NEXT SERVICE KM RESET", "COMPLETED"). The BCM log ends at an "Indicators command" adjustment that asks for a SECURITY CODE; the log shows no outcome. See "Actions" below.
- None of the logs carries the banner "SIMULATION MODE". SCAN logs have no simulation marker at all, so provenance of the SCAN is VIN-matched only (every module block reports VIN ZASFAKPN5J7B88115).

## Files

| # | File | Size (bytes) | Time in log | Type | Module / content |
|---|---|---|---|---|---|
| 1 | SCAN_2610230112.txt | 5808 | file saved 01:12:14 | scan (scan + clear) | 8-module scan, then clear |
| 2 | FESLog_2610230114_...txt | 18607 | 01:13:10 | session with adjustment | "Service Interval Reset" on IPC (ISO 00 03 50 8B 14) |
| 3 | FESLog_2610230116_...txt | 6867 | 01:16:10 | info + errors + parameters | Instrument Panel Continental (IPC) |
| 4 | FESLog_2610230118_...txt | 651 | 01:17:49 | info | Magneti Marelli IAW 10JA (ECM) |
| 5 | FESLog_2610230124_...txt | 78 | none | failed connect | no module: "Failed to connect to Body Computer (BCM)" |
| 6 | FESLog_2610230127_...txt | 657 | 01:26:54 | info + adjustment | Body Computer Marelli (949) (BCM) |

(`...` = `_Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir`.) CUORE corpus (`/api/logs?limit=500`): 59 logs before, 65 after. All six were also imported through `POST /api/tests/{vin}/mes-import` (see the end).

## Instrument cluster (IPC), MES reading 2026-10-23 (cable not recorded in log)

Identification (file 3, verbatim):

```
Instrument Panel Continental
ECU ISO code: 00 03 50 8B 14
VIN code: ZASFAKPN5J7B88115
FIAT drawing number: 50551318
Hardware number: A2C11140400
Hardware version: 01
Software number: AR952 HL
Software version: 203C
Homologation number:
Functioning time (EEPROM): 240193
Operating time: 240193
Startups counter: 14644
VIN lock status: Locked by odometer
PROXI configuration write counter: 1
```

Scan block (file 1): "Hardware number: A2C11140400 - Ver: 01", "Software number: AR952 HL - Ver: 203C". The FIAT drawing number 50551318 equals the F187 value CUORE read from the IPC at 00:11 (`MODULE_SOFTWARE_LEVELS.md`). CUORE could not read the IPC software number; this is the first software number for the IPC. No serial number is printed in the IPC log.

**Odometer: 148207.0 km** in file 3 (repeated in every parameter block, and in file 2). Owner-stated: 148,207 km. They are identical.

Errors:
- File 1, before the clear: `U1736-86 - Entertainment Telematic Module (ETM) - Signal/message invalid`, `U1736-87 - Entertainment Telematic Module (ETM) - Missing message`, `U0010-88 - BH-CAN - Bus OFF`. U1736-86 and U1736-87 match CUORE's 00:10 read (status 0x0E each, dealer sheet E3). **U0010-88 BH-CAN Bus OFF is new**; CUORE's IPC read did not list it.
- File 3 (01:16, after the clear): `READING ERROR CODES: No fault codes`.
- These logs hold no status byte and no environment/freeze data for any code; MES prints only the code and failure-type text.

Key parameters (last block of file 3, verbatim): Odometer 148207.0 km; Audible signal (Buzzer) volume 2; Dashboard illumination 4; External temperature 9.0 °C; Battery voltage 11.7 V; Fuel level 50 %; Engine speed 0 rpm; Vehicle speed 0 km/h; Seat belt alarm Enabled; Gear engaged P. Configuration-like fields: "VIN lock status: Locked by odometer", "PROXI configuration write counter: 1".

Service interval data (file 2), before and after "NEXT SERVICE KM RESET":

| Field | Before | After |
|---|---|---|
| Odometer | 148207.0 km | 148207.0 km |
| Distance after last service | 142475 km | 148207 km |
| Last service date | 09/12/2026 | 10/23/2026 |
| Number of services | 0 | 0 |
| Service interval | 16000 km | 16000 km |
| Service period | 365 days | 365 days |
| Distance till next service | 10268.0 km | 16000.0 km |
| Days till next service | 324 days | 365 days |

[inference] "09/12/2026" is 12 September (41 days before 10/23, matching 365 - 324 = 41). The reset moved the service counters to "now"; it did not change the odometer.

## Radio / navigation (ETM), HVAC, ABS, parking, airbag

Not read. No identification, errors or parameters exist in these logs. What the logs say about the ETM, verbatim, from other modules:
- IPC: `U1736-86 ... Signal/message invalid`, `U1736-87 ... Missing message`.
- BCM (file 1): `U1736-87 - Entertainment Telematic Module (ETM) - Missing message`.

No ABS code appears in any module block. The only C-code in the scan is `C141B-97 - Camera blinded/obstructed/blocked` in the DASM. [OWNER] statement that the radio sits on CAN-C is already in the job note on c70f2f3e6932.

## Engine (ECM), MES reading 2026-10-23 (adapter alone, per owner)

Identification (file 4, verbatim):

```
Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)
ECU ISO code: 00 01 50 40 18
VIN code: ZASFAKPN5J7B88115
ECU serial number: TD4192427B17540
Spare part number: 50544870
Hardware number: MM10JAHW232
Hardware version: 00
Software number: P235QB39
Software version: 0000
Homologation number: FIBA00
FIAT drawing number: 52055320
Functioning time (EEPROM): 299301
Operating time: 299376
Startups counter: 14644
VIN lock status: Locked by odometer
PROXI configuration write counter: 1
```

Matches CUORE's 00:10 read (serial, part 50544870, HW 52055320, supplier P235QB39 / 0000). Errors (file 1, before the clear): `P0455-00 - Evaporation system leak`, `P0440-00 - Evaporation control valve`, `P0456-00 - Evaporation system leak`, `B25CB-00 - Driver's door open/close switch`. B25CB-00 is not in CUORE's 00:10 ECM list. No status or environment data in the log.

## Body computer (BCM), MES reading 2026-10-23 (cable not recorded in log)

Identification (file 6, verbatim):

```
Body Computer Marelli (949)
ECU ISO code: 00 00 70 7C 15
VIN code: ZASFAKPN5J7B88115
ECU serial number: TD3692377101420
FIAT drawing number: 50554114
Hardware number: BCM949M_C02
Hardware version: 01
Software number: 04441660441
Software version: 1454
Homologation number:
Functioning time (EEPROM): 246669
Operating time: 246680
Startups counter: 14644
VIN lock status: Locked by odometer
PROXI configuration write counter: 1
```

File 6 then reads (verbatim, end of file): `EXECUTING ADJUSTMENT...` / `Indicators command` / `SECURITY CODE`. No result line follows. [inference] MES asked for a security code; the log does not say whether one was entered. File 5 (78 bytes, 01:24), verbatim, is the whole file:

```
Reading CAN configuration data ...
Failed to connect to Body Computer (BCM)
```

It is a failed connect attempt, three minutes before the successful BCM read in file 6.

BCM errors (file 1, before the clear): `U1736-87 - Entertainment Telematic Module (ETM) - Missing message`; `B1176-97 - Rear left window riser - Component or system operation obstructed or blocked`; `B10AA-4A - PROXI configuration control - Incorrect component installed` (a configuration field: the PROXI check names an incorrect component); `B101D-15 - Windscreen heated washers - Short to +V or open circuit`. These four equal CUORE's 00:10 BCM codes.

The MES BCM software number 04441660441 v1454 is a different numbering from CUORE's F188 value 52154912 (see `MODULE_SOFTWARE_LEVELS.md` notes); the BCM FIAT drawing number 50554114 equals CUORE's F187.

## Other modules in the scan (file 1, identification verbatim)

| Module | Name line | ISO code | Hardware number - Ver | Software number - Ver | Errors found |
|---|---|---|---|---|---|
| TCM | ZF 8HP50/75 Automatic Gearbox | 00 0B 50 AA 14 | 10344202761 - 20 | GK0902OE2HN - 0003 | none listed |
| DTCM | Magna Q4 Transfer Case | 00 43 50 91 14 | M0045027.01 - 21 | M0099947 - 0501 | none listed |
| ESM/GSM/NSC | ZF Electronic Gear Shift Module | 00 16 50 B4 14 | 1000597140 - 08 | 1000678050 - 0019 | none listed |
| RFHUB | Radio frequency hub (RFHUB) Continental | 00 41 50 89 15 | 10161500AA - 01 | 10307064AB - 0940 | none listed |
| DASM | Driver assistant system module (DASM) radar Bosch | 00 39 70 7E 15 | MRR1evo14F - 00 | 52081920 - 0500 | `C141B-97 - Camera blinded/obstructed/blocked - Component or system operation obstructed or blocked` |

TCM and RFHUB values equal CUORE's 00:10 F192/F194/F195 reads. DTCM, ESM and DASM were not read by CUORE; these are their first software numbers.

## Actions in the logs (writes, not reads)

1. **Fault-code clear, end of file 1** (verbatim): `CLEARING STORED FAULT CODES...` then SUCCESS for Engine / ECM (00 01 50 40 18), Dashboard / IPC (00 03 50 8B 14), Body / BCM (00 00 70 7C 15), Other / DASM (00 39 70 7E 15). The codes listed above were present just before. A clear erases stored codes and restarts readiness monitors, so the EVAP proof that CUORE found INCOMPLETE at 00:10 restarts [inference]; file 3 shows the IPC empty ("No fault codes") at 01:16. CUORE's MES-import entry for this scan lists the pre-clear codes as stored; read it as "present at 01:12, then cleared".
2. **IPC service interval reset** (file 2), table above.
3. **BCM "Indicators command" adjustment** (file 6), outcome not logged.

## Raw text

All six logs are plain text that CUORE's parsers decode (SCAN: 8 modules, 12 codes; each FES: 1 module). Nothing was undecodable, so no raw block is needed beyond the verbatim quotes above. Originals: `data/captures/stelvio-2018/mes_logs/`.

## CUORE import

`POST /api/tests/ZASFAKPN5J7B88115/mes-import` accepted all six (ledger ids SCAN_2610230112, FES_2610230114, FES_2610230116, FES_2610230118, FES_2610230124, FES_2610230127). Only the SCAN carries codes; the five FES logs report "No data: no DTC or readiness read this scan".
