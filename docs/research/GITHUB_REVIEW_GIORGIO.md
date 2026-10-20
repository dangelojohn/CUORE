# GitHub review: Alfa Romeo Giorgio / Maserati / FCA CAN and UDS data for CUORE

Date of review: 2026-10-20. Method: GitHub pages, raw.githubusercontent.com and api.github.com via WebFetch (a small model summarised each page, so quotes are paraphrase-grade, not byte-verified), plus 3 standard web searches. Only what was opened is recorded. Anything marked UNVERIFIED was not seen directly.

Naming map used below (inferred from pin numbers, see the BACCAble and giulia_ESCape sections):

| CUORE name | OBD pins | Speed | BACCAble name |
|---|---|---|---|
| CAN-C | 6/14 | 500k | C1 |
| CAN-CH | 12/13 | 500k | C2 |
| CAN-IHS | 3/11 | 125k | BH |

## 1. Summary table

| # | Project | URL | Licence | Last push | Useful to CUORE |
|---|---|---|---|---|---|
| 1 | commaai/opendbc, `fca_giorgio.dbc` | https://github.com/commaai/opendbc | MIT (repo) | repo 2026-10-20; DBC added 2024-09-18 (a894cc9, "FCA Giorgio: CAN database (#1250)") | HIGH. Names and signals for 8 of the 9 CAN-CH ids you listed |
| 2 | tr3ma-crew/BACCAble-firmware | https://github.com/tr3ma-crew/BACCAble-firmware | Mixed, see section 3 | 2025-10-05 | HIGH. Ids by bus, UDS addresses and DIDs, CAN-IHS 0x3E8 gear |
| 3 | AriotaG/AlfaRaceX-Framework | https://github.com/AriotaG/AlfaRaceX-Framework | Apache-2.0 | 2026-09-28 | MEDIUM. Small id table, bus speeds, ISO-TP behaviour. UDS database is empty |
| 4 | ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3 | https://github.com/ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3 | CC BY-NC 4.0 | 2026-07-09 | HIGH for ECM DIDs and module addresses (2019 2.0 petrol) |
| 5 | beaups/giulia_ESCape | https://github.com/beaups/giulia_ESCape | none stated | 2022-10-13 | LOW-MEDIUM. 0x384 and 0x1FC on CAN-CH |
| 6 | ILogEverything/Alfa-Romeo-Giulia-SimRacing | https://github.com/ILogEverything/Alfa-Romeo-Giulia-SimRacing | MIT | 2026-08-18 | LOW. Bus speeds only; ids are in zip files not opened |
| 7 | shawnlu96/grancabrio-can | https://github.com/shawnlu96/grancabrio-can | MIT (code), CC BY 4.0 (data) | 2026-10-16 | NONE for Giorgio. Older Maserati architecture |
| 8 | OBDb/Alfa-Romeo-Giulia | https://github.com/OBDb/Alfa-Romeo-Giulia | CC BY-SA 4.0 | 2026-10-14 | NONE. Signal set is empty |
| 9 | ufnalski/lin_bus_giulia_climatronic_panel_g431kb | https://github.com/ufnalski/lin_bus_giulia_climatronic_panel_g431kb | MIT | 2025-08-02 | LOW. LIN, not CAN or UDS |

Searches that returned nothing relevant: GitHub repo search for "stelvio can bus", "fca uds did", "giorgio platform can alfa", "maserati levante/ghibli/grecale". Two AlfaOBD repos advertise cracked software (ranvirsg/..., kaizo234/...); not opened, not recommended.

## 2. commaai/opendbc, fca_giorgio.dbc

- URL: https://github.com/commaai/opendbc/blob/master/opendbc/dbc/fca_giorgio.dbc
- Licence: MIT (repo licence reported by the API).
- Contents: one DBC, 37 messages. Added by jyoung8607 in PR #1250 (merged 2024-09-18), described there as an initial DBC for Stelvio and Giulia, "working and driving". There is no `fca_giorgio` directory under `opendbc/car/`, so no car port, no fingerprints and no firmware-query data exist in the repo. Only the DBC.
- The DBC does not say which bus it was captured on. The ids match your CAN-CH list exactly, so it is probably the bus a comma panda taps (inference, not stated).
- Sender nodes in the DBC are EPS, ABS, ENGINE, RADAR, CAMERA, BCM, plus XXX for unknown. Those are signal-source labels, not UDS addresses.

