# opendbc fca_giorgio.dbc validation against this car (2026-10-26)

Verdict up front: NO frame DATA has ever been saved from this car. The DBC scales are completely UNVERIFIED.
Only frame-ID presence (and counts) exists. Nothing could be decoded, so nothing can be called PLAUSIBLE.

## Captures found
- C:\ProgramData\cuore\recordings\ holds 5 files, all live DID recordings (live_*.csv, load-step-voltage). Zero buscapture_*.csv.
  (buscapture_<bus>_<cable>_<ts>.csv is what buscapture.capture_save writes; none exist. The only ones on disk are
  synthetic test fixtures under %TEMP%\cuore-check-buscapture-*, e.g. a 3-row can_ihs blue_a5 file - not from the car.)
- audit.jsonl: exactly one purpose=bus_capture session (2026-10-14 19:09:20, can_ihs, cable none), opened and closed
  in 0.12 s. No capture, no save. observations.jsonl has 0 "bus_capture" records.
- No CAN-CH 11-bit data capture exists. CAN-CH (grey A6) was only touched by verify_bus on 2026-10-14/15:
  29-bit STP 34 route only, 20-22 frames, ids 1E340000 / 1E36xxxx (NM keep-alive style). None are Giorgio ids.
- What does exist (observations.jsonl "adapter_identity", ids+counts only, no bytes), STP 33 11-bit passive listen,
  bus can_c, cable none, ~2 s each: 2026-10-19 00:23 (207 frames), 00:29:12 (206), 00:29:33 (207), 2026-10-24 13:22 (207).
  Latest (line 286, 50 distinct ids): the Giorgio ids ARE on the air, which supports the id mapping but says nothing about scales.
  Note chassis_decode.INTEREST comment says "seen on CAN-CH (2026-10-14)"; the records show them on can_c on 10-19/10-24
  (and buses.py claims the 11-bit CH finding of 10-14/15). Bus attribution of the DBC ids is therefore itself unclear.
- Cross-reference states available: live_snapshots.jsonl (10-13 20:38 parked idle: ecm_1000 rpm 755, ecm_1002 speed 0 km/h;
  20:09 driving: 1178 rpm, 16.8 km/h) and sensor_checks.jsonl (10-25 19:56 idle, TPMS 1.98-2.20 bar). Useful as the
  reference side of a future comparison; no bus bytes were recorded at those times.

## Message presence (latest 11-bit listen, 2026-10-24 13:22; DBC has 37 messages, 50 ids heard)
Heard AND defined in DBC (13): 0DE EPS_1(9) 0EE ABS_1(9) 0FA ABS_3(9) 0FC ENGINE_1(8) 0FE ABS_2(8) 101 ABS_6(8)
 107 ABS_4(8) 116 ABS_5(8) 11C NEW_MSG_11C(8) 1F5(4) 259(1) 2FA(4) 384(1).  (counts in ~2 s)
Defined but NOT heard in any listen: 0F1 (MAYBE_VOLTAGE), 106 EPS_2, 10E ABS_7, 122 EPS_3, 1F6 LKA_COMMAND, 73E BCM_1, etc.
 (INTEREST lists 106/10E/122 but they were not in the latest id sets; only cut-down list inspected, 10-19 sets show the same core ids.)
Heard but not in DBC: ~37 ids (0F0 0F4 0FB 0FF 100 103 104 192 1EF-1FB 2EC-2EF 256 257 412-426 5A8 5AE 736 ...) - DBC is incomplete for this car.
Rates: ~4 frames/2 s for 0x1F5/2FA means ~2 Hz; core ids ~4-4.5 Hz in the 2 s window (suspiciously low versus the usual
 50-100 Hz for EPS/ABS/ENGINE on a Giorgio car; the 207 frames/2 s total fits a short listen, not a full-rate bus). Treat as unexplained.

