# MES vs. CUORE: what each can access/modify/service, and what closes the gap

**Date:** 2026-10-14. **Scope:** Alfa Romeo Giulia/Stelvio 2.0T (Giorgio
platform, GME engine family) -- the platform this repo's own knowledge
tables (`mes.mechanic_tests`, `mes.known_good`, `mes.systems`) are built
for. **Method:** multiecuscan.net's own supported-vehicle listing and
support forum, owner-community writeups (giuliaforums.com,
stelvioforum.com, giuliatech.com, alfaowner.com, mhhauto.com), and a
read-only pass over the local install at
`C:\Program Files (x86)\MultiEcuScan` -- its `Lang\English.txt` UI string
table (534 entries, the same source `MES_CAPABILITY_GAPS.md`'s 2026-08-27
pass used) and its own FES session logs. The ECU database itself is
encrypted and was not touched, per standing instruction.

This doc answers one question: **where is MES the better tool today, where
is CUORE, and for every MES-only function, what is the safe way to close
the gap** -- read it into CUORE when a sourced DID exists, otherwise hand
the technician to MES (or, twice below, to the car's own menu) with a
clear card, never a silent HTTP write.

The data half of this doc is `mes-log-mcp/mes/mes_functions.py` -- every
row below is generated from that module, so the two can never drift out of
sync. Companion reading: `MES_CAPABILITY_GAPS.md` (2026-08-27, the inverse
question -- what MES *cannot* do) and `MES_INTEGRATION_SURFACE.md`.

## The three-tier closure rule

1. **Read-side, DID exists** -- wire it into `mes_bridge`/`live_obs` like
  every other channel. Nothing in the table below needs this tier; where
  CUORE is only "partial", the missing half is a channel with no public
  DID (tier 2).
2. **Read-side, no DID** -- "needs DID definition (TechAuthority /
  learn)". CUORE does not invent a PID/DID; it stays honestly partial
  until one is sourced or learned (`obd2.learn_correlate`).
3. **Write-side** (actuator/adjustment/coding) -- CUORE **never** performs
  these over HTTP. The few actuator tests already in
  `mes.mechanic_tests` (e.g. `esim_commanded_vent_test`) are MCP-only,
  gated on the `ACTUATE ECM <name>` consent phrase. Every other write in
  this table has no MCP tool at all today -- for those, the only safe
  path is a **handoff card** (`cuore.services.mes_handoff_bridge`, this
  pass) pointing the technician at MES (or the car's own menu, for the
  one exception below).

## The capability matrix

