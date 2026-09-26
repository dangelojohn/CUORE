# Actuator tests: learned from MES/wiTECH, replayed under strict guards

Written 2026-09-26. Covers `cuore/live/actuate.py` (extraction, persistence,
replay) and the `ACTUATION_UDS` / `ACTUATION_BLOCKED_MODULES` gates added to
`cuore/live/safety.py`. Companion to `docs/research/WITECH_PASSIVE_LEARNING.md`
(the capture/pairing pipeline this reuses) and `cuore/live/clear.py` (the
existing guarded write, whose evidence-first/consent-phrase/audit style this
follows).

## Why this exists

FCA does not publish `InputOutputControlByIdentifier` (UDS `0x2F`) or
`RoutineControl` (`0x31`) identifiers for Giorgio-platform modules, so cuore
never guesses at an actuator-test request. The only way to run one safely is
to watch a dealer tool run it once and record exactly what it sent. That is
what this feature does: it never invents a DID, controlParameter or routine
ID. It only replays, byte for byte, a sequence a real tool already sent to a
real module.

## The workflow

1. **Splitter cable**, same as passive DID learning: MultiEcuScan's (or
   wiTECH's) cable and cuore's adapter both listen on the same bus at once.
2. **Start a capture while the technician runs the test in MES**, e.g. the
   ECM's "Evaporation control valve" actuator test:
   `learn_capture(bus="can_c", seconds=20)`. This is the same tool passive
   DID learning uses; it saves raw frames and paired UDS transactions to
   `state_dir()/captures/<timestamp>_<bus>.json`.
3. **Extract the procedure**: `learn_actuator(capture, module="ECM",
   name="Evaporation control valve", tool="MES")`. This finds every request
   MES sent to that module's target address in the capture window, in order,
   classifies whether the sequence is safe to replay, and works out (or
   synthesises) the terminating request. The result is saved to
   `state_dir()/actuators.json` keyed by VIN, module and test name.
4. **List what was learned**: `list_actuators(vin=...)` — module, test name,
   source tool, whether it is replayable, and why not when it is not.
5. **Replay it**: `run_actuator(module="ECM", name="Evaporation control
   valve", consent="ACTUATE ECM EVAPORATION CONTROL VALVE", vin=...)`. See
   the guards below — most of them exist specifically so this step can be
   trusted with a real actuator.

## What gets classified `replayable`, and what does not

`extract_procedure(transactions, target)` in `actuate.py` walks the paired
UDS transactions to one target address, in the order the tool sent them, and
classifies:

- **Replayable** only if every request's service is on the actuation
  allowlist — `0x10` (DiagnosticSessionControl) sub `0x01` default or `0x03`
  extended, `0x3E` TesterPresent, `0x2F` InputOutputControlByIdentifier,
  `0x31` RoutineControl, `0x22`/`0x19` reads — **and** none of
  `0x2E` (WriteDataByIdentifier), `0x34`-`0x37` (reflash), `0x3D`
  (WriteMemoryByAddress), `0x11` (ECUReset), `0x28` (CommunicationControl) or
  `0x85` (ControlDTCSetting) appears anywhere in the sequence.
- **`requires_security_access`**, not replayable, if `0x27` SecurityAccess
  appears. A seed/key exchange is per-session; recording a captured key and
  replaying it later does not work and is not attempted. These procedures
  still get saved (for the record — the module and address are useful) but
  `run_actuator` refuses them.
- **Terminator**: if the last `0x2F`/`0x31` request in the sequence was
  already `returnControlToECU` (`2F <did> 00`) or a routine stop
  (`31 02 <routine>`), the capture is complete as recorded
  (`ended_with_terminator: true`). If it was not — the technician navigated
  away from the test screen without releasing control, which is common —
  `extract_procedure` **synthesises** the correct terminating request from
  the learned DID or routine ID and marks it `synthesised: true`. If the
  last request was too short to even read a DID/routine ID out of, nothing
  safe can be synthesised and the procedure is refused outright rather than
  replayed with no way back to normal.

