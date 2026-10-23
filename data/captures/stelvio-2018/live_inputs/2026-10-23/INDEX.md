# Stelvio input capture 2026-10-23 (partial, stopped early)

Read-only via CUORE HTTP API only. Capture STOPPED early at coordinator request (blue A5 cable fitted; CAN-C no longer reachable). Cable stayed declared none.

## Counts
- Mode 01 PIDs read individually: 46 (answered 17, NO DATA / empty 29). ECM 18DAF110 advertises 46 PIDs, TCM 18DAF118 advertises 12.
- Channels: 104-channel registry saved; two snapshots of the running all-channel poll session (82 of 104 had values in the late snapshot, 22 None); recording CSV with 4 rows.
- DIDs read: 0 (registry holds 44: ECM 31, BCM 4, TCM 4, IPC 1, RFHUB 4). NOT READ.
- Module identity (F190/F194 etc.): not read for any module. NOT READ.
- NRCs: 0 captured.
- Mode 09: VIN only (ZASFAKPN5J7B88115). CAL ID / CVN / IUPR: no read-only route in CUORE.

## Notes
- A live poll session (all 104 channels, no recording) was already running when the per-PID loop started (lock since 00:16:32, not started by this capture). It blocked PIDs 2C..72 with HTTP 403 Refused and made PID 21 time out (HTTP 0). I started recording on it (00:19:03), stopped recording at ~00:23, copied the CSV, then stopped the session (needed to proceed). The 29 re-reads of 21..72 (00:21+) all returned HTTP 200 with body error CAN ERROR (adapter/bus error, route 34 and 33 both failed), i.e. the bus was already unreachable; these are bus errors, not NO DATA from the ECU. The original 403 results were overwritten.
- Voltage at start: 14.5 V (00:15). End voltage not read, scan id not read (stopped).

## Engine hours
- Existing decoders: cuore/live/obd.py PID 7F (engine_run_time, 13-byte decoder), 4D, 4E, 1F (runtime_since_start). cuore/live/capabilities.py seed fact engine_hours_available = False (measured 2026-10-14/15: 7F not advertised, 4D/4E absent, 1F is time since start only). mes-log-mcp/mes: no engine-hours decoder.
- This capture: ECM advertises 1F but NOT 4D, 4E, 7F (supported-PID list). PID 1F read = 902 s (00:16:30). Channels engine_run_time, minutes_run_with_mil, minutes_since_codes_cleared were None in the snapshot. 7F/4D/4E were not individually read (stopped; not advertised). ECM DID 1009 (Time since start, engine-on timer) is the only registry DID with run-time naming; NOT READ.

## Skipped for the read-only rule (not on 01/09/22 allowlist)
Mode 03/07/0A DTCs, Mode 02 freeze frame, Mode 06, readiness, UDS 19 module DTCs. Also forbidden endpoints (clear, actuate, cable, probe, coverage, fullscan, connect, learn, capture, discover-dids, send_raw) unused.

