# Load-step voltage test, 2026-10-23: results

2018 Stelvio 2.0T, VIN ZASFAKPN5J7B88115. Procedure and method:
`docs/maintenance/LOAD_STEP_VOLTAGE_TEST.md`. Label convention: **fact** = a CUORE
reading; **inference** = reasoned from facts, to be confirmed with a multimeter.

## Run

- Recording `live_load-step-voltage_20261023-005518.csv` (+ `.json` sidecar), 00:55:18 to
  00:58:19, complete, not aborted. Raw copy: `data/captures/stelvio-2018/scans/2026-10-23_load_step/`.
- Conditions (**fact**, declared by the owner): vLinker plugged straight into the OBD socket
  (cable 'none', main bus), ignition on, engine idling, charger off. `POST /api/live/verify`
  on can_c verified before the run (24 frames 29-bit, 206 frames 11-bit); adapter 14.4 V.
- An earlier recording, `live_load-step-voltage_20261023-005308.csv`, was started by the owner at
  00:53:08 and aborted after 3 s (adapter had no vehicle power, `ATRV` read `--.-V`). It is
  **excluded from the analysis**.
- Rate (**fact**): 284 rows in 180 s = 1.59 Hz per channel (median interval 0.62 s; all three
  channels in each row). The 50 Hz request is "as fast as the adapter loop turns"; the loop turned at 1.6 Hz.
  That gives 10 to 11 samples per 10 s window, 8 to 9 in the 6 s reference.
- The script as run is 10 s ON then 10 s OFF per load (not 20 s steps), then 20 s all loads, then 20 s recovery.

## Per-step table

Mean and min over each ON window with the first 3 s skipped (settle). Baseline = the 20 s
BASELINE tag (29 samples): ATRV mean 14.397 / min 14.3, ECM PID 42 mean 14.282 / min 14.250,
BCM 1004 mean 14.431 / min 14.4. Drop = baseline mean minus step mean. Differential =
module drop minus ATRV drop. All in volts.

| Step | n | ATRV mean/min (drop) | ECM mean/min (drop) | BCM mean/min (drop) | ECM diff | BCM diff |
|---|---|---|---|---|---|---|
| Headlights | 11 | 14.400/14.4 (-0.003) | 14.301/14.250 (-0.019) | 14.427/14.4 (0.004) | -0.016 | 0.007 |
| High beam | 10 | 14.390/14.3 (0.007) | 14.287/14.250 (-0.005) | 14.430/14.4 (0.001) | -0.012 | -0.006 |
| Rear defrost | 10 | 14.400/14.4 (-0.003) | 14.293/14.250 (-0.011) | 14.420/14.4 (0.011) | -0.008 | 0.014 |
| Blower MAX | 11 | 13.827/13.7 (0.570) | 13.670/13.500 (0.612) | 13.845/13.7 (0.586) | 0.042 | 0.016 |
| Heated seats | 11 | 14.300/14.2 (0.097) | 14.153/14.125 (0.129) | 14.364/14.3 (0.067) | 0.032 | -0.030 |
| Brake pedal | 11 | 14.282/14.2 (0.115) | 14.119/14.062 (0.163) | 14.300/14.3 (0.131) | 0.048 | 0.016 |
| ALL together | 27 | 13.919/13.5 (0.478) | 13.840/13.312 (0.442) | 13.959/13.5 (0.472) | -0.036 | -0.006 |

CUORE's own analysis (`/api/live/load-step/analysis`, medians, 6 s reference) agrees: no
flagged step, ECM max excess 0.062 V, BCM max excess 0.1 V (one count of the BCM's 0.1 V resolution).
Saved as `analysis.json` beside the raw files. Recovery (last 20 s): ATRV mean 14.234, ECM 14.109, BCM 14.275.

## Observations (fact)

- Only the blower produced a clear sag: about 0.57 to 0.61 V on all three channels together.
  Low beam, high beam and rear defrost produced no sag at all (the alternator held the bus).
- Constant offsets at baseline: ECM reads about 0.115 V below ATRV; BCM about 0.034 V above.
- Largest module-minus-adapter differential in any step: 0.048 V (ECM, brake pedal). The
  0.3 V screening limit was never approached. No step flagged.

## Verdict (inference)

No sign of extra resistance in the ECM or BCM supply/ground paths **under these loads**: both
modules moved with the adapter within 0.05 V, with the BCM within one 0.1 V count.
This lowers the odds that the ECM or BCM feed or ground explains BCM B101D-15 or the
ABS 10.6 V freeze frame; it does not rule out other modules or other conditions.

## Limits

- 1.6 Hz and 10 s windows: 8 to 11 samples each. A sag shorter than about 1 s would be missed.
- Only one load (blower) drew enough current to move the bus. The headlight, defrost and
  seat steps cannot discriminate (the adapter itself did not drop), so they say nothing about resistance.
- BCM resolution 0.1 V; formula `A/10` still unverified beyond one agreeing pair.
- Only the ECM (PID 42) and BCM were compared. TCM (read 0.25 V below ECM on 2026-10-23 at
  idle, fact) was not recorded; ABS, IPC, DASM not measured.
- The adapter reads at the OBD port: a fault in the DLC feed or ground pins would shrink the
  adapter's drop and could hide a module fault.
- Engine running with a charging alternator, so absolute drops are regulator-influenced.
- Not a multimeter measurement. Next if pursued: the voltage-drop procedure in
  `docs/maintenance/GROUND_VOLTAGE_DROP_TEST.md` on the TCM and the ABS feeds, with a heavier load.
