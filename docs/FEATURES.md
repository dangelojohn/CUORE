# CUORE features

A tour of what the web app offers, grouped by page or route group. For each
group: what it shows, the routes, and the service or live-link module that
feeds it. For how the layers fit together see [ARCHITECTURE.md](ARCHITECTURE.md).

Conventions that apply everywhere:

- `{vin}` is a vehicle identifier. Pages live under `/v/{vin}/...`; the JSON
  API lives under `/api` and mirrors the pages. A page and its API route call
  the same bridge in `cuore/services/`, so they cannot disagree.
- Page routes are in `cuore/web/*_routes.py`; JSON routes are in
  `cuore/api/*.py`. Bridges are `cuore/services/*_bridge.py`. Live-link code is
  in `cuore/live/`.
- Every page requires the access token when one is configured.
- Pages are server-rendered and the forms work without JavaScript.
- The web app reads from the car; it sends no write. See the safety rules in
  the [README](../README.md).

## Bench, vehicle picker and navigation

- `/` lists vehicles known from the MES log corpus and shows corpus health.
- `/v/{vin}` is the bench: what to do right now for the car on the lift
  (`bench_routes.py`, `bench_bridge`). `POST /v/{vin}/bench/done` marks a bench
  item done.
- A flow bar and tab strip run across the vehicle pages (`flow_bridge`,
  `/api/vehicles/{vin}/flow`): the mechanic's steps from complaint to release.
  Tabs: Bench, Job, Codes, Live board, Tests, Systems, Report, and a More menu
  for the rest.
- `POST /lang` sets the interface language cookie (`i18n.py`).
- `/start` and `/v/{vin}/release` are the start-a-car and release forms
  (`shop_routes.py`, `shop_bridge`; JSON under `/api/shop/*`). Release records
  that the tools are put away.

## Connect and guided full scan

- `/live` shows the adapter, the declared cable, the buses and their
  verification state, and lets you declare the cable, verify a bus, probe the
  adapter and run OBD reads. `/live/module/{code}` shows one module's UDS
  codes and identity. Feeds: `cuore/live/ops.py` and `transport.py`.
- `/v/{vin}/scan` is the guided full-scan wizard (`fullscan_routes.py`,
  `cuore/live/fullscan.py`). It reads CAN-C, then pauses for the blue A5 cable
  (CAN-IHS) and the grey A6 cable (CAN-CH), with start, continue, skip and
  abandon actions. Every read is recorded as an observation, so the scan log,
  dossier and health report see it.
- `/coverage` is the earlier whole-car coverage run: baseline with no cable,
  each bypass cable, then CAN-C again, diffed against the baseline so codes
  planted by cable changes are reported as bystanders (`cuore/live/coverage.py`).
- API: `/api/live/*` (status, ports, cable, verify, probe, obd, module reads,
  fullscan, guided scan, coverage, audit).

## Scan requirements

The guided-scan page includes a checklist of what every scan must capture for
the open EVAP diagnosis, with each item met or a gap with a plain reason
(`scan_requirements_bridge`, data in `cuore/data/scan_requirements.json`). A
legislated read that returned nothing is reported as the adapter route being
silent, not as the car having nothing to say. `/v/{vin}/scan-plan` lists the
ten planned scans with status per row: done, due or blocked
(`scan_plan_bridge`); only a complete scan marks a row done.

## Live board

`/v/{vin}/liveboard` is a read-only board for a passenger to watch while
someone else drives: every known channel, grouped by system, as a large digital
readout coloured by how far it is out of its known-good band
(`liveboard_bridge`, `mes.known_good`). Freeze-frame capture, save and discard
and a snapshot-to-job action are under `/api/liveboard/{vin}/*`. Known-good
bands: `/api/live/known-good`.

## Live new-code alert

While a live-data session runs with the code watch on (the "Watch for new codes
(every 10 s)" box on the Live board, default on; `code_watch` and
`code_watch_interval_s`, minimum 5, on `POST /api/live/session/start`), the poller
reads OBD Mode 03 (stored) and Mode 07 (pending) on its own held session. Read-only:
nothing is ever cleared. The first read is the baseline; a code not in the previous
read raises a "! New code P0456 (pending) 12 s ago" banner (`_code_watch.html`) on the
Live board and Gauges pages, with a link to the code page and a Seen button
(`POST /api/live/session/code-watch/ack`). A code that clears and returns alerts
again. Each event is also an observation (`live_new_code`, with the session id) for
the evidence gate. State is under `code_watch` in `GET /api/live/session`. The watch
skips a read when a live channel is behind.

