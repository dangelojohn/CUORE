# GitHub tooling review for CUORE (STN1170 / vLinker FS, FCA)

Date: 2026-10-20. Method: GitHub API metadata, raw source files and READMEs opened via WebFetch; 8 standard web searches.
Rule applied: only what was opened is stated as fact. Anything from background knowledge is tagged **[UNVERIFIED]**.
Licence notes are reading of the licence field/file, not legal advice. CUORE's own licence is not stated here; GPL/CC-NC items matter if CUORE is ever distributed.

Problem numbers used throughout:
(1) functional (7DF / 18DB33F1) requests give NO DATA after physical UDS sessions; ATWS does not fix it.
(2) a module answers 22 F190 once, then never again.
(3) decode manufacturer freeze-frame DID records and Mode 06 (OBDMID/TID/UASID) for FCA.
(4) FCA ESIM / NVLD EVAP monitor internals.

## Summary table

| Project | URL | Licence | Last push | Relevance |
|---|---|---|---|---|
| python-udsoncan | https://github.com/pylessard/python-udsoncan | MIT | 2026-09-21 | P2/P2*/0x78 logic, SPR, session timing (1,2) |
| python-can-isotp | https://github.com/pylessard/python-can-isotp | MIT | 2026-08-22 | FC params, functional = single frame only, 29-bit addressing (1,2) |
| python-OBD | https://github.com/brendan-w/python-OBD | GPL-2.0 | 2025-04-07 | Mode 06 monitor parser + UAS table 0x01-0xFE (3), ELM init/reset (1) |
| opendbc (openpilot car code) | https://github.com/commaai/opendbc | MIT | 2026-10-20 | uds.py, isotp_parallel_query.py, Chrysler FW queries (1,2,3) |
| ObdMetrics | https://github.com/tzebrowski/ObdMetrics | Apache-2.0 | 2026-10-19 | CAN_ERROR_RESET / RECOVERY command groups (1) |
| OBD.NET | https://github.com/DarthAffe/OBD.NET | GPL-2.0 | 2022-06-06 | ST filter command names (1) |
| stn1170-tools | https://github.com/bigunclemax/stn1170-tools | GPL-3.0 | 2022-03-10 | ATWS reply check, `?` resync, STI/STP (1) |
| electricimp/STN1110 | https://github.com/electricimp/STN1110 | MIT | 2018-06-12 | timeout abort byte, ATZ+ATE0 reset (1) |
| caringcaribou | https://github.com/CaringCaribou/caringcaribou | GPL-3.0 | 2026-06-12 | UDS timing constants, DID dump, TP cadence (2) |
| ELM327-emulator (Ircama) | https://github.com/Ircama/ELM327-emulator | CC BY-NC-SA 4.0 (GitHub: NOASSERTION) | 2026-09-17 | which ST/AT cmds exist; test harness (limited) |
| ELMduino | https://github.com/PowerBroker2/ELMduino | MIT | 2025-05-20 | input flush before send; error-string mapping (2) |
| OBDb Chrysler-300 / Alfa-Romeo* / Maserati* | https://github.com/OBDb/Chrysler-300 | CC-BY-SA-4.0 | 2026-10-19 | FCA hdr/rax Mode 21/22 examples; no Stelvio, no EVAP (3) |

## Per-project sections

### python-udsoncan (MIT, v1.26.1, pushed 2026-09-21)
- `udsoncan/configs.py` default client config (quoted): `'request_timeout': 5`, `'p2_timeout': 1`, `'p2_star_timeout': 5`, `'use_server_timing': True`, `'tolerate_zero_padding': True`.
- `client.py: send_request`: `overall_timeout = config['request_timeout']`; `p2 = config['p2_timeout'] if session_timing.p2_server_max is None else session_timing.p2_server_max`; `single_request_timeout = min(overall_timeout, p2)`. On the first 0x78 (`RequestCorrectlyReceived_ResponsePending`) it switches once to P2* (`p2_star_server_max` or config `p2_star_timeout`) and keeps waiting; other negatives raise `NegativeResponseException`. Optional `nrc78_callback`. Errors distinguish "P2 timeout", "P2* timeout", "Global request timeout".
- `change_session()` stores the server's `p2_server_max` / `p2_star_server_max` from the 0x10 positive response when `use_server_timing` is on and standard_version > 2006 (a `SessionTiming` object).
- `tester_present()` sends a single request, no keepalive thread. `Client.SuppressPositiveResponse` has `enabled` and `wait_nrc`; if SPR used and not wait_nrc, `send_request` returns None without reading.
- `connections.py`: `BaseConnection` (`send`, `wait_frame`), `QueueConnection`, `FakeConnection`, `PythonIsoTpConnection`, `J2534Connection`. No serial/ELM class. A custom ELM/STN connection would subclass `BaseConnection`; `FakeConnection`/`QueueConnection` suit offline tests.
- Reuse: MIT, free to copy with notice.

