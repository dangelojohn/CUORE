# Cuore live link: building on the vLinker FS and the coloured cables

**Date:** 2026-09-14  
**Status:** plan, ready to build. Nothing here has been implemented yet except the Tier A `obd2-mcp` rework it depends on (commit `96473d5`).  
**Inputs:** `docs/research/MES_DEEP_INTEGRATION_REVIEW.md`, `docs/reference/GIORGIO_MODULE_MAP.md`, the cuore code survey in `docs/design/review-2026-09-14/cuore_survey.md`, `docs/COMPANION_APP_SPEC.md` sections 4, 6, 10, 11, 12.

---

## 0. The decision

**Build the live link inside cuore as a new `cuore/live/` package, read-only first, and make it the one process that owns the adapter.** `obd2-mcp` becomes a thin MCP adapter over the same code, so the MCP tools and the HTTP API cannot drift, and so three Claude sessions can no longer each open COM3.

Why cuore and not a new app:

- cuore already has the profile and capability model the spec calls for. `features_for()` returns a dict a caller may overlay at runtime, `AdapterInfo.blocked_by` exists so the interlock has somewhere to say "MES holds the port", and `/api/capabilities` is where clients learn what they can do. The live layer fills those in rather than inventing them.
- cuore already has the token gate, the error-to-HTTP mapping including 503 `Unavailable`, the bridge doctrine (routers never import the domain library), and a test style. A second app would duplicate all of it.
- `cuore/bootstrap.py` already declares `OBD_ROOT` "so the P2 live path has one authoritative answer", and the lock file location `%PROGRAMDATA%\cuore\adapter.lock` is already the one `obd2-mcp` writes. The design has been pointing here since the spec was written.

Why read-only first: `actuators` is `False` in both profiles and stays so. The HTTP layer ships with no code path that can emit a vehicle write, not a flag that defaults off. Writes remain MES's job and, for `clear_dtcs`, the MCP surface's job behind its evidence gate.

---

## 1. What the hardware gives us, and what it does not

| Fact | Consequence for the design |
|---|---|
| The STN1170 has one CAN peripheral multiplexed onto pins 6/14 (HS), 3/11 (MS) or 1 (SW). Only one bus is active at a time. | A bus is a session-level selection. "Scan all modules" is three sequential passes. |
| CAN-C on pins 6/14 needs no cable and carries ECM, TCM, BCM, IPC, RFHUB, DTCM, ESM, DASM (seven scans agree). | Phase 1 needs no cable and reaches the eight modules that matter most. |
| CAN-CH on pins 12/13 has no STN transceiver mapping. The grey A6 cable re-pins it onto 6/14. | The grey cable is mandatory for ABS, EPS, airbag, headlamps, parking, camera. The software must know the cable is fitted. |
| CAN-IHS on pins 3/11 at 125 kbps is exactly the STN MS-CAN mapping (`STP 54`). The blue A5 cable also re-pins it onto 6/14. | Two routes to the same bus that must never be mixed. With the blue cable fitted, use the HS preset at 125 kbps; without it, try `STP 54`. Untested. |
| The vLinker FS is a Ford tool. Its FEPS 18 V output is OBD pin 13, which on Giorgio is CAN-CH low. | Never send undocumented commands with no cable fitted. Treat pin 13 as live until vendor documentation says otherwise. |
| `STCMM 0` makes the adapter receive without acknowledging. | Passive capture is possible with the Security Gateway locked and is the safest operation in the design. |
| ST commands give ISO-TP segmentation, flow-control pairs, periodic TesterPresent, hardware filters and batched setup. | The UDS client can be simple and fast; the adapter does the framing work. |

---

## 2. Architecture

