# CUORE

CUORE is a diagnostic workbench for the Alfa Romeo Giorgio platform. The
reference car is a 2018 Stelvio 2.0T. Alfa Romeo comes first; Maserati and
Ferrari models are planned later, with marque-specific data kept in
configuration and data files rather than in code.

It combines three things: a live link to the car through an OBD adapter, a
parser and analysis library for MultiEcuScan (MES) logs, and a web app that
puts both in front of a mechanic, one car at a time. See [CUORE.md](CUORE.md)
for the short statement of purpose.

**Status (2026-10-26):** the diagnosis layer, mechanic-first lists, the parts
catalogue sources and the first stage of the write path (read-only discovery
and dry run) are in place. Writing to the car is still done in MES.

## Core directive

**Diagnose on evidence. Prove the fix. Learn for the next car.**

- Every fact carries its date, its source and a confidence grade. Unknown is
  shown as unknown.
- A repair is verified only by proof from the car, not by the absence of codes.
- Every finished job can become a case, so the next car of the same model
  starts where the last one finished.
- CUORE advises and records. The mechanic decides.

## Data-only diagnosis

A conclusion in CUORE cites readings that were captured from the car (live
reads, MES logs, recordings). Material from outside the car is kept and
labelled as such: service bulletins, forum and video links, owner and
mechanic input, photos and notes. It can suggest what to check; it is never
shown as proof. The evidence gate (`diagnosis_verdict`, page `/v/{vin}/gate`)
refuses a confirmed verdict until the fault is demonstrated from captured
data, a mechanism is stated, a measurement implicates the part, and
disconfirmation was attempted.

## Three interfaces

1. **Web app.** FastAPI, server-rendered pages plus a JSON API under `/api`.
   Phone and tablet friendly. This is the main interface.
2. **Claude Code.** Two MCP servers expose the same data conversationally:
   `obd2-mcp` (live link) and `mes-log-mcp` (MES log analysis).
3. **Static artifact.** A point-in-time HTML summary of a vehicle (a checklist
   or report) that can be printed or shared. It is not connected to the car;
   regenerate it after new data is captured.

## Hardware

- An STN1170-based adapter on the car's OBD port, such as a vLinker FS. The
  serial port and speed come from arguments, the `CUORE_OBD_PORT` /
  `CUORE_OBD_BAUD` environment variables, or MES's registry settings.
- MES bypass cables for the buses the OBD port does not reach:
  **blue A5 = CAN-IHS (125 kbit/s)** and **grey A6 = CAN-CH (500 kbit/s)**.
  With no cable fitted, the OBD port reaches CAN-C.

## Quick start

Requires Python 3.10+. The virtual environment lives in `.venv` at the repo
root.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r cuore/requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File start-cuore.ps1 -Restart
```

`start-cuore.ps1` starts the server (restarting it first with `-Restart`) and
opens the browser at `http://127.0.0.1:5000`. Check it with
`http://127.0.0.1:5000/api/health`; the interactive API reference is at
`/api/docs`. To run it directly:

```
.venv\Scripts\python.exe -m cuore --profile bench --port 5000
```

The script binds to all interfaces so a phone on the same network can reach
it. The MES corpus contains vehicle identifiers, so set a token
(`--token` or `CUORE_TOKEN`) before exposing it beyond a trusted network.

Optional environment variables for the log corpus: `MES_LOG_DIR`,
`MES_LOG_DIRS` (several, `os.pathsep`-separated, first match wins),
`MES_CSV_DIR` / `MES_CSV_DIRS`. The default is MES's install directory.

## Feature tour

Each item below is described, with its routes and data sources, in
[docs/FEATURES.md](docs/FEATURES.md).

- **Connect and guided full scan.** A wizard that reads every bus the declared
  cable reaches and pauses at each cable swap, with a checklist of what each
  scan must capture.
- **Live board and dashboard.** A large-digit board for a passenger to watch,
  and a customisable gauge dashboard, both graded against known-good bands.
- **Scans and scan log.** Live reads grouped into scans that can be browsed,
  diffed and exported, plus a health report for each scan.
- **Jobs, hypotheses and mechanic steps.** One job per visit: complaint,
  hypotheses, ordered steps that cite their source, actions and verification.
- **Bulletins.** A catalogue of bulletins, recalls and campaigns, checked off
  per car and cross-referenced to the car's codes, repairs and hypotheses,
  with analogues from sibling engines labelled as such.
- **SLVT replica.** A read-only re-creation of the small leak verification
  procedure in bulletin 18-048-23.
- **Vehicle, dossier and systems.** The code history, freeze frames, a map of
  vehicle systems and their dependencies, and electrical and drivetrain pages.
- **Diagnosis layer.** On the Job, code, sensor and electrical pages: the
  likely common cause of the active faults, ranked suspects with the best next
  test, sensor cross-checks, an intermittent-fault correlator, trends, a
  power and ground budget, and similar faults from earlier cases (all in
  `cuore/services`: `common_cause`, `suspect_ranking`, `sensor_crosscheck`,
  `intermittent`, `trends`, `power_budget`, `fault_similarity`). Each panel
  cites captured readings or says it cannot.
- **Fault board and mechanic-first lists.** Every list follows
  [docs/design/CUORE_LIST_ORGANISATION.md](docs/design/CUORE_LIST_ORGANISATION.md):
  priority first, then most recent, groups folded behind a rotate arrow. The
  Job page opens on "Work on now" and the fault board (`fault_board`), where
  one tap marks a fault Fixed, then Verifying, and it becomes Proven fixed
  only when the car's own readings show it.
