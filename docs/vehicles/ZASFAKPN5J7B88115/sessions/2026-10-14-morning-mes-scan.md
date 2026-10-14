# Session record: MES morning scan, 2026-10-14 08:59

Vehicle: 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115. Source file:
`SCAN_2610140859.txt` (MultiEcuScan "scan all systems", C:\Program Files
(x86)\MultiEcuScan), parsed with `mes.scan.parse_scan_text` / `mes.scan.load_scan`
(mes-log-mcp's own catalog library, same parser the rest of this repo uses — no
second copy of the logic). Read-only: this note reads the real file; it does
not touch it or the car.

## 1. Every module, every code, as MES printed it

All 8 modules this car answers on CAN-C answered. Software/hardware numbers
compared against the last full scan on file, `SCAN_2610080920.txt` (8 Oct
09:20) — **no module's software or hardware number changed.** No ECM reflash
has occurred; the wiTECH flash check (CASE.md next step 1) is still unconfirmed.

| Module | ISO code | Hardware | Software | Clean? |
|---|---|---|---|---|
| Engine / ECM (Magneti Marelli IAW 10JA) | 00 01 50 40 18 | MM10JAHW232 Ver 00 | P235QB39 Ver 0000 | **no — 2 codes** |
| Dashboard / IPC (Instrument Panel Continental) | 00 03 50 8B 14 | A2C11140400 Ver 01 | AR952 HL Ver 203C | **no — 2 codes** |
| Gearbox / TCM (ZF 8HP50/75) | 00 0B 50 AA 14 | 10344202761 Ver 20 | GK0902OE2HN Ver 0003 | yes |
| Gearbox / DTCM (Magna Q4 transfer case) | 00 43 50 91 14 | M0045027.01 Ver 21 | M0099947 Ver 0501 | **no — 1 code** |
| Gearbox / ESM (ZF electronic gear shift) | 00 16 50 B4 14 | 1000597140 Ver 08 | 1000678050 Ver 0019 | yes |
| Body / BCM (Marelli 949) | 00 00 70 7C 15 | BCM949M_C02 Ver 01 | 04441660441 Ver 1454 | **no — 5 codes** |
| Body / RFHUB (Continental) | 00 41 50 89 15 | 10161500AA Ver 01 | 10307064AB Ver 0940 | **no — 2 codes** |
| Other / DASM (Bosch radar) | 00 39 70 7E 15 | MRR1evo14F Ver 00 | 52081920 Ver 0500 | **no — 1 code** |