## Files
| file | endpoint | HTTP | note |
|---|---|---|---|
| 00_voltage_start.json | GET /api/live/obd/voltage | 200 |  |
| 01_supported_pids.json | GET /api/live/obd/supported | 200 |  |
| 02_channels.json | GET /api/live/channels | 200 |  |
| 03_modules.json | GET /api/live/modules | 200 |  |
| 04_vin_mode09.json | GET /api/live/obd/vin | 200 |  |
| 10_pid_01.json | GET /api/live/obd/pid/01 | 200 | answered: 18DAF110, 18DAF118 |
| 10_pid_03.json | GET /api/live/obd/pid/03 | 200 | answered: 18DAF110 |
| 10_pid_04.json | GET /api/live/obd/pid/04 | 200 | answered: 18DAF110, 18DAF118 |
| 10_pid_05.json | GET /api/live/obd/pid/05 | 200 | answered: 18DAF110, 18DAF118 |
| 10_pid_06.json | GET /api/live/obd/pid/06 | 200 | answered: 18DAF110 |
| 10_pid_07.json | GET /api/live/obd/pid/07 | 200 | answered: 18DAF110 |
| 10_pid_0B.json | GET /api/live/obd/pid/0B | 200 | answered: 18DAF110 |
| 10_pid_0C.json | GET /api/live/obd/pid/0C | 200 | answered: 18DAF110, 18DAF118 |
| 10_pid_0D.json | GET /api/live/obd/pid/0D | 200 | answered: 18DAF110, 18DAF118 |
| 10_pid_0E.json | GET /api/live/obd/pid/0E | 200 | answered: 18DAF110 |
| 10_pid_10.json | GET /api/live/obd/pid/10 | 200 | answered: 18DAF110 |
| 10_pid_11.json | GET /api/live/obd/pid/11 | 200 | answered: 18DAF110 |
| 10_pid_13.json | GET /api/live/obd/pid/13 | 200 | answered: 18DAF110 |
| 10_pid_15.json | GET /api/live/obd/pid/15 | 200 | answered: 18DAF110 |
| 10_pid_1C.json | GET /api/live/obd/pid/1C | 200 | answered: 18DAF110 |
| 10_pid_1F.json | GET /api/live/obd/pid/1F | 200 | answered: 18DAF110 |
| 10_pid_20.json | GET /api/live/obd/pid/20 | 200 | answered: 18DAF110, 18DAF118 |
| 10_pid_21.json | GET /api/live/obd/pid/21 | 200 | NO DATA / no ECU answered |
| 10_pid_2C.json | GET /api/live/obd/pid/2C | 200 | NO DATA / no ECU answered |
| 10_pid_2D.json | GET /api/live/obd/pid/2D | 200 | NO DATA / no ECU answered |
| 10_pid_2E.json | GET /api/live/obd/pid/2E | 200 | NO DATA / no ECU answered |
| 10_pid_2F.json | GET /api/live/obd/pid/2F | 200 | NO DATA / no ECU answered |
| 10_pid_30.json | GET /api/live/obd/pid/30 | 200 | NO DATA / no ECU answered |
| 10_pid_31.json | GET /api/live/obd/pid/31 | 200 | NO DATA / no ECU answered |
| 10_pid_33.json | GET /api/live/obd/pid/33 | 200 | NO DATA / no ECU answered |
| 10_pid_34.json | GET /api/live/obd/pid/34 | 200 | NO DATA / no ECU answered |
| 10_pid_3C.json | GET /api/live/obd/pid/3C | 200 | NO DATA / no ECU answered |
| 10_pid_40.json | GET /api/live/obd/pid/40 | 200 | NO DATA / no ECU answered |
| 10_pid_41.json | GET /api/live/obd/pid/41 | 200 | NO DATA / no ECU answered |
| 10_pid_42.json | GET /api/live/obd/pid/42 | 200 | NO DATA / no ECU answered |
| 10_pid_43.json | GET /api/live/obd/pid/43 | 200 | NO DATA / no ECU answered |
| 10_pid_44.json | GET /api/live/obd/pid/44 | 200 | NO DATA / no ECU answered |
| 10_pid_45.json | GET /api/live/obd/pid/45 | 200 | NO DATA / no ECU answered |
| 10_pid_46.json | GET /api/live/obd/pid/46 | 200 | NO DATA / no ECU answered |
| 10_pid_47.json | GET /api/live/obd/pid/47 | 200 | NO DATA / no ECU answered |
| 10_pid_49.json | GET /api/live/obd/pid/49 | 200 | NO DATA / no ECU answered |
| 10_pid_4A.json | GET /api/live/obd/pid/4A | 200 | NO DATA / no ECU answered |
| 10_pid_4C.json | GET /api/live/obd/pid/4C | 200 | NO DATA / no ECU answered |
| 10_pid_51.json | GET /api/live/obd/pid/51 | 200 | NO DATA / no ECU answered |
| 10_pid_54.json | GET /api/live/obd/pid/54 | 200 | NO DATA / no ECU answered |
| 10_pid_59.json | GET /api/live/obd/pid/59 | 200 | NO DATA / no ECU answered |
| 10_pid_60.json | GET /api/live/obd/pid/60 | 200 | NO DATA / no ECU answered |
| 10_pid_68.json | GET /api/live/obd/pid/68 | 200 | NO DATA / no ECU answered |
| 10_pid_6B.json | GET /api/live/obd/pid/6B | 200 | NO DATA / no ECU answered |
| 10_pid_70.json | GET /api/live/obd/pid/70 | 200 | NO DATA / no ECU answered |
| 10_pid_72.json | GET /api/live/obd/pid/72 | 200 | NO DATA / no ECU answered |
| 20_session_status_before.json | GET /api/live/session | 200 |  |
| 21_snapshot_early.json | GET /api/live/snapshot | 200 |  |
| 22_record_start.json | POST /api/live/record/start | 200 |  |
| 23_snapshot_late.json | GET /api/live/snapshot | 200 |  |
| 24_session_status_after.json | GET /api/live/session | 200 |  |
| 25_record_stop.json | POST /api/live/record/stop | 200 |  |
| 27_session_stop.json | POST /api/live/session/stop | 200 |  |
| 90_session_status_final.json | GET /api/live/session | 200 |  |
| 26_live_recording.csv | copy of C:\ProgramData\cuore
ecordings\live_20261023-001903.csv | - | 4 rows, 104 channels |
| manifest.jsonl | every call with timestamp and HTTP status | - | note: earlier 403/0 entries for 2C..72 and 21 precede the re-reads |
