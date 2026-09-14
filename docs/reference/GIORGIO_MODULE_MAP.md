# Giorgio module map (draft) — Stelvio 2.0T Q4, MY2018, VIN ZASFAKPN5J7B88115

Compiled 2026-09-14 from this car's own MES scans, the MES vendor capability
matrix, the stelvio_scan address table, the danardi78 Giulia/Stelvio PID
repository, the OBDLink FRPM rev F, and factory pinout threads. Every value is
tagged `CONFIRMED` (primary source or this car's own logs), `INFERRED`
(derived, reasoning stated) or `UNVERIFIED` (single weak or unsourced claim).
"unknown" is a valid entry. This file is data for `cuore/live/buses.py` and
`cuore/live/addressing.py`; do not encode an `UNVERIFIED` address as fact.

## The structural finding

Every Stelvio scan in the archive taken with no cable (`SCAN_2606070954`,
`2606071003`, `2608271131`, `2608271136`, `2608271141`, `2609021445`,
`2609041953`) finds the same eight modules, and `SCAN_2609042008` alone finds a
disjoint six. That is a hardware bus partition observed seven times:

- **No cable (CAN-C, pins 6/14):** ECM, IPC, TCM, DTCM, ESM, BCM, RFHUB, DASM
- **One cable (CAN-CH, pins 12/13, grey A6):** ABS, EPS, ORC, AFLS, PAM, HALF

The second group is exactly MES's A6/grey list (`MES_INTEGRATION_SURFACE.md:24`)
and the ABS-to-grey binding is documented independently by giuliatech, so
group 2 = grey A6 = CAN-CH is `CONFIRMED`.

This corrects `review-2026-09-14/web_research.md` section 3.2, which placed the
BCM and IPC on CAN-IHS: on this car they answer on CAN-C with no cable. The
Marelli 949 BCM is the gateway and is diagnostically reachable on the C bus.

**The blue A5 / CAN-IHS bus has never been scanned on this car.** HVAC,
ETM/radio, AMP, ESEM, CSWM, CRSM, LBSS/RBSS and PLGM are in MES's database for
this vehicle but in zero logs.

## Table A — modules present on this car

Sources: `SCAN_2609041953.txt`, `SCAN_2609042008.txt`,
`BEFORE_SNAPSHOT_2026-09-13.txt`, `FESLog_2609041957`, `FESLog_2609042001`.

| MES code | Name (MES string) | ISO code | HW (ver) | SW (ver) | Bus | Cable | 29-bit TA (req / resp) | TA source | TA conf. | STN preset |
|---|---|---|---|---|---|---|---|---|---|---|
| ECM | Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0) | `00 01 50 40 18` | MM10JAHW232 (00) | P235QB39 (0000) | CAN-C `CONFIRMED` | none | `0x10` → `18DA10F1` / `18DAF110` | danardi78 header `DA10F1`; ClaudeMarais ESP32 repo | CONFIRMED | `STP 34` (`STP 33` for legislated `7E0/7E8`) |
| TCM | ZF 8HP50/75 Automatic Gearbox | `00 0B 50 AA 14` | 10344202761 (20) | GK0902OE2HN (0003) | CAN-C `CONFIRMED` | none | `0x18` → `18DA18F1` / `18DAF118` | danardi78 header `DA18F1` | CONFIRMED | `STP 34` |
| BCM | Body Computer Marelli (949), gateway | `00 00 70 7C 15` | BCM949M_C02 (01) | 04441660441 (1454) | CAN-C (diag) `CONFIRMED`; gateways IHS | none | `0x40` → `18DA40F1` / `18DAF140` | danardi78 header `DA40F1` (IBS, key position, light switch) | CONFIRMED | `STP 34` |
| IPC | Instrument Panel Continental | `00 03 50 8B 14` | A2C11140400 (01) | AR952 HL (203C) | CAN-C `CONFIRMED` | none | `0x60` → `18DA60F1` / `18DAF160` | danardi78 header `DA60F1` | CONFIRMED | `STP 34` |
| RFHUB | Radio frequency hub Continental | `00 41 50 89 15` | 10161500AA (01) | 10307064AB (0940) | CAN-C `CONFIRMED` | none | `0xC7` → `18DAC7F1` / `18DAF1C7` | danardi78 header `DAC7F1` (TPMS `2240B1..B4`) | CONFIRMED address; INFERRED that it is RFHUB | `STP 34` |
| DTCM | Magna Q4 Transfer Case | `00 43 50 91 14` | M0045027.01 (21) | M0099947 (0501) | CAN-C `CONFIRMED` | none | unknown (`0x29` in stelvio_scan, self-declared unsourced) | — | UNVERIFIED | `STP 34` |
| ESM | ZF Electronic Gear Shift Module | `00 16 50 B4 14` | 1000597140 (08) | 1000678050 (0019) | CAN-C `CONFIRMED` | none | unknown | — | — | `STP 34` |
| DASM | Driver assistance radar Bosch | `00 39 70 7E 15` | MRR1evo14F (00) | 52081920 (0500) | CAN-C `CONFIRMED` (7/7 scans without cable) | none | unknown | — | — | `STP 34` |
| ABS | Continental ABS MK C1 | `00 06 50 5B 14` | 28554010535 (00) | XJ_RAL00165 (83C1) | CAN-CH `CONFIRMED` | grey A6 | `0x28` | stelvio_scan only | UNVERIFIED | `STP 34` (500 k assumed) |
| EPS | ZF Electric Steering | `00 02 40 5F 14` | 7806277500 (30) | 880802D0243 (A410) | CAN-CH `CONFIRMED` | grey A6 | `0x2A` → `18DA2AF1` | danardi78 header `DA2AF1` returns steering angle; conflicts with stelvio_scan SAS `0x76` | INFERRED (medium) | `STP 34` |
| ORC | Airbag / Occupant Restraint (MES: unsupported) | `00 1A 70 84 15` | 0285013327 (30) | BB70578 (0403) | CAN-CH `CONFIRMED` | grey A6 | `0x50` | stelvio_scan only | UNVERIFIED | `STP 34` |
| AFLS | Automotive Lighting adaptive headlights | `00 1D 50 C7 14` | 1470000328 (02) | 1409910330 (000C) | CAN-CH `CONFIRMED` | grey A6 | unknown | — | — | `STP 34` |
| PAM | Parking control Bosch | `00 18 50 87 15` | 19490108 (03) | 1.38 (0304) | CAN-CH `CONFIRMED` | grey A6 | unknown | — | — | `STP 34` |
| HALF | Haptical lane feedback camera Bosch (MFK2) | `00 1E 50 72 14` | 0203500279 (01) | 1037601726 (1001) | CAN-CH `CONFIRMED` (MES lists `ELMA6`) | grey A6 | unknown | — | — | `STP 34` |

