# MES-learn first real session: runbook

Goal: learn the ESIM commanded vent test (ECM) from MES, passively, once. CUORE
only listens. Related: `CUORE_WRITE_CAPABILITY_PLAN.md` (Stage 1),
`cuore/live/procedure_capture.py` (review + gate), `cuore/live/actuate.py`
(replay rules). Lesson that shapes every step: on 2026-10-14 one passive listen
at the wrong bitrate on CAN-CH set the airbag lamp (note 82b3090e1a85).

## Hardware

- Second OBD adapter (its own COM port, not COM3 if COM3 is MES's or the
  current CUORE adapter; `mes_learn_start` refuses the same adapter MES uses).
- Y-splitter at the OBD port, CAN-C only: pins 6 (CAN-H) and 14 (CAN-L).
  Adapter 1 -> MES. Adapter 2 -> CUORE listener. Nothing else on the port.
- Battery maintainer on the car (stable voltage for the whole session).
- Confirm CUORE's own first adapter is disconnected from the car, so exactly
  two devices are on the splitter: MES's and the listen-only one.

## Before starting (record these in the job)

1. Engine state and battery voltage (read by CUORE's own adapter before it is
   unplugged, or from the dash). These become the gate's `pre` conditions.
2. Fuel level 15-85 percent (MES prerequisite for the ESIM test).
3. EVAP proof state untouched: no code clearing, ever (job 76d3454bce75).
4. Bitrate: CAN-C is 500000, confirmed. The listener is opened on CAN-C only.

## Steps

1. Start MES on its adapter. Connect to the ECM. Do not start any test yet.
2. `obd2.mes_learn_start(port=<second adapter COM>, vin=...)`. Check
   `mes_learn_status`: frame count rising, no error. If it shows an error or
   zero frames after a few seconds, stop and abort (do not retry other rates).
3. In MES: Engine -> ECM -> Actuators -> ESIM / purge solenoid vent command.
   Run it ONCE, let MES finish and release it. Note the clock time and what MES
   showed (switch state, vacuum built).
4. `mes_learn_stop`. Record the post state (engine state, voltage).
5. Review: feed the saved frames to `procedure_capture.review(frames)` and read
   `report["text"]`: module, ordered services, any 0x27, any write/reset/reflash,
   whether `actuate.py` would allow replay.
6. Gate: `procedure_capture.gate(module_entry, listen_bitrate=500000, pre=...,
   post=..., name="ESIM vent test")`. A pass returns the consent phrase
   (`ACTUATE ECM ESIM VENT TEST`). A fail lists the reasons; that procedure is
   not offered. Do not edit the capture to make it pass.
7. Only after a pass: save through `actuate.save_actuator`, and dry-run against
   the simulator/test client before any live replay. Live replay is a separate,
   later decision.

## What to record

Capture frames (raw), review text, gate result with reasons, pre/post engine
state and voltage, fuel level, MES version, clock times, any lamp or code seen.
Label every value as read vs. reported (readings only; outside facts are not
proof).

## What NOT to do

- No transmitting from the second adapter. It stays passive (`STCMM 0`).
- Never a wrong bitrate. CAN-C 500000 only; never CAN-CH or CAN-IHS here.
- Abort at once if ANY warning lamp appears (airbag, MIL, ABS): stop the
  listener, disconnect adapter 2, read codes with MES only, note it.
- Never clear the EVAP proof codes, before or after.
- Do not run more than one MES test in the capture window; mixed sequences are
  hard to review.
- Do not replay anything the gate failed, and do not treat a synthetic fixture
  (tests) as a real procedure.
- Do not go beyond the ECM; safety-critical modules are blocked by the gate.

## Known gaps to fix before or during this session

- `mes_learn.stop` only aligns DIDs to a CSV; it does not call
  `procedure_capture.review`. Feed `state["frames"]` to it by hand for now.
- `run_actuator` requires engine off and stationary, but MES lists the ESIM
  test as needing the engine running. The learned test may therefore not be
  replayable under today's interlock. Decide that before promising a replay.