### Your CAN-CH ids mapped (all 11-bit, big-endian "@0+" Motorola)

| Id | Dec | DBC name | DLC | Signals (start|len, scale, offset, unit) | Notes |
|---|---|---|---|---|---|
| 0x0DE | 222 | EPS_1 | 6 | STEERING_ANGLE 5\|14 (0.1,-716.8) deg; STEERING_RATE 19\|12 (0.5,-1000) deg/s; COUNTER 35\|4; CHECKSUM 47\|8; two UNKNOWN bits | |
| 0x0EE | 238 | ABS_1 | 8 | WHEEL_SPEED_FL 7\|13, FR 10\|13, RL 29\|13, RR 32\|13 (all 0.017 m/s); COUNTER 51\|4; CHECKSUM 63\|8 | |
| 0x0FA | 250 | ABS_3 | 8 | BRAKE_PRESSURE_THRESHOLD 2\|1; BRAKE_PEDAL_SWITCH 3\|1; NEW_SIGNAL_1 9\|2; XCOUNTER 38\|4; XCHECKSUM 63\|8 | |
| 0x0FC | 252 | ENGINE_1 | 8 | ENGINE_RPM 7\|14 (1); ACCEL_PEDAL 20\|8 (0.4, %); REVERSE 26\|1; COUNTER 51\|4; CHECKSUM 63\|8 | BACCAble and AlfaRaceX also decode 0xFC as engine RPM |
| 0x106 | 262 | EPS_2 | 7 | UNKNOWN_TORQUE 7\|12 (1,-2000); DRIVER_TORQUE 23\|11 (1,-1024); LKA_STATUS 38\|2 (0=standby, 1=lka_active); LKA_FAULT 39\|1; COUNTER 43\|4; CHECKSUM 55\|8 | Only VAL_ table in the file |
| 0x10E | 270 | ABS_7 | 7 | LONG_ACCEL_RAW 7\|12 (0.01,-20.48); LATERAL_ACCEL_RAW 11\|12; YAW_RATE_RAW 31\|12 (-0.0014,2.86); COUNTER 43\|4; CHECKSUM 55\|8 | Raw version of ABS_2; sender is XXX |
| 0x116 | 278 | ABS_5 | 8 | WHEEL_IMPULSE_FL/FR/RL/RR 8 bits each; ACTIVE_FL..RR bits 32-35; FORWARD_1/REVERSE_1/FORWARD_2/REVERSE_2 bits 36-39 ("probably per-axle"); COUNTER 51\|4; CHECKSUM 63\|8 | |
| 0x11C | 284 | NEW_MSG_11C | 8 | VEHICLE_SPEED 47\|12 (0.017 m/s, "scale estimated"); 3 unknown signals; COUNTER 51\|4; CHECKSUM 63\|8 | |
| 0x122 | 290 | EPS_3 | 4 | EPS_TORQUE 7\|12 (1,-2048); COUNTER 19\|4; CHECKSUM 31\|8 | |

Also in the DBC (ids converted from the decimal the DBC uses): 0x0FE ABS_2 (LONG_ACCEL, LATERAL_ACCEL, YAW_RATE; comments "scale TBD" / "scale estimated"), 0x101 ABS_6 (MAYBE_ACC_BRAKE, VEHICLE_SPEED 15|11 x0.017, BRAKE_PRESSURE_1/2, CHECKSUM; same id BACCAble uses for speed on C1), 0x107 ABS_4 (BRAKE_PRESSURE 7|8), 0x1F6 LKA_COMMAND (sender CAMERA: LKA_TORQUE 7|11 offset -1024, LKA_ACTIVE, HAPTIC_WARN_1/2), 0x4AE LKA_HUD_1, 0x547 LKA_HUD_2, 0x5A2 ACC_1 (sender RADAR: HUD_SPEED km/h, TARGET_SPEED x0.433 m/s, CRUISE_STATUS 22|2, MAYBE_TJA), 0x73E BCM_1 (RIGHT/LEFT_TURN_STALK bits 16/17).