```
cuore/
  live/
    __init__.py      public surface: link(), adapter_info(), bus table
    errors.py        LiveError hierarchy mapped to BridgeError (503 / 400)
    config.py        port, baud, bus resolution: arg -> CUORE_* env -> MES registry
    interlock.py     MES liveness (process + status label) and the advisory lock file
    stream.py        Stream ABC, SerialStream, TcpStream, RecordingStream, PlaybackStream
    transport.py     AdapterLink: lazy session, cmd, init, bus selection, identity
    framing.py       pure parsers: adapter_error, reassemble, hex_pairs, payloads_for
    buses.py         Bus records: CAN-C, CAN-IHS, CAN-CH, with cable and status
    addressing.py    ECUAddress, normal-fixed 18DA<TA>F1, module table with confidence
    obd.py           J1979: PIDs with formulas, DTCs, readiness (spark and diesel layouts), VIN, freeze frame
    uds.py           0x10 01, 0x19 02/04/06, 0x22, 0x3E, NRC decoding, 0x78 handling
    capture.py       passive monitor: STCMM 0 + filters + STM, frame store, DBC decode
    safety.py        classify_command, read-only UDS allowlist, bus transmit policy
    audit.py         append-only JSONL audit log beside the lock file
    models.py        Pydantic contracts: LiveStatus, BusInfo, ModuleScan, DidValue, Capture
  api/
    live.py          the HTTP router, token-gated, every route a plain def
obd2-mcp/
  server.py          MCP tools that import cuore.live; tool names unchanged
```

Rules the code follows:

- **One operation, one open.** `AdapterLink.session()` resolves port and baud, checks the MES label, takes the lock, opens the stream, sends `ATE0 ATL0 ATS0 ATH1`, selects the bus, configures flow control, yields, closes, releases. No port is held between calls.
- **Bus is a session property.** `session(purpose, bus=CAN_C)`. The protocol pin is per bus, not per link. Switching bus is a new session.
- **Pure parsers take explicit state.** `reassemble(raw, headers_on=True)`. No parser reads device state.
- **Every result names its bus, its cable state, and its error.** An empty list with no error field is a bug.
- **Blocking work runs in the threadpool.** Live routes are `def`, not `async def`.
- **Injected streams.** `PlaybackStream` replays a recorded wire session so the entire stack runs with no car. `RecordingStream` captures wire bytes on the car so every real session becomes a regression fixture.

---

## 3. The cable protocol

The software cannot detect which cable is plugged in, and the wrong assumption transmits a 500 kbps preset onto a 125 kbps bus or, worse, treats the chassis bus as the powertrain bus. So cable state is declared, verified, and enforced:

1. **Declare.** The operator sets the fitted cable through `POST /api/live/cable {none | blue_a5 | grey_a6}` or the `set_cable` MCP tool. Stored in `AdapterLink`, shown in `/api/capabilities` and in every result.
2. **Verify before transmit.** The first session on a newly declared bus is passive: `STCMM 0`, open, `STMA 50`. If frames arrive at the expected rate, the bus is marked `verified` for this cable state. If not, the bus stays `unverified` and transmit is refused with a message naming the cable to check.
3. **Enforce.** `safety.assert_transmit_ok(bus)` refuses any request on a bus whose cable state does not match the bus record. CAN-CH additionally requires a per-session confirmation flag on both surfaces, because brakes, airbag and steering live there.
4. **Re-plug means re-verify.** Any change of declared cable clears all verification. The audit log records every declaration.

Bus records, from `GIORGIO_MODULE_MAP.md` Table B:

| Key | Pins | Bitrate | Cable | STN setup | Initial status |
|---|---|---|---|---|---|
| `can_c` | 6/14 | 500 k | none | `STP 34` | confirmed |
| `can_ihs` | 3/11 | 125 k | blue A5, or none via MS-CAN | `STP 34` + `STPBR 125000` with cable; `STP 54` without | untested |
| `can_ch` | 12/13 | 500 k inferred | grey A6, mandatory | `STP 34`; fall back `STP 36`, then `STPBR 125000` | confirmed bus, bitrate unverified |

---

## 4. The module table

`addressing.py` encodes `GIORGIO_MODULE_MAP.md` Table A with a `confidence` field on every address. The rule: **only `confirmed` addresses are used for targeted requests. `inferred` and `unverified` addresses appear in the discovery sweep only, and become `confirmed` when the module returns a VIN or a part number that matches this car's scan logs.** Confirmation is persisted per VIN so the sweep is done once.

Starting state: ECM `0x10`, TCM `0x18`, BCM `0x40`, IPC `0x60`, RFHUB `0xC7` confirmed on CAN-C. EPS `0x2A` inferred on CAN-CH. Everything else unknown. `0xBA` and `0xF1` and `0x33` are excluded from sweeps; `0xC7` carries a documented immobiliser hazard only when a BACCAble board is fitted, which it is not, and the warning stays in the data.

