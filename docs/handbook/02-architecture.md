# Architecture

Generated from the code on 2026-10-07. Re-run the greps noted inline if this drifts.

## The three programs

**`cuore/`** -- a FastAPI app (`cuore/app.py`). Two surfaces over one service layer: `/api/*` JSON mirroring the MCP tool surface call-for-call, and `/` server-rendered bench pages (`cuore/web/`) that are a client of the same bridge, not a parallel implementation. Entry point `cuore/__main__.py`, settings in `cuore/config.py` (`CUORE_*` env vars, binds loopback by default).

**`mes-log-mcp/`** -- the MES log analysis library (`mes-log-mcp/mes/`, pure stdlib, no FastAPI/MCP imports) plus a thin MCP tool surface (`mes-log-mcp/server.py`) exposing it. Parses MultiEcuScan's exported logs and CSV recordings, and holds the sourced knowledge tables (specs, parts, TSBs, fault trees...).

**`obd2-mcp/`** -- an MCP server (`obd2-mcp/server.py`) for the live ELM327/OBD-II link to the car. It does not talk to the adapter directly any more: `obd2-mcp/cuore_client.py` makes it an HTTP client of cuore, which owns the adapter so there is exactly one owner of the serial link. If cuore is unreachable at a local `CUORE_URL`, the client auto-starts it (`CUORE_AUTOSTART=0` disables that); if it still cannot be reached, calls fall back to in-process.

## How they connect

- **cuore -> mes**: the *only* module in cuore that imports `mes` is `cuore/services/mes_bridge.py` (its own docstring says so). Every other bridge in `cuore/services/*_bridge.py` either goes through `mes_bridge` or wraps one specific `mes` submodule (e.g. `electrical_bridge.py` for `mes.electrical`/`mes.electrical_inspections`, `known_good_bridge.py` for `mes.known_good`). This keeps `mes-log-mcp/server.py`'s MCP tools and cuore's HTTP/HTML answers from drifting apart -- one library, two faces.
- **obd2-mcp -> cuore**: `obd2-mcp/cuore_client.py` is a stdlib-only HTTP client hitting cuore's `/api/*` routes for adapter reads.
- **Writes to the car are MCP-only, with consent phrases.** `obd2-mcp/server.py`'s `run_actuator` requires `consent` to equal exactly `"ACTUATE <MODULE> <NAME>"`; `clear_module_dtcs` requires `consent` exactly `"CLEAR <MODULE>"` and is documented as destructive to evidence; `clear_dtcs` and `send_raw` are likewise marked MCP-only in their docstrings. cuore's `/api/live*` (`cuore/api/live.py`) has no write route at all -- its docstring states `actuators` stays `False` and the read-only UDS allowlist is enforced below that layer, "so a write cannot be added here by accident."

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

Not on the vbar but under `/v/{vin}/...`: `verify` (`dossier_routes.py`), `oil-change`/`service`/`brakes-tires`/`torque`/`maintenance` (`service_routes.py`), `drivetrain/{section}` (`drivetrain_routes.py`), `labels`/`labels.pdf` (`labels_routes.py`), `notes` (`routes.py`), `dealer` (`routes.py`), `live-vs-log` (`routes.py`).

## API router files (`cuore/api/*.py`)

| File | Prefix | Purpose (from docstring) |
|---|---|---|
| `checklists.py` | `/api` | Shop-visible checklist state over HTTP: GET/POST one step at a time |
| `deps.py` | n/a | Shared route dependencies (the single shared-token auth) |
| `dossier.py` | `/api` | `GET /api/vehicles/{vin}/view` -- the redesigned dossier's data as JSON, read-only |
| `electrical.py` | `/api` | Electrical elements, per-DTC electrical paths, and vehicle inspection records |
| `experience.py` | `/api` | HTTP face of `experience_bridge`: what other owners/forums/videos say about a code |
| `feedback.py` | `/api` | Mechanic feedback on a fact cuore showed; mirrors the MCP feedback tools call-for-call |
| `jobs.py` | `/api` | JSON face of the Job (case) workflow; writes are thin pass-through to the bridge |
| `known_good.py` | `/api` | `GET /api/live/known-good`: known-good reference bands for live channels |
| `live.py` | `/api` | The live link over HTTP; no write route, read-only UDS allowlist enforced |
| `live_ui.py` | `/api` | Layouts, replay, custom channels, snapshots and triggers for the live-data dashboard UI |
| `logs.py` | `/api` | Raw log access: index, one file verbatim, regex search (filename-resolution security note) |
| `media.py` | `/api` | Mechanic evidence media library: upload, browse, recover photos/scans/clips |
| `parts.py` | `/api` | Parts catalog (names, numbers, supersessions, torque, price, images) |
| `recordings.py` | `/api` | CSV recordings from MES's graph subsystem; only MES output with real per-sample timestamps |
| `reference.py` | `/api` | Static reference data: module registry and failure-type table |
| `system.py` | `/api` | Capabilities, health and corpus status; `/api/capabilities` is the first call any client makes |
| `systems.py` | `/api` | Vehicle-systems graph and DTC-system correlation |
| `timeline.py` | `/api` | Mechanic-vs-driver timeline: codes on one axis, felt symptoms on the other |
| `tools.py` | `/api` | Read-only data for the Tools catalogue page; writes to the car listed only as inert cards |
| `vehicles.py` | `/api` | Per-vehicle diagnostics: the dossier and everything it points at |