Unnamed messages (NEW_MSG_xx, meaning not given): 0x0AB, 0x0E4, 0x0F1 (one signal named MAYBE_VOLTAGE 18|10 x0.02), 0x0F9, 0x109, 0x118, 0x11A (comment: "smoothed yaw rate with low speed cutoff, maybe active forward lighting target angle"), 0x120, 0x1F5, 0x1FC, 0x259, 0x2FA, 0x384, 0x410, 0x416 (multiplexed, 3 groups of 7 bytes), 0x749. Camera-sender stubs with no signals: CAM_UNKNOWN_1 0x2FE, CAM_UNKNOWN_2 0x4AA, CAM_UNKNOWN_5 0x5B2.

Extended id: the DBC has exactly one 29-bit message, CAM_UNKNOWN_6, decimal 506855454 = 0x1E36001E, 1 byte, sender CAMERA, no signals. It sits in your 1E36xxxx family, so that family is probably camera-originated (inference: the DBC labels the sender CAMERA but gives no signals or purpose).

### CAN-IHS ids (0x2F0, 0x3DC, 0x3DE, 0x3E0, 0x3E2, 0x3E4, 0x3E6, 0x3E8)
None of them are in this DBC (checked by decimal conversion: 752, 988, 990, 992, 994, 996, 998, 1000 are absent). The DBC is a CAN-CH-type capture only.

### Reuse terms
MIT: data and code may be copied into CUORE, including a commercial or closed product, provided the MIT copyright notice and licence text travel with the copied material. No copyleft. Recommended: cite "commaai/opendbc fca_giorgio.dbc, MIT, a894cc9" in the CUORE data table's provenance column.

### Caveats
Many scales are marked "scale TBD" or "estimated" in the DBC comments (ABS_2 long and lateral accel, yaw, 0x11C speed). Treat names of NEW_MSG_* as unknown, not as meanings.

## 3. tr3ma-crew/BACCAble-firmware

- URL: https://github.com/tr3ma-crew/BACCAble-firmware
- Last push 2025-10-05; 171 commits; STM32F072 firmware (CANable/SLCAN based) with CAN sniffer, LED strip, start/stop disabler, ESC/TC selector, dyno, immobilizer-related functions, dashboard parameter menus.
- Licence: `LICENSE.md` lists three component licences (CANtact sources MIT; STM32 HAL BSD; STM32 USB Library ST Liberty V2). GitHub API reports "other / NOASSERTION". The README disclaimer says "developed exclusively for educational and research purposes". There is no explicit licence for the project's own Alfa-specific code (the `processingMessage*.c`, `functions_*baccable.c` files). Treat the Alfa-specific message tables as all-rights-reserved: use as a lead to verify on your own car, do not copy code or tables verbatim. Raw CAN ids and byte meanings are facts about the car and you can re-capture them yourself.
- Buses: C1 = OBD 6/14, C2 = 12/13, BH = 3/11. The README gives no speeds; the code comment says BH is "slow bus at 125kbps". Mapping to CAN-C / CAN-CH / CAN-IHS follows from the pins.
- No `.dbc` file. Ids are in `processingStandardMessage.c` case labels with comments.
- UDS: README says request ids typically "18DA...." and gives the pairing rule "if the reqID is 18DAAABB the replyID shall be 18DABBAA". Code also warns "recent vehicles requires SGW bypass to use obd devices".

### 11-bit ids by bus (comments from `processingStandardMessage.c`)

CAN-IHS (BH, 125k):
| Id | Meaning |
|---|---|
| 0x090 | Dashboard text display (radio name etc.) |
| 0x25A | Drive style (DNA), byte 0 bits 2-6 |
| 0x2EE | Steering-wheel radio buttons and volume; comment says present only on BH |
| 0x356 | Proxy alignment required flag (SysEOLsts=1) |
| 0x3E8 | Gear engaged = byte 3 bits 3..0; actual gear (GSI) = byte 3 bits 7..4 |
| 0x46C | DNA mode / Drive Style Status byte 7; turn indicators byte 6 bits 2,1 |
| 0x5A0 | Lane button on some Giulias, byte 4 bit 0 |
| 0x5A6 | Side-mirror positions |
| 0x5A8 | Park-mirror request block (no meaning commented) |
| 0x5AC | Chime request / seatbelt chime type |