## Per-signal table (all verdicts limited by missing data)
| id | signal | factor/offset | decoded range | expected (parked idle) | verdict |
|---|---|---|---|---|---|
| 0DE | STEERING_ANGLE | 0.1 / -716.8 deg (14b) | none | ~0 deg (+/- few) | NO DATA (id heard) |
| 0DE | STEERING_RATE | 0.5 / -1000 | none | ~0 | NO DATA |
| 0EE | WHEEL_SPEED_FL/FR/RL/RR | 0.017 m/s (13b) | none | all equal, 0 | NO DATA (id heard) |
| 0FC | ENGINE_RPM | 1 (14b) | none | ~755-780 | NO DATA (id heard); DBC range label [0\|255] is wrong for 14 bits, so upstream scale care is doubtful |
| 0FC | ACCEL_PEDAL | 0.4 % (8b) | none | pedal rest; ECM reads 19.6-20% (accelerator_pedal_d/e) | NO DATA. Cross-check target: DID 20% idle looks like pedal-sensor raw, not 0 |
| 101 | VEHICLE_SPEED (ABS_6) | 0.017 (11b, unit blank) | none | 0 | NO DATA; unit unlabeled in DBC |
| 11C | VEHICLE_SPEED | 0.017 m/s (12b) | none | 0 | NO DATA; two different speed signals, same factor, different width |
| 0FE | LONG/LATERAL_ACCEL | 0.01 / -20.48 | none | ~0 lat, ~0 long (+-0.3) | NO DATA |
| 0FE | YAW_RATE | -0.0014 / 2.86 rad/s | none | ~0 | NO DATA; 12-bit raw 2043 -> 0 so check centre |
| 0FA | BRAKE_PEDAL_SWITCH | bit | none | 0 unless pressed | NO DATA |
| 107 | BRAKE_PRESSURE (ABS_4) | 1 | none | low | NO DATA, unit unknown |
| 0F1 | MAYBE_VOLTAGE | 0.02 (10b) | none | ~12-14 V; 10b x0.02 max 20.5 V ok | NO DATA and id never heard; upstream flags as MAYBE |
| 116 | WHEEL_IMPULSE_* / ACTIVE_* | 1 | none | counters static when parked | NO DATA |
| 106 | EPS_2 DRIVER_TORQUE | 1 / -1024 | none | ~0 | NO DATA; id not heard |
Counts: PLAUSIBLE 0 / SUSPECT 0 (decode-based) / NO DATA = every signal (about 14 groups above, 40+ individual signals).

Structure suspects (from reading the DBC, not from data): ENGINE_RPM [0|255] range vs 14-bit field; unit-less
VEHICLE_SPEED in ABS_6; two VEHICLE_SPEED definitions; the whole file is from a different Giorgio car (Giulia) via
openpilot PR #1251; upstream marks many signals NEW_SIGNAL_/UNKNOWN_/MAYBE_. This is the same class of risk as the two wrong ECM DID formulas.

## Recommendations
1. Trust nothing from the DBC as a value. CUORE should keep did_catalog BROADCAST_SIGNALS at confidence "unverified" and
   show a visible "unverified scale" tag on any page using chassis_passive (liveboard_bridge.chassis_passive / chassis_decode).
   Presence of ids (which module is talking, message rate) is reasonable to show, tagged "id match only".
2. Never use decoded broadcast RPM/speed/steering as a diagnostic proof input (core directive: readings only, verified).
   Use UDS DIDs (ecm_1000 rpm, ecm_1002 speed) which are already cross-checked against known states.
3. Do not display MAYBE_VOLTAGE as battery volts.
4. Fix attribution: record which bus (can_c vs can_ch, cable, STPBR rate) each 11-bit listen was taken on; INTEREST comment currently disagrees with the records.
5. Make capture_save the path: buscapture saves FRAME DATA in the recording; the 10-19/24 listens kept only id counts.
   Persist the raw frames (id, hex data, timestamp) for each chassis_passive call so decoding can be checked offline.
## Next capture (needs the car, passive only, via CUORE session)
 Three 10-15 s passive captures on the bus where 0DE/0EE/0FC were heard, saved as bus captures with frame bytes, each
 paired with a live DID snapshot (ecm_1000 rpm, ecm_1002 speed) taken at the same moment:
 A. Parked, engine idle, steering centred, brake released (expect wheel speeds 0, speed 0, rpm ~780, steer ~0).
 B. Parked, engine idle, steering held full lock left then right, then brake pressed (steer angle sign/range, brake bit).
 C. Rolling straight at ~10-20 km/h, steady, with a live speed DID at the same time (wheel speeds/vehicle speed scale, factor 0.017 m/s = 0.061 km/h per count).
 Compare to DID values; only then promote any signal from "unverified" to "verified" per signal, per scale, in did_catalog.
