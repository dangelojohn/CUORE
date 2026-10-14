# 07 - The first live session (runbook)

This is the acceptance test for four things at once, on the Stelvio
(VIN `ZASFAKPN5J7B88115`), with the ELM327 adapter on COM3:

1. **Live board** (`/v/{vin}/liveboard`, gauges at `/v/{vin}/gauges`) -- can it
   show real channel values from the car, not a replay or demo source?
2. **Systems live overlay** (`/v/{vin}/systems`, backed by
   `GET /api/systems/{vin}/live`) -- does a live reading grade a system, and
   does a new code surface once, not twice?
3. **Tests surface** (`/v/{vin}/tests`) -- can Test A's result be recorded
   against the EVAP job?
4. **The EVAP verdict itself** -- does a real readiness read move this car
   from `CLEARED_UNVERIFIED`/`UNVERIFIED REPAIR` to `VERIFIED_CLEAN` /
   "verified clean", or does it stay unverified?

This is a runbook for the mechanic to follow in order. It assumes cuore is
already running (`start-cuore.ps1`) and the obd2-mcp server is attached to
this session. All MCP tool names below are obd2-mcp's own (see
`obd2-mcp/server.py`); the HTTP paths cuore serves alongside them are noted
for reference only -- you call the MCP tools, not the HTTP routes directly.

## 0. Preconditions -- check every one before touching the car

| Precondition | How to check | Why it matters |
|---|---|---|
| Fuel level 15-85% | dash gauge, or `read_pid("fuel_level")` once connected | Outside this window the EVAP monitor will not run this drive cycle -- see `docs/vehicles/ZASFAKPN5J7B88115/CASE.md` step 5. A readiness read taken outside the window still *reads*, it just will not show the monitor complete. |
| Battery steady, engine able to run | visual/dash check | Low voltage resets modules mid-session and corrupts the readiness story. |
| Adapter is the ELM327/STN on COM3 | `list_ports()` -- confirm COM3 is listed and not flagged as MES's own interface | Wrong port means every read below silently targets nothing or times out. |
| MultiEcuScan is **not** holding the port | `mes_state()` -- `state` must be `not_running` or `disconnected`, never `connected` | The interlock (`cuore/live/interlock.py`) refuses to open the adapter while MES's own status label says `Connected`/`Connecting`. Close MES or disconnect it first. |
| cuore is running and reachable | browser at the bench URL, or `GET /api/health` returns 200 | The Live board, Systems page and Tests surface are all served by cuore; obd2-mcp's HTTP fallback (`_via`) also needs it for anything routed through the API rather than in-process. |
| No stale adapter lock from a previous session | `status()` -- `lock` should be absent, or `audit_log(5)` shows the last session closed cleanly | A leftover lock (crash, kill -9) blocks `connect()` until it is cleared; see the troubleshooting table. |

Do **not** clear any codes before Test A is run and recorded (see Safety,
below). Clearing destroys the very evidence Test A and the verdict need.

## 1. The fast path: `full_scan()`, then Test A

Run **`full_scan(vin="ZASFAKPN5J7B88115")`** once. It performs the whole
read-only capture in section 2 below in a single call -- verify, VIN, every
DTC status plus freeze frame for every PID the car actually supports,
readiness, Mode 06, a Mode 01 snapshot, and a UDS sweep (DTCs, identity, a
short known-DID list) on every bus the declared cable reaches -- and
records every reading as an observation through
`cuore.live.store.record_observation`, so the Scans area, the dossier and
the health report all see it without the manual calls below. Its result is
a coverage summary: which bus/module answered, which was silent, and which
was not reachable and why (`"needs grey A6 cable"`, `"no known address: run
discovery"`, an NRC, ...). Check that summary before trusting anything
else: a module marked `not_reachable` for a fixable reason (wrong cable,
needs discovery) is worth a second pass first.

After `full_scan()`:
- Drive or idle through the fuel window (step 11 in section 2), then call
  `read_readiness()` again and compare -- `full_scan()` is a one-shot
  baseline, not a monitor; there is no substitute for the second readiness
  read.
- Run **Test A** (step 15 in section 2) with wiTECH or MultiEcuScan --
  `full_scan()` does not run actuator tests.
- `read_fullscan_last()` returns the same coverage summary again without
  re-running the scan, if you need to recheck it later in the session.

