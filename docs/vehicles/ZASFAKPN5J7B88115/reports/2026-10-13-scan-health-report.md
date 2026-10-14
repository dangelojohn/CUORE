# Scan health report — 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115

As of 2026-10-13 20:04, read live from the car (serial COM3, vLinker FS r2 / STN1170, 29-bit legislated OBD; ECM 18DAF110, TCM 18DAF118). Engine idling, 752–778 rpm, coolant 101 °C, 14.1 V at the port. Odometer about 142 290 km. Source files: `sessions/2026-10-13-live-read.json`, observation store (from-car). Confidence grades: CONFIRMED (manufacturer document), CORROBORATED (two sources), SINGLE-SOURCE, UNKNOWN (use the service manual, TechAuthority). Nothing below is invented; where a Stelvio specification is not on file the reading is reported without a verdict.

## Verdict

**ACTIVE FAULT — EVAP.** MIL on. Stored P0440; pending P0440 + P0455; permanent P0440 + P0456. Every readiness monitor has completed since the 29 Sep clear (1 663 km, 8 warm-ups), so the EVAP monitor has run with fuel in its window and the code came back: this is no longer "unverified repair", it is a live fault with a measured failure behind it (below). Everything else the ECM measures passes.

## System by system

| System | Reading | Band / spec | Health |
|---|---|---|---|
| EVAP | Mode 06: gross-leak test PASS; **0.090" large-leak test FAIL, 404 ms vs ≥ 3 965 ms**; 0.020" small-leak TID 90 FAIL 6 096 vs ≤ 6 000 (1.6 % over); purge-flow tests PASS (168 in 57–328). Freeze frame: purge commanded 18 %, fuel 28.6 %, 217 s after start, ECT 63 °C, idle 778 rpm | ECM's own limits (CONFIRMED, read from the car) | **FAULT** |
| Fuel & air (closed loop) | Frame: STFT +3.1 %, LTFT −2.3 %, λ 1.007. Hot idle: STFT +3.1 %, LTFT −5.5 %, λ 1.007, MAF 3.24 g/s, MAP 31 kPa at baro 98 kPa (≈ 67 kPa idle vacuum), load 19.6 % | Trims ±10 % (CORROBORATED). Idle MAF/MAP for the GME 2.0T: UNKNOWN | OK — trims inside band, strong idle vacuum, no sign of an intake leak |
| Ignition / misfire | Mode 06 misfire counters 0–1 per cylinder, all PASS. Timing +5° at hot idle, −4.5° in the cold frame (catalyst-heating retard, SINGLE-SOURCE engineering practice) | ECM limits (CONFIRMED) | OK |
| Catalyst | MID 21: 5 700 vs ≥ 1 764 — PASS, 3.2× margin | ECM limit (CONFIRMED) | OK |
| Oxygen sensors | MID 02 all PASS: downstream 913 mV, response 592 / 320 ms within limits; MID 41/42 PASS | ECM limits (CONFIRMED) | OK |
| VVT / MultiAir | MID 35: all 12 tests PASS | ECM limits (CONFIRMED) | OK |
| EGR (as reported by the ECM) | MID 31 PASS | ECM limits (CONFIRMED) | OK |
| Cooling | 101 °C at idle after 30 min; ambient 25 °C (sensor), 17 °C in the frame | Hot-idle target for this engine: UNKNOWN | Reading only — plausible for a hot idle; confirm fan cycling and the manual's target |
| Charging / electrical | 14.0 V module voltage, 14.1 V at the port, idle | 13.5–14.7 V (CORROBORATED) | OK |
| Turbo / boost | Not exercised at idle (MAP 48 kPa at 13 % throttle in the frame) | — | Not assessed |
| Transmission (TCM 18DAF118) | Answers; no emissions codes (Mode 03/07/0A empty) | — | No OBD fault; UDS module read not done |
| Engine oil | PID 5C not supported by this ECM; IAT (0F) gave no data in this read | — | UNKNOWN — re-read IAT; oil temp needs a UDS DID |
| Body / chassis / network | Not read tonight (UDS module scan not run); B1176 and the 28 Sep network event unchecked | — | GAP |

## What the EVAP measurement tells us

The ECM declares a large leak when its switch (ESIM) does not report the system sealed within the test time. Tonight it held for **0.4 s where ≥ 4 s is required**, with purge commanded at 18 % during a warm-up idle. Three smoke tests already found the system physically sealed and every EVAP part is new. The two explanations left are exactly the two on the hypothesis ledger: the ESIM switch / its signal path never reporting "sealed", or the ECM calibration (TSB 18-030-17 REV. B). The marginal 0.020" result (6 096 vs 6 000) is consistent with the permanent P0456 and does not change that picture.

## Issues to address, in order

1. **Test A now** (hand vacuum on the ESIM while watching the switch PID) — it separates "switch never closes" from "ECM never sees it". Do not clear codes before it.
2. **wiTECH flash comparison** against TSB 18-030-17 REV. B; recalls 25V586000 and 18V636000 by VIN; TSB 21-035-20 (TCM).
3. **Run the UDS module scan** (BCM, gateway, chassis modules) for body/network codes — B1176 (rear-left window riser) and the 28 Sep lost-communication family are unverified tonight.
4. **Re-read IAT (PID 0F)** and take an oil-temperature DID; both came back empty.
5. Maintenance overdue by the manual (unchanged, service ledger still empty): transfer-case oil, drive belt; air filter and plugs due at 90 k mi; brake fluid 2-year interval.
6. Record this scan's freeze frame and Mode 06 as evidence on the EVAP hypotheses (CUORE now offers them in the picker; the mechanic attaches).

## Clean bill tonight

Fuel control, ignition, catalyst, oxygen sensors, VVT, charging: all pass the ECM's own tests with margin. No misfire history. Idle vacuum strong. The car's problem is one system, and it is now measured, not inferred.
