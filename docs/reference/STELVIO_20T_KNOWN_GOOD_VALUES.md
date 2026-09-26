# 2018 Alfa Romeo Stelvio 2.0T — Live-Channel Known-Good Values

VIN ZASFAKPN5J7B88115. 2.0L GME-T4 MultiAir turbo (sales code EC2), US
market, Q4 AWD, ZF 8HP automatic.

This is the human-readable companion to `mes-log-mcp/mes/known_good.py`,
which is what the live-dashboard gauges (`cuore/live/layouts.py`, via
`cuore/services/known_good_bridge.py`) and the `GET /api/live/known-good`
endpoint actually read. The two must agree — this file exists so a person
can review the sourcing without reading Python. Channel ids are exactly
those in `cuore/live/channels.py`.

**Confidence levels** (same meaning as `mes.service_specs`, never invented —
an absent value is recorded as UNKNOWN, never guessed):

- **CONFIRMED** — an actual manufacturer document.
- **CORROBORATED** — two independent non-manufacturer sources agree.
- **SINGLE-SOURCE** — exactly one source found, not cross-checked.
- **UNKNOWN** — nothing credible found. Use the service manual
  (TechAuthority). Never a guess presented as a number.

**Generic** marks a value that is a well-established OBD-II/SAE/physics/
lead-acid-battery norm, not a Stelvio-specific figure — allowed by
instruction, kept clearly separate from a manufacturer spec.

