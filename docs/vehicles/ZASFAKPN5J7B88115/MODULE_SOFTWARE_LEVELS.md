# Module software levels, 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115

**CUORE reading 2026-10-23**, scan SCAN_2610230010, 00:10:55 to 00:11:16 local, CAN-C only, no adapter cable, no clears. Raw files: `data/captures/stelvio-2018/scans/2026-10-23_SCAN_2610230010/raw/34_B2_identity_ECM.json` to `38_B2_identity_RFHUB.json`. All five modules returned F190 = ZASFAKPN5J7B88115 (matches the car).

Fields: F187 hardware part no.; F188 software part no. (this is what wiTECH shows as "Current ECU Part Number"); F189 SW version; F18C serial; F191 hardware version no.; F192 hardware version string; F194 supplier software no.; F195 software version bytes. "not returned" means the module's read ended before that field (see notes).

| Field | ECM | BCM | TCM | IPC | RFHUB |
|---|---|---|---|---|---|
| Read time (2026-10-23) | 00:10:55 | 00:11:01 | 00:11:06 | 00:11:13 | 00:11:16 |
| Result | complete | CAN ERROR after F192 | complete | CAN ERROR after F187 | complete |
| F187 hardware part no. | 50544870 | 50554114 | 46337308 | 50551318 | 50544008 |
| **F188 software part no.** | **52170619** | **52154912** | **52119227** | not returned | **52091977** |
| F189 SW version | requestOutOfRange (18DAF110) | requestOutOfRange (18DAF140) | requestOutOfRange (18DAF118) | not returned | requestOutOfRange (18DAF1C7) |
| F18C serial | TD4192427B17540 | TD3692377101420 | TF0662057729150 | not returned | T04Z22117E01040 |
| F191 hardware version no. | 52055320 | 52058054 | 52097735 | not returned | 52057995 |
| F192 hardware version string | MM10JAHW232 | BCM949M_C02 | 10344202761 | not returned | 10161500AA |
| F194 supplier software no. | P235QB39 | not returned | GK0902OE2HN | not returned | 10307064AB |
| F195 software version bytes | 00 00 | not returned | 00 03 | not returned | 09 40 |
| F190 VIN | ZASFAKPN5J7B88115 | ZASFAKPN5J7B88115 | ZASFAKPN5J7B88115 | ZASFAKPN5J7B88115 | ZASFAKPN5J7B88115 |

Notes on the table:
- The IPC answered F187 (50551318) and F190 only, then the read ended in CAN ERROR. Its software number is therefore unknown from this scan.
- The BCM answered F190, F187, F188, F189, F18C, F191, F192, then the read ended in CAN ERROR; F194 and F195 are not returned, not zero.
- F189 is requestOutOfRange (not supported) in every module that was asked. The software version bytes are in F195 where the module returned it.
- Earlier records for the BCM quote a different identifier, "BCM Marelli 949, SW 04441660441 ver 1454" (`docs/research/CEL_2026-10-19_DIAGNOSIS.md` header). That is a different numbering from the F188 value read here (52154912); the two are not shown to be the same release. wiTECH's Current ECU Part Number is the arbiter.
- Not read: ABS (needs the grey adapter / CAN-CH), DASM, DTCM, ESM, radio/head unit. No camera, ParkView or PAM module answered on CAN-C.

## MES readings 2026-10-23 (SCAN_2610230112 and FESLog_2610230114 to 0127, 01:12 to 01:27), source MES

**MES reading 2026-10-23.** Cable not recorded in the logs. Full text and errors: `docs/vehicles/ZASFAKPN5J7B88115/radio/MES_MODULE_READS_2026-10-23.md`. MES prints hardware and software numbers in its own numbering; they are shown as MES prints them. Where a CUORE F-field has the same value it is named.

