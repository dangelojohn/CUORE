# Alfa / Stellantis Diagnostic Toolchain

Local MCP servers and reference material for professional Alfa Romeo and
Stellantis diagnostics, built around **MultiEcuScan (MES)** and a live OBD-II
link.

Two MCP servers, one shared knowledge base.

```
mcp-servers/
├── mes-log-mcp/        MES log parsing, indexing and analysis  (MCP server)
│   ├── server.py       thin MCP tool surface
│   ├── mes/            the library - all parsing and analysis lives here
│   └── tests/          corpus smoke checks
├── obd2-mcp/           live ELM327 / OBD-II link              (MCP server)
└── docs/
    ├── format/         reverse-engineered MES file formats
    ├── reference/      corpus baseline, module catalog, DTC data
    └── research/       platform, tuning and connectivity research
```

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

### Configuration

| Variable | Meaning |
|---|---|
| `MES_LOG_DIR` | single log directory |
| `MES_LOG_DIRS` | several, `os.pathsep`-separated; first match wins |

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
