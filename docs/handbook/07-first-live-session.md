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

### Guided scan with the coloured cables

`full_scan()` needs the mechanic to physically fit two bypass cables mid-
scan -- the blue A5 for CAN-IHS, the grey A6 for CAN-CH -- which used to
mean stopping the tool and running three separate scans by hand. The guided
scan turns that into one resumable session that pauses exactly when a
cable swap is needed, instead of stopping:

1. **`guided_scan_start(vin="ZASFAKPN5J7B88115")`** (or the wizard page,
   `/v/{vin}/scan`, "Start full scan") runs the no-cable segment in full
   (verify CAN-C, VIN, DTCs, freeze frames, readiness, Mode 06, PID
   snapshot, and the UDS sweep of every CAN-C module) under one `scan_id`,
   then pauses. Its result's `next` field says which cable to fit
   (`blue_a5`), which bus it unlocks (`can_ihs`), and the modules on it.
2. Fit the blue A5 cable, then **`guided_scan_continue(scan_id,
   cable_fitted="blue_a5")`** -- declares the cable (the same
   `set_cable()` path, a declaration only; writes stay blocked), verifies
   CAN-IHS with a passive listen, sweeps its modules, and pauses again for
   the grey A6 cable (`can_ch`).
3. No grey A6 cable on hand? **`guided_scan_skip(scan_id)`** records that
   segment as `"not reachable: skipped, needs grey A6 cable"` -- honest,
   never invented -- and moves on to the closing step.
4. Fit the grey A6 cable and repeat step 2 for `cable_fitted="grey_a6"`, or
   skip it the same way.
5. Remove the cable, then **`guided_scan_continue(scan_id,
   cable_fitted="none")`** redeclares no cable, re-verifies CAN-C, and
   closes the session.

`guided_scan_state()` (or reloading the wizard page) shows exactly where a
session is at any point -- it persists to disk, so a page reload or an MCP
reconnect resumes the same session rather than losing it. Every segment
records under the one `scan_id` picked at step 1, and the coverage summary
is rewritten at the end of every segment, so the Scans area and the health
report always see one scan, not three. `abandon_guided(scan_id)` (API only;
the wizard page's "Abandon this scan" button) closes a session honestly
without pretending it finished.

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
- **A person must approve anything that writes to the car** on the
  `/approve` page, and none of it is offered by this runbook's steps 1-15
  above (which are all reads). A write tool (`clear_module_dtcs`,
  `run_actuator`) is refused and returns a request link; the person opens
  it, reads what will be sent, and approves that one exact action. The
  caller cannot approve for itself (docs/design/CONSENT_GATE.md).
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

## 7. Bus capture, learn-a-signal and per-bus presets (blue A5 / grey A6)

The garage has two bypass cables: the **blue A5** re-pins the adapter onto
CAN-IHS (pins 3/11 -- body/comfort/infotainment); the **grey A6** re-pins
it onto CAN-CH (pins 12/13 -- chassis/ADAS: ABS, EPS, ORC...). Both coloured
cables re-pin their bus onto the adapter's HS pins, so the adapter's HS/MS
switch stays on HS whenever a cable is fitted; MS is only for the
cable-less MS-CAN route. Everything
below is read-only (passive listen, `STCMM 0` + `STM`/`ATMA`) -- the
existing write guards for ABS/EPS/ORC and anything on CAN-CH are untouched
and still refuse without explicit confirmation.

**Declare the cable first.** Fit the cable, then `set_cable("blue_a5")` or
`set_cable("grey_a6")` (MCP tool, or the Live board's "Change cable"
control at `/v/{vin}/liveboard`, which also lists what the new declaration
enables before you confirm). Every bus-capture and learn call below
refuses with `Refused` if the bus it targets is not reachable with the
currently declared cable, or if the poller/MultiEcuScan holds the adapter.

**Bus capture** -- the Live board's "Bus capture" panel (same Start/Stop/
Save shape as the Freeze frame panel above it): pick the bus the fitted
cable reaches, Start, watch the live frame rate and distinct-ID count,
Stop, then Save. Save writes a CSV recording in the same wire format
cuore's own live sessions use, named `buscapture_<bus>_<cable>_<time>.csv`
under the recordings directory, and logs a from-car observation (kind
`"bus_capture"`) carrying the recording path and id counts. The MCP tools
are `bus_capture_start(bus)`, `bus_capture_stop(bus)`,
`bus_capture_save(bus, vin=...)`.

**Learn a signal** -- `/v/{vin}/learn`: pick the bus, name the physical
action you're about to do (the page suggests a few per bus -- "press the
brake pedal", "turn the wheel", "open the driver door", "switch the HVAC
fan"), Start, hold the action for a few seconds, Stop. The page ranks
every `(CAN id, byte offset)` by how much it changed during that window
and lets you name the best candidate and save it. A saved signal is
logged with `scale: "unknown"` -- nothing here ever guesses a physical
unit from one capture -- and shows on the Live board as a raw channel
labelled "learned, unscaled". The MCP tools are `learn_start(bus,
action)` and `learn_stop(bus)`; naming and saving the chosen candidate is
a page action (`POST /api/buscapture/{bus}/learn/accept`), not an MCP
tool.

**Per-bus presets** -- `chassis_a6` (CAN-CH: ABS wheel speeds, steering
angle, yaw rate) and `body_a5` (CAN-IHS: HVAC temperature, battery
monitor, door states) list only what a public broadcast-signal source
(`cuore.live.did_catalog.BROADCAST_SIGNALS`) or this VIN's own learned
signals actually cover; anything else is shown `unknown_did` and is never
polled or implied to exist (brake pressure, for example, has no known
broadcast signal or DID on this platform and always shows `unknown_did`
in `chassis_a6`). The Live board shows each preset's required cable and
refuses to start it (`Refused`) without that cable declared.