CAN-C (C1, 500k):
| Id | Meaning |
|---|---|
| 0xFB | Engine torque, byte 2 bits 6..0 + byte 3 bits 7..4 |
| 0xFC | Engine RPM (handler, no comment; AlfaRaceX decodes as RPM, ClaudeMarais as EngineRPM) |
| 0x101 | Vehicle speed km/h (also AlfaRaceX: acc_brake_intervention) |
| 0x192 | Gear-lever release button / P button, byte 0 |
| 0x1EF | Handler present, no comment |
| 0x1F0 | Clutch interlock byte 0 bit 7, clutch up-stop, pedal position |
| 0x1F7 | Transmission temperature: byte 2 bit 0 + byte 3 bits 7..3 |
| 0x226 | Start-Stop state, byte 2 bits 3..2 (code checks value 01 = disabled; code and comment disagree, code trusted) |
| 0x2ED | Shift indicator to dashboard |
| 0x2EF | Current gear, byte 0 bits 7..4 (also ClaudeMarais GearInfo) |
| 0x2FA | Handler present, no comment (also an unnamed 3-byte NEW_MSG_2FA in opendbc) |
| 0x358 | Volume position |
| 0x384 | Drive style frame (also ClaudeMarais DriveMode; giulia_ESCape TC/ESC control; opendbc NEW_MSG_384) |
| 0x412 | Accelerator pressure |
| 0x41A | Battery current: byte 4 + byte 5 bits 7..4 |
| 0x420 | Battery state of charge, byte 0 |
| 0x4B1 | Start&Stop pad, door/bonnet status bits |
| 0x4B2 | Oil pressure (byte 0 bit 0, byte 1 bits 7..1, bar) and oil temperature (byte 2 bits 5..0 ...) |
| 0x545 | Dashboard brightness |
| 0x5A5 | Cruise control on/off byte 0 bit 7 |
| 0x5A8 | Race mode bits |
| 0x5AE | DPF dirty bit byte 4 bit 2; regeneration mode byte 5 bits 4..2 |
| 0x73A | Date, bytes 0-7 |
| 0x73C | ACC status byte 7 bits 6..4 (0 off, 1 on, 2 engaged, 3 brake only, 4 override, 5 cancel) |

CAN-CH (C2, 500k): 0x1FC (rear diff, active damping, aero, CDCM lamp status; also giulia_ESCape "suspension control"), 0x4B4 (empty), 0x5B0 (park assist button byte 1 bit 5). 0x4AF is handled on C1 or C2 (race bits).

### 29-bit / UDS items (`processingExtendedMessage.c`)
| Item | Value | Meaning |
|---|---|---|
| 0x18DAC7F0 / reply 0x18DAF0C7 | | RFHUB. Tester address F0 talking to module C7 (RFHUB) |
| 0x18DAF160 and request 0x18DA60F1 | | IPC (cluster) = address 0x60, tester F1 |
| 0x18DAF128 | | ABS ECU = address 0x28 (dyno mode) |
| 0x18DABAF1 | | "route request" (BACCAble internal, address BA is a private convention; UNVERIFIED as real module) |
| IPC DID 0x55A0 | IOControl (0x2F) option 03, 00 disable / 01 enable | Seatbelt alarm |
| ABS DID 0x3002 | read 0x22, write 0x2E; byte 4 = 00 means disabled | Dyno mode state; session 0x10 03 first |

Module-address inference: IPC = 0x60, ABS = 0x28, RFHUB = 0xC7 (module address in the low byte of 18DAxxF1 for requests from F1). This is seen in code, not in a published table.

### Reuse terms
See licence note above: ambiguous for the project's own code. Do not copy files. Re-verify each id on your own Stelvio with a passive capture before storing it.

## 4. AriotaG/AlfaRaceX-Framework

