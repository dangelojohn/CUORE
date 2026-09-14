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

## `obd2-mcp` — tools

Live link to the adapter on the OBD port. Every tool opens the COM port for one
operation and releases it, so MultiEcuScan can take the adapter between calls;
MES's own status label is checked first and a connected MES blocks the open.
Port and speed come from explicit arguments, then `OBD_PORT` / `OBD_BAUD`, then
MES's `HKLM\SOFTWARE\Multiecuscan` Interface 0 settings. Headers stay on and
ISO-TP frames are reassembled here, so every answer is attributed to the ECU
that sent it. All tools return JSON and set `error` whenever a read did not
complete, so a bus fault never reads as "no codes".

| Tool | Purpose |
|---|---|
| `list_ports` | serial ports, with MES's configured port marked |
| `status` | resolved port/speed and their sources, MES state, lock state, last adapter identity |
| `mes_state` | is MES running and connected (read-only process + window-label probe) |
| `mes_settings` | MES's registry settings: interfaces, folders, CSV separator, recent vehicles |
| `connect` | probe: reset the adapter, read its identity, pin the protocol if the car answers; does not hold the port |
| `disconnect` | release anything held and forget the pinned protocol |
| `read_dtcs` / `read_pending_dtcs` / `read_permanent_dtcs` | Modes 03 / 07 / 0A, per ECU |
| `read_pid` | Mode 01 with J1979 formulas for 32 named PIDs |
| `read_voltage` | battery voltage at the OBD port (`ATRV`) |
| `read_supported_pids` | Mode 01 support bitmaps per ECU |
| `read_freeze_frame` | Mode 02 frame 0, decoded |
| `read_vin` | Mode 09 PID 02, reassembled |
| `read_readiness` | Mode 01 PID 01 / 41 monitors plus drive-cycle counters, with an EVAP verdict |
| `clear_dtcs` | Mode 04: captures codes, freeze frame and readiness to a file first, refuses while moving, reads back after |
| `send_raw` | one AT/ST/hex command; vehicle writes, adapter reconfiguration and monitor modes are gated |

Adapter on this bench: Vgate vLinker FS r2 (STN1170) on COM3 at 115200.

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
