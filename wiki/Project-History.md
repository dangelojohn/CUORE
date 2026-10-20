# Project History

A dated account assembled from the session records in [docs/sessions/](https://github.com/dangelojohn/CUORE/tree/main/docs/sessions) and the research and handbook notes. The project's own history document is [docs/project/HISTORY.md](https://github.com/dangelojohn/CUORE/blob/main/docs/project/HISTORY.md). Dates are the dates written in the source documents.

## Before the software (2025 to mid 2026)

- **2025-08:** the reference car's EVAP fault is already being worked: a new fuel cap and canister, and a first smoke test. These repairs are known from owner statements, not from a tool.
- **2025-09-24:** the first MultiEcuScan log of the car (P0456 stored).
- **2026-06-07:** the first MES scan reports for the car appear in the corpus.

## August to September 2026: research and a plan

- **2026-08-27:** a gap analysis of MES (it has no generic OBD modes: readiness, Mode 06 and permanent codes are absent) and a connectivity and security-gateway study. The study found that only eight modules appear in a no-cable scan because of **physical bus access**, not a software gap, and that two cables reach the other buses.
- **2026-09-01:** a first companion-app specification: a phone, tablet and watch companion to the toolchain, in three tiers (personal, shop, product), reusing the MES library.
- **2026-09-14:** the first Giorgio module map (confirmed, inferred and unverified addresses, and the structural finding that the three buses partition the modules); a code review of the project, a binary analysis of MES and a web research pass; a first web UI.
- **2026-09-26:** an EVAP smoke-test procedure by section is written, after the third smoke test.

## October 2026: the live link and the case

**2026-10-07:** the dossier and handbook structure; a mechanic user-experience review; the systems layer (25 systems), job workflow, timeline, media, parts, feedback and printable reports.

**2026-10-08:** tests surface and systems dive-in; job user-experience fixes.

**2026-10-13 (session archive):** the largest build day.
- The **first real reads from the car** through the adapter. Three live-layer problems were found and fixed: a gateway-silent bus needs an active probe; legislated OBD answered on the 29-bit route (opposite to an earlier assumption); and clearing the adapter's pass filters wiped its defaults so every reply read NO DATA.
- The full-scan orchestrator, scan log with diff and export, scan health report, live-board freeze-frame panel and the first scans.
- The mobile page was rejected on first pass and rebuilt to the same standard as the main app.
- Report and job pages were made much faster (about 30 s to 5 s, and 3.2 s to 0.3 s) with a shared cache.
- Case memory, the marque-port groundwork and several mechanic-facing reviews.
- Dozens of focused agent tasks were archived with their reports (the working method: a main model decides and reviews, lower-cost agents build).

**2026-10-14:**
- Modifications layer, **connect to car** (adapter to bus to VIN to guided scan), review 5 to 7 fixes, typography audit.
- A diagnosis tool for the engine lamp: found and fixed a bug where a clear done only through an MES scan was missed.
- CUORE's own logs made as queryable as MES's, with archive and integrity tools.
- An OBD connectivity review and performance work: held sessions, multi-PID batching, optional baud raise; research into sibling-platform bus data (nothing met the evidence bar).
- A paddle-shift coding option was reviewed and decided against for CUORE (modifications are done in MES).
- A durable archive and backup script, and a versioned pre-push hook.
- **Night of 2026-10-14:** the wrong-rate listen incident (see [[Safety Rules|Safety-Rules]]). It led to the confirmed-rate rule and the "no adapter scripts outside CUORE" rule.

**2026-10-15:** the chassis-bus work, recorded in [2026-10-15-chassis-bus-discoveries.md](https://github.com/dangelojohn/CUORE/blob/main/docs/sessions/2026-10-15-chassis-bus-discoveries.md): the passive listen had been blind (the monitor, not the car); 11-bit listen routes added; the **ABS was identified at address 0x2A** and an earlier assumption corrected; the ABS then went silent for reasons unknown; guided scans accept cables out of order; a timing bug in sweeps was fixed; a blue-cable session proved the IHS bus alive but no module answered. The bulletin catalogue was corrected the same day (a flash bulletin was found to be Giulia-only).

**2026-10-19:** the case document. The eleventh code clear in 53 days is found to have erased the engine computer's own freeze frames and Mode 06 for that night. Hypotheses were added, one was retracted after outside research, an outside cross-check, a verification pass and a readings-only ledger followed. Result: **no component proven faulty by a reading**; the ESIM sense and vent path is the test target; the standing order is not to clear again.

**2026-10-20:** a data snapshot of the car's state and logs is copied into `data/captures/` ([[Data Captured|Data-Captured]]); four MES files from that morning are examined and found to be simulations; the ESIM bench-test sheet is written; this wiki is assembled.

## Themes that run through the history

1. **The evidence rule grew from experience.** Each correction (three smoke tests rather than two; a Giulia-only bulletin; a "pass" that was a reset value) led to a rule that data, not assertion, carries conclusions.
2. **Tool faults are reported as tool faults.** Silent buses, NO DATA and timing bugs became first-class statuses instead of "nothing wrong".
3. **Safety moved from policy to code.** The incident turned a habit into enforced rules: one rate per bus, one door to the adapter, one audit trail.
4. **Marque data is kept out of code,** so the port to other brands is a data task.

Related: [[Roadmap]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].