- URL: https://github.com/AriotaG/AlfaRaceX-Framework
- Licence: Apache-2.0 (full text in LICENSE, plus a NOTICE file not read). Last push 2026-09-28, 88 commits, 1 star. Reference vehicle: Stelvio MY20 2.2 JTDm 210 Q4 (diesel, ZF 8-speed), release candidate 1.0.0-rc5, hardware validation still pending per README.
- It is a BACCAble-like device project (STM32F072, three controllers C1/C2/BH) with an ELM-compatible bridge (default ISO 15765-4 CAN 11/500, padding 0xAA, ISO-TP up to 255-byte payloads, per-ECU bus discovery order C1, C2, BH).
- Bitrates from `database/vehicles/stelvio_my20_22_diesel_q4.json`: C1 500000, C2 500000, BH 125000.
- `database/can/stelvio_my20_initial.json` (the only CAN table) and `src/vehicle/arx_decoder.c`:

| Id | Bus | Signal |
|---|---|---|
| 0x0FC | C1 or C2 | engine_rpm |
| 0x0FB | C1 | engine_torque_nm |
| 0x101 | C1 | vehicle_speed_kmh, acc_brake_intervention |
| 0x226 | C1 | start_stop_vehicle_enabled |
| 0x2ED | C1 | shift_urgency: byte 6 bits 1..0 (0 none, 1-3 level) |
| 0x2EF | C1 | current_gear |
| 0x384 | C1 | drive_style byte 1 mask 0x7C: 0x00 Natural, 0x08 Dynamic, 0x10 AllWeather, 0x30 Race |
| 0x3E8 | BH | current_gear |
| 0x41A | C1 | battery_soc_percent, battery_current_a |
| 0x46C | BH | drive_style byte 7 mask 0x1F: 0x00 Natural, 0x02 Dynamic, 0x04 AllWeather, 0x0C Race; turn indicator byte 6 |
| 0x4B2 | C1 | oil_pressure ((b0&1)<<7 | (b1>>1)&0x7F) x0.1 bar; oil_temperature ((b2&0x3F)<<2 | (b3>>6)&3) degC |
| 0x73C | C1 | acc_state |
| 0x4AF, 0x5A8 | C1/C2 | marked "needs-capture-validation", no signals |

- `database/uds/README.md` states the UDS database is planned and empty: "Definitions are added only after they are validated against the reference vehicle or a trusted technical source." So no DIDs, no addresses, no routine IDs in the repo as of the files opened. Other files (`docs/*.md`, `docs/CAN_CAPTURE_FORMAT.md`, `tools/replay/arx_replay.py`) exist but were not read.
- Reuse (Apache-2.0): code and data may be copied if you keep the licence text, keep the NOTICE content, and mark changed files; patent grant included; no copyleft. Because the id table agrees with BACCAble (2 independent-looking sources, though the project may have drawn on BACCAble), it is a cross-check, not independent proof. The project says it is not validated on hardware yet.

## 5. ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3 (and Simple_OBD2_for_AlfaRomeoGiulia)

- URL: https://github.com/ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3 ; sibling https://github.com/ClaudeMarais/Simple_OBD2_for_AlfaRomeoGiulia (last push 2025-05-12, not opened).
- Licence: CC BY-NC 4.0 (copyright Claude Marais 2025). Last push 2026-07-09. Author states the ids and PIDs work on a 2019 Giulia 2.0 petrol, 500 kbps bus.
- Request format (`OBD2Utils.h`): extended id 0x18DA<module>F1, 8-byte frame, byte0 length, byte1 service, bytes 2-3 PID, rest 0xAA. Module addresses: All = 0x18DB33F1 (functional), ECM = 0x18DA10F1, TCM = 0x18DA18F1, BCM = 0x18DA40F1. Standard 11-bit responses in the 0x7E8-0x7EF range are noted in a comment; extended replies are 0x18DAF1xx.
- Manufacturer-specific service 0x22 PIDs (from `CollectCarData.h`; formulas live in `OBD2Calculations.h`, not opened):

| Name | Module | DID |
|---|---|---|
| Boost pressure | ECM | 0x195A |
| Engine coolant temp | ECM | 0x1003 |
| Engine oil temp | ECM | 0x1302 |
| Exhaust gas temp | ECM | 0x18BA |
| Atmospheric pressure | ECM | 0x1956 |
| Battery voltage | ECM | 0x1004 |
| Ignition key position | BCM | 0x0131 |

