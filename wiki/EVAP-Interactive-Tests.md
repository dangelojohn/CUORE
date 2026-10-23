# EVAP Interactive Tests

Added 2026-10-23. The reference car's EVAP codes (P0440, P0455, P0456) persist after the ESIM was replaced (see [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]). Passive reads of the ECM's monitor results are done; this page covers tests that exercise the EVAP system and watch the response. **Fact** means a CUORE reading or a cited source; **inference** means reasoned from facts.

## Purge-trim test (now)

A 4-minute, read-only recording at warm idle. The ECM opens the purge valve on its own; CUORE records commanded purge (PID 2E), short and long fuel trim (06/07), RPM, MAP, load, coolant, fuel level and ambient, and then compares the trims with purge off and on.

- Run it at `/v/ZASFAKPN5J7B88115/purge-trim` (routes `/api/live/purge-trim/{start,stop,status,analysis}`). Procedure, thresholds and result wording: `docs/maintenance/PURGE_TRIM_TEST.md`.
- **Fact:** the ECM supports PID 2E and 2F (supported-PID capture 2026-10-23). It has no EVAP vapour-pressure PID; the FCA ESIM system has no pressure sensor.
- **Inference:** when the canister holds vapour and the purge path flows, opening the valve pulls short-term trim negative. A dip of 3 % or more at steady RPM and MAP is reported as a response. No dip is **not** proof of a dead purge path; an empty canister behaves the same.
- If PID 2E never leaves 0 % the result is "ECM did not command purge in this window ... inconclusive".
- Status: built and checked on synthetic data (`cuore/tests/check_purge_trim.py`); **not yet run on the car**.

## ESIM switch probe (spec and software built, hardware not built)

An external, read-only meter on the ESIM switch lines, logged at 20 Hz next to the PIDs, to see whether and when the ECM's EVAP test closes the switch. Nothing is connected to the OBD port for the probe. Full spec: `docs/hardware/ESIM_SWITCH_PROBE.md`.

- **Hardware (design only):** a high-impedance tap (2.6 Mohm input per line, 100 kohm series protection, optional USB isolation) on the switch signal and the 5 V reference, read by a small ESP32-C3 or Nano-class board over USB serial. Line protocol `ESIM,<ms>,<sig_mV>,<ref_mV>,<state>` at 115200 baud. State: CLOSED when the signal is under 0.8 V with the reference over 4.5 V, OPEN when the signal is over 4.0 V, FAULT otherwise (open reference, wiring).
- **Facts about the part are outside literature** (switch closes near 1 inH2O vacuum, 5 V reference pulled to about 0 V; `mes/parts.py`), not readings from this car. **The connector pin numbers and wire colours are not in the repo:** the owner confirms the signal, reference and ground pins at the connector with a meter (ground by ohms to chassis with ignition off; reference by about 5 V with ignition on; signal is the pin that falls to about 0 V under gentle hand vacuum), and writes them on the ESIM Wiring Test sheet. A two-wire switch has no separate reference; `CUORE_ESIM_PROBE_NO_REF=1` then selects the matching state rule.
- **Safety:** tap only, never feed voltage into an ECM line, back-probe at the connector, no splice without the owner's OK, leads away from the exhaust, powered from USB only, never on COM3.
- **Software (checked on a simulator only):** `cuore/live/esim_probe.py` reads the port named in `CUORE_ESIM_PROBE_PORT` (read-only; COM3 and the OBD adapter's port are refused) and exposes `esim_switch_state` (1 CLOSED, 0 OPEN, -1 FAULT), `esim_signal_mV` and `esim_ref_mV` as `probe` channels on the live board. `CUORE_ESIM_PROBE_PORT=sim` replays a scripted open / closed / bounce / fault trace so the board and recordings work with no hardware; a probe-only session needs no OBD adapter. Checks: `cuore/tests/check_esim_probe.py`.
- **Recording preset `esim-switch-watch`:** the three probe channels plus PID 2E (purge), 06 (short-term trim), 0C (RPM), 0D (speed) and 2F (fuel level), for a drive cycle. Rows are written at the probe rate, and every state change is tagged (`ESIM CLOSED`, `ESIM OPEN`, `ESIM FAULT`).
- **Bench validation before fitting:** meter calibration, state rules with a resistor stand-in, then the real ESIM on the bench following the [[ESIM Bench Test|ESIM-Bench-Test]] (gentle blowing; no hand pump and no 12 V), then the host chain with `sim`.
- **Reading a drive (inference):** no CLOSED during the monitor window while purge is commanded means no closure reached the connector (vacuum not arriving, or the switch not closing); CLOSED that holds and releases while the code still sets moves the question to what the ECM did with it. The probe sees the connector, not the ECM's input.
- Status: **not built, not fitted, not run on the car.** CUORE needs a restart to load the new channels, and the environment variable only applies to a process started after it is set.

## Confirmed-actuation mode (planned)

A mode in which an actuator command is sent and its effect confirmed from readings before moving on. It would need the repository's actuation safeguards and explicit owner approval per command, and is not available: CUORE is read-only on the car today. Status: planned.

## Dealer SLVT comparison

The dealer's Small Leak Verification Test (bulletin 18-048-23) is run through wiTECH, which commands the ECM to run the leak test; the bulletin gives no numeric limits in the copy CUORE holds. CUORE's read-only replica waits for the ECM's own monitor and reads the outcome (Mode 01 readiness, Mode 06, DTC status). The purge-trim test does not replace the SLVT: it checks the purge side only, and a clean purge response says nothing about a small leak at the ESIM seal. Compare results by reading the same Mode 06 values (TID 0x87 and 0x90) before and after any repair.

Related: [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]], [[ESIM Bench Test|ESIM-Bench-Test]], [[Safety Rules|Safety-Rules]].
