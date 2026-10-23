# Load-step voltage test (read-only): 2018 Stelvio 2.0T

A 3-minute recording that switches one electrical load at a time and watches
what voltage three different places on the car see. A module that loses more
voltage than the adapter does has extra resistance somewhere between the
battery and itself. Written 2026-10-23. **Not run yet.** Nothing below is a
reading from this car except the two spot values in section 2, which are
labelled.

Label convention: **fact** = a CUORE reading or a cited source;
**inference** = reasoned from facts, to be confirmed with a multimeter
(`GROUND_VOLTAGE_DROP_TEST.md`).

## 1. What it does

Preset `load_step_voltage` (registry: `cuore/live/channels.py`, `PRESETS` and
`RECORDING_PRESETS`; engine: `cuore/live/load_step.py`).

| Channel id | What it is | How it is read | Resolution |
|---|---|---|---|
| `battery_voltage` | Adapter voltage at the OBD port (pins 16/4/5) | `ATRV` | 0.1 V |
| `control_module_voltage` | ECM's own supply measurement | Mode 01 PID 42 (the first ECU to answer = ECM) | 0.001 V |
| `bcm_1004` | BCM "Battery voltage" | UDS `22 1004`, formula `A/10` (registry confidence: unverified) | 0.1 V |

Why `bcm_1004` is trusted enough to use: **fact**, on 2026-10-23 00:11 the BCM
returned byte `0x91` = 14.5 V while `ATRV` read 14.5 V (raw capture
`data/captures/stelvio-2018/scans/2026-10-23_SCAN_2610230010/raw/51_B5_did_BCM_1004.json`
and `07_A1_adapter_voltage_ATRV_before.json`). One agreeing pair, not a
calibration; the test will show whether it tracks.

Not included on purpose: `ecm_1955` (also called "Battery voltage" in the
registry) answered `requestOutOfRange` on this car the same night, so it
cannot be polled. Other registry voltages (`o2_b1s1_voltage`,
`ecm_195b` boost sensor raw voltage) are sensor signals, not supply
voltages. PID 42 is also answered by the TCM (14.062 V vs ECM 14.312 V at
idle on 2026-10-23, **fact**); the poller keeps only the first reply, so the
TCM is not recorded. A per-ECU PID channel would be a small follow-up.

Rate: every channel is requested at 50 Hz. The poller has no upper clamp, only
a 0.02 s idle tick, so this means "as fast as the adapter loop turns"; the
achieved rate per channel is shown on the test page and in
`/api/live/session`. The analysis works on timestamps, so uneven sampling is
fine. Duration 180 s. Every CSV row carries the current script step in its TAG
column, and a `.json` sidecar next to the CSV stores the script and column order.

Read-only: ATRV, Mode 01 and UDS 0x22 only (the same services as any live
session). It holds the adapter for the 3 minutes, so do not run another
CUORE/MES/AlfaOBD session at the same time.

## 2. Why this test

**Fact** (CUORE and MES readings): ABS `U1700-87` was logged with a freeze frame
of **10.6 V** on 2026-09-04 (FESLog_2609042001). BCM `B101D-15` (battery voltage
circuit: short to battery or open) is set as of 2026-10-23. Tonight's PID 42
shows the TCM about 0.25 V below the ECM at idle. The failure-type map
(`GET /api/wiring`, electrical page) has no -11 / -14 / -16 code for any module.

**Inference**: these are consistent with, but do not prove, a resistive feed or
ground. The test separates "the whole car sags" (adapter drops too) from "one
module sags more" (resistance in that module's own path).

## 3. Owner script (on screen at `/v/ZASFAKPN5J7B88115/load-step`)

Before you start: engine **idling**, battery charger / maintainer
**disconnected**, car outdoors or ventilated, handbrake on, in P, every load
off, A/C setting left alone for the whole test. Press **Start 3-minute test**.

| Time | Step |
|---|---|
| 0:00 - 0:20 | Baseline. Touch nothing. |
| 0:20 - 0:30 | Headlights ON (low beam), then 0:30 - 0:40 OFF |
| 0:40 - 0:50 | High beam ON, then 0:50 - 1:00 OFF |
| 1:00 - 1:10 | Rear defrost ON, then 1:10 - 1:20 OFF |
| 1:20 - 1:30 | Blower MAX ON, then 1:30 - 1:40 OFF |
| 1:40 - 1:50 | Both heated seats HIGH, then 1:50 - 2:00 OFF |
| 2:00 - 2:10 | Brake pedal pressed and HELD, then 2:10 - 2:20 released |
| 2:20 - 2:40 | ALL together: headlights + rear defrost + blower MAX + heated seats |
| 2:40 - 3:00 | Everything OFF (recovery). Recording stops by itself at 3:00. |

The page shows the current step, the next one with a countdown, and live
values; the phone vibrates at each change. Stop early with **Stop**.

## 4. How it is started (API)

- `GET /api/live/load-step`: preset, script, which channels exist in the registry.
- `POST /api/live/load-step/start` with `{"label": "before-ground-clean"}`:
  starts the poll session and a recording named
  `live_load-step-voltage_<label>_<timestamp>.csv` in the CUORE recordings
  folder (`%PROGRAMDATA%\cuore\recordings`), tags rows by step, stops itself at 180 s.
- `GET /api/live/load-step/status`: elapsed (the recorder's own clock), step,
  seconds left, live values, achieved rates.
- `POST /api/live/load-step/stop`
- `GET /api/live/load-step/analysis[?recording=<file name>]`: the analysis below
  (newest recording by default).

The server must be restarted once to load this code (nothing is started by import).

## 5. Analysis (what the numbers mean)

For each ON step: **drop** = median of the channel in the 6 s before the load
went on minus its median from 3 s after switch-on to the end of the step (the
3 s settle is skipped). For each module channel:

    excess = module drop - adapter drop

A step is **flagged** when `excess > 0.3 V`. A module is reported as a
pattern when 2 or more steps are flagged; one flagged step says "repeat it".

Meaning (**inference**): the adapter's drop is what the battery and the
wiring up to the OBD port lost; any additional drop a module sees is
voltage lost between the common supply and that module: a resistive feed
(fuse, connector, splice) or a resistive ground (G-point, strap, ring
terminal). Limits come from general automotive voltage-drop practice, which is
not Alfa-specific: about 0.2 V or less on a ground side, about 0.3 V on a
positive side, 0.2 - 0.5 V total
([Fluke, starter-circuit voltage drop](https://www.fluke.com/en-us/learn/blog/digital-multimeters/how-to-check-starter-circuit-voltage-drop-with-a-multimeter);
other published tables differ slightly, e.g. 0.1 V per connection, so
treat 0.3 V as a screening threshold, not a pass/fail spec). Use the
manufacturer's figures from the service information if the dealer gives any.

Caveats built into the output:
- the alternator regulator reacts to load, so absolute drops can be near zero or
  negative; only the difference to the adapter is used;
- BCM resolution is 0.1 V, so one count is a third of the limit;
- the adapter reads at the OBD connector: a fault in the DLC ground/feed pins
  would make the adapter drop LESS than modules and masquerade as a module fault;
- only 6.5 s of data per ON window.

A flagged module is a lead, not a verdict: take it to the multimeter
voltage-drop procedure (`GROUND_VOLTAGE_DROP_TEST.md`) and record the result as
a measurement against the hypothesis.

## 6. Recording the result in CUORE

Add a job action (kind `test`) with a `ref` of `{"kind": "measurement", ...}`;
use the fields in section 6 of `GROUND_VOLTAGE_DROP_TEST.md` (what, when, values,
meaning, next test). Reference the recording file name in the text.
