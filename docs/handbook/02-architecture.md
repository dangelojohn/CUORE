# Architecture

Generated from the code on 2026-10-07, refreshed 2026-10-13. Re-run the greps noted inline if this drifts.

## The three programs

**`cuore/`** -- a FastAPI app (`cuore/app.py`). Two surfaces over one service layer: `/api/*` JSON mirroring the MCP tool surface call-for-call, and `/` server-rendered bench pages (`cuore/web/`) that are a client of the same bridge, not a parallel implementation. Entry point `cuore/__main__.py`, settings in `cuore/config.py` (`CUORE_*` env vars, binds loopback by default).

**`mes-log-mcp/`** -- the MES log analysis library (`mes-log-mcp/mes/`, pure stdlib, no FastAPI/MCP imports) plus a thin MCP tool surface (`mes-log-mcp/server.py`) exposing it. Parses MultiEcuScan's exported logs and CSV recordings, and holds the sourced knowledge tables (specs, parts, TSBs, fault trees...).

**`obd2-mcp/`** -- an MCP server (`obd2-mcp/server.py`) for the live ELM327/OBD-II link to the car. It does not talk to the adapter directly any more: `obd2-mcp/cuore_client.py` makes it an HTTP client of cuore, which owns the adapter so there is exactly one owner of the serial link. If cuore is unreachable at a local `CUORE_URL`, the client auto-starts it (`CUORE_AUTOSTART=0` disables that); if it still cannot be reached, calls fall back to in-process.

## How they connect

- **cuore -> mes**: the *only* module in cuore that imports `mes` is `cuore/services/mes_bridge.py` (its own docstring says so). Every other bridge in `cuore/services/*_bridge.py` either goes through `mes_bridge` or wraps one specific `mes` submodule (e.g. `electrical_bridge.py` for `mes.electrical`/`mes.electrical_inspections`, `known_good_bridge.py` for `mes.known_good`). This keeps `mes-log-mcp/server.py`'s MCP tools and cuore's HTTP/HTML answers from drifting apart -- one library, two faces.
- **obd2-mcp -> cuore**: `obd2-mcp/cuore_client.py` is a stdlib-only HTTP client hitting cuore's `/api/*` routes for adapter reads.
- **Writes to the car are MCP-only, approved by a person on the /approve page.** `obd2-mcp/server.py`'s `run_actuator`, `clear_module_dtcs`, `clear_dtcs` and `send_raw` are refused until a person approves that exact action at `/approve/{request_id}` (see docs/design/CONSENT_GATE.md); `clear_module_dtcs` is documented as destructive to evidence; all four are marked MCP-only in their docstrings. cuore's `/api/live*` (`cuore/api/live.py`) has no write route at all -- its docstring states `actuators` stays `False` and the read-only UDS allowlist is enforced below that layer, "so a write cannot be added here by accident."

## State directory layout

`CUORE_STATE_DIR` env var, else `%PROGRAMDATA%\cuore`, else `%LOCALAPPDATA%\cuore`, else `~/.cuore`, else cwd (first writable wins) -- defined in `cuore/live/config.py:state_dir()` and duplicated (by convention, not import, so `mes` never depends on `cuore`) in each `mes-log-mcp/mes/*.py` module that writes state. Found by grepping both trees for `CUORE_STATE_DIR` and for `state_dir() /` / `STATE_DIR / "`.