## Gauges dashboard

`/v/{vin}/gauges` and `/v/{vin}/gauges/hud` are a customisable live-data
dashboard (`live_dashboard_routes.py`, client code in
`cuore/web/static/live/`). Layouts, custom channels, snapshots, triggers and
recordings replay are stored through `/api/live/layouts`,
`/api/live/custom-channels`, `/api/live/snapshots`, `/api/live/triggers` and
`/api/live/replay/*` (`cuore/live/ui_store.py`, `layouts.py`, `replay.py`).
The live stream is `/api/live/stream`, fed by the poller session
(`/api/live/session/*`).

## Live list sorting

The Live board (`/v/{vin}/liveboard`) has a "Sort by" bar: Name, Value, Alarm
state or Group (`web/static/list_controls.js`). Sorting is client-side on the
rendered rows and remembered per VIN in localStorage; the server order is the
default, so the page works without JS. The page has no channel checkboxes, so
there is no Select All/None there.

## Live graphs

The Gauges page has a Graphs panel (`web/static/live/graphs.js`): 1 to 4
stacked canvas graphs, each with a channel list and a 30 s / 2 min / 10 min
window, fed by a rolling history from `/api/live/snapshot`. Now, min and max
show beside each graph. A tap on any graph puts one cursor on all graphs and
reads each channel's value at that time; a second tap clears it. Channels and
graph count are remembered per VIN.

## Recording tags and channel priority

While a gauges recording runs, keys 0-9 (or the ten buttons in
`_record_tags.html`) insert an instantaneous tag: one extra CSV row whose TAG
cell reads `TAG <key>: <label>`, so MES's parser and CUORE replay see an
ordinary marker. Labels default to "Tag 0".."Tag 9" and are renamed per VIN
under "Rename tags" (`ui_store.py`, `record_tags.json`). API:
`POST /api/live/record/tag` (409 when not recording) and
`GET/POST /api/live/record/tag-labels`; `status()` lists `recording_tags`.
Drive recordings (`/v/{vin}/recordings/{id}`) list their tags with time and row
and mark them on every chart and the time axis.

`POST /api/live/session/start` takes optional `priorities` (channel id to 1-5,
default 1). The value is a poll divisor: 1 reads on every scheduled cycle, 5 on
every 5th, freeing bus time for priority-1 channels. `status()` reports
`channel_rates` (priority, divisor, configured and achieved Hz). API only; the
gauges page has no channel picker.

## Vehicle dashboard

`/v/{vin}/dashboard` and `/api/vehicles/{vin}/dashboard` assemble a
per-vehicle overview with charts (`dashboard_bridge`, `dashboard_charts.py`).

## Scans and scan log

- `/v/{vin}/scans` is the browsable scan log: live reads grouped into scans
  (a 15-minute gap separates scans), with freeze frames, readiness, Mode 06 and
  which modules answered. `/v/{vin}/scans/{scan_id}` shows one scan;
  `/v/{vin}/scans/diff` compares two. Feed: `cuore/live/scanlog.py` over
  `observations.jsonl`, via `scanlog_bridge`.
- `/v/{vin}/scans/{scan_id}/health` and `/v/{vin}/health` show the scan health
  report: verdict, per-system table and issues, graded against known-good
  values (`scan_health_bridge`).
- `/v/{vin}/live-vs-log` compares what the live link read with what the MES
  logs say.
- `/recordings`, `/recording/{name}` and `/logs` show MES CSV recordings and
  the raw log index (`mes_bridge`).
- API: `/api/scans/*`, `/api/recordings`, `/api/logs`, `/api/live/observations`.

## Jobs, hypotheses and mechanic steps

- `/v/{vin}/job` and `/v/{vin}/job/{job_id}` are the job page, a stepper from
  complaint to close (`jobs_bridge`, store in `mes/jobs.py`). Open and close a
  job, close it as a case, record actions, review tools.