Pseudo-entries on the no-cable bus: `PROXI` (CAN Setup / PROXI Alignment (949),
write counter 1) and `SERVICE-RESET` are MES procedures against the BCM, not
separate ECUs. stelvio_scan's `0x6D` for PROXI is `UNVERIFIED` and conceptually
wrong: PROXI is a BCM data area, not a node.

Do not use `0x18DABAF1`: squatted by the BACCAble project's board. `0x18DAC7F1`
carries a documented immobiliser hazard if a BACCAble board is fitted; none is
fitted here, so reading TPMS is safe, but keep the warning in the data.

### Modules MES lists for this car that have never answered

All `UNVERIFIED` presence; bus and cable from the MES vendor capability matrix
(`MES_INTEGRATION_SURFACE.md:24-27`) corroborated by appcar-diagfca.

| Likely code | Name | Bus (inferred) | Cable | Status |
|---|---|---|---|---|
| HVAC | Climate control (TRW) | CAN-IHS | blue A5 | never scanned |
| ETM / EMCM / DSM | AlfaConnect radio-nav / uConnect | CAN-IHS | blue A5 | never scanned |
| AMP | Amplifier | CAN-IHS | blue A5 | never scanned |
| ESEM | Engine sound enhancement | CAN-IHS | blue A5 | never scanned |
| CSWM / CRSM | Comfort seat and wheel / rear seat | CAN-IHS | blue A5 | never scanned |
| LBSS / RBSS | Blind-spot sensors L/R | CAN-IHS | blue A5 | never scanned |
| PLGM | Power liftgate | CAN-IHS | blue A5 | never scanned |
| TVM | Torque vectoring | CAN-CH | grey A6 | did not answer on the A6 scan; likely not fitted (QV item) |
| ESL / NBS | Steering lock (TRW) | CAN-CH | grey A6 | did not answer on the A6 scan |
| SGW | Security Gateway | — | — | presence `UNVERIFIED`; MES never enumerates it |

