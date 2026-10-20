# MES Integration

MultiEcuScan (MES) is a Windows bench tool for Fiat-group cars. CUORE does not replace it. It reads MES's logs, avoids fighting MES for the adapter, picks up what the mechanic did in MES, and fills the gaps MES does not cover.

## What MES is, and what it is not

MES has seven tabs: Info, Errors, Parameters, Graph, Actuators, Adjustments and Log. A gap analysis of its install and string table (2026-08-27) found:

- **It implements no generic OBD-II modes at all.** No readiness monitors, no Mode 06 results, no permanent codes, no freeze-frame mode. It can show "no fault codes" on a car whose EVAP monitor has never run since the last clear, and offers no way to tell the difference. CUORE reads exactly these.
- It *does* have live graphing, min and max values, and timestamped CSV recording (a workflow gap, not a capability gap).
- It does not do guided diagnostics, wiring, pinouts or service history, and cannot do ADAS calibration, module flashing or key work on this platform.
- Bi-directional control works only from a fixed list (for example clutch self-calibration, the purge valve, thermostat, turbo vacuum valve, service interval reset).

This is why the two are complementary: MES does manufacturer-protocol work and writes; CUORE does evidence capture, grading and memory.

## Log types parsed

| Type | File | Parser |
|---|---|---|
| FES session | `FESLog_*.txt` | `mes/fes.py` |
| SCAN report | `SCAN_*.txt` | `mes/scan.py` |
| CSV recording | MES CSV export | `mes/csvlog.py` |

Formats are described in [docs/format/](https://github.com/dangelojohn/CUORE/tree/main/docs/format). Log roots come from `MES_LOG_DIR(S)` and `MES_CSV_DIR(S)`; the default is MES's install directory, and file access is contained to the configured roots. CUORE's own exports (`<state>/scans/<vin>/`) appear as a second log root, tagged "cuore live export" and never flagged as simulation.

## Simulation detection

MES has a simulation mode that produces plausible-looking data with no vehicle. It must never be used as evidence.

- A **FES log** that is a simulation carries the banner "SIMULATION MODE ... THE DATA IS NOT REAL". `mes.fes` flags `simulation = True` and lists the *fingerprints*: a vehicle-identifier field holding a short number (not a VIN), an ECU ISO code of `7C 86 4F FF FF`, and impossible values such as a vehicle speed of 3240 km/h.
- A **SCAN log carries no simulation marker**. Its provenance is reported as *unverifiable*; the fingerprints are the only cue.
- Simulation logs are **excluded by default** from listing, selection and analysis, and are not copied into the data snapshot ([[Data Captured|Data-Captured]]).

On 2026-10-20 the **38 simulation-mode logs were removed from the captured data snapshot**: the snapshot now holds only logs that describe the car (42 files, see [[Data Captured|Data-Captured]]). The code reviews of the same day likewise exclude every simulation log, and a few older logs that carry a different car's identifier ([[Code Reviews|Code-Reviews]]).

Worked example: four MES files saved on 2026-10-20 were parsed and found to be simulations (random values across samples, battery pinned at 1.4 V). The ledger recorded "nothing new" and noted the files must not be cited for or against any hypothesis.

## Clear auto-sync

When the mechanic clears codes in MES, CUORE records it without being told. `mes_clear_watch.sync` (called from the job page) parses logs newer than the last sync. A SCAN log with clear-phase blocks, or a FES log with clear events, adds a `clear` action to the VIN's open job, dated to the log, naming what was cleared and the codes present first. Simulation logs and logs without a matching VIN are skipped, and re-syncing is idempotent. Two real-world wrinkles are handled: a clear block can appear twice in one file (an incomplete first attempt then a real success), and a blank result is resolved from evidence (whether the module's pre-clear codes are gone on the next read) rather than from the literal text.

The newest clear is searched across the whole corpus, not only within the latest FES session. An earlier version anchored the clear to the latest FES session and so reported a stale clear when the newest one was SCAN-only; fixed 2026-10-14.

## MES import

`/api/tests/{vin}/mes-import` and `/mes-scans` bring in a MES scan captured outside CUORE's own link, so it appears in the same scan log.

## MES-learn

`/v/{vin}/learn-mes` discovers data identifiers by **listening** to MES. A second adapter on a Y-splitter on CAN-C records MES's own requests and the module replies; a CSV recorded by MES is fitted against what was heard, by least squares over the whole session, nearest-time-matched, never interpolated. A candidate becomes confident only with R squared above a threshold over enough distinct values; otherwise it is "no confident match". Accepted candidates are saved as learned entries, never as catalogue entries. It never transmits and refuses unless the port is a different adapter.

## Interlock and handoff

- CUORE refuses to open the adapter while MES reports it is connected. See [[Hardware and Cables|Hardware-and-Cables]].
- Anything CUORE does not do (coding, configuration, actuator tests) is handed to MES through a **handoff card**: module, menu path, prerequisites. The result is then recorded in CUORE. See [[Safety Rules|Safety-Rules]].

## Other MES-related research in the repository

Capability comparison and gap notes: [MES_CAPABILITY_GAPS](https://github.com/dangelojohn/CUORE/blob/main/docs/research/MES_CAPABILITY_GAPS.md), [MES_VS_CUORE_CAPABILITY](https://github.com/dangelojohn/CUORE/blob/main/docs/research/MES_VS_CUORE_CAPABILITY_2026-10-14.md), [MES_INTEGRATION_SURFACE](https://github.com/dangelojohn/CUORE/blob/main/docs/research/MES_INTEGRATION_SURFACE.md), [MES_DEEP_INTEGRATION_REVIEW](https://github.com/dangelojohn/CUORE/blob/main/docs/research/MES_DEEP_INTEGRATION_REVIEW.md). A paddle-shift coding option was reviewed and decided against for CUORE (a modification, done in MES, not in CUORE).

Related: [[MCP Servers and Claude|MCP-Servers-and-Claude]], [[Evidence Model|Evidence-Model]].