- Hypotheses can be added, edited, given a status and evidence, deleted and
  restored. Adding one checks for a similar existing hypothesis
  (`.../hypotheses/similar`) and offers suggestions.
- Mechanic steps for a hypothesis (`mechanic_plan_bridge`,
  `/api/jobs/{job_id}/hypotheses/{hyp_id}/plan`): ordered, numbered tasks, each
  citing its source (a bulletin, the hypothesis text, a job action or a
  dependency path). A button saves the plan as the hypothesis's next test.
- Recorded clears and repairs, the tools panel (`tools_kb_bridge`,
  `/api/tools-kb/*`) and past cases (`cases_bridge`,
  `/api/vehicles/{vin}/cases/match` and `/prefill`) support the job.
- API: `/api/vehicles/{vin}/job`, `/api/jobs/*`.

## Evidence gate and fault trees

`/v/{vin}/tree` walks a fault tree for a code family with each step sourced and
annotated with this car's own evidence. `/v/{vin}/gate` is the evidence gate: a
form that builds the measurement citations for `diagnosis_verdict`
(`mes/verdict.py`). `/v/{vin}/verify` is the verify-repair page. Checklist
steps post to `/v/{vin}/checklist` (`dossier_routes.py`).

## Bulletin layer, cross-reference and sibling analogues

- `/tsb?vin=...` lists every bulletin, recall, customer satisfaction notice,
  campaign and extended coverage known for the car as a per-VIN checklist;
  `POST /tsb/status` records a row's status and note (`tsb_bridge`, data in
  `cuore/data/tsb_catalogue.json`, readable form in
  [reference/TSB_CATALOGUE.md](reference/TSB_CATALOGUE.md)).
- The cross-reference (`tsb_xref_bridge`, `/api/tsb/xref?vin=...`) relates each
  catalogue row to the car's codes, the repairs on the job, open hypotheses and
  the systems-dependency layer. Every relation carries a reason that can be
  checked against its source. It writes nothing; suggested evidence is only
  offered through a form.
- Catalogue rows with scope `sibling_engine` are analogues from other models
  with the same engine family. They are listed separately and labelled as
  analogues, not as bulletins for this car.

## SLVT replica

`/slvt?vin=...` shows the bulletin 18-048-23 checklist, a Run button and the
last graded result (`slvt_bridge`). Run (`POST /slvt/run`) waits for the ECM's
own EVAP monitor and reads its outcome through three existing read-only
operations. It does not command the test. Preconditions the bulletin does not
state are not invented; each carries its source.

## Vehicle dossier and known limitations

`/v/{vin}/dossier` is the full dossier (`dossier_bridge`, `mes/workup.py`):
verdict, checklists, code table with chronic, returned and fresh
classification, freeze-frame flags, deduplicated bulletins and the blind spots
the logs cannot answer. A collapsible Known limitations section lists what
CUORE cannot read for this car and the evidence for each. `/v/{vin}/codes`
lists every code; `/v/{vin}/code/{code}` shows one code's life across sessions
and `/v/{vin}/code/{code}/report.pdf` prints it. The dealer-results and notes
forms are `/v/{vin}/dealer` and `/v/{vin}/notes`. API: `/api/vehicles/*`,
`/api/vehicle/{vin}/*`.

## Systems and dependencies

- `/v/{vin}/systems` is the cross-system dependency view: which systems may
  sit upstream of a code's family, and where this car's history corroborates
  it (`systems_bridge`, `systems_map_bridge`, `systems_svg.py`).
- `/v/{vin}/systems/{key}` is a page for one of the 25 systems
  (`system_detail_bridge`). Mechanic input for an unknown item is filed through
  `/api/attested/{vin}` and is labelled as attested, never as a measurement.
- API: `/api/systems`, `/api/systems/for-code/{code}`,
  `/api/systems/{vin}/state`, `/api/systems/{vin}/live`.

## Electrical

`/v/{vin}/electrical` is a car-layout electrical diagram (`electrical_bridge`,
`electrical_svg.py`). A code's page shows its electrical path.
`POST /v/{vin}/electrical/inspect` records an inspection. API:
`/api/electrical/*`.