| id | module | kind | MES | CUORE today | menu path (abridged) | confidence |
|---|---|---|---|---|---|---|
| all_module_scan | ALL (CAN-C/IHS/CH) | read | yes | yes -- cuore.live.fullscan.run over the  | main toolbar -> Scan vehicle (sweeps every module MES has a database entry for, across ... | CONFIRMED |
| module_info_identity | ALL | read | yes | partial -- mes.modules/read_module_ident | each module's own screen -> Info tab (ECU part number, HW/SW version, calibration ID) | CONFIRMED |
| live_parameters | ALL | read | yes | partial -- CUORE's live_obs/channels.py  | each module's own screen -> Parameters tab | CORROBORATED |
| graphs_recording_csv | ALL | read | yes | no -- CUORE has no equivalent graph/reco | Parameters tab -> graph icon, then Record (writes a .csv under MES's configured Export ... | CORROBORATED |
| freeze_frames_per_module | ALL | read | yes | partial -- cuore.live.obd read_freeze_fr | each module's own screen -> DTC EX tab | CONFIRMED |
| esim_commanded_vent_test | Engine/ECM (EVAP) | actuator | yes -- Actuators tab (or wiTEC | no -- MCP-only via obd2.run_actuator wit | Engine -> ECM -> Actuators tab -> ESIM / purge solenoid vent command | CORROBORATED |
| turbo_boost_waste_gate_actuator | Engine/ECM (intake/boost) | actuator | yes | no -- no CUORE actuator route for this c | Engine -> ECM -> Actuators tab -> boost control solenoid / waste-gate | SINGLE-SOURCE |
| zf_gear_shift_actuator | Gearbox/ZF Electronic Gear Shift Module | actuator | yes | no -- no OBD-II DID for this actuator; M | Gearbox -> ZF Electronic Gear Shift Module -> Actuators tab | CONFIRMED |
| proxi_alignment_952 | Body/BCM (CAN Setup) | adjustment | yes | no -- CUORE never writes PROXI/configura | Body -> CAN Setup / PROXI ALIGNMENT PROCEDURE (952) -- Adjustment tab; Ctrl+Alt+C opens... | CORROBORATED |
| oil_change_reset_ecm | Engine/ECM (Magneti Marelli IAW 10JA) | adjustment | yes | no -- write-side, never over HTTP; MCP-o | Engine -> Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0) -> Adjustments tab -> Oil C... | CORROBORATED |
| service_interval_reset | Service module (dash/BCM-side) | adjustment | yes | no -- write-side; MCP-only with consent | Service -> Service Interval Reset -> Adjustments tab -> NEXT SERVICE KM RESET | CORROBORATED |
| battery_type_registration | Body/BCM (CAN Setup, byte 63) | coding | yes | no -- coding write; MCP-only with consen | Body -> CAN Setup -> Adjustments tab -> PROXI byte 63, bits 0-3 (80Ah 680A / 95Ah 800A ... | CORROBORATED |
| ibs_battery_sensor_read | Body/BCM (IBS) | read | yes | no -- no CUORE DID for IBS; this is read | Body -> BCM -> Parameters tab -> IBS group (charge status, SoC, SoH) | SINGLE-SOURCE |
| sas_calibration | Chassis/ABS (Continental MK C1) | adjustment | yes | no -- write-side; MCP-only with consent | ABS -> Continental ABS MK C1 module -> Parameters tab to check 0 deg, then Adjustments ... | SINGLE-SOURCE |
| abs_accel_sensor_calibration | Chassis/ABS (Continental MK C1) | adjustment | yes | no -- write-side; MCP-only with consent | ABS -> Continental ABS MK C1 module -> Adjustments tab -> accel sensor calibration | SINGLE-SOURCE |
| abs_pressure_sensor_calibration | Chassis/ABS (Continental MK C1) | adjustment | yes | no -- write-side; MCP-only with consent | ABS -> Continental ABS MK C1 module -> Adjustments tab -> pressure sensor calibration | SINGLE-SOURCE |
| epb_service_mode | Chassis/EPB | adjustment | no -- native infotainment menu | no | NOT in MES, per owner reports -- Settings -> Driver Assistance -> Brake Service on the ... | CORROBORATED |
| tpms_pressure_threshold | Body/RF Hub | adjustment | yes | no -- write-side; MCP-only with consent | Body -> RFHub -> Adjustments tab -> TPMS pressure threshold (MES >=4.7R3) | SINGLE-SOURCE |
| seat_belt_chime_disable | Dashboard/Instrument Panel | coding | yes | no -- CUORE never performs coding writes | Dashboard -> Instrument Panel -> Adjustments tab -> seat belt chime | SINGLE-SOURCE |
| race_mode_dynamic_control_selector | Body/BCM (CAN Setup) | coding | yes | no -- coding write; MCP-only with consen | Body -> CAN Setup (Dynamic Control Selector) -> Adjustments tab (MES 4.5+) | CORROBORATED |
| acc_cruise_enable | Body/BCM (CAN Setup) | coding | yes | no -- coding write; MCP-only with consen | Body -> CAN Setup -> Adjustments tab -> Cruise Control/ACC settings | SINGLE-SOURCE |
| paddle_shifter_logic | Body/BCM (CAN Setup, byte 156) | coding | yes | no -- coding write; MCP-only with consen | Body -> CAN Setup -> Adjustments tab -> PROXI byte 156, bits 4-5 | SINGLE-SOURCE |
| window_comfort_logic | Body/BCM (CAN Setup, byte 58) | coding | yes | no -- coding write; MCP-only with consen | Body -> CAN Setup -> Adjustments tab -> PROXI byte 58, bit 1 | SINGLE-SOURCE |
| after_wipe_logic | Body/BCM (CAN Setup, byte 126) | coding | yes | no -- coding write; MCP-only with consen | Body -> CAN Setup -> Adjustments tab -> PROXI byte 126, bit 5 | SINGLE-SOURCE |
| cornering_lights_enable | Body/BCM (CAN Setup) | coding | yes | no -- coding write; MCP-only with consen | Body -> CAN Setup -> Adjustments tab -> Cornering Lights option | SINGLE-SOURCE |
| tvm_bcm_etm_coding | Body/TVM, BCM, ETM | coding | yes | no -- coding write; MCP-only with consen | each module's own screen -> Adjustments/Coding tab, per module | SINGLE-SOURCE |
| coil_actuator_test | Engine/ECM (ignition) | actuator | yes | no -- write-side; MCP-only via obd2.run_ | Engine -> ECM -> Actuators tab (string 6001 "Actuators") -> ACTUATES THE COIL (string 6... | CONFIRMED |
| idle_actuator_test | Engine/ECM (throttle/idle) | actuator | yes | no -- write-side; MCP-only with consent | Engine -> ECM -> Actuators tab -> ACTUATES IDLE ACTUATOR (string 6205); TIMING ACTUATOR... | CONFIRMED |
| key_rf_learning | Body/BCM (RF Hub, immobiliser) | adjustment | yes | no -- write-side; MCP-only with consent | Body -> BCM -> Adjustments tab -> key learning procedure (per-prompt: DETECTING KEY, st... | CONFIRMED |
| dpf_regen | Exhaust/DPF | adjustment | n/a | n/a | n/a on the 2.0T GME -- this is a gasoline engine with no diesel particulate filter; MES... | CONFIRMED |
| comfort_bus_module_roster | IHS/CH (Magna Q4 transfer case, TRW steering lock, Bosch HALF camera, Bosch DASM radar, ESEM engine sound, TVM torque vectoring) | read | yes | no -- CUORE's OBD-II link has no path to | main toolbar -> Scan vehicle with an A6 cable (or A5 + MES's IHS/CH adapter) reaches th... | CORROBORATED |

31 functions, every row sourced (see `mes_functions.py` for the full
`source`/`prerequisites`/`record_after` text abridged above). Full detail,
including the gap-closure path per row, lives in that module --
`mes.mes_functions.all_functions()` / `.function(id)`.

## Where MES is better today

- **Per-module parameter scaling for TCM/BCM/ABS.** MES's own database
  carries the named, scaled parameter for modules CUORE has no DID
  table for at all (IHS/CH comfort bus: BCM, RF Hub, ABS-specific
  channels beyond the generic OBD-II PID). This is a database-size
  problem CUORE cannot out-source without the same reverse-engineered
  DID table MES ships.
- **Adjustments, coding, and actuator tests.** Every PROXI byte, service
  reset, calibration and actuator in the matrix above is a live write
  CUORE deliberately never performs over HTTP. MES (or wiTECH, or the
  infotainment menu for the one exception) is simply the right tool for
  these, full stop -- not a gap to close so much as a boundary to respect.
- **Cable/connection guidance.** MES's own prompts (and the forum
  threads sourced above) carry the "which cable, which bus" knowledge
  (A5 vs. A6, the gray ABS-specific cable) that a bare OBD-II link has no
  way to know.
- **IHS/CH comfort-bus reach.** With an A6 cable MES/wiTECH reaches a
  roster of modules (Magna Q4 transfer case, TRW steering lock, Bosch
  HALF/DASM, ESEM, TVM) a CAN-C-only OBD-II link cannot see at all.

## Where CUORE is better today

- **Verdict/evidence gate.** MES shows a code; CUORE's
  `scan_health.verdict` turns stored/pending/permanent/readiness/Mode 06
  into one of four honest states (active fault / verified clean /
  unverified repair / no data) -- MES has no readiness or Mode 06 concept
  at all (`MES_CAPABILITY_GAPS.md`'s own headline finding, corroborated
  again by this pass's string-table read: "Readiness", "EOBD", "Permanent"
  and "Freeze" appear zero times in `Lang\English.txt`).
- **Mode 06 interpretation.** Confirmed absent from MES; CUORE reads it
  directly from the car.
- **Cross-session history and case memory.** `mes.experience`/`mes.cases`
  carry what happened last time, on this car and on sibling cars of the
  same model -- MES has no VIN-keyed service history at all.
- **Hypotheses, reports, mobile, honesty labels.** The job page's
  hypothesis tracking, the dossier's confidence-labelled findings, and a
  phone-sized UI are CUORE's own and have no MES equivalent.

## The one deliberately honest exception

`epb_service_mode` is the one row in this table where **MES is not the
better tool either** -- per owner reports, MES's own "EPB maintenance
mode" menu item does not reliably work; the brake-service retract lives in
the car's own infotainment (Settings -> Driver Assistance -> Brake
Service), and MES's only real role afterward is clearing the resulting
DTC. The handoff card for this one function says so, rather than sending a
technician to hunt for a working MES menu that multiple owners report
does not do what it says.

## What this pass built

1. This doc, and its data half, `mes-log-mcp/mes/mes_functions.py`.
2. `cuore/services/mes_handoff_bridge.py` -- handoff-card lookup
  (`candidates`/`find_for_test`/`find_for_text`/`card`) plus MES log
  import (`import_mes_log`/`list_mes_scans`/`health_line`), additive only
  -- it never touches `cuore.live.scanlog`, `cuore.services.scan_health_bridge`
  or `mes.scan_health`'s own files, only calls their public functions
  (`mes.scan_health.verdict`) and keeps its own small ledger
  (`mes_imports.json`) for MES-sourced scans, clearly tagged
  `source.kind = "MES"` -- never disguised as a live serial read.
3. `cuore/web/templates/_mes_handoff.html`, included once each from
  `tests.html` and `job.html` step 6 -- a client-side script that matches
  the small MES-function catalogue against whatever test rows / checklist
  steps are already on the page and injects a card, with an "Import the
  MES log" action when the function typically produces one. It never adds
  a second result-recording control -- the pass/fail buttons and
  done/outcome checkbox each row already has are reused as-is.
4. Two additive routes in `cuore/api/tests.py`
  (`/tests/mes-handoff/candidates`, `/tests/mes-handoff/by-test/{id}`,
  `/tests/mes-handoff/by-text`, `/tests/{vin}/mes-import`,
  `/tests/{vin}/mes-scans`).
5. `cuore/tests/check_mes_handoff.py`.