`full_scan()` refuses outright (no partial scan, nothing recorded) while
MultiEcuScan holds the port, or a live-data poll session (step 8 in section
2) is running -- stop the poller (`live_session_stop()`) or disconnect MES
first, same as every call below.

## 2. The manual sequence (fallback)

Use this when `full_scan()` cannot run (MES needs the port for something
else, or one step needs to be repeated or inspected on its own) -- it is
the same reads, one call at a time, in the same order `full_scan()` runs
them.

Each step names the tool, what it proves, and which cuore page should show
the result afterward.

1. **`list_ports()`**
   Confirms COM3 exists and is not MES's configured interface.
   *Shows nowhere yet* -- this is a pre-flight check only.

2. **`connect(port="COM3")`**
   Opens the serial link, runs the adapter init string, reads adapter
   identity (ELM327/STN) and resets verification state.
   *Shows on:* `status()` afterward reports a resolved port/baud and an
   adapter identity string.

3. **`status()`**
   Confirms port, baud, MES state, lock state, declared cable and bus
   verification right after connect. Re-run this any time something looks
   wrong -- it never holds the port.

4. **`read_vin()`**
   Mode 09 PID 02. Confirms the car answering is the Stelvio
   (`ZASFAKPN5J7B88115`), not a different vehicle on the bench.
   *Shows on:* nowhere directly, but every later call in cuore's dossier is
   keyed by this VIN -- a mismatch here invalidates everything that follows.

5. **`read_dtcs()`** then **`read_pending_dtcs()`** then
   **`read_permanent_dtcs()`**
   Mode 03/07/0A. Baseline: what is active, pending, and permanent *right
   now*, before anything else touches the car.
   *Shows on:* Systems page (`/v/{vin}/systems`) once the live overlay call
   below runs; the dossier's code table on the vehicle page.

6. **`read_freeze_frame()`**
   Mode 02. Captures the freeze frame for whichever DTC set it (empty
   `pid` argument reads the triggering DTC's own frame). Confirms the
   stored freeze frame (fuel %, RPM, load at the fault) still matches what
   the dossier already has from MES logs, or adds a fresh one if the fault
   is still active.

7. **`read_readiness()`**
   Mode 01 PID 01, decoded into "since clear" and "this drive cycle"
   monitor completion, plus an EVAP-specific verdict sentence
   (`cuore.live.obd.evap_verdict`). **This is the one read the whole
   acceptance test hinges on.** Run it now for a baseline, and again later
   (step 11) after driving in the fuel window.
   *Shows on:* the readiness panel feeding `systems_map_bridge.system_states`
   -- a from-car readiness read is what can promote the EVAP system from
   `CLEARED_UNVERIFIED` to `VERIFIED_CLEAN`. The Tests surface
   (`/v/{vin}/tests`) is where you record that Test A itself passed; the
   verdict comes from readiness, not from the Tests page.

8. **`live_session_start(preset="evap_job")`** (or name the channels you
   want: `engine_rpm`, `fuel_level`, `engine_coolant_temp`, the EVAP PID,
   etc. -- see `live_channels()` for the full registry and presets)
   Starts the round-robin poller. From this point the adapter is held
   until you stop it -- every other per-call read (`read_pid`,
   `scan_modules`, `read_module_dtcs`, etc.) will be refused with
   `Refused: a live-data poll session is running and holds the adapter`
   until you call `live_session_stop()`.
   *Shows on:* Live board / gauges page goes from "not connected" /
   "demo"/"replay" labels to live values ticking; Systems page's live
   overlay (`GET /api/systems/{vin}/live`) starts returning `active: true`
   with per-system grades instead of `none`.

9. **`live_channels()`** (if you have not already, to pick channels/preset)
   Lists every Mode 01 PID, catalogued UDS DID, computed channel and
   preset. Use this to build the channel list for step 8 if you are not
   using a canned preset.

10. **`live_snapshot()`**
    Polled repeatedly (or watched live on the Live board / gauges page),
    this is the latest value and alarm state of every channel in the
    running session. Use it to confirm the fuel-level channel sits in the
    15-85% window before you trust a readiness read as monitor-eligible,
    and to watch for any alarm-level channel before continuing.

11. **Drive, or idle through, the window needed for the EVAP monitor to
    run** (per `CASE.md`: fuel 15-85%, cold start helps), then call
    **`read_readiness()`** again. Compare against the step-7 baseline:
    did the Evaporative system monitor go from incomplete to complete
    since the last clear, with no EVAP code returning?

12. **Snapshot the moment** -- save evidence at these points specifically:
    - **Right after step 7** (pre-drive readiness baseline).
    - **At any alarm or unexpected value** during the live session (step
      10) -- snapshot immediately, do not wait for the drive to finish.
    - **Right after the second `read_readiness()` in step 11** -- this is
      the snapshot that either proves or fails to prove the repair.
    Use cuore's own snapshot capability on the Live board (saves a
    freeze-frame of the current widget values, distinct from the OBD
    Mode 02 freeze frame in step 6) so the evidence is timestamped and
    retrievable later, not just scrollback.