### `mes/modules.py` cross-check

`giorgio=yes` (35): AAML, AAMR, ABS, AFLS, AMP, BCM, CRSM, CSWM, DASM, DTCM, ECM,
EPB, EPS, ESEM, ESM, ETM, HALF, HVAC, IPC, LBSS, MMCM, NBS, NPG, ORC, PAM, PLGM,
PROXI, RBSS, RFHUB, SCCM, SCRM, SERVICE-RESET, SGW, TCM, TVM.
`giorgio=likely` (23): ADCM, AHBM, AHLM, ASU, DCM, DSCM, ECSB, ELSDM, GPCM, IBS,
NAG, NAP, NPE, NPP, NTR, OCM, RLS, SIS, SRM, TBM, TTM, UAM, WCPM.

Hygiene: SCRM (SCR/AdBlue) and GPCM (glow plugs) are diesel-only and should not
be `yes`/`likely` for a 2.0T petrol. EPB is `yes` but never appears in a scan or
in MES's Stelvio list; the Stelvio's park brake is driven by the ABS/ESC unit.
AAML/AAMR (active aero) are 2.9 QV items. `ModuleInfo` has no `bus` or `cable`
field; Table A's two strongest columns belong there.

## Table B — bus profiles

| Bus | OBD pins | Circuits | Bitrate | ID width | Cable | STN setup | Modules (this car) | Safety |
|---|---|---|---|---|---|---|---|---|
| CAN-C (diagnostic / powertrain) | 6 (+) / 14 (−) | GN D428 / BN D427 | 500 kbps `CONFIRMED` (factory pinout; Racelogic Stelvio doc) | 29-bit UDS + 11-bit legislated | none | `STP 34` (or `STP 33` legislated); `STPBRR` = 500000 | ECM, TCM, DTCM, ESM, BCM, IPC, RFHUB, DASM, PROXI, Service Reset | Live powertrain bus. Writes gated. Whole-vehicle serial UDS sweeps manufacture `-87`/`-2F` bystander codes (`SCAN_2609041953` shows exactly that: DTCM `U0100-87`, BCM `U171x-2F`, EPS `U1960-83`). Pull DTC EX before clearing. |
| CAN-IHS (body / comfort / infotainment) | 3 (+) / 11 (−) | DB D434 / WH D433 | 125 kbps `CONFIRMED` | 29-bit presumed | blue A5 (6→3, 14→11), or possibly none | With A5: `STP 34` then `STPBR 125000`. Without A5: `STP 54` (MS-CAN transceiver on adapter pins 3/11) `UNVERIFIED` | HVAC, ETM, AMP, ESEM, CSWM, CRSM, LBSS, RBSS, PLGM (all `UNVERIFIED` on this car) | Do not mix routes: with the A5 fitted, adapter pins 3/11 map to nothing defined, so use the HS preset plus `STPBR`, never `STP 53/54`. Opening a 500 k preset on a 125 k bus emits error frames; set `STCMM 0` before `STPO` when the rate is in doubt. |
| CAN-CH (chassis / ADAS / safety) | 12 (+) / 13 (−) | GN/WH D478 / BN/WH D477 | 500 kbps `INFERRED` (never measured) | 29-bit presumed | grey A6 (6→12, 14→13), mandatory: the STN1170 has no transceiver on pins 12/13 | `STP 34`; if silent, `STP 36` (250 k) then `STPBR 125000` | ABS/ESC, EPS, ORC, AFLS, PAM, HALF (TVM, ESL not answering) | Never transmit on CAN-CH without explicit human confirmation: brakes, airbag squibs and steering assist live here. Listen first with `STCMM 0` + `STM`. FEPS hazard: the vLinker FS is a Ford tool whose 18 V FEPS output is OBD pin 13, which on Giorgio is CAN-CH(−). Never issue any FEPS or programming-voltage command on this vehicle; whether the FS can be commanded to FEPS over serial is `UNVERIFIED`, treat as live. |
| hazard entry | 1 / 9 | — | — | — | — | — | — | MES vendor warning naming this car: do not use modified interfaces with a short between pins 1 and 9 on Giulia or Stelvio; it drops the bus. Continuity-check any cable before fitting. |