- Broadcast ids (`Shared.h`): DriveMode 0x384, GearInfo 0x2EF, EngineRPM 0x0FC, Boost 0x2EF (same id as gear, commented out), DashboardText 0x090.
- Relevance to your freeze-frame DIDs: your list has 1008, 1002, 1004, 19BD, 1B0D. This repo independently confirms 0x1004 = battery voltage and 0x1003 = coolant temperature on the 2.0 petrol ECM. Compare with your own tables before assuming a match on Stelvio.
- Reuse terms: CC BY-NC 4.0. Share and adapt with attribution, but not for commercial use, and it is not compatible with merging into MIT/Apache/GPL code. Safe use: read the DIDs as facts, confirm them on your own car, and record them with a link; do not copy source files or the repo's tables wholesale into a project that might ever be sold.

## 6. beaups/giulia_ESCape

- URL: https://github.com/beaups/giulia_ESCape. Last push 2022-10-13, 28 stars, 4 commits. No licence listed.
- Arduino sketch for a 2018 Giulia Quadrifoglio on CAN-CH (OBD pins 12/13), 500 kbps. README says untested on Stelvio and on cars with the Secure Gateway.
- `ESCaped.ino`: 0x384 "TCESC_CONTROL" (byte 1 DNA mode: 0x31 race, 0x09 dynamic, 0x01 and 0x11 uncertain; byte 3 bit 0x40 = left stalk (LDW) button), 0x1FC "SUSPENSION_CONTROL" received only (defined values 0x50 soft, 0x40 mid, 0x60 firm, unused).
- Mapping: this places 0x384 and 0x1FC on CAN-CH (BACCAble puts 0x384 on C1 and 0x1FC on C2, so 0x384 may appear on both). Both are unnamed in opendbc.
- Reuse: no licence, so all rights reserved by default. Use as a lead only.

## 7. ILogEverything/Alfa-Romeo-Giulia-SimRacing

- URL: https://github.com/ILogEverything/Alfa-Romeo-Giulia-SimRacing. MIT, last push 2026-08-18.
- Cluster driver for sim racing using two MCP2515: CAN1 500 kbps (RPM, speed, fuel), CAN2 125 kbps (indicators, headlights). The id tables are inside zip archives (`Alfa-Romeo-Giulia-SimRacing.zip` etc.) which were not opened, so no ids recorded. Possible later check: unzip and read `Config.h` for the cluster ids.

## 8. shawnlu96/grancabrio-can

- URL: https://github.com/shawnlu96/grancabrio-can. Code MIT; DBC, docs, samples CC BY 4.0. Last push 2026-10-16, 0 stars.
- 2016 GranCabrio (M145 4.7 V8, ZF 6HP26), 11-bit ids at 500k, 33 ids: 0x061 brake, 0x0CB gear, 0x0CC steering angle, 0x146 speed, 0x166 wheel speeds, 0x361 RPM and load, 0x560 trip counter, 0x566 speed 2, 0x581 oil temp, 0x761 coolant.
- None of your ids overlap. Pre-Giorgio architecture, so ids are not transferable. Reuse terms are permissive but nothing here helps.

## 9. Others checked