| Path under the state dir | Written by | What it holds |
|---|---|---|
| `observations.jsonl` | `cuore/live/store.py` (also read by `mes-log-mcp/mes/live_obs.py`) | One JSON line per live read the adapter made; the evidence gate's only live-data input |
| `audit.jsonl`, `audit.1.jsonl` | `cuore/live/audit.py` | Rotated audit log: every session, cable declaration, discovery and capture |
| `notes.jsonl` | `mes-log-mcp/mes/notes.py` | Append-only technician notes, amend/hide records, never rewritten |
| `service_records.jsonl` | `mes-log-mcp/mes/service.py` | Oil changes, general service, brakes/wheels/tyres -- one store, three kinds |
| `symptoms.jsonl` | `mes-log-mcp/mes/symptoms.py` | Driver/mechanic symptom reports, oldest first |
| `feedback.jsonl` | `mes-log-mcp/mes/feedback.py` | Mechanic feedback on a fact cuore showed (correction/question/confirmation/input/disagreement) |
| `jobs.jsonl` | `mes-log-mcp/mes/jobs.py` | The Job (case) record: complaint, hypotheses, actions, verification |
| `checklists.json` | `cuore/live/checklists.py` | Shop-visible checklist step state |
| `media/` (dir) | `cuore/live/media.py` (`index.jsonl` inside it) | Evidence photos/scans/borescope clips, indexed by `index.jsonl` |
| `live_layouts/` (dir) | `cuore/live/layouts.py` | Saved live-dashboard gauge layouts |
| `recordings/` (dir) | `cuore/live/replay.py` | Drive recordings captured by cuore itself (same CSV schema as MES's own recordings) |
| `electrical_inspections.jsonl` | `mes-log-mcp/mes/electrical_inspections.py` | What was actually found at one electrical element on one VIN |
| `custom_channels.json` | `cuore/live/ui_store.py` | User-defined live-data channels |
| `live_snapshots.jsonl` | `cuore/live/ui_store.py` | Saved snapshots of a live session |
| `live_triggers.json` | `cuore/live/ui_store.py` | Configured alert/trigger rules for live data |
| `dealer_results.jsonl` | `mes-log-mcp/mes/dealer.py` | wiTECH (dealer-tool) results recorded by hand -- the only way dealer-tool evidence enters the corpus |
| `learned_dids.json` | `cuore/live/learned.py` | Identifier mappings learned from dealer-tool (wiTECH) captures |
| `coverage.json` | `cuore/live/coverage.py` | Whole-vehicle bus/module coverage state |
| `addresses.json` | `cuore/live/store.py` | Learned/declared module bus addresses |
| labels (templates, no separate state file found) | `cuore/services/labels_bridge.py` / `mes-log-mcp/mes` | Printable label templates and records, served via `/v/{vin}/labels` |

## Vehicle tabs (`cuore/web/templates/_vbar.html`)

| Tab | Route | Routes module | Bridge | Template(s) | Test file |
|---|---|---|---|---|---|
| Dossier | `/v/{vin}` | `cuore/web/routes.py` | `dossier_bridge` (via `routes.py`'s `_dossier`) | `vehicle.html` | `cuore/tests/check_dossier_page.py`, `check_dossier_view.py` |
| Job | `/v/{vin}/job` | `cuore/web/jobs_routes.py` | `jobs_bridge` | `job.html` | `cuore/tests/check_jobs_page.py` |
| Modules | `/v/{vin}/modules` | `cuore/web/modules_routes.py` | -- | `vmodules.html`, `vmodule.html` | `cuore/tests/check_vmodules_page.py` |
| Timeline | `/v/{vin}/timeline` | `cuore/web/timeline_routes.py` | `timeline_bridge` | `timeline.html` | `cuore/tests/check_timeline_page.py` |
| Systems | `/v/{vin}/systems` | `cuore/web/systems_routes.py` | -- | `systems.html` | `cuore/tests/check_systems_page.py` |
| Electrical | `/v/{vin}/electrical` | `cuore/web/electrical_routes.py` | -- | `electrical.html`, `_electrical_path.html` | `cuore/tests/check_electrical_page.py` |
| Media | `/v/{vin}/media` | `cuore/web/media_routes.py` | `media_bridge` | `media.html`, `_media_attach.html` | `cuore/tests/check_media_page.py`, `check_media.py` |
| Parts | `/v/{vin}/parts` | `cuore/web/parts_routes.py` | `parts_bridge` | `parts.html`, `_part_card.html` | `cuore/tests/check_parts_page.py` |
| Dashboard | `/v/{vin}/dashboard` | `cuore/web/dashboard_routes.py` | `dashboard_bridge` | `dashboard.html` | `cuore/tests/check_dashboard_page.py` |
| Gauges | `/v/{vin}/gauges` | `cuore/web/live_dashboard_routes.py` | -- (live ops) | `live_dashboard.html` | `cuore/tests/check_live_dashboard_page.py` |
| Codes | `/v/{vin}/codes` | `cuore/web/routes.py` | `mes_bridge` | `codes.html`, `code.html` | `cuore/tests/check_detail.py`, `check_dtc_detail.py` |
| Fault tree | `/v/{vin}/tree` | `cuore/web/routes.py` | `mes_bridge` | `tree.html` | (covered via dossier/detail checks) |
| Evidence gate | `/v/{vin}/gate` | `cuore/web/routes.py` | `mes_bridge` | `gate.html` | (covered via `check_detail.py`) |
| Service | `/v/{vin}/service-hub` | `cuore/web/drivetrain_routes.py` | `service_bridge` | `service_hub.html` | `cuore/tests/check_drivetrain_page.py`, `check_service_page.py` |
| Report | `/v/{vin}/report` | `cuore/web/report_routes.py` | `dossier_bridge`, `timeline_bridge`, `experience_bridge`, `parts_bridge` | `report.html` | `cuore/tests/check_report.py` |
| Inbox | `/v/{vin}/inbox` | `cuore/web/inbox_routes.py` | `feedback_bridge` | `inbox.html`, `_feedback_panel.html` | `cuore/tests/check_feedback_page.py`, `check_feedback.py` |
| Logs (link, not a `/v/` tab) | `/logs?vin={vin}` | `cuore/web/routes.py` | `mes_bridge` | `logs.html` | -- |
| Tests (2026-10-08, visible tab) | `/v/{vin}/tests` | `cuore/web/tests_routes.py` | `tests_bridge` (via `GET /api/tests/{vin}`) | `tests.html` | `cuore/tests/check_tests_page.py` |
| Scans (2026-10-13) | `/v/{vin}/scans`, `/v/{vin}/scans/{scan_id}` | `cuore/web/scanlog_routes.py` | `scanlog_bridge` over `cuore/live/scanlog.py` (groups `observations.jsonl` into sessions, writes nothing) | `scanlog.html`, `scan.html` | `cuore/tests/check_scanlog_page.py` |
| Health report (2026-10-13, link from Scans, not its own vbar tab) | `/v/{vin}/health`, `/v/{vin}/scans/{scan_id}/health` | `cuore/web/scan_health_routes.py` | `scan_health_bridge` | `scan_health.html` | `cuore/tests/check_scan_health.py` |

Vehicle tab strip is now `cuore/web/templates/_vtabs.html` (included from `_vbar.html`), not the old inline list: visible row is Bench, Job, Codes, Live (liveboard), Tests, Systems, Report, Mobile; everything else (Dossier, Modules, Timeline, Gauges, Electrical, Parts, Media, Service, Fault tree, Evidence gate, Inbox, Labels, Logs, Scans, Dashboard, plus a plain link to Tell CUORE) sits behind "More...". Health report and the Systems dive-in (`/v/{vin}/systems/{key}`, below) are reached by links from Scans/Systems, not tab entries of their own.

Not on the vbar but under `/v/{vin}/...`: `verify` (`dossier_routes.py`), `oil-change`/`service`/`brakes-tires`/`torque`/`maintenance` (`service_routes.py`), `drivetrain/{section}` (`drivetrain_routes.py`), `labels`/`labels.pdf` (`labels_routes.py`), `notes` (`routes.py`), `dealer` (`routes.py`), `live-vs-log` (`routes.py`), `systems/{key}` (`cuore/web/system_routes.py` -- Systems dive-in phase 1, per-system status/relationship ring/fault tree page built from `cuore/services/system_detail_bridge.py`).

## Mobile companion: Tell CUORE (`/m/{vin}`), 2026-10-13

`cuore/web/owner_routes.py` -- its own phone-first layout (own `Jinja2Templates`, `m_*.html` templates, no desktop chrome), rebuilt 2026-10-13 to the "Ferrari benchmark" (dark, intro reveal every open, hero with odometer/verdict, four quick actions, 3-tap fill-up, camera on every form). Routes: `GET /m/{vin}`, `/add`, `/add/{category}`, `/add/{category}/{kind}` (+ `POST`), `/add/{category}/{kind}/confirm/{id}`, `/snap` (+ `POST`), `/messages` (+ reply `POST`), `/history`, `/qr`.

Every record it writes is **attested, never a car measurement** -- backed by `cuore/live/owner_events.py` (taxonomy: 9 categories, 62 kinds) via `cuore/services/owner_events_bridge.py`, exposed at `/api/owner/{vin}/taxonomy`, `/events` (GET/POST), `/messages` (GET, reply POST), `/correlations` (`cuore/api/owner_events.py`). No route in this chain ever reaches `cuore.live.actuate`/`clear`/`learn`.

"Snap & fill" photo reading: `POST /api/vision/{vin}/read` (`cuore/api/vision.py` -> `cuore/services/vision_bridge.py`), provider `CUORE_VISION_PROVIDER` = `none` (default, offline) | `claude` (opt-in, sends the photo to Anthropic) | `tesseract` (probe stub, nothing installed). Every value returned is a suggestion a human confirms; a confirmed value saved from a photo is stamped `fields_meta[key] = "photo"`. `docs/mobile/API_CONTRACT.md` is the documented contract for a future Swift/Flutter app, guarded by `check_api_contract.py`.

## API router files (`cuore/api/*.py`)

| File | Prefix | Purpose (from docstring) |
|---|---|---|
| `cases.py` (2026-10-13) | `/api` | `GET /vehicles/{vin}/cases/match`, `/cases/prefill` -- case memory read-only, via `cases_bridge` -> `mes.cases` |
| `checklists.py` | `/api` | Shop-visible checklist state over HTTP: GET/POST one step at a time |
| `deps.py` | n/a | Shared route dependencies (the single shared-token auth) |
| `dossier.py` | `/api` | `GET /api/vehicles/{vin}/view` -- the redesigned dossier's data as JSON, read-only |
| `electrical.py` | `/api` | Electrical elements, per-DTC electrical paths, and vehicle inspection records |
| `experience.py` | `/api` | HTTP face of `experience_bridge`: what other owners/forums/videos say about a code |
| `feedback.py` | `/api` | Mechanic feedback on a fact cuore showed; mirrors the MCP feedback tools call-for-call |
| `jobs.py` | `/api` | JSON face of the Job (case) workflow; writes are thin pass-through to the bridge |
| `known_good.py` | `/api` | `GET /api/live/known-good`: known-good reference bands for live channels |
| `live.py` | `/api` | The live link over HTTP; no write route, read-only UDS allowlist enforced; also hosts `/live/fullscan`, `/live/fullscan/last`, `/live/capture`, `/live/learn/*` (below) |
| `live_ui.py` | `/api` | Layouts, replay, custom channels, snapshots and triggers for the live-data dashboard UI |
| `logs.py` | `/api` | Raw log access: index, one file verbatim, regex search (filename-resolution security note) |
| `media.py` | `/api` | Mechanic evidence media library: upload, browse, recover photos/scans/clips |
| `owner_events.py` (2026-10-13) | `/api` | HTTP face of Tell CUORE (`/owner/{vin}/taxonomy`, `/events`, `/messages`, `/correlations`); every row attested, no route reaches the car |
| `parts.py` | `/api` | Parts catalog (names, numbers, supersessions, torque, price, images) |
| `recordings.py` | `/api` | CSV recordings from MES's graph subsystem; only MES output with real per-sample timestamps |
| `reference.py` | `/api` | Static reference data: module registry and failure-type table |
| `scan_health.py` (2026-10-13) | `/api` | `GET /scans/{vin}/{scan_id}/health`(`.md`), `POST .../health/save` -- the scan health report, via `scan_health_bridge` |
| `scanlog.py` (2026-10-13) | `/api` | `GET /{vin}/diff`, `/{vin}/{scan_id}`, `/{vin}/{scan_id}/export` -- one scan in full or diffed, exported as JSON or an MES-style log; the only writer, and only under `CUORE_STATE_DIR/scans/<vin>/` |
| `system.py` | `/api` | Capabilities, health and corpus status; `/api/capabilities` is the first call any client makes |
| `systems.py` | `/api` | Vehicle-systems graph and DTC-system correlation |
| `systems_map.py` (2026-10-13) | `/api` | `GET /systems/{vin}/state` (Systems map overlay: per-system colour, hot edges, session time slider) and `/systems/{vin}/live` (live overlay: worst live colour grade per system, any brand-new DTC); via `systems_map_bridge`, never writes to the car |
| `tests.py` (2026-10-08) | `/api` | `GET /tests/catalog`, `/tests/{vin}`, `POST /tests/{vin}/{test_id}/result` -- the mechanic-test catalogue (`mes.mechanic_tests`) and per-VIN results, via `tests_bridge` |
| `timeline.py` | `/api` | Mechanic-vs-driver timeline: codes on one axis, felt symptoms on the other |
| `tools.py` | `/api` | Read-only data for the Tools catalogue page; writes to the car listed only as inert cards |
| `vehicles.py` | `/api` | Per-vehicle diagnostics: the dossier and everything it points at |
| `vision.py` (2026-10-13) | `/api` | `GET /vision/status`, `POST /vision/{vin}/read` -- "read this photo" for Tell CUORE, via `vision_bridge`; never writes an owner event itself, never touches the car |

## Full scan, bus capture and learn (`cuore/live/*`, 2026-10-13)

- **Full scan** (`cuore/live/fullscan.py`, `POST /api/live/fullscan`, `GET /api/live/fullscan/last`): one read-only pass over every subsystem the adapter can reach -- OBD DTCs/readiness/Mode $06/Mode $09, every freeze-frame PID, a UDS module sweep with status flags, and a coverage rollup -- sequenced through the existing `cuore/live/ops.py` readers (no new adapter traffic of its own) and recorded as from-car observations so the Scans area, dossier and health report all see it without fifteen separate manual calls. Each step is wrapped so one failure doesn't sink the scan.
- **Guided cable wizard** is the pre-existing `/coverage` page (`cuore/web/routes.py`, `coverage.html`, not VIN-scoped itself): a guided three-pass, three-bus session (main bus with no cable, chassis bus through the grey cable, body bus through the blue cable, main bus again) with a bystander diff, backed by `/api/live/coverage*`. Full scan's own `scan_coverage` observation and this wizard's coverage session are two different mechanisms over the same `cuore/live/coverage.py` state.
- **Bus capture**: `POST /api/live/capture` (`cuore/live/capture.py`) listens passively (`STCMM 0`, no CAN ACK) and returns the raw frame list; it does **not** persist an observation today -- the frames go back to the caller only.
- **Learn**: `cuore/live/learn.py` (pure functions, reconstructs ISO-TP/UDS request-response pairs and DID time series from a passive capture) + `cuore/live/learned.py` (saves accepted mappings to `learned_dids.json`), reached at `POST /api/live/learn/capture`, `/live/learn/correlate`, `/live/learn/accept`, `GET /api/live/learned` -- how a wiTECH capture becomes a DID mapping cuore can read on its own, without ever talking to the adapter itself.
- **Live board freeze-frame panel** (`cuore/api/liveboard.py` `/liveboard/{vin}/freeze/capture|status|stop|save|discard`, `cuore/services/liveboard_bridge.py`): starts a capture of stored codes + every supported PID's freeze frame + a Mode 01 snapshot; on save, writes `obd_dtcs`, `freeze_frame`, `pid` (one per channel) and `readiness` observations and hands back a Scans-area scan id.

## Observation kinds (`cuore/live/store.py:record_observation`, `observations.jsonl`)

No kind is an enum -- any string is accepted; this is what the code actually writes and reads as of 2026-10-13.

| Kind | Written by | Read by |
|---|---|---|
| `adapter_identity` | `fullscan.py` | `dossier_bridge`/health report (adapter/session context) |
| `mode09` | `fullscan.py` | scan health report (coverage gaps) |
| `obd_dtcs` | `fullscan.py`, `ops.py` (single reads), `liveboard_bridge.py` (freeze save) | `dossier_bridge`, `scan_health_bridge`, `scanlog.py` (scan grouping) |
| `freeze_frame` | `fullscan.py`, `ops.py`, `liveboard_bridge.py` | `dossier_bridge`, `scanlog.py` |
| `readiness` | `fullscan.py`, `ops.py`, `liveboard_bridge.py` | `dossier_bridge`, `scanlog.py` |
| `mode06` | `fullscan.py`, `ops.py` | `dossier_bridge`, `scanlog.py` |
| `pids_snapshot` | `fullscan.py` | `scan_health_bridge` |
| `pid` | `liveboard_bridge.py` (freeze capture, one per channel) | `scanlog.py` (latest-value-per-PID in a window) |
| `module_dtcs` | `fullscan.py`, `ops.py` | `dossier_bridge`, `scan_health_bridge`, `scanlog.py` |
| `module_identity` | `fullscan.py` | `scan_health_bridge` |
| `did` | `fullscan.py`, `ops.py` | scan health report (DID coverage) |
| `scan_coverage` | `fullscan.py` | `scan_health_bridge` (the report's coverage section) |

`capture()`'s passive bus listen is not recorded under any kind (see above) -- that is a real gap, not an undocumented one.

## Case close-out (2026-10-13 commit 31c0d71)

Closing a Job (`cuore/services/jobs_bridge.py:close_job`, step 12) builds and saves a Case (`mes.cases.case_from_job`/`record_case`): confirmed/ruled-out hypotheses, tests run, parts fitted, verification state, pitfalls. `mes.cases.match(vin, codes)`/`prefill(vin, codes)`, exposed read-only at `GET /api/vehicles/{vin}/cases/match` and `/cases/prefill` (`cuore/api/cases.py`, `cuore/services/cases_bridge.py` -- the only module that imports `mes.cases`), rank real recorded cases above the seed data and feed Job prefill from the Systems pages; wording always says "on the last `<Model>` with these codes", never presenting a prior car's fix as this car's answer.

## Marque theming (`marque_for_vin`, 2026-10-13 commit 003d6a4)

`cuore/web/routes.py`'s `_page()` computes `data-marque` once per request from `cuore.services.mes_bridge.marque_for_vin(vin)` (pure passthrough to `mes.platform.marque_for_vin`, confidence-graded VIN-WMI decode: `alfa`/`maserati`/`ferrari`/`unknown`, never guessed) and every `/v/{vin}/*` page inherits it from that one call, instead of each route guessing (previously `data-marque` was hardcoded to `"alfa"`).

## MCP tools

### `mes-log-mcp/server.py` (62 tools, via `@mcp.tool`)

Corpus/log: `status`, `list_logs`, `latest_log`, `vehicles`, `read_log`, `search_logs`, `analyze_scan`, `analyze_session`, `get_freeze_frame`, `extract_dtcs`, `dtc_history`, `list_parameters`, `parameter_series`, `module_info`, `failure_type`, `dtc_description`, `log_dir`.

Diagnosis/knowledge: `experience_links`, `actuator_history`, `vehicle_report`, `workup`, `fault_tree`, `diagnosis_verdict` (the evidence gate), `dtc_feel`, `systems_for_code`, `system_correlation`, `part_info`, `electrical_path`, `physical_path`.

Recordings: `list_recordings`, `read_recording`, `recording_series`, `recording_events`, `recording_snapshot`.

Attested records (append-only): `record_dealer_result`/`dealer_results`, `add_note`/`notes`/`edit_note`/`hide_note`, `feedback_list`/`feedback_add`/`feedback_answer`/`feedback_status`, `add_symptom`/`symptoms`/`hide_symptom`, `electrical_inspection_add`/`electrical_inspections`, `job_open`/`job_current`/`job_add_action`/`job_set_hypothesis`.

CUORE live-log parity (`mes.cuore_log`, new 2026-10-14): `cuore_list_scans`/`cuore_latest_scan`/`cuore_read_scan`/`cuore_export_scan` read `CUORE_STATE_DIR`'s live-scan log exactly as easily as the MES tools above read MultiEcuScan's -- reusing `cuore.live.scanlog`'s observation-clustering rule (imported defensively; `mes` never duplicates it) rather than re-deriving scans from `observations.jsonl`, and tagging each scan `full`/`guided`/`partial`/`attempt`. `cuore_search` extends `search_logs`'s regex-with-context shape across `observations.jsonl`, `owner_events.jsonl`, `attested.jsonl`, `jobs.jsonl` and recording headers, read directly off disk (not through `cuore.live`, so this still works if that package is not importable). `logs_timeline(vin)` merges the MES and CUORE lists into one newest-first, sourced view. Two things change in `mes.catalog` for this: `LogEntry` now carries a `provenance` field, and a second log root -- `CUORE_STATE_DIR/scans/<vin>/`, where `cuore.live.scanlog.write_mes_export` writes MES-format exports of a live scan on request -- is scanned alongside the configured MES roots and tagged `provenance="cuore live export"`; those exports are real, from-car data (never flagged `simulation`), so `select()`/`workup` include them by default, just labelled differently from a desktop MES scan. `observations.jsonl` itself never enters the MES catalog. Log hygiene: `cuore_log_dir` reports each store file's size; `cuore_log_archive` copies a dated, sha256-manifested snapshot of every CUORE log file into `CUORE_STATE_DIR/archive/` without ever truncating or deleting the originals; `cuore_log_integrity` parses every line of every store and reports counts per kind/op and per day. The same search, independently implemented for its own process, is also reachable over HTTP as `GET /api/scans/search` (`cuore/api/scanlog.py`, additive to the existing `/api/scans/*` routes).

### `obd2-mcp/server.py` (47 tools, via `@mcp.tool`)

Link/status: `list_ports`, `status`, `mes_state`, `mes_settings`, `connect`, `disconnect`, `set_cable`, `buses`, `modules`, `verify_bus`, `capture`, `audit_log`, `coverage`.

Reads (Mode 01-0A, UDS): `read_dtcs`, `read_pending_dtcs`, `read_permanent_dtcs`, `read_pid`, `read_voltage`, `read_supported_pids`, `read_freeze_frame`, `read_vin`, `read_readiness`, `read_module_dtcs`, `read_module_identity`, `read_did`, `scan_modules`, `discover_modules`, `read_mode06`, `read_dtc_detail`, `read_all_module`, `discover_module_dids`.

Learning: `learn_capture`, `learn_correlate`, `learned_dids`, `learn_actuator`, `list_actuators`.

Writes (MCP-only, approved by a person on /approve): `run_actuator`, `clear_module_dtcs`, `clear_dtcs`, `send_raw`.

Live session: `live_channels`, `live_session_start`, `live_session_stop`, `live_snapshot`.

Media: `list_media`, `media_note`.

Verification: `verify_repair`.

## Connect to car flow (2026-10-14)

**Client**: `cuore/web/static/connect.js` (progressive enhancement overlay on the plain `/v/{vin}/scans` link in `_vbar.html`'s `#connect-drawer`). Never runs on page load; only a real tap on `#connect-car-btn` starts anything. Each refusal is shown with the live layer's real error text (from `cuore/live/ops.py`/`cuore/live/transport.py`), never invented copy.

**Server**: `POST /api/live/connect/start` (`cuore/api/live.py`) -- the one additive route -- runs pre-checks in order (adapter found → bus verified → VIN matches) and, if every one passes, starts or reports an already-open guided scan (`cuore/live/fullscan.py`). Every pause after that reuses the existing `/api/live/fullscan/guided/continue`, `/skip` endpoints.

## Modifications layer (2026-10-14 NO-GO decision)

**Rule**: CUORE diagnoses, it never performs coding/configuration writes itself. A modification is done in MES/wiTECH via a handoff card (below) and RECORDED here with who/when/from→to/backup/verification.

**Catalogue** (read-only): `mes/modifications.py` -- known modifications seeded from `mes.mes_functions` (rows of kind `"coding"`/`"adjustment"`) and a paddle-shift research pass (2026-10-14). Same split as `mes.parts` and `mes.mechanic_tests`: "what we know about this kind of thing."

**Ledger** (writable): `cuore/live/modifications.py` (append-only JSONL, `modifications.jsonl`) -- one car's actual edits, stamped with who/when/from/to/backup/verification. Four record shapes: `record`, `delete`, `restore`, `amend` (soft deletes + undos, folded in append order).

**Routes**: `cuore/web/mods_routes.py` (HTML `/v/{vin}/mods`, `/v/{vin}/mods/{mod_id}`), `cuore/api/modifications.py` (`/api/mods/catalog*`, `/api/mods/{vin}*`). The catalogue is generated from a research pass, not user-edited; the ledger is writable via `cuore/services/modifications_bridge.py`.

## MES handoff cards (2026-10-14)

**What**: when CUORE diagnoses that a coding/adjustment/actuator command is needed, it hands the technician a card -- module, menu path, prerequisites -- built from `mes.mes_functions`, never a cuore-driven write.

**Module**: `cuore/services/mes_handoff_bridge.py`. Two functions: `:func:`candidates`/`:func:`card` (lookup matched against a test id or free-text step label) + `:func:`import_mes_log`/`:func:`list_mes_scans` (MES-captured logs outside cuore's live link get a health report via the same `mes.scan_health.verdict` without disguising them as live serial reads).

**Import state**: `cuore/live/config.state_dir()` holds `mes_imports.json` (ledger of MES-sourced scans with verdicts), parallel to cuore's own `cuore/live/scanlog.py` (observations.jsonl) but never written to by the live layer.

**UI**: `cuore/web/templates/_mes_handoff.html` (card template, embedded in Tests/Job pages).

## CUORE log MCP tools (2026-10-14)

**Scan tools** (`mes.cuore_log`, new module): `cuore_list_scans`, `cuore_latest_scan`, `cuore_read_scan`, `cuore_export_scan` -- read `CUORE_STATE_DIR`'s live-scan log (`cuore/live/scanlog.py`, observation clustering) identically to how MES tools read MultiEcuScan's files. Each scan tagged `full`/`guided`/`partial`/`attempt`.

**Search tool**: `cuore_search` extends `search_logs`'s regex-with-context shape across `observations.jsonl`, `owner_events.jsonl`, `attested.jsonl`, `jobs.jsonl` and recording headers, read directly off disk (works even if `cuore.live` is not importable).

**Timeline**: `logs_timeline(vin)` merges MES and CUORE lists into one newest-first, sourced view. `mes.catalog.LogEntry` now carries a `provenance` field; a second log root -- `CUORE_STATE_DIR/scans/<vin>/` where `cuore.live.scanlog.write_mes_export` writes MES-format exports -- is scanned alongside MES roots and tagged `provenance="cuore live export"` (real from-car data, never flagged `simulation`).

**Hygiene**: `cuore_log_dir` reports store-file sizes; `cuore_log_archive` copies a dated, sha256-manifested snapshot of every CUORE log file to `CUORE_STATE_DIR/archive/` without truncating originals; `cuore_log_integrity` parses every store line and reports counts per kind/op/day. Same search independently implemented over HTTP at `GET /api/scans/search` (`cuore/api/scanlog.py`).

## Transmission additions (2026-10-14)

**Label kind**: `cuore/web/owner_routes.py` adds a label kind mapping `("fluids", "driveline_fluid")` → `("transmission_service", "")` for "Tell CUORE" fill-up guidance.

**Parts**: `mes/parts.py` includes `transmission_fluid` (ZF 8HP ATF, location/related jobs/torque keys).

**MES recording channels**: drivetrain-specific channels exposed in live capture; TCM DID discovery (`discover_module_dids`) for transmission-module reads.

## Others' experience inputs (2026-10-14)

**Module**: `cuore/live/experience_inputs.py` (append-only JSONL, `experience_inputs.jsonl`) -- driver/mechanic finds (YouTube video, forum thread, photo, note) typed in today, attributed to finder, shown on the code-experience card at confidence `"reported"` (same posture as `owner_events` and `mes.symptoms`, a person's claim not a fact).

**Four record shapes**: `input` (url, title, kind, found_by, verified status), `input_edit` (never rewrites original), `delete`/`restore` (soft delete + undo), `flag`/`worked` (marks on any link id, curated or user-added).

**API**: `cuore/services/experience_inputs_bridge.py` + `cuore/api/experience.py` (HTTP face, via `/api/experience/*`).

**Verification**: `:func:`verify_entry` (module-level, so tests monkeypatch it) uses a browser User-Agent GET for most hosts; XenForo forums (stelvioforum/giuliaforums/alfabb/alfaowner) sit behind JS challenge (202 to plain clients) so those are confirmed by headless Edge. Failure degrades to `{"status": "unreachable"}` rather than blocking save.

## Safety gates in `cuore/live/safety.py`

Three independent checks, all pure functions:

- `:func:`validate_command` -- CR, LF, STN batch separator rejected so nothing smuggles a second command past the classifier.
- `:func:`classify_command` -- `read` / `vehicle_write` / `adapter_state` / `blocked` with allowlists for AT (`AT_READ_ONLY`) and ST (`ST_READ_ONLY`) reads rather than deny-lists.
- `:func:`assert_read_only_uds` / `:func:`assert_transmit_allowed` -- HTTP layer's guarantee of no write route; cable protocol's ban on 500 kbps onto 125 kbps bus.

**Write services** (`WRITE_SERVICES` dict): UDS service codes that change vehicle state, e.g. `"2E"` (WriteDataByIdentifier, configuration), `"2F"` (InputOutputControl, actuates hardware), `"31"` (RoutineControl, adaptations/service routines).

## Launchers and keep-alive

- `start-cuore.ps1` -- launches cuore if not already up and opens a page in the default browser (`-Page`, `-Restart`). Only stops a process whose command line is `python -m cuore`, so it never kills an unrelated server.
- `cuore-keepalive.ps1` -- loop every 10s: starts cuore if nothing listens on `127.0.0.1:5000`, restarts it if `/api/health` fails 3x in a row. Logs to `C:\ProgramData\cuore\logs\server.log` (rotated at 10 MB). Single instance via a named mutex. Run by the scheduled task "CUORE Server".
- `install-cuore-autostart.ps1` -- installs/removes (`-Remove`) that per-user scheduled task (runs `cuore-keepalive.ps1` at logon and every 5 minutes; no admin rights needed).
- `make-cuore-shortcuts.ps1` -- rebuilds the desktop "CUORE Bench" shortcut and the Start Menu "CUORE" folder (one link per main page), all pointing through `start-cuore.ps1`.