- **Modules, parts and service.** The module tree as MES shows it, service
  records, torque values, maintenance and labels, and a parts catalogue with
  four sources: the Mopar Stelvio catalogue, Autodoc UK aftermarket, Jeep
  Wrangler GME engine parts (schematics and interchange) and standard parts.
  The catalogue data is kept in CUORE's state directory, never in the repo.
- **Owner page.** A phone-first page where the owner or mechanic records what
  the car cannot report itself.
- **Learning tools.** Bus capture and signal learning, and DID discovery by
  listening to MES on a second adapter.
- **Media, feedback and reports.** Photos and video attached to the car,
  mechanic feedback on any shown fact, and printable or PDF reports.

## Safety rules

- **Read-only by design.** The diagnostic service allowlist is `10 01`, `19`,
  `22` and `3E`. The web app cannot write to the car. Writing is being
  earned in stages (see Write path below); nothing is enabled yet.
- **Never clear codes without consent.** A clear erases evidence and proves
  nothing; after a clear the monitors have not yet run. The one gated clear
  is on the MCP surface, with evidence capture, a speed check and a read-back.
- **CAN-CH transmit needs confirmation.** Passive listening comes first; any
  transmit on CAN-CH requires an explicit confirm.
- **One program holds the port.** CUORE checks MES's state and a lock file
  before opening the adapter; every operation opens the port, does its work and
  releases it.
- **Open a bus only at its confirmed rate.** On 2026-10-14 a bus was opened at
  a rate other than its confirmed one; since then each bus is opened only at
  the rate recorded for it.
- **No adapter scripts outside CUORE.** Adapter access goes through
  `cuore/live` so the lock, the cable declaration and the audit log apply.
- **Modifications are separate from diagnostics.** Coding and configuration
  are done in MES or wiTECH from a handoff card and then recorded in CUORE;
  CUORE does not perform them.

## Write path

Planned in [docs/design/CUORE_WRITE_CAPABILITY_PLAN.md](docs/design/CUORE_WRITE_CAPABILITY_PLAN.md):
MES makes the changes, CUORE does the thinking, and CUORE earns write ability
one low-risk procedure at a time. Built so far: read-only service-value
discovery (`discover_module_dids`), a dry-run harness that replays a captured
procedure through the real gate on a fake session (`cuore/live/procedure_dry_run.py`),
typed consent phrases for the gated clear, actuator and raw sends (MCP only),
serial-mirror capture prep ([docs/design/SERIAL_MIRROR_CAPTURE.md](docs/design/SERIAL_MIRROR_CAPTURE.md),
not yet set up), a lockable web login (`scripts/web_token.py`, with a login
rate limit) and a crawl ingest endpoint for allow-listed parts sites
(`scripts/ingest_token.py`, `/api/ingest`).

## Testing

- `cuore/tests/check_*.py`: web app, API, live link (including a playback
  stream that needs no hardware), pages and bridges.
- `mes-log-mcp/tests/check_*.py`: the MES library and MCP server, against the
  log corpus.
- `obd2-mcp/tests/`: the MCP wrapper.

Each check is a standalone plain script (no pytest): it prints its results
and exits non-zero on failure. Run one with the `.venv` interpreter, for
example `.venv\Scripts\python.exe cuore	ests\check_fault_board.py`.

## Repository layout

```
mcp-servers/
├── cuore/              FastAPI app (the web app)
│   ├── api/            JSON routes, mirroring the MCP tools
│   ├── live/           adapter transport, buses, reads, scans, stores
│   ├── services/       *_bridge.py view models; mes_bridge is the one
│   │                   module that imports the mes library for log analysis
│   ├── web/            page routes, Jinja templates, static files
│   ├── data/           bulletin catalogue, scan requirements
│   └── tests/
├── mes-log-mcp/        MES log library (mes/) and its MCP server
│   └── tests/
├── obd2-mcp/           MCP server for the live link
├── docs/               architecture, features, handbook, reference, research
├── scripts/            backup and session helpers
├── start-cuore.ps1     launch the server and open the browser
└── cuore-keepalive.ps1, install-cuore-autostart.ps1, make-cuore-shortcuts.ps1
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, files, how a scan runs,
  how evidence is graded.
- [docs/FEATURES.md](docs/FEATURES.md): every page and route group.
- [docs/design/](docs/design): list organisation, write-capability plan,
  serial-mirror capture and other design notes.
- [docs/handbook/](docs/handbook/README.md): decisions and rules, knowledge
  tables, methods, roadmap.
- [docs/reference/TSB_CATALOGUE.md](docs/reference/TSB_CATALOGUE.md): the
  bulletin catalogue in readable form.
- [docs/integration/](docs/integration/README.md): CUORE to AlfaCore file bundle,
  specs, and [the live deployment](docs/integration/ALFACORE_LIVE_DEPLOYMENT.md).
- [docs/handbook/esim/ESIM_Bench_Test_Stelvio.pdf](docs/handbook/esim/ESIM_Bench_Test_Stelvio.pdf):
  the bench test sheet for the ESIM.
- [CUORE.md](CUORE.md): purpose and maxim.

## MCP servers

`mes-log-mcp` parses MES logs (FES sessions, SCAN reports, CSV recordings) and
provides analysis: per-module status, code history across sessions, freeze
frames, the pre-work dossier, fault trees and the evidence gate. Simulation
logs are excluded by default, and SCAN provenance is reported as unverifiable
because that format carries no simulation marker. File access is contained to
the configured log roots.

`obd2-mcp` exposes the live link. Reads are requests to the running CUORE app,
so the cable declaration and bus verification are shared; only the gated
`clear_dtcs` and `send_raw` run in process.
