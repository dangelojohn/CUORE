# MES logs from the September backup: the 2025-10 turbo-replacement era

Source folder: `C:\Users\User\Documents\Stelvio_MES_Backup_2026-09-13` (104 files; 97 are MES session logs).
Vehicle: Stelvio 2.0T, VIN ZASFAKPN5J7B88115. Turbo replacement 2025-10-14 is **owner-attested** (CASE.md); the logs below are consistent with it but do not prove it.
All facts below come from the log files named. The folder was parsed as data only, with `mes.fes` / `mes.scan` / `mes.catalog`.

## Result of the import

**Nothing new was imported.** Every genuine Stelvio log in the backup (25) is already in `data/captures/stelvio-2018/mes_logs/` and in the live MES install folder, byte-identical (SHA-256 equal). The backup's SHA256SUMS verify clean (0 mismatches).

| Backup content | Count | Disposition |
|---|---|---|
| MES logs in `logs/` (85 FESLog + 12 SCAN) | 97 | inventoried |
| Genuine Stelvio, our VIN, no simulation marker | 25 (16 FES + 8 SCAN with the VIN, plus FESLog_2606070950 with no VIN field) | already in repo corpus |
| Stelvio 2.0 FES with the "SIMULATION MODE" banner | 32 | skipped, not evidence |
| Fiat 500L / Alfa 166 / 4C / Tonale / Stelvio 2.9 V6 FES | 35 + 1 | skipped (other models; 13 of the 500L logs lack the banner but are a different car, VIN ZFBCFABH1EZ020882 where logged) |
| SCAN logs with another VIN (Fiat 500L ZFBCFABH1EZ020882) | 3 | skipped |
| SCAN_2608271112.txt | 1 | "Connection failed!" x5, no data and no VIN; not attributable; in the live folder, not in the repo; not imported |
| Not logs: README.txt, SHA256SUMS.txt, BEFORE_SNAPSHOT_2026-09-13.txt, FES_Tags.ini, FES_Templates.ini, multiecuscan_registry_settings.reg, Report1.pdf | 7 | described below, not imported |

Why the October 2025 set adds nothing: after the two genuine logs of 2025-10-14, every Stelvio 2.0 FES log from 2025-10-15 to 2025-10-27 (FESLog_2510150207 through FESLog_2510271230, 30 files) carries `SIMULATION MODE!!! THE DATA IS NOT REAL!!!` and the MES practice fingerprints (ISO `7C 86 4F FF FF`, VIN field `5188214`, serial `281011421`). They are MES demo sessions. Two more Stelvio 2.0 simulation files fall outside October (FESLog_2606061201, FESLog_2609021442), which makes the 32 in the table.

The repo had 42 logs and the live folder has 119 (96 FES, 23 SCAN; 60 simulated, 59 real). The corpus count did not change.

## Timeline of the genuine 2025 sessions (turbo era)

These are the only genuine Stelvio logs before 2026-06-07. All three read the **ECM only**; no other module was read in 2025.

| File (filename stamp) | Session time in header | Module | Content | DTCs (status, environment) | Odometer | Voltage |
|---|---|---|---|---|---|---|
| FESLog_2509241345 | 2025-09-24 10:58:07 | ECM IAW 10JA, SW P235QB39, op. time 250617 min, starts 12713 | 5x Evaporation control valve actuator COMPLETED; wastegate solenoid COMPLETED; turbo vacuum valve COMPLETED; electronic thermostat FAILED ("Request out of range error") | P0456-00 evaporation system leak, stored, freeze frame: 16 C engine, 1307 rpm, 0 km/h, fuel 73.73 %, atmos 989 mbar, op. time 250423 min, starts 12700. Also stored: P1189-00 intake pressure sensor, P00F5-00 humidity sensor, P0098-00 air temperature sensor, P105E-00 humidity sensor (freeze frames at 25 C, engine off) | P0456 frame 114008.9 km; other four 114116.9 km; session odometer 114116.9 km | 13.6 V (P0456 frame, running); 12.1 V (P1189, P00F5, P0098); 12.0 V (P105E) |
| FESLog_2510142142 | 2025-10-14 21:39:33 | ECM, op. time 251153 min, starts 12756 | Adjustment "Replacement of turbocharger" COMPLETED | "No fault codes" | not logged | not logged |
| FESLog_2510142149 | 2025-10-14 21:45:45 | ECM, op. time 251158 min, starts 12761 | Adjustment "Overboost counter reset" COMPLETED; actuators wastegate, turbo vacuum valve, Evaporation control valve, EGR solenoid COMPLETED; electronic thermostat FAILED twice ("Request out of range error") | no READING ERROR CODES section in the file | not logged | not logged |

