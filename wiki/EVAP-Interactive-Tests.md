# EVAP Interactive Tests

Added 2026-10-23. The reference car's EVAP codes (P0440, P0455, P0456) persist after the ESIM was replaced (see [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]). Passive reads of the ECM's monitor results are done; this page covers tests that exercise the EVAP system and watch the response. **Fact** means a CUORE reading or a cited source; **inference** means reasoned from facts.

## Purge-trim test (now)

A 4-minute, read-only recording at warm idle. The ECM opens the purge valve on its own; CUORE records commanded purge (PID 2E), short and long fuel trim (06/07), RPM, MAP, load, coolant, fuel level and ambient, and then compares the trims with purge off and on.

- Run it at `/v/ZASFAKPN5J7B88115/purge-trim` (routes `/api/live/purge-trim/{start,stop,status,analysis}`). Procedure, thresholds and result wording: `docs/maintenance/PURGE_TRIM_TEST.md`.
- **Fact:** the ECM supports PID 2E and 2F (supported-PID capture 2026-10-23). It has no EVAP vapour-pressure PID; the FCA ESIM system has no pressure sensor.
- **Inference:** when the canister holds vapour and the purge path flows, opening the valve pulls short-term trim negative. A dip of 3 % or more at steady RPM and MAP is reported as a response. No dip is **not** proof of a dead purge path; an empty canister behaves the same.
- If PID 2E never leaves 0 % the result is "ECM did not command purge in this window ... inconclusive".
- Status: built and checked on synthetic data (`cuore/tests/check_purge_trim.py`); **not yet run on the car**.

## ESIM switch probe (planned)

An external, read-only probe on the ESIM's switch lines to log whether and when the ECM actually closes the switch during its EVAP test, with the PIDs above as context. Nothing is connected to the OBD port for this. Not part of this commit's test; status: planned.

## Confirmed-actuation mode (planned)

A mode in which an actuator command is sent and its effect confirmed from readings before moving on. It would need the repository's actuation safeguards and explicit owner approval per command, and is not available: CUORE is read-only on the car today. Status: planned.

## Dealer SLVT comparison

The dealer's Small Leak Verification Test (bulletin 18-048-23) is run through wiTECH, which commands the ECM to run the leak test; the bulletin gives no numeric limits in the copy CUORE holds. CUORE's read-only replica waits for the ECM's own monitor and reads the outcome (Mode 01 readiness, Mode 06, DTC status). The purge-trim test does not replace the SLVT: it checks the purge side only, and a clean purge response says nothing about a small leak at the ESIM seal. Compare results by reading the same Mode 06 values (TID 0x87 and 0x90) before and after any repair.

Related: [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]], [[ESIM Bench Test|ESIM-Bench-Test]], [[Safety Rules|Safety-Rules]].
