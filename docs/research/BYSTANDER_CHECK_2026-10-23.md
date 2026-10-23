# Bystander check after the 00:50 wrong-rate frames, 2026-10-23

2018 Alfa Romeo Stelvio, VIN ZASFAKPN5J7B88115. CUORE read-only check, scan at 2026-10-23 00:59 local, adapter direct in the OBD port (cable none), engine idling, adapter 14.5 V.

Labels: **[CUORE]** a reading taken by CUORE (file named); **inference** is my reasoning from those readings, not a reading.

## What was done

- [CUORE] `GET /api/live/obd/voltage`: 14.5 V (`00_voltage.json`). No load-step test was running.
- [CUORE] `POST /api/live/verify {"bus":"can_c"}`: verified true by passive listen at 500k (24 frames, 11.8 Hz), responders 18DAF110 and 18DAF118 (`01_verify_can_c.json`).
- [CUORE] `GET /api/live/scan?bus=can_c&vin=...&mask=255&detail=true`, the same call as step B1 of the 00:10 scan: UDS `19 02 FF` on every addressed CAN-C module, raw status byte per code (`02_B1_uds_19_02_all_modules.json`). Read-only; nothing cleared, written or actuated.
- Baseline: `data/captures/stelvio-2018/scans/2026-10-23_SCAN_2610230010/raw/33_B1_uds_19_02_all_modules.json` (00:10).
- Raw files of this check: `data/captures/stelvio-2018/scans/2026-10-23_bystander/`.

## Result by module (19 02 FF, distinct codes)

| Module | Codes 00:10 | Codes 00:59 | NEW | CHANGED status byte | GONE | Status other than 0x40, 00:10 / now |
|---|---|---|---|---|---|---|
| ECM | 117 | 111 | none | none | 6 (all 0x40) | 3 / 3 |
| BCM | 153 | 119 | none | none | 34 (all 0x40) | 4 / 4 |
| TCM | 44 | 44 | none | none | none | 0 / 0 |
| IPC | 2 | 3 | **U0010-88, status 0x0E** | none | none | 2 / 3 |
| RFHUB | 0 | 0 | none | none | none | 0 / 0 |
| DTCM, ESM, DASM (also answered) | 0 | 0 | none | none | none | 0 / 0 |

Status 0x40 = only "test not completed this operation cycle" (not failed, not pending, not confirmed). 0x0E = test failed this cycle, pending and confirmed. 0x4D = test failed, pending, confirmed, not completed this cycle (the EVAP pattern, unchanged).

### NEW

- **IPC U0010-88**, raw `C01088`, status **0x0E** (testFailedThisOperationCycle, pending, confirmed). U0010 is the medium-speed CAN bus code; failure type 88 is bus off. [CUORE] It is not in any earlier CUORE observation (searched observations.jsonl; the only hits are this 00:59 scan). The IPC's two existing codes, U1736-86 and U1736-87, are unchanged at 0x0E.

### CHANGED status bytes

None. EVAP codes: P0440-00, P0455-00 and P0456-00 are still **0x4D**; BCM B101D-15 still 0x4D; BCM U1736-87, B1176-97 and B10AA-4A still 0x08.

### GONE (all were status 0x40 only at 00:10, none failed)

- ECM (6): P0172, P0171, P1044, P104B, P104C, P0531 (all `-00`).
- BCM (34): B1713-12, B1701-11, B1089-11, B1060-14, B1060-12, B104B-11, B1048-14, B1048-12, B1043-86, B1040-86, B101F-11, B101C-96, B101B-96, B101A-96, B1019-96, B1018-15, B1018-11, B1017-15, B1017-11, B1016-15, B1016-11, B1015-15, B1015-11, B1014-15, B1014-11, B1013-15, B1013-11, B1010-64, B100E-13, B100E-11, B100C-15, B100C-11, B100B-92, B100A-92.

The U-codes with -86 or -87 (missing or invalid message) in the BCM and IPC are all present and unchanged in status. No BCM or ECM code of any kind appeared; no U-code other than U0010-88 is new.

## Verdict (inference)

One new code, **IPC U0010-88 (bus off), confirmed and pending (0x0E)**, appeared between 00:10 and 00:59. It is the only new code in any module, and it is the kind of code a node logs after seeing a corrupted or bus-off event on its CAN-C segment, which fits the two `3E 00` frames sent at 125k onto the 500k bus at 00:50:02 and 00:50:08. The readings do not give a time of occurrence, so the same code could also come from the cable being pulled mid-session or from the car's own bus; I therefore call it **likely attributable to the 00:50 frames, not proven**. Treat it as a tool artefact, not a vehicle fault, and do not use it as evidence in the network-condition hypothesis. The 40 codes that disappeared were all "not completed this cycle" rows (0x40) and look like list differences from a different operation-cycle state (inference: engine idling now, owner-stated ignition on / engine off at 00:10; PID 0C at 00:10 read 750 rpm, so that is itself unsettled); nothing failed, and no EVAP status byte moved. Nothing was cleared by this check.