## The guards on replay

`run_actuator` (in `actuate.py`, wired through `ops.run_actuator`) refuses
unless, in order, before anything reaches the wire:

1. **Consent** is exactly `ACTUATE <MODULE> <NAME>`, upper-case, e.g.
   `ACTUATE ECM EVAPORATION CONTROL VALVE` — the same style as `clear.py`'s
   `CLEAR <MODULE>`.
2. **The module is not safety-critical.** `safety.ACTUATION_BLOCKED_MODULES`
   — ABS, EPS, ORC, HALF, DASM, ESL (aka NBS), TVM — is refused outright,
   and separately, *anything on the CAN-CH bus* is refused outright,
   regardless of `confirm`. This is not a confirmable risk like a CAN-CH
   read; it is a flat refusal. Use MultiEcuScan or wiTECH for an actuator
   test on brakes, airbag, steering or torque vectoring.
3. **The learned procedure is replayable** (see above).
4. **The vehicle is stationary with the engine off.** `ops.run_actuator`
   reads PID `0C` (RPM) then `0D` (speed) on the legislated OBD route before
   opening the actuator session. Refuses if either reads greater than zero,
   *or if either cannot be read at all* — an actuator test does not get the
   benefit of the doubt that `clear.py`'s `override_speed_check` gives a
   DTC-memory clear.
5. **MultiEcuScan is not connected** — enforced by the same transport
   interlock every other session uses; nothing new here.

During replay, every request is checked again by
`safety.assert_actuation_allowed(service, payload)` immediately before
`Session.uds` sends it — `Session.uds` will transmit any service, so this
call is the only thing standing between a learned procedure and the wire.
The requests are sent in the learned order with the learned timing (the
gap between consecutive requests' capture timestamps), bounded so the whole
replay never runs longer than `max_seconds` (default 10 s, hard capped at
30 s regardless of what is asked for).

**The terminating request(s) are ALWAYS sent**, in a `finally` block, even
if a mid-procedure response is a negative response (NRC) or sending raises
partway through — the module is never left in an actuated or held state.
The default diagnostic session (`10 01`) is restored afterward if the
procedure had switched to extended. Every request, response, and whether
control was returned is recorded (`audit.record("actuate", ...)` and an
`actuator_test` observation), and the report says so per step.

## What cannot be done here

- **SecurityAccess-gated procedures.** If a module demanded `0x27` before
  the actuator test, that test cannot be replayed by cuore at all — use MES
  or wiTECH, which hold the real key algorithm.
- **Calibrations and long-running adaptations** that write configuration
  (`0x2E`), reflash (`0x34`-`0x37`), or write memory (`0x3D`) — these are
  never actuator tests in the sense this feature covers, and are excluded
  from the allowlist entirely.
- **PROXI** (the security gateway / immobiliser boundary) is not touched by
  this feature at all; nothing here attempts to cross it.
- **Safety-critical modules**: ABS, EPS, ORC, HALF, DASM, ESL/NBS, TVM, and
  anything on CAN-CH — brakes, airbag, steering, torque vectoring — are
  refused outright. Run those tests in MultiEcuScan or wiTECH, with a human
  watching the car.

## API summary

```
ops.learn_actuator(capture_name, module, name, tool="MES") -> saved entry
ops.actuators(vin="") -> {"actuators": {vin: [{module, name, tool, source,
                          learned_at, kind, replayable, reasons,
                          requires_security_access}, ...]}}
ops.run_actuator(vin, module, name, consent, max_seconds=10.0, confirm=False)
    -> {"ecu", "name", "bus", "steps": [...], "control_returned",
        "session_restored", "duration_s"}

GET  /api/live/actuators?vin=...        # list only -- no run route over HTTP

MCP: learn_actuator(capture, module, name, tool="MES")
     list_actuators(vin="")
     run_actuator(module, name, consent, vin="", max_seconds=10.0, confirm=False)
```