Codes, exactly as MES printed them this morning (failure-type byte and status
wording; the generic FTB meaning per SAE J2012-DA/ISO 14229-1, CORROBORATED,
is identical to MES's own wording in every case below):

| Module | Code-FTB | MES text |
|---|---|---|
| ECM | **P0455-00** | Evaporation system leak |
| ECM | **P0440-00** | Evaporation control valve |
| IPC | U1736-86 | Entertainment Telematic Module (ETM) - Signal/message invalid |
| IPC | U1736-87 | Entertainment Telematic Module (ETM) - Missing message |
| DTCM | U0100-87 | No communication with engine control unit (ECU) - Missing message |
| BCM | U1765-86 | Lost communication with RF Hub module - Signal/message invalid |
| BCM | U1736-87 | Entertainment Telematic Module (ETM) - Missing message |
| BCM | U1713-2F | Engine control (NCM) - Signal/message erratic |
| BCM | B1176-97 | Rear left window riser - Component or system operation obstructed or blocked |
| BCM | B10AA-4A | PROXI configuration control - Incorrect component installed |
| RFHUB | U2054-87 | Error in communication with Body Computer Module (BCM) - Missing message |
| RFHUB | B1040-64 | Communication with Body Computer (BCM/NBC) - Signal/message plausibility |
| DASM | C141B-97 | Camera blinded/obstructed/blocked - Component or system operation obstructed or blocked |

(ECM EVAP codes print no separate failure phrase in this file's grammar —
MES gives one component/description string for P-codes here, same as every
other SCAN log for this ECM.)

## 2. MES cleared codes this morning — plainly

**Yes.** The file contains a `CLEARING STORED FAULT CODES...` block (confirmed
by direct search of the raw file) after the two read-back phases, and it
reports:

| Module | Clear result |
|---|---|
| ECM | SUCCESS |
| IPC | SUCCESS |
| DTCM | SUCCESS |
| BCM | SUCCESS |
| RFHUB | SUCCESS |
| DASM | SUCCESS |

Every module that had a code this morning was cleared successfully (TCM and
ESM needed no clear — they were clean before and after). **This is a bare
clear, not a post-repair clear** — nothing in this repo's record shows a part
was replaced or a repair performed between the 2026-09-26 case-file close and
this scan.

**What that does to the picture:** a clear resets the ECM's since-clear
counters (warm-ups, distance) to zero and drops the readiness-monitor
"complete" flags back to not-run. The 2026-10-13 20:03 live read's verdict —
**ACTIVE FAULT — EVAP** — was earned specifically because every monitor,
including EVAP, had completed *since the prior (29 Sep) clear* with fuel in
the 15–85% window, and the code still came back (`reports/2026-10-13-scan-
health-report.md`). This morning's clear throws that proof away. The EVAP
monitor, and every other monitor, must run again — warm-up cycles, fuel in
window — before a clean read means anything. Until then the verdict reverts
from ACTIVE FAULT back to **UNVERIFIED**, exactly the same reset that
followed the 29 Sep clear in CASE.md. Nothing has been disproven; the evidence
trail was just reset. **Do not treat a clean read in the next few drive
cycles as a fix** — it would mean the monitor hasn't run yet, not that the
leak is gone.

## 3. Comparison: 8 Oct 09:20 clear → 13 Oct ~20:03 live read → 14 Oct 08:59 MES scan

Reference points: `SCAN_2610080920.txt` (pre-clear read, then cleared ECM/
RFHUB/DASM — the only 3 modules with codes that day); the 13 Oct live serial
read from the car, 20:00–20:04, stored/pending/permanent buckets plus the UDS
module sweep (`sessions/2026-10-13-live-read.json`, session record §13/13b);
this morning's pre-clear read.

| Code | 8 Oct 09:20 | 13 Oct ~20:03 (from car) | 14 Oct 08:59 (MES) | Verdict |
|---|---|---|---|---|
| P0440 | not present | stored + pending + permanent | stored | **returned** |
| P0455 | stored (cleared) | pending + permanent | stored | **returned** |
| P0456 | stored (cleared) | permanent only (not stored/pending) | **absent** | did not come back as stored this time — still only ever seen as permanent since the 29 Sep clear |
| B1040-64 (RFHUB) | stored (cleared) | status 0x08, failed since last clear | stored | **returned / persisted since the 8 Oct clear** |
| C141B-97 (DASM) | stored (cleared) | DASM did not answer the 13 Oct UDS sweep (no address found) | stored | **returned** (gap in the 13th's data, not a clean module) |
| U1713-2F (BCM) | not present | status 0x0F — **ACTIVE NOW** | stored | **persisted**, confirms the live network fault the 13th found |
| U1765-86 (BCM) | not present | status 0x08, failed since last clear | stored | **persisted** |
| U1736-86 (IPC) | not present | reported on IPC, status 0x0C (pending+confirmed) | stored (IPC) | **persisted** |
| U1736-87 (IPC + BCM) | not present | reported on IPC, status 0x0C | stored on **both** IPC and BCM | **persisted**, now also mirrored on BCM |
| B1176-97 (BCM) | not present | status 0x08, failed since last clear (chronic per CASE.md) | stored | **persisted** |
| B10AA-4A (BCM) | not present | status 0x08, failed since last clear | stored | **persisted** |
| U0100-87 (DTCM) | not present | DTCM did not answer the 13 Oct UDS sweep (no address found) | stored | **new to this record** — first time DTCM's own code is actually captured |
| U2054-87 (RFHUB) | not present | not reported (sweep only named B1040-64 for RFHUB) | stored | **new to this record** — first appearance in any file/read on hand |

Net picture: the chronic EVAP pair (P0440/P0455) and the chronic network/body
family (B1040, C141B, U1713, U1765, U1736, B1176, B10AA) all returned —
nothing was fixed between 26 Sep and today. Two codes (U0100-87 on DTCM,
U2054-87 on RFHUB) are seen here for the first time because the 13 Oct UDS
sweep never reached DTCM or read RFHUB's full code list; they may well be as
old as the rest of the network-cascade family (`fault-tree: network-cascade`,
CASE.md) rather than genuinely new faults — MES's full-systems scan simply
covers ground the 13th's manual module probing didn't.

## 4. Readiness / verdict impact (restated)

- Before this morning: **ACTIVE FAULT — EVAP**, confirmed 2026-10-13 20:04 by
  a complete readiness cycle after the codes returned (`reports/2026-10-13-
  scan-health-report.md`).
- After this morning's clear: verdict reverts to **UNVERIFIED** until the
  EVAP monitor (and the rest) completes again with fuel in the 15–85% window
  and warm-up cycles accumulate. The underlying diagnosis (ESIM signal path
  vs. ECM calibration, TSB 18-030-17 REV. B) is unchanged — this clear
  produced no new evidence either way, it only cost the proof already on file
  and restarts the clock.
- Software/hardware unchanged on every module → no flash happened this
  morning either; Test A and the wiTECH flash comparison (CASE.md next steps)
  remain outstanding and unaffected.