## Drivetrain and transmission

`/v/{vin}/drivetrain/{section}` has pages for the transmission, transfer case,
differentials, driveline and mounts, each with a record form
(`drivetrain_routes.py`, `service_bridge`). `/v/{vin}/service-hub` is the
service hub. Reference data is in `docs/reference/` (for example the ZF 8HP
service data). API: `/api/vehicles/{vin}/drivetrain/{section}`,
`/api/vehicles/{vin}/service-hub`.

## Modules

`/v/{vin}/modules` and `/v/{vin}/modules/{code}` read the module tree the way
MES shows it, with Info, Errors, Parameters, Actuators and Adjustments per
module (`modules_bridge`). `/modules` is the module registry and bus map
(`mes` module catalogue; API `/api/modules`).

## Parts

`/v/{vin}/parts` is a searchable parts catalogue grouped by job (`parts_bridge`,
`mes/parts.py`): names, OEM and aftermarket numbers, supersessions, torque
specs. API: `/api/parts`, `/api/parts/for-code/{code}`, `/api/parts/for-job/{job}`.

## Service

`/v/{vin}/oil-change`, `/v/{vin}/service`, `/v/{vin}/brakes-tires`,
`/v/{vin}/torque` and `/v/{vin}/maintenance` cover specs, torque checklists,
service records and maintenance due by odometer (`service_routes.py`,
`service_bridge`). `/v/{vin}/labels` and `/v/{vin}/labels.pdf` preview and
download print-ready label sheets, with a calibration form
(`labels_bridge`). `/v/{vin}/mods` is the modifications ledger (see below).
API: `/api/vehicles/{vin}/service-records`, `/maintenance`, `/torque`,
`/api/mods/*`.

## Owner page

`/m/{vin}` is "Tell CUORE", a phone-first page where an owner, driver or
mechanic records what the car cannot report: fluids, fuel, battery work, tyres,
parts fitted elsewhere, incidents and driving pattern. It also carries
messages between owner, mechanic and CUORE, a print view, labels and a QR code
(`owner_routes.py`, `cuore/live/owner_events.py`). A photo of an odometer, oil
bottle or pump can propose fields for the human to confirm through
`/api/vision/*`; the provider is off by default. Everything entered is
labelled as attested input. API: `/api/owner/{vin}/*`.

## Modifications and MES handoff

`/v/{vin}/mods` and `/v/{vin}/mods/{mod_id}` list sourced modifications with a
"do it in MES" handoff card (module, menu path, prerequisites) and record that
one was done, with who, when, from and to values, backup and verification
(`modifications_bridge`, `mes_handoff_bridge`). CUORE does not perform coding
or configuration. The Tests page and job step use the same handoff cards for
actuator tests and adjustments.

## MES integration and clear auto-sync

- MES logs are parsed by `mes-log-mcp/mes/` and surfaced through `mes_bridge`.
- Clear auto-sync (`mes_clear_watch.sync`, called from the job page): logs
  newer than the last sync are parsed; a SCAN log with clear-phase blocks or a
  FES log with clear events adds a `clear` action to the VIN's open job,
  dated to the log, naming what was cleared and the codes present first.
  Simulation logs and logs without a matching VIN are skipped, and re-syncing
  is idempotent.
- MES log import (`mes_handoff_bridge.import_mes_log`,
  `/api/tests/{vin}/mes-import`, `/api/tests/{vin}/mes-scans`) brings in a MES
  scan captured outside CUORE's own link.

## Learn and MES-learn

- `/v/{vin}/learn` is signal learning on a bypass-cable bus: start a capture,
  perform one named action (press the brake, open a door), stop, and see ranked
  `(CAN id, byte offset)` candidates to name and save. Passive capture only.
  Feed: `cuore/live/learn.py`, `learned.py`; API `/api/live/learn/*` and
  `/api/live/learned`.