13. **`verify_repair(codes="P0455,P0456,P0440", module="ECM")`**
    After the drive and the second readiness read: this reads the ECM's
    UDS status byte for each of the three EVAP codes and reports, per
    code, whether it is failing / failed since clear / not run since
    clear / passed since clear, with an overall verdict and the full
    timeline of every earlier real read (including the MES-logged ones
    already in the dossier). This is the authoritative call for "did the
    repair actually hold."
    *Shows on:* the vehicle dossier's verdict line and the EVAP job card on
    the Tests surface / jobs view.

14. **`live_session_stop()`**
    Always stop the session when done -- releases the adapter so MES,
    wiTECH, or another cuore call can use it. Do this even if something
    went wrong; do not leave the session running overnight.

15. **Record Test A's own result** on the Tests surface
    (`/v/{vin}/tests`, `POST /v/{vin}/tests/{test_id}/result`): vacuum on
    the ESIM while watching the ECU's switch reading, per
    `docs/vehicles/ZASFAKPN5J7B88115/pdf/Stelvio wiTECH Test A - ESIM
    Switch.pdf` (one-page version also available). Test A is run with
    wiTECH or MultiEcuScan, not through obd2-mcp -- obd2-mcp has no
    actuator procedure learned for the ESIM switch on this car. Record
    the pass/fail here regardless of which tool ran it, so the Tests
    surface and the dossier agree.

## 3. Pass criteria

**"Verified clean"** requires ALL of:

- `read_readiness()` (or the readiness panel it feeds) shows the
  Evaporative system monitor **complete** since the last clear, from a
  real serial read (`cuore.live.store.is_from_car` -- stream starts with
  `serial` or `recording(serial`, never `demo`/`replay`/`simulated`).
- No EVAP code (P0455, P0456, P0440) returns on the subsequent
  `read_dtcs()` / `read_pending_dtcs()` / `verify_repair()` call.
- `verify_repair()` reports each of the three codes as "passed since
  clear," not "not run since clear" or "failed since clear."
- The drive/idle period covered fuel 15-85% (confirm from
  `live_snapshot()`'s fuel_level channel or the freeze frame at the time
  of the readiness read).
- Systems page shows the EVAP-mapped system as `VERIFIED_CLEAN`, which
  `systems_map_bridge.system_states` only produces when the readiness read
  is from-car AND the monitors for that system are all complete.

**"Still unverified"** is everything else, specifically:
- Readiness read taken outside the fuel window, or before the monitor has
  had a chance to run -- `evap_verdict()` itself will say the reading
  "carries no information" if the monitor has not run.
- A readiness read exists but is from a demo/replay/simulated source --
  `is_from_car` is false, so the Systems page keeps the system at
  `CLEARED_UNVERIFIED`, never `VERIFIED_CLEAN`, no matter what the
  monitor bits say.
- Any EVAP code returns, however briefly, during or after the drive.
- `verify_repair()` cannot find a "passed since clear" state for one or
  more of the three codes.

This matches the dossier's own computed states (`cuore/live/ops.py`,
`systems_map_bridge.py`): clearing a code is never the same as fixing it;
only a from-car readiness read with the relevant monitor complete can move
a system from `CLEARED_UNVERIFIED` to `VERIFIED_CLEAN`.

## 4. Test A procedure reference