| Module | MES hardware number - ver | MES software number - ver | Other fields (MES) | Source |
|---|---|---|---|---|
| IPC | A2C11140400 - 01 | **AR952 HL - 203C** | FIAT drawing 50551318 (= CUORE F187); ISO 00 03 50 8B 14; no serial printed | MES FESLog_2610230116 |
| ECM | MM10JAHW232 - 00 | P235QB39 - 0000 | serial TD4192427B17540; spare part 50544870; FIAT drawing 52055320; homologation FIBA00 | MES FESLog_2610230118 |
| BCM | BCM949M_C02 - 01 | 04441660441 - 1454 | serial TD3692377101420; FIAT drawing 50554114 | MES FESLog_2610230127 |
| TCM | 10344202761 - 20 | GK0902OE2HN - 0003 | ISO 00 0B 50 AA 14 | MES SCAN_2610230112 |
| RFHUB | 10161500AA - 01 | 10307064AB - 0940 | ISO 00 41 50 89 15 | MES SCAN_2610230112 |
| DTCM (Magna Q4 transfer case) | M0045027.01 - 21 | M0099947 - 0501 | ISO 00 43 50 91 14 | MES SCAN_2610230112 |
| ESM/GSM/NSC (ZF gear shift module) | 1000597140 - 08 | 1000678050 - 0019 | ISO 00 16 50 B4 14 | MES SCAN_2610230112 |
| DASM (Bosch radar) | MRR1evo14F - 00 | 52081920 - 0500 | ISO 00 39 70 7E 15 | MES SCAN_2610230112 |
| Radio / nav (ETM) | not read | not read | no radio log exists; the radio appears only as the fault "Entertainment Telematic Module (ETM)" in IPC and BCM | none |

The IPC software number AR952 HL / 203C is the first one known for this car; CUORE's IPC read ended in CAN ERROR after F187. The "Not read" line above is updated by this table for DASM, DTCM and ESM (read by MES, not by CUORE); ABS and the radio remain unread.

## ECM continuity

ECM F188 52170619 / F194 P235QB39 / F195 00 00 has been identical in every CUORE and MES read this year: `docs/research/CEL_2026-10-19_DIAGNOSIS.md` header ("unchanged in every 2026 read") and its evidence list (identical at 2026-09-25T20:11:51, 2026-10-14T19:02:07, 2026-10-19T00:23:42 and 2026-10-19T00:30:25; F187/F188 identical in the partial read 2026-10-13T20:25:15), and `docs/vehicles/ZASFAKPN5J7B88115/CASE.md` ("Vehicle and ECU": ECU software 52170619, supplier P235QB39 ver 0000). The 2026-10-23 read is a further identical read. It shows the ECM has not been reflashed this year; it does not show whether 52170619 is the newest calibration.

## How the dealer uses this

In wiTECH, open Topology, select the module, open the Flash tab, and compare "Current ECU Part Number" with "New ECU Part Number". Flash only if the two differ, and print both the before and the after screens. The Current number should equal the F188 value in the table above; if it does not, the car or the table is wrong and that must be settled before any flash. The ECM number 52170619 is the one that decides whether a newer EVAP-related calibration exists: TSB 18-026-20 (2018 Stelvio 2.0L ECM flash, lists P1CEA/P24D6 but not P0440/P0455/P0456, and says the BCM must also be on latest software) covers the ECM and BCM, and TSB 21-035-20 (2018 Stelvio 2.0L TCM flash, 8HP shift quality, pair with 18-026-20) covers the TCM. Catalogue rows: `cuore/data/tsb_catalogue.json`, id `tsb-18-026-20` (number 18-026-20, line 216, id line 263) and id `tsb-21-035-20` (number 21-035-20, line 357, id line 386). Neither bulletin is VIN-confirmed for this car; the Flash tab and the dealer's Service Library settle that. The dealer sheet that carries these numbers is `dealer/2026-10-28_dealer_visit_DRAFT.md` (B1 and E2).
