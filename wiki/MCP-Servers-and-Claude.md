# MCP Servers and Claude

MCP (Model Context Protocol) lets an assistant such as Claude Code call tools. CUORE has two MCP servers, so a mechanic can ask questions conversationally about the same data the web pages show. Both are plain Python servers in the repository.

## `obd2-mcp`: the live link

`obd2-mcp/server.py` exposes roughly 60 tools for the adapter. **Reads are requests to the running CUORE web app** (`cuore_client.py`), so the cable declaration, bus verification and audit log are shared; the same code runs in process only if the app cannot be reached. A few operations run in process only, by design: `clear_dtcs`, `clear_module_dtcs`, `send_raw`, and the actuator tools.

Tool groups:

| Group | Examples |
|---|---|
| Connection and state | `list_ports`, `status`, `mes_state`, `mes_settings`, `connect`, `disconnect`, `set_cable`, `buses`, `modules`, `verify_bus`, `audit_log` |
| Legislated OBD | `read_vin`, `read_dtcs`, `read_pending_dtcs`, `read_permanent_dtcs`, `read_pid`, `read_voltage`, `read_supported_pids`, `read_freeze_frame`, `read_readiness`, `read_mode06` |
| UDS per module | `read_module_dtcs`, `read_module_identity`, `read_did`, `read_dtc_detail`, `read_all_module`, `scan_modules`, `discover_modules`, `discover_module_dids` |
| Scans | `full_scan`, `read_fullscan_last`, `guided_scan_start`, `guided_scan_state`, `guided_scan_continue`, `guided_scan_skip`, `coverage` |
| Verification | `verify_repair` (do the codes stay away after the monitors ran?) |
| Live data | `live_channels`, `live_session_start`, `live_session_stop`, `live_snapshot` |
| Learning and capture | `capture`, `learn_capture`, `learn_correlate`, `learned_dids`, `learn_start`, `learn_stop`, `bus_capture_start`, `bus_capture_stop`, `bus_capture_save`, `learn_actuator`, `list_actuators` |
| Media | `list_media`, `media_note` |
| Gated writes | `clear_module_dtcs`, `clear_dtcs`, `run_actuator`, `send_raw` |

### Gated writes

- `clear_module_dtcs` needs the exact phrase `CLEAR <MODULE>` (for example `CLEAR ECM`), refuses while the car is moving, needs `confirm=True` on CAN-CH, captures every code, snapshot and counter first, and reads back to flag codes that return at once.
- `clear_dtcs` (Mode 04) needs `confirm=True`, captures stored, pending and permanent codes, the freeze-frame code and readiness to a file first, and refuses while the vehicle reports motion.
- `run_actuator` replays an actuator test learned from a passive capture; it needs a typed consent phrase and refuses modules with a safety function and the whole of CAN-CH.
- `send_raw` sends a raw adapter command, classified like any other write.
- There is no write route in the HTTP API; these exist only here. See [[Safety Rules|Safety-Rules]].

## `mes-log-mcp`: log analysis and the job store

`mes-log-mcp/server.py` exposes roughly 75 tools over the `mes` library:

| Group | Examples |
|---|---|
| Logs | `list_logs`, `latest_log`, `vehicles`, `read_log`, `search_logs`, `log_dir`, `status` |
| Analysis | `analyze_scan`, `analyze_session`, `get_freeze_frame`, `extract_dtcs`, `dtc_history`, `list_parameters`, `parameter_series`, `module_info`, `failure_type`, `dtc_description`, `actuator_history` |
| Recordings | `list_recordings`, `read_recording`, `recording_series`, `recording_events`, `recording_snapshot` |
| Dossier and reasoning | `vehicle_report`, `workup`, `fault_tree`, `diagnosis_verdict`, `systems_for_code`, `system_correlation`, `dtc_feel`, `experience_links`, `electrical_path`, `physical_path`, `part_info` |
| Human input | `record_dealer_result`, `dealer_results`, `add_note`, `notes`, `add_symptom`, `symptoms`, `feedback_*`, `electrical_inspection_add` |
| Jobs | `job_open`, `job_current`, `job_add_action`, `job_add_hypothesis`, `job_set_hypothesis`, `job_edit_hypothesis`, `job_add_evidence`, and delete/undelete/remove variants |
| Shop and cases | `shop_intake`, `shop_release`, `cases_match`, `cases_prefill`, `tool_recommend`, `tool_usage_add`, `tool_inventory_*` |
| CUORE's own logs | `cuore_list_scans`, `cuore_latest_scan`, `cuore_read_scan`, `cuore_export_scan`, `cuore_search`, `cuore_log_dir`, `cuore_log_archive`, `cuore_log_integrity`, `logs_timeline` |

CUORE's own scan logs are as easy to query as MES logs: scans can be listed, read, searched and exported in MES format, an archive copy with a sha256 manifest never truncates the original, and an integrity check parses every line and counts kinds per day.

Simulation logs are excluded by default; SCAN provenance is reported as unverifiable ([[MES Integration|MES-Integration]]). File access is contained to the configured log roots.

## Using them

- In **Claude Code**, both servers are configured at user scope. After editing a server's code, reload it with `/mcp`; the process keeps the code it started with, and a fix that "does not take" is usually this.
- In **Claude Desktop**, the same two servers are configured in its configuration file and need a restart to pick up changes. Write-side safety rules apply identically.
- The recommended pattern: let the assistant propose, let the web page show, let the mechanic decide. The assistant is bound by the same rules, including no clears without consent and data-only conclusions ([[Evidence Model|Evidence-Model]]).
- Because MES and CUORE share one serial port, ask the assistant to check `mes_state` first when a read refuses.

A first-live-session runbook that uses these tools in order is [docs/handbook/07-first-live-session.md](https://github.com/dangelojohn/CUORE/blob/main/docs/handbook/07-first-live-session.md): preconditions, the fast path (`full_scan` then the decisive test), the guided scan with cables, and the manual sequence as fallback.

Related: [[Architecture]], [[Features]].