Primary procedure: `docs/vehicles/ZASFAKPN5J7B88115/pdf/Stelvio wiTECH Test
A - ESIM Switch.pdf` (full version) or `...Test A - ESIM Switch (1
page).pdf` (quick-reference). If Test A fails, follow with the wiring test:
`docs/vehicles/ZASFAKPN5J7B88115/pdf/Stelvio ESIM Wiring Test (1
page).pdf`. Background and the full diagnostic story (why Test A is the
next step after three clean smoke tests and all-new EVAP parts) is in
`docs/vehicles/ZASFAKPN5J7B88115/CASE.md`.

## 5. Safety

- **No clears before Test A runs and is recorded.** `clear_module_dtcs()`
  and `clear_dtcs()` are DESTRUCTIVE TO EVIDENCE -- they erase the exact
  codes, snapshots and counters that prove whether a repair worked. Test A
  must be run and its result recorded on the Tests surface first. Clearing
  afterward is fine and expected (it starts the "unverified repair" clock
  that the next readiness read closes).
- **Exact consent phrases are required for anything that writes to the
  car**, and none of them are offered by this runbook's steps 1-15 above
  (which are all reads): `CLEAR <MODULE>` (e.g. `CLEAR ECM`) for
  `clear_module_dtcs`; `ACTUATE <MODULE> <NAME>` (e.g. `ACTUATE ECM
  EVAPORATION CONTROL VALVE`) or `RUN ROUTINE <MODULE> <NAME>` for
  `run_actuator`. Typos or paraphrases are refused, not auto-corrected.
- **Blocked modules** -- `run_actuator` and similar writes refuse outright
  on safety-critical modules: ABS, EPS, ORC, HALF, DASM, ESL, TVM, TCM,
  ESM, DTCM, RFHUB, and anything on the CAN-CH bus. Use MultiEcuScan or
  wiTECH for those, never a replay through obd2-mcp.
- **No HTTP route ever writes to the car.** Clears, actuator tests and
  routines are MCP-tool-only by design (no corresponding `POST` write
  route in cuore's API) so that a browser tab or a stray HTTP client can
  never trigger one by accident.
- `run_actuator` additionally refuses unless the vehicle reads engine-off
  and stationary, and always attempts to hand control back to the ECU
  afterward even if a step fails -- read `outcome`, `control_returned`
  and `session_restored` in its result; if either flag is false, switch
  the ignition off immediately.

## 6. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `list_ports()` does not list COM3 at all | Adapter not plugged in, wrong cable, or Windows assigned a different COM number this time | Check Device Manager for the actual port; re-run `list_ports()`; use the port it actually shows, not a remembered one. |
| `connect()` succeeds but every read times out / "NO DATA" | Bus silent -- wrong bus selected, ignition off, or a dead cable segment | Confirm ignition is on (engine need not be running for most reads); check `buses()` and `verify_bus(bus="can_c")` for passive traffic; try `set_cable()` if the wrong cable profile is declared. |
| `connect()` / any read raises `Refused`/`LinkUnavailable` mentioning MultiEcuScan | MES is holding the port -- `mes_state()` shows `state: "connected"` | Close MES or disconnect its session; re-check `mes_state()` until it reads `not_running` or `disconnected`, then retry. |
| Any per-call read (`read_pid`, `scan_modules`, etc.) raises `Refused: a live-data poll session is running and holds the adapter` | The poller (step 8) is still running and holds the one adapter session; this is the poller refusing a write/read while it holds the port, exactly as designed | Call `live_session_stop()` first, then retry the read; or use `live_snapshot()` instead of a per-call read while the session is active. |
| `connect()` fails citing a stale adapter lock | A previous cuore/obd2-mcp process crashed without releasing `cuore/live/interlock.py`'s lock file | `status()` or `audit_log()` to confirm the lock's PID is dead; the lock is advisory and self-heals once the dead PID is detected, but if it does not, the lock file path is reported in the error -- remove it only after confirming the PID is not a live process. |
| Readiness read looks fine but the Systems page still shows `CLEARED_UNVERIFIED`, not `VERIFIED_CLEAN` | The read was not actually from the car (demo/replay/simulated stream), or the monitor the system needs is not among the ones reported complete | Re-run `read_readiness()` live, with the adapter connected to the real car, and confirm the result's `at` timestamp is recent and the source stream starts with `serial`. |
| Live board / gauges page shows values but they never change | Session may be using a replay recording instead of the live poller, or the channel's rate is slower than you are watching | Confirm which session is active via `status()`/`live_snapshot()` HTTP equivalents; check the channel's configured rate in `live_channels()`. |