- `/v/{vin}/learn-mes` is DID discovery by listening to MES: a second adapter
  on a Y-splitter on CAN-C records MES's own requests and the replies, a CSV
  recorded by MES is fitted against what was heard, and candidates with fit
  numbers (R squared, scale, offset, sample count) are accepted or rejected.
  It never transmits, and refuses to start unless the port is a different
  adapter from MES's own. Feed: `cuore/live/mes_learn.py`; API `/api/mes-learn/*`.
  Also `POST /api/live/module/{code}/discover-dids`.

## Bus capture

Passive raw-frame capture per bypass-cable bus, with save and presets
(`cuore/live/buscapture.py`, `capture.py`). API: `/api/buscapture/*`
(`cable`, `{bus}/start`, `status`, `stop`, `save`, `presets/{name}`) and
`POST /api/live/capture`. The page front end for it is the Learn page above.

## Tests

`/v/{vin}/tests` is the shop-floor catalogue of mechanic tests with a
per-car result, a print view (`/v/{vin}/tests/{test_id}/print`) and a result
form (`tests_bridge`, `mes/mechanic_tests.py`). API: `/api/tests/*`.

## Timeline and symptoms

`/v/{vin}/timeline` puts codes on one axis and what the driver noticed on the
other (`timeline_bridge`, `timeline_svg.py`); `POST /v/{vin}/symptoms` records
a symptom. API: `/api/vehicles/{vin}/timeline`, `/symptoms`,
`/api/vehicles/{vin}/code/{code}/feel`.

## Media

`/v/{vin}/media` is the photo, video and document gallery; a small attach strip
is embedded on other pages for a code, checklist step, service record, symptom
or the vehicle (`media_bridge`, `cuore/live/media.py`). API:
`/api/vehicles/{vin}/media`, `/media/export.zip`, `/api/media/{id}/file`.

## Experience links and feedback

- Other people's experience is shown as links with a vehicle-fit grade
  (`experience_bridge`, `mes/experience.py`): forums and videos for a code,
  family or job, with flags for links that did not work. Inputs typed in on
  the shop floor are stored separately (`/api/experience/*`). All of it is
  labelled as outside material, not evidence.
- Feedback (`/v/{vin}/inbox`, `feedback_bridge`) lets a mechanic correct,
  question, confirm or disagree with a fact CUORE showed, pinned to a page and
  item, and later answered and marked applied or dismissed. API:
  `/api/vehicles/{vin}/feedback`, `/api/feedback/*`.

## Reports and PDF

`/v/{vin}/report` is a printable report and `/v/{vin}/report.pdf` the PDF
(`report_routes.py`, `report_pdf.py`, ReportLab). Possible fixes are exactly the
open checklist steps and bulletin actions the dossier already carries, each
with its source. Parts and media sections are skipped if unavailable.
`/v/{vin}/code/{code}/report.pdf` is the per-code report. Scan health reports
also export as Markdown (`/api/scans/{vin}/{scan_id}/health.md`).

## Session kits

Four read-only tools for one car session, all listed step by step in the Bench
"Next connection" fold: decode confirm (`decode_confirm_run` and
`/api/live/decode-confirm/*`, MES then CUORE, compared by recording tag), module
code round with ABS snapshot bindings (`/api/live/round`,
`/api/live/snapshot-bind`), the Mode 06 layout check (`layout_check` on
`read_mode06`) and responder naming (`name_responders`, `accept_responder`).

## Tools

`/tools` lists every CUORE operation reachable from a phone, merged with the
live-link state (`tools_routes.py`, `tools_bridge`, `/api/tools/*`). `/api`
redirects to `/tools`.

## API

- Interactive reference: `/api/docs`; schema `/api/openapi.json`.
- `/api/health`, `/api/status`, `/api/capabilities`, `/api/roots`.
- Errors return one JSON body (`error`, `detail`, `status`) under `/api`; page
  routes render an error page.
- Routers are registered in `cuore/app.py`; each `cuore/api/*.py` module
  covers one subject (live, vehicles, jobs, scans, systems, electrical, parts,
  media, feedback, tests, tools, shop, owner, buscapture, mes-learn and others).

## MCP surface

The same data is available to Claude Code through `mes-log-mcp` (log analysis,
dossier, fault trees, evidence gate) and `obd2-mcp` (live reads, over the
running CUORE app). `clear_dtcs` and `send_raw` exist only on the MCP surface,
behind explicit consent flags.
