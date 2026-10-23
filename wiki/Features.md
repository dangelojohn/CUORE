# Features

A tour of the web app, one section per page or route group. `{vin}` is a vehicle identifier: pages live under `/v/{vin}/...`, and the JSON API under `/api` mirrors them. The complete route-by-route list is [docs/FEATURES.md](https://github.com/dangelojohn/CUORE/blob/main/docs/FEATURES.md). Every page requires the access token when one is configured, and the web app only reads from the car.

## Bench, vehicle picker and navigation
`/` lists the vehicles known from the MES log corpus and shows corpus health. `/v/{vin}` is the **bench**: what to do right now for the car on the lift. A flow bar and tab strip carry the mechanic from complaint to release (Bench, Job, Codes, Live board, Tests, Systems, Report, and a More menu). `/start` and `/v/{vin}/release` open and close a visit; release records that the tools are put away.

## Connect and guided full scan
`/live` shows the adapter, declared cable, buses and verification state, and lets you declare the cable, verify, probe and run OBD reads. `/v/{vin}/scan` is the guided wizard that reads each bus and pauses at each cable swap. `/coverage` is the earlier whole-car run with a baseline. See [[Guided Full Scan|Guided-Full-Scan]].

## Scan requirements and scan plan
A checklist on the scan page lists what every scan must capture for the open EVAP job; each item is met, silent, missing or not applicable. `/v/{vin}/scan-plan` lists ten planned scans for a diagnosis with status per row.

## Live board
`/v/{vin}/liveboard`: large-digit readouts for a passenger to watch, graded against known-good bands. See [[Live Board|Live-Board]].

## Passive chassis panel (API)
`GET /api/live/chassis/passive`: a short receive-only listen on the chassis bus (grey A6 cable declared), decoded through a public Giorgio CAN database into steering, wheel-speed, brake-switch and engine-speed signals. Listen-only and not yet validated on the car. See [[Passive Chassis Decoding|Passive-Chassis-Decoding]].

## Gauges dashboard
`/v/{vin}/gauges` and `/v/{vin}/gauges/hud`: a customisable live dashboard with saved layouts, custom channels, snapshots, triggers and recording replay.

## Vehicle dashboard
`/v/{vin}/dashboard`: a per-vehicle overview with charts. It carries an **Oil level** card: owner-entered dipstick, measured-fill or drain-volume readings become litres and US quarts in the sump, % of capacity and % between MIN and MAX (the MIN-MAX span is assumed 1.0 L until measured). See `docs/maintenance/OIL_LEVEL_CARD.md`.

## Scans and scan log
`/v/{vin}/scans` groups live reads into scans (a 15-minute gap separates scans) with freeze frames, readiness, Mode 06 and which modules answered. A scan can be opened, exported and **diffed** against another. `/v/{vin}/scans/{id}/health` and `/v/{vin}/health` give the scan health report: verdict, per-system table and issues graded against known-good values. `/v/{vin}/live-vs-log` compares what the live link read with what MES logs say. `/recordings` and `/logs` show MES CSV recordings and the raw log index.

## Jobs, hypotheses and mechanic steps
One job per visit, a stepper from complaint to close; hypotheses with status and evidence; ordered mechanic steps that cite their source. See [[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]].

## Evidence gate and fault trees
`/v/{vin}/tree` walks a fault tree for a code family, each step sourced and annotated with this car's evidence. `/v/{vin}/gate` builds the citations for the diagnosis verdict; `/v/{vin}/verify` is the verify-repair page. See [[Evidence Model|Evidence-Model]].

## Bulletin layer, cross-reference and analogues
`/tsb` is a per-car checklist of bulletins, recalls, notices and campaigns; the cross-reference relates each to the car's codes, repairs, hypotheses and systems. Analogues from sibling engines are listed separately and labelled. See [[TSB Layer and Cross-Reference|TSB-Layer-and-Cross-Reference]].

## SLVT replica
`/slvt`: a read-only re-creation of the small-leak verification procedure in bulletin 18-048-23. It waits for the engine computer's own EVAP monitor and reads the outcome; it does not command the test.

## Vehicle dossier
`/v/{vin}/dossier`: verdict, checklists, a code table (chronic, returned, fresh), freeze-frame flags, deduplicated bulletins and the **blind spots** the logs cannot answer. `/v/{vin}/codes` lists every code; `/v/{vin}/code/{code}` shows one code's life across sessions and prints as a PDF.

**Per-code findings.** Every non-EVAP code the 2026-10-20 review covered also shows a panel, "What we found out about this code": meaning, readings from this car, owner statement (marked attested), classification (real, service-induced, artefact, bystander, downstream, readiness flag), implications, a resolution ladder, the proof of fix and outside literature, each labelled. A SAFETY chip marks a brake-hydraulic code until an ABS read confirms it is gone. A code with no recorded finding shows nothing rather than a guess. See [[Code Reviews|Code-Reviews]]. The vehicle page also lists **every open job**, with a SAFETY chip and the one marked current ([[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]).

## Systems and dependencies
`/v/{vin}/systems` is the cross-system dependency view (25 systems): which systems may sit upstream of a code, and where the car's own history corroborates it. `/v/{vin}/systems/{key}` is a page per system with status, a relationship ring, fault tree and this car's history. A live overlay can colour systems from live readings. A part with recorded design knowledge (today, the leak-detection module) carries a **design and checks card**: how it works, thresholds, orientation, electrical values, tests, what is not documented and what the engine computer can and cannot self-check, every fact labelled outside literature with its sources.

## Electrical
`/v/{vin}/electrical`: a car-layout electrical diagram; a code's page shows its electrical path; inspections are recorded as attested findings.

## Drivetrain and transmission
`/v/{vin}/drivetrain/{section}`: transmission, transfer case, differentials, driveline and mounts, each with a record form; `/v/{vin}/service-hub` collects service pages.

## Modules
`/v/{vin}/modules` reads the module tree the way MES shows it (Info, Errors, Parameters, Actuators, Adjustments per module). `/modules` is the module registry and bus map.

## Parts
`/v/{vin}/parts`: a searchable catalogue grouped by job with names, OEM and aftermarket numbers, supersessions and torque specifications.

## Service
Oil change, general service, brakes and tyres, torque, maintenance due by odometer, service records, and print-ready **label sheets** with a calibration form.

## Owner page: Tell CUORE
`/m/{vin}`: a phone-first page where an owner, driver or mechanic records what the car cannot report itself (fluids, fuel, battery work, tyres, parts fitted elsewhere, incidents, driving pattern) and exchanges messages. A photo of an odometer, oil bottle or pump can propose fields for a human to confirm; the photo-reading provider is **off by default**. Everything entered is labelled as attested input, never a measurement.

## Modifications and MES handoff
`/v/{vin}/mods`: sourced modifications with a "do it in MES" handoff card (module, menu path, prerequisites), and a per-car ledger of what was done, by whom, from and to values, backup and verification. CUORE does not perform coding or configuration. See [[Safety Rules|Safety-Rules]].

## MES integration
Log parsing, clear auto-sync, MES log import. See [[MES Integration|MES-Integration]].

## Learning tools
`/v/{vin}/learn`: passive signal learning on a bypass-cable bus (perform one named action, stop, see ranked `(CAN id, byte offset)` candidates). `/v/{vin}/learn-mes`: data-identifier discovery by listening to MES on a second adapter. Bus capture presets. Passive only.

## Tests
`/v/{vin}/tests`: a shop-floor catalogue of mechanic tests with sourced pass criteria, a per-car result and a print view.

## Timeline and symptoms
`/v/{vin}/timeline`: codes on one axis and what the driver noticed on the other.

## Media
`/v/{vin}/media`: photos, video, audio and documents attached to the car, a code, a checklist step, a service record or a symptom; export as a zip.

## Experience links and feedback
Other people's experience (forums and videos) is shown as links with a vehicle-fit grade, always labelled as outside material and never as evidence. `/v/{vin}/inbox` lets the mechanic correct, question, confirm or disagree with any fact CUORE showed, and track the answer.

## Reports and PDF
`/v/{vin}/report` and `/report.pdf`: a printable report with an "as of" stamp and sources; possible fixes are exactly the open checklist steps and bulletin actions the dossier already carries. Per-code and scan-health exports exist too.

## Tools and API
`/tools` lists every operation reachable from a phone. `/api/docs` is the interactive reference. Errors under `/api` return one JSON body (`error`, `detail`, `status`).

## MCP surface
The same data is available to Claude Code. See [[MCP Servers and Claude|MCP-Servers-and-Claude]].