Hard constraint: the STN1170 has one CAN peripheral multiplexed onto different
pins, so only one bus can be active at a time (OBDLink FRPM rev F 8.6). A
"scan all modules" flow is three sequential passes with two physical cable
changes, and every change is a re-plug on a live bus, itself a documented
source of bystander DTCs.

## Table C — known DIDs

Service `0x22`, positive response `0x62`. Formulas in CarScanner syntax (A, B, C
= response data bytes after the echoed DID).

### ECM, Magneti Marelli IAW 10JA, header `18DA10F1`

| DID | Meaning | Formula | Unit | Source | Confidence |
|---|---|---|---|---|---|
| `1000` | Engine RPM | `((A*256)+B)/4` | rpm | danardi78 | CONFIRMED on Giulia 2.2D, UNVERIFIED on 2.0T |
| `1002` | Vehicle speed | `((A*256)+B)/124` | km/h | danardi78 | UNVERIFIED on 2.0T |
| `1003` | Coolant temperature | `(((A*256)+B)*0.02)-40` | °C | danardi78 | UNVERIFIED on 2.0T |
| `1302` | Engine oil temperature | `B` | °C | danardi78 | UNVERIFIED; single-byte `B` looks like a truncated 2-byte field |
| `130A` | Engine oil pressure | `A*10/255` | bar | danardi78 | UNVERIFIED on 2.0T |
| `195A` | Boost pressure | `((A*256+B)-32768)/1000-1` | bar | danardi78 | UNVERIFIED on 2.0T; highest-value DID for this engine, verify first |
| `1935` | Intake air temp (post-turbo) | `(((A*256)+B)*0.02)-40` | °C | danardi78 | UNVERIFIED on 2.0T |
| `1955` | Battery voltage | `((A*256)+B)*(0.5/1000)` | V | danardi78 | UNVERIFIED on 2.0T |
| `192D` | Current engaged gear | `A` | — | danardi78 | UNVERIFIED on 2.0T |
| `19BD` | IBS state of charge | `A` | % | danardi78 | UNVERIFIED on 2.0T |
| `1946`, `1904`, `18E4`, `18DE`, `18A4`, `3807` | rail pressure, DPF, regen | — | — | danardi78 | Diesel-only; do not encode for this car |

### TCM, ZF 8HP50, header `18DA18F1`

| DID | Meaning | Formula | Unit | Source | Confidence |
|---|---|---|---|---|---|
| `1018` | Torque as received from ECM | `((A*256+B)-500)` | Nm | danardi78 | UNVERIFIED on 2.0T. The 8HP never measures torque, it is told torque over CAN (`TRANSMISSION_ZF8HP_Q4.md`), so this is the most informative value on the box |
| `04FE` | Gearbox oil temperature | `A-40` | °C | danardi78 | UNVERIFIED on 2.0T; fluid temp heads the 8HP failure chain, verify early |
| `0518` | DNA mode selector | `A` | — | danardi78 | UNVERIFIED |
| `0540` | DNA mode selector (alt byte) | `C` | — | danardi78 | UNVERIFIED; determine which is authoritative |