Discovery is `22 F190` per candidate address with a 200 ms timeout. A `62 F190` reply is a live node; the VIN proves the address, and `F187`/`F191` part numbers name the module by matching the HW numbers in Table A.

---

## 5. Phases

Each phase ends with a verification list that must pass before the next starts. Sizes are relative effort, not calendar promises.

### Phase 0: move the engine into cuore, no car needed (size M)

Deliverables:
- `cuore/live/` with `stream`, `interlock`, `config`, `transport`, `framing`, `safety`, `audit`, `models`, ported from `obd2-mcp/server.py` and `stelvio_scan/adapter/stream.py`, `recording/*`. `State` becomes `AdapterLink`. Parsers become pure.
- `buses.py` and `addressing.py` as data with confidence fields.
- `obd.py` with the PID table (stelvio_scan's dataclass, obd2's resolver), readiness with both spark and compression layouts, DTC decoding for 2-byte and 3-byte codes emitted as `P0456-00` so live codes join the MES vocabulary.
- `cuore/api/live.py` with `GET /api/live/status`, `GET /api/live/ports`, `POST /api/live/probe`, `POST /api/live/cable`, and the OBD reads (`dtcs`, `pid`, `readiness`, `vin`, `freeze`, `voltage`).
- `/api/capabilities` reports `live_obd` true on bench when a port resolves and MES is not connected, `adapter.present`, `adapter.port`, `adapter.blocked_by`, and the bus table with statuses.
- `obd2-mcp/server.py` reduced to tool wrappers over `cuore.live`, same tool names, plus `set_cable`.
- `cuore/tests/check_live.py`: the ported `test_fixes.py` cases plus a `PlaybackStream` end-to-end using a wire recording taken over USB.
- `check_api.py` updated where it pins the live flags to false.

Verification: all check scripts pass; the USB probe returns the vLinker identity through both surfaces; the lock file shows `process: cuore`; three concurrent Claude sessions cannot open COM3 at once.

### Phase 1: CAN-C on the car, no cable, read-only (size L)