- OBDb/Alfa-Romeo-Giulia (https://github.com/OBDb/Alfa-Romeo-Giulia): CC BY-SA 4.0, last push 2026-10-14. `signalsets/v3/default.json` contains `{ "commands": [ ] }` (empty). Test cases cover 2017-2024, only the standard functional request DB33 service 01 PIDs (0104 ... 018D) with response data. Share-alike licence would apply to anything copied. No UDS content.
- ufnalski/lin_bus_giulia_climatronic_panel_g431kb: MIT. Climate control panel over LIN, frame ids found by brute force, no ids written in the README, no CAN or UDS. The module is not named as HVAC in the text (only "climatronic panel"); the CUORE HVAC address is not given.
- AlfaOBD and MultiEcuScan GitHub hits: smooker/mesgraph (MES graphs in Perl, no licence, last push 2022), a MultiEcuScan download .github profile, and cracked-software ads. No data.
- Web searches ("openpilot Giulia Stelvio fca_giorgio", "Giulia 18DA addresses list EPS ORC PAM HVAC DID", "Maserati Levante Ghibli can dbc uds"): no source with a published module-address list, no Maserati Giorgio DBC, no openpilot car port for Giorgio (confirmed: `opendbc/car/` has no fca_giorgio directory). Not opened: forks of opendbc (Vaggysag, sunnypilot archive etc.); they were returned as generic mirrors by the search and would need a separate check for unmerged PR #1251 (Alfa Romeo Stelvio draft).

## 10. Directly usable for CUORE

1. CAN-CH ids, name and signal mapping from opendbc: 0x0DE EPS_1 (steering angle, rate), 0x0EE ABS_1 (4 wheel speeds), 0x0FA ABS_3 (brake switch and threshold), 0x0FC ENGINE_1 (RPM, pedal %, reverse), 0x106 EPS_2 (driver torque, LKA status, LKA fault), 0x10E ABS_7 (raw accel and yaw), 0x116 ABS_5 (wheel impulses and direction), 0x11C (vehicle speed + 3 unknowns), 0x122 EPS_3 (EPS torque). Use the MIT licence, keep provenance.
2. Note: 0x0FC is also confirmed as RPM by three other projects (BACCAble, AlfaRaceX, ClaudeMarais).
3. CAN-IHS 0x3E8: current gear, byte 3 bits 3..0 gear engaged, bits 7..4 GSI target (BACCAble code comment, AlfaRaceX decodes as current_gear, byte not stated there). Neighbours seen on BH: 0x090, 0x25A, 0x2EE, 0x356, 0x46C, 0x5A0, 0x5A6, 0x5A8, 0x5AC. Your other IHS ids (0x2F0, 0x3DC-0x3E6) are not named anywhere that was opened.
4. UDS module addresses from code: IPC 0x60 (18DA60F1 request / 18DAF160 reply), ABS 0x28 (18DAF128 reply), RFHUB 0xC7, ECM 0x10, TCM 0x18, BCM 0x40, functional 0x18DB33F1. Reply = swap of source/destination bytes (18DAF1xx).
5. DIDs: ECM 0x195A boost, 0x1003 coolant, 0x1302 oil temp, 0x18BA EGT, 0x1956 barometric, 0x1004 battery volts; BCM 0x0131 key position; IPC 0x55A0 seatbelt alarm (IOControl 0x2F, read-only use should be possible via 0x22 but the repo has the read commented out); ABS 0x3002 dyno mode state. Confirm each on your 2018 2.0T Stelvio before adding to the CUORE data table; every row needs a verified how-to link per your own rule.
6. The 0x4B2 oil pressure and temperature decode formulas, the 0x41A battery current and 0x420 SOC, 0x73C ACC status and 0x5AE DPF/regeneration (diesel-only likely) as candidates to capture on CAN-C to check against your own logs.
7. 1E36xxxx family: opendbc lists 0x1E36001E (CAM_UNKNOWN_6, 1 byte, sender CAMERA). Evidence for sender only, not for meaning; 1E34xxxx is not listed anywhere reviewed.
8. ISO-TP pairing rule: request 18DAAABB then reply 18DABBAA (BACCAble README).

## 11. Not useful, and reasons

- OBDb/Alfa-Romeo-Giulia: signal set empty, only standard OBD-II PIDs; CC BY-SA 4.0 would add share-alike.
- shawnlu96/grancabrio-can: older Maserati architecture, no id overlap with Giorgio ids, so it cannot inform Ghibli, Levante or Grecale.
- ufnalski climatronic repo: LIN bus, no ids published, does not address the HVAC UDS address gap.
- giulia_ESCape and BACCAble ESC/TC, immobilizer, dyno and message-injection features: these are write or override functions on safety systems; the data is useful for reading state only, and the repos' write paths are outside CUORE's diagnose-on-evidence directive.
- AlfaRaceX UDS database: empty by its own README. AlfaRaceX diesel-only (MY20 2.2 JTDm) telemetry pages are not applicable to a 2.0T.
- Cracked AlfaOBD repos: do not open or run; licence and malware risk.
- Still unfound anywhere reviewed: addresses for EPS, ORC, HALF, PAM, AFLS, HVAC, ETM; keep-alive ids 1E34xxxx / 1E36xxxx meanings; ESIM switch-state DID; FCA routine IDs; Mode 06 TID meanings; Maserati Giorgio data; meanings for CAN-IHS 0x2F0, 0x3DC-0x3E6.