<!-- cable-reference:start (generated by docs/handbook/generate_cable_reference.py -- do not hand-edit between these markers; re-run the script instead) -->

## 8. Which cable for which module

Generated straight from the live module registry (`cuore/live/buses.py` + `cuore.live.ops.modules()`) by `docs/handbook/generate_cable_reference.py` -- never hand-typed. This is the same table the Full scan wizard (`/v/{vin}/scan`) shows on its idle screen and on every pause card, so the page and this section can never disagree with each other or with the registry both are drawn from. Re-run the script after any change to `addressing.py` or `buses.py`.

### Blue A5 (CAN-IHS) -- adapter switch: HS

| Module | Confidence |
|---|---|
| HVAC | unverified |
| IHS62 | confirmed |
| IHS65 | confirmed |
| AMP | unknown |
| ESEM | unknown |
| CSWM | unknown |
| CRSM | unknown |
| LBSS | unknown |
| RBSS | unknown |
| PLGM | unknown |

### Grey A6 (CAN-CH) -- adapter switch: HS

| Module | Confidence |
|---|---|
| ABS | confirmed |
| EPS | unknown |
| ORC | unverified |
| AFLS | unknown |
| PAM | unknown |
| HALF | unknown |
| TVM | unknown |
| ESL | unknown |

### witech_splitter (CAN-C) -- adapter switch: HS

| Module | Confidence |
|---|---|
| ECM | confirmed |
| TCM | confirmed |
| BCM | confirmed |
| IPC | confirmed |
| RFHUB | confirmed |
| DTCM | unknown |
| ESM | unknown |
| DASM | unknown |
| ETM | unverified |

<!-- cable-reference:end -->







## 9. Learning module parameters from MES (a second adapter on CAN-C)

Section 7 learns an *unscaled* broadcast signal from a bypass cable by
watching what changed while you held a physical action. This is different:
it learns a *scaled* module DID -- a named channel with a real unit, not
"learned, unscaled" -- by overhearing MultiEcuScan's own UDS traffic on
CAN-C while MES graphs and records a parameter you already trust MES to
decode correctly. Nothing here replaces or edits a catalogue DID
(`cuore.live.did_catalog`); every entry it produces is stamped confidence
`SINGLE-SOURCE (learned)` and kept in its own store.

### Hardware

- **A Y-splitter on the OBD-II port**, wired to CAN-C (pins 6/14) so two
  adapters can read the same bus at once.
- **A second adapter**, on its *own* COM port, different from MES's own
  interface port: another STN/vLinker, or a USB-CAN interface. This is the
  one requirement the software cannot work around -- `mes_learn_start`
  refuses outright, naming exactly this, if only one adapter is detected at
  all, or if the port given is the same one MES is configured to use
  (`Interface 0 Port` in MES's own settings).
- MultiEcuScan, running its normal live view against its own adapter on its
  own port, recording a CSV (MES's graph subsystem, up to 4 graphs of 10
  parameters each -- see `docs/format/CSV_LOG_FORMAT.md`).

### Procedure

1. Fit the splitter and the second adapter; note its COM port (`list_ports()`
   marks MES's own interface so you can tell them apart).
2. `mes_learn_start(port="COM<n>")` (or the "Second adapter's port" field at
   `/v/{vin}/learn-mes`). This opens the second adapter **passively**
   (`STCMM 0`, receive-only, same as every other passive listen in this
   project -- see `cuore.live.capture.listen`): it never acknowledges a
   frame and never transmits a byte of its own onto the bus.
3. In MES, start the live view/graph for the parameters you want decoded,
   and record a CSV. Let it run long enough that each parameter you care
   about actually moves through at least 20 distinct values -- a channel
   that never leaves one value, or only ever takes a handful of discrete
   states (a 9-position gear indicator, say), cannot be fitted with
   confidence and is reported as such, not guessed.
4. `mes_learn_stop(csv="<the CSV MES just wrote>")` (bare filename, or a
   full path). This reassembles ISO-TP, pairs every UDS request/response
   the second adapter overheard (`cuore.live.learn.uds_transactions` --
   29-bit `18DAxxF1`/`18DAF1xx` and the 11-bit pair alike), groups by
   `(module, DID)`, and fits each named CSV column against every
   `(module, DID, byte offset, width, signedness)` seen, by ordinary least
   squares over the whole session.
5. `mes_learn_candidates()` (or the candidates table at `/v/{vin}/
   learn-mes`) lists the result: a confident fit (R² >= 0.98 over >= 20
   distinct raw values) per column, with its module, DID, field, scale,
   offset and R²; anything short of that bar is listed `"no confident
   match"` rather than a guessed scale.
6. Review each candidate against what MES labelled that column, then
   **Accept** (saves it through `cuore.live.learned.accept_mes` with source
   `"learned from MES <csv name> <date>, fit R² <value>"` -- immediately
   usable by the Live board as a named, scaled channel, the same hand-off
   `cuore.live.ui_store.load_custom_channels` already uses for custom
   channels) or **Reject** (kept observed-but-unscaled, never guessed, same
   posture as rejecting a Section 7 broadcast candidate).

The MCP tools are `mes_learn_start(port, vin="")`, `mes_learn_stop(csv="")`,
`mes_learn_status()`, `mes_learn_candidates()` and `mes_learn_accept
(candidate_id, vin, name)`; rejecting a candidate is a page/API action
(`POST /api/mes-learn/candidates/{id}/reject`), not an MCP tool, same split
as Section 7's learn-accept.