### Other confirmed headers worth encoding

| Header | DID | Meaning | Formula | Note |
|---|---|---|---|---|
| `18DA40F1` (BCM) | `1004` | Battery voltage | `A/10` V | conflicts with `web_research.md` listing `1004` under `DA10F1`; resolve by reading both |
| `18DA40F1` | `1005` | IBS composite: SoC `B` %, temp `G-40` °C, voltage `((J*256)+K)/800` V, current `(((L*256)+M)-32768)/100*0.8` A | multi-field | the ground-strap / parasitic-draw instrument |
| `18DA40F1` | `0131` | Key ignition position | `A` | |
| `18DA40F1` | `0133` | External light switch | `(A*256)+B` | |
| `18DA60F1` (IPC) | `0104` | IPC brightness | `A` | |
| `18DA2AF1` (EPS/SAS) | `083C` | Steering angle | `(SIGNED(A)*256+B)/16` ° | answered on pins 6/14 for danardi, so possibly reachable without the grey cable; test here |
| `18DAC7F1` (RFHUB/TPMS) | `40B1`–`40B4` | Per-wheel FL/FR/RL/RR pressure `((A*256)+B)/1000` bar, temp `E-50` °C | | |

### Universal ISO 14229 Annex C DIDs, safe on every module (`CONFIRMED` by standard)

`F190` VIN · `F187` spare part · `F188` ECU SW · `F189` SW version · `F18C`
serial · `F191`/`F192`/`F193` HW · `F194`/`F195` supplier SW · `F197` system
name · `F18B` manufacture date · `F199` programming date · `F186` active
session · `F198` last tester. Already in `stelvio_scan/data/did_catalog.yaml`.
These are the discovery probe: every module in Table A must answer `F190`, so
a no-answer proves a wrong address rather than an unsupported DID. The
`0xF4xx` OBD-mirror block in that YAML is speculative; expect NRC `0x31`.

MES exposes four identity fields with no known DID and they are high value:
`Functioning time (EEPROM)`, `Startups counter`, `VIN lock status`, `PROXI
configuration write counter`. Finding their DIDs is the best-value sweep target.

## Open questions, as read-only command sequences

Preconditions: MES fully closed, ignition on and engine off unless stated,
battery on a proper supply, more than 5 s after MES exits so any extended
session (S3 ≈ 5 s) has timed out. Start every session `ATE0` · `ATWS` · `ATH1`
· `ATS0` · `ATAT0`. Never inherit adapter state.

**Q1. Does `STP 54` reach CAN-IHS with no blue cable?** (highest value per minute)
```
STI              # expect STN1170 v4.3.2
STP 54
STPBRR           # expect 125000
STCMM 0          # receive only, no CAN ACK
STPO
STMA 200         # 200 frames then auto-exit
```
Traffic means CAN-IHS is reachable cable-free. Silence means the FS wires
MS-CAN elsewhere or auto-switch overrides `STP`; re-run with `STP 53`. Exiting a
monitoring session closes the protocol; always re-issue setup afterwards.

**Q2. Does auto-switch firmware override manual `STP`?**
```
STPRS
STP 54
STPRS            # must differ
STPBRR
```

**Q3. CAN-CH bitrate** (grey A6 fitted)
```
STP 34
STPBRR
STCMM 0
STPO
STMA 100
```
No frames: `STPC` · `STPBR 250000` · `STPO` · `STMA 100`, then `STPBR 125000`.

