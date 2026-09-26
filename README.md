# Alfa / Stellantis Diagnostic Toolchain

Local MCP servers and reference material for professional Alfa Romeo and
Stellantis diagnostics, built around **MultiEcuScan (MES)** and a live OBD-II
link.

Two MCP servers, a companion service, one shared knowledge base.

```
mcp-servers/
├── mes-log-mcp/        MES log parsing, indexing and analysis  (MCP server)
│   ├── server.py       thin MCP tool surface
│   ├── mes/            the library - all parsing and analysis lives here
│   └── tests/          corpus smoke checks
├── obd2-mcp/           live ELM327 / OBD-II link              (MCP server)
├── cuore/              the companion service      (FastAPI: JSON API + UI)
│   ├── api/            the mes surface as HTTP, mirroring the MCP tools
│   ├── services/       mes_bridge - the only module that imports `mes`
│   ├── web/            server-rendered bench pages
│   └── tests/          corpus-backed smoke checks
├── web-ui/             the earlier Flask UI - superseded by cuore/
└── docs/
    ├── COMPANION_APP_SPEC.md   where cuore is going: profiles, live data,
    │                           Claude layers, safety policy
    ├── format/         reverse-engineered MES file formats
    ├── reference/      corpus baseline, module catalog, DTC data
    └── research/       platform, tuning and connectivity research
```

### `cuore` — the companion service

```
.venv\Scripts\python.exe -m cuore --profile bench --port 5000
```

`http://127.0.0.1:5000` for the bench UI, `/api/docs` for the JSON API.
To reach it from a phone or tablet on the shop LAN, bind wider **and set a
token** — the corpus contains customer VINs:

```
.venv\Scripts\python.exe -m cuore --host 0.0.0.0 --token <secret>
```

One application, two deployment profiles. `bench` (this machine) owns the log
corpus and every analysis; `drive` will run on a small in-car node and own the
live link. Clients never assume which one they reached — they call
`/api/capabilities` and render what that host says it can do, which is what
keeps the live paths additive rather than a rewrite. Today `live_obd`,
`live_can` and `drive_recorder` all report `false`.

**Whole-car coverage** (`/coverage`, `/api/live/coverage`, obd2 MCP tool
`coverage`) reads all three buses as one tracked session: CAN-C with no cable
as the baseline, CAN-CH through the grey A6, CAN-IHS through the blue A5, then
CAN-C again. The final read is diffed against the baseline so codes planted by
cable re-plugs are reported as bystanders. Address discovery now names nodes at
unknown addresses by matching their identity DIDs to the Table A hardware and
software numbers (`cuore/live/identify.py`), and counts a negative response as
a live node. Only status-byte faults (failed, pending, confirmed) are reported
as active. Checks: `cuore/tests/check_coverage.py`.

`cuore/services/mes_bridge.py` is the only module that imports `mes`, and it
mirrors `mes-log-mcp/server.py` call-for-call so the MCP tools and the HTTP API
cannot drift apart. `web-ui/` still runs and is left in place until every page
has an equivalent.

---

## Three ways to use this at the car

**1. Web UI (recommended for at-the-car use).** A phone/tablet-friendly
Flask app that renders `workup`, `fault_tree` and `diagnosis_verdict` as
real pages — no typing JSON. It imports `mes` directly, so every page is
live against the current log corpus, never stale.

```
..\.venv\Scripts\python.exe web-ui\app.py
```

