# Everything readable on this car (draft) -- Stelvio 2.0T Q4, MY2018, VIN ZASFAKPN5J7B88115

Compiled 2026-09-26. One catalog of every item this project currently knows
how to *read* (never write/actuate) from this car, with an honest confidence
per item. Confidence is never upgraded past its source: `CONFIRMED` means a
primary source demonstrates the item working on a 2.0T Giorgio-platform
petrol car specifically; `INFERRED` means reasoned from a related confirmed
fact; `UNVERIFIED` means a single source with no petrol/2.0T confirmation.
Diesel-only items (DPF, EGR, common-rail injection timing, glow plugs) are
skipped outright for this petrol car rather than encoded as unusable rows.

Code lives in `cuore/live/addressing.py` (`DIDS`, `ANNEX_C`), the new
`cuore/live/did_catalog.py` (`EXTRA_DIDS`, `BROADCAST_SIGNALS`), and
`cuore/live/obd.py` (Mode 01 `PIDS_BY_HEX`). Reading them at runtime is
`cuore/live/readall.py` (`read_all`, `discover_dids`), which also decodes
formulas with a small hand-written parser (no `eval`).

## Sources consulted for this pass

| Source | What it gave | Caveat |
|---|---|---|
| [danardi78/Alfaromeo-Giulia-Stelvio-PIDs](https://github.com/danardi78/Alfaromeo-Giulia-Stelvio-PIDs) (`custompids.csv`) | Almost every UDS DID in this catalog, across `DA10F1` (ECM), `DA18F1` (TCM), `DA40F1` (BCM), `DA60F1` (IPC), `DA2AF1` (EPS), `DAC7F1` (RFHUB/tire) | Author's own words: "Those parameters are tested on my diesel version of Giulia, so maybe that some of that are not applicable and not working on 2.0L and 2.9L [petrol]." Nothing from it is `CONFIRMED` on a 2.0T here. |
| [ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3](https://github.com/ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3) and [Simple_OBD2_for_AlfaRomeoGiulia](https://github.com/ClaudeMarais/Simple_OBD2_for_AlfaRomeoGiulia) | Corroboration only: confirmed on the author's own 2019 Giulia 2.0L petrol, but every formula it uses (RPM, boost, gear, oil/coolant temp, battery voltage) is one already in `addressing.DIDS`, just via the OBD Mode-01 broadcast form rather than UDS. Nothing new to add, but it shows those danardi78 formulas are not diesel-only. | Source code excerpts only gave formulas, not CAN IDs, in this pass. |
| giuliaforums.com custom-PID thread | -- | Fetch returned HTTP 402 (paywalled/anti-scrape) at research time. Not incorporated. Flagged here as an unresolved source rather than silently dropped. |
| AlfaOBD / MultiEcuScan forum material on EVAP diagnostics | The vent-valve/canister actuator is an "ESIM" (Evaporative System Integrity Monitor) UDS **RoutineControl** (`0x31`), not a readable DID, and needs the SGW bypass cable on 2017+ cars | Out of scope for a read-only catalog: `0x31` is on `safety.WRITE_SERVICES` and `assert_read_only_uds` refuses it before a byte leaves the adapter. No plain-read (`0x22`) EVAP DID (tank pressure, purge duty, canister state) was found anywhere for this platform. |
| [commaai/opendbc `fca_giorgio.dbc`](https://github.com/commaai/opendbc) (PR #1251) | Passive broadcast CAN signals (steering, wheel speed, engine RPM, ABS/yaw, EPS torque, cruise, turn stalks), including the `MAYBE_VOLTAGE` signal `GIORGIO_MODULE_MAP.md` Q9 asks about | Community reverse-engineered for openpilot; many signals are still named `NEW_SIGNAL_n`/`UNKNOWN_n` by its own authors. No EVAP or fuel signal in it. Bus (CAN-C vs CAN-CH) is not distinguished by the DBC and is unverified on this car. |
| [gaucho1978/BACCAble](https://github.com/gaucho1978/BACCAble) | Confirms the DID list it ships is danardi78-derived and squats target `0xBA` (`18DABAF1`) | No broadcast-ID catalog of its own. Its `DABAF1`-header rows are **not encoded anywhere in this project**, formula content aside -- `0xBA` is forbidden (`addressing.RESERVED_TARGETS`, `GIORGIO_MODULE_MAP.md`'s hazard note) because of the documented immobiliser hazard. |
| ISO 14229-1 Annex C / SAE J1979 (ISO 15031) | The universal identity DID set and the legislated Mode 01 PID table | Confirmed by standard on any compliant ECU; this project's own scans (`GIORGIO_MODULE_MAP.md` Q4) already show Table A modules answering `F190`. |

## 1. Annex C identity (every module, `CONFIRMED` by standard)

Read via `uds.identity()`. Every module in Table A below should answer these;
a no-answer proves a wrong/unconfirmed address rather than an unsupported DID.

| DID | Meaning |
|---|---|
| `F190` | VIN |
| `F187` | spare part number |
| `F188` | ECU software |
| `F189` | software version |
| `F18C` | serial number |
| `F191`/`F192`/`F193` | hardware number |
| `F194`/`F195` | supplier software |
| `F197` | system name |
| `F18B` | manufacture date |
| `F199` | programming date |
| `F186` | active diagnostic session |
| `F198` | last tester address |

## 2. UDS DIDs by module

Bus/cable columns come from `GIORGIO_MODULE_MAP.md` Table A. "Existing" rows
are `addressing.DIDS`; "new" rows are `did_catalog.EXTRA_DIDS` added by this
pass. All formulas are CarScanner syntax (`A`, `B`, `C`... = response bytes
after the echoed DID).

### ECM -- Magneti Marelli IAW 10JA, header `18DA10F1`, CAN-C, no cable

| DID | Name | Formula | Unit | Confidence | Catalog | Source |
|---|---|---|---|---|---|---|
| `1000` | Engine RPM | `((A*256)+B)/4` | rpm | UNVERIFIED | existing | danardi78 (CONFIRMED on Giulia 2.2D only) |
| `1001` | Fuel tank level | `A*100/255` | % | UNVERIFIED | **new** | danardi78; also gives `A*53/255` in litres (53 L tank); EVAP-monitor precondition |
| `1002` | Vehicle speed | `((A*256)+B)/124` | km/h | UNVERIFIED | existing | danardi78 |
| `1003` | Coolant temperature | `(((A*256)+B)*0.02)-40` | °C | UNVERIFIED | existing | danardi78 |
| `1009` | Time since start | `((A*256)+B)/4` | min | UNVERIFIED | **new** | danardi78; generic, not diesel-specific |
| `1302` | Engine oil temperature | `B` | °C | UNVERIFIED | existing | danardi78 (source tags this row "(benz)" = petrol) |
| `130A` | Engine oil pressure | `A*10/255` | bar | UNVERIFIED | existing | danardi78 ("(benz)") |
| `1923` | Clutch / torque-converter status | `A` | -- | UNVERIFIED | **new** | danardi78; meaning on the ZF 8HP is unclear |
| `1924`/`1925` | Throttle position, sensors 1/2 | `((A*256)+B)/655.35` | % | UNVERIFIED | **new** | danardi78 |
| `1926` | Throttle position, sensor 3 | `((A*256)+B)*100/24576` | % | UNVERIFIED | **new** | danardi78; different scale, unresolved vs sensors 1/2 |
| `192B` | Cruise control target speed | `(((A*256)+B+1)/128)+2` | km/h | UNVERIFIED | **new** | danardi78 |
| `192D` | Current engaged gear | `A` | -- | UNVERIFIED | existing | danardi78 |
| `192F` | A/C refrigerant pressure | `((A*256)+B)/100` | bar | UNVERIFIED | **new** | danardi78 |
| `1935` | Intake air temp (post-turbo) | `(((A*256)+B)*0.02)-40` | °C | UNVERIFIED | existing | danardi78 (source also lists a conflicting single-byte `A-40` form at the same DID -- unresolved) |
| `193A` | Wastegate / overboost valve position | `(((SIGNED(A)*256)+B))/100` | -- | UNVERIFIED | **new** | danardi78; directly relevant to the 2.0T's turbo |
| `193C`/`193D` | Air mass measured / required | `((A*256)+B)/3` | mg/c | UNVERIFIED | **new** | danardi78 |
| `1955` | Battery voltage | `((A*256)+B)*(0.5/1000)` | V | UNVERIFIED | existing | danardi78 |
| `1956` | Ambient / barometric pressure | `(A*256+B)-32768` | mbar | UNVERIFIED | **new** | danardi78 |
| `1959` | Boost pressure required (target) | `((A*256+B)-32768)/1000-1` | bar | UNVERIFIED | **new** | danardi78; source also has a conflicting formula for "boost required" at `1942`, not encoded (see note in `did_catalog.py`) |
| `195A` | Boost pressure (measured) | `((A*256+B)-32768)/1000-1` | bar | UNVERIFIED | existing | danardi78 -- highest-value DID for this engine |
| `195B` | Boost pressure sensor (raw voltage) | `((A*256)+B)/10000` | V | UNVERIFIED | **new** | danardi78 |
| `19BD` | IBS state of charge | `A` | % | UNVERIFIED | existing | danardi78 |
| `1B00` | Start&Stop status | `A` | -- | UNVERIFIED | **new** | danardi78; S&S is fitted to this petrol variant |
| `1B02` | Start&Stop request | `A` | -- | UNVERIFIED | **new** | danardi78 |
| `2001` | Odometer | `((((A*256)+B)*256)+C)/10` | km | UNVERIFIED | **new** | danardi78 |
| `2003` | Number of ECU programming events | `A` | -- | UNVERIFIED | **new** | danardi78; anti-tamper / service-history value |
| `2005` | Maximum RPM recorded | `A` | rpm | UNVERIFIED | **new** | danardi78 |
| `3A41` | Engine oil level | `(A*256+B)/1000` | L | UNVERIFIED | **new** | danardi78 (source tags this row "(benz)" = petrol) |
| `3A58` | Intake manifold temp (pre-intercooler) | `A-40` | °C | UNVERIFIED | **new** | danardi78 |
| `1946`, `1904`, `18E4`, `18DE`, `18A4`, `3807`, plus DPF/EGR/injection-timing/glow-plug rows | -- diesel-only, skipped for this petrol car | -- | -- | n/a | existing (flagged `diesel_only`) / not encoded | danardi78 |

### TCM -- ZF 8HP50/75, header `18DA18F1`, CAN-C, no cable

| DID | Name | Formula | Unit | Confidence | Source |
|---|---|---|---|---|---|
| `1018` | Torque as received from ECM | `((A*256+B)-500)` | Nm | UNVERIFIED | danardi78 |
| `04FE` | Gearbox oil temperature | `A-40` | °C | UNVERIFIED | danardi78 |
| `0518` | DNA mode selector | `A` | -- | UNVERIFIED | danardi78 |
| `0540` | DNA mode selector (alt byte) | `C` | -- | UNVERIFIED | danardi78; unresolved vs `0518` |

No new TCM DIDs found beyond `addressing.DIDS`.

### BCM -- Marelli 949 (gateway), header `18DA40F1`, CAN-C, no cable

| DID | Name | Formula | Confidence | Source |
|---|---|---|---|---|
| `1004` | Battery voltage | `A/10` V | UNVERIFIED | danardi78 |
| `1005` | IBS composite (SoC/temp/voltage/current) | multi-field, see `addressing.py` | UNVERIFIED | danardi78 |
| `0131` | Key ignition position | `A` | UNVERIFIED | -- |
| `0133` | External light switch | `(A*256)+B` | UNVERIFIED | -- |

No new BCM DIDs found.

### IPC -- Continental instrument cluster, header `18DA60F1`, CAN-C, no cable

| DID | Name | Formula | Confidence | Source |
|---|---|---|---|---|
| `0104` | IPC brightness | `A` | UNVERIFIED | -- |

No new IPC DIDs found.

### EPS -- ZF electric steering, header `18DA2AF1`, CAN-CH, grey A6

| DID | Name | Formula | Confidence | Source |
|---|---|---|---|---|
| `083C` | Steering angle | `(SIGNED(A)*256+B)/16` ° | UNVERIFIED (INFERRED address, see `GIORGIO_MODULE_MAP.md`) | danardi78 |

No new EPS DIDs found. Corroborated in kind (not value) by opendbc's broadcast
`EPS_1.STEERING_ANGLE` -- see broadcast table below.

### RFHUB -- Continental RF hub / TPMS, header `18DAC7F1`, CAN-C, no cable

| DID | Name | Formula | Confidence | Source |
|---|---|---|---|---|
| `40B1`-`40B4` | Per-wheel pressure/temp, FL/FR/RL/RR | `pressure=((A*256)+B)/1000; temp=E-50` | UNVERIFIED | danardi78 |

No new RFHUB DIDs found. **Hazard**: `GIORGIO_MODULE_MAP.md` and
`addressing.py` both warn that with a BACCAble board fitted and its
immobiliser function active, reading this header's DIDs engages the
immobiliser and stops the car. No BACCAble board is fitted to this car, so
reading these DIDs is safe here, but the warning stays in the data.

### Modules with no public DID data found

DTCM, ESM, DASM (CAN-C); ABS, ORC, AFLS, PAM, HALF (CAN-CH, grey A6); every
CAN-IHS module (HVAC, ETM, AMP, ESEM, CSWM, CRSM, LBSS, RBSS, PLGM); TVM,
ESL (never answered on this car). None of the sources in this pass gave a
DID for any of these. `readall.discover_dids` is the tool for finding them,
module by module, once each module's target address is confirmed (see
`GIORGIO_MODULE_MAP.md` Q5).

## 3. Legislated Mode 01 PIDs (`obd.py`, `CONFIRMED` by SAE J1979/ISO 15031)

These are standard on any OBD-II-compliant vehicle; this project's own scans
(`GIORGIO_MODULE_MAP.md`) confirm the ECM answers on the legislated route.
Actual per-PID support is whatever the vehicle's own Mode 01 `00`/`20`/`40`
supported-PID bitmap says at runtime (`obd.decode_supported_pids`), not
encoded here.

| PID | Name | Unit | EVAP-relevant? |
|---|---|---|---|
| `05` | engine_coolant_temp | °C | |
| `06`-`09` | fuel trims (short/long, bank 1/2) | % | |
| `0A` | fuel_pressure | kPa | |
| `0B` | intake_map | kPa | |
| `0C` | engine_rpm | rpm | |
| `0D` | vehicle_speed | km/h | |
| `0E` | timing_advance | deg | |
| `0F` | intake_air_temp | °C | |
| `10` | maf | g/s | |
| `11` | throttle_position | % | |
| `14` | o2_b1s1_voltage | V | |
| `1F` | runtime_since_start | s | |
| `21` | distance_with_mil | km | |
| `23` | fuel_rail_pressure | kPa | |
| `2E` | **commanded_evap_purge** | % | yes -- purge duty cycle |
| `2F` | **fuel_level** | % | yes -- EVAP monitor precondition |
| `30` | warmups_since_clear | count | |
| `31` | distance_since_clear | km | |
| `32` | **evap_vapor_pressure** | Pa | yes -- signed, small-leak detection |
| `33` | barometric_pressure | kPa | |
| `42` | control_module_voltage | V | |
| `43` | absolute_load | % | |
| `44` | commanded_afr | ratio | |
| `46` | ambient_air_temp | °C | |
| `51` | fuel_type | code | |
| `52` | ethanol_percent | % | |
| `53` | **evap_vapor_pressure_abs** | kPa | yes -- absolute-sensor variant |
| `5C` | engine_oil_temp | °C | |
| `5E` | engine_fuel_rate | L/h | |

Plus Mode `01` PID `01`/readiness (`obd.decode_readiness`, `obd.evap_verdict`):
decodes the EVAP monitor's supported/complete bits directly -- the
authoritative "has the EVAP monitor even run since the last clear" answer,
independent of any DID.

### The best EVAP-relevant readable item on this car

**No UDS DID for EVAP (purge duty, canister/ESIM state, tank pressure) was
found publicly for the Giorgio platform in this pass.** The best available
readable items are the four legislated Mode 01 PIDs above (`2E`, `2F`, `32`,
`53`) plus the readiness-monitor bit. The vent-valve/canister "ESIM" function
AlfaOBD/MultiEcuScan expose is a **write** (RoutineControl `0x31` actuation,
behind the SGW bypass on 2017+ cars) and is out of scope for a read-only
catalog by construction (`safety.assert_read_only_uds` refuses it).

## 4. Mode $06 (on-board monitoring test results)

Not implemented anywhere in this project yet (`obd.py` has no Mode 06
decoder). Mode 06 would expose raw component-monitor test IDs/values (e.g.
catalyst efficiency, O2 sensor response, and on some platforms an EVAP small-
leak test result) reported by the ECU's own on-board diagnostics, independent
of both the DTC list and the Mode 01 PID table. This is a real gap: on many
platforms Mode 06 is the only place a numeric EVAP leak-test result (as
opposed to a pass/fail DTC) is visible. Flagged here as future work, not
invented as a DID or PID.

## 5. Broadcast CAN signals (passive listen only, `UNVERIFIED`)

From `commaai/opendbc`'s `fca_giorgio.dbc` (`did_catalog.BROADCAST_SIGNALS`).
These are not UDS targets and carry no request/response pair -- reading them
means a passive listen (`STCMM 0`) on whichever bus carries them, which this
car has not yet confirmed for any of these messages. No EVAP or fuel signal
exists in the DBC.

| CAN ID | Message | Signal | Formula | Unit | Note |
|---|---|---|---|---|---|
| `0xDE` | EPS_1 | STEERING_ANGLE | `raw*0.1 - 716.8` | deg | corroborates DID `083C` in kind, not value |
| `0xDE` | EPS_1 | STEERING_RATE | `raw*0.5 - 1000` | deg/s | |
| `0xEE` | ABS_1 | WHEEL_SPEED_FL/FR/RL/RR | `raw*0.017` | m/s | |
| `0xF1` | NEW_MSG_F1 | **MAYBE_VOLTAGE** | `raw*0.02` | -- | this is `GIORGIO_MODULE_MAP.md` Q9's "0x0F1.MAYBE_VOLTAGE"; still needs a DVOM check |
| `0xFC` | ENGINE_1 | ENGINE_RPM | `raw` | rev/min | |
| `0xFC` | ENGINE_1 | ACCEL_PEDAL | `raw*0.4` | percent | |
| `0xFE` | ABS_2 | LONG_ACCEL / LATERAL_ACCEL | `raw*0.01 - 20.48` | m/s² | |
| `0xFE` | ABS_2 | YAW_RATE | `raw*-0.0014 + 2.86` | rad/s | |
| `0x101` | ABS_6 | VEHICLE_SPEED | `raw*0.017` | m/s | |
| `0x106` | EPS_2 | DRIVER_TORQUE | `raw - 1024` | -- | |
| `0x73E` | BCM_1 | LEFT_TURN_STALK / RIGHT_TURN_STALK | boolean | -- | |
| `0x5A2` | ACC_1 | HUD_SPEED | `raw` | km/h | |
| `0x5A2` | ACC_1 | CRUISE_STATUS | `raw` | -- | |

This is a representative subset (the full DBC has ~150 signals, many still
named `NEW_SIGNAL_n`/`UNKNOWN_n` even by opendbc's own authors); see
`did_catalog.BROADCAST_SIGNALS` for exactly what is encoded, and the DBC
itself for the rest.

## 6. Hazards and deliberate exclusions

* **Target `0xBA` (`18DABAF1`)**: never used, anywhere in this project.
  BACCAble squats it; with a BACCAble board fitted and its immobiliser
  function active, using it stops the car. `addressing.RESERVED_TARGETS`
  already excludes it from every sweep.
* **Header `18DAC7F1` (RFHUB/TPMS)**: same immobiliser hazard, conditional
  on a BACCAble board being fitted. None is fitted to this car, so reading
  it (as `addressing.DIDS`/`did_catalog.py` do) is safe, but the warning
  travels with the data.
* **CAN-CH (grey A6)**: brakes, airbag squibs and steering assist. This
  catalog changes nothing about the transport's confirm-before-transmit
  gate; `readall.discover_dids`'s docstring says so explicitly and the code
  does not special-case around it.
* **ESIM / vent-valve actuation**: a write (RoutineControl), not a read;
  excluded from this catalog by construction, not by omission.
* **FEPS (OBD pin 13 on CAN-CH)**: unrelated to DIDs but repeated here per
  the module map's standing hazard note -- never issue undocumented ST/AT
  commands while plugged into CAN-CH without the grey cable confirmed.