## MCP tools

### `mes-log-mcp/server.py` (53 tools, via `@mcp.tool`)

Corpus/log: `status`, `list_logs`, `latest_log`, `vehicles`, `read_log`, `search_logs`, `analyze_scan`, `analyze_session`, `get_freeze_frame`, `extract_dtcs`, `dtc_history`, `list_parameters`, `parameter_series`, `module_info`, `failure_type`, `dtc_description`, `log_dir`.

Diagnosis/knowledge: `experience_links`, `actuator_history`, `vehicle_report`, `workup`, `fault_tree`, `diagnosis_verdict` (the evidence gate), `dtc_feel`, `systems_for_code`, `system_correlation`, `part_info`, `electrical_path`, `physical_path`.

Recordings: `list_recordings`, `read_recording`, `recording_series`, `recording_events`, `recording_snapshot`.

Attested records (append-only): `record_dealer_result`/`dealer_results`, `add_note`/`notes`/`edit_note`/`hide_note`, `feedback_list`/`feedback_add`/`feedback_answer`/`feedback_status`, `add_symptom`/`symptoms`/`hide_symptom`, `electrical_inspection_add`/`electrical_inspections`, `job_open`/`job_current`/`job_add_action`/`job_set_hypothesis`.

### `obd2-mcp/server.py` (47 tools, via `@mcp.tool`)

Link/status: `list_ports`, `status`, `mes_state`, `mes_settings`, `connect`, `disconnect`, `set_cable`, `buses`, `modules`, `verify_bus`, `capture`, `audit_log`, `coverage`.

Reads (Mode 01-0A, UDS): `read_dtcs`, `read_pending_dtcs`, `read_permanent_dtcs`, `read_pid`, `read_voltage`, `read_supported_pids`, `read_freeze_frame`, `read_vin`, `read_readiness`, `read_module_dtcs`, `read_module_identity`, `read_did`, `scan_modules`, `discover_modules`, `read_mode06`, `read_dtc_detail`, `read_all_module`, `discover_module_dids`.

Learning: `learn_capture`, `learn_correlate`, `learned_dids`, `learn_actuator`, `list_actuators`.

Writes (MCP-only, consent-gated): `run_actuator`, `clear_module_dtcs`, `clear_dtcs`, `send_raw`.

Live session: `live_channels`, `live_session_start`, `live_session_stop`, `live_snapshot`.

Media: `list_media`, `media_note`.

Verification: `verify_repair`.

## Launchers and keep-alive

- `start-cuore.ps1` -- launches cuore if not already up and opens a page in the default browser (`-Page`, `-Restart`). Only stops a process whose command line is `python -m cuore`, so it never kills an unrelated server.
- `cuore-keepalive.ps1` -- loop every 10s: starts cuore if nothing listens on `127.0.0.1:5000`, restarts it if `/api/health` fails 3x in a row. Logs to `C:\ProgramData\cuore\logs\server.log` (rotated at 10 MB). Single instance via a named mutex. Run by the scheduled task "CUORE Server".
- `install-cuore-autostart.ps1` -- installs/removes (`-Remove`) that per-user scheduled task (runs `cuore-keepalive.ps1` at logon and every 5 minutes; no admin rights needed).
- `make-cuore-shortcuts.ps1` -- rebuilds the desktop "CUORE Bench" shortcut and the Start Menu "CUORE" folder (one link per main page), all pointing through `start-cuore.ps1`.