Then open `http://<this machine's LAN IP>:5000` from any device on the same
network (find the IP with `ipconfig` — Wi-Fi adapter's IPv4 address).
Pages: vehicle list → workup dossier → fault tree (auto-loads open codes,
annotates steps with this car's own evidence) → evidence gate (a form that
builds the `diagnosis_verdict` measurement citations for you) → CSV
recordings.

**2. Claude Code (this toolchain's other interface).** Talk through a
diagnosis conversationally from the terminal, or from Claude Code's
mobile/desktop app if you're away from this machine — same MCP tools, no
extra setup, best when you want the reasoning spelled out in prose rather
than clicking through a form.

**3. Static snapshot.** For printing or texting a one-off summary of a
vehicle's current state, ask for an Artifact checklist — a point-in-time
HTML page (not live-connected; regenerate after new codes are pulled).

---

## Why this exists

MES is an excellent tool with no automation surface: it writes plain-text logs
into its install directory and that is the only way out. This project turns
those logs into structured, queryable diagnostic evidence, and adds the
analysis MES does not do.

The design is driven by things that were actually getting missed:

**A code's history is the diagnosis.** `P0456` on this shop's Stelvio was
present at 114,008 km and again at 140,572 km — a chronic small EVAP leak of
~26,500 km. A tool that reports only "last seen 2026-08-27" makes it look like
a fresh fault. Both ends of the history are now first-class.

**Clearing is not fixing.** After a clear the ECU reports nothing until each
monitor runs again, so a clean re-scan minutes later proves very little. The
tool says so instead of letting silence read as success — and it distinguishes
`cleared`, `returned` (erased and set again in the same session — a live fault
reproducing) and `uncleared` (the module refused the erase).

**A network event is one fault, not five.** When several modules each report
only "missing message" or "erratic" against *other* modules, that is one power
or bus event. Listing five module faults sends a technician chasing five
repairs.

**Most of the corpus is fake.** 54 of 79 FES logs in this install are MES
practice data. They are excluded by default. SCAN logs carry no simulation
marker at all, so their provenance is reported as *unverifiable* rather than
clean.

---

## `mes-log-mcp` — tools

| Tool | Purpose |
|---|---|
| `status` | corpus health: roots, real vs simulated counts, parse errors |
| `log_dir` | configured log roots and env overrides |
| `list_logs` | filter by kind, vehicle, VIN, date range |
| `latest_log` | newest matching session |
| `vehicles` | every vehicle in the corpus, keyed by VIN from file content |
| `read_log` | verbatim read, containment-checked |
| `search_logs` | regex across logs with context |
| `analyze_scan` | per-module status, deduplicated, with network-cascade detection |
| `analyze_session` | FES session: identity, DTCs, clear events, actuators |
| `get_freeze_frame` | the ~25 parameters captured when a code set |
| `extract_dtcs` | every code with first-seen, last-seen, session count, odometer span |
| `dtc_history` | one code's complete life across sessions |
| `list_parameters` | live parameters available in a session |
| `parameter_series` | one parameter as a series, with a static-value warning |
| `module_info` | 126-module registry; resolves every alias MES prints |
| `failure_type` | decode the failure-type byte after the dash |
| `actuator_history` | every actuator test and adjustment ever run, and why they failed |
| `vehicle_report` | whole-vehicle picture with chronic faults surfaced |
| `workup` | **the pre-work dossier**: current picture, chronic/returned/fresh history, freeze frames, TSB cross-refs, prior attempts, and the blind spots the logs cannot answer |
| `fault_tree` | FIM-style isolation sequences (EVAP leak family, P1CEA boost purge), cheapest-first, every step sourced; VIN-annotated with the car's own evidence |
| `diagnosis_verdict` | **the evidence gate**: refuses CONFIRMED until the fault is demonstrated, a mechanism is stated, a corpus-verified measurement implicates the part, and disconfirmation was attempted |
| `list_recordings` | CSV recordings from the graph subsystem, with measured rate |
| `read_recording` | one recording: columns, timing, dropouts, TAG/DTC events |
| `recording_series` | one recorded parameter as a *timed* series with stats |
| `recording_events` | TAG/DTC events + threshold queries as excursion intervals |
| `recording_snapshot` | post-hoc freeze frame at any second of a recording |

## `cuore/live` — the live vehicle link, and `obd2-mcp` over it

The adapter (a Vgate vLinker FS r2, STN1170, on COM3 at 115200) is driven by
one package, `cuore/live`, and exposed two ways: as `/api/live/*` HTTP routes
inside cuore and as MCP tools in `obd2-mcp/server.py`, which is now a thin
wrapper over the same code. One process-wide link, one lock file, one MES
interlock, so the two surfaces cannot open COM3 twice.

Rules the link follows (see `docs/design/CUORE_LIVE_LINK_PLAN.md`):

- **One operation, one open.** Every call opens the port, does its work and
  releases it. MES's own status label is checked first; a connected MES blocks.
- **Buses are declared cable states.** `set_cable none|blue_a5|grey_a6`, then
  `verify_bus` listens passively (receive only, no ACK) before anything is
  transmitted on that bus. CAN-CH additionally needs `confirm=True`.
- **Addresses carry confidence.** Only confirmed 29-bit targets are used for
  targeted UDS; the rest live in the discovery sweep until a VIN read proves
  them, and confirmations persist per VIN.
- **Read-only by construction.** The UDS allowlist is `10 01`, `19`, `22`, `3E`.
  The only vehicle write anywhere is `clear_dtcs` on the MCP surface, with
  evidence capture, a speed check and a read-back.
- Port and speed resolve from arguments, then `CUORE_OBD_PORT`/`OBD_PORT` and
  `CUORE_OBD_BAUD`/`OBD_BAUD`, then MES's `HKLM\SOFTWARE\Multiecuscan`.
- Everything returns JSON with the bus and cable named and `error` set when a
  read did not complete. State (lock, audit log, address confirmations, clear
  evidence) lives under `%PROGRAMDATA%\cuore\`.

| MCP tool / HTTP route | Purpose |
|---|---|
| `status` · `GET /api/live/status` | port, speed, sources, MES state, lock, cable, bus verification |
| `list_ports` · `GET /api/live/ports` | serial ports, MES's marked |
| `mes_state`, `mes_settings` · `GET /api/live/mes` | the interlock and MES's registry settings |
| `connect` · `POST /api/live/probe` | reset, identity, vehicle power; holds nothing |
| `set_cable` · `POST /api/live/cable` | declare the fitted cable |
| `buses`, `modules` · `GET /api/live/buses`, `/modules` | the bus and module tables |
| `verify_bus` · `POST /api/live/verify` | passive listen; marks the bus verified |
| `capture` · `POST /api/live/capture` | passive raw-frame capture with optional filters |
| `read_dtcs` / `read_pending_dtcs` / `read_permanent_dtcs` · `GET /api/live/obd/dtcs` | Modes 03 / 07 / 0A per ECU |
| `read_pid`, `read_voltage`, `read_supported_pids`, `read_freeze_frame`, `read_vin`, `read_readiness` · `GET /api/live/obd/...` | legislated OBD, decoded |
| `read_module_dtcs`, `read_module_identity`, `read_did` · `GET /api/live/module/{code}/...` | UDS 0x19 02, Annex C identity, 0x22 on one module |
| `scan_modules` · `GET /api/live/scan` | UDS DTC sweep over confirmed modules on a bus |
| `discover_modules` · `POST /api/live/discover` | `22 F190` at each candidate target; VIN reply proves the node |
| `audit_log` · `GET /api/live/audit` | every session, cable change, discovery and capture |
| `clear_dtcs`, `send_raw` (MCP only) | the gated write and the gated escape hatch |

Tests: `cuore/tests/check_live.py` (pure functions plus a playback-stream
end-to-end that needs no hardware) and the obd2-mcp scripts.

### Configuration

| Variable | Meaning |
|---|---|
| `MES_LOG_DIR` | single log directory |
| `MES_LOG_DIRS` | several, `os.pathsep`-separated; first match wins |
| `MES_CSV_DIR` / `MES_CSV_DIRS` | where MES's Settings "Export Folder" points, if moved off the log dir |

Default: `C:\Program Files (x86)\MultiEcuScan`.

---

## Security

`read_log` and every name-addressed tool resolve through
`mes.paths.resolve_log`, which requires a bare filename matching a MES log
pattern and verifies the fully resolved real path is inside a configured root.

This is not theoretical. The previous version built paths with
`Path(LOG_DIR) / name`, which on Windows contains nothing: `..\..\Windows\win.ini`
escapes via parent refs, and an **absolute** name replaces the base entirely —
pathlib semantics, not a typo. Every file the server process could read was
reachable through a tool call. Verified fixed; regression-tested in
`tests/check_server.py`.

---

## Data quality notes

Everything in `docs/format/` was reverse-engineered from the real corpus and
marks confidence per item. Load-bearing hazards handled by the parsers:

- The FES preamble is **not always at line 1** — four files open with a CAN/PROXI
  prologue, one has a stray `1`. Scan for `(Multiecuscan ` instead.
- A DTC freeze frame terminates on a line of **exactly two spaces**, and an
  empty unit slot shows up as a trailing space, so values are split before any
  strip.
- Live-parameter blocks have a **growing schema and duplicate keys** — `Engine
  oil pressure` appears as both an enum and a bar value in the same block. A
  dict loses data; samples are ordered lists.
- SCAN files repeat every module once per phase. Counting `ISO Code:` lines
  over-reports modules by 2-3x.
- Module blocks are found by anchoring on `ISO Code:` and walking back two
  lines — verified against all 122 occurrences with zero exceptions. Blank-line
  splitting fails on runs of up to five blank lines.
- ~45 files carry stray control bytes (`0x03`, `0x07`, `0x13`) from MES echoing
  raw ECU responses into identifier fields. Decoded and stripped, and the count
  is reported.

---

## Status

Parsers run clean across the full corpus: 79/79 FES logs and 9/9 SCAN logs,
zero parse failures. The failure-type table carries 99 entries with per-entry
confidence and source, reconstructed from MES's own string table and validated
against ten corpus-confirmed anchors.

Requires Python 3.10+ and `mcp>=1.2.0`.
