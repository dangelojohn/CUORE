# Purge-trim EVAP test (passive, read-only): 2018 Stelvio 2.0T

A 4-minute recording that watches whether the engine's fuel trims react when
the ECM opens the EVAP purge valve. You do nothing but let the engine idle;
the ECM decides when to purge. Written 2026-10-23. **Not run yet.** Nothing
below is a reading from this car except where a section says so.

Label convention: **fact** = a CUORE reading or a cited source; **inference**
= reasoned from facts, to be confirmed by another test.

## 1. What it does

Preset `purge_trim` (registry: `cuore/live/channels.py`, `PRESETS` and
`RECORDING_PRESETS`; engine: `cuore/live/purge_trim.py`; page
`/v/ZASFAKPN5J7B88115/purge-trim`; routes `/api/live/purge-trim/{start,stop,status,analysis}`).

| Channel id | PID | Rate requested |
|---|---|---|
| `commanded_evap_purge` | 2E | 10 Hz |
| `short_fuel_trim_b1` | 06 | 10 Hz |
| `long_fuel_trim_b1` | 07 | 2 Hz |
| `engine_rpm` | 0C | 10 Hz |
| `intake_map` | 0B | 5 Hz |
| `absolute_load` | 43 | 5 Hz |
| `engine_coolant_temp` | 05 | 0.5 Hz |
| `fuel_level` | 2F | 0.5 Hz |
| `ambient_air_temp` | 46 | 0.2 Hz |

**Fact** (`data/captures/stelvio-2018/live_inputs/2026-10-23/01_supported_pids.json`):
the ECM (18DAF110) lists PID 2E and PID 2F as supported, along with 04, 05,
06, 07, 0B, 0C, 0F, 11, 43 and 46. The achieved rate is whatever the adapter
loop can deliver for that many channels; the analysis works on timestamps.

Differences from the request, with reasons:

* PID 04 (calculated load) is supported by the ECM but `cuore/live/obd.py` has
  no decoder for it, so PID 43 (absolute load, also supported) is recorded as
  the load channel.
* No EVAP vapour-pressure channel: the FCA ESIM system has no pressure sensor,
  and the PID is not supported on this ECM.
* PID 2E is the ECM's **commanded** purge percentage, not measured flow. Nothing
  on this car reports whether gas really flowed.

Read-only: Mode 01 only. No Mode 08, no UDS 0x2F/0x31, no clearing. It holds
the adapter for 4 minutes, so do not run MES, AlfaOBD or another CUORE
session at the same time. Every CSV row carries the step tag; a `.json`
sidecar next to the CSV records the script, column order and thresholds.

## 2. Owner script

Engine idling and **fully warm** (coolant 75 C or more), battery charger
disconnected, parked outdoors or ventilated, handbrake on, car in P, A/C and
all loads off. Press Start, then touch nothing for 4 minutes, in particular not
the throttle. The ECM purges when its own conditions allow.

## 3. What the analysis reports

* Purge **on** = commanded purge at least 1 %; **off** = below 1 %.
* Mean STFT, LTFT, RPM, MAP and load with purge off versus on.
* For every off-to-on transition with at least 3 STFT samples in the 5 s before
  and in the 10 s after: the STFT baseline (median before), the lowest STFT
  after, the dip, the lag, and the RPM and MAP change. An opening counts only
  if RPM moved by 150 or less and MAP by 5 kPa or less. A dip of **3 % or
  more** (negative) on a steady opening is a "response". These thresholds are a
  screening choice, not a published limit.
* If PID 2E is missing from the recording the test degrades to trims only: STFT
  excursions of 3 % or more are listed and nothing is attributed to purge.

### Reading the result

| Result | Wording the tool uses | Meaning |
|---|---|---|
| 2E never reaches 1 % | "ECM did not command purge in this window (conditions not met: warm-up, time since start, fuel level) -- inconclusive" | Not "purge dead". Repeat warmer or later. |
| Purge opened, steady, STFT dips 3 % or more | "INFERENCE: ... consistent with a flowing purge path drawing vapour" | The valve passes vapour/air from a canister that holds fuel. It does **not** test the ESIM seal or the leak monitor. |
| Purge opened, steady, no dip | "consistent with a non-flowing purge path OR with a canister holding little vapour ... (inconclusive)" | A healthy valve with an empty canister gives the same trace. |
| Purge opened but RPM/MAP moved every time | "cannot be attributed to purge -- inconclusive" | Repeat with hands off. |

The interpretation is **inference**. General background on why a purge-fed
vapour load pulls trim negative: https://en.wikipedia.org/wiki/Evaporative_emissions_control
(not Alfa-specific, not a diagnostic procedure).

## 4. Limits

* One passive run depends on the ECM choosing to purge; at warm idle with a
  recent cold start it may not. The ECM's reasons are not readable here.
* A closed-loop state change also moves STFT; the steady-RPM/MAP rule removes
  only the obvious cases.
* Fuel level 46 % and ambient 8 C were read on 2026-10-23 (**fact**, scan
  `SCAN_2610230010`); both are plausible for purge but say nothing about
  canister loading.

## 5. After the run

`GET /api/live/purge-trim/analysis` (or the page button) analyses the newest
`live_purge-trim*.csv` in the CUORE recordings folder. Copy the raw CSV and
sidecar to `data/captures/stelvio-2018/scans/<date>_purge_trim/` and add a note to
the EVAP job. See also the wiki page `EVAP-Interactive-Tests`.