Header facts common to all three: VIN lock status "Locked by odometer", PROXI configuration write counter 1, ECU serial TD4192427B17540. The header time and the filename stamp differ (for example 10:58 vs 13:45 on 2025-09-24); the catalog treats the filename stamp as authoritative.

## What this adds

Nothing new to the corpus, but the first-seen dates for the codes of interest, computed over all genuine logs for this VIN, are stated here against the owner-attested 2025-10-14 turbo job:

| Code | First genuine appearance | File | Relative to the 2025-10-14 turbo job |
|---|---|---|---|
| P0456-00 | 2025-09-24 | FESLog_2509241345 | 20 days **before**; stored, with freeze frame |
| P0455-00 | 2026-08-27 11:19 | FESLog_2608271119 | about 10.5 months after; read then cleared in that session |
| P0440-00 | 2026-08-27 11:19 | FESLog_2608271119 | about 10.5 months after; read then cleared in that session |
| U1711-2F, U1712-2F, U1713-2F (BCM) | 2026-06-07 09:54 | SCAN_2606070954 | about 7.8 months after; first BCM read of any kind |
| U1736 (86 on IPC, 87 on BCM) | 2026-10-14 08:59 | SCAN_2610140859 | one year after |
| C104B-92 (ABS) | 2026-09-04 20:01 | FESLog_2609042001 | after; cleared in that session |
| U1700-87 (ABS) | 2026-09-04 20:01 | FESLog_2609042001 | after; cleared in that session |

Limits on reading that table. The only module read before 2026-06-07 is the ECM, so the network and chassis codes (U17xx, C104B) could not have appeared in a log before the BCM, ABS and others were read; their absence from 2025 logs is not evidence they were absent from the car. The 2025-09-24 log shows P0456 but not P0440 or P0455; the 2025-10-14 21:39 log, taken after the turbo adjustment, shows "No fault codes" for the ECM. No clear is recorded in any 2025 log (no `CLEARING STORED FAULT CODES` event), so the disappearance of P0456 between 2025-09-24 and 2025-10-14 happened outside the logged sessions. These logs do not say why.

- **Clears recorded in the backup's genuine range** (all 2026): SCAN_2606070954 (BCM, DASM), SCAN_2606071003 (RFHUB, DASM), FESLog_2608271119 (P0455, P0440, P0456), SCAN_2608271131 and 2608271136, FESLog_2608311823 (P0440), FESLog_2609021454 (P0456, P0440), SCAN_2609041953 (ECM, DTCM, BCM succeeded; DASM FAILED), FESLog_2609042001 (C104B, U1700), FESLog_2609042009.
- **Battery voltage readings:** only the five freeze frames in FESLog_2509241345 (13.6, 12.1, 12.1, 12.1, 12.0 V). No parameter-sample voltage appears in any 2025 genuine log.
- **ESIM or EVAP tests:** no ESIM reference in any of the three genuine 2025 logs. The EVAP-related entries are the "Evaporation control valve" actuator runs (5 COMPLETED in FESLog_2509241345, 1 COMPLETED in FESLog_2510142149). The logs record only that the actuator command completed; they hold no pressure or leak-decay reading.
- **Odometer:** 114,116.9 km on 2025-09-24, the last odometer value logged in 2025.

## Non-log files in the backup (described, not imported)

- **BEFORE_SNAPSHOT_2026-09-13.txt:** hand-written record made before the planned EU paddle-neutral PROXI change, built from SCAN_2609041953 and SCAN_2609042008. Gives PROXI write counter 1, byte 156 = 0x50 (paddle neutral disabled) with the restore step (set back to 50, run PROXI ALIGNMENT), and a 14-module table with hardware, software and stored codes. The full PROXI hex dump it points to was never captured.
- **README.txt / SHA256SUMS.txt:** backup description and checksums (all verify).
- **mes_config/multiecuscan_registry_settings.reg:** a single value, `HKCU\Software\Multiecuscan` `"installed"=dword:00000001`. **There is no "Interface 0 Port" value (or any COM, interface or speed value) in it.** The backup README says the same: MES does not keep its interface settings in the registry. CUORE's COM1 fallback therefore cannot be checked against this file.
- **mes_config/FES_Tags.ini, FES_Templates.ini:** MES UI list files (tag/template index numbers such as `0=1989,1802,1872,1804`); no vehicle or port data.
- **mes_config/Report1.pdf:** one-page image PDF titled "Multiecuscan report", created 2025-11-15 16:38 (-05:00) by PDFsharp, in the time window of the 2025-11-15 simulated 500L/Tonale sessions. Content not rendered.