Research pass done 2026-09-26: web search against stelvioforum.com,
giuliaforums.com and generic repair/physics references, the 2018 Stelvio US
[owner's manual](https://vehicleinfo.mopar.com/assets/publications/en-us/Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf),
and this repo's `docs/reference/ZF8HP_SERVICE_DATA.md`. Two stelvioforum
threads redirected through a bot-gate (`tollbit.stelvioforum.com`) that
could not be resolved during this pass — those rows are read via the search
engine's own summary of the thread, not the full text, same precedent as
`service_specs.TORQUES['caliper_slider_rear']`. No paywalled/bot-gated FCA
TechAuthority document was reached.

## Engine basics

| Channel | Name | Band (normal / warn / alarm) | Confidence | Source | Notes |
|---|---|---|---|---|---|
| `engine_rpm` | Engine RPM | 700-900 / 600-1050 / 400-1300 rpm | SINGLE-SOURCE | [stelvioforum idle thread](https://www.stelvioforum.com/threads/correct-idle-speed-and-service-alarm.18670/) | No factory hot-idle figure found; synthesized from forum reports (~800 rpm). Read via search-engine summary only (bot-gated thread). |
| `engine_coolant_temp` | Coolant temp | 88-105 / 105-115 / 115-130 °C | SINGLE-SOURCE | [stelvioforum coolant thread](https://www.stelvioforum.com/threads/coolant-operating-temperature-2-0-engine.17855/) | Read via search-engine summary only. **Caveat**: this platform's dash gauge is reported to read oil temp, not coolant — the PID here is the legislated coolant sensor regardless. |
| `intake_air_temp` | IAT | — | UNKNOWN | — | No fixed band is meaningful — tracks ambient + heat soak. Use `observed_ranges()`. |
| `throttle_position` | Throttle position | 0-100% (no warn/alarm) | CORROBORATED (generic) | [OBD-II PIDs](https://en.wikipedia.org/wiki/OBD-II_PIDs) | The PID's defined range, not a health band — there's no "abnormal" throttle position on its own. |
| `absolute_load` | Calculated load | 0-100% (no warn/alarm) | CORROBORATED (generic) | [OBD-II PIDs](https://en.wikipedia.org/wiki/OBD-II_PIDs) | Same treatment as throttle position. |

## Boost / turbo

| Channel | Name | Band | Confidence | Source | Notes |
|---|---|---|---|---|---|
| `intake_map` | MAP | 20-35 / 15-45 / 0-60 kPa abs | SINGLE-SOURCE (generic) | [engineerskill.blog](https://engineerskill.blog/map-sensor-reading-at-idle) | Idle-only, naturally-aspirated-idle-vacuum regime (turbo unspooled at idle); not valid under boost. Also varies with barometric pressure/altitude. |
| `barometric_pressure` | Barometric pressure | 95-105 / 90-108 / 80-115 kPa | CORROBORATED (generic) | [Atmospheric pressure](https://en.wikipedia.org/wiki/Atmospheric_pressure) | Physics reference; a reading far outside this at low elevation flags a sensor fault, not weather. |
| `boost` (computed) | Boost (MAP − baro) | — | **UNKNOWN** | — | No credible peak-boost figure found. One search result mixed a ~22 psi OBD2-readable ceiling, a claimed ~25 psi actual peak, and a ~2.5 bar turbo hardware rating that reads as an upgrade-turbo capability — not corroborating each other, not adopted. |
| `ecm_195a` | Boost pressure (ECM DID 0x195A) | — | UNKNOWN | — | DID formula itself UNVERIFIED on this 2.0T (danardi78, diesel-confirmed only). No peak figure to compare against either. |

## Fuel trims / O2

| Channel | Name | Band | Confidence | Source | Notes |
|---|---|---|---|---|---|
| `short_fuel_trim_b1` / `long_fuel_trim_b1` | Fuel trim, bank 1 | ±10 / ±15 / ±20 % | CORROBORATED (generic) | [obd-codes.com](https://www.obd-codes.com/faq/fuel-trims.php) | Requires closed loop, warm engine. |
| `short_fuel_trim_b2` / `long_fuel_trim_b2` | Fuel trim, bank 2 | same as bank 1 | CORROBORATED (generic) | same | **Caveat**: this engine is an inline-4, single exhaust bank — a static/zero Bank 2 reading may mean "not applicable," not a fault. Confirm before treating a deviation as meaningful. |
| `o2_b1s1_voltage` | O2 sensor B1S1 voltage | 0.1-0.9 V (no warn/alarm) | CORROBORATED (generic) | [Fluke](https://www.fluke.com/en-us/learn/blog/digital-multimeters/how-to-monitor-oxygen-sensor-voltage-with-a-multimeter) | Diagnostic signature is a value that *stops switching*, not a single-instant threshold — no warn/alarm band is set deliberately. |

## Electrical

| Channel | Name | Band | Confidence | Source | Notes |
|---|---|---|---|---|---|
| `battery_voltage` | Battery voltage | 13.5-14.7 / 12.0-15.0 / 11.0-15.5 V (engine running) | CORROBORATED (generic) | [Firestone](https://www.firestonecompleteautocare.com/blog/batteries/car-battery-voltage/) | Engine-off resting spec (not the widget band): ~12.2-12.8 V healthy, <12.0 V discharged. Do not compare a running reading against the resting band or vice versa. No FCA-specific figure found. |
| `fuel_level` | Fuel level | 0-100% (no warn/alarm) | CORROBORATED (generic) | [OBD-II PIDs](https://en.wikipedia.org/wiki/OBD-II_PIDs) | Tank level, not a health check; included because EVAP vapor-pressure interpretation depends on it. |

## EVAP (P0440 / P0455 / P0456 job)

| Channel | Name | Band | Confidence | Source | Notes |
|---|---|---|---|---|---|
| `commanded_evap_purge` | Commanded EVAP purge duty | — | **UNKNOWN** | — | No OEM/corroborated figure found anywhere in this or the `service_specs.py`/`did_catalog.py` research passes. |
| `evap_vapor_pressure` | EVAP vapor pressure | — | **UNKNOWN** | — | Same. |
| `evap_vapor_pressure_abs` | EVAP vapor pressure, absolute | — | **UNKNOWN** | — | Same. |

This is the single most important gap this module documents: exactly the
channels that matter for this car's chronic P0440/P0455/P0456 diagnosis
have no published spec anywhere. `mes.known_good.observed_ranges()` exists
so this car's own logged behaviour can stand in as a baseline until a
TechAuthority figure is obtained.

## Transmission (ZF 8HP)

| Channel | Name | Band | Confidence | Source | Notes |
|---|---|---|---|---|---|
| `tcm_04fe` | Gearbox fluid temp | 80-100 / 100-120 / 120-150 °C (driving) | SINGLE-SOURCE (generic) | [dodgedurango.net (ZF tech support quote)](https://www.dodgedurango.net/threads/normal-zf-transmission-operating-temp-for-2019-gt.89031/) | Not the CONFIRMED 30-50 °C **fill-check** window in `ZF8HP_SERVICE_DATA.md`/`service_specs.transmission_fill_plug` — that's a static service temperature, not a driving range. DID formula (`A-40`) itself UNVERIFIED on this TCM. |

## Tyres (TPMS via RFHUB)

| Channel | Name | Band | Confidence | Source | Notes |
|---|---|---|---|---|---|
| `rfhub_40b{1-4}_pressure` | Tire pressure, FL/FR/RL/RR | — | **UNKNOWN** | — | **Must be read from this VIN's own door-jamb placard.** One SINGLE-SOURCE, 19"-fitment-only figure exists (`service_specs.BRAKE_SPEC['tire_pressure_kpa']`: front 207 kPa/30 psi, rear 228 kPa/33 psi) but is not confirmed against this VIN's actual wheel option or a manufacturer placard image (image-based PDF, no extractable text) — kept UNKNOWN rather than treated as a spec. |
| `rfhub_40b{1-4}_temp` | Tire temperature, FL/FR/RL/RR | — | UNKNOWN | — | No fixed placard-style spec exists; compare corner-to-corner instead of against an absolute number. |

All four RFHUB DID formulas (pressure/temp) are themselves UNVERIFIED
(danardi78 catalog).

## `observed_ranges(vin)`: this car's own logged behaviour

`mes.known_good.observed_ranges(vin)` pools every non-simulated FES session
log for `vin` (via `mes.catalog`/`mes.fes`) plus every CSV graph recording
found on this install (`mes.csvlog`; recordings carry no VIN of their own,
so they're pooled in regardless — fine on this single-car install), matches
parameter/column names against a small alias table by loose substring, and
reports `{n, unit, min, p10, p50, p90, max, sources}` per channel using
linear-interpolation percentiles (`mes.params.ParamSeries` supplies the
typed values both log kinds are read through). **This is never a spec** —
label any number from here "observed on this car."

Sanity-checked during this build against the real corpus for
`ZASFAKPN5J7B88115`: `engine_rpm` observed 742-759 rpm (median 750),
`engine_coolant_temp` 89-96 °C, `intake_air_temp` 30-33 °C,
`barometric_pressure` 990-991 mbar (~99.0-99.1 kPa), `throttle_position`
1.57-1.96%, `battery_voltage` 14.0-14.1 V, `fuel_level` 84.7% — all
consistent with the sourced bands above, which is a reasonable amount of
cross-validation for figures that were largely forum-sourced.

## Gaps

- **EVAP purge duty and vapor pressure have no published spec anywhere.**
  This is the channel group that matters most for the P0440/P0455/P0456
  diagnosis and is exactly why `observed_ranges()` was built the way it
  was. Getting a real CSV recording of a purge test on this car (see
  `project_mes_toolchain` — no real CSV export has been captured yet) would
  turn this from UNKNOWN into at least an observed baseline.
- **Peak boost is UNKNOWN.** Forum research produced numbers that don't
  corroborate each other; do not set a boost alarm from any of them.
  `ecm_195a`'s own DID formula is also unverified on this ECU.
- **Two source threads (idle RPM, coolant temp) were read via search-engine
  summary only**, not the full thread — both redirected to a bot-gate
  (`tollbit.<site>`) unreachable during this pass. Re-fetch and verify if
  the summary language ever looks inconsistent with what the widget shows.
- **Tyre pressure is deliberately UNKNOWN** despite one sourced figure
  existing, because that figure's fitment (19") isn't confirmed to match
  this VIN and it never traced to a readable manufacturer placard. Read the
  physical door-jamb placard.
- **`o2_b1s1_voltage` has no `observed_ranges()` mapping.** This car's FES
  logs name lambda-system parameters ("Lambda control", "Lambda sensor N
  integrator", "Lambda 1 signal (Pre/After-Cat.)") rather than a plain
  "oxygen sensor voltage" column; a trial alias match pulled in a
  fuel-trim-like integrator value (~1.0, dimensionless) instead of a 0-1 V
  signal, so the mapping was deliberately left out rather than mislabel a
  different quantity as this channel.
- **A pre-existing display bug in `cuore/live/channels.py`** (out of scope
  for this change — that file is owned by other work): the RFHUB tire DIDs
  expand into one channel per field (`rfhub_40b1_pressure`,
  `rfhub_40b1_temp`, ...) but each field channel's `unit` is copied from the
  DID spec's *combined* unit string (`"bar, °C"`) rather than split per
  field. `mes.known_good`'s own `unit` values for these channels
  (`"bar"`/`"C"`) are correct regardless — they're independent of the
  registry's `Channel.unit` field.
- **CSV recordings carry no VIN tag** (`mes.csvlog`), so
  `observed_ranges()` pools every CSV recording found on the install
  regardless of the `vin` argument. Fine for a single-car rig; would need a
  VIN-tagging convention on export before this toolchain sees a second car.
- **Battery voltage bands the "engine running" case**, since that's what a
  live gauge on a running car dashboard mostly shows; the engine-off resting
  spec (12.2-12.8 V) lives only in the row's `notes`, not as a separate
  band — the schema has one band per channel, not one per operating state.