**Q4. Confirm the confirmed addresses on this car** (no cable, CAN-C), one module at a time:
```
STP 34
STCSEGR 1
STCSEGT 1
STPO
ATSH 18DA10F1
STCFCPA 18DA10F1,18DAF110
22F190           # expect 62 F190 + "ZASFAKPN5J7B88115"
22F191
22F188
```
Repeat for `18DA18F1` (TCM), `18DA40F1` (BCM), `18DA60F1` (IPC), `18DAC7F1`
(RFHUB), `18DA2AF1` (steering). A returned VIN is proof of address. Handle NRC
`0x78` by waiting, not failing.

**Q5. Discover the unknown addresses** (DTCM, ESM, DASM on CAN-C; ABS, ORC, AFLS,
PAM, HALF and EPS confirmation on CAN-CH). Sweep TA `0x00..0xFF`, skipping `0xF1`
(tester), `0x33` (functional), `0xBA` (BACCAble) and, until Q4 clears it, `0xC7`:
```
ATSH 18DA<TA>F1
STCFCPA 18DA<TA>F1,18DAF1<TA>
STPTO 200
22F190
```
Any `62 F190 ...` is a live node. Name it by matching returned part numbers to
Table A (`M0045027.01` is the DTCM, `0203500279` is HALF). The ISO code's byte 2
is not the address (ECM `01` but TA `0x10`; BCM `00`/`0x40`; IPC `03`/`0x60`).
Sweep CAN-C first; sweep CAN-CH only after Q3 and with `STCMM 0` proven.

**Q6. Adjudicate `0x2A` vs `0x76` for steering angle** and the seven stelvio_scan
constants (`0x28`, `0x50`, `0x68`, `0x38`, `0x6D`, `0x29`, `0x6F`). Q5 answers
them all. Until then they are marked unverified in code, not shipped as data.

**Q7. Filter-command spelling on firmware 4.3.2.** Probe both at startup and
cache the winner; every add-filter call allocates RAM and can return `OUT OF
MEMORY`, which then breaks ordinary requests too:
```
STFAC
STFPA 7E8,7FF     # rev F spelling
STFAP 7E8,7FF     # legacy spelling
```

**Q8. Verify the ECM/TCM DIDs on a petrol 2.0T.** With `ATSH 18DA10F1`: `221000`
at idle against MES's own RPM; `22195A` idle vs snap-throttle; `22130A`;
`221955` against a DVOM. With `ATSH 18DA18F1`: `2204FE` after a drive; `221018`
at steady cruise. NRC `0x31` means a diesel-only artefact; record the negative.

**Q9. Is `0x0F1.MAYBE_VOLTAGE` (opendbc `fca_giorgio.dbc`) real?** Validate once
against a DVOM; then it is a ~100 Hz battery-voltage trace for the ground-strap
question. Requires raw-CAN monitoring (`STP 32` + `STM`), not UDS.

**Q10. Scan the blue A5 bus at all.** One MES full scan with the A5 fitted
populates the third of Table A that is pure database inference.

**Q11. Flag, do not test blind:** whether the vLinker FS can be commanded into
FEPS 18 V over serial. Until answered from vendor documentation, treat OBD pin
13 as a live hazard and never send undocumented ST/AT commands while plugged in
without the grey cable.

## Files to edit once answers land

- `stelvio_scan/src/stelvio_scan/uds/addresses.py`: seven unverified constants; SAS `0x76` vs danardi `0x2A`; no DTCM, ESM, DASM, AFLS, PAM, HALF; ECM/TCM declared 11-bit only.
- `stelvio_scan/src/stelvio_scan/data/did_catalog.yaml`: Table C belongs in the Stelvio/Giulia placeholder slot with `source` and confidence.
- `mes-log-mcp/mes/modules.py`: SCRM and GPCM mis-flagged; EPB, AAML, AAMR flagged `yes` without evidence; add `bus` and `cable` fields.
- `docs/research/review-2026-09-14/web_research.md` section 3.2: CAN-IHS module list places BCM and IPC on the blue-cable bus; seven on-car scans say otherwise.
