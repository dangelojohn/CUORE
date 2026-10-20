# Glossary

Terms as used in this project. Where a meaning is an inference or is not established in the project sources, it says so.

## Vehicle and systems

- **Reference car**: the 2018 Alfa Romeo Stelvio 2.0 Turbo (Giorgio platform) used for development and the first worked diagnosis.
- **Giorgio**: the Alfa Romeo platform under Stelvio and Giulia. Periodic bus traffic is 11-bit; diagnostic addressing is 29-bit by default on the powertrain bus.
- **IAW 10JA**: the engine control unit family fitted to the 2.0 Turbo (hardware and software numbers are read from the ECM identity DIDs).
- **ECM / BCM / TCM / ABS / EPS / ORC / IPC**: engine, body, transmission, anti-lock brake, electric power steering, occupant restraint (airbag) control modules and instrument panel cluster.
- **RFHUB, DASM**: remote-function hub and driver-assistance systems module, as named in the module map. The private-CAN module paired with DASM appears in logs as HALF.
- **ZF 8HP / Q4**: the eight-speed automatic and the Q4 all-wheel-drive transfer case.
- **IBS**: Intelligent Battery Sensor; reports battery state of charge and voltage (read by DID from the BCM and ECM).
- **ESIM**: Evaporative System Integrity Monitor; the leak-detection unit in the EVAP vent path. Per outside literature (labelled): gravity-dependent, mounted vertically, no solenoid (weighted valves and a diaphragm switch that closes at about 1 inH2O of vacuum); the ECM supplies 5 V and ground and the closing switch pulls the signal toward 0 V.
- **NVLD**: Natural Vacuum Leak Detection; a leak test that uses the vacuum created as the sealed tank and canister cool after engine-off. The ESIM is the unit that senses it. The freeze frames of the EVAP codes on the reference car fit the cold-start, natural-vacuum test window.
- **EVAP**: evaporative emission control system (fuel tank vapour, canister, purge valve, vent path). Typical DTCs: P0440, P0455 (large leak), P0456 (small leak).
- **Purge valve**: engine-side valve metering canister vapour to the intake.
- **KOEO / KOER**: key on engine off; key on engine running. MES actuator tests need KOEO.
- **MIL**: malfunction indicator lamp (check-engine light). The ECM can store and confirm a fault without requesting the MIL; the MIL is not a reliable indicator on its own.

## Networks and gateway

- **SGW / Security Gateway**: gateway in 2018-and-later FCA vehicles that sits between the OBD port and the vehicle networks; legislated emissions diagnostics pass, other diagnostic access and writes are restricted. Wiring bypass cables (blue A5, grey A6) give access to the networks behind it.
- **CAN-C**: powertrain and diagnostic bus reachable at the standard OBD plug, 500k.
- **CAN-IHS**: interior high-speed (body) bus, 125k; reached with the blue A5 cable.
- **CAN-CH**: chassis bus (brakes, steering, airbag), 500k; reached with the grey A6 cable. Opening it at any wrong rate disturbs the cluster (RULES.md rule 4).
- **11-bit / 29-bit**: CAN identifier lengths. Legislated OBD uses 11-bit (functional 7DF) or 29-bit (functional 18DB33F1); UDS physical requests to a module use 18DAxxF1 (29-bit) or 7xx ids (11-bit).
- **ISO-TP**: transport protocol for multi-frame diagnostic messages over CAN.
- **Keep-alive frames**: periodic frames (1Exxxxxx ids on the 29-bit route of the bypass buses) that do not prove the car is awake.

## Adapter commands (ELM327 and STN family)

- **ELM327 / STN**: serial OBD interpreters. STN chips (here an STN1170) extend the ELM327 command set with ST commands.
- **AT commands** (examples): `ATZ` reset, `ATWS` warm start, `ATCAF0/1` CAN auto-formatting off/on, `ATSH` set header, `ATCRA` receive-address filter, `ATST` reply timeout (units of about 4 ms), `ATAT` adaptive timing, `ATFCSM` flow-control mode.
- **ST commands** (examples): `STP n` select protocol (`STP 33` is the 11-bit route used here), `STPBR` set protocol baud rate, `STMA` monitor all frames, `STM` monitor with filters, `STFAP` add a pass filter, `STCMM` CAN monitoring mode (1 for request sessions, 0 for listen).
- **STMA with ATCAF0**: the passive listen that works on Giorgio buses (STM with ATCAF1 heard nothing).

## UDS services (ISO 14229) and OBD modes