### python-can-isotp (MIT, pushed 2026-08-22)
- `TransportLayerLogic.Params` defaults: `stmin=0`, `blocksize=8`, `wftmax=0`, `tx_data_length=8`, `tx_padding=None`, `rx_flowcontrol_timeout=1000` ms, `rx_consecutive_frame_timeout=1000` ms, `blocking_send=False`, `listen_mode=False`.
- `send()`: Functional target address type raises `ValueError("Cannot send multi packet frame with Functional TargetAddressType")` if payload exceeds one frame. Functional = single frame only.
- `address.py`: `AddressingMode` Normal_11bits, Normal_29bits, NormalFixed_29bits, Extended_*, Mixed_*. NormalFixed_29bits physical base `0x18DA0000`, functional base `0x18DB0000`; TX id = base | (target<<8) | source; RX id = base | (source<<8) | target.
- Reuse: MIT. Useful as a reference for ISO-TP timers when ATCAF0 (raw) is used.

### python-OBD (GPL-2.0, pushed 2025-04-07)
- `elm327.py` init: open port `timeout=10`; `ATZ` (1 s delay), `ATE0`, `ATH1`, `ATL0`; optional `AT RV` (voltage < 6 fails); protocol `ATSP0` + `0100`, then `ATDPN`; fallback loop `ATTP<n>` + `0100` over order 6,8,1,7,9,2,3,4,5,A. `close()` sends `ATZ`. `__send` retries reading in 0.1 s steps up to about 1 s. The only failure string checked is `UNABLE TO CONNECT`. No `ATCAF`, `ATST`, `NO DATA` handling in this file.
- `decoders.py`: `monitor(messages)` drops the mode byte, truncates to a multiple of 9, calls `parse_monitor_test(d, mon)`: `tid = d[1]`, `uas = UAS_IDS.get(d[2])`, `test.value = uas(d[3:5])`, `test.min = uas(d[5:7])`, `test.max = uas(d[7:])`. So per 9-byte block: d[0]=OBDMID, d[1]=TID, d[2]=UASID, then value, min, max (2 bytes each).
- `commands.py` Mode 06: `OBDCommand("MONITOR_...", ..., b"0601", 0, monitor, ECU.ALL, False)`; `MIDS_A = 0600` with `pid` decoder; comment "This is for CAN only". EVAP MIDs: `MONITOR_EVAP_150 = 0639` (cap off/0.150"), `063A` 0.090", `063B` 0.040", `063C` 0.020", `063D` purge flow.
- `codes.py: TEST_IDS` only has 0x01-0x0C (O2 sensor TIDs, misfire average/count). No EVAP TIDs. Manufacturer TIDs are not covered.
- `UnitsAndScaling.py: UAS_IDS`: 92 keys; 0x01-0x41 unsigned, 0x81-0xFE signed (no 0x80); each `UAS(signed, scale, unit, offset=0.0)`; value = int(bytes) (two's complement if signed) * scale + offset; 0x2E is a lambda (any byte non-zero). Verified entries (hex: signed,scale,unit[,offset]): 01:0,1,count; 02:0,0.1,count; 03:0,0.01,count; 04:0,0.001,count; 05:0,0.0000305; 06:0,0.000305; 07:0,0.25,rpm; 08:0,0.01,kph; 09:0,1,kph; 0A:0,0.122,mV; 0B:0,0.001,V; 0C:0,0.01,V; 0D:0.00390625 mA; 0E:0.001 A; 0F:0.01 A; 10:1 ms; 11:100 ms; 12:1 s; 13:1 mOhm; 14:1 Ohm; 15:1 kOhm; 16:0.1 degC offset -40; 17:0.01 kPa; 18:0.0117 kPa; 19:0.079 kPa; 1A:1 kPa; 1B:10 kPa; 1C:0.01 deg; 1D:0.5 deg; 1E:0.0000305 ratio; 1F:0.05 ratio; 20:0.00390625 ratio; 21:1 mHz; 22:1 Hz; 23:1 kHz; 24:1 count; 25:1 km; 26:0.1 mV/ms; 27:0.01 g/s; 28:1 g/s; 29:0.25 Pa/s; 2A:0.001 kg/h; 2B:1 count; 2C:0.01 g; 2D:0.01 mg; 2F:0.01 %; 30:0.001526 %; 31:0.001 L; 32:0.0000305 inch; 33:0.00024414 ratio; 34:1 min; 35:10 ms; 36:0.01 g; 37:0.1 g; 38:1 g; 39:0.01 % offset -327.68; 3A:0.001 g; 3B:0.0001 g; 3C:0.1 us; 3D:0.01 mA; 3E:0.00006103516 mm^2; 3F:0.01 L; 40:1 ppm; 41:0.01 uA; signed: 81:1 count; 87:1 ppm; FE:0.25 Pa. The signed 0x81-0xFE entries other than these three were not read individually.
- Per a search snippet (not opened): python-OBD docs label Mode 06 experimental and untested on a real vehicle.
- Reuse: GPL-2.0 (copyleft). Do not paste the table verbatim into a non-GPL project. The UASID scalings are standard SAE J1979 facts; re-derive from J1979 or from a clean implementation, and keep python-OBD as a cross-check.

### opendbc / openpilot (MIT, pushed 2026-10-20)
Note: `panda/python/uds.py` no longer exists; UDS code lives in `opendbc/car/uds.py` (39.8 KB), plus `isotp_parallel_query.py`, `fw_query_definitions.py`, `fw_versions.py`, `ecu_addrs.py`, `disable_ecu.py`, and `chrysler/values.py`.
- `uds.py`: `UdsClient.__init__(timeout=1, tx_timeout=1, response_pending_timeout=10)`; wait uses `self.response_pending_timeout if response_pending else self.timeout`. NRC 0x78 sets `response_pending = True` and loops; no resend on timeout. `FUNCTIONAL_ADDRS = [0x7DF, 0x18DB33F1]`; `CanClient._recv_filter` ("handle functional addresses (switch to first addr to respond)") rebinds to the first physical responder.
- `IsoTpMessage.send(dat, setup_only=False)` starts with `self._can_client.recv(drain=True)`: stale input is discarded before every request. `setup_only=True` sets up RX state without transmitting (used after a functional broadcast). FC frame: `0x30` (continue), block size `0x01 if single_frame_mode else 0x00`, separation-time byte, zero-padded with `.ljust(max_len, b"\x00")` (padding is 0x00, not 0xAA). FC status handling: `0x32` aborts, `0x31` waits, `0x30` continues. ST min encoding: `0xF1+` for 100-900 us, ms otherwise. `CanClient.send` drains RX every 10 frames.
- `isotp_parallel_query.py`: `IsoTpParallelQuery.get_data(timeout, total_timeout=60.)`; functional requests are sent once on the functional addr, then each physical addr is listened to with `setup_only=True`; "Functional-address timeouts are not handled (TODO)". 0x78 resets the deadline to `response_pending_timeout`. Consecutive-frame pacing `separation_time=0.01`.
- `fw_versions.py`: default `timeout=0.1`; requests batched in chunks of 128; no retries; `set_obd_multiplexing(bool)` toggled per request group (a comma/panda concept, not an STN one).
- `fw_query_definitions.py` `StdQueries`: `OBD_VERSION_REQUEST = b'\x09\x04'`, `TESTER_PRESENT_REQUEST = [0x3E, 0x00]`, default/extended diagnostic session requests, manufacturer software number DID request. `Request.rx_offset` default 0x08.
- `chrysler/values.py` (FCA): `CHRYSLER_RX_OFFSET = -0x280` (response id = request id - 0x280 for the listed ECUs, not +8); DID `0xf132` and `SYSTEM_SUPPLIER_ECU_SOFTWARE_NUMBER` (0xF194) are the FW queries; alt ABS address 0x7e4 on hybrids. F190 is not used for FCA FW fingerprinting.
- `disable_ecu.py`: sequence `10 03` -> `28 83 01`, no TesterPresent, no functional addr (writes/state-changing; not for CUORE read-only use).
- `ecu_addrs.py`: scans 0x700-0x7FF and 0x18DA00F1+(i<<8); sends TesterPresent, accepts 0x7E or 0x7F 0x3E; does not use 0x7DF.
- Reuse: MIT.

### ObdMetrics (Apache-2.0, pushed 2026-10-19; branch v11.x)
`command/group/DefaultCommandGroup.java` (quoted): `INIT` = ATZ, delay 0, ATH0, ATL0, ATE0, ATAL, ATAT2; `CAN_ERROR_RESET` = delay 200 ms, ATWS, delay 500 ms; `RECOVERY_AFTER_STOPPED` = delay 500 ms, "\r", ATE0, ATCS; `SNIFFING` = ATZ, ATE0, ATL0, ATH1, ATCAF0. README: Mode 22 batching "up to 21 PID's in the single call"; expected-frame counts "bypass the hardware waiting timeout (P2)". I did not find where CAN_ERROR_RESET is triggered (AbstractConnector does not reference it). README names no individual ST commands.
Reuse: Apache-2.0.

### OBD.NET (GPL-2.0, pushed 2022-06-06)
`Commands/STCommand.cs` strings: AddPassFilter=`STFAP`, AddBlockFilter=`STFAB`, AddFlowControlFilter=`STFAFC`, ClearPassFilters=`STFCP`, ClearBlockFilters=`STFCB`, ClearFlowControlFilters=`STFCFC`, Monitor=`STM`, MonitorAll=`STMA`. `ELM327.cs` init: ResetDevice, EchoOff, LinefeedsOff, HeadersOff, PrintSpacesOff, SetProtocolAuto; no NO DATA handling, no timeouts. Reuse: GPL-2.0; only the command names are of use.

### stn1170-tools (GPL-3.0, pushed 2022-03-10)
`stnlib/CanDevice.cpp`: probes with `ATWS\r` and expects `"ELM327 v1."` in the reply (so ATWS on STN answers the ELM version string: a usable "did it really reset" check); `STI` identity; `?\r` flush/resync; `STBR`, `STWBR`, `STBRT`; protocol `STP53`/`STP33` (STN) vs `ATSPB`/`ATSP6`; `STDI`, `STIX`, `STMFR`, `STSN` info. No ATZ used. Reuse: GPL-3.0.

### electricimp/STN1110 (MIT, pushed 2018-06-12)
`reset()`: ATZ then ATE0, expects "OK". `_handleTimeout()` writes `_END_OF_TRANSMISSION` (0x04) to kill a hung command, then runs the next queued command. Packets split on `"\r\r>"`. Only ST command used: `STBR`. Whether 0x04 actually aborts on an STN1170 is **[UNVERIFIED]**.

### caringcaribou (GPL-3.0, pushed 2026-06-12)
`modules/uds.py` constants: `DELAY_DISCOVERY=0.01`, `VERIFICATION_BACKTRACK=5`, `VERIFICATION_EXTRA_DELAY=0.5`, `TIMEOUT_SERVICES=0.2`, `DELAY_TESTER_PRESENT=0.5`, `TIMEOUT_SUBSERVICES=0.02`, `DUMP_DID_MIN=0x0000`, `DUMP_DID_MAX=0xFFFF`, `DUMP_DID_TIMEOUT=0.2`. `tester_present` uses sub-function 0x80 (suppress) or 0x00, repeating every 0.5 s. `dump_dids` keeps responses >= 4 bytes whose echoed DID matches. 0x78 is not handled. `service_discovery` probes all services 0x00-0xFF (includes write services; unsafe for CUORE). Reuse: GPL-3.0.

### ELM327-emulator, Ircama (CC BY-NC-SA 4.0, pushed 2026-09-17)
README: `ATCAF` (`cmd_caf`), `ATSH` (`cmd_set_header`), `ATCRA` (`cmd_cra`, X/W wildcards) and `ATWS` (via `cmd_version`) handled. `STSLX`, `STPp`, `STCFCPA`/`STCAFCP`, `STPTO`, `STIP4` are recognised but unhandled; `ATFCSH/ATFCSD/ATFCSM` recognised, not handled. STPX, STFAP, STMA not mentioned. Does not model STN state, so it cannot reproduce problems 1-2. Non-commercial, share-alike: personal use only; do not copy code into a product.

### ELMduino (MIT, pushed 2025-05-20)
`sendCommand` flushes the input buffer, then sends the command + CR. `get_response` maps UNABLE TO CONNECT / NO DATA / STOPPED / ERROR to states; `sendCommand_Blocking` breaks on `millis() - startTime > timeout_ms`. Init sets defaults, reset, echo off, spaces off, long messages, data timeout (`SET_TIMEOUT_TO_H_X_4MS`, i.e. ATST in 4 ms units).

### OBDb (CC-BY-SA-4.0 data)
Repos exist for Alfa-Romeo (make), -Giulia, -Giulietta, -MiTo, -Tonale, Maserati, Maserati-Levante, and Chrysler-* (200, 300, Pacifica, ...). No Stelvio repo. Giulia and Tonale `signalsets/v3/default.json` are 21 bytes (empty). Chrysler-300 is 41 KB: commands use `hdr`/`rax` (e.g. `763`/`4E3`, `7E0`/`7E8`, `7E1`), `fcm1`, `cmd` as `{"22": "032D"}` or `{"21": "17"}`, `freq`, `dbg`. Only services 21 and 22. No 06, no 19, no EVAP/NVLD/ESIM signals. Share-alike: attribution plus same licence on derivative data.

## Actionable for CUORE (hypotheses to test; none proven)

1. (P1) Prove what state survives. After a physical session and a failed functional request, issue in order: `ATZ` (not ATWS), wait about 1 s (python-OBD waits 1 s after ATZ), `ATE0`, then `ATI`/`STI`, `ATDPN`. Compare with `ATWS` and check the reply is the ELM version string (stn1170-tools uses `"ELM327 v1."` as its ATWS success test). Log whether the STN actually went through reset. ObdMetrics' `CAN_ERROR_RESET` is delay 200 ms, ATWS, delay 500 ms: the delays may matter more than the command.
2. (P1) Clear every STN filter explicitly after each physical session, before functional requests: `STFCP`, `STFCB`, `STFCFC` (names from OBD.NET), and clear any ATCRA/ATSH/ATFCSH/ATCM/ATCF left from physical addressing, then re-issue `ATSH 7DF` or the 29-bit header. Whether ATZ/ATWS clears STN filters on an STN1170 is **[UNVERIFIED]** (no source found); test by reading back filter state if the firmware offers it.
3. (P1) Keep functional requests single-frame and receive-filter on the right IDs. Functional is single-frame only in python-can-isotp. For FCA, responses to non-engine modules are at request id - 0x280 (opendbc `CHRYSLER_RX_OFFSET`), so a leftover `ATCRA 7E8` hides them. Use no ATCRA (or a wildcard) for functional, then restore per-module ATCRA for physical.
4. (P1, P2) Drain before every request. opendbc `IsoTpMessage.send` starts with `recv(drain=True)`; ELMduino flushes input in `sendCommand`. In CUORE, flush serial input and send a bare `\r` (ObdMetrics `RECOVERY_AFTER_STOPPED`) or `?` (stn1170-tools) to resync the prompt, so a late 0x78 or final response is not read as the next reply. This is also the cheapest explanation for "answers once, then never" (reply offset by one).
5. (P2) Check the multi-frame path. A VIN reply is multi-frame. With ATCAF1 the adapter sends the flow control; with ATCAF0 CUORE must send it: `30 00 <STmin>` zero padded to 8 bytes (opendbc), BS 0 or isotp default 8, STmin 0. If a module is left waiting for FC it may ignore the next request until its own timer expires (isotp default 1000 ms `rx_flowcontrol_timeout`). Test: repeat F190 after waiting more than 1 s, and after an explicit `STFCFC`/ATCAF1.
6. (P2) Try other DIDs on the same module. opendbc FCA queries use `F132` and `F194` (SYSTEM_SUPPLIER_ECU_SOFTWARE_NUMBER), not F190; a module that stops answering F190 after one use but answers F194 points to adapter state, not the module.
7. (P1, P2) Timing model. Adopt udsoncan/openpilot semantics: P2 = 1 s default, after the first 0x78 switch to P2* (udsoncan 5 s default, openpilot 10 s), parse `p2_server_max`/`p2_star_server_max` from the 0x10 response if you use sessions. The adapter's own response timeout (ATST/STPTO) must be at least as long or it returns NO DATA while the ECU is still pending. Setting names: ELMduino uses the ATST x4 ms form; STPTO is named in Ircama's README. Values for the STN1170 are **[UNVERIFIED]**.
8. (P1, P2) TesterPresent: send `3E 80` (suppress positive response) at about 0.5 s cadence only while a non-default session is intentionally held (caringcaribou cadence), and stop it before functional OBD requests. udsoncan provides no keepalive, so CUORE owns this. Do not leave a keepalive running, and do not read the adapter's late `7E 00` replies as answers.
9. (P3) Mode 06 decode: implement `46 OBDMID TID UASID VAL(2) MIN(2) MAX(2)` in 9-byte blocks (python-OBD `parse_monitor_test` layout); value = raw * scale + offset with two's complement for UASID >= 0x81. Build the UASID table from J1979 (python-OBD values as a cross-check; GPL). Query supported MIDs with `0600` and walk `0620`, `0640`, ... (python-OBD `MIDS_A = 0600`). Standard EVAP MIDs per python-OBD: 0x39-0x3D. Treat TID >= 0x80 as manufacturer-defined and display raw plus UASID scaling, since no open table was found.
10. (P3) For manufacturer freeze-frame/snapshot DIDs, use `19 04`/`19 06`-style reads and log raw hex per DTC; no public FCA decoder exists in what I opened. Seed offline tests with udsoncan `FakeConnection`/`QueueConnection`.

## Not useful (for these problems)
- AlfaOBD GitHub results: repos are crack/licence-key spam with 0 stars; do not download. No real AlfaOBD source exists on GitHub from this search.
- STFAP/STPX/STCFCPA code search: GitHub code search needs authentication (401/403 returned), and repo-name searches for those terms returned only empty "stpx" spam repos. No public Python example of STFAP/STCFCPA/STPX flow control was found. ST command semantics must come from the ScanTool.net STN11xx/STN21xx reference manual (not opened; not on GitHub).
- python-OBD for FCA: Mode 06 `TEST_IDS` only has O2/misfire TIDs; no EVAP TIDs; Mode 06 labelled experimental.
- ELMduino: no Mode 06, no ST commands, no UDS.
- caringcaribou: security-research scanner (service discovery probes write services); only the timing constants and DID-dump idea are reusable. GPL-3.0.
- opendbc `disable_ecu.py`: sends 0x10 0x03 and 0x28; not read-only.
- OBDb: no Stelvio, Giulia/Tonale empty, Chrysler-300 has no EVAP or Mode 06.
- Anything on ESIM/NVLD internals (P4): no GitHub project found. Web results only gave background (Chrysler NVLD, then ESIM from 2007 uses a weighted check-valve switch, no solenoid; patents US7216636B2, US6928991B2, US7047950B2, US6823850B1; Chrysler Mode 06 data is behind paid access; mode06.com lists data). These were search snippets only, not opened, so treat as leads. No FCA EVAP Mode 06 TID list found.
- Generic FCA/Stellantis UDS freeze-frame decoders (P3): none found. Layouts are likely in non-public ODX/CDD data (search snippet, **[UNVERIFIED]**).