Deliverables:
- `uds.py`: session control default only, `0x19 02` DTC read by status mask, `0x19 04` and `0x19 06` for snapshot and extended data (to write; stelvio_scan has only `02`), `0x22` DID read with the Annex C catalog plus Table C entries carrying their confidence, `0x3E` via `STPPMA`, NRC decoding, and `0x78` handled by waiting `P2*` and re-reading.
- `GET /api/live/modules?bus=can_c`: per-module `0x19 02` sweep over confirmed addresses, results in MES vocabulary and attributed to the module.
- `GET /api/live/module/{code}/dtcs`, `GET /api/live/module/{code}/did/{did}`, `GET /api/live/module/{code}/identity` (the Annex C set).
- `POST /api/live/discover {bus}`: the `22 F190` address sweep, persisting confirmations per VIN.
- `capture.py` and `POST /api/live/capture {bus, seconds, filters}`: passive only.
- Wire recordings of every on-car session saved under `%PROGRAMDATA%\cuore\recordings\wire\` and promoted to test fixtures.

On-car checks, all read-only, from `GIORGIO_MODULE_MAP.md`: Q4 confirms the five addresses; Q5 discovers DTCM, ESM, DASM; Q7 settles the filter spelling; Q8 verifies the ECM and TCM DIDs on a petrol 2.0T; Q1 and Q2 test `STP 54` for CAN-IHS with no cable.

Verification: the VIN returned by `22 F190` on the ECM matches the scan logs; DTCs read live match the most recent MES scan for the same modules; a whole-bus sweep produces no new `-87`/`-2F` bystander codes on a following MES scan, or the plan documents that it does and the sweep gains a pacing option.

### Phase 2: the other two buses (size M)

Deliverables:
- CAN-CH profile active once the grey cable is declared and verified. Q3 settles the bitrate. Chassis modules read with the per-session confirmation. ABS, ORC, AFLS, PAM, HALF addresses discovered and confirmed.
- CAN-IHS profile with both routes: blue cable, and `STP 54` if Q1 passed. Q10, the first ever scan of that bus on this car, populates the missing third of the module table.
- `mes/modules.py` gains `bus` and `cable` fields from the confirmed data and drops the diesel-only flags for this car.

Verification: every module in the scan logs answers `22 F190` on its recorded bus; the capability response shows all three buses with `verified` under the right cable.

### Phase 3: correlation and persistence (size M)

Deliverables:
- A small SQLite store beside the lock file for `Session`, `Observation`, `AddressConfirmation`, `Capture`, following the spec's data model. No cache for live data.
- Live results enter the evidence gate: `live_dtc`, `live_readiness`, `live_permanent`, `uds_did` join `_VERIFIABLE` in `mes/verdict.py`, citing the persisted observation.
- A parameter synonym table mapping MES parameter names to PIDs and DIDs, so `workup` can say "MES saw boost at X, the DID says Y now".
- The session-completion watcher on the MES log folder, publishing an MCP notification and a `resources/list_changed` when a session lands.

Verification: a verdict can cite a live measurement and the gate verifies it against the store; a MES session flushed to disk shows up in cuore within seconds without polling.

### Phase 4: telemetry (size L, later)

- `0x0F1` voltage at 100 Hz through passive capture, validated once against a DVOM.
- DBC decoding with `cantools` and the opendbc Giorgio DBC, labelled relative not absolute.
- Drive recorder writing the `csvlog` schema, the WebSocket stream, and the drive profile. This is the spec's P3 and needs the in-car node decision.

---

## 6. Safety policy for the live layer

1. No vehicle writes exist in `cuore.live`. The read-only UDS allowlist is `0x10 01`, `0x19`, `0x22`, `0x3E`. Anything else raises before reaching the adapter.
2. `clear_dtcs` stays on the MCP surface only, with its evidence capture, speed check and read-back.
3. Transmit on CAN-CH requires the grey cable declared, the bus verified passively, and a per-session confirmation. Transmit on CAN-IHS requires the same minus the confirmation.
4. Never send FEPS, programming-voltage, or undocumented ST/AT commands. The `classify_command` allowlists from `obd2-mcp` are the gate on both surfaces; monitor modes run only through `capture.py`'s own loop.
5. Every session, cable declaration, discovery and capture is written to the audit log with timestamp, purpose, bus, and outcome.
6. Simulation-mode MES output and playback sessions are marked as such and never enter the store as real observations.
7. The pins 1/9 continuity check and the S3 wait after MES exits are shown in the UI and in the MCP tool descriptions.

---

## 7. Tests

- Pure-function regression over `framing`, `safety`, `addressing`, `obd`, `uds` decoders, ported from `test_fixes.py`.
- `PlaybackStream` end-to-end: a recorded USB probe now, recorded on-car sessions after Phase 1, run on every change with no hardware.
- `ELM327-emulator` over a virtual COM pair as an optional stateful UDS simulator for multi-frame and NRC `0x78` cases.
- `check_api.py` extended with the live routes against `PlaybackStream`.

---

## 8. Decisions for the owner

1. **One process for the adapter.** Recommend cuore owns COM3 and `obd2-mcp` imports `cuore.live` in-process. The alternative, `obd2-mcp` calling cuore over HTTP, is cleaner for concurrency but adds a running service dependency to every Claude session.
2. **Cable declaration UX.** A tool call and an HTTP route are proposed. A physical alternative is to read the bus passively on every open and infer the cable from traffic rate and IDs; that is safer but slower, and is worth adding once the buses are verified.
3. **Move MES off COM3?** Not required by this design, since the port is never held. It would still remove the last contention case.
4. **Store location.** `%PROGRAMDATA%\cuore\` for lock, audit, store and wire recordings, next to what exists. `%LOCALAPPDATA%` if a per-user split is preferred.
5. **The blue-cable bus has never been scanned.** One MES scan with the A5 fitted before Phase 2 would replace a third of the module table's inference with fact.

---

## 9. What to do first

Phase 0 needs no car and is mostly a move of code that already passes its tests. The first on-car session after it is Phase 1's Q4: five `22 F190` reads on CAN-C with no cable, ten minutes, read-only, proving the addressing on this exact car. Everything else builds on that answer.