- **UDS 19 (ReadDTCInformation)**: sub-function 01 count, 02 codes by status mask, 03 snapshots, 04 snapshot record, 06 extended data.
- **UDS 22 (ReadDataByIdentifier)**: read a DID; for example F190 VIN, F187 spare part number, F191 hardware number, F192 supplier hardware number, F194 supplier software number.
- **UDS 3E (TesterPresent)**: keep a session alive; also used as a single-shot "is anyone there" probe.
- **UDS 31 (RoutineControl)**: start, stop or read a routine result (for example a leak-verification routine). CUORE does not send routines it has no published definition for.
- **UDS 14 (ClearDiagnosticInformation)**: used only by the consent-gated per-module clear.
- **NRC**: negative response code. 0x11 service not supported, 0x22 conditions not correct, 0x33 security access denied.
- **DID**: data identifier. Learned DIDs are those discovered or captured from MES.
- **OBD modes**: 01 current data, 02 freeze frame, 03 stored DTCs, 04 clear, 06 on-board monitor test results, 07 pending DTCs, 09 vehicle information, 0A permanent DTCs. PID is a Mode 01 parameter id.

## DTC status byte (ISO 14229)

Bits: 0x01 testFailed, 0x02 testFailedThisOperationCycle, 0x04 pendingDTC, 0x08 confirmedDTC, 0x10 testNotCompletedSinceLastClear, 0x20 testFailedSinceLastClear, 0x40 testNotCompletedThisOperationCycle, 0x80 warningIndicatorRequested.

- **0x4D**: testFailed, pending and confirmed (0x40 also set). The EVAP codes on the reference car read 0x4D.
- **0xCD**: as 0x4D with the MIL requested.
- **0x40**: not run this cycle.
- **Mask 0xCF**: the status mask this ECM implements; bits 4 and 5 are not implemented, so no code reports "failed since last clear".

## Mode 06

- **Mode 06**: on-board monitoring test results.
- **OBDMID**: on-board diagnostic monitor id (which monitor, for example an EVAP leak test).
- **TID**: test id within a monitor.
- **UASID**: unit and scaling id that says how to read the value, minimum and maximum.
- Each result is value, minimum and maximum; pass or fail is the comparison.

## Tools and logs

- **MES / MultiEcuScan**: third-party multi-vehicle diagnostic program; no API, so the project reads its files. It holds the serial port while connected.
- **FES log** (`FESLog_YYMMDDHHMM_*.txt`): MES full engineering scan (live parameters, ECU info, freeze frames).
- **SCAN log** (`SCAN_YYMMDDHHMM.txt`): MES quick all-systems scan with per-module DTCs.
- **Simulation log**: MES practice session marked as not real data; excluded from every extraction.
- **wiTECH**: the manufacturer's dealer diagnostic tool; results are imported as evidence and passively learned from.
- **SLVT**: Small Leak Verification Test, the wiTECH dealer procedure of bulletin 18-048-23 (and 18-089-19); the bulletin says a road test cannot confirm an EVAP small-leak repair and the SLVT must be run before and after. CUORE's SLVT replica is read-only and uses the ECM's own EVAP monitor result.
- **MCP**: Model Context Protocol; the project's `mes-log` and `obd2` servers expose the log library and the live link to an assistant.
- **cuore**: the FastAPI service and UI. Profiles: `bench`, `drive`. Pages include Bench, Job, Scans, Systems, Tests, Report, Tell CUORE (mobile), Modifications, bulletins (`/tsb`).
- **Job / hypothesis ledger / case**: a job is one car's diagnosis in 12 steps; the ledger holds hypotheses with evidence, actions and next tests; a closed job becomes a case for the next same-model car.
- **Readings-only**: the rule that conclusions cite CUORE's own captured readings (RULES.md rule 2).
- **verify_bus**: on-demand proof that a bus is alive before transmitting on it.
- **xref (bulletin cross-reference)**: the engine relating bulletins to codes, repairs, hypotheses and systems.

## Bulletins and campaigns

- **TSB**: technical service bulletin; manufacturer repair guidance, not necessarily a defect admission.
- **CSN**: customer satisfaction notification; a manufacturer campaign, not a safety recall.
- **Recall**: safety or emissions campaign with a government campaign number (for example 18V636).
- **RRT**: Rapid Response Transmittal, an FCA service communication issued ahead of or alongside a TSB (e.g. RRT 17-112 cross-referenced by bulletin 18-026-20).
- **NHTSA**: US regulator whose database supplies bulletin and recall documents; the number following a bulletin is its document id.
- **Relations** in the cross-reference: explains, historical, same_system, dependent_system, candidate, already_applied, did_not_resolve, ruled_out_by_inspection, supports, weakens.
